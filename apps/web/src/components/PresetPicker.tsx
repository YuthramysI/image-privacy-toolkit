"use client";

import type { Preset, PresetName } from "@/lib/engine";

const COPY: Record<PresetName, { title: string; body: string; level: number; tag: string }> = {
  suave: { title: "Suave", body: "Invisible. La más rápida.", level: 1, tag: "invisible" },
  media: { title: "Media", body: "Invisible. El equilibrio recomendado.", level: 2, tag: "recomendada" },
  fuerte: { title: "Fuerte", body: "Más protección. Textura fina visible con zoom.", level: 3, tag: "máxima en CPU" },
  maxima: { title: "Máxima", body: "Ataca los modelos completos. Requiere GPU.", level: 4, tag: "GPU" },
};

type Props = {
  presets: Preset[];
  value: PresetName;
  onChange: (p: PresetName) => void;
  disabled?: boolean;
};

export function PresetPicker({ presets, value, onChange, disabled }: Props) {
  return (
    <fieldset className="space-y-3" disabled={disabled}>
      <legend className="mb-4 font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint">Intensidad</legend>
      {presets.map((p) => {
        const active = p.name === value;
        const copy = COPY[p.name];
        return (
          <label
            key={p.name}
            className={`group flex cursor-pointer items-center gap-4 rounded-2xl border p-4 transition-colors ${
              active ? "border-acid bg-acid-soft" : "border-line bg-surface hover:border-line-strong"
            } ${disabled ? "cursor-not-allowed opacity-60" : ""}`}
          >
            <input type="radio" name="preset" value={p.name} checked={active} onChange={() => onChange(p.name)} className="sr-only" />
            <span className="flex h-8 items-end gap-1" aria-hidden>
              {[1, 2, 3, 4].map((i) => (
                <span
                  key={i}
                  className={`w-1.5 rounded-sm ${i <= copy.level ? (active ? "bg-acid" : "bg-ink-soft") : "bg-line-strong"}`}
                  style={{ height: `${8 + i * 6}px` }}
                />
              ))}
            </span>
            <span className="min-w-0 flex-1">
              <span className="flex flex-wrap items-center gap-2">
                <span className="font-semibold">{copy.title}</span>
                <span
                  className={`rounded-full px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${
                    active ? "bg-acid text-acid-ink" : "bg-surface-2 text-ink-faint"
                  }`}
                >
                  {copy.tag}
                </span>
              </span>
              <span className="mt-0.5 block text-sm text-ink-soft">{copy.body}</span>
            </span>
            <span className="font-mono text-xs text-ink-faint">±{p.eps}</span>
          </label>
        );
      })}
    </fieldset>
  );
}
