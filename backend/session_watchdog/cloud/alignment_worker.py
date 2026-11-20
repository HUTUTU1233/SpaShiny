from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import pickle
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any


STEP4_SAMPLING_STATE_SCHEMA = "spashiny.alignment.step4_sampling_state"
STEP4_SAMPLING_STATE_VERSION = 1
STEP4_SAMPLING_STATE_KEYS = (
    "spot_coordinate",
    "spot_coordinate_edge",
    "pointsI_edge",
    "initial_scale",
)


def _configure_illustrator_vector_output() -> None:
    """Embed editable text in vector artifacts without changing plot content."""
    import matplotlib

    matplotlib.rcParams["pdf.fonttype"] = 42
    matplotlib.rcParams["ps.fonttype"] = 42
    matplotlib.rcParams["svg.fonttype"] = "none"


def _coordinate_metadata(value: Any) -> dict[str, Any]:
    """Return compact, deterministic metadata without changing coordinates."""

    import numpy as np

    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    points = np.asarray(value)
    if points.ndim != 2 or points.shape[1] < 2:
        raise ValueError(f"Expected an Nx2 coordinate array, got {points.shape}")
    points = np.ascontiguousarray(points[:, :2])
    finite = np.isfinite(points).all(axis=1)
    if not finite.any():
        raise ValueError("Coordinate array has no finite rows")
    valid = points[finite]
    encoded = np.ascontiguousarray(points.astype(np.float32, copy=False)).tobytes()
    return {
        "shape": list(points.shape),
        "dtype": str(points.dtype),
        "x_range": [float(valid[:, 0].min()), float(valid[:, 0].max())],
        "y_range": [float(valid[:, 1].min()), float(valid[:, 1].max())],
        "sha256_f32": hashlib.sha256(encoded).hexdigest(),
    }


def _select_best_alignment_key(result_dict: dict[str, Any]) -> str:
    if not isinstance(result_dict, dict) or not result_dict:
        raise ValueError("fit_alignment returned an empty or invalid result")

    def score(key: str) -> float:
        value = result_dict.get(key) or {}
        loss = value.get("loss", []) if isinstance(value, dict) else []
        if not loss:
            return float("inf")
        try:
            return float(loss[-1])
        except Exception:
            return float("inf")

    return min(result_dict.keys(), key=score)


def _load_step4_fit_payload(source_output_dir: Path) -> dict[str, Any]:
    raster_path = source_output_dir / "raster_result.pkl"
    spot_path = source_output_dir / "spot_result.pkl"
    sampling_path = source_output_dir / "step4_sampling_state.pkl"
    if not raster_path.is_file() or not spot_path.is_file():
        raise FileNotFoundError("Completed Step4 raster/spot payloads are missing")
    with raster_path.open("rb") as handle:
        raster_result = pickle.load(handle)
    with spot_path.open("rb") as handle:
        spot_result = pickle.load(handle)
    raster_payload = raster_result.get("data", {}) if isinstance(raster_result, dict) else {}
    spot_payload = spot_result.get("data", {}) if isinstance(spot_result, dict) else {}
    if not isinstance(raster_payload, dict) or not isinstance(spot_payload, dict):
        raise ValueError("Step4 payloads do not contain data mappings")
    if sampling_path.is_file():
        with sampling_path.open("rb") as handle:
            sampling_state = pickle.load(handle)
        if not isinstance(sampling_state, dict) or sampling_state.get("schema") != STEP4_SAMPLING_STATE_SCHEMA:
            raise ValueError("Step4 sampling state schema is invalid")
        sampling_payload = sampling_state.get("data", {})
    else:
        # Old completed Step4 jobs stored the authoritative values in spot_result.
        sampling_payload = spot_payload
    if not isinstance(sampling_payload, dict):
        raise ValueError("Step4 sampling state data is invalid")
    missing = [key for key in STEP4_SAMPLING_STATE_KEYS if sampling_payload.get(key) is None]
    if missing:
        raise ValueError("Step4 sampling state is incomplete: " + ", ".join(missing))
    payload = dict(raster_payload)
    payload.update({key: sampling_payload[key] for key in STEP4_SAMPLING_STATE_KEYS})
    return {"data": payload}


def _json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")


def _read_status(job: dict[str, Any]) -> dict[str, Any]:
    try:
        path = Path(job["status_file"])
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _status(job: dict[str, Any], status: str, **updates: Any) -> None:
    payload = {
        "job_id": job.get("job_id", ""),
        "task": job.get("task", ""),
        "workflow_id": job.get("workflow_id"),
        "owner_id": job.get("owner_id"),
        "analysis_session_id": job.get("analysis_session_id"),
        "queue_class": job.get("queue_class"),
        "queue_name": job.get("queue_name"),
        "worker_id": job.get("worker_id") or os.environ.get("SPASHINY_WORKER_ID", ""),
        "created_at": job.get("created_at"),
        "status": status,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    payload.update(updates)
    _json(Path(job["status_file"]), payload)
    if status == "failed":
        _json(Path(job["output_dir"]) / "result_manifest.json", payload)


def _log(job: dict[str, Any], message: str) -> None:
    path = Path(job["log_file"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", errors="replace") as handle:
        handle.write(time.strftime("%Y-%m-%dT%H:%M:%S%z") + " " + str(message) + "\n")


def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(float(os.environ.get(name, "") or default)))
    except Exception:
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except Exception:
        return default


def _configure_runtime_limits(job: dict[str, Any]) -> None:
    """Limit native thread fan-out and optional process memory for worker safety."""

    threads = _int_env("SPASHINY_ALIGNMENT_WORKER_THREADS", _int_env("SPASHINY_CPU_CPUS_PER_JOB", 8))
    for name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ):
        os.environ.setdefault(name, str(threads))
    os.environ.setdefault("MALLOC_ARENA_MAX", "2")

    memory_gb = _float_env("SPASHINY_ALIGNMENT_MEMORY_LIMIT_GB", 0.0)
    if memory_gb > 0:
        try:
            import resource

            limit_bytes = int(memory_gb * 1024 * 1024 * 1024)
            soft, hard = resource.getrlimit(resource.RLIMIT_AS)
            new_hard = hard if hard not in (-1, resource.RLIM_INFINITY) else limit_bytes
            resource.setrlimit(resource.RLIMIT_AS, (min(limit_bytes, new_hard), new_hard))
        except Exception as exc:
            _log(job, f"warning: failed to apply memory limit {memory_gb} GiB: {exc}")

    try:
        import torch

        torch.set_num_threads(threads)
        torch.set_num_interop_threads(max(1, min(2, threads)))
    except RuntimeError:
        pass
    except Exception as exc:
        _log(job, f"warning: failed to apply torch thread limit: {exc}")

    _log(job, f"runtime limits: threads={threads} memory_gb={memory_gb or 'unlimited'}")


def _configure_matplotlib_fonts(job: dict[str, Any] | None = None) -> None:
    try:
        import logging
        import warnings
        import matplotlib
        from matplotlib import font_manager

        # SpatialMETA may create text objects with fontfamily="arial" even when
        # Arial is unavailable in the offline image. Keep the fallback visual
        # behavior, but stop Matplotlib font-manager from flooding worker logs.
        try:
            matplotlib.set_loglevel("error")
        except Exception:
            pass
        logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
        warnings.filterwarnings("ignore", message=r".*findfont: Font family.*")

        installed = {str(font.name).lower() for font in font_manager.fontManager.ttflist}
        preferred: list[str] = []
        if "arial" in installed:
            preferred.append("Arial")
        if "dejavu sans" in installed:
            preferred.append("DejaVu Sans")
        preferred.append("sans-serif")
        matplotlib.rcParams["font.family"] = preferred
        matplotlib.rcParams["font.sans-serif"] = [name for name in preferred if name != "sans-serif"] or ["DejaVu Sans"]
        if job is not None:
            _log(job, f"matplotlib font fallback: {preferred}")
    except Exception as exc:
        try:
            import matplotlib

            matplotlib.rcParams["font.family"] = ["DejaVu Sans", "sans-serif"]
            matplotlib.rcParams["font.sans-serif"] = ["DejaVu Sans"]
        except Exception:
            pass
        if job is not None:
            _log(job, f"warning: failed to configure matplotlib fonts: {exc}")


def _configure_library_compatibility(job: dict[str, Any]) -> None:
    _configure_matplotlib_fonts(job)
    try:
        from scipy.spatial import Delaunay

        if not hasattr(Delaunay, "vertices"):
            Delaunay.vertices = property(lambda self: self.simplices)  # type: ignore[attr-defined]
            _log(job, "compatibility: mapped scipy.spatial.Delaunay.vertices to simplices")
    except Exception as exc:
        _log(job, f"warning: failed to apply scipy Delaunay compatibility patch: {exc}")

    try:
        import numpy as np
        from scipy.spatial import ConvexHull
        import spatialmeta.model._alignment_model as alignment_module

        original_alpha_shape = getattr(alignment_module, "alpha_shape", None)
        if original_alpha_shape is not None and not getattr(original_alpha_shape, "_spashiny_safe_alpha_shape", False):

            def _convex_hull_edges(points: Any):
                pts = np.asarray(points, dtype=float)
                if pts.ndim != 2 or pts.shape[0] < 3 or pts.shape[1] < 2:
                    return np.empty((0, 2, 2), dtype=float)
                hull = ConvexHull(pts[:, :2])
                vertices = list(hull.vertices)
                edges = []
                for index, start in enumerate(vertices):
                    end = vertices[(index + 1) % len(vertices)]
                    edges.append((pts[[start, end], 0], pts[[start, end], 1]))
                return np.asarray(edges)

            def safe_alpha_shape(points: Any, alpha: float, only_outer: bool = True):
                try:
                    result = original_alpha_shape(points, alpha, only_outer=only_outer)
                    arr = np.asarray(result)
                    if arr.ndim == 3 and arr.shape[0] > 0:
                        return result
                    _log(job, f"compatibility: alpha_shape returned empty for alpha={alpha}; using ConvexHull fallback")
                except Exception as exc:
                    _log(job, f"compatibility: alpha_shape failed for alpha={alpha}; using ConvexHull fallback: {exc}")
                return _convex_hull_edges(points)

            safe_alpha_shape._spashiny_safe_alpha_shape = True  # type: ignore[attr-defined]
            alignment_module.alpha_shape = safe_alpha_shape
            _log(job, "compatibility: installed safe alpha_shape fallback")
    except Exception as exc:
        _log(job, f"warning: failed to apply alpha_shape compatibility patch: {exc}")


class _Heartbeat:
    def __init__(self, job: dict[str, Any], current_step: str, *, interval_seconds: float = 15.0) -> None:
        self.job = job
        self.current_step = current_step
        self.interval_seconds = max(1.0, float(interval_seconds))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self):
        def run() -> None:
            while not self._stop.wait(self.interval_seconds):
                try:
                    previous = _read_status(self.job)
                    preserved = {}
                    for key in (
                        "progress",
                        "alignment_iteration",
                        "alignment_total",
                        "elapsed_seconds",
                        "estimated_remaining_seconds",
                        "alignment_postfix",
                        "device",
                    ):
                        if key in previous:
                            preserved[key] = previous[key]
                    _status(
                        self.job,
                        "running",
                        current_step=previous.get("current_step") or self.current_step,
                        heartbeat_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                        **preserved,
                    )
                except Exception:
                    pass

        self._thread = threading.Thread(target=run, name="alignment-worker-heartbeat", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)


