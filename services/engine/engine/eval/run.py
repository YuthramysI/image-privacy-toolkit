"""Benchmark honesto de la protección.

Mide la eficacia DESPUÉS de simular una subida real (reescalado + JPEG), y la
mide también con modelos que el ataque nunca vio (transferencia):
  - rostro: facenet entrenado en CASIA-WebFace (el ataque usa VGGFace2)
  - difusión: VAE completos de SD, FLUX y SDXL (los presets de CPU solo
    atacan a los sustitutos ligeros TAESD/TAEF1, y SDXL nunca se ataca)

Uso:
  python -m engine.eval.run --images samples/ --preset media --out reports/
"""

from __future__ import annotations

import argparse
import io
import json
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from facenet_pytorch import InceptionResnetV1
from PIL import Image, ImageOps
from skimage.metrics import peak_signal_noise_ratio, structural_similarity

from ..protect import face, vae
from ..protect.pipeline import PRESETS, Engine, to_tensor

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def social_upload(img: Image.Image, width: int = 1080, quality: int = 75) -> Image.Image:
    """Lo que le hace una red social: reducir a 1080 px de ancho y recomprimir."""
    if img.width > width:
        img = img.resize((width, round(img.height * width / img.width)), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")


def training_resize(img: Image.Image, side: int = 512, quality: int = 85) -> Image.Image:
    """Lo que hace un pipeline típico de fine-tuning: reducir a 512 y guardar."""
    s = side / max(img.size)
    img = img.resize((round(img.width * s), round(img.height * s)), Image.Resampling.BICUBIC)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")


def _crop8(img: Image.Image) -> Image.Image:
    return img.crop((0, 0, img.width - img.width % 8, img.height - img.height % 8))


class Evaluator:
    def __init__(self, engine: Engine):
        self.e = engine
        dev = engine.device
        self.face_holdout = InceptionResnetV1(pretrained="casia-webface").eval().to(dev)
        # Siempre se mide contra los VAE completos, aunque el preset ataque a
        # los sustitutos ligeros: es lo que usan los modelos reales.
        self.vaes = {name: enc for name, enc in vae.load(["sd", "flux", "sdxl"], dev).items()}

    @torch.no_grad()
    def _face_sims(self, clean: Image.Image, other: Image.Image) -> dict[str, float]:
        boxes = face.detect(self.e.faces, clean)
        if not boxes:
            return {}
        dev = self.e.device
        if other.size != clean.size:
            sx, sy = other.width / clean.width, other.height / clean.height
            other_boxes = [(x1 * sx, y1 * sy, x2 * sx, y2 * sy) for x1, y1, x2, y2 in boxes]
        else:
            other_boxes = boxes
        a, b = to_tensor(clean, dev), to_tensor(other, dev)
        out = {}
        for label, model in (("vggface2 (atacado)", self.e.faces.embedder), ("casia (no visto)", self.face_holdout)):
            fm = face.FaceModels(self.e.faces.detector, model)
            ea = face.embed(fm, a, [tuple(int(round(v)) for v in bx) for bx in boxes])
            eb = face.embed(fm, b, [tuple(int(round(v)) for v in bx) for bx in other_boxes])
            sims = [float((x * y).sum()) for x, y in zip(ea, eb) if x is not None and y is not None]
            if sims:
                out[label] = float(np.mean(sims))
        return out

    @torch.no_grad()
    def _vae_recon(self, clean: Image.Image, other: Image.Image) -> dict[str, float]:
        """PSNR de lo que el modelo "ve" (reconstrucción del VAE) frente a la
        foto limpia. Cuanto más bajo, más basura ve el modelo."""
        other = other.resize(clean.size, Image.Resampling.BICUBIC) if other.size != clean.size else other
        side = 512
        s = side / max(clean.size)
        size = (max(8, round(clean.width * s) // 8 * 8), max(8, round(clean.height * s) // 8 * 8))
        c = to_tensor(clean.resize(size, Image.Resampling.BICUBIC), self.e.device)
        o = to_tensor(other.resize(size, Image.Resampling.BICUBIC), self.e.device)
        out = {}
        for name, enc in self.vaes.items():
            rec = enc.decode(enc.encode(o))
            mse = F.mse_loss(rec, c).item()
            out[name] = 10 * np.log10(1 / max(mse, 1e-10))
        return out

    def visibility(self, clean: Image.Image, prot: Image.Image) -> dict[str, float]:
        a = np.asarray(clean, dtype=np.float32) / 255
        b = np.asarray(prot, dtype=np.float32) / 255
        dev = self.e.device
        with torch.no_grad():
            lp = float(self.e.perceptual(to_tensor(prot, dev), to_tensor(clean, dev)))
        return {
            "psnr": float(peak_signal_noise_ratio(a, b, data_range=1)),
            "ssim": float(structural_similarity(a, b, channel_axis=2, data_range=1)),
            "lpips": lp,
        }

    def evaluate(self, clean: Image.Image, prot: Image.Image) -> dict:
        report = {"visibilidad": self.visibility(clean, prot), "escenarios": {}}
        for scen, fn in (("red social (1080px, JPEG 75)", social_upload), ("entrenamiento (512px, JPEG 85)", training_resize)):
            c2, p2 = fn(clean), fn(prot)
            report["escenarios"][scen] = {
                "rostro_similitud": {"limpia": self._face_sims(clean, c2), "protegida": self._face_sims(clean, p2)},
                "vae_psnr": {"limpia": self._vae_recon(clean, c2), "protegida": self._vae_recon(clean, p2)},
            }
        return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", type=Path, required=True)
    ap.add_argument("--preset", default="media", choices=list(PRESETS))
    ap.add_argument("--out", type=Path, default=Path("reports"))
    ap.add_argument("--steps", type=int, default=None, help="sobrescribe los pasos del preset")
    args = ap.parse_args()

    preset = PRESETS[args.preset]
    if args.steps:
        from dataclasses import replace

        preset = replace(preset, steps=args.steps)

    files = sorted(p for p in args.images.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    out_dir = args.out / preset.name
    out_dir.mkdir(parents=True, exist_ok=True)

    engine = Engine(encoders=preset.encoders)
    ev = Evaluator(engine)
    results = {}
    for f in files:
        clean = _crop8(ImageOps.exif_transpose(Image.open(f)).convert("RGB"))
        t = time.time()
        res = engine.protect(clean, preset)
        res.image.save(out_dir / f"{f.stem}.png")
        rep = ev.evaluate(clean, res.image)
        # segundos = solo la protección; la evaluación con los VAE completos va aparte.
        rep.update(segundos=round(res.seconds, 1), segundos_eval=round(time.time() - t - res.seconds, 1), rostros=res.faces, s_por_paso=round(res.seconds / preset.steps, 2))
        results[f.name] = rep
        print(f"\n== {f.name}  ({rep['segundos']} s, {res.faces} rostro(s))")
        print(json.dumps(rep, indent=1, ensure_ascii=False))

    (out_dir / "report.json").write_text(json.dumps(results, indent=1, ensure_ascii=False))
    print(f"\nInforme: {out_dir / 'report.json'}")


if __name__ == "__main__":
    main()
