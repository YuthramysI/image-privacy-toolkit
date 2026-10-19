/**
 * Detector de reutilización de imágenes y expediente de evidencias.
 * NÚCLEO PURO (sin DOM): hashing, comparación y armado del expediente.
 *
 * Todo el procesamiento es LOCAL. Este módulo no hace ninguna llamada de red.
 * El adaptador de navegador (reuseImage.ts) decodifica la imagen con <canvas>
 * y produce las matrices en gris que estas funciones consumen.
 *
 * Honestidad: una coincidencia perceptual indica que dos imágenes se PARECEN
 * mucho; no demuestra copia, titularidad, identidad ni uso ilícito. Las fechas
 * que registra la app son fechas *declaradas o registradas por la aplicación*,
 * no una prueba independiente de cuándo existió una foto.
 */

// ---------------------------------------------------------------------------
// Tipos
// ---------------------------------------------------------------------------

export type PerceptualHashes = {
  phash: string; // 64 bits en hex (16 chars) — DCT, robusto a recompresión/escala
  dhash: string; // 64 bits en hex — gradiente horizontal, robusto a brillo/escala
};

export type RegistryRecord = PerceptualHashes & {
  id: string;
  name: string; // nombre de referencia que elige la persona
  fileName: string;
  fileSize: number;
  sha256: string;
  thumbnail: string; // data URL pequeña, solo para vista previa local
  registeredAt: string; // ISO; fecha REGISTRADA POR LA APP, no prueba independiente
  notes: string;
};

export type SuspectImage = PerceptualHashes & {
  fileName: string;
  fileSize: number;
  sha256: string;
  thumbnail: string;
};

export type Verdict = "identical" | "high" | "possible" | "none";

export type ComparisonResult = {
  verdict: Verdict;
  label: string;
  sha256Equal: boolean;
  phashDistance: number; // 0..64 (menor = más parecido)
  dhashDistance: number;
  note: string;
};

export type PublicationInfo = {
  url: string;
  foundAt: string; // texto libre: fecha/hora que DECLARA la persona
  platform: string;
  notes: string;
};

export type Attachment = {
  fileName: string;
  fileSize: number;
  sha256: string;
  dataUrl: string; // captura/archivo aportado por la persona
};

export type Dossier = {
  caseId: string;
  generatedAt: string; // fecha de generación del informe (registrada por la app)
  registered: RegistryRecord; // la foto objeto del caso
  suspect?: SuspectImage; // comparación local opcional
  comparison?: ComparisonResult; // comparación local opcional
  publication: PublicationInfo;
  attachments: Attachment[];
};

// ---------------------------------------------------------------------------
// Umbrales de similitud (calibrados; ver docs/EVIDENCIAS.md)
// No son una prueba absoluta: acompañan siempre a la distancia numérica.
// ---------------------------------------------------------------------------

export const PHASH_HIGH = 10; // ≤ ⇒ similitud alta
export const PHASH_POSSIBLE = 18; // ≤ ⇒ posible similitud (revisar)
export const DHASH_HIGH = 12;

// ---------------------------------------------------------------------------
// Hashing
// ---------------------------------------------------------------------------

