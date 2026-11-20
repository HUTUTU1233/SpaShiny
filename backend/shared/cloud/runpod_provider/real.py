from __future__ import annotations

import logging
import time
from typing import Any, Callable

from ..config import CloudConfigError, SpaShinyCloudConfig, load_cloud_config
from ..runpod_api import RunPodAPIClient, RunPodAPIError, RunPodGPUUnavailableError, RunPodTimeoutError
from ..security import redact_secrets
from .base import (
    RunPodAuthenticationError,
    RunPodCapacityUnavailable,
    RunPodCreateError,
    RunPodInvalidResponse,
    RunPodNotFound,
    RunPodProviderUnavailable,
    RunPodRateLimited,
    RunPodReadyTimeout,
    RunPodTerminateError,
)
from .models import PodSpec, ProviderPod, RunPodInstanceState


LOGGER = logging.getLogger(__name__)


class RealRunPodProvider:
    provider_name = "real"

    def __init__(
        self,
        config: SpaShinyCloudConfig | None = None,
        *,
        api_client: RunPodAPIClient | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.config = config or load_cloud_config()
        self.config.require_runpod_provider_config()
        self.client = api_client or RunPodAPIClient(self.config, rest_base_url=self.config.runpod_api_base_url)
        self.sleep = sleep or time.sleep

    def create_pod(self, spec: PodSpec, idempotency_key: str) -> ProviderPod:
        payload = self._pod_create_payload(spec, idempotency_key)
        payload["name"] = spec.pod_name
        try:
            data = self._with_retries(lambda: self.client.create_pod(payload), "create")
            pod = self._parse_provider_pod(data, spec=spec, idempotency_key=idempotency_key)
            return pod
        except RunPodCapacityUnavailable:
            raise
        except RunPodInvalidResponse:
            raise
        except Exception as exc:
            raise RunPodCreateError(redact_secrets(str(exc))) from exc

    def get_pod(self, pod_id: str) -> ProviderPod:
        try:
            data = self._with_retries(lambda: self.client.get_pod(pod_id), "get")
            return self._parse_provider_pod(data)
        except RunPodNotFound:
            raise
        except Exception as exc:
            message = str(exc).lower()
            if "not found" in message or "404" in message:
                raise RunPodNotFound("RunPod pod was not found.") from exc
            raise RunPodProviderUnavailable(redact_secrets(str(exc))) from exc

    def list_managed_pods(self) -> list[ProviderPod]:
        try:
            records = self._with_retries(lambda: self.client.list_pods(), "list")
        except RunPodInvalidResponse:
            raise
        except Exception as exc:
            raise RunPodProviderUnavailable(redact_secrets(str(exc))) from exc
        if not isinstance(records, list):
            raise RunPodInvalidResponse("RunPod /v1/pods response was not a pod list.")
        pods: list[ProviderPod] = []
        for index, item in enumerate(records):
            try:
                pods.append(self._parse_provider_pod(item))
            except Exception as exc:
                LOGGER.warning("Skipping invalid RunPod pod record at index %s: %s", index, redact_secrets(str(exc)))
        return pods

    def wait_until_ready(self, pod_id: str, timeout_seconds: int) -> ProviderPod:
        deadline = time.monotonic() + int(timeout_seconds)
        while time.monotonic() < deadline:
            pod = self.get_pod(pod_id)
            if pod.state == RunPodInstanceState.READY.value:
                return pod
            if pod.state in {RunPodInstanceState.CREATE_FAILED.value, RunPodInstanceState.TERMINATED.value}:
                raise RunPodReadyTimeout("RunPod pod did not become ready.")
            self.sleep(max(1, int(self.config.runpod_status_poll_seconds)))
        raise RunPodReadyTimeout("RunPod pod readiness timed out.")

    def get_connection_metadata(self, pod_id: str) -> dict[str, object]:
        try:
            pod = self.client.get_connection_info(pod_id)
        except Exception as exc:
            raise RunPodProviderUnavailable(redact_secrets(str(exc))) from exc
        return {
            "provider_name": self.provider_name,
            "state": str(pod.get("desired_status") or ""),
            "has_public_endpoint": bool(pod.get("host") and pod.get("port")),
        }

    def stop_pod(self, pod_id: str) -> ProviderPod:
        return self.terminate_pod(pod_id)

    def terminate_pod(self, pod_id: str) -> ProviderPod:
        try:
            self._with_retries(lambda: self.client.terminate_pod(pod_id), "terminate")
        except Exception as exc:
            message = str(exc).lower()
            if "not found" in message or "404" in message:
                return ProviderPod(provider_pod_id=pod_id, name="", state=RunPodInstanceState.TERMINATED.value, provider_name=self.provider_name)
            raise RunPodTerminateError(redact_secrets(str(exc))) from exc
        return ProviderPod(provider_pod_id=pod_id, name="", state=RunPodInstanceState.TERMINATING.value, provider_name=self.provider_name)

    def wait_until_terminated(self, pod_id: str, timeout_seconds: int) -> ProviderPod:
        deadline = time.monotonic() + int(timeout_seconds)
        while time.monotonic() < deadline:
            try:
                pod = self.get_pod(pod_id)
            except RunPodNotFound:
                return ProviderPod(provider_pod_id=pod_id, name="", state=RunPodInstanceState.TERMINATED.value, provider_name=self.provider_name)
            if pod.state == RunPodInstanceState.TERMINATED.value:
                return pod
            self.sleep(max(1, int(self.config.runpod_status_poll_seconds)))
        raise RunPodTerminateError("RunPod pod termination timed out.")

    def _with_retries(self, action: Callable[[], Any], operation: str) -> Any:
        attempts = max(1, int(self.config.runpod_api_max_retries))
        base = max(0, int(self.config.runpod_api_retry_base_seconds))
        for attempt in range(attempts):
            try:
                return action()
            except CloudConfigError as exc:
                raise RunPodAuthenticationError(str(exc)) from exc
            except RunPodGPUUnavailableError as exc:
                raise RunPodCapacityUnavailable(redact_secrets(str(exc))) from exc
            except RunPodTimeoutError as exc:
                raise RunPodProviderUnavailable(redact_secrets(str(exc))) from exc
            except RunPodAPIError as exc:
                message = redact_secrets(str(exc))
                if "429" in message or "rate" in message.lower():
                    if attempt + 1 >= attempts:
                        raise RunPodRateLimited(message) from exc
                elif "401" in message or "403" in message or "auth" in message.lower():
                    raise RunPodAuthenticationError(message) from exc
                elif "5" in message[:16] and attempt + 1 < attempts:
                    pass
                elif attempt + 1 >= attempts:
                    raise RunPodProviderUnavailable(message) from exc
                if base:
                    self.sleep(base * (2 ** attempt))
        raise RunPodProviderUnavailable(f"RunPod {operation} failed after retries.")

    def _pod_create_payload(self, spec: PodSpec, idempotency_key: str) -> dict[str, Any]:
        if any(int(port) == 22 for port in (spec.exposed_ports or ())):
            raise RunPodCreateError("RunPod worker pods must not expose SSH port 22.")
        payload: dict[str, Any] = {
            "templateId": spec.template_id or self.config.runpod_template_id,
            "imageName": spec.image_reference,
            "gpuCount": int(spec.gpu_count),
            "containerDiskInGb": int(spec.container_disk_gb),
            "volumeInGb": int(spec.volume_disk_gb),
            "env": {
                "SPASHINY_MANAGED_BY": "spashiny",
                "SPASHINY_JOB_ID": spec.job_id,
                "SPASHINY_WORKFLOW": spec.workflow_name,
                "SPASHINY_SESSION_ID": spec.session_id,
                "SPASHINY_CREATE_REQUEST_KEY": idempotency_key,
            },
        }
        if spec.control_api_base_url:
            payload["env"]["SPASHINY_CONTROL_API_BASE_URL"] = spec.control_api_base_url
        if spec.worker_id:
            payload["env"]["SPASHINY_WORKER_ID"] = spec.worker_id
        if spec.claim_token:
            payload["env"]["SPASHINY_CLAIM_TOKEN"] = spec.claim_token
        if spec.gpu_type_candidates:
            payload["gpuTypeIds"] = list(spec.gpu_type_candidates)
        if spec.cloud_type:
            payload["cloudType"] = spec.cloud_type
        if spec.location_candidates:
            payload["dataCenterIds"] = list(spec.location_candidates)
        return {key: value for key, value in payload.items() if value is not None and value != ""}

    def _parse_provider_pod(self, data: dict[str, Any], spec: PodSpec | None = None, idempotency_key: str = "") -> ProviderPod:
        if not isinstance(data, dict):
            raise RunPodInvalidResponse("RunPod response was not an object.")
        pod_id = str(data.get("id") or data.get("podId") or "").strip()
        if not pod_id:
            raise RunPodInvalidResponse("RunPod response did not include a pod id.")
        raw_status = str(data.get("desiredStatus") or data.get("status") or "").upper()
        runtime = data.get("runtime") if isinstance(data.get("runtime"), dict) else {}
        state = self._map_status(raw_status, runtime)
        metadata = self._extract_metadata(data, spec=spec, idempotency_key=idempotency_key)
        public_ip = ""
        ssh_port = None
        ports = runtime.get("ports") if isinstance(runtime, dict) else []
        if isinstance(ports, dict):
            ports = list(ports.values())
        if isinstance(ports, list):
            for port in ports:
                if not isinstance(port, dict):
                    continue
                if int(port.get("privatePort") or port.get("containerPort") or 0) == 22:
                    public_ip = str(port.get("ip") or port.get("host") or "")
                    if port.get("publicPort") or port.get("hostPort"):
                        ssh_port = int(port.get("publicPort") or port.get("hostPort"))
                    break
        return ProviderPod(
            provider_pod_id=pod_id,
            name=str(data.get("name") or (spec.pod_name if spec else "")),
            state=state,
            provider_name=self.provider_name,
            template_id=spec.template_id if spec else "",
            image_reference=str(data.get("imageName") or (spec.image_reference if spec else "")),
            gpu_type=str(data.get("machineId") or (spec.gpu_type_candidates[0] if spec and spec.gpu_type_candidates else "")),
            gpu_count=int(data.get("gpuCount") or (spec.gpu_count if spec else 1)),
            cloud_type=spec.cloud_type if spec else "",
            location=spec.location_candidates[0] if spec and spec.location_candidates else "",
            public_ip=public_ip,
            ssh_port=ssh_port,
            hourly_cost_usd=float(data.get("costPerHr") or 0.0),
            created_at=str(data.get("createdAt") or data.get("created_at") or ""),
            metadata=metadata,
            raw_status=raw_status,
        )

    def _extract_metadata(self, data: dict[str, Any], *, spec: PodSpec | None = None, idempotency_key: str = "") -> dict[str, str]:
        metadata: dict[str, str] = {}
        if spec is not None:
            metadata.update({str(key): str(value) for key, value in spec.labels.items()})
        for key in ("metadata", "labels"):
            value = data.get(key)
            if isinstance(value, dict):
                metadata.update({str(item_key): str(item_value) for item_key, item_value in value.items() if item_value is not None})
        env = data.get("env")
        if isinstance(env, dict):
            env_map = {str(key): str(value) for key, value in env.items() if value is not None}
        elif isinstance(env, list):
            env_map = {}
            for item in env:
                if isinstance(item, dict) and item.get("key"):
                    env_map[str(item["key"])] = str(item.get("value") or "")
        else:
            env_map = {}
        marker_map = {
            "SPASHINY_MANAGED_BY": "managed_by",
            "SPASHINY_JOB_ID": "job_id",
            "SPASHINY_SESSION_ID": "session_id",
            "SPASHINY_CREATE_REQUEST_KEY": "create_request_key",
        }
        for env_key, meta_key in marker_map.items():
            if env_map.get(env_key):
                metadata[meta_key] = env_map[env_key]
        if idempotency_key:
            metadata.setdefault("create_request_key", idempotency_key)
        return metadata

    def _map_status(self, raw_status: str, runtime: dict[str, Any]) -> str:
        if raw_status in {"RUNNING", "STARTED"} or runtime.get("uptimeInSeconds") is not None:
            return RunPodInstanceState.READY.value
        if raw_status in {"CREATED", "CREATING", "PENDING"}:
            return RunPodInstanceState.CREATING.value
        if raw_status in {"STARTING", "INITIALIZING"}:
            return RunPodInstanceState.STARTING.value
        if raw_status in {"STOPPING", "STOPPED"}:
            return RunPodInstanceState.STOPPING.value
        if raw_status in {"TERMINATING"}:
            return RunPodInstanceState.TERMINATING.value
        if raw_status in {"TERMINATED", "EXITED", "DELETED"}:
            return RunPodInstanceState.TERMINATED.value
        if raw_status in {"FAILED", "ERROR"}:
            return RunPodInstanceState.CREATE_FAILED.value
        return RunPodInstanceState.UNKNOWN.value
