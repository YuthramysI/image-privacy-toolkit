import io
import time
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from engine import metadata


@pytest.fixture(scope="module")
def client():
    import engine.api as api
    import engine.protect.pipeline as pl

    # Presets rápidos para no esperar minutos en las pruebas.
    pl.PRESETS["suave"] = replace(pl.PRESETS["suave"], steps=2)
    with TestClient(api.app) as c:
        yield c


def _png(size=(128, 96)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (120, 140, 160)).save(buf, "PNG")
    return buf.getvalue()


def test_rejects_unknown_preset(client):
    r = client.post("/jobs", files={"file": ("a.png", _png(), "image/png")}, data={"preset": "nope"})
    assert r.status_code == 400


def test_rejects_non_image(client):
    r = client.post("/jobs", files={"file": ("a.png", b"no soy una imagen", "image/png")}, data={"preset": "suave"})
    assert r.status_code == 400


def test_rejects_wrong_type(client):
    r = client.post("/jobs", files={"file": ("a.gif", b"GIF89a", "image/gif")}, data={"preset": "suave"})
    assert r.status_code == 415


def test_full_flow(client):
    r = client.post("/jobs", files={"file": ("a.png", _png(), "image/png")}, data={"preset": "suave"})
    assert r.status_code == 202
    job_id = r.json()["id"]

    deadline = time.time() + 120
    while time.time() < deadline:
        state = client.get(f"/jobs/{job_id}").json()
        if state["status"] in ("done", "failed"):
            break
        time.sleep(0.5)
    assert state["status"] == "done", state

    for fmt in ("png", "jpeg"):
        res = client.get(f"/jobs/{job_id}/result", params={"format": fmt})
        assert res.status_code == 200
        assert metadata.has_reservation(res.content)
        assert Image.open(io.BytesIO(res.content)).size == (128, 96)


def test_unknown_job_is_404(client):
    assert client.get("/jobs/no-existe").status_code == 404
