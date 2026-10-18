"""Resume los informes de engine.eval.run en una tabla Markdown.

  python -m engine.eval.summary reports/media/report.json reports/fuerte/report.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from ..protect.pipeline import PRESETS

SCENARIO = "red social (1080px, JPEG 75)"


def summarize(path: Path) -> dict[str, float]:
    data = json.loads(path.read_text())
    vis = [r["visibilidad"] for r in data.values()]
    out = {
        "psnr": np.mean([v["psnr"] for v in vis]),
        "lpips": np.mean([v["lpips"] for v in vis]),
        # Tiempo de protección por imagen, sin contar la evaluación.
        "segundos": np.mean([r["s_por_paso"] * PRESETS[path.parent.name].steps for r in data.values()]),
    }
    faces = [r["escenarios"][SCENARIO]["rostro_similitud"] for r in data.values() if r["rostros"]]
    for model in ("vggface2 (atacado)", "casia (no visto)"):
        vals = [(f["limpia"][model], f["protegida"][model]) for f in faces if model in f["protegida"]]
        if vals:
            out[f"rostro {model}"] = tuple(np.mean(vals, axis=0))
    for name in ("sd", "flux", "sdxl"):
        drops = [
            r["escenarios"][SCENARIO]["vae_psnr"]["limpia"][name] - r["escenarios"][SCENARIO]["vae_psnr"]["protegida"][name]
            for r in data.values()
        ]
        out[f"vae {name}"] = float(np.mean(drops))
    return out


def main() -> None:
    rows = {Path(p).parent.name: summarize(Path(p)) for p in sys.argv[1:]}
    print(f"Escenario: {SCENARIO}\n")
    print("| Preset | PSNR imagen | LPIPS | Identidad (modelo atacado) | Identidad (modelo no visto) | Caída VAE SD | Caída VAE FLUX | Caída VAE SDXL (no visto) | Tiempo de protección (CPU) |")
    print("|---|---|---|---|---|---|---|---|---|")
    for name, r in rows.items():

        def face(key):
            v = r.get(f"rostro {key}")
            return f"{v[0]:.2f} → {v[1]:.2f}" if v else "—"

        print(
            f"| {name} | {r['psnr']:.1f} dB | {r['lpips']:.4f} | {face('vggface2 (atacado)')} | {face('casia (no visto)')} "
            f"| −{r['vae sd']:.1f} dB | −{r['vae flux']:.1f} dB | −{r['vae sdxl']:.1f} dB | {r['segundos']:.0f} s |"
        )


if __name__ == "__main__":
    main()
