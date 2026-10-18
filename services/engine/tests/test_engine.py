import io
from dataclasses import replace

import numpy as np
import pytest
import torch
from PIL import Image

from pathlib import Path

from engine import metadata
from engine.protect import budget, eot
from engine.protect.pipeline import PRESETS, Engine, to_tensor


@pytest.fixture(scope="module")
def engine():
    return Engine(encoders=("taesd", "taef1"), device=torch.device("cpu"))


@pytest.fixture
def scene():
    from skimage import data

    return Image.fromarray(data.coffee()).resize((256, 192))


@pytest.fixture
def portrait():
    from skimage import data

    return Image.fromarray(data.astronaut()).resize((320, 320))


def _jpeg(img: Image.Image, q: int) -> torch.Tensor:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=q)
    return to_tensor(Image.open(buf).convert("RGB"), torch.device("cpu"))


@pytest.mark.parametrize("q", [60, 75, 90])
def test_diff_jpeg_matches_real_jpeg(scene, q):
    x = to_tensor(scene, torch.device("cpu"))
    real = _jpeg(scene, q)
    approx = eot.diff_jpeg(x, q)
    # El error frente a un JPEG real debe ser mucho menor que el propio
    # cambio que introduce la compresión.
    assert (approx - real).abs().mean() < 0.5 * (x - real).abs().mean()


def test_diff_jpeg_has_gradient(scene):
    x = to_tensor(scene, torch.device("cpu")).requires_grad_(True)
    eot.diff_jpeg(x, 75).sum().backward()
    assert x.grad is not None and x.grad.abs().sum() > 0


def test_eot_output_is_multiple_of_8(scene):
    import random

    x = to_tensor(scene, torch.device("cpu"))
    s = eot.sample(eot.EOTConfig(), random.Random(0))
    out = eot.apply(x, s)
    assert out.shape[-1] % 8 == 0 and out.shape[-2] % 8 == 0


def test_projection_respects_budget(scene):
    x = to_tensor(scene, torch.device("cpu"))
    emap = budget.eps_map(x, 8 / 255)
    d = budget.project(torch.randn_like(x), x, emap)
    assert torch.all(d.abs() <= emap + 1e-6)
    assert torch.all((x + d) >= 0) and torch.all((x + d) <= 1)


def _quick(name: str, steps: int = 3):
    return replace(PRESETS[name], steps=steps)


def test_protect_keeps_size_and_budget(engine, scene):
    preset = _quick("media")
    res = engine.protect(scene, preset)
    assert res.image.size == scene.size
    diff = np.abs(np.asarray(res.image, np.int16) - np.asarray(scene.convert("RGB"), np.int16))
    eps = round(preset.eps * 255)
    assert diff.max() > 0
    # Presupuesto perceptual (JND): el gasto medio respeta eps aunque algunos
    # píxeles de borde pasen de él; el techo es eps * cap.
    assert diff.mean() <= eps + 1
    assert diff.max() <= round(eps * 1.8) + 2


def test_face_layer_detects_and_lowers_similarity(engine, portrait):
    res = engine.protect(portrait, _quick("media", steps=4))
    assert res.faces == 1
    sims = [h["face_sim"] for h in res.history if "face_sim" in h]
    assert sims[-1] < sims[0]


def test_large_image_is_protected_at_full_resolution(engine, monkeypatch, scene):
    import engine.protect.pipeline as pl

    monkeypatch.setattr(pl, "MAX_WORK_SIDE", 128)
    res = engine.protect(scene, _quick("suave", steps=2))
    assert res.image.size == scene.size


def test_cancel(engine, scene):
    with pytest.raises(InterruptedError):
        engine.protect(scene, _quick("suave"), should_stop=lambda: True)


@pytest.mark.parametrize("fmt", ["png", "jpeg"])
def test_metadata_reservation(scene, fmt):
    # Sin sello (sin certificados), finalize cae a los metadatos IPTC/XMP.
    data = metadata.encode(scene, fmt, owner="Ana <ana@example.com>")
    assert metadata.has_reservation(data)
    Image.open(io.BytesIO(data)).verify()


def test_seal_declares_no_use_and_watermark_survives(scene, tmp_path):
    from engine import seal

    certs = Path.home() / ".cache/velo/certs"
    if not (certs / "es256_certs.pem").exists():
        pytest.skip("sin certificados de firma C2PA")
    data = seal.seal(
        scene, "jpeg", seal.SealConfig(certs_dir=certs, owner="Ana", watermark_id="VELOT01")
    )
    v = seal.verify(data)
    cc = v["content_credentials"]
    entries = [
        e
        for m in cc["manifests"].values()
        for a in m["assertions"]
        if a["label"] == "c2pa.training-mining"
        for e in [a["data"]["entries"]]
    ][0]
    assert entries["c2pa.ai_training"]["use"] == "notAllowed"
    # La marca de agua debe sobrevivir a una subida a redes.
    from engine.eval.run import social_upload

    assert seal.read_watermark(social_upload(Image.open(io.BytesIO(data)))) == v["watermark"]
