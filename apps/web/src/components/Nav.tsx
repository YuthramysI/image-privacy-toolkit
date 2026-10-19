"use client";

import { useEffect, useRef, useState } from "react";

import { ScrollProgress } from "./ScrollProgress";

const LINKS = [
  ["#privacidad", "Privacidad"],
  ["#evidencias", "Evidencias"],
  ["#proteger", "Perturbación"],
  ["#como-funciona", "Cómo funciona"],
  ["#metricas", "Métricas"],
  ["#limites", "Límites"],
] as const;

export function Logo({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden>
        <rect x="2" y="2" width="20" height="20" rx="5" fill="none" stroke="var(--acid)" strokeWidth="2" />
        <path d="M2 9h20M2 15h20" stroke="var(--acid)" strokeWidth="1.2" strokeDasharray="1.5 2.5" />
      </svg>
      <span className="text-base font-black tracking-[-0.03em]">Image Privacy Toolkit</span>
    </span>
  );
}

export function Nav() {
  const [active, setActive] = useState("");
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  // Sección activa (resaltado del menú) + fondo de la barra al hacer scroll.
  useEffect(() => {
    const ids = LINKS.map(([href]) => href.slice(1));
    let raf = 0;
    const measure = () => {
      raf = 0;
      setScrolled(window.scrollY > 8);
      const line = window.scrollY + window.innerHeight * 0.3;
      let current = "";
      for (const id of ids) {
        const el = document.getElementById(id);
        if (el && el.getBoundingClientRect().top + window.scrollY <= line + 1) current = id;
      }
      setActive(current);
    };
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(measure);
    };
    measure();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);

  // Menú móvil: Escape, trampa de foco, bloqueo de scroll, foco al abrir/cerrar.
  useEffect(() => {
    if (!open) return;
    const trigger = btnRef.current;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusables = () => Array.from(panelRef.current?.querySelectorAll<HTMLElement>("a,button") ?? []);
    focusables()[0]?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        return;
      }
      if (e.key === "Tab") {
        const els = focusables();
        if (els.length === 0) return;
        const first = els[0];
        const last = els[els.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
      trigger?.focus();
    };
  }, [open]);

  return (
    <header
      className={`fixed inset-x-0 top-0 z-40 border-b backdrop-blur-md transition-colors duration-300 ${
        scrolled || open ? "border-line/80 bg-bg/85" : "border-transparent bg-bg/40"
      }`}
    >
      <ScrollProgress />
      <nav className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6">
        <a href="#" aria-label="Image Privacy Toolkit, inicio" className="transition-opacity hover:opacity-80">
          <Logo />
        </a>

        <ul className="hidden items-center gap-6 text-sm text-ink-soft lg:flex">
          {LINKS.map(([href, label]) => {
            const isActive = active === href.slice(1);
            return (
              <li key={href}>
                <a
                  href={href}
                  aria-current={isActive ? "true" : undefined}
                  className={`relative py-1 transition-colors hover:text-ink ${isActive ? "text-ink" : ""}`}
                >
                  {label}
                  <span className={`absolute -bottom-0.5 left-0 h-px bg-acid transition-all duration-300 ${isActive ? "w-full opacity-100" : "w-0 opacity-0"}`} />
                </a>
              </li>
            );
          })}
        </ul>

        <div className="flex items-center gap-2">
          <a
            href="#privacidad"
            className="btn-glow hidden rounded-full border border-acid/60 px-4 py-2 text-sm font-medium text-acid transition-colors hover:bg-acid hover:text-acid-ink sm:inline-flex"
          >
            Empezar
          </a>
          <button
            ref={btnRef}
            type="button"
            onClick={() => setOpen((o) => !o)}
            aria-label={open ? "Cerrar menú" : "Abrir menú"}
            aria-expanded={open}
            aria-controls="mobile-menu"
            className="grid h-10 w-10 place-items-center rounded-lg border border-line text-ink transition-colors hover:border-acid/60 lg:hidden"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden>
              {open ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
            </svg>
          </button>
        </div>
      </nav>

      {open && (
        <div className="lg:hidden">
          <button
            type="button"
            aria-label="Cerrar menú"
            onClick={() => setOpen(false)}
            className="fixed inset-x-0 bottom-0 top-16 z-30 w-full cursor-default bg-bg/50 backdrop-blur-sm"
            tabIndex={-1}
          />
          <div
            id="mobile-menu"
            ref={panelRef}
            className="rise absolute inset-x-0 top-16 z-40 border-b border-line bg-bg/95 shadow-2xl backdrop-blur-md"
          >
            <ul className="mx-auto max-w-7xl px-4 py-3 sm:px-6">
              {LINKS.map(([href, label]) => {
                const isActive = active === href.slice(1);
                return (
                  <li key={href}>
                    <a
                      href={href}
                      onClick={() => setOpen(false)}
                      aria-current={isActive ? "true" : undefined}
                      className={`flex items-center justify-between rounded-lg px-3 py-3 text-base transition-colors hover:bg-surface ${
                        isActive ? "text-acid" : "text-ink-soft"
                      }`}
                    >
                      {label}
                      <span aria-hidden className={isActive ? "text-acid" : "text-ink-faint"}>→</span>
                    </a>
                  </li>
                );
              })}
              <li className="pt-2">
                <a
                  href="#privacidad"
                  onClick={() => setOpen(false)}
                  className="flex items-center justify-center rounded-full bg-acid px-5 py-3 text-sm font-semibold text-acid-ink"
                >
                  Empezar
                </a>
              </li>
            </ul>
          </div>
        </div>
      )}
    </header>
  );
}
