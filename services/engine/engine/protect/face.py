"""Capa anti-deepfake: aleja la identidad que extraen los reconocedores faciales.

- ArcFace (InsightFace w600k_r50): la huella que usan roop y FaceFusion para
  copiar una cara. Se ataca directamente si el modelo está descargado (ver
  engine/models.py).
- FaceNet InceptionResnetV1 (VGGFace2, facenet-pytorch, MIT): segundo
  reconocedor del ensamble.

Detección y puntos de referencia con MTCNN (facenet-pytorch).
"""

from __future__ import annotations

import random
import os
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from facenet_pytorch import MTCNN, InceptionResnetV1
from kornia.geometry.transform import warp_affine
from PIL import Image

from .. import models
from . import eot

_FACE_SIZE = 160
_MIN_FACE_PX = 40
_MIN_PROB = 0.9

# Plantilla de alineación de ArcFace (112×112): ojos, nariz, comisuras.
ARCFACE_DST = torch.tensor(
    [[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366], [41.5493, 92.3655], [70.7299, 92.2041]],
    dtype=torch.float32,
)


@dataclass
class Face:
    box: tuple[float, float, float, float]
    landmarks: np.ndarray  # (5, 2) en coordenadas de la imagen


@dataclass
class FaceModels:
    detector: MTCNN
    embedder: InceptionResnetV1
    arcfaces: list = field(default_factory=list)  # ensemble de reconocedores ArcFace


@dataclass
class References:
    facenet: list[torch.Tensor | None] = field(default_factory=list)
    arcface: list = field(default_factory=list)  # por cara, lista de refs (una por modelo del ensemble)


def load(device: torch.device) -> FaceModels:
    # MTCNN se ejecuta una sola vez por imagen y sin gradiente; en CPU basta.
    detector = MTCNN(keep_all=True, device="cpu", post_process=False)
    embedder = InceptionResnetV1(pretrained="vggface2").eval().to(device)
    for p in embedder.parameters():
        p.requires_grad_(False)
    return FaceModels(detector, embedder, _load_arcfaces(device))


def _load_arcfaces(device: torch.device) -> list:
    """Ensemble de ArcFace. Por defecto solo w600k (baseline). Con la variable
    VELO_ARCFACE_EXTRA (rutas .onnx separadas por ':') se añaden más, p. ej.
    glintr100, para optimizar contra un conjunto más diverso."""
    import onnx
    from onnx2torch import convert

    paths = []
    base = models.arcface_path()
    if base is not None:
        paths.append(Path(base))
    for extra in os.environ.get("VELO_ARCFACE_EXTRA", "").split(":"):
        if extra and Path(extra).exists():
            paths.append(Path(extra))
    nets = []
    for path in paths:
        net = convert(onnx.load(str(path))).eval().to(device)
        for q in net.parameters():
            q.requires_grad_(False)
        nets.append(net)
    return nets


def detect(fm: FaceModels, image: Image.Image) -> list[Face]:
    boxes, probs, points = fm.detector.detect(image, landmarks=True)
    if boxes is None:
        return []
    out = []
    for box, prob, pts in zip(boxes, probs, points):
        x1, y1, x2, y2 = box.tolist()
        if prob >= _MIN_PROB and min(x2 - x1, y2 - y1) >= _MIN_FACE_PX:
            out.append(Face(_pad_box((x1, y1, x2, y2), image.width, image.height), np.asarray(pts, np.float32)))
    return out


def _pad_box(box, w, h, margin=0.15):
    x1, y1, x2, y2 = box
    mx, my = (x2 - x1) * margin, (y2 - y1) * margin
    return (max(0.0, x1 - mx), max(0.0, y1 - my), min(float(w), x2 + mx), min(float(h), y2 + my))


def mask(faces: list[Face], h: int, w: int, device: torch.device, feather: int = 12) -> torch.Tensor:
    """Máscara suave (1,1,H,W) que vale 1 dentro de los rostros."""
    m = np.zeros((h, w), dtype=np.float32)
    for f in faces:
        x1, y1, x2, y2 = f.box
        m[int(y1) : int(np.ceil(y2)), int(x1) : int(np.ceil(x2))] = 1.0
    t = torch.from_numpy(m)[None, None].to(device)
    if feather > 0:
        t = eot.gaussian_blur(t, feather / 2)
    return t.clamp(0, 1)


