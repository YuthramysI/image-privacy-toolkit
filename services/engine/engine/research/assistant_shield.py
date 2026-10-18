"""Prototipo de investigación: escudo contra asistentes cerrados (Gemini, ChatGPT).

Los asistentes "ven" la imagen con codificadores de visión parecidos a CLIP.
Una perturbación optimizada contra un ensamble de codificadores abiertos puede
transferirse a ellos (M-Attack). Modo:

  identidad  lleva lo que ven hacia un señuelo neutro (un busto de mármol),
             para que no reconozcan ni conserven la cara. Nunca hacia otra
             persona real.

Siempre invisible (±8/255 con presupuesto perceptual), con recortes locales
aleatorios y las transformaciones de una subida a redes (EOT).

  python -m engine.research.assistant_shield samples/faces/kim.jpg --mode identidad
"""

from __future__ import annotations

import argparse
import math
import random
import time
from dataclasses import dataclass
from pathlib import Path

import open_clip
import torch
import torch.nn.functional as F
from PIL import Image, ImageOps
from transformers import AutoModel, AutoTokenizer

from ..device import configure_threads, pick_device
from ..eval.run import social_upload
from ..protect import budget, eot
from ..protect.pipeline import to_image, to_tensor

DECOYS = Path(__file__).resolve().parents[2] / "samples/decoys"

OPENAI_MEAN, OPENAI_STD = (0.48145466, 0.4578275, 0.40821073), (0.26862954, 0.26130258, 0.27577711)
IMAGENET_MEAN, IMAGENET_STD = (0.485, 0.456, 0.406), (0.229, 0.224, 0.225)


@dataclass
class Surrogate:
    name: str
    model: torch.nn.Module
    mean: tuple[float, float, float]
    std: tuple[float, float, float]
    kind: str  # "openclip" | "siglip" | "dino"
    tokenizer: object | None = None
    size: int = 224

    def _norm(self, x: torch.Tensor) -> torch.Tensor:
        m = torch.tensor(self.mean, device=x.device).view(1, 3, 1, 1)
        s = torch.tensor(self.std, device=x.device).view(1, 3, 1, 1)
        return (x - m) / s

    def image(self, x: torch.Tensor) -> torch.Tensor:
        x = self._norm(F.interpolate(x, size=(self.size, self.size), mode="bilinear", antialias=True, align_corners=False))
        if self.kind == "openclip":
            f = self.model.encode_image(x)
        elif self.kind == "siglip":
            f = self.model.get_image_features(pixel_values=x)
            f = getattr(f, "pooler_output", f)
        else:
            f = self.model(pixel_values=x).pooler_output
        return F.normalize(f, dim=-1)

    @torch.no_grad()
    def text(self, prompts: list[str]) -> torch.Tensor | None:
        if self.kind == "openclip":
            f = self.model.encode_text(self.tokenizer(prompts))
        elif self.kind == "siglip":
            tok = self.tokenizer(prompts, padding="max_length", return_tensors="pt")
            f = self.model.get_text_features(input_ids=tok["input_ids"])
            f = getattr(f, "pooler_output", f)
        else:
            return None  # DINOv2 no tiene torre de texto
        return F.normalize(f, dim=-1)


def _freeze(m: torch.nn.Module, device: torch.device) -> torch.nn.Module:
    m = m.eval().to(device)
    for p in m.parameters():
        p.requires_grad_(False)
    return m


def load_surrogates(device: torch.device) -> list[Surrogate]:
    out = []
    for arch, tag in (("ViT-B-32", "laion2b_s34b_b79k"), ("ViT-B-16", "laion2b_s34b_b88k")):
        model, _, _ = open_clip.create_model_and_transforms(arch, pretrained=tag)
        out.append(Surrogate(f"openclip-{arch}", _freeze(model, device), OPENAI_MEAN, OPENAI_STD, "openclip", open_clip.get_tokenizer(arch)))
    siglip = AutoModel.from_pretrained("google/siglip-base-patch16-224")
    out.append(Surrogate("siglip-b16", _freeze(siglip, device), (0.5, 0.5, 0.5), (0.5, 0.5, 0.5), "siglip", AutoTokenizer.from_pretrained("google/siglip-base-patch16-224")))
    dino = AutoModel.from_pretrained("facebook/dinov2-base")
    out.append(Surrogate("dinov2-b", _freeze(dino, device), IMAGENET_MEAN, IMAGENET_STD, "dino"))
    return out


def load_holdout(device: torch.device) -> Surrogate:
    model, _, _ = open_clip.create_model_and_transforms("ViT-L-14", pretrained="openai")
    return Surrogate("openai-ViT-L-14", _freeze(model, device), OPENAI_MEAN, OPENAI_STD, "openclip", open_clip.get_tokenizer("ViT-L-14"))


