from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

from .base import ExecutorResult
from ..config import SpaShinyCloudConfig, load_cloud_config
from ..cpu_workflows.common import CPUWorkflowContext, validate_result_contract, write_failure_artifacts
from ..cpu_workflows.registry import WORKFLOW_NOT_IMPLEMENTED, get_cpu_workflow
from ..database import CloudDatabase
from ..input_resolver import InputResolver, InputResolverError
from ..models import JobRecord, JobStatus
from ..worker_io import WorkerIOError, build_input_files, download_worker_input_assets, fetch_worker_input_plan, write_sanitized_input_manifest


class LocalCPUExecutor:
    """Runs a controlled local CPU subprocess; it never executes uploaded user code."""

    def __init__(
        self,
        *,
        termination_grace_seconds: int = 10,
        input_plan_fetcher: Callable[..., dict[str, Any]] | None = None,
        input_asset_downloader: Callable[..., list[dict[str, Any]]] | None = None,
        config: SpaShinyCloudConfig | None = None,
        database: CloudDatabase | None = None,
        input_resolver: InputResolver | None = None,
    ) -> None:
        self.processes: dict[str, subprocess.Popen] = {}
        self.process_metadata: dict[str, dict[str, int | str]] = {}
        self.termination_grace_seconds = max(1, int(termination_grace_seconds))
        self.input_plan_fetcher = input_plan_fetcher
        self.input_asset_downloader = input_asset_downloader or download_worker_input_assets
        self.config = config or load_cloud_config(require_storage=False)
        self.database = database
        self.input_resolver = input_resolver

    def start(self, job: JobRecord) -> ExecutorResult:
        workspace = Path(job.local_workspace)
        for dirname in ("input", "working", "output", "figures", "logs"):
            (workspace / dirname).mkdir(parents=True, exist_ok=True)
        workflow = job.workflow_name or job.workflow
        spec = get_cpu_workflow(workflow)
        if not spec.enabled or spec.handler is None:
            return self._fail_before_start(job, WORKFLOW_NOT_IMPLEMENTED, f"CPU workflow is not implemented: {workflow}")
        try:
            input_metadata = self._prepare_inputs(job, workspace)
            job_spec_path = self._write_job_spec(job, workspace, input_metadata)
        except (InputResolverError, WorkerIOError, ValueError, OSError) as exc:
            return self._fail_before_start(job, "INPUT_RESOLUTION_FAILED", f"{type(exc).__name__}: {exc}")
        creationflags = 0
        start_new_session = False
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            start_new_session = True
        env = self._subprocess_env()
        stdout = (workspace / "logs" / "stdout.log").open("ab")
        stderr = (workspace / "logs" / "stderr.log").open("ab")
        try:
            proc = subprocess.Popen(
                [sys.executable, "-m", "cloud.cpu_workflows.runner", str(job_spec_path)],
                stdout=stdout,
                stderr=stderr,
                creationflags=creationflags,
                start_new_session=start_new_session,
                cwd=str(Path(__file__).resolve().parents[2]),
                env=env,
            )
        finally:
            stdout.close()
            stderr.close()
        self.processes[job.job_id] = proc
        metadata: dict[str, int | str] = {
            "pid": int(proc.pid),
            "process_group": str(proc.pid),
            "input_asset_count": int(input_metadata.get("input_asset_count") or 0),
            "input_source": str(input_metadata.get("input_source") or ""),
            "workflow": workflow,
            "cpu_threads_per_job": str(self._cpu_threads()),
        }
        self.process_metadata[job.job_id] = metadata
        return ExecutorResult(JobStatus.RUNNING.value, "Local CPU workflow started.", metadata=metadata)

    def poll(self, job: JobRecord) -> ExecutorResult:
        proc = self.processes.get(job.job_id)
        if proc is None:
            return self._status_from_disk(job)
        code = proc.poll()
        if code is None:
            return ExecutorResult(JobStatus.RUNNING.value, "Local CPU workflow running.")
        self.processes.pop(job.job_id, None)
        self.process_metadata.pop(job.job_id, None)
        if code == 0:
            ok, error_code, message = self._validate_result(job)
            if ok:
                return ExecutorResult(JobStatus.SUCCEEDED.value, "Local CPU workflow succeeded.")
            return ExecutorResult(JobStatus.FAILED.value, message, error_code or "CPU_RESULT_INVALID")
        status = self._read_status_file(job)
        return ExecutorResult(
            JobStatus.FAILED.value,
            str(status.get("message") or "Local CPU workflow failed."),
            str(status.get("error_code") or "CPU_SUBPROCESS_FAILED"),
        )

    def request_cancel(self, job: JobRecord) -> ExecutorResult:
        return self.terminate(job)

    def terminate(self, job: JobRecord) -> ExecutorResult:
        proc = self.processes.pop(job.job_id, None)
        self.process_metadata.pop(job.job_id, None)
        if proc is None:
            return ExecutorResult(JobStatus.CANCELLED.value, "Local CPU subprocess already stopped.")
        if proc.poll() is not None:
            return ExecutorResult(JobStatus.CANCELLED.value, "Local CPU subprocess already stopped.")
        self._terminate_process_tree(proc)
        return ExecutorResult(JobStatus.CANCELLED.value, "Local CPU subprocess cancelled.")

    def collect_result(self, job: JobRecord) -> ExecutorResult:
        ok, error_code, message = self._validate_result(job)
        if ok:
            return ExecutorResult(JobStatus.SUCCEEDED.value, "Local CPU result collected.")
        return ExecutorResult(JobStatus.FAILED.value, message, error_code or "RESULT_MISSING")

    def _terminate_process_tree(self, proc: subprocess.Popen) -> None:
        if os.name == "nt":
            try:
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            except Exception:
                try:
                    proc.terminate()
                except Exception:
                    pass
            if self._wait(proc, self.termination_grace_seconds):
                return
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            self._wait(proc, self.termination_grace_seconds)
            return
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            return
        except Exception:
            proc.terminate()
        if self._wait(proc, self.termination_grace_seconds):
            return
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            return
        except Exception:
            proc.kill()
        self._wait(proc, self.termination_grace_seconds)

    def _wait(self, proc: subprocess.Popen, seconds: int) -> bool:
        deadline = time.time() + int(seconds)
        while time.time() < deadline:
            if proc.poll() is not None:
                return True
            time.sleep(0.05)
        return proc.poll() is not None

    def _parameters(self, job: JobRecord) -> dict:
        try:
            data = json.loads(job.parameters_json or "{}")
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _metadata(self, job: JobRecord) -> dict:
        try:
            data = json.loads(job.metadata_json or "{}")
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _prepare_inputs(self, job: JobRecord, workspace: Path) -> dict[str, Any]:
        object_root = self._local_object_root_for_config()
        if object_root is not None:
            os.environ["SPASHINY_LOCAL_OBJECT_ROOT"] = str(object_root)
        plan = self._input_plan(job)
        downloaded = self.input_asset_downloader(plan, workspace / "input")
        write_sanitized_input_manifest(workspace=workspace, plan=plan, downloaded=downloaded)
        return {
            "plan": self._sanitize_plan(plan, downloaded),
            "downloaded_assets": downloaded,
            "input_source": str(plan.get("input_source") or ""),
            "input_asset_count": len(downloaded),
            "input_files": build_input_files(downloaded),
        }

    def _input_plan(self, job: JobRecord) -> dict[str, Any]:
        if self.input_plan_fetcher is not None:
            return self.input_plan_fetcher(
                control_api_base_url=os.environ.get("SPASHINY_CONTROL_API_BASE_URL", ""),
                job_id=job.job_id,
                worker_id=job.worker_id or os.environ.get("SPASHINY_WORKER_ID", ""),
                claim_token=job.claim_token or os.environ.get("SPASHINY_CLAIM_TOKEN", ""),
            )
        control_api = os.environ.get("SPASHINY_CONTROL_API_BASE_URL", "").strip()
        if control_api:
            return fetch_worker_input_plan(
                control_api_base_url=control_api,
                job_id=job.job_id,
                worker_id=job.worker_id or os.environ.get("SPASHINY_WORKER_ID", ""),
                claim_token=job.claim_token or os.environ.get("SPASHINY_CLAIM_TOKEN", ""),
            )
        resolver = self.input_resolver
        if resolver is None:
            resolver = InputResolver(database=self.database or CloudDatabase(config=self.config), config=self.config)
        return resolver.resolve_for_worker(job)

    def _write_job_spec(self, job: JobRecord, workspace: Path, input_metadata: dict[str, Any]) -> Path:
        metadata = self._metadata(job)
        thread_config = {"cpu_threads_per_job": self._cpu_threads()}
        for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
            thread_config[name] = int(os.environ.get(name) or thread_config["cpu_threads_per_job"])
        payload = {
            "job_id": job.job_id,
            "workflow_name": job.workflow_name or job.workflow,
            "workflow": job.workflow,
            "session_id": job.session_id or "",
            "owner_session_id": job.owner_session_id or job.session_id or job.user_id,
            "workspace": str(workspace),
            "input_dir": str(Path(str((input_metadata.get("plan") or {}).get("materialized_input_dir") or "")) if (input_metadata.get("plan") or {}).get("materialized_input_dir") else workspace / "input"),
            "working_dir": str(workspace / "working"),
            "output_dir": str(workspace / "output"),
            "figures_dir": str(workspace / "figures"),
            "logs_dir": str(workspace / "logs"),
            "parameters": self._parameters(job),
            "metadata": metadata,
            "plan": input_metadata.get("plan") or {},
            "downloaded_assets": input_metadata.get("downloaded_assets") or [],
            "input_files": input_metadata.get("input_files") or {},
            "thread_config": thread_config,
        }
        path = workspace / "cpu_job_spec.json"
        path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def _sanitize_plan(self, plan: dict[str, Any], downloaded: list[dict[str, Any]]) -> dict[str, Any]:
        allowed = {
            "contract_version",
            "input_resolver_version",
            "job_id",
            "session_id",
            "workflow",
            "workflow_version",
            "runtime_profile",
            "input_source",
            "materialized_input_dir",
            "manifest_version",
            "session_input_binding",
            "example_bundle",
            "model",
        }
        result = {key: plan.get(key) for key in allowed if key in plan}
        result["assets"] = [dict(item) for item in downloaded]
        return result

    def _subprocess_env(self) -> dict[str, str]:
        env = os.environ.copy()
        repo_root = str(Path(__file__).resolve().parents[2])
        env["PYTHONPATH"] = repo_root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        threads = str(self._cpu_threads())
        env["SPASHINY_CPU_THREADS_PER_JOB"] = threads
        object_root = self._local_object_root_for_config()
        if object_root is not None:
            env["SPASHINY_LOCAL_OBJECT_ROOT"] = str(object_root)
        for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
            env[name] = threads
        return env

    def _cpu_threads(self) -> int:
        raw = os.environ.get("SPASHINY_CPU_THREADS_PER_JOB") or "1"
        try:
            return max(1, int(raw))
        except Exception:
            return 1

    def _local_object_root_for_config(self) -> Path | None:
        if str(self.config.storage_backend or "").lower() != "local":
            return None
        if self.config.is_lab_profile:
            return Path(self.config.local_object_root)
        return Path(self.config.workspace) / "temporary_objects"

    def _validate_result(self, job: JobRecord) -> tuple[bool, str, str]:
        spec = get_cpu_workflow(job.workflow_name or job.workflow)
        return validate_result_contract(Path(job.local_workspace), spec.required_outputs)

    def _read_status_file(self, job: JobRecord) -> dict[str, Any]:
        path = Path(job.local_workspace) / "cpu_workflow_status.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _status_from_disk(self, job: JobRecord) -> ExecutorResult:
        status = self._read_status_file(job)
        if str(status.get("status") or "").lower() == "failed":
            return ExecutorResult(JobStatus.FAILED.value, str(status.get("message") or "Local CPU workflow failed."), str(status.get("error_code") or "CPU_WORKFLOW_FAILED"))
        ok, error_code, message = self._validate_result(job)
        if ok:
            return ExecutorResult(JobStatus.SUCCEEDED.value, "Local CPU workflow finished.")
        return ExecutorResult(JobStatus.FAILED.value, message, error_code or "CPU_RESULT_INVALID")

    def _fail_before_start(self, job: JobRecord, error_code: str, message: str) -> ExecutorResult:
        workspace = Path(job.local_workspace)
        ctx = CPUWorkflowContext(
            job_id=job.job_id,
            workflow_name=job.workflow_name or job.workflow,
            session_id=job.session_id or "",
            owner_session_id=job.owner_session_id or job.session_id or job.user_id,
            workspace=workspace,
            input_dir=workspace / "input",
            working_dir=workspace / "working",
            output_dir=workspace / "output",
            figures_dir=workspace / "figures",
            logs_dir=workspace / "logs",
            parameters=self._parameters(job),
            plan={},
            downloaded_assets=[],
            input_files={},
            metadata=self._metadata(job),
            thread_config={"cpu_threads_per_job": self._cpu_threads()},
        )
        write_failure_artifacts(ctx, code=error_code, message=message)
        (workspace / "cpu_workflow_status.json").write_text(
            json.dumps({"status": "failed", "message": message, "error_code": error_code}, ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return ExecutorResult(JobStatus.FAILED.value, message, error_code)
