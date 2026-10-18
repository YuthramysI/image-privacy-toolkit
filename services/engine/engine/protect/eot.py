"""Transformaciones diferenciables que imitan lo que le pasa a una foto al subirla
a una red social o al entrar en un pipeline de entrenamiento: reescalado,
recompresión JPEG, desplazamiento de la rejilla de bloques y desenfoque leve.

Optimizar la perturbación a través de estas transformaciones (EOT) es lo que la
hace sobrevivir a la recompresión en vez de desaparecer al primer JPEG.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import numpy as np
import torch
import torch.nn.functional as F

# Tablas de cuantización estándar del anexo K de JPEG.
_Y_TABLE = torch.tensor(
    [
        [16, 11, 10, 16, 24, 40, 51, 61],
        [12, 12, 14, 19, 26, 58, 60, 55],
        [14, 13, 16, 24, 40, 57, 69, 56],
        [14, 17, 22, 29, 51, 87, 80, 62],
        [18, 22, 37, 56, 68, 109, 103, 77],
        [24, 35, 55, 64, 81, 104, 113, 92],
        [49, 64, 78, 87, 103, 121, 120, 101],
        [72, 92, 95, 98, 112, 100, 103, 99],
    ],
    dtype=torch.float32,
)
_C_TABLE = torch.full((8, 8), 99.0)
_C_TABLE[:4, :4] = torch.tensor(
    [[17, 18, 24, 47], [18, 21, 26, 66], [24, 26, 56, 99], [47, 66, 99, 99]],
    dtype=torch.float32,
)


def _dct_matrix(device: torch.device) -> torch.Tensor:
    m = torch.zeros(8, 8, device=device)
    for k in range(8):
        for n in range(8):
            c = math.sqrt(1 / 8) if k == 0 else math.sqrt(2 / 8)
            m[k, n] = c * math.cos(math.pi * (2 * n + 1) * k / 16)
    return m


def _quality_scale(quality: int) -> float:
    quality = max(1, min(100, quality))
    return (5000 / quality if quality < 50 else 200 - 2 * quality) / 100


def _soft_round(x: torch.Tensor) -> torch.Tensor:
    # Aproximación cúbica de round(): el valor hacia adelante es casi el
    # redondeo real y el gradiente no se anula.
    r = torch.round(x)
    return r + (x - r) ** 3


def _blockify(x: torch.Tensor) -> torch.Tensor:
    b, h, w = x.shape
    return x.view(b, h // 8, 8, w // 8, 8).permute(0, 1, 3, 2, 4)


def _unblockify(x: torch.Tensor, h: int, w: int) -> torch.Tensor:
    b = x.shape[0]
    return x.permute(0, 1, 3, 2, 4).reshape(b, h, w)


def diff_jpeg(img: torch.Tensor, quality: int) -> torch.Tensor:
    """JPEG diferenciable con submuestreo 4:2:0. `img`: (B,3,H,W) en [0,1]."""
    b, _, h, w = img.shape
    ph, pw = (-h) % 16, (-w) % 16
    x = F.pad(img, (0, pw, 0, ph), mode="replicate") * 255
    hh, ww = x.shape[-2:]

    r, g, bl = x[:, 0], x[:, 1], x[:, 2]
    y = 0.299 * r + 0.587 * g + 0.114 * bl
    cb = -0.168736 * r - 0.331264 * g + 0.5 * bl + 128
    cr = 0.5 * r - 0.418688 * g - 0.081312 * bl + 128

    cb = F.avg_pool2d(cb.unsqueeze(1), 2).squeeze(1)
    cr = F.avg_pool2d(cr.unsqueeze(1), 2).squeeze(1)

    d = _dct_matrix(img.device)
    s = _quality_scale(quality)
    qy = torch.clamp(torch.floor(_Y_TABLE.to(img.device) * s + 0.5), min=1)
    qc = torch.clamp(torch.floor(_C_TABLE.to(img.device) * s + 0.5), min=1)

    def codec(ch: torch.Tensor, q: torch.Tensor) -> torch.Tensor:
        ch_h, ch_w = ch.shape[-2:]
        blocks = _blockify(ch - 128)
        coef = d @ blocks @ d.T
        coef = _soft_round(coef / q) * q
        return _unblockify(d.T @ coef @ d, ch_h, ch_w) + 128

    y = codec(y, qy)
    cb = F.interpolate(codec(cb, qc).unsqueeze(1), scale_factor=2, mode="bilinear", align_corners=False).squeeze(1)
    cr = F.interpolate(codec(cr, qc).unsqueeze(1), scale_factor=2, mode="bilinear", align_corners=False).squeeze(1)

    r = y + 1.402 * (cr - 128)
    g = y - 0.344136 * (cb - 128) - 0.714136 * (cr - 128)
    bl = y + 1.772 * (cb - 128)
    out = torch.stack([r, g, bl], dim=1) / 255
    return out[..., :h, :w].clamp(0, 1)


def gaussian_blur(img: torch.Tensor, sigma: float) -> torch.Tensor:
    if sigma <= 0:
        return img
    radius = max(1, int(math.ceil(2 * sigma)))
    t = torch.arange(-radius, radius + 1, device=img.device, dtype=img.dtype)
    k = torch.exp(-(t**2) / (2 * sigma**2))
    k = k / k.sum()
    c = img.shape[1]
    kx = k.view(1, 1, 1, -1).repeat(c, 1, 1, 1)
    ky = k.view(1, 1, -1, 1).repeat(c, 1, 1, 1)
    x = F.pad(img, (radius, radius, radius, radius), mode="reflect")
    x = F.conv2d(x, kx, groups=c)
    return F.conv2d(x, ky, groups=c)


@dataclass(frozen=True)
class EOTConfig:
    # Lado mayor (px) al que se reduce la imagen antes de pasarla a los modelos.
    sizes: tuple[int, ...] = (384, 512, 640)
    jpeg_quality: tuple[int, int] = (60, 90)
    jpeg_prob: float = 0.8
    blur_sigma: tuple[float, float] = (0.0, 0.8)
    blur_prob: float = 0.3
    max_shift: int = 7


@dataclass(frozen=True)
class Sample:
    """Una realización concreta de la transformación (para poder repetirla)."""

    size: int
    shift: tuple[int, int]
    quality: int | None
    sigma: float


def sample(cfg: EOTConfig, rng: random.Random) -> Sample:
    return Sample(
        size=rng.choice(cfg.sizes),
        shift=(rng.randint(0, cfg.max_shift), rng.randint(0, cfg.max_shift)),
        quality=rng.randint(*cfg.jpeg_quality) if rng.random() < cfg.jpeg_prob else None,
        sigma=rng.uniform(*cfg.blur_sigma) if rng.random() < cfg.blur_prob else 0.0,
    )


def target_hw(h: int, w: int, size: int, multiple: int = 8) -> tuple[int, int]:
    scale = min(1.0, size / max(h, w))
    nh = max(multiple, int(round(h * scale / multiple)) * multiple)
    nw = max(multiple, int(round(w * scale / multiple)) * multiple)
    return nh, nw


def apply(img: torch.Tensor, s: Sample) -> torch.Tensor:
    """Reduce, desplaza la rejilla JPEG, recomprime y desenfoca. Devuelve una
    imagen cuyo tamaño es múltiplo de 8 (lo que piden los encoders VAE)."""
    h, w = img.shape[-2:]
    nh, nw = target_hw(h, w, s.size)
    x = F.interpolate(img, size=(nh + 8, nw + 8), mode="bilinear", antialias=True, align_corners=False)
    dy, dx = s.shift
    x = x[..., dy : dy + nh, dx : dx + nw]
    if s.quality is not None:
        x = diff_jpeg(x, s.quality)
    if s.sigma > 0:
        x = gaussian_blur(x, s.sigma)
    return x


def map_box(box: tuple[float, float, float, float], h: int, w: int, s: Sample) -> tuple[int, int, int, int]:
    """Lleva una caja (x1,y1,x2,y2) de la imagen original al espacio transformado."""
    nh, nw = target_hw(h, w, s.size)
    sy, sx = (nh + 8) / h, (nw + 8) / w
    dy, dx = s.shift
    x1, y1, x2, y2 = box
    return (
        max(0, int(x1 * sx) - dx),
        max(0, int(y1 * sy) - dy),
        min(nw, int(math.ceil(x2 * sx)) - dx),
        min(nh, int(math.ceil(y2 * sy)) - dy),
    )


def map_points(points: np.ndarray, h: int, w: int, s: Sample) -> np.ndarray:
    """Lleva puntos (N,2) en (x,y) de la imagen original al espacio transformado."""
    nh, nw = target_hw(h, w, s.size)
    sy, sx = (nh + 8) / h, (nw + 8) / w
    dy, dx = s.shift
    out = points.astype(np.float32).copy()
    out[:, 0] = out[:, 0] * sx - dx
    out[:, 1] = out[:, 1] * sy - dy
    return out
