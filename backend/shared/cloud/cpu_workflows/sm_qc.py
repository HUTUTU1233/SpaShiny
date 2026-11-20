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
    try:
        parser = ImzMLParser(str(imzml))
        coordinates = list(parser.coordinates)
        if not coordinates:
            raise CPUWorkflowError("SM_COORDINATES_MISSING", "imzML contains no readable coordinates.")
        mzs, intensities = parser.getspectrum(0)
    except CPUWorkflowError:
        raise
    except Exception as exc:
        raise CPUWorkflowError("INPUT_READ_FAILED", f"Could not parse imzML/ibd pair: {imzml.name}") from exc
    if len(mzs) == 0:
        raise CPUWorkflowError("SM_MZ_METADATA_MISSING", "imzML contains no readable m/z values.")
    obs_rows = [
        {"observation_id": f"pixel_{idx}", "x": coord[0], "y": coord[1], "z": coord[2] if len(coord) > 2 else 1}
        for idx, coord in enumerate(coordinates)
    ]
    feature_rows = [{"feature_id": f"mz_{idx}", "mz": float(value)} for idx, value in enumerate(mzs)]
    write_csv(ctx.workspace / "observation_qc.csv", obs_rows)
    write_csv(ctx.workspace / "feature_qc.csv", feature_rows)
    _write_imzml_h5ad(ctx, parser, coordinates)
    metrics = {
        "input_file": imzml.name,
        "ibd_file": ibd.name,
        "input_observations": int(len(coordinates)),
        "input_features": int(len(mzs)),
        "mz_features_readable": int(len(mzs)),
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


def _write_imzml_h5ad(ctx: CPUWorkflowContext, parser, coordinates) -> None:
    try:
        import anndata as ad
        import numpy as np
        import pandas as pd

        spectra = []
        mzs = None
        for idx in range(len(coordinates)):
            current_mz, intensities = parser.getspectrum(idx)
            if mzs is None:
                mzs = current_mz
            spectra.append(intensities)
        x = np.vstack(spectra)
        obs = pd.DataFrame(index=[f"pixel_{idx}" for idx in range(len(coordinates))])
        obs["x"] = [coord[0] for coord in coordinates]
        obs["y"] = [coord[1] for coord in coordinates]
        var = pd.DataFrame(index=[str(float(value)) for value in mzs])
        var["mz"] = [float(value) for value in mzs]
        ad.AnnData(X=x, obs=obs, var=var).write_h5ad(ctx.workspace / "filtered_result.h5ad")
    except Exception as exc:
        raise CPUWorkflowError("SM_H5AD_EXPORT_FAILED", "Could not export imzML QC matrix to h5ad.") from exc
