from __future__ import annotations

from pathlib import Path

from .common import (
    CPUWorkflowContext,
    CPUWorkflowError,
    apply_basic_filters,
    matrix_qc_frames,
    numeric_mz_values_from_adata,
    plot_qc_histograms,
    read_matrix_input,
    select_asset,
    select_assets,
    write_csv,
    write_json,
)


def run(ctx: CPUWorkflowContext) -> dict:
    imzml = select_asset(ctx, suffixes=(".imzml",), roles=("sm_pos_imzml", "sm_neg_imzml", "sm_raw_imzml"), required=False)
    if imzml is not None:
        return _run_imzml(ctx, imzml)
    input_path = select_asset(
        ctx,
        suffixes=(".h5ad", ".h5", ".hdf5"),
        roles=("sm_raw_h5ad", "sm_batch_raw", "joint_raw", "primary"),
        label="SM matrix",
    )
    adata = read_matrix_input(input_path, modality="SM")
    mz_values = numeric_mz_values_from_adata(adata)
    if not mz_values:
        raise CPUWorkflowError("SM_MZ_METADATA_MISSING", "SM input does not expose readable m/z feature values.")
    obs_qc, feature_qc = matrix_qc_frames(adata)
    filtered, obs_mask, var_mask = apply_basic_filters(adata, obs_qc, feature_qc, ctx.parameters)
    write_csv(ctx.workspace / "observation_qc.csv", obs_qc.to_dict(orient="records"))
    feature_records = feature_qc.to_dict(orient="records")
    for index, value in enumerate(mz_values[: len(feature_records)]):
        feature_records[index]["mz"] = value
    write_csv(ctx.workspace / "feature_qc.csv", feature_records)
    filtered.write_h5ad(ctx.workspace / "filtered_result.h5ad")
    figures = plot_qc_histograms(ctx, obs_qc, prefix="sm_qc")
    metrics = {
        "input_file": input_path.name,
        "input_observations": int(adata.n_obs),
        "input_features": int(adata.n_vars),
        "filtered_observations": int(filtered.n_obs),
        "filtered_features": int(filtered.n_vars),
        "mz_features_readable": int(len(mz_values)),
        "parameters": dict(ctx.parameters),
    }
    write_json(ctx.workspace / "qc_summary.json", {"status": "succeeded", "modality": "SM", **metrics})
    return {"metrics": metrics, "outputs": ["qc_summary.json", "observation_qc.csv", "feature_qc.csv", "filtered_result.h5ad", *figures]}


def _run_imzml(ctx: CPUWorkflowContext, imzml: Path) -> dict:
    ibd = _paired_ibd(ctx, imzml)
    if ibd is None:
        raise CPUWorkflowError("SM_IBD_PAIR_MISSING", f"imzML input is missing its paired ibd file: {imzml.name}")
    try:
        from pyimzml.ImzMLParser import ImzMLParser
    except Exception as exc:
        raise CPUWorkflowError("DEPENDENCY_MISSING", "pyimzML is required to validate imzML inputs.") from exc
    ibd_handle = ibd.open("rb")
    try:
        parser = ImzMLParser(str(imzml), ibd_file=ibd_handle)
        coordinates = list(parser.coordinates)
        if not coordinates:
            raise CPUWorkflowError("SM_COORDINATES_MISSING", "imzML contains no readable coordinates.")
    except CPUWorkflowError:
        ibd_handle.close()
        raise
    except Exception as exc:
        ibd_handle.close()
        raise CPUWorkflowError("INPUT_READ_FAILED", f"Could not parse imzML/ibd pair: {imzml.name}") from exc
    try:
        data = _write_imzml_h5ad(ctx, parser, coordinates)
    finally:
        ibd_handle.close()
    obs_qc, feature_qc = matrix_qc_frames(data)
    filtered, _, _ = apply_basic_filters(data, obs_qc, feature_qc, ctx.parameters)
    filtered.write_h5ad(ctx.workspace / "filtered_result.h5ad")
    for col in ("x_coord_original", "y_coord_original"):
        obs_qc[col] = data.obs[col].to_numpy()
    feature_qc["mz"] = data.var["m/z"].to_numpy()
    write_csv(ctx.workspace / "observation_qc.csv", obs_qc.to_dict("records"))
    write_csv(ctx.workspace / "feature_qc.csv", feature_qc.to_dict("records"))
    metrics = {
        "input_file": imzml.name,
        "ibd_file": ibd.name,
        "input_observations": int(len(coordinates)),
        "input_features": int(data.n_vars),
        "mz_features_readable": int(data.n_vars),
        "filtered_observations": int(filtered.n_obs),
        "filtered_features": int(filtered.n_vars),
        "native_nonpositive_pixel_filter_count": int(len(coordinates) - data.n_obs),
        "reader": "spatialmeta.pp.get_mz_reference + read_sm_imzml_as_anndata (native defaults)",
    }
    write_json(ctx.workspace / "qc_summary.json", {"status": "succeeded", "modality": "SM", **metrics})
    return {"metrics": metrics, "outputs": ["qc_summary.json", "observation_qc.csv", "feature_qc.csv", "filtered_result.h5ad"]}


def _paired_ibd(ctx: CPUWorkflowContext, imzml: Path) -> Path | None:
    same_stem = imzml.with_suffix(".ibd")
    if same_stem.is_file():
        return same_stem
    for path in select_assets(ctx, suffixes=(".ibd",), roles=("sm_pos_ibd", "sm_neg_ibd", "sm_raw_ibd")):
        if path.stem == imzml.stem or len(select_assets(ctx, suffixes=(".ibd",))) == 1:
            return path
    return None


def _write_imzml_h5ad(ctx: CPUWorkflowContext, parser, coordinates):
    try:
        import numpy as np
        import spatialmeta as smt
        from cloud.spatialmeta_runtime_compat import pandas_legacy_api

        # SPATIALMETA_PARITY F08: imzML spectra need not share the first pixel's
        # m/z axis. Native ppm binning preserves the actual union and coordinates.
        with pandas_legacy_api():
            reference = smt.pp.get_mz_reference(parser)
            data = smt.pp.read_sm_imzml_as_anndata(parser, reference).copy()
        spatial = np.asarray(data.obsm["spatial"])
        if spatial.shape != (data.n_obs, 2) or not np.isfinite(spatial).all():
            raise ValueError("Native imzML reader returned invalid spatial coordinates.")
        data.var["type"] = "SM"
        data.uns["spashiny_input_reader"] = "spatialmeta native imzML ppm reference; all spectra"
        return data
    except Exception as exc:
        raise CPUWorkflowError("SM_H5AD_EXPORT_FAILED", "Could not export imzML QC matrix to h5ad.") from exc
