from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .config import SpaShinyCloudConfig, load_cloud_config
from .database import CloudDatabase, utc_now
from .input_resolver import InputResolverError, verify_worker_callback_token
from .job_queue_repository import JobQueueRepository
from .models import JobRecord, JobStatus, TERMINAL_STATUSES
from .runpod_lifecycle_manager import RunPodLifecycleManager
from .storage_quota import StorageQuotaManager


class WorkerCallbackError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = int(status_code)


@dataclass
class WorkerCallbackService:
    database: CloudDatabase | None = None
    config: SpaShinyCloudConfig | None = None
    queue: JobQueueRepository | None = None
    lifecycle: RunPodLifecycleManager | None = None
    result_quota: StorageQuotaManager | None = None

    def __post_init__(self) -> None:
        if self.config is None:
            self.config = load_cloud_config()
        if self.database is None:
            self.database = CloudDatabase(config=self.config)
        if self.queue is None:
            self.queue = JobQueueRepository(self.database, self.config)
        if self.lifecycle is None:
            self.lifecycle = RunPodLifecycleManager(database=self.database, config=self.config, queue=self.queue)
        if self.result_quota is None:
            self.result_quota = StorageQuotaManager(database=self.database, config=self.config)

    def handle_callback(
        self,
        *,
        job_id: str,
        worker_id: str,
        callback_token: str,
        payload: dict[str, Any],
    ) -> JobRecord:
        try:
            job = self.database.get_job(job_id)
        except KeyError as exc:
            raise WorkerCallbackError("JOB_NOT_FOUND", "Job was not found.", status_code=404) from exc
        if str(worker_id or "") != str(job.worker_id or ""):
            raise WorkerCallbackError("WORKER_NOT_ALLOWED", "Worker id does not match the job claim.", status_code=403)
        try:
            verify_worker_callback_token(callback_token, job, config=self.config)
        except InputResolverError as exc:
            raise WorkerCallbackError("CALLBACK_TOKEN_INVALID", str(exc), status_code=403) from exc
        if job.status in TERMINAL_STATUSES:
            return job
        status = str(payload.get("status") or "").upper()
        if not status:
            raise WorkerCallbackError("INVALID_CALLBACK", "Callback status is required.", status_code=422)
        if status in {JobStatus.SUCCEEDED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value, JobStatus.TIMED_OUT.value}:
            return self._finish_terminal(job, payload, status)
        return self._update_progress(job, payload, status)

    def _update_progress(self, job: JobRecord, payload: dict[str, Any], status: str) -> JobRecord:
        updates = self._progress_updates(payload)
        updates["metadata_json"] = self._merge_metadata(
            job.metadata_json,
            {"worker_last_callback": self._callback_metadata(payload, status=status)},
        )
        try:
            updated = self.database.update_job(job.job_id, status=status, **updates)
        except ValueError:
            updated = self.database.update_job(job.job_id, **updates)
        self.queue.renew_lease(updated.job_id, updated.worker_id)
        return updated

    def _finish_terminal(self, job: JobRecord, payload: dict[str, Any], status: str) -> JobRecord:
        metadata = {
            "worker_last_callback": self._callback_metadata(payload, status=status),
            "worker_outputs": payload.get("output_objects") or payload.get("outputs") or [],
            "worker_checkpoints": payload.get("checkpoints") or [],
            "result_manifest": payload.get("result_manifest") or {},
        }
        if status == JobStatus.SUCCEEDED.value:
            self._commit_result_reservation(job, payload)
            updated = self._transition_to_success(job, payload, metadata)
        else:
            updated = self.database.update_job(
                job.job_id,
                status=status,
                finished_at=utc_now(),
                error_code=str(payload.get("error_code") or status),
                error_message=str(payload.get("message") or payload.get("error_message") or status)[:1000],
                current_step=str(payload.get("current_step") or status),
                metadata_json=self._merge_metadata(job.metadata_json, metadata),
            )
            self._release_result_reservation(job, status)
        self._terminate_compute_instance(job, reason=f"worker_callback_{status.lower()}")
        if job.worker_id:
            self.queue.release_lease(job.job_id, job.worker_id)
        self._finish_attempt(job.job_id, status, str(payload.get("error_code") or ""), str(payload.get("message") or ""))
        return updated

    def _transition_to_success(self, job: JobRecord, payload: dict[str, Any], metadata: dict[str, Any]) -> JobRecord:
        current = self.database.get_job(job.job_id)
        if current.status not in {JobStatus.VERIFYING.value, JobStatus.PACKAGING.value}:
            try:
                current = self.database.update_job(
                    job.job_id,
                    status=JobStatus.VERIFYING.value,
                    current_step="Verifying worker callback",
                )
            except ValueError:
                current = self.database.get_job(job.job_id)
        try:
            current = self.database.update_job(
                job.job_id,
                status=JobStatus.PACKAGING.value,
                current_step="Registering uploaded results",
            )
        except ValueError:
            current = self.database.get_job(job.job_id)
        return self.database.update_job(
            job.job_id,
            status=JobStatus.SUCCEEDED.value,
            finished_at=utc_now(),
            progress=100.0,
            current_step=str(payload.get("current_step") or "Completed"),
            message=str(payload.get("message") or "Worker completed."),
            metadata_json=self._merge_metadata(current.metadata_json, metadata),
            result_synced=True,
        )

    def _progress_updates(self, payload: dict[str, Any]) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        if payload.get("progress") is not None:
            updates["progress"] = max(0.0, min(100.0, float(payload.get("progress") or 0.0)))
        if payload.get("current_step") is not None:
            updates["current_step"] = str(payload.get("current_step") or "")[:500]
        if payload.get("message") is not None:
            updates["message"] = str(payload.get("message") or "")[:1000]
        if payload.get("gpu_name") is not None:
            updates["gpu_name"] = str(payload.get("gpu_name") or "")[:200]
        if payload.get("device") is not None:
            updates["device"] = str(payload.get("device") or "")[:200]
        return updates

    def _callback_metadata(self, payload: dict[str, Any], *, status: str) -> dict[str, Any]:
        return {
            "status": status,
            "progress": payload.get("progress"),
            "current_step": payload.get("current_step") or "",
            "message": payload.get("message") or "",
            "updated_at": utc_now(),
        }

    def _commit_result_reservation(self, job: JobRecord, payload: dict[str, Any]) -> None:
        actual = 0
        for item in payload.get("output_objects") or payload.get("outputs") or []:
            if isinstance(item, dict):
                actual += max(0, int(item.get("size_bytes") or 0))
        try:
            self.result_quota.commit_result_reservation_for_job(job.job_id, actual_bytes=actual)
        except Exception:
            return None

    def _release_result_reservation(self, job: JobRecord, status: str) -> None:
        try:
            self.result_quota.release_result_reservation_for_job(job.job_id, status="RELEASED", error_message=status)
        except Exception:
            return None

    def _terminate_compute_instance(self, job: JobRecord, *, reason: str) -> None:
        instance = self.database.get_runpod_instance_by_job(job.job_id, active_only=True)
        if instance is None:
            return
        try:
            self.lifecycle.terminate_instance(str(instance["instance_id"]), reason=reason)
        except Exception:
            return None

    def _finish_attempt(self, job_id: str, status: str, error_code: str = "", error_message: str = "") -> None:
        with self.database.connect() as conn:
            conn.execute(
                """
                UPDATE job_attempts
                SET status=?, finished_at=?, error_code=?, error_message=?
                WHERE job_id=?
                AND finished_at IS NULL
                """,
                (status, utc_now(), error_code, error_message, job_id),
            )

    def _merge_metadata(self, metadata_json: str, values: dict[str, Any]) -> str:
        try:
            data = json.loads(metadata_json or "{}")
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}
        data.update(values)
        return json.dumps(data, ensure_ascii=False, sort_keys=True)
