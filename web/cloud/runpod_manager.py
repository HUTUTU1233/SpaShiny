from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from .config import SpaShinyCloudConfig, load_cloud_config
from .environment_check import RemoteEnvironmentChecker
from .runpod_api import RunPodAPIClient
from .ssh_executor import SSHConnectionConfig, SSHExecutor

LOGGER = logging.getLogger(__name__)


class RunPodManager:
    def __init__(
        self,
        config: SpaShinyCloudConfig | None = None,
        api_client: RunPodAPIClient | None = None,
    ) -> None:
        self.config = config or load_cloud_config()
        self.api_client = api_client or RunPodAPIClient(self.config)
        self.last_activity_path = self.config.workspace / "runpod_last_activity.txt"

    def _touch_activity(self) -> None:
        self.last_activity_path.parent.mkdir(parents=True, exist_ok=True)
        self.last_activity_path.write_text(str(time.time()), encoding="utf-8")

    def ensure_pod_running(self) -> dict[str, Any]:
        pod_id = self.config.require_pod_id()
        pod = self.api_client.get_pod(pod_id)
        status = str(pod.get("desiredStatus") or pod.get("status") or "").upper()
        if status not in {"RUNNING", "STARTED"} and not (pod.get("runtime") or {}).get("uptimeInSeconds"):
            LOGGER.info("Starting RunPod pod %s from status %s", pod_id, status or "unknown")
            self.api_client.start_pod(pod_id)
            pod = self.api_client.wait_until_running(pod_id)
        self._touch_activity()
        return pod

    def get_ssh_config(self) -> dict[str, Any]:
        pod_id = self.config.require_pod_id()
        info = self.api_client.get_connection_info(pod_id)
        info["username"] = self.config.ssh_username
        info["private_key_path"] = str(self.config.ssh_private_key)
        return info

    def wait_for_ssh_ready(self) -> dict[str, Any]:
        deadline = time.monotonic() + self.config.ssh_connect_timeout * 6
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                info = self.get_ssh_config()
                ssh_cfg = SSHConnectionConfig.from_connection_info(info, self.config)
                with SSHExecutor(ssh_cfg) as ssh:
                    if ssh.test_connection():
                        return info
            except Exception as exc:
                last_error = exc
                LOGGER.info("Waiting for RunPod SSH readiness: %s", exc)
            time.sleep(5)
        raise TimeoutError(f"RunPod SSH did not become ready: {last_error}") from last_error

    def is_pod_idle(self) -> bool:
        if not self.last_activity_path.exists():
            return False
        try:
            last_activity = float(self.last_activity_path.read_text(encoding="utf-8").strip())
        except Exception:
            return False
        idle_seconds = time.time() - last_activity
        return idle_seconds >= self.config.gpu_idle_minutes * 60

    def stop_if_idle(self) -> bool:
        if not self.is_pod_idle():
            return False
        self.api_client.stop_pod(self.config.require_pod_id())
        return True

    def check_gpu_available(self) -> dict[str, Any]:
        info = self.get_ssh_config()
        ssh_cfg = SSHConnectionConfig.from_connection_info(info, self.config)
        output_path = f"{self.config.remote_job_root.rsplit('/jobs', 1)[0]}/environment_check.json"
        with SSHExecutor(ssh_cfg) as ssh:
            return RemoteEnvironmentChecker(ssh).run(output_path=output_path)