/** SHA-256 en hex de un buffer de bytes. Usa Web Crypto (navegador y Node 20+). */
export async function sha256Hex(bytes: ArrayBuffer | Uint8Array): Promise<string> {
  const u8 = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  const buf = u8.buffer.slice(u8.byteOffset, u8.byteOffset + u8.byteLength) as ArrayBuffer;
  const digest = await crypto.subtle.digest("SHA-256", buf);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** Empaqueta 64 bits (MSB primero) en 16 caracteres hex, en dos mitades de 32. */
export function bitsToHex(bits: number[]): string {
  let hi = 0;
  let lo = 0;
  for (let i = 0; i < 32; i++) hi = ((hi << 1) | (bits[i] ? 1 : 0)) >>> 0;
  for (let i = 32; i < 64; i++) lo = ((lo << 1) | (bits[i] ? 1 : 0)) >>> 0;
  return hi.toString(16).padStart(8, "0") + lo.toString(16).padStart(8, "0");
}

function popcount(n: number): number {
  n = n - ((n >>> 1) & 0x55555555);
  n = (n & 0x33333333) + ((n >>> 2) & 0x33333333);
  return (((n + (n >>> 4)) & 0x0f0f0f0f) * 0x01010101) >>> 24;
}

/** Distancia de Hamming entre dos hashes hex de 64 bits (0..64). */
export function hamming(a: string, b: string): number {
  const ah = parseInt(a.slice(0, 8), 16), al = parseInt(a.slice(8, 16), 16);
  const bh = parseInt(b.slice(0, 8), 16), bl = parseInt(b.slice(8, 16), 16);
  return popcount((ah ^ bh) >>> 0) + popcount((al ^ bl) >>> 0);
}

/** DCT-II 1D (ingenua, suficiente para N=32). */
function dct1d(input: Float64Array): Float64Array {
  const N = input.length;
  const out = new Float64Array(N);
  for (let k = 0; k < N; k++) {
    let sum = 0;
    for (let n = 0; n < N; n++) sum += input[n] * Math.cos((Math.PI / N) * (n + 0.5) * k);
    out[k] = sum;
  }
  return out;
}

/**
 * pHash: matriz de gris 32×32 (row-major) → DCT 2D → bloque 8×8 de baja
 * frecuencia → bit = coeficiente > mediana. Robusto a escala y recompresión.
 */
export function phashFromGray32(gray: ArrayLike<number>): string {
  const N = 32;
  const rows: Float64Array[] = [];
  for (let y = 0; y < N; y++) {
    const row = new Float64Array(N);
    for (let x = 0; x < N; x++) row[x] = gray[y * N + x];
    rows.push(dct1d(row));
  }
  // DCT por columnas.
  const cols: Float64Array[] = [];
  for (let x = 0; x < N; x++) {
    const col = new Float64Array(N);
    for (let y = 0; y < N; y++) col[y] = rows[y][x];
    cols.push(dct1d(col));
  }
  // Bloque 8×8 de baja frecuencia: coef[u][v] = cols[u][v].
  const low: number[] = [];
  for (let u = 0; u < 8; u++) for (let v = 0; v < 8; v++) low.push(cols[u][v]);
  const sorted = [...low].sort((p, q) => p - q);
  const median = (sorted[31] + sorted[32]) / 2;
  return bitsToHex(low.map((c) => (c > median ? 1 : 0)));
}

/**
 * dHash: matriz de gris 9×8 (ancho 9, alto 8, row-major) → por fila, bit =
 * píxel izquierdo > derecho. 64 bits. Robusto a brillo y escala.
 */
export function dhashFromGray9x8(gray: ArrayLike<number>): string {
  const W = 9;
  const bits: number[] = [];
  for (let y = 0; y < 8; y++) for (let x = 0; x < 8; x++) bits.push(gray[y * W + x] > gray[y * W + x + 1] ? 1 : 0);
  return bitsToHex(bits);
}

// ---------------------------------------------------------------------------
// Comparación
// ---------------------------------------------------------------------------

export function compare(a: PerceptualHashes & { sha256: string }, b: PerceptualHashes & { sha256: string }): ComparisonResult {
  const sha256Equal = a.sha256 === b.sha256;
  const phashDistance = hamming(a.phash, b.phash);
  const dhashDistance = hamming(a.dhash, b.dhash);

  if (sha256Equal) {
    return {
      verdict: "identical",
      label: "Archivo idéntico",
      sha256Equal,
      phashDistance,
      dhashDistance,
      note: "Los dos archivos son idénticos byte a byte (mismo SHA-256).",
    };
  }
  if (phashDistance <= PHASH_HIGH && dhashDistance <= DHASH_HIGH) {
    return {
      verdict: "high",
      label: "Similitud visual alta",
      sha256Equal,
      phashDistance,
      dhashDistance,
      note: "Las imágenes se parecen mucho (compatible con reescalado o recompresión). No es prueba de copia por sí sola.",
    };
  }
  if (phashDistance <= PHASH_POSSIBLE) {
    return {
      verdict: "possible",
      label: "Posible similitud visual (revisar)",
      sha256Equal,
      phashDistance,
      dhashDistance,
      note: "Hay cierta semejanza. Revísala a ojo: podría ser la misma imagen modificada o dos imágenes parecidas.",
    };
  }
  return {
    verdict: "none",
    label: "Sin coincidencia detectada",
    sha256Equal,
    phashDistance,
    dhashDistance,
    note: "No se detectó similitud con este método. No descarta un recorte fuerte u otra edición que estos hashes no capturan.",
  };
}

// ---------------------------------------------------------------------------
// Expediente
// ---------------------------------------------------------------------------

export const LIMITATIONS = [
  "Una coincidencia indica parecido visual; NO demuestra por sí sola copia, titularidad, identidad ni uso ilícito.",
  "Las fechas de registro y de generación las anota esta aplicación; no son una prueba independiente de cuándo existió una foto ni de quién la creó.",
  "El SHA-256 verifica la integridad de los archivos disponibles (si cambiaron o no), no cuándo existían ni quién los posee.",
  "La comparación se limita a las imágenes que tú aportas: no es un buscador de Internet.",
  "La app no verificó automáticamente la URL, la fecha ni el contenido de la publicación: esos datos los declaras tú.",
  "El método detecta bien reescalado y recompresión; recortes fuertes, rotaciones o ediciones grandes pueden no detectarse.",
  "Este expediente organiza evidencias, pero no garantiza su admisibilidad legal.",
];

export const NEXT_STEPS = [
  "Guarda los archivos originales sin modificarlos (no los edites ni los renombres).",
  "Anota cómo y cuándo encontraste la publicación, con la URL completa.",
  "Haz capturas que muestren la URL y la fecha visibles en la página.",
  "Consulta el procedimiento de reporte de la plataforma donde apareció la imagen.",
  "Si procede, busca orientación de una persona con conocimientos legales en tu jurisdicción.",
];

/** Escapa texto para insertarlo en HTML de forma segura. */
export function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
}

