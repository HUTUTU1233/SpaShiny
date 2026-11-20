from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class JobStatus(str, Enum):
    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    QUEUED = "QUEUED"
    QUEUED_CPU = "QUEUED_CPU"
    QUEUED_GPU = "QUEUED_GPU"
    SCHEDULING = "SCHEDULING"
    PROVISIONING = "PROVISIONING"
    STARTING = "STARTING"
    STARTING_GPU = "STARTING_GPU"
    WAITING_FOR_GPU = "WAITING_FOR_GPU"
    UPLOADING = "UPLOADING"
    UPLOADED = "UPLOADED"
    REMOTE_STARTING = "REMOTE_STARTING"
    RUNNING = "RUNNING"
    REMOTE_UNREACHABLE = "REMOTE_UNREACHABLE"
    POSTPROCESSING = "POSTPROCESSING"
    SYNCING = "SYNCING"
    DOWNLOADING = "DOWNLOADING"
    VERIFYING = "VERIFYING"
    PACKAGING = "PACKAGING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"
    CLEANING_UP = "CLEANING_UP"
    ABANDONED = "ABANDONED"
    NOT_ENABLED = "NOT_ENABLED"
    QUEUE_FULL = "QUEUE_FULL"
    BUDGET_LIMIT = "BUDGET_LIMIT"
    TIMED_OUT = "TIMED_OUT"
    CLEANING = "CLEANING"
    CLEANED = "CLEANED"
    INTERRUPTED = "INTERRUPTED"


class SessionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DISCONNECTED = "DISCONNECTED"
    ABANDONED = "ABANDONED"
    CLEANING = "CLEANING"
    CLEANED = "CLEANED"


class UploadStatus(str, Enum):
    INITIATED = "INITIATED"
    UPLOADING = "UPLOADING"
    COMPLETING = "COMPLETING"
    COMPLETED = "COMPLETED"
    ABORT_REQUESTED = "ABORT_REQUESTED"
    ABORTED = "ABORTED"
    FAILED = "FAILED"
    DELETING = "DELETING"
    DELETED = "DELETED"


class ExecutionBackend(str, Enum):
    CPU = "CPU"
    GPU_RUNPOD = "GPU_RUNPOD"
    GPU_LAB_LOCAL = "GPU_LAB_LOCAL"


class ResourceType(str, Enum):
    CPU = "cpu"
    GPU = "gpu"


class CleanupRetryStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    RETRY_WAIT = "RETRY_WAIT"
    COMPLETED = "COMPLETED"
    EXHAUSTED = "EXHAUSTED"


class WorkerStatus(str, Enum):
    STARTING = "STARTING"
    ACTIVE = "ACTIVE"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    LOST = "LOST"


TERMINAL_STATUSES = {
    JobStatus.SUCCEEDED.value,
    JobStatus.FAILED.value,
    JobStatus.CANCELLED.value,
    JobStatus.ABANDONED.value,
    JobStatus.NOT_ENABLED.value,
    JobStatus.QUEUE_FULL.value,
    JobStatus.BUDGET_LIMIT.value,
    JobStatus.TIMED_OUT.value,
    JobStatus.CLEANED.value,
    JobStatus.INTERRUPTED.value,
}


GPU_ACTIVE_STATUSES = {
    JobStatus.SCHEDULING.value,
    JobStatus.PROVISIONING.value,
    JobStatus.STARTING_GPU.value,
    JobStatus.STARTING.value,
    JobStatus.WAITING_FOR_GPU.value,
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
    JobStatus.CLEANING_UP.value,
}


NON_SUCCESS_JOB_STATUSES = {
    JobStatus.FAILED.value,
    JobStatus.ABANDONED.value,
    JobStatus.CANCELLED.value,
    JobStatus.CLEANED.value,
    JobStatus.NOT_ENABLED.value,
    JobStatus.QUEUE_FULL.value,
    JobStatus.BUDGET_LIMIT.value,
    JobStatus.TIMED_OUT.value,
}


