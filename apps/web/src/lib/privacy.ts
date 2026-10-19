/**
 * Privacidad antes de publicar — procesamiento 100% LOCAL en el navegador.
 *
 * Todas estas funciones trabajan sobre un <canvas>. La imagen NUNCA se envía a
 * ningún servidor. Al redibujar en un canvas y exportar, los metadatos del
 * archivo original (EXIF, GPS, fecha, modelo de cámara) NO se copian: el canvas
 * solo contiene los píxeles, así que la exportación queda sin metadatos.
 *
 * Importante y honesto: quitar metadatos NO anonimiza la imagen. El contenido
 * visual (una cara, un documento, un lugar) puede seguir revelando identidad o
 * ubicación. Por eso se ofrecen además redacción (difuminar/cubrir), recorte y
 * redimensionado, y la detección se presenta como "posibles riesgos", no como
 * garantía.
 */

export type Box = { x: number; y: number; w: number; h: number };
export type RedactMode = "blur" | "pixelate" | "solid";
export type Redaction = Box & { mode: RedactMode };

export type MetadataSummary = {
  hasExif: boolean;
  hasGps: boolean;
  fields: string[]; // etiquetas legibles de lo que se detectó
};

export type ExportOptions = {
  crop?: Box; // en píxeles de la imagen original
  maxSide?: number; // limita la resolución (lado mayor)
  redactions?: Redaction[]; // en coordenadas de la imagen (antes de recorte)
  format?: "image/jpeg" | "image/png";
  quality?: number; // 0..1 para JPEG
};

// Límite de área de trabajo (~40 MP): por encima, se reduce para no agotar la
// memoria del canvas con fotos enormes. El canvas de los navegadores también
// tiene un tope de dimensiones, así que esto protege el flujo.
export const MAX_WORK_AREA = 40_000_000;

export async function loadImage(file: Blob): Promise<HTMLImageElement> {
  const url = URL.createObjectURL(file);
  const img = new Image();
  img.decoding = "async";
  // Respeta la orientación EXIF (una foto de móvil no debe salir girada).
  (img as HTMLImageElement & { imageOrientation?: string }).imageOrientation = "from-image";
  img.src = url;
  try {
    await img.decode();
  } catch {
    URL.revokeObjectURL(url);
    throw new Error(
      "No se pudo leer la imagen. Puede estar dañada o en un formato que el navegador no abre (por ejemplo HEIC de iPhone). Prueba con JPEG, PNG o WebP.",
    );
  }
  // El bitmap ya está en memoria; se revoca la URL de forma segura.
  URL.revokeObjectURL(url);
  if (!img.naturalWidth || !img.naturalHeight) {
    throw new Error("La imagen no tiene dimensiones válidas.");
  }
  return img;
}

/**
 * Lector mínimo de EXIF para JPEG, solo para INFORMAR al usuario de qué
 * contiene su archivo (no para editarlo). Detecta el bloque EXIF (APP1) y la
 * presencia del IFD de GPS y de algunas etiquetas comunes. No es un parser
 * completo; si falla, informa que no pudo analizarse.
 */
export async function readMetadata(file: Blob): Promise<MetadataSummary> {
  const buf = new DataView(await file.arrayBuffer());
  const out: MetadataSummary = { hasExif: false, hasGps: false, fields: [] };
  if (buf.byteLength < 4 || buf.getUint16(0) !== 0xffd8) return out; // no es JPEG

  let off = 2;
  while (off + 4 < buf.byteLength) {
    if (buf.getUint8(off) !== 0xff) break;
    const marker = buf.getUint8(off + 1);
    const size = buf.getUint16(off + 2);
    if (marker === 0xe1) {
      // APP1: ¿es "Exif\0\0"?
      const sig = String.fromCharCode(buf.getUint8(off + 4), buf.getUint8(off + 5), buf.getUint8(off + 6), buf.getUint8(off + 7));
      if (sig === "Exif") {
        out.hasExif = true;
        const tiff = off + 10;
        const little = buf.getUint16(tiff) === 0x4949;
        const u16 = (p: number) => buf.getUint16(p, little);
        const u32 = (p: number) => buf.getUint32(p, little);
        try {
          const ifd0 = tiff + u32(tiff + 4);
          const n = u16(ifd0);
          for (let i = 0; i < n; i++) {
            const tag = u16(ifd0 + 2 + i * 12);
            if (tag === 0x8825) {
              out.hasGps = true;
              out.fields.push("Coordenadas GPS");
            } else if (tag === 0x0110) out.fields.push("Modelo de cámara");
            else if (tag === 0x0132) out.fields.push("Fecha y hora");
            else if (tag === 0x010f) out.fields.push("Fabricante");
          }
        } catch {
          /* parser best-effort */
        }
      }
    }
    if (marker === 0xda) break; // inicio de los datos de imagen
    off += 2 + size;
  }
  if (out.hasExif && out.fields.length === 0) out.fields.push("Metadatos EXIF");
  return out;
}

