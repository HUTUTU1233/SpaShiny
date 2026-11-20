from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .cleanup_retry_repository import CleanupRetryRepository, redact_cleanup_message
from .config import SpaShinyCloudConfig, load_cloud_config
from .database import CloudDatabase, utc_now
from .executor_registry import ExecutorRegistry
from .job_queue_repository import JobQueueRepository
from .local_workspace_manager import LocalWorkspaceError, LocalWorkspaceManager
from .models import ACTIVE_JOB_STATUSES, JobStatus, SessionStatus, TERMINAL_STATUSES, UploadStatus
from .runpod_lifecycle_manager import RunPodLifecycleManager
from .session_manager import SessionManager
from .storage_quota import StorageQuotaManager
from .upload_service import UploadService


QUEUED_JOB_STATUSES = {
    JobStatus.CREATED.value,
    JobStatus.VALIDATING.value,
    JobStatus.QUEUED.value,
    JobStatus.QUEUED_CPU.value,
    JobStatus.QUEUED_GPU.value,
    JobStatus.WAITING_FOR_GPU.value,
}

RUNNING_JOB_STATUSES = {
    JobStatus.STARTING.value,
    JobStatus.STARTING_GPU.value,
    JobStatus.UPLOADING.value,
    JobStatus.REMOTE_STARTING.value,
    JobStatus.RUNNING.value,
    JobStatus.REMOTE_UNREACHABLE.value,
    JobStatus.POSTPROCESSING.value,
    JobStatus.SYNCING.value,
    JobStatus.DOWNLOADING.value,
    JobStatus.VERIFYING.value,
    JobStatus.PACKAGING.value,
    JobStatus.CANCEL_REQUESTED.value,
    JobStatus.CANCELLING.value,
}


