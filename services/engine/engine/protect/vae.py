"""Capa anti-difusión: ataque al encoder VAE (enfoque de PhotoGuard y Mist).

Los modelos de difusión latente no ven píxeles: ven el latente que produce su
VAE. Si la perturbación arrastra ese latente hacia el de una textura sin
sentido, img2img, inpainting y el fine-tuning (LoRA/DreamBooth) trabajan sobre
basura. Se ataca un ensamble para cubrir varias familias de modelos.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np
import torch
import torch.nn.functional as F
from diffusers import AutoencoderKL, AutoencoderTiny

# Modelos con licencia libre y sin acceso restringido: (repo, subcarpeta, tiny).
ENCODERS: dict[str, tuple[str, str | None, bool]] = {
    # Familia Stable Diffusion 1.x/2.x (MIT).
    "sd": ("stabilityai/sd-vae-ft-mse", None, False),
    # VAE de 16 canales de la familia FLUX.1, vía el derivado Apache-2.0 de
    # FLUX.1-schnell (el repositorio oficial exige aceptar términos).
    "flux": ("ostris/Flex.1-alpha", "vae", False),
    # Familia SDXL (MIT). Solo se usa para evaluar transferencia.
    "sdxl": ("madebyollin/sdxl-vae-fp16-fix", None, False),
    # Sustitutos ligeros (MIT) entrenados para imitar los latentes de los VAE
    # de SD y FLUX. Mucho más baratos en CPU; la transferencia al VAE completo
    # se mide en engine.eval.
    "taesd": ("madebyollin/taesd", None, True),
    "taef1": ("madebyollin/taef1", None, True),
}


@dataclass
class Encoder:
    name: str
    vae: AutoencoderKL | AutoencoderTiny

    @property
    def tiny(self) -> bool:
        return isinstance(self.vae, AutoencoderTiny)

    def encode(self, img: torch.Tensor) -> torch.Tensor:
        # Los VAE esperan [-1, 1]; del VAE completo usamos la media latente.
        out = self.vae.encode(img * 2 - 1)
        return out.latents if self.tiny else out.latent_dist.mean

    def decode(self, latent: torch.Tensor) -> torch.Tensor:
        return (self.vae.decode(latent).sample.clamp(-1, 1) + 1) / 2


def load(names: list[str], device: torch.device) -> dict[str, Encoder]:
    out = {}
    for name in names:
        repo, sub, tiny = ENCODERS[name]
        cls = AutoencoderTiny if tiny else AutoencoderKL
        vae = cls.from_pretrained(repo, subfolder=sub, cache_dir=os.environ.get("ENGINE_CACHE"))
        vae = vae.eval().to(device)
        for p in vae.parameters():
            p.requires_grad_(False)
        out[name] = Encoder(name, vae)
    return out


def target_pattern(h: int, w: int, device: torch.device, seed: int = 7) -> torch.Tensor:
    """Textura de alta frecuencia que sirve de destino del ataque. Determinista
    para que todas las imágenes protegidas compartan el mismo "veneno"."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    chans = []
    for c in range(3):
        f1, f2 = rng.uniform(0.05, 0.25, size=2)
        a = rng.uniform(0, np.pi, size=2)
        stripes = np.sin(f1 * (xx * np.cos(a[0]) + yy * np.sin(a[0])))
        rings = np.sin(f2 * np.hypot(xx - w / 2, yy - h / 2) + c)
        check = ((xx // 16 + yy // 16) % 2) * 2 - 1
        chans.append(0.5 + 0.18 * stripes + 0.18 * rings + 0.1 * check)
    t = torch.from_numpy(np.stack(chans)).float().clamp(0, 1)
    return t[None].to(device)


class TargetCache:
    """Latentes del patrón destino por (encoder, tamaño) para no recalcularlos."""

    def __init__(self, device: torch.device):
        self.device = device
        self._cache: dict[tuple[str, int, int], torch.Tensor] = {}

    def get(self, enc: Encoder, h: int, w: int) -> torch.Tensor:
        key = (enc.name, h, w)
        if key not in self._cache:
            with torch.no_grad():
                self._cache[key] = enc.encode(target_pattern(h, w, self.device))
        return self._cache[key]


def latent_loss(enc: Encoder, img_t: torch.Tensor, cache: TargetCache) -> torch.Tensor:
    h, w = img_t.shape[-2:]
    return F.mse_loss(enc.encode(img_t), cache.get(enc, h, w))