ACTIVE_JOB_STATUSES = {
    JobStatus.CREATED.value,
    JobStatus.VALIDATING.value,
    JobStatus.QUEUED.value,
    JobStatus.QUEUED_CPU.value,
    JobStatus.QUEUED_GPU.value,
    JobStatus.SCHEDULING.value,
    JobStatus.PROVISIONING.value,
    JobStatus.STARTING.value,
    JobStatus.STARTING_GPU.value,
    JobStatus.WAITING_FOR_GPU.value,
    JobStatus.UPLOADING.value,
    JobStatus.UPLOADED.value,
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
    JobStatus.CLEANING_UP.value,
}


# Resource queues are a subset of ACTIVE_JOB_STATUSES.  Keeping this canonical
# prevents status consumers from treating packaging, syncing, or cancellation
# as a terminal state while still allowing queue-specific policy checks.
QUEUED_RESOURCE_JOB_STATUSES = frozenset(
    {
        JobStatus.QUEUED_CPU.value,
        JobStatus.QUEUED_GPU.value,
    }
)


ALLOWED_JOB_STATUS_TRANSITIONS = {
    JobStatus.CREATED.value: {
        JobStatus.VALIDATING.value,
        JobStatus.QUEUED.value,
        JobStatus.QUEUED_CPU.value,
        JobStatus.QUEUED_GPU.value,
        JobStatus.SCHEDULING.value,
        JobStatus.CANCELLED.value,
        JobStatus.NOT_ENABLED.value,
        JobStatus.QUEUE_FULL.value,
        JobStatus.BUDGET_LIMIT.value,
        JobStatus.FAILED.value,
        JobStatus.SUCCEEDED.value,
        JobStatus.ABANDONED.value,
    },
    JobStatus.VALIDATING.value: {
        JobStatus.QUEUED_CPU.value,
        JobStatus.QUEUED_GPU.value,
        JobStatus.NOT_ENABLED.value,
        JobStatus.QUEUE_FULL.value,
        JobStatus.BUDGET_LIMIT.value,
        JobStatus.FAILED.value,
        JobStatus.CANCEL_REQUESTED.value,
        JobStatus.CANCELLED.value,
    },
    JobStatus.QUEUED.value: {JobStatus.SCHEDULING.value, JobStatus.STARTING.value, JobStatus.STARTING_GPU.value, JobStatus.RUNNING.value, JobStatus.CANCELLED.value, JobStatus.CANCEL_REQUESTED.value, JobStatus.ABANDONED.value},
    JobStatus.QUEUED_CPU.value: {JobStatus.SCHEDULING.value, JobStatus.STARTING.value, JobStatus.CANCELLED.value, JobStatus.CANCEL_REQUESTED.value, JobStatus.ABANDONED.value},
    JobStatus.QUEUED_GPU.value: {JobStatus.SCHEDULING.value, JobStatus.PROVISIONING.value, JobStatus.STARTING.value, JobStatus.STARTING_GPU.value, JobStatus.CANCELLED.value, JobStatus.CANCEL_REQUESTED.value, JobStatus.ABANDONED.value, JobStatus.BUDGET_LIMIT.value},
    JobStatus.SCHEDULING.value: {JobStatus.PROVISIONING.value, JobStatus.STARTING.value, JobStatus.STARTING_GPU.value, JobStatus.RUNNING.value, JobStatus.FAILED.value, JobStatus.CANCEL_REQUESTED.value, JobStatus.CANCELLED.value, JobStatus.TIMED_OUT.value},
    JobStatus.PROVISIONING.value: {JobStatus.STARTING.value, JobStatus.STARTING_GPU.value, JobStatus.RUNNING.value, JobStatus.FAILED.value, JobStatus.CANCEL_REQUESTED.value, JobStatus.CANCELLED.value, JobStatus.TIMED_OUT.value},
    JobStatus.STARTING.value: {JobStatus.PROVISIONING.value, JobStatus.DOWNLOADING.value, JobStatus.RUNNING.value, JobStatus.FAILED.value, JobStatus.CANCEL_REQUESTED.value, JobStatus.CANCELLED.value, JobStatus.TIMED_OUT.value},
    JobStatus.STARTING_GPU.value: {JobStatus.PROVISIONING.value, JobStatus.UPLOADING.value, JobStatus.RUNNING.value, JobStatus.FAILED.value, JobStatus.CANCEL_REQUESTED.value, JobStatus.CANCELLED.value, JobStatus.TIMED_OUT.value},
    JobStatus.RUNNING.value: {JobStatus.POSTPROCESSING.value, JobStatus.SYNCING.value, JobStatus.DOWNLOADING.value, JobStatus.VERIFYING.value, JobStatus.SUCCEEDED.value, JobStatus.FAILED.value, JobStatus.CANCEL_REQUESTED.value, JobStatus.CANCELLED.value, JobStatus.TIMED_OUT.value, JobStatus.REMOTE_UNREACHABLE.value},
    JobStatus.DOWNLOADING.value: {JobStatus.RUNNING.value, JobStatus.VERIFYING.value, JobStatus.FAILED.value, JobStatus.CANCEL_REQUESTED.value, JobStatus.CANCELLED.value, JobStatus.TIMED_OUT.value},
    JobStatus.POSTPROCESSING.value: {JobStatus.VERIFYING.value, JobStatus.FAILED.value, JobStatus.CANCEL_REQUESTED.value, JobStatus.CANCELLED.value, JobStatus.TIMED_OUT.value},
    JobStatus.VERIFYING.value: {JobStatus.PACKAGING.value, JobStatus.SUCCEEDED.value, JobStatus.FAILED.value, JobStatus.CANCEL_REQUESTED.value, JobStatus.CANCELLED.value},
    JobStatus.PACKAGING.value: {JobStatus.SUCCEEDED.value, JobStatus.FAILED.value, JobStatus.CANCEL_REQUESTED.value, JobStatus.CANCELLED.value},
    JobStatus.CANCEL_REQUESTED.value: {JobStatus.CANCELLED.value, JobStatus.CANCELLING.value, JobStatus.CLEANING_UP.value},
    JobStatus.CANCELLING.value: {JobStatus.CANCELLED.value, JobStatus.CLEANING_UP.value},
    JobStatus.CLEANING_UP.value: {JobStatus.CANCELLED.value, JobStatus.FAILED.value, JobStatus.SUCCEEDED.value},
}


