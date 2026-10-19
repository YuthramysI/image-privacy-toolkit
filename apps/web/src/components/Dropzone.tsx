"use client";

import { useRef, useState } from "react";

const ACCEPT = ["image/jpeg", "image/png", "image/webp"];
const MAX_MB = 15;

type Props = {
  onFile: (file: File) => void;
  onError: (msg: string) => void;
  disabled?: boolean;
};

const CORNERS = [
  "left-4 top-4 border-l-2 border-t-2 group-hover:-translate-x-1 group-hover:-translate-y-1",
  "right-4 top-4 border-r-2 border-t-2 group-hover:translate-x-1 group-hover:-translate-y-1",
  "left-4 bottom-4 border-b-2 border-l-2 group-hover:-translate-x-1 group-hover:translate-y-1",
  "right-4 bottom-4 border-b-2 border-r-2 group-hover:translate-x-1 group-hover:translate-y-1",
];

export function Dropzone({ onFile, onError, disabled }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  function take(file: File | undefined) {
    if (!file) return;
    if (!ACCEPT.includes(file.type)) return onError("Usa una imagen JPEG, PNG o WebP.");
    if (file.size > MAX_MB * 1024 * 1024) return onError(`La imagen supera ${MAX_MB} MB.`);
    onFile(file);
  }

  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => input.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        take(e.dataTransfer.files[0]);
      }}
      className={`group relative flex min-h-[340px] w-full flex-col items-center justify-center gap-5 overflow-hidden rounded-3xl border px-6 py-16 text-center transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
        over ? "border-acid bg-acid-soft" : "border-line-strong bg-surface hover:border-acid/60"
      }`}
    >
      <div className="grid-bg pointer-events-none absolute inset-0 opacity-60" />
      {CORNERS.map((c) => (
        <span key={c} className={`pointer-events-none absolute h-8 w-8 border-acid transition-transform duration-300 ${c}`} />
      ))}

      <span
        className={`relative grid h-16 w-16 place-items-center rounded-2xl border border-acid/40 bg-acid-soft text-acid transition-transform duration-300 ${
          over ? "scale-110" : "group-hover:-translate-y-1"
        }`}
      >
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" aria-hidden>
          <path d="M12 16V4m0 0L7 9m5-5 5 5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
      </span>
      <span className="relative text-2xl font-extrabold tracking-tight sm:text-3xl">{over ? "Suéltala" : "Suelta tu foto aquí"}</span>
      <span className="relative text-ink-soft">
        o <span className="text-acid underline decoration-acid/40 underline-offset-4">elígela de tu equipo</span>
      </span>
      <span className="relative font-mono text-[11px] uppercase tracking-[0.16em] text-ink-faint">
        JPEG · PNG · WebP — máx. {MAX_MB} MB — se borra en 30 min
      </span>
      <input
        ref={input}
        type="file"
        accept={ACCEPT.join(",")}
        className="hidden"
        onChange={(e) => {
          take(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
    </button>
  );
}
