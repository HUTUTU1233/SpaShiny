from shiny import ui, reactive, render
import io
import json
import os
import posixpath
import shlex
import socket
import tempfile
import traceback
import uuid
import zipfile
from pathlib import Path


DEFAULT_REMOTE_WORKDIR = "~/SpaShiny_STSM_jobs"
DEFAULT_REMOTE_PYTHON = "python"
DEFAULT_STSM_PYTHON = DEFAULT_REMOTE_PYTHON
DEFAULT_RIVER_PYTHON = DEFAULT_REMOTE_PYTHON
REQUIRED_STSM_PACKAGES = ["numpy", "pandas", "scanpy", "scipy", "spatialmeta", "torch"]
REQUIRED_RIVER_PACKAGES = ["anndata", "captum", "matplotlib", "numpy", "pandas", "scanpy", "scSLAT", "sklearn", "torch", "tqdm"]
DEFAULT_LOCAL_WHEELHOUSE = "runtime/wheelhouse"
DEFAULT_REMOTE_PACKAGE_DIR = "data/packages"
IMPORT_TO_PIP_PACKAGE = {
    "sklearn": "scikit-learn",
    "pyimzml": "pyimzML",
}
WHEELHOUSE_SUFFIXES = (".whl", ".tar.gz", ".tar.bz2", ".zip")


def ssh_connection_ready(state):
    return bool(state and state.get("status") == "connected")


def ssh_quote(value):
    value = str(value)
    if value == "~":
        return "~"
    if value.startswith("~/"):
        parts = value[2:].split("/")
        quoted_parts = [shlex.quote(part) for part in parts if part]
        return "~/" + "/".join(quoted_parts)
    return shlex.quote(value)


def _load_private_key(key_text, passphrase=None):
    key_text = (key_text or "").strip()
    if not key_text:
        return None

    try:
        import paramiko
    except Exception as e:
        raise RuntimeError("paramiko is not installed, so the SSH private key cannot be parsed.") from e

    key_classes = [
        getattr(paramiko, "Ed25519Key", None),
        getattr(paramiko, "RSAKey", None),
        getattr(paramiko, "ECDSAKey", None),
        getattr(paramiko, "DSSKey", None),
    ]

    last_error = None
    for key_cls in [cls for cls in key_classes if cls is not None]:
        try:
            return key_cls.from_private_key(
                io.StringIO(key_text),
                password=passphrase or None,
            )
        except Exception as e:
            last_error = e

    raise ValueError(f"Could not parse the private key text: {last_error}")


def ssh_open_client(state, timeout=15):
    if not ssh_connection_ready(state):
        raise RuntimeError("SSH is not connected. Please test and connect on the SSH Connection page first.")

    try:
        import paramiko
    except Exception as e:
        raise RuntimeError("paramiko is not installed. Please install it in the current Python environment: pip install paramiko") from e

    host = (state.get("host") or "").strip()
    port = int(state.get("port") or 22)
    username = (state.get("username") or "").strip()
    password = state.get("password") or None
    key_text = state.get("key_text") or ""
    pkey = _load_private_key(key_text, password) if key_text.strip() else None

    if not host or not username:
        raise RuntimeError("SSH connection information is incomplete. Please reconnect.")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=host,
        port=port,
        username=username,
        password=password,
        pkey=pkey,
        timeout=timeout,
        banner_timeout=timeout,
        auth_timeout=timeout,
        look_for_keys=True,
        allow_agent=True,
    )
    return client


def ssh_exec_command(client, command, timeout=None, get_pty=False):
    import time

    stdin, stdout, stderr = client.exec_command(
        command,
        timeout=timeout,
        get_pty=get_pty,
    )
    stdin.close()

    channel = stdout.channel
    out_chunks = []
    err_chunks = []
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
            raise TimeoutError(f"SSH command timed out after {timeout} seconds: {command}")

        time.sleep(0.1)

    out = b"".join(out_chunks).decode("utf-8", errors="replace")
    err = b"".join(err_chunks).decode("utf-8", errors="replace")
    exit_status = channel.recv_exit_status()
    return {
        "exit_status": exit_status,
        "stdout": out,
        "stderr": err,
        "command": command,
    }


def _python_env_label(python_path, version=""):
    normalized = str(python_path).rstrip("/")
    env_name = normalized.split("/")[-3] if normalized.endswith("/bin/python") and len(normalized.split("/")) >= 3 else ""
    if not env_name or env_name == "bin":
        env_name = normalized.split("/")[-1] or "python"
    if env_name.lower() in {"miniconda3", "anaconda3", "mambaforge", "miniforge3", "conda"}:
        env_name = "base"
    version_text = f" (Python {version})" if version else ""
    return f"{env_name} - {normalized}{version_text}"


def _append_env_choice(choices, label, command):
    command = (command or "").strip()
    if not command:
        return
    if any(item.get("command") == command for item in choices):
        return
    choices.append({"label": label, "command": command})


def ssh_discover_python_envs(client):
    choices = [
        {"label": "python (PATH)", "command": "python"},
        {"label": "python3 (PATH)", "command": "python3"},
    ]

    command = (
        "for tool in conda mamba micromamba; do "
        "if command -v $tool >/dev/null 2>&1; then "
        "$tool env list --json 2>/dev/null && break; "
        "fi; "
        "done"
    )

    result = ssh_exec_command(client, command, timeout=30)
    stdout = (result.get("stdout") or "").strip()

    if stdout:
        start = stdout.find("{")
        end = stdout.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(stdout[start:end + 1])
                env_paths = data.get("envs", []) or []
                for env_path in env_paths:
                    env_path = str(env_path).rstrip("/")
                    if not env_path:
                        continue
                    env_name = env_path.split("/")[-1] or "base"
                    if env_name.lower() in {"miniconda3", "anaconda3", "mambaforge", "miniforge3"}:
                        env_name = "base"
                    python_path = posixpath.join(env_path, "bin", "python")
                    _append_env_choice(
                        choices,
                        f"{env_name} - {python_path}",
                        ssh_quote(python_path),
                    )
            except Exception:
                pass

    common_paths = (
        "python python3 "
        "$HOME/miniconda3/bin/python $HOME/anaconda3/bin/python "
        "$HOME/mambaforge/bin/python $HOME/miniforge3/bin/python "
        "$HOME/miniconda3/envs/*/bin/python $HOME/anaconda3/envs/*/bin/python "
        "$HOME/mambaforge/envs/*/bin/python $HOME/miniforge3/envs/*/bin/python "
        "$HOME/envs/*/bin/python /opt/conda/bin/python /opt/conda/envs/*/bin/python"
    )
    probe_command = (
        f"for p in {common_paths}; do "
        "[ -x \"$p\" ] || command -v \"$p\" >/dev/null 2>&1 || continue; "
        "resolved=$(\"$p\" -c 'import sys; print(sys.executable)' 2>/dev/null) || continue; "
        "version=$(\"$p\" -c 'import sys; print(sys.version.split()[0])' 2>/dev/null) || version=''; "
        "printf 'PYENV\\t%s\\t%s\\n' \"$resolved\" \"$version\"; "
        "done"
    )
    try:
        probe = ssh_exec_command(client, probe_command, timeout=45)
        for line in (probe.get("stdout") or "").splitlines():
            if not line.startswith("PYENV\t"):
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            python_path = parts[1].strip()
            version = parts[2].strip() if len(parts) > 2 else ""
            if python_path:
                _append_env_choice(
                    choices,
                    _python_env_label(python_path, version),
                    ssh_quote(python_path),
                )
    except Exception:
        pass

    seen = set()
    unique = []
    for item in choices:
        cmd = item["command"]
        if cmd in seen:
            continue
        seen.add(cmd)
        unique.append(item)
    return unique


