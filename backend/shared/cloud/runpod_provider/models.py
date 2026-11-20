from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class RunPodInstanceState(str, Enum):
    REQUESTED = "REQUESTED"
    CREATING = "CREATING"
    STARTING = "STARTING"
    READY = "READY"
    BUSY = "BUSY"
    STOPPING = "STOPPING"
    TERMINATING = "TERMINATING"
    TERMINATED = "TERMINATED"
    CREATE_FAILED = "CREATE_FAILED"
    READY_TIMEOUT = "READY_TIMEOUT"
    TERMINATE_FAILED = "TERMINATE_FAILED"
    ORPHANED = "ORPHANED"
    UNKNOWN = "UNKNOWN"


TERMINAL_INSTANCE_STATES = {
    RunPodInstanceState.TERMINATED.value,
    RunPodInstanceState.CREATE_FAILED.value,
    RunPodInstanceState.READY_TIMEOUT.value,
}


@dataclass(frozen=True)
class PodSpec:
    job_id: str
    session_id: str
    workflow_name: str
    pod_name: str
    image_name: str
    image_digest: str = ""
    template_id: str = ""
    gpu_type_candidates: tuple[str, ...] = ()
    gpu_count: int = 1
    cloud_type: str = ""
    location_candidates: tuple[str, ...] = ()
    container_disk_gb: int = 30
    volume_disk_gb: int = 0
    exposed_ports: tuple[int, ...] = ()
    environment_variable_names: tuple[str, ...] = ()
    worker_id: str = ""
    claim_token: str = field(default="", repr=False)
    job_spec_url: str = field(default="", repr=False)
    job_spec_sha256: str = ""
    callback_token: str = field(default="", repr=False)
    workflow_version: str = ""
    runtime_profile: str = "spatialmeta"
    control_api_base_url: str = ""
    max_runtime_seconds: int = 7200
    labels: dict[str, str] = field(default_factory=dict)

    @property
    def image_reference(self) -> str:
        if self.image_digest:
            return f"{self.image_name}@{self.image_digest}"
        return self.image_name

    def to_safe_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("claim_token", None)
        data.pop("job_spec_url", None)
        data.pop("callback_token", None)
        data["claim_token_configured"] = bool(self.claim_token)
        data["job_spec_url_configured"] = bool(self.job_spec_url)
        data["callback_token_configured"] = bool(self.callback_token)
        data["image_reference"] = self.image_reference
        data["environment_variable_names"] = sorted(set(self.environment_variable_names))
        return data


@dataclass(frozen=True)
class ProviderPod:
    provider_pod_id: str
    name: str
    state: str
    provider_name: str = "fake"
    template_id: str = ""
    image_reference: str = ""
    gpu_type: str = ""
    gpu_count: int = 1
    cloud_type: str = ""
    location: str = ""
    public_ip: str = ""
    ssh_port: int | None = None
    hourly_cost_usd: float = 0.0
    created_at: str = ""
    metadata: dict[str, str] = field(default_factory=dict)
    raw_status: str = ""

    def to_safe_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("metadata", None)
        return data
