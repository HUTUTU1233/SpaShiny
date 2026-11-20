from __future__ import annotations

from typing import Protocol

from .models import PodSpec, ProviderPod


class RunPodProviderError(RuntimeError):
    """Base class for redacted RunPod provider errors."""


class RunPodAuthenticationError(RunPodProviderError):
    pass


class RunPodCapacityUnavailable(RunPodProviderError):
    pass


class RunPodCreateError(RunPodProviderError):
    pass


class RunPodNotFound(RunPodProviderError):
    pass


class RunPodRateLimited(RunPodProviderError):
    pass


class RunPodReadyTimeout(RunPodProviderError):
    pass


class RunPodTerminateError(RunPodProviderError):
    pass


class RunPodProviderUnavailable(RunPodProviderError):
    pass


class RunPodInvalidResponse(RunPodProviderError):
    pass


class RunPodProvider(Protocol):
    provider_name: str

    def create_pod(self, spec: PodSpec, idempotency_key: str) -> ProviderPod:
        ...

    def get_pod(self, pod_id: str) -> ProviderPod:
        ...

    def list_managed_pods(self) -> list[ProviderPod]:
        ...

    def wait_until_ready(self, pod_id: str, timeout_seconds: int) -> ProviderPod:
        ...

    def get_connection_metadata(self, pod_id: str) -> dict[str, object]:
        ...

    def stop_pod(self, pod_id: str) -> ProviderPod:
        ...

    def terminate_pod(self, pod_id: str) -> ProviderPod:
        ...

    def wait_until_terminated(self, pod_id: str, timeout_seconds: int) -> ProviderPod:
        ...
