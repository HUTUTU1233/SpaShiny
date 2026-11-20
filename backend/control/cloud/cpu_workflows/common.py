from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


class CPUWorkflowError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code or "CPU_WORKFLOW_FAILED")


def configure_illustrator_vector_output() -> None:
    """Keep Matplotlib PDF/SVG text editable in Illustrator when possible.

    Plot geometry remains vector; source image layers (for example a tissue
    image) correctly stay raster instead of being falsely advertised as vector.
    """
    import matplotlib

    matplotlib.rcParams["pdf.fonttype"] = 42
    matplotlib.rcParams["ps.fonttype"] = 42
    matplotlib.rcParams["svg.fonttype"] = "none"


def save_figure_bundle(fig, png_path: Path, *, dpi: int = 150) -> tuple[Path, Path]:
    """Write the same original figure as Web PNG and Illustrator-editable PDF."""
    configure_illustrator_vector_output()
    png_path = Path(png_path)
    pdf_path = png_path.with_suffix(".pdf")
    png_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png_path, dpi=int(dpi), bbox_inches="tight", facecolor="white")
    fig.savefig(pdf_path, format="pdf", bbox_inches="tight", facecolor="white")
    return png_path, pdf_path


@dataclass
class CPUWorkflowContext:
    job_id: str
    workflow_name: str
    session_id: str
    owner_session_id: str
    workspace: Path
    input_dir: Path
    working_dir: Path
    output_dir: Path
    figures_dir: Path
    logs_dir: Path
    parameters: dict[str, Any]
    plan: dict[str, Any]
    downloaded_assets: list[dict[str, Any]]
    input_files: dict[str, str]
    metadata: dict[str, Any]
    thread_config: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_job_spec(cls, payload: dict[str, Any]) -> "CPUWorkflowContext":
        workspace = Path(str(payload.get("workspace") or "")).resolve()
        input_dir = Path(str(payload.get("input_dir") or workspace / "input")).resolve()
        return cls(
            job_id=str(payload.get("job_id") or ""),
            workflow_name=str(payload.get("workflow_name") or payload.get("workflow") or ""),
            session_id=str(payload.get("session_id") or ""),
            owner_session_id=str(payload.get("owner_session_id") or payload.get("session_id") or ""),
            workspace=workspace,
            input_dir=input_dir,
            working_dir=Path(str(payload.get("working_dir") or workspace / "working")).resolve(),
            output_dir=Path(str(payload.get("output_dir") or workspace / "output")).resolve(),
            figures_dir=Path(str(payload.get("figures_dir") or workspace / "figures")).resolve(),
            logs_dir=Path(str(payload.get("logs_dir") or workspace / "logs")).resolve(),
            parameters=dict(payload.get("parameters") or {}),
            plan=dict(payload.get("plan") or {}),
            downloaded_assets=[dict(item) for item in payload.get("downloaded_assets") or [] if isinstance(item, dict)],
            input_files={str(k): str(v) for k, v in dict(payload.get("input_files") or {}).items()},
            metadata=dict(payload.get("metadata") or {}),
            thread_config={str(k): int(v) for k, v in dict(payload.get("thread_config") or {}).items()},
        )

    def ensure_dirs(self) -> None:
        for path in (self.workspace, self.input_dir, self.working_dir, self.output_dir, self.figures_dir, self.logs_dir):
            path.mkdir(parents=True, exist_ok=True)


def ensure_dependency(module_name: str):
    try:
        return __import__(module_name)
    except Exception as exc:
        raise CPUWorkflowError("DEPENDENCY_MISSING", f"Python dependency is required for this workflow: {module_name}") from exc


def parse_number(value: Any, default: float | None = None) -> float | None:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except Exception:
        return default


