"""Post-KNN operations on the exact scoped completed result, never Web RAM."""
import json
import math
from pathlib import Path

from .common import CPUWorkflowError, save_figure_bundle, sha256_file, write_json


def _spot_ids(values, label):
    import pandas as pd

    names = pd.Index(values)
    if names.hasnans or not names.is_unique or any(not isinstance(n, str) or not n.strip() for n in names):
        raise CPUWorkflowError("KNN_PAIR_MISMATCH", f"{label} requires unique, non-empty spot IDs.")
    return names


def _paired_xy(adata):
    import numpy as np

    xy = np.asarray(adata.obsm["spatial"])
    if xy.shape != (adata.n_obs, 2) or not np.isfinite(xy).all():
        raise CPUWorkflowError("KNN_PAIR_MISMATCH", "Expected one finite full-resolution coordinate pair per spot.")
    return xy


def restore_tutorial_st(original, native, grid):
    """Resolve native spot_name -> exact full-res XY -> original Visium barcode.

    SpatialMETA assigns spot_name on its query grid. Native obs x/y are cast
    to integers, so the identity join must use the original, unrounded XY.
    """
    import numpy as np
    import pandas as pd

    keys = ["x_coord", "y_coord"]
    original_ids = _spot_ids(original.obs_names, "Original ST barcodes")
    grid_ids = _spot_ids(grid["spot_name"], "Native KNN query grid")
    native_ids = _spot_ids(native.obs["spot_name"], "Native KNN ST")
    xy_grid = grid[keys].to_numpy()
    origin_keys = pd.MultiIndex.from_arrays(_paired_xy(original).T)
    grid_keys = pd.MultiIndex.from_arrays(xy_grid.T)
    if not origin_keys.is_unique or not grid_keys.is_unique or len(grid_ids) != len(original_ids):
        raise CPUWorkflowError("KNN_PAIR_MISMATCH", "KNN query coordinates do not uniquely identify the original ST spots.")
    original_indexer = origin_keys.get_indexer(grid_keys)
    native_indexer = native_ids.get_indexer(grid_ids)
    if (len(native_ids) != len(grid_ids) or (original_indexer < 0).any() or (native_indexer < 0).any()
            or not np.array_equal(_paired_xy(native)[native_indexer], xy_grid)):
        raise CPUWorkflowError("KNN_PAIR_MISMATCH", "Native KNN ST spot IDs and full-resolution coordinates disagree with the query grid.")
    metadata = native.obs[[*keys, "spot_name"]].set_index("spot_name", drop=False).loc[grid_ids].copy()
    if not np.array_equal(metadata[keys].to_numpy(), xy_grid.astype(int)):
        raise CPUWorkflowError("KNN_PAIR_MISMATCH", "Native ST x_coord/y_coord disagree with its spot IDs.")
    metadata.index = original_ids.take(original_indexer)
    result = original.copy()
    for key in (*keys, "spot_name"):
        result.obs[key] = metadata[key].reindex(original_ids)
    return result


def pair_tutorial_st(st, sm, *, require_complete=False):
    """Put original ST X in SM spot order before the native Joint concatenation."""
    import numpy as np

    st_ids = _spot_ids(st.obs["spot_name"], "Mapped ST")
    sm_ids = _spot_ids(sm.obs["spot_name"], "Reassigned SM")
    order = st_ids.get_indexer(sm_ids)
    if ((require_complete and len(st_ids) != len(sm_ids)) or (order < 0).any()
            or not np.array_equal(_paired_xy(st)[order], _paired_xy(sm))
            or not np.array_equal(st.obs[["x_coord", "y_coord"]].to_numpy()[order], sm.obs[["x_coord", "y_coord"]].to_numpy())):
        raise CPUWorkflowError("KNN_PAIR_MISMATCH", "ST and SM spot IDs do not map to the same coordinates.")
    return st if np.array_equal(order, np.arange(st.n_obs)) else st[order, :].copy()


