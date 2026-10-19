"use client";

import { useEffect, useRef } from "react";

/**
 * Comparador del hero: a la izquierda de la línea la foto tal cual; a la
 * derecha, la misma foto dibujada con la perturbación real que le añade Image Privacy Toolkit
 * (preset fuerte). Todo se mueve con transform: la ventana se desplaza y la
 * imagen interior se desplaza al revés, así que nunca se repinta.
 */
export function Scanner() {
  const frame = useRef<HTMLDivElement>(null);
  const windowEl = useRef<HTMLDivElement>(null);
  const inner = useRef<HTMLDivElement>(null);
  const line = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = frame.current;
    if (!el) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let pos = 0.55;
    let target = pos;
    let manual = false;
    let visible = true;
    let raf = 0;
    let lastInput = 0;
    const t0 = performance.now();

    const apply = (p: number) => {
      const pct = p * 100;
      windowEl.current!.style.transform = `translate3d(${pct}%,0,0)`;
      inner.current!.style.transform = `translate3d(${-pct}%,0,0)`;
      line.current!.style.transform = `translate3d(${el.clientWidth * p}px,0,0)`;
    };

    const tick = (now: number) => {
      if (!manual || now - lastInput > 2500) {
        manual = false;
        // Barrido automático suave mientras nadie interactúa.
        target = 0.5 + 0.32 * Math.sin((now - t0) / 1900);
      }
      pos += (target - pos) * 0.12;
      apply(pos);
      if (visible) raf = requestAnimationFrame(tick);
    };

    const onMove = (e: PointerEvent) => {
      const r = el.getBoundingClientRect();
      target = Math.min(0.98, Math.max(0.02, (e.clientX - r.left) / r.width));
      manual = true;
      lastInput = performance.now();
    };

    const onResize = () => apply(pos);

    apply(pos);
    if (reduce) return;

    const io = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      cancelAnimationFrame(raf);
      if (visible) raf = requestAnimationFrame(tick);
    });
    io.observe(el);
    el.addEventListener("pointermove", onMove);
    window.addEventListener("resize", onResize);
    return () => {
      io.disconnect();
      cancelAnimationFrame(raf);
      el.removeEventListener("pointermove", onMove);
      window.removeEventListener("resize", onResize);
    };
  }, []);

  return (
    <div
      ref={frame}
      className="relative aspect-square w-full touch-pan-y select-none overflow-hidden rounded-[28px] border border-line-strong bg-black"
      aria-label="Comparación entre la foto original y la capa de protección que añade Image Privacy Toolkit"
      role="img"
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/hero/human.webp" alt="" className="absolute inset-0 h-full w-full object-cover" draggable={false} fetchPriority="high" />

      <div ref={windowEl} className="absolute inset-0 overflow-hidden will-change-transform">
        <div ref={inner} className="absolute inset-0 will-change-transform">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/hero/ai.webp"
            alt=""
            className="absolute inset-0 h-full w-full object-cover"
            draggable={false}
            fetchPriority="low"
            decoding="async"
          />
        </div>
      </div>

      {/* Línea de escaneo */}
      <div ref={line} className="pointer-events-none absolute inset-y-0 left-0 w-px will-change-transform">
        <div className="absolute inset-y-0 -left-px w-[3px] bg-acid shadow-[0_0_24px_4px_rgb(212_255_58/0.55)]" />
        <div className="absolute top-1/2 -left-[18px] grid h-9 w-9 -translate-y-1/2 place-items-center rounded-full border border-acid bg-black/80 font-mono text-[10px] text-acid">
          ⇆
        </div>
      </div>

      {/* Marco de rostro (coordenadas relativas a la foto) */}
      <div className="pointer-events-none absolute left-[30%] top-[14%] h-[44%] w-[34%]">
        {["left-0 top-0 border-l-2 border-t-2", "right-0 top-0 border-r-2 border-t-2", "left-0 bottom-0 border-b-2 border-l-2", "right-0 bottom-0 border-b-2 border-r-2"].map(
          (c) => (
            <span key={c} className={`absolute h-5 w-5 border-acid ${c}`} />
          ),
        )}
        <span className="absolute -bottom-7 left-0 whitespace-nowrap bg-acid px-1.5 py-0.5 font-mono text-[10px] font-medium uppercase tracking-wider text-acid-ink">
          Rostro · no coincide
        </span>
      </div>

      {/* HUD */}
      <div className="pointer-events-none absolute inset-x-0 top-0 flex justify-between p-4 font-mono text-[10px] uppercase tracking-[0.18em] sm:text-[11px]">
        <span className="rounded bg-black/70 px-2 py-1 text-ink">Tu ojo</span>
        <span className="rounded bg-black/70 px-2 py-1 text-acid">Lo que se añade ×10</span>
      </div>
      <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/90 to-transparent p-4 pt-16 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-soft sm:text-[11px]">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <span>
            Identidad <span className="text-ink">0.99</span> → <span className="text-acid">0.13</span>
          </span>
          <span>Reconocedor no visto · tras JPEG 75</span>
        </div>
      </div>
    </div>
  );
}
