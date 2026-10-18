"""Objetivo C — Reducir la utilidad de las imágenes para ENTRENAR modelos.

Mecanismo NUEVO (opuesto a todo lo anterior): ejemplos no aprendibles con ruido
que MINIMIZA el error (Huang et al., ICLR 2021). En vez de alejar embeddings, el
ruido hace que el modelo crea que no hay nada que aprender, así que no generaliza
a datos limpios. Es la protección contra "entrenar con tus fotos" (caso Meta).

Experimento honesto, en CPU, con controles:
  - LIMPIO     : entrenar un clasificador con datos sin tocar (referencia alta).
  - PROTEGIDO  : entrenar con datos + ruido no-aprendible (debería caer mucho).
  - ALEATORIO  : entrenar con datos + ruido aleatorio del mismo tamaño (control:
                 debería NO proteger; aísla el efecto del ruido estructurado).
Métrica: accuracy en el conjunto de prueba LIMPIO. Protección = PROTEGIDO cae
muy por debajo de LIMPIO, y ALEATORIO no.

Robustez: se repite evaluando tras JPEG (si la recompresión elimina el efecto,
la protección no sobrevive a una subida a redes).

  python -m engine.research.unlearnable --classes 5 --epsilon 8
"""

from __future__ import annotations

import argparse
import io
import os
import tempfile
import time

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image

from ..device import configure_threads


class SmallCNN(nn.Module):
    """CNN pequeña (ResNet-ish ligera) viable en CPU."""

    def __init__(self, n_classes: int):
        super().__init__()
        def block(i, o):
            return nn.Sequential(nn.Conv2d(i, o, 3, padding=1), nn.BatchNorm2d(o), nn.ReLU(), nn.Conv2d(o, o, 3, padding=1), nn.BatchNorm2d(o), nn.ReLU(), nn.MaxPool2d(2))
        self.net = nn.Sequential(block(3, 32), block(32, 64), block(64, 128), nn.AdaptiveAvgPool2d(1), nn.Flatten(), nn.Linear(128, n_classes))

    def forward(self, x):
        return self.net(x)


def load_subset(n_classes: int, per_class_train: int, per_class_test: int):
    import torchvision

    # Dónde descargar/cachear CIFAR. Configurable; por defecto, una carpeta local
    # temporal (no se versiona, ver .gitignore).
    root = os.environ.get("IPT_DATA_DIR", os.path.join(tempfile.gettempdir(), "ipt-cifar"))
    tr = torchvision.datasets.CIFAR10(root, train=True, download=True)
    te = torchvision.datasets.CIFAR10(root, train=False, download=True)

    def take(ds, per):
        xs, ys = [], []
        counts = {c: 0 for c in range(n_classes)}
        for img, y in zip(ds.data, ds.targets):
            if y < n_classes and counts[y] < per:
                xs.append(img)
                ys.append(y)
                counts[y] += 1
        return np.stack(xs).astype(np.float32) / 255.0, np.array(ys)

    xtr, ytr = take(tr, per_class_train)
    xte, yte = take(te, per_class_test)
    # (N,H,W,C) -> (N,C,H,W)
    to_t = lambda a: torch.from_numpy(a).permute(0, 3, 1, 2).contiguous()
    return to_t(xtr), torch.from_numpy(ytr), to_t(xte), torch.from_numpy(yte)


def train(model, x, y, epochs, bs=128, lr=0.05, device="cpu"):
    model.train().to(device)
    opt = torch.optim.SGD(model.parameters(), lr=lr, momentum=0.9, weight_decay=5e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, epochs)
    n = len(x)
    for _ in range(epochs):
        perm = torch.randperm(n)
        for i in range(0, n, bs):
            idx = perm[i : i + bs]
            opt.zero_grad()
            loss = F.cross_entropy(model(x[idx].to(device)), y[idx].to(device))
            loss.backward()
            opt.step()
        sched.step()
    return model


@torch.no_grad()
def accuracy(model, x, y, bs=256, device="cpu"):
    model.eval()
    correct = 0
    for i in range(0, len(x), bs):
        pred = model(x[i : i + bs].to(device)).argmax(1).cpu()
        correct += (pred == y[i : i + bs]).sum().item()
    return correct / len(x)


