"""Experimento: ¿atacar un ENSEMBLE de reconocedores mejora la protección real
frente a face-swap, a IGUALDAD de calidad? (ver docs/MATRIZ_INVESTIGACION.md)

Genera imágenes protegidas con el ensemble (w600k + glintr100, activado con
VELO_ARCFACE_EXTRA) a un ε dado, para compararlas con el baseline sobre el
face-swap real (inswapper fp32) con un juez independiente (FaceNet-casia).
Se versiona en el repositorio para que el experimento sea reproducible.

Generar (ε reducido para igualar la calidad del baseline ~36 dB):
  VELO_ARCFACE_EXTRA=~/.cache/velo-eval/antelopev2/glintr100.onnx \\
    python -m engine.research.faceswap_ensemble --eps 6 \\
    --out reports/faceswap-ensemble-eps6 clark jemison

Resultado preliminar (1 foto, chawla): a igualdad de calidad el ensemble NO
mejora frente al baseline (la ventaja del ε mayor era solo más ruido). Pendiente
confirmar con más fotos; el entorno sufrió reinicios que interrumpen la
generación (~12 min/imagen en CPU).
"""

from __future__ import annotations

import argparse
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
from PIL import Image
from skimage.metrics import peak_signal_noise_ratio as psnr

from ..protect.pipeline import PRESETS, Engine

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stems", nargs="+")
    ap.add_argument("--eps", type=float, default=6.0, help="en niveles de 255")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    e = Engine(encoders=PRESETS["media"].encoders)
    print(f"arcfaces en el ataque: {len(e.faces.arcfaces)} (ensemble si >1)", flush=True)
    preset = replace(PRESETS["media"], eps=args.eps / 255)
    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    for name in args.stems:
        f = ROOT / f"samples/faces/{name}.jpg"
        t = time.time()
        res = e.protect(Image.open(f), preset)
        res.image.save(out / f"{name}-media.png")
        o = np.asarray(Image.open(f).convert("RGB"), np.float32) / 255
        p = np.asarray(res.image.convert("RGB").resize(Image.open(f).size), np.float32) / 255
        print(f"{name}: PSNR {psnr(o, p, data_range=1):.1f} dB, {time.time() - t:.0f}s", flush=True)


if __name__ == "__main__":
    main()
