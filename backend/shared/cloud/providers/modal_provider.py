from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from cloud.config import SpaShinyCloudConfig, load_cloud_config
from cloud.runpod_provider import PodSpec, ProviderPod, RunPodInvalidResponse, RunPodProviderUnavailable
from cloud.runpod_provider.models import RunPodInstanceState
from cloud.security import redact_secrets

from .http import JsonHTTPClient


@dataclass(frozen=True)
class ModalSubmitRequest:
    job_id: str
    job_spec_url: str
    callback_token: str
    workflow_version: str
    runtime_profile: str = "spatialmeta"
    workflow: str = ""
    job_spec_sha256: str = ""
    idempotency_key: str = ""

    def to_payload(self) -> dict[str, Any]:
        if not self.job_id:
            raise RunPodProviderUnavailable("Modal submit request is missing job_id.")
        if not self.job_spec_url:
            raise RunPodProviderUnavailable("Modal submit request is missing job_spec_url.")
        if not self.callback_token:
            raise RunPodProviderUnavailable("Modal submit request is missing callback_token.")
        return {
            "contract_version": "modal_t4_signed_url_callback_v1",
            "job_id": self.job_id,
            "workflow": self.workflow,
            "workflow_version": self.workflow_version,
            "runtime_profile": self.runtime_profile,
            "job_spec_url": self.job_spec_url,
            "job_spec_sha256": self.job_spec_sha256,
            "callback_token": self.callback_token,
            "idempotency_key": self.idempotency_key,
            "resources": {
                "gpu": "T4",
                "cpu": 4,
                "memory": 32768,
                "min_containers": 0,
                "max_containers": 1,
            },
        }


@dataclass(frozen=True)
class ModalProviderJob:
    provider_job_id: str
    job_id: str
    status: str
    raw: dict[str, Any]


