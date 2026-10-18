"""Laboratorio de transferencia — módulo 2 (investigación propia).

Pregunta: ¿cómo lograr que una perturbación invisible optimizada contra unos
pocos codificadores de visión en CPU transfiera a un codificador NO VISTO (proxy
de un modelo cerrado grande)?

Hipótesis H-ILA: atacar el *embedding final* de CLIP sobreajusta a cada modelo.
Las activaciones *intermedias* capturan rasgos visuales más genéricos y
compartidos entre arquitecturas, así que atacarlas debería transferir mejor.
(Base: Intermediate Level Attack, Huang et al. 2019; aquí aplicado a CLIP para
protección de imágenes, con evaluación en codificadores no vistos.)

Se compara, con el MISMO presupuesto invisible y las mismas transformaciones:
  - baseline  : ataca el embedding final (acercar a señuelo, alejar del limpio)
  - ila       : aleja las activaciones de varias capas intermedias
  - ila+final : combinación

Métrica de transferencia (en el juez NO visto, tras subir a redes): distancia
coseno del embedding entre la imagen limpia y la protegida. Mayor = el juez
"ve" algo más distinto = mejor transferencia. Se reporta también el efecto en
los modelos atacados (para detectar sobreajuste) y la visibilidad (LPIPS).

  python -m engine.research.transfer_lab samples/faces/kim.jpg --steps 120
"""

from __future__ import annotations

import argparse
import math
import random
import time
from dataclasses import dataclass, field
from pathlib import Path

import open_clip
import torch
import torch.nn.functional as F
from PIL import Image, ImageOps

from ..device import configure_threads, pick_device
from ..eval.run import social_upload
from ..protect import budget, eot
from ..protect.pipeline import to_image, to_tensor

OPENAI_MEAN = (0.48145466, 0.4578275, 0.40821073)
OPENAI_STD = (0.26862954, 0.26130258, 0.27577711)
DECOY_PROMPTS = ["rough grey concrete texture", "a pile of dry autumn leaves", "abstract coloured noise"]
TRUTH_PROMPTS = ["a photograph of a person's face", "a portrait of a human being"]
# Capas intermedias a atacar (de 12). Medias: rasgos genéricos compartidos.
ILA_LAYERS = (3, 5, 7, 9)


@dataclass
class Encoder:
    name: str
    model: torch.nn.Module
    tokenizer: object
    held_out: bool = False
    size: int = 224
    _acts: dict = field(default_factory=dict)
    _hooks: list = field(default_factory=list)

    def _prep(self, x: torch.Tensor) -> torch.Tensor:
        m = torch.tensor(OPENAI_MEAN, device=x.device).view(1, 3, 1, 1)
        s = torch.tensor(OPENAI_STD, device=x.device).view(1, 3, 1, 1)
        return (F.interpolate(x, size=(self.size, self.size), mode="bilinear", antialias=True, align_corners=False) - m) / s

    def hook_layers(self, layers=ILA_LAYERS) -> None:
        blocks = self.model.visual.transformer.resblocks
        for i in layers:
            if i < len(blocks):
                self._hooks.append(blocks[i].register_forward_hook(self._make_hook(i)))

    def _make_hook(self, i):
        def hook(_m, _in, out):
            self._acts[i] = out

        return hook

    def image(self, x: torch.Tensor, want_mid: bool = False):
        self._acts.clear()
        emb = F.normalize(self.model.encode_image(self._prep(x)), dim=-1)
        if want_mid:
            return emb, dict(self._acts)
        return emb

    @torch.no_grad()
    def text(self, prompts) -> torch.Tensor:
        return F.normalize(self.model.encode_text(self.tokenizer(prompts)), dim=-1).mean(0, keepdim=True)


def load(device: torch.device):
    specs = [
        ("ViT-B-32", "laion2b_s34b_b79k", False),
        ("ViT-B-16", "laion2b_s34b_b88k", False),
        ("ViT-B-16", "datacomp_xl_s13b_b90k", False),
        ("ViT-B-16-quickgelu", "metaclip_400m", False),
        ("ViT-B-32", "datacomp_m_s128m_b4k", True),  # juez no visto
    ]
    out = []
    for arch, tag, held in specs:
        try:
            m, _, _ = open_clip.create_model_and_transforms(arch, pretrained=tag)
            m = m.eval().to(device)
            for p in m.parameters():
                p.requires_grad_(False)
            out.append(Encoder(f"{arch}:{tag[:8]}", m, open_clip.get_tokenizer(arch), held))
        except Exception as e:  # noqa: BLE001
            print(f"  (omitido {arch}/{tag}: {str(e)[:50]})")
    return out


def _tokens(acts: dict) -> list[torch.Tensor]:
    # (seq, batch, dim) o (batch, seq, dim) → aplanar por muestra
    out = []
    for v in acts.values():
        t = v if v.shape[0] == 1 else v.transpose(0, 1)
        out.append(F.normalize(t.reshape(1, -1), dim=-1))
    return out


def random_crop(x, rng, scale=(0.6, 1.0)):
    h, w = x.shape[-2:]
    a = rng.uniform(*scale)
    ch, cw = max(64, int(h * math.sqrt(a))), max(64, int(w * math.sqrt(a)))
    y0, x0 = rng.randint(0, h - ch), rng.randint(0, w - cw)
    return x[..., y0 : y0 + ch, x0 : x0 + cw]