def write_tutorial_spot_mapping(ctx, original, st, sm, joint):
    import numpy as np

    origin_ids = _spot_ids(original.obs_names, "Original ST barcodes")
    st_ids = _spot_ids(st.obs_names, "Saved ST barcodes")
    native_ids = _spot_ids(st.obs["spot_name"], "Saved ST spot names")
    orig = origin_ids.get_indexer(st_ids)
    xy = _paired_xy(st)
    if ((orig < 0).any() or not np.array_equal(_paired_xy(original)[orig], xy)
            or not native_ids.equals(_spot_ids(sm.obs["spot_name"], "Saved SM spot names"))
            or not native_ids.equals(_spot_ids(joint.obs["spot_name"], "Joint spot names"))
            or not np.array_equal(_paired_xy(sm), xy) or not np.array_equal(_paired_xy(joint), xy)
            or not np.array_equal(st.obs[["x_coord", "y_coord"]].to_numpy(), xy.astype(int))
            or not np.array_equal(sm.obs[["x_coord", "y_coord"]].to_numpy(), xy.astype(int))
            or not np.array_equal(joint.obs[["x_coord", "y_coord"]].to_numpy(), xy.astype(int))):
        raise CPUWorkflowError("KNN_PAIR_MISMATCH", "ST, SM and Joint must share the same verified spot order and coordinates.")
    rows = [{"original_st_barcode": barcode, "knn_spot_id": spot, "sm_obs_name": sm_id,
             "joint_obs_name": joint_id, "x_coord": int(x), "y_coord": int(y),
             "spatial_x": float(x), "spatial_y": float(y)}
            for barcode, spot, sm_id, joint_id, (x, y) in zip(st_ids, native_ids, sm.obs_names, joint.obs_names, xy)]
    path = ctx.workspace / "knn_spot_mapping.json"
    write_json(path, {"schema": "spashiny.knn.spot_mapping.v1", "row_order": "ST, SM, Joint (same spot order)",
                      "key": "knn_spot_id", "verified_spots": len(rows), "spots": rows})
    return {"relative_path": path.name, "sha256": sha256_file(path), "verified_spots": len(rows)}


def load_parent_and_filter(ctx, sc, smt):
    import numpy as np
    from ..knn_results import read_scoped_result, scoped_job
    from .knn_coordinates import matrix_quality

    parent_id = str(ctx.parameters.get("knn_parent_job_id") or "")
    key = str(ctx.parameters.get("knn_input_key") or "")
    owner, analysis = ctx.owner_session_id, str(ctx.metadata.get("analysis_session_id") or "")
    parent = scoped_job(owner, analysis, parent_id, key)
    parent_params = json.loads(parent.parameters_json or "{}")
    if (parent_params.get("operation", "reassign") not in {"reassign", "postprocess"}
            or parent_params.get("source_mode") != ctx.parameters.get("source_mode")):
        raise CPUWorkflowError("KNN_PARENT_INVALID", "Post-filtering requires this analysis's completed KNN result from the same input source.")
    def artifact(relative):
        return read_scoped_result(owner=owner, analysis=analysis, job_id=parent_id, key=key, relative=relative)
    metrics = json.loads(artifact("knn_summary.json").read_text())
    if (metrics.get("quality", {}).get("status") != "PASS"
            or not metrics.get("coordinate_contract") or not metrics.get("spatial_coverage")):
        raise CPUWorkflowError("KNN_PARENT_INVALID", "This older KNN result has no accepted coordinate/signal quality check. Run KNN again; a zero-filled legacy result cannot be used.")
    st = sc.read_h5ad(artifact("knn_st_reassigned.h5ad"))
    sm = sc.read_h5ad(artifact("knn_sm_reassigned.h5ad"))
    matrix_quality(st, sm)
    threshold = float(ctx.parameters.get("post_min_total_intensity", 0))
    if not math.isfinite(threshold) or threshold < 0:
        raise CPUWorkflowError("PARAMETER_INVALID", "Post-KNN intensity threshold must be finite and non-negative.")
    smt.pp.calculate_qc_metrics_sm(sm)
    before = sm.n_obs
    low = float(np.min(sm.obs["total_intensity"]))
    high = float(np.max(sm.obs["total_intensity"]))
    filtered = smt.pp.filter_cells_sm(sm, min_total_intensity=threshold).copy()
    if not filtered.n_obs:
        raise CPUWorkflowError("QC_FILTER_REMOVED_ALL_OBSERVATIONS", f"Post-KNN threshold {threshold:g} removed every spot; actual intensity range is {low:g}..{high:g}. Lower the threshold.")
    if not st.obs["spot_name"].is_unique or not filtered.obs["spot_name"].is_unique:
        raise CPUWorkflowError("KNN_PAIR_MISMATCH", "KNN spot identifiers are not unique.")
    by_spot = {name: i for i, name in enumerate(st.obs["spot_name"])}
    if any(name not in by_spot for name in filtered.obs["spot_name"]):
        raise CPUWorkflowError("KNN_PAIR_MISMATCH", "Filtered SM contains a spot absent from the completed ST result.")
    st_filtered = st[[by_spot[name] for name in filtered.obs["spot_name"]], :].copy()
    matrix_quality(st_filtered, filtered)
    return st_filtered, filtered, metrics, {"method": "spatialmeta.pp.filter_cells_sm",
        "parent_knn_job_id": parent_id, "min_total_intensity": threshold,
        "before_observations": before, "after_observations": filtered.n_obs,
        "removed_observations": before - filtered.n_obs, "knn_recomputed": False,
        "st_subset_by": "exact_retained_spot_name_order"}, (st, sm)


