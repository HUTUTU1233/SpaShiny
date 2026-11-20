from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

from .common import CPUWorkflowContext, CPUWorkflowError, asset_paths, write_json


RIVER_ST_WORKFLOW = "river_spatial_transcriptomics"
RIVER_REQUIRED_OUTPUTS = (
    "river_summary.json",
    "river_combined_plot.png",
    "river_combined_plot.pdf",
    "river_final_rank_temporal.csv",
    "river_plot_adata.h5ad",
    "results.zip",
)


def _bounded_int(value, *, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _sample_label_map(value, data_paths: list[Path]) -> list[str]:
    labels = [item.strip() for item in str(value or "").split(",") if item.strip()]
    if labels and len(labels) != len(data_paths):
        raise CPUWorkflowError(
            "RIVER_SAMPLE_LABEL_COUNT_MISMATCH",
            "The number of sample labels must match the number of spatial-transcriptomics files.",
        )
    return labels or [path.stem for path in data_paths]


def _input_sets(ctx: CPUWorkflowContext) -> tuple[list[Path], list[Path]]:
    data_paths = sorted(
        [path for path in asset_paths(ctx) if path.suffix.lower() in {".h5ad", ".h5"}],
        key=lambda path: path.name.lower(),
    )
    csv_paths = sorted(
        [path for path in asset_paths(ctx) if path.suffix.lower() == ".csv"],
        key=lambda path: path.name.lower(),
    )
    if len(data_paths) < 2:
        raise CPUWorkflowError(
            "RIVER_ST_INPUT_COUNT",
            "Spatial Transcriptomics River requires at least two .h5ad or .h5 files.",
        )
    return data_paths, csv_paths


def _match_csv(data_path: Path, csv_paths: list[Path]) -> Path | None:
    candidates = {path.stem.lower(): path for path in csv_paths}
    stem = data_path.stem.lower()
    return candidates.get(stem) or candidates.get(f"{stem}_annotation") or candidates.get(f"{stem}_annotations")


def _create_archive(workspace: Path, archive: Path) -> None:
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as bundle:
        for path in sorted(workspace.iterdir()):
            if not path.is_file() or path.resolve() == archive.resolve():
                continue
            bundle.write(path, path.name)


def _river_compatible_copy(source: Path, destination: Path) -> Path:
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
            adata = sc.read_h5ad(source)
        else:
            adata = sc.read_10x_h5(source)
        adata.uns = {}
        destination.parent.mkdir(parents=True, exist_ok=True)
        adata.write_h5ad(destination)
        return destination
    except Exception as exc:
        raise CPUWorkflowError("RIVER_INPUT_CONVERSION_FAILED", f"Could not prepare a River-compatible copy of {source.name}: {exc}") from exc


def run(ctx: CPUWorkflowContext) -> dict:
    """Run the legacy River algorithm through the isolated host River environment.

    The public workflow is deliberately ST-only.  It creates a narrow River config
    rather than forwarding any legacy modality selector from the retired desktop UI.
    """
    data_paths, csv_paths = _input_sets(ctx)
    labels = _sample_label_map(ctx.parameters.get("sample_labels"), data_paths)
    compat_dir = ctx.working_dir / "river_compatible_inputs"
    samples = []
    for data_path, label in zip(data_paths, labels, strict=True):
        csv_path = _match_csv(data_path, csv_paths)
        compat_path = _river_compatible_copy(data_path, compat_dir / f"{data_path.stem}.h5ad")
        samples.append(
            {
                "sample_id": data_path.stem,
                "condition": label,
                "data_path": str(compat_path),
                "csv_path": str(csv_path) if csv_path else "",
            }
        )

    config = {
        "mode": "ST",
        "subsample_size": _bounded_int(ctx.parameters.get("subsample_size"), default=6000, minimum=500, maximum=50000),
        "river_epochs": _bounded_int(ctx.parameters.get("river_epochs"), default=100, minimum=10, maximum=1000),
        "random_seed": 42,
        "samples": samples,
    }
    config_path = ctx.working_dir / "river_st_config.json"
    write_json(config_path, config)

    repository_root = Path(__file__).resolve().parents[2]
    runner = repository_root / "app" / "river_runner.py"
    if not runner.is_file():
        raise CPUWorkflowError("RIVER_RUNNER_MISSING", "The River runner is not present in the application source.")

    environment = os.environ.copy()
    environment["CUDA_VISIBLE_DEVICES"] = ""
    environment["PYTHONPATH"] = str(repository_root / "app") + os.pathsep + environment.get("PYTHONPATH", "")
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
    outputs = [path for path in RIVER_REQUIRED_OUTPUTS if (ctx.workspace / path).is_file()]
    return {
        "metrics": {
            "public_workflow": "spatial_transcriptomics_river",
            "random_seed": 42,
            "sample_count": len(samples),
            "sample_labels": labels,
            "subsample_size": config["subsample_size"],
            "river_epochs": config["river_epochs"],
            "runner_log": "logs/river_runner.log",
        },
        "outputs": outputs,
    }
