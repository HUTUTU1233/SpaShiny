from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlsplit
from urllib.request import Request, urlopen


class WorkerIOError(RuntimeError):
    pass


def fetch_worker_input_plan(
    *,
    control_api_base_url: str,
    job_id: str,
    worker_id: str,
    claim_token: str,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    base = str(control_api_base_url or "").strip().rstrip("/")
    if not base:
        raise WorkerIOError("SPASHINY_CONTROL_API_BASE_URL is required for worker input plans.")
    if not worker_id or not claim_token:
        raise WorkerIOError("Worker id and claim token are required for worker input plans.")
    url = f"{base}/api/jobs/{quote(str(job_id), safe='')}/worker-input-plan"
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "X-SpaShiny-Worker": str(worker_id),
            "X-SpaShiny-Claim-Token": str(claim_token),
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=int(timeout_seconds)) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise WorkerIOError(f"Control plane rejected worker input plan request: HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise WorkerIOError(f"Could not load worker input plan: {type(exc).__name__}.") from exc
    if not isinstance(payload, dict):
        raise WorkerIOError("Worker input plan response must be a JSON object.")
    if not isinstance(payload.get("assets"), list):
        raise WorkerIOError("Worker input plan response is missing the assets list.")
    return payload


def download_worker_input_assets(
    plan: dict[str, Any],
    target_dir: Path,
    *,
    timeout_seconds: int = 60,
) -> list[dict[str, Any]]:
    target = Path(str(plan.get("materialized_input_dir") or "") or target_dir)
    target.mkdir(parents=True, exist_ok=True)
    downloaded: list[dict[str, Any]] = []
    assets = plan.get("assets")
    if not isinstance(assets, list):
        raise WorkerIOError("Worker input plan assets must be a list.")
    for index, item in enumerate(assets):
        if not isinstance(item, dict):
            raise WorkerIOError("Worker input plan contains a malformed asset entry.")
        filename = _safe_filename(str(item.get("filename") or ""), fallback=f"asset-{index + 1}.bin")
        local_path = str(item.get("local_path") or "").strip()
        if local_path:
            downloaded.append(_bind_local_asset(local_path, item, filename=filename))
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            raise WorkerIOError(f"Worker input asset {filename} is missing a download URL.")
        local_path = target / filename
        metadata = _download_one(url, local_path, item, timeout_seconds=timeout_seconds)
        downloaded.append(metadata)
    return downloaded


def write_sanitized_input_manifest(
    *,
    workspace: Path,
    plan: dict[str, Any],
    downloaded: list[dict[str, Any]],
) -> Path:
    manifest = {
        "job_id": plan.get("job_id"),
        "session_id": plan.get("session_id"),
        "analysis_session_id": plan.get("analysis_session_id"),
        "input_source": plan.get("input_source"),
        "manifest_version": plan.get("manifest_version"),
        "materialized_input_dir": plan.get("materialized_input_dir"),
        "assets": downloaded,
    }
    input_dir = Path(str(plan.get("materialized_input_dir") or "") or (Path(workspace) / "input"))
    path = input_dir / "worker_input_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
    return path


def build_input_files(downloaded: list[dict[str, Any]]) -> dict[str, str]:
    files = {f"asset_{index + 1}": str(item["path"]) for index, item in enumerate(downloaded) if item.get("path")}
    if downloaded and downloaded[0].get("path"):
        files.setdefault("primary", str(downloaded[0]["path"]))
        files.setdefault("joint_h5ad", str(downloaded[0]["path"]))
    return files


def _bind_local_asset(local_path: str, item: dict[str, Any], *, filename: str) -> dict[str, Any]:
    source = Path(local_path).resolve()
    if not source.is_file():
        raise WorkerIOError(f"Worker input asset {filename} is missing from local examples storage.")
    size = source.stat().st_size
    expected_size = item.get("size_bytes")
    if expected_size not in (None, "") and int(expected_size) >= 0 and size != int(expected_size):
        raise WorkerIOError(f"Local worker input asset {filename} has an unexpected size.")
    expected_sha256 = str(item.get("sha256") or "").strip().lower()
    actual_sha256 = expected_sha256 or ""
    if expected_sha256:
        actual_sha256 = _sha256_file(source)
        if actual_sha256.lower() != expected_sha256:
            raise WorkerIOError(f"Local worker input asset {filename} failed SHA256 validation.")
    return {
        "object_key": str(item.get("object_key") or ""),
        "filename": filename,
        "path": str(source),
        "size_bytes": size,
        "sha256": actual_sha256,
        "content_type": str(item.get("content_type") or ""),
        "source": str(item.get("source") or "local_example_asset"),
        "role": str(item.get("role") or ""),
        "sample_id": str(item.get("sample_id") or ""),
        "read_only": bool(item.get("read_only", True)),
    }


def _download_one(url: str, local_path: Path, item: dict[str, Any], *, timeout_seconds: int) -> dict[str, Any]:
    tmp_path = local_path.with_name(local_path.name + ".part")
    if str(url or "").startswith("local-temp://download/"):
        source = _local_temp_object_path(url)
        if source is None or not source.is_file():
            raise WorkerIOError(f"Worker input asset {local_path.name} is missing from local object storage.")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, tmp_path)
        size = tmp_path.stat().st_size
        actual_sha256 = _sha256_file(tmp_path)
        expected_sha256 = str(item.get("sha256") or "").strip().lower()
        if expected_sha256 and actual_sha256.lower() != expected_sha256:
            tmp_path.unlink(missing_ok=True)
            raise WorkerIOError(f"Downloaded worker input asset {local_path.name} failed SHA256 validation.")
        tmp_path.replace(local_path)
        return {
            "object_key": str(item.get("object_key") or ""),
            "filename": local_path.name,
            "path": str(local_path),
            "size_bytes": size,
            "sha256": actual_sha256,
            "content_type": str(item.get("content_type") or ""),
        }
    digest = hashlib.sha256()
    size = 0
    try:
        with urlopen(url, timeout=int(timeout_seconds)) as response, tmp_path.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                digest.update(chunk)
                handle.write(chunk)
    except Exception as exc:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise WorkerIOError(f"Could not download worker input asset {local_path.name}: {type(exc).__name__}.") from exc
    expected_size = item.get("size_bytes")
    if expected_size not in (None, "") and int(expected_size) >= 0 and size != int(expected_size):
        tmp_path.unlink(missing_ok=True)
        raise WorkerIOError(f"Downloaded worker input asset {local_path.name} has an unexpected size.")
    actual_sha256 = digest.hexdigest()
    expected_sha256 = str(item.get("sha256") or "").strip().lower()
    if expected_sha256 and actual_sha256.lower() != expected_sha256:
        tmp_path.unlink(missing_ok=True)
        raise WorkerIOError(f"Downloaded worker input asset {local_path.name} failed SHA256 validation.")
    tmp_path.replace(local_path)
    return {
        "object_key": str(item.get("object_key") or ""),
        "filename": local_path.name,
        "path": str(local_path),
        "size_bytes": size,
        "sha256": actual_sha256,
        "content_type": str(item.get("content_type") or ""),
    }


def _safe_filename(value: str, *, fallback: str) -> str:
    candidate = Path(value.strip()).name
    if not candidate or candidate in {".", ".."}:
        candidate = fallback
    if "/" in candidate or "\\" in candidate or candidate in {".", ".."}:
        raise WorkerIOError("Worker input asset filename is not safe.")
    return candidate


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _local_temp_object_path(url: str) -> Path | None:
    parsed = urlsplit(str(url or ""))
    if parsed.scheme != "local-temp":
        return None
    path = parsed.path.strip("/")
    if parsed.netloc == "download":
        object_key = unquote(path).replace("\\", "/").strip("/")
    elif path.startswith("download/"):
        object_key = unquote(path[len("download/"):]).replace("\\", "/").strip("/")
    else:
        return None
    if not object_key or ".." in Path(object_key).parts:
        return None
    root = Path(os.environ.get("SPASHINY_LOCAL_OBJECT_ROOT") or "/workspace/data/sessions").resolve()
    candidate = (root / object_key).resolve()
    if candidate != root and root in candidate.parents:
        return candidate
    return None
