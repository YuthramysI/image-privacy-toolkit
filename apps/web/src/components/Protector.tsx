"use client";

import { useEffect, useRef, useState } from "react";

import { Compare } from "./Compare";
import { Dropzone } from "./Dropzone";
import { PresetPicker } from "./PresetPicker";
import { ProgressPanel } from "./ProgressPanel";
import {
  cancelJob,
  createJob,
  fetchPresets,
  fetchResult,
  watchJob,
  type JobState,
  type Preset,
  type PresetName,
} from "@/lib/engine";

type Phase = "pick" | "ready" | "running" | "done";

const STEPS = ["Sube tu foto", "Elige intensidad", "Descarga"] as const;

function stepIndex(phase: Phase) {
  return phase === "pick" ? 0 : phase === "done" ? 2 : 1;
}

export function Protector() {
  const [presets, setPresets] = useState<Preset[]>([]);
  const [engineDown, setEngineDown] = useState(false);
  const [preset, setPreset] = useState<PresetName>("media");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("pick");
  const [job, setJob] = useState<JobState | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [result, setResult] = useState<{ png: string; jpeg: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const stopWatching = useRef<(() => void) | null>(null);
  const stage = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchPresets()
      .then((p) => {
        setPresets(p);
        if (!p.some((x) => x.name === "media") && p[0]) setPreset(p[0].name);
      })
      .catch(() => setEngineDown(true));
    return () => stopWatching.current?.();
  }, []);

  useEffect(() => () => void (preview && URL.revokeObjectURL(preview)), [preview]);
  useEffect(
    () => () => {
      if (result) {
        URL.revokeObjectURL(result.png);
        URL.revokeObjectURL(result.jpeg);
      }
    },
    [result],
  );

  // Mantiene la herramienta a la vista al cambiar de fase.
  useEffect(() => {
    if (phase !== "pick") stage.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [phase]);

  function choose(f: File) {
    setError(null);
    setFile(f);
    setPreview(URL.createObjectURL(f));
    setResult(null);
    setJob(null);
    setPhase("ready");
  }

  function reset() {
    stopWatching.current?.();
    setFile(null);
    setPreview(null);
    setResult(null);
    setJob(null);
    setJobId(null);
    setError(null);
    setPhase("pick");
  }

  async function start() {
    if (!file) return;
    setError(null);
    setPhase("running");
    try {
      const id = await createJob(file, preset);
      setJobId(id);
      stopWatching.current = watchJob(
        id,
        async (s) => {
          setJob(s);
          if (s.status === "done") {
            const [png, jpeg] = await Promise.all([fetchResult(id, "png"), fetchResult(id, "jpeg")]);
            setResult({ png: URL.createObjectURL(png), jpeg: URL.createObjectURL(jpeg) });
            setPhase("done");
          } else if (s.status === "failed") {
            setError(s.error ?? "La protección falló.");
            setPhase("ready");
          } else if (s.status === "cancelled") {
            setPhase("ready");
          }
        },
        (msg) => {
          setError(msg);
          setPhase("ready");
        },
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo contactar con el motor.");
      setPhase("ready");
    }
  }

  async function cancel() {
    stopWatching.current?.();
    if (jobId) await cancelJob(jobId);
    setJob(null);
    setPhase("ready");
  }

  const baseName = file?.name.replace(/\.[^.]+$/, "") ?? "foto";
  const current = stepIndex(phase);

  return (
    <section id="proteger" className="scroll-mt-20 py-24 sm:py-32">
      <div className="mx-auto max-w-7xl px-4 sm:px-6">
        <div className="mb-12 flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-warn">03 — Perturbación · experimental</p>
            <h2 className="mt-4 text-5xl font-black leading-[0.95] tracking-[-0.04em] sm:text-6xl">
              Añade una capa
              <br />
              <span className="font-display font-normal italic text-ink-soft">contra los modelos.</span>
            </h2>
            <p className="mt-4 max-w-xl text-ink-soft">
              La parte de investigación: un ruido casi invisible contra reconocedores faciales y modelos de imagen abiertos (Stable Diffusion, FLUX).
              Ayuda contra esos modelos, con resultados modestos; <span className="text-ink">no es una garantía</span> y no frena a asistentes cerrados
              como Gemini o ChatGPT.
            </p>
          </div>
          <ol className="flex flex-wrap gap-2 sm:gap-3">
            {STEPS.map((label, i) => (
              <li
                key={label}
                className={`flex items-center gap-2 rounded-full border px-3 py-2 font-mono text-[10px] uppercase tracking-[0.14em] transition-colors sm:px-4 sm:text-[11px] ${
                  i === current ? "border-acid bg-acid text-acid-ink" : i < current ? "border-acid/40 text-acid" : "border-line text-ink-faint"
                }`}
              >
                <span>{i < current ? "✓" : `0${i + 1}`}</span>
                <span className="hidden sm:inline">{label}</span>
              </li>
            ))}
          </ol>
        </div>

        <div ref={stage} className="scroll-mt-24">
          {engineDown && (
            <div role="status" className="mb-6 flex flex-col gap-1 rounded-2xl border border-line-strong bg-surface p-4 text-sm text-ink-soft sm:flex-row sm:items-center sm:gap-3">
              <span className="inline-flex shrink-0 items-center gap-2 font-mono text-[11px] uppercase tracking-[0.14em] text-warn">
                <span className="h-1.5 w-1.5 rounded-full bg-warn" /> Motor no conectado
              </span>
              <span>
                Esta herramienta es experimental y necesita el <strong className="text-ink">motor local</strong>, que no se incluye con la web. Para
                probarla, arráncalo con <code className="rounded bg-bg px-1 font-mono text-ink">make serve</code> en{" "}
                <code className="rounded bg-bg px-1 font-mono text-ink">services/engine</code>. Privacidad y Evidencias no lo necesitan.
              </span>
            </div>
          )}

          {phase === "pick" && <Dropzone onFile={choose} onError={setError} disabled={engineDown} />}

          {phase === "ready" && preview && (
            <div className="rise grid gap-8 lg:grid-cols-[1.1fr_1fr]">
              <div className="relative overflow-hidden rounded-3xl border border-line-strong bg-black">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={preview} alt="Tu foto" className="block max-h-[560px] w-full object-contain" />
                <div className="absolute inset-x-0 bottom-0 flex items-center justify-between gap-4 bg-gradient-to-t from-black/90 to-transparent p-4 pt-14">
                  <div className="min-w-0">
                    <p className="truncate font-medium">{file?.name}</p>
                    <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-soft">{file && (file.size / 1024 / 1024).toFixed(1)} MB</p>
                  </div>
                  <button
                    onClick={reset}
                    className="shrink-0 rounded-full border border-line-strong bg-black/60 px-4 py-2 text-sm text-ink-soft transition-colors hover:text-ink"
                  >
                    Cambiar
                  </button>
                </div>
              </div>

              <div className="flex flex-col gap-8">
                {presets.length > 0 && <PresetPicker presets={presets} value={preset} onChange={setPreset} />}
                <button
                  onClick={start}
                  disabled={engineDown || presets.length === 0}
                  className="btn-glow group mt-auto inline-flex items-center justify-center gap-3 rounded-full bg-acid px-8 py-5 text-lg font-semibold text-acid-ink disabled:opacity-40"
                >
                  Proteger foto
                  <span className="transition-transform group-hover:translate-x-1">→</span>
                </button>
              </div>
            </div>
          )}

          {phase === "running" && preview && <ProgressPanel preview={preview} state={job} onCancel={cancel} />}

          {phase === "done" && preview && result && (
            <div className="rise grid gap-8 lg:grid-cols-[1.4fr_1fr] lg:items-start">
              <Compare original={preview} protectedUrl={result.png} />

              <div className="space-y-6 lg:sticky lg:top-24">
                <div className="rounded-3xl border border-acid/40 bg-acid-soft p-6">
                  <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-acid">Protegida</p>
                  <p className="mt-3 text-3xl font-black leading-tight tracking-tight">Lista para publicar.</p>
                  <ul className="mt-5 space-y-2 text-sm text-ink-soft">
                    <li className="flex gap-2">
                      <span className="text-acid">✓</span>
                      {job?.faces ? `${job.faces} rostro(s) protegido(s) contra reconocimiento` : "Sin rostros: protegida contra edición y entrenamiento"}
                    </li>
                    <li className="flex gap-2">
                      <span className="text-acid">✓</span>
                      Capa anti-difusión (SD y FLUX)
                    </li>
                    <li className="flex gap-2">
                      <span className="text-acid">✓</span>
                      Reserva &quot;no entrenar&quot; en los metadatos
                    </li>
                  </ul>
                </div>

                <div className="flex flex-col gap-3">
                  <a
                    href={result.png}
                    download={`${baseName}-protegida.png`}
                    className="group inline-flex items-center justify-between rounded-full bg-acid px-7 py-4 font-semibold text-acid-ink transition-transform hover:-translate-y-0.5"
                  >
                    Descargar PNG
                    <span className="font-mono text-xs font-medium uppercase tracking-wider opacity-70">máxima calidad ↓</span>
                  </a>
                  <a
                    href={result.jpeg}
                    download={`${baseName}-protegida.jpg`}
                    className="inline-flex items-center justify-between rounded-full border border-line-strong px-7 py-4 font-semibold transition-colors hover:border-acid"
                  >
                    Descargar JPEG
                    <span className="font-mono text-xs font-medium uppercase tracking-wider text-ink-faint">más ligero ↓</span>
                  </a>
                  <button onClick={reset} className="py-2 text-sm text-ink-soft underline decoration-line-strong underline-offset-8 hover:text-ink">
                    Proteger otra foto
                  </button>
                </div>

                <p className="text-sm leading-relaxed text-ink-faint">
                  Publica este archivo, no el original. Tu foto se borra del servidor en 30 minutos.
                </p>
              </div>
            </div>
          )}

          {error && (
            <p role="alert" className="mt-6 rounded-2xl border border-danger/40 bg-danger/10 p-4 text-sm text-danger">
              {error}
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
