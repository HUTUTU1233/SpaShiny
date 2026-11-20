# Original feature imports, constants and direct helper functions; no duplicate UI/server bodies.
from pathlib import Path as _ExportPath

LEGACY_ENTRYPOINT_FILE = str(_ExportPath(__file__).resolve().parents[3] / "ssh_module.py")
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
REQUIRED_RIVER_PACKAGES = [
    "anndata",
    "captum",
    "matplotlib",
    "numpy",
    "pandas",
    "scanpy",
    "scSLAT",
    "sklearn",
    "torch",
    "tqdm",
]
DEFAULT_LOCAL_WHEELHOUSE = "runtime/wheelhouse"
DEFAULT_REMOTE_PACKAGE_DIR = "data/packages"
IMPORT_TO_PIP_PACKAGE = {"sklearn": "scikit-learn", "pyimzml": "pyimzML"}
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
        raise RuntimeError(
            "paramiko is not installed, so the SSH private key cannot be parsed."
        ) from e
    key_classes = [
        getattr(paramiko, "Ed25519Key", None),
        getattr(paramiko, "RSAKey", None),
        getattr(paramiko, "ECDSAKey", None),
        getattr(paramiko, "DSSKey", None),
    ]
    last_error = None
    for key_cls in [cls for cls in key_classes if cls is not None]:
        try:
            return key_cls.from_private_key(io.StringIO(key_text), password=passphrase or None)
        except Exception as e:
            last_error = e
    raise ValueError(f"Could not parse the private key text: {last_error}")


def ssh_open_client(state, timeout=15):
    if not ssh_connection_ready(state):
        raise RuntimeError(
            "SSH is not connected. Please test and connect on the SSH Connection page first."
        )
    try:
        import paramiko
    except Exception as e:
        raise RuntimeError(
            "paramiko is not installed. Please install it in the current Python environment: pip install paramiko"
        ) from e
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

    stdin, stdout, stderr = client.exec_command(command, timeout=timeout, get_pty=get_pty)
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
    return {"exit_status": exit_status, "stdout": out, "stderr": err, "command": command}


def _python_env_label(python_path, version=""):
    normalized = str(python_path).rstrip("/")
    env_name = (
        normalized.split("/")[-3]
        if normalized.endswith("/bin/python") and len(normalized.split("/")) >= 3
        else ""
    )
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
    if any((item.get("command") == command for item in choices)):
        return
    choices.append({"label": label, "command": command})


def ssh_discover_python_envs(client):
    choices = [
        {"label": "python (PATH)", "command": "python"},
        {"label": "python3 (PATH)", "command": "python3"},
    ]
    command = "for tool in conda mamba micromamba; do if command -v $tool >/dev/null 2>&1; then $tool env list --json 2>/dev/null && break; fi; done"
    result = ssh_exec_command(client, command, timeout=30)
    stdout = (result.get("stdout") or "").strip()
    if stdout:
        start = stdout.find("{")
        end = stdout.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(stdout[start : end + 1])
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
                        choices, f"{env_name} - {python_path}", ssh_quote(python_path)
                    )
            except Exception:
                pass
    common_paths = "python python3 $HOME/miniconda3/bin/python $HOME/anaconda3/bin/python $HOME/mambaforge/bin/python $HOME/miniforge3/bin/python $HOME/miniconda3/envs/*/bin/python $HOME/anaconda3/envs/*/bin/python $HOME/mambaforge/envs/*/bin/python $HOME/miniforge3/envs/*/bin/python $HOME/envs/*/bin/python /opt/conda/bin/python /opt/conda/envs/*/bin/python"
    probe_command = f"""for p in {common_paths}; do [ -x "$p" ] || command -v "$p" >/dev/null 2>&1 || continue; resolved=$("$p" -c 'import sys; print(sys.executable)' 2>/dev/null) || continue; version=$("$p" -c 'import sys; print(sys.version.split()[0])' 2>/dev/null) || version=''; printf 'PYENV\\t%s\\t%s\\n' "$resolved" "$version"; done"""
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
                    choices, _python_env_label(python_path, version), ssh_quote(python_path)
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
    code = f"import importlib.util,json,sys;pkgs={json.dumps(packages)};present=[];missing=[];[(present if importlib.util.find_spec(p) is not None else missing).append(p) for p in pkgs];print(json.dumps({{'python':sys.executable,'version':sys.version.split()[0],'present':present,'missing':missing}},ensure_ascii=False));"
    result = ssh_exec_command(client, f"{python_cmd} -c {ssh_quote(code)}", timeout=90)
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
        raise RuntimeError(
            f"{label} environment is missing required package(s): {', '.join(missing)}"
        )
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
        path = Path(LEGACY_ENTRYPOINT_FILE).resolve().parents[1] / path
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
    return any((name.endswith(suffix) for suffix in WHEELHOUSE_SUFFIXES))