def parse_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def combined_input_sha256(downloaded_assets: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for item in sorted(downloaded_assets, key=lambda row: str(row.get("path") or row.get("filename") or "")):
        path = Path(str(item.get("path") or ""))
        digest.update(str(item.get("filename") or path.name).encode("utf-8"))
        if path.is_file():
            digest.update(sha256_file(path).encode("ascii"))
        else:
            digest.update(str(item.get("sha256") or "").encode("ascii"))
    return digest.hexdigest()


def write_json(path: Path, data: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
    return path


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str] | None = None) -> Path:
    rows = list(rows)
    if fieldnames is None:
        seen: list[str] = []
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.append(key)
        fieldnames = seen
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})
    return path


def read_table(path: Path):
    ensure_dependency("pandas")
    import pandas as pd

    suffix = path.suffix.lower()
    if suffix == ".tsv":
        return pd.read_csv(path, sep="\t")
    return pd.read_csv(path)


def read_h5ad(path: Path):
    ensure_dependency("anndata")
    import anndata as ad

    try:
        return ad.read_h5ad(path)
    except Exception as exc:
        raise CPUWorkflowError("INPUT_READ_FAILED", f"Could not read h5ad input: {path.name}") from exc


def read_matrix_input(path: Path, *, modality: str):
    suffix = path.suffix.lower()
    if path.is_dir():
        try:
            ensure_dependency("scanpy")
            import scanpy as sc

            return sc.read_10x_mtx(str(path), cache=False)
        except CPUWorkflowError:
            raise
        except Exception as exc:
            raise CPUWorkflowError("INPUT_READ_FAILED", f"Could not read 10x mtx directory for {modality}.") from exc
    if suffix == ".h5ad":
        return read_h5ad(path)
    if suffix in {".h5", ".hdf5"}:
        try:
            ensure_dependency("scanpy")
            import scanpy as sc

            return sc.read_10x_h5(str(path))
        except Exception:
            try:
                return read_h5ad(path)
            except CPUWorkflowError as exc:
                raise CPUWorkflowError("INPUT_READ_FAILED", f"Could not read 10x h5 or h5ad input for {modality}: {path.name}") from exc
    raise CPUWorkflowError("INPUT_TYPE_UNSUPPORTED", f"Unsupported {modality} matrix input type: {path.name}")


def matrix_qc_frames(adata):
    ensure_dependency("numpy")
    ensure_dependency("pandas")
    import numpy as np
    import pandas as pd
    from scipy import sparse

    x = adata.X
    if sparse.issparse(x):
        counts = np.asarray(x.sum(axis=1)).ravel()
        features = np.asarray((x > 0).sum(axis=1)).ravel()
        feature_counts = np.asarray(x.sum(axis=0)).ravel()
        feature_nonzero = np.asarray((x > 0).sum(axis=0)).ravel()
    else:
        arr = np.asarray(x)
        counts = arr.sum(axis=1)
        features = (arr > 0).sum(axis=1)
        feature_counts = arr.sum(axis=0)
        feature_nonzero = (arr > 0).sum(axis=0)
    obs = pd.DataFrame(
        {
            "observation_id": [str(item) for item in adata.obs_names],
            "total_counts": counts,
            "n_features_by_counts": features,
        }
    )
    var = pd.DataFrame(
        {
            "feature_id": [str(item) for item in adata.var_names],
            "total_counts": feature_counts,
            "n_observations_by_counts": feature_nonzero,
        }
    )
    return obs, var


