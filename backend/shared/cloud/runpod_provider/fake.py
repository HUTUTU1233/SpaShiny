from __future__ import annotations

import itertools
import time
from dataclasses import dataclass
from typing import Callable

from .base import (
    RunPodCapacityUnavailable,
    RunPodCreateError,
    RunPodNotFound,
    RunPodProviderUnavailable,
    RunPodRateLimited,
    RunPodReadyTimeout,
    RunPodTerminateError,
)
from .models import PodSpec, ProviderPod, RunPodInstanceState


Clock = Callable[[], float]


@dataclass
class _FakePodRecord:
    pod: ProviderPod
    spec: PodSpec
    poll_count: int = 0
    terminate_poll_count: int = 0
    create_key: str = ""
    managed: bool = True


class FakeRunPodProvider:
    provider_name = "fake"

    def __init__(
        self,
        *,
        clock: Clock | None = None,
        ready_after_polls: int = 1,
        terminate_after_polls: int = 1,
        scenario: str = "success",
    ) -> None:
        self.clock = clock or time.monotonic
        self.ready_after_polls = max(0, int(ready_after_polls))
        self.terminate_after_polls = max(0, int(terminate_after_polls))
        self.scenario = str(scenario or "success").lower()
        self._counter = itertools.count(1)
        self._pods: dict[str, _FakePodRecord] = {}
        self._idempotency: dict[str, str] = {}
        self.network_calls = 0

    def create_pod(self, spec: PodSpec, idempotency_key: str) -> ProviderPod:
        if self.scenario == "capacity_unavailable":
            raise RunPodCapacityUnavailable("RunPod capacity unavailable.")
        if self.scenario == "rate_limited":
            raise RunPodRateLimited("RunPod rate limited.")
        if self.scenario == "api_timeout":
            raise RunPodProviderUnavailable("RunPod provider unavailable.")
        if idempotency_key in self._idempotency:
            return self.get_pod(self._idempotency[idempotency_key])
        pod_id = f"fake-pod-{next(self._counter):06d}"
        state = RunPodInstanceState.CREATE_FAILED.value if self.scenario == "create_failed" else RunPodInstanceState.CREATING.value
        pod = ProviderPod(
            provider_pod_id=pod_id,
            name=spec.pod_name,
            state=state,
            provider_name=self.provider_name,
            template_id=spec.template_id,
            image_reference=spec.image_reference,
            gpu_type=spec.gpu_type_candidates[0] if spec.gpu_type_candidates else "FAKE_GPU",
            gpu_count=int(spec.gpu_count),
            cloud_type=spec.cloud_type,
            location=spec.location_candidates[0] if spec.location_candidates else "fake",
            public_ip="",
            ssh_port=None,
            hourly_cost_usd=0.0,
            created_at="",
            metadata=dict(spec.labels),
            raw_status=state,
        )
        self._pods[pod_id] = _FakePodRecord(pod=pod, spec=spec, create_key=idempotency_key)
        self._idempotency[idempotency_key] = pod_id
        if state == RunPodInstanceState.CREATE_FAILED.value:
            raise RunPodCreateError("Fake RunPod create failed.")
        return pod

    def get_pod(self, pod_id: str) -> ProviderPod:
        record = self._record(pod_id)
        pod = record.pod
        if pod.state in {
            RunPodInstanceState.TERMINATED.value,
            RunPodInstanceState.CREATE_FAILED.value,
            RunPodInstanceState.TERMINATING.value,
            RunPodInstanceState.TERMINATE_FAILED.value,
            RunPodInstanceState.READY.value,
            RunPodInstanceState.BUSY.value,
        }:
            if pod.state == RunPodInstanceState.TERMINATING.value:
                return self._advance_termination(record)
            return pod
        if self.scenario == "ready_timeout":
            state = RunPodInstanceState.STARTING.value
        elif record.poll_count <= 0:
            state = RunPodInstanceState.STARTING.value
        elif record.poll_count >= self.ready_after_polls:
            state = RunPodInstanceState.READY.value
        else:
            state = RunPodInstanceState.STARTING.value
        record.poll_count += 1
        record.pod = self._with_state(pod, state)
        return record.pod

    def list_managed_pods(self) -> list[ProviderPod]:
        return [record.pod for record in self._pods.values() if record.managed]

    def wait_until_ready(self, pod_id: str, timeout_seconds: int) -> ProviderPod:
        for _ in range(max(1, int(timeout_seconds))):
            pod = self.get_pod(pod_id)
            if pod.state == RunPodInstanceState.READY.value:
                return pod
            if pod.state == RunPodInstanceState.CREATE_FAILED.value:
                raise RunPodCreateError("Fake RunPod create failed.")
        raise RunPodReadyTimeout("Fake RunPod pod did not become ready.")

    def get_connection_metadata(self, pod_id: str) -> dict[str, object]:
        pod = self.get_pod(pod_id)
        return {"state": pod.state, "provider_name": self.provider_name}

    def stop_pod(self, pod_id: str) -> ProviderPod:
        return self.terminate_pod(pod_id)

    def terminate_pod(self, pod_id: str) -> ProviderPod:
        record = self._record(pod_id)
        if record.pod.state == RunPodInstanceState.TERMINATED.value:
            return record.pod
        if self.scenario == "terminate_failed":
            record.pod = self._with_state(record.pod, RunPodInstanceState.TERMINATE_FAILED.value)
            raise RunPodTerminateError("Fake RunPod terminate failed.")
        record.pod = self._with_state(record.pod, RunPodInstanceState.TERMINATING.value)
        return record.pod

    def wait_until_terminated(self, pod_id: str, timeout_seconds: int) -> ProviderPod:
        for _ in range(max(1, int(timeout_seconds))):
            pod = self.get_pod(pod_id)
            if pod.state == RunPodInstanceState.TERMINATED.value:
                return pod
        raise RunPodTerminateError("Fake RunPod pod did not terminate.")

    def inject_managed_pod(self, pod: ProviderPod, *, managed: bool = True) -> None:
        self._pods[pod.provider_pod_id] = _FakePodRecord(
            pod=pod,
            spec=PodSpec(
                job_id=str(pod.metadata.get("job_id") or ""),
                session_id=str(pod.metadata.get("session_id") or ""),
                workflow_name=str(pod.metadata.get("workflow") or ""),
                pod_name=pod.name,
                image_name=pod.image_reference or "fake",
            ),
            managed=managed,
        )

    def _record(self, pod_id: str) -> _FakePodRecord:
        record = self._pods.get(pod_id)
        if record is None:
            raise RunPodNotFound("RunPod pod was not found.")
        return record

    def _advance_termination(self, record: _FakePodRecord) -> ProviderPod:
        if record.terminate_poll_count >= self.terminate_after_polls:
            record.pod = self._with_state(record.pod, RunPodInstanceState.TERMINATED.value)
        record.terminate_poll_count += 1
        return record.pod

    def _with_state(self, pod: ProviderPod, state: str) -> ProviderPod:
        return ProviderPod(
            provider_pod_id=pod.provider_pod_id,
            name=pod.name,
            state=state,
            provider_name=pod.provider_name,
            template_id=pod.template_id,
            image_reference=pod.image_reference,
            gpu_type=pod.gpu_type,
            gpu_count=pod.gpu_count,
            cloud_type=pod.cloud_type,
            location=pod.location,
            public_ip=pod.public_ip,
            ssh_port=pod.ssh_port,
            hourly_cost_usd=pod.hourly_cost_usd,
            created_at=pod.created_at,
            metadata=dict(pod.metadata),
            raw_status=state,
        )
