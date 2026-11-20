from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .config import SpaShinyCloudConfig, load_cloud_config
from .database import CloudDatabase
from .models import WorkerStatus


def iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


class WorkerHeartbeatRepository:
    def __init__(self, database: CloudDatabase | None = None, config: SpaShinyCloudConfig | None = None) -> None:
        self.config = config or load_cloud_config()
        self.database = database or CloudDatabase(config=self.config)

    def register(self, worker_id: str, worker_type: str = "dispatcher") -> dict:
        return self.database.upsert_worker_instance(
            worker_id=worker_id,
            worker_type=worker_type,
            status=WorkerStatus.ACTIVE.value,
        )

    def heartbeat(self, worker_id: str) -> dict:
        return self.database.heartbeat_worker(worker_id, status=WorkerStatus.ACTIVE.value)

    def stop(self, worker_id: str) -> dict:
        return self.database.mark_worker_stopped(worker_id, status=WorkerStatus.STOPPED.value)

    def mark_lost(self) -> list[str]:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=int(self.config.worker_lost_timeout_seconds))
        return self.database.mark_lost_workers(heartbeat_before=iso(cutoff))

    def is_worker_active(self, worker_id: str) -> bool:
        worker = self.database.get_worker_instance(worker_id)
        if worker is None or worker["status"] != WorkerStatus.ACTIVE.value:
            return False
        last = datetime.fromisoformat(str(worker["last_heartbeat_at"]))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=int(self.config.worker_lost_timeout_seconds))
        return last >= cutoff
