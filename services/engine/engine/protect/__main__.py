"""Protege imágenes desde la terminal.

  python -m engine.protect foto.jpg [otra.png ...] --preset media --out protegidas/
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

from .. import metadata
from .pipeline import PRESETS, Engine


def main() -> None:
    ap = argparse.ArgumentParser(description="Añade perturbación de protección a imágenes.")
    ap.add_argument("images", nargs="+", type=Path)
    ap.add_argument("--preset", default="media", choices=list(PRESETS))
    ap.add_argument("--out", type=Path, default=Path("protegidas"))
    ap.add_argument("--format", default="png", choices=["png", "jpeg"])
    ap.add_argument("--owner", default=None, help="titular de los derechos (se escribe en los metadatos)")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    engine = Engine(encoders=PRESETS[args.preset].encoders)
    ext = "png" if args.format == "png" else "jpg"
    for path in args.images:

        def show(p, name=path.name):
            print(f"\r{name}: paso {p.step}/{p.total} ({p.elapsed:.0f} s)", end="", flush=True)

        res = engine.protect(Image.open(path), args.preset, on_progress=show)
        dest = args.out / f"{path.stem}-protegida.{ext}"
        dest.write_bytes(metadata.finalize(res.image, args.format, owner=args.owner))
        print(f"\n  → {dest}  ({res.faces} rostro(s), {res.seconds:.0f} s)")


if __name__ == "__main__":
    main()
