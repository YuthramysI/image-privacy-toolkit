"use client";

import { useEffect, useRef, useState } from "react";

type Props = {
  original: string;
  protectedUrl: string;
};

const AMPLIFY = 10;
const MAX_DIFF_SIDE = 1600;

async function load(src: string): Promise<HTMLImageElement> {
  const img = new Image();
  img.src = src;
  await img.decode();
  return img;
}

/** Pinta |protegida − original| × AMPLIFY para hacer visible la perturbación. */
function useDiff(original: string, protectedUrl: string, enabled: boolean) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!enabled || url) return;
    let cancelled = false;
    (async () => {
      const [a, b] = await Promise.all([load(original), load(protectedUrl)]);
      const scale = Math.min(1, MAX_DIFF_SIDE / Math.max(b.naturalWidth, b.naturalHeight));
      const w = Math.round(b.naturalWidth * scale);
      const h = Math.round(b.naturalHeight * scale);
      const canvas = document.createElement("canvas");
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
      ctx.drawImage(a, 0, 0, w, h);
      const pa = ctx.getImageData(0, 0, w, h);
      ctx.drawImage(b, 0, 0, w, h);
      const pb = ctx.getImageData(0, 0, w, h);
      for (let i = 0; i < pa.data.length; i += 4) {
        for (let c = 0; c < 3; c++) pb.data[i + c] = Math.min(255, Math.abs(pb.data[i + c] - pa.data[i + c]) * AMPLIFY);
        pb.data[i + 3] = 255;
      }
      ctx.putImageData(pb, 0, 0);
      const blob = await new Promise<Blob | null>((r) => canvas.toBlob(r));
      if (!cancelled && blob) setUrl(URL.createObjectURL(blob));
    })();
    return () => {
      cancelled = true;
    };
  }, [original, protectedUrl, enabled, url]);
  useEffect(() => () => void (url && URL.revokeObjectURL(url)), [url]);
  return url;
}

export function Compare({ original, protectedUrl }: Props) {
  const [mode, setMode] = useState<"slider" | "diff">("slider");
  const [pos, setPos] = useState(50);
  const frame = useRef<HTMLDivElement>(null);
  const diff = useDiff(original, protectedUrl, mode === "diff");

  function moveTo(clientX: number) {
    const rect = frame.current?.getBoundingClientRect();
    if (!rect) return;
    setPos(Math.max(0, Math.min(100, ((clientX - rect.left) / rect.width) * 100)));
  }

  return (
    <div className="space-y-3">
      <div role="tablist" className="inline-flex rounded-full border border-line-strong bg-surface p-1 font-mono text-[11px] uppercase tracking-[0.14em]">
        {(
          [
            ["slider", "Antes / después"],
            ["diff", `Diferencia ×${AMPLIFY}`],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            role="tab"
            aria-selected={mode === key}
            onClick={() => setMode(key)}
            className={`rounded-full px-4 py-2 transition-colors ${mode === key ? "bg-acid text-acid-ink" : "text-ink-soft hover:text-ink"}`}
          >
            {label}
          </button>
        ))}
      </div>

      {mode === "slider" ? (
        <div
          ref={frame}
          className="relative cursor-ew-resize touch-none select-none overflow-hidden rounded-3xl border border-line-strong bg-black"
          onPointerDown={(e) => {
            e.currentTarget.setPointerCapture(e.pointerId);
            moveTo(e.clientX);
          }}
          onPointerMove={(e) => e.buttons && moveTo(e.clientX)}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={protectedUrl} alt="Foto protegida" className="block w-full" draggable={false} />
          <div className="absolute inset-0" style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={original} alt="Foto original" className="block w-full" draggable={false} />
          </div>
          <div className="pointer-events-none absolute inset-y-0 w-[3px] -translate-x-1/2 bg-acid shadow-[0_0_24px_4px_rgb(212_255_58/0.5)]" style={{ left: `${pos}%` }}>
            <span className="absolute top-1/2 left-1/2 grid h-10 w-10 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border border-acid bg-black/80 font-mono text-xs text-acid">
              ⇆
            </span>
          </div>
          <span className="pointer-events-none absolute left-4 top-4 rounded bg-black/70 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.18em] text-ink">Original</span>
          <span className="pointer-events-none absolute right-4 top-4 rounded bg-black/70 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.18em] text-acid">Protegida</span>
          <input
            type="range"
            min={0}
            max={100}
            value={pos}
            onChange={(e) => setPos(Number(e.target.value))}
            aria-label="Deslizar entre original y protegida"
            className="sr-only"
          />
        </div>
      ) : (
        <div className="overflow-hidden rounded-3xl border border-line-strong bg-black">
          {diff ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={diff} alt="Perturbación amplificada" className="block w-full" />
          ) : (
            <div className="grid aspect-video place-items-center font-mono text-xs uppercase tracking-[0.18em] text-ink-faint">Calculando…</div>
          )}
        </div>
      )}
      {mode === "diff" && (
        <p className="text-sm text-ink-soft">
          Esto es lo que se añadió, amplificado {AMPLIFY} veces. A tamaño real, cada píxel cambia como máximo unos pocos niveles de 255.
        </p>
      )}
    </div>
  );
}
