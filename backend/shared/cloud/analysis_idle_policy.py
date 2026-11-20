"""Analysis-scoped inactivity policy; never cancel work or change scientific data."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from .models import ACTIVE_JOB_STATUSES

POLICY_KEY = "spashiny_idle_policy_v1"
IDLE_REASON = "idle_timeout_no_work"


def _seconds(value):
    if not value:
        return 0.0
    try:
        when = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return when.replace(tzinfo=when.tzinfo or timezone.utc).timestamp()
    except (ValueError, TypeError, OverflowError):
        return 0.0


def scoped_work(conn, owner, analysis, config):
    """Use exact owner/analysis; queued, packaging and cancellation are busy too."""
    statuses = sorted(ACTIVE_JOB_STATUSES)
    placeholders = ",".join("?" for _ in statuses)
    count = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE owner_session_id=? AND analysis_session_id=? "
        f"AND status IN ({placeholders})", (owner, analysis, *statuses),
    ).fetchone()[0]
    uploads = conn.execute(
        "SELECT COUNT(*) FROM uploads WHERE session_id=? AND analysis_session_id=? "
        "AND status IN ('INITIATED','UPLOADING','COMPLETING')", (owner, analysis),
    ).fetchone()[0]
    finished = conn.execute(
        "SELECT MAX(finished_at) FROM jobs WHERE owner_session_id=? AND analysis_session_id=?",
        (owner, analysis),
    ).fetchone()[0]
    completed = conn.execute(
        "SELECT MAX(completed_at) FROM uploads WHERE session_id=? AND analysis_session_id=?",
        (owner, analysis),
    ).fetchone()[0]
    latest = max(_seconds(finished), _seconds(completed))
    alignment = 0
    # Alignment is a separate file-backed queue, not necessarily a jobs row.
    # Never include another analysis's task or follow a symlink outside root.
    root = Path(config.lab_jobs_root).resolve()
    for job_path in root.glob("alignment_*/job.json"):
        if not job_path.resolve().is_relative_to(root):
            continue
        try:
            job = json.loads(job_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(job, dict) or str(job.get("owner_id") or "") != owner or str(job.get("analysis_session_id") or "") != analysis:
            continue
        path = job_path.with_name("status.json")
        # The queue writes status in-place. A temporarily missing/partial
        # status must protect this proven scope, not expire its active work.
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(state, dict):
                raise ValueError("invalid alignment status")
        except (OSError, ValueError):
            alignment += 1
            continue
        status = str(state.get("status") or "").lower()
        if status in {"queued", "pending", "running", "starting", "packaging", "postprocessing", "cancelling", "cleaning_up"}:
            alignment += 1
        else:
            latest = max(latest, _seconds(state.get("finished_at")))
    return {"active": bool(count or uploads or alignment), "jobs": int(count),
            "uploads": int(uploads), "alignment": alignment, "last_finished_at": latest}


def evaluate_idle(registry, context, *, idle_seconds, client_busy=False, now=None):
    """Atomic no-work check + existing lifecycle state transition, no schema change.

    Older clients missing activity telemetry are not forcibly expired. Browser
    telemetry can only extend this resource policy, never grant authorization.
    The API authenticates owner and exact active analysis before this function.
    """
    timeout = int(registry.database.config.session_idle_timeout_seconds)
    response = {"timeout_seconds": timeout, "expired": False, "active_work": False,
                "analysis_session_id": context["analysis_session_id"]}
    if idle_seconds is None:
        response["activity_known"] = False
        return response
    current = now or datetime.now(timezone.utc)
    timestamp = current.timestamp()
    owner, analysis = context["owner_session_id"], context["analysis_session_id"]
    # CloudDatabase connections use autocommit. This explicit transaction
    # therefore also needs sqlite3's context manager to commit or roll back.
    with registry.database.connect() as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT status,metadata_json FROM analysis_sessions WHERE owner_session_id=? AND analysis_session_id=?",
            (owner, analysis),
        ).fetchone()
        if row is None or row["status"] != "ACTIVE":
            raise ValueError("The exact analysis is not active.")
        connection = conn.execute(
            "SELECT 1 FROM browser_lifecycle_connections WHERE owner_session_id=? AND analysis_session_id=? "
            "AND tab_instance_id=? AND page_instance_id=? AND state IN ('ACTIVE','DISCONNECT_PENDING')",
            (owner, analysis, context["tab_instance_id"], context["page_instance_id"]),
        ).fetchone()
        if connection is None:
            response["activity_known"] = False
            return response
        metadata = json.loads(row["metadata_json"] or "{}")
        prior = metadata.get(POLICY_KEY, {})
        prior = prior if isinstance(prior, dict) else {}
        # Start an existing tab's new policy at its first observed heartbeat.
        # Do not immediately end an old user session during deployment.
        observed = float(prior.get("first_observed_at") or timestamp)
        last_activity = max(float(prior.get("last_activity_at") or observed), timestamp - max(0, int(idle_seconds)))
        work = scoped_work(conn, owner, analysis, registry.database.config)
        last_work = max(float(prior.get("last_work_at") or observed), work["last_finished_at"])
        if work["active"] or client_busy:
            last_work = timestamp
        deadline = max(observed, last_activity, last_work) + timeout
        response.update(activity_known=True, active_work=bool(work["active"] or client_busy),
                        remaining_seconds=max(0, int(deadline - timestamp + 0.999)),
                        jobs=work["jobs"], uploads=work["uploads"], alignment=work["alignment"])
        policy = {"first_observed_at": observed, "last_activity_at": last_activity,
                  "last_work_at": last_work, "timeout_seconds": timeout}
        should_end = timestamp >= deadline and not response["active_work"]
        if should_end:
            policy.update(ended_reason=IDLE_REASON, ended_at=current.isoformat())
        metadata[POLICY_KEY] = policy
        changed = conn.execute(
            "UPDATE analysis_sessions SET metadata_json=?,status=?,updated_at=? "
            "WHERE owner_session_id=? AND analysis_session_id=? AND status='ACTIVE'",
            (json.dumps(metadata, sort_keys=True), "ENDED" if should_end else "ACTIVE",
             current.isoformat(), owner, analysis),
        ).rowcount
        if should_end and changed:
            conn.execute(
                "UPDATE browser_lifecycle_connections SET state='DISCONNECTED',disconnected_at=?,updated_at=?,"
                "pending_until=NULL,last_event_type='ANALYSIS_IDLE_TIMEOUT',last_reason=? "
                "WHERE owner_session_id=? AND analysis_session_id=? AND state IN ('ACTIVE','DISCONNECT_PENDING')",
                (current.isoformat(), current.isoformat(), IDLE_REASON, owner, analysis),
            )
            registry._event(conn, event_type="ANALYSIS_IDLE_TIMEOUT", old_state="ACTIVE", new_state="ENDED",
                reason=IDLE_REASON, owner_session_id=owner, analysis_session_id=analysis,
                browser_client_id=context["browser_client_id"], tab_instance_id=context["tab_instance_id"],
                page_instance_id=context["page_instance_id"], workflow_id=context.get("workflow_id", ""),
                metadata={"idle_timeout_seconds": timeout, "active_work": False})
            response.update(expired=True, reason=IDLE_REASON)
    return response
