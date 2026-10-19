/**
 * Registro local de fotografías en IndexedDB. Guarda SOLO huellas y metadatos
 * (SHA-256, hashes perceptuales, nombre, notas, fecha, una miniatura pequeña),
 * nunca la fotografía completa. Vive únicamente en este navegador y se puede
 * perder si borras los datos del sitio. No sale nada a ningún servidor.
 */

import type { RegistryRecord } from "./reuse";

const DB_NAME = "ipt-evidencias";
const STORE = "registros";
const VERSION = 1;

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") return reject(new Error("Este navegador no permite almacenamiento local (IndexedDB)."));
    const req = indexedDB.open(DB_NAME, VERSION);
    req.onupgradeneeded = () => {
      if (!req.result.objectStoreNames.contains(STORE)) req.result.createObjectStore(STORE, { keyPath: "id" });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error("No se pudo abrir el almacenamiento local."));
  });
}

function tx<T>(mode: IDBTransactionMode, run: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  return openDb().then(
    (db) =>
      new Promise<T>((resolve, reject) => {
        const t = db.transaction(STORE, mode);
        const req = run(t.objectStore(STORE));
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error ?? new Error("Error de almacenamiento local."));
        t.oncomplete = () => db.close();
      }),
  );
}

export function putRecord(rec: RegistryRecord): Promise<void> {
  return tx("readwrite", (s) => s.put(rec)).then(() => undefined);
}

export async function listRecords(): Promise<RegistryRecord[]> {
  const all = await tx<RegistryRecord[]>("readonly", (s) => s.getAll() as IDBRequest<RegistryRecord[]>);
  return all.sort((a, b) => b.registeredAt.localeCompare(a.registeredAt));
}

export function getRecord(id: string): Promise<RegistryRecord | undefined> {
  return tx<RegistryRecord | undefined>("readonly", (s) => s.get(id) as IDBRequest<RegistryRecord | undefined>);
}

export function deleteRecord(id: string): Promise<void> {
  return tx("readwrite", (s) => s.delete(id)).then(() => undefined);
}

export async function clearAll(): Promise<void> {
  await tx("readwrite", (s) => s.clear());
}