def _install_spatialmeta_fit_progress(job: dict[str, Any], *, total: int, device: str):
    """Bridge SpatialMETA's internal tqdm-style updates into status.json.

    SpatialMETA's fit_alignment API does not expose a callback, but its loop
    creates a tqdm object and calls update() once per iteration.  Replacing only
    that provider for this worker process gives the Shiny UI live Step5 progress
    without changing SpatialMETA source code, parameters, or return values.
    """

    try:
        import spatialmeta.model._alignment_model as alignment_module
    except Exception as exc:
        _log(job, f"warning: unable to install Step5 progress bridge: {exc}")
        return lambda: None

    original_get_tqdm = getattr(alignment_module, "get_tqdm", None)
    total = max(1, int(total or 1))

    class _StatusProgressBar:
        def __init__(self, iterable=None, *args, **kwargs) -> None:
            self.iterable = iterable
            try:
                self.total = int(kwargs.get("total") or len(iterable) or total)
            except Exception:
                self.total = total
            self.total = max(1, self.total)
            self.n = 0
            self.started = time.time()
            self._last_status_at = 0.0
            self._last_log_iter = -1
            self._postfix: dict[str, Any] = {}
            self._write(force=True)

        def __iter__(self):
            return iter(self.iterable or [])

        def set_postfix(self, ordered_dict=None, **kwargs) -> None:
            data: dict[str, Any] = {}
            if isinstance(ordered_dict, dict):
                data.update(ordered_dict)
            data.update(kwargs)
            clean: dict[str, Any] = {}
            for key, value in data.items():
                try:
                    clean[str(key)] = float(value)
                except Exception:
                    clean[str(key)] = str(value)
            self._postfix = clean

        def update(self, n: int = 1) -> None:
            try:
                self.n += int(n or 1)
            except Exception:
                self.n += 1
            now = time.time()
            if now - self._last_status_at >= 2.0 or self.n >= self.total:
                self._write(now=now)

        def close(self) -> None:
            self._write(force=True)

        def _write(self, *, now: float | None = None, force: bool = False) -> None:
            now = time.time() if now is None else now
            if not force and now - self._last_status_at < 2.0 and self.n < self.total:
                return
            self._last_status_at = now
            elapsed = max(0.0, now - self.started)
            fraction = min(1.0, max(0.0, self.n / max(self.total, 1)))
            remaining = None
            if self.n > 0 and self.n < self.total:
                remaining = (elapsed / max(self.n, 1)) * (self.total - self.n)
            progress = min(99.0, 10.0 + 85.0 * fraction)
            _status(
                job,
                "running",
                current_step=f"fitting alignment iteration {self.n}/{self.total}",
                progress=round(progress, 2),
                device=device,
                alignment_iteration=int(self.n),
                alignment_total=int(self.total),
                elapsed_seconds=round(elapsed, 1),
                estimated_remaining_seconds=None if remaining is None else round(float(remaining), 1),
                alignment_postfix=self._postfix,
            )
            if force or self.n == 1 or self.n >= self.total or self.n % 10 == 0:
                if self.n != self._last_log_iter:
                    self._last_log_iter = self.n
                    _log(
                        job,
                        f"Step5 progress: iteration {self.n}/{self.total} "
                        f"({progress:.1f}%) elapsed={elapsed:.1f}s"
                        + ("" if remaining is None else f" remaining~{remaining:.1f}s")
                        + ("" if not self._postfix else " metrics=" + json.dumps(self._postfix, sort_keys=True)),
                    )

    def get_tqdm():
        return _StatusProgressBar

    alignment_module.get_tqdm = get_tqdm

    def restore() -> None:
        try:
            if original_get_tqdm is not None:
                alignment_module.get_tqdm = original_get_tqdm
        except Exception:
            pass

    _log(job, f"Step5 progress bridge installed: total_iterations={total}")
    return restore


def _alignment_seed(job: dict[str, Any]) -> int:
    """Use one explicit, persisted seed for every AlignmentVAE worker task."""
    config = dict(job.get("model_config") or {})
    raw = job.get("random_seed", config.get("random_seed", config.get("seed", 42)))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 42


def _sha256_file(path: str | Path) -> str | None:
    candidate = Path(path)
    if not candidate.is_file():
        return None
    digest = hashlib.sha256()
    with candidate.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _alignment_provenance(job: dict[str, Any], device: str) -> dict[str, Any]:
    try:
        from importlib.metadata import version
        spatialmeta_version = version("spatialmeta")
    except Exception:
        spatialmeta_version = "unknown"
    return {
        "random_seed": _alignment_seed(job),
        "input_files": {
            "st_h5ad": {"path": str(job.get("st_h5ad") or ""), "sha256": _sha256_file(str(job.get("st_h5ad") or ""))},
            "sm_h5ad": {"path": str(job.get("sm_h5ad") or ""), "sha256": _sha256_file(str(job.get("sm_h5ad") or ""))},
        },
        "spatialmeta_version": spatialmeta_version,
        "spashiny_release_version": str(os.environ.get("SPASHINY_RELEASE_VERSION") or "unknown"),
        "python_version": sys.version.split()[0],
        "device": device,
    }


def _set_alignment_seed(torch: Any, seed: int) -> None:
    import numpy as np
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    try:
        torch.use_deterministic_algorithms(True, warn_only=True)
    except Exception:
        pass


def _device(job: dict[str, Any]) -> str:
    requested = str(job.get("device") or "cpu")
    if requested.startswith("cuda"):
        try:
            import torch

            if torch.cuda.is_available():
                return requested
        except Exception:
            pass
    return "cpu"


def _read_h5ad(path: str, *, modality: str):
    import spatialmeta as smt

    if modality == "st":
        return smt.read_h5ad_st(str(path))
    return smt.read_h5ad_sm(str(path))


