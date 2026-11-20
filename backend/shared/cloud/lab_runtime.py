from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import SpaShinyCloudConfig, load_cloud_config
from .models import ACTIVE_JOB_STATUSES, JobStatus


LAB_GPU_CHOICES = ("auto", "gpu-0", "gpu-1", "cpu")
LAB_GPU_QUEUE_NAMES = {
    "gpu-0": "lab_gpu_0",
    "gpu-1": "lab_gpu_1",
}
LAB_GPU_UI_LABELS = {
    "auto": "Auto",
    "gpu-0": "GPU 1",
    "gpu-1": "GPU 2",
    "cpu": "CPU",
}
LAB_GPU_PHYSICAL_INDEX = {
    "gpu-0": 0,
    "gpu-1": 1,
}


class LabRuntimeError(ValueError):
    pass


def is_lab_queue_name(value: str | None) -> bool:
    return str(value or "") in set(LAB_GPU_QUEUE_NAMES.values())


def normalize_lab_gpu_choice(value: Any) -> str:
    choice = str(value or "auto").strip().lower()
    if choice not in LAB_GPU_CHOICES:
        raise LabRuntimeError("INVALID_COMPUTE_RESOURCE")
    return choice


def lab_queue_for_gpu(choice: str) -> str:
    choice = normalize_lab_gpu_choice(choice)
    if choice in {"auto", "cpu"}:
        raise LabRuntimeError("AUTO_RESOURCE_REQUIRES_SCHEDULER")
    return LAB_GPU_QUEUE_NAMES[choice]


def lab_gpu_for_queue(queue_name: str | None) -> str:
    for gpu, queue in LAB_GPU_QUEUE_NAMES.items():
        if queue == str(queue_name or ""):
            return gpu
    return ""


def lab_gpu_manifest(choice: str, *, gpu_name: str = "", gpu_uuid: str = "") -> dict[str, Any]:
    gpu = normalize_lab_gpu_choice(choice)
    if gpu in {"auto", "cpu"}:
        raise LabRuntimeError("AUTO_RESOURCE_REQUIRES_ASSIGNED_GPU")
    return {
        "ui_gpu_label": LAB_GPU_UI_LABELS[gpu],
        "physical_gpu_index": LAB_GPU_PHYSICAL_INDEX[gpu],
        "container_visible_index": 0,
        "gpu_uuid": str(gpu_uuid or ""),
        "gpu_name": str(gpu_name or ""),
    }


def safe_session_child(root: Path, session_id: str, *parts: str) -> Path:
    if not str(session_id or "").startswith("sess_"):
        raise LabRuntimeError("INVALID_SESSION_ID")
    root_resolved = Path(root).resolve()
    candidate = root_resolved / str(session_id)
    for part in parts:
        text = str(part or "")
        if not text or text in {".", ".."} or Path(text).is_absolute():
            raise LabRuntimeError("UNSAFE_PATH")
        if any(piece in {"", ".", ".."} for piece in Path(text).parts):
            raise LabRuntimeError("UNSAFE_PATH")
        candidate = candidate / text
    resolved = candidate.resolve()
    if resolved == root_resolved or root_resolved not in resolved.parents:
        raise LabRuntimeError("PATH_ESCAPE")
    return resolved


def short_anonymous_job_id(job_id: str) -> str:
    text = str(job_id or "")
    if len(text) <= 12:
        return text
    return text[:8] + "****"


