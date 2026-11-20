from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from cloud.config import SpaShinyCloudConfig, load_cloud_config
from cloud.runpod_provider import PodSpec, ProviderPod, RunPodInvalidResponse, RunPodNotFound, RunPodProviderUnavailable
from cloud.runpod_provider.models import RunPodInstanceState
from cloud.security import redact_secrets
from cloud.storage import safe_name

from .http import JsonHTTPClient


SALAD_GPU_CLASS_UNAVAILABLE = "SALAD_GPU_CLASS_UNAVAILABLE"


class SaladGPUClassUnavailable(RunPodProviderUnavailable):
    pass


@dataclass(frozen=True)
class SaladGPUClassMatch:
    gpu_class_id: str
    name: str
    vram_gb: float
    priority: str
    raw: dict[str, Any]


def resolve_salad_gpu_class(gpu_classes: list[dict[str, Any]], *, priority: str = "batch") -> SaladGPUClassMatch:
    for item in gpu_classes:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("display_name") or item.get("displayName") or "").strip()
        gpu_class_id = str(item.get("id") or item.get("gpu_class_id") or item.get("gpuClassId") or "").strip()
        if not name or not gpu_class_id:
            continue
        if "RTX 3090" not in _normalize_gpu_name(name):
            continue
        vram_gb = _vram_gb(item, name=name)
        if vram_gb < 24:
            continue
        if not _is_available(item):
            continue
        if not _supports_priority(item, priority):
            continue
        return SaladGPUClassMatch(gpu_class_id=gpu_class_id, name=name, vram_gb=vram_gb, priority=priority, raw=dict(item))
    raise SaladGPUClassUnavailable(SALAD_GPU_CLASS_UNAVAILABLE)


