# Shared imports/configuration and existing cross-feature utilities. No session state is lifted here.
from pathlib import Path as _ExportPath

LEGACY_ENTRYPOINT_FILE = str(_ExportPath(__file__).resolve().parents[2] / "ST-SM.py")
import os
import sys
import tempfile
import shutil
import zipfile
import subprocess
import time
import gc
import asyncio
import uuid
from pathlib import Path
from types import SimpleNamespace
import warnings

warnings.filterwarnings("ignore")
WORKSPACE_ROOT = Path(LEGACY_ENTRYPOINT_FILE).resolve().parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))
SPATIALMETA_RUNTIME_SPEC = "spatialMETA==0.0.3.0"
TORCH_RUNTIME_SPEC = "torch==2.8.0+cpu"
TORCHVISION_RUNTIME_SPEC = "torchvision==0.23.0+cpu"
import scanpy as sc

try:
    import torch
except Exception as exc:
    raise RuntimeError(
        f"PyTorch runtime dependency is unavailable. Install {TORCH_RUNTIME_SPEC} and {TORCHVISION_RUNTIME_SPEC} in the SpaShiny web runtime."
    ) from exc
try:
    import spatialmeta as smt
except Exception as exc:
    raise RuntimeError(
        f"SpatialMeta runtime dependency is unavailable. Install {SPATIALMETA_RUNTIME_SPEC} with the SpaShiny web runtime dependency lock."
    ) from exc
from shiny import App, ui, reactive, render, req
from shiny import reactive

try:
    from spatialmeta.model import AlignmentModule
except Exception as exc:
    raise RuntimeError("SpatialMeta AlignmentModule runtime dependency is unavailable.") from exc
import numpy as np
import pandas as pd

if not hasattr(pd.DataFrame, "append"):

    def _spashiny_dataframe_append(
        self, other, ignore_index=False, verify_integrity=False, sort=False
    ):
        if isinstance(other, dict):
            other = pd.DataFrame([other])
        elif isinstance(other, pd.Series):
            other = other.to_frame().T
        return pd.concat(
            [self, other], ignore_index=ignore_index, verify_integrity=verify_integrity, sort=sort
        )

    pd.DataFrame.append = _spashiny_dataframe_append
import scanpy as sc
import copy
import matplotlib
import matplotlib.pyplot as plt
from spashiny_enrichment_module.modules.enrichment_module_ui import enrichment_module_ui
from spashiny_enrichment_module.modules.enrichment_module_server import enrichment_module_server
from help_tutorial import help_tutorial_ui
from river_st_module import river_st_module_server, river_st_module_ui
from sm_tic_roi_module import sm_tic_roi_module_server, sm_tic_roi_module_ui
from enrichment_result_tools import (
    artifact_ui as enrichment_artifact_ui,
    register_downloads as register_enrichment_downloads,
)
from plot_color_tools import (
    COLOR_PRESETS,
    FIXED_COLORS,
    apply_color_settings_to_figure,
    clone_figure,
    extract_color_spec_from_figure,
    expand_color_list,
    figure_looks_empty,
    normalize_color,
    plot_output_with_palette,
    preset_colormap,
    preset_colors_for_count,
    settings_from_color_spec,
)
from cloud.figure_export import save_native_figure, mark_source_image
from spatialmeta_workbench_ui import one_stop_ui, network_panel_ui, register_workbench
from spatialmeta_workbench_adapter import (
    create_adapter,
    preserve_downstream_labels,
    resolve_pipeline_result,
)
from alignment_plot_export import (
    STEP7_EXPORT_VERSION as ALIGNMENT_EXPORT_VERSION,
    checked_path as alignment_checked_path,
    build_step7_tutorial_figure,
    export_saved_step4,
    read_step7_plot_inputs,
    step7_cache_key,
)
from plot_runtime import (
    build_session_feature_plot,
    editable_figure,
    native_matplotlib_figure,
    prepare_volcano_input,
    save_editable_figure,
    session_plotly_html,
)
from ssh_module import (
    ssh_module_ui,
    ssh_module_server,
    ssh_status_indicator_ui,
    ssh_connection_ready,
    ssh_check_python_packages,
    ssh_download_file,
    ssh_exec_command,
    ssh_open_client,
    ssh_prepare_job_dir,
    ssh_quote,
    ssh_upload_file,
    ssh_upload_text,
    REQUIRED_STSM_PACKAGES,
)

try:
    from memory_tools import current_process_memory
except Exception:
    current_process_memory = None
try:
    import psutil
except Exception:
    psutil = None
matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42
matplotlib.rcParams["ps.fonttype"] = 42
matplotlib.rcParams["svg.fonttype"] = "none"
import threading
import traceback
import time
import random
import re
import functools
from pathlib import Path

