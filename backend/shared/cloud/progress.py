from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .job_manager import JobManager, utc_now
from .remote_job_manager import RemoteJob, RemoteJobManager


class ProgressTracker:
    def __init__(self, jobs: JobManager | None = None, remote_jobs: RemoteJobManager | None = None) -> None:
        self.jobs = jobs or JobManager()
        self.remote_jobs = remote_jobs or RemoteJobManager()

    def sync_remote_status(self, job_id: str) -> dict[str, Any]:
        record = self.jobs.get_job(job_id)
        metadata_path = Path(record.local_workspace) / "cloud_job.json"
        if not metadata_path.exists():
            return {"status": record.status, "message": "Remote metadata is not available yet."}
        remote_job = RemoteJob.load(metadata_path)
        status = self.remote_jobs.read_status(remote_job) or {}
        if status:
            self.jobs.update_from_remote_status(job_id, status)
        return status

    def read_incremental_log(self, job_id: str) -> str:
        record = self.jobs.get_job(job_id)
        metadata_path = Path(record.local_workspace) / "cloud_job.json"
        if not metadata_path.exists():
            return ""
        remote_job = RemoteJob.load(metadata_path)
        text, _offset = self.remote_jobs.read_incremental_log(remote_job)
        if text:
            log_dir = Path(record.local_workspace) / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            with (log_dir / "run.log").open("a", encoding="utf-8") as handle:
                handle.write(text)
            self.jobs.add_event(job_id, "REMOTE", text[-1000:])
        return text

    def local_status_snapshot(self, job_id: str) -> dict[str, Any]:
        job = self.jobs.get_job(job_id)
        events = self.jobs.database.list_events(job_id, limit=40)
        return {"job": job.to_dict(), "events": events, "updated_at": utc_now()}
