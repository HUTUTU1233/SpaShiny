from __future__ import annotations

from pathlib import Path
from typing import Any

import math

from .config import SpaShinyCloudConfig, load_cloud_config
from .database import CloudDatabase
from .models import GPU_ACTIVE_STATUSES, JobStatus


class ResourceManager:
    def __init__(self, config: SpaShinyCloudConfig | None = None, database: CloudDatabase | None = None) -> None:
        self.config = config or load_cloud_config()
        self.database = database or CloudDatabase(config=self.config)

    def user_storage_bytes(self, user_id: str) -> int:
        root = (
            Path(self.config.lab_data_root) / "sessions" / user_id
            if self.config.is_lab_profile
            else self.config.workspace / "users" / user_id
        )
        if not root.exists():
            return 0
        total = 0
        for path in root.rglob("*"):
            if path.is_file():
                total += path.stat().st_size
        return total

    def gpu_queue_depth(self) -> int:
        return len(self.database.list_jobs(statuses=[JobStatus.QUEUED.value, JobStatus.WAITING_FOR_GPU.value], limit=10000))

    def active_gpu_jobs(self) -> list[dict[str, Any]]:
        return [job.to_dict() for job in self.database.list_jobs(statuses=list(GPU_ACTIVE_STATUSES), limit=10000)]


def estimate_array_memory(shape: tuple[int, ...] | list[int], dtype_itemsize: int = 4) -> int:
    total = int(dtype_itemsize)
    for dim in shape:
        total *= max(0, int(dim))
    return total


def estimate_sparse_matrix_memory(nnz: int, index_itemsize: int = 4, value_itemsize: int = 4) -> int:
    nnz = max(0, int(nnz))
    return nnz * (int(index_itemsize) * 2 + int(value_itemsize))


def estimate_raster_shape(width: float, height: float, dx: float) -> tuple[int, int]:
    if dx <= 0:
        raise ValueError("Raster dx must be positive.")
    return max(1, math.ceil(float(height) / float(dx))), max(1, math.ceil(float(width) / float(dx)))


def choose_safe_raster_dx(
    width: float,
    height: float,
    channels: int,
    dtype_itemsize: int,
    max_bytes: int,
    initial_dx: float,
) -> float:
    dx = float(initial_dx)
    while True:
        rows, cols = estimate_raster_shape(width, height, dx)
        estimated = estimate_array_memory((rows, cols, channels), dtype_itemsize)
        if estimated <= max_bytes:
            return dx
        dx *= 1.25


def validate_memory_request(estimated_bytes: int, max_bytes: int) -> dict[str, Any]:
    ok = int(estimated_bytes) <= int(max_bytes)
    return {
        "ok": ok,
        "estimated_bytes": int(estimated_bytes),
        "max_bytes": int(max_bytes),
        "message": "OK" if ok else "Estimated memory exceeds the configured limit.",
    }
