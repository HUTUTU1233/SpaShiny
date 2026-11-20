from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STATUS_PASS = "PASS"
STATUS_WARN = "WARN"
STATUS_FAIL = "FAIL"
STATUS_UNKNOWN = "UNKNOWN"

SEVERITY_INFO = "INFO"
SEVERITY_WARNING = "WARNING"
SEVERITY_ERROR = "ERROR"

CONFIDENCE_LOW = "LOW"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_HIGH = "HIGH"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def as_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return as_jsonable(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): as_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [as_jsonable(item) for item in value]
    return value


def json_dumps(value: Any) -> str:
    return json.dumps(as_jsonable(value), ensure_ascii=False, indent=2, sort_keys=True)


@dataclass
class QualityCheckResult:
    check_name: str
    status: str
    observed_value: str = ""
    expected_rule: str = ""
    message: str = ""
    severity: str = SEVERITY_INFO
    remediation: str = ""
    evidence_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return as_jsonable(self)


@dataclass
class DataQualityReport:
    report_id: str
    dataset_id: str
    modality: str = ""
    sample_count: int = 0
    file_count: int = 0
    total_size_bytes: int = 0
    readiness_score: float = 0.0
    status: str = STATUS_UNKNOWN
    checks: list[QualityCheckResult] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    synthetic: bool = False
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return as_jsonable(self)


@dataclass
class WorkflowRecommendation:
    workflow_name: str
    workflow_label: str
    rank: int
    recommended: bool
    executable: bool
    reason: str
    required_inputs: list[str] = field(default_factory=list)
    cpu_or_gpu: str = ""
    runtime_profile: str = ""
    dispatch_enabled: bool = False
    blocked_reason: str = ""
    confidence: str = CONFIDENCE_MEDIUM

    def to_dict(self) -> dict[str, Any]:
        return as_jsonable(self)


@dataclass
class ResourceEstimate:
    workflow_name: str
    recommended_runtime_class: str
    cpu_or_gpu: str
    estimated_cpu_cores: int = 0
    estimated_memory_gb: float = 0.0
    estimated_vram_gb: float = 0.0
    estimated_runtime_seconds: int | None = None
    confidence: str = CONFIDENCE_LOW
    basis: str = ""
    warning: str = ""
    error_code: str = ""
    requires_cuda: bool = False

    def to_dict(self) -> dict[str, Any]:
        return as_jsonable(self)


@dataclass
class CostEstimate:
    workflow_name: str
    provider_name: str
    runtime_class: str
    estimated_seconds: int
    estimated_cost_usd: float
    lower_bound_usd: float
    upper_bound_usd: float
    confidence: str
    pricing_version: str
    synthetic_pricing: bool = True
    warning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return as_jsonable(self)


@dataclass
class QuotaDecision:
    allowed: bool
    error_code: str = ""
    message: str = ""
    session_id: str = ""
    resource_type: str = ""
    active_jobs: int = 0
    queued_jobs: int = 0
    storage_bytes: int = 0
    limits: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return as_jsonable(self)


@dataclass
class ReproducibilityManifest:
    manifest_id: str
    job_id: str
    workflow_name: str
    workflow_version: str = ""
    runtime_profile: str = ""
    worker_image: str = ""
    model_registry_version: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    input_artifacts: list[dict[str, Any]] = field(default_factory=list)
    output_artifacts: list[dict[str, Any]] = field(default_factory=list)
    dependency_versions: dict[str, str] = field(default_factory=dict)
    random_seed: str = ""
    created_at: str = field(default_factory=utc_now)
    synthetic: bool = False

    def to_dict(self) -> dict[str, Any]:
        return as_jsonable(self)


@dataclass
class PlatformManagementReport:
    report_type: str
    records: list[dict[str, Any]]
    generated_at: str = field(default_factory=utc_now)
    synthetic: bool = False
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return as_jsonable(self)
