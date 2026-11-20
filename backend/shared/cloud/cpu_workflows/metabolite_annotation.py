from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from typing import Any
import zipfile

from .common import (
    CPUWorkflowContext,
    CPUWorkflowError,
    numeric_mz_values_from_adata,
    read_h5ad,
    read_table,
    select_asset,
    sha256_file,
    write_csv,
    write_json,
)


DEFAULT_ENRICHMENT_ROOT = Path(os.environ.get("SPASHINY_ENRICHMENT_ROOT") or "/workspace/data/enrichment")
DEFAULT_RAMP_SQLITE = DEFAULT_ENRICHMENT_ROOT / "metabolite" / "ramp" / "RaMP_SQLite_v3.0.7.sqlite"
Y7_T_EXAMPLE_ROOT = Path("/workspace/data/examples/raw/spatial_metabolomics/sample-1_Y7_T/SM")


ADDUCTS = {
    "positive": [
        ("[M+H]+", 1.007276466621),
        ("[M+Na]+", 22.989218),
        ("[M+K]+", 38.963158),
        ("[M+NH4]+", 18.033823),
    ],
    "negative": [
        ("[M-H]-", -1.007276466621),
        ("[M+Cl]-", 34.969402),
        ("[M+FA-H]-", 44.998201),
        ("[M+CH3COO]-", 59.013851),
    ],
}


def run(ctx: CPUWorkflowContext) -> dict:
    """Run the canonical SpatialMETA annotation procedure for a scoped SM H5AD.

    Historical RaMP helpers remain below so old results remain interpretable,
    but new public jobs never dispatch to them.
    """
    ctx.ensure_dirs()
    try:
        import pandas as pd
        import spatialmeta as smt
    except Exception as exc:
        raise CPUWorkflowError(
            "SPATIALMETA_DEPENDENCY_MISSING",
            "The SpatialMETA runtime is required for metabolite annotation.",
        ) from exc

    adduct_method = str(ctx.parameters.get("adduct_method") or "add").strip()
    adduct_type = str(ctx.parameters.get("adduct_type") or "H").strip()
    try:
        tolerance_ppm = float(ctx.parameters.get("tolerance_ppm") or 5.0)
    except (TypeError, ValueError):
        tolerance_ppm = 5.0
    if adduct_method not in {"add", "sub"} or not adduct_type or tolerance_ppm <= 0:
        raise CPUWorkflowError(
            "SPATIALMETA_ANNOTATION_PARAMETERS_INVALID",
            "SpatialMETA annotation requires adduct_method ('add' or 'sub'), adduct_type, and positive tolerance_ppm.",
        )
    input_path = select_asset(
        ctx,
        suffixes=(".h5ad",),
        roles=("sm_qc_input_h5ad", "sm_raw_h5ad", "sm_input_h5ad", "primary"),
        label="spatial-metabolomics H5AD",
    )
    # The original SpatialMETA tutorial annotates SM_pos with addition adducts
    # and SM_neg with subtraction adducts. Preserve that contract when a joint
    # SM H5AD carries the original feature-type labels.
    input_adata = read_h5ad(input_path)
    input_observation_count = int(getattr(input_adata, "n_obs", 0) or 0)
    input_var_count = int(getattr(input_adata, "n_vars", 0) or 0)
    input_type_counts = _spatialmeta_feature_type_counts(input_adata)
    polarity = "positive" if adduct_method == "add" else "negative"
    adata_sm = _spatial_metabolomics_view(input_adata, polarity=polarity)
    if int(getattr(adata_sm, "n_vars", 0) or 0) <= 0:
        raise CPUWorkflowError("SM_FEATURES_EMPTY", "The selected H5AD has no spatial-metabolomics features.")

    # The Test compose may bind an independently repaired, provenance-checked
    # copy over SpatialMETA's packaged resource.  This merely proves the
    # native function will read that declared file; it never replaces or
    # reimplements the SpatialMETA algorithm.
    hmdb_resource_provenance = _validated_hmdb_repair_provenance()
    native_started = time.monotonic()
    try:
        annotation_df = smt.pp.metabolite_annotation(
            adata_sm,
            adduct_type=adduct_type,
            adduct_method=adduct_method,
            tolerance_ppm=tolerance_ppm,
            inplace=True,
        )
    except Exception as exc:
        raise CPUWorkflowError(
            "SPATIALMETA_METABOLITE_ANNOTATION_FAILED",
            "SpatialMETA metabolite_annotation did not complete for this H5AD.",
        ) from exc
    native_runtime_seconds = round(time.monotonic() - native_started, 6)

    if annotation_df is None:
        annotation_df = adata_sm.var.copy()
    if not isinstance(annotation_df, pd.DataFrame):
        annotation_df = pd.DataFrame(annotation_df)

    # Keep the direct native result in the tabular artifact.  SpatialMETA's
    # HMDB fields may mix None, NaN, numeric IDs, and strings in an object
    # column; h5py cannot persist that mixture as a vlen string dataset.  The
    # conversion below affects only the serialised AnnData metadata, after the
    # native CSV has been written, and leaves matching/annotation unchanged.
    annotation_df.to_csv(ctx.workspace / "metabolite_annotations.csv", index=False)
    serialised_object_columns = _stringify_var_object_columns_for_h5ad(adata_sm)
    adata_sm.write_h5ad(ctx.workspace / "annotated_result.h5ad")
    accession = annotation_df.get("accession")
    summary = {
        "status": "succeeded",
        "source_api": "spatialmeta.pp.metabolite_annotation",
        "input_filename": input_path.name,
        "input_h5ad_sha256": sha256_file(input_path),
        "input_observation_count": input_observation_count,
        "input_total_feature_count": input_var_count,
        "input_feature_type_counts": input_type_counts,
        "input_feature_count": int(adata_sm.n_vars),
        "annotation_rows": int(len(annotation_df)),
        "matched_feature_count": int(accession.notna().sum()) if accession is not None else 0,
        "unmapped_feature_count": int(accession.isna().sum()) if accession is not None else int(len(annotation_df)),
        "ambiguous_candidate_count": None,
        "ambiguity_reporting": "not provided by the native SpatialMETA metabolite_annotation API",
        "adduct_method": adduct_method,
        "adduct_type": adduct_type,
        "tolerance_ppm": tolerance_ppm,
        "annotation_columns": [str(column) for column in annotation_df.columns],
        "annotated_h5ad_object_columns_stringified": serialised_object_columns,
        "annotated_h5ad_null_representation": "empty string in object metadata columns only",
        "inplace": True,
        "native_annotation_runtime_seconds": native_runtime_seconds,
        "hmdb_resource_provenance": hmdb_resource_provenance,
    }
    write_json(ctx.workspace / "annotation_summary.json", summary)
    return {
        "metrics": summary,
        "outputs": ["metabolite_annotations.csv", "annotation_summary.json", "annotated_result.h5ad"],
    }


