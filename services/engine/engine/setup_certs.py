"""Descarga los certificados de DESARROLLO de C2PA para firmar el sello.

Sirven para probar y verificar en local; NO son de confianza pública. Para un
despliegue real hay que reemplazarlos por un certificado de una autoridad del
programa de Content Credentials, con el mismo nombre de archivo.

  python -m engine.setup_certs
"""

from __future__ import annotations

import os
import urllib.request
from pathlib import Path

BASE = "https://raw.githubusercontent.com/contentauth/c2pa-python/main/tests/fixtures/"
FILES = ("es256_certs.pem", "es256_private.key")


def main() -> None:
    dest = Path(os.environ.get("VELO_CERTS", Path.home() / ".cache/velo/certs"))
    dest.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        (dest / name).write_bytes(urllib.request.urlopen(BASE + name).read())
        print(f"  {dest / name}")
    print("Certificados de desarrollo listos. Reemplázalos por los de producción antes de publicar.")


if __name__ == "__main__":
    main()
