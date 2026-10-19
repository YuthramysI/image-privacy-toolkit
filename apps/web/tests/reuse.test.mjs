/**
 * Pruebas del núcleo del detector de reutilización (reuse.ts), importando el
 * código real con el *type stripping* de Node.
 *
 *   node --experimental-strip-types --test tests/reuse.test.mjs
 *
 * Cubre: SHA-256 exacto, robustez del hash perceptual ante reescalado+ruido,
 * ausencia de falsos positivos entre imágenes distintas, veredictos de
 * comparación, generación/validación del expediente (y escape de HTML),
 * recalculado de integridad y ausencia de red en el código fuente.
 */
import assert from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

const R = await import("../src/lib/reuse.ts");

// --- imagen sintética realista (espectro 1/f, como una foto) --------------
// Ruido de valor multi-octava: a diferencia de unos pocos senos, llena el
// espectro de baja frecuencia, así que el pHash se comporta como con fotos
// reales (estable ante recompresión, discriminativo entre imágenes distintas).
function hash2(x, y, s) {
  let n = (x * 374761393 + y * 668265263 + s * 362437) | 0;
  n = (n ^ (n >>> 13)) * 1274126177;
  return ((n ^ (n >>> 16)) >>> 0) / 4294967295;
}
function valueNoise(u, v, f, s) {
  const gx = u * f, gy = v * f, ix = Math.floor(gx), iy = Math.floor(gy), fx = gx - ix, fy = gy - iy;
  const a = hash2(ix, iy, s), b = hash2(ix + 1, iy, s), c = hash2(ix, iy + 1, s), d = hash2(ix + 1, iy + 1, s);
  const sx = fx * fx * (3 - 2 * fx), sy = fy * fy * (3 - 2 * fy);
  return (a * (1 - sx) + b * sx) * (1 - sy) + (c * (1 - sx) + d * sx) * sy;
}
/** Devuelve una función de imagen (u,v)->0..255 de banda ancha, por semilla. */
function mkImage(seed) {
  return (u, v) => {
    let val = 0, amp = 1, f = 2;
    for (let o = 0; o < 5; o++) {
      val += amp * (valueNoise(u, v, f, seed + o) - 0.5);
      amp *= 0.55;
      f *= 2;
    }
    return 128 + 170 * val;
  };
}