def ssh_env_choices_dict(choices, *selected_commands):
    out = {item["command"]: item["label"] for item in choices or []}
    for cmd in selected_commands:
        cmd = (cmd or "").strip()
        if cmd and cmd not in out:
            out[cmd] = f"Manual - {cmd}"
    return out or {DEFAULT_REMOTE_PYTHON: f"Manual - {DEFAULT_REMOTE_PYTHON}"}


def ssh_python_command_available(client, python_cmd):
    code = "import sys; print(sys.executable); print(sys.version.split()[0])"
    try:
        result = ssh_exec_command(client, f"{python_cmd} -c {ssh_quote(code)}", timeout=30)
        return result.get("exit_status") == 0
    except Exception:
        return False


def ssh_pick_working_python_command(client, preferred_cmd, env_choices):
    candidates = []
    preferred_cmd = (preferred_cmd or "").strip()
    if preferred_cmd:
        candidates.append(preferred_cmd)
    for item in env_choices or []:
        command = (item.get("command") or "").strip()
        if command and command not in candidates:
            candidates.append(command)

    for command in candidates:
        if ssh_python_command_available(client, command):
            return command
    return preferred_cmd or DEFAULT_REMOTE_PYTHON


def ssh_probe_python_packages(client, python_cmd, packages):
    packages = list(packages or [])
    code = (
        "import importlib.util,json,sys;"
        f"pkgs={json.dumps(packages)};"
        "present=[];missing=[];"
        "[(present if importlib.util.find_spec(p) is not None else missing).append(p) for p in pkgs];"
        "print(json.dumps({'python':sys.executable,'version':sys.version.split()[0],"
        "'present':present,'missing':missing},ensure_ascii=False));"
    )
    result = ssh_exec_command(
        client,
        f"{python_cmd} -c {ssh_quote(code)}",
        timeout=90,
    )

    stdout = (result.get("stdout") or "").strip()
    stderr = (result.get("stderr") or "").strip()
    meta = {
        "python": python_cmd,
        "version": "",
        "present": [],
        "missing": packages,
        "exit_status": result.get("exit_status"),
        "stdout": stdout,
        "stderr": stderr,
    }
    if stdout:
        for line in reversed(stdout.splitlines()):
            try:
                parsed = json.loads(line)
                meta.update(parsed)
                break
            except Exception:
                continue

    return meta


def ssh_check_python_packages(client, python_cmd, packages, label="Python"):
    meta = ssh_probe_python_packages(client, python_cmd, packages)
    stdout = (meta.get("stdout") or "").strip()
    stderr = (meta.get("stderr") or "").strip()

    if meta.get("exit_status") != 0:
        raise RuntimeError(
            f"{label} environment dependency check failed.\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
        )

    missing = meta.get("missing") or []
    if missing:
        raise RuntimeError(f"{label} environment is missing required package(s): {', '.join(missing)}")

    return meta


def ssh_imports_to_pip_packages(import_names):
    out = []
    seen = set()
    for name in import_names or []:
        pip_name = IMPORT_TO_PIP_PACKAGE.get(name, name)
        key = pip_name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(pip_name)
    return out


def ssh_resolve_local_wheelhouse(path_text):
    path_text = (path_text or DEFAULT_LOCAL_WHEELHOUSE).strip()
    path = Path(os.path.expandvars(path_text)).expanduser()
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[1] / path
    return path


def ssh_resolve_remote_package_dir(remote_workspace, remote_package_dir):
    remote_package_dir = (remote_package_dir or DEFAULT_REMOTE_PACKAGE_DIR).strip()
    if not remote_package_dir:
        remote_package_dir = DEFAULT_REMOTE_PACKAGE_DIR
    if remote_package_dir.startswith("/") or remote_package_dir.startswith("~/"):
        return remote_package_dir.rstrip("/")
    workspace = (remote_workspace or DEFAULT_REMOTE_WORKDIR).strip().rstrip("/")
    return posixpath.join(workspace, remote_package_dir.strip("/"))


def _is_wheelhouse_file(path):
    name = str(path).lower()
    return any(name.endswith(suffix) for suffix in WHEELHOUSE_SUFFIXES)


