from __future__ import annotations

import json
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import SpaShinyCloudConfig, load_cloud_config
from .database import CloudDatabase, utc_now
from .models import JobRecord
from .object_keys import ObjectKeyBuilder
from .storage import safe_name
from .storage_backends import TemporaryObjectStorage, get_temporary_object_storage


LOGGER = logging.getLogger(__name__)

GLOBAL_R2_LIMIT_BYTES = 10_000_000_000
SAFETY_RESERVE_BYTES = 500_000_000
PROTECTED_PREFIXES = ("examples/", "reference/", "shared/")
ACTIVE_RESERVATION_STATUSES = {"RESERVED", "UPLOADING"}
FINAL_RESERVATION_STATUSES = {"COMMITTED", "RELEASED", "EXPIRED", "FAILED"}
RESULT_RESERVATION_KIND = "job_result"
DEFAULT_RUNTIME_BUCKET = "spashiny-runtime"


class StorageQuotaError(Exception):
    pass


class GlobalStorageLimitExceeded(StorageQuotaError):
    def __init__(
        self,
        *,
        required_bytes: int,
        available_bytes: int,
        global_limit_bytes: int,
        safety_reserve_bytes: int,
        physical_usage_bytes: int,
        reserved_bytes: int,
    ) -> None:
        self.required_bytes = int(required_bytes)
        self.available_bytes = int(available_bytes)
        self.global_limit_bytes = int(global_limit_bytes)
        self.safety_reserve_bytes = int(safety_reserve_bytes)
        self.physical_usage_bytes = int(physical_usage_bytes)
        self.reserved_bytes = int(reserved_bytes)
        super().__init__("Cloud temporary storage is full. Please try again later.")

    def to_dict(self) -> dict[str, int | str]:
        return {
            "code": "GLOBAL_STORAGE_LIMIT_EXCEEDED",
            "message": str(self),
            "required_bytes": self.required_bytes,
            "available_bytes": self.available_bytes,
            "global_limit_bytes": self.global_limit_bytes,
            "safety_reserve_bytes": self.safety_reserve_bytes,
            "physical_usage_bytes": self.physical_usage_bytes,
            "reserved_bytes": self.reserved_bytes,
        }


class StorageReservationNotFound(StorageQuotaError):
    pass


class StorageReservationConflict(StorageQuotaError):
    pass


