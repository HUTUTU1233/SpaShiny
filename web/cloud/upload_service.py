from __future__ import annotations

import json
import math
import re
import secrets
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from .config import SpaShinyCloudConfig, load_cloud_config
from .database import CloudDatabase
from .models import SessionStatus, UploadRecord, UploadStatus
from .object_keys import ObjectKeyBuilder
from .session_manager import SessionRecord, isoformat, utc_now
from .storage import safe_name
from .storage_backends import TemporaryObjectStorage, get_temporary_object_storage
from .storage_quota import GlobalStorageLimitExceeded, ScopedStorageLimitExceeded, StorageQuotaManager


ALLOWED_UPLOAD_SUFFIXES = {
    ".zip",
    ".h5ad",
    ".h5",
    ".hdf5",
    ".imzml",
    ".ibd",
    ".csv",
    ".tsv",
    ".txt",
    ".json",
    ".mtx",
    ".gz",
}

DANGEROUS_UPLOAD_SUFFIXES = {
    ".py",
    ".pyc",
    ".pyo",
    ".r",
    ".sh",
    ".bat",
    ".cmd",
    ".ps1",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".pem",
    ".key",
    ".p12",
    ".pfx",
}

WINDOWS_RESERVED_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


class UploadValidationError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 400, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = int(status_code)
        self.details = details or {}


@dataclass(frozen=True)
class UploadPart:
    part_number: int
    etag: str


def sanitize_upload_filename(filename: str) -> str:
    original = str(filename or "").strip()
    if not original:
        raise UploadValidationError("INVALID_FILENAME", "Filename is required.")
    without_controls = re.sub(r"[\x00-\x1f\x7f]+", "_", original)
    flattened = without_controls.replace("\\", "_").replace("/", "_")
    flattened = re.sub(r"\s+", "_", flattened)
    flattened = flattened.strip(" ._")
    if not flattened:
        raise UploadValidationError("INVALID_FILENAME", "Filename is not usable.")
    suffixes = [suffix.lower() for suffix in Path(flattened).suffixes]
    if any(suffix in DANGEROUS_UPLOAD_SUFFIXES for suffix in suffixes):
        raise UploadValidationError("DISALLOWED_FILE_TYPE", "This file type is not allowed.")
    if not suffixes or suffixes[-1] not in ALLOWED_UPLOAD_SUFFIXES:
        raise UploadValidationError("UNSUPPORTED_FILE_TYPE", "Unsupported upload file type.")
    stem = Path(flattened).stem.lower()
    if stem in WINDOWS_RESERVED_NAMES:
        flattened = f"upload_{flattened}"
    return safe_name(flattened, "upload")


def build_upload_object_key(session_id: str, upload_id: str, safe_filename: str, *, lab_profile: bool = False) -> str:
    if lab_profile:
        safe_session = safe_name(session_id, "session")
        safe_upload = safe_name(upload_id, "upload")
        safe_file = safe_name(safe_filename, "upload")
        return f"{safe_session}/uploads/{safe_upload}/{safe_file}"
    return ObjectKeyBuilder.upload_object(
        safe_name(session_id, "session"),
        safe_name(upload_id, "upload"),
        safe_name(safe_filename, "upload"),
    )


