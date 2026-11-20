from __future__ import annotations

import json
from dataclasses import dataclass, field

from .config import SpaShinyCloudConfig, load_cloud_config
from .executors.base import ExecutorResult, JobExecutor
from .executors.local_cpu import LocalCPUExecutor
from .executors.mock_gpu import MockGPUExecutor
from .models import JobRecord, JobStatus, ResourceType


@dataclass
class ExecutorRegistry:
    config: SpaShinyCloudConfig | None = None
    executors: dict[str, JobExecutor] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.config is None:
            self.config = load_cloud_config()
        self.executors.setdefault(
            "local_cpu",
            LocalCPUExecutor(
                termination_grace_seconds=int(self.config.local_process_termination_grace_seconds),
                config=self.config,
            ),
        )
        self.executors.setdefault("mock_gpu", MockGPUExecutor())

    def get_executor(self, job: JobRecord) -> JobExecutor:
        executor_name = self._executor_name(job)
        executor = self.executors.get(executor_name)
        if executor is None:
            fallback = "local_cpu" if job.resource_type == ResourceType.CPU.value else "mock_gpu"
            executor = self.executors[fallback]
        return executor

    def request_cancel(self, job: JobRecord) -> ExecutorResult:
        return self.get_executor(job).request_cancel(job)

    def terminate(self, job: JobRecord) -> ExecutorResult:
        return self.get_executor(job).terminate(job)

    def cleanup(self, job: JobRecord) -> ExecutorResult:
        executor = self.get_executor(job)
        cleanup = getattr(executor, "cleanup", None)
        if callable(cleanup):
            return cleanup(job)
        return ExecutorResult(JobStatus.CANCELLED.value, "Executor cleanup completed.")

    def _executor_name(self, job: JobRecord) -> str:
        try:
            metadata = json.loads(job.metadata_json or "{}")
            if isinstance(metadata, dict) and metadata.get("executor_name"):
                return str(metadata["executor_name"])
        except Exception:
            pass
        return "local_cpu" if job.resource_type == ResourceType.CPU.value else "mock_gpu"
