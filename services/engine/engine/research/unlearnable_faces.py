"""Validación de unlearnable examples con ROSTROS REALES y TRANSFER LEARNING.

Dataset: Olivetti (AT&T Cambridge), rostros reales recolectados con
consentimiento de los participantes para investigación. 40 identidades x 10.
Tarea: reconocimiento de identidad (clasificar entre N personas) — lo que
protegería a alguien de que entrenen un modelo que reconozca su cara.

Escenario: transfer learning sobre ResNet18 preentrenado (ImageNet, NO usado
para generar el ruido) — linear probe sobre sus features. Es como entrena la
industria. El ruido se genera con un surrogate pequeño distinto.

Criterio de éxito fijado a priori (ver docs/MATRIZ_INVESTIGACION.md).

  python -m engine.research.unlearnable_faces --identities 20 --seeds 2
"""

from __future__ import annotations

import argparse
import io
import time

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image

from ..device import configure_threads
from .unlearnable import SmallCNN, error_minimizing_noise


def load_faces(n_identities: int, train_per: int, seed: int):
    from sklearn.datasets import fetch_olivetti_faces

    d = fetch_olivetti_faces(shuffle=False)
    imgs = torch.from_numpy(d.images).float()  # (400,64,64) en [0,1]
    y = torch.from_numpy(d.target.astype(np.int64))
    rng = np.random.default_rng(seed)
    xs_tr, ys_tr, xs_te, ys_te = [], [], [], []
    for pid in range(n_identities):
        idx = (y == pid).nonzero().squeeze(1).numpy()
        rng.shuffle(idx)
        tr, te = idx[:train_per], idx[train_per:]
        for i in tr:
            xs_tr.append(imgs[i]); ys_tr.append(pid)
        for i in te:
            xs_te.append(imgs[i]); ys_te.append(pid)
    to3 = lambda s: torch.stack(s).unsqueeze(1).repeat(1, 3, 1, 1)  # gris -> RGB
    return to3(xs_tr), torch.tensor(ys_tr), to3(xs_te), torch.tensor(ys_te)


def jpeg_batch(x, quality=85):
    out = []
    for img in x:
        arr = (img.permute(1, 2, 0).numpy() * 255).astype(np.uint8)
        buf = io.BytesIO()
        Image.fromarray(arr).save(buf, "JPEG", quality=quality)
        out.append(np.asarray(Image.open(io.BytesIO(buf.getvalue())).convert("RGB"), np.float32) / 255)
    return torch.from_numpy(np.stack(out)).permute(0, 3, 1, 2).contiguous()


class Backbone:
    def __init__(self):
        from torchvision.models import ResNet18_Weights, resnet18

        self.m = resnet18(weights=ResNet18_Weights.IMAGENET1K_V1).eval()
        self.m.fc = nn.Identity()
        for p in self.m.parameters():
            p.requires_grad_(False)
        self.mean = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
        self.std = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)

    def feats(self, x, size=128, bs=64):
        out = []
        for i in range(0, len(x), bs):
            b = F.interpolate(x[i : i + bs], size=(size, size), mode="bilinear", antialias=True, align_corners=False)
            b = (b - self.mean) / self.std
            with torch.no_grad():
                out.append(self.m(b))
        return torch.cat(out)


def linprobe(ftr, ytr, fte, yte, nc, epochs=120):
    clf = nn.Linear(ftr.shape[1], nc)
    opt = torch.optim.Adam(clf.parameters(), lr=0.01, weight_decay=1e-3)
    mu, sd = ftr.mean(0, keepdim=True), ftr.std(0, keepdim=True) + 1e-6
    ftr, fte = (ftr - mu) / sd, (fte - mu) / sd
    for _ in range(epochs):
        perm = torch.randperm(len(ftr))
        for i in range(0, len(ftr), 128):
            idx = perm[i : i + 128]
            opt.zero_grad()
            F.cross_entropy(clf(ftr[idx]), ytr[idx]).backward()
            opt.step()
    with torch.no_grad():
        tr_acc = (clf(ftr).argmax(1) == ytr).float().mean().item()
        te_acc = (clf(fte).argmax(1) == yte).float().mean().item()
    return te_acc, tr_acc


def quality(clean, prot):
    from skimage.metrics import peak_signal_noise_ratio as psnr

    a = clean.permute(0, 2, 3, 1).numpy()
    b = prot.permute(0, 2, 3, 1).numpy()
    return float(np.mean([psnr(a[i], b[i], data_range=1) for i in range(len(a))]))


