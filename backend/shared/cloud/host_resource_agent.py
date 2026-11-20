from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Any


ACTIVE_STATUSES = {"running", "running_cpu", "running_gpu", "claimed", "started", "processing"}
QUEUED_STATUSES = {"queued", "queued_cpu", "queued_gpu"}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _float(value: Any) -> float | None:
    try:
        text = str(value).strip()
        if not text or text.upper() == "N/A":
            return None
        return float(text)
    except Exception:
        return None


def _int(value: Any) -> int | None:
    try:
        number = _float(value)
        return int(number) if number is not None else None
    except Exception:
        return None


def _gb(bytes_value: int | float | None) -> float | None:
    if bytes_value is None:
        return None
    return round(float(bytes_value) / 1024**3, 3)


def _cpu_times() -> tuple[int, int] | None:
    text = _read_text(Path("/proc/stat"))
    first = text.splitlines()[0] if text else ""
    parts = first.split()
    if not parts or parts[0] != "cpu":
        return None
    values = [int(part) for part in parts[1:] if part.isdigit()]
    if len(values) < 5:
        return None
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    total = sum(values)
    return idle, total


def _cpu_percent(previous: tuple[int, int] | None, current: tuple[int, int] | None) -> float | None:
    if previous is None or current is None:
        return None
    idle_delta = current[0] - previous[0]
    total_delta = current[1] - previous[1]
    if total_delta <= 0:
        return None
    return round(max(0.0, min(100.0, 100.0 * (1.0 - idle_delta / total_delta))), 2)


def _cpu_model() -> str:
    for line in _read_text(Path("/proc/cpuinfo")).splitlines():
        if line.lower().startswith("model name"):
            return line.split(":", 1)[-1].strip() or "UNKNOWN"
    return os.uname().machine if hasattr(os, "uname") else "UNKNOWN"


def _cpu_status(previous: tuple[int, int] | None, current: tuple[int, int] | None) -> dict[str, Any]:
    try:
        load_1, load_5, load_15 = os.getloadavg()
    except Exception:
        load_1 = load_5 = load_15 = None
    return {
        "model": _cpu_model(),
        "logical_cores": os.cpu_count(),
        "total_usage_percent": _cpu_percent(previous, current),
        "load_average": [round(load_1, 3) if load_1 is not None else None, round(load_5, 3) if load_5 is not None else None, round(load_15, 3) if load_15 is not None else None],
        "load_average_1m": round(load_1, 3) if load_1 is not None else None,
        "load_average_5m": round(load_5, 3) if load_5 is not None else None,
        "load_average_15m": round(load_15, 3) if load_15 is not None else None,
        "per_core_usage_percent": [],
    }


def _memory_status() -> dict[str, Any]:
    values: dict[str, int] = {}
    for line in _read_text(Path("/proc/meminfo")).splitlines():
        if ":" not in line:
            continue
        key, rest = line.split(":", 1)
        fields = rest.strip().split()
        if fields:
            try:
                values[key] = int(fields[0]) * 1024
            except Exception:
                pass
    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    free = values.get("MemFree")
    used = total - (available if available is not None else free or 0) if total is not None else None
    percent = round(100.0 * used / total, 2) if total and used is not None else None
    return {
        "total_gb": _gb(total),
        "used_gb": _gb(used),
        "available_gb": _gb(available if available is not None else free),
        "usage_percent": percent,
    }


def _disk_status(root: Path) -> dict[str, Any]:
    try:
        usage = shutil.disk_usage(str(root))
        return {
            "path": str(root),
            "total_gb": _gb(usage.total),
            "used_gb": _gb(usage.used),
            "available_gb": _gb(usage.free),
            "usage_percent": round(100.0 * usage.used / usage.total, 2) if usage.total else None,
        }
    except Exception as exc:
        return {"path": str(root), "total_gb": None, "used_gb": None, "available_gb": None, "usage_percent": None, "error": str(exc)}


def _short_job_id(value: str | None) -> str:
    text = str(value or "").strip()
    if len(text) <= 14:
        return text
    return f"{text[:6]}...{text[-6:]}"


def _normal_status(value: Any) -> str:
    return str(value or "").strip().lower()


def _job_bucket(status: str) -> str | None:
    normalized = _normal_status(status)
    if normalized in ACTIVE_STATUSES:
        return "running"
    if normalized in QUEUED_STATUSES:
        return "queued"
    return None


def _is_gpu_job(record: dict[str, Any]) -> bool:
    text = " ".join(
        str(record.get(key) or "").lower()
        for key in ("resource_type", "queue_name", "device", "gpu", "gpu_id", "worker_type")
    )
    return "gpu" in text or "cuda" in text


def _gpu_index(record: dict[str, Any]) -> int | None:
    for key in ("gpu_index", "gpu_id", "device_id"):
        value = _int(record.get(key))
        if value is not None:
            return value
    device = str(record.get("device") or "")
    if "cuda:" in device:
        return _int(device.split("cuda:", 1)[-1].split(",", 1)[0])
    queue = str(record.get("queue_name") or "")
    if "gpu-0" in queue:
        return 0
    if "gpu-1" in queue:
        return 1
    return None


def _add_job(records: dict[str, dict[str, Any]], payload: dict[str, Any], status: str | None = None) -> None:
    job_id = str(payload.get("job_id") or payload.get("id") or "").strip()
    if not job_id:
        return
    item = dict(payload)
    if status:
        item["status"] = status
    records[job_id] = item


