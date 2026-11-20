from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .auth import require_user
from .browser_lifecycle import BrowserLifecycleRegistry
from .cleanup_coordinator import CleanupCoordinator
from .example_action_bindings import ExampleActionBindingService, ExampleActionError
from .example_asset_references import ExampleAssetReferenceError, ExampleAssetReferenceService
from .example_assets import ExampleAssetAccessError, ExampleAssetError, ExampleAssetService
from .healthcheck import HealthChecker
from .input_resolver import InputResolver, InputResolverError, verify_worker_job_spec_token
from .job_manager import JobManager
from .job_queue_repository import JobQueueRepository
from .job_submission import JobSubmissionError, JobSubmissionService
from .session_manager import SessionAuthError, SessionExpiredError, SessionManager
from .task_queue import TaskQueue
from .upload_service import UploadPart, UploadService, UploadValidationError
from .worker_callbacks import WorkerCallbackError, WorkerCallbackService
from .workflow_registry import ST_SM_CONDITIONAL_VAE

try:
    from fastapi import Request as FastAPIRequest
except Exception:  # pragma: no cover - create_app reports missing FastAPI explicitly
    FastAPIRequest = Any  # type: ignore

try:
    from pydantic import BaseModel
except Exception:  # pragma: no cover - create_app reports missing pydantic explicitly
    class BaseModel:  # type: ignore
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

try:
    from pydantic import Field
except Exception:  # pragma: no cover - used by lightweight unit-test fakes
    def Field(default=None, *, default_factory=None, **_kwargs):
        return default_factory() if default_factory is not None else default


class StrictAPIModel(BaseModel):
    model_config = {"extra": "forbid"}


class SubmitConditionalVAERequest(BaseModel):
    user_id: str | None = None
    input_h5ad: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    run_inline: bool = False


class EndSessionRequest(StrictAPIModel):
    reason: str = "user_end"


class SessionTokenRequest(StrictAPIModel):
    session_token: str


class LifecycleEventRequest(StrictAPIModel):
    browser_client_id: str = ""
    tab_instance_id: str = ""
    page_instance_id: str = ""
    analysis_session_id: str = ""
    workflow_id: str = ""
    event_type: str = "LIFECYCLE_EVENT"
    reason: str = ""
    persisted: bool | None = None
    visibility_state: str = ""
    navigation_type: str = ""
    client_timestamp: str = ""


class ClientLifecycleDiagnosticRequest(StrictAPIModel):
    event_type: str = "CLIENT_DIAGNOSTIC"
    page_instance_id: str = ""
    ready_state: str = ""
    has_shiny: bool | None = None
    navigation_type: str = ""
    error_name: str = ""
    error_message: str = ""


class InitiateUploadRequest(StrictAPIModel):
    filename: str
    size_bytes: int
    content_type: str = "application/octet-stream"
    total_parts: int


class CompleteUploadPartRequest(StrictAPIModel):
    part_number: int
    etag: str


class CompleteUploadRequest(StrictAPIModel):
    parts: list[CompleteUploadPartRequest]


class SubmitJobRequest(StrictAPIModel):
    workflow_name: str
    input_upload_ids: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    requested_resource: str | None = None
    example_action_id: str = ""


def _job_submission_error_detail(exc: JobSubmissionError) -> dict[str, Any]:
    detail: dict[str, Any] = {"code": exc.code, "error": exc.code, "message": str(exc)}
    retry_after = getattr(exc, "retry_after", None)
    if retry_after is not None:
        detail["retry_after"] = int(retry_after)
    return detail


class CreateExampleAssetReferenceRequest(StrictAPIModel):
    asset_id: str | None = None
    asset_object_key: str | None = Field(default=None, deprecated=True)


class ActivateExampleActionRequest(StrictAPIModel):
    page_name: str = ""


class SubmitAssetJobRequest(StrictAPIModel):
    workflow_name: str
    asset_reference_ids: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    requested_resource: str | None = None
    asset_object_keys: list[str] = Field(default_factory=list, deprecated=True)
    asset_object_key: str | None = Field(default=None, deprecated=True)


class PresignExampleAssetRequest(StrictAPIModel):
    object_keys: list[str]


class WorkerCallbackRequest(StrictAPIModel):
    status: str
    progress: float | None = None
    current_step: str = ""
    message: str = ""
    device: str | None = None
    gpu_name: str | None = None
    output_objects: list[dict[str, Any]] = Field(default_factory=list)
    checkpoints: list[dict[str, Any]] = Field(default_factory=list)
    result_manifest: dict[str, Any] = Field(default_factory=dict)
    error_code: str = ""
    error_message: str = ""


def _normalize_origin(value: str | None) -> str | None:
    raw = str(value or "").strip().rstrip("/")
    if not raw:
        return None
    parsed = urlsplit(raw)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _host_name(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlsplit(f"//{raw}")
    return (parsed.hostname or "").lower()


def _first_header_value(value: str | None) -> str:
    return str(value or "").split(",", 1)[0].strip().lower()


def _install_public_proxy_middleware(app, config) -> None:
    if not hasattr(app, "add_middleware") or not hasattr(app, "middleware"):
        return
    try:
        from fastapi.middleware.cors import CORSMiddleware
        from starlette.responses import JSONResponse
    except Exception:
        return

    allowed_origins = tuple(config.cors_allowed_origins or ())
    allowed_origin_set = {origin.lower().rstrip("/") for origin in allowed_origins}
    trusted_hosts = {host.lower() for host in (config.trusted_hosts or ()) if host}
    public_origin = _normalize_origin(config.public_origin)
    require_https_forward = bool(public_origin and public_origin.startswith("https://"))

    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(allowed_origins),
            allow_credentials=True,
            allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
            allow_headers=["Accept", "Content-Type", "X-SpaShiny-Session", "X-SpaShiny-Browser-Client", "X-SpaShiny-Analysis-Session"],
        )

    @app.middleware("http")
    async def validate_public_proxy_headers(request, call_next):
        host = _host_name(request.headers.get("host"))
        if trusted_hosts and host and host not in trusted_hosts:
            return JSONResponse(status_code=400, content={"detail": {"code": "HOST_NOT_ALLOWED"}})

        origin = _normalize_origin(request.headers.get("origin"))
        if origin and allowed_origin_set and origin not in allowed_origin_set:
            return JSONResponse(status_code=403, content={"detail": {"code": "ORIGIN_NOT_ALLOWED"}})

        forwarded_proto = _first_header_value(request.headers.get("x-forwarded-proto"))
        if require_https_forward and forwarded_proto and forwarded_proto != "https":
            return JSONResponse(status_code=400, content={"detail": {"code": "INVALID_FORWARDED_PROTO"}})

        return await call_next(request)