@dataclass
class CleanupCoordinator:
    database: CloudDatabase | None = None
    config: SpaShinyCloudConfig | None = None
    sessions: SessionManager | None = None
    queue: JobQueueRepository | None = None
    uploads: UploadService | None = None
    registry: ExecutorRegistry | None = None
    workspace: LocalWorkspaceManager | None = None
    retries: CleanupRetryRepository | None = None
    runpod_lifecycle: RunPodLifecycleManager | None = None
    storage_quota: StorageQuotaManager | None = None

    def __post_init__(self) -> None:
        if self.config is None:
            self.config = load_cloud_config()
        if self.database is None:
            self.database = CloudDatabase(config=self.config)
        if self.sessions is None:
            self.sessions = SessionManager(database=self.database, config=self.config)
        if self.queue is None:
            self.queue = JobQueueRepository(self.database, self.config)
        if self.uploads is None:
            self.uploads = UploadService(database=self.database, config=self.config)
        if self.registry is None:
            self.registry = ExecutorRegistry(config=self.config)
        if self.workspace is None:
            self.workspace = LocalWorkspaceManager(self.config)
        if self.retries is None:
            self.retries = CleanupRetryRepository(self.database, self.config)
        if self.runpod_lifecycle is None:
            self.runpod_lifecycle = RunPodLifecycleManager(database=self.database, config=self.config, queue=self.queue)
        if self.storage_quota is None:
            self.storage_quota = StorageQuotaManager(database=self.database, config=self.config, storage=self.uploads.storage)

    def request_session_cleanup(self, session_id: str, reason: str = "requested") -> dict[str, Any]:
        self._ensure_abandoned(session_id, reason)
        session = self.sessions.mark_cleaning(session_id)
        self._event(session_id, "session", session_id, "cleanup_requested", "OK", message=reason)
        return {"session_id": session.session_id, "status": session.status, "cleanup_requested": True}

    def cleanup_session(self, session_id: str, reason: str = "cleanup") -> dict[str, Any]:
        session = self._ensure_abandoned(session_id, reason)
        if session.status == SessionStatus.CLEANED.value:
            return {"session_id": session_id, "status": SessionStatus.CLEANED.value, "ok": True}
        session = self.sessions.mark_cleaning(session_id)
        ok = True

        for job in self.database.list_jobs(session_id=session_id, limit=10000):
            ok = self.cleanup_job(job.job_id, reason=reason) and ok

        for upload in self.database.list_uploads_for_cleanup(session_id):
            ok = self.cleanup_upload(upload.upload_id, reason=reason) and ok

        ok = self._delete_session_prefix(session_id) and ok
        ok = self._release_session_leases(session_id) and ok
        ok = self._delete_session_workspace(session_id) and ok

        if ok:
            session = self.sessions.mark_cleaned(session_id)
            self._event(session_id, "session", session_id, "cleanup_session", "OK", message="cleaned")
            return {"session_id": session_id, "status": session.status, "ok": True}
        self._event(session_id, "session", session_id, "cleanup_session", "RETRY_WAIT", error_code="CLEANUP_INCOMPLETE")
        return {"session_id": session_id, "status": self.sessions.get_session(session_id).status, "ok": False}

    def cleanup_job(self, job_id: str, reason: str = "cleanup") -> bool:
        try:
            job = self.database.get_job(job_id)
        except KeyError:
            return True
        ok = True
        if job.status in QUEUED_JOB_STATUSES:
            self.database.update_job(job.job_id, status=JobStatus.CANCELLED.value, cancel_requested_at=utc_now(), finished_at=utc_now(), error_code="SESSION_CLEANUP")
            self._release_result_reservation(job.job_id, "RELEASED", "queued job cancelled during cleanup")
        elif job.status in RUNNING_JOB_STATUSES:
            try:
                if job.status != JobStatus.CANCEL_REQUESTED.value:
                    job = self.database.update_job(job.job_id, status=JobStatus.CANCEL_REQUESTED.value, cancel_requested_at=utc_now(), error_code="SESSION_CLEANUP")
                self.registry.request_cancel(job)
                self.registry.terminate(job)
                self.queue.release_job_leases(job.job_id)
                self._finish_attempts(job.job_id, JobStatus.CANCELLED.value, "SESSION_CLEANUP", "Job cancelled during cleanup.")
                self.database.update_job(job.job_id, status=JobStatus.CANCELLED.value, finished_at=utc_now(), current_step="Cancelled during cleanup")
                self._release_result_reservation(job.job_id, "RELEASED", "running job cancelled during cleanup")
            except Exception as exc:
                ok = False
                self._record_failure("job", job.job_id, "cancel_job", job.session_id or "", "JOB_CANCEL_FAILED", exc)
        elif job.status in TERMINAL_STATUSES:
            self.queue.release_job_leases(job.job_id)
            if job.status != JobStatus.SUCCEEDED.value:
                self._release_result_reservation(job.job_id, "RELEASED", f"terminal job cleanup: {job.status}")

        if not self._terminate_runpod_instances(job.job_id, job.session_id or ""):
            ok = False

        try:
            self.registry.cleanup(job)
        except Exception as exc:
            ok = False
            self._record_failure("job", job.job_id, "executor_cleanup", job.session_id or "", "EXECUTOR_CLEANUP_FAILED", exc)

        if not self._delete_job_workspace(job.job_id, job.local_workspace, job.session_id or ""):
            ok = False
        self._event(job.session_id or "", "job", job.job_id, "cleanup_job", "OK" if ok else "RETRY_WAIT")
        return ok

    def cleanup_upload(self, upload_id: str, reason: str = "cleanup") -> bool:
        try:
            record = self.database.get_upload(upload_id)
        except KeyError:
            return True
        if record.status in {UploadStatus.ABORTED.value, UploadStatus.DELETED.value}:
            return True
        try:
            if record.status in {UploadStatus.COMPLETED.value, UploadStatus.DELETING.value} or record.completed_at:
                self.database.update_upload(record.upload_id, status=UploadStatus.DELETING.value)
                self.uploads.storage.delete_object(record.object_key)
                self.uploads.quota.record_object_deleted(object_key=record.object_key, size_bytes=record.actual_size_bytes)
                if record.actual_size_bytes:
                    self.database.add_session_upload_bytes(record.session_id, -int(record.actual_size_bytes))
                self.database.update_upload(record.upload_id, status=UploadStatus.DELETED.value, aborted_at=utc_now(), error_code=None)
            else:
                self.database.update_upload(record.upload_id, status=UploadStatus.ABORT_REQUESTED.value)
                self.uploads.storage.abort_multipart_upload(
                    object_key=record.object_key,
                    multipart_upload_id=record.multipart_upload_id,
                )
                reservation_id = self.uploads._reservation_id(record)
                if reservation_id:
                    self.uploads.quota.release_reservation(reservation_id, status="RELEASED")
                self.database.update_upload(record.upload_id, status=UploadStatus.ABORTED.value, aborted_at=utc_now(), error_code=None)
            self._event(record.session_id, "upload", record.upload_id, "cleanup_upload", "OK")
            return True
        except Exception as exc:
            self.database.update_upload(record.upload_id, error_code="CLEANUP_RETRY")
            self._record_failure("upload", record.upload_id, "cleanup_upload", record.session_id, "UPLOAD_CLEANUP_FAILED", exc)
            self._event(record.session_id, "upload", record.upload_id, "cleanup_upload", "RETRY_WAIT", "UPLOAD_CLEANUP_FAILED", exc)
            return False

    def cleanup_orphan_resources(self) -> dict[str, Any]:
        valid_session_ids = {row["session_id"] for row in self.database.list_sessions_by_statuses([
            SessionStatus.ACTIVE.value,
            SessionStatus.DISCONNECTED.value,
            SessionStatus.ABANDONED.value,
            SessionStatus.CLEANING.value,
            SessionStatus.CLEANED.value,
        ])}
        valid_job_ids = {job.job_id for job in self.database.list_jobs(limit=100000)}
        removed = self.workspace.scan_orphan_workspaces(
            valid_session_ids=valid_session_ids,
            valid_job_ids=valid_job_ids,
            min_age_seconds=int(self.config.orphan_workspace_min_age_seconds),
        )
        return {"removed_workspaces": removed}

    def retry_cleanup(self, retry: dict[str, Any]) -> bool:
        retry = self.retries.mark_running(int(retry["id"]))
        try:
            resource_type = str(retry["resource_type"])
            action = str(retry["action"])
            resource_id = str(retry["resource_id"])
            session_id = str(retry["session_id"] or "")
            if resource_type == "job":
                ok = self.cleanup_job(resource_id, reason="retry")
            elif resource_type == "upload":
                ok = self.cleanup_upload(resource_id, reason="retry")
            elif resource_type == "object_prefix":
                ok = self._delete_session_prefix(session_id or resource_id)
            elif resource_type == "workspace_session":
                ok = self._delete_session_workspace(session_id or resource_id)
            elif resource_type == "workspace_job":
                ok = self._delete_job_workspace(resource_id, "", session_id)
            elif resource_type == "lease":
                ok = self.queue.release_job_leases(resource_id) >= 0
            elif resource_type == "runpod_instance":
                self.runpod_lifecycle.terminate_instance(resource_id, reason="cleanup_retry")
                ok = True
            elif resource_type == "runpod_provider_pod":
                ok = self.runpod_lifecycle.terminate_provider_pod(resource_id, session_id=session_id, action="cleanup_retry")
            elif resource_type == "result_reservation":
                self._release_result_reservation(resource_id, "RELEASED", "cleanup retry")
                ok = True
            else:
                ok = True
            if ok:
                self.retries.mark_completed(int(retry["id"]))
                return True
            self.retries.mark_failed(retry, error_code="CLEANUP_RETRY_FAILED", error_message="Retry action did not complete.")
            return False
        except Exception as exc:
            self.retries.mark_failed(retry, error_code="CLEANUP_RETRY_FAILED", error_message=exc)
            return False

    def run_due_retries(self) -> list[int]:
        completed: list[int] = []
        for retry in self.retries.due():
            if self.retry_cleanup(retry):
                completed.append(int(retry["id"]))
        return completed

    def _ensure_abandoned(self, session_id: str, reason: str):
        session = self.sessions.get_session(session_id)
        if session.status in {SessionStatus.ACTIVE.value, SessionStatus.DISCONNECTED.value}:
            with self.database.connect() as conn:
                conn.execute(
                    """
                    UPDATE sessions
                    SET status=?, abandoned_at=COALESCE(abandoned_at, ?)
                    WHERE session_id=? AND status IN (?, ?)
                    """,
                    (
                        SessionStatus.ABANDONED.value,
                        utc_now(),
                        session_id,
                        SessionStatus.ACTIVE.value,
                        SessionStatus.DISCONNECTED.value,
                    ),
                )
            self._event(session_id, "session", session_id, "abandon", "OK", message=reason)
        return self.sessions.get_session(session_id)

    def _delete_session_prefix(self, session_id: str) -> bool:
        try:
            self.uploads.delete_session_prefix(session_id)
            self._event(session_id, "object_prefix", session_id, "delete_prefix", "OK")
            return True
        except Exception as exc:
            self._record_failure("object_prefix", session_id, "delete_prefix", session_id, "PREFIX_DELETE_FAILED", exc)
            self._event(session_id, "object_prefix", session_id, "delete_prefix", "RETRY_WAIT", "PREFIX_DELETE_FAILED", exc)
            return False

    def _delete_session_workspace(self, session_id: str) -> bool:
        try:
            self.workspace.delete_session_workspace(session_id)
            self._event(session_id, "workspace_session", session_id, "delete_workspace", "OK")
            return True
        except Exception as exc:
            self._record_failure("workspace_session", session_id, "delete_workspace", session_id, "WORKSPACE_DELETE_FAILED", exc)
            return False

    def _delete_job_workspace(self, job_id: str, local_workspace: str, session_id: str) -> bool:
        try:
            if local_workspace:
                try:
                    self.workspace.delete_controlled_path(local_workspace)
                except LocalWorkspaceError:
                    self.workspace.delete_job_workspace(job_id)
            else:
                self.workspace.delete_job_workspace(job_id)
            self._event(session_id, "workspace_job", job_id, "delete_workspace", "OK")
            return True
        except Exception as exc:
            self._record_failure("workspace_job", job_id, "delete_workspace", session_id, "WORKSPACE_DELETE_FAILED", exc)
            return False

    def _release_session_leases(self, session_id: str) -> bool:
        try:
            self.queue.release_session_leases(session_id)
            self.storage_quota.release_session_reservations(session_id, status="RELEASED")
            self._event(session_id, "lease", session_id, "release_session_leases", "OK")
            return True
        except Exception as exc:
            self._record_failure("lease", session_id, "release_session_leases", session_id, "LEASE_RELEASE_FAILED", exc)
            return False

    def _terminate_runpod_instances(self, job_id: str, session_id: str) -> bool:
        ok = True
        for instance in self.database.list_runpod_instances(job_id=job_id, active_only=True, limit=100):
            if str(instance.get("session_id") or "") != str(session_id or ""):
                ok = False
                self._record_failure("runpod_instance", str(instance["instance_id"]), "terminate_instance", session_id, "SESSION_MISMATCH", "RunPod instance session mismatch.")
                continue
            try:
                self.runpod_lifecycle.terminate_instance(str(instance["instance_id"]), reason="cleanup")
            except Exception as exc:
                ok = False
                self._record_failure("runpod_instance", str(instance["instance_id"]), "terminate_instance", session_id, "RUNPOD_TERMINATE_FAILED", exc)
        return ok

    def _finish_attempts(self, job_id: str, status: str, error_code: str = "", error_message: str = "") -> None:
        with self.database.connect() as conn:
            conn.execute(
                """
                UPDATE job_attempts
                SET status=?, finished_at=?, error_code=?, error_message=?
                WHERE job_id=? AND finished_at IS NULL
                """,
                (status, utc_now(), error_code, redact_cleanup_message(error_message), job_id),
            )

    def _record_failure(
        self,
        resource_type: str,
        resource_id: str,
        action: str,
        session_id: str,
        error_code: str,
        error_message: object,
    ) -> None:
        self.retries.record_failure(
            resource_type=resource_type,
            resource_id=resource_id,
            session_id=session_id,
            action=action,
            error_code=error_code,
            error_message=error_message,
        )

    def _release_result_reservation(self, job_id: str, status: str, error_message: object = "") -> None:
        try:
            self.storage_quota.release_result_reservation_for_job(job_id, status=status, error_message=error_message)
        except Exception as exc:
            try:
                job = self.database.get_job(job_id)
                self._record_failure("result_reservation", job_id, "release_result_reservation", job.session_id or "", "RESULT_RESERVATION_RELEASE_FAILED", exc)
            except Exception:
                return

    def _event(
        self,
        session_id: str,
        resource_type: str,
        resource_id: str,
        action: str,
        status: str,
        error_code: str = "",
        message: object = "",
    ) -> None:
        self.database.record_cleanup_event(
            session_id=session_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            status=status,
            error_code=redact_cleanup_message(error_code, max_length=64),
            message=redact_cleanup_message(message),
        )
