from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import SpaShinyCloudConfig, load_cloud_config
from .database import CloudDatabase, utc_now
from .job_queue_repository import JobQueueRepository
from .lab_runtime import LAB_GPU_QUEUE_NAMES, LAB_GPU_UI_LABELS, short_anonymous_job_id
from .models import ACTIVE_JOB_STATUSES, JobStatus


def _unknown_gpu(label: str, queue_name: str) -> dict[str, Any]:
    return {
        "label": label,
        "health": "UNKNOWN",
        "name": "UNKNOWN",
        "utilization_percent": None,
        "vram_used_mb": None,
        "vram_total_mb": None,
        "vram_free_mb": None,
        "temperature_c": None,
        "power_watts": None,
        "queue_length": None,
        "lease_status": "UNKNOWN",
        "last_heartbeat_at": "",
        "queue_name": queue_name,
    }


@dataclass
class LabResourceMonitor:
    database: CloudDatabase | None = None
    config: SpaShinyCloudConfig | None = None

    def __post_init__(self) -> None:
        if self.config is None:
            self.config = load_cloud_config()
        if self.database is None:
            self.database = CloudDatabase(config=self.config)

    def snapshot(self) -> dict[str, Any]:
        queue = JobQueueRepository(self.database, self.config).queue_status()
        gpu_rows = self._nvidia_smi()
        gpus = {}
        for gpu_choice, queue_name in LAB_GPU_QUEUE_NAMES.items():
            label = LAB_GPU_UI_LABELS[gpu_choice]
            item = _unknown_gpu(label, queue_name)
            physical_index = int(gpu_choice.split("-", 1)[1])
            if physical_index < len(gpu_rows):
                row = gpu_rows[physical_index]
                item.update(
                    {
                        "health": "READY" if row.get("name") else "UNKNOWN",
                        "name": row.get("name") or "UNKNOWN",
                        "utilization_percent": row.get("utilization_percent"),
                        "vram_used_mb": row.get("vram_used_mb"),
                        "vram_total_mb": row.get("vram_total_mb"),
                        "vram_free_mb": row.get("vram_free_mb"),
                        "temperature_c": row.get("temperature_c"),
                        "power_watts": row.get("power_watts"),
                        "gpu_uuid": row.get("gpu_uuid") or "",
                    }
                )
            item.update(self._gpu_job_status(queue_name))
            gpus[gpu_choice] = item
        return {
            "profile": "lab",
            "timestamp": utc_now(),
            "cpu": self._cpu_status(),
            "memory": self._memory_status(),
            "disk": self._disk_status(),
            "jobs": {
                "cpu_active_jobs": self._active_count(resource_type="cpu"),
                "cpu_queue_length": int(queue.get("cpu_queue_length") or 0),
                "gpu_queue_length": int(queue.get("gpu_queue_length") or 0),
            },
            "gpus": gpus,
            "storage_backend": self.config.storage_backend,
            "r2_enabled": False,
            "remote_provider_enabled": False,
        }

    def cache_path(self) -> Path:
        return self.config.lab_logs_root / "resource_status.json"

    def host_cache_path(self) -> Path:
        return Path(os.environ.get("SPASHINY_HOST_RESOURCE_CACHE") or (self.config.lab_logs_root / "host_resource_status.json"))

    def cached_snapshot(self, *, max_age_seconds: int = 15) -> dict[str, Any]:
        targets = [
            (self.host_cache_path(), "HOST_CACHED"),
            (self.cache_path(), "CACHED"),
        ]
        stale_reasons = []
        for target, status_label in targets:
            try:
                stat = target.stat()
                age = time.time() - stat.st_mtime
                if age > max(1, int(max_age_seconds)):
                    stale_reasons.append(f"{status_label}_STALE")
                    continue
                data = json.loads(target.read_text(encoding="utf-8"))
                if not isinstance(data, dict) or data.get("profile") != "lab":
                    stale_reasons.append(f"{status_label}_INVALID")
                    continue
                data.setdefault("monitor_status", status_label)
                data.setdefault("cache_age_seconds", round(age, 3))
                return data
            except Exception:
                stale_reasons.append(f"{status_label}_UNAVAILABLE")
                continue
        reason = "MONITOR_CACHE_UNAVAILABLE"
        if stale_reasons:
            reason = ",".join(stale_reasons)
        return self.unknown_snapshot(reason=reason)

    def cached_snapshot_legacy(self, *, max_age_seconds: int = 15) -> dict[str, Any]:
        target = self.cache_path()
        try:
            stat = target.stat()
            age = time.time() - stat.st_mtime
            if age > max(1, int(max_age_seconds)):
                return self.unknown_snapshot(reason="STALE_MONITOR_CACHE")
            data = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("profile") != "lab":
                return self.unknown_snapshot(reason="INVALID_MONITOR_CACHE")
            data.setdefault("monitor_status", "CACHED")
            data.setdefault("cache_age_seconds", round(age, 3))
            return data
        except Exception:
            return self.unknown_snapshot(reason="MONITOR_CACHE_UNAVAILABLE")

    def unknown_snapshot(self, *, reason: str) -> dict[str, Any]:
        return {
            "profile": "lab",
            "timestamp": utc_now(),
            "monitor_status": reason,
            "cpu": {
                "model": "UNKNOWN",
                "logical_cores": None,
                "total_usage_percent": None,
                "per_core_usage_percent": [],
            },
            "memory": {"total_gb": None, "used_gb": None, "available_gb": None, "usage_percent": None},
            "disk": {
                "path": str(self.config.lab_data_root),
                "total_gb": None,
                "used_gb": None,
                "available_gb": None,
                "usage_percent": None,
            },
            "jobs": {"cpu_active_jobs": None, "cpu_queue_length": None, "gpu_queue_length": None},
            "gpus": {
                "gpu-0": _unknown_gpu(LAB_GPU_UI_LABELS["gpu-0"], LAB_GPU_QUEUE_NAMES["gpu-0"]),
                "gpu-1": _unknown_gpu(LAB_GPU_UI_LABELS["gpu-1"], LAB_GPU_QUEUE_NAMES["gpu-1"]),
            },
            "storage_backend": self.config.storage_backend,
            "r2_enabled": False,
            "remote_provider_enabled": False,
        }

    def write_snapshot(self) -> Path:
        target = self.cache_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.snapshot(), ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
        return target

    def _cpu_status(self) -> dict[str, Any]:
        try:
            import psutil

            per_core = psutil.cpu_percent(interval=0.05, percpu=True)
            total = psutil.cpu_percent(interval=0.0)
            return {
                "model": platform.processor() or platform.machine() or "UNKNOWN",
                "logical_cores": psutil.cpu_count(logical=True),
                "total_usage_percent": total,
                "per_core_usage_percent": per_core,
            }
        except Exception:
            return {
                "model": platform.processor() or platform.machine() or "UNKNOWN",
                "logical_cores": None,
                "total_usage_percent": None,
                "per_core_usage_percent": [],
            }

    def _memory_status(self) -> dict[str, Any]:
        try:
            import psutil

            mem = psutil.virtual_memory()
            return {
                "total_gb": round(mem.total / 1024**3, 3),
                "used_gb": round(mem.used / 1024**3, 3),
                "available_gb": round(mem.available / 1024**3, 3),
                "usage_percent": mem.percent,
            }
        except Exception:
            return {"total_gb": None, "used_gb": None, "available_gb": None, "usage_percent": None}

    def _disk_status(self) -> dict[str, Any]:
        try:
            import psutil

            disk = psutil.disk_usage(str(self.config.lab_data_root))
            return {
                "path": str(self.config.lab_data_root),
                "total_gb": round(disk.total / 1024**3, 3),
                "used_gb": round(disk.used / 1024**3, 3),
                "available_gb": round(disk.free / 1024**3, 3),
                "usage_percent": disk.percent,
            }
        except Exception:
            return {"path": str(self.config.lab_data_root), "total_gb": None, "used_gb": None, "available_gb": None, "usage_percent": None}

    def _nvidia_smi(self) -> list[dict[str, Any]]:
        command = [
            "nvidia-smi",
            "--query-gpu=index,uuid,name,utilization.gpu,memory.used,memory.total,memory.free,temperature.gpu,power.draw",
            "--format=csv,noheader,nounits",
        ]
        try:
            completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=5)
        except Exception:
            return []
        if completed.returncode != 0:
            return []
        rows = []
        for line in completed.stdout.splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) < 9:
                continue
            rows.append(
                {
                    "index": self._int(parts[0]),
                    "gpu_uuid": parts[1],
                    "name": parts[2],
                    "utilization_percent": self._int(parts[3]),
                    "vram_used_mb": self._int(parts[4]),
                    "vram_total_mb": self._int(parts[5]),
                    "vram_free_mb": self._int(parts[6]),
                    "temperature_c": self._int(parts[7]),
                    "power_watts": self._float(parts[8]),
                }
            )
        return rows

    def _gpu_job_status(self, queue_name: str) -> dict[str, Any]:
        with self.database.connect() as conn:
            queued = conn.execute(
                "SELECT COUNT(*) AS count FROM jobs WHERE queue_name=? AND status=?",
                (queue_name, JobStatus.QUEUED_GPU.value),
            ).fetchone()
            current = conn.execute(
                """
                SELECT job_id, status, worker_id FROM jobs
                WHERE queue_name=?
                AND status IN (
                """
                + ", ".join("?" for _ in ACTIVE_JOB_STATUSES)
                + """
                )
                AND status != ?
                ORDER BY started_at DESC, claimed_at DESC
                LIMIT 1
                """,
                (queue_name, *sorted(ACTIVE_JOB_STATUSES), JobStatus.QUEUED_GPU.value),
            ).fetchone()
            worker = conn.execute(
                "SELECT last_heartbeat_at FROM worker_instances WHERE worker_type='gpu' ORDER BY last_heartbeat_at DESC LIMIT 1"
            ).fetchone()
        return {
            "lease_status": str(current["status"]) if current else "IDLE",
            "queue_length": int(queued["count"] or 0),
            "last_heartbeat_at": str(worker["last_heartbeat_at"] or "") if worker else "",
        }

    def _active_count(self, *, resource_type: str) -> int:
        with self.database.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count FROM jobs
                WHERE resource_type=?
                AND status IN (
                """
                + ", ".join("?" for _ in ACTIVE_JOB_STATUSES)
                + """
                )
                AND status NOT IN (?, ?)
                """,
                (resource_type, *sorted(ACTIVE_JOB_STATUSES), JobStatus.QUEUED_CPU.value, JobStatus.QUEUED_GPU.value),
            ).fetchone()
        return int(row["count"] or 0)

    @staticmethod
    def _int(value: str) -> int | None:
        try:
            return int(float(str(value).strip()))
        except Exception:
            return None

    @staticmethod
    def _float(value: str) -> float | None:
        try:
            return float(str(value).strip())
        except Exception:
            return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the SpaShiny Lab resource monitor.")
    parser.add_argument("--serve", action="store_true", help="Continuously write cached status JSON.")
    parser.add_argument("--interval", type=float, default=3.0)
    args = parser.parse_args(argv)
    monitor = LabResourceMonitor()
    if not args.serve:
        print(json.dumps(monitor.snapshot(), ensure_ascii=True, sort_keys=True))
        return 0
    while True:
        monitor.write_snapshot()
        time.sleep(max(2.0, min(5.0, float(args.interval))))


if __name__ == "__main__":
    raise SystemExit(main())
