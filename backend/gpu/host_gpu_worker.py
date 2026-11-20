from __future__ import annotations

import argparse
import json
import os
import signal
import shutil
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from cloud.config import load_cloud_config
from cloud.database import CloudDatabase, db_debug_stage
from cloud.input_resolver import InputResolver
from cloud.worker_io import build_input_files, download_worker_input_assets, write_sanitized_input_manifest
from cloud.executors.base import ExecutorResult
from cloud.executors.local_gpu import LocalGPUExecutor
from cloud.job_dispatcher import JobDispatcher
from cloud.job_queue_repository import JobQueueRepository
from cloud.lab_runtime import LAB_GPU_QUEUE_NAMES, LAB_GPU_UI_LABELS, lab_gpu_manifest, safe_session_child
from cloud.models import JobRecord, JobStatus, ResourceType
from cloud.result_publisher import ResultPublisher


HOST_ROOT = Path(os.environ.get("SPASHINY_LAB_ROOT", "/srv/spashiny")).resolve()
HOTFIX_RUNTIME_ROOT = Path(
    os.environ.get(
        "SPASHINY_HOTFIX_RUNTIME_ROOT",
        str(HOST_ROOT / "hotfixes/example-runtime-20260804/server-dev-step1/runtime-test"),
    )
).resolve()
HOST_GPU_ENV = Path(os.environ.get("SPASHINY_HOST_GPU_ENV", str(HOST_ROOT / "runtime/gpu-env-hotfix11"))).resolve()


def fixed_random_seed(parameters: dict[str, Any] | None) -> int:
    raw = (parameters or {}).get("random_seed", os.environ.get("SPASHINY_RANDOM_SEED", "42"))
    try:
        seed = int(raw)
    except (TypeError, ValueError):
        return 42
    return seed if 0 <= seed <= 2_147_483_647 else 42


def map_container_path(value: str | os.PathLike[str] | None) -> Path:
    raw = str(value or "")
    mappings = [
        ("/workspace/data/examples", HOST_ROOT / "data/examples"),
        (str(HOST_ROOT / "data/examples"), HOST_ROOT / "data/examples"),
        ("/workspace/data/sessions", HOTFIX_RUNTIME_ROOT / "data/sessions"),
        (str(HOST_ROOT / "data/sessions"), HOTFIX_RUNTIME_ROOT / "data/sessions"),
        ("/workspace/results", HOTFIX_RUNTIME_ROOT / "results"),
        ("/workspace/jobs", HOTFIX_RUNTIME_ROOT / "jobs"),
        ("/workspace/logs", HOTFIX_RUNTIME_ROOT / "logs"),
        ("/workspace/sqlite", HOTFIX_RUNTIME_ROOT / "sqlite"),
        ("/workspace/data", HOTFIX_RUNTIME_ROOT / "data"),
    ]
    for prefix, target in mappings:
        if raw == prefix:
            return target
        if raw.startswith(prefix + "/"):
            return target / raw[len(prefix) + 1 :]
    return Path(raw)


def map_container_results_workspace(value: str, host_result_root: Path) -> Path:
    """Map only the canonical result namespace before resolver validation."""
    prefix = "/workspace/results/"
    raw = str(value or "")
    if not raw.startswith(prefix):
        raise ValueError("Parent KNN workspace is outside the container result namespace.")
    parts = raw[len(prefix) :].split("/")
    if any(not part or part in {".", ".."} or "\\" in part for part in parts):
        raise ValueError("Parent KNN workspace contains an unsafe path component.")
    root = Path(host_result_root).resolve()
    mapped = root.joinpath(*parts).resolve()
    if root not in mapped.parents:
        raise ValueError("Parent KNN workspace escapes the configured result root.")
    return mapped


def execution_workspace_host(job: JobRecord) -> Path:
    # Host-native GPU computation must happen in a host-writable bind mount.
    # Rootless Docker-created result/session directories appear on the host as
    # subordinate uid-owned 0755 directories, so they are not safe scratch dirs.
    return (HOTFIX_RUNTIME_ROOT / "jobs" / str(job.job_id)).resolve()


