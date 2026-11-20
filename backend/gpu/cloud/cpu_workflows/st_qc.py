from __future__ import annotations

from .common import (
    CPUWorkflowContext,
    apply_basic_filters,
    matrix_qc_frames,
    plot_qc_histograms,
    read_matrix_input,
    select_asset,
    write_csv,
    write_json,
)


def run(ctx: CPUWorkflowContext) -> dict:
    input_path = select_asset(
        ctx,
        suffixes=(".h5ad", ".h5", ".hdf5", ".mtx"),
        roles=("st_raw_h5ad", "st_h5ad", "joint_raw", "primary"),
        label="ST matrix",
    )
    adata = read_matrix_input(input_path, modality="ST")
    obs_qc, feature_qc = matrix_qc_frames(adata)
    filtered, obs_mask, var_mask = apply_basic_filters(adata, obs_qc, feature_qc, ctx.parameters)
    write_csv(ctx.workspace / "observation_qc.csv", obs_qc.to_dict(orient="records"))
    write_csv(ctx.workspace / "feature_qc.csv", feature_qc.to_dict(orient="records"))
    filtered.write_h5ad(ctx.workspace / "filtered_result.h5ad")
    figures = plot_qc_histograms(ctx, obs_qc, prefix="st_qc")
    metrics = {
        "input_file": input_path.name,
        "input_observations": int(adata.n_obs),
        "input_features": int(adata.n_vars),
        "filtered_observations": int(filtered.n_obs),
        "filtered_features": int(filtered.n_vars),
        "removed_observations": int(adata.n_obs - filtered.n_obs),
        "removed_features": int(adata.n_vars - filtered.n_vars),
        "parameters": dict(ctx.parameters),
    }
    write_json(ctx.workspace / "qc_summary.json", {"status": "succeeded", "modality": "ST", **metrics})
    return {"metrics": metrics, "outputs": ["qc_summary.json", "observation_qc.csv", "feature_qc.csv", "filtered_result.h5ad", *figures]}
