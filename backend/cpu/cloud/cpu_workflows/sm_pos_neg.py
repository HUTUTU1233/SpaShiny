"""Strict CSV import and the installed SpatialMETA POS/NEG merge API.

No registration, normalization, coordinate rounding or ownership fallback.
Inputs have already been materialized by the normal analysis-scoped worker IO.
"""
from __future__ import annotations

import csv
from pathlib import Path

from .common import CPUWorkflowError, sha256_file, write_csv, write_json

MAX_PIXELS = 250_000
MAX_FEATURES = 100_000
MAX_MATRIX_CELLS = 50_000_000
OUTPUT_H5AD = "sm_pos_neg_merged.h5ad"


def inspect_csv(path):
    """Validate before pandas can rename duplicate headers or allocate a matrix."""
    import numpy as np

    path = Path(path)
    coordinates = set()
    count = 0
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, [])
        if len(header) < 3 or header[:2] != ["x", "y"]:
            raise CPUWorkflowError("SM_CSV_HEADER_INVALID", "Spectrum CSV must start with x,y followed only by numeric m/z columns (no TIC or metadata columns).")
        try:
            masses = np.asarray(header[2:], dtype=float)
        except ValueError as exc:
            raise CPUWorkflowError("SM_CSV_MZ_INVALID", "Every spectrum column after x,y must be a numeric m/z.") from exc
        if not np.isfinite(masses).all() or (masses <= 0).any() or len(np.unique(masses)) != len(masses):
            raise CPUWorkflowError("SM_CSV_MZ_INVALID", "m/z headers must be finite, positive and unique, including numerically equivalent labels.")
        if len(masses) > MAX_FEATURES:
            raise CPUWorkflowError("SM_CSV_TOO_LARGE", f"CSV exceeds {MAX_FEATURES:,} m/z columns.")
        zero_tic = 0
        for row in reader:
            if len(row) != len(header):
                raise CPUWorkflowError("SM_CSV_ROW_INVALID", f"{path.name}: row {count + 2} has the wrong number of columns.")
            try:
                values = np.asarray(row, dtype=float)
            except ValueError as exc:
                raise CPUWorkflowError("SM_CSV_VALUE_INVALID", f"{path.name}: row {count + 2} contains nonnumeric data.") from exc
            if not np.isfinite(values).all() or (values[2:] < 0).any():
                raise CPUWorkflowError("SM_CSV_VALUE_INVALID", f"{path.name}: row {count + 2} contains nonfinite values or negative intensities.")
            xy = tuple(values[:2])
            if xy in coordinates:
                raise CPUWorkflowError("DUPLICATE_COORDINATES", f"{path.name}: duplicate pixel coordinate {xy}; no automatic deduplication is performed.")
            coordinates.add(xy)
            total = values[2:].sum(dtype=float)
            if not np.isfinite(total):
                raise CPUWorkflowError("SM_CSV_VALUE_INVALID", f"{path.name}: nonfinite total intensity.")
            zero_tic += int(total == 0)
            count += 1
            if count > MAX_PIXELS or count * len(masses) > MAX_MATRIX_CELLS:
                raise CPUWorkflowError("SM_CSV_TOO_LARGE", "CSV exceeds the pixel or 50-million-intensity-cell limit; export a smaller ROI.")
    if not count:
        raise CPUWorkflowError("SM_CSV_EMPTY", f"{path.name}: spectrum CSV has no pixels.")
    return {"filename": path.name, "sha256": sha256_file(path), "pixels": count,
            "features": len(masses), "zero_tic_pixels": zero_tic}


