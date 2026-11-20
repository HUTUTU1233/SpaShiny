from __future__ import annotations

import hashlib
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone

from .database import CloudDatabase


ACTION_TOO_FAST_MESSAGE = "操作过快，请稍后再试"


class ActionRateLimitExceeded(PermissionError):
    def __init__(self, *, retry_after: int, window_seconds: int) -> None:
        super().__init__(ACTION_TOO_FAST_MESSAGE)
        self.code = "ACTION_TOO_FAST"
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
    window_seconds: int | None = None

    def __post_init__(self) -> None:
        if self.window_seconds is None:
            self.window_seconds = int(os.environ.get("SPASHINY_ACTION_RATE_LIMIT_SECONDS", "10") or "10")
        self.window_seconds = max(1, int(self.window_seconds))

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
                        conn.execute("ROLLBACK")
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
                conn.execute("COMMIT")
            except ActionRateLimitExceeded:
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
                        conn.execute("ROLLBACK")
                        raise ActionRateLimitExceeded(
                            retry_after=retry_after,
                            window_seconds=int(self.window_seconds),
                        )
                conn.execute("COMMIT")
            except ActionRateLimitExceeded:
                raise
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return None

    @staticmethod
    def _key(owner: str, analysis: str, workflow: str, action: str) -> str:
        payload = "\x1f".join([owner, analysis, workflow, action]).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

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
