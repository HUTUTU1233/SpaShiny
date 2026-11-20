from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
import zipfile

from .config import SpaShinyCloudConfig, load_cloud_config
from .models import JobRecord
from .object_keys import ObjectKeyBuilder
from .r2_client import create_r2_client
from .storage import WorkspaceStorage


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ResultPublisher:
    def __init__(self, *, config: SpaShinyCloudConfig | None = None, storage: WorkspaceStorage | None = None, client: Any | None = None) -> None:
        self.config = config or load_cloud_config()
        self.storage = storage or WorkspaceStorage(self.config)
        self.client = client

    def publish(self, job: JobRecord) -> dict[str, Any]:
        job_root = self._job_root(job)
        self._write_job_log(job, job_root)
        result_zip = self._package_results_zip(job_root)
        archive_sha256 = sha256_file(result_zip)
        sha_path = job_root / "results.zip.sha256"
        sha_path.write_text(f"{archive_sha256}  results.zip\n", encoding="utf-8")
        file_entries = self._file_entries(job_root)
        plots = self._plot_entries(file_entries)
        downloads = self._download_entries(job_root, file_entries, result_zip, sha_path)
        manifest = {
            "job_id": job.job_id,
            "session_id": job.session_id,
            "workflow": job.workflow_name or job.workflow,
            "job_status": job.status,
            "status": "completed",
            "archive": {
                "filename": "results.zip",
                "path": "results.zip",
                "size_bytes": result_zip.stat().st_size,
                "sha256": archive_sha256,
            },
            "expected_outputs": self._expected_outputs(job),
            "files": file_entries,
            "plots": plots,
            "downloads": downloads,
        }
        manifest_path = job_root / "result_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
        published = {
            "archive_path": str(result_zip),
            "manifest_path": str(manifest_path),
            "sha256_path": str(sha_path),
            "sha256": archive_sha256,
            "r2_uploaded": False,
            "objects": [],
        }
        if str(self.config.storage_backend or "").lower() == "r2":
            published.update(self._upload_runtime_results(job, result_zip, manifest_path, sha_path, archive_sha256))
        return published

    def _upload_runtime_results(self, job: JobRecord, result_zip: Path, manifest_path: Path, sha_path: Path, archive_sha256: str) -> dict[str, Any]:
        bucket = self.config.require_r2_runtime_config()
        client = self.client or create_r2_client(self.config)
        prefix = (job.output_prefix or ObjectKeyBuilder.result_prefix(str(job.session_id or job.user_id), job.job_id)).strip("/")
        objects = [
            (f"{prefix}/results.zip", result_zip, "application/zip"),
            (f"{prefix}/result_manifest.json", manifest_path, "application/json"),
            (f"{prefix}/results.zip.sha256", sha_path, "text/plain"),
        ]
        uploaded = []
        for object_key, path, content_type in objects:
            key = ObjectKeyBuilder.validate_runtime_key(object_key)
            client.put_object(
                Bucket=bucket,
                Key=key,
                Body=path.read_bytes(),
                ContentType=content_type,
                Metadata={"sha256": sha256_file(path), "job_id": job.job_id},
            )
            uploaded.append(key)
        return {
            "r2_uploaded": True,
            "bucket": bucket,
            "objects": uploaded,
            "archive_sha256": archive_sha256,
        }

    @staticmethod
    def _expected_outputs(job: JobRecord) -> list[str]:
        try:
            metadata = json.loads(job.metadata_json or "{}")
            values = metadata.get("expected_outputs") if isinstance(metadata, dict) else []
            return [str(value) for value in values] if isinstance(values, list) else []
        except Exception:
            return []

    def _job_root(self, job: JobRecord) -> Path:
        if job.local_workspace:
            root = Path(job.local_workspace).resolve()
            root.mkdir(parents=True, exist_ok=True)
            workspace_root = Path(self.config.workspace).resolve()
            temp_root = Path(self.config.temp_root or (self.config.workspace / "temp")).resolve()
            lab_result_root = Path(self.config.lab_result_root).resolve()
            if (
                root != workspace_root
                and workspace_root not in root.parents
                and root != temp_root
                and temp_root not in root.parents
                and root != lab_result_root
                and lab_result_root not in root.parents
            ):
                raise RuntimeError("Job workspace is outside the configured SpaShiny workspace.")
            return root
        return self.storage.job_root(job.user_id, job.job_id)

    def _write_job_log(self, job: JobRecord, job_root: Path) -> Path:
        logs_dir = job_root / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = logs_dir / "job.log"
        lines = [
            f"job_id={job.job_id}",
            f"workflow={job.workflow_name or job.workflow}",
            f"status_at_publication={job.status}",
            f"session_id={job.session_id}",
            f"resource_type={job.resource_type}",
            f"execution_backend={job.execution_backend}",
            f"queue_name={job.queue_name}",
            f"worker_id={job.worker_id}",
            f"created_at={job.created_at}",
            f"queued_at={job.queued_at}",
            f"claimed_at={job.claimed_at}",
            f"started_at={job.started_at}",
            f"current_step={job.current_step}",
        ]
        try:
            from .database import CloudDatabase

            database = CloudDatabase(config=self.config)
            events = database.list_events(job.job_id, limit=500)
            if events:
                lines.append("")
                lines.append("events:")
                for event in events:
                    created_at = str(event.get("created_at") or "")
                    level = str(event.get("level") or "INFO")
                    message = str(event.get("message") or "")
                    lines.append(f"{created_at} [{level}] {message}")
        except Exception as exc:
            lines.append("")
            lines.append(f"event_log_unavailable={type(exc).__name__}: {exc}")
        text = "\n".join(lines).rstrip() + "\n"
        log_path.write_text(text, encoding="utf-8")
        return log_path

    def _package_results_zip(self, job_root: Path) -> Path:
        zip_path = job_root / "results.zip"
        tmp_path = zip_path.with_suffix(".zip.tmp")
        allowed_roots = ("output", "figures", "logs")
        manifest_output_paths = self._manifest_output_paths(job_root)
        archived: set[str] = set()

        def add_file(archive: zipfile.ZipFile, path: Path, arcname: str) -> None:
            rel = self._safe_relative_path(job_root, arcname)
            if not rel or rel in archived:
                return
            if path.name in {"results.zip", "results.zip.tmp"}:
                return
            if path.exists() and path.is_file():
                archive.write(path, rel)
                archived.add(rel)

        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            for root_name in allowed_roots:
                root = job_root / root_name
                if not root.exists():
                    continue
                for path in root.rglob("*"):
                    if path.is_file():
                        add_file(archive, path, path.relative_to(job_root).as_posix())
            for name in (
                "integrated_result.h5ad",
                "model_state.pt",
                "latent.npy",
                "loss_record.json",
                "cluster_statistics.csv",
                "summary.json",
                "manifest.json",
                "result_manifest.json",
                "session_info.txt",
            ):
                path = job_root / name
                add_file(archive, path, path.name)
            for rel in manifest_output_paths:
                add_file(archive, job_root / rel, rel)
        tmp_path.replace(zip_path)
        return zip_path

    def _manifest_output_paths(self, job_root: Path) -> list[str]:
        manifest_path = job_root / "manifest.json"
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            entries = data.get("output_files") if isinstance(data, dict) else []
        except Exception:
            entries = []
        paths: list[str] = []
        if isinstance(entries, list):
            for item in entries:
                if not isinstance(item, dict):
                    continue
                rel = self._safe_relative_path(job_root, str(item.get("path") or ""))
                if rel and rel not in paths:
                    paths.append(rel)
        return paths

    def _file_entries(self, job_root: Path) -> list[dict[str, Any]]:
        manifest_path = job_root / "manifest.json"
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            entries = data.get("output_files") if isinstance(data, dict) else []
        except Exception:
            entries = []
        files: list[dict[str, Any]] = []
        seen: set[str] = set()
        if isinstance(entries, list):
            for item in entries:
                if not isinstance(item, dict):
                    continue
                rel = self._safe_relative_path(job_root, str(item.get("path") or ""))
                if not rel or rel in seen:
                    continue
                path = job_root / rel
                if not path.is_file():
                    continue
                files.append(
                    {
                        "path": rel,
                        "name": path.name,
                        "size_bytes": int(item.get("size_bytes") or path.stat().st_size),
                        "sha256": str(item.get("sha256") or sha256_file(path)),
                    }
                )
                seen.add(rel)
        for path in sorted(job_root.rglob("*")):
            if not path.is_file():
                continue
            rel = self._safe_relative_path(job_root, path.relative_to(job_root).as_posix())
            if not rel or rel in seen:
                continue
            if rel.endswith(".tmp"):
                continue
            files.append({"path": rel, "name": path.name, "size_bytes": path.stat().st_size, "sha256": sha256_file(path)})
            seen.add(rel)
        return files

    def _plot_entries(self, file_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        plots: list[dict[str, Any]] = []
        for item in file_entries:
            rel = str(item.get("path") or "")
            suffix = Path(rel).suffix.lower()
            if not rel.startswith("figures/") or suffix not in {".png", ".jpg", ".jpeg", ".svg", ".pdf"}:
                continue
            plots.append(
                {
                    "name": self._display_name(Path(rel).stem),
                    "path": rel,
                    "size_bytes": int(item.get("size_bytes") or 0),
                    "sha256": str(item.get("sha256") or ""),
                }
            )
        return plots

    def _download_entries(self, job_root: Path, file_entries: list[dict[str, Any]], result_zip: Path, sha_path: Path) -> list[dict[str, Any]]:
        downloads = [
            {
                "name": "Download Result ZIP",
                "path": "results.zip",
                "size_bytes": result_zip.stat().st_size,
                "sha256": sha256_file(result_zip),
            },
            {
                "name": "Download Result ZIP SHA256",
                "path": "results.zip.sha256",
                "size_bytes": sha_path.stat().st_size,
                "sha256": sha256_file(sha_path),
            },
        ]
        for item in file_entries:
            rel = str(item.get("path") or "")
            suffix = Path(rel).suffix.lower()
            if suffix in {".png", ".pdf", ".csv", ".tsv", ".h5ad", ".json", ".txt", ".log"} or rel.startswith("logs/"):
                downloads.append(
                    {
                        "name": self._display_name(Path(rel).stem),
                        "path": rel,
                        "size_bytes": int(item.get("size_bytes") or 0),
                        "sha256": str(item.get("sha256") or ""),
                    }
                )
        return downloads

    @staticmethod
    def _display_name(value: str) -> str:
        text = str(value or "").replace("_", " ").replace("-", " ").strip()
        return " ".join(part.capitalize() for part in text.split()) or "Result"

    @staticmethod
    def _safe_relative_path(root: Path, value: str) -> str:
        raw = str(value or "").strip().replace("\\", "/")
        if not raw or raw.startswith("/") or "\x00" in raw:
            return ""
        try:
            candidate = (root / raw).resolve()
            candidate.relative_to(root.resolve())
        except Exception:
            return ""
        return Path(raw).as_posix()