SEED = 42
_SPASHINY_WEB_FLAG = os.environ.get("SPASHINY_WEB_PLATFORM", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
SPASHINY_DEPLOYMENT_PROFILE = os.environ.get("SPASHINY_DEPLOYMENT_PROFILE", "").strip().lower()
SPASHINY_DEPLOYMENT_MODE = (
    os.environ.get(
        "SPASHINY_DEPLOYMENT_MODE",
        (
            "lab"
            if SPASHINY_DEPLOYMENT_PROFILE == "lab_server"
            else "web" if _SPASHINY_WEB_FLAG else "desktop"
        ),
    )
    .strip()
    .lower()
)
SPASHINY_WEB_PLATFORM = SPASHINY_DEPLOYMENT_MODE in {"web", "lab"} or _SPASHINY_WEB_FLAG
SPASHINY_LAB_PROFILE = (
    SPASHINY_DEPLOYMENT_PROFILE == "lab_server"
    or SPASHINY_DEPLOYMENT_MODE == "lab"
    or os.environ.get("SPASHINY_LAB_PROFILE", "0").strip().lower() in {"1", "true", "yes", "on"}
)
LAB_COMPUTE_RESOURCE_CHOICES = {"auto": "Auto", "gpu-0": "GPU 1", "gpu-1": "GPU 2", "cpu": "CPU"}
LAB_GPU_COMPUTE_RESOURCE_CHOICES = {"auto": "Auto", "gpu-0": "GPU 1", "gpu-1": "GPU 2"}
SINGLE_SAMPLE_COMPUTE_RESOURCE = "gpu-0"
LAB_TRAINING_DEVICE_CHOICES = {"auto": "Auto", "cuda:0": "GPU 1", "cuda:1": "GPU 2"}
LOCAL_TRAINING_DEVICE_CHOICES = {"auto": "Auto", "cuda:0": "GPU 0", "cuda:1": "GPU 1", "cpu": "CPU"}
RESOURCE_STATUS_LABEL = "Lab Resources" if SPASHINY_LAB_PROFILE else "Resource Status"
SPASHINY_R_FEATURES_ENABLED = os.environ.get(
    "SPASHINY_R_FEATURES_ENABLED", "0" if SPASHINY_LAB_PROFILE else "1"
).strip().lower() in {"1", "true", "yes", "on"}
SPASHINY_CPU_ENRICHMENT_ENABLED = os.environ.get(
    "SPASHINY_CPU_ENRICHMENT_ENABLED", "1" if SPASHINY_LAB_PROFILE else "0"
).strip().lower() in {"1", "true", "yes", "on"}
SPASHINY_SHOW_EXAMPLE_ASSET_DEBUG = os.environ.get(
    "SPASHINY_SHOW_EXAMPLE_ASSET_DEBUG", "0"
).strip().lower() in {"1", "true", "yes", "on"}
SPASHINY_ENABLE_EMBEDDED_DASH = os.environ.get(
    "SPASHINY_ENABLE_EMBEDDED_DASH", "0" if SPASHINY_WEB_PLATFORM else "1"
).strip().lower() in {"1", "true", "yes", "on"}
DASH_BIND_HOST = os.environ.get("SPASHINY_DASH_BIND_HOST", "127.0.0.1").strip() or "127.0.0.1"
DASH_PROXY_BASE_PATH = (
    os.environ.get("SPASHINY_DASH_PROXY_BASE_PATH", "/dash-proxy").strip().rstrip("/")
    or "/dash-proxy"
)
DASH_APP_CONSTRUCTOR_LOCK = threading.Lock()


def set_global_seed(seed=42, deterministic=True):
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    np.random.seed(seed)
    try:
        sc.settings.seed = seed
    except Exception:
        pass
    try:
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed(seed)
            torch.cuda.manual_seed_all(seed)
        if deterministic:
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
            try:
                torch.use_deterministic_algorithms(True, warn_only=True)
            except Exception:
                pass
    except Exception:
        pass


set_global_seed(SEED)
DASH_PORT = 8050
PLOT_COLOR_IDS = [
    "qc_violin",
    "qc_hist",
    "qc_spatial",
    "st_qc_violin",
    "st_qc_hist",
    "st_qc_spatial",
    "initial_plot",
    "overlay_plot",
    "side_plot",
    "raster_plot",
    "spot_only_plot",
    "raster_panel_sm_feature",
    "raster_panel_sm_latent",
    "raster_panel_st_image",
    "raster_panel_st_latent",
    "spot_panel_st_latent",
    "spot_panel_sampled",
    "spot_panel_mask",
    "align_step7_show_alignment_plot",
    "perform_scale_and_plot",
    "knn_plot",
    "st_counts_histograms",
    "joint_spatial_plot1",
    "joint_spatial_plot2",
    "loss_plot",
    "umap_plot",
    "spatial_cluster_plot",
    "feature_original_plot",
    "feature_reconstruction_plot",
    "modality_contribution_spatial_plot",
    "modality_contribution_violin_plot",
    "sample_distribution_plot",
    "qc_violin_plot",
    "qc_scatter_plot",
    "spatial_variable_genes_plot",
    "loss_curves_plot",
    "umap_by_sample_plot",
    "umap_by_cluster_plot",
    "modality_contribution_plot",
    "reconstruction_quality_plot",
    "reconstruction_error_plot",
    "cluster_analysis_plot",
    "sm_sample_size_plot",
    "sm_feature_distribution_plot",
    "svm_plot",
    "sm_debatch_umap",
    "sm_batch_effect_evaluation",
    "vae_training_loss_plot",
    "plt_marker_celltype",
    "plt_corr_heatmap",
    "plt_gene_volcano",
    "plt_metabolite_volcano",
    "traj_arrow_plot",
    "traj_smooth_plot",
    "traj_feature_plot",
    "toi_gene_heatmap",
    "toi_mz_heatmap",
    "toi_mz_feature_plot",
    "roi_spatial_plot",
    "roi_marker_plot",
]


def humanize_plot_id(plot_id):
    return str(plot_id).replace("_", " ").title()


def resolve_enrichment_rscript():
    runtime_r_root = WORKSPACE_ROOT / "runtime" / "R"
    versioned_rscripts = (
        sorted(runtime_r_root.glob("R-*/bin/Rscript.exe"), reverse=True)
        if runtime_r_root.exists()
        else []
    )
    candidates = [
        *versioned_rscripts,
        WORKSPACE_ROOT / "runtime" / "R" / "bin" / "Rscript.exe",
        WORKSPACE_ROOT / "runtime" / "R" / "Rscript.exe",
        WORKSPACE_ROOT / "R" / "bin" / "Rscript.exe",
        WORKSPACE_ROOT / "R" / "Rscript.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return "Rscript"


def safe_console_print(*args, sep=" ", end="\n", flush=False):
    text = sep.join((str(arg) for arg in args)) + end
    stream = sys.stdout
    try:
        stream.write(text)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "utf-8"
        safe_text = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
        stream.write(safe_text)
    if flush:
        stream.flush()


LOG_ICON_PREFIX_RE = re.compile(
    "^\\s*(?:[\\U0001F300-\\U0001FAFF]|[\\u2600-\\u27BF]|\\ufe0f|\\u200d)+\\s*"
)


def sanitize_log_message(msg):
    text = str(msg)
    for _ in range(4):
        cleaned = LOG_ICON_PREFIX_RE.sub("", text)
        if cleaned == text:
            break
        text = cleaned
    return text


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
USER_INPUT_DIR = Path(LEGACY_ENTRYPOINT_FILE).resolve().parents[1] / "user_data" / "input"
USER_OUTPUT_DIR = Path(LEGACY_ENTRYPOINT_FILE).resolve().parents[1] / "user_data" / "output"
EXAMPLE_SAMPLE_NAME = "sample-1_Y7_T"
EXAMPLE_ST_H5AD_NAME = "adata_ST_Y7_T_raw.h5ad"
EXAMPLE_SM_H5AD_NAME = "adata_SM_Y7_T_raw.h5ad"
EXAMPLE_ST_RAW_DIR_NAME = "ST_raw"
EXAMPLE_ST_QC_H5AD_NAME = EXAMPLE_ST_H5AD_NAME
EXAMPLE_SM_QC_H5AD_NAME = EXAMPLE_SM_H5AD_NAME
EXAMPLE_KNN_ST_H5AD_NAME = "Y7_T_adata_ST_qc.h5ad"
EXAMPLE_KNN_SM_H5AD_NAME = "adata_SM_Y7_T_raw.aligned.h5ad"
EXAMPLE_DOWNSTREAM_JOINT_H5AD_NAME = "Y7_T_adata_joint_hvf2800_afterVAE_annoSM.h5ad"
EXAMPLE_JOINT_BATCH_DIR = Path(
    os.environ.get("SPASHINY_VHIT_EXAMPLE_DIR", "/workspace/data/examples/raw/multimodal/joint")
).resolve()
EXAMPLE_SM_BATCH_DIR = Path(
    os.environ.get(
        "SPASHINY_HIT_SM_EXAMPLE_DIR", "/workspace/data/examples/raw/spatial_metabolomics/SM"
    )
).resolve()
EXAMPLE_JOINT_BATCH_RAW_FILES = [
    "adata_joint_R114_T_raw.h5ad",
    "adata_joint_S15_T_raw.h5ad",
    "adata_joint_X49_T_raw.h5ad",
    "adata_joint_Y27_T_raw.h5ad",
    "adata_joint_Y7_T_raw.h5ad",
]
EXAMPLE_SM_BATCH_RAW_FILES = [
    "adata_SM_R114_T_raw.h5ad",
    "adata_SM_S15_T_raw.h5ad",
    "adata_SM_X49_T_raw.h5ad",
    "adata_SM_Y27_T_raw.h5ad",
    "adata_SM_Y7_T_raw.h5ad",
]
DEFAULT_SM_QC_MIN_TOTAL_INTENSITY = 100000.0
DEFAULT_ST_QC_MIN_COUNTS = 3000
DEFAULT_ST_QC_MIN_GENES = 1000


def workspace_relative_path(path):
    path = Path(path)
    try:
        return path.resolve().relative_to(WORKSPACE_ROOT).as_posix()
    except Exception:
        return path.as_posix()


def cloud_example_action_attrs(action_id, page_name, status_target):
    if not SPASHINY_WEB_PLATFORM:
        return {}
    return {
        "data-action-id": str(action_id),
        "data-page-name": str(page_name),
        "data-status-target": str(status_target),
    }


def cloud_example_button_class(base_class):
    classes = str(base_class or "").strip()
    if SPASHINY_WEB_PLATFORM and "cloud-example-action" not in classes:
        classes = f"{classes} cloud-example-action".strip()
    return classes


def cloud_example_status(status_id):
    return ui.tags.div(
        "Cloud example is ready to bind in this session. No job starts until you run the analysis.",
        id=str(status_id),
        class_="cloud-example-status cloud-muted",
        style="font-size:12px; color:#6e6e73; line-height:1.5; margin-top:6px;",
    )


def example_source_note(
    local_text,
    cloud_text="Cloud built-in example is session-bound on click; it is not downloaded to the Web container.",
):
    return cloud_text if SPASHINY_WEB_PLATFORM else local_text


def get_example_sm_imzml_pairs():
    example_sm_dir = get_example_sm_dir()
    pairs = {
        "positive_imzml": example_sm_dir / "Y7_T_pos.imzML",
        "positive_ibd": example_sm_dir / "Y7_T_pos.ibd",
        "negative_imzml": example_sm_dir / "Y7_T_neg.imzML",
        "negative_ibd": example_sm_dir / "Y7_T_neg.ibd",
    }
    missing = [workspace_relative_path(path) for path in pairs.values() if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing example SM paired files: " + ", ".join(missing))
    return pairs


def get_allowlisted_example_files(directory, filenames):
    paths = [Path(directory) / filename for filename in filenames]
    missing = [workspace_relative_path(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing bundled example files: " + ", ".join(missing))
    return paths


def resolve_y7_example_input(workflow, page_name, role):
    from cloud.lab_example_inputs import resolve_example_input

    return resolve_example_input(
        workflow=workflow, page_name=page_name, role=role, example_id="Y7_T"
    )


def resolve_y7_example_inputs(workflow, page_name, *roles):
    return {role: resolve_y7_example_input(workflow, page_name, role) for role in roles}


def read_numeric_input(getter, default, cast=float, minimum=None):
    try:
        value = getter()
    except Exception:
        value = default
    if value is None or value == "":
        value = default
    try:
        value = cast(value)
    except (TypeError, ValueError):
        value = cast(default)
    if minimum is not None and value < minimum:
        value = minimum
    return value


def create_user_output_job_dir(prefix="spatialmeta"):
    USER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    job_dir = USER_OUTPUT_DIR / f"job_{prefix}_{stamp}_{uuid.uuid4().hex[:8]}"
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


def resolve_spatialmeta_backend_python():
    return os.environ.get("SPASHINY_RIVER_PYTHON", sys.executable)


from cloud.spatialmeta_tutorial_policy import (
    NOTICE as NATIVE_SPATIALMETA_NOTICE,
    POLICY as NATIVE_SPATIALMETA_POLICY,
    tutorial_model_defaults,
    tutorial_training_defaults,
    tutorial_job_parameters,
    alignment_epochs,
    alignment_iterations,
)

ORIGINAL_SPATIALMETA_MODEL_CONFIG = tutorial_model_defaults(smt)
ORIGINAL_SPATIALMETA_TRAINING_CONFIG = tutorial_training_defaults(smt)


def read_h5ad_for_display(path):
    if not path or not os.path.exists(path):
        return (None, False)
    try:
        return (sc.read_h5ad(path, backed="r"), True)
    except Exception:
        return (sc.read_h5ad(path), False)


def close_display_h5ad(adata_obj, should_close):
    if not should_close or adata_obj is None:
        return
    try:
        file_obj = getattr(adata_obj, "file", None)
        if file_obj is not None:
            file_obj.close()
    except Exception:
        pass


def read_worker_training_metadata(result_path):
    """Read only compact, fixed-name metadata in an already authorized result.

    Worker summary paths describe its execution workspace, not the published
    workspace. Never follow those absolute paths or materialize AnnData here.
    """
    import json
    from pathlib import Path

    if not result_path:
        return ({}, {})
    root = Path(str(result_path)).resolve().parent

    def read_compact(relative_paths, limit):
        for relative in relative_paths:
            path = (root / relative).resolve()
            if not path.is_file():
                continue
            if root not in path.parents:
                raise ValueError(
                    "Worker training metadata escapes its authorized result directory."
                )
            if path.stat().st_size > limit:
                raise ValueError("Worker training metadata exceeds its display size limit.")
            with path.open(encoding="utf-8") as handle:
                value = json.load(handle)
            if not isinstance(value, dict):
                raise ValueError("Worker training metadata must be a JSON object.")
            return value
        return {}

    persisted = read_compact(("summary.json", "output/summary.json"), 256 * 1024)
    metadata = {
        key: persisted[key]
        for key in (
            "resolved_config",
            "device",
            "reconstruction_diagnostics",
            "filter_provenance",
            "shape",
            "elapsed_seconds",
            "cluster_key",
            "success",
            "message",
        )
        if key in persisted
    }
    metadata["result_h5ad"] = str(Path(str(result_path)).resolve())
    for relative in ("model_state.pt", "output/model_state_dict.pt"):
        state_path = (root / relative).resolve()
        if state_path.is_file():
            if root not in state_path.parents:
                raise ValueError("Worker model state escapes its authorized result directory.")
            if state_path.stat().st_size > 0:
                metadata["model_state_path"] = str(state_path)
                break
    losses = read_compact(("loss_record.json", "output/loss_record.json"), 8 * 1024 * 1024)
    return (metadata, losses)


def find_vae_cluster_key(adata_obj):
    if adata_obj is None:
        return None
    obs_cols = list(getattr(adata_obj, "obs", pd.DataFrame()).columns)
    for key in ("VAE_clusters", "VAE_clusters_latent10"):
        if key in obs_cols:
            return key
    candidates = [str(col) for col in obs_cols if str(col).startswith("VAE_clusters")]
    return candidates[0] if candidates else None


def get_example_sample_dir(sample_name=EXAMPLE_SAMPLE_NAME):
    sample_dir = USER_INPUT_DIR / sample_name
    if sample_dir.exists():
        return sample_dir
    for candidate in sorted(USER_INPUT_DIR.glob("sample-*")):
        if candidate.is_dir():
            return candidate
    return sample_dir


def get_example_st_dir(sample_name=EXAMPLE_SAMPLE_NAME):
    return get_example_sample_dir(sample_name) / "ST" / "outs"


def get_example_st_raw_dir(sample_name=EXAMPLE_SAMPLE_NAME):
    return get_example_sample_dir(sample_name) / "ST" / EXAMPLE_ST_RAW_DIR_NAME


def get_example_sm_dir(sample_name=EXAMPLE_SAMPLE_NAME):
    return get_example_sample_dir(sample_name) / "SM"


def _h5ad_safe_key(value):
    text = str(value).replace("/", "").strip()
    return text or "unnamed"


def _make_unique_key(base, existing):
    if base not in existing:
        return base
    counter = 1
    while f"{base}_{counter}" in existing:
        counter += 1
    return f"{base}_{counter}"


def _is_missing_scalar(value):
    try:
        missing = pd.isna(value)
        if isinstance(missing, (bool, np.bool_)):
            return bool(missing)
    except Exception:
        pass
    return False


def _coerce_h5ad_object_column(series):
    if not pd.api.types.is_object_dtype(series):
        return series
    non_missing = [value for value in series if not _is_missing_scalar(value)]
    if not non_missing:
        return series
    if all((isinstance(value, (str, bytes)) for value in non_missing)):
        return series
    try:
        numeric = pd.to_numeric(series, errors="coerce")
        if int(numeric.notna().sum()) == len(non_missing):
            return numeric
    except Exception:
        pass
    return series.map(lambda value: "" if _is_missing_scalar(value) else str(value))


def _sanitize_h5ad_dataframe(df, label):
    changes = []
    existing = set()
    new_columns = []
    for column in df.columns:
        safe_column = _make_unique_key(_h5ad_safe_key(column), existing)
        existing.add(safe_column)
        new_columns.append(safe_column)
        if safe_column != column:
            changes.append(f"{label}.{column}->{safe_column}")
    if changes:
        df.columns = new_columns
    if df.index.name is not None:
        safe_index_name = _h5ad_safe_key(df.index.name)
        if safe_index_name != df.index.name:
            changes.append(f"{label}.index:{df.index.name}->{safe_index_name}")
            df.index.name = safe_index_name
    for column in df.columns:
        original = df[column]
        coerced = _coerce_h5ad_object_column(original)
        if coerced is not original:
            df[column] = coerced
    return changes


def _sanitize_h5ad_mapping(mapping, label, recursive=False):
    changes = []
    try:
        keys = list(mapping.keys())
    except Exception:
        return changes
    existing = set(keys)
    for key in keys:
        value = mapping[key]
        if recursive and isinstance(value, dict):
            changes.extend(_sanitize_h5ad_mapping(value, f"{label}.{key}", recursive=True))
        safe_key = _h5ad_safe_key(key)
        if safe_key == key:
            continue
        existing.discard(key)
        unique_key = _make_unique_key(safe_key, existing)
        existing.add(unique_key)
        mapping[unique_key] = mapping.pop(key)
        changes.append(f"{label}.{key}->{unique_key}")
    return changes


def sanitize_h5ad_keys(adata):
    """Make AnnData metadata safe for h5ad/HDF5 writing."""
    if adata is None:
        return []
    changes = []
    changes.extend(_sanitize_h5ad_dataframe(adata.obs, "obs"))
    changes.extend(_sanitize_h5ad_dataframe(adata.var, "var"))
    changes.extend(_sanitize_h5ad_mapping(adata.uns, "uns", recursive=True))
    for attr_name in ("layers", "obsm", "varm", "obsp", "varp"):
        changes.extend(_sanitize_h5ad_mapping(getattr(adata, attr_name), attr_name))
    return changes


def release_unused_memory():
    gc.collect()
    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def compact_matrix_copy(X, dtype=np.float32):
    if X is None:
        return None
    try:
        import scipy.sparse as sp

        if sp.issparse(X):
            out = X.copy()
            if dtype is not None and np.issubdtype(out.dtype, np.number):
                out = out.astype(dtype)
            return out.tocsr() if hasattr(out, "tocsr") else out
    except Exception:
        pass
    try:
        arr = np.asarray(X)
        if dtype is not None and np.issubdtype(arr.dtype, np.number):
            return arr.astype(dtype, copy=True)
        return arr.copy()
    except Exception:
        return X.copy() if hasattr(X, "copy") else copy.deepcopy(X)


def compact_existing_matrix(X, dtype=np.float32):
    if X is None:
        return None
    try:
        import scipy.sparse as sp

        if sp.issparse(X):
            out = X
            if (
                dtype is not None
                and np.issubdtype(out.dtype, np.number)
                and (out.dtype != np.dtype(dtype))
            ):
                out = out.astype(dtype)
            if not sp.isspmatrix_csr(out) and hasattr(out, "tocsr"):
                out = out.tocsr()
            return out
    except Exception:
        pass
    try:
        arr = X if isinstance(X, np.ndarray) else np.asarray(X)
        if (
            dtype is not None
            and np.issubdtype(arr.dtype, np.number)
            and (arr.dtype != np.dtype(dtype))
        ):
            return arr.astype(dtype, copy=False)
        return arr
    except Exception:
        return X


def set_compact_layer(adata, layer_name, source=None, dtype=np.float32):
    adata.layers[layer_name] = compact_matrix_copy(
        adata.X if source is None else source, dtype=dtype
    )
    return adata.layers[layer_name]


def set_X_from_layer(adata, layer_name, dtype=np.float32):
    adata.X = compact_matrix_copy(adata.layers[layer_name], dtype=dtype)
    return adata.X


def compact_adata_X(adata, dtype=np.float32):
    try:
        adata.X = compact_existing_matrix(adata.X, dtype=dtype)
    except Exception:
        pass
    try:
        for layer_name in list(adata.layers.keys()):
            adata.layers[layer_name] = compact_existing_matrix(
                adata.layers[layer_name], dtype=dtype
            )
    except Exception:
        pass
    return adata


def preview_h5ad_metadata(path):
    adata = sc.read_h5ad(path, backed="r")
    try:
        return {
            "shape": tuple(adata.shape),
            "n_obs": int(adata.n_obs),
            "n_vars": int(adata.n_vars),
            "obs_columns": list(adata.obs.columns),
            "var_columns": list(adata.var.columns),
        }
    finally:
        try:
            adata.file.close()
        except Exception:
            pass


def log_process_memory(log_func, label="Memory"):
    if current_process_memory is None:
        return
    try:
        mem = current_process_memory()
        log_func(f"{label}: RSS {mem['rss_text']}")
    except Exception:
        pass


MEMORY_GB = 1024**3
_TORCH_RUNTIME_CONFIGURED = False


def format_memory_bytes(num_bytes):
    try:
        num_bytes = float(num_bytes)
    except Exception:
        return "unknown"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num_bytes) < 1024 or unit == "TB":
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} TB"


def available_memory_bytes():
    if psutil is None:
        return None
    try:
        return int(psutil.virtual_memory().available)
    except Exception:
        return None


def matrix_nbytes(X):
    if X is None:
        return 0
    try:
        import scipy.sparse as sp

        if sp.issparse(X):
            total = 0
            for part in (
                getattr(X, "data", None),
                getattr(X, "indices", None),
                getattr(X, "indptr", None),
            ):
                total += int(getattr(part, "nbytes", 0) or 0)
            return total
    except Exception:
        pass
    try:
        return int(getattr(X, "nbytes", 0) or 0)
    except Exception:
        return 0


def estimate_adata_matrix_bytes(adata, include_layers=True, include_obsm=True):
    if adata is None:
        return 0
    total = matrix_nbytes(getattr(adata, "X", None))
    if include_layers:
        try:
            for layer_name in list(adata.layers.keys()):
                total += matrix_nbytes(adata.layers[layer_name])
        except Exception:
            pass
    if include_obsm:
        try:
            for key in list(adata.obsm.keys()):
                total += matrix_nbytes(adata.obsm[key])
        except Exception:
            pass
    return int(total)


def notify_memory_warning(message, notify_func=None, duration=12):
    try:
        if notify_func is not None:
            notify_func(message, type_="error", duration=duration)
        else:
            ui.notification_show(message, type="error", duration=duration)
    except Exception:
        pass


def preflight_memory(
    task_name,
    adata=None,
    bytes_needed=None,
    multiplier=2.5,
    min_available_gb=1.5,
    log_func=None,
    notify_func=None,
):
    release_unused_memory()
    available = available_memory_bytes()
    if available is None:
        if log_func is not None:
            try:
                log_func(f"[Memory] {task_name}: system memory check unavailable; continuing.")
            except Exception:
                pass
        return True
    base_bytes = int(
        bytes_needed if bytes_needed is not None else estimate_adata_matrix_bytes(adata)
    )
    required = max(int(base_bytes * multiplier), int(float(min_available_gb) * MEMORY_GB))
    if log_func is not None:
        try:
            log_func(
                f"[Memory] {task_name}: available {format_memory_bytes(available)}, estimated peak {format_memory_bytes(required)}."
            )
        except Exception:
            pass
    if available < required:
        msg = f"Insufficient memory for {task_name}. Available: {format_memory_bytes(available)}; estimated peak: {format_memory_bytes(required)}. The task was stopped to keep the app responsive. Please close other apps or reduce highly variable features, batch size, epochs, or samples."
        if log_func is not None:
            try:
                log_func(f"[Memory] {msg}")
            except Exception:
                pass
        raise MemoryError(msg)
    return True


def configure_torch_runtime_for_desktop(log_func=None):
    global _TORCH_RUNTIME_CONFIGURED
    if _TORCH_RUNTIME_CONFIGURED:
        return
    try:
        cpu_count = os.cpu_count() or 1
        torch_threads = max(1, min(cpu_count, 4))
        torch.set_num_threads(torch_threads)
        try:
            torch.set_num_interop_threads(1)
        except Exception:
            pass
        try:
            torch.backends.cudnn.benchmark = False
        except Exception:
            pass
        _TORCH_RUNTIME_CONFIGURED = True
        if log_func is not None:
            log_func(
                f"[Runtime] Torch threads limited to {torch_threads} to reduce memory spikes and swapping."
            )
    except Exception:
        pass


def tune_batch_size_for_memory(batch_size, log_func=None):
    try:
        batch_size = int(batch_size)
    except Exception:
        batch_size = 128
    available = available_memory_bytes()
    tuned = batch_size
    if available is not None:
        if available < 2 * MEMORY_GB:
            tuned = min(batch_size, 32)
        elif available < 4 * MEMORY_GB:
            tuned = min(batch_size, 64)
    if tuned != batch_size and log_func is not None:
        try:
            log_func(
                f"[Memory] Batch size adjusted from {batch_size} to {tuned} to avoid swapping/OOM."
            )
        except Exception:
            pass
    return tuned


def is_memory_related_exception(exc):
    if isinstance(exc, MemoryError):
        return True
    text = str(exc).lower()
    markers = (
        "out of memory",
        "memoryerror",
        "unable to allocate",
        "not enough memory",
        "paging file",
        "cuda out of memory",
        "bad allocation",
    )
    return any((marker in text for marker in markers))


def user_facing_error(prefix, exc):
    """Format synchronous/local analysis failures with actionable detail.

    Cloud jobs use ``_job_error_ui`` below; local preprocessing/training paths
    historically called this helper directly.  Keep the execution semantics
    unchanged while applying the same network/GPU/resource/input/permission
    classification to those paths as well.
    """
    detail = str(exc or "").strip()
    try:
        info = _analysis_error_info(
            getattr(exc, "code", "") or "", detail, type(exc).__name__ if exc is not None else ""
        )
        return f"{prefix}: {info['label']}. {info['message']} ({(info['code'] or type(exc).__name__ if exc is not None else 'ERROR')}). {info['guidance']} Detail: {detail or 'No additional details were provided.'}"
    except Exception:
        if is_memory_related_exception(exc):
            return f"{prefix}: insufficient memory. The task was stopped before the app became unresponsive. Close other apps or reduce features/epochs/batch size. Detail: {detail}"
        return f"{prefix}: {detail or 'No additional details were provided.'}"


_ANALYSIS_ERROR_RULES = (
    (
        "network",
        "Network / connectivity error",
        "Check the network or SSH tunnel and retry. The input file was not changed.",
        (
            "NETWORK",
            "TIMEOUT",
            "TIMED_OUT",
            "REMOTE_UNREACHABLE",
            "CONNECTION",
            "CONNECT",
            "DNS",
            "HTTP_",
            "HTTP ",
            "DOWNLOAD",
            "UPLOAD",
            "PRESIGN",
            "PART_UPLOAD",
            "R2_",
            "S3_",
            "PROXY",
            "DISCONNECT",
            "BROKEN_PIPE",
        ),
    ),
    (
        "hardware",
        "GPU / hardware error",
        "The compute device or driver reported an error. Retry, or select CPU when available; do not delete the input data.",
        (
            "CUDA",
            "GPU",
            "NVIDIA",
            "CUDNN",
            "ROCM",
            "MPS",
            "DEVICE_LOST",
            "DRIVER",
            "XID",
            "GPU_SUBPROCESS",
            "HARDWARE",
        ),
    ),
    (
        "resource",
        "Memory / resource error",
        "The job needs more memory, disk, or queue capacity. Reduce the workload or wait for a slot and retry.",
        (
            "OUT_OF_MEMORY",
            "OOM",
            "MEMORY",
            "BAD_ALLOC",
            "NO_SPACE",
            "DISK_FULL",
            "QUEUE_FULL",
            "RESOURCE",
            "SCHEDUL",
            "CAPACITY",
            "LIMIT",
        ),
    ),
    (
        "input",
        "Input / result validation error",
        "Check the file format, dimensions, required layers, and generated artifacts before retrying.",
        (
            "INPUT",
            "H5AD",
            "ANNDATA",
            "FEATURE",
            "SHAPE",
            "SCHEMA",
            "PARSE",
            "VALIDATION",
            "RESULT_MISSING",
            "MANIFEST",
            "ARTIFACT",
            "FORMAT",
        ),
    ),
    (
        "permission",
        "Permission / session error",
        "The analysis session or resource authorization is no longer valid. Refresh the session and retry.",
        (
            "AUTH",
            "FORBIDDEN",
            "UNAUTHORIZED",
            "PERMISSION",
            "READONLY",
            "OWNER",
            "ANALYSIS_SESSION",
            "SESSION_EXPIRED",
            "SESSION_REQUIRED",
            "ACCESS_DENIED",
        ),
    ),
)


def _redact_analysis_detail(value, limit=4000):
    """Return useful diagnostics without exposing credentials or tokens."""
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(
        "(?i)(authorization|x-spashiny-session|x-spashiny-analysis-session|token|secret|password|api[_-]?key)\\s*[:=]\\s*[^\\s,;]+",
        "\\1=<redacted>",
        text,
    )
    return text[: int(limit)]


def _analysis_error_info(
    error_code="",
    error_message="",
    error_type="",
    traceback_text="",
    *,
    job_id="",
    workflow="",
    current_step="",
):
    """Classify a persisted analysis failure and build safe user details."""
    code = _redact_analysis_detail(error_code, 160)
    kind = _redact_analysis_detail(error_type, 160)
    message = _redact_analysis_detail(error_message, 1200)
    trace = _redact_analysis_detail(traceback_text, 4000)
    haystack = " ".join((code, kind, message)).upper()
    category = "internal"
    label = "Analysis execution error"
    guidance = "The worker did not complete the analysis. Keep the Job ID and diagnostic details when contacting support."
    for candidate, candidate_label, candidate_guidance, markers in _ANALYSIS_ERROR_RULES:
        if any((marker in haystack for marker in markers)):
            category = candidate
            label = candidate_label
            guidance = candidate_guidance
            break
    if not message:
        message = "The worker did not provide an error message."
    detail_lines = [
        f"Category: {label}",
        f"Error code: {code or 'N/A'}",
        f"Error type: {kind or 'N/A'}",
        f"Workflow: {_redact_analysis_detail(workflow, 200) or 'N/A'}",
        f"Step: {_redact_analysis_detail(current_step, 200) or 'N/A'}",
        f"Job ID: {_redact_analysis_detail(job_id, 200) or 'N/A'}",
        f"Message: {message}",
    ]
    if trace:
        detail_lines.extend(("Traceback (redacted):", trace))
    return {
        "category": category,
        "label": label,
        "guidance": guidance,
        "code": code,
        "message": message,
        "details": "\n".join(detail_lines),
    }


def _job_error_ui(job, *, title="Analysis failed"):
    """Render the same actionable error card for every cloud workflow."""
    if job is None:
        return ui.tags.div("No job details are available.", class_="alert alert-danger")
    if isinstance(job, dict):
        get_value = job.get
    else:
        get_value = lambda key, default="": getattr(job, key, default)
    info = _analysis_error_info(
        get_value("error_code", ""),
        get_value("error_message", "") or get_value("message", ""),
        get_value("error_type", ""),
        get_value("traceback", ""),
        job_id=get_value("job_id", ""),
        workflow=get_value("workflow_name", "") or get_value("workflow", ""),
        current_step=get_value("current_step", ""),
    )
    return ui.tags.div(
        ui.tags.strong(f"{title}: {info['label']}"),
        ui.tags.div(info["message"], style="margin-top:4px; white-space:pre-wrap;"),
        ui.tags.div(info["guidance"], class_="cloud-muted", style="margin-top:4px;"),
        ui.tags.details(
            ui.tags.summary("Show diagnostic details"),
            ui.tags.pre(
                info["details"],
                style="white-space:pre-wrap; max-height:260px; overflow:auto; margin-top:8px;",
            ),
            style="margin-top:8px;",
        ),
        class_="alert alert-danger spashiny-analysis-error",
        role="alert",
        style="margin-top:8px;",
    )


def _upload_failure_text(payload, filename, label="Upload"):
    """Format canonical multipart failures for every upload-backed workflow."""
    payload = payload if isinstance(payload, dict) else {}
    info = _analysis_error_info(
        payload.get("code") or "UPLOAD_FAILED",
        payload.get("message") or payload.get("error_message") or "",
        payload.get("error_type") or "",
        payload.get("traceback") or "",
        job_id=payload.get("upload_id") or "",
        workflow=label,
        current_step="multipart upload",
    )
    return f"{label} failed for {filename}: {info['label']}. {info['message']} ({info['code'] or 'UPLOAD_FAILED'}). {info['guidance']}"


def _analysis_status_error_text(prefix, status, *, job_id="", workflow="", current_step=""):
    """Classify a worker status payload used by local/Alignment renderers."""
    payload = status if isinstance(status, dict) else {}
    info = _analysis_error_info(
        payload.get("error_code") or payload.get("code") or "WORKER_FAILED",
        payload.get("error") or payload.get("error_message") or payload.get("message") or "",
        payload.get("error_type") or "",
        payload.get("traceback") or payload.get("traceback_text") or "",
        job_id=job_id or payload.get("job_id") or "",
        workflow=workflow or payload.get("workflow") or "",
        current_step=current_step or payload.get("step") or "",
    )
    return f"{prefix}: {info['label']}. {info['message']} ({info['code'] or 'WORKER_FAILED'}). {info['guidance']}"


def get_visium_count_file(visium_dir):
    for count_file in (
        "filtered_feature_bc_matrix.h5",
        "filtered_feature_bc_matrix",
        "raw_feature_bc_matrix.h5",
        "raw_feature_bc_matrix",
    ):
        if (visium_dir / count_file).exists():
            return count_file
    return None


def is_visium_dir(path):
    path = Path(path)
    return (
        path.is_dir() and (path / "spatial").is_dir() and (get_visium_count_file(path) is not None)
    )


def find_visium_dir(root):
    root = Path(root)
    if is_visium_dir(root):
        return root
    for candidate in sorted(root.rglob("*")):
        if is_visium_dir(candidate):
            return candidate
    return None


def read_visium_anndata(visium_dir):
    visium_dir = Path(visium_dir)
    count_file = get_visium_count_file(visium_dir)
    if count_file is None:
        raise FileNotFoundError(
            "No Visium expression matrix found. Expected filtered_feature_bc_matrix.h5 or filtered_feature_bc_matrix/ under the Visium output directory."
        )
    if (visium_dir / count_file).is_dir():
        from cloud.portable_inputs import read_visium_mtx

        return compact_adata_X(read_visium_mtx(visium_dir, visium_dir / count_file))
    return compact_adata_X(sc.read_visium(str(visium_dir), count_file=count_file))


def find_example_st_h5ad(sample_name=EXAMPLE_SAMPLE_NAME):
    sample_dir = get_example_sample_dir(sample_name)
    search_roots = [get_example_st_dir(sample_name), sample_dir / "ST", sample_dir]
    for root in search_roots:
        if not root.exists():
            continue
        exact_path = root / EXAMPLE_ST_H5AD_NAME
        if exact_path.exists():
            return exact_path
        h5ad_files = sorted(root.glob("*.h5ad"))
        if h5ad_files:
            return h5ad_files[0]
    return None


def find_example_sm_h5ad(sample_name=EXAMPLE_SAMPLE_NAME):
    sample_dir = get_example_sample_dir(sample_name)
    search_roots = [get_example_sm_dir(sample_name), sample_dir / "SM", sample_dir]
    for root in search_roots:
        if not root.exists():
            continue
        exact_path = root / EXAMPLE_SM_H5AD_NAME
        if exact_path.exists():
            return exact_path
        h5ad_files = sorted(root.glob("*SM*.h5ad")) or sorted(root.glob("*.h5ad"))
        if h5ad_files:
            return h5ad_files[0]
    return None


def get_example_raw_h5ad_paths(sample_name=EXAMPLE_SAMPLE_NAME):
    st_path = find_example_st_h5ad(sample_name)
    sm_path = find_example_sm_h5ad(sample_name)
    missing = []
    if st_path is None:
        missing.append(EXAMPLE_ST_H5AD_NAME)
    if sm_path is None:
        missing.append(EXAMPLE_SM_H5AD_NAME)
    if missing:
        raise FileNotFoundError("Example raw h5ad file(s) were not found: " + ", ".join(missing))
    return (st_path, sm_path)


def get_example_st_qc_h5ad_path(sample_name=EXAMPLE_SAMPLE_NAME):
    path = get_example_sample_dir(sample_name) / "ST" / EXAMPLE_ST_QC_H5AD_NAME
    if not path.exists():
        raise FileNotFoundError(
            f"ST QC example h5ad was not found: {workspace_relative_path(path)}"
        )
    return path


def get_example_sm_qc_h5ad_path(sample_name=EXAMPLE_SAMPLE_NAME):
    path = get_example_sample_dir(sample_name) / "SM" / EXAMPLE_SM_QC_H5AD_NAME
    if path.exists():
        return path
    fallback = find_example_sm_h5ad(sample_name)
    if fallback is not None:
        return fallback
    raise FileNotFoundError(f"SM QC example h5ad was not found: {workspace_relative_path(path)}")


def get_example_knn_h5ad_paths(sample_name=EXAMPLE_SAMPLE_NAME):
    sample_dir = get_example_sample_dir(sample_name)
    st_path = sample_dir / "ST" / EXAMPLE_KNN_ST_H5AD_NAME
    sm_path = EXAMPLE_SM_BATCH_DIR / EXAMPLE_KNN_SM_H5AD_NAME
    missing = []
    if not st_path.exists():
        missing.append(workspace_relative_path(st_path))
    if not sm_path.exists():
        missing.append(workspace_relative_path(sm_path))
    if missing:
        raise FileNotFoundError("KNN example h5ad file(s) were not found: " + ", ".join(missing))
    return (st_path, sm_path)


def get_example_downstream_joint_h5ad_path():
    path = EXAMPLE_JOINT_BATCH_DIR / EXAMPLE_DOWNSTREAM_JOINT_H5AD_NAME
    if not path.exists():
        raise FileNotFoundError(
            f"Downstream example h5ad was not found: {workspace_relative_path(path)}"
        )
    return path


def find_example_st_visium_dir(sample_name=EXAMPLE_SAMPLE_NAME):
    for candidate in (
        get_example_st_raw_dir(sample_name),
        get_example_st_dir(sample_name),
        get_example_sample_dir(sample_name) / "ST",
    ):
        if not candidate.exists():
            continue
        visium_dir = find_visium_dir(candidate)
        if visium_dir is not None:
            return visium_dir
    return None


def read_example_st_anndata(sample_name=EXAMPLE_SAMPLE_NAME):
    visium_dir = find_example_st_visium_dir(sample_name)
    if visium_dir is not None:
        adata = read_visium_anndata(visium_dir)
        return (adata, visium_dir, "Visium folder")
    h5ad_path = find_example_st_h5ad(sample_name)
    if h5ad_path is not None:
        adata = compact_adata_X(smt.read_h5ad_st(str(h5ad_path)))
        return (adata, h5ad_path, "SpatialMeta h5ad")
    example_st_dir = get_example_st_raw_dir(sample_name)
    raise FileNotFoundError(
        f"Example ST data was not found. Expected either a complete Visium outs folder under {workspace_relative_path(example_st_dir)}, or a SpatialMeta ST h5ad file such as {EXAMPLE_ST_H5AD_NAME}."
    )


def extract_zip_safely(zip_path, extract_dir):
    from cloud.portable_inputs import extract_portable_zip

    return extract_portable_zip(zip_path, extract_dir)


def resolve_visium_upload_path(uploaded_path, work_dir):
    uploaded_path = Path(uploaded_path)
    work_dir = Path(work_dir)
    if uploaded_path.suffix.lower() == ".zip":
        extract_dir = work_dir / f"{uploaded_path.stem}_extracted"
        extract_zip_safely(uploaded_path, extract_dir)
        visium_dir = find_visium_dir(extract_dir)
        if visium_dir is None:
            raise FileNotFoundError(
                "The uploaded zip was extracted, but no complete Visium output directory was found. Please include the folder that contains spatial/ and filtered_feature_bc_matrix.h5 or filtered_feature_bc_matrix/."
            )
        return visium_dir
    if uploaded_path.is_dir():
        visium_dir = find_visium_dir(uploaded_path)
        if visium_dir is not None:
            return visium_dir
    raise FileNotFoundError(
        "Please upload a complete Visium output folder as a .zip archive. A single file cannot be loaded as ST data because Scanpy also needs the spatial/ folder."
    )


REMOTE_STSM_ALIGNMENT_PRE_SCRIPT = """
import argparse
import copy
import json
import traceback

import numpy as np
import scanpy as sc
import spatialmeta as smt


def normalize_non_inplace(adata):
    adata.layers["normalized"] = adata.X.astype("float32").copy() if hasattr(adata.X, "astype") else copy.deepcopy(adata.X)
    sc.pp.normalize_total(adata, layer="normalized")
    sc.pp.log1p(adata, layer="normalized")


def add_spatial_normalized(adata):
    # Standalone remote script: same definition as cloud.coordinate_guards;
    # no dependency on a platform module being installed on the SSH target.
    coords = np.asarray(adata.obsm["spatial"], dtype=np.float64)
    if coords.shape != (adata.n_obs, 2) or not np.isfinite(coords).all():
        raise ValueError("Spatial coordinates must be finite n_obs x 2 values.")
    ranges = np.ptp(coords, axis=0)
    if np.any(ranges <= 0):
        raise ValueError("Spatial coordinates have a degenerate axis.")
    xmin = float(coords[:, 0].min())
    adata.obsm["spatial_normalized"] = (coords - xmin) / float(ranges[0]) * 100
    adata.uns['spashiny_normalization_definition'] = 'spatialmeta_scalar_xmin_xspan_100_v1'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--st", required=True)
    parser.add_argument("--sm", required=True)
    parser.add_argument("--out-st", required=True)
    parser.add_argument("--out-sm", required=True)
    parser.add_argument("--meta", required=True)
    args = parser.parse_args()

    print("[REMOTE] Loading ST and SM h5ad files...", flush=True)
    adata_st = smt.read_h5ad_st(args.st)
    adata_sm = smt.read_h5ad_sm(args.sm)
    print(f"[REMOTE] ST shape: {adata_st.shape}", flush=True)
    print(f"[REMOTE] SM shape: {adata_sm.shape}", flush=True)

    print("[REMOTE] Running ST normalization and spatial variable selection...", flush=True)
    normalize_non_inplace(adata_st)
    smt.pp.spatial_variable(
        adata_st,
        n_top_variable=2000,
        add_key="highly_variable_moranI",
        layer="normalized",
    )
    st_mask = adata_st.var["highly_variable_moranI"].astype(bool).values
    adata_st = adata_st[:, st_mask].copy()
    add_spatial_normalized(adata_st)

    print("[REMOTE] Running SM normalization and spatial variable selection...", flush=True)
    sc.pp.normalize_total(adata_sm, target_sum=1e3)
    smt.pp.spatial_variable(
        adata_sm,
        n_top_variable=500,
        add_key="highly_variable_moranI",
    )
    sm_mask = adata_sm.var["highly_variable_moranI"].astype(bool).values
    adata_sm = adata_sm[:, sm_mask].copy()
    add_spatial_normalized(adata_sm)

    print("[REMOTE] Writing processed h5ad files...", flush=True)
    adata_st.write_h5ad(args.out_st)
    adata_sm.write_h5ad(args.out_sm)

    with open(args.meta, "w", encoding="utf-8") as f:
        json.dump(
            {
                "st_shape": list(adata_st.shape),
                "sm_shape": list(adata_sm.shape),
                "st_obsm_keys": list(adata_st.obsm.keys()),
                "sm_obsm_keys": list(adata_sm.obsm.keys()),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print("[REMOTE] ST-SM preprocessing completed.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
"""
REMOTE_STSM_KNN_SCRIPT = """
import argparse
import json
import traceback

import numpy as np
import scanpy as sc
import spatialmeta as smt


def ensure_total_counts(adata_st_new, adata_st):
    if "total_counts" not in adata_st.obs.columns:
        adata_st_new.obs["total_counts"] = np.ones(adata_st_new.n_obs)
        return "source_missing_total_counts"

    common_obs = adata_st_new.obs_names.intersection(adata_st.obs_names)
    if len(common_obs) > 0:
        adata_st_new.obs["total_counts"] = np.nan
        adata_st_new.obs.loc[common_obs, "total_counts"] = adata_st.obs.loc[common_obs, "total_counts"]
        if adata_st_new.obs["total_counts"].isna().any():
            valid_mean = adata_st_new.obs["total_counts"].dropna().mean()
            if np.isnan(valid_mean):
                valid_mean = 1.0
            adata_st_new.obs["total_counts"] = adata_st_new.obs["total_counts"].fillna(valid_mean)
        return f"matched_by_obs:{len(common_obs)}"

    from scipy.spatial import cKDTree

    original_coords = adata_st.obsm["spatial"]
    tree = cKDTree(original_coords)
    new_coords = adata_st_new.obsm["spatial"]
    distances, indices = tree.query(new_coords, k=1)
    adata_st_new.obs["total_counts"] = adata_st.obs.iloc[indices]["total_counts"].values
    return f"matched_by_spatial:mean_distance={float(np.mean(distances)):.4f}"


def recover_sm_metadata(adata_sm_new, adata_sm):
    common_obs_sm = adata_sm_new.obs_names.intersection(adata_sm.obs_names)
    recovered = []
    if len(common_obs_sm) > 0:
        for col in ["total_intensity", "mean_intensity"]:
            if col in adata_sm.obs.columns:
                adata_sm_new.obs[col] = np.nan
                adata_sm_new.obs.loc[common_obs_sm, col] = adata_sm.obs.loc[common_obs_sm, col]
                recovered.append(col)
    return recovered


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--st", required=True)
    parser.add_argument("--sm", required=True)
    parser.add_argument("--k", type=int, required=True)
    parser.add_argument("--dist-fold", type=float, required=True)
    parser.add_argument("--out-st", required=True)
    parser.add_argument("--out-sm", required=True)
    parser.add_argument("--meta", required=True)
    args = parser.parse_args()

    print("[REMOTE] Loading ST and SM h5ad files...", flush=True)
    adata_st = sc.read_h5ad(args.st)
    adata_sm = sc.read_h5ad(args.sm)
    print(f"[REMOTE] ST shape: {adata_st.shape}", flush=True)
    print(f"[REMOTE] SM shape: {adata_sm.shape}", flush=True)

    print("[REMOTE] Sampling ST spots and calculating minimum distance...", flush=True)
    st_dot_in_df = smt.pp.ST_spot_sample(adata_st, "spatial")
    min_dist = smt.pp.calculate_min_dist(adata_st)
    print(f"[REMOTE] min_dist={float(min_dist):.6f}", flush=True)

    print(
        f"[REMOTE] Running spot_align_byknn with k={args.k}, dist_fold={args.dist_fold}...",
        flush=True,
    )
    adata_sm_new, adata_st_new = smt.pp.spot_align_byknn(
        new_dot_in_df=st_dot_in_df,
        adata_SM=adata_sm,
        adata_ST=adata_st,
        min_dist=min_dist,
        n_neighbors=args.k,
        dist_fold=args.dist_fold,
    )

    total_counts_mode = ensure_total_counts(adata_st_new, adata_st)
    recovered_sm_columns = recover_sm_metadata(adata_sm_new, adata_sm)
    smt.pp.calculate_qc_metrics_sm(adata_sm_new)

    print("[REMOTE] Writing reassigned h5ad files...", flush=True)
    adata_st_new.write_h5ad(args.out_st)
    adata_sm_new.write_h5ad(args.out_sm)

    with open(args.meta, "w", encoding="utf-8") as f:
        json.dump(
            {
                "st_shape": list(adata_st_new.shape),
                "sm_shape": list(adata_sm_new.shape),
                "total_counts_mode": total_counts_mode,
                "recovered_sm_columns": recovered_sm_columns,
                "st_obsm_keys": list(adata_st_new.obsm.keys()),
                "sm_obsm_keys": list(adata_sm_new.obsm.keys()),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print("[REMOTE] KNN reassignment completed.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
"""
custom_css = """
<style>
.card-box { padding: 12px; border-radius: 8px; box-shadow: 0 2px 6px rgba(0,0,0,0.06); }
</style>
"""


def nav_btn(id, label, is_danger=False):
    css_class = "dropdown-item-btn " + ("dropdown-item-danger" if is_danger else "")
    return ui.tags.button(label, id=id, type="button", class_=css_class + " action-button")


def nav_dropdown(title, *items):
    return ui.tags.div(
        ui.tags.button(
            ui.tags.span(title, class_="menu-title"),
            ui.tags.span(">", class_="menu-caret"),
            type="button",
            class_="menu-trigger",
        ),
        ui.tags.div(*items, class_="menu-panel"),
        class_="menu-dropdown",
    )


def alignment_image_output_with_palette(output_id: str, *, height: str = "430px"):
    return ui.div(
        ui.div(
            ui.input_action_button(
                f"palette_{output_id}", "Adjust Colors", class_="btn btn-outline-secondary btn-sm"
            ),
            style="display:flex; justify-content:flex-end; margin:0 0 8px 0;",
        ),
        ui.div(
            ui.output_ui(f"{output_id}_img_ui"),
            id=output_id,
            class_="alignment-worker-image-slot",
            **{"data-plot-id": output_id, "data-height": height},
            style=f"width:100%; min-height:{height}; display:flex; align-items:center; justify-content:center; overflow:hidden; background:#fff; color:#64748B; text-align:center; padding:16px;",
        ),
        class_="plot-color-shell",
    )


def cloud_platform_ui(section="jobs"):
    from spashiny.features.workspace.ui import cloud_platform_ui as _export_impl

    return _export_impl(section)


top_nav_style_css = """
<style>
    body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        background: #f5f5f7;
        margin: 0;
    }

    .top-navbar {
        position: sticky;
        top: 0;
        z-index: 1200;
        width: 100%;
        background: #ffffff;
        border-bottom: 1px solid #e5e5e7;
        box-shadow: none;
        padding: 6px 22px;
        display: flex;
        align-items: center;
        gap: 0;
        flex-wrap: wrap;
    }

    .cloud-page-reset-note {
        max-width: 1280px;
        margin: 10px auto 0;
        padding: 10px 14px;
        border: 1px solid #fde68a;
        background: #fffbeb;
        color: #78350f;
        border-radius: 8px;
        font-size: 0.92rem;
        line-height: 1.55;
    }

    .cloud-top-status {
        max-width: 1280px;
        margin: 10px auto 0;
        padding: 0 12px;
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        align-items: center;
    }

    .cloud-status-pill {
        border: 1px solid #dbeafe;
        background: #eff6ff;
        color: #1d4ed8;
        border-radius: 8px;
        padding: 6px 10px;
        font-size: 0.88rem;
        font-weight: 650;
    }

    .cloud-status-pill.ok {
        border-color: #bbf7d0;
        background: #f0fdf4;
        color: #166534;
    }

    /* Left panel */
    .brand-block {
        display: flex;
        flex-direction: row;
        align-items: center;
        gap: 0;
        width: auto;
        min-width: unset;
        padding: 0;
        margin: 0;
        background: transparent;
        border: none;
        box-shadow: none;
        border-radius: 0;
        flex-shrink: 0;
    }

    /* When the entire left panel is a button */
    .brand-home-btn {
        appearance: none;
        -webkit-appearance: none;
        border: none;
        background: transparent;
        cursor: pointer;
    }

    .brand-home-btn:focus-visible {
        outline: none;
        box-shadow: none;
    }

    .brand-title {
        display: flex;
        align-items: center;
        height: 54px;
        padding: 0 22px 0 4px;
        margin: 0;
        background: transparent;
        border: none;
        border-radius: 0;
        box-shadow: none;
        color: #1d1d1f;
        font-size: 18px;
        font-weight: 700;
        letter-spacing: 0.04em;
        line-height: 1;
        white-space: nowrap;
        transition: color 0.18s ease;
    }

    .brand-image-box {
        height: 54px;
        padding: 0 22px;
        margin: 0;
        background: transparent;
        border: none;
        border-left: 1px solid #e5e5e7;
        border-radius: 0;
        box-shadow: none;
        overflow: visible;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
        transition: opacity 0.18s ease;
    }

    .brand-logo-img {
        height: 34px;
        width: auto;
        max-width: none;
        object-fit: contain;
        display: block;
    }

    .brand-block:hover .brand-title,
    .brand-home-btn:hover .brand-title {
        color: #007aff;
    }

    .brand-block:hover .brand-image-box,
    .brand-home-btn:hover .brand-image-box {
        opacity: 0.82;
    }

    /* Right menu area */
    .nav-menu-area {
        flex: 1 1 auto;
        min-width: 0;
        display: flex;
        align-items: center;
        justify-content: flex-start;
        gap: 0;
        flex-wrap: wrap;
    }

    .home-menu-btn {
        height: 54px;
        padding: 0 22px;
        margin: 0;
        border: none;
        border-left: 1px solid #e5e5e7;
        border-radius: 0;
        background: transparent;
        color: #1d1d1f;
        font-size: 17px;
        font-weight: 600;
        letter-spacing: 0.03em;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        transition: color 0.18s ease;
        box-shadow: none;
        white-space: nowrap;
    }

    .home-menu-btn:hover {
        background: transparent;
        color: #007aff;
        transform: none;
        box-shadow: none;
    }

    .home-menu-btn:focus-visible {
        outline: none;
        box-shadow: none;
    }

    .menu-dropdown {
        position: relative;
        display: flex;
        align-items: center;
        border-left: 1px solid #e5e5e7;
    }

    .menu-trigger {
        height: 54px;
        padding: 0 22px;
        margin: 0;
        border: none;
        border-radius: 0;
        background: transparent;
        color: #1d1d1f;
        font-size: 17px;
        font-weight: 600;
        letter-spacing: 0.03em;
        display: inline-flex;
        align-items: center;
        gap: 10px;
        cursor: pointer;
        transition: color 0.18s ease;
        box-shadow: none;
        white-space: nowrap;
    }

    .menu-trigger:hover {
        background: transparent;
        color: #007aff;
        transform: none;
        box-shadow: none;
    }

    .menu-dropdown.open .menu-trigger,
    .menu-dropdown:hover .menu-trigger {
        background: transparent;
        color: #007aff;
        border-color: transparent;
    }

    .menu-title {
        pointer-events: none;
    }

    .menu-caret {
        font-size: 13px;
        line-height: 1;
        transition: transform 0.18s ease;
        pointer-events: none;
        color: #8a8a8e;
    }

    .menu-dropdown.open .menu-caret,
    .menu-dropdown:hover .menu-caret {
        transform: rotate(180deg);
        color: #007aff;
    }

    /* Dropdown menu panel */
    .menu-panel {
        position: absolute;
        top: calc(100% + 8px);
        left: 12px;
        min-width: 260px;
        padding: 10px;
        border-radius: 14px;
        background: #ffffff;
        border: 1px solid #e5e5e7;
        box-shadow: 0 10px 24px rgba(0,0,0,0.08);
        opacity: 0;
        visibility: hidden;
        transform: translateY(8px);
        pointer-events: none;
        transition: all 0.18s ease;
        display: flex;
        flex-direction: column;
        gap: 4px;
    }

    .menu-dropdown:hover .menu-panel,
    .menu-dropdown.open .menu-panel {
        opacity: 1;
        visibility: visible;
        transform: translateY(0);
        pointer-events: auto;
    }

    .dropdown-item-btn {
        width: 100%;
        min-height: 38px;
        border: none;
        border-radius: 10px;
        background: transparent;
        color: #1d1d1f;
        font-size: 14px;
        font-weight: 500;
        letter-spacing: 0.01em;
        text-align: left;
        padding: 8px 12px;
        transition: all 0.16s ease;
        cursor: pointer;
    }

    .dropdown-item-btn:hover {
        background: #f5f5f7;
        color: #007aff;
        padding-left: 15px;
    }

    .dropdown-item-btn:focus-visible {
        outline: none;
        box-shadow: none;
    }

    .dropdown-item-btn.is-selected {
        background: #f2f7ff;
        color: #007aff;
        font-weight: 600;
    }

    .dropdown-item-danger {
        color: #ff3b30;
    }

    .dropdown-item-danger:hover {
        background: #fff5f4;
        color: #ff3b30;
    }

    .main-content {
        padding: 24px 32px;
    }

    .ssh-top-status {
        position: fixed;
        top: 74px;
        right: 24px;
        z-index: 1300;
        display: inline-flex;
        align-items: center;
        gap: 7px;
        max-width: min(420px, calc(100vw - 48px));
        padding: 8px 12px;
        border-radius: 999px;
        font-size: 13px;
        font-weight: 720;
        border: 1px solid #cbd5e1;
        color: #475569;
        background: rgba(248,250,252,0.96);
        box-shadow: 0 10px 24px rgba(15,23,42,0.12);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        pointer-events: none;
    }

    .ssh-top-status.connected {
        border-color: #a7f3d0;
        color: #047857;
        background: rgba(236,253,245,0.96);
    }

    .ssh-top-status.error {
        border-color: #fecaca;
        color: #b91c1c;
        background: rgba(254,242,242,0.96);
    }

    .ssh-top-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        flex: 0 0 auto;
        background: #94a3b8;
    }

    .ssh-top-status.connected .ssh-top-dot { background: #10b981; }
    .ssh-top-status.error .ssh-top-dot { background: #ef4444; }

    .ssh-top-status span:last-child {
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    @media (max-width: 1200px) {
        .top-navbar {
            padding: 6px 14px;
        }

        .nav-menu-area {
            width: 100%;
            justify-content: flex-start;
        }
    }

    /* Cloud-only navigation: one stable row, with the action kept separate. */
    .top-navbar { flex-wrap: nowrap; min-height: 66px; padding-right: 146px; }
    /* Dropdown panels must not be clipped by a scrolling ancestor. */
    .nav-menu-area { flex-wrap: nowrap; justify-content: flex-start; overflow: visible; }
    .brand-title { padding-right: 14px; font-size: 19px; letter-spacing: 0.02em; }
    .brand-image-box { padding: 0 14px; }
    .menu-trigger { padding: 0 16px; font-size: 15px; }
    .new-analysis-fab {
        position: fixed; top: 13px; right: 22px; z-index: 1400;
        min-height: 40px; padding: 0 16px; border: 0; border-radius: 999px;
        background: #0f6fff; color: #fff; font-weight: 700; box-shadow: 0 8px 20px rgba(15,111,255,.25);
    }
    .new-analysis-fab:hover { background: #075fdc; }

    @media (max-width: 768px) {
        .brand-title,
        .home-menu-btn,
        .menu-trigger {
            font-size: 15px;
            padding: 0 16px;
            height: 48px;
            letter-spacing: 0.025em;
        }

        .brand-image-box {
            height: 48px;
            padding: 0 16px;
        }

        .brand-logo-img {
            height: 28px;
        }

        .ssh-top-status {
            top: 64px;
            right: 12px;
            max-width: calc(100vw - 24px);
        }
        .top-navbar { padding-right: 116px; }
        .new-analysis-fab { top: 12px; right: 12px; min-height: 36px; padding: 0 12px; font-size: 13px; }
    }
</style>
"""


def cpu_enrichment_module_ui():
    from spashiny.features.enrichment.ui import cpu_enrichment_module_ui as _export_impl

    return _export_impl()


def spatialmeta_metabolite_annotation_module_ui():
    from spashiny.features.metabolite_annotation.ui import (
        spatialmeta_metabolite_annotation_module_ui as _export_impl,
    )

    return _export_impl()
