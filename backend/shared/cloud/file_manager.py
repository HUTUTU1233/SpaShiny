from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterable

from .storage import WorkspaceStorage, safe_name


ALLOWED_INPUT_SUFFIXES = {".h5ad", ".csv", ".tsv", ".txt", ".json", ".mtx", ".npy", ".npz"}


class FileValidationError(ValueError):
    """Raised when an uploaded file cannot be accepted."""


class FileManager:
    def __init__(self, storage: WorkspaceStorage | None = None) -> None:
        self.storage = storage or WorkspaceStorage()

    def validate_input_file(self, path: Path, allowed_suffixes: Iterable[str] | None = None) -> Path:
        path = Path(path)
        suffixes = {suffix.lower() for suffix in (allowed_suffixes or ALLOWED_INPUT_SUFFIXES)}
        if not path.is_file():
            raise FileNotFoundError(f"Input file does not exist: {path}")
        if path.suffix.lower() not in suffixes:
            raise FileValidationError(f"Unsupported input file type: {path.suffix}")
        return path

    def copy_input_file(self, user_id: str, job_id: str, source: Path, target_name: str | None = None) -> Path:
        source = self.validate_input_file(source)
        input_dir = self.storage.job_root(user_id, job_id) / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        target = input_dir / safe_name(target_name or source.name, "input")
        self.storage.ensure_within_user(user_id, target)
        shutil.copy2(source, target)
        return target

    def list_job_files(self, user_id: str, job_id: str, folder: str = "output") -> list[dict[str, object]]:
        base = self.storage.job_root(user_id, job_id) / safe_name(folder, "output")
        self.storage.ensure_within_user(user_id, base)
        if not base.exists():
            return []
        files = []
        for path in base.rglob("*"):
            if path.is_file():
                files.append(
                    {
                        "name": path.name,
                        "relative_path": path.relative_to(base).as_posix(),
                        "size": path.stat().st_size,
                    }
                )
        return files
