import { Logo } from "./Nav";

export function Footer() {
  return (
    <footer className="relative overflow-hidden border-t border-line">
      <div className="mx-auto max-w-7xl px-4 py-24 text-center sm:px-6">
        <p className="mx-auto max-w-3xl text-4xl font-black leading-[1] tracking-[-0.04em] sm:text-6xl">
          Publica tus fotos.
          <br />
          <span className="font-display font-normal italic text-acid">No tu identidad.</span>
        </p>
        <a
          href="#proteger"
          className="group mt-10 inline-flex items-center gap-3 rounded-full bg-acid px-8 py-4 font-semibold text-acid-ink transition-transform hover:-translate-y-0.5"
        >
          Proteger una foto
          <span className="transition-transform group-hover:translate-x-1">→</span>
        </a>
      </div>

      <div
        aria-hidden
        className="pointer-events-none select-none text-center text-[28vw] font-black leading-[0.75] tracking-[-0.06em] text-transparent [-webkit-text-stroke:1px_var(--line-strong)]"
      >
        IPT
      </div>

      <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-4 border-t border-line px-4 py-6 text-sm text-ink-faint sm:flex-row sm:px-6">
        <Logo />
        <p className="font-mono text-[11px] uppercase tracking-[0.14em]">Código abierto · MIT · tus fotos no se guardan</p>
      </div>
    </footer>
  );
}
