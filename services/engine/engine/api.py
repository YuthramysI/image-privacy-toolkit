"""API HTTP del motor.

  POST   /jobs                 imagen + preset → {id}
  GET    /jobs/{id}            estado y progreso
  GET    /jobs/{id}/events     progreso en vivo (Server-Sent Events)
  GET    /jobs/{id}/result     imagen protegida (?format=png|jpeg)
  DELETE /jobs/{id}            cancelar
  GET    /presets              presets disponibles
"""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from PIL import Image, UnidentifiedImageError

from .jobs import JobQueue, Status, read_upload
from .protect.pipeline import PRESETS, Engine

MAX_UPLOAD_BYTES = int(os.environ.get("ENGINE_MAX_UPLOAD_MB", 15)) * 1024 * 1024
MAX_PIXELS = int(os.environ.get("ENGINE_MAX_MEGAPIXELS", 24)) * 1_000_000
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
# Por defecto solo los presets viables en CPU; "maxima" se activa con GPU.
ENABLED_PRESETS = os.environ.get("ENGINE_PRESETS", "suave,media,fuerte").split(",")

Image.MAX_IMAGE_PIXELS = MAX_PIXELS


@asynccontextmanager
async def lifespan(app: FastAPI):
    encoders = sorted({e for name in ENABLED_PRESETS for e in PRESETS[name].encoders})
    engine = await asyncio.to_thread(Engine, tuple(encoders))
    app.state.queue = JobQueue(engine, workers=int(os.environ.get("ENGINE_WORKERS", 1)))
    yield


app = FastAPI(title="Motor de perturbación", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("ENGINE_CORS", "http://localhost:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


def _queue() -> JobQueue:
    return app.state.queue


def _job(job_id: str):
    job = _queue().get(job_id)
    if job is None:
        raise HTTPException(404, "Trabajo no encontrado o expirado")
    return job


@app.get("/health")
def health():
    return {"ok": True, "device": str(_queue().engine.device)}


@app.get("/presets")
def presets():
    return [
        {"name": p.name, "eps": round(p.eps * 255), "steps": p.steps, "encoders": list(p.encoders)}
        for name, p in PRESETS.items()
        if name in ENABLED_PRESETS
    ]


@app.post("/jobs", status_code=202)
async def create_job(file: UploadFile = File(...), preset: str = Form("media")):
    if preset not in ENABLED_PRESETS:
        raise HTTPException(400, f"Preset no disponible: {preset}")
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(415, "Formato no soportado: usa JPEG, PNG o WebP")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"La imagen supera {MAX_UPLOAD_BYTES // 1024 // 1024} MB")
    try:
        img = read_upload(data, MAX_PIXELS)
    except (UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise HTTPException(400, "No se pudo leer la imagen") from exc
    except ValueError as exc:
        raise HTTPException(413, str(exc)) from exc
    job = _queue().submit(img, preset, original=data)
    return {"id": job.id}


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = _job(job_id)
    return job.public(_queue().position(job))


@app.get("/jobs/{job_id}/events")
async def job_events(job_id: str):
    job = _job(job_id)

    async def stream():
        last = None
        while True:
            payload = json.dumps(job.public(_queue().position(job)))
            if payload != last:
                yield f"data: {payload}\n\n"
                last = payload
            if job.status in (Status.done, Status.failed, Status.cancelled):
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/jobs/{job_id}/result")
def job_result(job_id: str, format: str = "png"):
    job = _job(job_id)
    if job.status != Status.done:
        raise HTTPException(409, "El trabajo aún no ha terminado")
    if format not in ("png", "jpeg"):
        raise HTTPException(400, "Formato: png o jpeg")
    data = job.png if format == "png" else job.jpeg
    ext = "png" if format == "png" else "jpg"
    return Response(
        data,
        media_type=f"image/{format}",
        headers={"Content-Disposition": f'attachment; filename="protegida-{job.id[:8]}.{ext}"'},
    )


@app.get("/jobs/{job_id}/record")
def job_record(job_id: str):
    """Certificado de derechos firmado: hash del original y del protegido,
    declaración de no autorización y firma verificable."""
    job = _job(job_id)
    if job.status != Status.done:
        raise HTTPException(409, "El trabajo aún no ha terminado")
    if not job.record:
        raise HTTPException(404, "Sin registro de derechos para este trabajo")
    return Response(
        json.dumps(job.record, indent=2, ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="derechos-{job.id[:8]}.json"'},
    )


@app.delete("/jobs/{job_id}", status_code=204)
def cancel_job(job_id: str):
    _queue().cancel(_job(job_id))


@app.post("/verify")
async def verify_image(file: UploadFile = File(...)):
    """Lee el sello de "no uso" de una imagen: la declaración firmada (Content
    Credentials) y la marca de agua invisible, si siguen presentes."""
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(415, "Formato no soportado")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Imagen demasiado grande")
    from . import seal

    result = await asyncio.to_thread(seal.verify, data)
    cc = result.get("content_credentials")
    reserved = False
    if isinstance(cc, dict):
        reserved = any("training-mining" in a.get("label", "") for m in cc.get("manifests", {}).values() for a in m.get("assertions", []))
    return {
        "proteccion_detectada": bool(result.get("watermark")) or reserved,
        "marca_de_agua": result.get("watermark"),
        "credenciales_no_uso": reserved,
    }
