"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { fingerprintFile, readAsDataUrl, sha256OfFile, type Fingerprint } from "@/lib/reuseImage";
import {
  buildDossier,
  compare,
  dossierToHtml,
  dossierToJson,
  type Attachment,
  type ComparisonResult,
  type PublicationInfo,
  type RegistryRecord,
} from "@/lib/reuse";
import { deleteRecord, listRecords, putRecord } from "@/lib/reuseStore";

const ACCEPT = ["image/jpeg", "image/png", "image/webp"];
const MAX_MB = 15;

function validate(file: File): string | null {
  if (!ACCEPT.includes(file.type)) return "Usa una imagen JPEG, PNG o WebP.";
  if (file.size > MAX_MB * 1024 * 1024) return `La imagen supera ${MAX_MB} MB.`;
  return null;
}

/** Botón que abre el selector de archivos sin exponer el input. */
function PickButton({ onPick, accept = ACCEPT.join(","), children, className = "" }: { onPick: (f: File) => void; accept?: string; children: React.ReactNode; className?: string }) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <>
      <button type="button" onClick={() => ref.current?.click()} className={className}>
        {children}
      </button>
      <input
        ref={ref}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          e.target.value = "";
          if (f) onPick(f);
        }}
      />
    </>
  );
}

const CARD = "rounded-2xl border border-line bg-surface p-5";
const LABEL = "font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint";
const INPUT = "w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-acid focus:outline-none";

type MatchRow = { record: RegistryRecord; result: ComparisonResult };

