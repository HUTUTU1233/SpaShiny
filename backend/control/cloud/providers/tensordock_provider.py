from __future__ import annotations

from typing import Any

from cloud.config import SpaShinyCloudConfig, load_cloud_config
from cloud.runpod_provider import PodSpec, ProviderPod, RunPodProviderUnavailable
from cloud.runpod_provider.models import RunPodInstanceState


class TensorDockProvider:
    provider_name = "tensordock_reserved"

    def __init__(self, config: SpaShinyCloudConfig | None = None) -> None:
        self.config = config or load_cloud_config()

    def health(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "enabled": bool(self.config.tensordock_enabled),
            "status": "RESERVED_DISABLED" if not self.config.tensordock_enabled else "RESERVED_CONFIGURED",
        }

    def submit(self, *_args, **_kwargs) -> dict[str, Any]:
        self._raise_disabled()

    def get_status(self, *_args, **_kwargs) -> dict[str, Any]:
        self._raise_disabled()

    def cancel(self, *_args, **_kwargs) -> dict[str, Any]:
        self._raise_disabled()

    def terminate(self, *_args, **_kwargs) -> dict[str, Any]:
        self._raise_disabled()

    def estimate_cost(self, *_args, **_kwargs) -> float:
        return 0.0

    def fetch_logs(self, *_args, **_kwargs) -> list[str]:
        return []

    def create_pod(self, spec: PodSpec, idempotency_key: str) -> ProviderPod:
        self._raise_disabled()

    def get_pod(self, pod_id: str) -> ProviderPod:
        self._raise_disabled()

    def list_managed_pods(self) -> list[ProviderPod]:
        return []

    def wait_until_ready(self, pod_id: str, timeout_seconds: int) -> ProviderPod:
        self._raise_disabled()

    def get_connection_metadata(self, pod_id: str) -> dict[str, object]:
        return {"provider_name": self.provider_name, "state": "DISABLED", "ssh": False}

    def stop_pod(self, pod_id: str) -> ProviderPod:
        self._raise_disabled()

    def terminate_pod(self, pod_id: str) -> ProviderPod:
        if not self.config.tensordock_enabled:
            return ProviderPod(provider_pod_id=pod_id, name="", state=RunPodInstanceState.TERMINATED.value, provider_name=self.provider_name)
        self._raise_disabled()

    def wait_until_terminated(self, pod_id: str, timeout_seconds: int) -> ProviderPod:
        return ProviderPod(provider_pod_id=pod_id, name="", state=RunPodInstanceState.TERMINATED.value, provider_name=self.provider_name)

    def _raise_disabled(self) -> None:
        raise RunPodProviderUnavailable("TENSORDOCK_RESERVED_DISABLED")
