from __future__ import annotations

import hmac
import json
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import SpaShinyCloudConfig, load_cloud_config
from .database import CloudDatabase
from .models import JobRecord, SessionStatus, row_to_job


class SessionAuthError(PermissionError):
    """Raised when a session token cannot be authenticated."""


class SessionExpiredError(PermissionError):
    """Raised when a valid session token belongs to an expired session."""


@dataclass(frozen=True)
class SessionRecord:
    id: int
    session_id: str
    anonymous_workspace_id: str
    token_hash: str
    status: str
    created_at: str
    last_heartbeat_at: str
    disconnected_at: str | None = None
    expires_at: str | None = None
    abandoned_at: str | None = None
    cleaned_at: str | None = None
    total_upload_bytes: int = 0
    active_job_id: str | None = None
    metadata_json: str | None = None

    def public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("id", None)
        data.pop("token_hash", None)
        return data


@dataclass(frozen=True)
class CreatedSession:
    session: SessionRecord
    session_token: str

    @property
    def session_id(self) -> str:
        return self.session.session_id


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def coerce_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def row_to_session(row: Any) -> SessionRecord:
    if row is None:
        raise KeyError("Session row is empty.")
    return SessionRecord(
        id=int(row["id"]),
        session_id=str(row["session_id"]),
        anonymous_workspace_id=str(row["anonymous_workspace_id"] or row["session_id"]),
        token_hash=str(row["token_hash"]),
        status=str(row["status"]),
        created_at=str(row["created_at"]),
        last_heartbeat_at=str(row["last_heartbeat_at"]),
        disconnected_at=row["disconnected_at"],
        expires_at=row["expires_at"],
        abandoned_at=row["abandoned_at"],
        cleaned_at=row["cleaned_at"],
        total_upload_bytes=int(row["total_upload_bytes"] or 0),
        active_job_id=row["active_job_id"],
        metadata_json=row["metadata_json"],
    )


