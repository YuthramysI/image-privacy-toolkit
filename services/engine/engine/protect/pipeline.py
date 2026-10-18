"""Protección por capas en un solo bucle de optimización (PGD con signo).

pérdida = w_arcface · identidad_ArcFace + w_face · identidad_FaceNet
        + w_vae  · distancia_del_latente_al_patrón (normalizada)
        + w_lpips · distancia_perceptual

Todo se evalúa a través de transformaciones aleatorias (EOT) para que la
protección sobreviva a la recompresión y al reescalado de las redes sociales.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageOps

from ..device import configure_threads, pick_device
from . import budget, eot, face, vae

# Por encima de este lado se optimiza a menor resolución y δ se reescala.
MAX_WORK_SIDE = 2048


@dataclass(frozen=True)
class Preset:
    name: str
    eps: float
    steps: int
    encoders: tuple[str, ...]
    eot: eot.EOTConfig = field(default_factory=eot.EOTConfig)
    # Transformaciones para la capa de rostro: el face-swap recorta la cara de la
    # foto a resolución completa, no de una miniatura.
    face_eot: eot.EOTConfig = field(default_factory=lambda: eot.EOTConfig(sizes=(512, 768, 1024)))
    w_face: float = 1.0
    w_arcface: float = 2.0
    w_vae: float = 1.0
    w_lpips: float = 2.0
    # Fracción mínima de ε en zonas lisas (1.0 = presupuesto uniforme).
    texture_floor: float = 0.45
    # Usa el presupuesto perceptual JND (reparte el ruido fuera de la piel lisa).
    perceptual_budget: bool = True


# Suave, media y fuerte atacan los sustitutos ligeros (viables en CPU); máxima
# ataca los VAE completos y está pensada para GPU.
_CPU_EOT = eot.EOTConfig(sizes=(256, 320, 384))

# Calibrado con engine.eval: hasta "media" la perturbación es invisible
# (LPIPS ≈ 0.001); "fuerte" deja una textura fina visible al hacer zoom a cambio
# de más daño a lo que "ve" el modelo de difusión.
_TINY = ("taesd", "taef1")

PRESETS: dict[str, Preset] = {
    "suave": Preset("suave", eps=4 / 255, steps=30, encoders=_TINY, eot=_CPU_EOT),
    "media": Preset("media", eps=8 / 255, steps=80, encoders=_TINY, eot=_CPU_EOT, w_lpips=1.0, texture_floor=0.6),
    "fuerte": Preset("fuerte", eps=12 / 255, steps=100, encoders=_TINY, eot=_CPU_EOT, w_lpips=0.5, texture_floor=0.75),
    "maxima": Preset(
        "maxima",
        eps=12 / 255,
        steps=150,
        encoders=("sd", "flux"),
        eot=eot.EOTConfig(sizes=(384, 512, 640, 768), jpeg_quality=(50, 90)),
        w_lpips=0.5,
        texture_floor=0.75,
    ),
}


@dataclass
class Progress:
    step: int
    total: int
    losses: dict[str, float]
    elapsed: float


@dataclass
class Result:
    image: Image.Image
    faces: int
    preset: str
    seconds: float
    history: list[dict[str, float]]


ProgressFn = Callable[[Progress], None]


class Engine:
    """Carga los modelos una vez y protege muchas imágenes."""

    def __init__(self, encoders: tuple[str, ...] = ("taesd", "taef1"), device: torch.device | None = None):
        configure_threads()
        self.device = device or pick_device()
        self.faces = face.load(self.device)
        self.encoders = vae.load(list(encoders), self.device)
        self.perceptual = budget.Perceptual(self.device)
        self.targets = vae.TargetCache(self.device)

    def protect(
        self,
        image: Image.Image,
        preset: str | Preset = "media",
        seed: int = 0,
        on_progress: ProgressFn | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> Result:
        p = PRESETS[preset] if isinstance(preset, str) else preset
        missing = [e for e in p.encoders if e not in self.encoders]
        if missing:
            raise ValueError(f"Encoders no cargados: {missing}")

        t0 = time.time()
        rng = random.Random(seed)
        torch.manual_seed(seed)

        original = ImageOps.exif_transpose(image).convert("RGB")
        work = _fit(original, MAX_WORK_SIDE)
        x = to_tensor(work, self.device)
        h, w = x.shape[-2:]

        faces = face.detect(self.faces, work)
        fmask = face.mask(faces, h, w, self.device) if faces else None
        refs = face.reference(self.faces, x, faces) if faces else None
        # El presupuesto JND reparte el ruido fuera de la piel lisa (más
        # invisible, LPIPS ~37% menor); el antiguo da más margen uniforme.
        if p.perceptual_budget:
            emap = budget.jnd_eps_map(x, p.eps)
        else:
            emap = budget.eps_map(x, p.eps, fmask, floor=p.texture_floor)

        delta = (torch.rand_like(x) * 2 - 1) * emap * 0.5
        delta = budget.project(delta, x, emap).requires_grad_(True)

        norms: dict[str, float] = {}
        history: list[dict[str, float]] = []
        for step in range(p.steps):
            if should_stop and should_stop():
                raise InterruptedError("cancelado")

            s = eot.sample(p.eot, rng)
            adv = (x + delta).clamp(0, 1)
            adv_t = eot.apply(adv, s)
            total = torch.zeros((), device=self.device)
            log: dict[str, float] = {}

            if faces:
                sf = eot.sample(p.face_eot, rng)
                sims = face.similarity(self.faces, eot.apply(adv, sf), faces, refs, sf, (h, w), rng)
                if "facenet" in sims:
                    total = total + p.w_face * sims["facenet"]
                    log["facenet_sim"] = sims["facenet"].item()
                if "arcface" in sims:
                    total = total + p.w_arcface * sims["arcface"]
                    log["arcface_sim"] = sims["arcface"].item()
                # Lo que muestra la interfaz: el reconocedor del face-swap si está.
                main = sims.get("arcface", sims.get("facenet"))
                if main is not None:
                    log["face_sim"] = main.item()

            # Ensamble por alternancia: un encoder por paso.
            enc = self.encoders[p.encoders[step % len(p.encoders)]]
            lat = vae.latent_loss(enc, adv_t, self.targets)
            norms.setdefault(enc.name, max(lat.item(), 1e-6))
            total = total + p.w_vae * lat / norms[enc.name]
            log[f"vae_{enc.name}"] = lat.item() / norms[enc.name]

            lp = self.perceptual(adv, x)
            total = total + p.w_lpips * lp
            log["lpips"] = lp.item()

            (grad,) = torch.autograd.grad(total, delta)
            with torch.no_grad():
                alpha = p.eps * (0.025 + 0.225 * 0.5 * (1 + math.cos(math.pi * step / p.steps)))
                delta -= alpha * grad.sign()
                delta.copy_(budget.project(delta, x, emap))

            history.append(log)
            if on_progress:
                on_progress(Progress(step + 1, p.steps, log, time.time() - t0))

        out = _apply_delta(original, work, delta.detach())
        return Result(out, len(faces), p.name, time.time() - t0, history)


def to_tensor(img: Image.Image, device: torch.device) -> torch.Tensor:
    arr = np.asarray(img, dtype=np.float32) / 255.0
    return torch.from_numpy(arr).permute(2, 0, 1)[None].to(device)


def to_image(t: torch.Tensor) -> Image.Image:
    arr = (t[0].clamp(0, 1).permute(1, 2, 0).cpu().numpy() * 255).round().astype(np.uint8)
    return Image.fromarray(arr)


def _fit(img: Image.Image, side: int) -> Image.Image:
    if max(img.size) <= side:
        return img
    s = side / max(img.size)
    return img.resize((round(img.width * s), round(img.height * s)), Image.Resampling.LANCZOS)


def _apply_delta(original: Image.Image, work: Image.Image, delta: torch.Tensor) -> Image.Image:
    x = to_tensor(original, delta.device)
    if original.size != work.size:
        delta = F.interpolate(delta, size=x.shape[-2:], mode="bicubic", align_corners=False)
    return to_image(x + delta)
