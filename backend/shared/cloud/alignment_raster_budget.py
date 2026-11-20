"""Per-call resource adapter for SpatialMETA's unchanged native raster code.

Preserve source coordinates and record a reversible isotropic computational
frame for SM, matching the tutorial's 0-100 x extent. Bound dense allocation
and bridge SciPy's renamed Delaunay attribute in private function namespaces.
"""
from __future__ import annotations

import inspect
import math
import os
from types import FunctionType, MethodType
from typing import Any

import numpy as np

DEFAULT_MAX_CELLS = 1_500_000


def _private_function(function, **bindings):
    adapted = FunctionType(function.__code__, dict(function.__globals__, **bindings),
                           function.__name__, function.__defaults__, function.__closure__)
    adapted.__kwdefaults__ = function.__kwdefaults__
    return adapted


def sm_computational_frame(values):
    from cloud.coordinate_guards import frame_roundtrip_check
    xy = spatial_xy(values, name="SM").astype(np.float64)
    origin = xy.min(axis=0)
    factor = 100.0 / float(np.ptp(xy[:, 0]))
    normalized = (xy - origin) * factor
    represented = normalized.astype(np.float32)
    validation = frame_roundtrip_check(xy, represented, origin=origin, scale=factor)
    return represented, {"origin": origin.tolist(), "scale": factor,
        "inverse_scale": 1.0 / factor, "aspect_ratio_preserved": True,
        "source_key": "spatial", "computational_space": "sm_isotropic_x_extent_100",
        "numeric_roundtrip": validation,
        "not_spatial_normalized": True}


def spatial_xy(values: Any, *, name: str) -> np.ndarray:
    xy = np.asarray(values)
    if xy.ndim != 2 or xy.shape[1] != 2 or len(xy) < 3:
        raise ValueError(f"{name} must contain at least three 2D spatial coordinates; got {xy.shape}")
    if not np.isfinite(xy).all():
        raise ValueError(f"{name} contains non-finite spatial coordinates")
    if np.any(np.ptp(xy.astype(np.float64), axis=0) <= 0):
        raise ValueError(f"{name} has a zero spatial range")
    return xy


def grid_shape(x: Any, y: Any, *, dx: float, expand: float) -> tuple[int, int]:
    """Predict STalign's np.arange lengths without allocating coordinate axes."""
    dx, expand = float(dx), float(expand)
    if not math.isfinite(dx) or dx <= 0 or not math.isfinite(expand) or expand <= 0:
        raise ValueError("Raster dx and expansion must be finite and positive")
    axes = []
    for values in (x, y):
        values = np.asarray(values, dtype=np.float64)
        if values.ndim != 1 or not values.size or not np.isfinite(values).all():
            raise ValueError("Raster axes must be nonempty finite vectors")
        lo, hi = float(values.min()), float(values.max())
        mid, half = (lo + hi) / 2, (hi - lo) * expand / 2
        width = (mid + half) - (mid - half)
        if not math.isfinite(width) or width <= 0:
            raise ValueError("Raster coordinate range is invalid")
        axes.append(max(1, math.ceil(width / dx)))
    return axes[0], axes[1]


