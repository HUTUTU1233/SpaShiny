from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from .config import CloudConfigError, SpaShinyCloudConfig, load_cloud_config
from .security import redact_secrets

LOGGER = logging.getLogger(__name__)


class RunPodAPIError(RuntimeError):
    """Base exception for RunPod API failures."""


class RunPodGPUUnavailableError(RunPodAPIError):
    """Raised when RunPod reports no capacity for the requested GPU."""


class RunPodTimeoutError(RunPodAPIError):
    """Raised when a pod does not reach the desired state in time."""


Transport = Callable[[dict[str, Any]], dict[str, Any]]


class RunPodAPIClient:
    def __init__(
        self,
        config: SpaShinyCloudConfig | None = None,
        *,
        api_key: str | None = None,
        endpoint: str | None = None,
        rest_base_url: str | None = None,
        connect_timeout: int | None = None,
        read_timeout: int | None = None,
        transport: Transport | None = None,
    ) -> None:
        self.config = config or load_cloud_config()
        self.api_key = api_key if api_key is not None else self.config.runpod_api_key
        self.endpoint = endpoint or self.config.runpod_api_endpoint
        self.rest_base_url = (rest_base_url or self.config.runpod_api_base_url or "https://api.runpod.io").rstrip("/")
        self.connect_timeout = int(connect_timeout or self.config.runpod_connect_timeout)
        self.read_timeout = int(read_timeout or self.config.runpod_read_timeout)
        self.transport = transport

    def _require_api_key(self) -> str:
        if not self.api_key:
            raise CloudConfigError("RUNPOD_API_KEY is not configured.")
        return self.api_key

    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        operation = payload.get("operationName") or "RunPodGraphQL"
        LOGGER.info("RunPod API call: %s", operation)
        if self.transport is not None:
            response = self.transport(payload)
        else:
            api_key = self._require_api_key()
            body = json.dumps(payload).encode("utf-8")
            request = urllib.request.Request(
                self.endpoint,
                data=body,
                method="POST",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "SpaShiny-Cloud/1.0",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=self.connect_timeout + self.read_timeout) as handle:
                    response = json.loads(handle.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                raise RunPodAPIError(f"RunPod HTTP {exc.code}: {redact_secrets(detail)}") from exc
            except urllib.error.URLError as exc:
                raise RunPodAPIError(f"RunPod request failed: {exc}") from exc

        errors = response.get("errors") if isinstance(response, dict) else None
        if errors:
            message = redact_secrets(json.dumps(errors, ensure_ascii=False))
            if "capacity" in message.lower() or "no gpu" in message.lower() or "stock" in message.lower():
                raise RunPodGPUUnavailableError(message)
            raise RunPodAPIError(message)
        return response.get("data", response)

    def _graphql(self, query: str, variables: dict[str, Any], operation_name: str) -> dict[str, Any]:
        return self._request(
            {
                "query": query,
                "variables": variables,
                "operationName": operation_name,
            }
        )

    def _rest_url(self, path: str) -> str:
        normalized = "/" + str(path).lstrip("/")
        if self.rest_base_url.endswith("/v1") and normalized.startswith("/v1/"):
            normalized = normalized[3:]
        return self.rest_base_url + normalized

    def _rest_headers(self) -> dict[str, str]:
        api_key = self._require_api_key()
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "SpaShiny-Cloud/1.0",
        }

    def _rest_request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        method = str(method).upper()
        url = self._rest_url(path)
        LOGGER.info("RunPod REST API call: %s %s", method, path)
        headers = self._rest_headers()
        timeout_seconds = self.connect_timeout + self.read_timeout
        if self.transport is not None:
            response = self.transport(
                {
                    "method": method,
                    "path": path,
                    "url": url,
                    "headers": headers,
                    "body": body,
                    "timeout_seconds": timeout_seconds,
                }
            )
            return self._parse_rest_transport_response(response)

        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as handle:
                raw = handle.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RunPodAPIError(f"RunPod HTTP {exc.code}: {redact_secrets(detail)}") from exc
        except urllib.error.URLError as exc:
            raise RunPodAPIError(f"RunPod request failed: {redact_secrets(str(exc))}") from exc
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise RunPodAPIError("RunPod REST response was not valid JSON.") from exc

    def _parse_rest_transport_response(self, response: Any) -> Any:
        status_code: int | None = None
        payload = response
        if isinstance(response, dict) and ("status_code" in response or "status" in response) and ("body" in response or "json" in response):
            status_code = int(response.get("status_code") or response.get("status") or 0)
            payload = response.get("json", response.get("body"))
        if status_code is not None and status_code >= 400:
            raise RunPodAPIError(f"RunPod HTTP {status_code}: {redact_secrets(str(payload))}")
        if isinstance(payload, (list, dict)):
            return payload
        if payload in {"", None}:
            return {}
        if isinstance(payload, (bytes, bytearray)):
            payload = payload.decode("utf-8", errors="replace")
        if isinstance(payload, str):
            try:
                return json.loads(payload)
            except json.JSONDecodeError as exc:
                raise RunPodAPIError("RunPod REST response was not valid JSON.") from exc
        raise RunPodAPIError("RunPod REST response had an unsupported payload type.")

    def list_pods(self) -> list[dict[str, Any]]:
        data = self._rest_request("GET", "/v1/pods")
        if not isinstance(data, list):
            raise RunPodAPIError("RunPod REST /v1/pods response was not a pod list.")
        return data

    def get_pod(self, pod_id: str) -> dict[str, Any]:
        safe_pod_id = urllib.parse.quote(str(pod_id), safe="")
        pod = self._rest_request("GET", f"/v1/pods/{safe_pod_id}")
        if not isinstance(pod, dict):
            raise RunPodAPIError(f"RunPod pod was not found: {pod_id}")
        return pod

    def start_pod(self, pod_id: str) -> dict[str, Any]:
        mutation = """
        mutation SpaShinyStartPod($podId: String!) {
          podResume(input: {podId: $podId}) {
            id
            desiredStatus
          }
        }
        """
        data = self._graphql(mutation, {"podId": pod_id}, "SpaShinyStartPod")
        return data.get("podResume") or data

    def stop_pod(self, pod_id: str) -> dict[str, Any]:
        mutation = """
        mutation SpaShinyStopPod($podId: String!) {
          podStop(input: {podId: $podId}) {
            id
            desiredStatus
          }
        }
        """
        data = self._graphql(mutation, {"podId": pod_id}, "SpaShinyStopPod")
        return data.get("podStop") or data

    def create_pod(self, config: dict[str, Any]) -> dict[str, Any]:
        pod = self._rest_request("POST", "/v1/pods", dict(config))
        if not isinstance(pod, dict):
            raise RunPodAPIError("RunPod REST /v1/pods create response was not an object.")
        return pod

    def terminate_pod(self, pod_id: str) -> dict[str, Any]:
        safe_pod_id = urllib.parse.quote(str(pod_id), safe="")
        data = self._rest_request("DELETE", f"/v1/pods/{safe_pod_id}")
        return data if isinstance(data, dict) else {}

    def get_connection_info(self, pod_id: str) -> dict[str, Any]:
        pod = self.get_pod(pod_id)
        runtime = pod.get("runtime") or {}
        ports = runtime.get("ports") or []
        if isinstance(ports, dict):
            ports = list(ports.values())

        candidates: list[dict[str, Any]] = []
        for port in ports:
            if not isinstance(port, dict):
                continue
            private_port = int(port.get("privatePort") or port.get("containerPort") or 0)
            public_port = port.get("publicPort") or port.get("hostPort")
            ip = port.get("ip") or port.get("host")
            if private_port == 22 and public_port and ip:
                candidates.append(port)
            elif str(port.get("type", "")).lower() == "tcp" and public_port and ip:
                candidates.append(port)

        if not candidates:
            raise RunPodAPIError("RunPod pod does not expose a public SSH port yet.")

        selected = candidates[0]
        return {
            "pod_id": pod_id,
            "host": str(selected.get("ip") or selected.get("host")).strip(),
            "port": int(selected.get("publicPort") or selected.get("hostPort")),
            "private_port": int(selected.get("privatePort") or selected.get("containerPort") or 22),
            "desired_status": pod.get("desiredStatus"),
            "pod": pod,
        }

    def wait_until_running(self, pod_id: str, timeout_seconds: int = 900) -> dict[str, Any]:
        deadline = time.monotonic() + int(timeout_seconds)
        last_pod: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            last_pod = self.get_pod(pod_id)
            status = str(last_pod.get("desiredStatus") or last_pod.get("status") or "").upper()
            runtime = last_pod.get("runtime") or {}
            if status in {"RUNNING", "STARTED"} or runtime.get("uptimeInSeconds") is not None:
                return last_pod
            time.sleep(5)
        raise RunPodTimeoutError(f"RunPod pod did not enter RUNNING within {timeout_seconds}s: {pod_id}")