@dataclass
class LabGpuScheduler:
    database: Any
    config: SpaShinyCloudConfig | None = None
    minimum_vram_gb: int = 0

    def __post_init__(self) -> None:
        if self.config is None:
            self.config = load_cloud_config()

    def queue_for_request(self, requested_resource: Any) -> tuple[str, str]:
        requested = normalize_lab_gpu_choice(requested_resource)
        if requested == "cpu":
            raise LabRuntimeError("CPU_RESOURCE_NOT_SUPPORTED_FOR_GPU_WORKFLOW")
        if requested != "auto":
            return LAB_GPU_QUEUE_NAMES[requested], requested
        selected = self._select_auto_gpu()
        return LAB_GPU_QUEUE_NAMES[selected], selected

    def _select_auto_gpu(self) -> str:
        gpu_status = self._cached_gpu_status()
        minimum_vram_mb = max(0, int(self.minimum_vram_gb or 0) * 1024)
        scores = []
        for gpu, queue_name in LAB_GPU_QUEUE_NAMES.items():
            status = gpu_status.get(gpu, {})
            health = str(status.get("health") or "UNKNOWN").strip().upper()
            health_score = 0 if health in {"READY", "HEALTHY", "IDLE"} else 1
            free_vram_mb = self._number(status.get("vram_free_mb"))
            vram_score = 0
            if minimum_vram_mb and (free_vram_mb is None or free_vram_mb < minimum_vram_mb):
                vram_score = 1
            free_vram_rank = -(free_vram_mb if free_vram_mb is not None else -1)
            scores.append(
                (
                    health_score,
                    vram_score,
                    self._active_count(queue_name),
                    self._queued_count(queue_name),
                    free_vram_rank,
                    gpu,
                )
            )
        scores.sort(key=lambda item: item)
        return str(scores[0][-1])

    def _cached_gpu_status(self) -> dict[str, dict[str, Any]]:
        try:
            path = self.config.lab_logs_root / "resource_status.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            gpus = data.get("gpus", {})
            return gpus if isinstance(gpus, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            return float(value)
        except Exception:
            return None

    def _active_count(self, queue_name: str) -> int:
        with self.database.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM jobs
                WHERE queue_name=?
                AND status IN (
                """
                + ", ".join("?" for _ in ACTIVE_JOB_STATUSES)
                + """
                )
                AND status != ?
                """,
                (queue_name, *sorted(ACTIVE_JOB_STATUSES), JobStatus.QUEUED_GPU.value),
            ).fetchone()
        return int(row["count"] or 0)

    def _queued_count(self, queue_name: str) -> int:
        with self.database.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM jobs
                WHERE queue_name=?
                AND status=?
                """,
                (queue_name, JobStatus.QUEUED_GPU.value),
            ).fetchone()
        return int(row["count"] or 0)


def validate_lab_gpu_worker_environment(config: SpaShinyCloudConfig | None = None) -> dict[str, Any]:
    config = config or load_cloud_config()
    if not bool(config.gpu_required):
        raise LabRuntimeError("SPASHINY_GPU_REQUIRED must be enabled for Lab GPU workers.")
    if bool(config.allow_cpu_fallback):
        raise LabRuntimeError("SPASHINY_ALLOW_CPU_FALLBACK must be disabled for Lab GPU workers.")
    requested = normalize_lab_gpu_choice(os.environ.get("SPASHINY_ASSIGNED_GPU", "gpu-0"))
    if requested == "auto":
        raise LabRuntimeError("Lab GPU worker must be pinned to gpu-0 or gpu-1.")
    visible = str(os.environ.get("CUDA_VISIBLE_DEVICES") or "").strip()
    if visible not in {"", "0"}:
        raise LabRuntimeError("Lab GPU worker containers must expose a single CUDA device as index 0.")
    try:
        import torch
    except Exception as exc:  # pragma: no cover - depends on GPU image
        raise LabRuntimeError("PyTorch is required for Lab GPU workers.") from exc
    if not torch.cuda.is_available():
        raise LabRuntimeError("CUDA is unavailable; Lab GPU workers fail closed.")
    name = str(torch.cuda.get_device_name(0) or "")
    if config.lab_allowed_gpu_name_tokens and not any(token in name for token in config.lab_allowed_gpu_name_tokens):
        raise LabRuntimeError(f"GPU name is not allowed for this Lab profile: {name}")
    uuid = ""
    try:  # pragma: no cover - depends on CUDA runtime
        uuid = str(torch.cuda.get_device_properties(0).uuid)
    except Exception:
        uuid = ""
    return lab_gpu_manifest(requested, gpu_name=name, gpu_uuid=uuid)


def write_lab_gpu_manifest(path: Path, manifest: dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
    return target