def _spatial_metabolomics_view(adata, *, polarity: str):
    """Select SM features only; this does not alter SpatialMETA's annotation math."""
    var = getattr(adata, "var", None)
    if var is None:
        raise CPUWorkflowError("SM_METADATA_MISSING", "The H5AD has no feature metadata for spatial-metabolomics annotation.")
    if "type" not in var.columns:
        # Dedicated SM H5ADs need not carry a joint-data feature type column.
        return adata.copy()
    feature_type = var["type"].astype(str).str.strip().str.upper()
    polarity_labels = {"SM_POS", "SM_POSITIVE"} if polarity == "positive" else {"SM_NEG", "SM_NEGATIVE"}
    sm_mask = feature_type.isin(polarity_labels)
    if not bool(sm_mask.any()):
        # For dedicated SM H5ADs without polarity-specific labels, retain all
        # generic SM features rather than inferring a new chemistry rule.
        sm_mask = feature_type.str.startswith("SM") | feature_type.isin({"METABOLITE", "METABOLITES", "SPATIAL_METABOLOMICS"})
    if bool(sm_mask.any()):
        return adata[:, sm_mask.to_numpy()].copy()
    raise CPUWorkflowError("SM_FEATURES_NOT_FOUND", "The H5AD type column contains no spatial-metabolomics features.")


def _spatialmeta_feature_type_counts(adata) -> dict[str, int]:
    """Describe the input feature types for provenance without changing data."""
    var = getattr(adata, "var", None)
    if var is None or "type" not in var.columns:
        return {}
    counts = var["type"].astype(str).value_counts(dropna=False)
    return {str(key): int(value) for key, value in counts.items()}


