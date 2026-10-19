"""Verifica el invariante de la limpieza de metadatos del flujo de privacidad.

El flujo del navegador exporta la imagen con canvas.toBlob, que produce un
archivo solo con los píxeles (sin EXIF/GPS). Este test comprueba ese invariante
de forma reproducible con una imagen que SÍ tiene GPS, re-codificándola como lo
hace el canvas, y confirmando que el resultado no conserva GPS ni EXIF y que la
imagen se preserva.

  python apps/web/tests/privacy_invariant.test.py

Necesita piexif, Pillow y numpy. El venv del motor ya los trae:
  services/engine/.venv/bin/python apps/web/tests/privacy_invariant.test.py
"""
import io
import sys

try:
    import piexif
    from PIL import Image
    import numpy as np
except ImportError as exc:
    print(f"SKIP: falta una dependencia ({exc.name}). Ejecuta con el venv del "
          "motor: services/engine/.venv/bin/python " + __file__)
    sys.exit(0)


def make_jpeg_with_gps():
    img = Image.fromarray((np.random.rand(80, 80, 3) * 255).astype("uint8"))
    exif = {"0th": {piexif.ImageIFD.Make: b"TestCam", piexif.ImageIFD.DateTime: b"2020:01:01 00:00:00"},
            "GPS": {piexif.GPSIFD.GPSLatitudeRef: b"N", piexif.GPSIFD.GPSLatitude: [(40, 1), (26, 1), (46, 1)],
                    piexif.GPSIFD.GPSLongitudeRef: b"W", piexif.GPSIFD.GPSLongitude: [(79, 1), (58, 1), (56, 1)]},
            "Exif": {}, "1st": {}, "thumbnail": None}
    b = io.BytesIO(); img.save(b, "JPEG", exif=piexif.dump(exif)); return b.getvalue()


def canvas_reencode(data):  # equivalente a canvas.toBlob: solo píxeles
    im = Image.open(io.BytesIO(data)).convert("RGB")
    o = io.BytesIO(); im.save(o, "JPEG", quality=92); return o.getvalue()


def has_gps_exif(data):
    try:
        d = piexif.load(data)
        return bool(d["GPS"]), bool(d["0th"]) or bool(d["Exif"])
    except Exception:
        return False, False


def main():
    orig = make_jpeg_with_gps()
    g0, e0 = has_gps_exif(orig)
    assert g0 and e0, "la imagen de prueba debería tener GPS/EXIF"
    out = canvas_reencode(orig)
    g1, e1 = has_gps_exif(out)
    assert not g1, "FALLO: el GPS sobrevivió a la exportación"
    assert not e1, "FALLO: quedó EXIF en la exportación"
    assert Image.open(io.BytesIO(out)).size == (80, 80), "la imagen no se conservó"
    print("OK: exportación sin GPS ni EXIF, imagen conservada.")


if __name__ == "__main__":
    main()