export function EvidenceStudio() {
  const [records, setRecords] = useState<RegistryRecord[]>([]);
  const [storageError, setStorageError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  // Registro de una foto nueva.
  const [newName, setNewName] = useState("");
  const [newNotes, setNewNotes] = useState("");
  const [pending, setPending] = useState<{ file: File; fp: Fingerprint } | null>(null);
  const [regError, setRegError] = useState<string | null>(null);

  // Comparación.
  const [suspect, setSuspect] = useState<(Fingerprint & { file: File }) | null>(null);
  const [matches, setMatches] = useState<MatchRow[] | null>(null);
  const [compareError, setCompareError] = useState<string | null>(null);

  // Publicación + adjuntos.
  const [pub, setPub] = useState<PublicationInfo>({ url: "", foundAt: "", platform: "", notes: "" });
  const [attachments, setAttachments] = useState<Attachment[]>([]);

  // Foto objeto del expediente.
  const [subjectId, setSubjectId] = useState<string | null>(null);

  // Integridad.
  const [integrity, setIntegrity] = useState<{ id: string; ok: boolean } | null>(null);

  const refresh = useCallback(async () => {
    try {
      setRecords(await listRecords());
      setStorageError(null);
    } catch (e) {
      setStorageError(e instanceof Error ? e.message : "No se pudo leer el almacenamiento local.");
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function onPickNew(file: File) {
    setRegError(null);
    const v = validate(file);
    if (v) return setRegError(v);
    setBusy("Calculando huellas…");
    try {
      const fp = await fingerprintFile(file);
      setPending({ file, fp });
      setNewName(file.name.replace(/\.[^.]+$/, ""));
    } catch (e) {
      setRegError(e instanceof Error ? e.message : "No se pudo leer la imagen.");
    } finally {
      setBusy(null);
    }
  }

  async function saveNew() {
    if (!pending) return;
    const rec: RegistryRecord = {
      id: crypto.randomUUID(),
      name: newName.trim() || pending.fp.fileName,
      fileName: pending.fp.fileName,
      fileSize: pending.fp.fileSize,
      sha256: pending.fp.sha256,
      phash: pending.fp.phash,
      dhash: pending.fp.dhash,
      thumbnail: pending.fp.thumbnail,
      registeredAt: new Date().toISOString(),
      notes: newNotes.trim(),
    };
    try {
      await putRecord(rec);
      setPending(null);
      setNewName("");
      setNewNotes("");
      await refresh();
    } catch (e) {
      setRegError(e instanceof Error ? e.message : "No se pudo guardar el registro.");
    }
  }

  async function onDelete(id: string) {
    try {
      await deleteRecord(id);
      await refresh();
    } catch {
      setStorageError("No se pudo eliminar el registro.");
    }
  }

  async function onVerifyIntegrity(rec: RegistryRecord, file: File) {
    setBusy("Verificando integridad…");
    try {
      const sha = await sha256OfFile(file);
      setIntegrity({ id: rec.id, ok: sha === rec.sha256 });
    } finally {
      setBusy(null);
    }
  }

  async function onPickSuspect(file: File) {
    setCompareError(null);
    setMatches(null);
    const v = validate(file);
    if (v) return setCompareError(v);
    setBusy("Analizando imagen…");
    try {
      const fp = await fingerprintFile(file);
      setSuspect({ ...fp, file });
      if (records.length) {
        const rows = records
          .map((record) => ({ record, result: compare(record, fp) }))
          .sort((a, b) => rank(a.result) - rank(b.result) || a.result.phashDistance - b.result.phashDistance);
        setMatches(rows);
      } else {
        setMatches([]);
      }
    } catch (e) {
      setCompareError(e instanceof Error ? e.message : "No se pudo leer la imagen.");
    } finally {
      setBusy(null);
    }
  }

  async function onAddAttachment(file: File) {
    if (file.size > MAX_MB * 1024 * 1024) return;
    const [dataUrl, sha256] = await Promise.all([readAsDataUrl(file), sha256OfFile(file)]);
    setAttachments((a) => [...a, { fileName: file.name, fileSize: file.size, sha256, dataUrl }]);
  }

  function download(name: string, mime: string, content: string) {
    const url = URL.createObjectURL(new Blob([content], { type: mime }));
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
    URL.revokeObjectURL(url);
  }

  const best = matches?.find((m) => m.result.verdict !== "none") ?? matches?.[0];
  const hasComparisonMatch = !!(best && best.result.verdict !== "none");

  // Foto objeto del expediente: la elegida, o la de la mejor coincidencia, o la única.
  const subjectRecord =
    records.find((r) => r.id === subjectId) ??
    (hasComparisonMatch ? best!.record : records.length === 1 ? records[0] : null);

  const canGenerate = !!subjectRecord && hasComparisonMatch;

  function generate(kind: "html" | "json") {
    if (!subjectRecord) return;
    const includeComparison = hasComparisonMatch && best!.record.id === subjectRecord.id && !!suspect;
    const dossier = buildDossier({
      registered: subjectRecord,
      suspect: includeComparison
        ? { fileName: suspect!.fileName, fileSize: suspect!.fileSize, sha256: suspect!.sha256, phash: suspect!.phash, dhash: suspect!.dhash, thumbnail: suspect!.thumbnail }
        : undefined,
      comparison: includeComparison ? best!.result : undefined,
      publication: pub,
      attachments,
    });
    if (kind === "html") download(`expediente-${dossier.caseId}.html`, "text/html", dossierToHtml(dossier));
    else download(`expediente-${dossier.caseId}.json`, "application/json", dossierToJson(dossier));
  }

  return (
    <div className="space-y-6">
      {busy && <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-acid">{busy}</p>}
      {storageError && <p className="text-sm text-warn">Almacenamiento local: {storageError} Puedes seguir comparando, pero no se guardará el registro.</p>}

      {/* Paso 1 — Registro */}
      <section className={CARD}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className={LABEL}>1 · Mis fotos registradas ({records.length})</h3>
          <PickButton onPick={onPickNew} className="rounded-full bg-acid px-4 py-2 text-sm font-semibold text-acid-ink transition-transform hover:-translate-y-0.5">
            + Registrar una foto
          </PickButton>
        </div>
        <p className="mt-2 text-xs text-ink-faint">
          Se guardan solo las huellas y una miniatura, nunca la foto completa. Quedan en este navegador; se pueden perder si borras los datos del sitio.
        </p>

        {pending && (
          <div className="mt-4 rounded-xl border border-acid/40 bg-acid-soft p-4">
            <div className="flex gap-4">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={pending.fp.thumbnail} alt="vista previa" className="h-20 w-20 rounded-lg object-cover" />
              <div className="flex-1 space-y-2">
                <input className={INPUT} placeholder="Nombre de referencia" value={newName} onChange={(e) => setNewName(e.target.value)} />
                <input className={INPUT} placeholder="Notas (opcional): dónde se publicó, etc." value={newNotes} onChange={(e) => setNewNotes(e.target.value)} />
              </div>
            </div>
            <div className="mt-3 flex gap-2">
              <button onClick={saveNew} className="rounded-lg bg-acid px-4 py-2 text-sm font-semibold text-acid-ink">Guardar registro</button>
              <button onClick={() => setPending(null)} className="rounded-lg border border-line px-4 py-2 text-sm text-ink-soft">Cancelar</button>
            </div>
          </div>
        )}
        {regError && <p className="mt-3 text-sm text-danger">{regError}</p>}

        {records.length > 0 && (
          <ul className="mt-4 space-y-2">
            {records.map((r) => (
              <li key={r.id} className="flex items-center gap-3 rounded-xl border border-line bg-bg-2 p-3">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={r.thumbnail} alt="" className="h-12 w-12 rounded-md object-cover" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-ink">{r.name}</p>
                  <p className="truncate font-mono text-[10px] text-ink-faint">Registrada {new Date(r.registeredAt).toLocaleString()} · SHA-256 {r.sha256.slice(0, 10)}…</p>
                  {integrity?.id === r.id && (
                    <p className={`text-xs ${integrity.ok ? "text-acid" : "text-danger"}`}>{integrity.ok ? "Integridad OK: el archivo coincide." : "El archivo NO coincide: ha cambiado."}</p>
                  )}
                </div>
                <PickButton onPick={(f) => onVerifyIntegrity(r, f)} className="rounded-md border border-line px-2 py-1 text-xs text-ink-soft hover:border-acid">Verificar archivo</PickButton>
                <button onClick={() => onDelete(r.id)} className="rounded-md border border-line px-2 py-1 text-xs text-ink-soft hover:border-danger hover:text-danger">Eliminar</button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Paso 2 — Comparar (local) */}
      <section className={CARD}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className={LABEL}>2 · Compara con una imagen que encontraste (local)</h3>
          <PickButton onPick={onPickSuspect} className="rounded-full border border-acid/60 px-4 py-2 text-sm font-medium text-acid hover:bg-acid hover:text-acid-ink">
            Importar imagen encontrada
          </PickButton>
        </div>
        {compareError && <p className="mt-3 text-sm text-danger">{compareError}</p>}

        {suspect && matches && (
          <div className="mt-4 space-y-3">
            {matches.length === 0 && <p className="text-sm text-ink-soft">No hay fotos registradas con las que comparar. Registra una arriba.</p>}
            {best && best.result.verdict !== "none" ? (
              <div className="rounded-xl border border-acid/40 bg-acid-soft p-4">
                <p className="text-lg font-bold text-ink">{best.result.label}</p>
                <p className="mt-1 text-sm text-ink-soft">Mejor coincidencia: <strong>{best.record.name}</strong>. {best.result.note}</p>
                <Technical result={best.result} />
              </div>
            ) : matches.length > 0 ? (
              <div className="rounded-xl border border-line bg-bg-2 p-4">
                <p className="text-lg font-bold text-ink">Sin coincidencia detectada</p>
                <p className="mt-1 text-sm text-ink-soft">Ninguna foto registrada se parece a esta con este método.</p>
                {best && <Technical result={best.result} />}
              </div>
            ) : null}
            <p className="text-xs text-ink-faint">
              Una coincidencia indica parecido visual; no prueba por sí sola copia, identidad ni uso ilícito. Recortes fuertes o rotaciones pueden no detectarse.
            </p>
          </div>
        )}
      </section>

      {/* Paso 4 — Publicación */}
      <section className={CARD}>
        <h3 className={LABEL}>3 · Datos de la publicación (los aportas tú)</h3>
        <p className="mt-2 text-xs text-ink-faint">La app no abre ni verifica la URL, la fecha ni el contenido de la página: quedan registrados como declarados por ti.</p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <input className={INPUT} placeholder="URL de la publicación" value={pub.url} onChange={(e) => setPub({ ...pub, url: e.target.value })} />
          <input className={INPUT} placeholder="Plataforma o sitio" value={pub.platform} onChange={(e) => setPub({ ...pub, platform: e.target.value })} />
          <input className={INPUT} placeholder="Cuándo la encontraste (fecha/hora)" value={pub.foundAt} onChange={(e) => setPub({ ...pub, foundAt: e.target.value })} />
          <input className={INPUT} placeholder="Por qué crees que no fue autorizado" value={pub.notes} onChange={(e) => setPub({ ...pub, notes: e.target.value })} />
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <PickButton onPick={onAddAttachment} accept="image/*,.pdf" className="rounded-lg border border-line px-3 py-2 text-sm text-ink-soft hover:border-acid">
            + Adjuntar captura o archivo
          </PickButton>
          {attachments.map((a, i) => (
            <span key={i} className="inline-flex items-center gap-2 rounded-full border border-line bg-bg-2 px-3 py-1 text-xs text-ink-soft">
              {a.fileName}
              <button onClick={() => setAttachments((list) => list.filter((_, j) => j !== i))} className="text-ink-faint hover:text-danger">✕</button>
            </span>
          ))}
        </div>
      </section>

      {/* Paso 5 — Expediente */}
      <section className={CARD}>
        <h3 className={LABEL}>4 · Generar el expediente</h3>
        {records.length > 0 && (
          <label className="mt-3 flex flex-wrap items-center gap-2 text-sm text-ink-soft">
            Expediente sobre la foto:
            <select
              className="rounded-md border border-line bg-bg px-2 py-1 text-ink"
              value={subjectRecord?.id ?? ""}
              onChange={(e) => setSubjectId(e.target.value || null)}
            >
              {records.map((r) => (
                <option key={r.id} value={r.id}>{r.name}</option>
              ))}
            </select>
          </label>
        )}
        <p className="mt-2 text-sm text-ink-soft">
          {canGenerate
            ? "Incluye la foto registrada elegida, las coincidencias de la búsqueda web, la comparación local (si la hay), tus datos de la publicación y los adjuntos."
            : "Para habilitar el expediente: registra una foto y, o bien compárala con otra imagen (paso 3), o bien anota al menos una coincidencia de la búsqueda web (paso 2)."}
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            onClick={() => generate("html")}
            disabled={!canGenerate}
            className="btn-glow rounded-full bg-acid px-5 py-3 text-sm font-semibold text-acid-ink disabled:opacity-40"
          >
            Descargar expediente (HTML imprimible)
          </button>
          <button
            onClick={() => generate("json")}
            disabled={!canGenerate}
            className="rounded-full border border-line px-5 py-3 text-sm text-ink-soft hover:border-acid disabled:opacity-40"
          >
            Descargar datos (JSON)
          </button>
        </div>
        <p className="mt-3 text-xs text-ink-faint">
          El expediente organiza evidencias que tú aportas; no garantiza su admisibilidad legal ni emite conclusiones. Para imprimirlo a PDF, abre el HTML y usa «Imprimir».
        </p>
      </section>
    </div>
  );
}

function rank(r: ComparisonResult): number {
  return { identical: 0, high: 1, possible: 2, none: 3 }[r.verdict];
}

function Technical({ result }: { result: ComparisonResult }) {
  return (
    <details className="mt-2">
      <summary className="cursor-pointer text-xs text-ink-faint hover:text-ink-soft">Detalles técnicos</summary>
      <ul className="mt-1 space-y-0.5 font-mono text-[11px] text-ink-soft">
        <li>Archivos idénticos (SHA-256): {result.sha256Equal ? "sí" : "no"}</li>
        <li>Distancia pHash: {result.phashDistance} / 64 (menor = más parecido)</li>
        <li>Distancia dHash: {result.dhashDistance} / 64</li>
      </ul>
    </details>
  );
}