export function buildDossier(params: Omit<Dossier, "caseId" | "generatedAt"> & { caseId?: string; generatedAt?: string }): Dossier {
  return {
    caseId: params.caseId ?? `IPT-${Date.now().toString(36).toUpperCase()}`,
    generatedAt: params.generatedAt ?? new Date().toISOString(),
    registered: params.registered,
    suspect: params.suspect,
    comparison: params.comparison,
    publication: params.publication,
    attachments: params.attachments,
  };
}

/** Quita los campos de imagen pesados (miniaturas, data URLs) de un objeto. */
function stripMedia<T extends Record<string, unknown>>(o: T): Omit<T, "thumbnail" | "dataUrl"> {
  const c: Record<string, unknown> = { ...o };
  delete c.thumbnail;
  delete c.dataUrl;
  return c as Omit<T, "thumbnail" | "dataUrl">;
}

/** Versión estructurada en JSON (sin los data URLs de imagen, que pesan). */
export function dossierToJson(d: Dossier): string {
  return JSON.stringify(
    {
      caseId: d.caseId,
      generatedAt: d.generatedAt,
      generatedBy: "Image Privacy Toolkit — comparación local y expediente",
      registered: stripMedia(d.registered),
      suspect: d.suspect ? stripMedia(d.suspect) : null,
      comparison: d.comparison ?? null,
      publication: d.publication,
      attachments: d.attachments.map((a) => stripMedia(a)),
      limitations: LIMITATIONS,
      nextSteps: NEXT_STEPS,
    },
    null,
    2,
  );
}

