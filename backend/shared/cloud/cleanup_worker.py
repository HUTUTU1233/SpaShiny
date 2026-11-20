from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .cleanup_coordinator import CleanupCoordinator
from .config import SpaShinyCloudConfig, load_cloud_config
from .database import CloudDatabase
from .models import SessionStatus
from .recovery_manager import RecoveryManager
from .runpod_lifecycle_manager import RunPodLifecycleManager
from .runpod_reconciler import RunPodReconciler
from .session_manager import SessionManager
from .session_watchdog import NoOpSessionCleanupHooks, SessionWatchdog
from .storage_quota import StorageQuotaManager


@dataclass
class CleanupWorker:
    database: CloudDatabase | None = None
    config: SpaShinyCloudConfig | None = None
    sessions: SessionManager | None = None
    coordinator: CleanupCoordinator | None = None
    recovery: RecoveryManager | None = None
    runpod_reconciler: RunPodReconciler | None = None
    storage_quota: StorageQuotaManager | None = None
    _stopped: bool = False

    def __post_init__(self) -> None:
        if self.config is None:
            self.config = load_cloud_config()
        if self.database is None:
            self.database = CloudDatabase(config=self.config)
        if self.sessions is None:
            self.sessions = SessionManager(database=self.database, config=self.config)
        if self.coordinator is None:
            self.coordinator = CleanupCoordinator(database=self.database, config=self.config, sessions=self.sessions)
        if self.recovery is None:
            self.recovery = RecoveryManager(database=self.database, config=self.config, cleanup=self.coordinator)
        if self.runpod_reconciler is None:
            self.runpod_reconciler = RunPodReconciler(RunPodLifecycleManager(database=self.database, config=self.config))
        if self.storage_quota is None:
            self.storage_quota = StorageQuotaManager(database=self.database, config=self.config)

    def stop(self) -> None:
        self._stopped = True

    def run_forever(self) -> None:
        while not self._stopped:
            self.run_once()
            time.sleep(int(self.config.cleanup_worker_interval_seconds))

    def run_once(self) -> dict[str, Any]:
        watchdog = SessionWatchdog(self.sessions, self.database, NoOpSessionCleanupHooks())
        abandoned = watchdog.run_once()
        cleaned_sessions = self.cleanup_pending_sessions()
        retries = self.coordinator.run_due_retries()
        recovery = self.recovery.run_once()
        runpod = self.runpod_reconciler.reconcile_all_managed_instances()
        reconciled_usage = self.storage_quota.reconcile_if_due()
        storage_quota = {
            "expired_reservations": self.storage_quota.expire_stale_reservations(),
            "reconciled": reconciled_usage is not None,
            "status": self.storage_quota.status(),
        }
        return {
            "abandoned_sessions": abandoned,
            "cleaned_sessions": cleaned_sessions,
            "completed_retries": retries,
            "recovery": recovery,
            "runpod": runpod,
            "storage_quota": storage_quota,
        }

    def cleanup_pending_sessions(self) -> list[str]:
        cleaned: list[str] = []
        rows = self.database.list_sessions_by_statuses([SessionStatus.ABANDONED.value, SessionStatus.CLEANING.value])
        for row in rows:
            result = self.coordinator.cleanup_session(str(row["session_id"]), reason="cleanup_worker")
            if result.get("status") == SessionStatus.CLEANED.value:
                cleaned.append(str(row["session_id"]))
        return cleaned
