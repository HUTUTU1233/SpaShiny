from __future__ import annotations

import time
from pathlib import Path

from .database import CloudDatabase
from .models import TERMINAL_STATUSES


class CleanupManager:
    def __init__(self, database: CloudDatabase | None = None) -> None:
        self.database = database or CloudDatabase()

    def stale_terminal_jobs(self, max_age_days: int = 30) -> list[str]:
        cutoff = time.time() - max_age_days * 86400
        stale = []
        for job in self.database.list_jobs(statuses=list(TERMINAL_STATUSES), limit=10000):
            path = Path(job.local_workspace)
            if path.exists() and path.stat().st_mtime < cutoff:
                stale.append(job.job_id)
        return stale