def apply_basic_filters(adata, obs_qc, feature_qc, params: dict[str, Any]):
    ensure_dependency("numpy")
    import numpy as np

    min_counts = parse_number(params.get("min_counts"), 0) or 0
    min_features = parse_number(params.get("min_features"), 0) or 0
    max_counts = parse_number(params.get("max_counts"), None)
    max_features = parse_number(params.get("max_features"), None)
    min_cells = parse_number(params.get("min_cells"), 0) or 0
    obs_mask = (obs_qc["total_counts"].to_numpy() >= min_counts) & (obs_qc["n_features_by_counts"].to_numpy() >= min_features)
    if max_counts is not None:
        obs_mask &= obs_qc["total_counts"].to_numpy() <= max_counts
    if max_features is not None:
        obs_mask &= obs_qc["n_features_by_counts"].to_numpy() <= max_features
    var_mask = feature_qc["n_observations_by_counts"].to_numpy() >= min_cells
    if not bool(np.any(obs_mask)):
        raise CPUWorkflowError("QC_FILTER_REMOVED_ALL_OBSERVATIONS", "QC parameters removed all observations.")
    if not bool(np.any(var_mask)):
        raise CPUWorkflowError("QC_FILTER_REMOVED_ALL_FEATURES", "QC parameters removed all features.")
    return adata[obs_mask, var_mask].copy(), obs_mask, var_mask


def plot_qc_histograms(ctx: CPUWorkflowContext, obs_qc, *, prefix: str) -> list[str]:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return []
    created: list[str] = []
    for column in ("total_counts", "n_features_by_counts"):
        if column not in obs_qc:
            continue
        fig, ax = plt.subplots(figsize=(5, 3))
        ax.hist(obs_qc[column], bins=min(30, max(5, len(obs_qc))))
        ax.set_xlabel(column)
        ax.set_ylabel("observations")
        ax.set_title(f"{prefix} {column}")
        fig.tight_layout()
        path = ctx.figures_dir / f"{prefix.lower()}_{column}.png"
        png_path, pdf_path = save_figure_bundle(fig, path, dpi=120)
        created.extend([
            png_path.relative_to(ctx.workspace).as_posix(),
            pdf_path.relative_to(ctx.workspace).as_posix(),
        ])
    return created


def asset_paths(ctx: CPUWorkflowContext) -> list[Path]:
    paths: list[Path] = []
    for item in ctx.downloaded_assets:
        path = Path(str(item.get("path") or ""))
        if path.exists():
            paths.append(path)
    for value in ctx.input_files.values():
        path = Path(str(value or ""))
        if path.exists() and path not in paths:
            paths.append(path)
    return paths


def select_asset(
    ctx: CPUWorkflowContext,
    *,
    suffixes: tuple[str, ...] = (),
    roles: tuple[str, ...] = (),
    required: bool = True,
    label: str = "input",
) -> Path | None:
    suffixes = tuple(item.lower() for item in suffixes)
    roles_set = {str(item) for item in roles if str(item)}
    candidates: list[Path] = []
    for item in ctx.downloaded_assets:
        role = str(item.get("role") or "")
        path = Path(str(item.get("path") or ""))
        if not path.exists():
            continue
        if roles_set and role not in roles_set:
            continue
        if suffixes and path.suffix.lower() not in suffixes:
            continue
        candidates.append(path)
    if not candidates:
        for path in asset_paths(ctx):
            if suffixes and path.suffix.lower() not in suffixes:
                continue
            candidates.append(path)
    if candidates:
        return candidates[0]
    if required:
        raise CPUWorkflowError("INPUT_REQUIRED", f"Required {label} input was not found.")
    return None


def select_assets(
    ctx: CPUWorkflowContext,
    *,
    suffixes: tuple[str, ...] = (),
    roles: tuple[str, ...] = (),
) -> list[Path]:
    suffixes = tuple(item.lower() for item in suffixes)
    roles_set = {str(item) for item in roles if str(item)}
    selected: list[Path] = []
    for item in ctx.downloaded_assets:
        role = str(item.get("role") or "")
        path = Path(str(item.get("path") or ""))
        if not path.exists():
            continue
        if roles_set and role not in roles_set:
            continue
        if suffixes and path.suffix.lower() not in suffixes:
            continue
        selected.append(path)
    if not selected:
        selected = [path for path in asset_paths(ctx) if not suffixes or path.suffix.lower() in suffixes]
    return selected


