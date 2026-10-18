"""Sello de "no uso": deja constancia verificable de que la imagen no se cede
para IA, por dos vías que se complementan.

1. Content Credentials (C2PA): una declaración firmada, dentro de la foto, que
   dice que no se permite entrenar modelos, generar contenido derivado ni minar
   datos. Es el estándar que leen Adobe, Google y otros. Se pierde si una red
   social borra los metadatos.
2. Marca de agua invisible (TrustMark, Adobe, MIT): un identificador de 61 bits
   que sobrevive a recompresión y capturas de pantalla, para reconocer la foto
   como protegida aunque se hayan borrado los metadatos.

Ninguna de las dos impide técnicamente el uso: dejan prueba de que no hubo
consentimiento, lo que tiene valor legal y para pedir retiradas.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from PIL import Image

# Declaración de no uso, alineada con las propiedades del estándar.
ASSERTIONS = [
    {
        "label": "c2pa.training-mining",
        "data": {
            "entries": {
                "c2pa.ai_generative_training": {"use": "notAllowed"},
                "c2pa.ai_training": {"use": "notAllowed"},
                "c2pa.ai_inference": {"use": "notAllowed"},
                "c2pa.data_mining": {"use": "notAllowed"},
            }
        },
    },
]
CLAIM_GENERATOR = "velo/0.1"
NO_USE_NOTICE = (
    "Esta imagen no autoriza su uso para entrenar o ajustar modelos de IA, "
    "generar contenido derivado ni minería de datos."
)


@dataclass
class SealConfig:
    certs_dir: Path
    owner: str | None = None
    watermark: bool = True
    # Prefijo + 32 bits de identificador para la marca de agua.
    watermark_id: str | None = None


def _manifest(cfg: SealConfig) -> str:
    # La primera acción debe declarar el origen de la imagen.
    assertions = [
        {
            "label": "c2pa.actions",
            "data": {"actions": [{"action": "c2pa.created", "digitalSourceType": "http://cv.iptc.org/newscodes/digitalsourcetype/digitalCapture"}]},
        },
        *ASSERTIONS,
    ]
    author = [{"@type": "Person", "name": cfg.owner}] if cfg.owner else []
    assertions.append(
        {
            "label": "stds.schema-org.CreativeWork",
            "data": {"@context": "https://schema.org", "@type": "CreativeWork", "author": author, "usageInfo": NO_USE_NOTICE},
        }
    )
    return json.dumps(
        {
            "claim_generator": CLAIM_GENERATOR,
            "claim_generator_info": [{"name": "Image Privacy Toolkit", "version": "0.1.0"}],
            "title": "Imagen protegida con Image Privacy Toolkit",
            "assertions": assertions,
            "metadata": [{"dateTime": datetime.now(timezone.utc).isoformat()}],
        }
    )


def ensure_certs(certs_dir: Path) -> tuple[Path, Path]:
    """Devuelve el certificado y la clave para firmar las credenciales.

    Por defecto usa el par de DESARROLLO de C2PA (`es256_certs.pem` /
    `es256_private.key`): sirve para probar y verificar la firma en local, pero
    su cadena no es de confianza pública, así que un validador la marcará como
    "firmante no reconocido".

    Para un despliegue real hay que colocar en `certs_dir` un certificado de una
    autoridad del programa de Content Credentials (o uno propio añadido a la
    lista de confianza), con el mismo nombre de archivo."""
    cert_path, key_path = certs_dir / "es256_certs.pem", certs_dir / "es256_private.key"
    if not (cert_path.exists() and key_path.exists()):
        raise FileNotFoundError(
            f"Faltan los certificados de firma en {certs_dir}. "
            "Coloca es256_certs.pem y es256_private.key (de C2PA para desarrollo, "
            "o los tuyos de producción)."
        )
    return cert_path, key_path


@lru_cache(maxsize=1)
def _watermarker():
    from trustmark import TrustMark

    return TrustMark(verbose=False, model_type="Q", encoding_type=TrustMark.Encoding.BCH_5)


def apply_watermark(img: Image.Image, secret: str) -> Image.Image:
    # 61 bits de capacidad; se usa un identificador corto.
    return _watermarker().encode(img.convert("RGB"), secret[:7], MODE="text")


def read_watermark(img: Image.Image) -> str | None:
    secret, present, _ = _watermarker().decode(img.convert("RGB"), MODE="text")
    return secret if present else None


def seal(img: Image.Image, fmt: str, cfg: SealConfig, quality: int = 95) -> bytes:
    """Devuelve la imagen con la marca de agua y las Content Credentials."""
    import c2pa

    if cfg.watermark:
        img = apply_watermark(img, cfg.watermark_id or "VELO")

    raw = io.BytesIO()
    if fmt == "jpeg":
        img.save(raw, "JPEG", quality=quality, subsampling=0)
        mime = "image/jpeg"
    else:
        img.save(raw, "PNG")
        mime = "image/png"
    raw.seek(0)

    cert_path, key_path = ensure_certs(cfg.certs_dir)
    signer = c2pa.Signer.from_info(
        c2pa.C2paSignerInfo(
            alg=c2pa.C2paSigningAlg.ES256,
            sign_cert=cert_path.read_bytes(),
            private_key=key_path.read_bytes(),
            ta_url="http://timestamp.digicert.com".encode(),
        )
    )
    builder = c2pa.Builder.from_json(_manifest(cfg))
    dest = io.BytesIO()
    builder.sign(signer, mime, raw, dest)
    return dest.getvalue()


def verify(data: bytes) -> dict:
    """Lee las Content Credentials y la marca de agua de una imagen."""
    import c2pa

    out: dict = {"content_credentials": None, "watermark": None}
    try:
        with c2pa.Reader(io.BytesIO(data)) as reader:
            out["content_credentials"] = json.loads(reader.json())
    except Exception as exc:  # noqa: BLE001 — se informa, no se interrumpe
        out["content_credentials_error"] = str(exc)
    try:
        out["watermark"] = read_watermark(Image.open(io.BytesIO(data)))
    except Exception as exc:  # noqa: BLE001
        out["watermark_error"] = str(exc)
    return out


def _cli() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Lee el sello de no uso de una imagen.")
    ap.add_argument("image", type=Path)
    args = ap.parse_args()
    v = verify(args.image.read_bytes())
    cc = v.get("content_credentials")
    reserved = isinstance(cc, dict) and any(
        "training-mining" in a.get("label", "") for m in cc.get("manifests", {}).values() for a in m.get("assertions", [])
    )
    print(f"Marca de agua: {v.get('watermark') or 'no encontrada'}")
    print(f"Declaración de no uso (Content Credentials): {'sí' if reserved else 'no'}")
    print(f"→ {'Imagen protegida con Image Privacy Toolkit' if (v.get('watermark') or reserved) else 'Sin sello de Image Privacy Toolkit detectado'}")


if __name__ == "__main__":
    _cli()
