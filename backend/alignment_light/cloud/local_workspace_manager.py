from __future__ import annotations

import shutil
import time
from pathlib import Path

from .config import SpaShinyCloudConfig, load_cloud_config
from .storage import safe_name


class LocalWorkspaceError(RuntimeError):
    """Raised when a local temporary workspace path is outside the controlled root."""


class LocalWorkspaceManager:
    def __init__(self, config: SpaShinyCloudConfig | None = None, root: Path | None = None) -> None:
        self.config = config or load_cloud_config()
        self.root = Path(root or self.config.temp_root or (self.config.workspace / "temp")).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)

    def session_workspace(self, session_id: str, *, create: bool = True) -> Path:
        return self._workspace("sessions", session_id, create=create)

    def job_workspace(self, job_id: str, *, create: bool = True) -> Path:
        return self._workspace("jobs", job_id, create=create)

    def delete_session_workspace(self, session_id: str) -> bool:
        return self._delete(self.session_workspace(session_id, create=False))

    def delete_job_workspace(self, job_id: str) -> bool:
        return self._delete(self.job_workspace(job_id, create=False))

    def delete_controlled_path(self, path: str | Path) -> bool:
        target = self._ensure_within_root(Path(path))
        return self._delete(target)

    def scan_orphan_workspaces(
        self,
        *,
        valid_session_ids: set[str],
        valid_job_ids: set[str],
        min_age_seconds: int,
        now: float | None = None,
    ) -> list[str]:
        now = time.time() if now is None else float(now)
        removed: list[str] = []
        for kind, valid_ids in (("sessions", valid_session_ids), ("jobs", valid_job_ids)):
            base = self._ensure_within_root(self.root / kind)
            if not base.exists():
                continue
            for child in base.iterdir():
                if child.name == "examples":
                    continue
                if child.name in {safe_name(item, kind[:-1]) for item in valid_ids}:
                    continue
                try:
                    target = self._ensure_within_root(child)
                except LocalWorkspaceError:
                    continue
                try:
                    age = now - child.stat().st_mtime
                except FileNotFoundError:
                    continue
                if age >= int(min_age_seconds):
                    self._delete(target)
                    removed.append(f"{kind}/{child.name}")
        return removed

    def _workspace(self, kind: str, resource_id: str, *, create: bool) -> Path:
        if kind not in {"sessions", "jobs"}:
            raise LocalWorkspaceError("Invalid workspace kind.")
        self._validate_resource_id(resource_id)
        path = self.root / kind / safe_name(resource_id, kind[:-1])
        resolved = self._ensure_within_root(path)
        if create:
            resolved.mkdir(parents=True, exist_ok=True)
        return resolved

    def _validate_resource_id(self, resource_id: str) -> None:
        value = str(resource_id or "").strip()
        if not value:
            raise LocalWorkspaceError("Resource id is required.")
        path = Path(value)
        if path.is_absolute() or "/" in value or "\\" in value or ".." in path.parts:
            raise LocalWorkspaceError("Resource id is not allowed in local workspace paths.")

    def _ensure_within_root(self, path: Path) -> Path:
        root = self.root.resolve()
        resolved = Path(path).resolve()
        if resolved != root and root not in resolved.parents:
            raise LocalWorkspaceError("Local workspace path escapes the temporary root.")
        return resolved

    def _delete(self, path: Path) -> bool:
        target = self._ensure_within_root(path)
        if not target.exists() and not target.is_symlink():
            return True
        if target.is_symlink() or target.is_file():
            target.unlink(missing_ok=True)
        else:
            shutil.rmtree(target)
        return True
