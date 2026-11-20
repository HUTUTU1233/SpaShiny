from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


TERMINAL = {"completed", "failed", "cancelled", "timed_out"}
ALIGNMENT_LIGHT_QUEUE = "alignment_light"
ALIGNMENT_HEAVY_QUEUE = "alignment_heavy"
VALID_QUEUE_CLASSES = {ALIGNMENT_LIGHT_QUEUE, ALIGNMENT_HEAVY_QUEUE}
# Jobs submitted before Option C did not carry an explicit class.  They remain
# readable/downloadable as before; a legacy queued job is conservatively treated
# as heavy so it can never consume the preview-only worker.
LEGACY_QUEUE_CLASS = ALIGNMENT_HEAVY_QUEUE


def _jobs_root() -> Path:
    return Path(os.environ.get("SPASHINY_LOCAL_JOBS_ROOT") or os.environ.get("SPASHINY_TEMP_ROOT") or "/workspace/jobs")


def _worker_id() -> str:
    return str(os.environ.get("SPASHINY_WORKER_ID") or "spashiny-alignment-worker")


def _log(message: str) -> None:
    print(time.strftime("%Y-%m-%dT%H:%M:%S%z"), message, flush=True)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")


def _timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _epoch_from_status(value: str) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S%z"):
        try:
            return time.mktime(time.strptime(text, fmt))
        except Exception:
            pass
    return 0.0


def _created_epoch(job: dict[str, Any], job_json: Path) -> float:
    text = str(job.get("created_at") or job.get("queued_at") or "").strip()
    if text:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
        except ValueError:
            parsed = _epoch_from_status(text)
            if parsed:
                return parsed
    try:
        return job_json.stat().st_mtime
    except OSError:
        return 0.0


def _queue_class(job: dict[str, Any]) -> str:
    value = str(job.get("queue_class") or "").strip()
    if value in VALID_QUEUE_CLASSES:
        return value
    return LEGACY_QUEUE_CLASS


def _mark_failed(job: dict[str, Any], code: str, message: str) -> None:
    payload = {
        "job_id": job.get("job_id", ""),
        "task": job.get("task", ""),
        "workflow_id": job.get("workflow_id"),
        "owner_id": job.get("owner_id"),
        "analysis_session_id": job.get("analysis_session_id"),
        "queue_class": _queue_class(job),
        "worker_id": str(job.get("worker_id") or _worker_id()),
        "status": "failed",
        "error_code": code,
        "error_message": message,
        "updated_at": _timestamp(),
    }
    _write_json(Path(job["status_file"]), payload)
    _write_json(Path(job["output_dir"]) / "result_manifest.json", payload)


def _claim(job_dir: Path, stale_seconds: int, *, queue_class: str, worker_id: str) -> bool:
    lock = job_dir / "alignment_worker.lock"
    try:
        fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "pid": os.getpid(),
                    "worker_id": worker_id,
                    "queue_class": queue_class,
                    "claimed_at": _timestamp(),
                },
                handle,
                ensure_ascii=True,
                sort_keys=True,
            )
            handle.write("\n")
        return True
    except FileExistsError:
        try:
            if time.time() - lock.stat().st_mtime > stale_seconds:
                lock.unlink()
                return _claim(job_dir, stale_seconds, queue_class=queue_class, worker_id=worker_id)
        except Exception:
            pass
        return False


def _release(job_dir: Path) -> None:
    try:
        (job_dir / "alignment_worker.lock").unlink()
    except Exception:
        pass


def _record_claim(job_dir: Path, job: dict[str, Any], *, queue_class: str, worker_id: str) -> dict[str, Any]:
    job = dict(job)
    job["queue_class"] = queue_class
    # queue_name is the existing generic JobManager queue-field terminology.
    # Keeping both makes the alignment manifest explicit without creating a
    # second queue database.
    job["queue_name"] = queue_class
    job["worker_id"] = worker_id
    job["claimed_at"] = _timestamp()
    _write_json(job_dir / "job.json", job)
    status_path = Path(job["status_file"])
    status = _read_json(status_path)
    status.update(
        {
            "job_id": job.get("job_id", ""),
            "task": job.get("task", ""),
            "workflow_id": job.get("workflow_id"),
            "owner_id": job.get("owner_id"),
            "analysis_session_id": job.get("analysis_session_id"),
            "queue_class": queue_class,
            "worker_id": worker_id,
            "claimed_at": job["claimed_at"],
        }
    )
    _write_json(status_path, status)
    return job