def execution_workspace_container(job: JobRecord) -> str:
    # Platform/container path semantics stored in JobManager while running.
    return f"/workspace/jobs/{str(job.job_id)}"


def final_result_workspace_container(job: JobRecord) -> str:
    session_id = str(job.session_id or job.owner_session_id or job.user_id or "").strip()
    if not session_id.startswith("sess_"):
        session_id = "sess_host_gpu"
    # Keep final artifacts under /workspace/results/sessions, but avoid the
    # rootless-owned session dir created by Control by using a GPU publication
    # sibling that host can create from the writable sessions root.
    final_session_id = f"{session_id}__hostgpu"
    final_host = safe_session_child(HOTFIX_RUNTIME_ROOT / "results" / "sessions", final_session_id, str(job.job_id))
    rel = final_host.relative_to((HOTFIX_RUNTIME_ROOT / "results").resolve()).as_posix()
    return f"/workspace/results/{rel}"


def final_result_workspace_host(job: JobRecord) -> Path:
    return map_container_path(final_result_workspace_container(job)).resolve()


def map_host_to_container_path(value: str | os.PathLike[str] | None) -> str:
    raw = str(value or "")
    if not raw:
        return ""
    path = Path(raw).resolve()
    mappings = [
        (HOTFIX_RUNTIME_ROOT / "results", "/workspace/results"),
        (HOTFIX_RUNTIME_ROOT / "jobs", "/workspace/jobs"),
        (HOTFIX_RUNTIME_ROOT / "logs", "/workspace/logs"),
        (HOTFIX_RUNTIME_ROOT / "sqlite", "/workspace/sqlite"),
        (HOTFIX_RUNTIME_ROOT / "data", "/workspace/data"),
        (HOST_ROOT / "data/examples", "/workspace/data/examples"),
    ]
    for host_root, container_root in mappings:
        resolved_root = host_root.resolve()
        if path == resolved_root:
            return container_root
        if resolved_root in path.parents:
            return container_root.rstrip("/") + "/" + path.relative_to(resolved_root).as_posix()
    return raw