def _alignment_model(job: dict[str, Any], *, load_state: bool):
    import torch
    from spatialmeta.model._alignment_model import AlignmentVAE

    device = _device(job)
    config = dict(job.get("model_config") or {})
    seed = _alignment_seed(job)
    _set_alignment_seed(torch, seed)
    config.setdefault("random_seed", seed)
    adata_st = _read_h5ad(str(job["st_h5ad"]), modality="st")
    adata_sm = _read_h5ad(str(job["sm_h5ad"]), modality="sm")
    model = AlignmentVAE(
        adata_st=adata_st,
        adata_sm=adata_sm,
        hidden_stacks=config.get("hidden_stacks", [128]),
        n_latent=int(config.get("n_latent", 10)),
        device=device,
        reconstruction_method_st=config.get("reconstruction_method_st", "zinb"),
        reconstruction_method_sm=config.get("reconstruction_method_sm", "g"),
        encode_libsize=bool(config.get("encode_libsize", False)),
    )
    if load_state:
        state_path = Path(str(job.get("state_dict") or ""))
        if not state_path.is_file():
            raise FileNotFoundError(f"AlignmentVAE state_dict not found: {state_path}")
        try:
            state = torch.load(state_path, map_location=device, weights_only=True)
        except TypeError:
            state = torch.load(state_path, map_location=device)
        model.load_state_dict(state, strict=True)
        model.eval()
    return model, device


def _to_numpy(value: Any):
    import numpy as np

    if value is None:
        return None
    if hasattr(value, "detach"):
        return value.detach().cpu().numpy()
    return np.asarray(value)


def _normalize(arr: Any):
    import numpy as np

    out = np.asarray(arr, dtype=float)
    out = out - np.nanmin(out)
    maxv = np.nanmax(out)
    if maxv > 0:
        out = out / maxv
    return out


def _alignment_colormaps():
    from matplotlib.colors import LinearSegmentedColormap

    return {
        "sm_raster": LinearSegmentedColormap.from_list(
            "sm_raster_cmap",
            ["#9F66BE", "#379155", "#8de9ac", "#84d43e"],
        ),
        "tissue": LinearSegmentedColormap.from_list(
            "tissue_cmap",
            ["#fff8f4", "#f7d9cf", "#eab7a8", "#d89c8a", "#b87c70"],
        ),
        "st_latent": LinearSegmentedColormap.from_list(
            "st_latent_cmap",
            ["#7B2F92", "#b699db", "#d6c9e6", "#f9f4fa"],
        ),
    }


def _clean_panel_colorbar(fig: Any, mappable: Any, ax: Any) -> Any:
    cbar = fig.colorbar(mappable, ax=ax, fraction=0.046, pad=0.03, shrink=0.88)
    cbar.set_ticks([])
    cbar.outline.set_visible(False)
    return cbar


def _style_alignment_panel(ax: Any, title: str) -> None:
    ax.set_title(title, fontsize=9, fontweight="normal", pad=6, loc="left")
    ax.tick_params(axis="both", which="both", labelsize=7, length=2.2, width=0.7, pad=1.5)
    ax.locator_params(nbins=4)
    for spine in ax.spines.values():
        spine.set_linewidth(0.7)
        spine.set_edgecolor("#666666")


def _ensure_app_import_path() -> None:
    app_dir = Path(__file__).resolve().parents[1] / "app"
    if app_dir.is_dir() and str(app_dir) not in sys.path:
        sys.path.insert(0, str(app_dir))


def _extract_worker_color_spec(fig: Any) -> dict[str, Any]:
    try:
        _ensure_app_import_path()
        from plot_color_tools import extract_color_spec_from_figure

        spec = extract_color_spec_from_figure(fig)
        return spec if isinstance(spec, dict) else {"colors": [], "colormap": None}
    except Exception:
        return {"colors": [], "colormap": None}


def _apply_worker_color_settings(fig: Any, spec: dict[str, Any], settings: dict[str, Any] | None) -> Any:
    if not settings:
        return fig
    try:
        _ensure_app_import_path()
        from plot_color_tools import apply_color_settings_to_figure

        return apply_color_settings_to_figure(fig, settings, spec) or fig
    except Exception:
        return fig


def _plot_manifest_item(
    *,
    name: str,
    path: Path,
    output_dir: Path,
    group: str,
    plot_id: str,
    panel: str | None = None,
    preview_kind: str | None = None,
    color_spec: dict[str, Any] | None = None,
    color_parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "name": name,
        "group": group,
        "plot_id": plot_id,
        "path": path.relative_to(output_dir).as_posix(),
        "color_spec": color_spec or {"colors": [], "colormap": None},
        "color_parameters": color_parameters or {},
    }
    # A companion PDF is generated from the same live Matplotlib Figure, not
    # converted from the PNG.  Illustrator can therefore edit vector marks and
    # embedded text; image-array layers remain raster where scientifically
    # required.
    vector_path = path.with_suffix(".pdf")
    if vector_path.is_file():
        item["editable_pdf_path"] = vector_path.relative_to(output_dir).as_posix()
    if panel:
        item["panel"] = panel
    if preview_kind:
        item["preview_kind"] = preview_kind
    return item


def _mean_image(value: Any) -> Any:
    import numpy as np

    arr = _to_numpy(value)
    if arr is None:
        return None
    if arr.ndim >= 3:
        return arr.mean(axis=0)
    return arr


