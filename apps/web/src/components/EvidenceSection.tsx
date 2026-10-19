"use client";

import { EvidenceStudio } from "./EvidenceStudio";

export function EvidenceSection() {
  return (
    <section id="evidencias" className="scroll-mt-20 border-t border-line py-24 sm:py-32">
      <div className="mx-auto max-w-7xl px-4 sm:px-6">
        <div className="mb-10">
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-acid">02 — Cuando una copia ya circula</p>
          <h2 className="mt-4 max-w-4xl text-5xl font-black leading-[0.95] tracking-[-0.04em] sm:text-6xl">
            Compara y
            <span className="font-display font-normal italic text-ink-soft"> documenta la evidencia.</span>
          </h2>
          <p className="mt-6 max-w-2xl text-lg text-ink-soft">
            Si crees que una foto tuya se reutilizó: regístrala, <strong className="text-ink">compárala con la imagen que encuentres</strong> por huella
            criptográfica y perceptual, y genera un <strong className="text-ink">expediente descargable</strong> con las huellas y los datos. Todo en tu
            navegador, <strong className="text-ink">sin servidores ni terceros</strong>.
          </p>
          <p className="mt-3 max-w-2xl text-sm text-ink-faint">
            Es una herramienta de comparación y documentación, <strong className="text-ink-soft">no un buscador de Internet</strong>: tú aportas las
            imágenes. Una coincidencia indica parecido visual; no prueba por sí sola copia, identidad ni uso ilícito, y el expediente no garantiza
            admisibilidad legal.
          </p>
        </div>

        <EvidenceStudio />
      </div>
    </section>
  );
}
