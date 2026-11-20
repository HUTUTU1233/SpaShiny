from __future__ import annotations

import logging
import posixpath
import stat
import time
from pathlib import Path
from typing import Callable

from .config import load_cloud_config
from .security import safe_remote_path, sha256_file, shell_quote
from .ssh_executor import SSHExecutor, SSHExecutorError

LOGGER = logging.getLogger(__name__)
ProgressCallback = Callable[[int, int], None]


class SFTPTransferError(RuntimeError):
    """Raised when a protected SFTP transfer fails."""


class SFTPManager:
    def __init__(self, ssh: SSHExecutor, remote_root: str | None = None, retries: int = 3) -> None:
        self.ssh = ssh
        self.remote_root = (remote_root or load_cloud_config().remote_job_root).rstrip("/")
        self.retries = max(1, int(retries))

    def normalize_remote_path(self, remote_path: str) -> str:
        return safe_remote_path(self.remote_root, remote_path)

    def _with_retry(self, action):
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                return action()
            except Exception as exc:
                last_error = exc
                LOGGER.warning("SFTP attempt %s failed: %s", attempt, exc)
                time.sleep(min(2 * attempt, 8))
        raise SFTPTransferError(str(last_error)) from last_error

    def mkdir_recursive(self, remote_dir: str) -> None:
        remote_dir = self.normalize_remote_path(remote_dir)
        sftp = self.ssh._require_client().open_sftp()
        try:
            parts = [part for part in remote_dir.split("/") if part]
            current = ""
            for part in parts:
                current += "/" + part
                try:
                    sftp.mkdir(current)
                except OSError:
                    pass
        finally:
            sftp.close()

    def upload_file(self, local_path: Path, remote_path: str, progress_callback: ProgressCallback | None = None) -> None:
        local_path = Path(local_path)
        if not local_path.is_file():
            raise FileNotFoundError(f"Local file does not exist: {local_path}")
        remote_path = self.normalize_remote_path(remote_path)
        self.mkdir_recursive(posixpath.dirname(remote_path))

        def action() -> None:
            sftp = self.ssh._require_client().open_sftp()
            try:
                sftp.put(str(local_path), remote_path, callback=progress_callback)
            finally:
                sftp.close()

        self._with_retry(action)
        local_hash = sha256_file(local_path)
        remote_hash = self.calculate_remote_sha256(remote_path)
        if local_hash != remote_hash:
            raise SFTPTransferError(f"SHA256 mismatch after upload: {local_path.name}")

    def upload_directory(self, local_dir: Path, remote_dir: str, progress_callback: ProgressCallback | None = None) -> None:
        local_dir = Path(local_dir)
        if not local_dir.is_dir():
            raise NotADirectoryError(f"Local directory does not exist: {local_dir}")
        remote_dir = self.normalize_remote_path(remote_dir)
        self.mkdir_recursive(remote_dir)
        for local_file in local_dir.rglob("*"):
            if not local_file.is_file():
                continue
            rel = local_file.relative_to(local_dir).as_posix()
            self.upload_file(local_file, posixpath.join(remote_dir, rel), progress_callback)

    def download_file(self, remote_path: str, local_path: Path, progress_callback: ProgressCallback | None = None) -> None:
        remote_path = self.normalize_remote_path(remote_path)
        local_path = Path(local_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)

        def action() -> None:
            sftp = self.ssh._require_client().open_sftp()
            try:
                sftp.get(remote_path, str(local_path), callback=progress_callback)
            finally:
                sftp.close()

        self._with_retry(action)

    def download_directory(self, remote_dir: str, local_dir: Path, progress_callback: ProgressCallback | None = None) -> None:
        remote_dir = self.normalize_remote_path(remote_dir)
        local_dir = Path(local_dir)
        local_dir.mkdir(parents=True, exist_ok=True)

        def walk(current_remote: str, current_local: Path) -> None:
            sftp = self.ssh._require_client().open_sftp()
            try:
                entries = sftp.listdir_attr(current_remote)
            finally:
                sftp.close()
            for entry in entries:
                remote_child = posixpath.join(current_remote, entry.filename)
                local_child = current_local / entry.filename
                if stat.S_ISDIR(entry.st_mode):
                    local_child.mkdir(parents=True, exist_ok=True)
                    walk(remote_child, local_child)
                else:
                    self.download_file(remote_child, local_child, progress_callback)

        walk(remote_dir, local_dir)

    def remove_directory(self, remote_dir: str) -> None:
        remote_dir = self.normalize_remote_path(remote_dir)
        if remote_dir.rstrip("/") == self.remote_root.rstrip("/"):
            raise ValueError("Refusing to remove the remote job root.")

        def remove_tree(current: str) -> None:
            sftp = self.ssh._require_client().open_sftp()
            try:
                entries = sftp.listdir_attr(current)
            finally:
                sftp.close()
            for entry in entries:
                remote_child = posixpath.join(current, entry.filename)
                if stat.S_ISDIR(entry.st_mode):
                    remove_tree(remote_child)
                else:
                    sftp2 = self.ssh._require_client().open_sftp()
                    try:
                        sftp2.remove(remote_child)
                    finally:
                        sftp2.close()
            sftp3 = self.ssh._require_client().open_sftp()
            try:
                sftp3.rmdir(current)
            finally:
                sftp3.close()

        remove_tree(remote_dir)

    def calculate_remote_sha256(self, remote_path: str) -> str:
        remote_path = self.normalize_remote_path(remote_path)
        command = f"sha256sum {shell_quote(remote_path)}"
        result = self.ssh.execute_command(command, timeout=300)
        if result.get("exit_status") != 0:
            raise SSHExecutorError(f"Remote sha256sum failed: {result.get('stderr', '')}")
        digest = (result.get("stdout") or "").strip().split()[0]
        if len(digest) != 64:
            raise SSHExecutorError(f"Remote sha256sum returned an invalid digest: {digest}")
        return digest