def targets(surrogates: list[Surrogate], mode: str, device: torch.device) -> dict[str, torch.Tensor]:
    out = {}
    if mode == "identidad":
        decoys = [to_tensor(Image.open(p).convert("RGB"), device) for p in sorted(DECOYS.glob("*.jpg"))]
        with torch.no_grad():
            for s in surrogates:
                out[s.name] = F.normalize(torch.cat([s.image(d) for d in decoys]).mean(0, keepdim=True), dim=-1)
    return out


def random_crop(x: torch.Tensor, rng: random.Random, scale=(0.5, 1.0)) -> torch.Tensor:
    """Recorte local aleatorio (emparejamiento local-global de M-Attack)."""
    h, w = x.shape[-2:]
    a = rng.uniform(*scale)
    ch, cw = max(32, int(h * math.sqrt(a))), max(32, int(w * math.sqrt(a)))
    y0, x0 = rng.randint(0, h - ch), rng.randint(0, w - cw)
    return x[..., y0 : y0 + ch, x0 : x0 + cw]


def shield(
    img: Image.Image,
    surrogates: list[Surrogate],
    target: dict[str, torch.Tensor],
    perceptual: budget.Perceptual,
    eps: float = 8 / 255,
    steps: int = 300,
    seed: int = 0,
    log_every: int = 25,
) -> Image.Image:
    device = next(surrogates[0].model.parameters()).device
    rng = random.Random(seed)
    torch.manual_seed(seed)
    x = to_tensor(img, device)
    emap = budget.eps_map(x, eps, floor=0.6)
    delta = budget.project((torch.rand_like(x) * 2 - 1) * emap * 0.5, x, emap).requires_grad_(True)
    cfg = eot.EOTConfig(sizes=(512, 768, 1024))
    active = [s for s in surrogates if s.name in target]
    t0 = time.time()
    for step in range(steps):
        adv = (x + delta).clamp(0, 1)
        view = random_crop(eot.apply(adv, eot.sample(cfg, rng)), rng)
        sims = torch.stack([(s.image(view) * target[s.name]).sum() for s in active])
        lp = perceptual(adv, x)
        loss = -sims.mean() + 1.0 * lp
        (grad,) = torch.autograd.grad(loss, delta)
        with torch.no_grad():
            alpha = eps * (0.02 + 0.18 * 0.5 * (1 + math.cos(math.pi * step / steps)))
            delta -= alpha * grad.sign()
            delta.copy_(budget.project(delta, x, emap))
        if log_every and (step + 1) % log_every == 0:
            print(f"  paso {step + 1}/{steps}  sim_objetivo={sims.mean().item():.3f}  lpips={lp.item():.4f}  {time.time() - t0:.0f}s", flush=True)
    return to_image((x + delta.detach()).clamp(0, 1))


@torch.no_grad()
def proxy_report(holdout: Surrogate, img: Image.Image, mode: str) -> dict[str, float]:
    """¿Qué ve un CLIP que el ataque nunca usó? Probabilidad de cada etiqueta."""
    labels = ["a photo of a person", "a marble statue"]
    device = next(holdout.model.parameters()).device
    im = holdout.image(to_tensor(img, device))
    tx = holdout.text(labels)
    probs = (100 * im @ tx.T).softmax(-1)[0]
    return {lab: round(float(p), 3) for lab, p in zip(labels, probs)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+", type=Path)
    ap.add_argument("--mode", choices=["identidad"], default="identidad")
    ap.add_argument("--steps", type=int, default=300)
    ap.add_argument("--eps", type=float, default=8, help="en niveles de 255")
    ap.add_argument("--out", type=Path, default=Path("reports/shield"))
    args = ap.parse_args()

    configure_threads()
    device = pick_device()
    surrogates = load_surrogates(device)
    holdout = load_holdout(device)
    perceptual = budget.Perceptual(device)
    target = targets(surrogates, args.mode, device)
    out_dir = args.out / args.mode
    out_dir.mkdir(parents=True, exist_ok=True)

    for path in args.images:
        img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
        print(f"{path.name}: antes {proxy_report(holdout, social_upload(img), args.mode)}", flush=True)
        prot = shield(img, surrogates, target, perceptual, eps=args.eps / 255, steps=args.steps)
        prot.save(out_dir / f"{path.stem}-{args.mode}.png")
        print(f"{path.name}: después (tras subir a red social) {proxy_report(holdout, social_upload(prot), args.mode)}", flush=True)


if __name__ == "__main__":
    main()