def attack(img, encoders, perceptual, mode, eps=8 / 255, steps=120, lpips_w=0.6, seed=0, log=False):
    device = next(encoders[0].model.parameters()).device
    rng = random.Random(seed)
    torch.manual_seed(seed)
    att = [e for e in encoders if not e.held_out]
    if mode in ("ila", "ila+final"):
        for e in att:
            e.hook_layers()

    x = to_tensor(img, device)
    decoy = {e.name: e.text(DECOY_PROMPTS) for e in att}
    with torch.no_grad():
        clean_emb, clean_mid = {}, {}
        for e in att:
            emb, mid = e.image(x, want_mid=True)
            clean_emb[e.name] = emb
            clean_mid[e.name] = _tokens(mid)

    emap = budget.jnd_eps_map(x, eps)
    delta = budget.project((torch.rand_like(x) * 2 - 1) * emap * 0.4, x, emap).requires_grad_(True)
    mom = torch.zeros_like(x)
    cfg = eot.EOTConfig(sizes=(224, 288, 384))
    t0 = time.time()

    for step in range(steps):
        adv = (x + delta).clamp(0, 1)
        view = random_crop(eot.apply(adv, eot.sample(cfg, rng)), rng)
        batch = rng.sample(att, k=min(3, len(att)))
        terms = []
        for e in batch:
            out = e.image(view, want_mid=(mode != "baseline"))
            emb, mid = out if isinstance(out, tuple) else (out, None)
            if mode in ("baseline", "ila+final"):
                terms.append(-(emb * decoy[e.name]).sum() + 0.5 * (emb * clean_emb[e.name]).sum())
            if mode in ("ila", "ila+final"):
                # alejar activaciones intermedias de las del limpio (bajar coseno)
                for a_tok, c_tok in zip(_tokens(mid), clean_mid[e.name]):
                    terms.append((a_tok * c_tok).sum())
        loss = torch.stack([t if torch.is_tensor(t) else torch.tensor(t, device=device) for t in terms]).mean()
        loss = loss + lpips_w * perceptual(adv, x)
        (grad,) = torch.autograd.grad(loss, delta)
        with torch.no_grad():
            g = grad / grad.abs().mean().clamp(min=1e-8)
            mom = 0.9 * mom + g
            alpha = eps * (0.03 + 0.17 * 0.5 * (1 + math.cos(math.pi * step / steps)))
            delta -= alpha * mom.sign()
            delta.copy_(budget.project(delta, x, emap))
        if log and (step + 1) % 40 == 0:
            print(f"    {mode} paso {step+1}/{steps} loss {loss.item():.3f} {time.time()-t0:.0f}s", flush=True)

    for e in att:
        for h in e._hooks:
            h.remove()
        e._hooks.clear()
    return to_image((x + delta.detach()).clamp(0, 1))


@torch.no_grad()
def transfer_metrics(encoders, clean_img, prot_img):
    """Distancia coseno del embedding (1 - sim) entre limpio y protegido, tras
    subir a redes. En el juez no visto mide transferencia; en los atacados,
    sobreajuste."""
    device = next(encoders[0].model.parameters()).device
    cu, pu = social_upload(clean_img), social_upload(prot_img)

    def dist(e):
        a = e.image(to_tensor(cu, device))
        b = e.image(to_tensor(pu, device))
        return 1 - float((a * b).sum())

    att = [e for e in encoders if not e.held_out]
    judge = [e for e in encoders if e.held_out]
    return {
        "atacados_dist": round(sum(dist(e) for e in att) / len(att), 3),
        "juez_dist": round(sum(dist(e) for e in judge) / len(judge), 3),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+", type=Path)
    ap.add_argument("--steps", type=int, default=120)
    ap.add_argument("--eps", type=float, default=8.0)
    ap.add_argument("--modes", nargs="+", default=["baseline", "ila", "ila+final"])
    ap.add_argument("--out", type=Path, default=Path("reports/transfer_lab"))
    args = ap.parse_args()

    configure_threads()
    device = pick_device()
    print(f"dispositivo: {device}")
    enc = load(device)
    print(f"codificadores: {len([e for e in enc if not e.held_out])} atacados, {len([e for e in enc if e.held_out])} juez no visto")
    perceptual = budget.Perceptual(device)
    import lpips as _l

    lp = _l.LPIPS(net="alex", verbose=False).to(device)
    args.out.mkdir(parents=True, exist_ok=True)

    for path in args.images:
        img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
        print(f"\n=== {path.name} ===  (distancia mayor en el juez = mejor transferencia)")
        for mode in args.modes:
            prot = attack(img, enc, perceptual, mode, eps=args.eps / 255, steps=args.steps)
            prot.save(args.out / f"{path.stem}-{mode.replace('+','_')}.png")
            m = transfer_metrics(enc, img, prot)
            a = to_tensor(img, device) * 2 - 1
            b = to_tensor(prot.resize(img.size), device) * 2 - 1
            with torch.no_grad():
                visib = float(lp(a, b).mean())
            print(f"  {mode:10s}  juez_dist {m['juez_dist']:.3f}  atacados_dist {m['atacados_dist']:.3f}  LPIPS(visib) {visib:.4f}", flush=True)


if __name__ == "__main__":
    main()