def validate_job_status_transition(current_status: str, new_status: str) -> None:
    """Enforce the terminal-state protections shared by all job updates."""

    current = str(current_status or "")
    new = str(new_status or "")
    if current == new:
        return
    if current in TERMINAL_STATUSES:
        raise ValueError(f"{current} jobs cannot transition to another status.")
    if current in NON_SUCCESS_JOB_STATUSES and new == JobStatus.SUCCEEDED.value:
        raise ValueError(f"{current} jobs cannot transition to SUCCEEDED.")
    allowed = ALLOWED_JOB_STATUS_TRANSITIONS.get(current)
    if allowed is not None and new not in allowed and new not in TERMINAL_STATUSES:
        raise ValueError(f"Illegal job status transition: {current} -> {new}.")


@dataclass
class JobRecord:
    job_id: str
    user_id: str
    workflow: str
    workflow_name: str = ""
    session_id: str | None = None
    owner_session_id: str = ""
    analysis_session_id: str = ""
    anonymous_workspace_id: str = ""
    resource_type: str = ResourceType.GPU.value
    execution_backend: str = ExecutionBackend.GPU_RUNPOD.value
    status: str = JobStatus.CREATED.value
    priority: int = 0
    progress: float = 0.0
    current_step: str = ""
    message: str = ""
    parameters_json: str = "{}"
    local_workspace: str = ""
    remote_workspace: str = ""
    runpod_pod_id: str = ""
    remote_pid: int | None = None
    queue_name: str = "gpu"
    requested_resource: str = ""
    assigned_gpu: str = ""
    device: str = ""
    gpu_name: str = ""
    created_at: str = ""
    queued_at: str = ""
    claimed_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    cancel_requested_at: str = ""
    timeout_at: str = ""
    worker_id: str = ""
    claim_token: str = ""
    attempt: int = 0
    max_attempts: int = 0
    estimated_gpu_cost_usd: float = 0.0
    actual_gpu_cost_usd: float = 0.0
    input_upload_ids_json: str = "[]"
    input_manifest: str = "{}"
    output_manifest: str = "{}"
    output_prefix: str = ""
    metadata_json: str = "{}"
    last_remote_sync_at: str = ""
    runtime_seconds: float = 0.0
    error_code: str = ""
    error_type: str = ""
    error_message: str = ""
    traceback: str = ""
    result_synced: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data.get("workflow_name"):
            data["workflow_name"] = data.get("workflow") or ""
        data["result_synced"] = bool(data["result_synced"])
        return data