def error_minimizing_noise(x, y, n_classes, eps, device="cpu", rounds=4, inner=8):
    """Ruido que minimiza el error del surrogate (clase-wise). Se alterna entre
    entrenar el surrogate y optimizar el ruido para bajar su pérdida."""
    model = SmallCNN(n_classes).to(device)
    # Ruido por clase: una perturbación compartida por cada clase (robusta, no
    # se evita con early stopping, según el paper).
    noise = torch.zeros(n_classes, *x.shape[1:], device=device)
    for _ in range(rounds):
        # entrena el surrogate sobre datos ya perturbados
        model.train()
        opt = torch.optim.SGD(model.parameters(), lr=0.05, momentum=0.9)
        perm = torch.randperm(len(x))
        for i in range(0, len(x), 128):
            idx = perm[i : i + 128]
            xb = (x[idx].to(device) + noise[y[idx].to(device)]).clamp(0, 1)
            opt.zero_grad()
            F.cross_entropy(model(xb), y[idx].to(device)).backward()
            opt.step()
        # optimiza el ruido para MINIMIZAR la pérdida (PGD descendente)
        model.eval()
        for c in range(n_classes):
            idx = (y == c).nonzero().squeeze(1)
            d = noise[c : c + 1].clone().requires_grad_(True)
            for _ in range(inner):
                xb = (x[idx].to(device) + d).clamp(0, 1)
                loss = F.cross_entropy(model(xb), y[idx].to(device))
                (g,) = torch.autograd.grad(loss, d)
                with torch.no_grad():
                    d -= eps / 4 * g.sign()  # descenso: baja la pérdida
                    d.clamp_(-eps, eps)
            noise[c] = d.detach()[0]
    return noise


def jpeg_batch(x, quality=85):
    out = []
    for img in x:
        arr = (img.permute(1, 2, 0).numpy() * 255).astype(np.uint8)
        buf = io.BytesIO()
        Image.fromarray(arr).save(buf, "JPEG", quality=quality)
        out.append(np.asarray(Image.open(io.BytesIO(buf.getvalue())).convert("RGB"), np.float32) / 255)
    return torch.from_numpy(np.stack(out)).permute(0, 3, 1, 2).contiguous()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--classes", type=int, default=5)
    ap.add_argument("--per-train", type=int, default=800)
    ap.add_argument("--per-test", type=int, default=400)
    ap.add_argument("--epochs", type=int, default=25)
    ap.add_argument("--epsilon", type=float, default=8.0, help="niveles de 255")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    configure_threads()
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    device = "cpu"
    eps = args.epsilon / 255

    print("cargando CIFAR...", flush=True)
    xtr, ytr, xte, yte = load_subset(args.classes, args.per_train, args.per_test)
    print(f"train {len(xtr)}  test {len(xte)}  clases {args.classes}", flush=True)

    t0 = time.time()
    print("generando ruido no-aprendible (error-minimizing)...", flush=True)
    noise = error_minimizing_noise(xtr, ytr, args.classes, eps, device)
    xtr_prot = (xtr + noise[ytr]).clamp(0, 1)
    rnd = (torch.rand_like(noise) * 2 - 1) * eps
    xtr_rand = (xtr + rnd[ytr]).clamp(0, 1)
    print(f"ruido listo ({time.time()-t0:.0f}s). ε={args.epsilon}/255. Entrenando clasificadores desde cero...", flush=True)

    results = {}
    for name, data in (("LIMPIO", xtr), ("PROTEGIDO", xtr_prot), ("ALEATORIO", xtr_rand)):
        torch.manual_seed(args.seed)
        m = train(SmallCNN(args.classes), data, ytr, args.epochs, device=device)
        acc = accuracy(m, xte, yte, device=device)
        acc_jpeg = None
        if name == "PROTEGIDO":
            # robustez: entrenar con la versión protegida recomprimida (JPEG)
            torch.manual_seed(args.seed)
            mj = train(SmallCNN(args.classes), jpeg_batch(data), ytr, args.epochs, device=device)
            acc_jpeg = accuracy(mj, xte, yte, device=device)
        results[name] = (acc, acc_jpeg)
        extra = f"  | tras JPEG85: {acc_jpeg*100:.1f}%" if acc_jpeg is not None else ""
        print(f"  {name:10s} accuracy test LIMPIO: {acc*100:.1f}%{extra}", flush=True)

    clean = results["LIMPIO"][0]
    prot = results["PROTEGIDO"][0]
    rand = results["ALEATORIO"][0]
    chance = 100 / args.classes
    print(f"\nReferencia azar: {chance:.0f}%")
    print(f"Protección (caída vs limpio): {(clean-prot)*100:.1f} puntos. Control aleatorio: {(clean-rand)*100:.1f} puntos.")
    verdict = "FUNCIONA" if (prot < clean - 0.15 and rand > clean - 0.1) else "no concluyente/no protege"
    print(f"Veredicto: {verdict}  (protege si PROTEGIDO cae mucho y ALEATORIO no)")


if __name__ == "__main__":
    main()
