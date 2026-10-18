"""Módulo 1 — Registro de consentimiento y derechos.

Genera, para cada imagen, un certificado firmado y verificable que deja
constancia de que su titular NO autoriza el entrenamiento ni los usos
generativos. Contiene:

- el hash SHA-256 de la imagen original (identifica la foto sin guardarla);
- el hash SHA-256 de la imagen protegida (la que de verdad se publica);
- una declaración explícita de no autorización;
- titular, fecha y el identificador de la marca de agua invisible;
- una firma Ed25519 sobre todo lo anterior, que cualquiera puede verificar con
  la clave pública (incluida en el propio registro).

No depende de servicios externos: es una prueba autónoma, con fecha y firma, de
que no hubo consentimiento. Sirve ante una plataforma o en una reclamación.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

DECLARATION = (
    "El titular de los derechos de esta imagen NO autoriza su uso para entrenar, "
    "ajustar o evaluar modelos de inteligencia artificial, ni para generar "
    "contenido derivado, ni para minería de datos, ni para extraer de ella "
    "identidad, descripciones, etiquetas o representaciones. Esta reserva se "
    "ampara en la normativa de protección de datos personales y de propiedad "
    "intelectual aplicable."
)
SPEC = "velo-rights-record/1"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _keys_dir() -> Path:
    return Path(os.environ.get("VELO_REGISTRY_KEYS", Path.home() / ".cache/velo/registry"))


def ensure_signing_key():
    """Par Ed25519 propio del registro (independiente de los certificados C2PA).
    Se crea una vez; la clave privada permanece local."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519

    d = _keys_dir()
    d.mkdir(parents=True, exist_ok=True)
    key_path, pub_path = d / "registry_ed25519.key", d / "registry_ed25519.pub"
    if key_path.exists():
        key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    else:
        key = ed25519.Ed25519PrivateKey.generate()
        key_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
            )
        )
        pub_path.write_bytes(
            key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        )
    return key


def _public_pem(key) -> str:
    from cryptography.hazmat.primitives import serialization

    return key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()


def _canonical(payload: dict) -> bytes:
    # Serialización estable para que la firma sea reproducible.
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def create_record(
    original: bytes,
    protected: bytes,
    owner: str | None = None,
    watermark_id: str | None = None,
) -> dict:
    """Devuelve el certificado de derechos firmado para una imagen."""
    key = ensure_signing_key()
    payload = {
        "spec": SPEC,
        "declaration": DECLARATION,
        "owner": owner,
        "created": datetime.now(timezone.utc).isoformat(),
        "original_sha256": sha256(original),
        "protected_sha256": sha256(protected),
        "watermark_id": watermark_id,
    }
    signature = key.sign(_canonical(payload))
    return {
        **payload,
        "signature": {
            "alg": "Ed25519",
            "value": base64.b64encode(signature).decode(),
            "public_key": _public_pem(key),
        },
    }


def verify_record(record: dict, image: bytes | None = None) -> dict:
    """Comprueba la firma del registro y, si se pasa una imagen, si coincide con
    el hash del original o del protegido que declara el registro."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import serialization

    out = {"firma_valida": False, "coincide_imagen": None}
    sig = record.get("signature", {})
    payload = {k: v for k, v in record.items() if k != "signature"}
    try:
        pub = serialization.load_pem_public_key(sig["public_key"].encode())
        pub.verify(base64.b64decode(sig["value"]), _canonical(payload))
        out["firma_valida"] = True
    except (InvalidSignature, KeyError, ValueError):
        out["firma_valida"] = False
    if image is not None:
        h = sha256(image)
        if h == record.get("original_sha256"):
            out["coincide_imagen"] = "original"
        elif h == record.get("protected_sha256"):
            out["coincide_imagen"] = "protegida"
        else:
            out["coincide_imagen"] = "no coincide"
    return out


def _cli() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Registro de derechos de una imagen.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create", help="crea el registro firmado de una imagen")
    c.add_argument("image", type=Path)
    c.add_argument("--owner", default=None)
    c.add_argument("--out", type=Path, default=None)
    v = sub.add_parser("verify", help="verifica un registro .json")
    v.add_argument("record", type=Path)
    v.add_argument("--image", type=Path, default=None)
    args = ap.parse_args()

    if args.cmd == "create":
        data = args.image.read_bytes()
        rec = create_record(data, data, owner=args.owner)
        out = args.out or args.image.with_suffix(".rights.json")
        out.write_text(json.dumps(rec, indent=2, ensure_ascii=False))
        print(f"Registro firmado: {out}\n  SHA-256: {rec['original_sha256']}")
    else:
        rec = json.loads(args.record.read_text())
        img = args.image.read_bytes() if args.image else None
        print(json.dumps(verify_record(rec, img), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    _cli()