def _stringify_var_object_columns_for_h5ad(adata) -> list[str]:
    """Make only mixed object metadata serialisable by h5py.

    This is deliberately a post-annotation persistence step.  The native
    DataFrame is saved first and the original SpatialMETA candidate logic is
    never inspected, sorted, filtered, or recomputed here.
    """
    try:
        import pandas as pd
    except Exception as exc:  # pragma: no cover - pandas is a native dependency
        raise CPUWorkflowError("PANDAS_DEPENDENCY_MISSING", "Pandas is required to persist the annotated H5AD.") from exc
    var = getattr(adata, "var", None)
    if var is None:
        return []
    changed: list[str] = []
    for column in var.columns:
        values = var[column]
        if str(getattr(values, "dtype", "")) != "object":
            continue

        def _safe_string(value: Any) -> str:
            if value is None:
                return ""
            try:
                if bool(pd.isna(value)):
                    return ""
            except (TypeError, ValueError):
                pass
            return value if isinstance(value, str) else str(value)

        var[column] = values.map(_safe_string).astype(str)
        changed.append(str(column))
    return changed


def _validated_hmdb_repair_provenance() -> dict[str, Any] | None:
    """Validate the explicitly mounted Test HMDB repair before native use.

    No environment variable means no override and normal SpatialMETA behavior.
    The helper only reads proof data and verifies the exact resource that the
    unmodified SpatialMETA function resolves from its own module path.
    """
    configured = os.environ.get("SPASHINY_SPATIALMETA_HMDB_REPAIR_PROVENANCE", "").strip()
    if not configured:
        return None
    provenance_path = Path(configured)
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        expected_hash = str(provenance["repaired_sha256"])
        import spatialmeta.preprocess._metabolite_annotation as native_annotation

        active_path = (Path(native_annotation.MODULE_PATH) / ".." / "data" / "hmdb.csv").resolve()
        active_hash = sha256_file(active_path)
    except Exception as exc:
        raise CPUWorkflowError(
            "SPATIALMETA_HMDB_REPAIR_PROVENANCE_INVALID",
            "The configured Test HMDB repair provenance cannot be verified.",
        ) from exc
    if active_hash != expected_hash:
        raise CPUWorkflowError(
            "SPATIALMETA_HMDB_REPAIR_RESOURCE_MISMATCH",
            "The active SpatialMETA HMDB resource does not match the approved Test repair provenance.",
        )
    return {
        "provenance_file": str(provenance_path),
        "active_resource_path": str(active_path),
        "original_sha256": provenance.get("original_sha256"),
        "original_size_bytes": provenance.get("original_size_bytes"),
        "repaired_sha256": provenance.get("repaired_sha256"),
        "repaired_size_bytes": provenance.get("repaired_size_bytes"),
        "removed_bytes": provenance.get("removed_bytes"),
        "removed_complete_records": provenance.get("removed_complete_records"),
        "removed_incomplete_terminal_fragment": provenance.get("removed_incomplete_terminal_fragment"),
        "original_complete_record_count": provenance.get("original_complete_record_count"),
        "repaired_record_count": provenance.get("repaired_record_count"),
        "strict_prefix_identity_verified": provenance.get("strict_prefix_identity_verified"),
        "spatialmeta_version": provenance.get("spatialmeta_version"),
    }


def _selected_methods(ctx: CPUWorkflowContext) -> list[str]:
    raw = ctx.parameters.get("annotation_methods") or ctx.parameters.get("methods") or ctx.parameters.get("annotation_method")
    if raw is None:
        return ["ms1_ramp_exact_mass"]
    values = raw if isinstance(raw, list) else re.split(r"[,;\s]+", str(raw))
    methods = [str(item).strip() for item in values if str(item).strip()]
    return methods or ["ms1_ramp_exact_mass"]


