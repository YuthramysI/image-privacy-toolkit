"""Calibración del hash perceptual del detector de reutilización, sobre
transformaciones REALES (recompresión y reescalado JPEG) de imágenes de prueba.

Reimplementa el MISMO pHash/dHash que src/lib/reuse.ts y lo verifica contra un
valor de referencia fijado desde el TS (para que no diverjan). Luego mide la
distancia de Hamming tras cada transformación y documenta qué detecta y qué no.

  services/engine/.venv/bin/python apps/web/tests/reuse_perceptual.test.py

Necesita Pillow y numpy (el venv del motor los trae).
"""
import math
import sys
from pathlib import Path

try:
    import numpy as np
    from PIL import Image
except ImportError as exc:
    print(f"SKIP: falta una dependencia ({exc.name}). Usa el venv del motor: "
          "services/engine/.venv/bin/python " + __file__)
    sys.exit(0)

# Valores fijados desde la implementación TS (node --experimental-strip-types).
PHASH_RAMP = "aa6eaae98254aaf4"
DHASH_RAMP = "0808101121424284"
PHASH_HIGH, PHASH_POSSIBLE, DHASH_HIGH = 10, 18, 12  # deben coincidir con reuse.ts


def bits_to_hex(bits):
    v = 0
    for b in bits:
        v = (v << 1) | (1 if b else 0)
    return format(v, "016x")


def hamming(a, b):
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def dct1d(vec):
    N = len(vec)
    out = np.zeros(N)
    for k in range(N):
        out[k] = sum(vec[n] * math.cos((math.pi / N) * (n + 0.5) * k) for n in range(N))
    return out


def phash_from_gray32(gray):  # gray: lista row-major de 1024
    N = 32
    m = np.array(gray, dtype=float).reshape(N, N)
    rows = np.array([dct1d(m[y]) for y in range(N)])
    cols = [dct1d(rows[:, x]) for x in range(N)]  # cols[u][v] = dct1d(rows[:,u])[v], igual que el TS
    low = [cols[u][v] for u in range(8) for v in range(8)]
    s = sorted(low)
    median = (s[31] + s[32]) / 2
    return bits_to_hex([1 if c > median else 0 for c in low])


def dhash_from_gray9x8(gray):  # gray: lista row-major de 72 (ancho 9, alto 8)
    W = 9
    bits = [1 if gray[y * W + x] > gray[y * W + x + 1] else 0 for y in range(8) for x in range(8)]
    return bits_to_hex(bits)


def phash_img(img):
    g = np.asarray(img.convert("L").resize((32, 32), Image.BILINEAR), dtype=float).flatten().tolist()
    return phash_from_gray32(g)


def dhash_img(img):
    g = np.asarray(img.convert("L").resize((9, 8), Image.BILINEAR), dtype=float).flatten().tolist()
    return dhash_from_gray9x8(g)


def jpeg(img, q):
    import io
    b = io.BytesIO()
    img.convert("RGB").save(b, "JPEG", quality=q)
    return Image.open(io.BytesIO(b.getvalue()))


def main():
    # 1) Comprobación cruzada con el TS sobre una matriz determinista.
    g32 = [(x * 53 + y * 31) % 256 for y in range(32) for x in range(32)]
    g98 = [(x * 53 + y * 31) % 256 for y in range(8) for x in range(9)]
    assert phash_from_gray32(g32) == PHASH_RAMP, f"pHash diverge del TS: {phash_from_gray32(g32)} != {PHASH_RAMP}"
    assert dhash_from_gray9x8(g98) == DHASH_RAMP, f"dHash diverge del TS: {dhash_from_gray9x8(g98)} != {DHASH_RAMP}"
    print("OK: la reimplementación coincide bit a bit con el TS.")

    faces = sorted((Path(__file__).resolve().parents[3] / "services/engine/samples/faces").glob("*.jpg"))
    if len(faces) < 3:
        print("SKIP: no hay suficientes imágenes de prueba en samples/faces.")
        return

    imgs = [Image.open(f).convert("RGB") for f in faces[:6]]
    base_p = [phash_img(im) for im in imgs]
    base_d = [dhash_img(im) for im in imgs]

    def dist_after(transform):
        ds = []
        for im, bp in zip(imgs, base_p):
            ds.append(hamming(bp, phash_img(transform(im))))
        return ds

    # 2) Transformaciones: media y máximo de la distancia pHash sobre las imágenes.
    cases = {
        "JPEG q90": lambda im: jpeg(im, 90),
        "JPEG q60": lambda im: jpeg(im, 60),
        "JPEG q40": lambda im: jpeg(im, 40),
        "reescala 50%": lambda im: im.resize((im.width // 2, im.height // 2), Image.LANCZOS),
        "reescala 150%": lambda im: im.resize((int(im.width * 1.5), int(im.height * 1.5)), Image.LANCZOS),
        "recorte 5%": lambda im: im.crop((int(im.width * 0.05), int(im.height * 0.05), int(im.width * 0.95), int(im.height * 0.95))),
        "recorte 20%": lambda im: im.crop((int(im.width * 0.2), int(im.height * 0.2), int(im.width * 0.8), int(im.height * 0.8))),
        "rotación 3°": lambda im: im.rotate(3, expand=True, fillcolor=(127, 127, 127)),
    }
    print(f"\nCalibración sobre {len(imgs)} retratos (distancia pHash /64, menor = más parecido):")
    print(f"{'transformación':<16} {'media':>6} {'máx':>5}   detectado (≤ posible={PHASH_POSSIBLE})")
    results = {}
    for name, fn in cases.items():
        ds = dist_after(fn)
        results[name] = (sum(ds) / len(ds), max(ds))
        det = "sí" if max(ds) <= PHASH_POSSIBLE else ("parcial" if min(ds) <= PHASH_POSSIBLE else "NO")
        print(f"{name:<16} {results[name][0]:>6.1f} {results[name][1]:>5}   {det}")

    # 3) Falsos positivos: distancia entre imágenes DISTINTAS.
    cross = [hamming(base_p[i], base_p[j]) for i in range(len(imgs)) for j in range(i + 1, len(imgs))]
    print(f"\nEntre imágenes distintas: distancia pHash mín {min(cross)}, media {sum(cross)/len(cross):.1f} (debe ser alta)")

    # --- Aserciones honestas: lo que el método SÍ detecta ---
    assert results["JPEG q60"][1] <= PHASH_HIGH, "la recompresión JPEG debería mantener distancia pequeña"
    assert results["JPEG q40"][1] <= PHASH_POSSIBLE, "JPEG q40 debería seguir siendo detectable"
    assert results["reescala 50%"][1] <= PHASH_POSSIBLE, "el reescalado debería ser detectable"
    assert results["reescala 150%"][1] <= PHASH_POSSIBLE, "el reescalado debería ser detectable"
    assert min(cross) > PHASH_POSSIBLE, "imágenes distintas NO deberían coincidir (sin falsos positivos)"
    # --- Limitación documentada: recorte fuerte y rotación NO se detectan ---
    assert results["recorte 20%"][1] > PHASH_POSSIBLE, "se esperaba que el recorte fuerte NO se detectara (limitación)"

    print("\nRESULTADO: OK — recompresión y reescalado se detectan; recortes fuertes y "
          "rotaciones NO (limitación documentada); sin falsos positivos entre distintas.")


if __name__ == "__main__":
    main()
