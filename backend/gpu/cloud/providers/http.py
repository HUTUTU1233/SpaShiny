from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from cloud.runpod_provider import RunPodInvalidResponse, RunPodProviderUnavailable
from cloud.security import redact_secrets


class JsonHTTPClient:
    def __init__(self, *, timeout_seconds: int = 30) -> None:
        self.timeout_seconds = max(1, int(timeout_seconds))

    def request_json(
        self,
        method: str,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload, ensure_ascii=True).encode("utf-8")
        request_headers = {"Accept": "application/json", **dict(headers or {})}
        if body is not None:
            request_headers["Content-Type"] = "application/json"
        request = Request(url, data=body, headers=request_headers, method=method.upper())
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                text = response.read().decode("utf-8")
        except HTTPError as exc:
            raise RunPodProviderUnavailable(redact_secrets(f"Provider request failed: HTTP {exc.code}.")) from exc
        except (URLError, TimeoutError) as exc:
            raise RunPodProviderUnavailable(redact_secrets(f"Provider request failed: {type(exc).__name__}.")) from exc
        try:
            data = json.loads(text or "{}")
        except json.JSONDecodeError as exc:
            raise RunPodInvalidResponse("Provider response was not valid JSON.") from exc
        if not isinstance(data, dict):
            raise RunPodInvalidResponse("Provider response was not a JSON object.")
        return data
