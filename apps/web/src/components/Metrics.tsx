import { Reveal } from "./Reveal";

// Cifras del benchmark (services/engine/engine/eval), tras simular una subida
// a una red social (1080 px + JPEG 75). Si cambia el algoritmo, actualizarlas.
const STATS = [
  {
    value: "0.13",
    label: "parecido de identidad",
    note: "Con un reconocedor facial que el ataque nunca vio (preset fuerte). Empezaba en 0.99; por debajo de ~0.5 es “otra persona”.",
  },
  {
    value: "−3.5 dB",
    label: "lo que ve FLUX",
    note: "Caída de calidad de la imagen que recibe el modelo de difusión. Real pero modesta: el modelo sigue viendo tu foto, peor.",
  },
  {
    value: "36 dB",
    label: "diferencia para tu ojo",
    note: "PSNR del preset medio: a simple vista no se distingue de la original.",
  },
  {
    value: "~3 min",
    label: "en un portátil",
    note: "Sin tarjeta gráfica. Con GPU se activan los modelos completos.",
  },
];

export function Metrics() {
  return (
    <section id="metricas" className="scroll-mt-20 py-24 sm:py-32">
      <div className="mx-auto max-w-7xl px-4 sm:px-6">
        <Reveal className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-acid">Perturbación · medido, no prometido</p>
            <h2 className="mt-4 max-w-3xl text-5xl font-black leading-[0.95] tracking-[-0.04em] sm:text-6xl">
              Números reales.
              <span className="font-display font-normal italic text-ink-soft"> También los malos.</span>
            </h2>
          </div>
          <p className="max-w-sm text-ink-soft">
            Medimos cada capa contra modelos que el ataque nunca vio, después de reescalar y recomprimir la foto. El benchmark es público.
          </p>
        </Reveal>

        <div className="mt-16 grid gap-px overflow-hidden rounded-3xl border border-line bg-line sm:grid-cols-2 lg:grid-cols-4">
          {STATS.map((s, i) => (
            <Reveal key={s.label} delay={i * 100} className="bg-bg p-8">
              <p className="font-mono text-5xl font-medium tracking-tight text-acid tabular-nums">{s.value}</p>
              <p className="mt-3 font-semibold">{s.label}</p>
              <p className="mt-3 text-sm leading-relaxed text-ink-soft">{s.note}</p>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