JOBS_COLUMNS = [
    "job_id",
    "user_id",
    "workflow",
    "workflow_name",
    "session_id",
    "owner_session_id",
    "analysis_session_id",
    "anonymous_workspace_id",
    "resource_type",
    "execution_backend",
    "status",
    "priority",
    "progress",
    "current_step",
    "message",
    "parameters_json",
    "local_workspace",
    "remote_workspace",
    "runpod_pod_id",
    "remote_pid",
    "queue_name",
    "requested_resource",
    "assigned_gpu",
    "device",
    "gpu_name",
    "created_at",
    "queued_at",
    "claimed_at",
    "started_at",
    "finished_at",
    "cancel_requested_at",
    "timeout_at",
    "worker_id",
    "claim_token",
    "attempt",
    "max_attempts",
    "estimated_gpu_cost_usd",
    "actual_gpu_cost_usd",
    "input_upload_ids_json",
    "input_manifest",
    "output_manifest",
    "output_prefix",
    "metadata_json",
    "last_remote_sync_at",
    "runtime_seconds",
    "error_code",
    "error_type",
    "error_message",
    "traceback",
    "result_synced",
]


def row_to_job(row: Any) -> JobRecord:
    if row is None:
        raise KeyError("Job row is empty.")
    values = {column: row[column] for column in JOBS_COLUMNS}
    values["result_synced"] = bool(values.get("result_synced"))
    for key in ("priority", "attempt", "max_attempts"):
        values[key] = int(values.get(key) or 0)
    for key in ("estimated_gpu_cost_usd", "actual_gpu_cost_usd", "runtime_seconds", "progress"):
        values[key] = float(values.get(key) or 0.0)
    if not values.get("workflow_name"):
        values["workflow_name"] = values.get("workflow") or ""
    return JobRecord(**values)


@dataclass
class UploadRecord:
    upload_id: str
    session_id: str
    original_filename: str
    safe_filename: str
    object_key: str
    multipart_upload_id: str
    declared_size_bytes: int
    # Exact browser-tab analysis scope; legacy rows remain empty and are never
    # selected by active analysis paths.
    analysis_session_id: str = ""
    actual_size_bytes: int = 0
    content_type: str = "application/octet-stream"
    status: str = UploadStatus.INITIATED.value
    created_at: str = ""
    completed_at: str | None = None
    aborted_at: str | None = None
    expires_at: str | None = None
    sha256: str | None = None
    error_code: str | None = None
    metadata_json: str | None = None
    id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def public_dict(self) -> dict[str, Any]:
        data = self.to_dict()
        data.pop("id", None)
        data.pop("object_key", None)
        data.pop("multipart_upload_id", None)
        return data


UPLOADS_COLUMNS = [
    "upload_id",
    "session_id",
    "analysis_session_id",
    "original_filename",
    "safe_filename",
    "object_key",
    "multipart_upload_id",
    "declared_size_bytes",
    "actual_size_bytes",
    "content_type",
    "status",
    "created_at",
    "completed_at",
    "aborted_at",
    "expires_at",
    "sha256",
    "error_code",
    "metadata_json",
]


def row_to_upload(row: Any) -> UploadRecord:
    if row is None:
        raise KeyError("Upload row is empty.")
    values = {column: row[column] for column in UPLOADS_COLUMNS}
    values["id"] = row["id"]
    values["declared_size_bytes"] = int(values.get("declared_size_bytes") or 0)
    values["actual_size_bytes"] = int(values.get("actual_size_bytes") or 0)
    return UploadRecord(**values)
