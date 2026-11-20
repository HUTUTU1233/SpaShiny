"""Native initial QC/preview in the CPU worker, never in Shiny's event loop."""
from copy import deepcopy
import math

from .common import CPUWorkflowError, save_figure_bundle, sha256_file, write_csv, write_json


def apply_initial_qc(smt, adata_sm, threshold):
    import numpy as np

    threshold = float(threshold)
    if not math.isfinite(threshold) or threshold < 0:
        raise CPUWorkflowError("PARAMETER_INVALID", "Initial SM intensity threshold must be finite and non-negative.")
    smt.pp.calculate_qc_metrics_sm(adata_sm)
    values = np.asarray(adata_sm.obs["total_intensity"], dtype=float)
    if not values.size or not np.isfinite(values).all():
        raise CPUWorkflowError("INPUT_CONTRACT_INVALID", "SM total intensities are empty or contain non-finite values.")
    before = [int(v) for v in adata_sm.shape]
    filtered = smt.pp.filter_cells_sm(adata_sm, min_total_intensity=threshold)
    if filtered is None or not filtered.n_obs or not filtered.n_vars:
        raise CPUWorkflowError("QC_FILTER_REMOVED_ALL_OBSERVATIONS",
            f"Initial SM QC removed every pixel: threshold={threshold:g}, input total-intensity range={values.min():g}..{values.max():g}. Lower the intensity threshold; normalized/aligned inputs do not use raw-intensity thresholds.")
    filtered = filtered.copy()
    return filtered, {
        "method": "spatialmeta.pp.calculate_qc_metrics_sm + spatialmeta.pp.filter_cells_sm",
        "min_total_intensity": threshold, "before_shape": before,
        "after_shape": [int(v) for v in filtered.shape],
        "removed_observations": before[0] - int(filtered.n_obs),
        "input_total_intensity_min": float(values.min()), "input_total_intensity_max": float(values.max()),
    }


def structure(adata):
    return {"shape": [int(v) for v in adata.shape], "obs_columns": list(map(str, adata.obs.columns)),
        "var_columns": list(map(str, adata.var.columns)), "obsm_keys": list(map(str, adata.obsm)),
        "uns_keys": list(map(str, adata.uns)), "spatial_sample_ids": list(map(str, (adata.uns.get("spatial") or {}).keys()))}


def run(ctx, smt, adata_st, adata_sm, st_path, sm_path, lineage):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import scanpy as sc

    adata_sm, qc = apply_initial_qc(smt, adata_sm, ctx.parameters.get("initial_min_total_intensity", 0))
    outputs = []
    st_xy = np.asarray(adata_st.obsm["spatial"])
    sm_key = "spatial"
    sm_xy = np.asarray(adata_sm.obsm[sm_key])
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.scatter(st_xy[:, 0], st_xy[:, 1], s=8, alpha=.55, label="ST spatial")
    ax.scatter(sm_xy[:, 0], sm_xy[:, 1], s=8, alpha=.55, label="SM " + sm_key)
    ax.set(title="Current KNN input after initial SM QC", xlabel="x", ylabel="y")
    ax.set_aspect("equal", adjustable="box"); ax.legend(); fig.tight_layout()
    png, pdf = save_figure_bundle(fig, ctx.figures_dir / "knn_input_overlay.png", dpi=150)
    plt.close(fig)
    outputs.extend(p.relative_to(ctx.workspace).as_posix() for p in (png, pdf))

    libraries = list((adata_st.uns.get("spatial") or {}).keys())
    sample = str(lineage["coordinate_contract"].get("sample_name") or "")
    preview = ""
    if ctx.parameters.get("operation") == "input_preview":
        if not sample or sample not in libraries:
            raise CPUWorkflowError("PREVIEW_SAMPLE_REQUIRED", "Choose a sample present in the current ST uns['spatial'] metadata.")
        spatial = adata_st.uns["spatial"][sample]
        scale = float(spatial.get("scalefactors", {}).get("tissue_hires_scalef", 0))
        if not math.isfinite(scale) or scale <= 0 or "hires" not in spatial.get("images", {}):
            raise CPUWorkflowError("PREVIEW_METADATA_INVALID", "ST hires image or tissue_hires_scalef is missing or invalid.")
        # The same explicitly converted full-resolution coordinates are used
        # by preview and KNN. Scanpy applies the image scale for display.
        view = adata_sm.copy()
        view.uns["spatial"] = {sample: deepcopy(spatial)}
        fig, ax = plt.subplots(figsize=(6, 6))
        sc.pl.spatial(view, library_id=sample, img_key="hires", color="total_intensity", show=False, ax=ax)
        png, pdf = save_figure_bundle(fig, ctx.figures_dir / "knn_scaled_preview.png", dpi=150)
        plt.close(fig)
        outputs.extend(p.relative_to(ctx.workspace).as_posix() for p in (png, pdf))
        preview = "figures/knn_scaled_preview.png"

    adata_st.write_h5ad(ctx.workspace / "knn_st_prepared.h5ad")
    adata_sm.write_h5ad(ctx.workspace / "knn_sm_prepared.h5ad")
    inputs = {"st": {"filename": st_path.name, "sha256": sha256_file(st_path)},
              "sm": {"filename": sm_path.name, "sha256": sha256_file(sm_path)}}
    if "sm_raw" in lineage["inputs"]:
        inputs["sm_raw"] = dict(lineage["inputs"]["sm_raw"])
    report = {"job_id": ctx.job_id, "owner_session_id": ctx.owner_session_id,
        "analysis_session_id": str(ctx.metadata.get("analysis_session_id") or ""),
        "source_mode": lineage["source_mode"], "operation": ctx.parameters["operation"],
        "inputs": inputs,
        "initial_sm_qc": qc, "st": structure(adata_st), "sm": structure(adata_sm),
        "preview_sample_name": sample, "preview_png": preview,
        "input_lineage": lineage, "coordinate_contract": adata_sm.uns["spashiny_knn_coordinate_contract"], "knn_executed": False}
    write_json(ctx.workspace / "knn_input_inspection.json", report)
    write_csv(ctx.workspace / "knn_initial_qc.csv", [{"dataset": "SM", **qc}])
    outputs.extend(("knn_input_inspection.json", "knn_initial_qc.csv", "knn_st_prepared.h5ad", "knn_sm_prepared.h5ad"))
    return {"metrics": report, "outputs": outputs}