/** Expediente en HTML autocontenido e imprimible (las imágenes van embebidas). */
export function dossierToHtml(d: Dossier): string {
  const row = (k: string, v: string) => `<tr><th>${escapeHtml(k)}</th><td>${v}</td></tr>`;
  const mono = (s: string) => `<code>${escapeHtml(s)}</code>`;
  const declared = `<span class="tag declared">declarado por el usuario</span>`;
  const computed = `<span class="tag computed">calculado por la app</span>`;

  const attachmentsHtml = d.attachments.length
    ? d.attachments
        .map(
          (a) => `<figure><img src="${a.dataUrl}" alt="${escapeHtml(a.fileName)}"/>
      <figcaption>${escapeHtml(a.fileName)} · ${(a.fileSize / 1024).toFixed(0)} KB<br/>SHA-256 ${computed}: ${mono(a.sha256)}</figcaption></figure>`,
        )
        .join("\n")
    : "<p>Sin archivos adjuntos.</p>";

  const comparisonHtml = d.comparison
    ? `<h2>Comparación local con una imagen</h2>
<p><span class="verdict">${escapeHtml(d.comparison.label)}</span></p>
<table>
  ${row("Método", "SHA-256 (idéntico byte a byte) + hash perceptual pHash/dHash (distancia de Hamming)")}
  ${row("Archivos idénticos (SHA-256)", d.comparison.sha256Equal ? "Sí" : "No")}
  ${row("Distancia pHash", `${d.comparison.phashDistance} / 64 (menor = más parecido)`)}
  ${row("Distancia dHash", `${d.comparison.dhashDistance} / 64`)}
  ${row("Lectura", escapeHtml(d.comparison.note))}
</table>`
    : "";

  const suspectHtml = d.suspect
    ? `<h2>Imagen comparada</h2>
<figure><img src="${d.suspect.thumbnail}" alt="miniatura"/><figcaption>vista previa (miniatura local)</figcaption></figure>
<table>
  ${row("Archivo", `${escapeHtml(d.suspect.fileName)} · ${(d.suspect.fileSize / 1024).toFixed(0)} KB`)}
  ${row("SHA-256 " + computed, mono(d.suspect.sha256))}
  ${row("pHash / dHash " + computed, mono(d.suspect.phash) + " / " + mono(d.suspect.dhash))}
</table>`
    : "";

  const privacyNote = `<p>Todo el análisis (huellas y comparación) se hizo en tu dispositivo.</p>`;

  return `<!doctype html>
<html lang="es"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Expediente ${escapeHtml(d.caseId)}</title>
<style>
  :root { color-scheme: light; }
  body { font: 15px/1.5 system-ui, sans-serif; color: #141414; max-width: 820px; margin: 2rem auto; padding: 0 1rem; }
  h1 { font-size: 1.5rem; margin-bottom: .2rem; }
  h2 { font-size: 1.05rem; margin: 1.6rem 0 .5rem; border-bottom: 2px solid #111; padding-bottom: .2rem; }
  table { border-collapse: collapse; width: 100%; margin: .4rem 0; }
  th, td { border: 1px solid #ccc; padding: .4rem .6rem; text-align: left; vertical-align: top; }
  th { width: 34%; background: #f4f4f4; font-weight: 600; }
  code { font: 12px ui-monospace, monospace; word-break: break-all; }
  .tag { font-size: 11px; padding: 1px 6px; border-radius: 10px; white-space: nowrap; }
  .declared { background: #fff3d6; border: 1px solid #e0b64d; }
  .computed { background: #e4f0ff; border: 1px solid #6ba3e8; }
  .verdict { font-size: 1.1rem; font-weight: 700; padding: .5rem .8rem; border-radius: 8px; background: #f0f0f0; display: inline-block; }
  figure { display: inline-block; margin: .4rem .6rem .4rem 0; vertical-align: top; max-width: 240px; }
  figure img { max-width: 240px; max-height: 240px; border: 1px solid #bbb; display: block; }
  figcaption { font-size: 12px; color: #444; margin-top: .2rem; }
  ul { margin: .3rem 0 .3rem 1.1rem; padding: 0; }
  .warn { background: #fff6f5; border: 1px solid #e8a79f; padding: .6rem .8rem; border-radius: 8px; }
  footer { margin-top: 2rem; font-size: 12px; color: #666; border-top: 1px solid #ccc; padding-top: .6rem; }
  @media print { body { margin: 0; } h2 { break-after: avoid; } figure { break-inside: avoid; } }
</style></head><body>

<h1>Expediente de evidencias</h1>
<p><strong>Caso:</strong> ${mono(d.caseId)} · <strong>Generado:</strong> ${escapeHtml(d.generatedAt)} ${computed}</p>
${privacyNote}

<h2>Imagen registrada (objeto del caso)</h2>
<figure><img src="${d.registered.thumbnail}" alt="miniatura"/><figcaption>vista previa (miniatura local)</figcaption></figure>
<table>
  ${row("Nombre de referencia", escapeHtml(d.registered.name))}
  ${row("Archivo", `${escapeHtml(d.registered.fileName)} · ${(d.registered.fileSize / 1024).toFixed(0)} KB`)}
  ${row("SHA-256 " + computed, mono(d.registered.sha256))}
  ${row("pHash / dHash " + computed, mono(d.registered.phash) + " / " + mono(d.registered.dhash))}
  ${row("Registrada el " + computed, escapeHtml(d.registered.registeredAt) + " — fecha anotada por la app, no prueba independiente")}
  ${row("Notas " + declared, escapeHtml(d.registered.notes) || "—")}
</table>

${comparisonHtml}

${suspectHtml}

<h2>Publicación sospechosa (datos aportados por ti)</h2>
<table>
  ${row("URL " + declared, escapeHtml(d.publication.url) || "—")}
  ${row("Encontrada el " + declared, escapeHtml(d.publication.foundAt) || "—")}
  ${row("Plataforma " + declared, escapeHtml(d.publication.platform) || "—")}
  ${row("Por qué se considera no autorizado " + declared, escapeHtml(d.publication.notes) || "—")}
</table>
<p><em>La app no abrió ni verificó la URL, la fecha ni el contenido de la página.</em></p>

<h2>Archivos adjuntos</h2>
${attachmentsHtml}

<h2>Advertencias y limitaciones</h2>
<div class="warn"><ul>${LIMITATIONS.map((l) => `<li>${escapeHtml(l)}</li>`).join("")}</ul></div>

<h2>Pasos sugeridos para documentar el caso</h2>
<ul>${NEXT_STEPS.map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ul>

<footer>Image Privacy Toolkit organiza evidencias que tú aportas; no emite conclusiones legales. Verifica la integridad recalculando el SHA-256 de cada archivo.</footer>
</body></html>`;
}
