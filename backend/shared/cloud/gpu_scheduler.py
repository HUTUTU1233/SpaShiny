from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import SpaShinyCloudConfig, load_cloud_config
from .database import CloudDatabase, utc_now
from .job_manager import JobManager
from .models import JobStatus
from .remote_job_manager import RemoteJob, RemoteJobManager
from .result_sync import delete_result_artifacts, result_artifact_size_bytes, verify_conditional_vae_outputs
from .runpod_manager import RunPodManager
from .storage_quota import GlobalStorageLimitExceeded, StorageQuotaManager


class GPUScheduler:
    """Single-GPU scheduler used by phase 2.

    Stage 3 will replace the local JSON metadata with the jobs database and a
    proper queue. This class already exposes the method names requested by the
    deployment plan so the UI can move over incrementally.
    """

    def __init__(
        self,
        config: SpaShinyCloudConfig | None = None,
        runpod_manager: RunPodManager | None = None,
        remote_jobs: RemoteJobManager | None = None,
        jobs: JobManager | None = None,
        quota: StorageQuotaManager | None = None,
    ) -> None:
        self.config = config or load_cloud_config()
        self.runpod_manager = runpod_manager or RunPodManager(self.config)
        self.jobs = jobs or JobManager(database=CloudDatabase(config=self.config))
        self.quota = quota or StorageQuotaManager(database=self.jobs.database, config=self.config)
        self.remote_jobs = remote_jobs or RemoteJobManager(self.config, self.runpod_manager, database=self.jobs.database, quota=self.quota)

    def prepare_gpu(self, job_id: str) -> dict[str, Any]:
        pod = self.runpod_manager.ensure_pod_running()
        ssh_info = self.runpod_manager.wait_for_ssh_ready()
        env = self.runpod_manager.check_gpu_available()
        return {"job_id": job_id, "pod": pod, "ssh": ssh_info, "environment": env}

    def submit_conditional_vae_job(
        self,
        *,
        input_h5ad: Path,
        parameters: dict[str, Any],
        user_id: str = "default",
        wait: bool = False,
    ) -> RemoteJob:
        job = self.remote_jobs.create_conditional_vae_job(
            input_h5ad=input_h5ad,
            parameters=parameters,
            user_id=user_id,
        )
        self.prepare_gpu(job.job_id)
        self.remote_jobs.upload_job(job)
        self.remote_jobs.start_remote_job(job)
        if wait:
            self.remote_jobs.monitor_until_finished(job)
            self.remote_jobs.synchronize_results(job)
        return job

    def submit_gpu_job(self, job_id: str) -> None:
        job = self._load_job(job_id)
        succeeded = False
        try:
            self.jobs.database.update_job(job_id, status=JobStatus.STARTING_GPU.value)
            try:
                self.quota.reserve_result_storage_for_job(job_id)
            except GlobalStorageLimitExceeded as exc:
                self.jobs.database.update_job(
                    job_id,
                    status=JobStatus.FAILED.value,
                    finished_at=utc_now(),
                    error_code="INSUFFICIENT_RESULT_STORAGE",
                    error_message=str(exc),
                    current_step="Insufficient result storage",
                )
                raise RuntimeError("INSUFFICIENT_RESULT_STORAGE") from exc
            self.prepare_gpu(job.job_id)
            self.jobs.database.update_job(job_id, status=JobStatus.UPLOADING.value)
            self.upload_job(job.job_id)
            self.jobs.database.update_job(job_id, status=JobStatus.REMOTE_STARTING.value)
            self.start_remote_job(job.job_id)
            self.jobs.database.update_job(job_id, status=JobStatus.RUNNING.value)
            status = self.remote_jobs.monitor_until_finished(
                job,
                on_update=lambda remote_status, _log: self.jobs.update_from_remote_status(job_id, remote_status)
                if remote_status
                else None,
            )
            final_status = str(status.get("status", "")).upper()
            if final_status == JobStatus.SUCCEEDED.value:
                self.jobs.database.update_job(job_id, status=JobStatus.DOWNLOADING.value)
                sync_result = self.remote_jobs.synchronize_results(job)
                self.jobs.database.update_job(job_id, status=JobStatus.VERIFYING.value)
                verification = verify_conditional_vae_outputs(Path(job.local_workspace))
                if not verification["ok"]:
                    raise RuntimeError(f"Result verification failed: {verification}")
                self.jobs.database.update_job(job_id, status=JobStatus.PACKAGING.value)
                actual_bytes = int(sync_result.get("actual_result_bytes") or result_artifact_size_bytes(Path(job.local_workspace)))
                if not self.quota.result_reservation_committed_for_job(job_id, expected_actual_bytes=actual_bytes):
                    self.quota.commit_result_reservation_for_job(job_id, actual_bytes=actual_bytes)
                self.jobs.mark_succeeded(job_id, result_synced=True)
                succeeded = True
            elif final_status == JobStatus.CANCELLED.value:
                self.jobs.database.update_job(job_id, status=JobStatus.CANCELLED.value)
                self.quota.release_result_reservation_for_job(job_id, status="RELEASED", error_message="remote job cancelled")
            else:
                raise RuntimeError(status.get("message") or f"Remote job ended with status {final_status}")
        except GlobalStorageLimitExceeded as exc:
            delete_result_artifacts(Path(job.local_workspace))
            self.quota.release_result_reservation_for_job(job_id, status="FAILED", error_message="result storage limit exceeded")
            try:
                self.cancel_remote_job(job_id)
            except Exception:
                pass
            try:
                self.runpod_manager.stop_if_idle()
            except Exception:
                pass
            self.jobs.database.update_job(
                job_id,
                status=JobStatus.FAILED.value,
                error_code="RESULT_STORAGE_LIMIT_EXCEEDED",
                error_message=str(exc),
                current_step="Result storage limit exceeded",
            )
            raise RuntimeError("RESULT_STORAGE_LIMIT_EXCEEDED") from exc
        except Exception as exc:
            if not succeeded:
                self.quota.release_result_reservation_for_job(job_id, status="RELEASED", error_message=exc)
            self.jobs.mark_failed(job_id, exc)
            raise

    def upload_job(self, job_id: str) -> None:
        self.remote_jobs.upload_job(self._load_job(job_id))

    def start_remote_job(self, job_id: str) -> None:
        self.remote_jobs.start_remote_job(self._load_job(job_id))

    def monitor_remote_job(self, job_id: str) -> None:
        self.remote_jobs.monitor_until_finished(self._load_job(job_id))

    def synchronize_results(self, job_id: str) -> None:
        self.remote_jobs.synchronize_results(self._load_job(job_id))

    def cancel_remote_job(self, job_id: str) -> None:
        self.remote_jobs.cancel_job(self._load_job(job_id))

    def stop_idle_gpu(self) -> None:
        protected = [
            JobStatus.QUEUED.value,
            JobStatus.WAITING_FOR_GPU.value,
            JobStatus.UPLOADING.value,
            JobStatus.REMOTE_STARTING.value,
            JobStatus.RUNNING.value,
            JobStatus.DOWNLOADING.value,
        ]
        if self.jobs.database.list_jobs(statuses=protected, limit=1):
            return
        self.runpod_manager.stop_if_idle()

    def _load_job(self, job_id: str) -> RemoteJob:
        matches = list(self.config.workspace.glob(f"users/*/jobs/{job_id}/cloud_job.json"))
        if matches:
            return RemoteJob.load(matches[0])
        record = self.jobs.get_job(job_id)
        return self.remote_jobs.ensure_remote_job_for_record(record)
