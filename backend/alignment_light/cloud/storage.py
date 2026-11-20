from __future__ import annotations

import json
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any

from .config import SpaShinyCloudConfig, load_cloud_config


class StorageError(RuntimeError):
    """Raised when a user workspace or result path is invalid."""


def safe_name(value: str, fallback: str = "item") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    cleaned = cleaned.strip("._")
    return cleaned[:120] or fallback


class WorkspaceStorage:
    def __init__(self, config: SpaShinyCloudConfig | None = None) -> None:
        self.config = config or load_cloud_config()
        self.root = self.config.workspace

    def user_root(self, user_id: str) -> Path:
        path = self.root / "users" / safe_name(user_id, "default")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def job_root(self, user_id: str, job_id: str) -> Path:
        path = self.user_root(user_id) / "jobs" / safe_name(job_id, "job")
        path.mkdir(parents=True, exist_ok=True)
        self.ensure_within_user(user_id, path)
        return path

    def ensure_within_user(self, user_id: str, path: Path) -> Path:
        user_root = self.user_root(user_id).resolve()
        resolved = Path(path).resolve()
        if resolved != user_root and user_root not in resolved.parents:
            raise StorageError(f"Path is outside the user's workspace: {path}")
        return resolved

    def write_json(self, user_id: str, job_id: str, name: str, data: dict[str, Any]) -> Path:
        path = self.job_root(user_id, job_id) / safe_name(name, "data.json")
        self.ensure_within_user(user_id, path)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return path

    def package_results_zip(self, user_id: str, job_id: str) -> Path:
        job_dir = self.job_root(user_id, job_id)
        zip_path = job_dir / "results.zip"
        tmp_path = zip_path.with_suffix(".zip.tmp")
        allowed_roots = ["output", "figures", "logs"]
        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            for root_name in allowed_roots:
                root = job_dir / root_name
                if not root.exists():
                    continue
                for path in root.rglob("*"):
                    if path.is_file():
                        archive.write(path, path.relative_to(job_dir).as_posix())
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
                path = job_dir / name
                if path.exists() and path.is_file():
                    archive.write(path, path.name)
        tmp_path.replace(zip_path)
        return zip_path

    def remove_job(self, user_id: str, job_id: str) -> None:
        job_dir = self.job_root(user_id, job_id)
        self.ensure_within_user(user_id, job_dir)
        shutil.rmtree(job_dir)
