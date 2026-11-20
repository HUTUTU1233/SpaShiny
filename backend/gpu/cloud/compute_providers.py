from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import SpaShinyCloudConfig, load_cloud_config
from .models import JobRecord
from .providers import FallbackComputeProvider, ModalProvider, SaladProvider, TensorDockProvider
from .runpod_provider import FakeRunPodProvider, ProviderPod, RunPodProvider, RunPodProviderUnavailable
from .runpod_provider.models import PodSpec, RunPodInstanceState
from .security import redact_secrets


@dataclass(frozen=True)
class ComputeProviderSpec:
    name: str
    label: str
    role: str
    gpu_profile: str
    worker_image: str
    template_id: str = ""
    enabled: bool = True
    reserved: bool = False
    hourly_cost_usd: float = 0.0
    launch_url: str | None = None
    status_url: str | None = None
    terminate_url: str | None = None

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "role": self.role,
            "gpu_profile": self.gpu_profile,
            "worker_image": self.worker_image,
            "template_id_configured": bool(self.template_id),
            "enabled": bool(self.enabled),
            "reserved": bool(self.reserved),
            "hourly_cost_usd": float(self.hourly_cost_usd or 0.0),
            "launch_url_configured": bool(self.launch_url),
            "status_url_configured": bool(self.status_url),
            "terminate_url_configured": bool(self.terminate_url),
        }


