from __future__ import annotations

import json
import logging
import posixpath
from datetime import datetime, timezone
from typing import Any

from .security import shell_quote
from .ssh_executor import SSHExecutor

LOGGER = logging.getLogger(__name__)


class EnvironmentCheckError(RuntimeError):
    """Raised when the RunPod GPU environment cannot run SpaShiny jobs."""


class RemoteEnvironmentChecker:
    def __init__(self, ssh: SSHExecutor, python_command: str = "python") -> None:
        self.ssh = ssh
        self.python_command = python_command

    def _run(self, command: str, timeout: int = 120) -> dict[str, Any]:
        result = self.ssh.execute_command(command, timeout=timeout)
        return {
            "command": command,
            "exit_status": result.get("exit_status"),
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "ok": result.get("exit_status") == 0,
        }

    def run(self, *, output_path: str | None = None) -> dict[str, Any]:
        torch_probe = (
            "import json, torch; "
            "print(json.dumps({'cuda_available': torch.cuda.is_available(), "
            "'version': torch.__version__, 'device_count': torch.cuda.device_count()}))"
        )
        scanpy_probe = "import scanpy; print(scanpy.__version__)"
        spatialmeta_probe = "import spatialmeta; print(getattr(spatialmeta, '__version__', 'unknown'))"
        anndata_probe = "import anndata; print(anndata.__version__)"
        python_probe = "import sys; print(sys.version); print(sys.executable)"
        checks: dict[str, Any] = {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "nvidia_smi": self._run(
                "nvidia-smi --query-gpu=name,memory.total,memory.free,driver_version --format=csv,noheader,nounits",
                timeout=60,
            ),
            "torch": self._run(
                f"{self.python_command} -c {shell_quote(torch_probe)}",
                timeout=60,
            ),
            "scanpy": self._run(f"{self.python_command} -c {shell_quote(scanpy_probe)}", timeout=60),
            "spatialmeta": self._run(f"{self.python_command} -c {shell_quote(spatialmeta_probe)}", timeout=60),
            "anndata": self._run(f"{self.python_command} -c {shell_quote(anndata_probe)}", timeout=60),
            "python": self._run(f"{self.python_command} -c {shell_quote(python_probe)}", timeout=60),
            "disk": self._run("df -Pk /workspace 2>/dev/null || df -Pk .", timeout=30),
            "memory": self._run("grep -E 'MemTotal|MemAvailable' /proc/meminfo 2>/dev/null || true", timeout=30),
        }
        checks["ok"] = all(
            checks[name].get("ok")
            for name in ("nvidia_smi", "torch", "scanpy", "spatialmeta", "anndata", "python")
        )
        if output_path:
            directory = posixpath.dirname(output_path)
            self.ssh.execute_command(f"mkdir -p {shell_quote(directory)}", timeout=30)
            self.ssh.write_text_file(output_path, json.dumps(checks, ensure_ascii=False, indent=2))
        LOGGER.info("Remote environment check ok=%s", checks["ok"])
        return checks
