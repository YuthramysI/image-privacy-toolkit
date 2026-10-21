"""Objetivo C3 — Robust unlearnable: que la protección anti-entrenamiento
SOBREVIVA a su defensa conocida, el *adversarial training*.

Contexto. C1 (`unlearnable.py`) demostró que un ruido *error-minimizing* por
clase impide entrenar un clasificador útil (el modelo cree que no hay nada que
aprender). Su debilidad, documentada en la literatura: si quien entrena usa
**adversarial training** (entrena sobre versiones adversarialmente perturbadas),
puede recuperar parte de la utilidad de las fotos. C3 (Fu et al., "Robust
Unlearnable Examples", ICLR 2022) genera el ruido teniendo en cuenta esa
defensa, para que el atajo protector no se pueda limpiar con adversarial
training.

Experimento honesto, en CPU, con CUATRO condiciones y DOS regímenes de
entrenamiento, para aislar el efecto:

  Datos de entrenamiento:  LIMPIO · C1 (error-min) · C3 (robust) · ALEATORIO
  Entrenador (defensa):    ESTÁNDAR  y  ADVERSARIAL (la defensa)

Métrica: accuracy en el test LIMPIO. "Efecto neto" = acc(ALEATORIO) − acc(prot),
que aísla el ruido estructurado del simple ensuciado (mismo ε).

Criterio de éxito/fracaso (fijado ANTES de ver resultados):
  1. Con entrenador ESTÁNDAR, C1 y C3 deben proteger (efecto neto ≥ 15 pts):
     sanity de que ambos son no-aprendibles sin defensa.
  2. Con entrenador ADVERSARIAL, el efecto de C1 debe COLAPSAR (neto < 10 pts):
     reproduce la debilidad conocida.
  3. ÉXITO de C3 = su efecto neto SOBREVIVE al adversarial training
     (neto ≥ 15 pts) y supera claramente a C1 bajo la misma defensa.
  4. FRACASO = C3 también colapsa bajo adversarial training → resultado NEGATIVO
     honesto: el adversarial training vence incluso al robust unlearnable en este
     montaje (no extrapolar a Meta).

  python -m engine.research.unlearnable_robust --classes 4 --epsilon 8
"""

from __future__ import annotations

import argparse
import time

import numpy as np
import torch
import torch.nn.functional as F

from ..device import configure_threads
from .unlearnable import (
    SmallCNN,
    accuracy,
    error_minimizing_noise,
    jpeg_batch,
    load_subset,
    train,
)


def pgd_ascent(model, x, y, eps, steps, device="cpu"):
    """Perturbación adversarial (ascenso de pérdida) para un lote. Es lo que
    añade el DEFENSOR durante el adversarial training. BN en eval para no
    contaminar las estadísticas al generar el ataque."""
    was_training = model.training
    model.eval()
    alpha = 2.5 * eps / max(1, steps)
    delta = torch.empty_like(x).uniform_(-eps, eps)
    for _ in range(steps):
        delta.requires_grad_(True)
        loss = F.cross_entropy(model((x + delta).clamp(0, 1)), y)
        (g,) = torch.autograd.grad(loss, delta)
        with torch.no_grad():
            delta = (delta + alpha * g.sign()).clamp(-eps, eps)
    if was_training:
        model.train()
    return delta.detach()


def train_adv(model, x, y, epochs, eps_adv, steps, bs=128, lr=0.05, device="cpu"):
    """Adversarial training (Madry et al.): en cada lote, craftea una
    perturbación adversarial y entrena sobre ella. Es la defensa que intenta
    limpiar el ruido protector."""
    model.to(device)
    opt = torch.optim.SGD(model.parameters(), lr=lr, momentum=0.9, weight_decay=5e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, epochs)
    n = len(x)
    for _ in range(epochs):
        perm = torch.randperm(n)
        for i in range(0, n, bs):
            idx = perm[i : i + bs]
            xb, yb = x[idx].to(device), y[idx].to(device)
            delta = pgd_ascent(model, xb, yb, eps_adv, steps, device)
            model.train()
            opt.zero_grad()
            F.cross_entropy(model((xb + delta).clamp(0, 1)), yb).backward()
            opt.step()
        sched.step()
    return model