def ssh_prepare_wheelhouse_archive(local_wheelhouse):
    local_wheelhouse = Path(local_wheelhouse)
    if not local_wheelhouse.exists():
        raise FileNotFoundError(f"Local wheelhouse path does not exist: {local_wheelhouse}")
    if local_wheelhouse.is_file():
        if local_wheelhouse.suffix.lower() != ".zip":
            raise ValueError("Local wheelhouse file must be a .zip archive.")
        return (local_wheelhouse, False, f"{local_wheelhouse.name}")
    package_files = [
        p for p in local_wheelhouse.rglob("*") if p.is_file() and _is_wheelhouse_file(p)
    ]
    if not package_files:
        raise ValueError(
            "The local wheelhouse folder does not contain .whl/.tar.gz/.tar.bz2/.zip package files. Build or place compatible package archives there first."
        )
    tmp = tempfile.NamedTemporaryFile(prefix="spashiny_wheelhouse_", suffix=".zip", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()
    with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for package_file in package_files:
            zf.write(package_file, package_file.name)
    return (tmp_path, True, f"{local_wheelhouse} ({len(package_files)} package file(s))")


def ssh_upload_local_wheelhouse(
    client,
    local_wheelhouse,
    remote_workspace,
    extract_python_cmd,
    remote_package_dir=None,
    log=None,
):
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
        extract_cmd = f"mkdir -p {ssh_quote(remote_wheelhouse)} && {extract_python_cmd} -m zipfile -e {ssh_quote(remote_zip)} {ssh_quote(remote_wheelhouse)}"
        result = ssh_exec_command(client, extract_cmd, timeout=None)
        if result.get("exit_status") != 0:
            raise RuntimeError(
                f"Failed to extract wheelhouse on the remote server.\nSTDOUT:\n{result.get('stdout', '')}\nSTDERR:\n{result.get('stderr', '')}"
            )
        log(f"[OK] Wheelhouse extracted on remote server: {remote_wheelhouse}")
        return remote_wheelhouse
    finally:
        if is_temp:
            try:
                archive_path.unlink()
            except Exception:
                pass


def ssh_install_missing_packages_from_wheelhouse(
    client, python_cmd, packages, remote_wheelhouse, label="Python", log=None
):
    log = log or (lambda _msg: None)
    before = ssh_probe_python_packages(client, python_cmd, packages)
    if before.get("exit_status") != 0:
        raise RuntimeError(
            f"{label} environment could not run the dependency probe.\nSTDOUT:\n{before.get('stdout', '')}\nSTDERR:\n{before.get('stderr', '')}"
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
                f"{label} environment does not have pip, and ensurepip failed.\nSTDOUT:\n{ensure.get('stdout', '')}\nSTDERR:\n{ensure.get('stderr', '')}"
            )
    package_args = " ".join((ssh_quote(pkg) for pkg in pip_packages))
    install_cmd = f"{python_cmd} -m pip install --no-index --find-links {ssh_quote(remote_wheelhouse)} {package_args}"
    result = ssh_exec_command(client, install_cmd, timeout=None)
    if result.get("exit_status") != 0:
        raise RuntimeError(
            f"{label} offline package installation failed.\nSTDOUT:\n{result.get('stdout', '')}\nSTDERR:\n{result.get('stderr', '')}"
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
            f"Failed to create remote directory: {remote_path}\nSTDOUT:\n{result['stdout']}\nSTDERR:\n{result['stderr']}"
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
            remote_root = (
                str(remote_dir)
                if str(rel_root) == "."
                else posixpath.join(str(remote_dir), *rel_root.parts)
            )
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
            f"Failed to create the remote job directory.\nSTDOUT:\n{result['stdout']}\nSTDERR:\n{result['stderr']}"
        )
    resolved = result["stdout"].strip().splitlines()
    return resolved[-1] if resolved else remote_job_dir


def ssh_module_ui():
    from spashiny.features.connection.ui import ssh_module_ui as _entry

    return _entry()


def ssh_status_indicator_ui(status, host="", username=""):
    from spashiny.features.connection.ui import ssh_status_indicator_ui as _entry

    return _entry(status, host, username)


def ssh_module_server(input, output, session):
    from spashiny.features.connection.server import ssh_module_server as _entry

    return _entry(input, output, session)
