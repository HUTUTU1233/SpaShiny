from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .config import SpaShinyCloudConfig, load_cloud_config
from .database import CloudDatabase, utc_now


@dataclass
class GpuBudgetManager:
    database: CloudDatabase
    config: SpaShinyCloudConfig | None = None

    def __post_init__(self) -> None:
        if self.config is None:
            self.config = self.database.config or load_cloud_config()

    def usage_date(self, now: datetime | None = None) -> str:
        now = now or datetime.now(timezone.utc)
        return now.astimezone(timezone.utc).date().isoformat()

    def get_gpu_usage(self, usage_date: str | None = None) -> dict[str, float]:
        usage_date = usage_date or self.usage_date()
        with self.database.connect() as conn:
            row = conn.execute(
                """
                SELECT jobs_started, runtime_seconds, estimated_cost_usd, actual_cost_usd
                FROM daily_usage
                WHERE usage_date=? AND resource_type='gpu'
                """,
                (usage_date,),
            ).fetchone()
        if row is None:
            return {"jobs_started": 0, "runtime_seconds": 0.0, "estimated_cost_usd": 0.0, "actual_cost_usd": 0.0}
        return {
            "jobs_started": int(row["jobs_started"] or 0),
            "runtime_seconds": float(row["runtime_seconds"] or 0.0),
            "estimated_cost_usd": float(row["estimated_cost_usd"] or 0.0),
            "actual_cost_usd": float(row["actual_cost_usd"] or 0.0),
        }

    def can_start_gpu_job(self, estimated_cost_usd: float, usage_date: str | None = None) -> bool:
        assert self.config is not None
        if self.config.is_lab_profile:
            return True
        budget = float(self.config.daily_gpu_budget_usd)
        if budget <= 0:
            return False
        usage = self.get_gpu_usage(usage_date)
        return usage["estimated_cost_usd"] + float(estimated_cost_usd or 0.0) <= budget

    def record_gpu_job_start(self, estimated_cost_usd: float, usage_date: str | None = None) -> None:
        usage_date = usage_date or self.usage_date()
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO daily_usage(
                    usage_date, resource_type, jobs_started, runtime_seconds,
                    estimated_cost_usd, actual_cost_usd, updated_at
                )
                VALUES(?, 'gpu', 1, 0, ?, 0, ?)
                ON CONFLICT(usage_date, resource_type) DO UPDATE SET
                    jobs_started=jobs_started + 1,
                    estimated_cost_usd=estimated_cost_usd + excluded.estimated_cost_usd,
                    updated_at=excluded.updated_at
                """,
                (usage_date, float(estimated_cost_usd or 0.0), utc_now()),
            )

    def record_gpu_job_finish(self, runtime_seconds: float, actual_cost_usd: float, usage_date: str | None = None) -> None:
        usage_date = usage_date or self.usage_date()
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO daily_usage(
                    usage_date, resource_type, jobs_started, runtime_seconds,
                    estimated_cost_usd, actual_cost_usd, updated_at
                )
                VALUES(?, 'gpu', 0, ?, 0, ?, ?)
                ON CONFLICT(usage_date, resource_type) DO UPDATE SET
                    runtime_seconds=runtime_seconds + excluded.runtime_seconds,
                    actual_cost_usd=actual_cost_usd + excluded.actual_cost_usd,
                    updated_at=excluded.updated_at
                """,
                (usage_date, float(runtime_seconds or 0.0), float(actual_cost_usd or 0.0), utc_now()),
            )
