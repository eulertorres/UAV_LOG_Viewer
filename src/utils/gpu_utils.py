import os
import subprocess
from dataclasses import dataclass
from typing import Iterable, Optional


@dataclass
class GpuInfo:
    index: int
    name: str
    memory_total: float
    memory_free: float


def _parse_nvidia_smi() -> list[GpuInfo]:
    """Interroga o `nvidia-smi` para obter GPUs disponíveis.

    Retorna uma lista vazia se o utilitário não estiver disponível ou
    se ocorrer qualquer erro, evitando quebrar a inicialização do app.
    """

    query = [
        "nvidia-smi",
        "--query-gpu=index,memory.total,memory.free,name",
        "--format=csv,noheader,nounits",
    ]
    try:
        raw = subprocess.check_output(query, encoding="utf-8", stderr=subprocess.DEVNULL)
    except Exception:
        return []

    gpus: list[GpuInfo] = []
    for line in raw.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        try:
            idx = int(parts[0])
            mem_total = float(parts[1])
            mem_free = float(parts[2])
            name = parts[3]
        except Exception:
            continue
        gpus.append(GpuInfo(index=idx, name=name, memory_total=mem_total, memory_free=mem_free))
    return gpus


def _pick_best_gpu(gpus: Iterable[GpuInfo]) -> Optional[GpuInfo]:
    """Seleciona a GPU com maior memória total (empate → mais livre)."""

    best: Optional[GpuInfo] = None
    for gpu in gpus:
        if best is None:
            best = gpu
            continue
        if gpu.memory_total > best.memory_total:
            best = gpu
        elif gpu.memory_total == best.memory_total and gpu.memory_free > best.memory_free:
            best = gpu
    return best


def apply_best_gpu_env(preferred_index: int | None = None) -> Optional[GpuInfo]:
    """Define variáveis de ambiente para privilegiar a GPU mais forte.

    Se `preferred_index` for informado e existir, ele é priorizado; caso
    contrário, escolhe a GPU com maior memória. Retorna a GPU escolhida
    (ou ``None`` se nenhuma foi encontrada).
    """

    gpus = _parse_nvidia_smi()
    if not gpus:
        return None

    chosen: Optional[GpuInfo] = None
    if preferred_index is not None:
        chosen = next((g for g in gpus if g.index == preferred_index), None)
    if chosen is None:
        chosen = _pick_best_gpu(gpus)

    if chosen is None:
        return None

    os.environ.setdefault("CUDA_VISIBLE_DEVICES", str(chosen.index))
    os.environ.setdefault("NVIDIA_VISIBLE_DEVICES", str(chosen.index))

    # Ativa aceleração no WebEngine quando possível.
    chromium_flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    accel_flags = "--ignore-gpu-blocklist --enable-gpu-rasterization --use-gl=desktop"
    if accel_flags not in chromium_flags:
        merged = (chromium_flags + " " + accel_flags).strip()
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = merged

    return chosen
