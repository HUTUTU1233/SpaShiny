from __future__ import annotations

import logging
import os
import posixpath
import shlex
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import SpaShinyCloudConfig, load_cloud_config
from .security import redact_secrets, shell_quote

LOGGER = logging.getLogger(__name__)


class SSHExecutorError(RuntimeError):
    """Raised for SSH command, authentication, or transport failures."""


@dataclass(frozen=True)
class SSHConnectionConfig:
    host: str
    port: int
    username: str
    private_key_path: Path
    known_hosts_path: Path
    connect_timeout: int
    command_timeout: int
    retries: int = 3
    trust_on_first_use: bool = False

    @classmethod
    def from_connection_info(
        cls,
        connection_info: dict[str, Any],
        cloud_config: SpaShinyCloudConfig | None = None,
    ) -> "SSHConnectionConfig":
        cloud_config = cloud_config or load_cloud_config()
        return cls(
            host=str(connection_info["host"]),
            port=int(connection_info.get("port") or 22),
            username=cloud_config.ssh_username,
            private_key_path=cloud_config.ssh_private_key,
            known_hosts_path=cloud_config.ssh_known_hosts,
            connect_timeout=cloud_config.ssh_connect_timeout,
            command_timeout=cloud_config.ssh_command_timeout,
            trust_on_first_use=cloud_config.ssh_trust_on_first_use,
        )


class SaveMissingHostKeyPolicy:
    """Paramiko policy that stores first-seen keys in a protected known_hosts file."""

    def __init__(self, known_hosts_path: Path) -> None:
        self.known_hosts_path = Path(known_hosts_path)

    def missing_host_key(self, client: Any, hostname: str, key: Any) -> None:
        self.known_hosts_path.parent.mkdir(parents=True, exist_ok=True)
        client.get_host_keys().add(hostname, key.get_name(), key)
        client.save_host_keys(str(self.known_hosts_path))
        try:
            os.chmod(self.known_hosts_path, 0o600)
        except OSError:
            pass
        LOGGER.warning(
            "Saved first-seen SSH host key for %s to %s fingerprint=%s. "
            "After verifying the fingerprint, set SPASHINY_SSH_TRUST_ON_FIRST_USE=0.",
            hostname,
            self.known_hosts_path,
            host_key_fingerprint_hex(key),
        )


def host_key_fingerprint_hex(key: Any) -> str:
    try:
        return key.get_fingerprint().hex()
    except Exception:
        return ""


def _check_private_key_permissions(path: Path) -> None:
    if os.name == "nt":
        return
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise SSHExecutorError(f"SSH private key permissions must be 600: {path}")


def build_background_shell_command(command: str, stdout_path: str, stderr_path: str, pid_path: str) -> str:
    stdout_q = shell_quote(stdout_path)
    stderr_q = shell_quote(stderr_path)
    pid_q = shell_quote(pid_path)
    command_q = shell_quote(command)
    stdout_dir = posixpath.dirname(str(stdout_path)) or "."
    stderr_dir = posixpath.dirname(str(stderr_path)) or "."
    pid_dir = posixpath.dirname(str(pid_path)) or "."
    return (
        f"mkdir -p {shell_quote(stdout_dir)} {shell_quote(stderr_dir)} {shell_quote(pid_dir)} && "
        f"setsid sh -lc {command_q} > {stdout_q} 2> {stderr_q} < /dev/null & "
        f"echo $! > {pid_q} && cat {pid_q}"
    )


