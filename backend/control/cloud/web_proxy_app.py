from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Iterable

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
SHINY_APP_PATH = WORKSPACE_ROOT / "app" / "ST-SM.py"
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
    "origin",
    "referer",
}


def _load_shiny_app():
    spec = importlib.util.spec_from_file_location("spashiny_st_sm_app", SHINY_APP_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load Shiny app from {SHINY_APP_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    shiny_app = getattr(module, "app", None)
    if shiny_app is None:
        raise RuntimeError("ST-SM.py did not expose an ASGI app named 'app'.")
    return shiny_app


def _control_api_base() -> str:
    base = (os.environ.get("SPASHINY_CONTROL_API_BASE_URL") or "").strip().rstrip("/")
    if not base:
        raise RuntimeError("SPASHINY_CONTROL_API_BASE_URL is required for /api proxy.")
    return base


def _filtered_request_headers(request: Request) -> dict[str, str]:
    headers: dict[str, str] = {}
    for key, value in request.headers.items():
        lower = key.lower()
        if lower in HOP_BY_HOP_HEADERS or lower.startswith("sec-fetch-"):
            continue
        headers[key] = value
    return headers


def _filtered_response_headers(headers: Iterable[tuple[str, str]]) -> dict[str, str]:
    output: dict[str, str] = {}
    for key, value in headers:
        lower = key.lower()
        if lower in HOP_BY_HOP_HEADERS:
            continue
        output[key] = value
    return output


async def proxy_api(request: Request) -> Response:
    target = _control_api_base() + request.url.path
    if request.url.query:
        target += "?" + request.url.query
    body = await request.body()
    data = body if request.method.upper() not in {"GET", "HEAD"} else None
    upstream = urllib.request.Request(
        target,
        data=data,
        method=request.method,
        headers=_filtered_request_headers(request),
    )
    timeout = float(os.environ.get("SPASHINY_WEB_PROXY_TIMEOUT_SECONDS", "120") or "120")
    try:
        with urllib.request.urlopen(upstream, timeout=timeout) as response:
            payload = response.read()
            return Response(
                payload,
                status_code=int(response.status),
                headers=_filtered_response_headers(response.headers.items()),
            )
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        return Response(
            payload,
            status_code=int(exc.code),
            headers=_filtered_response_headers(exc.headers.items()),
        )
    except Exception as exc:
        return JSONResponse(
            {"detail": {"code": "CONTROL_API_PROXY_FAILED", "message": f"{type(exc).__name__}: {exc}"}},
            status_code=502,
        )


def _embedded_dash_enabled() -> bool:
    return (
        os.environ.get("SPASHINY_ENABLE_EMBEDDED_DASH", "0").strip().lower()
        in {"1", "true", "yes", "on"}
    )


def _dash_proxy_port_bounds() -> tuple[int, int]:
    start = int(os.environ.get("SPASHINY_DASH_PROXY_MIN_PORT", "8050") or "8050")
    end = int(os.environ.get("SPASHINY_DASH_PROXY_MAX_PORT", "8250") or "8250")
    return start, end


async def proxy_dash(request: Request) -> Response:
    if not _embedded_dash_enabled():
        return JSONResponse({"detail": {"code": "DASH_PROXY_DISABLED"}}, status_code=404)
    if not _authenticated_request_session_id(request):
        return JSONResponse({"detail": {"code": "DASH_PROXY_SESSION_REQUIRED"}}, status_code=403)

    try:
        port = int(request.path_params.get("port") or "0")
    except Exception:
        return JSONResponse({"detail": {"code": "DASH_PROXY_INVALID_PORT"}}, status_code=400)
    port_min, port_max = _dash_proxy_port_bounds()
    if port < port_min or port > port_max:
        return JSONResponse(
            {"detail": {"code": "DASH_PROXY_PORT_FORBIDDEN", "min": port_min, "max": port_max}},
            status_code=403,
        )

    expected_prefix = f"/dash-proxy/{port}"
    upstream_path = request.url.path
    if upstream_path != expected_prefix and not upstream_path.startswith(expected_prefix + "/"):
        return JSONResponse({"detail": {"code": "DASH_PROXY_PATH_FORBIDDEN"}}, status_code=403)

    target = f"http://127.0.0.1:{port}{upstream_path}"
    if request.url.query:
        target += "?" + request.url.query
    body = await request.body()
    data = body if request.method.upper() not in {"GET", "HEAD"} else None
    upstream = urllib.request.Request(
        target,
        data=data,
        method=request.method,
        headers=_filtered_request_headers(request),
    )
    timeout = float(os.environ.get("SPASHINY_DASH_PROXY_TIMEOUT_SECONDS", "120") or "120")
    try:
        with urllib.request.urlopen(upstream, timeout=timeout) as response:
            payload = response.read()
            return Response(
                payload,
                status_code=int(response.status),
                headers=_filtered_response_headers(response.headers.items()),
            )
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        return Response(
            payload,
            status_code=int(exc.code),
            headers=_filtered_response_headers(exc.headers.items()),
        )
    except Exception as exc:
        return JSONResponse(
            {"detail": {"code": "DASH_PROXY_UPSTREAM_FAILED", "message": f"{type(exc).__name__}: {exc}"}},
            status_code=502,
        )


def _download_secret() -> str:
    secret = (os.environ.get("SPASHINY_SESSION_HMAC_SECRET") or "").strip()
    if not secret:
        raise RuntimeError("SPASHINY_SESSION_HMAC_SECRET is required for result downloads.")
    return secret


def _expected_signature(
    *, session_id: str, analysis_session_id: str, job_id: str, rel_path: str, expires: str
) -> str:
    payload = "\n".join([session_id, analysis_session_id, job_id, rel_path, expires]).encode("utf-8")
    return hmac.new(_download_secret().encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _expected_alignment_signature(
    *, owner_id: str, analysis_session_id: str, job_id: str, rel_path: str, expires: str
) -> str:
    payload = "\n".join([owner_id, analysis_session_id, job_id, rel_path, expires]).encode("utf-8")
    return hmac.new(_download_secret().encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _safe_rel_path(value: str) -> str:
    raw = str(value or "").strip().replace("\\", "/")
    if not raw or raw.startswith("/") or "\x00" in raw:
        return ""
    parts = [part for part in raw.split("/") if part not in {"", "."}]
    if any(part == ".." for part in parts):
        return ""
    return "/".join(parts)


def _manifest_allowed_paths(root: Path) -> set[str]:
    import json

    allowed = {
        "result_manifest.json",
        "results.zip",
        "results.zip.sha256",
        "summary.json",
        "manifest.json",
        "session_info.txt",
        "logs/stdout.log",
        "logs/stderr.log",
        "logs/job.log",
        "logs/error.log",
    }
    manifest = root / "result_manifest.json"
    if not manifest.is_file():
        return allowed
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception:
        return allowed
    for section in ("downloads", "plots", "files"):
        entries = data.get(section) if isinstance(data, dict) else []
        if not isinstance(entries, list):
            continue
        for item in entries:
            if not isinstance(item, dict):
                continue
            rel = _safe_rel_path(str(item.get("path") or ""))
            if rel:
                allowed.add(rel)
    archive = data.get("archive") if isinstance(data, dict) else {}
    if isinstance(archive, dict):
        rel = _safe_rel_path(str(archive.get("path") or ""))
        if rel:
            allowed.add(rel)
    return allowed


def _local_result_root() -> Path:
    return Path(os.environ.get("SPASHINY_LOCAL_RESULT_ROOT") or os.environ.get("SPASHINY_RESULTS_DIR") or "/workspace/results").resolve()


def _local_jobs_root() -> Path:
    return Path(os.environ.get("SPASHINY_LOCAL_JOBS_ROOT") or os.environ.get("SPASHINY_TEMP_ROOT") or "/workspace/jobs").resolve()


def _authenticated_request_session_id(request: Request) -> str:
    """Return the owner session authenticated by the current HTTP request.

    A signed URL prevents tampering but is not itself authorization.  Images
    and downloads are browser requests, so the HttpOnly lab cookie is used
    here (with the explicit header retained for API-compatible callers).
    """
    from cloud.config import load_cloud_config
    from cloud.session_manager import SessionAuthError, SessionManager

    config = load_cloud_config()
    token = str(request.headers.get("X-SpaShiny-Session") or "").strip()
    if not token:
        token = str(request.cookies.get(config.lab_session_cookie_name) or "").strip()
    if not token:
        return ""
    try:
        return str(SessionManager(config=config).authenticate(token).session_id or "")
    except SessionAuthError:
        return ""


def _authenticated_request_analysis_session_id(request: Request, owner_id: str) -> str:
    """Validate the current analysis workspace in addition to its owner."""
    from cloud.database import CloudDatabase

    cookie_name = str(os.environ.get("SPASHINY_ANALYSIS_SESSION_COOKIE_NAME") or "spashiny_analysis_session").strip()
    analysis_session_id = str(
        request.headers.get("X-SpaShiny-Analysis-Session")
        or request.cookies.get(cookie_name)
        or ""
    ).strip()
    if not analysis_session_id or not re.fullmatch(r"[A-Za-z0-9_.:-]+", analysis_session_id):
        return ""
    try:
        CloudDatabase().get_analysis_session(analysis_session_id, owner_session_id=owner_id)
        return analysis_session_id
    except Exception:
        return ""


async def download_result(request: Request) -> Response:
    try:
        session_id = str(request.query_params.get("session_id") or "")
        analysis_session_id = str(request.query_params.get("analysis_session_id") or "")
        expires = str(request.query_params.get("expires") or "")
        sig = str(request.query_params.get("sig") or "")
        job_id = str(request.path_params.get("job_id") or "")
        rel_path = _safe_rel_path(str(request.path_params.get("artifact") or ""))
        if (
            not re.fullmatch(r"[A-Za-z0-9_.:-]+", job_id or "")
            or not session_id
            or not analysis_session_id
            or not rel_path
        ):
            return JSONResponse({"detail": {"code": "INVALID_DOWNLOAD_REQUEST"}}, status_code=400)
        if int(expires) < int(time.time()):
            return JSONResponse({"detail": {"code": "DOWNLOAD_LINK_EXPIRED"}}, status_code=403)
        expected = _expected_signature(
            session_id=session_id,
            analysis_session_id=analysis_session_id,
            job_id=job_id,
            rel_path=rel_path,
            expires=expires,
        )
        if not hmac.compare_digest(expected, sig):
            return JSONResponse({"detail": {"code": "DOWNLOAD_SIGNATURE_INVALID"}}, status_code=403)
        if _authenticated_request_session_id(request) != session_id:
            return JSONResponse({"detail": {"code": "CURRENT_SESSION_FORBIDDEN"}}, status_code=403)
        if _authenticated_request_analysis_session_id(request, session_id) != analysis_session_id:
            return JSONResponse({"detail": {"code": "CURRENT_ANALYSIS_FORBIDDEN"}}, status_code=403)

        from cloud.job_manager import JobManager

        job = JobManager().assert_job_owner(
            session_id, job_id, analysis_session_id=analysis_session_id
        )
        root = Path(str(job.local_workspace or "")).resolve()
        if not root.exists():
            return JSONResponse({"detail": {"code": "RESULT_ROOT_MISSING"}}, status_code=404)
        if rel_path not in _manifest_allowed_paths(root):
            return JSONResponse({"detail": {"code": "RESULT_ARTIFACT_NOT_ALLOWLISTED"}}, status_code=403)
        target = (root / rel_path).resolve()
        if root != target and root not in target.parents:
            return JSONResponse({"detail": {"code": "RESULT_PATH_FORBIDDEN"}}, status_code=403)
        if not target.is_file():
            return JSONResponse({"detail": {"code": "RESULT_ARTIFACT_MISSING"}}, status_code=404)
        media_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        # Signed image previews use the identical ownership and manifest checks
        # as downloads, but must be served inline so an <img> element can render
        # the worker-owned PNG instead of triggering a browser download.
        inline = str(request.query_params.get("inline") or "") == "1"
        return FileResponse(
            target,
            media_type=media_type,
            filename=None if inline else target.name,
            headers={"X-SpaShiny-Download": "result-artifact"},
        )
    except KeyError:
        return JSONResponse({"detail": {"code": "JOB_NOT_FOUND"}}, status_code=404)
    except Exception as exc:
        return JSONResponse(
            {"detail": {"code": "RESULT_DOWNLOAD_FAILED", "message": f"{type(exc).__name__}: {exc}"}},
            status_code=500,
        )


async def download_alignment_artifact(request: Request) -> Response:
    try:
        owner_id = str(request.path_params.get("owner_id") or "")
        analysis_session_id = str(request.path_params.get("analysis_session_id") or "")
        job_id = str(request.path_params.get("job_id") or "")
        rel_path = _safe_rel_path(str(request.path_params.get("artifact") or ""))
        expires = str(request.query_params.get("expires") or "")
        sig = str(request.query_params.get("sig") or "")
        safe_segment = r"[A-Za-z0-9_.:-]+"
        if (
            not re.fullmatch(safe_segment, owner_id or "")
            or not re.fullmatch(safe_segment, analysis_session_id or "")
            or not re.fullmatch(safe_segment, job_id or "")
            or not rel_path
        ):
            return JSONResponse({"detail": {"code": "INVALID_ALIGNMENT_ARTIFACT_REQUEST"}}, status_code=400)
        if int(expires) < int(time.time()):
            return JSONResponse({"detail": {"code": "ALIGNMENT_ARTIFACT_LINK_EXPIRED"}}, status_code=403)
        expected = _expected_alignment_signature(
            owner_id=owner_id,
            analysis_session_id=analysis_session_id,
            job_id=job_id,
            rel_path=rel_path,
            expires=expires,
        )
        if not hmac.compare_digest(expected, sig):
            return JSONResponse({"detail": {"code": "ALIGNMENT_ARTIFACT_SIGNATURE_INVALID"}}, status_code=403)
        if _authenticated_request_session_id(request) != owner_id:
            return JSONResponse({"detail": {"code": "ALIGNMENT_CURRENT_SESSION_FORBIDDEN"}}, status_code=403)
        if _authenticated_request_analysis_session_id(request, owner_id) != analysis_session_id:
            return JSONResponse({"detail": {"code": "ALIGNMENT_CURRENT_ANALYSIS_FORBIDDEN"}}, status_code=403)

        jobs_root = _local_jobs_root()
        job_path = (jobs_root / job_id / "job.json").resolve()
        if jobs_root != job_path and jobs_root not in job_path.parents:
            return JSONResponse({"detail": {"code": "ALIGNMENT_JOB_PATH_FORBIDDEN"}}, status_code=403)
        try:
            job = json.loads(job_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return JSONResponse({"detail": {"code": "ALIGNMENT_JOB_NOT_FOUND"}}, status_code=404)
        except Exception:
            return JSONResponse({"detail": {"code": "ALIGNMENT_JOB_METADATA_INVALID"}}, status_code=403)
        if not isinstance(job, dict) or (
            str(job.get("job_id") or "") != job_id
            or str(job.get("owner_id") or "") != owner_id
            or str(job.get("analysis_session_id") or "") != analysis_session_id
        ):
            return JSONResponse({"detail": {"code": "ALIGNMENT_JOB_OWNERSHIP_FORBIDDEN"}}, status_code=403)

        result_root = _local_result_root()
        root = (result_root / "sessions" / "owners" / owner_id / "analysis_sessions" / analysis_session_id / job_id).resolve()
        if result_root != root and result_root not in root.parents:
            return JSONResponse({"detail": {"code": "ALIGNMENT_RESULT_ROOT_FORBIDDEN"}}, status_code=403)
        if Path(str(job.get("output_dir") or "")).resolve() != root:
            return JSONResponse({"detail": {"code": "ALIGNMENT_RESULT_OWNERSHIP_FORBIDDEN"}}, status_code=403)
        if not root.exists():
            return JSONResponse({"detail": {"code": "ALIGNMENT_RESULT_ROOT_MISSING"}}, status_code=404)
        if rel_path not in _manifest_allowed_paths(root):
            return JSONResponse({"detail": {"code": "ALIGNMENT_ARTIFACT_NOT_ALLOWLISTED"}}, status_code=403)
        target = (root / rel_path).resolve()
        if root != target and root not in target.parents:
            return JSONResponse({"detail": {"code": "ALIGNMENT_ARTIFACT_PATH_FORBIDDEN"}}, status_code=403)
        if not target.is_file():
            return JSONResponse({"detail": {"code": "ALIGNMENT_ARTIFACT_MISSING"}}, status_code=404)
        media_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        return FileResponse(
            target,
            media_type=media_type,
            filename=target.name,
            headers={"X-SpaShiny-Download": "alignment-artifact"},
        )
    except Exception as exc:
        return JSONResponse(
            {"detail": {"code": "ALIGNMENT_ARTIFACT_DOWNLOAD_FAILED", "message": f"{type(exc).__name__}: {exc}"}},
            status_code=500,
        )


async def healthz(_request: Request) -> Response:
    """Lightweight liveness probe for the already-started Web proxy.

    This deliberately performs no database, Shiny-session, artifact, or model
    operation. Docker uses it only to determine whether the ASGI process can
    respond to an HTTP request.
    """
    return JSONResponse({"status": "ok"})


shiny_app = _load_shiny_app()
app = Starlette(
    routes=[
        Route("/healthz", healthz, methods=["GET"]),
        Route("/api/{path:path}", proxy_api, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]),
        Route("/dash-proxy/{port:int}", proxy_dash, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]),
        Route("/dash-proxy/{port:int}/{path:path}", proxy_dash, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]),
        Route("/lab-result-download/{job_id}/{artifact:path}", download_result, methods=["GET"]),
        Route("/lab-alignment-artifact/{owner_id}/{analysis_session_id}/{job_id}/{artifact:path}", download_alignment_artifact, methods=["GET"]),
        Mount("/", app=shiny_app),
    ]
)
