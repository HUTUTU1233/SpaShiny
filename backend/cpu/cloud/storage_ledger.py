from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .config import SpaShinyCloudConfig, load_cloud_config
from .database import CloudDatabase, utc_now
from .object_keys import ObjectKeyBuilder


STORAGE_OBJECT_STATUSES = {
    "RESERVED",
    "UPLOADING",
    "ACTIVE",
    "CONSUMED",
    "DELETE_PENDING",
    "PURGED",
    "DELETE_FAILED",
}

STORAGE_OBJECT_TYPES = {
    "ASSET",
    "USER_UPLOAD",
    "JOB_INPUT",
    "JOB_RESULT",
    "JOB_LOG",
    "PREVIEW",
    "MANIFEST",
    "SMOKE_TEST",
}

RUNTIME_USAGE_STATUSES = {"ACTIVE", "CONSUMED", "DELETE_PENDING", "DELETE_FAILED"}
RUNTIME_RESERVED_STATUSES = {"RESERVED", "UPLOADING"}
DEFAULT_RUNTIME_BUCKET = "spashiny-runtime"
DEFAULT_ASSETS_BUCKET = "spashiny-assets"


class StorageLedgerError(RuntimeError):
    pass


class StorageLedgerQuotaExceeded(StorageLedgerError):
    def __init__(self, *, required_bytes: int, available_bytes: int, runtime_limit_bytes: int) -> None:
        self.required_bytes = int(required_bytes)
        self.available_bytes = int(available_bytes)
        self.runtime_limit_bytes = int(runtime_limit_bytes)
        super().__init__("Runtime R2 storage limit exceeded.")


