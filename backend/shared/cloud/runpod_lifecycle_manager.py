from __future__ import annotations

import json
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import quote

from .cleanup_retry_repository import CleanupRetryRepository, redact_cleanup_message
from .compute_providers import ComputeProviderRegistry
from .config import SpaShinyCloudConfig, load_cloud_config
from .database import CloudDatabase, RUNPOD_INSTANCE_TERMINAL_STATES, utc_now
from .gpu_budget import GpuBudgetManager
from .input_resolver import sign_worker_callback_token, sign_worker_job_spec_token
from .job_queue_repository import LEASE_ACTIVE, JobQueueRepository
from .models import ACTIVE_JOB_STATUSES, JobRecord, JobStatus, ResourceType, TERMINAL_STATUSES
from .runpod_provider import (
    FakeRunPodProvider,
    PodSpec,
    ProviderPod,
    RealRunPodProvider,
    RunPodCapacityUnavailable,
    RunPodCreateError,
    RunPodNotFound,
    RunPodProvider,
    RunPodReadyTimeout,
    RunPodTerminateError,
)
from .runpod_provider.models import RunPodInstanceState
from .session_manager import SessionManager
from .storage import safe_name
from .storage_quota import GlobalStorageLimitExceeded, StorageQuotaManager
from .workflow_registry import ensure_workflow_dispatch_enabled, get_workflow_spec


class RunPodLifecycleError(RuntimeError):
    pass


class ResultStorageReservationError(RunPodLifecycleError):
    pass


Clock = Callable[[], datetime]


