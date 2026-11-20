from __future__ import annotations

from pathlib import Path

from .common import CPUWorkflowContext, CPUWorkflowError, ensure_dependency, save_figure_bundle, select_asset, write_csv, write_json


def _spatial_array(adata, *keys: str):
    for key in keys:
        if key in adata.obsm:
            return adata.obsm[key], key
    return None, ""


def _write_spatial_preview(ctx: CPUWorkflowContext, adata_st, adata_sm) -> list[str]:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except Exception:
        return []

    st_xy, st_key = _spatial_array(adata_st, "spatial", "spatial_transformed")
    sm_xy, sm_key = _spatial_array(adata_sm, "spatial_transformed", "spatial")
    if st_xy is None or sm_xy is None:
        return []

    st_xy = np.asarray(st_xy)
    sm_xy = np.asarray(sm_xy)
    if st_xy.ndim != 2 or st_xy.shape[1] < 2 or sm_xy.ndim != 2 or sm_xy.shape[1] < 2:
        return []

    fig, ax = plt.subplots(figsize=(7, 6))
    ax.scatter(st_xy[:, 0], st_xy[:, 1], s=8, alpha=0.55, label=f"ST ({st_key})")
    ax.scatter(sm_xy[:, 0], sm_xy[:, 1], s=8, alpha=0.55, label=f"SM ({sm_key})")
    ax.set_title("KNN reassigned spatial overlay")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.legend(loc="best")
    ax.set_aspect("equal", adjustable="box")
    fig.tight_layout()
    path, pdf_path = save_figure_bundle(fig, ctx.figures_dir / "knn_reassignment_spatial.png", dpi=150)
    plt.close(fig)
    return [path.relative_to(ctx.workspace).as_posix(), pdf_path.relative_to(ctx.workspace).as_posix()]


def _recover_st_total_counts(adata_st_new, adata_st):
    ensure_dependency("numpy")
    import numpy as np

    if "total_counts" not in adata_st.obs:
        adata_st_new.obs["total_counts"] = np.ones(adata_st_new.n_obs, dtype="float32")
        return {"method": "default_ones", "shared_observations": 0}

    common_obs = adata_st_new.obs_names.intersection(adata_st.obs_names)
    if len(common_obs) > 0:
        adata_st_new.obs["total_counts"] = np.nan
        adata_st_new.obs.loc[common_obs, "total_counts"] = adata_st.obs.loc[common_obs, "total_counts"]
        return {"method": "obs_name", "shared_observations": int(len(common_obs))}

    try:
        from scipy.spatial import cKDTree

        original_coords = adata_st.obsm["spatial"]
        new_coords = adata_st_new.obsm["spatial"]
        tree = cKDTree(original_coords)
        distances, indices = tree.query(new_coords, k=1)
        adata_st_new.obs["total_counts"] = adata_st.obs.iloc[indices]["total_counts"].values
        return {
            "method": "spatial_nearest_neighbor",
            "shared_observations": 0,
            "mean_distance": float(distances.mean()) if len(distances) else 0.0,
        }
    except Exception:
        adata_st_new.obs["total_counts"] = np.ones(adata_st_new.n_obs, dtype="float32")
        return {"method": "default_ones_after_nearest_neighbor_failure", "shared_observations": 0}


def _recover_sm_metadata(adata_sm_new, adata_sm) -> dict:
    ensure_dependency("numpy")
    import numpy as np

    recovered: list[str] = []
    common_obs = adata_sm_new.obs_names.intersection(adata_sm.obs_names)
    if len(common_obs) > 0:
        for col in ("total_intensity", "mean_intensity"):
            if col in adata_sm.obs:
                adata_sm_new.obs[col] = np.nan
                adata_sm_new.obs.loc[common_obs, col] = adata_sm.obs.loc[common_obs, col]
                recovered.append(col)
    return {"shared_observations": int(len(common_obs)), "recovered_columns": recovered}


