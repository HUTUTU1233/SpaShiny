"""Streaming imzML TIC/ROI utility with explicit, recorded export choices.

The spectrum CSV is exactly x,y,<numeric m/z>... for SpatialMETA's
read_sm_csv_as_anndata. Pixel/TIC/selection metadata is deliberately separate.
"""
from __future__ import annotations

import csv
import hashlib
import re
import uuid
from contextlib import contextmanager
from pathlib import Path

from .common import CPUWorkflowError, sha256_file, write_csv, write_json

MAX_PAIRS = 8
MAX_PIXELS = 250_000
MAX_FEATURES = 100_000
MAX_MATRIX_CELLS = 50_000_000
PREVIEW_WORKFLOW = "sm_tic_preview"
EXPORT_WORKFLOW = "sm_roi_export"


def pairs_from_assets(assets):
    pairs = {}
    for asset in assets:
        path = Path(str(asset.get("path") or ""))
        name = str(asset.get("filename") or path.name)
        if Path(name).name != name or "\\" in name or not path.is_file():
            raise CPUWorkflowError("INPUT_INVALID", "A materialized input file is unavailable or has an unsafe name.")
        suffix = Path(name).suffix.lower()
        if suffix not in {".imzml", ".ibd"}:
            raise CPUWorkflowError("INPUT_TYPE_MISMATCH", "Select only paired .imzML and .ibd files.")
        stem = Path(name).stem
        key = stem.casefold()
        pair = pairs.setdefault(key, {"name": stem, "id": hashlib.sha256(key.encode()).hexdigest()[:16]})
        if suffix in pair:
            raise CPUWorkflowError("DUPLICATE_INPUT", f"Duplicate input filename for {stem} ({suffix}).")
        pair[suffix] = path
    if not pairs or len(pairs) > MAX_PAIRS:
        raise CPUWorkflowError("PAIR_COUNT_INVALID", f"Select between 1 and {MAX_PAIRS} imzML/IBD pairs.")
    for pair in pairs.values():
        if ".imzml" not in pair or ".ibd" not in pair:
            raise CPUWorkflowError("PAIR_INCOMPLETE", f"{pair['name']}: the matching imzML/IBD file is missing (same filename stem required).")
        pair["source_sha256"] = {
            "imzml": sha256_file(pair[".imzml"]),
            "ibd": sha256_file(pair[".ibd"]),
        }
        safe_stem = re.sub(r"[^A-Za-z0-9_.-]", "_", pair["name"]).strip("._")[:100] or "sample"
        pair["csv_stem"] = safe_stem
    stems = [p["csv_stem"].casefold() for p in pairs.values()]
    for pair in pairs.values():
        if stems.count(pair["csv_stem"].casefold()) > 1:
            pair["csv_stem"] += "_" + pair["id"]
    return list(pairs.values())


@contextmanager
def open_parser(pair):
    from pyimzml.ImzMLParser import ImzMLParser

    with pair[".ibd"].open("rb") as handle:
        try:
            parser = ImzMLParser(str(pair[".imzml"]), ibd_file=handle)
            uuid_values = [node.get("value") for node in parser.root.iter()
                           if node.get("accession") == "IMS:1000080"]
            if uuid_values:
                expected = uuid.UUID(str(uuid_values[0]).strip("{}"))
                handle.seek(0)
                if handle.read(16) != expected.bytes:
                    raise CPUWorkflowError("IBD_UUID_MISMATCH", f"{pair['name']}: imzML and IBD UUIDs do not match. Select the original matching pair.")
            yield parser
        except CPUWorkflowError:
            raise
        except Exception as exc:
            raise CPUWorkflowError("IMZML_READ_FAILED", f"{pair['name']}: {type(exc).__name__}: {exc}") from exc


