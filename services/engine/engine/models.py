"""Modelos que no se distribuyen con el repositorio.

El reconocedor ArcFace de InsightFace (paquete buffalo_l) es el que usan las
herramientas de face-swap (roop, FaceFusion) para copiar una identidad, así que
la capa de rostro lo ataca directamente. Su licencia es de investigación no
comercial: cada persona lo descarga desde la fuente oficial y acepta esa
licencia. Sin él, la capa de rostro usa solo FaceNet (mucho menos eficaz contra
el face-swap).

  python -m engine.models download
"""

from __future__ import annotations

import io
import os
import sys
import urllib.request
import zipfile
from pathlib import Path

BUFFALO_URL = "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip"
LICENSE_NOTE = (
    "Los modelos de InsightFace (buffalo_l) se publican solo para investigación no comercial:\n"
    "https://github.com/deepinsight/insightface#license\n"
)


def models_dir() -> Path:
    return Path(os.environ.get("VELO_MODELS", Path.home() / ".cache/velo/models"))


def arcface_path() -> Path | None:
    for candidate in (models_dir() / "buffalo_l/w600k_r50.onnx", Path.home() / ".cache/velo-eval/buffalo_l/w600k_r50.onnx"):
        if candidate.exists():
            return candidate
    return None


def download() -> Path:
    dest = models_dir() / "buffalo_l"
    dest.mkdir(parents=True, exist_ok=True)
    print(LICENSE_NOTE)
    print(f"Descargando {BUFFALO_URL} …")
    data = urllib.request.urlopen(BUFFALO_URL).read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            if name.endswith("w600k_r50.onnx"):
                (dest / "w600k_r50.onnx").write_bytes(z.read(name))
    print(f"Listo: {dest / 'w600k_r50.onnx'}")
    return dest / "w600k_r50.onnx"


if __name__ == "__main__":
    if sys.argv[1:] == ["download"]:
        download()
    else:
        print(__doc__)
