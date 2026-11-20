from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from .database import CloudDatabase
from .models import ACTIVE_JOB_STATUSES


class BrowserLifecycleRegistry:
    """Persistent browser-page lifecycle state, deliberately separate from jobs."""

    def __init__(self, database: CloudDatabase, *, grace_seconds: int = 30, heartbeat_lease_seconds: int = 90) -> None:
        self.database = database
        self.grace_seconds = max(1, int(grace_seconds))
        self.heartbeat_lease_seconds = max(self.grace_seconds, int(heartbeat_lease_seconds))
        self._ensure_tables()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _text(value: Any, *, limit: int = 512) -> str:
        return str(value or "").strip()[:limit]

    def _ensure_tables(self) -> None:
        with self.database.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS browser_lifecycle_connections (
                    page_instance_id TEXT PRIMARY KEY,
                    owner_session_id TEXT NOT NULL,
                    analysis_session_id TEXT NOT NULL DEFAULT '',
                    browser_client_id TEXT NOT NULL DEFAULT '',
                    tab_instance_id TEXT NOT NULL DEFAULT '',
                    workflow_id TEXT NOT NULL DEFAULT '',
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    pending_until TEXT,
                    disconnected_at TEXT,
                    last_event_type TEXT NOT NULL DEFAULT '',
                    last_reason TEXT NOT NULL DEFAULT '',
                    last_persisted INTEGER,
                    last_visibility_state TEXT NOT NULL DEFAULT '',
                    last_navigation_type TEXT NOT NULL DEFAULT ''
                )
                """
            )
            columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(browser_lifecycle_connections)").fetchall()}
            if "tab_instance_id" not in columns:
                conn.execute("ALTER TABLE browser_lifecycle_connections ADD COLUMN tab_instance_id TEXT NOT NULL DEFAULT ''")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_browser_lifecycle_pending "
                "ON browser_lifecycle_connections(state, pending_until)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_browser_lifecycle_owner_analysis_tab "
                "ON browser_lifecycle_connections(owner_session_id, analysis_session_id, tab_instance_id, state)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_browser_lifecycle_owner_analysis "
                "ON browser_lifecycle_connections(owner_session_id, analysis_session_id, browser_client_id, state)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS browser_lifecycle_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    server_timestamp TEXT NOT NULL,
                    owner_session_id TEXT NOT NULL,
                    analysis_session_id TEXT NOT NULL DEFAULT '',
                    browser_client_id TEXT NOT NULL DEFAULT '',
                    tab_instance_id TEXT NOT NULL DEFAULT '',
                    page_instance_id TEXT NOT NULL DEFAULT '',
                    workflow_id TEXT NOT NULL DEFAULT '',
                    event_type TEXT NOT NULL,
                    old_state TEXT NOT NULL DEFAULT '',
                    new_state TEXT NOT NULL DEFAULT '',
                    reason TEXT NOT NULL DEFAULT '',
                    persisted INTEGER,
                    visibility_state TEXT NOT NULL DEFAULT '',
                    navigation_type TEXT NOT NULL DEFAULT '',
                    client_timestamp TEXT NOT NULL DEFAULT '',
                    active_job_count INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            event_columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(browser_lifecycle_events)").fetchall()}
            if "tab_instance_id" not in event_columns:
                conn.execute("ALTER TABLE browser_lifecycle_events ADD COLUMN tab_instance_id TEXT NOT NULL DEFAULT ''")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_browser_lifecycle_events_owner_time "
                "ON browser_lifecycle_events(owner_session_id, analysis_session_id, event_id DESC)"
            )

    def _active_job_count(self, conn, owner_session_id: str, analysis_session_id: str) -> int:
        statuses = sorted(str(value) for value in ACTIVE_JOB_STATUSES)
        query = (
            "SELECT COUNT(*) AS count FROM jobs "
            "WHERE owner_session_id=? AND analysis_session_id=? "
            "AND status IN (" + ", ".join("?" for _ in statuses) + ")"
        )
        row = conn.execute(query, [owner_session_id, analysis_session_id, *statuses]).fetchone()
        return int(row["count"] if row is not None else 0)

    def _event(self, conn, *, owner_session_id: str, analysis_session_id: str,
               browser_client_id: str, tab_instance_id: str, page_instance_id: str, workflow_id: str,
               event_type: str, old_state: str = "", new_state: str = "",
               reason: str = "", persisted: bool | None = None,
               visibility_state: str = "", navigation_type: str = "",
               client_timestamp: str = "", metadata: dict[str, Any] | None = None) -> None:
        conn.execute(
            """
            INSERT INTO browser_lifecycle_events(
                server_timestamp, owner_session_id, analysis_session_id,
                browser_client_id, tab_instance_id, page_instance_id, workflow_id, event_type,
                old_state, new_state, reason, persisted, visibility_state,
                navigation_type, client_timestamp, active_job_count, metadata_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self._now(), owner_session_id, analysis_session_id,
                browser_client_id, tab_instance_id, page_instance_id, workflow_id, event_type,
                old_state, new_state, reason,
                None if persisted is None else int(bool(persisted)),
                visibility_state, navigation_type, client_timestamp,
                self._active_job_count(conn, owner_session_id, analysis_session_id),
                json.dumps(metadata or {}, ensure_ascii=True, sort_keys=True),
            ),
        )

    def record_event(self, **context: Any) -> None:
        context = self._context(**context)
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT state FROM browser_lifecycle_connections WHERE page_instance_id=?",
                (context["page_instance_id"],),
            ).fetchone() if context["page_instance_id"] else None
            state = str(row["state"]) if row is not None else ""
            self._event(conn, old_state=state, new_state=state, **context)

    def connect(self, **context: Any) -> dict[str, Any]:
        context = self._context(**context, require_page_instance=True, require_tab_instance=True)
        now = self._now()
        with self.database.connect() as conn:
            analysis = conn.execute(
                "SELECT status FROM analysis_sessions WHERE analysis_session_id=? AND owner_session_id=?",
                (context["analysis_session_id"], context["owner_session_id"]),
            ).fetchone()
            if analysis is None or str(analysis["status"]) != "ACTIVE":
                raise ValueError("analysis session is not active")
            current = conn.execute(
                "SELECT state FROM browser_lifecycle_connections WHERE page_instance_id=?",
                (context["page_instance_id"],),
            ).fetchone()
            old_state = str(current["state"]) if current is not None else ""
            recovered_others = conn.execute(
                """
                UPDATE browser_lifecycle_connections
                SET state='RECONNECTED', updated_at=?, pending_until=NULL,
                    last_event_type=?, last_reason=?, last_persisted=?,
                    last_visibility_state=?, last_navigation_type=?
                WHERE owner_session_id=? AND analysis_session_id=? AND tab_instance_id=?
                  AND state='DISCONNECT_PENDING' AND page_instance_id<>?
                """,
                (
                    now, context["event_type"], context["reason"],
                    None if context["persisted"] is None else int(bool(context["persisted"])),
                    context["visibility_state"], context["navigation_type"],
                    context["owner_session_id"], context["analysis_session_id"],
                    context["tab_instance_id"], context["page_instance_id"],
                ),
            ).rowcount
            conn.execute(
                """
                INSERT INTO browser_lifecycle_connections(
                    page_instance_id, owner_session_id, analysis_session_id,
                    browser_client_id, tab_instance_id, workflow_id, state, created_at, updated_at,
                    pending_until, disconnected_at, last_event_type, last_reason,
                    last_persisted, last_visibility_state, last_navigation_type
                ) VALUES(?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, NULL, NULL, ?, ?, ?, ?, ?)
                ON CONFLICT(page_instance_id) DO UPDATE SET
                    owner_session_id=excluded.owner_session_id,
                    analysis_session_id=excluded.analysis_session_id,
                    browser_client_id=excluded.browser_client_id,
                    tab_instance_id=excluded.tab_instance_id,
                    workflow_id=excluded.workflow_id,
                    state='ACTIVE', updated_at=excluded.updated_at,
                    pending_until=NULL, disconnected_at=NULL,
                    last_event_type=excluded.last_event_type,
                    last_reason=excluded.last_reason,
                    last_persisted=excluded.last_persisted,
                    last_visibility_state=excluded.last_visibility_state,
                    last_navigation_type=excluded.last_navigation_type
                """,
                (
                    context["page_instance_id"], context["owner_session_id"],
                    context["analysis_session_id"], context["browser_client_id"],
                    context["tab_instance_id"], context["workflow_id"], now, now, context["event_type"],
                    context["reason"],
                    None if context["persisted"] is None else int(bool(context["persisted"])),
                    context["visibility_state"], context["navigation_type"],
                ),
            )
            recovered = old_state == "DISCONNECT_PENDING" or bool(recovered_others)
            self._event(conn, old_state=old_state, new_state="ACTIVE",
                        metadata={"recovered_pending_connection": recovered}, **context)
            if recovered:
                self._event(
                    conn, old_state="DISCONNECT_PENDING", new_state="ACTIVE",
                    event_type="RECONNECT_WITHIN_GRACE", reason="reconnect",
                    metadata={"recovered_pending_connection_count": int(recovered_others) + int(old_state == "DISCONNECT_PENDING")},
                    **{key: value for key, value in context.items() if key not in {"event_type", "reason"}},
                )
        return {"state": "ACTIVE", "recovered_pending_connection": recovered, "grace_seconds": self.grace_seconds}

    def disconnect_pending(self, **context: Any) -> dict[str, Any]:
        context = self._context(**context, require_page_instance=True, require_tab_instance=True)
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat()
        pending_until = (now_dt + timedelta(seconds=self.grace_seconds)).isoformat()
        with self.database.connect() as conn:
            current = conn.execute(
                "SELECT state FROM browser_lifecycle_connections WHERE page_instance_id=?",
                (context["page_instance_id"],),
            ).fetchone()
            old_state = str(current["state"]) if current is not None else ""
            conn.execute(
                """
                INSERT INTO browser_lifecycle_connections(
                    page_instance_id, owner_session_id, analysis_session_id,
                    browser_client_id, tab_instance_id, workflow_id, state, created_at, updated_at,
                    pending_until, disconnected_at, last_event_type, last_reason,
                    last_persisted, last_visibility_state, last_navigation_type
                ) VALUES(?, ?, ?, ?, ?, ?, 'DISCONNECT_PENDING', ?, ?, ?, NULL, ?, ?, ?, ?, ?)
                ON CONFLICT(page_instance_id) DO UPDATE SET
                    owner_session_id=excluded.owner_session_id,
                    analysis_session_id=excluded.analysis_session_id,
                    browser_client_id=excluded.browser_client_id,
                    tab_instance_id=excluded.tab_instance_id,
                    workflow_id=excluded.workflow_id,
                    state='DISCONNECT_PENDING', updated_at=excluded.updated_at,
                    pending_until=excluded.pending_until, disconnected_at=NULL,
                    last_event_type=excluded.last_event_type,
                    last_reason=excluded.last_reason,
                    last_persisted=excluded.last_persisted,
                    last_visibility_state=excluded.last_visibility_state,
                    last_navigation_type=excluded.last_navigation_type
                """,
                (
                    context["page_instance_id"], context["owner_session_id"],
                    context["analysis_session_id"], context["browser_client_id"],
                    context["tab_instance_id"], context["workflow_id"], now, now, pending_until,
                    context["event_type"], context["reason"],
                    None if context["persisted"] is None else int(bool(context["persisted"])),
                    context["visibility_state"], context["navigation_type"],
                ),
            )
            self._event(
                conn, old_state=old_state, new_state="DISCONNECT_PENDING",
                event_type="DISCONNECT_PENDING", reason=context["reason"],
                metadata={"source_event_type": context["event_type"], "pending_until": pending_until},
                **{key: value for key, value in context.items() if key not in {"event_type", "reason"}},
            )
        return {"state": "DISCONNECT_PENDING", "pending_until": pending_until, "grace_seconds": self.grace_seconds}

    def _end_if_orphaned(self, conn, row, *, now: str, reason: str) -> dict[str, str] | None:
        owner = str(row["owner_session_id"]); analysis = str(row["analysis_session_id"]); tab = str(row["tab_instance_id"] or "")
        live = conn.execute("SELECT 1 FROM browser_lifecycle_connections WHERE owner_session_id=? AND analysis_session_id=? AND tab_instance_id=? AND (state='ACTIVE' OR (state='DISCONNECT_PENDING' AND pending_until > ?)) LIMIT 1", (owner, analysis, tab, now)).fetchone()
        if live is not None:
            return None
        changed = conn.execute("UPDATE analysis_sessions SET status='ENDED', updated_at=? WHERE analysis_session_id=? AND owner_session_id=? AND status='ACTIVE'", (now, analysis, owner)).rowcount
        if not changed:
            return None
        self._event(conn, owner_session_id=owner, analysis_session_id=analysis, browser_client_id=str(row["browser_client_id"] or ""), tab_instance_id=tab, page_instance_id=str(row["page_instance_id"] or ""), workflow_id=str(row["workflow_id"] or ""), event_type="ANALYSIS_ENDED", old_state="DISCONNECTED", new_state="ENDED", reason=reason, metadata={"analysis_scope": analysis})
        return {"owner_session_id": owner, "analysis_session_id": analysis}

    def _expire(self, *, state: str, cutoff: str, reason: str, event_type: str) -> list[dict[str, str]]:
        now = self._now(); column = "pending_until" if state == "DISCONNECT_PENDING" else "updated_at"; ended: list[dict[str, str]] = []
        with self.database.connect() as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(f"SELECT * FROM browser_lifecycle_connections WHERE state=? AND {column} IS NOT NULL AND {column} <= ?", (state, cutoff)).fetchall()
            for row in rows:
                if state == "ACTIVE":
                    # Missed heartbeats are not permission to cancel running
                    # work. Explicit page-close grace is intentionally separate.
                    from .analysis_idle_policy import scoped_work, _seconds
                    work = scoped_work(conn, str(row["owner_session_id"]),
                                       str(row["analysis_session_id"]), self.database.config)
                    if work["active"] or work["last_finished_at"] > _seconds(cutoff):
                        continue
                changed = conn.execute(f"UPDATE browser_lifecycle_connections SET state='DISCONNECTED', updated_at=?, disconnected_at=?, pending_until=NULL, last_event_type=?, last_reason=? WHERE page_instance_id=? AND state=? AND {column} IS NOT NULL AND {column} <= ?", (now, now, event_type, reason, row["page_instance_id"], state, cutoff)).rowcount
                if not changed:
                    continue
                self._event(conn, owner_session_id=str(row["owner_session_id"]), analysis_session_id=str(row["analysis_session_id"]), browser_client_id=str(row["browser_client_id"] or ""), tab_instance_id=str(row["tab_instance_id"] or ""), page_instance_id=str(row["page_instance_id"]), workflow_id=str(row["workflow_id"] or ""), event_type=event_type, old_state=state, new_state="DISCONNECTED", reason=reason)
                scope = self._end_if_orphaned(conn, row, now=now, reason=reason)
                if scope is not None:
                    ended.append(scope)
        return ended

    def expire_pending(self) -> list[dict[str, str]]:
        return self._expire(state="DISCONNECT_PENDING", cutoff=self._now(), reason="grace_expired", event_type="DISCONNECT_GRACE_EXPIRED")

    def expire_heartbeat_leases(self) -> list[dict[str, str]]:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=self.heartbeat_lease_seconds)).isoformat()
        return self._expire(state="ACTIVE", cutoff=cutoff, reason="heartbeat_lease_expired", event_type="HEARTBEAT_LEASE_EXPIRED")

    def heartbeat(self, **context: Any) -> bool:
        context = self._context(**context, require_page_instance=True, require_tab_instance=True)
        now = self._now()
        with self.database.connect() as conn:
            changed = conn.execute("UPDATE browser_lifecycle_connections SET state='ACTIVE', updated_at=?, pending_until=NULL, disconnected_at=NULL, last_event_type=?, last_reason=? WHERE page_instance_id=? AND owner_session_id=? AND analysis_session_id=? AND tab_instance_id=? AND state IN ('ACTIVE', 'DISCONNECT_PENDING')", (now, context["event_type"], context["reason"], context["page_instance_id"], context["owner_session_id"], context["analysis_session_id"], context["tab_instance_id"])).rowcount
            if changed:
                self._event(conn, old_state="ACTIVE", new_state="ACTIVE", **context)
        return bool(changed)

    def events(self, *, owner_session_id: str, analysis_session_id: str = "", limit: int = 100) -> list[dict[str, Any]]:
        query = "SELECT * FROM browser_lifecycle_events WHERE owner_session_id=?"
        params: list[Any] = [self._text(owner_session_id)]
        if analysis_session_id:
            query += " AND analysis_session_id=?"
            params.append(self._text(analysis_session_id))
        query += " ORDER BY event_id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 200)))
        with self.database.connect() as conn:
            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def _context(self, *, owner_session_id: str, analysis_session_id: str = "",
                 browser_client_id: str = "", tab_instance_id: str = "", page_instance_id: str = "",
                 workflow_id: str = "", event_type: str = "LIFECYCLE_EVENT",
                 reason: str = "", persisted: bool | None = None,
                 visibility_state: str = "", navigation_type: str = "",
                 client_timestamp: str = "", require_page_instance: bool = False, require_tab_instance: bool = False,
                 **_ignored: Any) -> dict[str, Any]:
        owner = self._text(owner_session_id)
        analysis = self._text(analysis_session_id)
        page = self._text(page_instance_id)
        tab = self._text(tab_instance_id)
        if not owner:
            raise ValueError("owner_session_id is required")
        if not analysis:
            raise ValueError("analysis_session_id is required")
        if require_page_instance and not page:
            raise ValueError("page_instance_id is required")
        if require_tab_instance and not tab:
            raise ValueError("tab_instance_id is required")
        return {
            "owner_session_id": owner,
            "analysis_session_id": analysis,
            "browser_client_id": self._text(browser_client_id),
            "tab_instance_id": tab,
            "page_instance_id": page,
            "workflow_id": self._text(workflow_id),
            "event_type": self._text(event_type, limit=128) or "LIFECYCLE_EVENT",
            "reason": self._text(reason, limit=128),
            "persisted": persisted,
            "visibility_state": self._text(visibility_state, limit=64),
            "navigation_type": self._text(navigation_type, limit=64),
            "client_timestamp": self._text(client_timestamp, limit=128),
        }

