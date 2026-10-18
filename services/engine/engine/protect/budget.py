"""Presupuesto de visibilidad: cuánto puede cambiar cada píxel.

Reparte más perturbación donde hay textura (el ojo no la nota) y menos en zonas
lisas como cielo o fondos planos, y penaliza la distancia perceptual LPIPS.
"""

from __future__ import annotations

import lpips
import torch
import torch.nn.functional as F

from . import eot


def texture_map(img: torch.Tensor, window: int = 9) -> torch.Tensor:
    """Desviación estándar local de la luminancia, normalizada a [0, 1]."""
    gray = (0.299 * img[:, 0:1] + 0.587 * img[:, 1:2] + 0.114 * img[:, 2:3])
    pad = window // 2
    g = F.pad(gray, (pad, pad, pad, pad), mode="reflect")
    mean = F.avg_pool2d(g, window, stride=1)
    sq = F.avg_pool2d(g * g, window, stride=1)
    std = (sq - mean * mean).clamp(min=0).sqrt()
    std = eot.gaussian_blur(std, 2.0)
    hi = torch.quantile(std.flatten(), 0.95).clamp(min=1e-4)
    return (std / hi).clamp(0, 1)


def eps_map(
    img: torch.Tensor,
    eps: float,
    face_mask: torch.Tensor | None = None,
    floor: float = 0.45,
    face_level: float = 0.8,
) -> torch.Tensor:
    m = floor + (1 - floor) * texture_map(img)
    if face_mask is not None:
        # La piel es lisa: sin este mínimo, la capa de rostro no tendría margen.
        m = torch.maximum(m, face_level * face_mask)
    return (eps * m).expand_as(img).contiguous()


def _luminance_masking(gray: torch.Tensor) -> torch.Tensor:
    """Cuánto ruido tolera el ojo según el brillo de fondo (Chou-Li).
    Tolera más en zonas oscuras y muy claras, menos en los grises medios."""
    bg = eot.gaussian_blur(gray, 1.5) * 255.0
    t0, gamma = 17.0, 3.0 / 128.0
    dark = t0 * (1 - (bg / 127.0).clamp(0, 1).sqrt())
    bright = gamma * (bg - 127.0).clamp(min=0)
    return (torch.where(bg <= 127.0, dark, bright) + 3.0) / 255.0


def _texture_masking(gray: torch.Tensor) -> torch.Tensor:
    """Cuánto ruido esconde la textura/bordes locales. Alto en cejas, pelo y
    contornos; casi cero en piel lisa, cielo o fondos planos."""
    k = torch.tensor([[-1.0, 0, 1], [-2, 0, 2], [-1, 0, 1]], device=gray.device).view(1, 1, 3, 3) / 4
    gx = F.conv2d(F.pad(gray, (1, 1, 1, 1), mode="reflect"), k)
    gy = F.conv2d(F.pad(gray, (1, 1, 1, 1), mode="reflect"), k.transpose(-1, -2))
    grad = (gx * gx + gy * gy).sqrt()
    return eot.gaussian_blur(grad, 1.0)


def jnd_map(img: torch.Tensor, chroma_gain: float = 1.4, tex_weight: float = 1.1) -> torch.Tensor:
    """Mapa de diferencia apenas perceptible (JND) por píxel y canal.

    Reparte el presupuesto donde el ojo humano no ve el ruido: bordes, textura,
    zonas oscuras y color. Lo quita de la piel lisa y de la luminancia plana,
    que es donde más se nota. Devuelve un peso relativo (media ≈ 1)."""
    gray = 0.299 * img[:, 0:1] + 0.587 * img[:, 1:2] + 0.114 * img[:, 2:3]
    lum = _luminance_masking(gray)
    tex = _texture_masking(gray)
    # Solapamiento (NAMM): las dos máscaras no se suman del todo. El peso de la
    # textura es alto: los bordes (cejas, ojos, contorno) esconden mucho ruido y
    # son justo donde un reconocedor facial saca la identidad.
    jnd = lum + tex_weight * tex - 0.3 * torch.minimum(lum, tex_weight * tex)
    jnd = jnd / jnd.mean().clamp(min=1e-6)  # peso relativo, media 1
    weight = jnd.repeat(1, 3, 1, 1).clone()
    # El ojo tolera algo más de ruido en color que en brillo, pero sin exagerar
    # (demasiado croma se ve como manchas de color en la piel).
    weight[:, 0] *= chroma_gain
    weight[:, 1] *= 0.8
    weight[:, 2] *= chroma_gain
    return weight


def jnd_eps_map(img: torch.Tensor, eps: float, cap: float = 1.8, floor: float = 0.12) -> torch.Tensor:
    """Presupuesto por píxel basado en JND, con el mismo gasto medio que `eps`
    pero repartido perceptualmente. El techo evita que un píxel delate; el suelo
    deja algo de margen en la piel lisa para no perder del todo la eficacia."""
    w = jnd_map(img).clamp(min=floor)
    w = w / w.mean().clamp(min=1e-6)
    return (eps * w.clamp(max=cap)).expand_as(img).contiguous()


def project(delta: torch.Tensor, img: torch.Tensor, emap: torch.Tensor) -> torch.Tensor:
    delta = torch.maximum(torch.minimum(delta, emap), -emap)
    return (img + delta).clamp(0, 1) - img


class Perceptual:
    """LPIPS (AlexNet) sobre una versión reducida, barato incluso en CPU."""

    def __init__(self, device: torch.device, size: int = 256):
        self.model = lpips.LPIPS(net="alex", verbose=False).eval().to(device)
        for p in self.model.parameters():
            p.requires_grad_(False)
        self.size = size

    def _small(self, x: torch.Tensor) -> torch.Tensor:
        h, w = x.shape[-2:]
        s = self.size / max(h, w)
        if s < 1:
            x = F.interpolate(x, size=(max(8, int(h * s)), max(8, int(w * s))), mode="bilinear", antialias=True, align_corners=False)
        return x * 2 - 1

    def __call__(self, a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
        return self.model(self._small(a), self._small(b)).mean()