def merge_csvs(pos_path, neg_path, workspace, *, provenance=None):
    import anndata as ad
    import numpy as np
    import pandas as pd
    import spatialmeta as smt
    from scipy import sparse

    workspace = Path(workspace)
    pos_info, neg_info = inspect_csv(pos_path), inspect_csv(neg_path)
    print("SpatialMETA: read_sm_csv_as_anndata(POS), read_sm_csv_as_anndata(NEG)", flush=True)
    pos = smt.pp.read_sm_csv_as_anndata(str(pos_path))
    neg = smt.pp.read_sm_csv_as_anndata(str(neg_path))
    cols = ["x_coord_original", "y_coord_original"]
    pk = pd.MultiIndex.from_frame(pos.obs[cols])
    nk = pd.MultiIndex.from_frame(neg.obs[cols])
    if not pk.is_unique or not nk.is_unique:
        raise CPUWorkflowError("DUPLICATE_COORDINATES", "SpatialMETA inputs contain duplicate coordinates.")
    common = pk[pk.isin(nk)]
    if not len(common):
        raise CPUWorkflowError("NO_COMMON_COORDINATES", "POS and NEG have no exact shared positive-intensity pixels after SpatialMETA import. Register them first; no coordinates are rounded or fabricated.")
    if len(common) * (pos.n_vars + neg.n_vars) > MAX_MATRIX_CELLS:
        raise CPUWorkflowError("MERGED_MATRIX_TOO_LARGE", "The official merge requires a dense intermediate; the merged ROI exceeds 50 million intensity cells. Choose a smaller ROI.")
    # The installed native function concatenates matrices in their row order;
    # membership alone is insufficient when input CSVs have different orders.
    pos = pos[pk.get_indexer(common), :].copy()
    neg = neg[nk.get_indexer(common), :].copy()
    if not np.array_equal(pos.obsm["spatial"], neg.obsm["spatial"]):
        raise CPUWorkflowError("COORDINATE_ORDER_MISMATCH", "POS/NEG coordinate ordering did not match.")
    print(f"SpatialMETA: merge_sm_pos_neg; common pixels={len(common)}", flush=True)
    merged = smt.pp.merge_sm_pos_neg(pos, neg)
    merged.var_names_make_unique()
    # Keep the original mass explicitly when unique names acquire suffixes.
    merged.var["m/z"] = pd.to_numeric(merged.var["name"], errors="raise").to_numpy()
    expected = sparse.hstack([pos.X, neg.X], format="csr")
    if (merged.shape != expected.shape or (merged.X != expected).nnz
            or not np.array_equal(merged.obsm["spatial"], pos.obsm["spatial"])):
        raise CPUWorkflowError("MERGE_VALIDATION_FAILED", "Native merge did not preserve the aligned input intensities and coordinates.")
    types = merged.var["type"].astype(str).tolist()
    if types != ["SM_pos"] * pos.n_vars + ["SM_neg"] * neg.n_vars:
        raise CPUWorkflowError("MERGE_VALIDATION_FAILED", "Native merge returned incorrect POS/NEG feature labels.")
    summary = {"native_reader": "spatialmeta.pp.read_sm_csv_as_anndata",
               "native_merge": "spatialmeta.pp.merge_sm_pos_neg",
               "pos": pos_info, "neg": neg_info, "shared_pixels": len(common),
               "pos_features": pos.n_vars, "neg_features": neg.n_vars,
               "pos_positive_pixels": len(pk), "neg_positive_pixels": len(nk),
               "pos_unmatched_positive_pixels": len(pk) - len(common),
               "neg_unmatched_positive_pixels": len(nk) - len(common),
               "coordinate_matching": "exact XY intersection in POS CSV order, after zero-TIC filtering",
               "normalization": "none", "registration": "none", "output": OUTPUT_H5AD}
    if provenance:
        summary["provenance"] = provenance
    merged.uns["spashiny_pos_neg_merge"] = {
        "native_merge": summary["native_merge"], "pos_sha256": pos_info["sha256"],
        "neg_sha256": neg_info["sha256"], "coordinate_matching": summary["coordinate_matching"],
        "normalization": "none", "registration": "none"}
    destination = workspace / OUTPUT_H5AD
    merged.write_h5ad(str(destination), compression="gzip")
    reloaded = ad.read_h5ad(destination)
    if (reloaded.shape != merged.shape or not reloaded.var_names.equals(merged.var_names)
            or (reloaded.X != merged.X).nnz or not np.array_equal(reloaded.obsm["spatial"], merged.obsm["spatial"])
            or reloaded.var["type"].astype(str).tolist() != types):
        raise CPUWorkflowError("H5AD_RELOAD_FAILED", "Saved H5AD failed the shape/intensity/coordinate/feature-type roundtrip check.")
    summary["h5ad_reload"] = "PASS"
    summary["h5ad_sha256"] = sha256_file(destination)
    write_json(workspace / "pos_neg_merge_summary.json", summary)
    write_csv(workspace / "pos_neg_matched_coordinates.csv", [
        {"row": i + 1, "x": xy[0], "y": xy[1]} for i, xy in enumerate(common.tolist())])
    print(f"H5AD reload PASS: {merged.n_obs} pixels x {merged.n_vars} features", flush=True)
    return summary


def run(ctx):
    import zipfile

    pos_name = str(ctx.parameters.get("pos_filename") or "")
    neg_name = str(ctx.parameters.get("neg_filename") or "")
    if not pos_name or not neg_name or pos_name == neg_name:
        raise CPUWorkflowError("POS_NEG_ROLE_REQUIRED", "Choose separate, distinctly named POS and NEG spectrum CSVs.")
    assets = ctx.downloaded_assets
    if len(assets) != 2:
        raise CPUWorkflowError("POS_NEG_PAIR_REQUIRED", "Upload exactly one POS and one NEG spectrum CSV.")
    by_name = {}
    for asset in assets:
        path = Path(str(asset.get("path") or ""))
        name = str(asset.get("filename") or path.name)
        if (Path(name).name != name or "\\" in name or Path(name).suffix.lower() != ".csv"
                or not path.is_file() or name in by_name):
            raise CPUWorkflowError("INPUT_INVALID", "POS/NEG inputs must be distinct materialized CSV files.")
        by_name[name] = path
    if set(by_name) != {pos_name, neg_name}:
        raise CPUWorkflowError("POS_NEG_ROLE_MISMATCH", "POS/NEG roles do not match these exact uploaded CSVs.")
    summary = merge_csvs(by_name[pos_name], by_name[neg_name], ctx.workspace)
    outputs = [OUTPUT_H5AD, "pos_neg_merge_summary.json", "pos_neg_matched_coordinates.csv"]
    with zipfile.ZipFile(ctx.workspace / "pos_neg_results.zip", "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for output in outputs:
            bundle.write(ctx.workspace / output, output)
    outputs.append("pos_neg_results.zip")
    return {"metrics": {"pixels": summary["shared_pixels"],
                        "features": summary["pos_features"] + summary["neg_features"], "h5ad_reload": "PASS"},
            "outputs": outputs}
