"""Minimal DB-free host-native GPU runner for SpaShiny V2."""
from __future__ import annotations
import argparse, json, os, random, sys, traceback
from pathlib import Path
from typing import Any
class RunnerV2Error(RuntimeError): pass
def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)
def _status(workspace: Path, *, status: str, progress: float, current_step: str, message: str = "", **extra: Any) -> None:
    _write_json(workspace / "status.json", {"status": status, "progress": max(0.0, min(100.0, float(progress))), "current_step": str(current_step), "message": str(message), **extra})
def _seed_everything(seed: int, workspace: Path) -> None:
    os.environ["PYTHONHASHSEED"] = str(seed); random.seed(seed)
    import numpy as np
    import torch
    np.random.seed(seed); torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed); torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.benchmark = False; torch.backends.cudnn.deterministic = True
    try: torch.use_deterministic_algorithms(True, warn_only=True)
    except Exception: pass
    _write_json(workspace / "reproducibility.json", {"random_seed": seed, "pythonhashseed": str(seed), "numpy": str(np.__version__), "torch": str(torch.__version__), "torch_cuda": str(torch.version.cuda or "")})
def _preflight(workspace: Path, gpu_id: str) -> dict[str, Any]:
    import torch
    payload: dict[str, Any] = {"python_executable": sys.executable, "torch_version": str(torch.__version__), "torch_cuda_version": str(torch.version.cuda or ""), "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES", ""), "cuda_available": bool(torch.cuda.is_available()), "gpu_id": str(gpu_id)}
    if not payload["cuda_available"]:
        _write_json(workspace / "gpu_runner_v2_preflight.json", payload); raise RunnerV2Error("CUDA is unavailable in the V2 runner.")
    payload["visible_device_count"] = int(torch.cuda.device_count()); payload["gpu_name"] = str(torch.cuda.get_device_name(0))
    try:
        import spatialmeta
        payload["spatialmeta_import"] = "PASS"; payload["spatialmeta_path"] = str(spatialmeta.__file__)
    except Exception as exc:
        payload["spatialmeta_import"] = "FAIL"; payload["spatialmeta_error"] = f"{type(exc).__name__}: {exc}"
        _write_json(workspace / "gpu_runner_v2_preflight.json", payload); raise RunnerV2Error("SpatialMETA import failed in the V2 runner.") from exc
    _write_json(workspace / "gpu_runner_v2_preflight.json", payload); return payload
def _read_manifest(manifest_path: Path, *, job_id: str, workspace: Path) -> tuple[dict[str, str], list[str]]:
    try: manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc: raise RunnerV2Error("worker_input_manifest.json is not valid JSON.") from exc
    if not isinstance(manifest, dict) or str(manifest.get("job_id") or "") != str(job_id): raise RunnerV2Error("worker_input_manifest.json does not match this job.")
    assets = manifest.get("assets")
    if not isinstance(assets, list) or not assets: raise RunnerV2Error("worker_input_manifest.json has no resolved input assets.")
    input_files: dict[str, str] = {}; sample_ids: list[str] = []
    for index, asset in enumerate(assets, start=1):
        if not isinstance(asset, dict): raise RunnerV2Error("worker_input_manifest.json contains an invalid asset.")
        filename = Path(str(asset.get("filename") or "")).name
        staged = workspace / "input" / filename; source = Path(str(asset.get("path") or "")); selected = staged if staged.is_file() else source
        if not selected.is_file(): raise RunnerV2Error(f"Resolved input asset is missing: {filename or source}")
        input_files[f"asset_{index}"] = str(selected.resolve())
        sample_id = str(asset.get("sample_id") or "").strip()
        if sample_id: sample_ids.append(sample_id)
    return input_files, sample_ids
def _read_parameters(parameters_path: Path) -> dict[str, Any]:
    try: parameters = json.loads(parameters_path.read_text(encoding="utf-8"))
    except Exception as exc: raise RunnerV2Error("parameters.json is not valid JSON.") from exc
    if not isinstance(parameters, dict): raise RunnerV2Error("parameters.json must be a JSON object.")
    return parameters
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SpaShiny host-native GPU runner V2")
    parser.add_argument("--job-id", required=True); parser.add_argument("--workflow", required=True); parser.add_argument("--manifest", required=True); parser.add_argument("--parameters", required=True); parser.add_argument("--output-dir", required=True); parser.add_argument("--gpu-id", required=True); parser.add_argument("--random-seed", required=True, type=int)
    return parser.parse_args()
def main() -> int:
    args = _parse_args(); workspace = Path(args.output_dir).resolve(); workspace.mkdir(parents=True, exist_ok=True)
    _status(workspace, status="RUNNING", progress=1.0, current_step="V2 GPU preflight", message="Starting isolated GPU runner")
    try:
        if args.workflow != "vhit_multi_sample_integration": raise RunnerV2Error(f"V2 runner only supports vhit_multi_sample_integration, not {args.workflow!r}.")
        preflight = _preflight(workspace, args.gpu_id)
        _status(workspace, status="RUNNING", progress=3.0, current_step="Reading worker input manifest", message="CUDA and SpatialMETA preflight passed", device=preflight["gpu_name"])
        input_files, sample_ids = _read_manifest(Path(args.manifest), job_id=args.job_id, workspace=workspace)
        parameters = _read_parameters(Path(args.parameters)); parameters["input_files"] = input_files; parameters["random_seed"] = int(args.random_seed); parameters.setdefault("runner_path", str(Path.cwd() / "app" / "river" / "run_spatialmeta_train.py"))
        _seed_everything(int(args.random_seed), workspace)
        _write_json(workspace / "gpu_runner_v2_execution.json", {"job_id": args.job_id, "workflow": args.workflow, "manifest_path": str(Path(args.manifest).resolve()), "input_asset_count": len(input_files), "sample_ids": sample_ids, "gpu_id": str(args.gpu_id), "random_seed": int(args.random_seed), "runner_has_sqlite_access": False, "runner_writes_job_state": False})
        _status(workspace, status="RUNNING", progress=5.0, current_step="Starting VHiT computation", message=f"Resolved {len(input_files)} worker-authorized inputs: {', '.join(sample_ids)}", device=preflight["gpu_name"])
        from remote_worker.workflow_registry import run_workflow
        def progress_callback(**payload: Any) -> None: _status(workspace, **payload)
        def cancel_callback() -> None: return None
        result = run_workflow(args.workflow, input_files, parameters, workspace, progress_callback, cancel_callback)
        _write_json(workspace / "gpu_runner_v2_result.json", {"status": "COMPLETED", "result": result})
        _status(workspace, status="COMPLETED", progress=100.0, current_step="V2 GPU computation complete", message="SpatialMETA artifacts written"); return 0
    except Exception as exc:
        _write_json(workspace / "gpu_runner_v2_error.json", {"error_type": type(exc).__name__, "error": str(exc), "traceback": traceback.format_exc()})
        _status(workspace, status="FAILED", progress=0.0, current_step="V2 GPU runner failed", message=f"{type(exc).__name__}: {exc}")
        print(traceback.format_exc(), file=sys.stderr, flush=True); return 1
if __name__ == "__main__": raise SystemExit(main())
