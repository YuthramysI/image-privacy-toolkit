"use client";

import { useState } from "react";

import { Dropzone } from "./Dropzone";
import { PrivacyStudio } from "./PrivacyStudio";

export function PrivacySection() {
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  return (
    <section id="privacidad" className="scroll-mt-20 border-t border-line bg-bg-2 py-24 sm:py-32">
      <div className="mx-auto max-w-7xl px-4 sm:px-6">
        <div className="mb-10">
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-acid">01 — Privacidad antes de publicar</p>
          <h2 className="mt-4 max-w-4xl text-5xl font-black leading-[0.95] tracking-[-0.04em] sm:text-6xl">
            Limpia tu foto
            <span className="font-display font-normal italic text-ink-soft"> sin que salga de tu equipo.</span>
          </h2>
          <p className="mt-6 max-w-2xl text-lg text-ink-soft">
            Quita la ubicación GPS y los metadatos, oculta rostros, documentos o matrículas, y reduce la resolución. Todo se procesa en tu navegador:
            la foto <strong className="text-ink">no se envía a ningún servidor</strong>. El original queda intacto.
          </p>
        </div>

        {!file ? (
          <>
            <Dropzone onFile={setFile} onError={setError} />
            {error && (
              <p role="alert" className="mt-4 text-sm text-danger">
                {error}
              </p>
            )}
          </>
        ) : (
          <PrivacyStudio file={file} onReset={() => setFile(null)} />
        )}
      </div>
    </section>
  );
}