def robust_error_minimizing_noise(x, y, n_classes, eps, eps_adv, steps,
                                  device="cpu", rounds=4, inner=8, epochs_per_round=1):
    """Ruido *robust unlearnable* por clase. Como el error-minimizing de C1,
    pero (a) el surrogate se entrena adversarialmente y (b) el ruido se optimiza
    para minimizar la pérdida EN EL PUNTO ADVERSARIAL (x+δ+ρ), de modo que el
    atajo protector sobrevive a que el defensor añada su perturbación ρ.

    `epochs_per_round` controla cuánto se entrena el surrogate en cada ronda: con
    1 (default) reproduce la versión simplificada; subirlo (+ más `rounds`/`inner`)
    da la versión "fiel", donde el ruido se craftea contra un surrogate bien
    entrenado (Fu et al., ICLR 2022)."""
    model = SmallCNN(n_classes).to(device)
    noise = torch.zeros(n_classes, *x.shape[1:], device=device)
    for _ in range(rounds):
        # (a) adversarial training del surrogate sobre datos ya protegidos.
        # Optimizador fresco por ronda (idéntico a la versión simplificada con
        # epochs_per_round=1, para que el default siga siendo reproducible).
        model.train()
        opt = torch.optim.SGD(model.parameters(), lr=0.05, momentum=0.9)
        for _ in range(epochs_per_round):
            perm = torch.randperm(len(x))
            for i in range(0, len(x), 128):
                idx = perm[i : i + 128]
                yb = y[idx].to(device)
                xb = (x[idx].to(device) + noise[yb]).clamp(0, 1)
                rho = pgd_ascent(model, xb, yb, eps_adv, steps, device)
                model.train()
                opt.zero_grad()
                F.cross_entropy(model((xb + rho).clamp(0, 1)), yb).backward()
                opt.step()
        # (b) optimiza el ruido por clase para MINIMIZAR la pérdida adversarial
        model.eval()
        for c in range(n_classes):
            idx = (y == c).nonzero().squeeze(1)
            xb0 = x[idx].to(device)
            yb = y[idx].to(device)
            d = noise[c : c + 1].clone()
            for _ in range(inner):
                # el defensor craftea ρ sobre el punto actual (fijo para el grad de d)
                rho = pgd_ascent(model, (xb0 + d).clamp(0, 1), yb, eps_adv, steps, device)
                d.requires_grad_(True)
                xadv = (xb0 + d + rho).clamp(0, 1)
                loss = F.cross_entropy(model(xadv), yb)
                (g,) = torch.autograd.grad(loss, d)
                with torch.no_grad():
                    d = (d - eps / 4 * g.sign()).clamp(-eps, eps)  # descenso
            noise[c] = d.detach()[0]
    return noise


