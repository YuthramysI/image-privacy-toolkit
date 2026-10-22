"""¿La protección anti-entrenamiento en ROSTROS REALES sobrevive al adversarial
training? (extensión de unlearnable_faces.py con la defensa del atacante)

Montaje: Olivetti (rostros reales), transfer learning sobre ResNet18 preentrenado
congelado + linear probe. La protección es C1 (error-minimizing). Se compara el
probe entrenado de forma ESTÁNDAR vs ADVERSARIAL (el atacante añade una
perturbación PGD en píxeles, a través del ResNet, al entrenar el probe).

Es el análogo en rostros de `unlearnable_robust.py` (que lo midió en CIFAR y
encontró que el adversarial training vence la protección). Aquí se comprueba en
el caso de uso real: que no entrenen un reconocedor de TU cara.

Controles: LIMPIO · PROTEGIDO (C1) · ALEATORIO (ruido por imagen). Métrica:
accuracy de identidad en test limpio; efecto neto = aleatorio − protegido.

  python -m engine.research.unlearnable_faces_adv --identities 15 --eps-adv 8
"""

from __future__ import annotations

import argparse
import time

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from ..device import configure_threads
from .unlearnable import error_minimizing_noise
from .unlearnable_faces import Backbone, load_faces


def _norm_in(bk, x, size=128):
    b = F.interpolate(x, size=(size, size), mode="bilinear", antialias=True, align_corners=False)
    return (b - bk.mean) / bk.std


def feats_grad(bk, x, size=128):
    """Features CON gradiente hacia la entrada (para el ataque PGD). El ResNet
    está congelado (sin grad de parámetros) pero el gradiente fluye al input."""
    return bk.m(_norm_in(bk, x, size))


@torch.no_grad()
def feats_nograd(bk, x, size=128, bs=64):
    out = []
    for i in range(0, len(x), bs):
        out.append(bk.m(_norm_in(bk, x[i : i + bs], size)))
    return torch.cat(out)


def pgd_input(bk, clf, x, y, mu, sd, eps, steps):
    """Perturbación adversarial en píxeles que MAXIMIZA la pérdida del probe."""
    alpha = 2.5 * eps / max(1, steps)
    delta = torch.empty_like(x).uniform_(-eps, eps)
    for _ in range(steps):
        delta.requires_grad_(True)
        f = (feats_grad(bk, (x + delta).clamp(0, 1)) - mu) / sd
        loss = F.cross_entropy(clf(f), y)
        (g,) = torch.autograd.grad(loss, delta)
        with torch.no_grad():
            delta = (delta + alpha * g.sign()).clamp(-eps, eps)
    return delta.detach()


def linprobe(bk, data, ytr, xte, yte, nc, epochs, adv=False, eps_adv=0.0, steps=3):
    # Normalización POR-DATASET desde las features limpias de 'data' (método
    # validado en unlearnable_faces.py). mu/sd se calculan de los datos que el
    # atacante realmente tiene, no del limpio.
    fdata = feats_nograd(bk, data)
    mu, sd = fdata.mean(0, keepdim=True), fdata.std(0, keepdim=True) + 1e-6
    fte = (feats_nograd(bk, xte) - mu) / sd
    ftr_std = (fdata - mu) / sd
    clf = nn.Linear(mu.shape[1], nc)
    opt = torch.optim.Adam(clf.parameters(), lr=0.01, weight_decay=1e-3)
    for _ in range(epochs):
        perm = torch.randperm(len(data))
        for i in range(0, len(data), 128):
            idx = perm[i : i + 128]
            if adv:
                rho = pgd_input(bk, clf, data[idx], ytr[idx], mu, sd, eps_adv, steps)
                f = (feats_nograd(bk, (data[idx] + rho).clamp(0, 1)) - mu) / sd
            else:
                f = ftr_std[idx]
            opt.zero_grad()
            F.cross_entropy(clf(f), ytr[idx]).backward()
            opt.step()
    with torch.no_grad():
        return (clf(fte).argmax(1) == yte).float().mean().item()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--identities", type=int, default=15)
    ap.add_argument("--train-per", type=int, default=7)
    ap.add_argument("--epsilon", type=float, default=8.0, help="ε de la protección, /255")
    ap.add_argument("--eps-adv", type=float, default=8.0, help="ρ del defensor, /255")
    ap.add_argument("--adv-steps", type=int, default=3)
    ap.add_argument("--epochs-std", type=int, default=120)
    ap.add_argument("--epochs-adv", type=int, default=40)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    configure_threads()
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    eps = args.epsilon / 255
    eps_adv = args.eps_adv / 255
    nc = args.identities
    chance = 100 / nc

    print(f"ROSTROS (Olivetti) · {nc} identidades · ε={args.epsilon} ρ={args.eps_adv} · ResNet18 linear probe", flush=True)
    bk = Backbone()
    xtr, ytr, xte, yte = load_faces(nc, args.train_per, args.seed)
    print(f"train {len(xtr)} test {len(xte)}  (azar {chance:.0f}%)", flush=True)

    t = time.time()
    noise = error_minimizing_noise(xtr, ytr, nc, eps, rounds=5, inner=10)
    print(f"ruido C1 listo ({time.time()-t:.0f}s)", flush=True)
    xprot = (xtr + noise[ytr]).clamp(0, 1)
    xrand = (xtr + (torch.rand_like(xtr) * 2 - 1) * eps).clamp(0, 1)

    datasets = {"LIMPIO": xtr, "PROTEGIDO": xprot, "ALEATORIO": xrand}
    res = {}
    for mode, adv in (("ESTÁNDAR", False), ("ADVERSARIAL", True)):
        print(f"\n=== Probe {mode} ===", flush=True)
        res[mode] = {}
        ep = args.epochs_adv if adv else args.epochs_std
        for name, data in datasets.items():
            ts = time.time()
            acc = linprobe(bk, data, ytr, xte, yte, nc, ep, adv=adv, eps_adv=eps_adv, steps=args.adv_steps)
            res[mode][name] = acc
            print(f"  {name:10s} identidad acc: {acc*100:5.1f}%  ({time.time()-ts:.0f}s)", flush=True)

    print("\n================= RESUMEN (efecto neto = aleatorio − protegido) =================", flush=True)
    for mode in ("ESTÁNDAR", "ADVERSARIAL"):
        neto = (res[mode]["ALEATORIO"] - res[mode]["PROTEGIDO"]) * 100
        print(f"  {mode:12s}: neto {neto:5.1f} pts  (limpio {res[mode]['LIMPIO']*100:.1f}%, prot {res[mode]['PROTEGIDO']*100:.1f}%, aleat {res[mode]['ALEATORIO']*100:.1f}%)", flush=True)
    ne_std = (res["ESTÁNDAR"]["ALEATORIO"] - res["ESTÁNDAR"]["PROTEGIDO"]) * 100
    ne_adv = (res["ADVERSARIAL"]["ALEATORIO"] - res["ADVERSARIAL"]["PROTEGIDO"]) * 100
    print(f"\n  Efecto estándar {ne_std:.1f} pts -> adversarial {ne_adv:.1f} pts", flush=True)
    if ne_std >= 15 and ne_adv < 10:
        v = "NEGATIVO: el adversarial training también vence la protección en ROSTROS (como en CIFAR)."
    elif ne_std >= 15 and ne_adv >= 15:
        v = "La protección en rostros SOBREVIVE al adversarial training (distinto de CIFAR)."
    else:
        v = "NO CONCLUYENTE (revisar sanity/controles)."
    print(f"  => {v}", flush=True)


if __name__ == "__main__":
    main()
