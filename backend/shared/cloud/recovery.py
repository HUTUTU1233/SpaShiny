from __future__ import annotations

from pathlib import Path
from typing import Any

from .database import CloudDatabase
from .job_manager import JobManager
from .models import GPU_ACTIVE_STATUSES, JobStatus, TERMINAL_STATUSES
from .progress import ProgressTracker
from .remote_job_manager import RemoteJob


class RecoveryManager:
    def __init__(
        self,
        database: CloudDatabase | None = None,
        jobs: JobManager | None = None,
        progress: ProgressTracker | None = None,
    ) -> None:
        self.database = database or CloudDatabase()
        self.jobs = jobs or JobManager(database=self.database)
        self.progress = progress or ProgressTracker(jobs=self.jobs)

    def recover_active_jobs(self) -> list[dict[str, Any]]:
        recovered = []
        active = self.database.list_jobs(statuses=list(GPU_ACTIVE_STATUSES), limit=10000)
        for job in active:
            try:
                status = self.progress.sync_remote_status(job.job_id)
                if status:
                    recovered.append({"job_id": job.job_id, "status": status.get("status"), "recovered": True})
                else:
                    recovered.append({"job_id": job.job_id, "status": job.status, "recovered": False})
            except Exception as exc:
                self.database.update_job(
                    job.job_id,
                    status=JobStatus.INTERRUPTED.value,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
                recovered.append({"job_id": job.job_id, "status": JobStatus.INTERRUPTED.value, "error": str(exc)})
        return recovered

    def resume_downloading_jobs(self) -> list[str]:
        resumed = []
        jobs = self.database.list_jobs(statuses=[JobStatus.DOWNLOADING.value], limit=10000)
        for job in jobs:
            manifest = Path(job.local_workspace) / "result_manifest.json"
            if manifest.exists():
                self.jobs.mark_succeeded(job.job_id, result_synced=True)
                resumed.append(job.job_id)
        return resumed
