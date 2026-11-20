from __future__ import annotations

import hashlib
import shutil
import time
from pathlib import Path
from urllib.parse import quote

from .base import ObjectHead, StorageBackendError


class LocalTempStorage:
    """Filesystem-backed temporary object storage used by local development and tests."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.multipart_root = self.root / ".multipart"
        self.multipart_root.mkdir(parents=True, exist_ok=True)

    def _object_path(self, object_key: str) -> Path:
        normalized = str(object_key or "").replace("\\", "/").strip("/")
        if not normalized or ".." in Path(normalized).parts:
            raise StorageBackendError("Invalid object key.")
        path = (self.root / normalized).resolve()
        root = self.root.resolve()
        if path != root and root not in path.parents:
            raise StorageBackendError("Object key escapes the storage root.")
        return path

    def _multipart_dir(self, multipart_upload_id: str) -> Path:
        safe = str(multipart_upload_id or "").strip()
        if not safe or "/" in safe or "\\" in safe or ".." in safe:
            raise StorageBackendError("Invalid multipart upload id.")
        return self.multipart_root / safe

    def create_multipart_upload(
        self,
        *,
        object_key: str,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> str:
        upload_id = "local-" + hashlib.sha256(f"{object_key}:{time.time_ns()}".encode("utf-8")).hexdigest()[:24]
        upload_dir = self._multipart_dir(upload_id)
        upload_dir.mkdir(parents=True, exist_ok=False)
        (upload_dir / "object_key.txt").write_text(object_key, encoding="utf-8")
        return upload_id

    def create_presigned_part_url(
        self,
        *,
        object_key: str,
        multipart_upload_id: str,
        part_number: int,
        expires_seconds: int,
    ) -> str:
        expires_at = int(time.time() + int(expires_seconds))
        return f"local-temp://upload/{quote(multipart_upload_id)}/part/{int(part_number)}?expires={expires_at}"

    def put_part(self, multipart_upload_id: str, part_number: int, data: bytes) -> str:
        upload_dir = self._multipart_dir(multipart_upload_id)
        if not upload_dir.exists():
            raise StorageBackendError("Multipart upload does not exist.")
        part_path = upload_dir / f"part-{int(part_number):08d}"
        part_path.write_bytes(data)
        return hashlib.sha256(data).hexdigest()

    def complete_multipart_upload(
        self,
        *,
        object_key: str,
        multipart_upload_id: str,
        parts: list[dict[str, object]],
    ) -> ObjectHead:
        upload_dir = self._multipart_dir(multipart_upload_id)
        if not upload_dir.exists():
            raise StorageBackendError("Multipart upload does not exist.")
        target = self._object_path(object_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        with target.open("wb") as output:
            for part in sorted(parts, key=lambda item: int(item["part_number"])):
                part_path = upload_dir / f"part-{int(part['part_number']):08d}"
                if not part_path.exists():
                    raise StorageBackendError("Multipart upload is missing a part.")
                data = part_path.read_bytes()
                digest.update(data)
                output.write(data)
        shutil.rmtree(upload_dir, ignore_errors=True)
        return self.head_object(object_key)

    def abort_multipart_upload(self, *, object_key: str, multipart_upload_id: str) -> None:
        shutil.rmtree(self._multipart_dir(multipart_upload_id), ignore_errors=True)

    def head_object(self, object_key: str) -> ObjectHead:
        path = self._object_path(object_key)
        if not path.is_file():
            raise FileNotFoundError(object_key)
        data = path.read_bytes()
        sha256 = hashlib.sha256(data).hexdigest()
        return ObjectHead(object_key=object_key, size_bytes=len(data), etag=sha256, sha256=sha256)

    def create_presigned_download_url(
        self,
        *,
        object_key: str,
        expires_seconds: int,
        filename: str | None = None,
    ) -> str:
        expires_at = int(time.time() + int(expires_seconds))
        return f"local-temp://download/{quote(object_key)}?expires={expires_at}"

    def create_presigned_put_url(
        self,
        *,
        object_key: str,
        expires_seconds: int,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> str:
        expires_at = int(time.time() + int(expires_seconds))
        return f"local-temp://put/{quote(object_key)}?expires={expires_at}"

    def delete_object(self, object_key: str) -> None:
        path = self._object_path(object_key)
        if path.exists():
            path.unlink()

    def delete_prefix(self, prefix: str) -> None:
        for object_key in self.list_prefix(prefix):
            self.delete_object(object_key)

    def list_prefix(self, prefix: str) -> list[str]:
        normalized = str(prefix or "").replace("\\", "/").strip("/")
        base = self._object_path(normalized) if normalized else self.root.resolve()
        if not base.exists():
            return []
        files = []
        for path in base.rglob("*"):
            if path.is_file():
                files.append(path.relative_to(self.root).as_posix())
        return sorted(files)

    def managed_usage_bytes(self, buckets: tuple[str, ...] = ()) -> int:
        total = 0
        for object_key in self.list_prefix(""):
            try:
                total += max(0, int(self.head_object(object_key).size_bytes))
            except Exception:
                continue
        return total

    def object_exists(self, object_key: str) -> bool:
        return self._object_path(object_key).is_file()
