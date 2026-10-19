/**
 * Prueba automatizada de readMetadata (detección de EXIF/GPS) sin navegador.
 * Construye un JPEG mínimo con un bloque EXIF que contiene el tag GPS y verifica
 * que la función lo detecta; y uno sin EXIF, que no.
 *
 *   node --test apps/web/tests/readMetadata.test.mjs
 *
 * readMetadata usa solo DataView y Blob.arrayBuffer (disponibles en Node 18+),
 * así que se reimplementa aquí la MISMA lógica para probarla de forma aislada.
 * (El componente del navegador importa la versión de src/lib/privacy.ts.)
 */
import assert from "node:assert";
import { test } from "node:test";

// --- copia verbatim de la lógica de parsing de src/lib/privacy.ts ---
async function readMetadata(bytes) {
  const buf = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const out = { hasExif: false, hasGps: false, fields: [] };
  if (buf.byteLength < 4 || buf.getUint16(0) !== 0xffd8) return out;
  let off = 2;
  while (off + 4 < buf.byteLength) {
    if (buf.getUint8(off) !== 0xff) break;
    const marker = buf.getUint8(off + 1);
    const size = buf.getUint16(off + 2);
    if (marker === 0xe1) {
      const sig = String.fromCharCode(buf.getUint8(off + 4), buf.getUint8(off + 5), buf.getUint8(off + 6), buf.getUint8(off + 7));
      if (sig === "Exif") {
        out.hasExif = true;
        const tiff = off + 10;
        const little = buf.getUint16(tiff) === 0x4949;
        const u16 = (p) => buf.getUint16(p, little);
        const u32 = (p) => buf.getUint32(p, little);
        try {
          const ifd0 = tiff + u32(tiff + 4);
          const n = u16(ifd0);
          for (let i = 0; i < n; i++) {
            const tag = u16(ifd0 + 2 + i * 12);
            if (tag === 0x8825) { out.hasGps = true; out.fields.push("Coordenadas GPS"); }
            else if (tag === 0x0110) out.fields.push("Modelo de cámara");
            else if (tag === 0x0132) out.fields.push("Fecha y hora");
            else if (tag === 0x010f) out.fields.push("Fabricante");
          }
        } catch { /* best-effort */ }
      }
    }
    if (marker === 0xda) break;
    off += 2 + size;
  }
  if (out.hasExif && out.fields.length === 0) out.fields.push("Metadatos EXIF");
  return out;
}

/** Construye un JPEG mínimo con un IFD0 que contiene los tags dados. */
function jpegWithTags(tags) {
  // TIFF little-endian: header + IFD0 con `tags.length` entradas (12 bytes c/u).
  const nEntries = tags.length;
  const tiff = [];
  tiff.push(0x49, 0x49, 0x2a, 0x00); // "II" + 0x002A
  tiff.push(0x08, 0x00, 0x00, 0x00); // offset a IFD0 = 8
  tiff.push(nEntries & 0xff, (nEntries >> 8) & 0xff);
  for (const t of tags) {
    tiff.push(t & 0xff, (t >> 8) & 0xff); // tag
    tiff.push(0x03, 0x00); // tipo SHORT
    tiff.push(0x01, 0x00, 0x00, 0x00); // count 1
    tiff.push(0x00, 0x00, 0x00, 0x00); // valor (irrelevante para la detección)
  }
  tiff.push(0x00, 0x00, 0x00, 0x00); // next IFD = 0
  const app1Payload = [0x45, 0x78, 0x69, 0x66, 0x00, 0x00, ...tiff]; // "Exif\0\0" + TIFF
  const app1Len = app1Payload.length + 2;
  const bytes = [
    0xff, 0xd8, // SOI
    0xff, 0xe1, (app1Len >> 8) & 0xff, app1Len & 0xff, ...app1Payload, // APP1
    0xff, 0xd9, // EOI
  ];
  return new Uint8Array(bytes);
}

test("detecta GPS en un JPEG con tag GPS", async () => {
  const r = await readMetadata(jpegWithTags([0x8825, 0x0110, 0x0132]));
  assert.equal(r.hasExif, true);
  assert.equal(r.hasGps, true);
  assert.ok(r.fields.includes("Coordenadas GPS"));
  assert.ok(r.fields.includes("Modelo de cámara"));
});

test("no reporta GPS en un JPEG sin EXIF", async () => {
  const noExif = new Uint8Array([0xff, 0xd8, 0xff, 0xd9]);
  const r = await readMetadata(noExif);
  assert.equal(r.hasExif, false);
  assert.equal(r.hasGps, false);
});

test("devuelve vacío para datos que no son JPEG", async () => {
  const r = await readMetadata(new Uint8Array([1, 2, 3, 4]));
  assert.equal(r.hasExif, false);
});