def table_gene_list(path: Path, *, gene_column: str = "gene") -> list[str]:
    df = read_table(path)
    column = gene_column if gene_column in df.columns else ""
    if not column:
        for candidate in ("gene", "feature", "feature_id", "name", "symbol"):
            if candidate in df.columns:
                column = candidate
                break
    if not column and len(df.columns) > 0:
        column = str(df.columns[0])
    genes = [str(item).strip() for item in df[column].tolist()] if column else []
    return [item for item in genes if item]


def numeric_mz_values_from_adata(adata) -> list[float]:
    values: list[Any] = []
    for column in ("mz", "m/z", "mass_to_charge", "feature_mz"):
        if column in adata.var:
            values = list(adata.var[column])
            break
    if not values:
        values = list(adata.var_names)
    parsed: list[float] = []
    for value in values:
        try:
            parsed.append(float(value))
        except Exception:
            continue
    return parsed


def find_local_db_path(params: dict[str, Any], keys: tuple[str, ...], *, env_var: str = "") -> Path:
    raw = ""
    for key in keys:
        if params.get(key):
            raw = str(params.get(key) or "")
            break
    if not raw and env_var:
        raw = str(os.environ.get(env_var) or "")
    if not raw:
        raise CPUWorkflowError("LOCAL_DATABASE_MISSING", "A local database path is required for this offline workflow.")
    if "://" in raw:
        raise CPUWorkflowError("REMOTE_DATABASE_DISABLED", "Runtime network databases are disabled in Lab CPU workflows.")
    path = Path(raw).expanduser().resolve()
    if not path.is_file():
        raise CPUWorkflowError("LOCAL_DATABASE_MISSING", f"Local database was not found: {path}")
    return path


def session_info(ctx: CPUWorkflowContext) -> dict[str, Any]:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor() or _linux_cpu_model(),
        "thread_config": dict(ctx.thread_config),
        "pid": os.getpid(),
    }


def _linux_cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()
    except Exception:
        return ""
    return ""


def write_session_info(ctx: CPUWorkflowContext) -> Path:
    info = session_info(ctx)
    path = ctx.workspace / "session_info.txt"
    text = "\n".join(f"{key}: {value}" for key, value in info.items()) + "\n"
    path.write_text(text, encoding="utf-8")
    return path