@dataclass
class StorageQuotaManager:
    database: CloudDatabase | None = None
    config: SpaShinyCloudConfig | None = None
    storage: TemporaryObjectStorage | None = None

    def __post_init__(self) -> None:
        if self.config is None:
            self.config = self.database.config if self.database is not None else load_cloud_config()
        if self.database is None:
            self.database = CloudDatabase(config=self.config)
        if self.storage is None:
            self.storage = get_temporary_object_storage(self.config)

    @property
    def global_limit_bytes(self) -> int:
        value = self.config.r2_global_storage_limit_bytes
        return max(0, int(GLOBAL_R2_LIMIT_BYTES if value is None else value))

    @property
    def safety_reserve_bytes(self) -> int:
        value = self.config.r2_storage_safety_reserve_bytes
        return max(0, int(SAFETY_RESERVE_BYTES if value is None else value))

    def get_physical_usage_bytes(self) -> int:
        state = self.database.get_storage_usage_state()
        return max(0, int(state.get("physical_usage_bytes") or 0))

    def get_reserved_bytes(self) -> int:
        with self.database.connect() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(expected_bytes), 0) AS total
                FROM storage_reservations
                WHERE status IN (?, ?)
                """,
                ("RESERVED", "UPLOADING"),
            ).fetchone()
        return max(0, int(row["total"] or 0))

    def get_effective_usage_bytes(self) -> int:
        return max(0, self.get_physical_usage_bytes() + self.get_reserved_bytes())

    def get_available_bytes(self) -> int:
        return self._available(self.get_physical_usage_bytes(), self.get_reserved_bytes())

    def can_reserve(self, required_bytes: int) -> bool:
        return int(required_bytes) <= self.get_available_bytes()

    def estimate_result_reservation_bytes(self, job: JobRecord | str) -> int:
        job_record = self._job_record(job)
        input_sizes: list[int] = []
        try:
            upload_ids = json.loads(job_record.input_upload_ids_json or "[]")
            if isinstance(upload_ids, list):
                for upload_id in upload_ids:
                    try:
                        upload = self.database.get_upload(str(upload_id), session_id=job_record.session_id)
                        input_sizes.append(max(0, int(upload.actual_size_bytes or upload.declared_size_bytes or 0)))
                    except Exception:
                        continue
        except Exception:
            input_sizes = []
        input_joint_h5ad_size = max(input_sizes) if input_sizes else 0
        factor = max(0.0, float(self.config.r2_result_size_estimate_factor or 0.0))
        minimum = max(1, int(self.config.r2_result_min_reservation_bytes or 1_073_741_824))
        return max(int(input_joint_h5ad_size * factor), minimum)

    def reserve_result_storage_for_job(self, job: JobRecord | str) -> dict[str, Any]:
        job_record = self._job_record(job)
        existing = self.get_result_reservation_for_job(job_record)
        if existing is not None and str(existing.get("status") or "") not in FINAL_RESERVATION_STATUSES:
            return existing
        estimated_bytes = self.estimate_result_reservation_bytes(job_record)
        object_key = self._job_result_object_key(job_record)
        reservation = self.reserve_storage(
            session_id=job_record.session_id or job_record.user_id,
            object_key=object_key,
            expected_bytes=estimated_bytes,
            operation="job_result",
            metadata={
                "kind": RESULT_RESERVATION_KIND,
                "job_id": job_record.job_id,
                "workflow": job_record.workflow_name or job_record.workflow,
                "input_upload_ids": self._safe_json_list(job_record.input_upload_ids_json),
                "estimate_factor": float(self.config.r2_result_size_estimate_factor or 0.0),
                "minimum_bytes": int(self.config.r2_result_min_reservation_bytes or 0),
            },
        )
        self._update_job_quota_metadata(
            job_record.job_id,
            {
                "result_storage_reservation_id": reservation["reservation_id"],
                "result_storage_estimated_bytes": estimated_bytes,
                "result_storage_status": reservation["status"],
                "result_storage_object_key": object_key,
            },
        )
        return reservation

    def get_result_reservation_for_job(self, job: JobRecord | str) -> dict[str, Any] | None:
        job_record = self._job_record(job)
        metadata = self._job_metadata(job_record)
        reservation_id = str(metadata.get("result_storage_reservation_id") or "")
        if reservation_id:
            try:
                return self.database.get_storage_reservation(reservation_id)
            except KeyError:
                pass
        object_key = self._job_result_object_key(job_record)
        for reservation in self.database.list_storage_reservations(session_id=job_record.session_id or None, limit=10000):
            if str(reservation.get("object_key") or "") != object_key:
                continue
            if self._reservation_is_job_result(reservation, job_record.job_id):
                return reservation
        return None

    def release_result_reservation_for_job(self, job: JobRecord | str, *, status: str = "RELEASED", error_message: object = "") -> dict[str, Any] | None:
        job_record = self._job_record(job)
        reservation = self.get_result_reservation_for_job(job_record)
        if reservation is None:
            return None
        if str(reservation.get("status") or "") == "COMMITTED":
            return reservation
        updated = self.release_reservation(str(reservation["reservation_id"]), status=status, error_message=error_message)
        self._update_job_quota_metadata(
            job_record.job_id,
            {
                "result_storage_status": updated["status"],
                "result_storage_released_at": utc_now(),
            },
        )
        return updated

    def commit_result_reservation_for_job(self, job: JobRecord | str, *, actual_bytes: int) -> dict[str, Any]:
        job_record = self._job_record(job)
        reservation = self.get_result_reservation_for_job(job_record)
        if reservation is None:
            reservation = self.reserve_result_storage_for_job(job_record)
        updated = self.commit_reservation(str(reservation["reservation_id"]), actual_bytes=max(0, int(actual_bytes)))
        self._update_job_quota_metadata(
            job_record.job_id,
            {
                "result_storage_status": updated["status"],
                "result_storage_actual_bytes": max(0, int(actual_bytes)),
                "result_storage_committed_at": utc_now(),
            },
        )
        return updated

    def result_reservation_committed_for_job(self, job: JobRecord | str, *, expected_actual_bytes: int | None = None) -> bool:
        job_record = self._job_record(job)
        reservation = self.get_result_reservation_for_job(job_record)
        if reservation is None or str(reservation.get("status") or "") != "COMMITTED":
            return False
        if expected_actual_bytes is not None and int(reservation.get("actual_bytes") or 0) != int(expected_actual_bytes):
            return False
        return True

    def reserve_storage(
        self,
        *,
        session_id: str,
        object_key: str,
        expected_bytes: int,
        reservation_id: str | None = None,
        expires_at: str | None = None,
        operation: str = "upload",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        expected = self._validate_required_bytes(expected_bytes)
        reservation_id = reservation_id or "res_" + secrets.token_hex(16)
        now = utc_now()
        expires_at = expires_at or self._default_expires_at(operation)
        object_key = str(object_key or "").strip()
        if not object_key:
            raise StorageQuotaError("object_key is required for storage reservation.")
        try:
            if self.config.is_lab_profile:
                object_key = self._validate_lab_local_object_key(object_key, session_id=session_id)
            else:
                object_key = ObjectKeyBuilder.validate_runtime_key(object_key)
        except ValueError as exc:
            raise StorageQuotaError(str(exc)) from exc
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True)
        with self.database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                self._ensure_usage_row(conn, now)
                physical = self._physical_usage_for_update(conn)
                reserved = self._reserved_usage_for_update(conn)
                available = self._available(physical, reserved)
                if expected > available:
                    raise GlobalStorageLimitExceeded(
                        required_bytes=expected,
                        available_bytes=available,
                        global_limit_bytes=self.global_limit_bytes,
                        safety_reserve_bytes=self.safety_reserve_bytes,
                        physical_usage_bytes=physical,
                        reserved_bytes=reserved,
                    )
                conn.execute(
                    """
                    INSERT INTO storage_reservations(
                        reservation_id, session_id, object_key, expected_bytes,
                        actual_bytes, status, created_at, updated_at, expires_at,
                        error_message, metadata_json
                    )
                    VALUES(?, ?, ?, ?, NULL, ?, ?, ?, ?, '', ?)
                    """,
                    (
                        reservation_id,
                        str(session_id),
                        object_key,
                        expected,
                        "RESERVED",
                        now,
                        now,
                        expires_at,
                        metadata_json,
                    ),
                )
                self._insert_storage_object_reservation(
                    conn,
                    reservation_id=reservation_id,
                    session_id=str(session_id),
                    object_key=object_key,
                    expected_bytes=expected,
                    expires_at=expires_at,
                    operation=operation,
                    metadata=metadata or {},
                    now=now,
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        self._log_quota_event("reserve", session_id=session_id, reservation_id=reservation_id, object_key=object_key, requested_bytes=expected, status="RESERVED")
        return self.database.get_storage_reservation(reservation_id)

    def mark_uploading(self, reservation_id: str) -> dict[str, Any]:
        reservation = self.database.get_storage_reservation(reservation_id)
        if reservation["status"] == "RESERVED":
            updated = self.database.update_storage_reservation(reservation_id, status="UPLOADING")
            self._mark_storage_object_status(reservation_id, "UPLOADING")
            return updated
        return reservation

    def release_reservation(self, reservation_id: str, *, status: str = "RELEASED", error_message: object = "") -> dict[str, Any]:
        try:
            reservation = self.database.get_storage_reservation(reservation_id)
        except KeyError as exc:
            raise StorageReservationNotFound(str(exc)) from exc
        if reservation["status"] in {"COMMITTED", "RELEASED", "EXPIRED", "FAILED"}:
            return reservation
        updated = self.database.update_storage_reservation(
            reservation_id,
            status=status,
            error_message=str(error_message or "")[:180],
        )
        self._release_storage_object_reservation(reservation_id, last_error=str(error_message or "")[:500])
        self._log_quota_event(
            "release",
            session_id=str(updated.get("session_id") or ""),
            reservation_id=reservation_id,
            object_key=str(updated.get("object_key") or ""),
            requested_bytes=int(updated.get("expected_bytes") or 0),
            status=str(updated.get("status") or ""),
        )
        return updated

    def release_session_reservations(self, session_id: str, *, status: str = "RELEASED") -> list[str]:
        released: list[str] = []
        for reservation in self.database.list_storage_reservations(session_id=session_id, statuses=sorted(ACTIVE_RESERVATION_STATUSES), limit=10000):
            object_key = str(reservation.get("object_key") or "")
            if object_key and not self._reservation_is_result(reservation) and self.storage.object_exists(object_key):
                continue
            updated = self.release_reservation(str(reservation["reservation_id"]), status=status)
            released.append(str(updated["reservation_id"]))
        return released

    def commit_reservation(self, reservation_id: str, *, actual_bytes: int) -> dict[str, Any]:
        actual = self._validate_actual_bytes(actual_bytes)
        now = utc_now()
        with self.database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute("SELECT * FROM storage_reservations WHERE reservation_id=?", (reservation_id,)).fetchone()
                if row is None:
                    raise StorageReservationNotFound(reservation_id)
                reservation = dict(row)
                if reservation["status"] == "COMMITTED":
                    conn.execute("COMMIT")
                    return reservation
                if reservation["status"] not in ACTIVE_RESERVATION_STATUSES:
                    raise StorageReservationConflict(f"Cannot commit reservation in status {reservation['status']}.")
                self._ensure_usage_row(conn, now)
                physical = self._physical_usage_for_update(conn)
                reserved = self._reserved_usage_for_update(conn)
                expected = int(reservation["expected_bytes"] or 0)
                extra = max(0, actual - expected)
                available = self._available(physical, reserved)
                if extra > available:
                    raise GlobalStorageLimitExceeded(
                        required_bytes=extra,
                        available_bytes=available,
                        global_limit_bytes=self.global_limit_bytes,
                        safety_reserve_bytes=self.safety_reserve_bytes,
                        physical_usage_bytes=physical,
                        reserved_bytes=reserved,
                    )
                conn.execute(
                    """
                    UPDATE storage_usage_state
                    SET physical_usage_bytes=MAX(0, physical_usage_bytes + ?),
                        updated_at=?
                    WHERE id=1
                    """,
                    (actual, now),
                )
                conn.execute(
                    """
                    UPDATE storage_reservations
                    SET actual_bytes=?, status='COMMITTED', updated_at=?, error_message=''
                    WHERE reservation_id=?
                    """,
                    (actual, now, reservation_id),
                )
                conn.execute(
                    """
                    UPDATE storage_objects
                    SET size_bytes=?,
                        reserved_bytes=0,
                        status='ACTIVE',
                        updated_at=?,
                        last_error=''
                    WHERE id=?
                    """,
                    (actual, now, reservation_id),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        updated = self.database.get_storage_reservation(reservation_id)
        self._log_quota_event(
            "commit",
            session_id=str(updated.get("session_id") or ""),
            reservation_id=reservation_id,
            object_key=str(updated.get("object_key") or ""),
            requested_bytes=actual,
            status="COMMITTED",
        )
        return updated

    def record_object_deleted(self, *, object_key: str, size_bytes: int | None = None) -> None:
        size = int(size_bytes or 0)
        if size <= 0:
            try:
                reservation = self.database.get_storage_reservation_by_object_key(object_key)
                if reservation:
                    size = int(reservation.get("actual_bytes") or reservation.get("expected_bytes") or 0)
            except Exception:
                size = 0
        if size > 0:
            self.database.increment_storage_usage(-size)
        self._mark_storage_object_purged_by_key(object_key, bucket=self.config.runtime_bucket_name() or DEFAULT_RUNTIME_BUCKET)

    def reconcile_with_r2(self) -> dict[str, Any]:
        physical = max(0, int(self.storage.managed_usage_bytes(tuple(self.config.r2_managed_buckets))))
        return self.database.set_storage_usage_state(physical_usage_bytes=physical, last_reconciled_at=utc_now())

    def reconcile_if_due(self) -> dict[str, Any] | None:
        state = self.database.get_storage_usage_state()
        last_reconciled = str(state.get("last_reconciled_at") or "").strip()
        interval = max(1, int(self.config.r2_reconcile_interval_seconds or 3600))
        if not last_reconciled:
            return self.reconcile_with_r2()
        try:
            last = datetime.fromisoformat(last_reconciled)
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
        except ValueError:
            return self.reconcile_with_r2()
        if datetime.now(timezone.utc) - last >= timedelta(seconds=interval):
            return self.reconcile_with_r2()
        return None

    def expire_stale_reservations(self) -> list[str]:
        now = utc_now()
        expired: list[str] = []
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM storage_reservations
                WHERE status IN (?, ?)
                AND expires_at IS NOT NULL
                AND expires_at < ?
                ORDER BY created_at ASC
                LIMIT 1000
                """,
                ("RESERVED", "UPLOADING", now),
            ).fetchall()
        for row in rows:
            reservation = dict(row)
            object_key = str(reservation.get("object_key") or "")
            if object_key and not self._reservation_is_result(reservation) and self.storage.object_exists(object_key):
                continue
            self.release_reservation(str(reservation["reservation_id"]), status="EXPIRED", error_message="Reservation expired before object commit.")
            expired.append(str(reservation["reservation_id"]))
        return expired

    def status(self) -> dict[str, Any]:
        state = self.database.get_storage_usage_state()
        physical = max(0, int(state.get("physical_usage_bytes") or 0))
        reserved = self.get_reserved_bytes()
        effective = max(0, physical + reserved)
        available = self._available(physical, reserved)
        limit = self.global_limit_bytes
        usage_percent = round((effective / limit * 100), 1) if limit > 0 else 100.0
        status_text = self._status_text(usage_percent, available)
        return {
            "global_limit_bytes": limit,
            "safety_reserve_bytes": self.safety_reserve_bytes,
            "physical_usage_bytes": physical,
            "reserved_bytes": reserved,
            "effective_usage_bytes": effective,
            "available_bytes": available,
            "usage_percent": usage_percent,
            "status": status_text,
            "last_reconciled_at": state.get("last_reconciled_at") or "",
        }

    def is_protected_object(self, object_key: str) -> bool:
        normalized = str(object_key or "").replace("\\", "/").lstrip("/")
        return normalized.startswith(PROTECTED_PREFIXES)

    def _available(self, physical_usage_bytes: int, reserved_bytes: int) -> int:
        return max(0, self.global_limit_bytes - self.safety_reserve_bytes - max(0, int(physical_usage_bytes)) - max(0, int(reserved_bytes)))

    def _validate_required_bytes(self, value: int) -> int:
        size = int(value)
        if size <= 0:
            raise StorageQuotaError("Storage reservation size must be positive.")
        return size

    def _validate_actual_bytes(self, value: int) -> int:
        size = int(value)
        if size < 0:
            raise StorageQuotaError("Actual storage size cannot be negative.")
        return size

    def _default_expires_at(self, operation: str) -> str:
        if operation == "job_result":
            ttl = int(self.config.r2_job_result_reservation_ttl_seconds)
        elif operation == "multipart_upload":
            ttl = int(self.config.r2_multipart_reservation_ttl_seconds)
        else:
            ttl = int(self.config.r2_upload_reservation_ttl_seconds)
        return (datetime.now(timezone.utc) + timedelta(seconds=max(1, ttl))).isoformat()

    def _validate_lab_local_object_key(self, object_key: str, *, session_id: str) -> str:
        normalized = str(object_key or "").replace("\\", "/").strip("/")
        parts = normalized.split("/")
        if len(parts) < 4 or any(part in {"", ".", ".."} for part in parts):
            raise StorageQuotaError("Invalid Lab local object key.")
        safe_session = safe_name(session_id, "session")
        if parts[0] != safe_session:
            raise StorageQuotaError("Lab local object key does not belong to the authenticated session.")
        if parts[1] not in {"uploads", "inputs"}:
            raise StorageQuotaError("Lab local object key uses an unauthorized session prefix.")
        for index, part in enumerate(parts):
            label = "filename" if index == len(parts) - 1 else "path segment"
            if index == 0:
                label = "session_id"
            ObjectKeyBuilder.validate_segment(part, label=label)
        return normalized

    def _job_record(self, job: JobRecord | str) -> JobRecord:
        if isinstance(job, JobRecord):
            return self.database.get_job(job.job_id)
        return self.database.get_job(str(job))

    def _job_result_object_key(self, job: JobRecord) -> str:
        prefix = str(job.output_prefix or "").replace("\\", "/").strip("/")
        if not prefix:
            prefix = ObjectKeyBuilder.result_prefix(safe_name(job.session_id or job.user_id, "session"), safe_name(job.job_id, "job")).strip("/")
        return prefix.rstrip("/") + "/results.zip"

    def _safe_json_list(self, value: str) -> list[str]:
        try:
            data = json.loads(value or "[]")
            if isinstance(data, list):
                return [str(item) for item in data]
        except Exception:
            pass
        return []

    def _job_metadata(self, job: JobRecord) -> dict[str, Any]:
        try:
            data = json.loads(job.metadata_json or "{}")
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _update_job_quota_metadata(self, job_id: str, values: dict[str, Any]) -> None:
        try:
            job = self.database.get_job(job_id)
            metadata = self._job_metadata(job)
            metadata.update(values)
            self.database.update_job(job_id, metadata_json=json.dumps(metadata, ensure_ascii=False, sort_keys=True))
        except Exception:
            return

    def _reservation_is_result(self, reservation: dict[str, Any]) -> bool:
        return self._reservation_metadata(reservation).get("kind") == RESULT_RESERVATION_KIND

    def _reservation_is_job_result(self, reservation: dict[str, Any], job_id: str) -> bool:
        metadata = self._reservation_metadata(reservation)
        return metadata.get("kind") == RESULT_RESERVATION_KIND and str(metadata.get("job_id") or "") == str(job_id)

    def _reservation_metadata(self, reservation: dict[str, Any]) -> dict[str, Any]:
        try:
            data = json.loads(str(reservation.get("metadata_json") or "{}"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _ensure_usage_row(self, conn, now: str) -> None:
        conn.execute(
            "INSERT OR IGNORE INTO storage_usage_state(id, physical_usage_bytes, last_reconciled_at, updated_at) VALUES(1, 0, NULL, ?)",
            (now,),
        )

    def _insert_storage_object_reservation(
        self,
        conn,
        *,
        reservation_id: str,
        session_id: str,
        object_key: str,
        expected_bytes: int,
        expires_at: str | None,
        operation: str,
        metadata: dict[str, Any],
        now: str,
    ) -> None:
        bucket = self.config.runtime_bucket_name() or DEFAULT_RUNTIME_BUCKET
        object_type = "JOB_RESULT" if operation == "job_result" or metadata.get("kind") == RESULT_RESERVATION_KIND else "USER_UPLOAD"
        job_id = str(metadata.get("job_id") or "")
        original_filename = str(metadata.get("filename") or "")
        content_type = str(metadata.get("content_type") or "application/octet-stream")
        conn.execute(
            """
            INSERT INTO storage_objects(
                id, bucket, object_key, session_id, job_id, sha256,
                original_filename, object_type, content_type,
                size_bytes, reserved_bytes, status, expires_at,
                created_at, updated_at, deleted_at, last_error
            )
            VALUES(?, ?, ?, ?, ?, '', ?, ?, ?, 0, ?, 'RESERVED', ?, ?, ?, NULL, '')
            """,
            (
                reservation_id,
                bucket,
                object_key,
                session_id,
                job_id,
                original_filename,
                object_type,
                content_type,
                int(expected_bytes),
                expires_at,
                now,
                now,
            ),
        )

    def _mark_storage_object_status(self, reservation_id: str, status: str) -> None:
        try:
            with self.database.connect() as conn:
                conn.execute(
                    "UPDATE storage_objects SET status=?, updated_at=? WHERE id=?",
                    (status, utc_now(), reservation_id),
                )
        except Exception:
            return

    def _release_storage_object_reservation(self, reservation_id: str, *, last_error: str = "") -> None:
        try:
            now = utc_now()
            with self.database.connect() as conn:
                conn.execute(
                    """
                    UPDATE storage_objects
                    SET status='PURGED', reserved_bytes=0, updated_at=?, deleted_at=?, last_error=?
                    WHERE id=? AND status IN ('RESERVED', 'UPLOADING')
                    """,
                    (now, now, last_error, reservation_id),
                )
        except Exception:
            return

    def _mark_storage_object_purged_by_key(self, object_key: str, *, bucket: str) -> None:
        try:
            now = utc_now()
            with self.database.connect() as conn:
                conn.execute(
                    """
                    UPDATE storage_objects
                    SET status='PURGED', reserved_bytes=0, updated_at=?, deleted_at=?, last_error=''
                    WHERE bucket=? AND object_key=?
                    """,
                    (now, now, bucket, object_key),
                )
        except Exception:
            return

    def _physical_usage_for_update(self, conn) -> int:
        row = conn.execute("SELECT physical_usage_bytes FROM storage_usage_state WHERE id=1").fetchone()
        return max(0, int(row["physical_usage_bytes"] if row else 0))

    def _reserved_usage_for_update(self, conn) -> int:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(expected_bytes), 0) AS total
            FROM storage_reservations
            WHERE status IN (?, ?)
            """,
            ("RESERVED", "UPLOADING"),
        ).fetchone()
        return max(0, int(row["total"] or 0))

    def _status_text(self, usage_percent: float, available: int) -> str:
        if available <= 0:
            return "Full"
        if usage_percent >= 95:
            return "Critical"
        if usage_percent >= 85:
            return "High Risk"
        if usage_percent >= 70:
            return "Warning"
        return "Normal"

    def _log_quota_event(self, action: str, *, session_id: str, reservation_id: str, object_key: str, requested_bytes: int, status: str) -> None:
        try:
            snapshot = self.status()
            LOGGER.info(
                "storage quota %s session_id=%s reservation_id=%s object_key=%s requested_bytes=%s physical_usage_bytes=%s reserved_bytes=%s available_bytes=%s status=%s",
                action,
                safe_name(session_id, "session"),
                safe_name(reservation_id, "reservation"),
                safe_name(object_key.replace("/", "_"), "object"),
                int(requested_bytes),
                snapshot["physical_usage_bytes"],
                snapshot["reserved_bytes"],
                snapshot["available_bytes"],
                status,
            )
        except Exception:
            return