def _save_figure(fig: Any, path: Path, *, dpi: int = 180) -> None:
    import matplotlib.pyplot as plt

    _configure_illustrator_vector_output()
    fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")
    if path.suffix.lower() == ".png":
        fig.savefig(path.with_suffix(".pdf"), format="pdf", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _raster_panel_figure(raster_result: dict[str, Any], panel: str) -> Any:
    import matplotlib.pyplot as plt
    import numpy as np

    data = raster_result.get("data", {}) if isinstance(raster_result, dict) else {}
    I = data.get("I")
    J = data.get("J")
    G = data.get("G")
    z_sm = _to_numpy(data.get("z_sm"))
    x_sm = _to_numpy(data.get("x_sm"))
    y_sm = _to_numpy(data.get("y_sm"))
    if I is None or J is None or G is None:
        raise ValueError("Raster result is missing required keys: I / J / G")

    I_np = _normalize(_mean_image(I))
    J_np = _normalize(_mean_image(J))
    G_np = _normalize(_mean_image(G))
    cmaps = _alignment_colormaps()

    fig, ax = plt.subplots(figsize=(6.4, 5.0), dpi=180)
    fig.patch.set_facecolor("white")

    if panel == "sm_feature":
        im = ax.imshow(I_np, cmap=cmaps["sm_raster"], origin="upper")
        _style_alignment_panel(ax, "SM rasterized feature")
        _clean_panel_colorbar(fig, im, ax)
    elif panel == "sm_latent":
        if z_sm is not None and x_sm is not None and y_sm is not None:
            values = np.mean(z_sm, axis=1) if len(z_sm.shape) > 1 else z_sm
            values = _normalize(values)
            sc = ax.scatter(
                x_sm,
                y_sm,
                c=values,
                s=5.2,
                cmap=cmaps["sm_raster"],
                alpha=0.95,
                linewidths=0,
                rasterized=True,
            )
            _clean_panel_colorbar(fig, sc, ax)
        else:
            ax.text(0.5, 0.5, "latent feature unavailable", ha="center", va="center", fontsize=9)
        _style_alignment_panel(ax, "SM latent embedding")
        ax.set_xlabel("SM x", fontsize=8)
        ax.set_ylabel("SM y", fontsize=8)
    elif panel == "st_image":
        im = ax.imshow(J_np, cmap=cmaps["tissue"], origin="upper")
        _style_alignment_panel(ax, "ST spatial image")
        _clean_panel_colorbar(fig, im, ax)
    elif panel == "st_latent":
        im = ax.imshow(G_np, cmap=cmaps["st_latent"], origin="upper")
        _style_alignment_panel(ax, "ST latent feature")
        _clean_panel_colorbar(fig, im, ax)
    else:
        raise ValueError(f"Unknown raster panel: {panel}")

    ax.set_aspect("equal", adjustable="box")
    fig.tight_layout(pad=1.0)
    return fig


def _spot_panel_figure(result_dict: dict[str, Any], panel: str, raster_result: dict[str, Any] | None = None) -> Any:
    import matplotlib.pyplot as plt
    import numpy as np

    data = {}
    if isinstance(raster_result, dict):
        data.update(raster_result.get("data", {}) or {})
    if isinstance(result_dict, dict):
        data.update(result_dict.get("data", {}) or {})
    J = data.get("J")
    maskJ = data.get("maskJ")
    z_st = data.get("z_st")
    spot_coordinate = data.get("spot_coordinate")
    scale = data.get("scale")
    x_st = data.get("x_st")
    y_st = data.get("y_st")
    st_spatial = data.get("st_spatial")

    if J is None or spot_coordinate is None:
        raise ValueError("Spot result is missing required keys: J / spot_coordinate")

    J_arr = _to_numpy(J)
    J_np = J_arr[0] if getattr(J_arr, "ndim", 0) >= 3 else J_arr
    J_np = _normalize(J_np)
    maskJ_np = _to_numpy(maskJ) if maskJ is not None else None
    z_st_np = _to_numpy(z_st) if z_st is not None else None
    z_st_color = np.mean(z_st_np, axis=1) if z_st_np is not None and len(z_st_np.shape) > 1 else z_st_np
    spot_np = _to_numpy(spot_coordinate)
    x_st_np = _to_numpy(x_st) if x_st is not None else None
    y_st_np = _to_numpy(y_st) if y_st is not None else None
    if (x_st_np is None or y_st_np is None) and st_spatial is not None:
        spatial = _to_numpy(st_spatial)
        if spatial is not None and getattr(spatial, "ndim", 0) == 2 and spatial.shape[1] >= 2:
            factor = float(scale or 1.0)
            x_st_np = spatial[:, 0] * factor
            y_st_np = spatial[:, 1] * factor

    try:
        if maskJ_np is not None:
            mask_source = maskJ_np.T if maskJ_np.T.shape == J_np.shape else maskJ_np
            tissue_mean = J_np[mask_source > 0].mean()
        else:
            tissue_mean = np.nanmean(J_np)
        Jtrue = (J_np <= tissue_mean * 0.65).astype(float)
    except Exception:
        Jtrue = None

    cmaps = _alignment_colormaps()
    fig, ax = plt.subplots(figsize=(6.0, 5.2), dpi=180)
    fig.patch.set_facecolor("white")

    if panel == "st_latent":
        ax.imshow(J_np, cmap=cmaps["tissue"], origin="upper")
        if x_st_np is not None and y_st_np is not None and z_st_color is not None:
            ax.scatter(
                x_st_np,
                y_st_np,
                s=5,
                lw=0,
                c=z_st_color,
                cmap="magma",
                alpha=0.78,
                marker="s",
                rasterized=True,
            )
        if maskJ_np is not None:
            overlay = maskJ_np.T if maskJ_np.T.shape == J_np.shape else maskJ_np
            ax.imshow(overlay, alpha=0.12, cmap="Greys", origin="upper")
        _style_alignment_panel(ax, "ST tissue and latent structure")
    elif panel == "sampled":
        ax.imshow(J_np, cmap=cmaps["tissue"], origin="upper")
        ax.scatter(
            spot_np[:, 0],
            spot_np[:, 1],
            s=8,
            lw=0,
            c="#f8f8f8",
            alpha=0.96,
            edgecolors="none",
            rasterized=True,
        )
        _style_alignment_panel(ax, "Randomly sampled inside-tissue spots")
        ax.set_xlim(0, J_np.shape[1])
        ax.set_ylim(J_np.shape[0], 0)
    elif panel == "mask":
        ax.imshow(Jtrue if Jtrue is not None else J_np, cmap="gray", origin="upper")
        _style_alignment_panel(ax, "Binary tissue mask")
    else:
        raise ValueError(f"Unknown spot panel: {panel}")

    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("image x", fontsize=8)
    ax.set_ylabel("image y", fontsize=8)
    fig.tight_layout()
    return fig


def _save_raster_plots(
    raster_result: dict[str, Any],
    plots_dir: Path,
    *,
    color_settings_by_plot: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plots_dir.mkdir(parents=True, exist_ok=True)
    output_dir = plots_dir.parent
    outputs: list[dict[str, Any]] = []
    panel_specs = [
        ("sm_feature", "raster_panel_sm_feature", "SM rasterized feature", "sm_rasterized_feature.png"),
        ("sm_latent", "raster_panel_sm_latent", "SM latent embedding", "sm_latent_embedding.png"),
        ("st_image", "raster_panel_st_image", "ST spatial image", "st_spatial_image.png"),
        ("st_latent", "raster_panel_st_latent", "ST latent feature", "st_latent_feature.png"),
    ]
    color_settings_by_plot = color_settings_by_plot or {}
    for panel, plot_id, name, filename in panel_specs:
        fig = _raster_panel_figure(raster_result, panel)
        color_spec = _extract_worker_color_spec(fig)
        color_parameters = dict(color_settings_by_plot.get(plot_id) or {})
        fig = _apply_worker_color_settings(fig, color_spec, color_parameters)
        path = plots_dir / filename
        _save_figure(fig, path, dpi=180)
        outputs.append(_plot_manifest_item(
            name=name,
            path=path,
            output_dir=output_dir,
            group="raster",
            panel=panel,
            plot_id=plot_id,
            color_spec=color_spec,
            color_parameters=color_parameters,
        ))

    fig, axes = plt.subplots(2, 2, figsize=(11, 9), dpi=160)
    axes = axes.ravel()
    for ax, (_panel, _plot_id, _name, filename) in zip(axes, panel_specs):
        import matplotlib.image as mpimg

        ax.imshow(mpimg.imread(plots_dir / filename))
        ax.axis("off")
    fig.tight_layout(pad=0.3)
    combined = plots_dir / "alignment_raster_panels.png"
    # This convenience composite intentionally remains a PNG: it is assembled
    # from preview rasters.  The individual panel PDFs above are the editable
    # Illustrator exports from the original plotting figures.
    fig.savefig(combined, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    outputs.append({
        "name": "Alignment raster panels",
        "group": "raster_combined",
        "plot_id": "raster_plot",
        "path": combined.relative_to(output_dir).as_posix(),
    })
    return outputs


def _save_spot_plot(
    result_dict: dict[str, Any],
    plots_dir: Path,
    raster_result: dict[str, Any] | None = None,
    *,
    color_settings_by_plot: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plots_dir.mkdir(parents=True, exist_ok=True)
    output_dir = plots_dir.parent
    outputs: list[dict[str, Any]] = []
    panel_specs = [
        ("st_latent", "spot_panel_st_latent", "ST tissue and latent structure", "st_tissue_latent_structure.png"),
        ("sampled", "spot_panel_sampled", "Randomly sampled inside-tissue spots", "sampled_inside_tissue_spots.png"),
        ("mask", "spot_panel_mask", "Binary tissue mask", "binary_tissue_mask.png"),
    ]
    color_settings_by_plot = color_settings_by_plot or {}
    for panel, plot_id, name, filename in panel_specs:
        fig = _spot_panel_figure(result_dict, panel, raster_result)
        color_spec = _extract_worker_color_spec(fig)
        color_parameters = dict(color_settings_by_plot.get(plot_id) or {})
        fig = _apply_worker_color_settings(fig, color_spec, color_parameters)
        path = plots_dir / filename
        _save_figure(fig, path, dpi=180)
        outputs.append(_plot_manifest_item(
            name=name,
            path=path,
            output_dir=output_dir,
            group="spot",
            panel=panel,
            plot_id=plot_id,
            color_spec=color_spec,
            color_parameters=color_parameters,
        ))

    fig, axes = plt.subplots(1, 3, figsize=(14, 4.8), dpi=160)
    for ax, (_panel, _plot_id, _name, filename) in zip(axes, panel_specs):
        import matplotlib.image as mpimg

        ax.imshow(mpimg.imread(plots_dir / filename))
        ax.axis("off")
    fig.tight_layout(pad=0.3)
    combined = plots_dir / "alignment_spot_panels.png"
    # Keep the raster convenience composite separate from the per-panel vector
    # PDFs generated from the original figures.
    fig.savefig(combined, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    outputs.append({
        "name": "Alignment spot panels",
        "group": "spot_combined",
        "plot_id": "spot_only_plot",
        "path": combined.relative_to(output_dir).as_posix(),
    })
    return outputs


def _save_render_pdf(output_dir: Path, plots: list[dict[str, str]]) -> dict[str, str] | None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.image as mpimg
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    ordered = [
        item for item in plots
        if item.get("group") in {"raster", "spot"}
        and str(item.get("path") or "").lower().endswith(".png")
    ]
    if not ordered:
        return None
    pdf_path = output_dir / "plots" / "raster_and_spot.pdf"
    with PdfPages(pdf_path) as pdf:
        for item in ordered:
            path = output_dir / str(item.get("path") or "")
            if not path.is_file():
                continue
            img = mpimg.imread(path)
            h, w = img.shape[:2]
            fig_w = 7.0 if h >= w else 9.0
            fig_h = max(4.0, min(8.0, fig_w * h / max(w, 1)))
            fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=180)
            ax.imshow(img)
            ax.axis("off")
            fig.tight_layout(pad=0.2)
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)
    return {
        "name": "Raster and spot PDF",
        "path": pdf_path.relative_to(output_dir).as_posix(),
    }


def _raster_grid_size(x_values: Any, y_values: Any, *, dx: float, expand: float) -> tuple[int, int, int]:
    import numpy as np

    x_arr = np.asarray(x_values, dtype=float)
    y_arr = np.asarray(y_values, dtype=float)
    minx = float(np.min(x_arr))
    maxx = float(np.max(x_arr))
    miny = float(np.min(y_arr))
    maxy = float(np.max(y_arr))
    minx, maxx = (minx + maxx) / 2.0 - (maxx - minx) / 2.0 * expand, (minx + maxx) / 2.0 + (maxx - minx) / 2.0 * expand
    miny, maxy = (miny + maxy) / 2.0 - (maxy - miny) / 2.0 * expand, (miny + maxy) / 2.0 + (maxy - miny) / 2.0 * expand
    nx = max(1, int(np.ceil(max(0.0, maxx - minx) / dx)))
    ny = max(1, int(np.ceil(max(0.0, maxy - miny) / dx)))
    return nx, ny, nx * ny


def _bounded_raster_dx(job: dict[str, Any], x_values: Any, y_values: Any, *, requested_dx: float, expand: float) -> float:
    import math

    max_pixels = int(job.get("max_raster_cells") or os.environ.get("SPASHINY_ALIGNMENT_MAX_RASTER_PIXELS") or 1500000)
    dx = max(1e-6, float(requested_dx))
    if max_pixels <= 0:
        return dx
    nx, ny, pixels = _raster_grid_size(x_values, y_values, dx=dx, expand=expand)
    if pixels <= max_pixels:
        _log(job, f"raster grid accepted: dx={dx} nx={nx} ny={ny} pixels={pixels} limit={max_pixels}")
        return dx
    adjusted = dx * math.sqrt(float(pixels) / float(max_pixels))
    for _ in range(8):
        nx, ny, pixels = _raster_grid_size(x_values, y_values, dx=adjusted, expand=expand)
        if pixels <= max_pixels:
            break
        adjusted *= 1.05
    _log(job, f"raster grid adjusted: requested_dx={dx} effective_dx={adjusted} nx={nx} ny={ny} pixels={pixels} limit={max_pixels}")
    return adjusted


def _get_rasterized_feature_map_with_limits(model: Any, job: dict[str, Any]) -> dict[str, Any]:
    import einops
    import numpy as np
    import torch
    from sklearn.neighbors import NearestNeighbors
    from spatialmeta.external.stalign.STalign import rasterize_with_signal
    from spatialmeta.plotting._plotting import create_subplots
    from spatialmeta.plotting._utils import get_spatial_image

    adata_st = model.adata_st
    adata_sm = model.adata_sm
    J, scale = get_spatial_image(adata_st)
    x_st, y_st = model.st_spatial_coord[:, 0] * scale, model.st_spatial_coord[:, 1] * scale
    x_sm, y_sm = model.sm_spatial_coord[:, 0], model.sm_spatial_coord[:, 1]
    z_st, z_sm = model.get_latent_embedding(latent_key="q_mu")
    requested_dx = float(job.get("raster_dx") or os.environ.get("SPASHINY_ALIGNMENT_RASTER_DX") or 0.4)
    blur = float(job.get("raster_blur") or os.environ.get("SPASHINY_ALIGNMENT_RASTER_BLUR") or 0.01)
    expand = float(job.get("raster_expand") or os.environ.get("SPASHINY_ALIGNMENT_RASTER_EXPAND") or 1.1)
    effective_dx = _bounded_raster_dx(job, x_sm, y_sm, requested_dx=requested_dx, expand=expand)
    output_sm = rasterize_with_signal(x_sm, y_sm, z_sm, dx=effective_dx, blur=blur, expand=expand)

    xJ = [
        torch.arange(J.shape[1], device=model.device),
        torch.arange(J.shape[0], device=model.device),
    ]
    xI = [
        torch.tensor(output_sm[0], device=model.device),
        torch.tensor(output_sm[1], device=model.device),
    ]
    I = (
        torch.nn.functional.normalize(
            torch.tensor(output_sm[2], dtype=torch.float32, device=model.device),
            p=2.0,
            dim=0,
        )
        * 100
    )

    pointsI = torch.tensor(np.vstack([x_sm, y_sm]).T, dtype=torch.float32)
    pointsJ = torch.tensor(np.vstack([x_st, y_st]).T, dtype=torch.float32)
    maskI = torch.from_numpy(model.inside_delaunay_mask([xI[0].detach().cpu().numpy(), xI[1].detach().cpu().numpy()], pointsI)).to(model.device)
    maskJ = torch.from_numpy(model.inside_delaunay_mask([xJ[0].detach().cpu().numpy(), xJ[1].detach().cpu().numpy()], pointsJ)).to(model.device)
    pointsI = pointsI.to(model.device)
    pointsJ = pointsJ.to(model.device)
    J = J / 255
    J = torch.tensor(np.dot(J[..., :3], [0.2989, 0.5870, 0.1140]))
    J = J.unsqueeze(0)
    J = J.to(torch.float32).to(model.device)

    coordinates = np.indices(np.array(J.shape)[[2, 1]]).transpose(2, 1, 0)
    coordinates_flat = einops.rearrange(coordinates, "a b c -> (a b) c")

    neighbors = NearestNeighbors(n_neighbors=1)
    neighbors.fit(model.st_spatial_coord * scale)
    distances, indices = neighbors.kneighbors(coordinates_flat)

    G = einops.rearrange(z_st[indices.flatten()], "(w h) c-> h w c", w=J.shape[-2], h=J.shape[-1])
    maskJ = einops.rearrange(distances > 10, "(w h) c-> h w c", w=J.shape[-2], h=J.shape[-1])[:, :, 0]
    G[maskJ] = 0
    maskJ = torch.from_numpy(maskJ).to(model.device)

    G = torch.from_numpy(G).to(model.device)
    G = einops.rearrange(G, "w h c -> c h w")

    fig, axes = create_subplots(2, 2, figsize=(10, 10))
    axes = axes.flatten()
    axes[0].imshow(I.mean(0).detach().cpu().numpy())
    axes[0].set_title("SM rasterized latent feature")
    axes[1].scatter(
        adata_sm.obsm["spatial"][:, 0],
        -adata_sm.obsm["spatial"][:, 1],
        c=z_sm.mean(-1),
        s=0.7,
    )
    axes[1].set_title("SM latent feature")
    axes[2].imshow(J.mean(0).detach().cpu().numpy())
    axes[2].set_title("ST spatial image")
    axes[3].imshow(G.detach().cpu().numpy().mean(0))
    axes[3].set_title("ST latent feature")

    return {
        "data": {
            "I": I,
            "J": J,
            "G": G,
            "maskI": maskI,
            "maskJ": maskJ,
            "pointsI": pointsI,
            "pointsJ": pointsJ,
            "z_st": z_st,
            "z_sm": z_sm,
            "x_st": x_st,
            "y_st": y_st,
            "x_sm": x_sm,
            "y_sm": y_sm,
            "scale": scale,
            "xI": xI,
            "xJ": xJ,
            "requested_dx": requested_dx,
            "effective_dx": effective_dx,
        },
        "fig": {
            "feature": fig,
        },
    }


def _sample_xy(xy: Any, max_points: int) -> Any:
    import numpy as np

    arr = np.asarray(xy, dtype=float)
    if arr.ndim != 2 or arr.shape[1] < 2:
        return arr[:, :2] if arr.ndim == 2 else arr
    arr = arr[:, :2]
    good = np.isfinite(arr).all(axis=1)
    arr = arr[good]
    if arr.shape[0] > max_points:
        index = np.linspace(0, arr.shape[0] - 1, max_points, dtype=int)
        arr = arr[index]
    return arr


def _manual_preview(job: dict[str, Any]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    matplotlib.rcParams["pdf.fonttype"] = 42
    matplotlib.rcParams["ps.fonttype"] = 42
    import matplotlib.pyplot as plt
    import spatialmeta as smt
    from matplotlib.backends.backend_pdf import PdfPages

    _configure_matplotlib_fonts(job)
    output_dir = Path(job["output_dir"])
    plots_dir = output_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    _status(job, "running", current_step="loading preview inputs", started_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"))

    ad_st = smt.read_h5ad_st(str(job["st_h5ad"]))
    ad_sm_source = smt.read_h5ad_sm(str(job["sm_h5ad"]))
    source_coordinates = ad_sm_source.obsm["spatial"].copy()
    transform = dict(job.get("transform") or {})
    kind = str(job.get("preview_kind") or transform.get("mode") or "overlay").lower()

    def _default_transform(render_kind: str) -> dict[str, Any]:
        if render_kind == "initial":
            return {
                "rotation": 0.0,
                "horizontal_flip": False,
                "vertical_flip": False,
                "scale_width": None,
                "scale_height": None,
                "translation_x": 0.0,
                "translation_y": 0.0,
                "mode": "initial",
            }
        if render_kind == "side":
            return {
                "rotation": 0.0,
                "horizontal_flip": False,
                "vertical_flip": False,
                "scale_width": None,
                "scale_height": None,
                "translation_x": 0.0,
                "translation_y": 0.0,
                "mode": "side",
            }
        return {
            "rotation": 0.0,
            "horizontal_flip": False,
            "vertical_flip": False,
            "scale_width": 190.0,
            "scale_height": 190.0,
            "translation_x": 0.0,
            "translation_y": 0.0,
            "mode": "overlay",
        }

    def _render_preview_figure(render_kind: str, render_transform: dict[str, Any] | None = None):
        render_kind = str(render_kind or "overlay").lower()
        render_transform = dict(render_transform or _default_transform(render_kind))
        ad_sm = ad_sm_source.copy()
        if render_kind == "initial":
            plt.figure(figsize=(6, 6))
            smt.pl.plot_spot_sm_st(
                adata_SM=ad_sm,
                adata_ST=ad_st,
                marker="H",
                SM_spatial_key="spatial",
            )
            return plt.gcf(), ad_sm, "initial_st_sm_view.png", "Initial ST / SM View", "initial", "initial_plot"
        if render_kind == "side":
            smt.pp.spot_transform_by_manual(
                adata=ad_sm,
                rotation=float(render_transform.get("rotation") or 0.0),
                spatial_key_SM="spatial",
                new_spatial_key_SM="spatial",
            )
            coords = ad_sm.obsm["spatial"].copy()
            if bool(render_transform.get("horizontal_flip")):
                coords[:, 0] = -coords[:, 0]
            if bool(render_transform.get("vertical_flip")):
                coords[:, 1] = -coords[:, 1]
            ad_sm.obsm["spatial"] = coords
            plt.figure(figsize=(10, 5))
            smt.pl.plot_spot_sm_st(
                adata_SM=ad_sm,
                adata_ST=ad_st,
                marker="H",
                SM_spatial_key="spatial",
            )
            return plt.gcf(), ad_sm, "side_by_side.png", "Side-by-Side View", "side", "side_plot"
        smt.pp.spot_transform_by_manual(
            adata=ad_sm,
            rotation=float(render_transform.get("rotation") or 0.0),
            horizontal_flip=bool(render_transform.get("horizontal_flip")),
            vertical_flip=bool(render_transform.get("vertical_flip")),
            scale_width=float(render_transform.get("scale_width") or 190),
            scale_height=float(render_transform.get("scale_height") or 190),
            translation_x=float(render_transform.get("translation_x") or 0.0),
            translation_y=float(render_transform.get("translation_y") or 0.0),
            spatial_key_SM="spatial",
            new_spatial_key_SM="spatial",
        )
        plt.figure(figsize=(6, 6))
        smt.pl.plot_spot_sm_st(
            adata_SM=ad_sm,
            adata_ST=ad_st,
            marker="H",
            SM_spatial_key="spatial",
            ST_spatial_key="spatial",
            stacked=True,
        )
        return plt.gcf(), ad_sm, "manual_overlay.png", "Manual Registration Preview", "overlay", "overlay_plot"

    _status(job, "running", current_step="rendering preview with original plotting logic", progress=55.0)
    fig, rendered_ad_sm, filename, plot_name, kind, plot_id = _render_preview_figure(kind, transform)
    fig.tight_layout()
    color_spec = _extract_worker_color_spec(fig)
    color_parameters = dict(job.get("color_parameters") or {})
    fig = _apply_worker_color_settings(fig, color_spec, color_parameters)
    path = plots_dir / filename
    pdf_filename = str(Path(filename).with_suffix(".pdf"))
    pdf_path = plots_dir / pdf_filename
    fig.savefig(path, dpi=180, bbox_inches="tight", facecolor="white")
    fig.savefig(pdf_path, format="pdf", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    plt.close("all")

    combined_pdf_path = output_dir / "alignment_preprocessing_plots_vector.pdf"
    pdf_transforms = dict(job.get("manual_preview_pdf_transforms") or {})
    _status(job, "running", current_step="writing editable vector PDF", progress=75.0)
    with PdfPages(combined_pdf_path) as pdf:
        for page_kind in ("initial", "overlay", "side"):
            page_transform = dict(pdf_transforms.get(page_kind) or (_default_transform(page_kind)))
            page_fig, _, _, _, _, _ = _render_preview_figure(page_kind, page_transform)
            page_fig.tight_layout()
            page_fig = _apply_worker_color_settings(
                page_fig,
                _extract_worker_color_spec(page_fig),
                color_parameters if page_kind == kind else {},
            )
            pdf.savefig(page_fig, bbox_inches="tight")
            plt.close(page_fig)
    plt.close("all")

    manual_transform_artifact = None
    if kind == "overlay":
        # The preview and the persisted coordinates are generated by the same
        # SpatialMETA operation.  The PNG is never the only manual result.
        import numpy as np

        coordinate_path = output_dir / "manual_transformed_coordinates.npy"
        transformed_coordinates = np.asarray(rendered_ad_sm.obsm["spatial"], dtype=np.float32)
        np.save(coordinate_path, transformed_coordinates, allow_pickle=False)
        metadata_path = output_dir / "manual_transform.json"
        metadata = {
            "schema": "spashiny.alignment.manual_transform",
            "version": 1,
            "workflow_id": job.get("workflow_id"),
            "session_id": job.get("session_id"),
            "job_id": job.get("job_id"),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "source_coordinate_key": "spatial",
            "transformed_coordinate_key": "spatial",
            "parameters": transform,
            "source": _coordinate_metadata(source_coordinates),
            "transformed": _coordinate_metadata(transformed_coordinates),
            "coordinate_artifact": coordinate_path.name,
        }
        _json(metadata_path, metadata)
        manual_transform_artifact = {
            "metadata": metadata_path.name,
            "coordinates": coordinate_path.name,
            "source_coordinate_key": metadata["source_coordinate_key"],
            "transformed_coordinate_key": metadata["transformed_coordinate_key"],
            "coordinate_metadata": metadata["transformed"],
        }

    manifest = {
        "job_id": job["job_id"],
        "task": "manual_preview",
        "status": "completed",
        "workflow_id": job.get("workflow_id"),
        "transform": transform,
        "preview_kind": kind,
        "plot_key": str(job.get("plot_key") or plot_id),
        "color_parameters": color_parameters,
        "plots": [_plot_manifest_item(
            name=plot_name,
            path=path,
            output_dir=output_dir,
            group="manual_preview",
            preview_kind=kind,
            plot_id=plot_id,
            color_spec=color_spec,
            color_parameters=color_parameters,
        )],
        "downloads": [{
            "name": plot_name,
            "path": f"plots/{filename}",
            "plot_id": plot_id,
            "color_parameters": color_parameters,
        }, {
            "name": f"{plot_name} editable vector PDF",
            "path": f"plots/{pdf_filename}",
            "plot_id": plot_id,
            "preview_kind": kind,
            "content_type": "application/pdf",
            "color_parameters": color_parameters,
        }, {
            "name": "Alignment preprocessing plots editable vector PDF",
            "path": combined_pdf_path.relative_to(output_dir).as_posix(),
            "content_type": "application/pdf",
            "vector_pdf_bundle": True,
        }],
        "vector_pdfs": {
            "preview": f"plots/{pdf_filename}",
            "combined": combined_pdf_path.relative_to(output_dir).as_posix(),
        },
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    if manual_transform_artifact is not None:
        manifest["manual_transform"] = manual_transform_artifact
        manifest["downloads"].extend([
            {"name": "Manual transform metadata", "path": manual_transform_artifact["metadata"]},
            {"name": "Manual transformed coordinates", "path": manual_transform_artifact["coordinates"]},
        ])
    _json(output_dir / "result_manifest.json", manifest)
    _status(job, "completed", current_step="completed", progress=100.0, result_manifest=str(output_dir / "result_manifest.json"))


def _train(job: dict[str, Any]) -> None:
    import torch

    output_dir = Path(job["output_dir"])
    checkpoint_dir = output_dir / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    model, device = _alignment_model(job, load_state=False)
    provenance = _alignment_provenance(job, device)
    seed = int(provenance["random_seed"])
    max_epoch = int(job.get("max_epoch") or 128)
    loss_history: list[float] = []
    started_monotonic = time.monotonic()
    _status(
        job,
        "running",
        current_step=f"training epoch 0/{max_epoch}",
        started_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        device=device,
        train_epoch=0,
        train_total_epochs=max_epoch,
        train_loss=None,
        progress=0.0,
    )
    for epoch in range(1, max_epoch + 1):
        loss_dict = model.fit_vae(max_epoch=1, random_seed=seed)
        total_loss = None
        if isinstance(loss_dict, dict):
            total_loss = loss_dict.get("total_loss") or loss_dict.get("loss")
        elif hasattr(loss_dict, "__len__") and len(loss_dict) > 0:
            first = loss_dict[0]
            if isinstance(first, dict):
                total_loss = first.get("total_loss") or first.get("loss")
        if total_loss is not None:
            loss_history.append(float(total_loss))
        elapsed = max(0.0, time.monotonic() - started_monotonic)
        remaining = None
        if epoch > 0:
            remaining = max(0.0, elapsed / epoch * (max_epoch - epoch))
        _status(
            job,
            "running",
            current_step=f"training epoch {epoch}/{max_epoch}",
            progress=round(epoch * 100 / max_epoch, 2),
            device=device,
            train_epoch=epoch,
            train_total_epochs=max_epoch,
            train_loss=float(total_loss) if total_loss is not None else None,
            train_loss_history_len=len(loss_history),
            elapsed_seconds=round(elapsed, 2),
            estimated_remaining_seconds=round(remaining, 2) if remaining is not None else None,
        )
        if epoch == 1 or epoch % 10 == 0 or epoch == max_epoch:
            _log(job, f"epoch={epoch} loss={total_loss}")
    state_path = checkpoint_dir / "alignment_vae_state_dict.pt"
    torch.save(getattr(model, "trained_state_dict", None) or model.state_dict(), state_path)
    loss_path = checkpoint_dir / "alignment_vae_loss_history.json"
    _json(loss_path, {"loss_history": loss_history})
    config_path = checkpoint_dir / "alignment_model_config.json"
    model_config = dict(job.get("model_config") or {})
    model_config["device"] = device
    model_config["random_seed"] = seed
    adata_st_obj = getattr(model, "adata_st", None)
    adata_sm_obj = getattr(model, "adata_sm", None)
    bundle_config = {
        "schema": "spashiny.automatic_alignment_vae_bundle",
        "version": 1,
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "model_class": "spatialmeta.model._alignment_model.AlignmentVAE",
        "model_config": model_config,
        "provenance": provenance,
        "data_signature": {
            "st_shape": list(getattr(adata_st_obj, "shape", [])) if adata_st_obj is not None else None,
            "sm_shape": list(getattr(adata_sm_obj, "shape", [])) if adata_sm_obj is not None else None,
            "st_var_names": [str(x) for x in list(getattr(adata_st_obj, "var_names", []))[:200]] if adata_st_obj is not None else [],
            "sm_var_names": [str(x) for x in list(getattr(adata_sm_obj, "var_names", []))[:200]] if adata_sm_obj is not None else [],
        },
        "training": {
            "trained_epochs": max_epoch,
            "random_seed": seed,
            "loss_history": loss_history,
            "ready_to_skip_step3": True,
        },
    }
    _json(config_path, bundle_config)
    manifest = {
        "job_id": job["job_id"],
        "task": "train",
        "status": "completed",
        "workflow_id": job.get("workflow_id"),
        "device": device,
        "provenance": provenance,
        "state_dict": str(state_path),
        "config": str(config_path),
        "loss_history": str(loss_path),
        "downloads": [
            {"name": "AlignmentVAE state dict", "path": state_path.relative_to(output_dir).as_posix()},
            {"name": "AlignmentVAE config", "path": config_path.relative_to(output_dir).as_posix()},
            {"name": "AlignmentVAE loss history", "path": loss_path.relative_to(output_dir).as_posix()},
        ],
        "plots": [],
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    _json(output_dir / "result_manifest.json", manifest)
    _status(
        job,
        "completed",
        current_step=f"completed {max_epoch}/{max_epoch} epochs",
        progress=100.0,
        device=device,
        train_epoch=max_epoch,
        train_total_epochs=max_epoch,
        train_loss=loss_history[-1] if loss_history else None,
        train_loss_history_len=len(loss_history),
        result_manifest=str(output_dir / "result_manifest.json"),
    )


def _render(job: dict[str, Any]) -> None:
    output_dir = Path(job["output_dir"])
    plots_dir = output_dir / "plots"
    model, device = _alignment_model(job, load_state=True)
    setattr(model, "max_raster_cells", int(job.get("max_raster_cells") or 1500000))
    setattr(model, "raster_dx", float(job.get("raster_dx") or 0.4))
    _log(job, f"render limits: max_raster_cells={getattr(model, 'max_raster_cells', None)} raster_dx={getattr(model, 'raster_dx', None)}")
    _status(job, "running", current_step="generating raster", started_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"), device=device)
    with _Heartbeat(job, "generating raster"):
        raster_result = _get_rasterized_feature_map_with_limits(model, job)
    with (output_dir / "raster_result.pkl").open("wb") as handle:
        pickle.dump(raster_result, handle, protocol=pickle.HIGHEST_PROTOCOL)
    plots = _save_raster_plots(raster_result, plots_dir)
    _status(job, "running", current_step="generating spot plot", progress=65.0, device=device)
    with _Heartbeat(job, "generating spot plot"):
        result_dict = model.random_sample_inside_image_spot(raster_result)
    with (output_dir / "spot_result.pkl").open("wb") as handle:
        pickle.dump(result_dict, handle, protocol=pickle.HIGHEST_PROTOCOL)
    spot_payload = result_dict.get("data", {}) if isinstance(result_dict, dict) else {}
    missing_sampling_keys = [key for key in STEP4_SAMPLING_STATE_KEYS if spot_payload.get(key) is None]
    if missing_sampling_keys:
        raise ValueError(
            "Step4 spot sampling returned an incomplete state: " + ", ".join(missing_sampling_keys)
        )
    sampling_state_path = output_dir / "step4_sampling_state.pkl"
    with sampling_state_path.open("wb") as handle:
        pickle.dump(
            {
                "schema": STEP4_SAMPLING_STATE_SCHEMA,
                "version": STEP4_SAMPLING_STATE_VERSION,
                "data": {key: spot_payload[key] for key in STEP4_SAMPLING_STATE_KEYS},
            },
            handle,
            protocol=pickle.HIGHEST_PROTOCOL,
        )
    _log(job, "Step4 sampling state persisted: " + ", ".join(STEP4_SAMPLING_STATE_KEYS))
    plots.extend(_save_spot_plot(result_dict, plots_dir, raster_result))
    render_pdf = _save_render_pdf(output_dir, plots)
    try:
        import matplotlib.pyplot as plt

        plt.close("all")
    except Exception:
        pass
    warnings: list[str] = []
    if isinstance(raster_result, dict):
        warnings.extend(str(item) for item in (raster_result.get("warnings") or []))
    if isinstance(result_dict, dict):
        warnings.extend(str(item) for item in (result_dict.get("warnings") or []))
    manifest = {
        "job_id": job["job_id"],
        "task": "render",
        "status": "completed",
        "workflow_id": job.get("workflow_id"),
        "device": device,
        "plots": plots,
        "warnings": warnings,
        "step4_state": {
            "schema": STEP4_SAMPLING_STATE_SCHEMA,
            "version": STEP4_SAMPLING_STATE_VERSION,
            "raster_payload": "raster_result.pkl",
            "spot_payload": "spot_result.pkl",
            "sampling_payload": sampling_state_path.name,
            "sampling_keys": list(STEP4_SAMPLING_STATE_KEYS),
        },
        "downloads": [
            {"name": "Raster payload", "path": "raster_result.pkl"},
            {"name": "Spot payload", "path": "spot_result.pkl"},
            {"name": "Step4 sampling state", "path": sampling_state_path.name},
            *plots,
            *([render_pdf] if render_pdf else []),
        ],
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    _json(output_dir / "result_manifest.json", manifest)
    _status(job, "completed", current_step="completed", progress=100.0, device=device, result_manifest=str(output_dir / "result_manifest.json"))


def _render_color_panel(job: dict[str, Any]) -> None:
    output_dir = Path(job["output_dir"])
    plots_dir = output_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    source_output_dir = Path(str(job.get("source_output_dir") or ""))
    if not source_output_dir.is_dir():
        raise FileNotFoundError(f"Source render result directory not found: {source_output_dir}")

    plot_id = str(job.get("plot_id") or "")
    panel = str(job.get("panel") or "")
    group = str(job.get("group") or "")
    color_parameters = dict(job.get("color_parameters") or {})
    name = str(job.get("plot_name") or plot_id or panel)
    _status(job, "running", current_step=f"re-rendering {plot_id}", started_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"))

    if group == "raster":
        with (source_output_dir / "raster_result.pkl").open("rb") as handle:
            raster_result = pickle.load(handle)
        fig = _raster_panel_figure(raster_result, panel)
    elif group == "spot":
        with (source_output_dir / "spot_result.pkl").open("rb") as handle:
            result_dict = pickle.load(handle)
        raster_result = None
        raster_path = source_output_dir / "raster_result.pkl"
        if raster_path.is_file():
            with raster_path.open("rb") as handle:
                raster_result = pickle.load(handle)
        fig = _spot_panel_figure(result_dict, panel, raster_result)
    else:
        raise ValueError(f"Unsupported color re-render group: {group}")

    color_spec = _extract_worker_color_spec(fig)
    fig = _apply_worker_color_settings(fig, color_spec, color_parameters)
    filename = f"{plot_id or group + '_' + panel}.png"
    path = plots_dir / filename
    _save_figure(fig, path, dpi=180)
    try:
        import matplotlib.pyplot as plt

        plt.close("all")
    except Exception:
        pass

    item = _plot_manifest_item(
        name=name,
        path=path,
        output_dir=output_dir,
        group=group,
        panel=panel,
        plot_id=plot_id,
        color_spec=color_spec,
        color_parameters=color_parameters,
    )
    manifest = {
        "job_id": job["job_id"],
        "task": "render_color_panel",
        "status": "completed",
        "source_render_job_id": job.get("source_render_job_id"),
        "source_output_dir": str(source_output_dir),
        "plot_key": plot_id,
        "plot_id": plot_id,
        "panel": panel,
        "group": group,
        "color_parameters": color_parameters,
        "plots": [item],
        "downloads": [item],
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    _json(output_dir / "result_manifest.json", manifest)
    _status(job, "completed", current_step="completed", progress=100.0, result_manifest=str(output_dir / "result_manifest.json"))


def _fit_alignment(job: dict[str, Any]) -> None:
    """Run the expensive Step5 registration entirely outside the Shiny process."""
    import inspect
    import numpy as np

    output_dir = Path(job["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    source_output_dir = Path(str(job.get("source_render_output_dir") or ""))
    if not source_output_dir.is_dir():
        raise FileNotFoundError(f"Completed Step4 result directory not found: {source_output_dir}")
    _status(job, "running", current_step="loading Step4 state", started_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    data = _load_step4_fit_payload(source_output_dir)
    _log(job, "Step4 state loaded for fit: " + ", ".join(STEP4_SAMPLING_STATE_KEYS))
    model, device = _alignment_model(job, load_state=True)
    try:
        import spatialmeta.model._alignment_model as alignment_module

        alignment_module.os = os
    except Exception as exc:
        _log(job, f"warning: unable to inject spatialMETA os compatibility: {exc}")

    requested_config = dict(job.get("alignment_config") or {})
    parameters = inspect.signature(model.fit_alignment).parameters
    fit_kwargs = {key: value for key, value in requested_config.items() if key in parameters}
    ignored = sorted(set(requested_config) - set(fit_kwargs))
    if ignored:
        _log(job, "fit_alignment ignored unsupported API settings: " + ", ".join(ignored))
    debug_path = None
    if bool(job.get("save_debug_figures")):
        debug_dir = output_dir / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        debug_path = str(debug_dir)
    _status(job, "running", current_step="fitting alignment", progress=10.0, device=device)
    try:
        total_niter = int(fit_kwargs.get("niter") or requested_config.get("niter") or 500)
    except Exception:
        total_niter = 500
    restore_progress = _install_spatialmeta_fit_progress(job, total=total_niter, device=device)
    try:
        with _Heartbeat(job, "fitting alignment"):
            result_dict = model.fit_alignment(data, debug_path=debug_path, **fit_kwargs)
    finally:
        restore_progress()
    best_key = _select_best_alignment_key(result_dict)
    best_result = result_dict.get(best_key) or {}
    points = best_result.get("pointsIt")
    if points is None:
        raise ValueError(f"fit_alignment result {best_key} does not contain pointsIt")
    points_np = _to_numpy(points).astype(np.float32, copy=False)
    if points_np.ndim != 2 or points_np.shape[1] < 2:
        raise ValueError(f"fit_alignment result has invalid pointsIt shape: {points_np.shape}")
    points_np = points_np[:, :2]
    full_result_path = output_dir / "alignment_fit_result.pkl"
    with full_result_path.open("wb") as handle:
        pickle.dump(result_dict, handle, protocol=pickle.HIGHEST_PROTOCOL)
    points_path = output_dir / "aligned_points.npy"
    np.save(points_path, points_np, allow_pickle=False)
    step4_payload = data.get("data", {}) if isinstance(data, dict) else {}
    st_points = step4_payload.get("pointsJ") if isinstance(step4_payload, dict) else None
    if st_points is None:
        raise ValueError("Step4 payload does not contain ST raster coordinates (pointsJ)")
    st_points_np = _to_numpy(st_points).astype(np.float32, copy=False)
    if st_points_np.ndim != 2 or st_points_np.shape[1] < 2:
        raise ValueError(f"Step4 ST raster coordinate shape is invalid: {st_points_np.shape}")
    st_points_np = st_points_np[:, :2]
    st_points_path = output_dir / "step7_st_raster_points.npy"
    np.save(st_points_path, st_points_np, allow_pickle=False)
    loss = best_result.get("loss", [])
    try:
        final_loss = float(loss[-1]) if loss else None
    except Exception:
        final_loss = None
    summary_path = output_dir / "alignment_fit_summary.json"
    provenance = _alignment_provenance(job, device)
    _json(summary_path, {
        "schema": "spashiny.alignment.step5_fit_summary",
        "version": 1,
        "workflow_id": job.get("workflow_id"),
        "source_render_job_id": job.get("source_render_job_id"),
        "provenance": provenance,
        "coordinate_space": "step4_raster",
        "best_key": best_key,
        "final_loss": final_loss,
        "points_path": points_path.name,
        "points_shape": list(points_np.shape),
        "points_dtype": str(points_np.dtype),
        "aligned_coordinate_metadata": _coordinate_metadata(points_np),
        "st_points_path": st_points_path.name,
        "st_coordinate_metadata": _coordinate_metadata(st_points_np),
        "requested_config": requested_config,
        "applied_config": fit_kwargs,
        "ignored_config": ignored,
    })
    manifest = {
        "job_id": job["job_id"],
        "task": "fit_alignment",
        "status": "completed",
        "workflow_id": job.get("workflow_id"),
        "device": device,
        "source_render_job_id": job.get("source_render_job_id"),
        "provenance": provenance,
        "summary": summary_path.name,
        "downloads": [
            {"name": "Alignment fit summary", "path": summary_path.name},
            {"name": "Aligned SM coordinates", "path": points_path.name},
            {"name": "Step7 ST raster coordinates", "path": st_points_path.name},
            {"name": "Full alignment fit result", "path": full_result_path.name},
        ],
        "plots": [],
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    _json(output_dir / "result_manifest.json", manifest)
    _status(job, "completed", current_step="completed", progress=100.0, device=device, result_manifest=str(output_dir / "result_manifest.json"))


def main(argv: list[str] | None = None) -> int:
    _configure_illustrator_vector_output()
    parser = argparse.ArgumentParser(description="Run SpaShiny Lab alignment tasks outside Shiny.")
    parser.add_argument("--job", required=True)
    args = parser.parse_args(argv)
    job_path = Path(args.job).resolve()
    job = json.loads(job_path.read_text(encoding="utf-8"))
    job.setdefault("status_file", str(job_path.parent / "status.json"))
    job.setdefault("log_file", str(job_path.parent / "worker.log"))
    try:
        _configure_runtime_limits(job)
        _configure_library_compatibility(job)
        _log(job, f"starting task={job.get('task')}")
        task = str(job.get("task") or "")
        if task == "train":
            _train(job)
        elif task == "render":
            _render(job)
        elif task == "manual_preview":
            _manual_preview(job)
        elif task == "render_color_panel":
            _render_color_panel(job)
        elif task == "fit_alignment":
            _fit_alignment(job)
        else:
            raise ValueError(f"Unsupported alignment task: {task}")
        _log(job, "completed")
        return 0
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        _log(job, message)
        _log(job, traceback.format_exc())
        _status(job, "failed", error=message, traceback=traceback.format_exc(), finished_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
