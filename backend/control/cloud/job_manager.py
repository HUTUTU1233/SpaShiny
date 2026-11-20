from __future__ import annotations

import json
import time
import traceback as tb_module
import uuid
from pathlib import Path
from typing import Any

from .database import CloudDatabase
from .file_manager import FileManager
from .config import SpaShinyCloudConfig, load_cloud_config
from .lab_runtime import LabGpuScheduler, normalize_lab_gpu_choice
from .models import ExecutionBackend, JobRecord, JobStatus
from .storage import WorkspaceStorage, safe_name
from .workflow_registry import validate_workflow_name


def utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


class JobManager:
    def __init__(
        self,
        database: CloudDatabase | None = None,
        storage: WorkspaceStorage | None = None,
        files: FileManager | None = None,
        config: SpaShinyCloudConfig | None = None,
    ) -> None:
        self.config = config or load_cloud_config()
        self.database = database or CloudDatabase(config=self.config)
        self.storage = storage or WorkspaceStorage(self.config)
        self.files = files or FileManager(self.storage)

    def create_gpu_job(
        self,
        *,
        user_id: str,
        workflow: str,
        parameters: dict[str, Any],
        session_id: str | None = None,
        analysis_session_id: str | None = None,
        input_h5ad: Path | None = None,
        job_id: str | None = None,
        requested_resource: str | None = None,
    ) -> JobRecord:
        workflow = validate_workflow_name(workflow, require_implemented=True)
        job_id = safe_name(job_id or str(uuid.uuid4()), "job")
        user_id = safe_name(user_id, "default")
        session_id = safe_name(session_id, "session") if session_id else None
        analysis_session_id = safe_name(analysis_session_id, "analysis") if analysis_session_id else ""
        local_workspace = self.storage.job_root(user_id, job_id)
        for dirname in ("input", "output", "figures", "logs"):
            (local_workspace / dirname).mkdir(parents=True, exist_ok=True)
        if input_h5ad is not None:
            self.files.copy_input_file(user_id, job_id, input_h5ad, "joint.h5ad")
        parameters_path = local_workspace / "parameters.json"
        parameters_path.write_text(json.dumps(parameters, ensure_ascii=False, indent=2), encoding="utf-8")

        queue_name = "gpu"
        assigned_gpu = ""
        requested = ""
        execution_backend = ExecutionBackend.GPU_RUNPOD.value
        if self.config.is_lab_profile:
            requested = normalize_lab_gpu_choice(requested_resource or "auto")
            queue_name, assigned_gpu = LabGpuScheduler(self.database, self.config).queue_for_request(requested)
            execution_backend = ExecutionBackend.GPU_LAB_LOCAL.value

        record = JobRecord(
            job_id=job_id,
            user_id=user_id,
            workflow=workflow,
            workflow_name=workflow,
            session_id=session_id,
            owner_session_id=session_id or user_id,
            analysis_session_id=analysis_session_id,
            anonymous_workspace_id=session_id or user_id,
            execution_backend=execution_backend,
            status=JobStatus.CREATED.value,
            queue_name=queue_name,
            requested_resource=requested,
            assigned_gpu=assigned_gpu,
            parameters_json=json.dumps(parameters, ensure_ascii=False),
            local_workspace=str(local_workspace),
            created_at=utc_now(),
        )
        record = self.database.create_job(record)
        self.add_event(job_id, "INFO", "Job created.")
        return record

    def create_job_for_session(
        self,
        session_id: str,
        *,
        workflow: str,
        parameters: dict[str, Any],
        analysis_session_id: str | None = None,
        input_h5ad: Path | None = None,
        job_id: str | None = None,
        requested_resource: str | None = None,
    ) -> JobRecord:
        session_id = safe_name(session_id, "session")
        return self.create_gpu_job(
            user_id=session_id,
            session_id=session_id,
            analysis_session_id=analysis_session_id,
            workflow=workflow,
            parameters=parameters,
            input_h5ad=input_h5ad,
            job_id=job_id,
            requested_resource=requested_resource,
        )

    def queue_job(self, job_id: str) -> JobRecord:
        current = self.database.get_job(job_id)
        if self.config.is_lab_profile:
            queued_status = JobStatus.QUEUED_GPU.value if current.resource_type == "gpu" else JobStatus.QUEUED_CPU.value
        else:
            queued_status = JobStatus.QUEUED.value
        record = self.database.update_job(job_id, status=queued_status, queued_at=utc_now(), progress=0.0)
        self.add_event(job_id, "INFO", "Job queued.")
        return record

    def mark_running(self, job_id: str, **updates: Any) -> JobRecord:
        payload = {"status": JobStatus.RUNNING.value, "started_at": updates.pop("started_at", utc_now())}
        payload.update(updates)
        return self.database.update_job(job_id, **payload)

    def update_from_remote_status(self, job_id: str, remote_status: dict[str, Any]) -> JobRecord:
        status_value = str(remote_status.get("status") or JobStatus.RUNNING.value)
        if status_value == JobStatus.REMOTE_UNREACHABLE.value:
            current = self.database.get_job(job_id)
            self.add_event(job_id, "WARN", str(remote_status.get("message") or "Remote temporarily unreachable."))
            return self.database.update_job(
                job_id,
                status=current.status if current.status != JobStatus.CREATED.value else JobStatus.RUNNING.value,
                message=str(remote_status.get("message") or current.message),
                last_remote_sync_at=utc_now(),
            )
        updates = {
            "status": status_value,
            "progress": float(remote_status.get("progress") or 0.0),
            "current_step": str(remote_status.get("current_step") or ""),
            "message": str(remote_status.get("message") or ""),
            "device": str(remote_status.get("device") or ""),
            "gpu_name": str(remote_status.get("gpu_name") or ""),
            "last_remote_sync_at": utc_now(),
        }
        if remote_status.get("pid"):
            updates["remote_pid"] = int(remote_status["pid"])
        return self.database.update_job(job_id, **updates)

    def mark_failed(self, job_id: str, exc: BaseException) -> JobRecord:
        record = self.database.update_job(
            job_id,
            status=JobStatus.FAILED.value,
            finished_at=utc_now(),
            error_type=type(exc).__name__,
            error_message=str(exc),
            traceback=tb_module.format_exc(),
        )
        self.add_event(job_id, "ERROR", str(exc))
        return record

    def mark_succeeded(self, job_id: str, *, result_synced: bool = True) -> JobRecord:
        record = self.database.update_job(
            job_id,
            status=JobStatus.SUCCEEDED.value,
            progress=100.0,
            current_step="Completed",
            finished_at=utc_now(),
            result_synced=result_synced,
        )
        self.add_event(job_id, "INFO", "Job succeeded.")
        return record

    def request_cancel(
        self,
        job_id: str,
        user_id: str | None = None,
        session_id: str | None = None,
        analysis_session_id: str | None = None,
    ) -> JobRecord:
        record = self.database.get_job(
            job_id,
            user_id=user_id,
            session_id=session_id,
            analysis_session_id=analysis_session_id,
        )
        updated = self.database.update_job(record.job_id, status=JobStatus.CANCEL_REQUESTED.value)
        self.add_event(job_id, "INFO", "Cancellation requested.")
        return updated

    def get_job(self, job_id: str, user_id: str | None = None, session_id: str | None = None) -> JobRecord:
        return self.database.get_job(job_id, user_id=user_id, session_id=session_id)

    def list_jobs(
        self,
        user_id: str | None = None,
        session_id: str | None = None,
        analysis_session_id: str | None = None,
        limit: int = 100,
    ) -> list[JobRecord]:
        return self.database.list_jobs(
            user_id=user_id,
            session_id=session_id,
            analysis_session_id=analysis_session_id,
            limit=limit,
        )

    def list_jobs_for_session(
        self, session_id: str, *, analysis_session_id: str | None = None, limit: int = 100
    ) -> list[JobRecord]:
        return self.database.list_jobs(
            session_id=safe_name(session_id, "session"),
            analysis_session_id=safe_name(analysis_session_id, "analysis") if analysis_session_id else None,
            limit=limit,
        )

    def get_job_for_session(
        self, session_id: str, job_id: str, *, analysis_session_id: str | None = None
    ) -> JobRecord:
        return self.database.get_job(
            job_id,
            session_id=safe_name(session_id, "session"),
            analysis_session_id=safe_name(analysis_session_id, "analysis") if analysis_session_id else None,
        )

    def cancel_job_for_session(
        self, session_id: str, job_id: str, *, analysis_session_id: str | None = None
    ) -> JobRecord:
        return self.request_cancel(
            job_id,
            session_id=safe_name(session_id, "session"),
            analysis_session_id=safe_name(analysis_session_id, "analysis") if analysis_session_id else None,
        )

    def list_results_for_session(
        self, session_id: str, *, analysis_session_id: str | None = None, limit: int = 100
    ) -> list[JobRecord]:
        return self.database.list_jobs(
            session_id=safe_name(session_id, "session"),
            analysis_session_id=safe_name(analysis_session_id, "analysis") if analysis_session_id else None,
            statuses=[JobStatus.SUCCEEDED.value],
            limit=limit,
        )

    def assert_job_owner(
        self, session_id: str, job_id: str, *, analysis_session_id: str | None = None
    ) -> JobRecord:
        return self.get_job_for_session(session_id, job_id, analysis_session_id=analysis_session_id)

    def add_event(self, job_id: str, level: str, message: str) -> None:
        self.database.add_event(job_id, utc_now(), level, message)

    def package_results(self, job_id: str, user_id: str | None = None) -> Path:
        record = self.database.get_job(job_id, user_id=user_id)
        return self.storage.package_results_zip(record.user_id, record.job_id)

    def compute_runtime_seconds(self, job: JobRecord) -> float:
        try:
            from datetime import datetime

            start = datetime.fromisoformat(job.started_at) if job.started_at else None
            end = datetime.fromisoformat(job.finished_at) if job.finished_at else None
            if start and end:
                return max(0.0, (end - start).total_seconds())
        except Exception:
            pass
        return float(job.runtime_seconds or 0.0)