def create_app(
    *,
    jobs: JobManager | None = None,
    queue: TaskQueue | None = None,
    health: HealthChecker | None = None,
    sessions: SessionManager | None = None,
    uploads: UploadService | None = None,
    submissions: JobSubmissionService | None = None,
    example_assets: ExampleAssetService | None = None,
    example_references: ExampleAssetReferenceService | None = None,
    example_actions: ExampleActionBindingService | None = None,
    input_resolver: InputResolver | None = None,
    worker_callbacks: WorkerCallbackService | None = None,
    job_queue: JobQueueRepository | None = None,
    cleanup: CleanupCoordinator | None = None,
):
    try:
        from fastapi import FastAPI, Header, HTTPException
        try:
            from fastapi.exceptions import RequestValidationError
            from fastapi.responses import JSONResponse
        except Exception:  # pragma: no cover - used only by the lightweight unit-test fakes
            RequestValidationError = None
            JSONResponse = None
    except Exception as exc:
        raise RuntimeError("FastAPI and pydantic are required for cloud.api.") from exc

    app = FastAPI(title="SpaShiny Cloud API")
    jobs = jobs or JobManager()
    queue = queue or TaskQueue(jobs=jobs)
    health = health or HealthChecker(database=jobs.database)
    sessions = sessions or SessionManager(database=jobs.database)
    browser_lifecycle = BrowserLifecycleRegistry(
        database=jobs.database,
        grace_seconds=jobs.config.analysis_close_grace_seconds,
        heartbeat_lease_seconds=jobs.config.analysis_heartbeat_lease_seconds,
    )
    uploads = uploads or UploadService(database=jobs.database, config=sessions.config)
    submissions = submissions or JobSubmissionService(database=jobs.database, config=sessions.config)
    example_assets = example_assets or ExampleAssetService(config=sessions.config)
    example_references = example_references or ExampleAssetReferenceService(database=jobs.database, config=sessions.config, example_assets=example_assets)
    example_actions = example_actions or ExampleActionBindingService(database=jobs.database, config=sessions.config, example_assets=example_assets)
    submissions.example_assets = example_assets
    submissions.example_references = example_references
    job_queue = job_queue or JobQueueRepository(jobs.database, sessions.config)
    input_resolver = input_resolver or InputResolver(database=jobs.database, config=sessions.config, example_assets=example_assets)
    worker_callbacks = worker_callbacks or WorkerCallbackService(database=jobs.database, config=sessions.config, queue=job_queue)
    cleanup = cleanup or CleanupCoordinator(database=jobs.database, config=sessions.config, sessions=sessions, uploads=uploads, queue=job_queue)
    _install_public_proxy_middleware(app, sessions.config)

    if getattr(sessions.config, "is_lab_profile", False) and hasattr(app, "middleware"):
        @app.middleware("http")
        async def lab_session_cookie_middleware(request, call_next):
            headers = list(request.scope.get("headers") or [])
            has_header = any(key.lower() == b"x-spashiny-session" for key, _value in headers)
            if not has_header:
                cookie_token = request.cookies.get(sessions.config.lab_session_cookie_name)
                if cookie_token:
                    headers.append((b"x-spashiny-session", str(cookie_token).encode("utf-8")))
                    request.scope["headers"] = headers
            return await call_next(request)

    if RequestValidationError is not None and JSONResponse is not None and hasattr(app, "exception_handler"):
        @app.exception_handler(RequestValidationError)
        async def validation_exception_handler(_request, exc):
            return JSONResponse(
                status_code=422,
                content={
                    "detail": {
                        "code": "INVALID_REQUEST_PAYLOAD",
                        "message": "The request payload does not match this API contract.",
                        "errors": exc.errors(),
                    }
                },
            )

    def _session_token(header_value: str | None) -> str:
        token = str(header_value or "").strip()
        if not token:
            raise HTTPException(status_code=401, detail={"code": "INVALID_SESSION"})
        return token

    def _browser_client_id(header_value: str | None) -> str:
        """Validate the non-secret, browser-profile correlation id.

        It is stored only for auditing/ownership correlation.  Authentication
        remains the opaque session token handled by ``_active_session``.
        """
        value = str(header_value or "").strip()
        if not value:
            return ""
        try:
            return str(uuid.UUID(value))
        except (ValueError, AttributeError) as exc:
            raise HTTPException(status_code=422, detail={"code": "INVALID_BROWSER_CLIENT_ID"}) from exc

    async def _session_token_from_beacon_request(request: FastAPIRequest) -> str:
        content_type = str(request.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
        try:
            if content_type in {"application/json", "application/beacon+json"} or content_type.endswith("+json"):
                payload = await request.json()
            elif content_type in {"", "text/plain", "application/octet-stream"}:
                raw = await request.body()
                payload = json.loads(raw.decode("utf-8", "strict"))
            else:
                raise HTTPException(status_code=415, detail={"code": "UNSUPPORTED_BEACON_CONTENT_TYPE"})
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=422, detail={"code": "INVALID_BEACON_PAYLOAD"}) from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=422, detail={"code": "INVALID_BEACON_PAYLOAD"})
        token = payload.get("session_token")
        if not isinstance(token, str):
            raise HTTPException(status_code=422, detail={"code": "INVALID_BEACON_PAYLOAD"})
        return _session_token(token)

    def _authenticate_session(header_value: str | None):
        token = _session_token(header_value)
        try:
            return sessions.authenticate(token)
        except SessionAuthError as exc:
            raise HTTPException(status_code=401, detail={"code": "INVALID_SESSION"}) from exc

    def _active_session(header_value: str | None):
        session = _authenticate_session(header_value)
        if session.status != "ACTIVE":
            raise HTTPException(status_code=410, detail={"code": "SESSION_EXPIRED"})
        return session

    def _session_response(session) -> dict[str, Any]:
        data = session.public_dict()
        data.setdefault("anonymous_session_id", session.session_id)
        data.setdefault("anonymous_workspace_id", getattr(session, "anonymous_workspace_id", session.session_id))
        return data

    def _analysis_session_cookie_name() -> str:
        return str(os.environ.get("SPASHINY_ANALYSIS_SESSION_COOKIE_NAME") or "spashiny_analysis_session").strip()

    def _analysis_session_response(record: dict[str, Any]):
        # Analysis identity comes only from the requesting tab's sessionStorage.
        # Owner authentication remains cookie/session-token based.
        return record

    def _require_current_analysis_session(owner_session_id: str, header_value: str | None) -> str:
        """Require a live analysis workspace owned by the authenticated session."""
        analysis_session_id = str(header_value or "").strip()
        if not analysis_session_id:
            raise HTTPException(status_code=409, detail={"code": "ANALYSIS_SESSION_REQUIRED"})
        try:
            record = jobs.database.get_analysis_session(
                analysis_session_id,
                owner_session_id=str(owner_session_id or ""),
            )
        except KeyError as exc:
            raise HTTPException(status_code=403, detail={"code": "ANALYSIS_SESSION_NOT_FOUND"}) from exc
        if str(record.get("status") or "") != "ACTIVE":
            raise HTTPException(status_code=409, detail={"code": "ANALYSIS_SESSION_ENDED"})
        return analysis_session_id

    def _lifecycle_context(
        session,
        request: LifecycleEventRequest,
        x_spashiny_browser_client: str | None = None,
        x_spashiny_analysis_session: str | None = None,
    ) -> dict[str, Any]:
        analysis_session_id = str(
            getattr(request, "analysis_session_id", "") or x_spashiny_analysis_session or ""
        ).strip()
        if analysis_session_id:
            _require_current_analysis_session(session.session_id, analysis_session_id)
        return {
            "owner_session_id": session.session_id,
            "analysis_session_id": analysis_session_id,
            "browser_client_id": _browser_client_id(
                str(getattr(request, "browser_client_id", "") or x_spashiny_browser_client or "")
            ),
            "tab_instance_id": str(getattr(request, "tab_instance_id", "") or "").strip(),
            "page_instance_id": str(getattr(request, "page_instance_id", "") or "").strip(),
            "workflow_id": str(getattr(request, "workflow_id", "") or "").strip(),
            "event_type": str(getattr(request, "event_type", "") or "LIFECYCLE_EVENT").strip(),
            "reason": str(getattr(request, "reason", "") or "").strip(),
            "persisted": getattr(request, "persisted", None),
            "visibility_state": str(getattr(request, "visibility_state", "") or "").strip(),
            "navigation_type": str(getattr(request, "navigation_type", "") or "").strip(),
            "client_timestamp": str(getattr(request, "client_timestamp", "") or "").strip(),
        }

    def _upload_response(upload) -> dict[str, Any]:
        return upload.public_dict()

    def _job_response(job) -> dict[str, Any]:
        data = job.to_dict()
        data.pop("claim_token", None)
        data.pop("worker_id", None)
        return data

    def _asset_error(exc: ExampleAssetError):
        status = 403 if isinstance(exc, ExampleAssetAccessError) else 503
        code = "ASSET_NOT_ALLOWLISTED" if isinstance(exc, ExampleAssetAccessError) else "ASSET_MANIFEST_UNAVAILABLE"
        raise HTTPException(status_code=status, detail={"code": code, "message": str(exc)}) from exc

    def _reference_error(exc: ExampleAssetReferenceError):
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)}) from exc

    def _example_action_error(exc: ExampleActionError):
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)}) from exc

    def _upload_error(exc: UploadValidationError):
        detail = {"code": exc.code, "message": str(exc)}
        detail.update(getattr(exc, "details", {}) or {})
        raise HTTPException(status_code=exc.status_code, detail=detail) from exc

    def _anonymous_session_monitor(*, limit: int = 100) -> dict[str, Any]:
        """Read-only anonymous session monitor data.

        ``last_seen_at`` is reported for operators only; it is not used here to
        expire, disconnect, or clean up user sessions.
        """
        with jobs.database.connect() as conn:
            status_rows = conn.execute(
                "SELECT status, COUNT(*) AS count FROM sessions GROUP BY status"
            ).fetchall()
            rows = conn.execute(
                """
                SELECT
                    s.session_id,
                    s.anonymous_workspace_id,
                    s.status,
                    s.created_at,
                    s.last_heartbeat_at,
                    s.total_upload_bytes,
                    COALESCE((
                        SELECT analysis_session_id
                        FROM analysis_sessions a
                        WHERE a.owner_session_id=s.session_id
                        ORDER BY updated_at DESC
                        LIMIT 1
                    ), '') AS analysis_session_id,
                    (
                        SELECT COUNT(*) FROM jobs j
                        WHERE j.owner_session_id=s.session_id
                    ) AS job_count,
                    (
                        SELECT COUNT(*) FROM jobs j
                        WHERE j.owner_session_id=s.session_id
                          AND j.status IN ('RUNNING', 'STARTING', 'STARTING_GPU', 'POSTPROCESSING', 'SYNCING', 'VERIFYING')
                    ) AS running_jobs,
                    (
                        SELECT COUNT(*) FROM jobs j
                        WHERE j.owner_session_id=s.session_id
                          AND j.status IN ('CREATED', 'VALIDATING', 'QUEUED', 'QUEUED_CPU', 'QUEUED_GPU', 'WAITING_FOR_GPU')
                    ) AS queued_jobs
                FROM sessions s
                ORDER BY s.id DESC
                LIMIT ?
                """,
                (max(1, min(int(limit), 500)),),
            ).fetchall()
        return {
            "active_anonymous_sessions": sum(
                int(row["count"] or 0) for row in status_rows if str(row["status"] or "") == "ACTIVE"
            ),
            "status_counts": {str(row["status"] or ""): int(row["count"] or 0) for row in status_rows},
            "sessions": [
                {
                    "owner_id": str(row["session_id"] or ""),
                    "anonymous_workspace_id": str(row["anonymous_workspace_id"] or ""),
                    "analysis_session_id": str(row["analysis_session_id"] or ""),
                    "status": str(row["status"] or ""),
                    "created_at": str(row["created_at"] or ""),
                    "last_seen_at": str(row["last_heartbeat_at"] or ""),
                    "job_count": int(row["job_count"] or 0),
                    "running_jobs": int(row["running_jobs"] or 0),
                    "queued_jobs": int(row["queued_jobs"] or 0),
                    "storage_usage_bytes": int(row["total_upload_bytes"] or 0),
                }
                for row in rows
            ],
        }

    @app.get("/health")
    def get_health():
        # Existing health probes also finalize expired browser-page pending state.
        # This never changes analysis sessions or jobs.
        browser_lifecycle.expire_pending()
        return {"ok": True}

    @app.get("/")
    def get_root():
        return {"ok": True, "service": "spashiny-control"}

    @app.post("/api/session/client-diagnostic")
    def client_lifecycle_diagnostic(request: ClientLifecycleDiagnosticRequest):
        # TEST-ONLY h11aj readiness diagnostic; no session state is changed here.
        try:
            print(
                "SPASHINY_TEST_CLIENT_LIFECYCLE_DIAG "
                + json.dumps(request.model_dump() if hasattr(request, "model_dump") else request.__dict__, sort_keys=True),
                flush=True,
            )
        except Exception:
            pass
        return {"ok": True}

    @app.get("/resource-status")
    def resource_status():
        status = health.resource_status(include_admin=False)
        status["anonymous_session_monitor"] = _anonymous_session_monitor()
        return status

    @app.get("/api/deployment/tunnel-status")
    def tunnel_status():
        status = "CONFIGURED" if sessions.config.cloudflare_tunnel_configured else "NOT_CONFIGURED"
        return {
            "status": status,
            "public_base_url": sessions.config.public_base_url or "",
            "public_origin": sessions.config.public_origin or "",
            "origin_service": sessions.config.cloudflare_tunnel_origin_service,
            "cors_allowed_origins": list(sessions.config.cors_allowed_origins),
        }

    @app.post("/api/session/start")
    @app.post("/session/start")
    def start_session(
        x_spashiny_browser_client: str | None = Header(default=None, alias="X-SpaShiny-Browser-Client"),
    ):
        _browser_client_id(x_spashiny_browser_client)
        created = sessions.create_session()
        payload = {
            "session_id": created.session.session_id,
            "anonymous_session_id": created.session.session_id,
            "anonymous_workspace_id": created.session.anonymous_workspace_id,
            "session_token": created.session_token,
            "status": created.session.status,
            "heartbeat_interval_seconds": sessions.config.session_heartbeat_interval_seconds,
            "idle_timeout_seconds": sessions.config.session_idle_timeout_seconds,
        }
        if getattr(sessions.config, "is_lab_profile", False) and JSONResponse is not None:
            response = JSONResponse(content=payload)
            response.set_cookie(
                key=sessions.config.lab_session_cookie_name,
                value=created.session_token,
                httponly=True,
                samesite="lax",
                secure=False,
                path="/",
            )
            return response
        return payload

    @app.post("/api/session/heartbeat")
    @app.post("/session/heartbeat")
    def heartbeat_session(
        request: LifecycleEventRequest | None = None,
        x_spashiny_session: str | None = Header(default=None, alias="X-SpaShiny-Session"),
        x_spashiny_browser_client: str | None = Header(default=None, alias="X-SpaShiny-Browser-Client"),
        x_spashiny_analysis_session: str | None = Header(default=None, alias="X-SpaShiny-Analysis-Session"),
    ):
        token = _session_token(x_spashiny_session)
        try:
            session = sessions.heartbeat(token)
            if request is not None:
                browser_lifecycle.heartbeat(
                    **_lifecycle_context(
                        session, request, x_spashiny_browser_client, x_spashiny_analysis_session
                    )
                )
            return _session_response(session)
        except SessionExpiredError as exc:
            raise HTTPException(status_code=410, detail={"code": "SESSION_EXPIRED"}) from exc
        except SessionAuthError as exc:
            raise HTTPException(status_code=401, detail={"code": "INVALID_SESSION"}) from exc

    @app.post("/api/session/lifecycle/connect")
    def connect_browser_lifecycle(
        request: LifecycleEventRequest,
        x_spashiny_session: str | None = Header(default=None, alias="X-SpaShiny-Session"),
        x_spashiny_browser_client: str | None = Header(default=None, alias="X-SpaShiny-Browser-Client"),
        x_spashiny_analysis_session: str | None = Header(default=None, alias="X-SpaShiny-Analysis-Session"),
    ):
        token = _session_token(x_spashiny_session)
        try:
            session = sessions.heartbeat(token)
            connection = browser_lifecycle.connect(
                **_lifecycle_context(session, request, x_spashiny_browser_client, x_spashiny_analysis_session)
            )
            return {"session": _session_response(session), "browser_connection": connection}
        except SessionExpiredError as exc:
            raise HTTPException(status_code=410, detail={"code": "SESSION_EXPIRED"}) from exc
        except SessionAuthError as exc:
            raise HTTPException(status_code=401, detail={"code": "INVALID_SESSION"}) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "INVALID_LIFECYCLE_CONTEXT"}) from exc

    @app.post("/api/session/lifecycle/event")
    def record_browser_lifecycle_event(
        request: LifecycleEventRequest,
        x_spashiny_session: str | None = Header(default=None, alias="X-SpaShiny-Session"),
        x_spashiny_browser_client: str | None = Header(default=None, alias="X-SpaShiny-Browser-Client"),
        x_spashiny_analysis_session: str | None = Header(default=None, alias="X-SpaShiny-Analysis-Session"),
    ):
        session = _authenticate_session(x_spashiny_session)
        browser_lifecycle.record_event(
            **_lifecycle_context(session, request, x_spashiny_browser_client, x_spashiny_analysis_session)
        )
        return {"ok": True}

    @app.get("/api/session/lifecycle/events")
    def list_browser_lifecycle_events(
        limit: int = 100,
        x_spashiny_session: str | None = Header(default=None, alias="X-SpaShiny-Session"),
        x_spashiny_analysis_session: str | None = Header(default=None, alias="X-SpaShiny-Analysis-Session"),
    ):
        session = _authenticate_session(x_spashiny_session)
        analysis_session_id = str(x_spashiny_analysis_session or "").strip()
        if analysis_session_id:
            _require_current_analysis_session(session.session_id, analysis_session_id)
        return browser_lifecycle.events(
            owner_session_id=session.session_id,
            analysis_session_id=analysis_session_id,
            limit=limit,
        )

    def _pending_disconnect(session, request, browser_client, analysis_session):
        return browser_lifecycle.disconnect_pending(
            **_lifecycle_context(session, request, browser_client, analysis_session)
        )

    @app.post("/api/session/disconnect")
    @app.post("/session/disconnect")
    def disconnect_session(
        request: LifecycleEventRequest | None = None,
        x_spashiny_session: str | None = Header(default=None, alias="X-SpaShiny-Session"),
        x_spashiny_browser_client: str | None = Header(default=None, alias="X-SpaShiny-Browser-Client"),
        x_spashiny_analysis_session: str | None = Header(default=None, alias="X-SpaShiny-Analysis-Session"),
    ):
        token = _session_token(x_spashiny_session)
        try:
            session = sessions.authenticate(token)
            if request is None or not str(getattr(request, "page_instance_id", "") or "").strip():
                raise HTTPException(status_code=422, detail={"code": "LIFECYCLE_PAGE_REQUIRED"})
            return {"session": _session_response(session), "browser_connection": _pending_disconnect(
                session, request, x_spashiny_browser_client, x_spashiny_analysis_session
            )}
        except SessionAuthError as exc:
            raise HTTPException(status_code=401, detail={"code": "INVALID_SESSION"}) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "INVALID_LIFECYCLE_CONTEXT"}) from exc

    @app.post("/api/session/disconnect-beacon")
    @app.post("/session/disconnect-beacon")
    async def disconnect_session_beacon(request: FastAPIRequest):
        try:
            body = await request.body()
            payload = json.loads(body.decode("utf-8")) if body else {}
            if not isinstance(payload, dict):
                raise ValueError("payload is not an object")
            token = _session_token(str(payload.get("session_token") or ""))
            context = LifecycleEventRequest(**{
                key: value for key, value in payload.items() if key != "session_token"
            })
            session = sessions.authenticate(token)
            if not str(context.page_instance_id or "").strip():
                raise HTTPException(status_code=422, detail={"code": "LIFECYCLE_PAGE_REQUIRED"})
            return {"session": _session_response(session), "browser_connection": _pending_disconnect(
                session, context, str(context.browser_client_id or ""), str(context.analysis_session_id or "")
            )}
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=422, detail={"code": "INVALID_BEACON_PAYLOAD"}) from exc
        except SessionAuthError as exc:
            raise HTTPException(status_code=401, detail={"code": "INVALID_SESSION"}) from exc

    @app.post("/api/session/end")
    @app.post("/session/end")
    def end_session(
        request: EndSessionRequest,
        x_spashiny_session: str | None = Header(default=None, alias="X-SpaShiny-Session"),
    ):
        token = _session_token(x_spashiny_session)
        try:
            session = sessions.abandon(token, reason=request.reason)
            cleanup.request_session_cleanup(session.session_id, reason=request.reason)
            response = _session_response(session)
            response["cleanup_requested"] = True
            return response
        except SessionAuthError as exc:
            raise HTTPException(status_code=401, detail={"code": "INVALID_SESSION"}) from exc

    @app.get("/api/session/cleanup-status")
    def session_cleanup_status(x_spashiny_session: str | None = Header(default=None, alias="X-SpaShiny-Session")):
        session = _authenticate_session(x_spashiny_session)
        retries = jobs.database.list_cleanup_retries(session_id=session.session_id)
        events = jobs.database.list_cleanup_events(session_id=session.session_id, limit=50)
        return {
            "session_id": session.session_id,
            "status": session.status,
            "cleanup_retries": [
                {
                    "resource_type": item["resource_type"],
                    "resource_id": item["resource_id"],
                    "action": item["action"],
                    "attempt_count": item["attempt_count"],
                    "max_attempts": item["max_attempts"],
                    "status": item["status"],
                    "last_error_code": item["last_error_code"],
                }
                for item in retries
            ],
            "cleanup_events": events,
        }

    @app.get("/api/session/status")
    @app.get("/session/status")
    def session_status(
        request: FastAPIRequest,
        x_spashiny_session: str | None = Header(default=None, alias="X-SpaShiny-Session"),
    ):
        # On a restored HTTP page, lifecycle status may run before the Shiny
        # replay has reattached the header token.  The existing HttpOnly lab
        # cookie is the same opaque credential set by /api/session/start.
        # Resolve it directly here instead of relying on middleware header
        # mutation after Starlette has cached request headers.
        token = str(x_spashiny_session or "").strip()
        if not token and getattr(sessions.config, "is_lab_profile", False):
            token = str(request.cookies.get(sessions.config.lab_session_cookie_name) or "").strip()
        session = _active_session(token)
        payload = _session_response(session)
        if token:
            payload["session_token"] = token
        # A restored browser session has the token in sessionStorage and sends
        # it as a header, while <img> artifact requests can only use the
        # HttpOnly cookie.  Re-sync that same authenticated token here.  This
        # does not relax owner or analysis-session checks in the download route.
        if token and getattr(sessions.config, "is_lab_profile", False) and JSONResponse is not None:
            response = JSONResponse(content=payload)
            response.set_cookie(
                key=sessions.config.lab_session_cookie_name,
                value=token,
                httponly=True,
                samesite="lax",
                secure=False,
                path="/",
            )
            return response
        return payload

    @app.post("/api/analysis-sessions/start")
    def start_analysis_session(
        x_spashiny_session: str | None = Header(default=None, alias="X-SpaShiny-Session"),
        x_spashiny_browser_client: str | None = Header(default=None, alias="X-SpaShiny-Browser-Client"),
    ):
        session = _active_session(x_spashiny_session)
        record = jobs.database.create_analysis_session(
            owner_session_id=session.session_id,
            browser_client_id=_browser_client_id(x_spashiny_browser_client),
        )
        return _analysis_session_response(record)

    @app.get("/api/analysis-sessions/current")
    def get_current_analysis_session(
        request: FastAPIRequest,
        x_spashiny_session: str | None = Header(default=None, alias="X-SpaShiny-Session"),
        x_spashiny_analysis_session: str | None = Header(default=None, alias="X-SpaShiny-Analysis-Session"),
        x_spashiny_browser_client: str | None = Header(default=None, alias="X-SpaShiny-Browser-Client"),
    ):
        session = _active_session(x_spashiny_session)
        analysis_session_id = str(x_spashiny_analysis_session or "").strip()
        if not analysis_session_id:
            raise HTTPException(status_code=409, detail={"code": "ANALYSIS_SESSION_REQUIRED"})
        try:
            record = jobs.database.get_analysis_session(
                analysis_session_id,
                owner_session_id=session.session_id,
            )
            if str(record.get("status") or "") != "ACTIVE":
                raise HTTPException(status_code=409, detail={"code": "ANALYSIS_SESSION_ENDED"})
            return _analysis_session_response(record)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "ANALYSIS_SESSION_NOT_FOUND"}) from exc

    @app.get("/api/analysis-sessions/{analysis_session_id}")
    def get_analysis_session(
        analysis_session_id: str,
        x_spashiny_session: str | None = Header(default=None, alias="X-SpaShiny-Session"),
    ):
        session = _active_session(x_spashiny_session)
        try:
            record = jobs.database.get_analysis_session(
                analysis_session_id,
                owner_session_id=session.session_id,
            )
            if str(record.get("status") or "") != "ACTIVE":
                raise HTTPException(status_code=409, detail={"code": "ANALYSIS_SESSION_ENDED"})
            return _analysis_session_response(record)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "ANALYSIS_SESSION_NOT_FOUND"}) from exc

    @app.post("/api/uploads/initiate")
    def initiate_upload(
        request: InitiateUploadRequest,
        x_spashiny_session: str | None = Header(default=None, alias="X-SpaShiny-Session"),
        x_spashiny_analysis_session: str | None = Header(default=None, alias="X-SpaShiny-Analysis-Session"),
    ):
        session = _active_session(x_spashiny_session)
        analysis_session_id = _require_current_analysis_session(session.session_id, x_spashiny_analysis_session)
        try:
            return uploads.initiate_upload(session=session, analysis_session_id=analysis_session_id, filename=request.filename, size_bytes=request.size_bytes, content_type=request.content_type, total_parts=request.total_parts)
        except UploadValidationError as exc:
            _upload_error(exc)

    @app.post("/api/uploads/{upload_id}/parts/{part_number}/presign")
    def presign_upload_part(upload_id: str, part_number: int, x_spashiny_session: str | None = Header(default=None, alias="X-SpaShiny-Session"), x_spashiny_analysis_session: str | None = Header(default=None, alias="X-SpaShiny-Analysis-Session")):
        session = _active_session(x_spashiny_session)
        analysis_session_id = _require_current_analysis_session(session.session_id, x_spashiny_analysis_session)
        try:
            return uploads.presign_part(session=session, analysis_session_id=analysis_session_id, upload_id=upload_id, part_number=part_number)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "UPLOAD_NOT_FOUND"}) from exc
        except UploadValidationError as exc:
            _upload_error(exc)

    @app.post("/api/uploads/{upload_id}/complete")
    def complete_upload(upload_id: str, request: CompleteUploadRequest, x_spashiny_session: str | None = Header(default=None, alias="X-SpaShiny-Session"), x_spashiny_analysis_session: str | None = Header(default=None, alias="X-SpaShiny-Analysis-Session")):
        session = _active_session(x_spashiny_session)
        analysis_session_id = _require_current_analysis_session(session.session_id, x_spashiny_analysis_session)
        try:
            parts = [UploadPart(part_number=int(part.part_number), etag=str(part.etag)) for part in request.parts]
            return _upload_response(uploads.complete_upload(session=session, analysis_session_id=analysis_session_id, upload_id=upload_id, parts=parts))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "UPLOAD_NOT_FOUND"}) from exc
        except UploadValidationError as exc:
            _upload_error(exc)

    @app.post("/api/uploads/{upload_id}/abort")
    def abort_upload(upload_id: str, x_spashiny_session: str | None = Header(default=None, alias="X-SpaShiny-Session"), x_spashiny_analysis_session: str | None = Header(default=None, alias="X-SpaShiny-Analysis-Session")):
        session = _authenticate_session(x_spashiny_session)
        analysis_session_id = _require_current_analysis_session(session.session_id, x_spashiny_analysis_session)
        try:
            return _upload_response(uploads.abort_upload(session=session, analysis_session_id=analysis_session_id, upload_id=upload_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "UPLOAD_NOT_FOUND"}) from exc

    @app.get("/api/uploads")
    def list_uploads(x_spashiny_session: str | None = Header(default=None, alias="X-SpaShiny-Session"), x_spashiny_analysis_session: str | None = Header(default=None, alias="X-SpaShiny-Analysis-Session")):
        session = _authenticate_session(x_spashiny_session)
        analysis_session_id = _require_current_analysis_session(session.session_id, x_spashiny_analysis_session)
        return [_upload_response(record) for record in uploads.list_uploads(session=session, analysis_session_id=analysis_session_id)]

    @app.post("/api/jobs")
    def submit_job(
        request: SubmitJobRequest,
        x_spashiny_session: str | None = Header(default=None, alias="X-SpaShiny-Session"),
        x_spashiny_analysis_session: str | None = Header(default=None, alias="X-SpaShiny-Analysis-Session"),
    ):
        session = _active_session(x_spashiny_session)
        analysis_session_id = _require_current_analysis_session(session.session_id, x_spashiny_analysis_session)
        try:
            example_action_id = str(getattr(request, "example_action_id", "") or "").strip()
            if example_action_id:
                job = submissions.submit_with_example_action(
                    session=session,
                    workflow_name=request.workflow_name,
                    example_action_id=example_action_id,
                    parameters=request.parameters or {},
                    requested_resource=getattr(request, "requested_resource", None),
                    analysis_session_id=analysis_session_id,
                )
            else:
                job = submissions.submit(
                    session=session,
                    workflow_name=request.workflow_name,
                    input_upload_ids=list(request.input_upload_ids or []),
                    parameters=request.parameters or {},
                    requested_resource=getattr(request, "requested_resource", None),
                    analysis_session_id=analysis_session_id,
                )
            return _job_response(job)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "UPLOAD_NOT_FOUND"}) from exc
        except JobSubmissionError as exc:
            raise HTTPException(status_code=exc.status_code, detail=_job_submission_error_detail(exc)) from exc

    @app.get("/api/example-assets")
    def list_example_assets(x_spashiny_session: str | None = Header(default=None, alias="X-SpaShiny-Session")):
        _active_session(x_spashiny_session)
        try:
            return {
                "asset_version": example_assets.asset_version,
                "manifest_version": example_assets.load_manifest().get("manifest_version"),
                "manifest_key": example_assets.manifest_key,
                "asset_count": len(example_assets.ui_rows()),
                "assets": example_assets.ui_rows(),
                "by_modality": example_assets.group_by_modality(),
                "by_sample": example_assets.group_by_sample(),
            }
        except ExampleAssetError as exc:
            _asset_error(exc)

    @app.get("/api/example-asset-references")
    def list_example_asset_references(x_spashiny_session: str | None = Header(default=None, alias="X-SpaShiny-Session")):
        session = _authenticate_session(x_spashiny_session)
        return example_references.list_public(session.session_id)

    @app.post("/api/example-asset-references")
    def create_example_asset_reference(
        request: CreateExampleAssetReferenceRequest,
        x_spashiny_session: str | None = Header(default=None, alias="X-SpaShiny-Session"),
    ):
        session = _active_session(x_spashiny_session)
        try:
            return example_references.create(
                session=session,
                asset_id=getattr(request, "asset_id", None),
                asset_object_key=getattr(request, "asset_object_key", None),
            )
        except ExampleAssetReferenceError as exc:
            _reference_error(exc)

    @app.post("/api/example-actions/{action_id}/activate")
    def activate_example_action(
        action_id: str,
        request: ActivateExampleActionRequest,
        x_spashiny_session: str | None = Header(default=None, alias="X-SpaShiny-Session"),
        x_spashiny_analysis_session: str | None = Header(default=None, alias="X-SpaShiny-Analysis-Session"),
    ):
        session = _active_session(x_spashiny_session)
        analysis_session_id = _require_current_analysis_session(session.session_id, x_spashiny_analysis_session)
        try:
            return example_actions.activate(
                session=session,
                analysis_session_id=analysis_session_id,
                action_id=action_id,
                page_name=str(getattr(request, "page_name", "") or ""),
            )
        except ExampleActionError as exc:
            _example_action_error(exc)
        except ExampleAssetError as exc:
            _asset_error(exc)

    @app.post("/api/example-assets/presign")
    def presign_example_assets(
        request: PresignExampleAssetRequest,
        x_spashiny_session: str | None = Header(default=None, alias="X-SpaShiny-Session"),
    ):
        _active_session(x_spashiny_session)
        if sessions.config.is_lab_profile:
            raise HTTPException(status_code=410, detail={"code": "LAB_PRESIGNED_URL_DISABLED"})
        try:
            assets = example_assets.resolve_selection(list(request.object_keys or []))
            return {
                "asset_version": example_assets.asset_version,
                "expires_in": int(sessions.config.r2_presigned_url_ttl_seconds),
                "urls": [
                    {
                        "object_key": asset.object_key,
                        "url": example_assets.presign_get_url(asset.object_key),
                        "size_bytes": asset.size_bytes,
                        "sha256": asset.sha256,
                    }
                    for asset in assets
                ],
            }
        except ExampleAssetError as exc:
            _asset_error(exc)

    @app.post("/api/jobs/from-example-assets")
    def submit_job_from_example_assets(
        request: SubmitAssetJobRequest,
        x_spashiny_session: str | None = Header(default=None, alias="X-SpaShiny-Session"),
        x_spashiny_analysis_session: str | None = Header(default=None, alias="X-SpaShiny-Analysis-Session"),
    ):
        session = _active_session(x_spashiny_session)
        analysis_session_id = _require_current_analysis_session(session.session_id, x_spashiny_analysis_session)
        if getattr(request, "asset_object_key", None) or getattr(request, "asset_object_keys", None):
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "INVALID_ASSET_REFERENCE",
                    "message": "Use asset_reference_ids created by /api/example-asset-references.",
                },
            )
        try:
            job = submissions.submit_with_asset_references(
                session=session,
                workflow_name=request.workflow_name,
                asset_reference_ids=list(getattr(request, "asset_reference_ids", None) or []),
                parameters=getattr(request, "parameters", None) or {},
                requested_resource=getattr(request, "requested_resource", None),
                analysis_session_id=analysis_session_id,
            )
            return _job_response(job)
        except JobSubmissionError as exc:
            raise HTTPException(status_code=exc.status_code, detail=_job_submission_error_detail(exc)) from exc

    @app.get("/api/jobs")
    def list_session_jobs(
        x_spashiny_session: str | None = Header(default=None, alias="X-SpaShiny-Session"),
        x_spashiny_analysis_session: str | None = Header(default=None, alias="X-SpaShiny-Analysis-Session"),
    ):
        session = _authenticate_session(x_spashiny_session)
        analysis_session_id = _require_current_analysis_session(session.session_id, x_spashiny_analysis_session)
        return [
            _job_response(job)
            for job in jobs.list_jobs_for_session(
                session.session_id, analysis_session_id=analysis_session_id, limit=100
            )
        ]

    @app.get("/api/jobs/{job_id}")
    def get_session_job(
        job_id: str,
        x_spashiny_session: str | None = Header(default=None, alias="X-SpaShiny-Session"),
        x_spashiny_analysis_session: str | None = Header(default=None, alias="X-SpaShiny-Analysis-Session"),
    ):
        session = _authenticate_session(x_spashiny_session)
        analysis_session_id = _require_current_analysis_session(session.session_id, x_spashiny_analysis_session)
        try:
            return _job_response(
                jobs.get_job_for_session(
                    session.session_id, job_id, analysis_session_id=analysis_session_id
                )
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "JOB_NOT_FOUND"}) from exc

    @app.get("/api/jobs/{job_id}/worker-input-plan")
    def get_worker_input_plan(
        job_id: str,
        x_spashiny_worker: str | None = Header(default=None, alias="X-SpaShiny-Worker"),
        x_spashiny_claim_token: str | None = Header(default=None, alias="X-SpaShiny-Claim-Token"),
    ):
        worker_id = str(x_spashiny_worker or "").strip()
        claim_token = str(x_spashiny_claim_token or "").strip()
        if not worker_id or not claim_token:
            raise HTTPException(status_code=401, detail={"code": "WORKER_CLAIM_REQUIRED"})
        try:
            job = jobs.database.get_job(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "JOB_NOT_FOUND"}) from exc
        if job.worker_id != worker_id or job.claim_token != claim_token:
            raise HTTPException(status_code=403, detail={"code": "WORKER_CLAIM_NOT_ALLOWED"})
        try:
            return input_resolver.resolve_for_worker(job)
        except ExampleAssetError as exc:
            _asset_error(exc)
        except InputResolverError as exc:
            raise HTTPException(status_code=409, detail={"code": "INPUT_RESOLUTION_FAILED", "message": str(exc)}) from exc

    @app.get("/api/jobs/{job_id}/worker-job-spec")
    def get_worker_job_spec(job_id: str, token: str = ""):
        if not str(token or "").strip():
            raise HTTPException(status_code=401, detail={"code": "WORKER_JOB_SPEC_TOKEN_REQUIRED"})
        try:
            job = jobs.database.get_job(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "JOB_NOT_FOUND"}) from exc
        try:
            callback_expires_at = verify_worker_job_spec_token(token, job, config=sessions.config)
            return input_resolver.resolve_for_worker(job, callback_expires_at=callback_expires_at)
        except ExampleAssetError as exc:
            _asset_error(exc)
        except InputResolverError as exc:
            raise HTTPException(status_code=403, detail={"code": "WORKER_JOB_SPEC_TOKEN_INVALID", "message": str(exc)}) from exc

    @app.post("/api/jobs/{job_id}/worker-callback")
    def worker_callback(
        job_id: str,
        request: WorkerCallbackRequest,
        x_spashiny_worker: str | None = Header(default=None, alias="X-SpaShiny-Worker"),
        x_spashiny_callback_token: str | None = Header(default=None, alias="X-SpaShiny-Callback-Token"),
    ):
        worker_id = str(x_spashiny_worker or "").strip()
        callback_token = str(x_spashiny_callback_token or "").strip()
        if not worker_id or not callback_token:
            raise HTTPException(status_code=401, detail={"code": "WORKER_CALLBACK_AUTH_REQUIRED"})
        payload = request.model_dump() if hasattr(request, "model_dump") else dict(request.__dict__)
        try:
            job = worker_callbacks.handle_callback(
                job_id=job_id,
                worker_id=worker_id,
                callback_token=callback_token,
                payload=payload,
            )
            return _job_response(job)
        except WorkerCallbackError as exc:
            raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)}) from exc

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_session_job(
        job_id: str,
        x_spashiny_session: str | None = Header(default=None, alias="X-SpaShiny-Session"),
        x_spashiny_analysis_session: str | None = Header(default=None, alias="X-SpaShiny-Analysis-Session"),
    ):
        session = _authenticate_session(x_spashiny_session)
        analysis_session_id = _require_current_analysis_session(session.session_id, x_spashiny_analysis_session)
        try:
            jobs.get_job_for_session(
                session.session_id, job_id, analysis_session_id=analysis_session_id
            )
            return _job_response(job_queue.request_cancel(session.session_id, job_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "JOB_NOT_FOUND"}) from exc

    @app.get("/api/queue/status")
    def get_queue_status(
        x_spashiny_session: str | None = Header(default=None, alias="X-SpaShiny-Session"),
        x_spashiny_analysis_session: str | None = Header(default=None, alias="X-SpaShiny-Analysis-Session"),
    ):
        session = _authenticate_session(x_spashiny_session)
        analysis_session_id = _require_current_analysis_session(session.session_id, x_spashiny_analysis_session)
        status = job_queue.queue_status(session.session_id)
        session_jobs = jobs.list_jobs_for_session(
            session.session_id, analysis_session_id=analysis_session_id, limit=100
        )
        queued = [
            job for job in session_jobs
            if job.status in {"QUEUED_CPU", "QUEUED_GPU"}
        ]
        status["current_job_queue_position"] = 1 if queued else None
        status["gpu_budget_limit_reached"] = False if sessions.config.is_lab_profile else sessions.config.daily_gpu_budget_usd <= 0
        return status

    @app.get("/api/uploads/{upload_id}/download")
    def download_upload(upload_id: str, x_spashiny_session: str | None = Header(default=None, alias="X-SpaShiny-Session"), x_spashiny_analysis_session: str | None = Header(default=None, alias="X-SpaShiny-Analysis-Session")):
        session = _authenticate_session(x_spashiny_session)
        analysis_session_id = _require_current_analysis_session(session.session_id, x_spashiny_analysis_session)
        try:
            return uploads.download_upload(session=session, analysis_session_id=analysis_session_id, upload_id=upload_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "UPLOAD_NOT_FOUND"}) from exc
        except UploadValidationError as exc:
            _upload_error(exc)

    @app.delete("/api/uploads/{upload_id}")
    def delete_upload(upload_id: str, x_spashiny_session: str | None = Header(default=None, alias="X-SpaShiny-Session"), x_spashiny_analysis_session: str | None = Header(default=None, alias="X-SpaShiny-Analysis-Session")):
        session = _authenticate_session(x_spashiny_session)
        analysis_session_id = _require_current_analysis_session(session.session_id, x_spashiny_analysis_session)
        try:
            return _upload_response(uploads.delete_upload(session=session, analysis_session_id=analysis_session_id, upload_id=upload_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "UPLOAD_NOT_FOUND"}) from exc

    @app.post("/jobs/conditional-vae")
    def submit_conditional_vae(
        request: SubmitConditionalVAERequest,
        x_spashiny_session: str | None = Header(default=None, alias="X-SpaShiny-Session"),
    ):
        if sessions.config.is_lab_profile:
            raise HTTPException(status_code=410, detail={"code": "LEGACY_JOB_ENDPOINT_DISABLED_IN_LAB"})
        try:
            if x_spashiny_session:
                session = _authenticate_session(x_spashiny_session)
                job = jobs.create_job_for_session(
                    session.session_id,
                    workflow=ST_SM_CONDITIONAL_VAE,
                    parameters=request.parameters,
                    input_h5ad=Path(request.input_h5ad),
                )
            else:
                user = require_user(request.user_id)
                job = jobs.create_gpu_job(
                    user_id=user.user_id,
                    workflow=ST_SM_CONDITIONAL_VAE,
                    parameters=request.parameters,
                    input_h5ad=Path(request.input_h5ad),
                )
            queue.submit_gpu_job(job.job_id, run_inline=request.run_inline)
            return job.to_dict()
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/jobs/{job_id}")
    def get_job(
        job_id: str,
        user_id: str | None = None,
        x_spashiny_session: str | None = Header(default=None, alias="X-SpaShiny-Session"),
    ):
        try:
            if x_spashiny_session:
                session = _authenticate_session(x_spashiny_session)
                return jobs.get_job_for_session(session.session_id, job_id).to_dict()
            user = require_user(user_id)
            return jobs.get_job(job_id, user_id=user.user_id).to_dict()
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return app


app = create_app()
if not callable(app):
    raise RuntimeError("cloud.api:app initialization failed: ASGI application is not callable")