class SaladProvider:
    provider_name = "salad_rtx3090"

    def __init__(
        self,
        config: SpaShinyCloudConfig | None = None,
        *,
        http_client: JsonHTTPClient | None = None,
        sleep=None,
    ) -> None:
        self.config = config or load_cloud_config()
        self.http = http_client or JsonHTTPClient(timeout_seconds=self.config.runpod_read_timeout)
        self.sleep = sleep or time.sleep

    def list_gpu_classes(self) -> list[dict[str, Any]]:
        data = self.http.request_json("GET", self._url(f"/organizations/{self._org()}/gpu-classes"), headers=self._headers())
        items = data.get("items") or data.get("gpu_classes") or data.get("gpuClasses") or data.get("data")
        if not isinstance(items, list):
            raise RunPodInvalidResponse("Salad GPU Classes response did not include a list.")
        return [item for item in items if isinstance(item, dict)]

    def resolve_gpu_class(self) -> SaladGPUClassMatch:
        return resolve_salad_gpu_class(self.list_gpu_classes(), priority=self.config.salad_priority)

    def create_container_group(self, spec: PodSpec, idempotency_key: str) -> dict[str, Any]:
        if not self._configured():
            raise RunPodProviderUnavailable("Salad provider is not configured.")
        gpu_class = self.resolve_gpu_class()
        payload = self._container_group_payload(spec, idempotency_key, gpu_class)
        return self.http.request_json(
            "POST",
            self._url(f"/organizations/{self._org()}/projects/{self._project()}/containers"),
            payload=payload,
            headers=self._headers(),
        )

    def get_container_group(self, container_group_name: str) -> dict[str, Any]:
        try:
            return self.http.request_json(
                "GET",
                self._url(f"/organizations/{self._org()}/projects/{self._project()}/containers/{quote(container_group_name, safe='')}"),
                headers=self._headers(),
            )
        except RunPodProviderUnavailable as exc:
            if "404" in str(exc):
                raise RunPodNotFound("Salad Container Group was not found.") from exc
            raise

    def start_container_group(self, container_group_name: str) -> dict[str, Any]:
        return self.http.request_json(
            "POST",
            self._url(f"/organizations/{self._org()}/projects/{self._project()}/containers/{quote(container_group_name, safe='')}"),
            payload={},
            headers=self._headers(),
        )

    def stop_container_group(self, container_group_name: str) -> dict[str, Any]:
        return self.http.request_json(
            "POST",
            self._url(f"/organizations/{self._org()}/projects/{self._project()}/containers/{quote(container_group_name, safe='')}/stop"),
            payload={},
            headers=self._headers(),
        )

    def delete_container_group(self, container_group_name: str) -> dict[str, Any]:
        return self.http.request_json(
            "DELETE",
            self._url(f"/organizations/{self._org()}/projects/{self._project()}/containers/{quote(container_group_name, safe='')}"),
            headers=self._headers(),
        )

    def get_status(self, container_group_name: str) -> dict[str, Any]:
        data = self.get_container_group(container_group_name)
        status = self._status_from_group(data)
        if status in {"SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT"}:
            self._delete_best_effort(container_group_name)
        return {"provider_job_id": container_group_name, "status": status, "raw": data}

    def cancel(self, container_group_name: str) -> dict[str, Any]:
        self._stop_best_effort(container_group_name)
        self._delete_best_effort(container_group_name)
        return {"provider_job_id": container_group_name, "status": "CANCELLED"}

    def terminate(self, container_group_name: str) -> dict[str, Any]:
        self._stop_best_effort(container_group_name)
        self._delete_best_effort(container_group_name)
        return {"provider_job_id": container_group_name, "status": "TERMINATED"}

    def estimate_cost(self, max_runtime_seconds: int | None = None) -> float:
        runtime = float(max_runtime_seconds or self.config.max_gpu_job_seconds or 0)
        hourly = float(self.config.salad_hourly_cost_usd or self.config.runpod_gpu_hourly_cost_usd or 0.0)
        return hourly * (runtime / 3600.0)

    def fetch_logs(self, container_group_name: str, *, limit: int = 200) -> list[str]:
        if not self.config.salad_logs_url:
            return []
        data = self.http.request_json(
            "GET",
            self._url(
                f"/organizations/{self._org()}/projects/{self._project()}/containers/{quote(container_group_name, safe='')}/logs?limit={max(1, int(limit))}"
            ),
            headers=self._headers(),
        )
        logs = data.get("logs")
        if isinstance(logs, list):
            return [redact_secrets(str(item)) for item in logs]
        return []

    def create_pod(self, spec: PodSpec, idempotency_key: str) -> ProviderPod:
        group = self.create_container_group(spec, idempotency_key)
        name = str(group.get("name") or group.get("display_name") or spec.pod_name).strip()
        if not name:
            raise RunPodInvalidResponse("Salad Container Group response did not include a name.")
        self.start_container_group(name)
        return ProviderPod(
            provider_pod_id=name,
            name=name,
            state=RunPodInstanceState.CREATING.value,
            provider_name=self.provider_name,
            template_id="salad-container-group",
            image_reference=spec.image_reference,
            gpu_type="RTX 3090",
            gpu_count=1,
            public_ip="",
            ssh_port=None,
            hourly_cost_usd=float(self.config.salad_hourly_cost_usd or 0.0),
            metadata={"managed_by": "spashiny", "job_id": spec.job_id, "compute_provider": self.provider_name},
            raw_status="CREATED",
        )

    def get_pod(self, pod_id: str) -> ProviderPod:
        status = self.get_status(pod_id)
        return ProviderPod(
            provider_pod_id=pod_id,
            name=pod_id,
            state=self._map_runpod_state(str(status.get("status") or "")),
            provider_name=self.provider_name,
            template_id="salad-container-group",
            image_reference=self.config.salad_rtx3090_image,
            gpu_type="RTX 3090",
            gpu_count=1,
            public_ip="",
            ssh_port=None,
            hourly_cost_usd=float(self.config.salad_hourly_cost_usd or 0.0),
            metadata={"managed_by": "spashiny", "compute_provider": self.provider_name},
            raw_status=str(status.get("status") or ""),
        )

    def list_managed_pods(self) -> list[ProviderPod]:
        return []

    def wait_until_ready(self, pod_id: str, timeout_seconds: int) -> ProviderPod:
        deadline = time.monotonic() + int(timeout_seconds)
        last = self.get_pod(pod_id)
        while time.monotonic() < deadline:
            last = self.get_pod(pod_id)
            if last.state in {RunPodInstanceState.READY.value, RunPodInstanceState.BUSY.value}:
                return last
            if last.state in {RunPodInstanceState.TERMINATED.value, RunPodInstanceState.CREATE_FAILED.value}:
                return last
            self.sleep(max(1, int(self.config.runpod_status_poll_seconds)))
        return last

    def get_connection_metadata(self, pod_id: str) -> dict[str, object]:
        status = self.get_status(pod_id)
        return {"provider_name": self.provider_name, "state": str(status.get("status") or ""), "ssh": False}

    def stop_pod(self, pod_id: str) -> ProviderPod:
        self.cancel(pod_id)
        return ProviderPod(provider_pod_id=pod_id, name=pod_id, state=RunPodInstanceState.STOPPING.value, provider_name=self.provider_name)

    def terminate_pod(self, pod_id: str) -> ProviderPod:
        self.terminate(pod_id)
        return ProviderPod(provider_pod_id=pod_id, name=pod_id, state=RunPodInstanceState.TERMINATING.value, provider_name=self.provider_name)

    def wait_until_terminated(self, pod_id: str, timeout_seconds: int) -> ProviderPod:
        return ProviderPod(provider_pod_id=pod_id, name=pod_id, state=RunPodInstanceState.TERMINATED.value, provider_name=self.provider_name)

    def _container_group_payload(self, spec: PodSpec, idempotency_key: str, gpu_class: SaladGPUClassMatch) -> dict[str, Any]:
        if not spec.job_spec_url:
            raise RunPodProviderUnavailable("Salad Container Group requires a short-lived job_spec_url.")
        if not spec.callback_token:
            raise RunPodProviderUnavailable("Salad Container Group requires a callback token.")
        group_name = spec.pod_name or f"{safe_name(self.config.salad_container_group_prefix, 'spashiny')}-{safe_name(spec.job_id, 'job')}"
        env = {
            "SPASHINY_JOB_SPEC_URL": spec.job_spec_url,
            "SPASHINY_JOB_SPEC_SHA256": spec.job_spec_sha256,
            "SPASHINY_JOB_ID": spec.job_id,
            "SPASHINY_CALLBACK_TOKEN": spec.callback_token,
            "SPASHINY_WORKFLOW_VERSION": spec.workflow_version or self.config.model_registry_version,
            "SPASHINY_RUNTIME_PROFILE": spec.runtime_profile or "spatialmeta",
            "SPASHINY_WORKER_CONTRACT_MODE": "signed_url_callback_v1",
        }
        env = {key: value for key, value in env.items() if value}
        return {
            "name": group_name,
            "display_name": group_name,
            "autostart_policy": False,
            "replicas": 1,
            "restart_policy": "never",
            "priority": self.config.salad_priority,
            "metadata": {
                "managed_by": "spashiny",
                "job_id": spec.job_id,
                "session_id": spec.session_id,
                "workflow": spec.workflow_name,
                "idempotency_key": idempotency_key,
            },
            "container": {
                "image": spec.image_reference,
                "command": ["python", "-m", "remote_worker.runner"],
                "environment_variables": env,
                "resources": {
                    "cpu": int(self.config.salad_cpu),
                    "memory": int(self.config.salad_memory_mb),
                    "gpu_classes": [gpu_class.gpu_class_id],
                    "gpu": 1,
                    "storage_amount": int(self.config.salad_storage_gb),
                },
            },
        }

    def _headers(self) -> dict[str, str]:
        if not self.config.salad_api_key:
            raise RunPodProviderUnavailable("Salad API key is not configured.")
        return {"Salad-Api-Key": str(self.config.salad_api_key)}

    def _url(self, path: str) -> str:
        return str(self.config.salad_api_base_url).rstrip("/") + "/" + path.lstrip("/")

    def _org(self) -> str:
        value = str(self.config.salad_organization_name or "").strip()
        if not value:
            raise RunPodProviderUnavailable("SALAD_ORGANIZATION_NAME is not configured.")
        return quote(value, safe="")

    def _project(self) -> str:
        value = str(self.config.salad_project_name or "").strip()
        if not value:
            raise RunPodProviderUnavailable("SALAD_PROJECT_NAME is not configured.")
        return quote(value, safe="")

    def _configured(self) -> bool:
        return bool(
            self.config.salad_enabled
            and self.config.salad_api_key
            and self.config.salad_organization_name
            and self.config.salad_project_name
            and self.config.salad_rtx3090_image
        )

    @staticmethod
    def _status_from_group(data: dict[str, Any]) -> str:
        raw = str(
            data.get("status")
            or data.get("current_state")
            or data.get("currentState")
            or data.get("state")
            or ""
        ).upper()
        if isinstance(data.get("current_state"), dict):
            raw = str(data["current_state"].get("status") or data["current_state"].get("state") or "").upper()
        if raw in {"RUNNING", "DEPLOYED", "STARTED"}:
            return "RUNNING"
        if raw in {"PENDING", "CREATING", "STARTING", "ALLOCATING"}:
            return "PENDING"
        if raw in {"SUCCEEDED", "COMPLETED", "FINISHED"}:
            return "SUCCEEDED"
        if raw in {"FAILED", "ERROR", "CRASHED"}:
            return "FAILED"
        if raw in {"CANCELLED", "CANCELED", "STOPPED"}:
            return "CANCELLED"
        if raw in {"TIMED_OUT", "TIMEOUT"}:
            return "TIMED_OUT"
        if raw in {"DELETED"}:
            return "CANCELLED"
        return raw or "UNKNOWN"

    @staticmethod
    def _map_runpod_state(status: str) -> str:
        value = str(status or "").upper()
        if value in {"RUNNING"}:
            return RunPodInstanceState.READY.value
        if value in {"PENDING"}:
            return RunPodInstanceState.CREATING.value
        if value in {"SUCCEEDED", "CANCELLED"}:
            return RunPodInstanceState.TERMINATED.value
        if value in {"FAILED", "TIMED_OUT"}:
            return RunPodInstanceState.CREATE_FAILED.value
        return RunPodInstanceState.UNKNOWN.value

    def _stop_best_effort(self, container_group_name: str) -> None:
        try:
            self.stop_container_group(container_group_name)
        except Exception:
            return None

    def _delete_best_effort(self, container_group_name: str) -> None:
        try:
            self.delete_container_group(container_group_name)
        except Exception:
            return None