def spectrum(parser, index, name, *, allow_duplicates=False):
    import numpy as np

    mz, intensity = parser.getspectrum(index)
    mz = np.asarray(mz, dtype=float)
    intensity = np.asarray(intensity, dtype=float)
    if (mz.ndim != 1 or intensity.ndim != 1 or len(mz) != len(intensity)
            or not np.isfinite(mz).all() or not np.isfinite(intensity).all()
            or (mz <= 0).any()):
        raise CPUWorkflowError("SPECTRUM_INVALID", f"{name}: pixel {index + 1} contains invalid m/z or intensity values.")
    if (intensity < 0).any():
        raise CPUWorkflowError("NEGATIVE_INTENSITY", f"{name}: pixel {index + 1} contains negative intensities; no silent clipping is performed.")
    if not allow_duplicates and len(np.unique(mz)) != len(mz):
        raise CPUWorkflowError("DUPLICATE_MZ", f"{name}: pixel {index + 1} has repeated m/z values. Explicitly choose sum-equal-m/z for CSV export; originals are not changed.")
    return mz, intensity


def pixel_rows(parser, pair):
    import numpy as np

    if not parser.coordinates or len(parser.coordinates) > MAX_PIXELS:
        raise CPUWorkflowError("PIXEL_LIMIT", f"{pair['name']}: interactive preview requires 1–{MAX_PIXELS:,} pixels per dataset.")
    rows = []
    seen = set()
    for index, coords in enumerate(parser.coordinates):
        x, y, z = [float(value) for value in coords]
        if not np.isfinite([x, y, z]).all():
            raise CPUWorkflowError("COORDINATES_INVALID", f"{pair['name']}: invalid coordinates at pixel {index + 1}.")
        if (x, y, z) in seen:
            raise CPUWorkflowError("DUPLICATE_COORDINATES", f"{pair['name']}: repeated (x,y,z) coordinates at pixel {index + 1}.")
        seen.add((x, y, z))
        # A TIC is the sum of *all* acquired intensities, even when native
        # float32 m/z values repeat. CSV feature-axis policy belongs to export.
        mz, intensity = spectrum(parser, index, pair["name"], allow_duplicates=True)
        tic = float(intensity.sum(dtype=float))
        if not np.isfinite(tic):
            raise CPUWorkflowError("TIC_INVALID", f"{pair['name']}: non-finite TIC at pixel {index + 1}.")
        rows.append({"sample_id": pair["id"], "sample": pair["name"], "pixel_id": index + 1,
                     "x": x, "y": y, "z": z, "TIC": tic, "logTIC": float(np.log10(tic + 1)),
                     "duplicate_mz_entries": len(mz) - len(np.unique(mz))})
    return rows


def preview(ctx):
    datasets = []
    all_rows = []
    for pair in pairs_from_assets(ctx.downloaded_assets):
        print(f"TIC preview: {pair['name']}", flush=True)
        with open_parser(pair) as parser:
            rows = pixel_rows(parser, pair)
            accessions = {node.get("accession") for node in parser.root.iter()}
            polarity = ("pos" if "MS:1000130" in accessions else "neg" if "MS:1000129" in accessions else "unknown")
        all_rows.extend(rows)
        datasets.append({"id": pair["id"], "name": pair["name"], "csv_stem": pair["csv_stem"],
                         "source_sha256": pair["source_sha256"], "pixels": rows,
                         "z_values": sorted({r["z"] for r in rows}), "polarity": polarity,
                         "duplicate_mz_pixels": sum(r["duplicate_mz_entries"] > 0 for r in rows)})
    write_csv(ctx.workspace / "tic_pixels.csv", all_rows)
    write_json(ctx.workspace / "tic_preview.json", {"version": 1, "datasets": datasets,
                "coordinates": "original imzML pixel coordinates; display y axis is reversed only"})
    summary = {"pairs": len(datasets), "pixels": len(all_rows), "normalization": "none", "mz_binning": "none"}
    write_json(ctx.workspace / "tic_roi_summary.json", summary)
    return {"metrics": summary, "outputs": ["tic_preview.json", "tic_pixels.csv", "tic_roi_summary.json"]}


