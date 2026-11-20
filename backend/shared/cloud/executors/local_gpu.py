from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .base import ExecutorResult
from ..lab_runtime import lab_gpu_manifest, write_lab_gpu_manifest
from ..models import JobRecord, JobStatus


class LocalGPUExecutor:
    """Runs a pinned Lab GPU worker subprocess; it never falls back to CPU."""

    def __init__(
        self,
        *,
        physical_gpu_index: int,
        ui_gpu_label: str,
        gpu_name: str = "",
        gpu_uuid: str = "",
        termination_grace_seconds: int = 30,
    ) -> None:
        self.physical_gpu_index = int(physical_gpu_index)
        self.ui_gpu_label = str(ui_gpu_label)
        self.gpu_name = str(gpu_name or "")
        self.gpu_uuid = str(gpu_uuid or "")
        self.termination_grace_seconds = max(1, int(termination_grace_seconds))
        self.processes: dict[str, subprocess.Popen] = {}

    def start(self, job: JobRecord) -> ExecutorResult:
        workspace = Path(job.local_workspace)
        for name in ("input", "working", "output", "figures", "logs", "checkpoints"):
            (workspace / name).mkdir(parents=True, exist_ok=True)
        parameters = self._parameters(job)
        parameters_path = workspace / "parameters.json"
        parameters_path.write_text(json.dumps(parameters, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
        manifest = self._gpu_manifest(job)
        write_lab_gpu_manifest(workspace / "lab_gpu_manifest.json", manifest)
        env = os.environ.copy()
        env.update(
            {
                "SPASHINY_JOB_ID": job.job_id,
                "SPASHINY_WORKFLOW": job.workflow_name or job.workflow,
                "SPASHINY_JOB_WORKSPACE": str(workspace),
                "SPASHINY_PARAMETERS_PATH": str(parameters_path),
                "SPASHINY_WORKER_ID": job.worker_id or env.get("SPASHINY_WORKER_ID", ""),
                "SPASHINY_CLAIM_TOKEN": job.claim_token or env.get("SPASHINY_CLAIM_TOKEN", ""),
                "SPASHINY_GPU_REQUIRED": "1",
                "SPASHINY_ALLOW_CPU_FALLBACK": "0",
                "SPASHINY_ASSIGNED_GPU": str(job.assigned_gpu or ""),
                "CUDA_VISIBLE_DEVICES": "0",
            }
        )
        command = [
            sys.executable,
            "-m",
            "remote_worker.runner",
            "--job-id",
            job.job_id,
            "--workflow",
            job.workflow_name or job.workflow,
            "--workspace",
            str(workspace),
            "--parameters",
            str(parameters_path),
        ]
        stdout = (workspace / "logs" / "remote_worker.stdout.log").open("ab")
        stderr = (workspace / "logs" / "remote_worker.stderr.log").open("ab")
        creationflags = 0
        start_new_session = False
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            start_new_session = True
        proc = subprocess.Popen(
            command,
            cwd=str(Path.cwd()),
            env=env,
            stdout=stdout,
            stderr=stderr,
            creationflags=creationflags,
            start_new_session=start_new_session,
        )
        self.processes[job.job_id] = proc
        metadata = {
            **manifest,
            "pid": int(proc.pid),
            "process_group": str(proc.pid),
            "entrypoint": "python -m remote_worker.runner",
        }
        return ExecutorResult(JobStatus.RUNNING.value, "Lab GPU worker subprocess started.", metadata=metadata)

    def poll(self, job: JobRecord) -> ExecutorResult:
        proc = self.processes.get(job.job_id)
        if proc is None:
            error_log = Path(job.local_workspace) / "logs" / "error.log"
            if error_log.exists() and error_log.stat().st_size > 0:
                return ExecutorResult(JobStatus.FAILED.value, "Lab GPU subprocess error log is non-empty.", "GPU_SUBPROCESS_FAILED")
            return ExecutorResult(JobStatus.SUCCEEDED.value, "Lab GPU subprocess finished.")
        code = proc.poll()
        if code is None:
            return ExecutorResult(JobStatus.RUNNING.value, "Lab GPU subprocess running.")
        self.processes.pop(job.job_id, None)
        if code == 0:
            return ExecutorResult(JobStatus.SUCCEEDED.value, "Lab GPU subprocess succeeded.")
        return ExecutorResult(JobStatus.FAILED.value, f"Lab GPU subprocess failed with exit code {code}.", "GPU_SUBPROCESS_FAILED")

    def request_cancel(self, job: JobRecord) -> ExecutorResult:
        return self.terminate(job)

    def terminate(self, job: JobRecord) -> ExecutorResult:
        proc = self.processes.pop(job.job_id, None)
        if proc is None or proc.poll() is not None:
            return ExecutorResult(JobStatus.CANCELLED.value, "Lab GPU subprocess already stopped.")
        self._terminate_process_tree(proc)
        return ExecutorResult(JobStatus.CANCELLED.value, "Lab GPU subprocess cancelled.")

    def cleanup(self, job: JobRecord) -> ExecutorResult:
        return self.terminate(job)

    def collect_result(self, job: JobRecord) -> ExecutorResult:
        workspace = Path(job.local_workspace)
        error_log = workspace / "logs" / "error.log"
        if error_log.exists() and error_log.stat().st_size > 0:
            return ExecutorResult(JobStatus.FAILED.value, "Lab GPU result contains a non-empty error log.", "GPU_RESULT_ERROR")
        status = self._result_status(workspace)
        if status == "failed":
            return ExecutorResult(JobStatus.FAILED.value, "Lab GPU result manifest reports failure.", "GPU_RESULT_FAILED")
        missing = self._missing_required_outputs(job, workspace)
        if missing:
            return ExecutorResult(JobStatus.FAILED.value, "Lab GPU result is missing required outputs: " + ", ".join(missing), "RESULT_MISSING")
        if status == "succeeded" or (workspace / "summary.json").exists() or (workspace / "output" / "summary.json").exists() or (workspace / "result_manifest.json").exists():
            return ExecutorResult(JobStatus.SUCCEEDED.value, "Lab GPU result collected.")
        return ExecutorResult(JobStatus.FAILED.value, "Lab GPU result manifest missing.", "RESULT_MISSING")

    def _result_status(self, workspace: Path) -> str:
        for path in (
            workspace / "summary.json",
            workspace / "output" / "summary.json",
            workspace / "result_manifest.json",
            workspace / "manifest.json",
        ):
            if not path.is_file():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            status = str(data.get("status") or "").strip().lower()
            success = data.get("success")
            if status in {"failed", "failure", "error"} or success is False:
                return "failed"
            if status in {"success", "succeeded", "ok"} or success is True:
                return "succeeded"
        return ""

    def _missing_required_outputs(self, job: JobRecord, workspace: Path) -> list[str]:
        expected: list[str] = []
        try:
            metadata = json.loads(job.metadata_json or "{}")
            values = metadata.get("expected_outputs") if isinstance(metadata, dict) else []
            expected = [str(item) for item in values] if isinstance(values, list) else []
        except Exception:
            expected = []
        missing: list[str] = []
        for relative in expected:
            name = Path(relative).name
            if not name or name == "results.zip":
                continue
            candidates = [
                workspace / relative,
                workspace / name,
                workspace / "output" / name,
                workspace / "figures" / name,
                workspace / "logs" / name,
            ]
            if not any(path.is_file() for path in candidates):
                missing.append(relative)
        return missing

    def _gpu_manifest(self, job: JobRecord) -> dict[str, Any]:
        requested = str(job.assigned_gpu or "gpu-0")
        manifest = lab_gpu_manifest(requested, gpu_name=self.gpu_name, gpu_uuid=self.gpu_uuid)
        manifest["ui_gpu_label"] = self.ui_gpu_label or manifest["ui_gpu_label"]
        return manifest

    def _parameters(self, job: JobRecord) -> dict[str, Any]:
        try:
            data = json.loads(job.parameters_json or "{}")
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _terminate_process_tree(self, proc: subprocess.Popen) -> None:
        if os.name == "nt":
            try:
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            except Exception:
                proc.terminate()
            if self._wait(proc):
                return
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], check=False)
            self._wait(proc)
            return
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            return
        except Exception:
            proc.terminate()
        if self._wait(proc):
            return
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            return
        except Exception:
            proc.kill()
        self._wait(proc)

    def _wait(self, proc: subprocess.Popen) -> bool:
        deadline = time.time() + self.termination_grace_seconds
        while time.time() < deadline:
            if proc.poll() is not None:
                return True
            time.sleep(0.05)
        return proc.poll() is not None
