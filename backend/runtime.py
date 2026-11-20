"""Prepare the shared sources and run an existing SpaShiny service."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time


PROJECT = Path(__file__).resolve().parents[1]
LAYOUT = PROJECT / "config" / "runtime_layout.json"
ROLES = {
    "web": ("web", ["-m", "uvicorn", "cloud.web_proxy_app:app", "--host", "127.0.0.1", "--port", "8001"]),
    "control": ("backend/control", ["-m", "uvicorn", "cloud.api:app", "--host", "127.0.0.1", "--port", "8000"]),
    "cpu": ("backend/cpu", ["-m", "cloud.cpu_worker"]),
    "alignment-light": ("backend/alignment_light", ["-m", "cloud.alignment_queue_worker", "--queue-class", "alignment_light"]),
    "alignment-heavy": ("backend/alignment_heavy", ["-m", "cloud.alignment_queue_worker", "--queue-class", "alignment_heavy"]),
    "gpu": ("backend/gpu", ["host_gpu_worker.py"]),
    "watchdog": ("backend/session_watchdog", ["-m", "cloud.session_watchdog_runner"]),
}


def contained(root: Path, relative: str) -> Path:
    rel = PurePosixPath(relative)
    if not relative or rel.is_absolute() or ".." in rel.parts or "\\" in relative or ":" in relative:
        raise ValueError(f"Invalid relative source path: {relative!r}")
    result = (root / Path(*rel.parts)).resolve()
    result.relative_to(root.resolve())
    return result


def layout_files() -> dict[str, str]:
    document = json.loads(LAYOUT.read_text(encoding="utf-8"))
    if document.get("schema") != "spashiny.shared-source.v1" or not isinstance(document.get("files"), dict):
        raise ValueError("Unsupported source layout")
    files = dict(document["files"])
    # New service modules can be added normally; shared aliases remain explicit.
    for folder in (PROJECT / "web", PROJECT / "backend"):
        for path in folder.rglob("*"):
            relative = path.relative_to(PROJECT).as_posix()
            if (not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc"
                    or relative.startswith("backend/shared/") or relative == "backend/runtime.py"):
                continue
            files.setdefault(relative, relative)
    return files


def prepare(output: str | None = None) -> Path:
    files = layout_files()
    if output:
        destination = Path(output).resolve()
        if destination == PROJECT or PROJECT in destination.parents or destination in PROJECT.parents:
            raise ValueError("The runtime directory must be outside the source project")
        # Never overwrite an existing directory, results or user data.
        destination.mkdir(parents=True, exist_ok=False)
    else:
        destination = Path(tempfile.mkdtemp(prefix="spashiny-runtime-"))
    records = []
    for relative, canonical in sorted(files.items()):
        source = contained(PROJECT, canonical)
        if not source.is_file() or source.is_symlink():
            raise FileNotFoundError(f"Shared source is missing: {canonical}")
        target = contained(destination, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise OSError(f"Source copy verification failed: {relative}")
        records.append({"path": relative, "source": canonical, "sha256": digest})
    (destination / "runtime_manifest.json").write_text(
        json.dumps({"schema": "spashiny.runtime.v1", "files": records}, indent=2) + "\n",
        encoding="utf-8")
    return destination


def service_environment(runtime: Path, role: str, base: dict[str, str] | None = None) -> tuple[Path, dict[str, str]]:
    folder = runtime / ROLES[role][0]
    env = dict(os.environ if base is None else base)
    paths = [str(folder / "app"), str(folder)]
    if env.get("PYTHONPATH"):
        paths.append(env["PYTHONPATH"])
    env.update(PYTHONPATH=os.pathsep.join(paths), PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1")
    return folder, env


def stop_children(children: list[subprocess.Popen]) -> None:
    for child in children:
        if child.poll() is None:
            child.terminate()
    for child in children:
        try:
            child.wait(timeout=8)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=8)


def local_environment(state: Path, web_port: int, control_port: int) -> dict[str, str]:
    state.mkdir(parents=True, exist_ok=True)
    key_path = state / "session.key"
    if not key_path.exists():
        # Local credentials belong in the user's state directory, not the sources.
        with key_path.open("x", encoding="utf-8") as handle:
            handle.write(secrets.token_urlsafe(48))
        if os.name != "nt":
            key_path.chmod(0o600)
    env = dict(os.environ)
    env.update({
        "SPASHINY_DEPLOYMENT_PROFILE": "lab_server", "SPASHINY_DEPLOYMENT_MODE": "lab",
        "SPASHINY_WEB_PLATFORM": "1", "SPASHINY_STORAGE_BACKEND": "local",
        "SPASHINY_COMPUTE_PROVIDER_MODE": "local", "RUNPOD_PROVIDER_MODE": "local",
        "SPASHINY_R2_ENABLED": "0", "R2_ENABLED": "0", "SPASHINY_REMOTE_PROVIDER_ENABLED": "0",
        "REMOTE_PROVIDER_ENABLED": "0", "SPASHINY_DATABASE_URL": "", "SPASHINY_REDIS_URL": "",
        "SPASHINY_WORKSPACE": str(state / "workspace"),
        "SPASHINY_SESSION_HMAC_SECRET": key_path.read_text(encoding="utf-8").strip(),
        "SPASHINY_CONTROL_API_BASE_URL": f"http://127.0.0.1:{control_port}",
        "PUBLIC_BASE_URL": f"http://127.0.0.1:{web_port}",
        "SPASHINY_PUBLIC_ORIGIN": f"http://127.0.0.1:{web_port}",
    })
    for name, folder in {"DATA": "data", "OBJECT": "objects", "SQLITE": "sqlite",
                         "RESULT": "results", "JOBS": "jobs", "LOGS": "logs"}.items():
        env[f"SPASHINY_LOCAL_{name}_ROOT"] = str(state / folder)
    env["SPASHINY_TEMP_ROOT"] = str(state / "temp")
    env["NO_PROXY"] = "127.0.0.1,localhost,::1"
    env.setdefault("SESSION_IDLE_TIMEOUT_SECONDS", "43200")
    env.setdefault("SPASHINY_EXAMPLE_PRECOMPUTE_ENABLED", "0")
    return env


def run_local(args: argparse.Namespace) -> int:
    missing = [name for name in ("uvicorn", "fastapi", "shiny", "scanpy", "spatialmeta", "torch")
               if importlib.util.find_spec(name) is None]
    if missing:
        raise RuntimeError("The selected Python environment is missing: " + ", ".join(missing)
                           + ". Activate the SpaShiny environment or set SPASHINY_PYTHON in Start.bat.")
    if args.web_port == args.control_port:
        raise ValueError("Web and Control need different ports")
    for port in (args.web_port, args.control_port):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                raise RuntimeError(f"Port {port} is already in use; no existing process was stopped")
    state = Path(args.state_dir).expanduser().resolve() if args.state_dir else (
        Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share"))) / "SpaShiny" / "local")
    if state == PROJECT or PROJECT in state.parents or state in PROJECT.parents:
        raise ValueError("Local analysis data must be outside the source project")
    env = local_environment(state, args.web_port, args.control_port)
    runtime = prepare()
    print(f"Runtime: {runtime}\nLocal data: {state}\nWebsite: http://127.0.0.1:{args.web_port}", flush=True)
    children: list[subprocess.Popen] = []
    logs = []
    roles = [("control", args.control_port), ("web", args.web_port)]
    if not args.no_worker:
        roles.append(("cpu", None))
    try:
        for role, port in roles:
            folder, child_env = service_environment(runtime, role, env)
            command = [sys.executable, "-B"] + ROLES[role][1]
            if port is not None:
                command[-1] = str(port)
            log_folder = state / "logs"
            log_folder.mkdir(parents=True, exist_ok=True)
            log = (log_folder / f"{role}.log").open("a", encoding="utf-8")
            logs.append(log)
            child = subprocess.Popen(command, cwd=folder, env=child_env, stdout=log, stderr=subprocess.STDOUT)
            children.append(child)
            print(f"Started {role}; log: {log_folder / (role + '.log')}", flush=True)
        while True:
            for role, child in zip(roles, children):
                if child.poll() is not None:
                    print(f"{role[0]} exited ({child.returncode}). Check {state / 'logs' / (role[0] + '.log')}", file=sys.stderr)
                    return child.returncode or 1
            time.sleep(0.5)
    except KeyboardInterrupt:
        return 0
    finally:
        stop_children(children)
        for log in logs:
            log.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    create = commands.add_parser("prepare", help="Assemble the original service directories without running jobs")
    create.add_argument("--output", help="New directory outside this source project; existing directories are rejected")
    run = commands.add_parser("run", help="Run one existing service in its configured Python environment")
    run.add_argument("role", choices=sorted(ROLES))
    run.add_argument("arguments", nargs=argparse.REMAINDER)
    local = commands.add_parser("local", help="Run local Web, Control and CPU services; no GPU worker is started")
    local.add_argument("--web-port", type=int, default=8001)
    local.add_argument("--control-port", type=int, default=8000)
    local.add_argument("--state-dir")
    local.add_argument("--no-worker", action="store_true", help="Preview the UI/API without consuming analysis jobs")
    args = parser.parse_args(argv)
    if args.action == "prepare":
        print(prepare(args.output))
        return 0
    if args.action == "local":
        return run_local(args)
    runtime = prepare()
    folder, env = service_environment(runtime, args.role)
    extra = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
    command = [sys.executable, "-B"] + ROLES[args.role][1] + extra
    print(f"Runtime: {runtime}", flush=True)
    children: list[subprocess.Popen] = []
    try:
        children.append(subprocess.Popen(command, cwd=folder, env=env))
        return children[0].wait()
    except KeyboardInterrupt:
        return 0
    finally:
        stop_children(children)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"SpaShiny could not start: {exc}", file=sys.stderr)
        raise SystemExit(1)
