from __future__ import annotations

import hashlib
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone

from .config import SpaShinyCloudConfig
from .database import CloudDatabase


ACTION_TOO_FAST_MESSAGE = "操作过快，请稍后再试"


class ActionRateLimitExceeded(PermissionError):
    def __init__(self, *, retry_after: int, window_seconds: int) -> None:
        super().__init__(ACTION_TOO_FAST_MESSAGE)
        self.code = "ACTION_TOO_FAST"
        self.retry_after = max(1, int(retry_after))
        self.window_seconds = max(1, int(window_seconds))


class OwnerActionRateLimitExceeded(PermissionError):
    def __init__(self, *, retry_after: int, window_seconds: int) -> None:
        super().__init__("Too many job submissions for this account. Please wait before submitting another job.")
        self.code = "JOB_SUBMIT_RATE_LIMITED"
        self.retry_after = max(1, int(retry_after))
        self.window_seconds = max(1, int(window_seconds))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _clean_part(value: object) -> str:
    return str(value or "").strip()


@dataclass
class ActionRateLimiter:
    database: CloudDatabase
    config: SpaShinyCloudConfig | None = None
    window_seconds: int | None = None

    def __post_init__(self) -> None:
        if self.window_seconds is None:
            self.window_seconds = int(os.environ.get("SPASHINY_ACTION_RATE_LIMIT_SECONDS", "10") or "10")
        self.window_seconds = max(1, int(self.window_seconds))

    @property
    def owner_submit_limit(self) -> int:
        if self.config is not None:
            return max(0, int(self.config.job_submit_rate_limit_count))
        return max(0, int(os.environ.get("JOB_SUBMIT_RATE_LIMIT_COUNT", "20") or "20"))

    @property
    def owner_submit_window_seconds(self) -> int:
        if self.config is not None:
            return max(1, int(self.config.job_submit_rate_limit_window_seconds))
        return max(1, int(os.environ.get("JOB_SUBMIT_RATE_LIMIT_WINDOW_SECONDS", "600") or "600"))

    def check_and_record(
        self,
        *,
        owner_session_id: str,
        analysis_session_id: str,
        workflow_name: str,
        action_name: str,
    ) -> None:
        owner = _clean_part(owner_session_id)
        analysis = _clean_part(analysis_session_id)
        workflow = _clean_part(workflow_name)
        action = _clean_part(action_name)
        if not owner or not workflow or not action:
            return None

        now = _utc_now()
        now_iso = now.isoformat()
        key = self._key(owner, analysis, workflow, action)

        with self.database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                self._ensure_schema(conn)
                row = conn.execute(
                    "SELECT last_action_at FROM action_rate_limits WHERE rate_limit_key=?",
                    (key,),
                ).fetchone()
                last_at = _parse_datetime(row["last_action_at"]) if row is not None else None
                if last_at is not None:
                    elapsed = max(0.0, (now - last_at).total_seconds())
                    if elapsed < int(self.window_seconds):
                        retry_after = math.ceil(int(self.window_seconds) - elapsed)
                        raise ActionRateLimitExceeded(
                            retry_after=retry_after,
                            window_seconds=int(self.window_seconds),
                        )
                conn.execute(
                    """
                    INSERT INTO action_rate_limits(
                        rate_limit_key, owner_session_id, analysis_session_id,
                        workflow_name, action_name, last_action_at
                    ) VALUES(?, ?, ?, ?, ?, ?)
                    ON CONFLICT(rate_limit_key) DO UPDATE SET
                        owner_session_id=excluded.owner_session_id,
                        analysis_session_id=excluded.analysis_session_id,
                        workflow_name=excluded.workflow_name,
                        action_name=excluded.action_name,
                        last_action_at=excluded.last_action_at
                    """,
                    (key, owner, analysis, workflow, action, now_iso),
                )
                if action == "submit_job" and self.owner_submit_limit:
                    self._check_and_record_owner_submit_window(conn, owner=owner, now=now)
                conn.execute("COMMIT")
            except (ActionRateLimitExceeded, OwnerActionRateLimitExceeded):
                conn.execute("ROLLBACK")
                raise
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return None

    def check(
        self,
        *,
        owner_session_id: str,
        analysis_session_id: str,
        workflow_name: str,
        action_name: str,
    ) -> None:
        owner = _clean_part(owner_session_id)
        analysis = _clean_part(analysis_session_id)
        workflow = _clean_part(workflow_name)
        action = _clean_part(action_name)
        if not owner or not workflow or not action:
            return None

        now = _utc_now()
        key = self._key(owner, analysis, workflow, action)
        with self.database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                self._ensure_schema(conn)
                row = conn.execute(
                    "SELECT last_action_at FROM action_rate_limits WHERE rate_limit_key=?",
                    (key,),
                ).fetchone()
                last_at = _parse_datetime(row["last_action_at"]) if row is not None else None
                if last_at is not None:
                    elapsed = max(0.0, (now - last_at).total_seconds())
                    if elapsed < int(self.window_seconds):
                        retry_after = math.ceil(int(self.window_seconds) - elapsed)
                        raise ActionRateLimitExceeded(
                            retry_after=retry_after,
                            window_seconds=int(self.window_seconds),
                        )
                conn.execute("COMMIT")
            except ActionRateLimitExceeded:
                conn.execute("ROLLBACK")
                raise
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return None

    @staticmethod
    def _key(owner: str, analysis: str, workflow: str, action: str) -> str:
        payload = "\x1f".join([owner, analysis, workflow, action]).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def _check_and_record_owner_submit_window(self, conn, *, owner: str, now: datetime) -> None:
        """Bound submissions across all tabs for one owner, atomically."""
        self._ensure_owner_schema(conn)
        window_seconds = self.owner_submit_window_seconds
        limit = self.owner_submit_limit
        key = hashlib.sha256((owner + "\x1fsubmit_job").encode("utf-8")).hexdigest()
        row = conn.execute(
            "SELECT window_started_at, action_count FROM owner_action_rate_limits WHERE rate_limit_key=?",
            (key,),
        ).fetchone()
        started_at = _parse_datetime(row["window_started_at"]) if row is not None else None
        count = int(row["action_count"] or 0) if row is not None else 0
        if started_at is None or (now - started_at).total_seconds() >= window_seconds:
            started_at = now
            count = 0
        if count >= limit:
            retry_after = max(1, math.ceil(window_seconds - max(0.0, (now - started_at).total_seconds())))
            raise OwnerActionRateLimitExceeded(retry_after=retry_after, window_seconds=window_seconds)
        conn.execute(
            """
            INSERT INTO owner_action_rate_limits(
                rate_limit_key, owner_session_id, action_name,
                window_started_at, action_count, updated_at
            ) VALUES(?, ?, 'submit_job', ?, 1, ?)
            ON CONFLICT(rate_limit_key) DO UPDATE SET
                owner_session_id=excluded.owner_session_id,
                action_count=owner_action_rate_limits.action_count + 1,
                updated_at=excluded.updated_at
            """,
            (key, owner, started_at.isoformat(), now.isoformat()),
        )

    @staticmethod
    def _ensure_schema(conn) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS action_rate_limits (
                rate_limit_key TEXT PRIMARY KEY,
                owner_session_id TEXT NOT NULL,
                analysis_session_id TEXT NOT NULL DEFAULT '',
                workflow_name TEXT NOT NULL DEFAULT '',
                action_name TEXT NOT NULL DEFAULT '',
                last_action_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_action_rate_limits_owner "
            "ON action_rate_limits(owner_session_id, analysis_session_id, workflow_name, action_name)"
        )

    @staticmethod
    def _ensure_owner_schema(conn) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS owner_action_rate_limits (
                rate_limit_key TEXT PRIMARY KEY,
                owner_session_id TEXT NOT NULL,
                action_name TEXT NOT NULL,
                window_started_at TEXT NOT NULL,
                action_count INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