// Muestrea una imagen a una matriz w×h promediando por celda (como el suavizado
// del reescalado). El ruido se añade POR SUBMUESTRA y el promediado lo atenúa,
// igual que una recompresión JPEG seguida de reescalado.
function sampleWH(fn, w, h, { noise = 0, shiftX = 0, shiftY = 0, ss = 6, seed = 1 } = {}) {
  let s = seed;
  const rnd = () => ((s = (s * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff) * 2 - 1;
  const out = new Array(w * h);
  for (let y = 0; y < h; y++)
    for (let x = 0; x < w; x++) {
      let acc = 0;
      for (let sy = 0; sy < ss; sy++)
        for (let sx = 0; sx < ss; sx++) acc += fn((x + (sx + 0.5) / ss) / w + shiftX, (y + (sy + 0.5) / ss) / h + shiftY) + noise * rnd();
      out[y * w + x] = Math.max(0, Math.min(255, acc / (ss * ss)));
    }
  return out;
}
const sample = (fn, N, opts) => sampleWH(fn, N, N, opts);

// --- SHA-256 ---------------------------------------------------------------
test("SHA-256: idéntico para los mismos bytes, distinto para otros", async () => {
  const a = await R.sha256Hex(new TextEncoder().encode("imagen-de-prueba"));
  const b = await R.sha256Hex(new TextEncoder().encode("imagen-de-prueba"));
  const c = await R.sha256Hex(new TextEncoder().encode("imagen-de-prueba!"));
  assert.equal(a, b);
  assert.notEqual(a, c);
  assert.equal(a.length, 64);
});

test("recalculado de integridad: detecta un byte cambiado", async () => {
  const orig = new Uint8Array([1, 2, 3, 4, 5]);
  const same = await R.sha256Hex(orig.slice());
  const changed = await R.sha256Hex(Uint8Array.from([1, 2, 3, 4, 6]));
  assert.equal(await R.sha256Hex(orig), same, "mismos bytes → misma huella (integridad OK)");
  assert.notEqual(same, changed, "un byte distinto → huella distinta (integridad rota)");
});

// --- hamming / bits --------------------------------------------------------
test("hamming y bitsToHex", () => {
  assert.equal(R.hamming("ffffffffffffffff", "0000000000000000"), 64);
  assert.equal(R.hamming("ffffffffffffffff", "fffffffffffffffe"), 1);
  assert.equal(R.hamming("abcdef0123456789", "abcdef0123456789"), 0);
  assert.equal(R.bitsToHex(Array(64).fill(0)), "0000000000000000");
});

// --- robustez perceptual (reescalado + recompresión simulados) ------------
test("pHash estable ante ruido (proxy de recompresión)", () => {
  const img = mkImage(100);
  const base = R.phashFromGray32(sample(img, 32));
  const noisy = R.phashFromGray32(sample(img, 32, { noise: 14, seed: 7 }));
  const d = R.hamming(base, noisy);
  assert.ok(d <= R.PHASH_HIGH, `distancia con ruido ${d} debería ser ≤ ${R.PHASH_HIGH}`);
});

test("pHash estable ante desplazamiento sub-celda (proxy de reescalado)", () => {
  const img = mkImage(100);
  const base = R.phashFromGray32(sample(img, 32));
  const shifted = R.phashFromGray32(sample(img, 32, { shiftX: 0.004, shiftY: -0.003, seed: 3 }));
  const d = R.hamming(base, shifted);
  assert.ok(d <= R.PHASH_POSSIBLE, `distancia con desplazamiento ${d} debería ser ≤ ${R.PHASH_POSSIBLE}`);
});

test("dHash estable ante ruido leve", () => {
  const img = mkImage(100);
  const base = R.dhashFromGray9x8(sampleWH(img, 9, 8));
  const noisy = R.dhashFromGray9x8(sampleWH(img, 9, 8, { noise: 8, seed: 11 }));
  const d = R.hamming(base, noisy);
  assert.ok(d <= R.DHASH_HIGH, `distancia dHash con ruido ${d} debería ser ≤ ${R.DHASH_HIGH}`);
});

// --- ausencia de falsos positivos -----------------------------------------
test("imágenes distintas → distancia pHash grande (sin falsos positivos)", () => {
  const hashes = [];
  for (let i = 0; i < 6; i++) hashes.push(R.phashFromGray32(sample(mkImage(200 + i * 17), 32, { seed: i + 1 })));
  let min = 64;
  for (let i = 0; i < hashes.length; i++)
    for (let j = i + 1; j < hashes.length; j++) min = Math.min(min, R.hamming(hashes[i], hashes[j]));
  assert.ok(min > R.PHASH_POSSIBLE, `la distancia mínima entre imágenes distintas ${min} debería superar ${R.PHASH_POSSIBLE}`);
});

// --- veredictos ------------------------------------------------------------
test("compare(): archivo idéntico por SHA-256", () => {
  const h = { sha256: "aa", phash: "ffffffffffffffff", dhash: "ffffffffffffffff" };
  const r = R.compare(h, { ...h });
  assert.equal(r.verdict, "identical");
  assert.equal(r.sha256Equal, true);
});

test("compare(): mismas huellas perceptuales, distinto archivo → alta", () => {
  const r = R.compare(
    { sha256: "aa", phash: "ffffffffffffffff", dhash: "ffffffffffffffff" },
    { sha256: "bb", phash: "ffffffffffffffff", dhash: "ffffffffffffffff" },
  );
  assert.equal(r.verdict, "high");
  assert.equal(r.sha256Equal, false);
});

test("compare(): sin coincidencia cuando las huellas difieren mucho", () => {
  const r = R.compare(
    { sha256: "aa", phash: "ffffffffffffffff", dhash: "ffffffffffffffff" },
    { sha256: "bb", phash: "0000000000000000", dhash: "0000000000000000" },
  );
  assert.equal(r.verdict, "none");
});

// --- expediente ------------------------------------------------------------
function sampleDossier() {
  const reg = {
    id: "r1", name: "Mi foto", fileName: "foto.jpg", fileSize: 2048, sha256: "deadbeef",
    phash: "ffffffffffffffff", dhash: "ffffffffffffffff", thumbnail: "data:image/jpeg;base64,AAAA",
    registeredAt: "2026-10-17T10:00:00.000Z", notes: "Publicada en mi perfil <privado>",
  };
  const sus = { fileName: "captura.png", fileSize: 4096, sha256: "cafe", phash: "fffffffffffffffe", dhash: "ffffffffffffffff", thumbnail: "data:image/jpeg;base64,BBBB" };
  const cmp = R.compare(reg, sus);
  return R.buildDossier({
    registered: reg,
    suspect: sus,
    comparison: cmp,
    publication: { url: "https://ejemplo.com/post", foundAt: "2026-10-16 20:00", platform: "Red X", notes: "<script>alert(1)</script> sin permiso" },
    attachments: [{ fileName: "pantallazo.png", fileSize: 1000, sha256: "abcd", dataUrl: "data:image/png;base64,CCCC" }],
  });
}

test("buildDossier: genera caseId y fecha", () => {
  const d = sampleDossier();
  assert.ok(d.caseId.startsWith("IPT-"));
  assert.ok(Date.parse(d.generatedAt) > 0);
});

test("dossierToJson: JSON válido, con limitaciones y sin data URLs", () => {
  const json = R.dossierToJson(sampleDossier());
  const obj = JSON.parse(json);
  assert.ok(Array.isArray(obj.limitations) && obj.limitations.length > 0);
  assert.ok(Array.isArray(obj.nextSteps) && obj.nextSteps.length > 0);
  assert.equal(obj.registered.thumbnail, undefined, "las miniaturas no deben ir en el JSON");
  assert.ok(!json.includes("data:image"), "el JSON no debe contener data URLs");
  assert.equal(obj.comparison.verdict, "high");
});

test("dossierToHtml: contiene el caso, el veredicto y escapa el HTML del usuario", () => {
  const html = R.dossierToHtml(sampleDossier());
  assert.ok(html.includes("Expediente"));
  assert.ok(html.includes("Similitud visual alta"));
  assert.ok(html.includes("&lt;script&gt;"), "las notas con HTML deben escaparse");
  assert.ok(!html.includes("<script>alert(1)</script>"), "no debe inyectarse HTML del usuario");
  assert.ok(html.includes("data:image/jpeg;base64,AAAA"), "las miniaturas sí se embeben en el HTML");
});

test("escapeHtml", () => {
  assert.equal(R.escapeHtml(`<a href="x">&'`), "&lt;a href=&quot;x&quot;&gt;&amp;&#39;");
});

// --- sin red en el código fuente ------------------------------------------
test("el núcleo no contiene llamadas de red", () => {
  for (const f of ["reuse.ts", "reuseImage.ts", "reuseStore.ts"]) {
    const src = readFileSync(fileURLToPath(new URL(`../src/lib/${f}`, import.meta.url)), "utf8");
    assert.ok(!/\bfetch\s*\(|XMLHttpRequest|new WebSocket|navigator\.sendBeacon/.test(src), `${f} no debe hacer llamadas de red`);
  }
});