def _method_catalog(ramp_path: Path) -> dict[str, dict[str, Any]]:
    ramp_ready = ramp_path.is_file()
    return {
        "ms1_ramp_exact_mass": {
            "label": "MS1 accurate mass + adduct candidates using local RaMP",
            "can_run_now": ramp_ready,
            "required_files": "m/z table, H5AD with numeric var m/z, or imzML/ibd pair; RaMP SQLite with chem_props/source tables",
            "current_resource": str(ramp_path) if ramp_ready else "",
            "notes": "Works for current Y7_T MSI data. Produces candidate annotations and ambiguity flags.",
        },
        "explicit_kegg_id_mapping": {
            "label": "Explicit KEGG Compound ID mapping",
            "can_run_now": ramp_ready,
            "required_files": "CSV/TSV with KEGG.ID column; RaMP SQLite source table",
            "current_resource": str(ramp_path) if ramp_ready else "",
            "notes": "Available through the existing metabolite enrichment path; listed here for user guidance.",
        },
        "ms1_isotope_adduct_grouping": {
            "label": "MS1 isotope/adduct grouping",
            "can_run_now": False,
            "required_files": "centroid feature table plus intensity matrix across spots/samples; polarity; spatial co-localization settings",
            "current_resource": "",
            "notes": "Not enabled in this minimal restore; LC-MS CAMERA/CliqueMS co-elution logic is not directly valid for MSI without adaptation.",
        },
        "hmdb_exact_mass_local": {
            "label": "HMDB exact-mass candidate search",
            "can_run_now": False,
            "required_files": "offline HMDB XML/CSV/SDF with exact mass, formula, names, HMDB ID and KEGG cross-references",
            "current_resource": "",
            "notes": "Upload a licensed/offline HMDB snapshot before enabling.",
        },
        "lipidmaps_exact_mass_local": {
            "label": "LIPID MAPS exact-mass candidate search",
            "can_run_now": False,
            "required_files": "offline LMSD SDF/TSV/RDF with exact mass, formula, lipid class, LM_ID and cross-references",
            "current_resource": "",
            "notes": "Useful for MSI lipid candidates after a local LMSD resource is installed.",
        },
        "msms_spectral_library": {
            "label": "MS/MS spectral library matching",
            "can_run_now": False,
            "required_files": "MS2 spectra in MGF/MSP plus local MassBank/MoNA/NIST/METLIN-compatible spectral library",
            "current_resource": "",
            "notes": "Current Y7_T imzML audit found MS1 only, so this cannot run on the example data.",
        },
        "sirius_csi_fingerid": {
            "label": "SIRIUS / CSI:FingerID style in-silico MS/MS annotation",
            "can_run_now": False,
            "required_files": "MS2 spectra, precursor m/z, polarity, formula candidates, local executable/models/databases",
            "current_resource": "",
            "notes": "Requires an offline tool installation and MS2 evidence.",
        },
        "metdna3": {
            "label": "MetDNA3 contextual annotation",
            "can_run_now": False,
            "required_files": "LC-MS feature table with m/z, retention time, MS2 spectra, reliable seed annotations, and MetDNA3 resources/modules",
            "current_resource": "",
            "notes": "Not runnable on current Y7_T MSI MS1-only example data.",
        },
        "metgenx": {
            "label": "MetGenX structure-informed annotation",
            "can_run_now": False,
            "required_files": "MS2 MGF/MSP, precursor m/z/formula/polarity, model weights, structure databases and Java/Python runtime",
            "current_resource": "",
            "notes": "Not runnable without MS2 spectra and offline model/database resources.",
        },
        "gnps_molecular_networking": {
            "label": "GNPS-style molecular networking",
            "can_run_now": False,
            "required_files": "MS2 spectra in MGF plus local networking workflow/library resources",
            "current_resource": "",
            "notes": "Current server runtime must remain offline; online GNPS workflows are not used.",
        },
        "gcms_libraries": {
            "label": "GC-MS libraries (GMD/Fiehn/NIST EI)",
            "can_run_now": False,
            "required_files": "GC-EI-MS spectra and retention index data plus licensed/offline spectral libraries",
            "current_resource": "",
            "notes": "Not applicable to current MALDI-MSI imzML/ibd example data.",
        },
    }