def selected_rows(parser, pair, selection, export_all):
    coordinates = parser.coordinates
    if not isinstance(selection, dict) or selection.get("source_sha256") != pair["source_sha256"]:
        raise CPUWorkflowError("ROI_SOURCE_MISMATCH", f"{pair['name']}: selection does not belong to these exact input files. Regenerate the TIC preview.")
    # Each export CSV must represent a single z plane. Never flatten a volume
    # into duplicate XY coordinates for the official SpatialMETA reader.
    z = selection.get("z")
    if isinstance(z, bool) or not isinstance(z, (float, int)):
        raise CPUWorkflowError("Z_PLANE_REQUIRED", f"{pair['name']}: choose one z plane for CSV export.")
    ids = selection.get("pixel_ids")
    if not export_all and (not isinstance(ids, list) or not ids):
        raise CPUWorkflowError("ROI_EMPTY", f"{pair['name']}: select at least one ROI pixel, or explicitly choose all pixels.")
    if export_all:
        indices = [i for i, c in enumerate(coordinates) if float(c[2]) == float(z)]
    else:
        if (len(ids) > MAX_PIXELS or any(type(v) is not int or v < 1 or v > len(coordinates) for v in ids)
                or len(set(ids)) != len(ids)):
            raise CPUWorkflowError("ROI_INVALID", f"{pair['name']}: invalid or repeated ROI pixel identifiers.")
        indices = sorted(v - 1 for v in ids)
    if not indices:
        raise CPUWorkflowError("ROI_EMPTY", f"{pair['name']}: no pixels in the selected z plane.")
    rows = []
    seen = set()
    for index in indices:
        x, y, pixel_z = map(float, coordinates[index])
        if pixel_z != float(z):
            raise CPUWorkflowError("ROI_Z_MISMATCH", f"{pair['name']}: ROI contains pixels from another z plane.")
        if (x, y) in seen:
            raise CPUWorkflowError("DUPLICATE_COORDINATES", f"{pair['name']}: selected ROI contains duplicate XY coordinates.")
        seen.add((x, y))
        rows.append({"pixel_id": index + 1, "x": x, "y": y, "z": pixel_z})
    return rows


def match_selected_coordinates(samples):
    if len(samples) < 2:
        raise CPUWorkflowError("PAIR_REQUIRED", "Shared-coordinate export requires at least two datasets.")
    common = set((r["x"], r["y"]) for r in samples[0]["rows"])
    for sample in samples[1:]:
        common.intersection_update((r["x"], r["y"]) for r in sample["rows"])
    if not common:
        raise CPUWorkflowError("NO_COMMON_COORDINATES", "No exact shared ROI coordinates. Register POS/NEG spatially first; coordinates are not rounded or fabricated.")
    order = [(r["x"], r["y"]) for r in samples[0]["rows"] if (r["x"], r["y"]) in common]
    for sample in samples:
        lookup = {(r["x"], r["y"]): r for r in sample["rows"]}
        sample["rows"] = [lookup[key] for key in order]
    return len(common)


def export_options(params):
    import math

    duplicate_policy = params.get("duplicate_mz_policy", "error")
    axis_mode = params.get("mz_axis_mode", "exact")
    if duplicate_policy not in {"error", "sum_exact"} or axis_mode not in {"exact", "fixed_da"}:
        raise CPUWorkflowError("MZ_POLICY_INVALID", "Choose a supported explicit duplicate/mass-axis policy.")
    width = params.get("mz_bin_width_da") if axis_mode == "fixed_da" else None
    if axis_mode == "fixed_da" and (type(width) not in (int, float) or not math.isfinite(width) or width <= 0):
        raise CPUWorkflowError("MZ_BIN_WIDTH_INVALID", "Fixed-Da export requires an explicit finite positive bin width.")
    return {"duplicate_mz_policy": duplicate_policy, "mz_axis_mode": axis_mode, "mz_bin_width_da": width}