def _facenet_crop(img: torch.Tensor, box: tuple[int, int, int, int]) -> torch.Tensor | None:
    x1, y1, x2, y2 = box
    if x2 - x1 < 16 or y2 - y1 < 16:
        return None
    face = img[..., y1:y2, x1:x2]
    face = F.interpolate(face, size=(_FACE_SIZE, _FACE_SIZE), mode="bilinear", antialias=True, align_corners=False)
    return (face * 255 - 127.5) / 128.0


def _similarity_matrix(src: torch.Tensor) -> torch.Tensor:
    """Transformación de semejanza (2×3) que lleva los 5 puntos a la plantilla
    de ArcFace (Umeyama, como hace InsightFace)."""
    dst = ARCFACE_DST.to(src.device)
    mu_s, mu_d = src.mean(0), dst.mean(0)
    s, d = src - mu_s, dst - mu_d
    cov = d.T @ s / len(src)
    u, sig, vt = torch.linalg.svd(cov)
    sign = torch.ones(2, device=src.device)
    if torch.det(u) * torch.det(vt) < 0:
        sign[-1] = -1
    r = u @ torch.diag(sign) @ vt
    scale = (sig * sign).sum() / s.pow(2).sum(1).mean()
    t = mu_d - scale * r @ mu_s
    return torch.cat([scale * r, t[:, None]], dim=1)


def _arcface_crop(img: torch.Tensor, pts: np.ndarray) -> torch.Tensor:
    m = _similarity_matrix(torch.as_tensor(pts, dtype=torch.float32, device=img.device))
    crop = warp_affine(img, m[None], dsize=(112, 112), mode="bilinear", align_corners=False)
    return (crop * 255 - 127.5) / 127.5


def _embed(net: torch.nn.Module, x: torch.Tensor) -> torch.Tensor:
    return F.normalize(net(x), dim=-1)


def reference(fm: FaceModels, img: torch.Tensor, faces: list[Face]) -> References:
    refs = References()
    with torch.no_grad():
        for f in faces:
            crop = _facenet_crop(img, tuple(int(round(v)) for v in f.box))
            refs.facenet.append(None if crop is None else _embed(fm.embedder, crop))
            crop_a = _arcface_crop(img, f.landmarks) if fm.arcfaces else None
            refs.arcface.append([_embed(net, crop_a) for net in fm.arcfaces] if crop_a is not None else [])
    return refs


def similarity(
    fm: FaceModels,
    img_t: torch.Tensor,
    faces: list[Face],
    refs: References,
    s: eot.Sample,
    orig_hw: tuple[int, int],
    rng: random.Random,
    jitter: float = 1.5,
) -> dict[str, torch.Tensor]:
    """Similitud coseno media entre la identidad original y la de la imagen
    transformada, por reconocedor. Son las pérdidas a minimizar."""
    h, w = orig_hw
    out: dict[str, list[torch.Tensor]] = {"facenet": [], "arcface": []}
    for i, f in enumerate(faces):
        crop = _facenet_crop(img_t, eot.map_box(f.box, h, w, s))
        if crop is not None and refs.facenet[i] is not None:
            out["facenet"].append((_embed(fm.embedder, crop) * refs.facenet[i]).sum())
        if fm.arcfaces and refs.arcface[i]:
            pts = eot.map_points(f.landmarks, h, w, s)
            # El detector del atacante no pondrá los puntos exactamente igual.
            pts = pts + np.array([[rng.gauss(0, jitter), rng.gauss(0, jitter)] for _ in range(5)], np.float32)
            crop = _arcface_crop(img_t, pts)
            for net, ref in zip(fm.arcfaces, refs.arcface[i]):
                out["arcface"].append((_embed(net, crop) * ref).sum())
    return {k: torch.stack(v).mean() for k, v in out.items() if v}