/** Detección de rostros con la API del navegador, si existe. Best-effort. */
export async function detectFaces(img: HTMLImageElement): Promise<{ supported: boolean; boxes: Box[] }> {
  const Detector = (globalThis as unknown as { FaceDetector?: new (o?: object) => { detect: (i: unknown) => Promise<{ boundingBox: DOMRectReadOnly }[]> } }).FaceDetector;
  if (!Detector) return { supported: false, boxes: [] };
  try {
    const det = new Detector({ fastMode: true, maxDetectedFaces: 20 });
    const res = await det.detect(img);
    return {
      supported: true,
      boxes: res.map((r) => ({ x: r.boundingBox.x, y: r.boundingBox.y, w: r.boundingBox.width, h: r.boundingBox.height })),
    };
  } catch {
    return { supported: false, boxes: [] };
  }
}

function drawRedaction(ctx: CanvasRenderingContext2D, source: CanvasImageSource, r: Redaction, scale: number, offX: number, offY: number) {
  // Coordenadas de imagen -> coordenadas de canvas (tras recorte y escala).
  const x = (r.x - offX) * scale;
  const y = (r.y - offY) * scale;
  const w = r.w * scale;
  const h = r.h * scale;
  if (w <= 0 || h <= 0) return;
  if (r.mode === "solid") {
    ctx.fillStyle = "#000";
    ctx.fillRect(x, y, w, h);
    return;
  }
  // blur y pixelate: reescalan la región a baja resolución y la devuelven.
  const factor = r.mode === "pixelate" ? 0.06 : 0.12;
  const tw = Math.max(1, Math.round(w * factor));
  const th = Math.max(1, Math.round(h * factor));
  const tmp = document.createElement("canvas");
  tmp.width = tw;
  tmp.height = th;
  const tctx = tmp.getContext("2d")!;
  tctx.imageSmoothingEnabled = r.mode === "blur";
  tctx.drawImage(ctx.canvas, x, y, w, h, 0, 0, tw, th);
  ctx.imageSmoothingEnabled = r.mode === "blur";
  ctx.drawImage(tmp, 0, 0, tw, th, x, y, w, h);
  void source;
}

/**
 * Procesa la imagen (recorte, redimensionado y redacciones) y devuelve el
 * canvas resultante, SIN metadatos. El original no se toca.
 */
export function render(img: HTMLImageElement, opts: ExportOptions): HTMLCanvasElement {
  const crop = opts.crop ?? { x: 0, y: 0, w: img.naturalWidth, h: img.naturalHeight };
  let scale = 1;
  if (opts.maxSide && Math.max(crop.w, crop.h) > opts.maxSide) {
    scale = opts.maxSide / Math.max(crop.w, crop.h);
  } else if (crop.w * crop.h > MAX_WORK_AREA) {
    // Reduce automáticamente las fotos enormes para no bloquear el navegador.
    scale = Math.sqrt(MAX_WORK_AREA / (crop.w * crop.h));
  }
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(crop.w * scale));
  canvas.height = Math.max(1, Math.round(crop.h * scale));
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Tu navegador no permite procesar la imagen (canvas no disponible).");
  ctx.drawImage(img, crop.x, crop.y, crop.w, crop.h, 0, 0, canvas.width, canvas.height);
  for (const r of opts.redactions ?? []) drawRedaction(ctx, img, r, scale, crop.x, crop.y);
  return canvas;
}

export function canvasToBlob(canvas: HTMLCanvasElement, format: "image/jpeg" | "image/png", quality = 0.92): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("No se pudo exportar la imagen"))), format, quality);
  });
}

/** Procesa y exporta en un solo paso. Devuelve un Blob sin metadatos. */
export async function exportProtected(img: HTMLImageElement, opts: ExportOptions): Promise<Blob> {
  const canvas = render(img, opts);
  const blob = await canvasToBlob(canvas, opts.format ?? "image/jpeg", opts.quality ?? 0.92);
  // Verificación defensiva: el blob exportado no debe conservar EXIF.
  const check = await readMetadata(blob);
  if (check.hasExif) throw new Error("La exportación no eliminó los metadatos; no se descarga el archivo.");
  return blob;
}
