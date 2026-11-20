from __future__ import annotations

import json
import posixpath
import re
import shlex
import shutil
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .config import SpaShinyCloudConfig, load_cloud_config
from .database import CloudDatabase
from .models import JobRecord
from .result_sync import ResultSynchronizer, delete_result_artifacts, package_results_zip, result_artifact_size_bytes, verify_conditional_vae_outputs
from .runpod_manager import RunPodManager
from .security import safe_remote_path
from .sftp_manager import SFTPManager
from .ssh_executor import SSHConnectionConfig, SSHExecutor
from .storage_quota import GlobalStorageLimitExceeded, StorageQuotaManager
from .workflow_registry import ST_SM_CONDITIONAL_VAE, validate_workflow_name


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_id(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    return cleaned[:96] or fallback


def build_remote_worker_command(
    *,
    python_command: str,
    job_id: str,
    workflow: str,
    workspace: str,
    parameters_path: str,
) -> str:
    args = [
        python_command,
        "-m",
        "remote_worker.remote_worker",
        "--job-id",
        job_id,
        "--workflow",
        workflow,
        "--workspace",
        workspace,
        "--parameters",
        parameters_path,
    ]
    return " ".join(shlex.quote(str(arg)) for arg in args)


@dataclass
class RemoteJob:
    job_id: str
    user_id: str
    workflow: str
    local_workspace: str
    remote_workspace: str
    parameters_path: str
    input_h5ad: str
    remote_pid: int | None = None
    log_offset: int = 0
    status: str = "CREATED"
    created_at: str = ""

    @property
    def metadata_path(self) -> Path:
        return Path(self.local_workspace) / "cloud_job.json"

    def save(self) -> None:
        path = self.metadata_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "RemoteJob":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(**data)


class RemoteJobManager:
    def __init__(
        self,
        config: SpaShinyCloudConfig | None = None,
        runpod_manager: RunPodManager | None = None,
        database: CloudDatabase | None = None,
        quota: StorageQuotaManager | None = None,
    ) -> None:
        self.config = config or load_cloud_config()
        self.runpod_manager = runpod_manager or RunPodManager(self.config)
        self.database = database or CloudDatabase(config=self.config)
        self.quota = quota or StorageQuotaManager(database=self.database, config=self.config)
        self.project_root = Path(__file__).resolve().parents[1]
        self.remote_app_root = self.config.remote_job_root.rsplit("/jobs", 1)[0]

    def create_conditional_vae_job(
        self,
        *,
        input_h5ad: Path,
        parameters: dict[str, Any],
        user_id: str = "default",
        job_id: str | None = None,
    ) -> RemoteJob:
        input_h5ad = Path(input_h5ad)
        if not input_h5ad.is_file():
            raise FileNotFoundError(f"Conditional VAE input h5ad was not found: {input_h5ad}")
        job_id = _safe_id(job_id or str(uuid.uuid4()), "job")
        user_id = _safe_id(user_id, "default")
        workflow = validate_workflow_name(ST_SM_CONDITIONAL_VAE)
        local_workspace = self.config.workspace / "users" / user_id / "jobs" / job_id
        remote_workspace = safe_remote_path(self.config.remote_job_root, job_id)
        for name in ("input", "output", "figures", "logs"):
            (local_workspace / name).mkdir(parents=True, exist_ok=True)

        local_input = local_workspace / "input" / "joint.h5ad"
        if input_h5ad.resolve() != local_input.resolve():
            shutil.copy2(input_h5ad, local_input)

        remote_parameters_path = posixpath.join(remote_workspace, "parameters.json")
        payload = dict(parameters)
        payload.update(
            {
                "job_id": job_id,
                "workflow": workflow,
                "input_files": {"joint_h5ad": posixpath.join(remote_workspace, "input", "joint.h5ad")},
                "created_at": _utc_now(),
            }
        )
        local_parameters = local_workspace / "parameters.json"
        local_parameters.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        job = RemoteJob(
            job_id=job_id,
            user_id=user_id,
            workflow=workflow,
            local_workspace=str(local_workspace),
            remote_workspace=remote_workspace,
            parameters_path=remote_parameters_path,
            input_h5ad=str(local_input),
            status="CREATED",
            created_at=_utc_now(),
        )
        job.save()
        return job

    def ensure_remote_job_for_record(self, record: JobRecord) -> RemoteJob:
        metadata_path = Path(record.local_workspace) / "cloud_job.json"
        if metadata_path.exists():
            return RemoteJob.load(metadata_path)
        parameters = json.loads(record.parameters_json or "{}")
        input_h5ad = Path(record.local_workspace) / "input" / "joint.h5ad"
        if not input_h5ad.exists():
            raise FileNotFoundError(f"Job input file is missing: {input_h5ad}")
        return self.create_conditional_vae_job(
            input_h5ad=input_h5ad,
            parameters=parameters,
            user_id=record.user_id,
            job_id=record.job_id,
        )

    def _open_ssh(self) -> SSHExecutor:
        info = self.runpod_manager.get_ssh_config()
        ssh_cfg = SSHConnectionConfig.from_connection_info(info, self.config)
        ssh = SSHExecutor(ssh_cfg)
        ssh.connect()
        return ssh

    def sync_remote_worker_source(self, sftp: SFTPManager) -> None:
        source_sftp = SFTPManager(sftp.ssh, remote_root=self.remote_app_root, retries=sftp.retries)
        source_sftp.mkdir_recursive(f"{self.remote_app_root}/remote_worker")
        source_sftp.upload_directory(self.project_root / "remote_worker", f"{self.remote_app_root}/remote_worker")

        runner = self.project_root / "app" / "river" / "run_spatialmeta_train.py"
        if runner.exists():
            source_sftp.mkdir_recursive(f"{self.remote_app_root}/app/river")
            source_sftp.upload_file(runner, f"{self.remote_app_root}/app/river/run_spatialmeta_train.py")

    def upload_job(self, job: RemoteJob, *, sync_source: bool = True) -> None:
        with self._open_ssh() as ssh:
            sftp = SFTPManager(ssh, self.config.remote_job_root)
            for dirname in ("input", "working", "output", "figures", "logs", "checkpoints"):
                sftp.mkdir_recursive(f"{job.remote_workspace}/{dirname}")
            if sync_source:
                self.sync_remote_worker_source(sftp)
            sftp.upload_file(Path(job.input_h5ad), f"{job.remote_workspace}/input/joint.h5ad")
            sftp.upload_file(Path(job.local_workspace) / "parameters.json", f"{job.remote_workspace}/parameters.json")
        job.status = "UPLOADED"
        job.save()

    def start_remote_job(self, job: RemoteJob, python_command: str = "python") -> int:
        command = build_remote_worker_command(
            python_command=python_command,
            job_id=job.job_id,
            workflow=job.workflow,
            workspace=job.remote_workspace,
            parameters_path=job.parameters_path,
        )
        with self._open_ssh() as ssh:
            pid = ssh.execute_background(
                f"cd {shlex.quote(self.remote_app_root)} && {command}",
                stdout_path=f"{job.remote_workspace}/logs/run.log",
                stderr_path=f"{job.remote_workspace}/logs/error.log",
                pid_path=f"{job.remote_workspace}/job.pid",
            )
        job.remote_pid = pid
        job.status = "REMOTE_STARTING"
        job.save()
        return pid

    def read_status(self, job: RemoteJob) -> dict[str, Any] | None:
        with self._open_ssh() as ssh:
            if not ssh.file_exists(f"{job.remote_workspace}/status.json"):
                return None
            text, _ = ssh.read_text_file(f"{job.remote_workspace}/status.json", 0)
        return json.loads(text)

    def read_incremental_log(self, job: RemoteJob) -> tuple[str, int]:
        with self._open_ssh() as ssh:
            if not ssh.file_exists(f"{job.remote_workspace}/logs/run.log"):
                return "", job.log_offset
            text, offset = ssh.read_text_file(f"{job.remote_workspace}/logs/run.log", job.log_offset)
        job.log_offset = offset
        job.save()
        return text, offset

    def monitor_until_finished(
        self,
        job: RemoteJob,
        *,
        timeout_seconds: int | None = None,
        on_update: Callable[[dict[str, Any], str], None] | None = None,
    ) -> dict[str, Any]:
        timeout_seconds = timeout_seconds or self.config.gpu_job_timeout_hours * 3600
        deadline = time.monotonic() + timeout_seconds
        last_status: dict[str, Any] = {}
        unreachable_count = 0
        while time.monotonic() < deadline:
            try:
                status = self.read_status(job) or {}
                log_text, _ = self.read_incremental_log(job)
                unreachable_count = 0
                if status:
                    last_status = status
                    job.status = str(status.get("status") or job.status)
                    job.save()
                if on_update is not None:
                    on_update(status, log_text)
                if str(status.get("status", "")).upper() in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                    return status
            except Exception as exc:
                unreachable_count += 1
                unreachable_status = {
                    "status": "REMOTE_UNREACHABLE",
                    "message": f"Remote temporarily unreachable; retry {unreachable_count}: {exc}",
                    "last_known_status": last_status.get("status") or job.status,
                }
                if on_update is not None:
                    on_update(unreachable_status, "")
                job.status = last_status.get("status") or job.status or "RUNNING"
                job.save()
            time.sleep(self.config.status_poll_seconds)
        raise TimeoutError(f"Remote job timed out: {job.job_id}")

    def synchronize_results(self, job: RemoteJob) -> dict[str, Any]:
        with self._open_ssh() as ssh:
            sftp = SFTPManager(ssh, self.config.remote_job_root)
            result = ResultSynchronizer(sftp).sync_from_manifest(job.remote_workspace, Path(job.local_workspace))
        package_results_zip(Path(job.local_workspace))
        verification = verify_conditional_vae_outputs(Path(job.local_workspace))
        if not verification["ok"]:
            raise RuntimeError(f"Result verification failed before storage commit: {verification}")
        try:
            self.database.get_job(job.job_id)
            actual_bytes = result_artifact_size_bytes(Path(job.local_workspace))
            try:
                self.quota.commit_result_reservation_for_job(job.job_id, actual_bytes=actual_bytes)
            except GlobalStorageLimitExceeded:
                delete_result_artifacts(Path(job.local_workspace))
                self.quota.release_result_reservation_for_job(job.job_id, status="FAILED", error_message="result storage limit exceeded")
                raise
            result["actual_result_bytes"] = actual_bytes
        except KeyError:
            pass
        job.status = "RESULT_SYNCED"
        job.save()
        return result

    def cancel_job(self, job: RemoteJob) -> None:
        with self._open_ssh() as ssh:
            ssh.write_text_file(f"{job.remote_workspace}/cancel.flag", "cancelled\n")
            if job.remote_pid:
                ssh.terminate_process(job.remote_pid, force=False)
        job.status = "CANCELLING"
        job.save()
