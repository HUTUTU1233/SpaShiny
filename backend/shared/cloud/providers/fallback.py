from __future__ import annotations

from typing import Any

from cloud.runpod_provider import PodSpec, ProviderPod, RunPodProvider, RunPodProviderUnavailable
from cloud.runpod_provider.models import RunPodInstanceState
from cloud.security import redact_secrets


class FallbackComputeProvider:
    provider_name = "gpu_provider_fallback"

    def __init__(self, providers: list[RunPodProvider]) -> None:
        self.providers = list(providers)
        self._by_pod_id: dict[str, RunPodProvider] = {}
        if not self.providers:
            raise RunPodProviderUnavailable("NO_GPU_PROVIDER_AVAILABLE")

    def create_pod(self, spec: PodSpec, idempotency_key: str) -> ProviderPod:
        errors: list[str] = []
        for provider in self.providers:
            try:
                pod = provider.create_pod(spec, idempotency_key)
                self._by_pod_id[pod.provider_pod_id] = provider
                return pod
            except Exception as exc:
                errors.append(f"{getattr(provider, 'provider_name', 'provider')}: {redact_secrets(str(exc))}")
                continue
        if not errors:
            raise RunPodProviderUnavailable("NO_GPU_PROVIDER_AVAILABLE")
        raise RunPodProviderUnavailable("NO_GPU_PROVIDER_AVAILABLE: " + "; ".join(errors))

    def get_pod(self, pod_id: str) -> ProviderPod:
        return self._provider_for(pod_id).get_pod(pod_id)

    def list_managed_pods(self) -> list[ProviderPod]:
        pods: list[ProviderPod] = []
        for provider in self.providers:
            pods.extend(provider.list_managed_pods())
        return pods

    def wait_until_ready(self, pod_id: str, timeout_seconds: int) -> ProviderPod:
        return self._provider_for(pod_id).wait_until_ready(pod_id, timeout_seconds)

    def get_connection_metadata(self, pod_id: str) -> dict[str, object]:
        return self._provider_for(pod_id).get_connection_metadata(pod_id)

    def stop_pod(self, pod_id: str) -> ProviderPod:
        return self._provider_for(pod_id).stop_pod(pod_id)

    def terminate_pod(self, pod_id: str) -> ProviderPod:
        return self._provider_for(pod_id).terminate_pod(pod_id)

    def wait_until_terminated(self, pod_id: str, timeout_seconds: int) -> ProviderPod:
        return self._provider_for(pod_id).wait_until_terminated(pod_id, timeout_seconds)

    def _provider_for(self, pod_id: str) -> RunPodProvider:
        provider = self._by_pod_id.get(pod_id)
        if provider is not None:
            return provider
        if len(self.providers) == 1:
            return self.providers[0]
        raise RunPodProviderUnavailable("Provider job id is not associated with an active fallback provider.")