def run_once(n_id, train_per, eps, seed, bk):
    torch.manual_seed(seed)
    np.random.seed(seed)
    xtr, ytr, xte, yte = load_faces(n_id, train_per, seed)
    t = time.time()
    noise = error_minimizing_noise(xtr, ytr, n_id, eps, rounds=5, inner=10)
    gen_s = time.time() - t
    xprot = (xtr + noise[ytr]).clamp(0, 1)
    # Control CORRECTO: ruido aleatorio POR IMAGEN (sample-wise), no por clase.
    # Un aleatorio por clase crearía un atajo espurio que el modelo memoriza y
    # contaminaría el control. Por imagen no da ningún atajo: aísla el mecanismo.
    xrand = (xtr + (torch.rand_like(xtr) * 2 - 1) * eps).clamp(0, 1)
    fte = bk.feats(xte)
    res = {}
    for name, data in (("LIMPIO", xtr), ("PROTEGIDO", xprot), ("ALEATORIO", xrand), ("PROT+JPEG", jpeg_batch(xprot))):
        te, tr = linprobe(bk.feats(data), ytr, fte, yte, n_id)
        res[name] = te
    res["_psnr"] = quality(xtr, xprot)
    res["_gen_s"] = gen_s
    res["_per_img_s"] = gen_s / len(xtr)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--identities", type=int, default=20)
    ap.add_argument("--train-per", type=int, default=7)  # 7 train / 3 test por persona
    ap.add_argument("--epsilon", type=float, default=8.0)
    ap.add_argument("--seeds", type=int, default=2)
    args = ap.parse_args()

    configure_threads()
    print(f"ROSTROS REALES (Olivetti) · identidades {args.identities} · ε={args.epsilon}/255 · transfer learning ResNet18", flush=True)
    print("cargando ResNet18 preentrenado...", flush=True)
    bk = Backbone()
    chance = 100 / args.identities

    runs = []
    for s in range(args.seeds):
        t = time.time()
        r = run_once(args.identities, args.train_per, args.epsilon / 255, s, bk)
        runs.append(r)
        print(f"\nsemilla {s} ({time.time()-t:.0f}s, ruido {r['_per_img_s']:.2f}s/img, PSNR {r['_psnr']:.1f} dB):", flush=True)
        for k in ("LIMPIO", "PROTEGIDO", "ALEATORIO", "PROT+JPEG"):
            print(f"  {k:10s} identidad acc: {r[k]*100:.1f}%", flush=True)

    def avg(k):
        return np.mean([r[k] for r in runs]) * 100

    def std(k):
        return np.std([r[k] for r in runs]) * 100

    clean, prot, rand, jpg = avg("LIMPIO"), avg("PROTEGIDO"), avg("ALEATORIO"), avg("PROT+JPEG")
    print(f"\n=== MEDIA sobre {args.seeds} semillas (azar {chance:.0f}%) ===")
    print(f"  LIMPIO    {clean:.1f}% (±{std('LIMPIO'):.1f})")
    print(f"  PROTEGIDO {prot:.1f}% (±{std('PROTEGIDO'):.1f})  -> caída {clean-prot:.1f} pts")
    print(f"  ALEATORIO {rand:.1f}% (±{std('ALEATORIO'):.1f})  -> caída {clean-rand:.1f} pts (control)")
    print(f"  PROT+JPEG {jpg:.1f}%  -> caída {clean-jpg:.1f} pts")
    print(f"  calidad PSNR medio {np.mean([r['_psnr'] for r in runs]):.1f} dB · ruido {np.mean([r['_per_img_s'] for r in runs]):.2f} s/img")
    # criterio a priori
    c1 = (clean - prot) >= 20
    c2 = (clean - rand) < 10
    c3 = (clean - jpg) >= 15
    c4 = np.mean([r["_psnr"] for r in runs]) >= 30
    c5 = std("PROTEGIDO") < 8
    print(f"\nCriterios: 1 caída>=20 {'OK' if c1 else 'NO'} | 2 aleatorio no protege {'OK' if c2 else 'NO'} | "
          f"3 sobrevive JPEG {'OK' if c3 else 'NO'} | 4 PSNR>=30 {'OK' if c4 else 'NO'} | 5 estable {'OK' if c5 else 'NO'}")
    print(f"VEREDICTO: {'PROTEGE contra transfer learning' if (c1 and c2 and c3) else 'NO cumple el criterio'}")


if __name__ == "__main__":
    main()
