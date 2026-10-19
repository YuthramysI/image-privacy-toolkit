import { Reveal } from "./Reveal";

const LAYERS = [
  {
    n: "A",
    title: "Capa de rostro",
    against: "Face-swap · reconocimiento facial",
    body: "Desplaza la identidad que un reconocedor extrae de tu cara. Para el modelo pasas a ser otra persona; para tus amigos sigues siendo tú.",
  },
  {
    n: "B",
    title: "Capa de difusión",
    against: "img2img · LoRA con modelos abiertos",
    body: "Arrastra lo que “ve” un modelo de difusión abierto hacia una textura sin sentido. Ataca a la vez la familia Stable Diffusion y la familia FLUX; no alcanza a modelos cerrados como Gemini.",
  },
  {
    n: "C",
    title: "Capa legal",
    against: "Minería de datos",
    body: "Escribe en los metadatos la reserva IPTC “prohibido entrenar IA”. No frena a nadie técnicamente, pero deja constancia de tus derechos.",
  },
];

export function HowItWorks() {
  return (
    <section id="como-funciona" className="scroll-mt-20 border-t border-line bg-bg-2 py-24 sm:py-32">
      <div className="mx-auto max-w-7xl px-4 sm:px-6">
        <Reveal>
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-acid">Perturbación · cómo funciona</p>
          <h2 className="mt-4 max-w-4xl text-5xl font-black leading-[0.95] tracking-[-0.04em] sm:text-6xl">
            Tres capas.
            <span className="font-display font-normal italic text-ink-soft"> Una sola pasada.</span>
          </h2>
          <p className="mt-6 max-w-2xl text-lg text-ink-soft">
            Las tres se calculan juntas en una optimización que pasa tu foto, una y otra vez, por lo mismo que le hará una red social: reducirla y
            recomprimirla. Por eso la protección sigue ahí después de subirla.
          </p>
        </Reveal>

        <div className="mt-16 grid gap-4 md:grid-cols-3">
          {LAYERS.map((l, i) => (
            <Reveal key={l.n} delay={i * 120}>
              <article className="glow-card group relative h-full overflow-hidden rounded-3xl border border-line bg-surface p-8 hover:border-acid/50">
                <span className="absolute inset-x-0 top-0 h-px origin-left scale-x-0 bg-acid transition-transform duration-500 group-hover:scale-x-100" />
                <div className="flex items-start justify-between">
                  <span className="font-display text-7xl italic leading-none text-acid">{l.n}</span>
                  <span className="rounded-full border border-line-strong px-3 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-faint">
                    capa {i + 1}/3
                  </span>
                </div>
                <h3 className="mt-10 text-2xl font-extrabold tracking-tight">{l.title}</h3>
                <p className="mt-2 font-mono text-[11px] uppercase tracking-[0.14em] text-acid/80">Contra: {l.against}</p>
                <p className="mt-5 leading-relaxed text-ink-soft">{l.body}</p>
              </article>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
