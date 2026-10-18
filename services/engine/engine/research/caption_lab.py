"""Laboratorio del OBJETIVO REAL: degradar la DESCRIPCIÓN, no un embedding.

Cambio de método tras la prueba directa en Gemini: la distancia de embedding en
CLIP no predice nada sobre un modelo comercial. Aquí se ataca y se mide un VLM
que GENERA texto (BLIP), y se evalúa la precisión de los atributos del caption.
La transferencia se mide en un segundo VLM NO visto (ViT-GPT2), de arquitectura
y entrenamiento distintos.

Ataque: maximizar la pérdida de lenguaje del caption correcto bajo BLIP (ataque
generativo directo, 1 forward con teacher forcing) + alejar las activaciones
intermedias del encoder de visión (ILA, para transferir). Presupuesto JND
invisible + EOT (JPEG/reescalado) para robustez.

Criterio de éxito (objetivo real): el caption pierde atributos correctos o mete
errores, en BLIP (atacado) Y en el VLM no visto (transferencia), manteniendo
calidad visual. No se mide distancia de embedding.

  python -m engine.research.caption_lab samples/faces/jemison.jpg --steps 80
"""

from __future__ import annotations

import argparse
import math
import random
import time
from pathlib import Path

import torch
import torch.nn.functional as F
from PIL import Image, ImageOps

from ..device import configure_threads, pick_device
from ..eval.run import social_upload
from ..protect import budget, eot
from ..protect.pipeline import to_image, to_tensor

MEAN = (0.48145466, 0.4578275, 0.40821073)
STD = (0.26862954, 0.26130258, 0.27577711)
ILA_LAYERS = (3, 5, 7, 9)


def _norm(x, size):
    m = torch.tensor(MEAN, device=x.device).view(1, 3, 1, 1)
    s = torch.tensor(STD, device=x.device).view(1, 3, 1, 1)
    return (F.interpolate(x, size=(size, size), mode="bilinear", antialias=True, align_corners=False) - m) / s


class CaptionModels:
    def __init__(self, device):
        from transformers import (
            AutoTokenizer,
            BlipForConditionalGeneration,
            BlipProcessor,
            VisionEncoderDecoderModel,
            ViTImageProcessor,
        )

        self.device = device
        self.blip_proc = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
        self.blip = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base").eval().to(device)
        for p in self.blip.parameters():
            p.requires_grad_(False)
        # Juez no visto: captioner distinto (ViT encoder + GPT2 decoder).
        self.vg = VisionEncoderDecoderModel.from_pretrained("nlpconnect/vit-gpt2-image-captioning").eval().to(device)
        self.vg_fe = ViTImageProcessor.from_pretrained("nlpconnect/vit-gpt2-image-captioning")
        self.vg_tok = AutoTokenizer.from_pretrained("nlpconnect/vit-gpt2-image-captioning")
        for p in self.vg.parameters():
            p.requires_grad_(False)

    @torch.no_grad()
    def caption_blip(self, img: Image.Image) -> str:
        inp = self.blip_proc(img, return_tensors="pt").to(self.device)
        out = self.blip.generate(**inp, max_new_tokens=30)
        return self.blip_proc.decode(out[0], skip_special_tokens=True).strip()

    @torch.no_grad()
    def caption_vg(self, img: Image.Image) -> str:
        pv = self.vg_fe(img, return_tensors="pt").pixel_values.to(self.device)
        out = self.vg.generate(pv, max_new_tokens=30)
        return self.vg_tok.decode(out[0], skip_special_tokens=True).strip()


