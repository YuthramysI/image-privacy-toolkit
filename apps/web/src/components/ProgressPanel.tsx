"use client";

import type { JobState } from "@/lib/engine";

type Props = {
  preview: string;
  state: JobState | null;
  onCancel: () => void;
};

/** Tu foto bajo el escáner mientras se calcula la protección. */
export function ProgressPanel({ preview, state, onCancel }: Props) {
  const pct = state && state.total ? state.step / state.total : 0;
  const queued = !state || state.status === "queued";
  const faceSim = state?.losses.face_sim;
  const identity = faceSim === undefined ? null : Math.max(0, Math.round(faceSim * 100));

  return (
    <div className="rise grid gap-8 lg:grid-cols-[1.1fr_1fr] lg:items-center">
      <div className="relative overflow-hidden rounded-3xl border border-line-strong bg-black">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={preview} alt="Tu foto mientras se protege" className="block max-h-[560px] w-full object-contain" />
        {/* El velo verde se intensifica con el progreso (solo opacity). */}
        <div className="pointer-events-none absolute inset-0 bg-acid mix-blend-overlay transition-opacity duration-700" style={{ opacity: 0.08 + pct * 0.22 }} />
        <div className="grid-bg pointer-events-none absolute inset-0 transition-opacity duration-700" style={{ opacity: 0.4 + pct * 0.6 }} />
        <div className="pointer-events-none absolute inset-0 overflow-hidden">
          <div className="scan-sweep absolute inset-x-0 top-0 h-full">
            <div className="absolute inset-x-0 bottom-0 h-24 bg-gradient-to-b from-transparent to-acid/25" />
            <div className="absolute inset-x-0 bottom-0 h-0.5 bg-acid shadow-[0_0_20px_3px_rgb(212_255_58/0.6)]" />
          </div>
        </div>
        <div className="pointer-events-none absolute inset-x-0 top-0 flex justify-between p-4 font-mono text-[10px] uppercase tracking-[0.18em]">
          <span className="rounded bg-black/70 px-2 py-1 text-acid">
            <span className="blink">●</span> Escaneando
          </span>
          <span className="rounded bg-black/70 px-2 py-1 text-ink">{state?.preset ?? ""}</span>
        </div>
      </div>

      <div className="space-y-8">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint">
            {queued ? (state?.queue_position ? `En cola · ${state.queue_position} delante` : "Preparando modelos") : `Paso ${state.step} / ${state.total}`}
          </p>
          <p className="mt-2 font-mono text-7xl font-medium tracking-tight tabular-nums sm:text-8xl">
            {Math.round(pct * 100)}
            <span className="text-acid">%</span>
          </p>
          <div className="mt-4 h-1 overflow-hidden rounded-full bg-surface-2" role="progressbar" aria-valuenow={Math.round(pct * 100)} aria-valuemin={0} aria-valuemax={100}>
            <div className="h-full origin-left bg-acid transition-transform duration-500" style={{ transform: `scaleX(${pct})` }} />
          </div>
        </div>

        {identity !== null && (
          <div className="rounded-2xl border border-line bg-surface p-5">
            <div className="flex items-baseline justify-between">
              <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint">Parecido de identidad</span>
              <span className={`font-mono text-2xl tabular-nums ${identity < 40 ? "text-acid" : "text-ink"}`}>{identity}%</span>
            </div>
            <div className="relative mt-3 h-2 overflow-hidden rounded-full bg-surface-2">
              <div
                className={`h-full origin-left transition-transform duration-500 ${identity < 40 ? "bg-acid" : "bg-warn"}`}
                style={{ transform: `scaleX(${identity / 100})` }}
              />
              <span className="absolute inset-y-0 left-[40%] w-px bg-ink-soft" />
            </div>
            <p className="mt-3 text-sm text-ink-soft">Empieza cerca del 100%. Por debajo de la marca (~40%), un reconocedor facial suele dejar de reconocerte como la misma persona (según los modelos que probamos; no es garantía universal).</p>
          </div>
        )}

        <div className="flex items-center justify-between gap-4 border-t border-line pt-6">
          <p className="text-sm text-ink-soft">Sin tarjeta gráfica tarda unos 3 minutos. Puedes seguir mirando la página.</p>
          <button
            onClick={onCancel}
            className="shrink-0 rounded-full border border-line-strong px-4 py-2 text-sm text-ink-soft transition-colors hover:border-danger hover:text-danger"
          >
            Cancelar
          </button>
        </div>
      </div>
    </div>
  );
}
