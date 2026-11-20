"""Saved Alignment plot export only: no analysis, uploads, jobs, or DB access.

Legacy PNG-backed reports are never passed through as editable results. Rebuild
their artists from trusted, same-analysis Step4 arrays in an isolated child,
leaving the Shiny event loop free to answer WebSocket/session heartbeats.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import pickle
import sys
import tempfile
from pathlib import Path
from typing import Any

EXPORT_VERSION = "alignment-native-vectors-20261020-v3"
STEP7_EXPORT_VERSION = "alignment-step7-current-X-qc-20261105-v5"
_EXPORT_SLOTS: asyncio.Semaphore | None = None


def fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()


def checked_path(path: Path | str, root: Path | str, *, file: bool = True) -> Path:
    candidate, allowed = Path(path).resolve(), Path(root).resolve()
    try:
        candidate.relative_to(allowed)
    except ValueError as exc:
        raise ValueError("Alignment plot path is outside the current analysis scope.") from exc
    if file and not candidate.is_file():
        raise FileNotFoundError("Required saved Alignment plot data is unavailable.")
    return candidate


def step7_cache_key(*, owner: str, analysis: str, workflow: str, step4: str,
                    step5: str, step6: str, colors: dict) -> str:
    if not all((owner, analysis, workflow, step4, step5)) or step6 != step5:
        raise ValueError("Step7 requires the exact current analysis/workflow/Step5/Step6 lineage.")
    return fingerprint(dict(version=STEP7_EXPORT_VERSION, owner=owner, analysis=analysis,
                            workflow=workflow, step4=step4, step5=step5,
                            step6=step6, colors=colors))


def step7_source_image(adata_st, st_points):
    """Recover the native ST image only if its scale matches saved Step5 XY.

    No coordinate swapping, rescaling, image-stretching, or guessing based on
    image bounds is permitted. An absent image is reported as coordinates-only.
    """
    import numpy as np

    metadata = getattr(adata_st, "uns", {}).get("spatial", {})
    if not metadata:
        return None, "No H&E image in this input; coordinates-only preview."
    from spatialmeta.plotting._utils import get_spatial_image

    image, scale = get_spatial_image(adata_st)
    expected = np.asarray(adata_st.obsm["spatial"], dtype=float)[:, :2] * float(scale)
    actual = np.asarray(st_points, dtype=float)
    if expected.shape != actual.shape or not np.allclose(expected, actual, rtol=1e-5, atol=1e-3):
        raise ValueError("The ST image scale does not match this Step5 coordinate artifact; refusing an incorrect overlay.")
    image = np.asarray(image)
    if image.ndim not in (2, 3) or not image.size:
        raise ValueError("The saved ST H&E image has an invalid shape.")
    return image, f"Native ST image; XY scale={float(scale):g}."


def _step7_intensity_fingerprint(values):
    import numpy as np
    array = np.ascontiguousarray(values, dtype=np.float64)
    return hashlib.sha256(str(array.shape).encode() + array.tobytes()).hexdigest()


def step7_current_intensity(adata, *, block_rows=512):
    """Native calculate_qc_metrics_sm semantics: sum CURRENT X, not stale obs.

    Backed inputs are streamed in complete row blocks. No normalization, feature
    filtering, coordinate operation or assignment to the input is performed.
    """
    import numpy as np
    if adata.n_obs <= 0 or adata.n_vars <= 0 or adata.X is None:
        raise ValueError("Step7 needs a nonempty current Alignment SM matrix.")
    if int(block_rows) <= 0:
        raise ValueError("Step7 row-block size must be positive.")
    # Keep dense blocks bounded even for a nonstandard, wide uploaded matrix.
    rows = max(1, min(int(block_rows), (8 * 1024 * 1024) // max(8 * adata.n_vars, 1)))
    totals = []
    for start in range(0, adata.n_obs, rows):
        block = adata.X[start:start + rows]
        totals.append(np.asarray(block.sum(axis=1)).reshape(-1))
    values = np.concatenate(totals)
    if values.shape != (adata.n_obs,) or not np.isfinite(values).all():
        raise ValueError("Current Alignment SM X has invalid/nonfinite row totals.")
    return values, {
        "schema": "spashiny.step7.color_source.v1", "matrix": "X",
        "operation": "row_sum; equivalent to spatialmeta.pp.calculate_qc_metrics_sm",
        "shape": [int(adata.n_obs), int(adata.n_vars)], "block_rows": rows,
        "stored_obs_used": False, "normalization_applied": False,
        "input_modified": False, "value_sha256": _step7_intensity_fingerprint(values),
        "min": float(values.min()), "max": float(values.max()),
    }


def read_step7_plot_inputs(st_path: Path, sm_path: Path):
    """Read XY/image metadata and bounded current-X row sums for SM colors.

    Paths are supplied only after Web verifies the current owner/analysis,
    workflow and exact Step3 -> Step4 lineage. These lightweight facades let a
    restored workflow redraw without materializing expression matrices/models.
    The tutorial recomputes SM QC AFTER normalization and feature selection;
    imported obs['total_intensity'] can still describe the original raw TIC.
    """
    import h5py
    import numpy as np
    import pandas as pd
    from types import SimpleNamespace
    try:
        from anndata.io import read_elem
    except ImportError:
        from anndata.experimental import read_elem

    inputs = []
    for path, is_st in ((st_path, True), (sm_path, False)):
        with h5py.File(path, "r") as handle:
            xy = np.asarray(read_elem(handle["obsm/spatial"]))
            columns = {}
            for name in ("total_intensity", "total_counts", "n_counts"):
                if f"obs/{name}" in handle:
                    columns[name] = read_elem(handle[f"obs/{name}"])
            spatial = (read_elem(handle["uns/spatial"]) if is_st and "uns/spatial" in handle else {})
        color_source = None
        if not is_st:
            from anndata import read_h5ad
            backed = read_h5ad(path, backed="r")
            try:
                totals, color_source = step7_current_intensity(backed)
                if backed.n_obs != len(xy):
                    raise ValueError("Step7 matrix and coordinate row counts differ.")
                columns["total_intensity"] = totals
            finally:
                backed.file.close()
        inputs.append(SimpleNamespace(n_obs=len(xy), obsm={"spatial": xy},
                                      obs=pd.DataFrame(columns, index=range(len(xy))),
                                      uns={"spatial": spatial},
                                      _spashiny_step7_intensity_source=color_source))
    return tuple(inputs)


def build_step7_tutorial_figure(adata_st, adata_sm, *, st_raster_points,
                               aligned_points, source_step5_job_id: str):
    """Render the tutorial's Scanpy overlay from saved, verified Step5 XY.

    Plot-only AnnData objects have zero variables; colors are verified row sums
    of the current prepared X, not imported raw-TIC obs. No full expression
    matrix is copied into the figure. The aligned SM basis is in ST image pixels; applying the
    Visium scale to it a second time would corrupt the overlay. These copies
    are neither Step6 artifacts nor new analytical results.
    """
    from copy import deepcopy
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    import scanpy as sc
    from anndata import AnnData
    from cloud.figure_export import mark_source_image

    st_xy = np.asarray(st_raster_points, dtype=float)
    sm_xy = np.asarray(aligned_points, dtype=float)
    for label, points, data in (("ST", st_xy, adata_st), ("SM", sm_xy, adata_sm)):
        if (points.shape != (data.n_obs, 2) or not data.n_obs
                or not np.isfinite(points).all()):
            raise ValueError(f"Step7 rejected invalid/mismatched {label} coordinates from Step5.")
    color_source = getattr(adata_sm, "_spashiny_step7_intensity_source", None)
    if getattr(adata_sm, "X", None) is not None:
        intensity, color_source = step7_current_intensity(adata_sm)
    else:
        if not color_source or "total_intensity" not in adata_sm.obs:
            raise ValueError("Step7 color source is unverified; reload current Alignment X instead of stale raw-TIC obs.")
        intensity = np.asarray(adata_sm.obs["total_intensity"])
        if _step7_intensity_fingerprint(intensity) != color_source.get("value_sha256"):
            raise ValueError("Step7 color vector no longer matches its current-X fingerprint.")
    intensity = np.asarray(intensity, dtype=float)
    if intensity.shape != (adata_sm.n_obs,) or not np.isfinite(intensity).all():
        raise ValueError("Step7 requires one finite total_intensity value per aligned SM pixel.")

    spatial = getattr(adata_st, "uns", {}).get("spatial", {})
    if len(spatial) != 1:
        raise ValueError("The tutorial ST H&E overlay requires exactly one saved Visium image library; no library or image was guessed.")
    library = next(iter(spatial.values()))
    images = library.get("images", {})
    image_key = next((key for key in ("hires", "lowres") if key in images), None)
    if image_key is None:
        raise ValueError("The tutorial ST H&E overlay requires a saved hires or lowres image.")
    scalefactors = library.get("scalefactors", {})
    scale = float(scalefactors.get(f"tissue_{image_key}_scalef", 0))
    diameter = float(scalefactors.get("spot_diameter_fullres", 0))
    if not np.isfinite([scale, diameter]).all() or scale <= 0 or diameter <= 0:
        raise ValueError("The ST image scale and spot_diameter_fullres must be finite and positive for the tutorial overlay.")
    original_st = np.asarray(adata_st.obsm["spatial"], dtype=float)
    if (original_st.shape != st_xy.shape or not np.isfinite(original_st).all()
            or not np.allclose(original_st * scale, st_xy, rtol=1e-5, atol=1e-3)):
        raise ValueError("The ST image scale does not match this Step5 coordinate artifact; refusing a double-scaled or incorrect overlay.")
    image = np.asarray(images[image_key])
    if image.ndim not in (2, 3) or not image.size:
        raise ValueError("The saved ST H&E image has an invalid shape.")

    st_plot = AnnData(X=None, shape=(adata_st.n_obs, 0),
                      obsm={"spatial": original_st.copy()},
                      uns={"spatial": deepcopy(spatial)})
    sm_plot = AnnData(X=None, shape=(adata_sm.n_obs, 0),
                      obs=pd.DataFrame({"total_intensity": intensity.copy()},
                                       index=pd.Index([str(i) for i in range(adata_sm.n_obs)])),
                      obsm={"spatial_transformed": sm_xy.copy()})
    fig, ax = plt.subplots(figsize=(6, 6), dpi=180)
    try:
        # Same scientific plotting functions and SM point size as the tutorial.
        sc.pl.spatial(st_plot, show=False, ax=ax)
        sc.pl.embedding(sm_plot, basis="spatial_transformed", ax=ax,
                        s=10, color="total_intensity", show=False)
        # Keep the original tissue image as an honest image layer; export point
        # artists, labels and colorbar directly as editable vectors.
        for axes in fig.axes:
            for artist in axes.images:
                mark_source_image(artist)
            for artist in axes.collections:
                artist.set_rasterized(False)
        fig.tight_layout()
        fig._spashiny_alignment_ready = True
        fig._spashiny_step5_job_id = str(source_step5_job_id)
        fig._spashiny_step7_plot_contract = {
            "version": STEP7_EXPORT_VERSION,
            "st_api": "scanpy.pl.spatial",
            "sm_api": "scanpy.pl.embedding",
            "basis": "spatial_transformed", "color": "total_intensity", "s": 10,
            "coordinate_space": "step4_raster", "st_image_scale": scale,
            "coordinates_modified": False, "expression_matrix_materialized": False,
            "color_source": dict(color_source),
        }
        return fig
    except BaseException:
        plt.close(fig)
        raise


def compact_scalar_meshes(fig) -> list[dict]:
    """Losslessly merge adjacent cells with identical *displayed* RGBA.

    The saved numeric arrays, normalization, colormap, limits and coordinates
    are never changed. A 2000x1951 computed grid need not emit 3.9M individual
    PDF paths when large adjacent regions already have the exact same mapped
    color. Output remains editable vector rectangles, not a raster image.
    Original H&E images and scatter points are deliberately untouched.
    """
    import numpy as np
    from matplotlib.collections import QuadMesh
    from matplotlib.path import Path as MatplotlibPath
    from matplotlib.patches import PathPatch

    statistics = []
    for ax in fig.axes:
        for mesh in list(ax.collections):
            if not isinstance(mesh, QuadMesh) or not mesh.get_visible():
                continue
            coords = np.asarray(mesh.get_coordinates())
            if coords.ndim != 3 or coords.shape[2] != 2:
                continue
            height, width = coords.shape[0]-1, coords.shape[1]-1
            if height*width < 4096:
                continue  # Colorbars/small meshes need no compaction.
            # Only rectilinear, flat cell meshes can be merged this way.
            if (not np.array_equal(coords[..., 0], np.broadcast_to(coords[0, :, 0], coords.shape[:2]))
                    or not np.array_equal(coords[..., 1], np.broadcast_to(coords[:, 0:1, 1], coords.shape[:2]))):
                continue
            mesh.update_scalarmappable()
            rgba = np.asarray(mesh.get_facecolors()).reshape(height, width, 4)
            active, rectangles = {}, []
            for row in range(height):
                changes = np.flatnonzero(np.any(rgba[row, 1:] != rgba[row, :-1], axis=1))+1
                starts, stops = np.r_[0, changes], np.r_[changes, width]
                current = {}
                for start, stop in zip(starts.tolist(), stops.tolist()):
                    color = rgba[row, start]
                    if color[3] == 0:
                        continue
                    key = (start, stop, color.tobytes())
                    rect = active.pop(key, None)
                    if rect is None:
                        rect = [row, row+1, start, stop, color.copy()]
                    else:
                        rect[1] = row+1
                    current[key] = rect
                rectangles.extend(active.values())
                active = current
            rectangles.extend(active.values())
            vertices = np.empty((len(rectangles), 4, 2), dtype=float)
            colors = np.empty((len(rectangles), 4), dtype=float)
            for i, (top, bottom, left, right, color) in enumerate(rectangles):
                vertices[i] = (coords[top, left], coords[top, right],
                               coords[bottom, right], coords[bottom, left])
                colors[i] = color
            unique_colors, groups = np.unique(colors, axis=0, return_inverse=True)
            # One compound fill per RGBA is important for translucent masks.
            # Independent adjacent fills can create PDF viewer stitching seams
            # by applying transparency twice along subpixel-shared boundaries.
            for group, color in enumerate(unique_colors):
                path = MatplotlibPath.make_compound_path_from_polys(vertices[groups == group])
                replacement = PathPatch(path, facecolor=color, edgecolor="none", linewidth=0,
                                        antialiased=False, rasterized=False,
                                        transform=mesh.get_transform(), zorder=mesh.get_zorder())
                replacement.set_clip_on(mesh.get_clip_on())
                replacement.set_clip_box(mesh.get_clip_box())
                replacement.set_clip_path(mesh.get_clip_path())
                replacement._spashiny_compacted_mesh = True
                ax.add_artist(replacement)
            # Keep the original ScalarMappable for its existing colorbar, but
            # do not draw its redundant per-pixel paths.
            mesh.set_visible(False)
            statistics.append(dict(cells=height*width, vector_rectangles=len(rectangles),
                                   vector_compound_paths=len(unique_colors),
                                   displayed_rgba_unchanged=True))
    return statistics


async def export_saved_step4(*, scope_root: Path, workflow_root: Path,
                             source_dir: Path, source_job_id: str,
                             colors_by_plot: dict) -> dict:
    """Bounded on-demand legacy re-export; only this child can read pickles."""
    global _EXPORT_SLOTS
    if _EXPORT_SLOTS is None:
        _EXPORT_SLOTS = asyncio.Semaphore(1)
    source_dir = checked_path(source_dir, scope_root, file=False)
    workflow_root = checked_path(workflow_root, scope_root, file=False)
    source_manifest = checked_path(source_dir / "result_manifest.json", scope_root)
    manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
    if manifest.get("job_id") != source_job_id or manifest.get("status") != "completed":
        raise ValueError("The current Step4 render manifest is not a completed matching job.")
    sources = {}
    for name in ("result_manifest.json", "raster_result.pkl", "spot_result.pkl"):
        path = checked_path(source_dir / name, scope_root)
        stat = path.stat()
        sources[name] = [stat.st_size, stat.st_mtime_ns]
    key = fingerprint(dict(version=EXPORT_VERSION, source_job_id=source_job_id,
                           sources=sources, colors_by_plot=colors_by_plot))
    target = workflow_root / "exports" / key

    def cached():
        marker = target / "export_manifest.json"
        if not marker.is_file():
            return None
        data = json.loads(marker.read_text(encoding="utf-8"))
        if data.get("version") != EXPORT_VERSION or data.get("fingerprint") != key:
            return None
        if data.get("source_job_id") != source_job_id:
            return None
        for item in data.get("files", []):
            path = checked_path(target / item["path"], target)
            if not path.stat().st_size:
                return None
        return data

    async with _EXPORT_SLOTS:
        data = cached()
        if data:
            return dict(data, root=str(target))
        target.parent.mkdir(parents=True, exist_ok=True)
        request = dict(scope_root=str(Path(scope_root).resolve()), source_dir=str(source_dir),
                       source_job_id=source_job_id, target=str(target), fingerprint=key,
                       colors_by_plot=colors_by_plot)
        with tempfile.TemporaryDirectory(prefix="alignment-vector-request-") as temporary:
            request_path = Path(temporary) / "request.json"
            request_path.write_text(json.dumps(request), encoding="utf-8")
            env = dict(os.environ, MPLBACKEND="Agg", OMP_NUM_THREADS="1",
                       OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
            process = await asyncio.create_subprocess_exec(
                sys.executable, str(Path(__file__).resolve()), "--request", str(request_path),
                env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            )
            try:
                output, _ = await asyncio.wait_for(process.communicate(), timeout=300)
            except BaseException:
                if process.returncode is None:
                    process.kill()
                await process.wait()
                raise
            if process.returncode:
                detail = output.decode("utf-8", errors="replace")[-1600:]
                raise RuntimeError(f"Editable Alignment export failed; no PNG fallback was used. {detail}")
        data = cached()
        if not data:
            raise RuntimeError("Editable Alignment export produced no validated artifact manifest.")
        return dict(data, root=str(target))


def write_saved_step4(request: dict) -> None:
    """Child entrypoint: original data -> original artists -> PDF/SVG."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from cloud.figure_export import EditablePdfPages, mark_source_image, save_native_figure
    from alignment_saved_panels import _raster_panel_figure, _spot_panel_figure

    scope = Path(request["scope_root"]).resolve()
    source = checked_path(request["source_dir"], scope, file=False)
    target = checked_path(request["target"], scope, file=False)
    manifest = json.loads(checked_path(source / "result_manifest.json", scope).read_text())
    if manifest.get("job_id") != request["source_job_id"] or manifest.get("status") != "completed":
        raise ValueError("Source render lineage changed before export.")
    # Only server-generated job payloads under the verified current analysis
    # can reach this reader. Never unpickle an uploaded/client-selected file.
    with checked_path(source / "raster_result.pkl", scope).open("rb") as handle:
        raster = pickle.load(handle)
    if isinstance(raster, dict):
        raster.pop("fig", None)
    with checked_path(source / "spot_result.pkl", scope).open("rb") as handle:
        spot = pickle.load(handle)
    if isinstance(spot, dict):
        spot.pop("fig", None)
    # Some historical pickle files also contain old native Figure objects.
    # Discard them: they are neither trusted export input nor PNG fallbacks.
    plt.close("all")
    import gc
    gc.collect()
    order = [("raster", "sm_feature"), ("raster", "sm_latent"),
             ("raster", "st_image"), ("raster", "st_latent"),
             ("spot", "st_latent"), ("spot", "sampled"), ("spot", "mask")]
    files = []
    mesh_statistics = {}
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pending-vectors-", dir=target.parent) as temporary:
        pending = Path(temporary)
        # PdfPages embeds fonts at close(), not just savefig(). Keep Type42
        # active for the entire report lifetime, including font finalization.
        with matplotlib.rc_context({"pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none"}), \
                EditablePdfPages(pending / "raster_and_spot.pdf") as report:
            for group, panel in order:
                plot_id = f"{group}_panel_{panel}"
                fig = (_raster_panel_figure(raster, panel) if group == "raster"
                       else _spot_panel_figure(spot, panel, raster))
                try:
                    # Tissue photographs remain honest image layers. Scalar
                    # features/masks are editable QuadMesh cells, not imshow.
                    for ax in fig.axes:
                        for image in ax.images:
                            mark_source_image(image)
                    settings = request.get("colors_by_plot", {}).get(plot_id)
                    if settings:
                        from plot_color_tools import apply_color_settings_to_figure, extract_color_spec_from_figure
                        fig = apply_color_settings_to_figure(fig, settings,
                                                            extract_color_spec_from_figure(fig))
                    mesh_statistics[plot_id] = compact_scalar_meshes(fig)
                    report.savefig(fig, bbox_inches="tight", facecolor="white")
                    for suffix in ("pdf", "svg"):
                        filename = f"{plot_id}.{suffix}"
                        save_native_figure(fig, pending / filename, format=suffix,
                                           bbox_inches="tight", facecolor="white")
                        files.append(dict(plot_id=plot_id, path=filename))
                finally:
                    plt.close(fig)
        files.append(dict(plot_id="raster_and_spot", path="raster_and_spot.pdf"))
        record = dict(version=EXPORT_VERSION, fingerprint=request["fingerprint"],
                      source_job_id=request["source_job_id"], files=files,
                      rerun_analysis=False, source_images_preserved=True,
                      lossless_vector_mesh_compaction=mesh_statistics)
        (pending / "export_manifest.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        # A valid completed directory is immutable. Partial work never serves
        # as a cached result and originals are never overwritten.
        if target.exists():
            raise RuntimeError("An incomplete export directory already exists; original results were not changed.")
        Path(temporary).rename(target)


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--request":
        raise SystemExit("Use --request with a server-generated export request.")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    write_saved_step4(json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")))
