"""Capa legal: declara en los metadatos que la imagen no puede usarse para
minería de datos ni entrenamiento de modelos (IPTC PLUS "Data Mining").

No impide técnicamente nada, pero deja constancia de la reserva de derechos.
Algunas redes sociales borran los metadatos al subir la foto.
"""

from __future__ import annotations

import io
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image
from PIL.PngImagePlugin import PngInfo

DMI_PROHIBITED_AIML = "http://ns.useplus.org/ldf/vocab/DMI-PROHIBITED-AIMLTRAINING"
NOTICE = (
    "Prohibido el uso de esta imagen para minería de datos, entrenamiento, "
    "ajuste fino o generación con modelos de inteligencia artificial."
)


def xmp_packet(owner: str | None = None, notice: str = NOTICE) -> bytes:
    rights = f"<dc:rights><rdf:Alt><rdf:li xml:lang=\"x-default\">{escape(owner)}</rdf:li></rdf:Alt></dc:rights>" if owner else ""
    xml = f"""<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:plus="http://ns.useplus.org/ldf/xmp/1.0/"
    xmlns:xmpRights="http://ns.adobe.com/xap/1.0/rights/"
    xmlns:dc="http://purl.org/dc/elements/1.1/">
   <plus:DataMining>{DMI_PROHIBITED_AIML}</plus:DataMining>
   <plus:OtherConstraints><rdf:Alt><rdf:li xml:lang="x-default">{escape(notice)}</rdf:li></rdf:Alt></plus:OtherConstraints>
   <xmpRights:Marked>True</xmpRights:Marked>
   <xmpRights:UsageTerms><rdf:Alt><rdf:li xml:lang="x-default">{escape(notice)}</rdf:li></rdf:Alt></xmpRights:UsageTerms>
   {rights}
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""
    return xml.encode("utf-8")


def encode(img: Image.Image, fmt: str, owner: str | None = None, quality: int = 95) -> bytes:
    """Serializa la imagen protegida con los metadatos de reserva incluidos.
    Se descarta el EXIF original (GPS, modelo de cámara...) por privacidad."""
    xmp = xmp_packet(owner)
    buf = io.BytesIO()
    if fmt == "png":
        info = PngInfo()
        info.add_itxt("XML:com.adobe.xmp", xmp.decode("utf-8"))
        img.save(buf, "PNG", pnginfo=info, optimize=True)
    elif fmt == "jpeg":
        img.save(buf, "JPEG", quality=quality, subsampling=0, xmp=xmp)
    else:
        raise ValueError(f"Formato no soportado: {fmt}")
    return buf.getvalue()


def has_reservation(data: bytes) -> bool:
    """True si la imagen declara la reserva de "no entrenar", por cualquiera de
    las dos vías con que la escribe Image Privacy Toolkit: los metadatos XMP/IPTC (ruta de
    respaldo de `encode`) o la aserción C2PA del sello (ruta de `finalize` con
    certificados). Antes solo miraba el XMP y daba falso negativo con el sello."""
    # 1) Metadatos XMP/IPTC.
    try:
        img = Image.open(io.BytesIO(data))
        xmp = img.info.get("xmp") or img.info.get("XML:com.adobe.xmp") or b""
        if isinstance(xmp, str):
            xmp = xmp.encode("utf-8")
        if DMI_PROHIBITED_AIML.encode() in xmp:
            return True
    except Exception:  # noqa: BLE001 — ilegible como XMP; se intenta por C2PA
        pass
    # 2) Aserción C2PA del sello (c2pa.training-mining con use=notAllowed).
    try:
        import json

        import c2pa

        with c2pa.Reader(io.BytesIO(data)) as reader:
            cc = json.loads(reader.json())
        return any(
            "training-mining" in a.get("label", "")
            for m in cc.get("manifests", {}).values()
            for a in m.get("assertions", [])
        )
    except Exception:  # noqa: BLE001 — sin C2PA legible, no hay reserva detectable
        return False


def finalize(img: Image.Image, fmt: str, owner: str | None = None, watermark_id: str | None = None, quality: int = 95) -> bytes:
    """Serializa la imagen protegida con el sello de "no uso": Content
    Credentials firmadas + marca de agua invisible. Si el sellado no está
    disponible (faltan certificados o librerías), cae a los metadatos IPTC/XMP,
    para que proteger una foto nunca falle por el sello."""
    import os

    from . import seal

    certs = Path(os.environ.get("VELO_CERTS", Path.home() / ".cache/velo/certs"))
    try:
        cfg = seal.SealConfig(certs_dir=certs, owner=owner, watermark=True, watermark_id=watermark_id)
        return seal.seal(img, fmt, cfg, quality=quality)
    except Exception:  # noqa: BLE001 — sin sello, al menos los metadatos
        return encode(img, fmt, owner=owner, quality=quality)
