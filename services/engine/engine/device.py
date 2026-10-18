import os

import torch


def pick_device() -> torch.device:
    forced = os.environ.get("ENGINE_DEVICE")
    if forced:
        return torch.device(forced)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def configure_threads() -> None:
    # Los hilos lógicos (hyperthreading) compiten por las mismas unidades de
    # cálculo: con convoluciones rinde más usar solo los núcleos físicos.
    n = os.environ.get("ENGINE_THREADS")
    torch.set_num_threads(int(n) if n else max(1, (os.cpu_count() or 2) // 2))
