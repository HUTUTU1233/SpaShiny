from __future__ import annotations

"""Safe, opt-in result retention reporting.

The initial rollout intentionally performs a dry run only.  Job records and
small provenance stay in SQLite; this helper considers filesystem artifacts
only and reports aggregate counts/bytes without putting user paths in logs.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

from .config import SpaShinyCloudConfig


@dataclass(frozen=True)
class ResultRetentionReport:
    scanned_files: int
    candidate_files: int
    candidate_bytes: int
    oldest_candidate_at: str | None
    dry_run: bool
    deletion_enabled: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanned_files": self.scanned_files,
            "candidate_files": self.candidate_files,
            "candidate_bytes": self.candidate_bytes,
            "oldest_candidate_at": self.oldest_candidate_at,
            "dry_run": self.dry_run,
            "deletion_enabled": self.deletion_enabled,
        }


class ResultRetentionManager:
    def __init__(self, config: SpaShinyCloudConfig) -> None:
        self.config = config

    def report(self) -> ResultRetentionReport:
        root = Path(self.config.lab_result_root)
        cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, int(self.config.result_retention_days)))
        scanned = candidates = candidate_bytes = 0
        oldest: datetime | None = None
        if root.exists():
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                scanned += 1
                try:
                    modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                    size = int(path.stat().st_size)
                except OSError:
                    continue
                if modified < cutoff:
                    candidates += 1
                    candidate_bytes += size
                    oldest = modified if oldest is None or modified < oldest else oldest
        return ResultRetentionReport(
            scanned_files=scanned,
            candidate_files=candidates,
            candidate_bytes=candidate_bytes,
            oldest_candidate_at=oldest.isoformat() if oldest else None,
            dry_run=bool(self.config.cleanup_dry_run),
            deletion_enabled=bool(self.config.result_auto_delete_enabled),
        )

    def write_dry_run_report(self) -> Path:
        """Write an aggregate audit record; this method never removes files."""
        target = Path(self.config.lab_logs_root) / "result-retention-dry-run.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = self.report().to_dict()
        payload["generated_at"] = datetime.now(timezone.utc).isoformat()
        target.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
        return target
