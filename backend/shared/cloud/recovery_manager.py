from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .cleanup_coordinator import CleanupCoordinator, RUNNING_JOB_STATUSES
from .config import SpaShinyCloudConfig, load_cloud_config
from .database import CloudDatabase, utc_now
from .job_queue_repository import LEASE_ACTIVE, LEASE_RELEASED, JobQueueRepository
from .models import ACTIVE_JOB_STATUSES, JobStatus, SessionStatus, UploadStatus
from .worker_heartbeat import WorkerHeartbeatRepository


def coerce_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(str(value))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass
class RecoveryManager:
    database: CloudDatabase | None = None
    config: SpaShinyCloudConfig | None = None
    queue: JobQueueRepository | None = None
    heartbeat: WorkerHeartbeatRepository | None = None
    cleanup: CleanupCoordinator | None = None

    def __post_init__(self) -> None:
        if self.config is None:
            self.config = load_cloud_config()
        if self.database is None:
            self.database = CloudDatabase(config=self.config)
        if self.queue is None:
            self.queue = JobQueueRepository(self.database, self.config)
        if self.heartbeat is None:
            self.heartbeat = WorkerHeartbeatRepository(self.database, self.config)
        if self.cleanup is None:
            self.cleanup = CleanupCoordinator(database=self.database, config=self.config, queue=self.queue)

    def run_once(self) -> dict[str, Any]:
        lost_workers = self.heartbeat.mark_lost()
        leases = self.recover_leases()
        orphan_jobs = self.recover_orphan_jobs()
        stuck = self.recover_stuck_cancellations()
        invalid_sessions = self.recover_invalid_session_resources()
        orphans = self.cleanup.cleanup_orphan_resources()
        return {
            "lost_workers": lost_workers,
            "leases": leases,
            "orphan_jobs": orphan_jobs,
            "stuck_cancellations": stuck,
            "invalid_sessions": invalid_sessions,
            "orphans": orphans,
        }

    def recover_leases(self) -> list[str]:
        now = datetime.now(timezone.utc)
        recovered: list[str] = []
        for lease in self.queue.list_active_leases():
            job_id = str(lease["job_id"])
            try:
                job = self.database.get_job(job_id)
            except KeyError:
                self.queue.release_job_leases(job_id, status=LEASE_RELEASED)
                recovered.append(job_id)
                continue
            if job.status not in ACTIVE_JOB_STATUSES:
                self.queue.release_job_leases(job_id, status=LEASE_RELEASED)
                recovered.append(job_id)
                continue
            expires_at = coerce_utc(str(lease["expires_at"]))
            worker_active = self.heartbeat.is_worker_active(str(lease["worker_id"]))
            if expires_at >= now and worker_active:
                continue
            if worker_active:
                continue
            if job.status == JobStatus.CANCEL_REQUESTED.value:
                self.cleanup.cleanup_job(job.job_id, reason="stale_cancel")
            elif job.status in RUNNING_JOB_STATUSES:
                self.database.update_job(
                    job.job_id,
                    status=JobStatus.FAILED.value,
                    finished_at=utc_now(),
                    error_code="WORKER_LOST",
                    current_step="Worker lost",
                )
                self.queue.release_job_leases(job.job_id)
                self.cleanup.cleanup_job(job.job_id, reason="worker_lost")
            else:
                self.queue.release_job_leases(job.job_id)
            recovered.append(job_id)
        return recovered

    def recover_orphan_jobs(self) -> list[str]:
        recovered: list[str] = []
        for job in self.database.list_jobs(statuses=sorted(RUNNING_JOB_STATUSES), limit=10000):
            if not job.worker_id:
                continue
            if self.heartbeat.is_worker_active(job.worker_id):
                continue
            if job.status == JobStatus.CANCEL_REQUESTED.value:
                self.cleanup.cleanup_job(job.job_id, reason="orphan_cancel")
            else:
                self.database.update_job(
                    job.job_id,
                    status=JobStatus.FAILED.value,
                    finished_at=utc_now(),
                    error_code="WORKER_LOST",
                    current_step="Worker lost",
                )
                self.queue.release_job_leases(job.job_id)
                self.cleanup.cleanup_job(job.job_id, reason="orphan_worker")
            recovered.append(job.job_id)
        return recovered

    def recover_stuck_cancellations(self) -> list[str]:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=int(self.config.cancel_grace_seconds))
        recovered: list[str] = []
        for job in self.database.list_jobs(statuses=[JobStatus.CANCEL_REQUESTED.value], limit=10000):
            if not job.cancel_requested_at:
                continue
            try:
                requested_at = coerce_utc(job.cancel_requested_at)
            except Exception:
                requested_at = cutoff - timedelta(seconds=1)
            if requested_at <= cutoff:
                self.cleanup.cleanup_job(job.job_id, reason="cancel_grace_expired")
                recovered.append(job.job_id)
        return recovered

    def recover_invalid_session_resources(self) -> list[str]:
        recovered: list[str] = []
        invalid_sessions = {
            row["session_id"]
            for row in self.database.list_sessions_by_statuses([
                SessionStatus.ABANDONED.value,
                SessionStatus.CLEANING.value,
                SessionStatus.CLEANED.value,
            ])
        }
        for session_id in invalid_sessions:
            for job in self.database.list_jobs(session_id=session_id, statuses=sorted(ACTIVE_JOB_STATUSES), limit=10000):
                self.cleanup.cleanup_job(job.job_id, reason="invalid_session")
                recovered.append(job.job_id)
            for upload in self.database.list_uploads_for_cleanup(session_id):
                if upload.status in {
                    UploadStatus.INITIATED.value,
                    UploadStatus.UPLOADING.value,
                    UploadStatus.COMPLETING.value,
                    UploadStatus.ABORT_REQUESTED.value,
                    UploadStatus.DELETING.value,
                    UploadStatus.COMPLETED.value,
                }:
                    self.cleanup.cleanup_upload(upload.upload_id, reason="invalid_session")
                    recovered.append(upload.upload_id)
        return recovered
