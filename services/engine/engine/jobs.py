"""Cola de trabajos en proceso. Un solo hilo trabajador por defecto: en CPU dos
optimizaciones simultáneas solo se reparten los mismos núcleos.

Nada se guarda en disco: las imágenes viven en memoria y se borran al expirar.
"""

from __future__ import annotations

import io
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum

from PIL import Image

from . import metadata
from .protect.pipeline import Engine, Progress

TTL_SECONDS = int(os.environ.get("ENGINE_JOB_TTL", 30 * 60))


class Status(str, Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"


@dataclass
class Job:
    id: str
    preset: str
    image: Image.Image | None
    status: Status = Status.queued
    step: int = 0
    total: int = 0
    losses: dict[str, float] = field(default_factory=dict)
    faces: int = 0
    error: str | None = None
    created: float = field(default_factory=time.time)
    finished: float | None = None
    png: bytes | None = None
    jpeg: bytes | None = None
    original: bytes | None = None  # bytes subidos, para el hash del registro
    record: dict | None = None  # certificado de derechos firmado
    cancel: threading.Event = field(default_factory=threading.Event)

    def public(self, position: int | None = None) -> dict:
        return {
            "id": self.id,
            "preset": self.preset,
            "status": self.status.value,
            "step": self.step,
            "total": self.total,
            "losses": self.losses,
            "faces": self.faces,
            "error": self.error,
            "queue_position": position,
        }


class JobQueue:
    def __init__(self, engine: Engine, workers: int = 1):
        self.engine = engine
        self.jobs: dict[str, Job] = {}
        self.order: list[str] = []
        self.lock = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="protect")

    def submit(self, image: Image.Image, preset: str, original: bytes | None = None) -> Job:
        self.sweep()
        job = Job(id=uuid.uuid4().hex, preset=preset, image=image, original=original)
        with self.lock:
            self.jobs[job.id] = job
            self.order.append(job.id)
        self.pool.submit(self._run, job)
        return job

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def position(self, job: Job) -> int | None:
        if job.status != Status.queued:
            return None
        with self.lock:
            waiting = [j for j in self.order if self.jobs[j].status in (Status.queued, Status.running)]
        return waiting.index(job.id) if job.id in waiting else None

    def cancel(self, job: Job) -> None:
        job.cancel.set()
        if job.status == Status.queued:
            job.status = Status.cancelled

    def sweep(self) -> None:
        now = time.time()
        with self.lock:
            expired = [j.id for j in self.jobs.values() if now - j.created > TTL_SECONDS and j.status not in (Status.queued, Status.running)]
            for jid in expired:
                del self.jobs[jid]
                self.order.remove(jid)

    def _run(self, job: Job) -> None:
        if job.cancel.is_set():
            return
        job.status = Status.running

        def on_progress(p: Progress) -> None:
            job.step, job.total, job.losses = p.step, p.total, p.losses

        wid = f"VELO{job.id[:3].upper()}"
        try:
            res = self.engine.protect(job.image, job.preset, on_progress=on_progress, should_stop=job.cancel.is_set)
            job.faces = res.faces
            job.png = metadata.finalize(res.image, "png", watermark_id=wid)
            job.jpeg = metadata.finalize(res.image, "jpeg", watermark_id=wid)
            if job.original is not None:
                from . import registry

                try:
                    job.record = registry.create_record(job.original, job.png, watermark_id=wid)
                except Exception:  # noqa: BLE001 — el registro es opcional, no bloquea
                    job.record = None
            job.status = Status.done
        except InterruptedError:
            job.status = Status.cancelled
        except Exception as exc:  # noqa: BLE001 — el error se devuelve al cliente
            job.status = Status.failed
            job.error = str(exc)
        finally:
            job.image = None
            job.original = None
            job.finished = time.time()


def read_upload(data: bytes, max_pixels: int) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    if img.width * img.height > max_pixels:
        raise ValueError(f"La imagen supera {max_pixels // 1_000_000} MP")
    img.load()
    return img