def run(ctx: CPUWorkflowContext) -> dict:
    ensure_dependency("scanpy")
    ensure_dependency("spatialmeta")
    import scanpy as sc
    import spatialmeta as smt

    st_path = select_asset(
        ctx,
        suffixes=(".h5ad",),
        roles=("st_qc_h5ad", "knn_st_h5ad", "st_h5ad", "primary"),
        label="KNN ST h5ad",
    )
    sm_path = select_asset(
        ctx,
        suffixes=(".h5ad",),
        roles=("sm_aligned_h5ad", "knn_sm_h5ad", "sm_h5ad"),
        label="KNN aligned SM h5ad",
    )
    if st_path is None or sm_path is None:
        raise CPUWorkflowError("INPUT_REQUIRED", "KNN reassignment requires ST and aligned SM h5ad inputs.")
    if Path(st_path).resolve() == Path(sm_path).resolve():
        raise CPUWorkflowError("INPUT_CONTRACT_INVALID", "KNN reassignment received the same h5ad for ST and SM inputs.")

    k = int(ctx.parameters.get("spot_knn_k") or ctx.parameters.get("n_neighbors") or ctx.parameters.get("k") or 5)
    dist_fold = float(ctx.parameters.get("spot_dist_fold") or ctx.parameters.get("dist_fold") or 2.0)
    if k <= 0:
        raise CPUWorkflowError("PARAMETER_INVALID", "KNN n_neighbors must be positive.")
    if dist_fold <= 0:
        raise CPUWorkflowError("PARAMETER_INVALID", "KNN dist_fold must be positive.")

    adata_st = sc.read_h5ad(str(st_path))
    adata_sm = sc.read_h5ad(str(sm_path))
    if "spatial" not in adata_st.obsm:
        raise CPUWorkflowError("INPUT_CONTRACT_INVALID", "ST h5ad must contain obsm['spatial'].")
    if "spatial_transformed" not in adata_sm.obsm and "spatial" not in adata_sm.obsm:
        raise CPUWorkflowError("INPUT_CONTRACT_INVALID", "Aligned SM h5ad must contain obsm['spatial_transformed'] or obsm['spatial'].")

    st_dot_in_df = smt.pp.ST_spot_sample(adata_st, "spatial")
    min_dist = smt.pp.calculate_min_dist(adata_st)
    adata_sm_new, adata_st_new = smt.pp.spot_align_byknn(
        new_dot_in_df=st_dot_in_df,
        adata_SM=adata_sm,
        adata_ST=adata_st,
        min_dist=min_dist,
        n_neighbors=k,
        dist_fold=dist_fold,
    )

    st_recovery = _recover_st_total_counts(adata_st_new, adata_st)
    sm_recovery = _recover_sm_metadata(adata_sm_new, adata_sm)
    try:
        smt.pp.calculate_qc_metrics_sm(adata_sm_new)
    except Exception as exc:
        # Keep the real KNN result but surface the QC issue in the manifest.
        sm_recovery["qc_warning"] = f"{type(exc).__name__}: {exc}"

    adata_sm_new.write_h5ad(ctx.workspace / "knn_sm_reassigned.h5ad")
    adata_st_new.write_h5ad(ctx.workspace / "knn_st_reassigned.h5ad")

    obs_rows = [
        {
            "dataset": "ST",
            "observations": int(adata_st_new.n_obs),
            "features": int(adata_st_new.n_vars),
        },
        {
            "dataset": "SM",
            "observations": int(adata_sm_new.n_obs),
            "features": int(adata_sm_new.n_vars),
        },
    ]
    write_csv(ctx.workspace / "knn_observation_summary.csv", obs_rows)

    figures = _write_spatial_preview(ctx, adata_st_new, adata_sm_new)
    metrics = {
        "st_input_file": st_path.name,
        "sm_input_file": sm_path.name,
        "st_input_shape": [int(adata_st.n_obs), int(adata_st.n_vars)],
        "sm_input_shape": [int(adata_sm.n_obs), int(adata_sm.n_vars)],
        "st_output_shape": [int(adata_st_new.n_obs), int(adata_st_new.n_vars)],
        "sm_output_shape": [int(adata_sm_new.n_obs), int(adata_sm_new.n_vars)],
        "min_dist": float(min_dist),
        "n_neighbors": int(k),
        "dist_fold": float(dist_fold),
        "st_total_counts_recovery": st_recovery,
        "sm_metadata_recovery": sm_recovery,
    }
    write_json(ctx.workspace / "knn_summary.json", {"status": "succeeded", **metrics})
    return {
        "metrics": metrics,
        "outputs": [
            "knn_summary.json",
            "knn_observation_summary.csv",
            "knn_sm_reassigned.h5ad",
            "knn_st_reassigned.h5ad",
            *figures,
        ],
    }