class NamedFakeComputeProvider(FakeRunPodProvider):
    def __init__(self, spec: ComputeProviderSpec, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.spec = spec
        self.provider_name = spec.name

    def create_pod(self, spec: PodSpec, idempotency_key: str) -> ProviderPod:
        pod = super().create_pod(spec, idempotency_key)
        return self._provider_pod(pod)

    def get_pod(self, pod_id: str) -> ProviderPod:
        return self._provider_pod(super().get_pod(pod_id))

    def wait_until_ready(self, pod_id: str, timeout_seconds: int) -> ProviderPod:
        return self._provider_pod(super().wait_until_ready(pod_id, timeout_seconds))

    def stop_pod(self, pod_id: str) -> ProviderPod:
        return self._provider_pod(super().stop_pod(pod_id))

    def terminate_pod(self, pod_id: str) -> ProviderPod:
        return self._provider_pod(super().terminate_pod(pod_id))

    def wait_until_terminated(self, pod_id: str, timeout_seconds: int) -> ProviderPod:
        return self._provider_pod(super().wait_until_terminated(pod_id, timeout_seconds))

    def _provider_pod(self, pod: ProviderPod) -> ProviderPod:
        return ProviderPod(
            provider_pod_id=pod.provider_pod_id,
            name=pod.name,
            state=pod.state,
            provider_name=self.provider_name,
            template_id=pod.template_id or self.spec.template_id,
            image_reference=pod.image_reference or self.spec.worker_image,
            gpu_type=self.spec.gpu_profile,
            gpu_count=pod.gpu_count,
            cloud_type=pod.cloud_type,
            location=pod.location,
            public_ip="",
            ssh_port=None,
            hourly_cost_usd=float(self.spec.hourly_cost_usd or 0.0),
            created_at=pod.created_at,
            metadata={**dict(pod.metadata), "compute_provider": self.provider_name},
            raw_status=pod.raw_status,
        )


class LocalUnavailableComputeProvider:
    provider_name = "lab_local_gpu_runtime"

    def create_pod(self, spec: PodSpec, idempotency_key: str) -> ProviderPod:
        raise RunPodProviderUnavailable("GPU_RUNTIME_BLOCKED: local Docker NVIDIA runtime is not configured.")

    def get_pod(self, pod_id: str) -> ProviderPod:
        return ProviderPod(
            provider_pod_id=str(pod_id),
            name=str(pod_id),
            state=RunPodInstanceState.TERMINATED.value,
            provider_name=self.provider_name,
            raw_status="GPU_RUNTIME_BLOCKED",
        )

    def list_managed_pods(self) -> list[ProviderPod]:
        return []

    def wait_until_ready(self, pod_id: str, timeout_seconds: int) -> ProviderPod:
        raise RunPodProviderUnavailable("GPU_RUNTIME_BLOCKED: local Docker NVIDIA runtime is not configured.")

    def get_connection_metadata(self, pod_id: str) -> dict[str, object]:
        return {"state": "GPU_RUNTIME_BLOCKED", "provider_name": self.provider_name, "ssh": False}

    def stop_pod(self, pod_id: str) -> ProviderPod:
        return self.get_pod(pod_id)

    def terminate_pod(self, pod_id: str) -> ProviderPod:
        return self.get_pod(pod_id)

    def wait_until_terminated(self, pod_id: str, timeout_seconds: int) -> ProviderPod:
        return self.get_pod(pod_id)


class WebhookComputeProvider:
    """Generic no-SSH provider adapter for Modal, SaladCloud, and TensorDock.

    The adapter intentionally talks only to configured HTTPS launch/status/terminate
    endpoints. Provider-specific auth and deployment details stay outside the
    SpaShiny UI and are injected by runtime environment variables.
    """

    def __init__(self, spec: ComputeProviderSpec, *, api_token: str | None = None, timeout_seconds: int = 30) -> None:
        self.spec = spec
        self.provider_name = spec.name
        self.api_token = api_token or ""
        self.timeout_seconds = max(1, int(timeout_seconds))

    def create_pod(self, spec: PodSpec, idempotency_key: str) -> ProviderPod:
        if not self.spec.launch_url:
            raise RunPodProviderUnavailable(f"{self.provider_name} launch URL is not configured.")
        payload = {
            "idempotency_key": idempotency_key,
            "provider": self.provider_name,
            "worker_contract": spec.to_safe_dict(),
            "labels": spec.labels,
            "max_runtime_seconds": int(spec.max_runtime_seconds),
        }
        data = self._request_json(self.spec.launch_url, payload)
        provider_id = str(data.get("provider_pod_id") or data.get("job_id") or data.get("id") or "").strip()
        if not provider_id:
            raise RunPodProviderUnavailable(f"{self.provider_name} launch response did not include an id.")
        return self._pod_from_response(provider_id, data, default_state=RunPodInstanceState.CREATING.value)

    def get_pod(self, pod_id: str) -> ProviderPod:
        if not self.spec.status_url:
            return ProviderPod(provider_pod_id=pod_id, name="", state=RunPodInstanceState.READY.value, provider_name=self.provider_name)
        url = self.spec.status_url.rstrip("/") + "/" + str(pod_id)
        data = self._request_json(url, None, method="GET")
        return self._pod_from_response(pod_id, data, default_state=RunPodInstanceState.READY.value)

    def list_managed_pods(self) -> list[ProviderPod]:
        return []

    def wait_until_ready(self, pod_id: str, timeout_seconds: int) -> ProviderPod:
        deadline = time.monotonic() + int(timeout_seconds)
        last = self.get_pod(pod_id)
        while time.monotonic() < deadline:
            last = self.get_pod(pod_id)
            if last.state in {RunPodInstanceState.READY.value, RunPodInstanceState.BUSY.value}:
                return last
            time.sleep(2)
        raise RunPodProviderUnavailable(f"{self.provider_name} worker did not become ready in time.")

    def get_connection_metadata(self, pod_id: str) -> dict[str, object]:
        pod = self.get_pod(pod_id)
        return {"state": pod.state, "provider_name": self.provider_name, "ssh": False}

    def stop_pod(self, pod_id: str) -> ProviderPod:
        return self.terminate_pod(pod_id)

    def terminate_pod(self, pod_id: str) -> ProviderPod:
        if self.spec.terminate_url:
            url = self.spec.terminate_url.rstrip("/") + "/" + str(pod_id)
            self._request_json(url, {"provider_pod_id": pod_id}, method="POST")
        return ProviderPod(provider_pod_id=pod_id, name="", state=RunPodInstanceState.TERMINATING.value, provider_name=self.provider_name)

    def wait_until_terminated(self, pod_id: str, timeout_seconds: int) -> ProviderPod:
        return ProviderPod(provider_pod_id=pod_id, name="", state=RunPodInstanceState.TERMINATED.value, provider_name=self.provider_name)

    def _request_json(self, url: str, payload: dict[str, Any] | None, *, method: str = "POST") -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload, ensure_ascii=True).encode("utf-8")
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8") or "{}")
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RunPodProviderUnavailable(redact_secrets(f"{self.provider_name} request failed: {exc}")) from exc
        if not isinstance(data, dict):
            raise RunPodProviderUnavailable(f"{self.provider_name} response was not a JSON object.")
        return data

    def _pod_from_response(self, pod_id: str, data: dict[str, Any], *, default_state: str) -> ProviderPod:
        raw_state = str(data.get("state") or data.get("status") or default_state).upper()
        state = raw_state if raw_state in {item.value for item in RunPodInstanceState} else default_state
        return ProviderPod(
            provider_pod_id=pod_id,
            name=str(data.get("name") or pod_id),
            state=state,
            provider_name=self.provider_name,
            template_id=self.spec.template_id,
            image_reference=str(data.get("image_reference") or self.spec.worker_image),
            gpu_type=self.spec.gpu_profile,
            gpu_count=int(data.get("gpu_count") or 1),
            public_ip="",
            ssh_port=None,
            hourly_cost_usd=float(data.get("hourly_cost_usd") or self.spec.hourly_cost_usd or 0.0),
            metadata={"managed_by": "spashiny", "compute_provider": self.provider_name},
            raw_status=raw_state,
        )