def collect_output_manifest(workspace: Path) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for path in sorted(Path(workspace).rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(workspace).as_posix()
        if rel in {"manifest.json", "cpu_workflow_status.json"}:
            continue
        if rel.startswith("input/") or rel.startswith("working/"):
            continue
        files.append({"path": rel, "size_bytes": path.stat().st_size, "sha256": sha256_file(path)})
    return files


def write_success_summary(
    ctx: CPUWorkflowContext,
    *,
    metrics: dict[str, Any],
    outputs: list[str],
    wall_time_seconds: float,
    peak_ram_mb: float,
) -> Path:
    payload = {
        "status": "succeeded",
        "workflow": ctx.workflow_name,
        "job_id": ctx.job_id,
        "metrics": metrics,
        "outputs": sorted(outputs),
        "wall_time_seconds": wall_time_seconds,
        "peak_ram_mb": peak_ram_mb,
    }
    return write_json(ctx.workspace / "summary.json", payload)


def write_failure_artifacts(
    ctx: CPUWorkflowContext,
    *,
    code: str,
    message: str,
    wall_time_seconds: float = 0.0,
    peak_ram_mb: float = 0.0,
) -> None:
    ctx.ensure_dirs()
    error_path = ctx.logs_dir / "error.log"
    error_path.write_text(f"{code}: {message}\n", encoding="utf-8")
    write_json(
        ctx.workspace / "summary.json",
        {
            "status": "failed",
            "workflow": ctx.workflow_name,
            "job_id": ctx.job_id,
            "error_code": code,
            "error_message": message,
            "wall_time_seconds": wall_time_seconds,
            "peak_ram_mb": peak_ram_mb,
        },
    )
    write_session_info(ctx)
    write_manifest(ctx, status="failed", wall_time_seconds=wall_time_seconds, peak_ram_mb=peak_ram_mb, error_code=code, error_message=message)


def write_manifest(
    ctx: CPUWorkflowContext,
    *,
    status: str,
    wall_time_seconds: float,
    peak_ram_mb: float,
    error_code: str = "",
    error_message: str = "",
) -> Path:
    binding = ctx.metadata.get("session_input_binding") if isinstance(ctx.metadata.get("session_input_binding"), dict) else {}
    payload = {
        "job_id": ctx.job_id,
        "owner_session_hash": hashlib.sha256(str(ctx.owner_session_id or ctx.session_id).encode("utf-8")).hexdigest()[:16],
        "workflow": ctx.workflow_name,
        "status": str(status),
        "input_binding": {
            "binding_id": str(binding.get("binding_id") or ""),
            "source": str(binding.get("source") or ctx.plan.get("input_source") or ""),
            "example_action_id": str(binding.get("example_action_id") or ""),
            "materialized_input_dir": str(binding.get("materialized_input_dir") or ctx.plan.get("materialized_input_dir") or ""),
            "result_dir": str(binding.get("result_dir") or ctx.workspace),
        },
        "input_sha256": combined_input_sha256(ctx.downloaded_assets),
        "parameters": ctx.parameters,
        "versions": session_info(ctx),
        "cpu_model": session_info(ctx).get("processor", ""),
        "thread_config": dict(ctx.thread_config),
        "peak_ram_mb": peak_ram_mb,
        "wall_time_seconds": wall_time_seconds,
        "error_code": error_code,
        "error_message": error_message,
        "output_files": collect_output_manifest(ctx.workspace),
        "manifest_version": "cpu_workflow_manifest_v1",
    }
    return write_json(ctx.workspace / "manifest.json", payload)


def nonempty_error_log(workspace: Path) -> Path | None:
    candidates = [Path(workspace) / "error.log", Path(workspace) / "logs" / "error.log"]
    for path in candidates:
        if path.is_file() and path.read_text(encoding="utf-8", errors="ignore").strip():
            return path
    return None


def validate_result_contract(workspace: Path, required_outputs: tuple[str, ...]) -> tuple[bool, str, str]:
    root = Path(workspace)
    error_log = nonempty_error_log(root)
    if error_log is not None:
        return False, "CPU_RESULT_ERROR", f"Non-empty error log: {error_log.relative_to(root).as_posix()}"
    manifest_path = root / "manifest.json"
    summary_path = root / "summary.json"
    for path in (manifest_path, summary_path):
        if path.is_file():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return False, "RESULT_MANIFEST_INVALID", f"{path.name} is not valid JSON."
            status = str(payload.get("status") or "").lower()
            if status in {"failed", "failure", "error"}:
                return False, "RESULT_MANIFEST_FAILED", f"{path.name} reports failed status."
    missing = [item for item in required_outputs if not (root / item).is_file()]
    if missing:
        return False, "REQUIRED_OUTPUT_MISSING", "Missing required outputs: " + ", ".join(missing)
    if manifest_path.is_file():
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            if str(payload.get("status") or "").lower() not in {"succeeded", "success"}:
                return False, "RESULT_MANIFEST_NOT_SUCCEEDED", "manifest.json does not report succeeded status."
        except Exception:
            return False, "RESULT_MANIFEST_INVALID", "manifest.json is not valid JSON."
    return True, "", "CPU workflow result contract satisfied."


def peak_ram_mb() -> float:
    try:
        import psutil

        return round(float(psutil.Process(os.getpid()).memory_info().rss) / (1024 * 1024), 3)
    except Exception:
        return 0.0


def monotonic_seconds() -> float:
    return time.monotonic()