def prepared_spectrum(parser, index, name, options):
    import numpy as np

    mz, intensities = spectrum(parser, index, name, allow_duplicates=True)
    duplicates = len(mz) - len(np.unique(mz))
    if duplicates and options["duplicate_mz_policy"] != "sum_exact":
        raise CPUWorkflowError("DUPLICATE_MZ", f"{name}: pixel {index + 1} contains repeated m/z. Select 'Sum intensities at exactly equal m/z' to export explicitly; no automatic deduplication is performed.")
    if options["mz_axis_mode"] == "fixed_da":
        width = float(options["mz_bin_width_da"])
        scaled = mz / width
        if not np.isfinite(scaled).all() or (scaled >= np.iinfo(np.int64).max).any():
            raise CPUWorkflowError("MZ_BIN_WIDTH_INVALID", "Bin width is too small for these masses.")
        # Grid origin is 0 Da. Bin k = [k*w,(k+1)*w), labeled by its center.
        keys = np.floor(scaled).astype(np.int64)
    else:
        keys = mz
    unique, inverse = np.unique(keys, return_inverse=True)
    values = np.bincount(inverse, weights=intensities, minlength=len(unique))
    if not np.isfinite(values).all():
        raise CPUWorkflowError("SPECTRUM_INVALID", f"{name}: aggregated intensity overflow.")
    return unique, values, {"duplicate_entries": duplicates, "source_entries": len(mz),
                            "export_entries": len(unique), "TIC": float(intensities.sum(dtype=float))}


