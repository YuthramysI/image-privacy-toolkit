export const ENGINE_URL = (process.env.NEXT_PUBLIC_ENGINE_URL ?? "http://localhost:8000").replace(/\/$/, "");

export type PresetName = "suave" | "media" | "fuerte" | "maxima";

export type Preset = {
  name: PresetName;
  eps: number;
  steps: number;
  encoders: string[];
};

export type JobStatus = "queued" | "running" | "done" | "failed" | "cancelled";

export type JobState = {
  id: string;
  preset: PresetName;
  status: JobStatus;
  step: number;
  total: number;
  losses: Record<string, number>;
  faces: number;
  error: string | null;
  queue_position: number | null;
};

async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json();
    return typeof body.detail === "string" ? body.detail : `Error ${res.status}`;
  } catch {
    return `Error ${res.status}`;
  }
}

export async function fetchPresets(): Promise<Preset[]> {
  const res = await fetch(`${ENGINE_URL}/presets`);
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

export async function createJob(file: File, preset: PresetName): Promise<string> {
  const form = new FormData();
  form.append("file", file);
  form.append("preset", preset);
  const res = await fetch(`${ENGINE_URL}/jobs`, { method: "POST", body: form });
  if (!res.ok) throw new Error(await errorMessage(res));
  return (await res.json()).id;
}

/** Escucha el progreso por SSE. Devuelve una función para dejar de escuchar. */
export function watchJob(id: string, onState: (s: JobState) => void, onError: (msg: string) => void): () => void {
  const source = new EventSource(`${ENGINE_URL}/jobs/${id}/events`);
  source.onmessage = (ev) => {
    const state: JobState = JSON.parse(ev.data);
    onState(state);
    if (state.status === "done" || state.status === "failed" || state.status === "cancelled") source.close();
  };
  source.onerror = () => {
    if (source.readyState === EventSource.CLOSED) return;
    source.close();
    onError("Se perdió la conexión con el motor");
  };
  return () => source.close();
}

export async function cancelJob(id: string): Promise<void> {
  await fetch(`${ENGINE_URL}/jobs/${id}`, { method: "DELETE" });
}

export async function fetchResult(id: string, format: "png" | "jpeg"): Promise<Blob> {
  const res = await fetch(`${ENGINE_URL}/jobs/${id}/result?format=${format}`);
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.blob();
}
