from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import SpaShinyCloudConfig, load_cloud_config
from .lab_runtime import is_lab_queue_name
from .database import CloudDatabase, utc_now
from .models import (
    JobRecord,
    JobStatus,
    QUEUED_RESOURCE_JOB_STATUSES,
    ResourceType,
    TERMINAL_STATUSES,
    row_to_job,
    validate_job_status_transition,
)
from .workflow_registry import gpu_provider_workflow_allowlist


LEASE_ACTIVE = "ACTIVE"
LEASE_RELEASED = "RELEASED"
LEASE_EXPIRED = "EXPIRED"


@dataclass(frozen=True)
class ClaimedJob:
    job: JobRecord
    worker_id: str
    claim_token: str
    lease_id: str


def coerce_utc(value: datetime | str | None = None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso(value: datetime | str | None = None) -> str:
    return coerce_utc(value).isoformat()


class JobQueueRepository:
    def __init__(self, database: CloudDatabase | None = None, config: SpaShinyCloudConfig | None = None) -> None:
        self.config = config or load_cloud_config()
        self.database = database or CloudDatabase(config=self.config)

    def claim_next_cpu_job(self, worker_id: str, *, queue_names: tuple[str, ...] | None = None) -> ClaimedJob | None:
        return self._claim_next_job(
            worker_id=worker_id,
            resource_type=ResourceType.CPU.value,
            queue_status=JobStatus.QUEUED_CPU.value,
            concurrency=int(self.config.max_cpu_concurrency),
            timeout_seconds=int(self.config.max_cpu_job_seconds),
            queue_names=queue_names or (ResourceType.CPU.value, "leaseweb_local_cpu", "runpod_cpu"),
        )

    def claim_next_gpu_job(self, worker_id: str, *, queue_names: tuple[str, ...] | None = None) -> ClaimedJob | None:
        return self._claim_next_job(
            worker_id=worker_id,
            resource_type=ResourceType.GPU.value,
            queue_status=JobStatus.QUEUED_GPU.value,
            concurrency=int(self.config.max_gpu_concurrency),
            timeout_seconds=int(self.config.max_gpu_job_seconds),
            queue_names=queue_names or (
                ResourceType.GPU.value,
                "lab_gpu_0",
                "lab_gpu_1",
                "modal_t4",
                "salad_rtx3090",
                "tensordock_reserved",
                "runpod_gpu",
            ),
            allowed_workflows=gpu_provider_workflow_allowlist(),
        )

    def _claim_next_job(
        self,
        *,
        worker_id: str,
        resource_type: str,
        queue_status: str,
        concurrency: int,
        timeout_seconds: int,
        queue_names: tuple[str, ...],
        allowed_workflows: tuple[str, ...] | None = None,
    ) -> ClaimedJob | None:
        now = coerce_utc()
        now_iso = iso(now)
        lease_expires_at = iso(now + timedelta(seconds=int(self.config.resource_lease_seconds)))
        timeout_at = iso(now + timedelta(seconds=timeout_seconds))
        with self.database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                queue_name_values = tuple(str(value) for value in queue_names if str(value).strip()) or (resource_type,)
                if resource_type == ResourceType.GPU.value and any(is_lab_queue_name(value) for value in queue_name_values):
                    active_leases = conn.execute(
                        """
                        SELECT COUNT(*) AS count
                        FROM resource_leases AS leases
                        JOIN jobs ON jobs.job_id=leases.job_id
                        WHERE leases.resource_type=?
                        AND leases.status=?
                        AND leases.expires_at > ?
                        AND jobs.queue_name IN (
                        """
                        + ", ".join("?" for _ in queue_name_values)
                        + """
                        )
                        """,
                        (resource_type, LEASE_ACTIVE, now_iso, *queue_name_values),
                    ).fetchone()
                else:
                    active_leases = conn.execute(
                        """
                        SELECT COUNT(*) AS count
                        FROM resource_leases
                        WHERE resource_type=?
                        AND status=?
                        AND expires_at > ?
                        """,
                        (resource_type, LEASE_ACTIVE, now_iso),
                    ).fetchone()
                if int(active_leases["count"] or 0) >= int(concurrency):
                    conn.execute("COMMIT")
                    return None
                workflow_values = tuple(str(value) for value in (allowed_workflows or ()) if str(value).strip())
                if resource_type == ResourceType.GPU.value and not workflow_values:
                    conn.execute("COMMIT")
                    return None
                workflow_filter = ""
                workflow_params: tuple[str, ...] = ()
                if resource_type == ResourceType.GPU.value:
                    workflow_filter = (
                        " AND (workflow_name IN ("
                        + ", ".join("?" for _ in workflow_values)
                        + ") OR workflow IN ("
                        + ", ".join("?" for _ in workflow_values)
                        + "))"
                    )
                    workflow_params = (*workflow_values, *workflow_values)
                row = conn.execute(
                    """
                    SELECT * FROM jobs
                    WHERE status=?
                    AND queue_name IN (
                    """ + ", ".join("?" for _ in queue_name_values) + """
                    )
                    """ + workflow_filter + """
                    ORDER BY priority DESC, created_at ASC, job_id ASC
                    LIMIT 1
                    """,
                    (queue_status, *queue_name_values, *workflow_params),
                ).fetchone()
                if row is None:
                    conn.execute("COMMIT")
                    return None
                if resource_type == ResourceType.GPU.value and not self._gpu_budget_available(conn, row, now):
                    validate_job_status_transition(str(row["status"]), JobStatus.BUDGET_LIMIT.value)
                    conn.execute(
                        "UPDATE jobs SET status=?, error_code=? WHERE job_id=? AND status=?",
                        (JobStatus.BUDGET_LIMIT.value, "BUDGET_LIMIT", row["job_id"], queue_status),
                    )
                    conn.execute("COMMIT")
                    return None
                claim_token = secrets.token_urlsafe(24)
                lease_id = "lease_" + secrets.token_hex(16)
                attempt_number = int(row["attempt"] or 0) + 1
                cursor = conn.execute(
                    """
                    UPDATE jobs
                    SET status=?,
                        worker_id=?,
                        claim_token=?,
                        claimed_at=?,
                        timeout_at=?,
                        attempt=?
                    WHERE job_id=?
                    AND status=?
                    """,
                    (
                        JobStatus.STARTING.value,
                        worker_id,
                        claim_token,
                        now_iso,
                        timeout_at,
                        attempt_number,
                        row["job_id"],
                        queue_status,
                    ),
                )
                if cursor.rowcount != 1:
                    conn.execute("ROLLBACK")
                    return None
                conn.execute(
                    """
                    INSERT INTO resource_leases(
                        lease_id, resource_type, worker_id, job_id,
                        acquired_at, expires_at, released_at, status
                    )
                    VALUES(?, ?, ?, ?, ?, ?, NULL, ?)
                    """,
                    (lease_id, resource_type, worker_id, row["job_id"], now_iso, lease_expires_at, LEASE_ACTIVE),
                )
                conn.execute(
                    """
                    INSERT INTO job_attempts(
                        job_id, attempt_number, worker_id, status,
                        started_at, finished_at, error_code, error_message, metadata_json
                    )
                    VALUES(?, ?, ?, ?, ?, NULL, NULL, NULL, '{}')
                    """,
                    (row["job_id"], attempt_number, worker_id, JobStatus.STARTING.value, now_iso),
                )
                if resource_type == ResourceType.GPU.value:
                    self._record_gpu_start(conn, row, now)
                updated = conn.execute("SELECT * FROM jobs WHERE job_id=?", (row["job_id"],)).fetchone()
                conn.execute("COMMIT")
                return ClaimedJob(row_to_job(updated), worker_id=worker_id, claim_token=claim_token, lease_id=lease_id)
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def update_claimed_job(self, job_id: str, worker_id: str, claim_token: str, status: str, **updates: Any) -> JobRecord:
        filtered = {key: value for key, value in updates.items() if key in set(JobRecord.__dataclass_fields__) - {"job_id"}}
        assignments = ["status=?"]
        params: list[Any] = [status]
        for key, value in filtered.items():
            assignments.append(f"{key}=?")
            params.append(value)
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT status FROM jobs WHERE job_id=? AND worker_id=? AND claim_token=?",
                (job_id, worker_id, claim_token),
            ).fetchone()
            if row is None:
                raise PermissionError("Worker claim does not match this job.")
            validate_job_status_transition(str(row["status"]), str(status))
            cursor = conn.execute(
                f"UPDATE jobs SET {', '.join(assignments)} WHERE job_id=? AND worker_id=? AND claim_token=?",
                [*params, job_id, worker_id, claim_token],
            )
            if cursor.rowcount != 1:
                raise PermissionError("Worker claim does not match this job.")
        return self.database.get_job(job_id)

    def renew_lease(self, job_id: str, worker_id: str) -> bool:
        expires_at = iso(coerce_utc() + timedelta(seconds=int(self.config.resource_lease_seconds)))
        with self.database.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE resource_leases
                SET expires_at=?
                WHERE job_id=?
                AND worker_id=?
                AND status=?
                """,
                (expires_at, job_id, worker_id, LEASE_ACTIVE),
            )
        return cursor.rowcount == 1

    def release_lease(self, job_id: str, worker_id: str) -> bool:
        released_at = utc_now()
        with self.database.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE resource_leases
                SET status=?, released_at=?
                WHERE job_id=?
                AND worker_id=?
                AND status=?
                """,
                (LEASE_RELEASED, released_at, job_id, worker_id, LEASE_ACTIVE),
            )
        return cursor.rowcount == 1

    def release_job_leases(self, job_id: str, *, status: str = LEASE_RELEASED) -> int:
        released_at = utc_now()
        with self.database.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE resource_leases
                SET status=?, released_at=?
                WHERE job_id=? AND status=?
                """,
                (status, released_at, job_id, LEASE_ACTIVE),
            )
        return int(cursor.rowcount or 0)

    def release_session_leases(self, session_id: str, *, status: str = LEASE_RELEASED) -> int:
        released_at = utc_now()
        with self.database.connect() as conn:
            rows = conn.execute("SELECT job_id FROM jobs WHERE session_id=?", (session_id,)).fetchall()
            job_ids = [str(row["job_id"]) for row in rows]
            if not job_ids:
                return 0
            cursor = conn.execute(
                "UPDATE resource_leases SET status=?, released_at=? WHERE status=? AND job_id IN ("
                + ", ".join("?" for _ in job_ids)
                + ")",
                [status, released_at, LEASE_ACTIVE, *job_ids],
            )
        return int(cursor.rowcount or 0)

    def list_active_leases(self) -> list[dict[str, Any]]:
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM resource_leases WHERE status=? ORDER BY acquired_at ASC",
                (LEASE_ACTIVE,),
            ).fetchall()
        return [dict(row) for row in rows]

    def request_cancel(self, session_id: str, job_id: str) -> JobRecord:
        now = utc_now()
        job = self.database.get_job(job_id, session_id=session_id)
        if job.status in {JobStatus.QUEUED.value, JobStatus.QUEUED_CPU.value, JobStatus.QUEUED_GPU.value, JobStatus.CREATED.value, JobStatus.VALIDATING.value}:
            return self.database.update_job(job_id, status=JobStatus.CANCELLED.value, cancel_requested_at=now, finished_at=now)
        if job.status in TERMINAL_STATUSES:
            return job
        return self.database.update_job(job_id, status=JobStatus.CANCEL_REQUESTED.value, cancel_requested_at=now)

    def mark_timed_out_jobs(self, now: datetime | str | None = None) -> list[str]:
        now_iso = iso(now)
        timed_out: list[str] = []
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM jobs
                WHERE status IN (?, ?, ?)
                AND timeout_at != ''
                AND timeout_at < ?
                """,
                (JobStatus.STARTING.value, JobStatus.RUNNING.value, JobStatus.POSTPROCESSING.value, now_iso),
            ).fetchall()
            for row in rows:
                validate_job_status_transition(str(row["status"]), JobStatus.TIMED_OUT.value)
                conn.execute(
                    "UPDATE jobs SET status=?, finished_at=?, error_code=? WHERE job_id=?",
                    (JobStatus.TIMED_OUT.value, now_iso, "TIMED_OUT", row["job_id"]),
                )
                conn.execute(
                    "UPDATE resource_leases SET status=?, released_at=? WHERE job_id=? AND status=?",
                    (LEASE_RELEASED, now_iso, row["job_id"], LEASE_ACTIVE),
                )
                timed_out.append(str(row["job_id"]))
        return timed_out

    def recover_expired_leases(self, now: datetime | str | None = None) -> list[str]:
        now_iso = iso(now)
        recovered: list[str] = []
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT job_id FROM resource_leases WHERE status=? AND expires_at < ?",
                (LEASE_ACTIVE, now_iso),
            ).fetchall()
            for row in rows:
                job_id = str(row["job_id"])
                conn.execute(
                    "UPDATE resource_leases SET status=?, released_at=? WHERE job_id=? AND status=?",
                    (LEASE_EXPIRED, now_iso, job_id, LEASE_ACTIVE),
                )
                job_row = conn.execute("SELECT status FROM jobs WHERE job_id=?", (job_id,)).fetchone()
                if job_row and str(job_row["status"]) in {JobStatus.STARTING.value, JobStatus.RUNNING.value, JobStatus.POSTPROCESSING.value}:
                    conn.execute(
                        "UPDATE jobs SET status=?, cancel_requested_at=?, error_code=? WHERE job_id=?",
                        (JobStatus.CANCEL_REQUESTED.value, now_iso, "LEASE_EXPIRED", job_id),
                    )
                recovered.append(job_id)
        return recovered

    def queue_status(self, session_id: str | None = None) -> dict[str, Any]:
        with self.database.connect() as conn:
            cpu_queue = int(conn.execute("SELECT COUNT(*) AS count FROM jobs WHERE status=?", (JobStatus.QUEUED_CPU.value,)).fetchone()["count"] or 0)
            gpu_queue = int(conn.execute("SELECT COUNT(*) AS count FROM jobs WHERE status=?", (JobStatus.QUEUED_GPU.value,)).fetchone()["count"] or 0)
            lab_gpu_0_queue = int(conn.execute("SELECT COUNT(*) AS count FROM jobs WHERE queue_name=? AND status=?", ("lab_gpu_0", JobStatus.QUEUED_GPU.value)).fetchone()["count"] or 0)
            lab_gpu_1_queue = int(conn.execute("SELECT COUNT(*) AS count FROM jobs WHERE queue_name=? AND status=?", ("lab_gpu_1", JobStatus.QUEUED_GPU.value)).fetchone()["count"] or 0)
            now_iso = utc_now()
            cpu_used = int(conn.execute("SELECT COUNT(*) AS count FROM resource_leases WHERE resource_type='cpu' AND status=? AND expires_at>?", (LEASE_ACTIVE, now_iso)).fetchone()["count"] or 0)
            gpu_used = int(conn.execute("SELECT COUNT(*) AS count FROM resource_leases WHERE resource_type='gpu' AND status=? AND expires_at>?", (LEASE_ACTIVE, now_iso)).fetchone()["count"] or 0)
        return {
            "cpu_queue_length": cpu_queue,
            "gpu_queue_length": gpu_queue,
            "lab_gpu_0_queue_length": lab_gpu_0_queue,
            "lab_gpu_1_queue_length": lab_gpu_1_queue,
            "cpu_slots_used": cpu_used,
            "gpu_slots_used": gpu_used,
            "cpu_concurrency": int(self.config.max_cpu_concurrency),
            "gpu_concurrency": int(self.config.max_gpu_concurrency),
            "system_state": self._system_state(cpu_queue=cpu_queue, gpu_queue=gpu_queue, cpu_used=cpu_used, gpu_used=gpu_used),
            "maintenance_mode": bool(self.config.maintenance_mode),
        }

    def get_job_queue_position(
        self,
        *,
        job_id: str,
        owner_session_id: str,
        analysis_session_id: str,
    ) -> dict[str, Any] | None:
        """Return a caller-authorized queued job's position in scheduler order.

        A position is only meaningful while a job is in a resource queue.  The
        query uses the scheduler's priority/created_at/job_id ordering and an
        exact owner plus tab-analysis scope; it deliberately never exposes
        information about the jobs ahead of the caller.
        """
        owner = str(owner_session_id or "").strip()
        analysis = str(analysis_session_id or "").strip()
        if not owner or not analysis or not str(job_id or "").strip():
            return None
        with self.database.connect() as conn:
            job = conn.execute(
                """
                SELECT job_id, status, queue_name, priority, created_at, resource_type
                FROM jobs
                WHERE job_id=? AND owner_session_id=? AND analysis_session_id=?
                """,
                (str(job_id), owner, analysis),
            ).fetchone()
            if job is None or str(job["status"] or "") not in QUEUED_RESOURCE_JOB_STATUSES:
                return None
            queue_name = str(job["queue_name"] or "").strip()
            if not queue_name:
                return None
            ahead = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM jobs
                WHERE status=? AND queue_name=?
                AND (
                    priority > ?
                    OR (priority = ? AND created_at < ?)
                    OR (priority = ? AND created_at = ? AND job_id < ?)
                )
                """,
                (
                    str(job["status"]),
                    queue_name,
                    int(job["priority"] or 0),
                    int(job["priority"] or 0),
                    str(job["created_at"] or ""),
                    int(job["priority"] or 0),
                    str(job["created_at"] or ""),
                    str(job["job_id"]),
                ),
            ).fetchone()
        jobs_ahead = int(ahead["count"] or 0) if ahead is not None else 0
        return {
            "job_id": str(job["job_id"]),
            "resource_type": str(job["resource_type"] or ""),
            "queue_name": queue_name,
            "queue_position": jobs_ahead + 1,
            "jobs_ahead": jobs_ahead,
        }

    def _system_state(self, *, cpu_queue: int, gpu_queue: int, cpu_used: int, gpu_used: int) -> str:
        if bool(self.config.maintenance_mode):
            return "MAINTENANCE"
        cpu_capacity = max(1, int(self.config.max_cpu_concurrency))
        gpu_capacity = max(1, int(self.config.max_gpu_concurrency))
        max_queue = max(1, int(self.config.max_cpu_queue_length) + int(self.config.max_gpu_queue_length))
        total_queue = int(cpu_queue) + int(gpu_queue)
        resources_full = int(cpu_used) >= cpu_capacity or int(gpu_used) >= gpu_capacity
        if total_queue >= max(1, int(max_queue * 0.8)):
            return "VERY_BUSY"
        if resources_full and total_queue > 0:
            return "BUSY"
        return "NORMAL"

    def _gpu_budget_available(self, conn, row, now: datetime) -> bool:
        budget = float(self.config.daily_gpu_budget_usd)
        if budget <= 0:
            return False
        usage_date = now.date().isoformat()
        usage = conn.execute(
            """
            SELECT estimated_cost_usd FROM daily_usage
            WHERE usage_date=? AND resource_type='gpu'
            """,
            (usage_date,),
        ).fetchone()
        used = float(usage["estimated_cost_usd"] or 0.0) if usage else 0.0
        return used + float(row["estimated_gpu_cost_usd"] or 0.0) <= budget

    def _record_gpu_start(self, conn, row, now: datetime) -> None:
        usage_date = now.date().isoformat()
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
            (usage_date, float(row["estimated_gpu_cost_usd"] or 0.0), iso(now)),
        )