def utc_dt(value: str | None = None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    dt = datetime.fromisoformat(str(value))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass
class RunPodLifecycleManager:
    database: CloudDatabase | None = None
    config: SpaShinyCloudConfig | None = None
    provider: RunPodProvider | None = None
    budget: GpuBudgetManager | None = None
    queue: JobQueueRepository | None = None
    sessions: SessionManager | None = None
    cleanup_retries: CleanupRetryRepository | None = None
    result_quota: StorageQuotaManager | None = None
    clock: Clock | None = None

    def __post_init__(self) -> None:
        if self.config is None:
            self.config = load_cloud_config()
        if self.database is None:
            self.database = CloudDatabase(config=self.config)
        self._provider_injected = self.provider is not None
        if self.provider is None:
            self.provider = self._default_provider()
        if self.budget is None:
            self.budget = GpuBudgetManager(self.database, self.config)
        if self.queue is None:
            self.queue = JobQueueRepository(self.database, self.config)
        if self.sessions is None:
            self.sessions = SessionManager(database=self.database, config=self.config)
        if self.cleanup_retries is None:
            self.cleanup_retries = CleanupRetryRepository(database=self.database, config=self.config)
        if self.result_quota is None:
            self.result_quota = StorageQuotaManager(database=self.database, config=self.config)
        if self.clock is None:
            self.clock = lambda: datetime.now(timezone.utc)

    def provision_for_job(self, job_id: str) -> dict[str, Any]:
        job = self.database.get_job(job_id)
        self._validate_job_can_provision(job)
        if not getattr(self, "_provider_injected", False):
            self.provider = ComputeProviderRegistry(self.config).select_provider(job)
        existing = self.database.get_runpod_instance_by_job(job_id, active_only=True)
        if existing is not None:
            return existing
        spec = self._build_spec(job)
        estimated_cost = self._estimate_cost_for_spec(spec)
        self._check_budget(job, estimated_cost)
        try:
            self.result_quota.reserve_result_storage_for_job(job)
        except GlobalStorageLimitExceeded as exc:
            self.database.update_job(
                job.job_id,
                status=JobStatus.FAILED.value,
                finished_at=utc_now(),
                error_code="INSUFFICIENT_RESULT_STORAGE",
                error_message=redact_cleanup_message(exc),
                current_step="Insufficient result storage",
            )
            raise ResultStorageReservationError("INSUFFICIENT_RESULT_STORAGE") from exc
        instance_id = "rpi_" + secrets.token_hex(16)
        create_key = f"{job.job_id}:{secrets.token_hex(12)}"
        now = self._now()
        values = {
            "instance_id": instance_id,
            "provider_pod_id": None,
            "job_id": job.job_id,
            "session_id": job.session_id or "",
            "provider_name": self.provider.provider_name,
            "pod_name": spec.pod_name,
            "state": RunPodInstanceState.REQUESTED.value,
            "template_id": spec.template_id,
            "image_reference": spec.image_reference,
            "gpu_type": spec.gpu_type_candidates[0] if spec.gpu_type_candidates else "",
            "gpu_count": int(spec.gpu_count),
            "cloud_type": spec.cloud_type,
            "location": spec.location_candidates[0] if spec.location_candidates else "",
            "public_ip": "",
            "ssh_port": None,
            "requested_at": now,
            "created_at": None,
            "ready_at": None,
            "started_at": None,
            "stop_requested_at": None,
            "terminate_requested_at": None,
            "terminated_at": None,
            "last_polled_at": None,
            "last_provider_status": "",
            "estimated_hourly_cost_usd": float(self.config.runpod_gpu_hourly_cost_usd or 0.0),
            "estimated_cost_usd": estimated_cost,
            "actual_runtime_seconds": 0.0,
            "actual_cost_usd": 0.0,
            "create_request_key": create_key,
            "error_code": "",
            "error_message": "",
            "metadata_json": json.dumps(
                {
                    "job_id": job.job_id,
                    "session_id": job.session_id or "",
                    "compute_provider": self.provider.provider_name,
                    "provider_contract": "signed_url_callback_v1",
                    "ssh": False,
                },
                sort_keys=True,
            ),
        }
        try:
            instance = self.database.create_runpod_instance(values)
        except Exception:
            current = self.database.get_runpod_instance_by_job(job_id, active_only=True)
            if current is not None:
                return current
            self.result_quota.release_result_reservation_for_job(job, status="FAILED", error_message="runpod instance database insert failed")
            raise
        try:
            self.database.update_runpod_instance(instance_id, state=RunPodInstanceState.CREATING.value)
            pod = self.provider.create_pod(spec, create_key)
            if pod.state == RunPodInstanceState.CREATE_FAILED.value:
                raise RunPodCreateError("RunPod pod creation failed.")
            return self._sync_provider_pod(instance_id, pod, state=pod.state or RunPodInstanceState.CREATING.value, created_at=self._now())
        except RunPodCapacityUnavailable as exc:
            self._mark_create_failed(instance_id, "CAPACITY_UNAVAILABLE", exc)
            raise
        except Exception as exc:
            self._mark_create_failed(instance_id, "RUNPOD_CREATE_FAILED", exc)
            raise RunPodCreateError(redact_cleanup_message(exc)) from exc

    def poll_instance(self, instance_id: str) -> dict[str, Any]:
        instance = self.database.get_runpod_instance(instance_id)
        pod_id = str(instance.get("provider_pod_id") or "")
        if not pod_id:
            return instance
        try:
            pod = self.provider.get_pod(pod_id)
            return self._sync_provider_pod(instance_id, pod)
        except RunPodNotFound:
            return self.database.update_runpod_instance(
                instance_id,
                state=RunPodInstanceState.TERMINATED.value,
                terminated_at=self._now(),
                last_polled_at=self._now(),
                last_provider_status="NOT_FOUND",
            )

    def wait_ready(self, instance_id: str) -> dict[str, Any]:
        instance = self.database.get_runpod_instance(instance_id)
        pod_id = str(instance.get("provider_pod_id") or "")
        if not pod_id:
            raise RunPodLifecycleError("RunPod instance does not have a provider pod id.")
        try:
            pod = self.provider.wait_until_ready(pod_id, int(self.config.runpod_pod_ready_timeout_seconds))
            return self._sync_provider_pod(
                instance_id,
                pod,
                state=RunPodInstanceState.READY.value,
                ready_at=self._now(),
                started_at=self._now(),
            )
        except RunPodReadyTimeout:
            self.database.update_runpod_instance(instance_id, state=RunPodInstanceState.READY_TIMEOUT.value, error_code="READY_TIMEOUT", error_message="RunPod pod readiness timed out.")
            self.terminate_instance(instance_id, reason="ready_timeout")
            self.result_quota.release_result_reservation_for_job(str(instance["job_id"]), status="FAILED", error_message="RunPod pod readiness timed out.")
            raise

    def mark_busy(self, instance_id: str) -> dict[str, Any]:
        return self.database.update_runpod_instance(instance_id, state=RunPodInstanceState.BUSY.value, last_polled_at=self._now())

    def request_stop(self, instance_id: str) -> dict[str, Any]:
        instance = self.database.get_runpod_instance(instance_id)
        pod_id = str(instance.get("provider_pod_id") or "")
        self.database.update_runpod_instance(instance_id, state=RunPodInstanceState.STOPPING.value, stop_requested_at=self._now())
        if pod_id:
            pod = self.provider.stop_pod(pod_id)
            return self._sync_provider_pod(instance_id, pod, state=RunPodInstanceState.STOPPING.value)
        return self.database.get_runpod_instance(instance_id)

    def terminate_instance(self, instance_id: str, reason: str = "terminate") -> dict[str, Any]:
        instance = self.database.get_runpod_instance(instance_id)
        if instance["state"] == RunPodInstanceState.TERMINATED.value:
            return instance
        pod_id = str(instance.get("provider_pod_id") or "")
        self.database.update_runpod_instance(
            instance_id,
            state=RunPodInstanceState.TERMINATING.value,
            terminate_requested_at=self._now(),
            error_code=instance.get("error_code") or "",
        )
        try:
            if pod_id:
                self.provider.terminate_pod(pod_id)
                try:
                    self.provider.wait_until_terminated(pod_id, int(self.config.runpod_pod_terminate_timeout_seconds))
                except RunPodNotFound:
                    pass
            terminated_at = self._now()
            runtime_seconds, actual_cost = self._cost_at_termination(instance, terminated_at)
            updated = self.database.update_runpod_instance(
                instance_id,
                state=RunPodInstanceState.TERMINATED.value,
                terminated_at=terminated_at,
                last_polled_at=terminated_at,
                last_provider_status=RunPodInstanceState.TERMINATED.value,
                actual_runtime_seconds=runtime_seconds,
                actual_cost_usd=actual_cost,
            )
            self.budget.record_gpu_job_finish(runtime_seconds, actual_cost, self._usage_date(terminated_at))
            self._write_job_actual_cost(str(instance["job_id"]), runtime_seconds, actual_cost)
            return updated
        except RunPodNotFound:
            terminated_at = self._now()
            runtime_seconds, actual_cost = self._cost_at_termination(instance, terminated_at)
            updated = self.database.update_runpod_instance(
                instance_id,
                state=RunPodInstanceState.TERMINATED.value,
                terminated_at=terminated_at,
                last_polled_at=terminated_at,
                last_provider_status="NOT_FOUND",
                actual_runtime_seconds=runtime_seconds,
                actual_cost_usd=actual_cost,
            )
            self.budget.record_gpu_job_finish(runtime_seconds, actual_cost, self._usage_date(terminated_at))
            self._write_job_actual_cost(str(instance["job_id"]), runtime_seconds, actual_cost)
            return updated
        except Exception as exc:
            self.database.update_runpod_instance(
                instance_id,
                state=RunPodInstanceState.TERMINATE_FAILED.value,
                error_code="TERMINATE_FAILED",
                error_message=redact_cleanup_message(exc),
            )
            raise RunPodTerminateError(redact_cleanup_message(exc)) from exc

    def reconcile_instance(self, instance_id: str) -> dict[str, Any]:
        instance = self.database.get_runpod_instance(instance_id)
        if instance["state"] in RUNPOD_INSTANCE_TERMINAL_STATES:
            return instance
        pod_id = str(instance.get("provider_pod_id") or "")
        if not pod_id:
            recovered = self._recover_provider_pod_for_instance(instance)
            if recovered is None:
                self._fail_missing_provider_pod(instance)
                return self.database.get_runpod_instance(instance_id)
            instance = self.database.update_runpod_instance(instance_id, provider_pod_id=recovered.provider_pod_id)
            pod_id = recovered.provider_pod_id
        try:
            job = self.database.get_job(str(instance["job_id"]))
        except KeyError:
            self.database.update_runpod_instance(instance_id, state=RunPodInstanceState.ORPHANED.value, error_code="JOB_NOT_FOUND")
            return self.terminate_instance(instance_id, reason="orphan_job")
        if job.status in TERMINAL_STATUSES:
            if job.status != JobStatus.SUCCEEDED.value:
                self.result_quota.release_result_reservation_for_job(job.job_id, status="RELEASED", error_message=f"job terminal: {job.status}")
            return self.terminate_instance(instance_id, reason="job_terminal")
        try:
            session = self.sessions.get_session(str(instance["session_id"]))
            if session.status in {"ABANDONED", "CLEANING", "CLEANED"}:
                return self.terminate_instance(instance_id, reason="session_inactive")
        except Exception:
            return self.terminate_instance(instance_id, reason="session_missing")
        if self._ready_idle_seconds(instance) > int(self.config.runpod_pod_ready_timeout_seconds):
            self.database.update_job(job.job_id, status=JobStatus.TIMED_OUT.value, finished_at=utc_now(), error_code="RUNPOD_READY_IDLE_TIMEOUT")
            self.database.update_runpod_instance(instance_id, error_code="RUNPOD_READY_IDLE_TIMEOUT", error_message="RunPod pod stayed READY without becoming BUSY.")
            self.result_quota.release_result_reservation_for_job(job.job_id, status="RELEASED", error_message="RunPod pod stayed READY without becoming BUSY.")
            return self.terminate_instance(instance_id, reason="ready_idle_timeout")
        if self._age_seconds(instance) > int(self.config.runpod_max_pod_age_seconds):
            self.database.update_job(job.job_id, status=JobStatus.TIMED_OUT.value, finished_at=utc_now(), error_code="RUNPOD_MAX_AGE")
            self.result_quota.release_result_reservation_for_job(job.job_id, status="RELEASED", error_message="RunPod pod exceeded maximum age.")
            return self.terminate_instance(instance_id, reason="max_age")
        if instance["state"] == RunPodInstanceState.TERMINATING.value:
            return self.terminate_instance(instance_id, reason="reconcile_terminating")
        return self.poll_instance(instance_id)

    def reconcile_all_managed_instances(self) -> dict[str, Any]:
        provider_pods = self.provider.list_managed_pods()
        provider_by_id = {pod.provider_pod_id: pod for pod in provider_pods if pod.provider_pod_id}
        db_instances = self.database.list_runpod_instances(limit=10000)
        db_by_provider_id = {str(item.get("provider_pod_id")): item for item in db_instances if item.get("provider_pod_id")}

        reconciled: list[str] = []
        provider_missing: list[str] = []
        for instance in self.database.list_runpod_instances(active_only=True, limit=10000):
            pod_id = str(instance.get("provider_pod_id") or "")
            if pod_id and pod_id not in provider_by_id:
                self._fail_missing_provider_pod(instance)
                provider_missing.append(str(instance["instance_id"]))
                continue
            reconciled.append(str(self.reconcile_instance(str(instance["instance_id"]))["instance_id"]))

        terminated_orphans: list[str] = []
        ignored: list[str] = []
        retry_pods: list[str] = []
        for pod in provider_pods:
            if pod.state in RUNPOD_INSTANCE_TERMINAL_STATES:
                continue
            instance = db_by_provider_id.get(pod.provider_pod_id)
            if instance is not None:
                if str(instance.get("state") or "") in RUNPOD_INSTANCE_TERMINAL_STATES:
                    if self._terminate_provider_pod(pod, session_id=str(instance.get("session_id") or ""), action="terminate_terminal_db_pod"):
                        terminated_orphans.append(pod.provider_pod_id)
                    else:
                        retry_pods.append(pod.provider_pod_id)
                continue
            if not self.is_managed_pod(pod):
                ignored.append(pod.provider_pod_id)
                continue
            if self._terminate_provider_pod(pod, session_id=str(pod.metadata.get("session_id") or ""), action="terminate_orphan_provider_pod"):
                terminated_orphans.append(pod.provider_pod_id)
            else:
                retry_pods.append(pod.provider_pod_id)
        return {
            "reconciled": reconciled,
            "provider_missing": provider_missing,
            "terminated_orphans": terminated_orphans,
            "retry_pods": retry_pods,
            "ignored": ignored,
        }

    def is_managed_pod(self, provider_pod: ProviderPod) -> bool:
        evidence = self._managed_pod_evidence(provider_pod)
        return evidence["known_provider_pod_id"] or evidence["known_create_request_key"] or int(evidence["count"]) >= 2

    def terminate_provider_pod(self, provider_pod_id: str, *, session_id: str = "", action: str = "cleanup_retry") -> bool:
        try:
            pod = self.provider.get_pod(provider_pod_id)
        except RunPodNotFound:
            self._record_runpod_cleanup_event(provider_pod_id, session_id, action, "completed", "NOT_FOUND", "Provider pod was already absent.")
            return True
        return self._terminate_provider_pod(pod, session_id=session_id, action=action)

    def fail_job_for_result_storage_limit(self, job_id: str, error_message: object = "Result storage limit exceeded.") -> None:
        instance = self.database.get_runpod_instance_by_job(job_id, active_only=True)
        if instance is not None:
            try:
                self.terminate_instance(str(instance["instance_id"]), reason="result_storage_limit_exceeded")
            except Exception:
                pass
        self.result_quota.release_result_reservation_for_job(job_id, status="FAILED", error_message=error_message)
        try:
            self.database.update_job(
                job_id,
                status=JobStatus.FAILED.value,
                finished_at=utc_now(),
                error_code="RESULT_STORAGE_LIMIT_EXCEEDED",
                error_message=redact_cleanup_message(error_message),
                current_step="Result storage limit exceeded",
            )
        finally:
            self.queue.release_job_leases(job_id)

    def estimate_instance_cost(self, instance_id: str) -> float:
        instance = self.database.get_runpod_instance(instance_id)
        max_runtime = float(self.config.runpod_max_pod_age_seconds or self.config.max_gpu_job_seconds)
        return float(instance.get("estimated_hourly_cost_usd") or 0.0) * (max_runtime / 3600.0)

    def _default_provider(self) -> RunPodProvider:
        if self.config.compute_provider_mode:
            return ComputeProviderRegistry(self.config).select_provider()
        if self.config.runpod_provider_mode == "real":
            return RealRunPodProvider(self.config)
        return FakeRunPodProvider()

    def _validate_job_can_provision(self, job: JobRecord) -> None:
        if job.resource_type != ResourceType.GPU.value:
            raise RunPodLifecycleError("Only GPU jobs can provision RunPod pods.")
        try:
            ensure_workflow_dispatch_enabled(job.workflow_name or job.workflow)
        except NotImplementedError as exc:
            raise RunPodLifecycleError(str(exc)) from exc
        if job.status not in {JobStatus.PROVISIONING.value, JobStatus.STARTING.value, JobStatus.RUNNING.value, JobStatus.CANCEL_REQUESTED.value}:
            raise RunPodLifecycleError(f"Job is not in a provisionable state: {job.status}")
        if job.status == JobStatus.CANCEL_REQUESTED.value:
            raise RunPodLifecycleError("Job cancellation is already requested.")
        if not self._has_active_lease(job.job_id):
            raise RunPodLifecycleError("GPU job does not have an active resource lease.")

    def _has_active_lease(self, job_id: str) -> bool:
        with self.database.connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM resource_leases
                WHERE job_id=? AND resource_type='gpu' AND status=? LIMIT 1
                """,
                (job_id, LEASE_ACTIVE),
            ).fetchone()
        return row is not None

    def _build_spec(self, job: JobRecord) -> PodSpec:
        suffix = safe_name(job.job_id, "job")[:18]
        pod_name = f"{safe_name(self.config.runpod_name_prefix, 'spashiny')}-{suffix}-{secrets.token_hex(4)}"
        try:
            metadata = json.loads(job.metadata_json or "{}")
            metadata = metadata if isinstance(metadata, dict) else {}
        except Exception:
            metadata = {}
        contract = self._signed_worker_contract(job, metadata)
        return PodSpec(
            job_id=job.job_id,
            session_id=job.session_id or "",
            workflow_name=job.workflow_name or job.workflow,
            pod_name=pod_name,
            image_name=self._worker_image_for_provider(job),
            image_digest=self.config.runpod_image_digest or "",
            template_id=self._template_for_provider(),
            gpu_type_candidates=self._gpu_candidates_for_provider(),
            gpu_count=max(1, int(self.config.runpod_gpu_count)),
            cloud_type=self.config.runpod_cloud_type,
            location_candidates=tuple(self.config.runpod_location_candidates),
            container_disk_gb=int(self.config.runpod_container_disk_gb),
            volume_disk_gb=max(0, int(self.config.runpod_volume_disk_gb)),
            exposed_ports=(),
            environment_variable_names=(
                "SPASHINY_JOB_ID",
                "SPASHINY_JOB_SPEC_URL",
                "SPASHINY_JOB_SPEC_SHA256",
                "SPASHINY_CALLBACK_TOKEN",
                "SPASHINY_WORKFLOW_VERSION",
                "SPASHINY_WORKER_CONTRACT_MODE",
            ),
            worker_id=job.worker_id or "",
            claim_token=job.claim_token or "",
            job_spec_url=str(contract.get("job_spec_url") or ""),
            job_spec_sha256=str(contract.get("job_spec_sha256") or ""),
            callback_token=str(contract.get("callback_token") or ""),
            workflow_version=str(contract.get("workflow_version") or self.config.model_registry_version),
            runtime_profile=str(contract.get("runtime_profile") or "spatialmeta"),
            control_api_base_url=os.environ.get("SPASHINY_CONTROL_API_BASE_URL", "http://spashiny-control:8000"),
            max_runtime_seconds=int(self.config.runpod_max_pod_age_seconds),
            labels={
                "managed_by": "spashiny",
                "job_id": job.job_id,
                "session_id": job.session_id or "",
                "workflow": job.workflow_name or job.workflow,
                "compute_provider": getattr(self.provider, "provider_name", "gpu"),
                "ssh": "false",
            },
        )

    def _signed_worker_contract(self, job: JobRecord, metadata: dict[str, Any]) -> dict[str, str]:
        runtime_profile = self._runtime_profile_for_job(job)
        if metadata.get("job_spec_url") and metadata.get("callback_token"):
            return {
                "job_spec_url": str(metadata.get("job_spec_url") or ""),
                "job_spec_sha256": str(metadata.get("job_spec_sha256") or ""),
                "callback_token": str(metadata.get("callback_token") or ""),
                "workflow_version": str(metadata.get("workflow_version") or self.config.model_registry_version),
                "runtime_profile": runtime_profile,
            }
        base = (self.config.public_base_url or self.config.public_origin or "").rstrip("/")
        if not base or not job.worker_id or not job.claim_token:
            return {
                "job_spec_url": "",
                "job_spec_sha256": "",
                "callback_token": "",
                "workflow_version": str(self.config.model_registry_version),
                "runtime_profile": runtime_profile,
            }
        expires_at = int(time.time()) + int(self.config.worker_callback_token_ttl_seconds)
        job_spec_token = sign_worker_job_spec_token(job, expires_at=expires_at, config=self.config)
        callback_token = sign_worker_callback_token(job, expires_at=expires_at, config=self.config)
        return {
            "job_spec_url": f"{base}/api/jobs/{quote(job.job_id, safe='')}/worker-job-spec?token={quote(job_spec_token, safe='')}",
            "job_spec_sha256": "",
            "callback_token": callback_token,
            "workflow_version": str(self.config.model_registry_version),
            "runtime_profile": runtime_profile,
        }

    def _worker_image_for_provider(self, job: JobRecord) -> str:
        provider_name = getattr(self.provider, "provider_name", "")
        runtime_profile = self._runtime_profile_for_job(job)
        if (self.config.compute_provider_mode or "fake").lower() == "real":
            return self.config.gpu_worker_image_for_profile(runtime_profile)
        specs = ComputeProviderRegistry(self.config).specs()
        if provider_name in specs:
            return specs[provider_name].worker_image
        if (self.config.compute_provider_mode or "fake").lower() == "real":
            return self.config.spashiny_gpu_worker_image
        return self.config.runpod_gpu_image or self.config.runpod_image

    def _runtime_profile_for_job(self, job: JobRecord) -> str:
        spec = get_workflow_spec(job.workflow_name or job.workflow)
        return str(spec.runtime_profile or "spatialmeta")

    def _template_for_provider(self) -> str:
        provider_name = getattr(self.provider, "provider_name", "")
        if (self.config.compute_provider_mode or "fake").lower() == "real" and provider_name == "gpu_provider_fallback":
            return ""
        specs = ComputeProviderRegistry(self.config).specs()
        if provider_name in specs:
            return specs[provider_name].template_id
        return self.config.runpod_gpu_template_id or self.config.runpod_template_id or ""

    def _gpu_candidates_for_provider(self) -> tuple[str, ...]:
        provider_name = getattr(self.provider, "provider_name", "")
        if (self.config.compute_provider_mode or "fake").lower() == "real" and provider_name == "gpu_provider_fallback":
            return ("T4", "RTX_3090")
        specs = ComputeProviderRegistry(self.config).specs()
        if provider_name in specs:
            return (specs[provider_name].gpu_profile,)
        return tuple(self.config.runpod_gpu_type_candidates)

    def _check_budget(self, job: JobRecord, estimated_cost: float) -> None:
        budget = float(self.config.daily_gpu_budget_usd)
        if budget <= 0:
            raise RunPodLifecycleError("GPU budget is exhausted.")
        usage = self.budget.get_gpu_usage()
        remaining_new_cost = max(0.0, float(estimated_cost) - float(job.estimated_gpu_cost_usd or 0.0))
        if usage["estimated_cost_usd"] + remaining_new_cost > budget:
            raise RunPodLifecycleError("GPU budget is exhausted.")

    def _estimate_cost_for_spec(self, spec: PodSpec) -> float:
        return float(self.config.runpod_gpu_hourly_cost_usd or 0.0) * (float(spec.max_runtime_seconds or 0) / 3600.0)

    def _mark_create_failed(self, instance_id: str, code: str, exc: object) -> None:
        self.database.update_runpod_instance(
            instance_id,
            state=RunPodInstanceState.CREATE_FAILED.value,
            error_code=code,
            error_message=redact_cleanup_message(exc),
            last_polled_at=self._now(),
        )
        instance = self.database.get_runpod_instance(instance_id)
        self.result_quota.release_result_reservation_for_job(str(instance["job_id"]), status="FAILED", error_message=code)
        try:
            self.database.update_job(str(instance["job_id"]), status=JobStatus.FAILED.value, finished_at=utc_now(), error_code=code, current_step="RunPod create failed")
        except Exception:
            pass

    def _sync_provider_pod(
        self,
        instance_id: str,
        pod: ProviderPod,
        *,
        state: str | None = None,
        created_at: str | None = None,
        ready_at: str | None = None,
        started_at: str | None = None,
    ) -> dict[str, Any]:
        updates: dict[str, Any] = {
            "provider_pod_id": pod.provider_pod_id,
            "state": state or pod.state,
            "gpu_type": pod.gpu_type,
            "gpu_count": int(pod.gpu_count),
            "cloud_type": pod.cloud_type,
            "location": pod.location,
            "public_ip": pod.public_ip,
            "ssh_port": pod.ssh_port,
            "last_polled_at": self._now(),
            "last_provider_status": pod.raw_status or pod.state,
        }
        if created_at:
            updates["created_at"] = created_at
        if ready_at:
            updates["ready_at"] = ready_at
        if started_at:
            updates["started_at"] = started_at
        if pod.hourly_cost_usd:
            updates["estimated_hourly_cost_usd"] = float(pod.hourly_cost_usd)
        return self.database.update_runpod_instance(instance_id, **updates)

    def _recover_provider_pod_for_instance(self, instance: dict[str, Any]) -> ProviderPod | None:
        for pod in self.provider.list_managed_pods():
            if not self.is_managed_pod(pod):
                continue
            if pod.name == instance["pod_name"] or pod.metadata.get("job_id") == instance["job_id"]:
                return pod
        return None

    def _managed_pod_evidence(self, pod: ProviderPod) -> dict[str, Any]:
        provider_pod_id = str(pod.provider_pod_id or "")
        evidence: dict[str, Any] = {
            "known_provider_pod_id": False,
            "known_create_request_key": False,
            "items": [],
            "count": 0,
        }
        if provider_pod_id and self.database.get_runpod_instance_by_provider_pod_id(provider_pod_id) is not None:
            evidence["known_provider_pod_id"] = True
            evidence["items"].append("provider_pod_id")
            return evidence
        create_request_key = str(pod.metadata.get("create_request_key") or "")
        if create_request_key:
            for instance in self.database.list_runpod_instances(limit=10000):
                if str(instance.get("create_request_key") or "") == create_request_key:
                    evidence["known_create_request_key"] = True
                    evidence["items"].append("create_request_key")
                    return evidence

        count = 0
        items: list[str] = []
        prefix = safe_name(self.config.runpod_name_prefix, "spashiny")
        if pod.name.startswith(prefix + "-"):
            count += 1
            items.append("pod_name_prefix")
        if str(pod.metadata.get("managed_by") or "").lower() == "spashiny":
            count += 1
            items.append("managed_by")
        if pod.metadata.get("job_id") or pod.metadata.get("session_id"):
            count += 1
            items.append("job_or_session_marker")
        if self.config.runpod_template_id and pod.template_id == self.config.runpod_template_id:
            count += 1
            items.append("template_id")
        expected_image = str(self.config.runpod_image or "")
        if expected_image and pod.image_reference and (pod.image_reference == expected_image or pod.image_reference.startswith(expected_image + "@")):
            count += 1
            items.append("image_reference")
        evidence["count"] = count
        evidence["items"] = items
        return evidence

    def _terminate_provider_pod(self, pod: ProviderPod, *, session_id: str = "", action: str) -> bool:
        if not self.is_managed_pod(pod):
            self._record_runpod_cleanup_event(pod.provider_pod_id, session_id, action, "ignored", "NOT_MANAGED", "Provider pod did not meet SpaShiny management evidence threshold.")
            return False
        try:
            self.provider.terminate_pod(pod.provider_pod_id)
            self.provider.wait_until_terminated(pod.provider_pod_id, int(self.config.runpod_pod_terminate_timeout_seconds))
            self._record_runpod_cleanup_event(pod.provider_pod_id, session_id, action, "completed", "", "Provider pod terminated.")
            return True
        except RunPodNotFound:
            self._record_runpod_cleanup_event(pod.provider_pod_id, session_id, action, "completed", "NOT_FOUND", "Provider pod was already absent.")
            return True
        except Exception as exc:
            message = redact_cleanup_message(exc)
            self._record_runpod_cleanup_event(pod.provider_pod_id, session_id, action, "failed", "RUNPOD_TERMINATE_FAILED", message)
            self.cleanup_retries.record_failure(
                resource_type="runpod_provider_pod",
                resource_id=pod.provider_pod_id,
                session_id=session_id,
                action=action,
                error_code="RUNPOD_TERMINATE_FAILED",
                error_message=message,
                metadata_json=json.dumps({"provider_pod_id": pod.provider_pod_id, "provider_name": pod.provider_name}, sort_keys=True),
            )
            return False

    def _record_runpod_cleanup_event(self, resource_id: str, session_id: str, action: str, status: str, error_code: str, message: str) -> None:
        self.database.record_cleanup_event(
            session_id=session_id or "",
            resource_type="runpod_provider_pod",
            resource_id=resource_id,
            action=action,
            status=status,
            error_code=redact_cleanup_message(error_code, max_length=64),
            message=redact_cleanup_message(message),
        )

    def _fail_missing_provider_pod(self, instance: dict[str, Any]) -> None:
        self.database.update_runpod_instance(
            str(instance["instance_id"]),
            state=RunPodInstanceState.CREATE_FAILED.value,
            error_code="PROVIDER_POD_MISSING",
            error_message="Provider pod was not found during reconciliation.",
            last_polled_at=self._now(),
        )
        try:
            job = self.database.get_job(str(instance["job_id"]))
            if job.status in ACTIVE_JOB_STATUSES:
                self.database.update_job(job.job_id, status=JobStatus.FAILED.value, finished_at=utc_now(), error_code="PROVIDER_POD_MISSING")
                self.result_quota.release_result_reservation_for_job(job.job_id, status="FAILED", error_message="Provider pod missing.")
        except Exception:
            return

    def _cost_at_termination(self, instance: dict[str, Any], terminated_at: str) -> tuple[float, float]:
        start_value = instance.get("ready_at") or instance.get("created_at") or instance.get("requested_at") or terminated_at
        runtime_seconds = max(0.0, (utc_dt(terminated_at) - utc_dt(str(start_value))).total_seconds())
        hourly = float(instance.get("estimated_hourly_cost_usd") or self.config.runpod_gpu_hourly_cost_usd or 0.0)
        return runtime_seconds, hourly * (runtime_seconds / 3600.0)

    def _write_job_actual_cost(self, job_id: str, runtime_seconds: float, actual_cost: float) -> None:
        try:
            self.database.get_job(job_id)
        except KeyError:
            return
        self.database.update_job(job_id, runtime_seconds=float(runtime_seconds), actual_gpu_cost_usd=float(actual_cost))

    def _usage_date(self, value: str) -> str:
        return utc_dt(value).date().isoformat()

    def _age_seconds(self, instance: dict[str, Any]) -> float:
        requested_at = str(instance.get("requested_at") or self._now())
        return max(0.0, (self.clock() - utc_dt(requested_at)).total_seconds())

    def _ready_idle_seconds(self, instance: dict[str, Any]) -> float:
        if instance.get("state") != RunPodInstanceState.READY.value or not instance.get("ready_at"):
            return 0.0
        return max(0.0, (self.clock() - utc_dt(str(instance["ready_at"]))).total_seconds())

    def _now(self) -> str:
        return self.clock().astimezone(timezone.utc).isoformat()