def _run_job(job_dir: Path, *, queue_class: str, worker_id: str) -> None:
    job_json = job_dir / "job.json"
    job = _read_json(job_json)
    if not job:
        return
    job = _record_claim(job_dir, job, queue_class=queue_class, worker_id=worker_id)
    log_file = Path(str(job.get("log_file") or (Path(job.get("output_dir", "/workspace/results")) / "alignment_worker.log")))
    log_file.parent.mkdir(parents=True, exist_ok=True)
    _log(f"claimed {queue_class} job {job.get('job_id')} task={job.get('task')} worker_id={worker_id}")
    with log_file.open("ab") as log_handle:
        proc = subprocess.run(
            [sys.executable, "-m", "cloud.alignment_worker", "--job", str(job_json)],
            cwd=str(Path(__file__).resolve().parents[1]),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            env=os.environ.copy(),
        )
    if proc.returncode != 0:
        latest = _read_json(Path(job["status_file"]))
        if str(latest.get("status") or "").lower() not in TERMINAL:
            _mark_failed(job, "ALIGNMENT_WORKER_EXITED", f"Alignment worker exited with code {proc.returncode}. See {log_file}.")
    _log(f"finished {queue_class} job {job.get('job_id')} rc={proc.returncode} worker_id={worker_id}")


def _handle_stale_running(job_dir: Path, stale_seconds: int) -> None:
    job = _read_json(job_dir / "job.json")
    status = _read_json(job_dir / "status.json")
    if not job or str(status.get("status") or "").lower() != "running":
        return
    updated = _epoch_from_status(str(status.get("updated_at") or ""))
    if updated and time.time() - updated > stale_seconds:
        _mark_failed(job, "ALIGNMENT_WORKER_STALE", f"Alignment worker heartbeat is stale for more than {stale_seconds} seconds.")
        _release(job_dir)


@dataclass(frozen=True)
class _Candidate:
    job_json: Path
    job: dict[str, Any]
    created_epoch: float
    owner_id: str


def _queued_candidates(queue_class: str, stale_seconds: int) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    for job_json in _jobs_root().glob("alignment_*_*/job.json"):
        job_dir = job_json.parent
        job = _read_json(job_json)
        if not job or _queue_class(job) != queue_class:
            continue
        status = _read_json(job_dir / "status.json")
        state = str(status.get("status") or "").lower()
        if state == "running":
            _handle_stale_running(job_dir, stale_seconds)
            continue
        if state != "queued":
            continue
        candidates.append(
            _Candidate(
                job_json=job_json,
                job=job,
                created_epoch=_created_epoch(job, job_json),
                owner_id=str(job.get("owner_id") or job.get("session_id") or "legacy-unowned"),
            )
        )
    return sorted(candidates, key=lambda item: (item.created_epoch, str(item.job.get("job_id") or "")))


def _select_fair_candidate(candidates: list[_Candidate], last_owner_id: str | None) -> _Candidate | None:
    if not candidates:
        return None
    # Each owner contributes its oldest queued job. Owners are ordered by their
    # earliest job, then rotated after the owner most recently served. This
    # preserves FIFO within an owner while preventing one owner from starving
    # another queue participant.
    oldest_by_owner: dict[str, _Candidate] = {}
    for candidate in candidates:
        oldest_by_owner.setdefault(candidate.owner_id, candidate)
    owners = list(oldest_by_owner)
    if last_owner_id in owners and len(owners) > 1:
        owner = owners[(owners.index(last_owner_id) + 1) % len(owners)]
    else:
        owner = owners[0]
    return oldest_by_owner[owner]


def run_once(stale_seconds: int, queue_class: str, *, last_owner_id: str | None = None) -> tuple[bool, str | None]:
    candidate = _select_fair_candidate(_queued_candidates(queue_class, stale_seconds), last_owner_id)
    if candidate is None:
        return False, last_owner_id
    worker_id = _worker_id()
    job_dir = candidate.job_json.parent
    if not _claim(job_dir, stale_seconds, queue_class=queue_class, worker_id=worker_id):
        return False, last_owner_id
    try:
        _run_job(job_dir, queue_class=queue_class, worker_id=worker_id)
        return True, candidate.owner_id
    finally:
        _release(job_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a single class of queued SpaShiny Alignment jobs outside the Shiny web process.")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--queue-class", choices=sorted(VALID_QUEUE_CLASSES), required=True)
    parser.add_argument("--interval", type=float, default=float(os.environ.get("SPASHINY_ALIGNMENT_WORKER_INTERVAL_SECONDS") or 3))
    parser.add_argument("--stale-seconds", type=int, default=int(os.environ.get("SPASHINY_ALIGNMENT_WORKER_STALE_SECONDS") or 600))
    args = parser.parse_args(argv)
    last_owner_id: str | None = None
    if args.once:
        run_once(args.stale_seconds, args.queue_class, last_owner_id=last_owner_id)
        return 0
    _log(f"alignment {args.queue_class} queue worker started worker_id={_worker_id()}")
    while True:
        did_work, last_owner_id = run_once(
            args.stale_seconds,
            args.queue_class,
            last_owner_id=last_owner_id,
        )
        if not did_work:
            time.sleep(max(1.0, float(args.interval)))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
