"""Ajuste de calidad de la protección contra entrenamiento (objetivo C).

Barre ε y compara ruido uniforme (clamp ±ε) vs ruido con presupuesto perceptual
JND (reparte el ruido fuera de zonas lisas), midiendo a la vez:
  - eficacia: efecto NETO = accuracy(ALEATORIO por-imagen) − accuracy(PROTEGIDO)
    en reconocimiento de identidad, transfer learning ResNet18 (ver
    unlearnable_faces para el montaje y los controles).
  - calidad: PSNR y LPIPS medios.
Objetivo: la configuración con mejor equilibrio protección/imperceptibilidad.

  python -m engine.research.unlearnable_quality
"""

from __future__ import annotations

import argparse
import time

import numpy as np
import torch
import torch.nn.functional as F

from ..device import configure_threads
from ..protect import budget
from .unlearnable import SmallCNN
from .unlearnable_faces import Backbone, jpeg_batch, linprobe, load_faces, quality


def noise_uniform(x, y, nc, eps, rounds=5, inner=10):
    """Ruido error-minimizing por clase, acotado uniformemente a ±eps."""
    m = SmallCNN(nc)
    noise = torch.zeros(nc, *x.shape[1:])
    for _ in range(rounds):
        m.train()
        opt = torch.optim.SGD(m.parameters(), lr=0.05, momentum=0.9)
        perm = torch.randperm(len(x))
        for i in range(0, len(x), 128):
            idx = perm[i : i + 128]
            xb = (x[idx] + noise[y[idx]]).clamp(0, 1)
            opt.zero_grad()
            F.cross_entropy(m(xb), y[idx]).backward()
            opt.step()
        m.eval()
        for c in range(nc):
            idx = (y == c).nonzero().squeeze(1)
            d = noise[c : c + 1].clone().requires_grad_(True)
            for _ in range(inner):
                loss = F.cross_entropy(m((x[idx] + d).clamp(0, 1)), y[idx])
                (g,) = torch.autograd.grad(loss, d)
                with torch.no_grad():
                    d -= eps / 4 * g.sign()
                    d.clamp_(-eps, eps)
            noise[c] = d.detach()[0]
    return noise[y]  # expand a per-imagen


def noise_jnd(x, y, nc, eps, rounds=5, inner=10):
    """Ruido error-minimizing POR IMAGEN, acotado por el presupuesto JND de cada
    imagen (reparte el ruido fuera de la piel lisa -> más imperceptible)."""
    m = SmallCNN(nc)
    emaps = torch.cat([budget.jnd_eps_map(x[i : i + 1], eps) for i in range(len(x))])
    delta = torch.zeros_like(x)
    for _ in range(rounds):
        m.train()
        opt = torch.optim.SGD(m.parameters(), lr=0.05, momentum=0.9)
        perm = torch.randperm(len(x))
        for i in range(0, len(x), 128):
            idx = perm[i : i + 128]
            xb = (x[idx] + delta[idx]).clamp(0, 1)
            opt.zero_grad()
            F.cross_entropy(m(xb), y[idx]).backward()
            opt.step()
        m.eval()
        for i in range(0, len(x), 128):
            idx = slice(i, i + 128)
            d = delta[idx].clone().requires_grad_(True)
            for _ in range(inner):
                loss = F.cross_entropy(m((x[idx] + d).clamp(0, 1)), y[idx])
                (g,) = torch.autograd.grad(loss, d)
                with torch.no_grad():
                    d -= eps / 4 * g.sign()
                    d.copy_(torch.maximum(torch.minimum(d, emaps[idx]), -emaps[idx]))
            delta[idx] = d.detach()
    return delta


def lpips_mean(clean, prot, model):
    with torch.no_grad():
        return float(model(clean * 2 - 1, prot.clamp(0, 1) * 2 - 1).mean())


def evaluate(x, y, xte, yte, nc, bk, noise_fn, eps, lp):
    t = time.time()
    delta = noise_fn(x, y, nc, eps)
    gen = time.time() - t
    xprot = (x + delta).clamp(0, 1)
    xrand = (x + (torch.rand_like(x) * 2 - 1) * eps).clamp(0, 1)
    fte = bk.feats(xte)
    prot_acc = linprobe(bk.feats(xprot), y, fte, yte, nc)[0]
    rand_acc = linprobe(bk.feats(xrand), y, fte, yte, nc)[0]
    jpg_acc = linprobe(bk.feats(jpeg_batch(xprot)), y, fte, yte, nc)[0]
    return {
        "neto": (rand_acc - prot_acc) * 100,
        "prot": prot_acc * 100,
        "rand": rand_acc * 100,
        "jpeg": jpg_acc * 100,
        "psnr": quality(x, xprot),
        "lpips": lpips_mean(x, xprot, lp),
        "gen_s_img": gen / len(x),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--identities", type=int, default=20)
    ap.add_argument("--train-per", type=int, default=7)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--eps-list", type=float, nargs="+", default=[2, 4, 6, 8])
    args = ap.parse_args()

    configure_threads()
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    import lpips as _l

    lp = _l.LPIPS(net="alex", verbose=False)
    print("cargando ResNet18 + rostros...", flush=True)
    bk = Backbone()
    x, y, xte, yte = load_faces(args.identities, args.train_per, args.seed)
    clean_acc = linprobe(bk.feats(x), y, bk.feats(xte), yte, args.identities)[0] * 100
    print(f"LIMPIO identidad acc: {clean_acc:.1f}%  (azar {100/args.identities:.0f}%)\n", flush=True)

    print(f"{'config':20s} {'neto':>6s} {'prot':>6s} {'rand':>6s} {'jpeg':>6s} {'PSNR':>6s} {'LPIPS':>7s} {'s/img':>6s}")
    for name, fn in (("uniforme", noise_uniform), ("JND", noise_jnd)):
        for eps in args.eps_list:
            torch.manual_seed(args.seed)
            r = evaluate(x, y, xte, yte, args.identities, bk, fn, eps / 255, lp)
            print(f"{name+' ε='+str(int(eps)):20s} {r['neto']:6.1f} {r['prot']:6.1f} {r['rand']:6.1f} "
                  f"{r['jpeg']:6.1f} {r['psnr']:6.1f} {r['lpips']:7.4f} {r['gen_s_img']:6.2f}", flush=True)
    print("\nMejor equilibrio = mayor 'neto' con PSNR alto / LPIPS bajo. neto = rand−prot (efecto del mecanismo).")


if __name__ == "__main__":
    main()
