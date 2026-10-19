/**
 * Adaptador de navegador para el detector de reutilización. Decodifica la
 * imagen con <canvas> y produce las huellas que consume reuse.ts.
 *
 * Reutiliza loadImage() del flujo de privacidad (maneja orientación EXIF,
 * HEIC/corruptas) para no duplicar lógica. Todo es local: sin llamadas de red.
 */

import { loadImage } from "./privacy";
import { dhashFromGray9x8, phashFromGray32, sha256Hex, type PerceptualHashes } from "./reuse";

export type Fingerprint = PerceptualHashes & {
  sha256: string;
  thumbnail: string;
  fileName: string;
  fileSize: number;
};

/** Matriz de luminancia w×h (row-major, 0..255) reescalando con suavizado. */
function grayMatrix(img: HTMLImageElement, w: number, h: number): number[] {
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Tu navegador no permite procesar la imagen (canvas no disponible).");
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(img, 0, 0, w, h);
  const { data } = ctx.getImageData(0, 0, w, h);
  const out = new Array<number>(w * h);
  for (let i = 0; i < w * h; i++) {
    const r = data[i * 4], g = data[i * 4 + 1], b = data[i * 4 + 2];
    out[i] = 0.299 * r + 0.587 * g + 0.114 * b;
  }
  return out;
}

/** Miniatura JPEG pequeña (solo para vista previa local), como data URL. */
function thumbnail(img: HTMLImageElement, maxSide = 140): string {
  const scale = Math.min(1, maxSide / Math.max(img.naturalWidth, img.naturalHeight));
  const w = Math.max(1, Math.round(img.naturalWidth * scale));
  const h = Math.max(1, Math.round(img.naturalHeight * scale));
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) return "";
  ctx.drawImage(img, 0, 0, w, h);
  return canvas.toDataURL("image/jpeg", 0.6);
}

/** Calcula SHA-256, pHash, dHash y miniatura de un archivo de imagen. */
export async function fingerprintFile(file: Blob & { name?: string }): Promise<Fingerprint> {
  const bytes = await file.arrayBuffer();
  const sha256 = await sha256Hex(bytes);
  const img = await loadImage(file); // lanza mensajes claros si está dañada o es HEIC
  return {
    sha256,
    phash: phashFromGray32(grayMatrix(img, 32, 32)),
    dhash: dhashFromGray9x8(grayMatrix(img, 9, 8)),
    thumbnail: thumbnail(img),
    fileName: file.name ?? "imagen",
    fileSize: file.size,
  };
}

/** Recalcula solo el SHA-256 de un archivo (para verificar integridad). */
export async function sha256OfFile(file: Blob): Promise<string> {
  return sha256Hex(await file.arrayBuffer());
}

/** Lee un archivo (p. ej. una captura) como data URL para adjuntarlo. */
export function readAsDataUrl(file: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(new Error("No se pudo leer el archivo adjunto."));
    reader.readAsDataURL(file);
  });
}