class SSHExecutor:
    def __init__(self, config: SSHConnectionConfig) -> None:
        self.config = config
        self.client: Any | None = None

    def __enter__(self) -> "SSHExecutor":
        self.connect()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _new_client(self) -> Any:
        try:
            import paramiko
        except Exception as exc:
            raise SSHExecutorError("paramiko is required for SSH execution.") from exc

        private_key = Path(self.config.private_key_path)
        if not private_key.exists():
            raise SSHExecutorError(f"SSH private key was not found: {private_key}")
        _check_private_key_permissions(private_key)

        try:
            pkey = paramiko.Ed25519Key.from_private_key_file(str(private_key))
        except Exception as exc:
            raise SSHExecutorError("RUNPOD_SSH_PRIVATE_KEY must be an ED25519 private key.") from exc

        client = paramiko.SSHClient()
        try:
            client.load_system_host_keys()
        except Exception:
            pass
        known_hosts = Path(self.config.known_hosts_path)
        if known_hosts.exists():
            client.load_host_keys(str(known_hosts))
        if self.config.trust_on_first_use:
            client.set_missing_host_key_policy(SaveMissingHostKeyPolicy(known_hosts))
        else:
            client.set_missing_host_key_policy(paramiko.RejectPolicy())

        client.connect(
            hostname=self.config.host,
            port=int(self.config.port),
            username=self.config.username,
            pkey=pkey,
            password=None,
            timeout=self.config.connect_timeout,
            banner_timeout=self.config.connect_timeout,
            auth_timeout=self.config.connect_timeout,
            look_for_keys=False,
            allow_agent=False,
        )
        return client

    def connect(self) -> None:
        last_error: Exception | None = None
        for attempt in range(1, max(1, self.config.retries) + 1):
            try:
                self.client = self._new_client()
                LOGGER.info("SSH connected to %s:%s", self.config.host, self.config.port)
                return
            except Exception as exc:
                last_error = exc
                LOGGER.warning("SSH connect attempt %s failed: %s", attempt, redact_secrets(str(exc)))
                time.sleep(min(2 * attempt, 8))
        raise SSHExecutorError(f"SSH connection failed: {last_error}") from last_error

    def _require_client(self) -> Any:
        if self.client is None:
            self.connect()
        return self.client

    def test_connection(self) -> bool:
        try:
            result = self.execute_command("printf SSH_OK", timeout=min(self.config.command_timeout, 20))
            return result.get("exit_status") == 0 and "SSH_OK" in result.get("stdout", "")
        except Exception:
            return False

    def execute_command(self, command: str, timeout: int | None = None) -> dict[str, Any]:
        client = self._require_client()
        timeout = self.config.command_timeout if timeout is None else timeout
        LOGGER.info("SSH command: %s", redact_secrets(command))
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout, get_pty=False)
        stdin.close()
        channel = stdout.channel
        out_chunks: list[bytes] = []
        err_chunks: list[bytes] = []
        deadline = time.monotonic() + timeout if timeout else None

        while True:
            while channel.recv_ready():
                out_chunks.append(channel.recv(65535))
            while channel.recv_stderr_ready():
                err_chunks.append(channel.recv_stderr(65535))
            if channel.exit_status_ready():
                while channel.recv_ready():
                    out_chunks.append(channel.recv(65535))
                while channel.recv_stderr_ready():
                    err_chunks.append(channel.recv_stderr(65535))
                break
            if deadline and time.monotonic() > deadline:
                channel.close()
                raise TimeoutError(f"SSH command timed out after {timeout}s: {redact_secrets(command)}")
            time.sleep(0.1)

        return {
            "exit_status": channel.recv_exit_status(),
            "stdout": b"".join(out_chunks).decode("utf-8", errors="replace"),
            "stderr": b"".join(err_chunks).decode("utf-8", errors="replace"),
            "command": command,
        }

    def execute_background(self, command: str, stdout_path: str, stderr_path: str, pid_path: str) -> int:
        background = build_background_shell_command(command, stdout_path, stderr_path, pid_path)
        result = self.execute_command(background, timeout=30)
        if result.get("exit_status") != 0:
            raise SSHExecutorError(
                "Failed to start remote background process.\n"
                f"STDOUT:\n{result.get('stdout', '')}\nSTDERR:\n{result.get('stderr', '')}"
            )
        for line in reversed((result.get("stdout") or "").splitlines()):
            line = line.strip()
            if line.isdigit():
                return int(line)
        raise SSHExecutorError(f"Remote background command did not return a PID: {result.get('stdout', '')}")

    def read_text_file(self, remote_path: str, offset: int = 0) -> tuple[str, int]:
        sftp = self._require_client().open_sftp()
        try:
            with sftp.file(remote_path, "rb") as handle:
                handle.seek(max(0, int(offset)))
                data = handle.read()
                new_offset = handle.tell()
            return data.decode("utf-8", errors="replace"), int(new_offset)
        finally:
            sftp.close()

    def write_text_file(self, remote_path: str, text: str) -> None:
        sftp = self._require_client().open_sftp()
        try:
            with sftp.file(remote_path, "wb") as handle:
                handle.write(str(text).encode("utf-8"))
        finally:
            sftp.close()

    def file_exists(self, remote_path: str) -> bool:
        sftp = self._require_client().open_sftp()
        try:
            sftp.stat(remote_path)
            return True
        except OSError:
            return False
        finally:
            sftp.close()

    def process_exists(self, pid: int) -> bool:
        result = self.execute_command(f"kill -0 {int(pid)} >/dev/null 2>&1", timeout=10)
        return result.get("exit_status") == 0

    def terminate_process(self, pid: int, force: bool = False) -> bool:
        signal = "-KILL" if force else "-TERM"
        result = self.execute_command(f"kill {signal} {int(pid)} >/dev/null 2>&1", timeout=10)
        return result.get("exit_status") == 0

    def close(self) -> None:
        if self.client is not None:
            try:
                self.client.close()
            finally:
                self.client = None