def ssh_prepare_wheelhouse_archive(local_wheelhouse):
    local_wheelhouse = Path(local_wheelhouse)
    if not local_wheelhouse.exists():
        raise FileNotFoundError(f"Local wheelhouse path does not exist: {local_wheelhouse}")

    if local_wheelhouse.is_file():
        if local_wheelhouse.suffix.lower() != ".zip":
            raise ValueError("Local wheelhouse file must be a .zip archive.")
        return local_wheelhouse, False, f"{local_wheelhouse.name}"

    package_files = [p for p in local_wheelhouse.rglob("*") if p.is_file() and _is_wheelhouse_file(p)]
    if not package_files:
        raise ValueError(
            "The local wheelhouse folder does not contain .whl/.tar.gz/.tar.bz2/.zip package files. "
            "Build or place compatible package archives there first."
        )

    tmp = tempfile.NamedTemporaryFile(prefix="spashiny_wheelhouse_", suffix=".zip", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()

    with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for package_file in package_files:
            zf.write(package_file, package_file.name)

    return tmp_path, True, f"{local_wheelhouse} ({len(package_files)} package file(s))"


def ssh_upload_local_wheelhouse(client, local_wheelhouse, remote_workspace, extract_python_cmd, remote_package_dir=None, log=None):
    log = log or (lambda _msg: None)
    archive_path, is_temp, description = ssh_prepare_wheelhouse_archive(local_wheelhouse)
    token = uuid.uuid4().hex[:10]
    remote_base = ssh_resolve_remote_package_dir(remote_workspace, remote_package_dir)
    remote_zip = posixpath.join(remote_base, f"spashiny_wheelhouse_{token}.zip")
    remote_wheelhouse = posixpath.join(remote_base, f"wheelhouse_{token}")

    try:
        ssh_mkdir_p(client, remote_base)
        log(f"[INFO] Uploading local wheelhouse: {description}")
        log(f"[INFO] Remote package data directory: {remote_base}")
        ssh_upload_file(client, archive_path, remote_zip)

        extract_cmd = (
            f"mkdir -p {ssh_quote(remote_wheelhouse)} && "
            f"{extract_python_cmd} -m zipfile -e {ssh_quote(remote_zip)} {ssh_quote(remote_wheelhouse)}"
        )
        result = ssh_exec_command(client, extract_cmd, timeout=None)
        if result.get("exit_status") != 0:
            raise RuntimeError(
                "Failed to extract wheelhouse on the remote server.\n"
                f"STDOUT:\n{result.get('stdout', '')}\nSTDERR:\n{result.get('stderr', '')}"
            )
        log(f"[OK] Wheelhouse extracted on remote server: {remote_wheelhouse}")
        return remote_wheelhouse
    finally:
        if is_temp:
            try:
                archive_path.unlink()
            except Exception:
                pass


def ssh_install_missing_packages_from_wheelhouse(client, python_cmd, packages, remote_wheelhouse, label="Python", log=None):
    log = log or (lambda _msg: None)
    before = ssh_probe_python_packages(client, python_cmd, packages)
    if before.get("exit_status") != 0:
        raise RuntimeError(
            f"{label} environment could not run the dependency probe.\n"
            f"STDOUT:\n{before.get('stdout', '')}\nSTDERR:\n{before.get('stderr', '')}"
        )

    missing = before.get("missing") or []
    if not missing:
        log(f"[OK] {label} environment already has all required packages.")
        return {"ok": True, "installed": [], "missing_after": []}

    pip_packages = ssh_imports_to_pip_packages(missing)
    log(f"[INFO] Installing missing {label} package(s) from wheelhouse: {', '.join(pip_packages)}")

    pip_check = ssh_exec_command(client, f"{python_cmd} -m pip --version", timeout=60)
    if pip_check.get("exit_status") != 0:
        log(f"[WARN] pip is not available in {label}; trying ensurepip.")
        ensure = ssh_exec_command(client, f"{python_cmd} -m ensurepip --upgrade", timeout=300)
        if ensure.get("exit_status") != 0:
            raise RuntimeError(
                f"{label} environment does not have pip, and ensurepip failed.\n"
                f"STDOUT:\n{ensure.get('stdout', '')}\nSTDERR:\n{ensure.get('stderr', '')}"
            )

    package_args = " ".join(ssh_quote(pkg) for pkg in pip_packages)
    install_cmd = (
        f"{python_cmd} -m pip install --no-index --find-links {ssh_quote(remote_wheelhouse)} {package_args}"
    )
    result = ssh_exec_command(client, install_cmd, timeout=None)
    if result.get("exit_status") != 0:
        raise RuntimeError(
            f"{label} offline package installation failed.\n"
            f"STDOUT:\n{result.get('stdout', '')}\nSTDERR:\n{result.get('stderr', '')}"
        )

    after = ssh_probe_python_packages(client, python_cmd, packages)
    missing_after = after.get("missing") or []
    if after.get("exit_status") != 0 or missing_after:
        raise RuntimeError(
            f"{label} still has missing package(s) after installation: {', '.join(missing_after or missing)}"
        )

    log(f"[OK] {label} missing packages installed and verified.")
    return {"ok": True, "installed": pip_packages, "missing_after": []}


def ssh_upload_file(client, local_path, remote_path):
    sftp = client.open_sftp()
    try:
        sftp.put(str(local_path), str(remote_path))
    finally:
        sftp.close()


def ssh_mkdir_p(client, remote_path):
    result = ssh_exec_command(client, f"mkdir -p {ssh_quote(remote_path)}", timeout=30)
    if result["exit_status"] != 0:
        raise RuntimeError(
            f"Failed to create remote directory: {remote_path}\n"
            f"STDOUT:\n{result['stdout']}\nSTDERR:\n{result['stderr']}"
        )


def ssh_upload_directory(client, local_dir, remote_dir):
    import os
    from pathlib import Path

    local_dir = Path(local_dir)
    ssh_mkdir_p(client, remote_dir)

    sftp = client.open_sftp()
    try:
        for root, dirs, files in os.walk(local_dir):
            rel_root = Path(root).relative_to(local_dir)
            remote_root = str(remote_dir) if str(rel_root) == "." else posixpath.join(str(remote_dir), *rel_root.parts)

            for dirname in dirs:
                remote_subdir = posixpath.join(remote_root, dirname)
                try:
                    sftp.mkdir(remote_subdir)
                except OSError:
                    pass

            for filename in files:
                local_file = Path(root) / filename
                remote_file = posixpath.join(remote_root, filename)
                sftp.put(str(local_file), remote_file)
    finally:
        sftp.close()


def ssh_download_file(client, remote_path, local_path):
    sftp = client.open_sftp()
    try:
        sftp.get(str(remote_path), str(local_path))
    finally:
        sftp.close()


def ssh_upload_text(client, remote_path, text):
    sftp = client.open_sftp()
    try:
        with sftp.file(str(remote_path), "wb") as remote_file:
            remote_file.write(text.encode("utf-8"))
    finally:
        sftp.close()


def ssh_prepare_job_dir(client, state, prefix="stsm_job"):
    remote_workspace = (state.get("remote_workspace") or DEFAULT_REMOTE_WORKDIR).strip()
    job_name = f"{prefix}_{uuid.uuid4().hex[:12]}"
    remote_job_dir = posixpath.join(remote_workspace.rstrip("/"), job_name)
    command = f"mkdir -p {ssh_quote(remote_job_dir)} && cd {ssh_quote(remote_job_dir)} && pwd"
    result = ssh_exec_command(client, command, timeout=30)
    if result["exit_status"] != 0:
        raise RuntimeError(
            "Failed to create the remote job directory.\n"
            f"STDOUT:\n{result['stdout']}\nSTDERR:\n{result['stderr']}"
        )
    resolved = result["stdout"].strip().splitlines()
    return resolved[-1] if resolved else remote_job_dir


def ssh_module_ui():
    return ui.page_fluid(
        ui.tags.style("""
        .ssh-page {
            max-width: 1280px;
            margin: 0 auto;
            padding: 28px 8px 42px 8px;
        }
        .ssh-hero {
            background: linear-gradient(135deg, rgba(255,255,255,0.98), rgba(245,249,255,0.94));
            border: 1px solid rgba(0,0,0,0.06);
            border-radius: 28px;
            box-shadow: 0 12px 30px rgba(0,0,0,0.05);
            padding: 30px 34px;
            margin-bottom: 22px;
        }
        .ssh-title {
            font-size: 2.0rem;
            font-weight: 760;
            color: #1d1d1f;
            letter-spacing: -0.03em;
            margin-bottom: 8px;
        }
        .ssh-subtitle {
            color: #6e6e73;
            line-height: 1.75;
            max-width: 980px;
        }
        .ssh-layout {
            display: grid;
            grid-template-columns: minmax(320px, 420px) minmax(0, 1fr);
            gap: 20px;
            align-items: start;
        }
        .ssh-card {
            background: rgba(255,255,255,0.96);
            border: 1px solid rgba(0,0,0,0.06);
            border-radius: 24px;
            box-shadow: 0 10px 26px rgba(0,0,0,0.045);
            padding: 22px 24px;
        }
        .ssh-card h4 {
            font-weight: 740;
            color: #1d1d1f;
            margin-top: 0;
            margin-bottom: 14px;
        }
        .ssh-muted {
            color: #6e6e73;
            font-size: 0.94rem;
            line-height: 1.7;
        }
        .ssh-btn-row {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin-top: 14px;
        }
        .ssh-status-card {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 18px;
            padding: 18px 20px;
            border-radius: 20px;
            background: #f8fafc;
            border: 1px solid #e5e7eb;
            margin-bottom: 16px;
        }
        .ssh-status-title {
            font-size: 1.06rem;
            font-weight: 730;
            color: #1d1d1f;
            margin-bottom: 4px;
        }
        .ssh-status-desc {
            color: #6e6e73;
            line-height: 1.6;
            font-size: 0.93rem;
        }
        .ssh-pill {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 9px 13px;
            border-radius: 999px;
            font-size: 0.92rem;
            font-weight: 720;
            white-space: nowrap;
        }
        .ssh-pill.local {
            background: #f1f5f9;
            color: #475569;
            border: 1px solid #cbd5e1;
        }
        .ssh-pill.connected {
            background: #ecfdf5;
            color: #047857;
            border: 1px solid #a7f3d0;
        }
        .ssh-pill.error {
            background: #fef2f2;
            color: #b91c1c;
            border: 1px solid #fecaca;
        }
        .ssh-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            display: inline-block;
            background: #94a3b8;
            box-shadow: 0 0 0 4px rgba(148,163,184,0.14);
        }
        .ssh-pill.connected .ssh-dot {
            background: #10b981;
            box-shadow: 0 0 0 4px rgba(16,185,129,0.16);
        }
        .ssh-pill.error .ssh-dot {
            background: #ef4444;
            box-shadow: 0 0 0 4px rgba(239,68,68,0.14);
        }
        .ssh-log-box pre {
            min-height: 260px;
            max-height: 420px;
            overflow: auto;
            background: #0f172a;
            color: #dbeafe;
            border-radius: 18px;
            border: 1px solid #1e293b;
            padding: 16px 18px;
            font-size: 0.9rem;
            line-height: 1.55;
        }
        .ssh-wheelhouse-panel {
            margin-top: 14px;
            padding: 14px 15px;
            border-radius: 16px;
            background: #f8fafc;
            border: 1px solid #e5e7eb;
        }
        .ssh-wheelhouse-panel .form-group {
            margin-bottom: 8px;
        }
        .ssh-check-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 12px;
            margin-bottom: 16px;
        }
        .ssh-check-card {
            border: 1px solid #e5e7eb;
            border-radius: 16px;
            padding: 13px 14px;
            background: #ffffff;
        }
        .ssh-check-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
            margin-bottom: 8px;
            font-weight: 740;
            color: #1d1d1f;
        }
        .ssh-check-badge {
            border-radius: 999px;
            padding: 4px 9px;
            font-size: 0.78rem;
            font-weight: 760;
            white-space: nowrap;
        }
        .ssh-check-badge.ok {
            background: #ecfdf5;
            color: #047857;
            border: 1px solid #a7f3d0;
        }
        .ssh-check-badge.warn {
            background: #fff7ed;
            color: #c2410c;
            border: 1px solid #fed7aa;
        }
        .ssh-check-meta {
            color: #64748b;
            font-size: 0.86rem;
            line-height: 1.55;
            word-break: break-word;
        }
        .ssh-top-status {
            display: inline-flex;
            align-items: center;
            gap: 7px;
            margin-left: 14px;
            padding: 7px 10px;
            border-radius: 999px;
            font-size: 13px;
            font-weight: 720;
            border: 1px solid #cbd5e1;
            color: #475569;
            background: #f8fafc;
        }
        .ssh-top-status.connected {
            border-color: #a7f3d0;
            color: #047857;
            background: #ecfdf5;
        }
        .ssh-top-status.error {
            border-color: #fecaca;
            color: #b91c1c;
            background: #fef2f2;
        }
        .ssh-top-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #94a3b8;
        }
        .ssh-top-status.connected .ssh-top-dot { background: #10b981; }
        .ssh-top-status.error .ssh-top-dot { background: #ef4444; }
        @media (max-width: 980px) {
            .ssh-layout { grid-template-columns: 1fr; }
            .ssh-check-grid { grid-template-columns: 1fr; }
        }
        """),
        ui.tags.div(
            ui.tags.div(
                ui.tags.div("SSH Connection", class_="ssh-title"),
                ui.tags.div(
                    "Optionally connect to a remote server for downstream background analysis. When disconnected, jobs run locally; after a successful SSH test, ST-SM and River can use the selected remote environments.",
                    class_="ssh-subtitle"
                ),
                class_="ssh-hero"
            ),
            ui.tags.div(
                ui.tags.div(
                    ui.tags.div(
                        ui.tags.h4("Connection Parameters"),
                        ui.input_text("ssh_host", "Host / IP", placeholder="e.g. 127.0.0.1 or server.example.com"),
                        ui.input_numeric("ssh_port", "Port", value=22, min=1, max=65535, step=1),
                        ui.input_text("ssh_username", "Username", placeholder="e.g. zhuozhong"),
                        ui.input_password("ssh_password", "Password", placeholder="Optional; leave empty when using an unencrypted key"),
                        ui.input_text_area(
                            "ssh_key_text",
                            "Private key text (optional)",
                            placeholder="Paste an OpenSSH private key here. If provided, it is preferred for login; the password field can also be used as the passphrase.",
                            rows=4
                        ),
                        ui.input_text(
                            "ssh_remote_workspace",
                            "Remote workspace",
                            value=DEFAULT_REMOTE_WORKDIR,
                            placeholder="e.g. ~/SpaShiny_STSM_jobs"
                        ),
                        ui.output_ui("ssh_env_selectors"),
                        ui.tags.div(
                            ui.input_text(
                                "ssh_local_wheelhouse",
                                "Local wheelhouse folder / zip",
                                value=DEFAULT_LOCAL_WHEELHOUSE,
                                placeholder="e.g. runtime/wheelhouse or /opt/spashiny/packages/spashiny_wheels.zip",
                            ),
                            ui.input_text(
                                "ssh_remote_package_dir",
                                "Remote package directory",
                                value=DEFAULT_REMOTE_PACKAGE_DIR,
                                placeholder="e.g. data/packages, ~/spashiny_packages, or /data/user/spashiny_packages",
                            ),
                            ui.tags.div(
                                "When packages are missing, SpaShiny uploads this compatible Python wheelhouse to the remote package directory and installs with pip --no-index.",
                                class_="ssh-muted"
                            ),
                            class_="ssh-wheelhouse-panel",
                        ),
                        ui.tags.div(
                            ui.input_action_button("ssh_test", "Test and Connect", class_="btn btn-primary"),
                            ui.input_action_button("ssh_validate_envs", "Validate Selected Environments", class_="btn btn-info"),
                            ui.input_action_button("ssh_install_missing", "Upload Python Wheelhouse & Install Missing", class_="btn btn-success"),
                            ui.input_action_button("ssh_disconnect", "Disconnect / Use Local", class_="btn btn-default"),
                            class_="ssh-btn-row"
                        ),
                        ui.tags.hr(),
                        ui.tags.div(
                            "SSH manages the remote connection. ST-SM and River use the remote Python/conda environments configured here. Disconnecting switches analysis back to local mode.",
                            class_="ssh-muted"
                        ),
                        class_="ssh-card"
                    ),
                    ui.tags.div(
                        ui.tags.div(
                            ui.output_ui("ssh_status_card"),
                            ui.output_ui("ssh_env_check_card"),
                            ui.tags.h4("Connection Log"),
                            ui.tags.div(ui.output_text_verbatim("ssh_log"), class_="ssh-log-box"),
                            class_="ssh-card"
                        ),
                    ),
                    class_="ssh-layout"
                ),
            ),
            class_="ssh-page"
        )
    )


def ssh_status_indicator_ui(status, host="", username=""):
    if status == "connected":
        label = "SSH connected"
        extra = f" - {username}@{host}" if host and username else ""
        cls = "ssh-top-status connected"
    elif status == "error":
        label = "SSH error"
        extra = ""
        cls = "ssh-top-status error"
    else:
        label = "Local mode"
        extra = ""
        cls = "ssh-top-status"

    return ui.tags.div(
        ui.tags.span(class_="ssh-top-dot"),
        ui.tags.span(label + extra),
        class_=cls,
        title=label + extra,
    )


def ssh_module_server(input, output, session):
    ssh_state = reactive.Value({
        "status": "local",
        "host": "",
        "port": 22,
        "username": "",
        "password": "",
        "key_text": "",
        "remote_workspace": DEFAULT_REMOTE_WORKDIR,
        "python_cmd": DEFAULT_REMOTE_PYTHON,
        "stsm_python_cmd": DEFAULT_STSM_PYTHON,
        "river_python_cmd": DEFAULT_RIVER_PYTHON,
        "env_choices": [
            {"label": "python (PATH)", "command": "python"},
            {"label": "python3 (PATH)", "command": "python3"},
        ],
        "env_check": {},
        "wheelhouse_path": DEFAULT_LOCAL_WHEELHOUSE,
        "remote_package_dir": DEFAULT_REMOTE_PACKAGE_DIR,
        "install_summary": {},
        "message": "Local mode is active.",
    })
    ssh_log_value = reactive.Value("[INFO] Local mode is active. SSH is not connected.\n")

    def append_log(msg):
        import time
        old = ssh_log_value.get() or ""
        ssh_log_value.set(old + time.strftime("[%H:%M:%S] ") + str(msg) + "\n")

    def set_state(
        status,
        host="",
        port=22,
        username="",
        password="",
        key_text="",
        remote_workspace=DEFAULT_REMOTE_WORKDIR,
        python_cmd=DEFAULT_STSM_PYTHON,
        stsm_python_cmd=DEFAULT_STSM_PYTHON,
        river_python_cmd=DEFAULT_RIVER_PYTHON,
        env_choices=None,
        env_check=None,
        wheelhouse_path=None,
        remote_package_dir=None,
        install_summary=None,
        message="",
    ):
        current = ssh_state.get()
        stsm_python_cmd = stsm_python_cmd or python_cmd or DEFAULT_STSM_PYTHON
        ssh_state.set({
            "status": status,
            "host": host or "",
            "port": int(port or 22),
            "username": username or "",
            "password": password or "",
            "key_text": key_text or "",
            "remote_workspace": remote_workspace or DEFAULT_REMOTE_WORKDIR,
            "python_cmd": stsm_python_cmd,
            "stsm_python_cmd": stsm_python_cmd,
            "river_python_cmd": river_python_cmd or DEFAULT_RIVER_PYTHON,
            "env_choices": env_choices or [
                {"label": "python (PATH)", "command": "python"},
                {"label": "python3 (PATH)", "command": "python3"},
            ],
            "env_check": env_check or {},
            "wheelhouse_path": wheelhouse_path if wheelhouse_path is not None else current.get("wheelhouse_path", DEFAULT_LOCAL_WHEELHOUSE),
            "remote_package_dir": remote_package_dir if remote_package_dir is not None else current.get("remote_package_dir", DEFAULT_REMOTE_PACKAGE_DIR),
            "install_summary": install_summary if install_summary is not None else current.get("install_summary", {}),
            "message": message or "",
        })

    def validate_envs_with_client(client, stsm_python_cmd, river_python_cmd, raise_on_missing=False):
        checks = {}
        errors = []

        for label, cmd, packages, key in [
            ("ST-SM", stsm_python_cmd, REQUIRED_STSM_PACKAGES, "stsm"),
            ("River", river_python_cmd, REQUIRED_RIVER_PACKAGES, "river"),
        ]:
            try:
                meta = ssh_probe_python_packages(client, cmd, packages)
                if meta.get("exit_status") != 0:
                    error = (
                        f"{label} environment dependency probe failed.\n"
                        f"STDOUT:\n{meta.get('stdout', '')}\nSTDERR:\n{meta.get('stderr', '')}"
                    )
                    checks[key] = {"ok": False, "cmd": cmd, "command_ok": False, "error": error, **meta}
                    errors.append(error)
                    append_log(f"[ERROR] {label} dependency probe failed: {cmd}")
                    continue

                missing = meta.get("missing") or []
                if missing:
                    error = f"{label} environment is missing required package(s): {', '.join(missing)}"
                    checks[key] = {"ok": False, "cmd": cmd, "command_ok": True, "error": error, **meta}
                    errors.append(error)
                    append_log(f"[WARN] {error}")
                    continue

                checks[key] = {"ok": True, "cmd": cmd, "command_ok": True, **meta}
                append_log(
                    f"[OK] {label} environment dependencies are complete: {cmd} "
                    f"(Python {meta.get('version', '')}, executable={meta.get('python', '')})"
                )
            except Exception as e:
                checks[key] = {"ok": False, "cmd": cmd, "command_ok": False, "error": str(e)}
                errors.append(str(e))
                append_log(f"[ERROR] {e}")

        if errors and raise_on_missing:
            raise RuntimeError("; ".join(errors))

        return checks, errors

    @output
    @render.ui
    def ssh_env_selectors():
        st = ssh_state.get()
        if st.get("status") == "connected":
            choices = ssh_env_choices_dict(
                st.get("env_choices", []),
                st.get("stsm_python_cmd", DEFAULT_STSM_PYTHON),
                st.get("river_python_cmd", DEFAULT_RIVER_PYTHON),
            )
            return ui.tags.div(
                ui.input_select(
                    "ssh_stsm_env_choice",
                    "ST-SM remote environment",
                    choices=choices,
                    selected=st.get("stsm_python_cmd", DEFAULT_STSM_PYTHON),
                ),
                ui.input_select(
                    "ssh_river_env_choice",
                    "River remote environment",
                    choices=choices,
                    selected=st.get("river_python_cmd", DEFAULT_RIVER_PYTHON),
                ),
                ui.tags.div(
                    "Available Python/conda environments were discovered on the SSH server. Select one, then click Validate Selected Environments.",
                    class_="ssh-muted"
                ),
            )

        return ui.tags.div(
            ui.input_text(
                "ssh_python_cmd",
                "ST-SM remote Python command",
                value=DEFAULT_STSM_PYTHON,
                placeholder="e.g. python, python3, conda run -n spatialmeta python"
            ),
            ui.input_text(
                "ssh_river_python_cmd",
                "River remote Python command",
                value=DEFAULT_RIVER_PYTHON,
                placeholder="e.g. python, python3, conda run -n river python"
            ),
            ui.tags.div(
                "Before connecting, you can enter commands manually. After a successful connection, conda/mamba environments on the SSH server will be discovered automatically.",
                class_="ssh-muted"
            ),
        )

    @reactive.Effect
    @reactive.event(input.ssh_stsm_env_choice, input.ssh_river_env_choice)
    def _apply_selected_envs():
        st = ssh_state.get()
        if st.get("status") != "connected":
            return

        try:
            stsm_cmd = input.ssh_stsm_env_choice()
            river_cmd = input.ssh_river_env_choice()
        except Exception:
            return

        if not stsm_cmd or not river_cmd:
            return

        if stsm_cmd == st.get("stsm_python_cmd") and river_cmd == st.get("river_python_cmd"):
            return

        set_state(
            "connected",
            host=st.get("host", ""),
            port=st.get("port", 22),
            username=st.get("username", ""),
            password=st.get("password", ""),
            key_text=st.get("key_text", ""),
            remote_workspace=st.get("remote_workspace", DEFAULT_REMOTE_WORKDIR),
            stsm_python_cmd=stsm_cmd,
            river_python_cmd=river_cmd,
            env_choices=st.get("env_choices", []),
            env_check={},
            message=f"Selected remote environments: ST-SM={stsm_cmd}; River={river_cmd}. Please validate dependencies.",
        )

    @reactive.Effect
    @reactive.event(input.ssh_test)
    def _test_ssh_connection():
        host = (input.ssh_host() or "").strip()
        port = int(input.ssh_port() or 22)
        username = (input.ssh_username() or "").strip()
        password = input.ssh_password() or ""
        key_text = input.ssh_key_text() or ""
        remote_workspace = (input.ssh_remote_workspace() or DEFAULT_REMOTE_WORKDIR).strip()
        current = ssh_state.get()
        try:
            stsm_python_cmd = (input.ssh_python_cmd() or current.get("stsm_python_cmd") or DEFAULT_STSM_PYTHON).strip()
        except Exception:
            stsm_python_cmd = (current.get("stsm_python_cmd") or DEFAULT_STSM_PYTHON).strip()
        try:
            river_python_cmd = (input.ssh_river_python_cmd() or current.get("river_python_cmd") or DEFAULT_RIVER_PYTHON).strip()
        except Exception:
            river_python_cmd = (current.get("river_python_cmd") or DEFAULT_RIVER_PYTHON).strip()

        if not host:
            set_state("error", message="Please enter Host / IP.")
            append_log("[ERROR] Host / IP is empty.")
            return
        if not username:
            set_state("error", host=host, port=port, message="Please enter a username.")
            append_log("[ERROR] Username is empty.")
            return
        if not stsm_python_cmd:
            set_state("error", host=host, port=port, username=username, message="Please enter the ST-SM remote Python command.")
            append_log("[ERROR] ST-SM remote Python command is empty.")
            return
        if not river_python_cmd:
            set_state("error", host=host, port=port, username=username, message="Please enter the River remote Python command.")
            append_log("[ERROR] River remote Python command is empty.")
            return

        append_log(f"[INFO] Testing SSH connection: {username}@{host}:{port}")

        # First do a fast TCP reachability check, so network errors are clearer.
        try:
            with socket.create_connection((host, port), timeout=6):
                append_log("[OK] TCP port is reachable.")
        except Exception as e:
            msg = f"TCP connection failed: {e}"
            set_state("error", host=host, port=port, username=username, message=msg)
            append_log("[ERROR] " + msg)
            return

        try:
            import paramiko
        except Exception:
            msg = "paramiko is not installed. Please install it in the current Python environment: pip install paramiko"
            set_state("error", host=host, port=port, username=username, message=msg)
            append_log("[ERROR] " + msg)
            return

        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            pkey = _load_private_key(key_text, password) if key_text.strip() else None
            client.connect(
                hostname=host,
                port=port,
                username=username,
                password=password if password else None,
                pkey=pkey,
                timeout=8,
                banner_timeout=8,
                auth_timeout=8,
                look_for_keys=True,
                allow_agent=True,
            )
            test_cmd = (
                "echo SSH_OK && hostname && "
                f"mkdir -p {ssh_quote(remote_workspace)} && "
                f"cd {ssh_quote(remote_workspace)} && pwd"
            )
            result = ssh_exec_command(client, test_cmd, timeout=20)
            out = result["stdout"].strip()
            err = result["stderr"].strip()
            exit_status = result["exit_status"]

            if exit_status != 0:
                raise RuntimeError(f"Remote workspace test failed: {err or out}")

            append_log("[INFO] Discovering Python/conda environments on the SSH server...")
            env_choices = ssh_discover_python_envs(client)
            append_log(f"[OK] Discovered {len(env_choices)} selectable Python command(s) / environment(s).")

            selected_stsm_python_cmd = ssh_pick_working_python_command(client, stsm_python_cmd, env_choices)
            selected_river_python_cmd = ssh_pick_working_python_command(client, river_python_cmd, env_choices)
            if selected_stsm_python_cmd != stsm_python_cmd:
                append_log(f"[INFO] ST-SM Python default changed to discovered command: {selected_stsm_python_cmd}")
            if selected_river_python_cmd != river_python_cmd:
                append_log(f"[INFO] River Python default changed to discovered command: {selected_river_python_cmd}")
            stsm_python_cmd = selected_stsm_python_cmd
            river_python_cmd = selected_river_python_cmd

            append_log("[INFO] Checking dependencies for the selected ST-SM / River environments...")
            env_check, env_errors = validate_envs_with_client(
                client,
                stsm_python_cmd,
                river_python_cmd,
                raise_on_missing=False,
            )

            msg = "SSH login succeeded." + (f" Remote output: {out}" if out else "")
            if env_errors:
                msg += " Remote environment dependency checks did not pass: " + "; ".join(env_errors)
            set_state(
                "connected",
                host=host,
                port=port,
                username=username,
                password=password,
                key_text=key_text,
                remote_workspace=remote_workspace,
                python_cmd=stsm_python_cmd,
                stsm_python_cmd=stsm_python_cmd,
                river_python_cmd=river_python_cmd,
                env_choices=env_choices,
                env_check=env_check,
                message=msg,
            )
            append_log("[OK] " + msg)
            if err:
                append_log("[REMOTE STDERR] " + err)
            client.close()
        except Exception as e:
            try:
                client.close()
            except Exception:
                pass
            msg = f"SSH login failed: {e}"
            set_state("error", host=host, port=port, username=username, message=msg)
            append_log("[ERROR] " + msg)
            append_log(traceback.format_exc())

    @reactive.Effect
    @reactive.event(input.ssh_validate_envs)
    def _validate_selected_envs():
        st = ssh_state.get()
        if st.get("status") != "connected":
            append_log("[WARN] Please test and connect SSH before validating remote environment dependencies.")
            return

        try:
            stsm_cmd = input.ssh_stsm_env_choice() or st.get("stsm_python_cmd", DEFAULT_STSM_PYTHON)
            river_cmd = input.ssh_river_env_choice() or st.get("river_python_cmd", DEFAULT_RIVER_PYTHON)
        except Exception:
            stsm_cmd = st.get("stsm_python_cmd", DEFAULT_STSM_PYTHON)
            river_cmd = st.get("river_python_cmd", DEFAULT_RIVER_PYTHON)

        client = None
        try:
            client = ssh_open_client(st)
            append_log("[INFO] Validating selected remote environment dependencies...")
            env_check, env_errors = validate_envs_with_client(
                client,
                stsm_cmd,
                river_cmd,
                raise_on_missing=False,
            )

            message = f"Selected remote environments: ST-SM={stsm_cmd}; River={river_cmd}"
            if env_errors:
                message += ". Missing dependencies: " + "; ".join(env_errors)
            else:
                message += ". Dependency checks passed."

            set_state(
                "connected",
                host=st.get("host", ""),
                port=st.get("port", 22),
                username=st.get("username", ""),
                password=st.get("password", ""),
                key_text=st.get("key_text", ""),
                remote_workspace=st.get("remote_workspace", DEFAULT_REMOTE_WORKDIR),
                stsm_python_cmd=stsm_cmd,
                river_python_cmd=river_cmd,
                env_choices=st.get("env_choices", []),
                env_check=env_check,
                message=message,
            )
        except Exception as e:
            append_log(f"[ERROR] Remote environment validation failed: {e}")
            append_log(traceback.format_exc())
        finally:
            if client is not None:
                client.close()

    @reactive.Effect
    @reactive.event(input.ssh_install_missing)
    def _install_missing_remote_packages():
        st = ssh_state.get()
        if st.get("status") != "connected":
            append_log("[WARN] Please test and connect SSH before installing remote packages.")
            return

        try:
            stsm_cmd = input.ssh_stsm_env_choice() or st.get("stsm_python_cmd", DEFAULT_STSM_PYTHON)
            river_cmd = input.ssh_river_env_choice() or st.get("river_python_cmd", DEFAULT_RIVER_PYTHON)
        except Exception:
            stsm_cmd = st.get("stsm_python_cmd", DEFAULT_STSM_PYTHON)
            river_cmd = st.get("river_python_cmd", DEFAULT_RIVER_PYTHON)

        try:
            wheelhouse_text = (input.ssh_local_wheelhouse() or st.get("wheelhouse_path") or DEFAULT_LOCAL_WHEELHOUSE).strip()
        except Exception:
            wheelhouse_text = st.get("wheelhouse_path") or DEFAULT_LOCAL_WHEELHOUSE
        try:
            remote_package_dir = (input.ssh_remote_package_dir() or st.get("remote_package_dir") or DEFAULT_REMOTE_PACKAGE_DIR).strip()
        except Exception:
            remote_package_dir = st.get("remote_package_dir") or DEFAULT_REMOTE_PACKAGE_DIR

        client = None
        try:
            client = ssh_open_client(st)
            append_log("[INFO] Checking missing remote packages before offline installation...")
            initial_check, _ = validate_envs_with_client(
                client,
                stsm_cmd,
                river_cmd,
                raise_on_missing=False,
            )

            fatal = [
                f"{label}: {initial_check.get(key, {}).get('error', 'command failed')}"
                for key, label in [("stsm", "ST-SM"), ("river", "River")]
                if initial_check.get(key, {}).get("command_ok") is False
            ]
            if fatal:
                message = "Cannot install packages until the selected Python command runs successfully. " + "; ".join(fatal)
                append_log("[ERROR] " + message)
                set_state(
                    "connected",
                    host=st.get("host", ""),
                    port=st.get("port", 22),
                    username=st.get("username", ""),
                    password=st.get("password", ""),
                    key_text=st.get("key_text", ""),
                    remote_workspace=st.get("remote_workspace", DEFAULT_REMOTE_WORKDIR),
                    stsm_python_cmd=stsm_cmd,
                    river_python_cmd=river_cmd,
                    env_choices=st.get("env_choices", []),
                    env_check=initial_check,
                    wheelhouse_path=wheelhouse_text,
                    remote_package_dir=remote_package_dir,
                    message=message,
                )
                return

            missing_jobs = []
            for key, label, cmd, packages in [
                ("stsm", "ST-SM", stsm_cmd, REQUIRED_STSM_PACKAGES),
                ("river", "River", river_cmd, REQUIRED_RIVER_PACKAGES),
            ]:
                missing = initial_check.get(key, {}).get("missing") or []
                if missing:
                    missing_jobs.append((key, label, cmd, packages))

            if not missing_jobs:
                append_log("[OK] No missing packages were detected. Nothing to install.")
                set_state(
                    "connected",
                    host=st.get("host", ""),
                    port=st.get("port", 22),
                    username=st.get("username", ""),
                    password=st.get("password", ""),
                    key_text=st.get("key_text", ""),
                    remote_workspace=st.get("remote_workspace", DEFAULT_REMOTE_WORKDIR),
                    stsm_python_cmd=stsm_cmd,
                    river_python_cmd=river_cmd,
                    env_choices=st.get("env_choices", []),
                    env_check=initial_check,
                    wheelhouse_path=wheelhouse_text,
                    remote_package_dir=remote_package_dir,
                    message="Selected remote environments already have all required packages.",
                )
                return

            local_wheelhouse = ssh_resolve_local_wheelhouse(wheelhouse_text)
            extract_python_cmd = missing_jobs[0][2]
            remote_wheelhouse = ssh_upload_local_wheelhouse(
                client,
                local_wheelhouse,
                st.get("remote_workspace", DEFAULT_REMOTE_WORKDIR),
                extract_python_cmd,
                remote_package_dir,
                append_log,
            )

            install_summary = {}
            for key, label, cmd, packages in missing_jobs:
                install_summary[key] = ssh_install_missing_packages_from_wheelhouse(
                    client,
                    cmd,
                    packages,
                    remote_wheelhouse,
                    label=label,
                    log=append_log,
                )

            append_log("[INFO] Re-validating remote environments after installation...")
            env_check, env_errors = validate_envs_with_client(
                client,
                stsm_cmd,
                river_cmd,
                raise_on_missing=False,
            )
            message = "Offline package installation completed."
            if env_errors:
                message += " Some dependency checks still failed: " + "; ".join(env_errors)
            else:
                message += " Dependency checks passed."

            set_state(
                "connected",
                host=st.get("host", ""),
                port=st.get("port", 22),
                username=st.get("username", ""),
                password=st.get("password", ""),
                key_text=st.get("key_text", ""),
                remote_workspace=st.get("remote_workspace", DEFAULT_REMOTE_WORKDIR),
                stsm_python_cmd=stsm_cmd,
                river_python_cmd=river_cmd,
                env_choices=st.get("env_choices", []),
                env_check=env_check,
                wheelhouse_path=wheelhouse_text,
                remote_package_dir=remote_package_dir,
                install_summary=install_summary,
                message=message,
            )
            append_log("[OK] " + message)
        except Exception as e:
            append_log(f"[ERROR] Remote offline package installation failed: {e}")
            append_log(traceback.format_exc())
        finally:
            if client is not None:
                client.close()

    @reactive.Effect
    @reactive.event(input.ssh_disconnect)
    def _disconnect_ssh():
        set_state("local", message="Returned to local mode.")
        append_log("[INFO] SSH has been disconnected. Switched back to local mode.")

    @output
    @render.ui
    def ssh_status_card():
        st = ssh_state.get()
        status = st.get("status", "local")
        host = st.get("host", "")
        port = st.get("port", 22)
        username = st.get("username", "")
        message = st.get("message", "")

        if status == "connected":
            pill_cls = "ssh-pill connected"
            pill_text = "Remote mode"
            title = "SSH Connected"
            desc = f"Current connection: {username}@{host}:{port}. {message}"
        elif status == "error":
            pill_cls = "ssh-pill error"
            pill_text = "Connection failed"
            title = "SSH Connection Error"
            desc = message or "Connection failed. Please check the host, port, username, password, key, or network."
        else:
            pill_cls = "ssh-pill local"
            pill_text = "Local mode"
            title = "SSH Not Connected"
            desc = message or "Analysis runs locally by default."

        return ui.tags.div(
            ui.tags.div(
                ui.tags.div(title, class_="ssh-status-title"),
                ui.tags.div(desc, class_="ssh-status-desc"),
            ),
            ui.tags.div(
                ui.tags.span(class_="ssh-dot"),
                ui.tags.span(pill_text),
                class_=pill_cls
            ),
            class_="ssh-status-card"
        )

    @output
    @render.ui
    def ssh_env_check_card():
        st = ssh_state.get()
        checks = st.get("env_check") or {}
        if not checks:
            return ui.tags.div(
                ui.tags.h4("Environment Check"),
                ui.tags.div("Connect SSH to scan environments and validate required packages.", class_="ssh-muted"),
            )

        def build_item(key, label):
            check = checks.get(key) or {}
            ok = bool(check.get("ok"))
            missing = check.get("missing") or []
            command_ok = check.get("command_ok")
            badge_text = "Ready" if ok else ("Command error" if command_ok is False else "Needs packages")
            badge_cls = "ssh-check-badge ok" if ok else "ssh-check-badge warn"
            meta_parts = []
            cmd = check.get("cmd") or ""
            if cmd:
                meta_parts.append(f"Command: {cmd}")
            if check.get("python") or check.get("version"):
                meta_parts.append(f"Python: {check.get('python', '')} {check.get('version', '')}".strip())
            if command_ok is False and check.get("error"):
                meta_parts.append("Error: " + str(check.get("error")))
            elif missing:
                meta_parts.append("Missing: " + ", ".join(missing))
            elif check.get("error") and not ok:
                meta_parts.append("Error: " + str(check.get("error")))
            else:
                meta_parts.append("Required packages are available.")

            return ui.tags.div(
                ui.tags.div(
                    ui.tags.span(label),
                    ui.tags.span(badge_text, class_=badge_cls),
                    class_="ssh-check-head",
                ),
                ui.tags.div(" | ".join(meta_parts), class_="ssh-check-meta"),
                class_="ssh-check-card",
            )

        return ui.tags.div(
            ui.tags.h4("Environment Check"),
            ui.tags.div(
                build_item("stsm", "ST-SM"),
                build_item("river", "River"),
                class_="ssh-check-grid",
            ),
        )

    @output
    @render.text
    def ssh_log():
        return ssh_log_value.get()

    return ssh_state