def attack(img: Image.Image, M: CaptionModels, eps=8 / 255, steps=80, mode="gen+ila", seed=0, log=False):
    device = M.device
    rng = random.Random(seed)
    torch.manual_seed(seed)
    x = to_tensor(img, device)

    # Caption correcto (el que BLIP da en la imagen limpia): el objetivo es que
    # el modelo deje de poder producirlo.
    target_caption = M.caption_blip(img)
    ids = M.blip_proc(text=target_caption, return_tensors="pt").input_ids.to(device)

    # Hooks ILA en el encoder de visión de BLIP.
    acts = {}
    hooks = []
    if "ila" in mode:
        for i in ILA_LAYERS:
            hooks.append(M.blip.vision_model.encoder.layers[i].register_forward_hook(
                lambda _m, _i, o, k=i: acts.__setitem__(k, o[0] if isinstance(o, tuple) else o)
            ))
    with torch.no_grad():
        M.blip.vision_model(_norm(x, 384))
        clean_mid = {k: F.normalize(v.reshape(1, -1), dim=-1) for k, v in acts.items()}

    emap = budget.jnd_eps_map(x, eps)
    delta = budget.project((torch.rand_like(x) * 2 - 1) * emap * 0.4, x, emap).requires_grad_(True)
    mom = torch.zeros_like(x)
    cfg = eot.EOTConfig(sizes=(320, 384))
    t0 = time.time()

    for step in range(steps):
        adv = (x + delta).clamp(0, 1)
        view = eot.apply(adv, eot.sample(cfg, rng))
        acts.clear()
        loss = torch.zeros((), device=device)
        if "gen" in mode:
            # maximizar la pérdida de lenguaje del caption correcto (teacher forcing)
            out = M.blip(pixel_values=_norm(view, 384), input_ids=ids, labels=ids)
            loss = loss - out.loss  # minimizar -loss = maximizar la pérdida del modelo
        if "ila" in mode:
            if not acts:
                M.blip.vision_model(_norm(view, 384))
            for k in clean_mid:
                if k in acts:
                    loss = loss + 0.3 * (F.normalize(acts[k].reshape(1, -1), dim=-1) * clean_mid[k]).sum()
        loss = loss + 0.6 * budget.Perceptual(device)(adv, x) if step == 0 else loss  # init cheap; LPIPS cada paso abajo
        lp = budget.Perceptual(device)(adv, x) if step else torch.zeros((), device=device)
        total = loss + 0.6 * lp
        (grad,) = torch.autograd.grad(total, delta)
        with torch.no_grad():
            g = grad / grad.abs().mean().clamp(min=1e-8)
            mom = 0.9 * mom + g
            alpha = eps * (0.03 + 0.17 * 0.5 * (1 + math.cos(math.pi * step / steps)))
            delta -= alpha * mom.sign()
            delta.copy_(budget.project(delta, x, emap))
        if log and (step + 1) % 20 == 0:
            print(f"    paso {step+1}/{steps} {time.time()-t0:.0f}s", flush=True)

    for h in hooks:
        h.remove()
    return to_image((x + delta.detach()).clamp(0, 1)), target_caption


# Atributos esperados por imagen (para medir precisión del caption de forma consistente).
EXPECTED = {
    "jemison": ["woman", "blue", "uniform"],
    "clark": ["woman", "blue", "uniform"],
    "kim": ["man", "blue", "uniform"],
    "chawla": ["woman", "orange", "suit"],
    "rubio": ["man", "blue"],
    "melroy": ["woman", "blue"],
}


def attrib_score(caption: str, keys: list[str]) -> str:
    c = caption.lower()
    hit = [k for k in keys if k in c]
    return f"{len(hit)}/{len(keys)} [{','.join(hit)}]"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+", type=Path)
    ap.add_argument("--steps", type=int, default=80)
    ap.add_argument("--eps", type=float, default=8.0)
    ap.add_argument("--mode", default="gen+ila", choices=["gen", "ila", "gen+ila"])
    ap.add_argument("--out", type=Path, default=Path("reports/caption_lab"))
    args = ap.parse_args()

    configure_threads()
    device = pick_device()
    print(f"dispositivo: {device} — cargando VLMs...", flush=True)
    M = CaptionModels(device)
    import lpips as _l

    lp = _l.LPIPS(net="alex", verbose=False).to(device)
    args.out.mkdir(parents=True, exist_ok=True)

    for path in args.images:
        key = path.stem
        img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
        keys = EXPECTED.get(key, ["person"])
        up_clean = social_upload(img)
        cb0, cv0 = M.caption_blip(up_clean), M.caption_vg(up_clean)
        prot, target = attack(img, M, eps=args.eps / 255, steps=args.steps, mode=args.mode)
        prot.save(args.out / f"{key}-cap.png")
        up_prot = social_upload(prot)
        cb1, cv1 = M.caption_blip(up_prot), M.caption_vg(up_prot)
        with torch.no_grad():
            a = to_tensor(img, device) * 2 - 1
            b = to_tensor(prot.resize(img.size), device) * 2 - 1
            visib = float(lp(a, b).mean())
        print(f"\n=== {key} === (modo {args.mode}, tras subir a redes)")
        print(f"  BLIP (atacado)  limpia: {cb0}")
        print(f"                  proteg: {cb1}")
        print(f"     atributos: limpia {attrib_score(cb0,keys)} -> proteg {attrib_score(cb1,keys)}")
        print(f"  ViT-GPT2 (NO visto) limpia: {cv0}")
        print(f"                      proteg: {cv1}")
        print(f"     atributos: limpia {attrib_score(cv0,keys)} -> proteg {attrib_score(cv1,keys)}")
        print(f"  visibilidad LPIPS: {visib:.4f}", flush=True)


if __name__ == "__main__":
    main()