def sanitize_publication_paths(payload: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in dict(payload or {}).items():
        if isinstance(value, str) and key.endswith("_path"):
            sanitized[key] = map_host_to_container_path(value)
        else:
            sanitized[key] = value
    return sanitized


def map_job(job: JobRecord) -> JobRecord:
    return replace(job, local_workspace=str(execution_workspace_host(job)))


class HostPathResultPublisher(ResultPublisher):
    def publish(self, job: JobRecord) -> dict[str, Any]:
        execution_root = execution_workspace_host(job)
        final_container = final_result_workspace_container(job)
        final_job = replace(job, local_workspace=final_container)
        final_root = final_result_workspace_host(job)
        self._copy_execution_results(execution_root, final_root,
            river_only=(job.workflow_name or job.workflow)=='river_spatial_transcriptomics')
        if job.worker_id and job.claim_token:
            queue = JobQueueRepository(database=CloudDatabase(config=self.config), config=self.config)
            final_job = queue.update_claimed_job(
                job.job_id,
                job.worker_id,
                job.claim_token,
                job.status,
                local_workspace=final_container,
            )
        published = super().publish(final_job)
        return sanitize_publication_paths(published)

    def _copy_execution_results(self, execution_root: Path, final_root: Path, *, river_only=False) -> None:
        execution_root = execution_root.resolve()
        final_root = final_root.resolve()
        jobs_root = (HOTFIX_RUNTIME_ROOT / "jobs").resolve()
        results_root = (HOTFIX_RUNTIME_ROOT / "results" / "sessions").resolve()
        if execution_root != jobs_root and jobs_root not in execution_root.parents:
            raise RuntimeError(f"Unsafe GPU execution root: {execution_root}")
        if final_root == results_root or results_root not in final_root.parents:
            raise RuntimeError(f"Unsafe GPU final result root: {final_root}")
        final_root.mkdir(parents=True, exist_ok=True)
        if river_only:
            from cloud.river_outputs import RIVER_PUBLIC_OUTPUTS,RIVER_PUBLIC_RUNTIME_FILES,RIVER_PUBLIC_LOGS
            for name in (*RIVER_PUBLIC_OUTPUTS,*RIVER_PUBLIC_RUNTIME_FILES):
                source=execution_root/name
                if source.is_file() and not source.is_symlink() and source.resolve().parent==execution_root:
                    shutil.copy2(source,final_root/name)
            (final_root/'logs').mkdir(exist_ok=True)
            for name in RIVER_PUBLIC_LOGS:
                source=execution_root/'logs'/name
                if source.is_file() and not source.is_symlink() and source.resolve().parent==execution_root/'logs':
                    shutil.copy2(source,final_root/'logs'/name)
            self._sanitize_published_text_files(final_root)
            return
        # Only named worker-owned artifact directories may cross from the
        # writable execution workspace into the session result directory.
        # Multi-sample QC adds compact JSON tables alongside figures.
        for dirname in ("output", "figures", "tables", "logs", "checkpoints"):
            source = execution_root / dirname
            if source.exists():
                shutil.copytree(source, final_root / dirname, dirs_exist_ok=True)
        for source in execution_root.iterdir() if execution_root.exists() else []:
            if not source.is_file():
                continue
            if source.name in {"results.zip", "results.zip.tmp", "results.zip.sha256"}:
                continue
            shutil.copy2(source, final_root / source.name)
        self._sanitize_published_text_files(final_root)

    def _sanitize_published_text_files(self, final_root: Path) -> None:
        replacements = {
            str(HOTFIX_RUNTIME_ROOT): "/workspace",
            str(HOST_ROOT / "data" / "examples"): "/workspace/data/examples",
            str(HOST_ROOT): "/workspace",
        }
        suffixes = {".json", ".log", ".txt", ".csv", ".tsv", ".yaml", ".yml"}
        for path in final_root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in suffixes:
                continue
            try:
                if path.stat().st_size > 4 * 1024 * 1024:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            sanitized = text
            for old, new in replacements.items():
                sanitized = sanitized.replace(old, new)
            if sanitized != text:
                path.write_text(sanitized, encoding="utf-8")

    def _job_root(self, job: JobRecord) -> Path:
        mapped = map_container_path(job.local_workspace).resolve()
        mapped.mkdir(parents=True, exist_ok=True)
        allowed = [
            HOTFIX_RUNTIME_ROOT / "results",
            HOTFIX_RUNTIME_ROOT / "jobs",
            HOTFIX_RUNTIME_ROOT / "logs",
            HOTFIX_RUNTIME_ROOT / "sqlite",
            HOTFIX_RUNTIME_ROOT / "data",
            HOST_ROOT / "data/examples",
        ]
        if not any(mapped == root.resolve() or root.resolve() in mapped.parents for root in allowed):
            raise RuntimeError(f"Mapped job workspace is outside allowed host runtime roots: {mapped}")
        return mapped


class HostNativeGPUExecutor(LocalGPUExecutor):
    def __init__(self, *, physical_gpu_index: int, ui_gpu_label: str, gpu_name: str = "", gpu_uuid: str = "", termination_grace_seconds: int = 30) -> None:
        super().__init__(
            physical_gpu_index=physical_gpu_index,
            ui_gpu_label=ui_gpu_label,
            gpu_name=gpu_name,
            gpu_uuid=gpu_uuid,
            termination_grace_seconds=termination_grace_seconds,
        )

    def start(self, job: JobRecord) -> ExecutorResult:
        host_job = map_job(job)
        workspace = Path(host_job.local_workspace)
        self._persist_execution_workspace(job)
        for name in ("input", "working", "output", "figures", "tables", "logs", "checkpoints"):
            (workspace / name).mkdir(parents=True, exist_ok=True)
        parameters = self._parameters(job)
        seed = fixed_random_seed(parameters)
        parameters["random_seed"] = seed
        try:
            input_metadata = self._prepare_inputs(job, workspace)
        except Exception as exc:
            message = f"GPU input resolution failed: {type(exc).__name__}: {exc}"
            return ExecutorResult(JobStatus.FAILED.value, message, "INPUT_RESOLUTION_FAILED")
        if input_metadata.get("input_files"):
            parameters["input_files"] = input_metadata["input_files"]
        parameters["input_plan"] = input_metadata.get("plan") or {}
        parameters_path = workspace / "parameters.json"
        parameters_path.write_text(json.dumps(parameters, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
        manifest = self._gpu_manifest(job)
        manifest["host_native"] = True
        manifest["random_seed"] = seed
        manifest["host_cuda_visible_devices"] = str(self.physical_gpu_index)
        manifest["execution_workspace"] = execution_workspace_container(job)
        manifest_path = workspace / "lab_gpu_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")

        # HIT_SM currently uses the legacy runner because gpu_runner_v2 only
        # accepts the VHiT workflow.  Do not inherit an ambient Intel MKL
        # threading choice into this GNU OpenMP Python stack: mkl-service
        # rejects INTEL when libgomp has already been loaded.  This mirrors
        # the tested V2 thread-layer contract without changing HIT_SM's
        # workflow, model, inputs, or numerical parameters.
        env = os.environ.copy()
        env.pop("MKL_SERVICE_FORCE_INTEL", None)
        pythonpath = [str(Path(__file__).resolve().parent), str(Path.cwd())]
        if env.get("PYTHONPATH"):
            pythonpath.append(env["PYTHONPATH"])
        env.update(
            {
                "PYTHONPATH": os.pathsep.join(pythonpath),
                "SPASHINY_JOB_ID": job.job_id,
                "SPASHINY_WORKFLOW": job.workflow_name or job.workflow,
                "SPASHINY_JOB_WORKSPACE": str(workspace),
                "SPASHINY_PARAMETERS_PATH": str(parameters_path),
                "SPASHINY_WORKER_ID": job.worker_id or env.get("SPASHINY_WORKER_ID", ""),
                "SPASHINY_CLAIM_TOKEN": job.claim_token or env.get("SPASHINY_CLAIM_TOKEN", ""),
                "SPASHINY_GPU_REQUIRED": "1",
                "SPASHINY_ALLOW_CPU_FALLBACK": "0",
                "SPASHINY_ASSIGNED_GPU": str(job.assigned_gpu or f"gpu-{self.physical_gpu_index}"),
                "CUDA_VISIBLE_DEVICES": str(self.physical_gpu_index),
                "SPASHINY_RANDOM_SEED": str(seed),
                "PYTHONHASHSEED": str(seed),
                "MKL_THREADING_LAYER": "GNU",
                "MKL_NUM_THREADS": "1",
                "OMP_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "NUMEXPR_NUM_THREADS": "1",
            }
        )
        command = [
            str(HOST_GPU_ENV / "bin/python"),
            "-m",
            "remote_worker.runner",
            "--job-id",
            job.job_id,
            "--workflow",
            job.workflow_name or job.workflow,
            "--workspace",
            str(workspace),
            "--parameters",
            str(parameters_path),
        ]
        stdout = (workspace / "logs" / "remote_worker.stdout.log").open("ab")
        stderr = (workspace / "logs" / "remote_worker.stderr.log").open("ab")
        # Python -m puts its working directory ahead of PYTHONPATH. River's
        # isolated handler must not resolve the older hotfix cloud package;
        # preserve the original cwd for every other GPU workflow.
        river_cwd = (
            Path(__file__).resolve().parent
            if (job.workflow_name or job.workflow) == "river_spatial_transcriptomics"
            else Path.cwd()
        )
        try:
            proc = subprocess.Popen(
                command,
                cwd=str(Path(__file__).resolve().parent if (job.workflow_name or job.workflow) in {
                    "vit_single_sample_integration", "vhit_multi_sample_integration",
                    "hit_sm_multi_sample_integration", "st_sm_conditional_vae"} else river_cwd),
                env=env,
                stdout=stdout,
                stderr=stderr,
                start_new_session=(os.name != "nt"),
            )
        finally:
            stdout.close()
            stderr.close()
        self.processes[job.job_id] = proc
        metadata = {
            **manifest,
            "pid": int(proc.pid),
            "process_group": str(proc.pid),
            "entrypoint": "host-native-gpu-python -m remote_worker.runner",
            "execution_workspace": execution_workspace_container(job),
        }
        return ExecutorResult(JobStatus.RUNNING.value, "Host-native GPU worker subprocess started.", metadata=metadata)

    def _persist_execution_workspace(self, job: JobRecord) -> None:
        if not job.worker_id or not job.claim_token:
            return
        config = load_cloud_config()
        queue = JobQueueRepository(database=CloudDatabase(config=config), config=config)
        with db_debug_stage("EXECUTOR_PERSIST_WORKSPACE"):
            queue.update_claimed_job(
                job.job_id,
                job.worker_id,
                job.claim_token,
                job.status,
                local_workspace=execution_workspace_container(job),
            )

    def _prepare_inputs(self, job: JobRecord, workspace: Path) -> dict[str, Any]:
        config = load_cloud_config()
        # Input resolution only reads immutable binding/upload metadata. Keep
        # schema initialization and queue writes in the normal dispatcher
        # read-write database instance.
        database = CloudDatabase(config=config, read_only=True)
        plan = InputResolver(
            database=database,
            config=config,
            workspace_path_mapper=lambda stored: map_container_results_workspace(
                stored, config.lab_result_root
            ),
        ).resolve_for_worker(job)
        mapped_plan = self._map_input_plan(plan)
        # Host-native workers cannot safely write into session input directories
        # created by rootless Docker containers (they appear on the host as
        # subordinate uid-owned 0755 paths).  Keep input staging inside the
        # host-writable per-job workspace while preserving read-only example
        # bindings and platform result/job path semantics.
        mapped_plan["materialized_input_dir"] = str(workspace / "input")
        downloaded = download_worker_input_assets(mapped_plan, workspace / "input")
        write_sanitized_input_manifest(workspace=workspace, plan=mapped_plan, downloaded=downloaded)
        return {
            "plan": mapped_plan,
            "downloaded_assets": downloaded,
            "input_source": str(mapped_plan.get("input_source") or ""),
            "input_asset_count": len(downloaded),
            "input_files": build_input_files(downloaded),
        }

    def _map_input_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        mapped = dict(plan or {})
        if mapped.get("materialized_input_dir"):
            mapped["materialized_input_dir"] = str(map_container_path(mapped.get("materialized_input_dir")))
        assets = []
        for item in mapped.get("assets") or []:
            asset = dict(item)
            if asset.get("local_path"):
                asset["local_path"] = str(map_container_path(asset.get("local_path")))
            assets.append(asset)
        mapped["assets"] = assets
        return mapped

    def poll(self, job: JobRecord) -> ExecutorResult:
        result = super().poll(map_job(job))
        if result.status != JobStatus.RUNNING.value:
            return result

        # The child runner persists genuine epoch/phase updates in status.json.
        # Propagate only those small fields through the existing claim token so
        # Shiny can poll JobManager without touching the training process.
        try:
            status_path = execution_workspace_host(job) / "status.json"
            payload = json.loads(status_path.read_text(encoding="utf-8"))
            child_status = str(payload.get("status") or "").upper()
            if child_status not in {"RUNNING", "DOWNLOADING"}:
                return result
            progress = max(0.0, min(99.0, float(payload.get("progress") or 0.0)))
            current_step = str(payload.get("current_step") or "Training worker is running").strip()
            if not job.worker_id or not job.claim_token:
                return result
            config = load_cloud_config()
            JobQueueRepository(
                database=CloudDatabase(config=config), config=config
            ).update_claimed_job(
                job.job_id,
                job.worker_id,
                job.claim_token,
                JobStatus.RUNNING.value,
                progress=progress,
                current_step=current_step[:500],
                message=str(payload.get("message") or "")[:1000],
            )
        except Exception:
            # A partial status write must never terminate a real GPU job.
            pass
        return result

    def request_cancel(self, job: JobRecord) -> ExecutorResult:
        return self.terminate(job)

    def terminate(self, job: JobRecord) -> ExecutorResult:
        return super().terminate(map_job(job))

    def cleanup(self, job: JobRecord) -> ExecutorResult:
        return self.terminate(job)

    def collect_result(self, job: JobRecord) -> ExecutorResult:
        return super().collect_result(map_job(job))


class HostNativeGPUExecutorV2(HostNativeGPUExecutor):
    """Test-only isolated GPU subprocess layer; unsupported jobs use legacy."""
    _V2_WORKFLOWS = frozenset({"vhit_multi_sample_integration"})
    def _use_v2_for(self, job: JobRecord) -> bool:
        workflow = str(job.workflow_name or job.workflow or "")
        configured = {item.strip() for item in os.environ.get("SPASHINY_GPU_V2_ENABLED_WORKFLOWS", "vhit_multi_sample_integration").split(",") if item.strip()}
        return workflow in self._V2_WORKFLOWS and workflow in configured
    def _build_v2_environment(self, *, job: JobRecord, workspace: Path, parameters_path: Path, seed: int) -> dict[str, str]:
        home = workspace / "working" / "v2-home"; tmpdir = workspace / "working" / "v2-tmp"
        home.mkdir(parents=True, exist_ok=True); tmpdir.mkdir(parents=True, exist_ok=True)
        project_root = Path.cwd().resolve(); worker_root = Path(__file__).resolve().parent
        return {"PATH": os.pathsep.join((str(HOST_GPU_ENV / "bin"), "/usr/local/bin", "/usr/bin", "/bin")), "PYTHONPATH": os.pathsep.join((str(worker_root), str(project_root))), "HOME": str(home), "TMPDIR": str(tmpdir), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1", "PYTHONHASHSEED": str(seed), "CUDA_VISIBLE_DEVICES": str(self.physical_gpu_index), "SPASHINY_GPU_REQUIRED": "1", "SPASHINY_ALLOW_CPU_FALLBACK": "0", "SPASHINY_JOB_ID": job.job_id, "SPASHINY_WORKFLOW": str(job.workflow_name or job.workflow), "SPASHINY_JOB_WORKSPACE": str(workspace), "SPASHINY_PARAMETERS_PATH": str(parameters_path), "SPASHINY_ASSIGNED_GPU": str(job.assigned_gpu or f"gpu-{self.physical_gpu_index}"), "SPASHINY_RANDOM_SEED": str(seed), "MKL_THREADING_LAYER": "GNU", "MKL_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"}
    def start(self, job: JobRecord) -> ExecutorResult:
        if not self._use_v2_for(job): return super().start(job)
        host_job = map_job(job); workspace = Path(host_job.local_workspace); self._persist_execution_workspace(job)
        for name in ("input", "working", "output", "figures", "tables", "logs", "checkpoints"): (workspace / name).mkdir(parents=True, exist_ok=True)
        parameters = self._parameters(job); seed = fixed_random_seed(parameters); parameters["random_seed"] = seed
        parameters["runner_path"] = str(Path(__file__).resolve().parent / "app" / "river" / "run_spatialmeta_train.py")
        try: input_metadata = self._prepare_inputs(job, workspace)
        except Exception as exc: return ExecutorResult(JobStatus.FAILED.value, f"GPU input resolution failed: {type(exc).__name__}: {exc}", "INPUT_RESOLUTION_FAILED")
        parameters["input_files"] = input_metadata.get("input_files") or {}; parameters["input_plan"] = input_metadata.get("plan") or {}
        parameters_path = workspace / "parameters.json"; parameters_path.write_text(json.dumps(parameters, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
        input_manifest_path = workspace / "input" / "worker_input_manifest.json"
        if not input_manifest_path.is_file(): return ExecutorResult(JobStatus.FAILED.value, "GPU input manifest was not created.", "INPUT_MANIFEST_MISSING")
        manifest = self._gpu_manifest(job)
        manifest.update({"host_native": True, "executor_version": "v2", "random_seed": seed, "host_cuda_visible_devices": str(self.physical_gpu_index), "execution_workspace": execution_workspace_container(job), "subprocess_env_mode": "whitelist", "subprocess_python": str(HOST_GPU_ENV / "bin/python"), "mkl_threading_layer": "GNU", "ld_preload": "", "ld_library_path": ""})
        (workspace / "lab_gpu_manifest.json").write_text(json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
        env = self._build_v2_environment(job=job, workspace=workspace, parameters_path=parameters_path, seed=seed)
        command = [str(HOST_GPU_ENV / "bin/python"), "-m", "cloud.gpu_runner_v2", "--job-id", job.job_id, "--workflow", str(job.workflow_name or job.workflow), "--manifest", str(input_manifest_path), "--parameters", str(parameters_path), "--output-dir", str(workspace), "--gpu-id", str(self.physical_gpu_index), "--random-seed", str(seed)]
        stdout = (workspace / "logs" / "gpu_runner_v2.stdout.log").open("ab"); stderr = (workspace / "logs" / "gpu_runner_v2.stderr.log").open("ab")
        try: proc = subprocess.Popen(command, cwd=str(Path(__file__).resolve().parent), env=env, stdout=stdout, stderr=stderr, start_new_session=(os.name != "nt"))
        finally: stdout.close(); stderr.close()
        self.processes[job.job_id] = proc
        metadata = {**manifest, "pid": int(proc.pid), "process_group": str(proc.pid), "entrypoint": "host-native-gpu-python -m cloud.gpu_runner_v2", "execution_workspace": execution_workspace_container(job)}
        return ExecutorResult(JobStatus.RUNNING.value, "Host-native GPU V2 subprocess started.", metadata=metadata)

    def _persisted_process_group(self, job: JobRecord) -> int:
        try:
            metadata = json.loads(job.metadata_json or "{}")
            executor = metadata.get("executor") if isinstance(metadata, dict) else {}
            value = executor.get("process_group") or executor.get("pid")
            return int(value)
        except (TypeError, ValueError, AttributeError, json.JSONDecodeError):
            return 0

    @staticmethod
    def _process_group_alive(process_group: int) -> bool:
        if process_group <= 0:
            return False
        if os.name != "nt" and Path("/proc").is_dir():
            # killpg(..., 0) reports a group containing only zombies as alive.
            # Zombies hold no compute resources; enumerate the group and require
            # at least one non-zombie member before withholding terminalization.
            found_member = False
            for proc_path in Path("/proc").glob("[0-9]*"):
                try:
                    tail = (proc_path / "stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()
                    state, group = tail[0], int(tail[2])
                except (FileNotFoundError, PermissionError, IndexError, ValueError):
                    continue
                if group != process_group:
                    continue
                found_member = True
                if state != "Z":
                    return True
            if found_member:
                return False
        try:
            if os.name == "nt":
                os.kill(process_group, 0)
            else:
                os.killpg(process_group, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    def _wait_for_process_group_exit(self, process_group: int) -> bool:
        deadline = time.monotonic() + float(self.termination_grace_seconds)
        while time.monotonic() < deadline:
            if not self._process_group_alive(process_group):
                return True
            time.sleep(0.05)
        return not self._process_group_alive(process_group)

    def _signal_persisted_process_group(self, process_group: int, signum: int) -> bool:
        if process_group <= 0:
            return False
        try:
            os.killpg(process_group, signum)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            raise
        except Exception:
            return False

    def terminate(self, job: JobRecord) -> ExecutorResult:
        if not self._use_v2_for(job):
            return super().terminate(job)

        # Defence in depth: only the process owning this worker identity may
        # signal a persisted process group.  JobDispatcher applies the same
        # scope before invoking the executor.
        configured_owner = str(os.environ.get("SPASHINY_WORKER_ID") or "").strip()
        if configured_owner and job.worker_id and job.worker_id != configured_owner:
            return ExecutorResult(JobStatus.RUNNING.value, "V2 cancellation ignored by non-owner worker.")

        # The persisted PGID is the source of truth. A Popen handle is only a
        # convenience and can be absent/stale after a dispatcher restart; it
        # must never infer that a surviving process group has stopped.
        process_group = self._persisted_process_group(job)
        if process_group <= 0:
            return ExecutorResult(JobStatus.RUNNING.value, "V2 cancellation cannot confirm process-group exit: persisted PGID is missing.")
        if not self._process_group_alive(process_group):
            self.processes.pop(job.job_id, None)
            return ExecutorResult(JobStatus.CANCELLED.value, "V2 subprocess process group is confirmed stopped.")

        self._signal_persisted_process_group(process_group, signal.SIGTERM)
        if self._wait_for_process_group_exit(process_group):
            self.processes.pop(job.job_id, None)
            return ExecutorResult(JobStatus.CANCELLED.value, "V2 subprocess process group stopped after SIGTERM.")

        self._signal_persisted_process_group(process_group, signal.SIGKILL)
        if self._wait_for_process_group_exit(process_group):
            self.processes.pop(job.job_id, None)
            return ExecutorResult(JobStatus.CANCELLED.value, "V2 subprocess process group stopped after SIGKILL.")

        return ExecutorResult(JobStatus.RUNNING.value, "V2 subprocess process group remains alive after cancellation signals.")


def validate_host_gpu(gpu_index: int) -> dict[str, Any]:
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_index)
    os.environ["SPASHINY_GPU_REQUIRED"] = "1"
    os.environ["SPASHINY_ALLOW_CPU_FALLBACK"] = "0"
    os.environ["SPASHINY_ASSIGNED_GPU"] = f"gpu-{gpu_index}"
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError(f"CUDA unavailable for physical GPU {gpu_index}")
    name = str(torch.cuda.get_device_name(0) or "")
    uuid = ""
    try:
        uuid = str(torch.cuda.get_device_properties(0).uuid)
    except Exception:
        uuid = ""
    manifest = lab_gpu_manifest(f"gpu-{gpu_index}", gpu_name=name, gpu_uuid=uuid)
    manifest["host_native"] = True
    manifest["host_cuda_visible_devices"] = str(gpu_index)
    manifest["physical_gpu_id"] = int(gpu_index)
    manifest["cuda_visible_devices"] = str(os.environ.get("CUDA_VISIBLE_DEVICES", ""))
    manifest["torch_version"] = str(getattr(torch, "__version__", ""))
    manifest["torch_cuda"] = str(torch.version.cuda or "")
    manifest["torch_cuda_available"] = bool(torch.cuda.is_available())
    manifest["torch_cuda_device_count"] = int(torch.cuda.device_count())
    manifest["torch_visible_device_name_0"] = name
    manifest["worker_id"] = str(os.environ.get("SPASHINY_WORKER_ID", ""))
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a pinned host-native SpaShiny Lab GPU worker.")
    parser.add_argument("--gpu-index", required=True, choices=("0", "1"))
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--healthcheck", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    gpu_index = int(args.gpu_index)
    gpu_choice = f"gpu-{gpu_index}"
    manifest = validate_host_gpu(gpu_index)
    print(json.dumps({"worker": "host-native-gpu", "gpu_index": gpu_index, "manifest": manifest}, sort_keys=True), flush=True)
    if args.healthcheck:
        return 0

    config = load_cloud_config()
    worker_id = os.environ.get("SPASHINY_WORKER_ID", f"spashiny-host-gpu-worker-{gpu_index}").strip()
    executor_class = HostNativeGPUExecutorV2 if os.environ.get("SPASHINY_GPU_EXECUTOR", "legacy").strip().lower() == "v2" else HostNativeGPUExecutor
    executor = executor_class(
        physical_gpu_index=gpu_index,
        ui_gpu_label=LAB_GPU_UI_LABELS[gpu_choice],
        gpu_name=str(manifest.get("gpu_name") or ""),
        gpu_uuid=str(manifest.get("gpu_uuid") or ""),
        termination_grace_seconds=int(config.local_process_termination_grace_seconds),
    )
    dispatcher = JobDispatcher(
        config=config,
        worker_id=worker_id,
        worker_type="gpu",
        enabled_resources=(ResourceType.GPU.value,),
        gpu_queue_names=(LAB_GPU_QUEUE_NAMES[gpu_choice],),
        executors={ResourceType.GPU.value: executor},
        result_publisher=HostPathResultPublisher(config=config),
    )
    try:
        if args.once or os.environ.get("SPASHINY_WORKER_ONCE", "").strip().lower() in {"1", "true", "yes", "on"}:
            dispatcher.run_once()
        else:
            dispatcher.run_forever()
    finally:
        dispatcher.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