def net_effect(acc_rand, acc_prot):
    return (acc_rand - acc_prot) * 100


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--classes", type=int, default=4)
    ap.add_argument("--per-train", type=int, default=400)
    ap.add_argument("--per-test", type=int, default=200)
    ap.add_argument("--epochs", type=int, default=15)
    ap.add_argument("--epsilon", type=float, default=8.0, help="ε del ruido protector, en /255")
    ap.add_argument("--eps-adv", type=float, default=8.0, help="ε de la perturbación del defensor, en /255")
    ap.add_argument("--adv-steps", type=int, default=5, help="pasos PGD del adversarial training")
    # Minuciosidad de la generación del ruido C3 (robust). Defaults = versión
    # simplificada; subirlos = versión "fiel" (surrogate mejor entrenado).
    ap.add_argument("--c3-rounds", type=int, default=4)
    ap.add_argument("--c3-inner", type=int, default=8)
    ap.add_argument("--c3-epochs-per-round", type=int, default=1)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    configure_threads()
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    device = "cpu"
    eps = args.epsilon / 255
    eps_adv = args.eps_adv / 255

    print("cargando CIFAR...", flush=True)
    xtr, ytr, xte, yte = load_subset(args.classes, args.per_train, args.per_test)
    print(f"train {len(xtr)}  test {len(xte)}  clases {args.classes}  "
          f"ε={args.epsilon}/255  ε_adv={args.eps_adv}/255  adv_steps={args.adv_steps}", flush=True)

    t0 = time.time()
    print("generando ruido C1 (error-minimizing)...", flush=True)
    noise_c1 = error_minimizing_noise(xtr, ytr, args.classes, eps, device)
    print(f"  C1 listo ({time.time()-t0:.0f}s). Generando ruido C3 (robust, con adversarial training)...", flush=True)
    t1 = time.time()
    noise_c3 = robust_error_minimizing_noise(
        xtr, ytr, args.classes, eps, eps_adv, args.adv_steps, device,
        rounds=args.c3_rounds, inner=args.c3_inner, epochs_per_round=args.c3_epochs_per_round)
    print(f"  C3 listo ({time.time()-t1:.0f}s).", flush=True)

    rnd = (torch.rand_like(noise_c1) * 2 - 1) * eps
    datasets = {
        "LIMPIO": xtr,
        "C1": (xtr + noise_c1[ytr]).clamp(0, 1),
        "C3": (xtr + noise_c3[ytr]).clamp(0, 1),
        "ALEATORIO": (xtr + rnd[ytr]).clamp(0, 1),
    }

    def run(trainer_name, trainer):
        print(f"\n=== Entrenador {trainer_name} ===", flush=True)
        accs = {}
        for name, data in datasets.items():
            torch.manual_seed(args.seed)
            ts = time.time()
            m = trainer(SmallCNN(args.classes), data, ytr)
            accs[name] = accuracy(m, xte, yte, device=device)
            print(f"  {name:10s} acc test LIMPIO: {accs[name]*100:5.1f}%  ({time.time()-ts:.0f}s)", flush=True)
        return accs

    std = run("ESTÁNDAR", lambda m, d, yy: train(m, d, yy, args.epochs, device=device))
    adv = run("ADVERSARIAL (defensa)",
              lambda m, d, yy: train_adv(m, d, yy, args.epochs, eps_adv, args.adv_steps, device=device))

    # Efecto neto = acc(ALEATORIO) − acc(protegido), mismo régimen
    print("\n================= RESUMEN (efecto neto = aleatorio − protegido) =================", flush=True)
    rows = []
    for cond in ("C1", "C3"):
        ne_std = net_effect(std["ALEATORIO"], std[cond])
        ne_adv = net_effect(adv["ALEATORIO"], adv[cond])
        rows.append((cond, ne_std, ne_adv))
        print(f"  {cond}:  neto ESTÁNDAR {ne_std:5.1f} pts   |   neto ADVERSARIAL {ne_adv:5.1f} pts", flush=True)
    print(f"\n  (acc LIMPIO: estándar {std['LIMPIO']*100:.1f}%, adversarial {adv['LIMPIO']*100:.1f}%; "
          f"azar {100/args.classes:.0f}%)", flush=True)

    c1_std, c1_adv = rows[0][1], rows[0][2]
    c3_std, c3_adv = rows[1][1], rows[1][2]
    # Criterio fijado a priori
    sanity = c1_std >= 15 and c3_std >= 15
    c1_collapses = c1_adv < 10
    c3_survives = c3_adv >= 15 and c3_adv >= c1_adv + 8
    print("\n--- Veredicto (criterio fijado antes de ver resultados) ---", flush=True)
    print(f"  1. Sanity sin defensa (C1,C3 ≥15 pts): {'OK' if sanity else 'NO'}", flush=True)
    print(f"  2. C1 colapsa con adversarial training (<10 pts): {'OK' if c1_collapses else 'NO'} ({c1_adv:.1f})", flush=True)
    print(f"  3. C3 sobrevive (≥15 pts y supera a C1 por ≥8): {'OK' if c3_survives else 'NO'} ({c3_adv:.1f} vs {c1_adv:.1f})", flush=True)
    if sanity and c3_survives:
        verdict = "C3 FUNCIONA: el robust unlearnable sobrevive al adversarial training donde C1 no."
    elif sanity and c1_collapses and not c3_survives:
        verdict = "NEGATIVO HONESTO: el adversarial training también vence a C3 en este montaje."
    else:
        verdict = "NO CONCLUYENTE: revisar (sanity o controles no se cumplen)."
    print(f"  => {verdict}", flush=True)


if __name__ == "__main__":
    main()
