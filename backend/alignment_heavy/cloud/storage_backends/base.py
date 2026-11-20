from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class StorageBackendError(RuntimeError):
    """Raised when temporary object storage cannot complete an operation."""


@dataclass(frozen=True)
class ObjectHead:
    object_key: str
    size_bytes: int
    etag: str = ""
    sha256: str | None = None
    metadata: dict[str, str] | None = None


class TemporaryObjectStorage(Protocol):
    def create_multipart_upload(
        self,
        *,
        object_key: str,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> str:
        ...

    def create_presigned_part_url(
        self,
        *,
        object_key: str,
        multipart_upload_id: str,
        part_number: int,
        expires_seconds: int,
    ) -> str:
        ...

    def complete_multipart_upload(
        self,
        *,
        object_key: str,
        multipart_upload_id: str,
        parts: list[dict[str, object]],
    ) -> ObjectHead:
        ...

    def abort_multipart_upload(self, *, object_key: str, multipart_upload_id: str) -> None:
        ...

    def head_object(self, object_key: str) -> ObjectHead:
        ...

    def create_presigned_download_url(
        self,
        *,
        object_key: str,
        expires_seconds: int,
        filename: str | None = None,
    ) -> str:
        ...

    def create_presigned_put_url(
        self,
        *,
        object_key: str,
        expires_seconds: int,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> str:
        ...

    def delete_object(self, object_key: str) -> None:
        ...

    def delete_prefix(self, prefix: str) -> None:
        ...

    def list_prefix(self, prefix: str) -> list[str]:
        ...

    def managed_usage_bytes(self, buckets: tuple[str, ...] = ()) -> int:
        ...

    def object_exists(self, object_key: str) -> bool:
        ...
