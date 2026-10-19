"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  detectFaces,
  exportProtected,
  loadImage,
  readMetadata,
  render,
  type Box,
  type MetadataSummary,
  type RedactMode,
  type Redaction,
} from "@/lib/privacy";

type Props = { file: File; onReset: () => void };

const MODE_LABEL: Record<RedactMode, string> = { blur: "Difuminar", pixelate: "Pixelar", solid: "Cubrir" };

export function PrivacyStudio({ file, onReset }: Props) {
  const [img, setImg] = useState<HTMLImageElement | null>(null);
  const [meta, setMeta] = useState<MetadataSummary | null>(null);
  const [redactions, setRedactions] = useState<Redaction[]>([]);
  const [mode, setMode] = useState<RedactMode>("blur");
  const [maxSide, setMaxSide] = useState<number>(0); // 0 = sin límite
  const [format, setFormat] = useState<"image/jpeg" | "image/png">("image/jpeg");
  const [faceNote, setFaceNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const drawing = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [image, m] = await Promise.all([loadImage(file), readMetadata(file)]);
        if (!alive) return;
        setImg(image);
        setMeta(m);
      } catch (e) {
        if (!alive) return;
        setError(e instanceof Error ? e.message : "No se pudo leer la imagen.");
      }
    })();
    return () => {
      alive = false;
    };
  }, [file]);

  // Repinta la vista previa (imagen + redacciones aplicadas).
  const repaint = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !img) return;
    const maxW = 720;
    const scale = Math.min(1, maxW / img.naturalWidth);
    const preview = render(img, { redactions });
    canvas.width = Math.round(img.naturalWidth * scale);
    canvas.height = Math.round(img.naturalHeight * scale);
    const ctx = canvas.getContext("2d")!;
    ctx.drawImage(preview, 0, 0, canvas.width, canvas.height);
  }, [img, redactions]);

  useEffect(() => repaint(), [repaint]);

  function toImageCoords(e: React.PointerEvent): { x: number; y: number } {
    const canvas = canvasRef.current!;
    const rect = canvas.getBoundingClientRect();
    const sx = img!.naturalWidth / rect.width;
    const sy = img!.naturalHeight / rect.height;
    return { x: (e.clientX - rect.left) * sx, y: (e.clientY - rect.top) * sy };
  }

  function onDown(e: React.PointerEvent) {
    if (!img) return;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    drawing.current = toImageCoords(e);
  }
  function onMove(e: React.PointerEvent) {
    if (!drawing.current || !img) return;
    const p = toImageCoords(e);
    const s = drawing.current;
    repaint();
    const canvas = canvasRef.current!;
    const ctx = canvas.getContext("2d")!;
    const k = canvas.width / img.naturalWidth;
    ctx.strokeStyle = "#d4ff3a";
    ctx.lineWidth = 2;
    ctx.strokeRect(Math.min(s.x, p.x) * k, Math.min(s.y, p.y) * k, Math.abs(p.x - s.x) * k, Math.abs(p.y - s.y) * k);
  }
  function onUp(e: React.PointerEvent) {
    if (!drawing.current || !img) return;
    const p = toImageCoords(e);
    const s = drawing.current;
    drawing.current = null;
    const box: Box = { x: Math.min(s.x, p.x), y: Math.min(s.y, p.y), w: Math.abs(p.x - s.x), h: Math.abs(p.y - s.y) };
    if (box.w > 6 && box.h > 6) setRedactions((r) => [...r, { ...box, mode }]);
  }

  async function onDetectFaces() {
    if (!img) return;
    const res = await detectFaces(img);
    if (!res.supported) {
      setFaceNote("Tu navegador no ofrece detección de rostros. Puedes marcar las zonas a mano.");
      return;
    }
    setRedactions((r) => [...r, ...res.boxes.map((b) => ({ ...b, mode }))]);
    setFaceNote(res.boxes.length ? `Se marcaron ${res.boxes.length} rostro(s). Revisa que sean correctos.` : "No se detectaron rostros (puede haberlos; marca a mano).");
  }

  async function onDownload() {
    if (!img) return;
    setBusy(true);
    setError(null);
    try {
      const blob = await exportProtected(img, {
        redactions,
        maxSide: maxSide || undefined,
        format,
        quality: 0.92,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const ext = format === "image/png" ? "png" : "jpg";
      a.download = `${file.name.replace(/\.[^.]+$/, "")}-privada.${ext}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo exportar.");
    } finally {
      setBusy(false);
    }
  }

  const removed = ["Todos los metadatos (EXIF)"];
  if (meta?.hasGps) removed.push("Ubicación GPS");
  if (maxSide) removed.push(`Resolución limitada a ${maxSide}px`);

  // Si la imagen no se pudo cargar, no tiene sentido mostrar el editor.
  if (!img && error) {
    return (
      <div className="rise space-y-4 rounded-2xl border border-danger/40 bg-surface p-6 text-center">
        <p className="text-sm text-danger">{error}</p>
        <button
          onClick={onReset}
          className="rounded-full border border-line px-5 py-2 text-sm text-ink-soft hover:border-acid"
        >
          Elegir otra foto
        </button>
      </div>
    );
  }

  return (
    <div className="rise space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1.5 font-mono text-[11px] uppercase tracking-[0.16em] text-acid">
          <span className="h-1.5 w-1.5 rounded-full bg-acid" /> Procesado solo en tu dispositivo
        </div>
        <button onClick={onReset} className="text-sm text-ink-soft underline-offset-4 hover:underline">
          Cambiar foto
        </button>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <div className="space-y-3">
          <canvas
            ref={canvasRef}
            onPointerDown={onDown}
            onPointerMove={onMove}
            onPointerUp={onUp}
            className="w-full cursor-crosshair touch-none rounded-2xl border border-line-strong bg-black"
          />
          <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-faint">
            Arrastra sobre la foto para marcar una zona a ocultar
          </p>
        </div>

        <div className="space-y-5">
          <section className="rounded-2xl border border-line bg-surface p-4">
            <h3 className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint">Qué contiene tu archivo</h3>
            {meta ? (
              meta.hasExif ? (
                <ul className="mt-2 space-y-1 text-sm text-ink-soft">
                  {meta.fields.map((f) => (
                    <li key={f} className="flex gap-2">
                      <span className={f.includes("GPS") ? "text-danger" : "text-warn"}>●</span> {f}
                    </li>
                  ))}
                  <li className="pt-1 text-xs text-ink-faint">Todo esto se eliminará al descargar.</li>
                </ul>
              ) : (
                <p className="mt-2 text-sm text-ink-soft">No se detectaron metadatos EXIF (o no se pudieron leer). Se re-exporta sin metadatos de todas formas.</p>
              )
            ) : (
              <p className="mt-2 text-sm text-ink-faint">Analizando…</p>
            )}
          </section>

          <section className="space-y-3">
            <div className="flex gap-2">
              {(Object.keys(MODE_LABEL) as RedactMode[]).map((m) => (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  className={`flex-1 rounded-lg border px-2 py-2 text-sm transition-colors ${mode === m ? "border-acid bg-acid-soft text-ink" : "border-line text-ink-soft hover:border-line-strong"}`}
                >
                  {MODE_LABEL[m]}
                </button>
              ))}
            </div>
            <div className="flex flex-wrap gap-2">
              <button onClick={onDetectFaces} className="rounded-lg border border-line px-3 py-2 text-sm text-ink-soft hover:border-acid">
                Detectar rostros
              </button>
              {redactions.length > 0 && (
                <button onClick={() => setRedactions([])} className="rounded-lg border border-line px-3 py-2 text-sm text-ink-soft hover:border-danger hover:text-danger">
                  Quitar marcas ({redactions.length})
                </button>
              )}
            </div>
            {faceNote && <p className="text-xs text-ink-soft">{faceNote}</p>}
          </section>

          <section className="rounded-2xl border border-line bg-surface p-4 text-sm">
            <label className="flex items-center justify-between gap-3">
              <span className="text-ink-soft">Limitar resolución</span>
              <select value={maxSide} onChange={(e) => setMaxSide(Number(e.target.value))} className="rounded-md border border-line bg-bg px-2 py-1 text-ink">
                <option value={0}>Original</option>
                <option value={1600}>1600 px</option>
                <option value={1080}>1080 px</option>
                <option value={720}>720 px</option>
              </select>
            </label>
            <label className="mt-3 flex items-center justify-between gap-3">
              <span className="text-ink-soft">Formato</span>
              <select value={format} onChange={(e) => setFormat(e.target.value as "image/jpeg" | "image/png")} className="rounded-md border border-line bg-bg px-2 py-1 text-ink">
                <option value="image/jpeg">JPEG</option>
                <option value="image/png">PNG</option>
              </select>
            </label>
          </section>

          <button
            onClick={onDownload}
            disabled={busy}
            className="btn-glow w-full rounded-full bg-acid px-6 py-4 font-semibold text-acid-ink disabled:opacity-50"
          >
            {busy ? "Preparando…" : "Descargar copia privada"}
          </button>
          {error && <p className="text-sm text-danger">{error}</p>}
        </div>
      </div>

      <section className="rounded-2xl border border-line bg-bg-2 p-5 text-sm text-ink-soft">
        <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint">Qué hace y qué no</p>
        <div className="mt-3 grid gap-4 sm:grid-cols-2">
          <div>
            <p className="font-medium text-ink">Se elimina / oculta</p>
            <ul className="mt-1 space-y-1">
              {removed.map((r) => (
                <li key={r} className="flex gap-2">
                  <span className="text-acid">✓</span> {r}
                </li>
              ))}
              {redactions.length > 0 && (
                <li className="flex gap-2">
                  <span className="text-acid">✓</span> {redactions.length} zona(s) marcada(s)
                </li>
              )}
            </ul>
          </div>
          <div>
            <p className="font-medium text-ink">Riesgos que siguen</p>
            <ul className="mt-1 space-y-1">
              <li className="flex gap-2">
                <span className="text-warn">!</span> Quitar metadatos NO anonimiza: la cara, un documento o un lugar visibles pueden seguir identificándote.
              </li>
              <li className="flex gap-2">
                <span className="text-warn">!</span> La detección de rostros es orientativa, no infalible. Revisa a mano.
              </li>
            </ul>
          </div>
        </div>
      </section>
    </div>
  );
}
