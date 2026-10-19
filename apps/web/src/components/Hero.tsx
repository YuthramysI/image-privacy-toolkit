import { Scanner } from "./Scanner";

// Las tres herramientas, como índice compacto (no tarjetas descriptivas: la
// descripción vive en cada sección, aquí solo navegación).
const TOOLS = [
  {
    n: "01",
    href: "#privacidad",
    name: "Privacidad local",
    tag: "Estable",
    icon: (
      <>
        <path d="M12 3l7 3v5c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3z" />
        <path d="M9 12l2 2 4-4" />
      </>
    ),
  },
  {
    n: "02",
    href: "#evidencias",
    name: "Comparar y documentar",
    tag: "Estable",
    icon: (
      <>
        <circle cx="11" cy="11" r="7" />
        <path d="M21 21l-4.3-4.3" />
      </>
    ),
  },
  {
    n: "03",
    href: "#proteger",
    name: "Perturbación",
    tag: "Experimental",
    icon: <path d="M3 12c3 0 3-6 6-6s3 12 6 12 3-6 6-6" />,
  },
];

export function Hero() {
  return (
    <section className="relative overflow-hidden">
      <div className="aurora" aria-hidden />
      <div className="grid-bg pointer-events-none absolute inset-0 [mask-image:radial-gradient(ellipse_at_top,black_30%,transparent_72%)]" />

      <div className="relative mx-auto flex min-h-[calc(100svh-4rem)] max-w-7xl flex-col justify-center gap-10 px-4 pb-10 pt-28 sm:px-6 sm:pb-14 sm:pt-32">
        <div className="grid items-center gap-10 lg:grid-cols-[1.08fr_1fr] lg:gap-14">
          <div className="rise">
            <p className="mb-6 inline-flex items-center gap-2 rounded-full border border-line-strong bg-surface/60 px-3 py-1.5 font-mono text-[11px] uppercase tracking-[0.18em] text-ink-soft backdrop-blur">
              <span className="blink h-1.5 w-1.5 rounded-full bg-acid" />
              Privacidad de imágenes · local y de código abierto
            </p>

            <h1 className="text-[clamp(3.2rem,min(7.5vw,11svh),6.4rem)] font-black leading-[0.86] tracking-[-0.045em]">
              Tu cara
              <br />
              no es un
              <br />
              <span className="chroma font-display text-[1.12em] font-normal italic tracking-[-0.02em] text-acid">dataset.</span>
            </h1>

            <p className="mt-6 max-w-xl text-lg leading-relaxed text-ink-soft">
              Un kit de <span className="text-ink">tres herramientas gratuitas</span> para reducir el uso no consentido de tus fotos, todas en tu
              navegador: <span className="text-ink">límpialas</span>, descubre <span className="text-ink">dónde se han reutilizado</span> y —experimental—
              añádeles una <span className="text-ink">capa contra los modelos de imagen</span>.
            </p>

            <div className="mt-8 flex flex-wrap items-center gap-4">
              <a
                href="#privacidad"
                className="btn-glow group inline-flex items-center gap-3 rounded-full bg-acid px-7 py-4 text-base font-semibold text-acid-ink"
              >
                Limpia tu foto
                <span className="transition-transform group-hover:translate-x-1">→</span>
              </a>
              <a href="#limites" className="px-2 py-4 text-sm text-ink-soft underline decoration-line-strong underline-offset-8 transition-colors hover:text-ink">
                Qué protege y qué no
              </a>
            </div>

            <dl className="mt-10 grid max-w-lg grid-cols-3 gap-6 border-t border-line pt-6">
              {[
                ["0 €", "para siempre"],
                ["Local", "en tu navegador"],
                ["MIT", "código abierto"],
              ].map(([k, v]) => (
                <div key={v}>
                  <dt className="font-mono text-2xl text-ink">{k}</dt>
                  <dd className="mt-1 text-xs uppercase tracking-wider text-ink-faint">{v}</dd>
                </div>
              ))}
            </dl>
          </div>

          <div className="rise mx-auto w-full max-w-[460px] [animation-delay:150ms] lg:mx-0 lg:max-w-none lg:justify-self-end">
            <Scanner />
            <p className="mt-3 text-center font-mono text-[11px] uppercase tracking-[0.16em] text-ink-faint">
              Demo de la capa de perturbación · mueve el cursor
            </p>
          </div>
        </div>

        {/* Índice compacto de las tres herramientas (navegación, sin repetir descripciones). */}
        <nav aria-label="Las tres herramientas" className="rise grid overflow-hidden rounded-2xl border border-line bg-surface/40 backdrop-blur divide-y divide-line sm:grid-cols-3 sm:divide-x sm:divide-y-0 [animation-delay:250ms]">
          {TOOLS.map((t) => (
            <a key={t.n} href={t.href} className="group flex items-center gap-4 px-5 py-4 transition-colors hover:bg-surface">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-line-strong bg-bg text-acid transition-colors group-hover:border-acid/50">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                  {t.icon}
                </svg>
              </span>
              <span className="min-w-0">
                <span className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-ink-faint">
                  {t.n}
                  <span className={`h-1 w-1 rounded-full ${t.tag === "Estable" ? "bg-acid" : "bg-warn"}`} />
                  {t.tag}
                </span>
                <span className="mt-0.5 block truncate text-sm font-semibold text-ink transition-colors group-hover:text-acid">{t.name}</span>
              </span>
              <span className="ml-auto text-ink-faint transition-all group-hover:translate-x-0.5 group-hover:text-acid" aria-hidden>→</span>
            </a>
          ))}
        </nav>
      </div>
    </section>
  );
}
