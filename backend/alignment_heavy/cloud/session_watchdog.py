from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .browser_lifecycle import BrowserLifecycleRegistry
from .database import CloudDatabase
from .models import JobStatus
from .session_manager import SessionManager, utc_now
from .upload_cleanup import StorageSessionCleanupHooks


class SessionCleanupHooks(Protocol):
    def on_session_abandoned(self, session_id: str) -> None:
        ...


@dataclass
class NoOpSessionCleanupHooks:
    def on_session_abandoned(self, session_id: str) -> None:
        return None


class SessionWatchdog:
    def __init__(
        self,
        session_manager: SessionManager | None = None,
        database: CloudDatabase | None = None,
        cleanup_hooks: SessionCleanupHooks | None = None,
    ) -> None:
        self.session_manager = session_manager or SessionManager()
        self.database = database or self.session_manager.database
        self.cleanup_hooks = cleanup_hooks or StorageSessionCleanupHooks(database=self.database)
        self.browser_lifecycle = BrowserLifecycleRegistry(database=self.database)

    def run_once(self) -> list[str]:
        # This expires only browser-page pending records. It deliberately does
        # not expire owner sessions based on inactivity: long-running Lab jobs
        # are owned by JobManager/worker state, not by websocket idleness.
        self.browser_lifecycle.expire_pending()
        return []

    def cancel_unstarted_jobs(self, session_id: str) -> int:
        cancellable = [
            JobStatus.CREATED.value,
            JobStatus.VALIDATING.value,
            JobStatus.QUEUED.value,
            JobStatus.QUEUED_CPU.value,
            JobStatus.QUEUED_GPU.value,
            JobStatus.WAITING_FOR_GPU.value,
        ]
        with self.database.connect() as conn:
            cursor = conn.execute(
                "UPDATE jobs SET status=?, cancel_requested_at=? WHERE session_id=? AND status IN ("
                + ", ".join("?" for _ in cancellable)
                + ")",
                [JobStatus.CANCELLED.value, utc_now().isoformat(), session_id, *cancellable],
            )
            return int(cursor.rowcount or 0)

    def request_cancel_running_jobs(self, session_id: str) -> int:
        running = [
            JobStatus.STARTING.value,
            JobStatus.STARTING_GPU.value,
            JobStatus.RUNNING.value,
            JobStatus.POSTPROCESSING.value,
            JobStatus.SYNCING.value,
            JobStatus.VERIFYING.value,
        ]
        with self.database.connect() as conn:
            cursor = conn.execute(
                "UPDATE jobs SET status=?, cancel_requested_at=? WHERE session_id=? AND status IN ("
                + ", ".join("?" for _ in running)
                + ")",
                [JobStatus.CANCEL_REQUESTED.value, utc_now().isoformat(), session_id, *running],
            )
            return int(cursor.rowcount or 0)
