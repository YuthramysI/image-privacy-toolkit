"""¿Frena la protección a las herramientas de face-swap abiertas?

roop, FaceFusion y similares usan el paquete buffalo_l de InsightFace: detectan
la cara con SCRFD, la alinean con 5 puntos y sacan su huella con ArcFace. Esa
huella es la identidad que pegan sobre otro vídeo. Si la huella de la foto
protegida ya no se parece a la de la persona, el deepfake sale con otra cara.

Los modelos de InsightFace tienen licencia de investigación no comercial: aquí
solo se usan para medir, nunca dentro del producto.

  python -m engine.eval.faceswap --images samples/faces --presets media fuerte

Requiere buffalo_l descomprimido en $VELO_EVAL_MODELS (por defecto
~/.cache/velo-eval/buffalo_l): https://github.com/deepinsight/insightface/releases/tag/v0.7
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageOps
from skimage.transform import SimilarityTransform, warp

from ..protect.pipeline import PRESETS, Engine
from .run import IMAGE_EXTS, social_upload

MODELS = Path(os.environ.get("VELO_EVAL_MODELS", Path.home() / ".cache/velo-eval/buffalo_l"))

# Plantilla de alineación de ArcFace (112×112).
ARCFACE_DST = np.array(
    [[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366], [41.5493, 92.3655], [70.7299, 92.2041]],
    dtype=np.float32,
)
# Por debajo de este coseno ArcFace suele considerar que son personas distintas.
MATCH_THRESHOLD = 0.35


def _session(name: str) -> ort.InferenceSession:
    opts = ort.SessionOptions()
    opts.log_severity_level = 3
    return ort.InferenceSession(str(MODELS / name), opts, providers=["CPUExecutionProvider"])


def _session_at(path: Path) -> ort.InferenceSession:
    opts = ort.SessionOptions()
    opts.log_severity_level = 3
    return ort.InferenceSession(str(path), opts, providers=["CPUExecutionProvider"])


class SCRFD:
    """Detector de caras de buffalo_l (det_10g)."""

    def __init__(self, size: int = 640):
        self.sess = _session("det_10g.onnx")
        self.input = self.sess.get_inputs()[0].name
        self.size = size
        self.strides = (8, 16, 32)

    def detect(self, img: Image.Image, thresh: float = 0.5):
        rgb = np.asarray(img.convert("RGB"), dtype=np.float32)
        h, w = rgb.shape[:2]
        scale = self.size / max(h, w)
        nh, nw = int(round(h * scale)), int(round(w * scale))
        resized = np.asarray(Image.fromarray(rgb.astype(np.uint8)).resize((nw, nh), Image.Resampling.BILINEAR), dtype=np.float32)
        canvas = np.zeros((self.size, self.size, 3), np.float32)
        canvas[:nh, :nw] = resized
        blob = ((canvas - 127.5) / 128.0).transpose(2, 0, 1)[None]
        outs = self.sess.run(None, {self.input: blob})

        boxes, kpss, scores = [], [], []
        for i, stride in enumerate(self.strides):
            sc = outs[i][:, 0] if outs[i].ndim == 2 else outs[i][0, :, 0]
            bb = (outs[i + 3] if outs[i + 3].ndim == 2 else outs[i + 3][0]) * stride
            kp = (outs[i + 6] if outs[i + 6].ndim == 2 else outs[i + 6][0]) * stride
            gh, gw = self.size // stride, self.size // stride
            centers = np.stack(np.mgrid[:gh, :gw][::-1], axis=-1).reshape(-1, 2).astype(np.float32) * stride
            centers = np.repeat(centers, 2, axis=0)  # 2 anclas por posición
            keep = sc >= thresh
            c, b, k = centers[keep], bb[keep], kp[keep]
            boxes.append(np.concatenate([c - b[:, :2], c + b[:, 2:]], axis=1))
            kpss.append((c[:, None, :] + k.reshape(-1, 5, 2)))
            scores.append(sc[keep])
        boxes = np.concatenate(boxes) / scale
        kpss = np.concatenate(kpss) / scale
        scores = np.concatenate(scores)
        if len(scores) == 0:
            return None
        order = _nms(boxes, scores, 0.4)
        boxes, kpss, scores = boxes[order], kpss[order], scores[order]
        # La cara principal: la mayor.
        areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
        best = int(np.argmax(areas))
        return boxes[best], kpss[best], float(scores[best])


def _nms(boxes, scores, iou):
    order = scores.argsort()[::-1]
    keep = []
    while order.size:
        i = order[0]
        keep.append(i)
        xx1 = np.maximum(boxes[i, 0], boxes[order[1:], 0])
        yy1 = np.maximum(boxes[i, 1], boxes[order[1:], 1])
        xx2 = np.minimum(boxes[i, 2], boxes[order[1:], 2])
        yy2 = np.minimum(boxes[i, 3], boxes[order[1:], 3])
        inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
        area = lambda b: (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
        ovr = inter / (area(boxes[[i]]) + area(boxes[order[1:]]) - inter)
        order = order[1:][ovr <= iou]
    return np.array(keep)


HELDOUT = Path(os.environ.get("VELO_EVAL_HELDOUT", Path.home() / ".cache/velo-eval/antelopev2/glintr100.onnx"))


class ArcFace:
    """Huella de identidad. Por defecto la de buffalo_l (w600k_r50), la que usa
    el face-swap; con `path` otro ArcFace (p. ej. glintr100, que el ataque no ve)."""

    def __init__(self, path: Path | None = None):
        self.sess = _session("w600k_r50.onnx") if path is None else _session_at(path)
        self.input = self.sess.get_inputs()[0].name

    def embed(self, img: Image.Image, kps: np.ndarray) -> np.ndarray:
        tform = SimilarityTransform()
        tform.estimate(kps.astype(np.float32), ARCFACE_DST)
        rgb = np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0
        crop = warp(rgb, tform.inverse, output_shape=(112, 112), order=1, mode="constant") * 255.0
        blob = ((crop - 127.5) / 127.5).transpose(2, 0, 1)[None].astype(np.float32)
        emb = self.sess.run(None, {self.input: blob})[0][0]
        return emb / np.linalg.norm(emb)


def identity(det: SCRFD, arc: ArcFace, ref: np.ndarray, img: Image.Image) -> float | None:
    """Coseno ArcFace entre la identidad de referencia y la cara de `img`.
    None si el detector ni siquiera encuentra la cara."""
    found = det.detect(img)
    if found is None:
        return None
    return float(np.dot(ref, arc.embed(img, found[1])))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", type=Path, required=True)
    ap.add_argument("--presets", nargs="+", default=["media", "fuerte"], choices=list(PRESETS))
    ap.add_argument("--out", type=Path, default=Path("reports/faceswap"))
    args = ap.parse_args()

    det, arc = SCRFD(), ArcFace()
    held = ArcFace(HELDOUT) if HELDOUT.exists() else None
    files = sorted(p for p in args.images.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    encoders = tuple(sorted({e for name in args.presets for e in PRESETS[name].encoders}))
    engine = Engine(encoders=encoders)
    args.out.mkdir(parents=True, exist_ok=True)

    results: dict[str, dict] = {}
    for f in files:
        clean = ImageOps.exif_transpose(Image.open(f)).convert("RGB")
        found = det.detect(clean)
        if found is None:
            print(f"{f.name}: sin cara detectable, se omite")
            continue
        ref = arc.embed(clean, found[1])
        href = held.embed(clean, found[1]) if held else None
        row = {"limpia": identity(det, arc, ref, social_upload(clean))}
        if held:
            row["limpia_noVisto"] = identity(det, held, href, social_upload(clean))
        for name in args.presets:
            t = time.time()
            res = engine.protect(clean, name)
            res.image.save(args.out / f"{f.stem}-{name}.png")
            uploaded = social_upload(res.image)
            row[name] = identity(det, arc, ref, uploaded)
            if held:
                row[f"{name}_noVisto"] = identity(det, held, href, uploaded)
            row[f"{name}_s"] = round(time.time() - t, 1)
        results[f.name] = row
        print(f.name, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in row.items()}, flush=True)

    (args.out / "report.json").write_text(json.dumps(results, indent=1))
    cols = ["limpia", *args.presets]
    if held:
        cols += [f"{c}_noVisto" for c in cols]
    fmt = lambda v: "sin cara" if v is None else f"{v:.2f}"
    print("\n| Foto | " + " | ".join(cols) + " |")
    print("|---|" + "---|" * len(cols))
    for name, row in results.items():
        print(f"| {name} | " + " | ".join(fmt(row[c]) for c in cols) + " |")
    for p in cols:
        vals = [r[p] for r in results.values()]
        broken = sum(1 for v in vals if v is None or v < MATCH_THRESHOLD)
        sims = [v for v in vals if v is not None]
        print(f"{p}: media {np.mean(sims):.2f} · identidad rota (< {MATCH_THRESHOLD} o sin cara) en {broken}/{len(vals)}")


if __name__ == "__main__":
    main()