def _normalize_gpu_name(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").upper()).replace("GEFORCE ", "")


def _vram_gb(item: dict[str, Any], *, name: str) -> float:
    for key in ("vram_gb", "vramGB", "vram", "gpu_vram_gb", "gpuVramGb", "memory_gb", "memoryGb"):
        if item.get(key) not in (None, ""):
            value = item[key]
            try:
                number = float(value)
                if number > 1024:
                    return number / (1024 ** 3)
                return number
            except (TypeError, ValueError):
                match = re.search(r"(\d+(?:\.\d+)?)\s*GB", str(value), re.IGNORECASE)
                if match:
                    return float(match.group(1))
    name_match = re.search(r"(\d+(?:\.\d+)?)\s*GB", name, re.IGNORECASE)
    if name_match:
        return float(name_match.group(1))
    if "RTX 3090" in _normalize_gpu_name(name):
        return 24.0
    return 0.0


def _is_available(item: dict[str, Any]) -> bool:
    for key in ("available", "is_available", "isAvailable", "enabled", "is_enabled", "isEnabled"):
        if key in item:
            return bool(item.get(key))
    status = str(item.get("status") or item.get("availability") or "").lower()
    if status:
        return status in {"available", "ready", "active", "enabled"}
    return True


def _supports_priority(item: dict[str, Any], priority: str) -> bool:
    desired = str(priority or "batch").strip().lower()
    for key in ("priorities", "supported_priorities", "supportedPriorities"):
        values = item.get(key)
        if isinstance(values, list):
            return desired in {str(value).lower() for value in values}
    prices = item.get("prices")
    if isinstance(prices, list):
        for price in prices:
            if isinstance(price, dict) and str(price.get("priority") or price.get("type") or "").lower() == desired:
                return True
    if desired == "batch":
        return bool(item.get("batch") is not False and item.get("batch_priority") is not False)
    return True
