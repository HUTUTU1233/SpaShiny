from __future__ import annotations

import re
import uuid


VALID_RUNTIME_ROOTS = {"uploads", "results", "logs", "failed", "checkpoints", "_smoke_test"}
SAFE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,119}$")


class ObjectKeyError(ValueError):
    pass


class ObjectKeyBuilder:
    """Build server-owned R2 runtime object keys."""

    @staticmethod
    def validate_segment(value: str, *, label: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            raise ObjectKeyError(f"{label} is required.")
        if "\\" in raw or "/" in raw or raw in {".", ".."}:
            raise ObjectKeyError(f"{label} contains an invalid path segment.")
        if not SAFE_SEGMENT_RE.match(raw):
            raise ObjectKeyError(f"{label} contains unsupported characters.")
        return raw

    @staticmethod
    def validate_filename(filename: str) -> str:
        raw = str(filename or "").strip()
        if not raw:
            raise ObjectKeyError("filename is required.")
        if "\\" in raw or "/" in raw or raw in {".", ".."}:
            raise ObjectKeyError("filename contains an invalid path segment.")
        return ObjectKeyBuilder.validate_segment(raw, label="filename")

    @staticmethod
    def validate_runtime_key(object_key: str, *, allowed_roots: set[str] | None = None) -> str:
        normalized = str(object_key or "").strip()
        if not normalized or normalized.startswith("/") or "\\" in normalized:
            raise ObjectKeyError("Invalid runtime object key.")
        parts = normalized.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise ObjectKeyError("Invalid runtime object key.")
        roots = allowed_roots or VALID_RUNTIME_ROOTS
        if parts[0] not in roots:
            raise ObjectKeyError("Runtime object key uses an unauthorized prefix.")
        if parts[0] == "_smoke_test":
            if len(parts) < 3:
                raise ObjectKeyError("Smoke test object key must include uuid and filename.")
        elif len(parts) < 4:
            raise ObjectKeyError("Runtime object key must include session_id, job_id, and filename.")
        for index, part in enumerate(parts[1:], start=1):
            label = "filename" if index == len(parts) - 1 else "path segment"
            if not SAFE_SEGMENT_RE.match(part):
                raise ObjectKeyError(f"Invalid {label}.")
        return normalized

    @staticmethod
    def upload_prefix(session_id: str, job_id: str) -> str:
        return f"uploads/{ObjectKeyBuilder.validate_segment(session_id, label='session_id')}/{ObjectKeyBuilder.validate_segment(job_id, label='job_id')}/"

    @staticmethod
    def upload_object(session_id: str, job_id: str, filename: str) -> str:
        return ObjectKeyBuilder.upload_prefix(session_id, job_id) + ObjectKeyBuilder.validate_filename(filename)

    @staticmethod
    def result_prefix(session_id: str, job_id: str) -> str:
        return f"results/{ObjectKeyBuilder.validate_segment(session_id, label='session_id')}/{ObjectKeyBuilder.validate_segment(job_id, label='job_id')}/"

    @staticmethod
    def result_object(session_id: str, job_id: str, filename: str) -> str:
        return ObjectKeyBuilder.result_prefix(session_id, job_id) + ObjectKeyBuilder.validate_filename(filename)

    @staticmethod
    def log_prefix(session_id: str, job_id: str) -> str:
        return f"logs/{ObjectKeyBuilder.validate_segment(session_id, label='session_id')}/{ObjectKeyBuilder.validate_segment(job_id, label='job_id')}/"

    @staticmethod
    def log_object(session_id: str, job_id: str, filename: str) -> str:
        return ObjectKeyBuilder.log_prefix(session_id, job_id) + ObjectKeyBuilder.validate_filename(filename)

    @staticmethod
    def failed_prefix(session_id: str, job_id: str) -> str:
        return f"failed/{ObjectKeyBuilder.validate_segment(session_id, label='session_id')}/{ObjectKeyBuilder.validate_segment(job_id, label='job_id')}/"

    @staticmethod
    def failed_object(session_id: str, job_id: str, filename: str) -> str:
        return ObjectKeyBuilder.failed_prefix(session_id, job_id) + ObjectKeyBuilder.validate_filename(filename)

    @staticmethod
    def checkpoint_prefix(session_id: str, job_id: str) -> str:
        return f"checkpoints/{ObjectKeyBuilder.validate_segment(session_id, label='session_id')}/{ObjectKeyBuilder.validate_segment(job_id, label='job_id')}/"

    @staticmethod
    def checkpoint_object(session_id: str, job_id: str, filename: str) -> str:
        return ObjectKeyBuilder.checkpoint_prefix(session_id, job_id) + ObjectKeyBuilder.validate_filename(filename)

    @staticmethod
    def session_runtime_prefixes(session_id: str) -> tuple[str, ...]:
        safe_session_id = ObjectKeyBuilder.validate_segment(session_id, label="session_id")
        return (
            f"uploads/{safe_session_id}/",
            f"results/{safe_session_id}/",
            f"logs/{safe_session_id}/",
            f"failed/{safe_session_id}/",
            f"checkpoints/{safe_session_id}/",
        )

    @staticmethod
    def smoke_prefix(value: str | None = None) -> str:
        smoke_id = value or str(uuid.uuid4())
        return f"_smoke_test/{ObjectKeyBuilder.validate_segment(smoke_id, label='uuid')}/"

    @staticmethod
    def smoke_object(filename: str = "payload.bin", value: str | None = None) -> str:
        return ObjectKeyBuilder.smoke_prefix(value) + ObjectKeyBuilder.validate_filename(filename)
