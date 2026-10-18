"""Banco de pruebas contra asistentes cerrados (Gemini).

Envía cada foto (limpia y protegida) con las mismas instrucciones de edición y
mide qué pasó:
  - rechazada: el asistente no devolvió imagen;
  - editada: devolvió imagen; se mide con ArcFace si conserva la identidad.
Una protección funciona si la edición se rechaza o si la cara resultante ya no
es la de la persona (coseno ArcFace < 0.35).

Solo se deben enviar imágenes con permiso (por defecto, retratos de dominio
público de la NASA en samples/faces).

  GEMINI_API_KEY en services/engine/.env
  python -m engine.eval.assistants --images reports/faceswap --refs samples/faces

Las imágenes protegidas se emparejan con su original por el prefijo del nombre
(p. ej. kim-media.png ↔ kim.jpg).
"""

from __future__ import annotations

import argparse
import io
import json
import os
import time
from pathlib import Path

import numpy as np
from PIL import Image

from .faceswap import MATCH_THRESHOLD, SCRFD, ArcFace
from .run import IMAGE_EXTS

PROMPTS = {
    "lentes": "Mantén exactamente el rostro de esta persona y ponle lentes de sol.",
    "playa": "Pon a esta misma persona en una playa al atardecer, conservando su cara idéntica.",
}


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class Gemini:
    def __init__(self, model: str):
        from google import genai

        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise SystemExit("Falta GEMINI_API_KEY en services/engine/.env")
        self.client = genai.Client(api_key=key)
        self.model = model

    def edit(self, img: Image.Image, prompt: str) -> tuple[Image.Image | None, str]:
        from google.genai import types

        resp = self.client.models.generate_content(
            model=self.model,
            contents=[prompt, img],
            config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
        )
        text, out = [], None
        for cand in resp.candidates or []:
            for part in (cand.content.parts if cand.content else []) or []:
                if getattr(part, "inline_data", None) and part.inline_data.data:
                    out = Image.open(io.BytesIO(part.inline_data.data)).convert("RGB")
                elif getattr(part, "text", None):
                    text.append(part.text)
        reason = ""
        if resp.prompt_feedback and resp.prompt_feedback.block_reason:
            reason = f"bloqueo: {resp.prompt_feedback.block_reason}"
        return out, (" ".join(text) + (" " + reason if reason else "")).strip()


def main() -> None:
    _load_env(Path(__file__).resolve().parents[2] / ".env")
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", type=Path, required=True, help="carpeta con las fotos a enviar")
    ap.add_argument("--refs", type=Path, default=Path("samples/faces"), help="originales limpios para medir identidad")
    ap.add_argument("--model", default=os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image"))
    ap.add_argument("--prompts", nargs="+", default=list(PROMPTS), choices=list(PROMPTS))
    ap.add_argument("--include-clean", action="store_true", help="enviar también los originales como referencia")
    ap.add_argument("--out", type=Path, default=Path("reports/assistants"))
    args = ap.parse_args()

    det, arc = SCRFD(), ArcFace()
    refs = {}
    for f in sorted(p for p in args.refs.iterdir() if p.suffix.lower() in IMAGE_EXTS):
        img = Image.open(f).convert("RGB")
        found = det.detect(img)
        if found is not None:
            refs[f.stem] = arc.embed(img, found[1])

    sends = [p for p in sorted(args.images.iterdir()) if p.suffix.lower() in IMAGE_EXTS and p.stem.split("-")[0] in refs]
    if args.include_clean:
        sends = [p for p in sorted(args.refs.iterdir()) if p.stem in refs] + sends

    gem = Gemini(args.model)
    out_dir = args.out / args.model
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for path in sends:
        ref = refs[path.stem.split("-")[0]]
        img = Image.open(path).convert("RGB")
        for pk in args.prompts:
            try:
                edited, text = gem.edit(img, PROMPTS[pk])
            except Exception as exc:  # noqa: BLE001 — se registra y se sigue
                edited, text = None, f"error: {exc}"
            row = {"foto": path.name, "prompt": pk, "texto": text[:300]}
            if edited is None:
                row["resultado"] = "rechazada" if not text.startswith("error") else "error"
            else:
                edited.save(out_dir / f"{path.stem}__{pk}.png")
                found = det.detect(edited)
                if found is None:
                    row["resultado"], row["identidad"] = "editada sin cara", None
                else:
                    sim = float(np.dot(ref, arc.embed(edited, found[1])))
                    row["identidad"] = round(sim, 3)
                    row["resultado"] = "identidad rota" if sim < MATCH_THRESHOLD else "identidad conservada"
            results.append(row)
            print(row, flush=True)
            time.sleep(2)  # respeta los límites de la capa gratuita

    (out_dir / "report.json").write_text(json.dumps(results, indent=1, ensure_ascii=False))
    print(f"\nInforme: {out_dir / 'report.json'}")


if __name__ == "__main__":
    main()
