from __future__ import annotations

from dataclasses import dataclass

from .database import CloudDatabase
from .models import UploadStatus
from .upload_service import UploadService


@dataclass
class StorageSessionCleanupHooks:
    database: CloudDatabase | None = None
    uploads: UploadService | None = None

    def __post_init__(self) -> None:
        if self.uploads is None:
            self.uploads = UploadService(database=self.database)
        if self.database is None:
            self.database = self.uploads.database

    def on_session_abandoned(self, session_id: str) -> None:
        assert self.uploads is not None
        assert self.database is not None
        records = self.database.list_uploads_for_cleanup(session_id)
        for record in records:
            try:
                if record.status == UploadStatus.COMPLETED.value:
                    self.uploads.delete_record(record)
                elif record.status not in {UploadStatus.ABORTED.value, UploadStatus.DELETED.value}:
                    self.uploads.abort_record(record)
            except Exception:
                self.database.update_upload(record.upload_id, status=UploadStatus.FAILED.value, error_code="CLEANUP_FAILED")
        try:
            self.uploads.delete_session_prefix(session_id)
        except Exception:
            for record in records:
                try:
                    current = self.database.get_upload(record.upload_id, session_id=session_id)
                except Exception:
                    continue
                if current.status != UploadStatus.DELETED.value:
                    self.database.update_upload(record.upload_id, status=UploadStatus.FAILED.value, error_code="CLEANUP_FAILED")
        try:
            self.uploads.quota.release_session_reservations(session_id, status="RELEASED")
        except Exception:
            return None