def _requirement_rows(catalog: dict[str, dict[str, Any]], selected: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    selected_set = set(selected)
    for method_id, item in catalog.items():
        can_run = bool(item["can_run_now"])
        rows.append(
            {
                "method_id": method_id,
                "label": item["label"],
                "status": "SELECTED_AVAILABLE" if method_id in selected_set and can_run else "SELECTED_REQUIRES_FILES" if method_id in selected_set else "AVAILABLE" if can_run else "REQUIRES_FILES",
                "can_run_now": can_run,
                "required_files": item["required_files"],
                "current_resource": item["current_resource"],
                "notes": item["notes"],
            }
        )
    return rows


def _ramp_sqlite_path(ctx: CPUWorkflowContext) -> Path:
    raw = (
        ctx.parameters.get("ramp_sqlite_path")
        or ctx.parameters.get("database_path")
        or ctx.parameters.get("metabolite_db_path")
        or os.environ.get("SPASHINY_RAMP_SQLITE")
        or DEFAULT_RAMP_SQLITE
    )
    if "://" in str(raw):
        raise CPUWorkflowError("REMOTE_DATABASE_DISABLED", "Runtime network databases are disabled for metabolite annotation.")
    return Path(str(raw)).expanduser().resolve()


def _query_mz(ctx: CPUWorkflowContext, *, max_query_mz: int) -> list[tuple[str, float, str]]:
    path = _example_imzml_path(ctx)
    if path is None:
        path = select_asset(
            ctx,
            suffixes=(".csv", ".tsv", ".txt", ".h5ad", ".imzml"),
            roles=("mz_table", "feature_table", "sm_raw_h5ad", "sm_pos_imzml", "sm_neg_imzml", "primary"),
            required=False,
        )
    if path is None and ctx.parameters.get("mz_values"):
        raw = ctx.parameters["mz_values"]
        raw_values = raw if isinstance(raw, list) else str(raw).replace(";", ",").split(",")
        values = []
        for idx, value in enumerate(raw_values):
            try:
                values.append((f"mz_{idx}", float(value), "parameter:mz_values"))
            except Exception:
                continue
        return values[:max_query_mz]
    if path is None:
        return []
    suffix = path.suffix.lower()
    if suffix == ".h5ad":
        return [(f"feature_{idx}", float(mz), path.name) for idx, mz in enumerate(numeric_mz_values_from_adata(read_h5ad(path))[:max_query_mz])]
    if suffix == ".imzml":
        return _mz_from_imzml(path, ctx=ctx, max_query_mz=max_query_mz)
    df = read_table(path)
    mz_col = _first_existing_column(df.columns, [str(ctx.parameters.get("mz_column") or ""), "mz", "m/z", "mass_to_charge", "feature_mz"])
    if not mz_col:
        raise CPUWorkflowError("MZ_COLUMN_MISSING", "Metabolite annotation input table must contain an mz column.")
    id_col = _first_existing_column(df.columns, ["feature_id", "id", "query_id", "name"])
    values = []
    for idx, row in df.iterrows():
        try:
            query_id = str(row[id_col]) if id_col else f"feature_{idx}"
            values.append((query_id, float(row[mz_col]), path.name))
        except Exception:
            continue
        if len(values) >= max_query_mz:
            break
    return values


def _example_imzml_path(ctx: CPUWorkflowContext) -> Path | None:
    example_id = str(ctx.parameters.get("example_id") or "").strip().lower()
    if example_id not in {"y7_t", "y7-t", "y7t"}:
        return None
    polarity = _ion_mode(ctx)
    stem = "Y7_T_neg.imzML" if polarity == "negative" else "Y7_T_pos.imzML"
    path = Y7_T_EXAMPLE_ROOT / stem
    return path if path.is_file() else None


def _mz_from_imzml(path: Path, *, ctx: CPUWorkflowContext, max_query_mz: int) -> list[tuple[str, float, str]]:
    try:
        from pyimzml.ImzMLParser import ImzMLParser
    except Exception as exc:
        raise CPUWorkflowError("DEPENDENCY_MISSING", "pyimzML is required to read imzML example data for annotation.") from exc
    max_spectra = _int_param(ctx, "max_imzml_spectra", 8, minimum=1, maximum=200)
    top_peaks = _int_param(ctx, "top_peaks_per_spectrum", 200, minimum=1, maximum=5000)
    parser = ImzMLParser(str(path))
    seen: dict[float, float] = {}
    spectra_count = min(max_spectra, len(getattr(parser, "coordinates", []) or []))
    for index in range(spectra_count):
        mzs, intensities = parser.getspectrum(index)
        pairs = []
        for mz, intensity in zip(mzs, intensities):
            try:
                inten = float(intensity)
                if inten <= 0:
                    continue
                pairs.append((inten, float(mz)))
            except Exception:
                continue
        pairs.sort(reverse=True)
        if pairs:
            selected_mz = [mz for _, mz in pairs[:top_peaks]]
        else:
            selected_mz = []
            for mz in mzs[:top_peaks]:
                try:
                    selected_mz.append(float(mz))
                except Exception:
                    continue
        for mz in selected_mz:
            key = round(mz, 4)
            seen.setdefault(key, mz)
            if len(seen) >= max_query_mz:
                break
        if len(seen) >= max_query_mz:
            break
    return [(f"{path.stem}_mz_{idx}", float(mz), path.name) for idx, mz in enumerate(sorted(seen.values()))]


def _load_ramp_compounds(path: Path) -> tuple[list[float], list[dict[str, Any]]]:
    if not path.is_file():
        raise CPUWorkflowError("DATABASE_RESOURCE_MISSING", f"RaMP SQLite database was not found: {path}")
    con = sqlite3.connect(str(path))
    try:
        rows = []
        for ramp_id, mass, name, formula in con.execute(
            "select ramp_id, monoisotop_mass, common_name, mol_formula from chem_props "
            "where monoisotop_mass is not null and monoisotop_mass > 0"
        ):
            try:
                rows.append(
                    {
                        "ramp_id": str(ramp_id or ""),
                        "neutral_mass": float(mass),
                        "name": str(name or ""),
                        "formula": str(formula or ""),
                    }
                )
            except Exception:
                continue
    finally:
        con.close()
    rows.sort(key=lambda item: item["neutral_mass"])
    masses = [float(item["neutral_mass"]) for item in rows]
    if not rows:
        raise CPUWorkflowError("DATABASE_RESOURCE_MISSING", f"RaMP chem_props has no usable monoisotopic masses: {path}")
    return masses, rows


def _annotate_ms1_ramp(
    *,
    query: list[tuple[str, float, str]],
    compounds: tuple[list[float], list[dict[str, Any]]],
    ramp_path: Path,
    tolerance_ppm: float,
    ion_mode: str,
) -> list[dict[str, Any]]:
    masses, rows = compounds
    adducts = _adducts_for_mode(ion_mode)
    candidates: list[dict[str, Any]] = []
    for query_id, observed_mz, source in query:
        for adduct, delta in adducts:
            neutral_target = observed_mz - delta
            if neutral_target <= 0:
                continue
            neutral_delta = max(observed_mz * tolerance_ppm / 1_000_000.0, 1e-9)
            left = bisect_left(masses, neutral_target - neutral_delta)
            right = bisect_right(masses, neutral_target + neutral_delta)
            for item in rows[left:right]:
                predicted_mz = float(item["neutral_mass"]) + delta
                ppm_error = (observed_mz - predicted_mz) / predicted_mz * 1_000_000.0 if predicted_mz else 0.0
                candidates.append(
                    {
                        "query_id": query_id,
                        "source": source,
                        "query_mz": round(observed_mz, 8),
                        "method": "ms1_ramp_exact_mass",
                        "database": "RaMP",
                        "ramp_id": item["ramp_id"],
                        "metabolite_name": item["name"],
                        "formula": item["formula"],
                        "neutral_mass": round(float(item["neutral_mass"]), 8),
                        "adduct": adduct,
                        "predicted_mz": round(predicted_mz, 8),
                        "ppm_error": round(ppm_error, 4),
                        "abs_ppm_error": round(abs(ppm_error), 4),
                        "ion_mode": "positive" if adduct.endswith("+") else "negative",
                        "annotation_level": "MS1_candidate",
                    }
                )
    _attach_crossrefs(candidates, ramp_path)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        grouped[str(row["query_id"])].append(row)
    ranked: list[dict[str, Any]] = []
    max_candidates = 20
    for query_id, group in grouped.items():
        group.sort(key=lambda row: (float(row["abs_ppm_error"]), str(row.get("metabolite_name") or "")))
        candidate_count = len(group)
        for rank, row in enumerate(group[:max_candidates], start=1):
            row["candidate_rank"] = rank
            row["candidate_count"] = candidate_count
            row["ambiguous"] = candidate_count > 1
            ranked.append(row)
    ranked.sort(key=lambda row: (str(row["query_id"]), int(row["candidate_rank"])))
    return ranked


def _attach_crossrefs(candidates: list[dict[str, Any]], ramp_path: Path) -> None:
    ramp_ids = sorted({str(row.get("ramp_id") or "") for row in candidates if row.get("ramp_id")})
    refs: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    if not ramp_ids:
        return
    con = sqlite3.connect(str(ramp_path))
    try:
        for start in range(0, len(ramp_ids), 800):
            batch = ramp_ids[start : start + 800]
            placeholders = ",".join("?" for _ in batch)
            sql = (
                "select sourceId, rampId, IDtype from source "
                "where geneOrCompound='compound' and rampId in (" + placeholders + ") "
                "and lower(IDtype) in ('kegg','hmdb','chebi','lipidmaps','pubchem','refmet','cas')"
            )
            for source_id, ramp_id, id_type in con.execute(sql, batch):
                clean = _clean_source_id(source_id, id_type)
                if clean:
                    refs[str(ramp_id)][str(id_type or "").lower()].add(clean)
    finally:
        con.close()
    for row in candidates:
        ref = refs.get(str(row.get("ramp_id") or ""), {})
        row["kegg_ids"] = ";".join(sorted(ref.get("kegg", set())))
        row["hmdb_ids"] = ";".join(sorted(ref.get("hmdb", set())))
        row["chebi_ids"] = ";".join(sorted(ref.get("chebi", set())))
        row["lipidmaps_ids"] = ";".join(sorted(ref.get("lipidmaps", set())))
        row["pubchem_ids"] = ";".join(sorted(ref.get("pubchem", set())))
        row["refmet_ids"] = ";".join(sorted(ref.get("refmet", set())))


def _mapping_partitions(query: list[tuple[str, float, str]], candidates: list[dict[str, Any]]):
    by_query: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        by_query[str(row["query_id"])].append(row)
    mapped: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    unmapped: list[dict[str, Any]] = []
    for query_id, mz, source in query:
        group = by_query.get(str(query_id), [])
        if not group:
            unmapped.append({"query_id": query_id, "query_mz": mz, "source": source, "mapping_status": "UNMAPPED", "reason": "no_mass_match"})
            continue
        best = sorted(group, key=lambda row: (float(row["abs_ppm_error"]), int(row["candidate_rank"])))[0]
        status = "MAPPED" if len(group) == 1 and best.get("kegg_ids") else "AMBIGUOUS" if len(group) > 1 else "NO_KEGG_ID"
        row = {
            "query_id": query_id,
            "query_mz": mz,
            "source": source,
            "mapping_status": status,
            "candidate_count": len(group),
            "best_ramp_id": best.get("ramp_id", ""),
            "best_name": best.get("metabolite_name", ""),
            "best_formula": best.get("formula", ""),
            "best_adduct": best.get("adduct", ""),
            "best_ppm_error": best.get("ppm_error", ""),
            "KEGG.ID": str(best.get("kegg_ids") or "").split(";")[0] if best.get("kegg_ids") else "",
            "all_kegg_ids": best.get("kegg_ids", ""),
        }
        if status == "AMBIGUOUS":
            ambiguous.append(row)
        elif status == "MAPPED":
            mapped.append(row)
        else:
            unmapped.append({**row, "reason": "candidate_without_kegg_id"})
    return mapped, unmapped, ambiguous


def _summary(
    ctx: CPUWorkflowContext,
    methods: list[str],
    ramp_path: Path,
    query: list[Any],
    candidates: list[dict[str, Any]],
    mapped: list[dict[str, Any]],
    ambiguous: list[dict[str, Any]],
    *,
    unmapped: list[dict[str, Any]] | None = None,
    status: str = "succeeded",
) -> dict[str, Any]:
    return {
        "status": status,
        "analysis_kind": "metabolite_annotation",
        "runtime_internet_required": False,
        "selected_methods": methods,
        "methods_run": [method for method in methods if method == "ms1_ramp_exact_mass"],
        "query_mz_count": len(query),
        "candidate_rows": len(candidates),
        "mapped_count": len(mapped),
        "ambiguous_count": len(ambiguous),
        "unmapped_count": len(unmapped or []),
        "resource": {
            "database_name": "RaMP",
            "database_version": "RaMP_SQLite_v3.0.7",
            "resource_file": str(ramp_path),
            "resource_size_bytes": ramp_path.stat().st_size if ramp_path.is_file() else 0,
            "resource_sha256": _known_ramp_sha256(ramp_path),
        },
        "job_id": ctx.job_id,
    }


def _write_outputs(
    ctx: CPUWorkflowContext,
    candidates: list[dict[str, Any]],
    mapped: list[dict[str, Any]],
    ambiguous: list[dict[str, Any]],
    unmapped: list[dict[str, Any]],
    requirement_rows: list[dict[str, Any]],
    summary: dict[str, Any],
) -> list[str]:
    candidate_fields = [
        "query_id",
        "source",
        "query_mz",
        "method",
        "database",
        "ramp_id",
        "metabolite_name",
        "formula",
        "neutral_mass",
        "adduct",
        "predicted_mz",
        "ppm_error",
        "abs_ppm_error",
        "ion_mode",
        "kegg_ids",
        "hmdb_ids",
        "chebi_ids",
        "lipidmaps_ids",
        "pubchem_ids",
        "refmet_ids",
        "candidate_rank",
        "candidate_count",
        "ambiguous",
        "annotation_level",
    ]
    mapping_fields = [
        "query_id",
        "query_mz",
        "source",
        "mapping_status",
        "candidate_count",
        "best_ramp_id",
        "best_name",
        "best_formula",
        "best_adduct",
        "best_ppm_error",
        "KEGG.ID",
        "all_kegg_ids",
        "reason",
    ]
    write_csv(ctx.workspace / "metabolite_annotations.csv", candidates, fieldnames=candidate_fields)
    write_csv(ctx.workspace / "metabolite_annotation_candidates.csv", candidates, fieldnames=candidate_fields)
    write_csv(ctx.workspace / "mapped_metabolites.csv", mapped, fieldnames=mapping_fields)
    write_csv(ctx.workspace / "ambiguous_metabolites.csv", ambiguous, fieldnames=mapping_fields)
    write_csv(ctx.workspace / "unmapped_metabolites.csv", unmapped, fieldnames=mapping_fields)
    write_json(ctx.workspace / "annotation_summary.json", summary)
    outputs = [
        "metabolite_annotations.csv",
        "metabolite_annotation_candidates.csv",
        "mapped_metabolites.csv",
        "ambiguous_metabolites.csv",
        "unmapped_metabolites.csv",
        "annotation_requirements.csv",
        "annotation_methods.json",
        "annotation_summary.json",
    ]
    outputs.extend(_write_annotation_manifest(ctx, summary=summary, outputs=outputs))
    return outputs


def _write_annotation_manifest(ctx: CPUWorkflowContext, *, summary: dict[str, Any], outputs: list[str]) -> list[str]:
    files = []
    for rel in outputs:
        path = ctx.workspace / rel
        if path.is_file():
            files.append({"path": rel, "size_bytes": path.stat().st_size, "sha256": sha256_file(path)})
    manifest = {
        "status": "completed",
        "workflow": ctx.workflow_name,
        "job_id": ctx.job_id,
        "summary": summary,
        "plots": [],
        "files": files,
        "archive": {"path": "results.zip"},
        "downloads": [{"label": item["path"], "path": item["path"]} for item in files],
        "manifest_version": "spashiny_metabolite_annotation_result_manifest_v1",
    }
    write_json(ctx.workspace / "result_manifest.json", manifest)
    zip_path = ctx.workspace / "results.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        for rel in [*outputs, "result_manifest.json"]:
            path = ctx.workspace / rel
            if path.is_file():
                archive.write(path, rel)
    return ["result_manifest.json", "results.zip"]


def _known_ramp_sha256(path: Path) -> str:
    manifest = path.parents[1] / "kegg" / "resource_manifest.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if str(data.get("source_database_file") or "").endswith(path.name):
            return str(data.get("source_database_sha256") or "")
    except Exception:
        pass
    return ""


def _adducts_for_mode(ion_mode: str) -> list[tuple[str, float]]:
    if ion_mode == "positive":
        return ADDUCTS["positive"]
    if ion_mode == "negative":
        return ADDUCTS["negative"]
    return [*ADDUCTS["positive"], *ADDUCTS["negative"]]


def _ion_mode(ctx: CPUWorkflowContext) -> str:
    raw = str(ctx.parameters.get("ion_mode") or ctx.parameters.get("polarity") or "positive").strip().lower()
    if raw in {"pos", "+", "positive"}:
        return "positive"
    if raw in {"neg", "-", "negative"}:
        return "negative"
    return "auto"


def _float_param(ctx: CPUWorkflowContext, key: str, default: float) -> float:
    try:
        return float(ctx.parameters.get(key) or default)
    except Exception:
        return default


def _int_param(ctx: CPUWorkflowContext, key: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(ctx.parameters.get(key) or default)
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


def _first_existing_column(columns, preferred: list[str]) -> str:
    available = [str(col) for col in columns]
    lookup = {col.lower(): col for col in available}
    for item in preferred:
        if not item:
            continue
        match = lookup.get(str(item).lower())
        if match:
            return match
    return ""


def _clean_source_id(source_id: Any, id_type: Any) -> str:
    value = str(source_id or "").strip()
    kind = str(id_type or "").strip().lower()
    if not value:
        return ""
    value = re.sub(r"^[A-Za-z0-9_.-]+:", "", value).strip()
    if kind == "kegg":
        match = re.search(r"C\d{5}", value, flags=re.IGNORECASE)
        return match.group(0).upper() if match else ""
    if kind == "hmdb":
        match = re.search(r"HMDB\d+", value, flags=re.IGNORECASE)
        return match.group(0).upper() if match else value
    if kind == "chebi":
        value = re.sub(r"(?i)^CHEBI:", "", value).strip()
    return value