def raster_plan(x: Any, y: Any, channels: int, *, dx: float, expand: float,
                max_cells: int = DEFAULT_MAX_CELLS, memory_gb: float = 0) -> dict[str, Any]:
    channels, max_cells = int(channels), int(max_cells)
    if channels <= 0 or max_cells <= 0:
        raise ValueError("Raster channels and cell budget must be positive; an unlimited grid is not allowed")
    # Conservative estimate includes float64 work arrays/meshgrid and float32
    # tensors. It is an allocation estimate, not a measured process RSS peak.
    bytes_per_cell = 64 + 64 * channels
    if not math.isfinite(float(memory_gb)) or float(memory_gb) < 0:
        raise ValueError("Invalid alignment memory budget")
    work_budget = int(min(2 * 1024**3, memory_gb * 1024**3 / 4)) if memory_gb else 2 * 1024**3
    limit = min(DEFAULT_MAX_CELLS, max_cells, work_budget // bytes_per_cell)
    if limit < 16:
        raise ValueError("Alignment raster memory budget is too small")
    nx, ny = grid_shape(x, y, dx=dx, expand=expand)
    native_shape = [ny, nx, channels]
    effective = float(dx)
    if nx * ny > limit:
        effective *= math.sqrt(nx * ny / limit)
        for _ in range(16):
            nx, ny = grid_shape(x, y, dx=effective, expand=expand)
            if nx * ny <= limit:
                break
            effective *= 1.01
    if nx * ny > limit or min(nx, ny) < 2:
        raise ValueError("Cannot construct a valid raster within the cell/memory budget")
    return {"schema": "spashiny.alignment.raster_budget", "version": 1,
            "requested_dx": float(dx), "effective_dx": effective,
            "expand": float(expand), "native_shape": native_shape,
            "native_work_array_bytes": math.prod(native_shape) * 8,
            "planned_shape": [ny, nx, channels], "cell_limit": limit,
            "estimated_raster_work_bytes": nx * ny * bytes_per_cell,
            "raster_work_budget_bytes": work_budget,
            "resolution_adjusted": effective != float(dx),
            "physical_coordinates_changed": False}


def native_raster_with_budget(model: Any, job: dict[str, Any], log) -> dict[str, Any]:
    st = spatial_xy(model.st_spatial_coord, name="ST")
    sm = spatial_xy(model.sm_spatial_coord, name="SM")
    sm_before, st_before = sm.copy(), st.copy()
    normalized, sm_frame = sm_computational_frame(sm)
    log(job, "Reversible SM computational frame (source coordinates unchanged): " + str(sm_frame))
    unadapted = raster_plan(sm[:, 0], sm[:, 1], int(getattr(model, "n_latent", 10)),
                            dx=.4, expand=1.1)
    method = model.get_rasterized_feature_map
    function = getattr(method, "__func__", None)
    if function is None or getattr(method, "__self__", None) is not model:
        raise RuntimeError("Unsupported SpatialMETA raster API; dense allocation was not attempted")
    native = function.__globals__.get("rasterize_with_signal")
    if not callable(native):
        raise RuntimeError("SpatialMETA native rasterizer could not be budgeted; allocation was not attempted")
    signature = inspect.signature(native)
    plans = []

    def bounded(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        values = bound.arguments
        signal = np.asarray(values["s"])
        if signal.ndim not in (1, 2) or len(signal) != len(values["x"]) or not np.isfinite(signal).all():
            raise ValueError("Native raster latent signal is invalid")
        channels = 1 if signal.ndim == 1 else signal.shape[1]
        configured = int(job.get("max_raster_cells", DEFAULT_MAX_CELLS))
        env_limit = int(os.environ.get("SPASHINY_ALIGNMENT_MAX_RASTER_PIXELS", DEFAULT_MAX_CELLS))
        if min(configured, env_limit) <= 0:
            raise ValueError("Disabling the alignment raster allocation guard is not supported")
        plan = raster_plan(values["x"], values["y"], channels, dx=values["dx"],
                           expand=values["expand"], max_cells=min(configured, env_limit),
                           memory_gb=float(os.environ.get("SPASHINY_ALIGNMENT_MEMORY_LIMIT_GB", "0")))
        log(job, "Native raster allocation plan: " + str(plan))
        values["dx"] = plan["effective_dx"]
        output = native(*bound.args, **bound.kwargs)
        actual = list(np.asarray(output[2]).shape)
        if len(actual) != 3 or actual[0] != channels or actual[1] * actual[2] > plan["cell_limit"]:
            raise RuntimeError(f"Native raster violated allocation contract: {actual}")
        plan["actual_shape"] = actual
        plans.append(plan)
        return output

    adapted = _private_function(function, rasterize_with_signal=bounded)
    source_sm = model.adata_sm
    source_sm_coordinates = model.sm_spatial_coord
    # A private derived AnnData keeps the native plot, native raster points and
    # native alpha=1 boundary sampling in the SAME computational frame. Never
    # rewrite the saved input, expression matrix or caller's AnnData object.
    derived_sm = source_sm.copy()
    derived_sm.obsm["spatial"] = normalized
    try:
        model.adata_sm = derived_sm
        model.sm_spatial_coord = normalized
        result = MethodType(adapted, model)()
    finally:
        model.adata_sm = source_sm
        model.sm_spatial_coord = source_sm_coordinates
    if len(plans) != 1:
        raise RuntimeError("Expected exactly one native SM rasterization")
    np.testing.assert_array_equal(np.asarray(model.st_spatial_coord), st_before)
    np.testing.assert_array_equal(np.asarray(model.sm_spatial_coord), sm_before)
    payload = result["data"]
    scale = float(payload["scale"])
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("ST image-to-full-resolution scale must be finite and positive")
    def cpu_values(value):
        return value.detach().cpu().numpy() if hasattr(value, "detach") else np.asarray(value)
    np.testing.assert_allclose(cpu_values(payload["pointsI"]), normalized, rtol=2e-7, atol=1e-5)
    np.testing.assert_allclose(cpu_values(payload["pointsJ"]), st_before * scale, rtol=2e-7, atol=1e-4)
    from cloud.coordinate_guards import frame_roundtrip_check
    st_validation = frame_roundtrip_check(st_before, cpu_values(payload['pointsJ']),
        origin=[0, 0], scale=scale)
    payload['coordinate_validation'] = {"schema": "spashiny.raster_coordinate_validation.v1",
        "sm_numeric_roundtrip": sm_frame['numeric_roundtrip'],
        "st_image_scale_roundtrip": st_validation,
        "input_st_coordinates_unchanged": True, "input_sm_coordinates_unchanged": True,
        "scientific_registration_accuracy": "UNVERIFIED_BY_NUMERIC_ROUNDTRIP"}
    contract = {"schema": "spashiny.alignment.coordinate_contract", "version": 1,
                "model_coordinate_key": "spatial", "sm_input_space": "manual_prealigned",
                "sm_computational_frame": sm_frame,
                "st_input_space": "visium_full_resolution", "fit_output_space": "st_image_pixels",
                "st_image_scale": scale, "to_st_full_resolution_scale": 1.0 / scale,
                "source_coordinates_unchanged": True}
    payload["raster_budget"] = plans[0]
    plans[0]["unadapted_native_shape"] = unadapted["native_shape"]
    plans[0]["unadapted_native_work_array_bytes"] = unadapted["native_work_array_bytes"]
    payload["coordinate_contract"] = contract
    if plans[0]["resolution_adjusted"]:
        result.setdefault("warnings", []).append(
            "Large coordinate range: native raster dx increased from "
            f"{plans[0]['requested_dx']:.6g} to {plans[0]['effective_dx']:.6g} "
            "to respect the allocation budget. Physical coordinates, latent channels and training parameters are unchanged.")
    return result


def _compatible_alpha_shape(native):
    """Exact old alpha-shape body with vertices -> identical SciPy simplices."""
    delaunay = native.__globals__["Delaunay"]

    class DelaunayView:
        def __init__(self, *args, **kwargs):
            self.triangulation = delaunay(*args, **kwargs)

        @property
        def vertices(self):
            return self.triangulation.simplices

        def __getattr__(self, name):
            return getattr(self.triangulation, name)

    return _private_function(native, Delaunay=DelaunayView)


def repair_native_figure_size(fig):
    """The installed sampler assigns a tuple to a Matplotlib method by typo.

    Repair that returned Figure instance only and apply the intended dimensions.
    Do not reconstruct scientific marks or change the native plotting function.
    """
    value = getattr(fig, "set_size_inches", None)
    if callable(value):
        return False
    if (not isinstance(value, (tuple, list)) or len(value) != 2
            or not all(math.isfinite(float(v)) and float(v) > 0 for v in value)
            or "set_size_inches" not in vars(fig)):
        raise RuntimeError("Native Figure has an invalid size setter")
    dimensions = tuple(float(v) for v in value)
    delattr(fig, "set_size_inches")
    fig.set_size_inches(*dimensions)
    return True


def native_sample_with_compat(model, raster_result, log, job):
    """Keep native thresholds/formulas; no global SciPy/vendor monkey-patch."""
    function = model.random_sample_inside_image_spot.__func__
    native_alpha = function.__globals__.get("alpha_shape")
    if native_alpha is None:
        raise RuntimeError("Unsupported native alpha-shape sampling API")
    frame = raster_result.get("data", {}).get("coordinate_contract", {}).get("sm_computational_frame")
    if frame is None:
        raise ValueError("Native sampling requires the recorded SM computational frame")
    adapted = _private_function(function, alpha_shape=_compatible_alpha_shape(native_alpha))
    result = MethodType(adapted, model)(raster_result)
    for name, fig in (result.get("fig") or {}).items():
        if repair_native_figure_size(fig):
            log(job, f"Native Figure {name}: repaired instance set_size_inches tuple typo; original artists retained")
    log(job, "Native spot sampling: original thresholds; SciPy Delaunay.simplices compatibility; recorded SM frame")
    return result
