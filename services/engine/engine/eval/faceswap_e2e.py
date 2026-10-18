"""Evaluación de EXTREMO A EXTREMO de la protección anti-face-swap.

A diferencia de faceswap.py (que mide el embedding del reconocedor, un proxy),
aquí se EJECUTA un face-swap real (inswapper, el generador de roop/FaceFusion) y
se mide si la cara resultante realmente se parece a la persona fuente.

Escenario:
  fuente A (original o protegida) -> inyectar su identidad en el rostro destino B
  -> cara swapped. Si la protección funciona, el swap hecho con la fuente
  PROTEGIDA NO se parece a A (identidad baja), medido con un reconocedor que el
  ataque NO usó (glintr100 / FaceNet-casia).

Uso DEFENSIVO (medir una protección), con imágenes de dominio público. inswapper
tiene licencia de investigación no comercial; se descarga aparte y no se
distribuye. Requiere ~/.cache/velo-eval/faceswap/inswapper_128_fp16.onnx.

  python -m engine.eval.faceswap_e2e
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
from onnx import numpy_helper
from PIL import Image
from skimage.transform import SimilarityTransform, warp

from .faceswap import ARCFACE_DST, SCRFD, ArcFace, HELDOUT, _session

INSWAPPER = Path(os.environ.get("VELO_INSWAPPER", Path.home() / ".cache/velo-eval/faceswap/inswapper_128_fp16.onnx"))
DST_128 = ARCFACE_DST * (128.0 / 112.0)  # plantilla de alineación escalada a 128


class InSwapper:
    def __init__(self, path: Path):
        model = onnx.load(str(path))
        # emap: matriz de proyección del embedding (initializer del grafo).
        cand = [numpy_helper.to_array(t) for t in model.graph.initializer if numpy_helper.to_array(t).ndim == 2 and numpy_helper.to_array(t).shape == (512, 512)]
        self.emap = cand[0].astype("float32")
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        self.sess = ort.InferenceSession(str(path), opts, providers=["CPUExecutionProvider"])
        self.inputs = [i.name for i in self.sess.get_inputs()]

    def _align(self, img: np.ndarray, kps: np.ndarray):
        t = SimilarityTransform()
        t.estimate(kps.astype(np.float32), DST_128)
        aligned = warp(img, t.inverse, output_shape=(128, 128), order=1, mode="constant")
        return aligned.astype(np.float32), t

    def swap(self, target_img: Image.Image, target_kps: np.ndarray, source_emb: np.ndarray) -> Image.Image:
        """Inyecta la identidad `source_emb` (embedding ArcFace normado) en el
        rostro de `target_img`. Devuelve la cara swapped 128x128."""
        rgb = np.asarray(target_img.convert("RGB"), np.float32) / 255.0
        aligned, _ = self._align(rgb, target_kps)
        blob = aligned.transpose(2, 0, 1)[None]  # NCHW, RGB, [0,1]
        latent = source_emb.reshape(1, -1) @ self.emap
        latent = latent / np.linalg.norm(latent)
        feed = {self.inputs[0]: blob.astype(np.float32), self.inputs[1]: latent.astype(np.float32)}
        out = self.sess.run(None, feed)[0][0]  # (3,128,128) en [0,1]
        arr = (np.clip(out.transpose(1, 2, 0), 0, 1) * 255).astype(np.uint8)
        return Image.fromarray(arr)


def _normed(arc: ArcFace, img: Image.Image, kps: np.ndarray) -> np.ndarray:
    e = arc.embed(img, kps)
    return e / np.linalg.norm(e)


def _normed_aligned(arc: ArcFace, aligned128: Image.Image) -> np.ndarray:
    """Embedding de una cara YA alineada a la plantilla de 128 (la salida del
    swap): se usan los puntos de la plantilla como referencia, sin re-detectar."""
    e = arc.embed(aligned128, DST_128.astype(np.float32))
    return e / np.linalg.norm(e)


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--faces", type=Path, default=Path("samples/faces"))
    ap.add_argument("--protected", type=Path, default=Path("reports/faceswap-arcface"))
    ap.add_argument("--suffix", default="-media.png")
    args = ap.parse_args()

    if not INSWAPPER.exists():
        print(f"FALTA el modelo de face-swap: {INSWAPPER}\nNo se puede validar de extremo a extremo. Descárgalo aparte.")
        return

    det = SCRFD()
    arc_sw = ArcFace()  # w600k: el que usa inswapper internamente (ATACADO)
    judge = ArcFace(HELDOUT) if HELDOUT.exists() else arc_sw  # glintr100: reconocedor NO visto
    swapper = InSwapper(INSWAPPER)

    sources = sorted(p for p in args.faces.glob("*.jpg"))
    # Pares (fuente A, destino B): identidad de A inyectada en la cara de B.
    pairs = [(sources[i], sources[(i + 1) % len(sources)]) for i in range(len(sources))]

    print(f"{'A→B':20s} {'orig: id(swap,A)':>17s} {'prot: id(swap,A)':>17s} {'veredicto':>24s}")
    rows = []
    for a_path, b_path in pairs:
        prot_path = args.protected / f"{a_path.stem}{args.suffix}"
        if not prot_path.exists():
            continue
        A = Image.open(a_path).convert("RGB")
        Aprot = Image.open(prot_path).convert("RGB")
        B = Image.open(b_path).convert("RGB")
        fa, fb = det.detect(A), det.detect(B)
        if fa is None or fb is None:
            continue
        ref_A = _normed(judge, A, fa[1])  # identidad real de A (juez no visto)

        def swap_and_judge(src_img):
            fs = det.detect(src_img)
            if fs is None:
                return None
            emb = _normed(arc_sw, src_img, fs[1])  # embedding que ve inswapper
            swapped = swapper.swap(B, fb[1], emb)  # cara ya alineada a 128
            e = _normed_aligned(judge, swapped)
            return float(np.dot(ref_A, e))

        id_orig = swap_and_judge(A)
        id_prot = swap_and_judge(Aprot)
        if id_orig is None or id_prot is None:
            continue
        rows.append((id_orig, id_prot))
        # protección "funciona" en este par si el swap original SÍ se parece a A
        # (>0.35) pero el protegido NO (<0.35).
        verdict = "protege" if (id_orig > 0.35 and id_prot < 0.35) else ("sin efecto" if id_prot >= 0.35 else "ambos bajos")
        print(f"{a_path.stem+'→'+b_path.stem:20s} {id_orig:17.2f} {id_prot:17.2f} {verdict:>24s}")

    if rows:
        o = np.mean([r[0] for r in rows])
        p = np.mean([r[1] for r in rows])
        works = sum(1 for a, b in rows if a > 0.35 and b < 0.35)
        print(f"\nMedia identidad(swap, A) con reconocedor NO visto: original {o:.2f} · protegida {p:.2f}")
        print(f"Face-swap neutralizado (swap original reconocible, protegido no): {works}/{len(rows)}")
        print("Mide el RESULTADO del face-swap real, no el embedding. Solo retratos de estudio; no extrapolar.")


if __name__ == "__main__":
    main()