def write_figures(ctx, smt, sc, st, sm, quality, *, before_post=None, post_filter=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import seaborn as sns
    from copy import deepcopy
    from ..figure_export import EditablePdfPages

    figures = []
    outputs = []
    official = quality["source_mode"] == "EXAMPLE"
    pre_st, pre_sm = before_post if official and before_post is not None else (st, sm)
    histogram_record = None
    def save(fig, name):
        png, pdf = save_figure_bundle(fig, ctx.figures_dir / (name + ".png"), dpi=150)
        outputs.extend(p.relative_to(ctx.workspace).as_posix() for p in (png, pdf))
        figures.append(fig)
        return fig

    try:
        libraries = st.uns.get("spatial") or {}
        sample = str(quality["coordinate_contract"].get("sample_name") or "")
        if not sample and len(libraries) == 1:
            sample = str(next(iter(libraries)))
        has_hires = sample in libraries and "hires" in libraries[sample].get("images", {})
        if official and not has_hires:
            raise CPUWorkflowError("PREVIEW_METADATA_INVALID", "The official Y7_T plots require the ST hires tissue image.")
        intensity_cmap = smt.pl.make_colormap(["#3c096c", "#FFFFFF", "#ff6b35"])

        def spatial(adata, column, name, title, cmap, *, project_st_image=False):
            fig, ax = plt.subplots(figsize=(6, 6))
            if has_hires:
                view = adata
                if project_st_image or sample not in (adata.uns.get("spatial") or {}):
                    view = adata.copy()
                    view.uns["spatial"] = {sample: deepcopy(libraries[sample])}
                sc.pl.spatial(view, library_id=sample, img_key="hires", color=column, cmap=cmap, show=False, ax=ax)
            else:
                xy = np.asarray(adata.obsm["spatial"])
                points = ax.scatter(xy[:, 0], xy[:, 1], c=np.asarray(adata.obs[column]), s=7, cmap=cmap, linewidths=0)
                fig.colorbar(points, ax=ax, label=column)
                ax.set_aspect("equal", adjustable="box")
                title += " (no tissue image provided)"
            ax.set_title(title)
            fig.tight_layout()
            return save(fig, name)

        if official:
            spatial(pre_sm, "total_intensity", "knn_sm_total_intensity", "Reassigned SM total_intensity", intensity_cmap, project_st_image=True)
            spatial(pre_st, "total_counts", "knn_st_total_counts", "QC ST total_counts", "vlag")

        xy_st = np.asarray(st.obsm["spatial"])
        xy_sm = np.asarray(sm.obsm["spatial"])
        fig, axes = plt.subplots(1, 3, figsize=(14, 5))
        axes[0].scatter(xy_st[:, 0], xy_st[:, 1], s=6, c="#2878b5", linewidths=0)
        axes[0].set_title(f"ST: {st.n_obs:,} positions")
        axes[1].scatter(xy_sm[:, 0], xy_sm[:, 1], s=6, c="#ed8b23", linewidths=0)
        axes[1].set_title(f"SM: {sm.n_obs:,} positions")
        axes[2].scatter(xy_sm[:, 0], xy_sm[:, 1], s=5, c="#ed8b23", linewidths=0, label="SM signal", zorder=2)
        axes[2].scatter(xy_st[:, 0], xy_st[:, 1], s=22, facecolors="none", edgecolors="#2878b5", linewidths=.65, label="ST ring", zorder=3)
        axes[2].legend(loc="best", fontsize=8)
        axes[2].set_title("Shared coordinates: both layers visible")
        for ax in axes:
            ax.set_aspect("equal", adjustable="box")
            ax.set(xlabel="ST full-resolution x", ylabel="ST full-resolution y")
        fig.suptitle("Native KNN reassignment - ST and SM share the same output positions")
        fig.tight_layout()
        save(fig, "knn_reassignment_spatial")

        fig, axes = plt.subplots(1, 2, figsize=(8, 4) if official else (10, 4))
        for ax, column, color in zip(axes, ("total_intensity", "mean_intensity"), ("#ff6b35", "#3c096c")):
            if official:
                sns.histplot(pre_sm.obs[column], kde=False, ax=ax)
                ax.set_xlabel(column)
                if column == "total_intensity":
                    threshold = float(post_filter["min_total_intensity"])
                    threshold_line = ax.axvline(threshold, color="#a01818", linestyle="--", label=f"QC threshold: {threshold:,.0f}")
                    ax.legend(fontsize=8)
            else:
                values = np.asarray(sm.obs[column], dtype=float)
                sns.histplot(values, bins=30, kde=np.unique(values).size > 1, color=color, ax=ax)
                ax.axvline(float(np.mean(values)), color="red", linestyle="--", label=f"Mean {np.mean(values):.3g}")
                ax.axvline(float(np.median(values)), color="blue", linestyle="--", label=f"Median {np.median(values):.3g}")
                ax.set_title(column.replace("_", " ").title())
                ax.legend(fontsize=8)
        if official:
            fig.suptitle("Reassigned SM QC before filtering")
            histogram_record = {"layout": list(axes[0].get_subplotspec().get_gridspec().get_geometry()),
                "columns_left_to_right": [ax.get_xlabel() for ax in axes], "pre_filter_observations": int(pre_sm.n_obs),
                "threshold_line_x": list(map(float, threshold_line.get_xdata())), "threshold_panel": "total_intensity"}
        fig.tight_layout()
        save(fig, "knn_intensity_histograms")

        joint = sc.read_h5ad(ctx.workspace / "knn_joint_ready.h5ad")
        types = np.asarray(joint.var["type"], dtype=str)
        for modality in ("SM", "ST"):
            if not np.any(types == modality) or joint[:, types == modality].X.count_nonzero() <= 0:
                raise CPUWorkflowError("KNN_ZERO_OR_INVALID_MODALITY", "Native joint output lost a non-zero modality.")
        joint_figures = []
        for column, name, title, cmap in (
            ("total_intensity", "knn_joint_intensity", "Joint SM total intensity", intensity_cmap),
            ("total_counts", "knn_joint_counts", "Joint ST total counts", "vlag"),
        ):
            joint_figures.append(spatial(joint, column, name, title, cmap))
        with EditablePdfPages(ctx.workspace / "knn_joint_plots.pdf") as pdf:
            for fig in joint_figures:
                pdf.savefig(fig, bbox_inches="tight")
        cover, ax = plt.subplots(figsize=(8.27, 11.69))
        ax.axis("off")
        ax.text(.08, .92, "KNN reassignment quality report", fontsize=18, va="top")
        lines = [f"Job: {ctx.job_id}", f"Source: {quality['source_mode']}",
            f"ST: {st.n_obs} x {st.n_vars}; non-zero values: {quality['st']['nonzero_values']}",
            f"SM: {sm.n_obs} x {sm.n_vars}; non-zero values: {quality['sm']['nonzero_values']}",
            f"Matched ST positions before optional post-filter: {quality['spatial_coverage']['st_with_sm_neighbor']}",
            f"Coverage: {quality['spatial_coverage']['coverage_fraction']:.2%}",
            "Canonical coordinate units: ST full-resolution pixels", "Pair order and coordinates: validated",
            "KNN algorithm: spatialmeta.pp.spot_align_byknn", "Joint assembly: spatialmeta.pp.joint_adata_sm_st",
            "Equal output coordinates are expected after reassignment.",
            "Unmatched zero rows, if present, are not evidence of biological absence."]
        ax.text(.08, .85, "\n\n".join(lines), fontsize=10, va="top", wrap=True)
        with EditablePdfPages(ctx.workspace / "knn_full_report.pdf") as pdf:
            pdf.savefig(cover, bbox_inches="tight")
            for fig in figures:
                pdf.savefig(fig, bbox_inches="tight")
        plt.close(cover)
        outputs.extend(("knn_joint_plots.pdf", "knn_full_report.pdf"))
        if histogram_record:
            manifest = "knn_tutorial_figures.json"
            write_json(ctx.workspace / manifest, {"qc_histogram": histogram_record, "figures": list(outputs)})
            outputs.append(manifest)
        return outputs
    finally:
        for fig in figures:
            plt.close(fig)