def export_matrix(parser, pair, rows, destination, options=None):
    import numpy as np

    options = export_options(options or {})
    # Default is still exact native m/z. Binning never activates automatically.
    masses = set()
    for row in rows:
        mz, _, _ = prepared_spectrum(parser, row["pixel_id"] - 1, pair["name"], options)
        masses.update(map(float, mz))
        if len(masses) > MAX_FEATURES:
            raise CPUWorkflowError("MZ_UNION_TOO_LARGE", f"{pair['name']}: m/z union exceeds {MAX_FEATURES:,} features. Choose a smaller ROI or explicitly select a fixed-Da bin width; no automatic binning is performed.")
    if not masses:
        raise CPUWorkflowError("NO_MZ_FEATURES", f"{pair['name']}: selected spectra have no m/z features.")
    if len(rows) * len(masses) > MAX_MATRIX_CELLS:
        raise CPUWorkflowError("CSV_EXPORT_TOO_LARGE", f"{pair['name']}: CSV exceeds {MAX_MATRIX_CELLS:,} intensity cells. Select a smaller ROI or use a preprocessed matrix.")
    axis = np.asarray(sorted(masses))
    header_axis = (axis + 0.5) * float(options["mz_bin_width_da"]) if options["mz_axis_mode"] == "fixed_da" else axis
    header = [format(v, ".17g") for v in header_axis]
    if len(set(header)) != len(header):
        raise CPUWorkflowError("MZ_HEADER_COLLISION", "Distinct m/z values would produce duplicate CSV columns.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["x", "y", *header])
        for row in rows:
            mz, intensities, info = prepared_spectrum(parser, row["pixel_id"] - 1, pair["name"], options)
            values = np.zeros(len(axis), dtype=float)
            values[np.searchsorted(axis, mz)] = intensities
            writer.writerow([format(row["x"], ".17g"), format(row["y"], ".17g"), *map(lambda v: format(v, ".17g"), values)])
            row["TIC"] = info["TIC"]
            row["duplicate_mz_entries_summed"] = info["duplicate_entries"]
            row["spectral_entries_aggregated"] = info["source_entries"] - info["export_entries"]
    return len(axis)


def export(ctx):
    import zipfile

    params = ctx.parameters
    options = export_options(params)
    selections = params.get("selections")
    if not isinstance(selections, dict):
        raise CPUWorkflowError("ROI_REQUIRED", "A TIC preview selection is required.")
    pairs = pairs_from_assets(ctx.downloaded_assets)
    merge_requested = params.get("merge_pos_neg") is True
    pos_id, neg_id = str(params.get("pos_dataset_id") or ""), str(params.get("neg_dataset_id") or "")
    if merge_requested and (len(pairs) != 2 or pos_id == neg_id or {pos_id, neg_id} != {p["id"] for p in pairs}):
        raise CPUWorkflowError("POS_NEG_ROLE_REQUIRED", "Combined export/merge requires exactly two datasets with distinct explicit POS and NEG roles.")
    if set(selections) != {p["id"] for p in pairs}:
        raise CPUWorkflowError("ROI_SOURCE_MISMATCH", "ROI datasets and uploaded input pairs do not match exactly.")
    export_all = params.get("export_all") is True
    samples = []
    for pair in pairs:
        with open_parser(pair) as parser:
            if merge_requested:
                accessions = {node.get("accession") for node in parser.root.iter()}
                wrong = "MS:1000129" if pair["id"] == pos_id else "MS:1000130"
                if wrong in accessions:
                    raise CPUWorkflowError("POS_NEG_POLARITY_MISMATCH", f"{pair['name']}: selected role conflicts with imzML ion-polarity metadata.")
            rows = selected_rows(parser, pair, selections[pair["id"]], export_all)
        samples.append({"pair": pair, "rows": rows})
    common_count = match_selected_coordinates(samples) if params.get("match_common_coordinates") is True else None
    outputs = []
    reports = []
    for sample in samples:
        pair, rows = sample["pair"], sample["rows"]
        filename = f"{pair['csv_stem']}.csv"
        csv_path = ctx.workspace / "spectra" / filename
        print(f"ROI spectrum export: {pair['name']}, {len(rows)} pixels", flush=True)
        with open_parser(pair) as parser:
            n_features = export_matrix(parser, pair, rows, csv_path, options)
            selected = {r["pixel_id"] for r in rows}
            mask = [{"pixel_id": i + 1, "x": c[0], "y": c[1], "z": c[2], "in_roi": int(i + 1 in selected)}
                    for i, c in enumerate(parser.coordinates)]
        metadata_path = ctx.workspace / "roi_metadata" / filename
        mask_path = ctx.workspace / "roi_masks" / filename
        write_csv(metadata_path, rows)
        write_csv(mask_path, mask)
        outputs.extend([csv_path.relative_to(ctx.workspace).as_posix(), metadata_path.relative_to(ctx.workspace).as_posix(), mask_path.relative_to(ctx.workspace).as_posix()])
        reports.append({"id": pair["id"], "sample": pair["name"], "spectrum_csv": outputs[-3],
                        "roi_metadata_csv": outputs[-2], "roi_mask_csv": outputs[-1],
                        "pixels": len(rows), "features": n_features, "zero_tic_pixels": sum(r["TIC"] == 0 for r in rows),
                        "source_sha256": pair["source_sha256"], "csv_sha256": sha256_file(csv_path),
                        "duplicate_mz_pixels_summed": sum(r["duplicate_mz_entries_summed"] > 0 for r in rows),
                        "mz_processing": options})
    summary = {"datasets": reports, "export_all": export_all, "common_coordinates": common_count,
               "format": "x,y,<numeric m/z>...", "normalization": "none", "mz_processing": options,
               "mz_axis": ("exact native union; absent m/z intensity is 0" if options["mz_axis_mode"] == "exact"
                           else "explicit fixed-Da sum; origin 0; bins [k*w,(k+1)*w); numeric headers are bin centers"),
               "reader_note": "SpatialMETA filters pixels with total intensity <= 0. Match POS/NEG coordinates after reading both CSVs.",
               "preview_job_id": str(params.get("preview_job_id") or "")}
    write_json(ctx.workspace / "tic_roi_summary.json", summary)
    outputs.append("tic_roi_summary.json")
    if merge_requested:
        from .sm_pos_neg import OUTPUT_H5AD, merge_csvs

        paths = {report["id"]: ctx.workspace / report["spectrum_csv"] for report in reports}
        merge_summary = merge_csvs(paths[pos_id], paths[neg_id], ctx.workspace,
                                  provenance={"source": "same-job ROI CSV export", "mz_processing": options})
        summary["pos_neg_merge"] = {"output": OUTPUT_H5AD, "shared_pixels": merge_summary["shared_pixels"], "h5ad_reload": "PASS"}
        write_json(ctx.workspace / "tic_roi_summary.json", summary)
        outputs.extend([OUTPUT_H5AD, "pos_neg_merge_summary.json", "pos_neg_matched_coordinates.csv"])
    with zipfile.ZipFile(ctx.workspace / "spatialmeta_csv.zip", "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as bundle:
        for output in outputs:
            bundle.write(ctx.workspace / output, output)
    outputs.append("spatialmeta_csv.zip")
    return {"metrics": {"datasets": len(reports), "pixels": sum(r["pixels"] for r in reports)}, "outputs": outputs}