def _scan_file_jobs(root: Path, records: dict[str, dict[str, Any]]) -> None:
    jobs_root = root / "jobs"
    if not jobs_root.is_dir():
        return
    for job_json in jobs_root.glob("*/job.json"):
        try:
            payload = json.loads(job_json.read_text(encoding="utf-8"))
            status_path = job_json.with_name("status.json")
            status_payload = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
            if isinstance(status_payload, dict):
                payload.update({k: v for k, v in status_payload.items() if v not in ("", None)})
            _add_job(records, payload)
        except Exception:
            continue


def _scan_sqlite_jobs(root: Path, records: dict[str, dict[str, Any]]) -> None:
    sqlite_root = root / "sqlite"
    if not sqlite_root.is_dir():
        return
    for db_path in sqlite_root.rglob("*"):
        if not db_path.is_file() or db_path.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
            continue
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=1)
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    "SELECT job_id,status,resource_type,queue_name,worker_id,started_at,claimed_at,current_step,progress FROM jobs"
                ).fetchall()
            finally:
                conn.close()
            for row in rows:
                _add_job(records, dict(row))
        except Exception:
            continue


def _job_status(root: Path) -> tuple[dict[str, Any], dict[int, str]]:
    records: dict[str, dict[str, Any]] = {}
    _scan_sqlite_jobs(root, records)
    _scan_file_jobs(root, records)
    queued_cpu = running_cpu = queued_gpu = running_gpu = 0
    gpu_current: dict[int, str] = {}
    for record in records.values():
        bucket = _job_bucket(str(record.get("status") or ""))
        if bucket is None:
            continue
        is_gpu = _is_gpu_job(record)
        if is_gpu:
            if bucket == "queued":
                queued_gpu += 1
            else:
                running_gpu += 1
                index = _gpu_index(record)
                if index is not None and index not in gpu_current:
                    gpu_current[index] = _short_job_id(str(record.get("job_id") or ""))
        else:
            if bucket == "queued":
                queued_cpu += 1
            else:
                running_cpu += 1
    return (
        {
            "cpu_active_jobs": running_cpu,
            "cpu_queue_length": queued_cpu,
            "running_cpu_jobs": running_cpu,
            "queued_cpu_jobs": queued_cpu,
            "gpu_queue_length": queued_gpu,
            "running_gpu_jobs": running_gpu,
            "queued_gpu_jobs": queued_gpu,
        },
        gpu_current,
    )


def _unknown_gpu(index: int, gpu_current: dict[int, str]) -> dict[str, Any]:
    return {
        "index": index,
        "label": f"GPU{index}",
        "health": "UNKNOWN",
        "name": "UNKNOWN",
        "utilization_percent": None,
        "vram_used_mb": None,
        "vram_total_mb": None,
        "vram_free_mb": None,
        "temperature_c": None,
        "power_watts": None,
        "current_spashiny_job": gpu_current.get(index, ""),
        "queue_length": None,
        "lease_status": "RUNNING" if gpu_current.get(index) else "IDLE",
        "last_heartbeat_at": "",
        "queue_name": f"gpu-{index}",
    }


def _nvidia_smi(gpu_current: dict[int, str]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {f"gpu-{idx}": _unknown_gpu(idx, gpu_current) for idx in (0, 1)}
    command = [
        "nvidia-smi",
        "--query-gpu=index,uuid,name,utilization.gpu,memory.used,memory.total,memory.free,temperature.gpu,power.draw",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=5)
    except Exception:
        return rows
    if completed.returncode != 0:
        return rows
    for line in completed.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 9:
            continue
        index = _int(parts[0])
        if index is None:
            continue
        key = f"gpu-{index}"
        rows[key] = {
            "index": index,
            "label": f"GPU{index}",
            "health": "READY",
            "gpu_uuid": parts[1],
            "name": parts[2],
            "utilization_percent": _int(parts[3]),
            "vram_used_mb": _int(parts[4]),
            "vram_total_mb": _int(parts[5]),
            "vram_free_mb": _int(parts[6]),
            "temperature_c": _int(parts[7]),
            "power_watts": _float(parts[8]),
            "current_spashiny_job": gpu_current.get(index, ""),
            "queue_length": None,
            "lease_status": "RUNNING" if gpu_current.get(index) else "IDLE",
            "last_heartbeat_at": "",
            "queue_name": key,
        }
    return rows


def snapshot(root: Path, previous_cpu: tuple[int, int] | None = None, current_cpu: tuple[int, int] | None = None) -> dict[str, Any]:
    jobs, gpu_current = _job_status(root)
    return {
        "profile": "lab",
        "source": "host_resource_agent",
        "timestamp": _now(),
        "monitor_status": "HOST_AGENT",
        "cpu": _cpu_status(previous_cpu, current_cpu),
        "memory": _memory_status(),
        "disk": _disk_status(root),
        "jobs": jobs,
        "gpus": _nvidia_smi(gpu_current),
        "storage_backend": "local",
        "r2_enabled": False,
        "remote_provider_enabled": False,
    }


def _write_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def run(root: Path, cache: Path, interval: float, *, once: bool) -> int:
    previous = _cpu_times()
    time.sleep(0.2)
    current = _cpu_times()
    _write_atomic(cache, snapshot(root, previous, current))
    if once:
        return 0
    while True:
        previous = current
        time.sleep(max(1.0, float(interval)))
        current = _cpu_times()
        _write_atomic(cache, snapshot(root, previous, current))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write host CPU/RAM/GPU/job resource snapshots for SpaShiny Lab.")
    parser.add_argument("--root", default="/srv/spashiny")
    parser.add_argument("--cache", default="")
    parser.add_argument("--interval", type=float, default=3.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    cache = Path(args.cache).resolve() if args.cache else root / "logs" / "host_resource_status.json"
    return run(root, cache, args.interval, once=bool(args.once))


if __name__ == "__main__":
    raise SystemExit(main())
