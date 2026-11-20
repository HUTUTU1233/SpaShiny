from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..models import JobRecord


@dataclass(frozen=True)
class ExecutorResult:
    status: str
    message: str = ""
    error_code: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class JobExecutor(Protocol):
    def start(self, job: JobRecord) -> ExecutorResult:
        ...

    def poll(self, job: JobRecord) -> ExecutorResult:
        ...

    def request_cancel(self, job: JobRecord) -> ExecutorResult:
        ...

    def terminate(self, job: JobRecord) -> ExecutorResult:
        ...

    def collect_result(self, job: JobRecord) -> ExecutorResult:
        ...
