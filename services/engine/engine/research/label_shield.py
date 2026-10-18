"""Módulo 2 — Protección frente a extracción de etiquetas, descripciones y
representaciones visuales (investigación; objetivo: modelos grandes cerrados).

Los VLM y captioners (Gemini, ChatGPT y las tuberías de entrenamiento) "ven" la
imagen con codificadores de visión parecidos a CLIP. Si una perturbación
optimizada contra un conjunto diverso de codificadores abiertos empuja la imagen
hacia una etiqueta señuelo y lejos de lo que realmente es, el modelo grande
—que comparte familia con esos codificadores— tiende a describirla mal.

Implementación propia (licencia MIT) del método, no copia de ningún repositorio.
Técnicas aplicadas, con base en la literatura (M-Attack; VEIL-PGD como
referencia de resultados):
  - conjunto DIVERSO de codificadores (varios datos de entrenamiento), no grande;
  - pérdida mixta: acercar a una etiqueta señuelo (targeted) y alejar del
    embedding limpio (untargeted);
  - PGD con momento;
  - EOT con JPEG, reescalado y recorte en cada paso (sobrevive a la subida);
  - presupuesto perceptual JND + LPIPS para que sea invisible;
  - jueces "no vistos" (codificadores que el ataque nunca usa) para medir honesto.

En CPU corre un conjunto reducido para prototipar; la versión fuerte necesita
GPU (Kaggle/Colab) con más codificadores.

  python -m engine.research.label_shield samples/faces/kim.jpg --steps 150
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

from ..device import configure_threads, pick_device
from ..eval.run import social_upload
from ..protect import budget, eot
from ..protect.pipeline import to_image, to_tensor

OPENAI_MEAN, OPENAI_STD = (0.48145466, 0.4578275, 0.40821073), (0.26862954, 0.26130258, 0.27577711)

# Etiqueta señuelo: materiales/objetos neutros hacia los que empujar la imagen.
# Nunca otra persona real. El objetivo es que el modelo "no vea" a la persona.
DECOY_PROMPTS = [
    "a close-up photograph of rough grey concrete texture",
    "a pile of dry autumn leaves on the ground",
    "an abstract pattern of coloured noise",
]
# "Verdad" de la que alejarse (para fotos con rostro).
TRUTH_PROMPTS = ["a photograph of a person's face", "a portrait of a human being"]


@dataclass
class Encoder:
    name: str
    model: torch.nn.Module
    tokenizer: object
    mean: tuple
    std: tuple
    size: int = 224
    held_out: bool = False

    def _prep(self, x: torch.Tensor) -> torch.Tensor:
        m = torch.tensor(self.mean, device=x.device).view(1, 3, 1, 1)
        s = torch.tensor(self.std, device=x.device).view(1, 3, 1, 1)
        return (F.interpolate(x, size=(self.size, self.size), mode="bilinear", antialias=True, align_corners=False) - m) / s

    def image(self, x: torch.Tensor) -> torch.Tensor:
        return F.normalize(self.model.encode_image(self._prep(x)), dim=-1)

    @torch.no_grad()
    def text(self, prompts: list[str]) -> torch.Tensor:
        return F.normalize(self.model.encode_text(self.tokenizer(prompts)), dim=-1).mean(0, keepdim=True)


def _load(arch: str, pretrained: str, device: torch.device, held_out: bool = False) -> Encoder:
    model, _, _ = open_clip.create_model_and_transforms(arch, pretrained=pretrained)
    model = model.eval().to(device)
    for p in model.parameters():
        p.requires_grad_(False)
    return Encoder(f"{arch}/{pretrained}", model, open_clip.get_tokenizer(arch), OPENAI_MEAN, OPENAI_STD, held_out=held_out)


def load_ensemble(device: torch.device, strong: bool = False) -> list[Encoder]:
    """Conjunto DIVERSO: lo que importa para transferir es la variedad de datos
    de entrenamiento, no solo el tamaño. En CPU, modelos base."""
    specs = [
        ("ViT-B-32", "laion2b_s34b_b79k", False),
        ("ViT-B-16", "laion2b_s34b_b88k", False),
        ("ViT-B-16", "datacomp_xl_s13b_b90k", False),
        ("ViT-B-16-quickgelu", "metaclip_400m", False),
        # Juez no visto: nunca se ataca, sirve para medir transferencia honesta.
        ("ViT-B-32", "datacomp_m_s128m_b4k", True),
    ]
    if strong:  # para GPU: añade modelos grandes
        specs += [("ViT-L-14", "laion2b_s32b_b82k", False), ("EVA02-L-14", "merged2b_s4b_b131k", False)]
    out = []
    for arch, tag, held in specs:
        try:
            out.append(_load(arch, tag, device, held))
        except Exception as e:  # noqa: BLE001 — si un modelo no está disponible, se omite
            print(f"  (omitido {arch}/{tag}: {str(e)[:60]})")
    return out


def random_crop(x: torch.Tensor, rng: random.Random, scale=(0.4, 1.0)) -> torch.Tensor:
    h, w = x.shape[-2:]
    a = rng.uniform(*scale)
    ch, cw = max(48, int(h * math.sqrt(a))), max(48, int(w * math.sqrt(a)))
    y0, x0 = rng.randint(0, h - ch), rng.randint(0, w - cw)
    return x[..., y0 : y0 + ch, x0 : x0 + cw]


def shield(
    img: Image.Image,
    encoders: list[Encoder],
    perceptual: budget.Perceptual,
    eps: float = 6 / 255,
    steps: int = 150,
    stealth: bool = True,
    seed: int = 0,
    log_every: int = 25,
) -> Image.Image:
    device = next(encoders[0].model.parameters()).device
    rng = random.Random(seed)
    torch.manual_seed(seed)
    attack = [e for e in encoders if not e.held_out]

    x = to_tensor(img, device)
    decoy = {e.name: e.text(DECOY_PROMPTS) for e in attack}
    truth = {e.name: e.text(TRUTH_PROMPTS) for e in attack}
    with torch.no_grad():
        clean = {e.name: e.image(x) for e in attack}

    emap = budget.jnd_eps_map(x, eps) if stealth else (eps * torch.ones_like(x))
    delta = budget.project((torch.rand_like(x) * 2 - 1) * emap * 0.4, x, emap).requires_grad_(True)
    momentum = torch.zeros_like(x)
    eot_cfg = eot.EOTConfig(sizes=(224, 288, 384))
    t0 = time.time()

    for step in range(steps):
        adv = (x + delta).clamp(0, 1)
        view = random_crop(eot.apply(adv, eot.sample(eot_cfg, rng)), rng)
        # Un subconjunto de codificadores por paso (más variedad, más barato).
        batch = rng.sample(attack, k=min(3, len(attack)))
        terms = []
        for e in batch:
            emb = e.image(view)
            # acercar a señuelo, alejar de la verdad y del embedding limpio
            terms.append(-(emb * decoy[e.name]).sum() + 0.5 * (emb * truth[e.name]).sum() + 0.5 * (emb * clean[e.name]).sum())
        loss = torch.stack(terms).mean()
        if stealth:
            loss = loss + 3.0 * perceptual(adv, x)
        (grad,) = torch.autograd.grad(loss, delta)
        with torch.no_grad():
            g = grad / grad.abs().mean().clamp(min=1e-8)
            momentum = 0.9 * momentum + g
            alpha = eps * (0.03 + 0.17 * 0.5 * (1 + math.cos(math.pi * step / steps)))
            delta -= alpha * momentum.sign()
            delta.copy_(budget.project(delta, x, emap))
        if log_every and (step + 1) % log_every == 0:
            print(f"  paso {step + 1}/{steps}  loss {loss.item():.3f}  {time.time() - t0:.0f}s", flush=True)
    return to_image((x + delta.detach()).clamp(0, 1))


@torch.no_grad()
def judge(encoders: list[Encoder], img: Image.Image) -> dict:
    """Con los codificadores NO vistos: ¿la imagen se parece más a la verdad
    ('persona') o al señuelo? Es el indicador de si el ataque transfiere."""
    device = next(encoders[0].model.parameters()).device
    held = [e for e in encoders if e.held_out] or encoders
    x = to_tensor(img, device)
    truth_sim, decoy_sim = [], []
    for e in held:
        emb = e.image(x)
        truth_sim.append(float((emb * e.text(TRUTH_PROMPTS)).sum()))
        decoy_sim.append(float((emb * e.text(DECOY_PROMPTS)).sum()))
    t, d = sum(truth_sim) / len(truth_sim), sum(decoy_sim) / len(decoy_sim)
    probs = torch.tensor([t, d]).mul(100).softmax(0)
    return {"verdad(persona)": round(float(probs[0]), 3), "senuelo": round(float(probs[1]), 3)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+", type=Path)
    ap.add_argument("--steps", type=int, default=150)
    ap.add_argument("--eps", type=float, default=6.0, help="en niveles de 255")
    ap.add_argument("--strong", action="store_true", help="conjunto grande (requiere GPU)")
    ap.add_argument("--no-stealth", action="store_true", help="sin presupuesto invisible (más fuerte, visible)")
    ap.add_argument("--out", type=Path, default=Path("reports/label_shield"))
    args = ap.parse_args()

    configure_threads()
    device = pick_device()
    print(f"dispositivo: {device}")
    encoders = load_ensemble(device, strong=args.strong)
    print(f"codificadores: {len([e for e in encoders if not e.held_out])} atacados, {len([e for e in encoders if e.held_out])} jueces")
    perceptual = budget.Perceptual(device)
    args.out.mkdir(parents=True, exist_ok=True)

    for path in args.images:
        img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
        print(f"\n{path.name}  antes (juez no visto, tras subir a redes): {judge(encoders, social_upload(img))}", flush=True)
        prot = shield(img, encoders, perceptual, eps=args.eps / 255, steps=args.steps, stealth=not args.no_stealth)
        prot.save(args.out / f"{path.stem}-label.png")
        print(f"{path.name}  después: {judge(encoders, social_upload(prot))}", flush=True)


if __name__ == "__main__":
    main()
