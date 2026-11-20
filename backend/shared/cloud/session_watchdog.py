from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .browser_lifecycle import BrowserLifecycleRegistry
from .database import CloudDatabase
from .models import ACTIVE_JOB_STATUSES
from .job_queue_repository import JobQueueRepository
from .session_manager import SessionManager
from .upload_cleanup import StorageSessionCleanupHooks


class SessionCleanupHooks(Protocol):
    def on_session_abandoned(self, session_id: str) -> None:
        ...


@dataclass
class NoOpSessionCleanupHooks:
    def on_session_abandoned(self, session_id: str) -> None:
        return None


class SessionWatchdog:
    """End abandoned analyses and use the existing queue cancellation path."""

    def __init__(self, session_manager: SessionManager | None = None, database: CloudDatabase | None = None, cleanup_hooks: SessionCleanupHooks | None = None) -> None:
        self.session_manager = session_manager or SessionManager()
        self.database = database or self.session_manager.database
        self.cleanup_hooks = cleanup_hooks or StorageSessionCleanupHooks(database=self.database)
        config = self.session_manager.config
        self.browser_lifecycle = BrowserLifecycleRegistry(
            database=self.database,
            grace_seconds=config.analysis_close_grace_seconds,
            heartbeat_lease_seconds=config.analysis_heartbeat_lease_seconds,
        )
        self.job_queue = JobQueueRepository(database=self.database, config=config)

    def _request_analysis_cancellation(self, owner_session_id: str, analysis_session_id: str) -> int:
        jobs = self.database.list_active_jobs_for_analysis(
            owner_session_id=owner_session_id,
            analysis_session_id=analysis_session_id,
            statuses=ACTIVE_JOB_STATUSES,
        )
        for job in jobs:
            # Canonical and idempotent: queue repository handles terminal races.
            self.job_queue.request_cancel(str(job.session_id), job.job_id)
        return len(jobs)

    def run_once(self) -> list[str]:
        ended = self.browser_lifecycle.expire_pending()
        ended.extend(self.browser_lifecycle.expire_heartbeat_leases())
        seen: set[tuple[str, str]] = set()
        cancelled: list[str] = []
        for scope in ended:
            key = (str(scope["owner_session_id"]), str(scope["analysis_session_id"]))
            if key in seen:
                continue
            seen.add(key)
            self._request_analysis_cancellation(*key)
            cancelled.append(key[1])
        return cancelled
