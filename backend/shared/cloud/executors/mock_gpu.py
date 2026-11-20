from __future__ import annotations

import json
from pathlib import Path

from .base import ExecutorResult
from ..models import JobRecord, JobStatus


class MockGPUExecutor:
    """Deterministic GPU executor for queue tests; it never calls RunPod or SSH."""

    def start(self, job: JobRecord) -> ExecutorResult:
        return ExecutorResult(JobStatus.RUNNING.value, "Mock GPU job started.")

    def poll(self, job: JobRecord) -> ExecutorResult:
        parameters = self._parameters(job)
        simulate = str(parameters.get("simulate") or "success").lower()
        if simulate == "cuda_oom":
            return ExecutorResult(JobStatus.FAILED.value, "Simulated CUDA OOM.", "CUDA_OOM")
        if simulate == "remote_failed":
            return ExecutorResult(JobStatus.FAILED.value, "Simulated remote failure.", "REMOTE_FAILED")
        if simulate == "timeout":
            return ExecutorResult(JobStatus.TIMED_OUT.value, "Simulated timeout.", "TIMED_OUT")
        if simulate == "cancelled":
            return ExecutorResult(JobStatus.CANCELLED.value, "Simulated cancellation.")
        return ExecutorResult(JobStatus.SUCCEEDED.value, "Mock GPU job succeeded.")

    def request_cancel(self, job: JobRecord) -> ExecutorResult:
        return ExecutorResult(JobStatus.CANCELLED.value, "Mock GPU job cancelled.")

    def terminate(self, job: JobRecord) -> ExecutorResult:
        return ExecutorResult(JobStatus.CANCELLED.value, "Mock GPU job terminated.")

    def collect_result(self, job: JobRecord) -> ExecutorResult:
        output_dir = Path(job.local_workspace) / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "mock_gpu_result.json").write_text(
            json.dumps({"job_id": job.job_id, "workflow": job.workflow_name or job.workflow}, ensure_ascii=False),
            encoding="utf-8",
        )
        return ExecutorResult(JobStatus.SUCCEEDED.value, "Mock GPU result collected.")

    def _parameters(self, job: JobRecord) -> dict:
        try:
            data = json.loads(job.parameters_json or "{}")
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