@dataclass
class StorageObjectLedger:
    database: CloudDatabase | None = None
    config: SpaShinyCloudConfig | None = None

    def __post_init__(self) -> None:
        if self.config is None:
            self.config = self.database.config if self.database is not None else load_cloud_config()
        if self.database is None:
            self.database = CloudDatabase(config=self.config)

    @property
    def runtime_bucket(self) -> str:
        return self.config.runtime_bucket_name() or DEFAULT_RUNTIME_BUCKET

    @property
    def assets_bucket(self) -> str:
        return self.config.r2_assets_bucket or DEFAULT_ASSETS_BUCKET

    @property
    def runtime_limit_bytes(self) -> int:
        values = (
            int(self.config.r2_absolute_limit_bytes),
            int(self.config.r2_safe_limit_bytes),
            int(self.config.r2_runtime_limit_bytes),
        )
        return max(0, min(value for value in values if value >= 0))

    @property
    def max_upload_bytes(self) -> int:
        return max(0, int(self.config.r2_max_upload_bytes))

    def reserve_storage(
        self,
        *,
        object_key: str,
        reserved_bytes: int,
        bucket: str | None = None,
        session_id: str = "",
        job_id: str = "",
        object_type: str = "USER_UPLOAD",
        content_type: str = "application/octet-stream",
        original_filename: str = "",
        sha256: str = "",
        expires_at: str | None = None,
        object_id: str | None = None,
    ) -> dict[str, Any]:
        object_type = self._validate_object_type(object_type)
        bucket_name = self._validate_bucket(bucket or self.runtime_bucket, object_type)
        object_key = self._validate_object_key(object_key, bucket=bucket_name, object_type=object_type)
        reserved = self._validate_size(reserved_bytes, allow_zero=False)
        if not self._is_asset(bucket_name, object_type) and reserved > self.max_upload_bytes:
            raise StorageLedgerError("Object reservation exceeds R2_MAX_UPLOAD_BYTES.")
        now = utc_now()
        object_id = object_id or "obj_" + secrets.token_hex(16)
        with self.database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if not self._is_asset(bucket_name, object_type):
                    available = self._runtime_available_for_update(conn)
                    if reserved > available:
                        raise StorageLedgerQuotaExceeded(
                            required_bytes=reserved,
                            available_bytes=available,
                            runtime_limit_bytes=self.runtime_limit_bytes,
                        )
                conn.execute(
                    """
                    INSERT INTO storage_objects(
                        id, bucket, object_key, session_id, job_id, sha256,
                        original_filename, object_type, content_type,
                        size_bytes, reserved_bytes, status, expires_at,
                        created_at, updated_at, deleted_at, last_error
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 'RESERVED', ?, ?, ?, NULL, '')
                    """,
                    (
                        object_id,
                        bucket_name,
                        object_key,
                        str(session_id or ""),
                        str(job_id or ""),
                        str(sha256 or ""),
                        str(original_filename or ""),
                        object_type,
                        str(content_type or "application/octet-stream"),
                        reserved,
                        expires_at,
                        now,
                        now,
                    ),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return self.get_object(object_id=object_id)

    def mark_uploading(self, *, object_id: str | None = None, bucket: str | None = None, object_key: str | None = None) -> dict[str, Any]:
        return self._update_status(object_id=object_id, bucket=bucket, object_key=object_key, status="UPLOADING")

    def confirm_uploaded_object(
        self,
        *,
        size_bytes: int,
        object_id: str | None = None,
        bucket: str | None = None,
        object_key: str | None = None,
        sha256: str = "",
        content_type: str | None = None,
    ) -> dict[str, Any]:
        actual = self._validate_size(size_bytes, allow_zero=True)
        now = utc_now()
        with self.database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._select_object_for_update(conn, object_id=object_id, bucket=bucket, object_key=object_key)
                if row is None:
                    raise KeyError("Storage object was not found.")
                obj = dict(row)
                if obj["status"] == "ACTIVE":
                    raise StorageLedgerError("Storage object has already been confirmed.")
                if obj["status"] not in RUNTIME_RESERVED_STATUSES:
                    raise StorageLedgerError(f"Cannot confirm object in status {obj['status']}.")
                if self._is_expired(obj.get("expires_at")):
                    raise StorageLedgerError("Storage object reservation has expired.")
                expected_content_type = str(obj.get("content_type") or "application/octet-stream")
                if content_type and expected_content_type and str(content_type) != expected_content_type:
                    raise StorageLedgerError("Content-Type does not match the storage reservation.")
                current_reserved = max(0, int(obj["reserved_bytes"] or 0))
                if not self._is_asset(str(obj["bucket"]), str(obj["object_type"])):
                    extra = max(0, actual - current_reserved)
                    available = self._runtime_available_for_update(conn)
                    if extra > available:
                        raise StorageLedgerQuotaExceeded(
                            required_bytes=extra,
                            available_bytes=available,
                            runtime_limit_bytes=self.runtime_limit_bytes,
                        )
                updates = [
                    "size_bytes=?",
                    "reserved_bytes=0",
                    "status='ACTIVE'",
                    "updated_at=?",
                    "last_error=''",
                ]
                values: list[Any] = [actual, now]
                if sha256:
                    updates.append("sha256=?")
                    values.append(str(sha256))
                if content_type:
                    updates.append("content_type=?")
                    values.append(str(content_type))
                values.append(str(obj["id"]))
                conn.execute(f"UPDATE storage_objects SET {', '.join(updates)} WHERE id=?", values)
                updated = conn.execute("SELECT * FROM storage_objects WHERE id=?", (str(obj["id"]),)).fetchone()
                conn.execute("COMMIT")
                return dict(updated)
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def release_reservation(self, *, object_id: str | None = None, bucket: str | None = None, object_key: str | None = None) -> dict[str, Any]:
        now = utc_now()
        with self.database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._select_object_for_update(conn, object_id=object_id, bucket=bucket, object_key=object_key)
                if row is None:
                    raise KeyError("Storage object was not found.")
                obj = dict(row)
                if obj["status"] in {"PURGED", "ACTIVE", "CONSUMED", "DELETE_PENDING", "DELETE_FAILED"}:
                    conn.execute("COMMIT")
                    return obj
                conn.execute(
                    """
                    UPDATE storage_objects
                    SET status='PURGED', reserved_bytes=0, updated_at=?, deleted_at=?
                    WHERE id=?
                    """,
                    (now, now, str(obj["id"])),
                )
                updated = conn.execute("SELECT * FROM storage_objects WHERE id=?", (str(obj["id"]),)).fetchone()
                conn.execute("COMMIT")
                return dict(updated)
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def mark_consumed(self, *, object_id: str | None = None, bucket: str | None = None, object_key: str | None = None) -> dict[str, Any]:
        return self._update_status(object_id=object_id, bucket=bucket, object_key=object_key, status="CONSUMED")

    def mark_delete_pending(self, *, object_id: str | None = None, bucket: str | None = None, object_key: str | None = None) -> dict[str, Any]:
        return self._update_status(object_id=object_id, bucket=bucket, object_key=object_key, status="DELETE_PENDING")

    def mark_purged(self, *, object_id: str | None = None, bucket: str | None = None, object_key: str | None = None) -> dict[str, Any]:
        now = utc_now()
        with self.database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._select_object_for_update(conn, object_id=object_id, bucket=bucket, object_key=object_key)
                if row is None:
                    raise KeyError("Storage object was not found.")
                conn.execute(
                    """
                    UPDATE storage_objects
                    SET status='PURGED', reserved_bytes=0, updated_at=?, deleted_at=?, last_error=''
                    WHERE id=?
                    """,
                    (now, now, str(row["id"])),
                )
                updated = conn.execute("SELECT * FROM storage_objects WHERE id=?", (str(row["id"]),)).fetchone()
                conn.execute("COMMIT")
                return dict(updated)
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def mark_delete_failed(
        self,
        *,
        last_error: str,
        object_id: str | None = None,
        bucket: str | None = None,
        object_key: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        with self.database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._select_object_for_update(conn, object_id=object_id, bucket=bucket, object_key=object_key)
                if row is None:
                    raise KeyError("Storage object was not found.")
                conn.execute(
                    """
                    UPDATE storage_objects
                    SET status='DELETE_FAILED', updated_at=?, last_error=?
                    WHERE id=?
                    """,
                    (now, str(last_error or "")[:500], str(row["id"])),
                )
                updated = conn.execute("SELECT * FROM storage_objects WHERE id=?", (str(row["id"]),)).fetchone()
                conn.execute("COMMIT")
                return dict(updated)
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def get_runtime_usage(self) -> int:
        with self.database.connect() as conn:
            return self._runtime_usage_for_update(conn)

    def get_reserved_usage(self) -> int:
        with self.database.connect() as conn:
            return self._runtime_reserved_for_update(conn)

    def list_expired_objects(self, *, now: str | None = None, limit: int = 1000) -> list[dict[str, Any]]:
        cutoff = now or utc_now()
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM storage_objects
                WHERE expires_at IS NOT NULL
                AND expires_at <= ?
                AND status != 'PURGED'
                ORDER BY expires_at ASC, created_at ASC
                LIMIT ?
                """,
                (cutoff, int(limit)),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_object(self, *, object_id: str | None = None, bucket: str | None = None, object_key: str | None = None) -> dict[str, Any]:
        with self.database.connect() as conn:
            row = self._select_object_for_update(conn, object_id=object_id, bucket=bucket, object_key=object_key)
        if row is None:
            raise KeyError("Storage object was not found.")
        return dict(row)

    def _update_status(self, *, object_id: str | None, bucket: str | None, object_key: str | None, status: str) -> dict[str, Any]:
        if status not in STORAGE_OBJECT_STATUSES:
            raise StorageLedgerError(f"Unsupported storage object status: {status}")
        now = utc_now()
        with self.database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._select_object_for_update(conn, object_id=object_id, bucket=bucket, object_key=object_key)
                if row is None:
                    raise KeyError("Storage object was not found.")
                conn.execute(
                    "UPDATE storage_objects SET status=?, updated_at=?, last_error='' WHERE id=?",
                    (status, now, str(row["id"])),
                )
                updated = conn.execute("SELECT * FROM storage_objects WHERE id=?", (str(row["id"]),)).fetchone()
                conn.execute("COMMIT")
                return dict(updated)
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def _runtime_available_for_update(self, conn) -> int:
        return max(0, self.runtime_limit_bytes - self._runtime_usage_for_update(conn) - self._runtime_reserved_for_update(conn))

    def _runtime_usage_for_update(self, conn) -> int:
        rows = conn.execute(
            """
            SELECT COALESCE(SUM(size_bytes), 0) AS total
            FROM storage_objects
            WHERE bucket=?
            AND object_type != 'ASSET'
            AND status IN (?, ?, ?, ?)
            """,
            (self.runtime_bucket, *sorted(RUNTIME_USAGE_STATUSES)),
        ).fetchone()
        return max(0, int(rows["total"] or 0))

    def _runtime_reserved_for_update(self, conn) -> int:
        rows = conn.execute(
            """
            SELECT COALESCE(SUM(reserved_bytes), 0) AS total
            FROM storage_objects
            WHERE bucket=?
            AND object_type != 'ASSET'
            AND status IN (?, ?)
            """,
            (self.runtime_bucket, *sorted(RUNTIME_RESERVED_STATUSES)),
        ).fetchone()
        return max(0, int(rows["total"] or 0))

    def _select_object_for_update(self, conn, *, object_id: str | None = None, bucket: str | None = None, object_key: str | None = None):
        if object_id:
            return conn.execute("SELECT * FROM storage_objects WHERE id=?", (str(object_id),)).fetchone()
        if object_key:
            if not bucket:
                raise StorageLedgerError("bucket is required when locating a storage object by object_key.")
            bucket_name = str(bucket or "").strip()
            return conn.execute(
                "SELECT * FROM storage_objects WHERE bucket=? AND object_key=?",
                (bucket_name, self._validate_object_key(object_key, bucket=bucket_name, object_type="ASSET" if bucket_name == self.assets_bucket else "USER_UPLOAD")),
            ).fetchone()
        raise StorageLedgerError("object_id or object_key is required.")

    def _validate_bucket(self, bucket: str, object_type: str) -> str:
        bucket_name = str(bucket or "").strip()
        if not bucket_name:
            raise StorageLedgerError("bucket is required.")
        if object_type == "ASSET":
            if bucket_name != self.assets_bucket:
                raise StorageLedgerError("ASSET objects must use R2_ASSETS_BUCKET.")
        elif bucket_name != self.runtime_bucket:
            raise StorageLedgerError("Runtime objects must use R2_RUNTIME_BUCKET.")
        return bucket_name

    def _validate_object_key(self, object_key: str, *, bucket: str, object_type: str) -> str:
        normalized = str(object_key or "").strip()
        if "\\" in normalized:
            raise StorageLedgerError("Invalid R2 object key.")
        parts = [part for part in normalized.split("/") if part]
        if not normalized or normalized.startswith("/") or any(part in {".", ".."} for part in parts):
            raise StorageLedgerError("Invalid R2 object key.")
        if not self._is_asset(bucket, object_type):
            try:
                ObjectKeyBuilder.validate_runtime_key(normalized)
            except ValueError as exc:
                raise StorageLedgerError(str(exc)) from exc
        return normalized

    def _validate_object_type(self, object_type: str) -> str:
        normalized = str(object_type or "").strip().upper()
        if normalized not in STORAGE_OBJECT_TYPES:
            raise StorageLedgerError(f"Unsupported storage object type: {object_type}")
        return normalized

    def _validate_size(self, value: int, *, allow_zero: bool) -> int:
        size = int(value)
        if size < 0 or (size == 0 and not allow_zero):
            raise StorageLedgerError("Storage object size must be positive.")
        return size

    def _is_asset(self, bucket: str, object_type: str) -> bool:
        return str(bucket) == self.assets_bucket or str(object_type) == "ASSET"

    def _is_expired(self, expires_at: object) -> bool:
        raw = str(expires_at or "").strip()
        if not raw:
            return False
        try:
            expires = datetime.fromisoformat(raw)
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            return expires <= datetime.now(timezone.utc)
        except ValueError:
            return False