class ModalProvider:
    provider_name = "modal_t4"

    def __init__(
        self,
        config: SpaShinyCloudConfig | None = None,
        *,
        http_client: JsonHTTPClient | None = None,
    ) -> None:
        self.config = config or load_cloud_config()
        self.http = http_client or JsonHTTPClient(timeout_seconds=self.config.runpod_read_timeout)

    def health(self) -> dict[str, Any]:
        if not self.config.modal_health_url:
            return {"provider": self.provider_name, "configured": self._configured()}
        return self.http.request_json("GET", self.config.modal_health_url, headers=self._headers())

    def submit(self, request: ModalSubmitRequest) -> ModalProviderJob:
        if not self._configured():
            raise RunPodProviderUnavailable("Modal T4 provider is not configured.")
        data = self.http.request_json("POST", str(self.config.modal_submit_url), payload=request.to_payload(), headers=self._headers())
        return self._parse_submit_response(data, expected_job_id=request.job_id)

    def get_status(self, provider_job_id: str) -> dict[str, Any]:
        if not self.config.modal_status_url:
            raise RunPodProviderUnavailable("Modal status URL is not configured.")
        payload = {"provider_job_id": str(provider_job_id)}
        data = self.http.request_json("POST", str(self.config.modal_status_url), payload=payload, headers=self._headers())
        if not str(data.get("provider_job_id") or provider_job_id):
            raise RunPodInvalidResponse("Modal status response did not include provider_job_id.")
        data.setdefault("provider_job_id", provider_job_id)
        return data

    def cancel(self, provider_job_id: str) -> dict[str, Any]:
        if not self.config.modal_cancel_url:
            raise RunPodProviderUnavailable("Modal cancel URL is not configured.")
        payload = {"provider_job_id": str(provider_job_id)}
        return self.http.request_json("POST", str(self.config.modal_cancel_url), payload=payload, headers=self._headers())

    def terminate(self, provider_job_id: str) -> dict[str, Any]:
        return self.cancel(provider_job_id)

    def estimate_cost(self, max_runtime_seconds: int | None = None) -> float:
        runtime = float(max_runtime_seconds or self.config.max_gpu_job_seconds or 0)
        hourly = float(self.config.modal_hourly_cost_usd or self.config.runpod_gpu_hourly_cost_usd or 0.0)
        return hourly * (runtime / 3600.0)

    def fetch_logs(self, provider_job_id: str, *, limit: int = 200) -> list[str]:
        if not self.config.modal_logs_url:
            return []
        payload = {"provider_job_id": str(provider_job_id), "limit": max(1, int(limit))}
        data = self.http.request_json("POST", str(self.config.modal_logs_url), payload=payload, headers=self._headers())
        logs = data.get("logs")
        if isinstance(logs, list):
            return [redact_secrets(str(item)) for item in logs]
        return []

    def create_pod(self, spec: PodSpec, idempotency_key: str) -> ProviderPod:
        job = self.submit(self._request_from_spec(spec, idempotency_key))
        return ProviderPod(
            provider_pod_id=job.provider_job_id,
            name=spec.pod_name or job.job_id,
            state=RunPodInstanceState.CREATING.value,
            provider_name=self.provider_name,
            template_id="modal-app:spashiny-gpu",
            image_reference="modal.Image",
            gpu_type="T4",
            gpu_count=1,
            public_ip="",
            ssh_port=None,
            hourly_cost_usd=float(self.config.modal_hourly_cost_usd or 0.0),
            metadata={"managed_by": "spashiny", "job_id": spec.job_id, "compute_provider": self.provider_name},
            raw_status=job.status,
        )

    def get_pod(self, pod_id: str) -> ProviderPod:
        data = self.get_status(pod_id)
        return ProviderPod(
            provider_pod_id=pod_id,
            name=str(data.get("job_id") or pod_id),
            state=self._map_status(str(data.get("status") or "")),
            provider_name=self.provider_name,
            template_id="modal-app:spashiny-gpu",
            image_reference="modal.Image",
            gpu_type="T4",
            gpu_count=1,
            public_ip="",
            ssh_port=None,
            hourly_cost_usd=float(self.config.modal_hourly_cost_usd or 0.0),
            metadata={"managed_by": "spashiny", "compute_provider": self.provider_name},
            raw_status=str(data.get("status") or ""),
        )

    def list_managed_pods(self) -> list[ProviderPod]:
        return []

    def wait_until_ready(self, pod_id: str, timeout_seconds: int) -> ProviderPod:
        return self.get_pod(pod_id)

    def get_connection_metadata(self, pod_id: str) -> dict[str, object]:
        data = self.get_status(pod_id)
        return {"provider_name": self.provider_name, "state": str(data.get("status") or ""), "ssh": False}

    def stop_pod(self, pod_id: str) -> ProviderPod:
        return self.terminate_pod(pod_id)

    def terminate_pod(self, pod_id: str) -> ProviderPod:
        self.terminate(pod_id)
        return ProviderPod(provider_pod_id=pod_id, name="", state=RunPodInstanceState.TERMINATING.value, provider_name=self.provider_name)

    def wait_until_terminated(self, pod_id: str, timeout_seconds: int) -> ProviderPod:
        return ProviderPod(provider_pod_id=pod_id, name="", state=RunPodInstanceState.TERMINATED.value, provider_name=self.provider_name)

    def _request_from_spec(self, spec: PodSpec, idempotency_key: str) -> ModalSubmitRequest:
        return ModalSubmitRequest(
            job_id=spec.job_id,
            workflow=spec.workflow_name,
            job_spec_url=spec.job_spec_url,
            job_spec_sha256=spec.job_spec_sha256,
            callback_token=spec.callback_token,
            workflow_version=spec.workflow_version or self.config.model_registry_version,
            runtime_profile=spec.runtime_profile or "spatialmeta",
            idempotency_key=idempotency_key,
        )

    def _headers(self) -> dict[str, str]:
        if not self.config.modal_proxy_token_id or not self.config.modal_proxy_token_secret:
            raise RunPodProviderUnavailable("Modal proxy token id/secret are not configured.")
        return {
            "Modal-Key": str(self.config.modal_proxy_token_id),
            "Modal-Secret": str(self.config.modal_proxy_token_secret),
        }

    def _configured(self) -> bool:
        return bool(
            self.config.modal_enabled
            and self.config.modal_submit_url
            and self.config.modal_status_url
            and self.config.modal_cancel_url
            and self.config.modal_proxy_token_id
            and self.config.modal_proxy_token_secret
        )

    @staticmethod
    def _parse_submit_response(data: dict[str, Any], *, expected_job_id: str) -> ModalProviderJob:
        if not isinstance(data, dict):
            raise RunPodInvalidResponse("Modal submit response was not a JSON object.")
        provider_job_id = str(data.get("provider_job_id") or data.get("function_call_id") or data.get("id") or "").strip()
        if not provider_job_id:
            raise RunPodInvalidResponse("Modal submit response did not include provider_job_id.")
        job_id = str(data.get("job_id") or expected_job_id)
        status = str(data.get("status") or "SUBMITTED").upper()
        return ModalProviderJob(provider_job_id=provider_job_id, job_id=job_id, status=status, raw=dict(data))

    @staticmethod
    def _map_status(status: str) -> str:
        value = str(status or "").upper()
        if value in {"SUBMITTED", "PENDING", "QUEUED"}:
            return RunPodInstanceState.CREATING.value
        if value in {"RUNNING", "STARTED"}:
            return RunPodInstanceState.READY.value
        if value in {"CANCELLED", "CANCELED"}:
            return RunPodInstanceState.TERMINATED.value
        if value in {"SUCCEEDED", "COMPLETED"}:
            return RunPodInstanceState.TERMINATED.value
        if value in {"FAILED", "ERROR", "TIMED_OUT", "TIMEOUT"}:
            return RunPodInstanceState.CREATE_FAILED.value
        return RunPodInstanceState.UNKNOWN.value