class SessionManager:
    def __init__(
        self,
        database: CloudDatabase | None = None,
        config: SpaShinyCloudConfig | None = None,
        *,
        hmac_secret: str | None = None,
    ) -> None:
        self.config = config or load_cloud_config()
        self.database = database or CloudDatabase(config=self.config)
        self.hmac_secret = hmac_secret if hmac_secret is not None else self.config.require_session_hmac_secret()
        self.idle_timeout_seconds = int(self.config.session_idle_timeout_seconds)

    def _token_hash(self, token: str) -> str:
        return hmac.new(
            self.hmac_secret.encode("utf-8"),
            str(token).encode("utf-8"),
            "sha256",
        ).hexdigest()

    def create_session(self, metadata: dict[str, Any] | None = None) -> CreatedSession:
        token = secrets.token_urlsafe(32)
        session_id = "sess_" + secrets.token_hex(24)
        anonymous_workspace_id = "labws_" + secrets.token_hex(8)
        now = utc_now()
        expires_at = now + timedelta(seconds=self.idle_timeout_seconds)
        token_hash = self._token_hash(token)
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True)
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions(
                    session_id,
                    anonymous_workspace_id,
                    token_hash,
                    status,
                    created_at,
                    last_heartbeat_at,
                    expires_at,
                    total_upload_bytes,
                    metadata_json
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    session_id,
                    anonymous_workspace_id,
                    token_hash,
                    SessionStatus.ACTIVE.value,
                    isoformat(now),
                    isoformat(now),
                    isoformat(expires_at),
                    metadata_json,
                ),
            )
        return CreatedSession(session=self.get_session_by_token(token), session_token=token)

    def authenticate(self, token: str) -> SessionRecord:
        if not token:
            raise SessionAuthError("Invalid session.")
        token_hash = self._token_hash(token)
        with self.database.connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE token_hash=?", (token_hash,)).fetchone()
        if row is None or not hmac.compare_digest(str(row["token_hash"]), token_hash):
            raise SessionAuthError("Invalid session.")
        return row_to_session(row)

    def get_session_by_token(self, token: str) -> SessionRecord:
        return self.authenticate(token)

    def get_session(self, session_id: str) -> SessionRecord:
        with self.database.connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        if row is None:
            raise KeyError("Session was not found.")
        return row_to_session(row)

    def heartbeat(self, token: str) -> SessionRecord:
        session = self.authenticate(token)
        if session.status in {
            SessionStatus.ABANDONED.value,
            SessionStatus.CLEANING.value,
            SessionStatus.CLEANED.value,
        }:
            raise SessionExpiredError("Session has expired.")
        now = utc_now()
        expires_at = now + timedelta(seconds=self.idle_timeout_seconds)
        with self.database.connect() as conn:
            conn.execute(
                """
                UPDATE sessions
                SET status=?,
                    last_heartbeat_at=?,
                    expires_at=?,
                    disconnected_at=NULL
                WHERE session_id=?
                AND status IN (?, ?)
                """,
                (
                    SessionStatus.ACTIVE.value,
                    isoformat(now),
                    isoformat(expires_at),
                    session.session_id,
                    SessionStatus.ACTIVE.value,
                    SessionStatus.DISCONNECTED.value,
                ),
            )
        return self.get_session(session.session_id)

    def mark_disconnected(self, token: str) -> SessionRecord:
        session = self.authenticate(token)
        if session.status == SessionStatus.ACTIVE.value:
            now = isoformat(utc_now())
            with self.database.connect() as conn:
                conn.execute(
                    """
                    UPDATE sessions
                    SET status=?, disconnected_at=?
                    WHERE session_id=? AND status=?
                    """,
                    (
                        SessionStatus.DISCONNECTED.value,
                        now,
                        session.session_id,
                        SessionStatus.ACTIVE.value,
                    ),
                )
        return self.get_session(session.session_id)

    def abandon(self, token: str, reason: str = "user_end") -> SessionRecord:
        session = self.authenticate(token)
        now = isoformat(utc_now())
        metadata = self._metadata_with_reason(session, reason)
        with self.database.connect() as conn:
            conn.execute(
                """
                UPDATE sessions
                SET status=?,
                    abandoned_at=?,
                    metadata_json=?
                WHERE session_id=?
                AND status IN (?, ?)
                """,
                (
                    SessionStatus.ABANDONED.value,
                    now,
                    metadata,
                    session.session_id,
                    SessionStatus.ACTIVE.value,
                    SessionStatus.DISCONNECTED.value,
                ),
            )
        return self.get_session(session.session_id)

    def find_expired_sessions(self, cutoff: datetime | str) -> list[SessionRecord]:
        cutoff_iso = isoformat(coerce_datetime(cutoff))
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM sessions
                WHERE status IN (?, ?)
                AND last_heartbeat_at < ?
                ORDER BY last_heartbeat_at ASC
                """,
                (SessionStatus.ACTIVE.value, SessionStatus.DISCONNECTED.value, cutoff_iso),
            ).fetchall()
        return [row_to_session(row) for row in rows]

    def mark_abandoned_if_expired(self, session_id: str, cutoff: datetime | str) -> SessionRecord | None:
        cutoff_iso = isoformat(coerce_datetime(cutoff))
        now_iso = isoformat(utc_now())
        with self.database.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE sessions
                SET status=?, abandoned_at=?
                WHERE session_id=?
                AND status IN (?, ?)
                AND last_heartbeat_at < ?
                """,
                (
                    SessionStatus.ABANDONED.value,
                    now_iso,
                    session_id,
                    SessionStatus.ACTIVE.value,
                    SessionStatus.DISCONNECTED.value,
                    cutoff_iso,
                ),
            )
            if cursor.rowcount != 1:
                return None
        return self.get_session(session_id)

    def mark_cleaning(self, session_id: str) -> SessionRecord:
        session = self.get_session(session_id)
        if session.status == SessionStatus.CLEANED.value:
            return session
        with self.database.connect() as conn:
            conn.execute(
                """
                UPDATE sessions
                SET status=?
                WHERE session_id=?
                AND status IN (?, ?)
                """,
                (
                    SessionStatus.CLEANING.value,
                    session_id,
                    SessionStatus.ABANDONED.value,
                    SessionStatus.CLEANING.value,
                ),
            )
            row = conn.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        updated = row_to_session(row)
        if updated.status == SessionStatus.ABANDONED.value:
            # Keep ABANDONED stable if the state machine rejected the transition.
            return updated
        return self.get_session(session_id)

    def mark_cleaned(self, session_id: str) -> SessionRecord:
        session = self.get_session(session_id)
        if session.status == SessionStatus.CLEANED.value:
            return session
        now_iso = isoformat(utc_now())
        with self.database.connect() as conn:
            conn.execute(
                """
                UPDATE sessions
                SET status=?, cleaned_at=?
                WHERE session_id=?
                AND status IN (?, ?)
                """,
                (
                    SessionStatus.CLEANED.value,
                    now_iso,
                    session_id,
                    SessionStatus.CLEANING.value,
                    SessionStatus.CLEANED.value,
                ),
            )
        return self.get_session(session_id)

    def assert_job_owner(self, token: str, job_id: str) -> JobRecord:
        session = self.authenticate(token)
        if session.status in {SessionStatus.ABANDONED.value, SessionStatus.CLEANING.value, SessionStatus.CLEANED.value}:
            raise SessionExpiredError("Session has expired.")
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE job_id=? AND session_id=?",
                (job_id, session.session_id),
            ).fetchone()
        if row is None:
            raise PermissionError("Job was not found.")
        return row_to_job(row)

    def _metadata_with_reason(self, session: SessionRecord, reason: str) -> str:
        try:
            metadata = json.loads(session.metadata_json or "{}")
            if not isinstance(metadata, dict):
                metadata = {}
        except Exception:
            metadata = {}
        metadata["abandon_reason"] = str(reason or "unspecified")[:80]
        return json.dumps(metadata, ensure_ascii=False, sort_keys=True)
