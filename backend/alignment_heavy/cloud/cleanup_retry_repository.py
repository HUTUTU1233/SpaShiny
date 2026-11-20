from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import SpaShinyCloudConfig, load_cloud_config
from .database import CloudDatabase


SENSITIVE_PATTERNS = [
    re.compile(r"(?i)(token|secret|key|signature|credential)=([^&\s]+)"),
    re.compile(r"(?i)(X-Amz-Signature|X-Amz-Credential|X-Amz-Security-Token)=([^&\s]+)"),
    re.compile(r"[A-Za-z]:\\[^\s]+"),
    re.compile(r"/(?:home|opt|tmp|var|workspace)/[^\s]+"),
]


def redact_cleanup_message(message: object, *, max_length: int = 180) -> str:
    text = str(message or "")
    for pattern in SENSITIVE_PATTERNS:
        text = pattern.sub(lambda match: f"{match.group(1)}=<redacted>" if match.lastindex else "<redacted-path>", text)
    text = text.replace("\r", " ").replace("\n", " ")
    return text[:max_length]


class CleanupRetryRepository:
    def __init__(self, database: CloudDatabase | None = None, config: SpaShinyCloudConfig | None = None) -> None:
        self.config = config or load_cloud_config()
        self.database = database or CloudDatabase(config=self.config)

    def record_failure(
        self,
        *,
        resource_type: str,
        resource_id: str,
        action: str,
        session_id: str = "",
        error_code: str = "CLEANUP_FAILED",
        error_message: object = "",
        metadata_json: str = "{}",
    ) -> dict[str, Any]:
        return self.database.create_or_update_cleanup_retry(
            resource_type=resource_type,
            resource_id=resource_id,
            session_id=session_id,
            action=action,
            error_code=redact_cleanup_message(error_code, max_length=64),
            error_message=redact_cleanup_message(error_message),
            max_attempts=int(self.config.cleanup_max_retries),
            metadata_json=metadata_json,
            next_retry_at=self._next_retry_at(0),
        )

    def due(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return self.database.list_due_cleanup_retries(limit=limit)

    def mark_running(self, retry_id: int) -> dict[str, Any]:
        return self.database.mark_cleanup_retry_running(retry_id)

    def mark_completed(self, retry_id: int) -> dict[str, Any]:
        return self.database.mark_cleanup_retry_completed(retry_id)

    def mark_failed(self, retry: dict[str, Any], *, error_code: str, error_message: object) -> dict[str, Any]:
        attempt_count = int(retry.get("attempt_count") or 0) + 1
        return self.database.mark_cleanup_retry_failed(
            int(retry["id"]),
            error_code=redact_cleanup_message(error_code, max_length=64),
            error_message=redact_cleanup_message(error_message),
            next_retry_at=self._next_retry_at(attempt_count),
        )

    def _next_retry_at(self, attempt_count: int) -> str:
        base = max(0, int(self.config.cleanup_retry_base_seconds))
        delay = base * max(1, int(attempt_count) + 1)
        return (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()