class ComputeProviderRegistry:
    def __init__(self, config: SpaShinyCloudConfig | None = None) -> None:
        self.config = config or load_cloud_config()

    def specs(self) -> dict[str, ComputeProviderSpec]:
        cfg = self.config
        fake_mode = (cfg.compute_provider_mode or "fake").lower() == "fake"
        return {
            "modal_t4": ComputeProviderSpec(
                name="modal_t4",
                label="Modal T4",
                role="preferred_gpu",
                gpu_profile="T4",
                worker_image=cfg.modal_t4_image,
                template_id=cfg.modal_t4_template_id,
                enabled=bool(cfg.modal_enabled or fake_mode),
                hourly_cost_usd=float(cfg.modal_hourly_cost_usd or cfg.runpod_gpu_hourly_cost_usd or 0.0),
                launch_url=cfg.modal_submit_url,
                status_url=cfg.modal_status_url,
                terminate_url=cfg.modal_cancel_url,
            ),
            "salad_rtx3090": ComputeProviderSpec(
                name="salad_rtx3090",
                label="SaladCloud RTX 3090",
                role="main_gpu",
                gpu_profile="RTX_3090",
                worker_image=cfg.salad_rtx3090_image,
                template_id=cfg.salad_container_group,
                enabled=bool(cfg.salad_enabled or fake_mode),
                hourly_cost_usd=float(cfg.salad_hourly_cost_usd or cfg.runpod_gpu_hourly_cost_usd or 0.0),
                launch_url=cfg.salad_api_base_url,
                status_url=cfg.salad_api_base_url,
                terminate_url=cfg.salad_api_base_url,
            ),
            "tensordock_reserved": ComputeProviderSpec(
                name="tensordock_reserved",
                label="TensorDock Reserved",
                role="reserved_interface",
                gpu_profile="RESERVED_GPU",
                worker_image=cfg.tensordock_image,
                enabled=bool(cfg.tensordock_enabled or fake_mode),
                reserved=True,
                hourly_cost_usd=float(cfg.tensordock_hourly_cost_usd or 0.0),
                launch_url=cfg.tensordock_launch_url,
                status_url=cfg.tensordock_status_url,
                terminate_url=cfg.tensordock_terminate_url,
            ),
        }

    def provider_status(self) -> dict[str, Any]:
        return {
            name: {
                **spec.to_safe_dict(),
                "mode": self.config.compute_provider_mode,
                "status": "READY" if spec.enabled else "NOT_CONFIGURED",
            }
            for name, spec in self.specs().items()
        }

    def select_provider(self, job: JobRecord | None = None) -> RunPodProvider:
        mode = (self.config.compute_provider_mode or "fake").lower()
        if mode in {"lab", "local"}:
            return LocalUnavailableComputeProvider()
        if mode == "real":
            providers = []
            specs = self.specs()
            for name in self._provider_chain(job):
                spec = specs.get(name)
                if spec is not None and spec.enabled:
                    providers.append(self._real_provider_for(name))
            if not providers:
                for name in ("modal_t4", "salad_rtx3090", "tensordock_reserved"):
                    spec = specs[name]
                    if spec.enabled:
                        providers.append(self._real_provider_for(name))
            if not providers:
                raise RunPodProviderUnavailable("NO_GPU_PROVIDER_AVAILABLE")
            if len(providers) == 1:
                return providers[0]
            return FallbackComputeProvider(providers)
        spec = self.select_provider_spec(job)
        return NamedFakeComputeProvider(spec)

    def select_provider_spec(self, job: JobRecord | None = None) -> ComputeProviderSpec:
        specs = self.specs()
        chain = self._provider_chain(job)
        for name in chain:
            spec = specs.get(name)
            if spec is not None and spec.enabled:
                return spec
        for name in ("modal_t4", "salad_rtx3090", "tensordock_reserved"):
            spec = specs[name]
            if spec.enabled:
                return spec
        raise RunPodProviderUnavailable("No GPU compute provider is configured.")

    def _provider_chain(self, job: JobRecord | None) -> tuple[str, ...]:
        if job is not None:
            try:
                metadata = json.loads(job.metadata_json or "{}")
                chain = metadata.get("provider_chain")
                if isinstance(chain, list):
                    values = tuple(str(item) for item in chain if str(item).strip())
                    if values:
                        return values
            except Exception:
                pass
        return tuple(self.config.gpu_provider_order or ("modal_t4", "salad_rtx3090", "tensordock_reserved"))

    def _token_for_provider(self, provider_name: str) -> str:
        if provider_name == "modal_t4":
            return self.config.modal_api_token or ""
        if provider_name == "salad_rtx3090":
            return self.config.salad_api_key or ""
        if provider_name == "tensordock_reserved":
            return self.config.tensordock_api_token or ""
        return ""

    def _real_provider_for(self, provider_name: str) -> RunPodProvider:
        if provider_name == "modal_t4":
            return ModalProvider(self.config)
        if provider_name == "salad_rtx3090":
            return SaladProvider(self.config)
        if provider_name == "tensordock_reserved":
            return TensorDockProvider(self.config)
        raise RunPodProviderUnavailable(f"Unknown GPU compute provider: {provider_name}")