class UploadService:
    def __init__(
        self,
        *,
        config: SpaShinyCloudConfig | None = None,
        database: CloudDatabase | None = None,
        storage: TemporaryObjectStorage | None = None,
        quota: StorageQuotaManager | None = None,
    ) -> None:
        self.config = config or (database.config if database is not None else load_cloud_config())
        self.database = database or CloudDatabase(config=self.config)
        self.storage = storage or get_temporary_object_storage(self.config)
        self.quota = quota or StorageQuotaManager(database=self.database, config=self.config, storage=self.storage)

    def initiate_upload(
        self,
        *,
        session: SessionRecord,
        analysis_session_id: str,
        filename: str,
        size_bytes: int,
        content_type: str,
        total_parts: int,
    ) -> dict[str, Any]:
        self._require_active_session(session)
        analysis_session_id = str(analysis_session_id or "").strip()
        if not analysis_session_id:
            raise UploadValidationError("ANALYSIS_SESSION_REQUIRED", "A tab analysis session is required.", status_code=409)
        declared_size = self._validate_size(size_bytes)
        part_size = int(self.config.r2_multipart_part_size_bytes)
        expected_parts = max(1, math.ceil(declared_size / part_size))
        total_parts = int(total_parts)
        if total_parts < 1:
            raise UploadValidationError("INVALID_PART_COUNT", "Part count must be positive.")
        total_parts = expected_parts
        self._validate_session_limits(session, declared_size)
        safe_filename = sanitize_upload_filename(filename)
        upload_id = "upl_" + secrets.token_hex(16)
        object_key = build_upload_object_key(
            session.session_id,
            upload_id,
            safe_filename,
            lab_profile=bool(self.config.is_lab_profile),
        )
        expires_at = utc_now() + timedelta(seconds=int(self.config.r2_presigned_url_ttl_seconds))
        reservation_id = ""
        multipart_upload_id = ""
        try:
            reservation = self.quota.reserve_storage(
                session_id=session.session_id,
                analysis_session_id=analysis_session_id,
                object_key=object_key,
                expected_bytes=declared_size,
                expires_at=isoformat(expires_at),
                operation="multipart_upload",
                metadata={"upload_id": upload_id, "filename": safe_filename},
            )
            reservation_id = str(reservation["reservation_id"])
        except GlobalStorageLimitExceeded as exc:
            raise UploadValidationError("GLOBAL_STORAGE_LIMIT_EXCEEDED", str(exc), status_code=507, details=exc.to_dict()) from exc
        except ScopedStorageLimitExceeded as exc:
            raise UploadValidationError(exc.code, str(exc), status_code=413, details=exc.to_dict()) from exc
        try:
            multipart_upload_id = self.storage.create_multipart_upload(
                object_key=object_key,
                content_type=content_type or "application/octet-stream",
                metadata={"session_id": session.session_id, "upload_id": upload_id, "reservation_id": reservation_id},
            )
        except Exception:
            if reservation_id:
                self.quota.release_reservation(
                    reservation_id, session_id=session.session_id, analysis_session_id=analysis_session_id,
                    status="FAILED", error_message="multipart create failed"
                )
            raise
        metadata = {
            "part_size": part_size,
            "total_parts": total_parts,
            "max_parallel_parts": int(self.config.r2_multipart_max_parallel_parts),
            "storage_reservation_id": reservation_id,
        }
        record = UploadRecord(
            upload_id=upload_id,
            session_id=session.session_id,
            analysis_session_id=analysis_session_id,
            original_filename=str(filename),
            safe_filename=safe_filename,
            object_key=object_key,
            multipart_upload_id=multipart_upload_id,
            declared_size_bytes=declared_size,
            actual_size_bytes=0,
            content_type=content_type or "application/octet-stream",
            status=UploadStatus.INITIATED.value,
            created_at=isoformat(utc_now()),
            expires_at=isoformat(expires_at),
            metadata_json=json.dumps(metadata, ensure_ascii=False, sort_keys=True),
        )
        try:
            record = self.database.create_upload(record)
        except Exception:
            try:
                self.storage.abort_multipart_upload(object_key=object_key, multipart_upload_id=multipart_upload_id)
            finally:
                self.quota.release_reservation(
                    reservation_id, session_id=session.session_id, analysis_session_id=analysis_session_id,
                    status="FAILED", error_message="upload database insert failed"
                )
            raise
        return {
            "upload_id": record.upload_id,
            "status": record.status,
            "part_size": part_size,
            "total_parts": total_parts,
            "max_parallel_parts": int(self.config.r2_multipart_max_parallel_parts),
            "expires_at": record.expires_at,
        }

    def presign_part(self, *, session: SessionRecord, analysis_session_id: str, upload_id: str, part_number: int) -> dict[str, Any]:
        record, part_number, _ = self._prepare_part_upload(
            session=session,
            analysis_session_id=analysis_session_id,
            upload_id=upload_id,
            part_number=part_number,
        )
        url = self.storage.create_presigned_part_url(
            object_key=record.object_key,
            multipart_upload_id=record.multipart_upload_id,
            part_number=part_number,
            expires_seconds=int(self.config.r2_presigned_url_ttl_seconds),
        )
        return {
            "upload_id": record.upload_id,
            "part_number": part_number,
            "url": url,
            "expires_in": int(self.config.r2_presigned_url_ttl_seconds),
        }

    def local_part_upload_limit(
        self, *, session: SessionRecord, analysis_session_id: str, upload_id: str, part_number: int
    ) -> int:
        _, _, expected_bytes = self._prepare_part_upload(
            session=session,
            analysis_session_id=analysis_session_id,
            upload_id=upload_id,
            part_number=part_number,
        )
        return expected_bytes

    def put_local_part_from_path(
        self,
        *,
        session: SessionRecord,
        analysis_session_id: str,
        upload_id: str,
        part_number: int,
        source_path: str | Path,
    ) -> dict[str, Any]:
        record, part_number, expected_bytes = self._prepare_part_upload(
            session=session,
            analysis_session_id=analysis_session_id,
            upload_id=upload_id,
            part_number=part_number,
        )
        source = Path(source_path)
        if not source.is_file() or int(source.stat().st_size) != expected_bytes:
            raise UploadValidationError("INVALID_PART_SIZE", "Uploaded part size does not match the declared multipart contract.")
        put_from_path = getattr(self.storage, "put_part_from_path", None)
        if not callable(put_from_path):
            raise UploadValidationError("LOCAL_PART_TRANSPORT_UNAVAILABLE", "This storage backend does not accept Control-streamed multipart parts.", status_code=409)
        etag = str(put_from_path(record.multipart_upload_id, part_number, source))
        return {"upload_id": record.upload_id, "part_number": part_number, "etag": etag}

    def _prepare_part_upload(
        self, *, session: SessionRecord, analysis_session_id: str, upload_id: str, part_number: int
    ) -> tuple[UploadRecord, int, int]:
        self._require_active_session(session)
        analysis_session_id = self._require_analysis_scope(analysis_session_id)
        record = self.database.get_upload(upload_id, session_id=session.session_id, analysis_session_id=analysis_session_id)
        metadata = self._metadata(record)
        total_parts = int(metadata.get("total_parts") or 0)
        part_number = int(part_number)
        if part_number < 1 or part_number > total_parts:
            raise UploadValidationError("INVALID_PART_NUMBER", "Part number is outside the upload range.")
        if record.status not in {UploadStatus.INITIATED.value, UploadStatus.UPLOADING.value}:
            raise UploadValidationError("UPLOAD_NOT_ACTIVE", "Upload is not accepting parts.", status_code=409)
        if record.status == UploadStatus.INITIATED.value:
            record = self.database.update_upload(upload_id, session_id=session.session_id, analysis_session_id=analysis_session_id, status=UploadStatus.UPLOADING.value)
            reservation_id = self._reservation_id(record)
            if reservation_id:
                self.quota.mark_uploading(
                    reservation_id, session_id=session.session_id, analysis_session_id=analysis_session_id
                )
        part_size = int(self.config.r2_multipart_part_size_bytes)
        remaining = int(record.declared_size_bytes) - ((part_number - 1) * part_size)
        expected_bytes = min(part_size, remaining)
        if expected_bytes <= 0:
            raise UploadValidationError("INVALID_PART_NUMBER", "Part number is outside the declared upload size.")
        return record, part_number, expected_bytes

    def complete_upload(self, *, session: SessionRecord, analysis_session_id: str, upload_id: str, parts: list[UploadPart]) -> UploadRecord:
        self._require_active_session(session)
        analysis_session_id = self._require_analysis_scope(analysis_session_id)
        record = self.database.get_upload(upload_id, session_id=session.session_id, analysis_session_id=analysis_session_id)
        if record.status == UploadStatus.COMPLETED.value:
            return record
        if record.status not in {
            UploadStatus.INITIATED.value,
            UploadStatus.UPLOADING.value,
            UploadStatus.COMPLETING.value,
        }:
            raise UploadValidationError("UPLOAD_NOT_ACTIVE", "Upload cannot be completed.", status_code=409)
        normalized_parts = self._validate_complete_parts(record, parts)
        self.database.update_upload(upload_id, session_id=session.session_id, analysis_session_id=analysis_session_id, status=UploadStatus.COMPLETING.value)
        try:
            head = self.storage.complete_multipart_upload(
                object_key=record.object_key,
                multipart_upload_id=record.multipart_upload_id,
                parts=[{"part_number": part.part_number, "etag": part.etag} for part in normalized_parts],
            )
            self._validate_completed_size(record, head.size_bytes)
            reservation_id = self._reservation_id(record)
            if reservation_id:
                try:
                    self.quota.commit_reservation(
                        reservation_id, session_id=session.session_id, analysis_session_id=analysis_session_id,
                        actual_bytes=head.size_bytes
                    )
                except (GlobalStorageLimitExceeded, ScopedStorageLimitExceeded) as exc:
                    self._safe_delete_object(record.object_key)
                    self.quota.release_reservation(
                        reservation_id, session_id=session.session_id, analysis_session_id=analysis_session_id,
                        status="FAILED", error_message="completed object exceeded global storage limit"
                    )
                    status_code = 507 if isinstance(exc, GlobalStorageLimitExceeded) else 413
                    code = "GLOBAL_STORAGE_LIMIT_EXCEEDED" if isinstance(exc, GlobalStorageLimitExceeded) else exc.code
                    self.database.update_upload(upload_id, session_id=session.session_id, analysis_session_id=analysis_session_id, status=UploadStatus.FAILED.value, error_code=code)
                    raise UploadValidationError(code, str(exc), status_code=status_code, details=exc.to_dict()) from exc
        except UploadValidationError:
            raise
        except Exception as exc:
            self._safe_delete_object(record.object_key)
            reservation_id = self._reservation_id(record)
            if reservation_id:
                self.quota.release_reservation(
                    reservation_id, session_id=session.session_id, analysis_session_id=analysis_session_id,
                    status="FAILED", error_message=exc
                )
            return self._fail_upload(record.upload_id, "COMPLETE_FAILED", exc, session_id=session.session_id, analysis_session_id=analysis_session_id)
        updated = self.database.update_upload(
            upload_id,
            session_id=session.session_id,
            analysis_session_id=analysis_session_id,
            status=UploadStatus.COMPLETED.value,
            actual_size_bytes=head.size_bytes,
            completed_at=isoformat(utc_now()),
            sha256=head.sha256,
            error_code=None,
        )
        self.database.add_session_upload_bytes(session.session_id, head.size_bytes)
        return updated

    def abort_upload(self, *, session: SessionRecord, analysis_session_id: str, upload_id: str) -> UploadRecord:
        analysis_session_id = self._require_analysis_scope(analysis_session_id)
        record = self.database.get_upload(upload_id, session_id=session.session_id, analysis_session_id=analysis_session_id)
        return self.abort_record(record, session_id=session.session_id, analysis_session_id=analysis_session_id)

    def abort_record(
        self, record: UploadRecord, *, session_id: str | None = None, analysis_session_id: str | None = None
    ) -> UploadRecord:
        if record.status in {UploadStatus.ABORTED.value, UploadStatus.DELETED.value}:
            return record
        self.database.update_upload(record.upload_id, session_id=session_id, analysis_session_id=analysis_session_id, status=UploadStatus.ABORT_REQUESTED.value)
        try:
            self.storage.abort_multipart_upload(
                object_key=record.object_key,
                multipart_upload_id=record.multipart_upload_id,
            )
        finally:
            reservation_id = self._reservation_id(record)
            if reservation_id:
                self.quota.release_reservation(
                    reservation_id, session_id=session_id, analysis_session_id=analysis_session_id, status="RELEASED"
                )
            return self.database.update_upload(
                record.upload_id,
                session_id=session_id,
                analysis_session_id=analysis_session_id,
                status=UploadStatus.ABORTED.value,
                aborted_at=isoformat(utc_now()),
            )

    def delete_upload(self, *, session: SessionRecord, analysis_session_id: str, upload_id: str) -> UploadRecord:
        analysis_session_id = self._require_analysis_scope(analysis_session_id)
        record = self.database.get_upload(upload_id, session_id=session.session_id, analysis_session_id=analysis_session_id)
        return self.delete_record(record, session_id=session.session_id, analysis_session_id=analysis_session_id)

    def delete_record(
        self, record: UploadRecord, *, session_id: str | None = None, analysis_session_id: str | None = None
    ) -> UploadRecord:
        if record.status == UploadStatus.DELETED.value:
            return record
        self.database.update_upload(record.upload_id, session_id=session_id, analysis_session_id=analysis_session_id, status=UploadStatus.DELETING.value)
        try:
            if record.status == UploadStatus.COMPLETED.value:
                self.storage.delete_object(record.object_key)
                self.quota.record_object_deleted(object_key=record.object_key, size_bytes=record.actual_size_bytes)
                if record.actual_size_bytes:
                    self.database.add_session_upload_bytes(record.session_id, -int(record.actual_size_bytes))
            else:
                self.storage.abort_multipart_upload(
                    object_key=record.object_key,
                    multipart_upload_id=record.multipart_upload_id,
                )
                reservation_id = self._reservation_id(record)
                if reservation_id:
                    self.quota.release_reservation(reservation_id, session_id=session_id, analysis_session_id=analysis_session_id, status="RELEASED")
        except Exception as exc:
            return self._fail_upload(record.upload_id, "DELETE_FAILED", exc, session_id=session_id, analysis_session_id=analysis_session_id)
        return self.database.update_upload(record.upload_id, session_id=session_id, analysis_session_id=analysis_session_id, status=UploadStatus.DELETED.value, aborted_at=isoformat(utc_now()))

    def list_uploads(self, *, session: SessionRecord, analysis_session_id: str, limit: int = 100) -> list[UploadRecord]:
        analysis_session_id = self._require_analysis_scope(analysis_session_id)
        return self.database.list_uploads(session_id=session.session_id, analysis_session_id=analysis_session_id, limit=limit)

    def download_upload(self, *, session: SessionRecord, analysis_session_id: str, upload_id: str) -> dict[str, Any]:
        analysis_session_id = self._require_analysis_scope(analysis_session_id)
        record = self.database.get_upload(upload_id, session_id=session.session_id, analysis_session_id=analysis_session_id)
        if record.status != UploadStatus.COMPLETED.value:
            raise UploadValidationError("UPLOAD_NOT_COMPLETED", "Only completed uploads can be downloaded.", status_code=409)
        url = self.storage.create_presigned_download_url(
            object_key=record.object_key,
            expires_seconds=int(self.config.r2_presigned_url_ttl_seconds),
            filename=record.safe_filename,
        )
        return {
            "upload_id": record.upload_id,
            "url": url,
            "expires_in": int(self.config.r2_presigned_url_ttl_seconds),
        }

    def delete_session_prefix(self, session_id: str) -> None:
        safe_session_id = safe_name(session_id, "session")
        if self.config.is_lab_profile:
            prefixes = [f"{safe_session_id}/uploads/", f"{safe_session_id}/inputs/"]
        else:
            prefixes = [*ObjectKeyBuilder.session_runtime_prefixes(safe_session_id), f"sessions/{safe_session_id}/"]
        for prefix in prefixes:
            for object_key in self.storage.list_prefix(prefix):
                if self.quota.is_protected_object(object_key):
                    continue
                size = 0
                try:
                    size = int(self.storage.head_object(object_key).size_bytes)
                except Exception:
                    size = 0
                self.storage.delete_object(object_key)
                self.quota.record_object_deleted(object_key=object_key, size_bytes=size)

    def _require_active_session(self, session: SessionRecord) -> None:
        if session.status != SessionStatus.ACTIVE.value:
            raise UploadValidationError("SESSION_NOT_ACTIVE", "Session is not active.", status_code=410)

    @staticmethod
    def _require_analysis_scope(analysis_session_id: str) -> str:
        scope = str(analysis_session_id or "").strip()
        if not scope:
            raise UploadValidationError("ANALYSIS_SESSION_REQUIRED", "A tab analysis session is required.", status_code=409)
        return scope

    def _validate_size(self, size_bytes: int) -> int:
        size = int(size_bytes)
        if size <= 0:
            raise UploadValidationError("INVALID_SIZE", "Upload size must be positive.")
        if size > int(self.config.max_upload_file_bytes):
            raise UploadValidationError("FILE_TOO_LARGE", "Upload exceeds the per-file limit.", status_code=413)
        return size

    def _validate_session_limits(self, session: SessionRecord, declared_size: int) -> None:
        pending_bytes = self.database.sum_session_declared_upload_bytes(session.session_id)
        if int(session.total_upload_bytes) + pending_bytes + declared_size > int(self.config.max_session_upload_bytes):
            raise UploadValidationError("SESSION_UPLOAD_LIMIT_EXCEEDED", "Session upload byte limit exceeded.", status_code=413)
        if self.database.count_session_uploads(session.session_id) >= int(self.config.max_session_upload_files):
            raise UploadValidationError("SESSION_UPLOAD_FILE_LIMIT_EXCEEDED", "Session upload file limit exceeded.", status_code=429)
        active_sessions = self.database.count_active_upload_sessions()
        if not self.database.session_has_active_upload(session.session_id) and active_sessions >= int(self.config.max_concurrent_upload_sessions):
            raise UploadValidationError("UPLOAD_SESSION_CONCURRENCY_EXCEEDED", "Too many upload sessions are active.", status_code=429)

    def _validate_complete_parts(self, record: UploadRecord, parts: list[UploadPart]) -> list[UploadPart]:
        metadata = self._metadata(record)
        total_parts = int(metadata.get("total_parts") or 0)
        if not parts:
            raise UploadValidationError("INVALID_PARTS", "Complete request must include uploaded parts.")
        seen = set()
        normalized = []
        for part in parts:
            if part.part_number in seen:
                raise UploadValidationError("INVALID_PARTS", "Duplicate part number.")
            seen.add(part.part_number)
            normalized.append(part)
        expected = list(range(1, total_parts + 1))
        actual = sorted(seen)
        if actual != expected:
            raise UploadValidationError("INVALID_PARTS", "Parts must be continuous and complete.")
        return sorted(normalized, key=lambda item: item.part_number)

    def _validate_completed_size(self, record: UploadRecord, actual_size: int) -> None:
        if int(actual_size) > int(self.config.max_upload_file_bytes):
            raise UploadValidationError("FILE_TOO_LARGE", "Completed object exceeds the per-file limit.", status_code=413)

    def _metadata(self, record: UploadRecord) -> dict[str, Any]:
        try:
            data = json.loads(record.metadata_json or "{}")
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _reservation_id(self, record: UploadRecord) -> str:
        return str(self._metadata(record).get("storage_reservation_id") or "")

    def _safe_delete_object(self, object_key: str) -> None:
        try:
            self.storage.delete_object(object_key)
        except Exception:
            return None

    def _fail_upload(
        self, upload_id: str, code: str, exc: Exception, *,
        session_id: str | None = None, analysis_session_id: str | None = None
    ) -> UploadRecord:
        self.database.update_upload(
            upload_id, session_id=session_id, analysis_session_id=analysis_session_id,
            status=UploadStatus.FAILED.value, error_code=code
        )
        if isinstance(exc, UploadValidationError):
            raise exc
        raise UploadValidationError(code, "Upload operation failed.", status_code=500) from exc
