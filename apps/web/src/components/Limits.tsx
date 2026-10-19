import { Reveal } from "./Reveal";

const PROTECTS = [
  "Reconocedores faciales de herramientas de face-swap: tu identidad deja de coincidir.",
  "Edición con modelos de difusión abiertos (Stable Diffusion, FLUX): el modelo recibe una versión degradada.",
  "Ajuste fino con tus fotos (LoRA, DreamBooth): el entrenamiento absorbe parte de la perturbación.",
  "Reserva legal en los metadatos contra minería de datos y entrenamiento (IPTC).",
];

const LIMITS = [
  "No frena a los asistentes cerrados como Gemini, ChatGPT o Meta AI. En pruebas reales, Gemini editó una foto protegida (le puso lentes de sol manteniendo el rostro) sin problema.",
  "Ninguna perturbación es una garantía. Un modelo distinto a los atacados, o alguien que limpie la imagen a propósito, puede reducir el efecto.",
  "Resiste el reescalado y el JPEG de las redes, pero los recortes fuertes, los filtros y las capturas de pantalla la debilitan.",
  "Muchas redes borran los metadatos al subir la foto: la reserva legal solo viaja con el archivo original.",
  "No protege las fotos que ya publicaste sin proteger.",
];

export function Limits() {
  return (
    <section id="limites" className="scroll-mt-20 border-t border-line bg-bg-2 py-24 sm:py-32">
      <div className="mx-auto max-w-7xl px-4 sm:px-6">
        <Reveal>
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-acid">04 — Sin letra pequeña</p>
          <h2 className="mt-4 max-w-4xl text-5xl font-black leading-[0.95] tracking-[-0.04em] sm:text-6xl">
            Qué protege.
            <span className="font-display font-normal italic text-warn"> Y qué no.</span>
          </h2>
        </Reveal>

        <div className="mt-16 grid gap-4 md:grid-cols-2">
          <Reveal className="rounded-3xl border border-line bg-surface p-8">
            <h3 className="font-mono text-[11px] uppercase tracking-[0.18em] text-acid">Protege</h3>
            <ul className="mt-6 space-y-5">
              {PROTECTS.map((t) => (
                <li key={t} className="flex gap-4 leading-relaxed text-ink-soft">
                  <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full bg-acid-soft font-mono text-xs text-acid">✓</span>
                  {t}
                </li>
              ))}
            </ul>
          </Reveal>
          <Reveal delay={120} className="rounded-3xl border border-warn/30 bg-warn/5 p-8">
            <h3 className="font-mono text-[11px] uppercase tracking-[0.18em] text-warn">No puede prometer</h3>
            <ul className="mt-6 space-y-5">
              {LIMITS.map((t) => (
                <li key={t} className="flex gap-4 leading-relaxed text-ink-soft">
                  <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full bg-warn/10 font-mono text-xs text-warn">!</span>
                  {t}
                </li>
              ))}
            </ul>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
