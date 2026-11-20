from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

from .common import CPUWorkflowContext, CPUWorkflowError, asset_paths, write_json, sha256_file
from ..river_options import sampling_request
from ..river_input_contract import execution_settings, validate_parity_order, validated_zip_members, extract_checked_member, validate_spatial
from ..river_outputs import RIVER_PUBLIC_OUTPUTS


RIVER_ST_WORKFLOW = "river_spatial_transcriptomics"
RIVER_REQUIRED_OUTPUTS = (
    "river_summary.json",
    "river_combined_plot.png",
    "river_combined_plot.pdf",
    "river_final_rank_temporal.csv",
    "river_plot_adata.h5ad",
    "results.zip",
)
RIVER_GENE_PLOT_OUTPUTS = (
    "river_selected_gene_temporal.png",
    "river_selected_gene_temporal.pdf",
    "river_selected_gene_temporal.csv",
    "river_selected_gene_spatial.png",
    "river_selected_gene_spatial.pdf",
)
MAX_ARCHIVE_MEMBERS = 256
MAX_ARCHIVE_H5AD_FILES = 64
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 80 * 1024 * 1024 * 1024
MAX_SINGLE_H5AD_BYTES = 20 * 1024 * 1024 * 1024


def _bounded_int(value, *, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _sample_label_map(parameters: dict, data_paths: list[Path]) -> list[str]:
    raw_time_labels = parameters.get("time_labels")
    if isinstance(raw_time_labels, list):
        labels = [str(item).strip() for item in raw_time_labels]
        if any(not item for item in labels):
            raise CPUWorkflowError("RIVER_TIME_LABEL_EMPTY", "Every River time point must have a non-empty label.")
    else:
        labels = [item.strip() for item in str(parameters.get("sample_labels") or "").split(",") if item.strip()]
    if labels and len(labels) != len(data_paths):
        raise CPUWorkflowError(
            "RIVER_SAMPLE_LABEL_COUNT_MISMATCH",
            "The number of sample labels must match the number of spatial-transcriptomics files.",
        )
    return labels or [path.stem for path in data_paths]


def _extract_river_archive(source: Path, destination: Path) -> tuple[list[Path], list[Path]]:
    destination.mkdir(parents=True, exist_ok=True)
    data_paths = []
    csv_paths = []
    seen_names = set()
    try:
        bundle = zipfile.ZipFile(source, "r")
    except Exception as exc:
        raise CPUWorkflowError("RIVER_ARCHIVE_INVALID", f"Could not open River ZIP package {source.name}: {exc}") from exc
    with bundle:
        try:infos = validated_zip_members(bundle)
        except ValueError as exc:raise CPUWorkflowError('RIVER_ARCHIVE_REJECTED',str(exc)) from exc
        if len(infos) > MAX_ARCHIVE_MEMBERS:
            raise CPUWorkflowError("RIVER_ARCHIVE_TOO_MANY_FILES", f"River ZIP contains {len(infos)} files; maximum is {MAX_ARCHIVE_MEMBERS}.")
        total_h5ad_bytes = 0
        h5ad_count = 0
        for info in infos:
            member = Path(str(info.filename).replace("\\", "/"))
            if member.is_absolute() or ".." in member.parts:
                raise CPUWorkflowError("RIVER_ARCHIVE_PATH_UNSAFE", f"Unsafe archive path: {info.filename}")
            mode = (int(info.external_attr) >> 16) & 0o170000
            if mode and stat.S_ISLNK(mode):
                raise CPUWorkflowError("RIVER_ARCHIVE_SYMLINK", f"Symbolic links are not allowed: {info.filename}")
            if int(info.flag_bits) & 0x1:
                raise CPUWorkflowError("RIVER_ARCHIVE_ENCRYPTED", f"Encrypted entries are not supported: {info.filename}")
            suffix = member.suffix.lower()
            if suffix not in {".h5ad", ".csv"}:
                continue
            name_key = member.name.casefold()
            if name_key in seen_names:
                raise CPUWorkflowError("RIVER_ARCHIVE_DUPLICATE_NAME", f"Duplicate archive file name: {member.name}")
            seen_names.add(name_key)
            if info.file_size <= 0:
                raise CPUWorkflowError("RIVER_ARCHIVE_EMPTY_FILE", f"Archive entry is empty: {info.filename}")
            if suffix == ".h5ad":
                h5ad_count += 1
                total_h5ad_bytes += int(info.file_size)
                if info.file_size > MAX_SINGLE_H5AD_BYTES:
                    raise CPUWorkflowError("RIVER_ARCHIVE_FILE_TOO_LARGE", f"H5AD entry is too large: {info.filename}")
                if info.compress_size == 0 or (info.file_size / max(1, info.compress_size)) > 2000:
                    raise CPUWorkflowError("RIVER_ARCHIVE_RATIO_UNSAFE", f"Unsafe compression ratio: {info.filename}")
            target = destination / member.name
            extract_checked_member(bundle,info,target)
            if suffix == ".h5ad":
                data_paths.append(target)
            else:
                csv_paths.append(target)
        if h5ad_count > MAX_ARCHIVE_H5AD_FILES:
            raise CPUWorkflowError("RIVER_ARCHIVE_TOO_MANY_H5AD", f"River ZIP contains {h5ad_count} H5AD files; maximum is {MAX_ARCHIVE_H5AD_FILES}.")
        if total_h5ad_bytes > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
            raise CPUWorkflowError("RIVER_ARCHIVE_TOO_LARGE", "The total uncompressed H5AD size exceeds the River package limit.")
    return data_paths, csv_paths


def _apply_sample_order(data_paths: list[Path], value) -> list[Path]:
    if not isinstance(value, list) or not value:
        return sorted(data_paths, key=lambda path: path.name.casefold())
    requested = [str(item).strip() for item in value]
    by_name = {path.name.casefold(): path for path in data_paths}
    if len(by_name) != len(data_paths):
        raise CPUWorkflowError("RIVER_SAMPLE_NAME_DUPLICATE", "River input sample file names must be unique.")
    if len(requested) != len(data_paths) or len(set(item.casefold() for item in requested)) != len(requested):
        raise CPUWorkflowError("RIVER_SAMPLE_ORDER_INVALID", "The submitted River sample order is incomplete or contains duplicates.")
    missing = [item for item in requested if item.casefold() not in by_name]
    if missing:
        raise CPUWorkflowError("RIVER_SAMPLE_ORDER_MISMATCH", "Submitted River sample order does not match the uploaded package: " + ", ".join(missing))
    return [by_name[item.casefold()] for item in requested]


def _input_sets(ctx: CPUWorkflowContext) -> tuple[list[Path], list[Path]]:
    inputs = list(asset_paths(ctx))
    data_paths = [path for path in inputs if path.suffix.lower() in {".h5ad", ".h5"}]
    csv_paths = [path for path in inputs if path.suffix.lower() == ".csv"]
    archives = [path for path in inputs if path.suffix.lower() == ".zip" or zipfile.is_zipfile(path)]
    if len(archives) > 1:
        raise CPUWorkflowError("RIVER_ARCHIVE_COUNT", "Submit exactly one River ZIP package per job.")
    if archives:
        extracted_data, extracted_csv = _extract_river_archive(archives[0], ctx.working_dir / "river_archive_inputs")
        data_paths.extend(extracted_data)
        csv_paths.extend(extracted_csv)
    data_paths = _apply_sample_order(data_paths, ctx.parameters.get("sample_order"))
    csv_paths = sorted(csv_paths, key=lambda path: path.name.casefold())
    if len(data_paths) < 2:
        raise CPUWorkflowError(
            "RIVER_ST_INPUT_COUNT",
            "Spatial Transcriptomics River requires at least two .h5ad files.",
        )
    return data_paths, csv_paths


def _match_csv(data_path: Path, csv_paths: list[Path]) -> Path | None:
    candidates = {path.stem.lower(): path for path in csv_paths}
    stem = data_path.stem.lower()
    return candidates.get(stem) or candidates.get(f"{stem}_annotation") or candidates.get(f"{stem}_annotations")


def _create_archive(workspace: Path, archive: Path) -> None:
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as bundle:
        for name in RIVER_PUBLIC_OUTPUTS:
            path=workspace/name
            if not path.is_file() or path.is_symlink() or path.resolve().parent!=workspace.resolve():
                continue
            bundle.write(path, path.name)


def _river_compatible_copy(source: Path, destination: Path, settings=None) -> Path:
    """Materialize a minimal H5AD that the pre-existing Python 3.8 River stack can read.

    The current web/worker environment can read newer AnnData encodings that the
    legacy River environment cannot (notably null values in ``uns``).  River only
    consumes matrix, observation/feature metadata, and spatial coordinates, so a
    private worker copy with nonessential ``uns`` removed is the safe bridge.
    """
    try:
        import scanpy as sc
    except Exception as exc:
        raise CPUWorkflowError("RIVER_COMPAT_READER_MISSING", "The host River worker needs scanpy to prepare input compatibility copies.") from exc
    try:
        if source.suffix.lower() == ".h5ad":
            # Bound the legacy compatibility bridge before loading all arrays.
            import h5py
            with h5py.File(source,'r') as handle:
                total=[0]
                def account(_name,obj):
                    if isinstance(obj,h5py.Dataset):total[0]+=obj.size*obj.dtype.itemsize
                handle.visititems(account)
                if total[0]>2*1024**3:
                    raise MemoryError('The H5AD compatibility bridge exceeds its 2 GiB input budget; reduce the input size before submission.')
            adata = sc.read_h5ad(source)
        else:
            adata = sc.read_10x_h5(source)
        validate_spatial(adata,sample=source.name,allow_obs_coordinates=(settings or {}).get('analysis_mode')!='original_python_parity')
        if settings and settings['input_scale']!='log1p' and 'log1p' in adata.uns:
            raise ValueError('H5AD has a log1p marker but was declared unlogged. Verify the expression scale instead of processing it twice.')
        # No source mutation. The actual preprocessing declaration is in config.
        adata.uns = {}
        destination.parent.mkdir(parents=True, exist_ok=True)
        adata.write_h5ad(destination)
        return destination
    except Exception as exc:
        raise CPUWorkflowError("RIVER_INPUT_CONVERSION_FAILED", f"Could not prepare a River-compatible copy of {source.name}: {exc}") from exc


def run(ctx: CPUWorkflowContext) -> dict:
    try:
        return _run_impl(ctx)
    except Exception as exc:
        path=ctx.workspace/'river_execution_trace.json'
        # Preserve a runner's richer failure trace if it has already started.
        if not path.is_file():
            write_json(path,{'trace_schema':'river-execution-trace-v2',
                'execution_mode':ctx.parameters.get('execution_mode'),
                'execution_contract_version':ctx.parameters.get('execution_contract_version'),
                'requested_analysis_mode':ctx.parameters.get('requested_analysis_mode',ctx.parameters.get('analysis_mode')),
                'analysis_mode':None,'technical_success':False,'phase':'worker_preflight',
                'scientific_validity':'UNVERIFIED_ORIGINAL_ALGORITHM',
                'error':f'{type(exc).__name__}: {exc}'})
        raise


def _run_impl(ctx: CPUWorkflowContext) -> dict:
    """Run the legacy River algorithm through the isolated host River environment.

    The public workflow is deliberately ST-only.  It creates a narrow River config
    rather than forwarding any legacy modality selector from the retired desktop UI.
    """
    from ..river_execution_contract import V2
    from ..river_unified_contract import V3
    if ctx.parameters.get('execution_contract_version') == V3:
        from .river_unified import run_unified
        return run_unified(ctx)
    if ctx.parameters.get('execution_contract_version') == V2:
        from .river_v2 import run_v2
        return run_v2(ctx)
    if ctx.parameters.get('execution_contract_version') not in (None,'','river-parity-execution-v1'):
        raise CPUWorkflowError('RIVER_CONTRACT_UNKNOWN','Unknown River contract; no fallback is permitted.')
    if 'execution_mode' in ctx.parameters:
        raise CPUWorkflowError('RIVER_CONTRACT_REQUIRED','execution_mode requires river-execution-v2.')
    settings=execution_settings(ctx.parameters)
    data_paths, csv_paths = _input_sets(ctx)
    order_policy=validate_parity_order([path.name for path in data_paths],settings['analysis_mode'])
    labels = _sample_label_map(ctx.parameters, data_paths)
    representative_gene = str(ctx.parameters.get("representative_gene") or "").strip()
    requested_n, sampling_mode = sampling_request(ctx.parameters)
    compat_dir = ctx.working_dir / "river_compatible_inputs"
    samples = []
    for data_path, label in zip(data_paths, labels, strict=True):
        csv_path = _match_csv(data_path, csv_paths)
        before=data_path.stat()
        original={'path':str(data_path.resolve()),'sha256':sha256_file(data_path),'size_bytes':before.st_size}
        after=data_path.stat()
        if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):
            raise CPUWorkflowError('RIVER_INPUT_CHANGED','A required H5AD changed during provenance hashing.')
        compat_path = _river_compatible_copy(data_path, compat_dir / f"{data_path.stem}.h5ad",settings)
        copied=data_path.stat()
        if (after.st_ino,after.st_size,after.st_mtime_ns)!=(copied.st_ino,copied.st_size,copied.st_mtime_ns):
            raise CPUWorkflowError('RIVER_INPUT_CHANGED','An original H5AD changed while preparing its private compatibility copy.')
        samples.append(
            {
                "sample_id": data_path.stem,
                "condition": label,
                "data_path": str(compat_path),
                "csv_path": str(csv_path) if csv_path else "",
                "original_h5ad": original,
            }
        )

    config = {
        **settings,
        "mode": "ST",
        "subsample_size": requested_n,
        "subsample_mode": sampling_mode,
        "river_epochs": 100 if settings['analysis_mode']=='original_python_parity' else _bounded_int(ctx.parameters.get("river_epochs"), default=100, minimum=10, maximum=1000),
        "random_seed": 42,
        "sample_order_policy":order_policy,
        "sample_order":[path.name for path in data_paths],
        "worker_mode_lineage":{'received':ctx.parameters.get('analysis_mode'),
            'requested':settings['requested_analysis_mode'],'effective':settings['analysis_mode']},
        "representative_gene": representative_gene,
        "samples": samples,
    }
    config_path = ctx.working_dir / "river_st_config.json"
    write_json(config_path, config)

    repository_root = Path(__file__).resolve().parents[2]
    runner = repository_root / "app" / "river_runner.py"
    if not runner.is_file():
        raise CPUWorkflowError("RIVER_RUNNER_MISSING", "The River runner is not present in the application source.")

    environment = os.environ.copy()
    require_gpu = environment.get("SPASHINY_RIVER_REQUIRE_GPU", "") == "1"
    python_paths = [str(repository_root / "app")]
    if require_gpu:
        dependency_root = Path(environment.get("SPASHINY_RIVER_GPU_DEPS_ROOT", "")).resolve()
        if not dependency_root.is_dir() or not (dependency_root / "scSLAT").is_dir():
            raise CPUWorkflowError("RIVER_GPU_DEPS_MISSING", "The isolated River GPU dependency directory is unavailable.")
        try:
            import torch
        except ImportError as exc:
            raise CPUWorkflowError("RIVER_CUDA_UNAVAILABLE", "The River GPU Python environment cannot import PyTorch.") from exc
        if not environment.get("CUDA_VISIBLE_DEVICES", "").strip() or not torch.cuda.is_available():
            raise CPUWorkflowError("RIVER_CUDA_UNAVAILABLE", "River requires an assigned and available CUDA device.")
        python_paths.append(str(dependency_root))
    else:
        environment["CUDA_VISIBLE_DEVICES"] = ""
    python_paths.append(environment.get("PYTHONPATH", ""))
    environment["PYTHONPATH"] = os.pathsep.join(item for item in python_paths if item)
    runner_python = os.environ.get("SPASHINY_RIVER_PYTHON", "").strip() or sys.executable
    if not Path(runner_python).is_file():
        raise CPUWorkflowError("RIVER_PYTHON_MISSING", "The configured River Python executable is not available on this worker.")
    log_path = ctx.logs_dir / "river_runner.log"
    with log_path.open("wb") as stream:
        completed = subprocess.run(
            [runner_python, str(runner), "--config", str(config_path), "--output", str(ctx.workspace)],
            cwd=str(repository_root / "app"),
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
            check=False,
        )
    if completed.returncode != 0:
        raise CPUWorkflowError("RIVER_RUNNER_FAILED", f"River runner exited with status {completed.returncode}; inspect logs/river_runner.log.")

    summary_path = ctx.workspace / "river_summary.json"
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CPUWorkflowError("RIVER_SUMMARY_MISSING", "River did not produce a readable river_summary.json.") from exc
    if not bool(summary.get("river_success")):
        raise CPUWorkflowError("RIVER_ANALYSIS_FAILED", str(summary.get("message") or "River analysis failed."))

    archive = ctx.workspace / "results.zip"
    _create_archive(ctx.workspace, archive)
    outputs = [name for name in (*RIVER_PUBLIC_OUTPUTS,'results.zip') if (ctx.workspace/name).is_file()]
    return {
        "metrics": {
            "public_workflow": "spatial_transcriptomics_river",
            "random_seed": 42,
            "sample_count": len(samples),
            "sample_labels": labels,
            "sample_order": [path.name for path in data_paths],
            "representative_gene": representative_gene,
            "subsample_size": summary.get("sampling", {}).get("resolved_n_obs", config["subsample_size"]),
            "river_epochs": config["river_epochs"],
            "runner_log": "logs/river_runner.log",
            'input_contract':settings,
            "execution_device": "cuda" if require_gpu else "cpu",
        },
        "outputs": outputs,
    }
