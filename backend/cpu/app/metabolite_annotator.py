# -*- coding: utf-8 -*-
from __future__ import annotations

import gc
import json
import math
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

import anndata as ad
import numpy as np
import pandas as pd


OUTPUT_VAR_COLUMNS = [
    "accession",
    "metabolite_name",
    "iupac_name",
    "chemical_formula",
    "kegg",
    "hmdb",
    "lipidmaps",
    "direct_parent",
    "class",
    "sub_class",
    "annotation_source",
    "matched_mz",
    "adduct",
    "ppm_error",
    "n_candidates",
]

ANNOTATION_OUTPUT_ALIASES = {
    "accession": ["accession", "id", "identifier", "compound_id"],
    "metabolite_name": ["metabolite_name", "compound_name", "name", "metabolite", "compound"],
    "iupac_name": ["iupac_name", "iupac"],
    "chemical_formula": ["chemical_formula", "formula"],
    "kegg": ["kegg", "kegg_id", "kegg.id", "kegg_compound", "kegg_compound_id"],
    "hmdb": ["hmdb", "hmdb_id"],
    "lipidmaps": ["lipidmaps", "lipidmaps_id", "lipid_maps"],
    "direct_parent": ["direct_parent", "direct parent"],
    "class": ["class", "super_class", "superclass"],
    "sub_class": ["sub_class", "subclass", "sub class"],
}

FEATURE_ID_ALIASES = [
    "feature_id",
    "featureid",
    "feature",
    "id",
    "name",
    "metabolite_name",
    "compound_name",
]
ANNOTATION_MZ_ALIASES = [
    "mz",
    "m/z",
    "observed_mz",
    "observed m/z",
    "observedmz",
    "mass_to_charge",
    "mass/charge",
]
VAR_MZ_ALIASES = [
    "mz",
    "m/z",
    "observed_mz",
    "observed m/z",
    "feature_mz",
    "mass_to_charge",
]
EXACT_MASS_ALIASES = [
    "exact_mass",
    "exact mass",
    "neutral_mass",
    "neutral mass",
    "monoisotopic_mass",
    "mono_mass",
]
POLARITY_ALIASES = ["polarity", "ion_mode", "ion mode", "mode", "type"]
ADDUCT_ALIASES = ["adduct", "ion", "ion_type", "ion type"]

PROTON = 1.007276466812
ADDUCT_MZ = {
    "[M+H]+": (PROTON, 1),
    "M+H": (PROTON, 1),
    "[M+Na]+": (22.989218, 1),
    "M+Na": (22.989218, 1),
    "[M+K]+": (38.963158, 1),
    "M+K": (38.963158, 1),
    "[M+NH4]+": (18.033823, 1),
    "M+NH4": (18.033823, 1),
    "[M+2H]2+": (2 * PROTON, 2),
    "M+2H": (2 * PROTON, 2),
    "[M-H]-": (-PROTON, 1),
    "M-H": (-PROTON, 1),
    "[M+Cl]-": (34.969402, 1),
    "M+Cl": (34.969402, 1),
    "[M+FA-H]-": (44.998201, 1),
    "M+FA-H": (44.998201, 1),
    "[M+HCOO]-": (44.998201, 1),
    "M+HCOO": (44.998201, 1),
    "[M+CH3COO]-": (59.013851, 1),
    "M+CH3COO": (59.013851, 1),
}
POSITIVE_DEFAULT_ADDUCTS = ["[M+H]+", "[M+Na]+", "[M+K]+", "[M+NH4]+"]
NEGATIVE_DEFAULT_ADDUCTS = ["[M-H]-", "[M+Cl]-", "[M+FA-H]-", "[M+CH3COO]-"]
ALL_DEFAULT_ADDUCTS = POSITIVE_DEFAULT_ADDUCTS + NEGATIVE_DEFAULT_ADDUCTS


def _canon(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())


def _clean_optional(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _column_lookup(df: pd.DataFrame) -> Dict[str, str]:
    return {_canon(col): col for col in df.columns}


def find_column(df: pd.DataFrame, aliases: Sequence[str], manual: Optional[str] = None) -> Optional[str]:
    lookup = _column_lookup(df)
    manual = _clean_optional(manual)
    if manual:
        if manual in df.columns:
            return manual
        return lookup.get(_canon(manual))
    for alias in aliases:
        col = lookup.get(_canon(alias))
        if col is not None:
            return col
    return None


def read_annotation_table(path: Union[str, Path]) -> pd.DataFrame:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        try:
            return pd.read_excel(path)
        except ImportError as exc:
            raise ImportError(
                "Reading Excel annotation tables requires openpyxl/xlrd in runtime/env_river. "
                "Please upload CSV/TSV or install the Excel reader dependency."
            ) from exc
    if suffix in {".tsv", ".txt"}:
        return pd.read_csv(path, sep="\t")
    return pd.read_csv(path, sep=None, engine="python")


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def _normalize_key(value: Any) -> str:
    text = _as_str(value)
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip().casefold()


def _to_float(value: Any) -> float:
    if value is None:
        return math.nan
    try:
        if pd.isna(value):
            return math.nan
    except Exception:
        pass
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)
    text = str(value).strip()
    if not text:
        return math.nan
    match = re.search(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", text)
    if not match:
        return math.nan
    try:
        return float(match.group(0))
    except Exception:
        return math.nan


def _safe_json_value(value: Any) -> Any:
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def _extract_feature_mz(adata: ad.AnnData, manual_col: Optional[str] = None) -> Tuple[pd.Series, Optional[str]]:
    var = adata.var
    mz_col = find_column(var, VAR_MZ_ALIASES, manual=manual_col)
    if mz_col is not None:
        mz_values = var[mz_col].map(_to_float).astype(float)
        return mz_values, mz_col

    parsed = pd.Series([_to_float(idx) for idx in var.index], index=var.index, dtype=float)
    return parsed, "var_names_parsed"


def _select_sm_features(adata: ad.AnnData, only_sm_features: bool) -> Tuple[pd.Index, Optional[str]]:
    if not only_sm_features:
        return adata.var.index, None

    var = adata.var
    type_candidates = ["type", "modality", "feature_type", "omics", "data_type"]
    sm_values = {
        "sm",
        "ms",
        "mz",
        "m/z",
        "metabolite",
        "metabolites",
        "spatial_metabolomics",
        "spatial metabolomics",
    }
    for col in type_candidates:
        real_col = find_column(var, [col])
        if real_col is None:
            continue
        values = var[real_col].astype(str).str.strip().str.lower()
        mask = values.isin(sm_values)
        if bool(mask.any()):
            return var.index[mask], real_col

    return adata.var.index, None


def _annotation_output_value(row: pd.Series, output_col: str, output_cols: Dict[str, Optional[str]]) -> str:
    source_col = output_cols.get(output_col)
    if source_col is None:
        return ""
    return _as_str(row.get(source_col, ""))


def _split_adducts(value: Any) -> List[str]:
    text = _as_str(value)
    if not text:
        return []
    parts = [part.strip() for part in re.split(r"[;,|]", text) if part.strip()]
    return parts or [text]


def _adducts_for_polarity(value: Any) -> List[str]:
    text = _as_str(value).lower()
    if text in {"positive", "pos", "+", "esi+", "positive ion", "positive_mode"}:
        return POSITIVE_DEFAULT_ADDUCTS
    if text in {"negative", "neg", "-", "esi-", "negative ion", "negative_mode"}:
        return NEGATIVE_DEFAULT_ADDUCTS
    return ALL_DEFAULT_ADDUCTS


def theoretical_mz(neutral_mass: float, adduct: str) -> float:
    if not np.isfinite(neutral_mass):
        return math.nan
    spec = ADDUCT_MZ.get(adduct)
    if spec is None:
        spec = ADDUCT_MZ.get(adduct.strip())
    if spec is None:
        return math.nan
    delta, charge = spec
    if charge <= 0:
        return math.nan
    return (neutral_mass + delta) / charge


def _build_annotation_column_map(anno: pd.DataFrame) -> Dict[str, Optional[str]]:
    return {
        output_col: find_column(anno, aliases)
        for output_col, aliases in ANNOTATION_OUTPUT_ALIASES.items()
    }


def _candidate_base(
    adata: ad.AnnData,
    feature_name: str,
    feature_mz: float,
    anno: pd.DataFrame,
    anno_row_index: int,
    source: str,
    matched_mz: float,
    adduct: str,
    ppm_error: float,
    output_cols: Dict[str, Optional[str]],
) -> Dict[str, Any]:
    row = anno.iloc[int(anno_row_index)]
    candidate = {
        "feature_index": feature_name,
        "feature_id": feature_name,
        "feature_mz": feature_mz if np.isfinite(feature_mz) else np.nan,
        "annotation_row": int(anno_row_index),
        "annotation_source": source,
        "matched_mz": matched_mz if np.isfinite(matched_mz) else np.nan,
        "adduct": adduct,
        "ppm_error": ppm_error if np.isfinite(ppm_error) else np.nan,
        "abs_ppm_error": abs(ppm_error) if np.isfinite(ppm_error) else np.nan,
    }
    for output_col in ANNOTATION_OUTPUT_ALIASES:
        candidate[output_col] = _annotation_output_value(row, output_col, output_cols)
    if not candidate["metabolite_name"]:
        for alias in ("name", "compound_name", "metabolite_name"):
            col = find_column(anno, [alias])
            if col is not None:
                candidate["metabolite_name"] = _as_str(row.get(col, ""))
                if candidate["metabolite_name"]:
                    break
    return candidate


def _feature_key_map(adata: ad.AnnData, feature_names: Iterable[str]) -> Dict[str, List[str]]:
    var = adata.var
    feature_names = list(feature_names)
    key_map: Dict[str, List[str]] = {}

    def add_key(key: Any, feature_name: str) -> None:
        norm = _normalize_key(key)
        if norm:
            key_map.setdefault(norm, []).append(feature_name)

    for feature_name in feature_names:
        add_key(feature_name, feature_name)

    for col in FEATURE_ID_ALIASES:
        real_col = find_column(var, [col])
        if real_col is None:
            continue
        for feature_name, value in var.loc[feature_names, real_col].items():
            add_key(value, feature_name)

    return key_map


def _feature_id_candidates(
    adata: ad.AnnData,
    anno: pd.DataFrame,
    feature_names: Sequence[str],
    feature_mz: pd.Series,
    output_cols: Dict[str, Optional[str]],
) -> List[Dict[str, Any]]:
    key_map = _feature_key_map(adata, feature_names)
    anno_key_cols = [
        col for col in (find_column(anno, [alias]) for alias in FEATURE_ID_ALIASES) if col is not None
    ]
    anno_key_cols = list(dict.fromkeys(anno_key_cols))
    if not anno_key_cols:
        return []

    anno_mz_col = find_column(anno, ANNOTATION_MZ_ALIASES)
    candidates: List[Dict[str, Any]] = []
    seen = set()
    for row_idx, row in anno.iterrows():
        row_keys = {_normalize_key(row.get(col, "")) for col in anno_key_cols}
        row_keys.discard("")
        for key in row_keys:
            for feature_name in key_map.get(key, []):
                dedupe_key = (feature_name, int(row_idx), "feature_id")
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                matched_mz = _to_float(row.get(anno_mz_col, "")) if anno_mz_col else math.nan
                candidates.append(
                    _candidate_base(
                        adata,
                        feature_name,
                        float(feature_mz.get(feature_name, math.nan)),
                        anno,
                        int(row_idx),
                        "feature_id",
                        matched_mz,
                        _as_str(row.get(find_column(anno, ADDUCT_ALIASES) or "", "")),
                        math.nan,
                        output_cols,
                    )
                )
    return candidates


def _mass_candidates_from_table(
    adata: ad.AnnData,
    anno: pd.DataFrame,
    ann_mz_rows: List[Tuple[int, float, str]],
    feature_names: Sequence[str],
    feature_mz: pd.Series,
    tolerance_ppm: float,
    source: str,
    output_cols: Dict[str, Optional[str]],
) -> List[Dict[str, Any]]:
    valid_rows = [(row_idx, mz, adduct) for row_idx, mz, adduct in ann_mz_rows if np.isfinite(mz) and mz > 0]
    if not valid_rows:
        return []

    sorted_rows = sorted(valid_rows, key=lambda item: item[1])
    mz_array = np.asarray([item[1] for item in sorted_rows], dtype=float)
    candidates: List[Dict[str, Any]] = []

    for feature_name in feature_names:
        fmz = float(feature_mz.get(feature_name, math.nan))
        if not np.isfinite(fmz) or fmz <= 0:
            continue
        delta = fmz * float(tolerance_ppm) / 1_000_000.0
        left = int(np.searchsorted(mz_array, fmz - delta, side="left"))
        right = int(np.searchsorted(mz_array, fmz + delta, side="right"))
        for row_idx, matched_mz, adduct in sorted_rows[left:right]:
            ppm_error = (fmz - matched_mz) / matched_mz * 1_000_000.0
            candidates.append(
                _candidate_base(
                    adata,
                    feature_name,
                    fmz,
                    anno,
                    row_idx,
                    source,
                    matched_mz,
                    adduct,
                    ppm_error,
                    output_cols,
                )
            )

    return candidates


def _observed_mz_candidates(
    adata: ad.AnnData,
    anno: pd.DataFrame,
    feature_names: Sequence[str],
    feature_mz: pd.Series,
    tolerance_ppm: float,
    output_cols: Dict[str, Optional[str]],
    anno_mz_col: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    mz_col = find_column(anno, ANNOTATION_MZ_ALIASES, manual=anno_mz_col)
    if mz_col is None:
        return [], None

    adduct_col = find_column(anno, ADDUCT_ALIASES)
    ann_mz_rows = [
        (int(row_idx), _to_float(row.get(mz_col, "")), _as_str(row.get(adduct_col, "")) if adduct_col else "")
        for row_idx, row in anno.iterrows()
    ]
    return (
        _mass_candidates_from_table(
            adata,
            anno,
            ann_mz_rows,
            feature_names,
            feature_mz,
            tolerance_ppm,
            "observed_mz",
            output_cols,
        ),
        mz_col,
    )


def _exact_mass_candidates(
    adata: ad.AnnData,
    anno: pd.DataFrame,
    feature_names: Sequence[str],
    feature_mz: pd.Series,
    tolerance_ppm: float,
    output_cols: Dict[str, Optional[str]],
    polarity_col: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], Optional[str], Optional[str], Optional[str]]:
    mass_col = find_column(anno, EXACT_MASS_ALIASES)
    if mass_col is None:
        return [], None, None, None

    adduct_col = find_column(anno, ADDUCT_ALIASES)
    pol_col = find_column(anno, POLARITY_ALIASES, manual=polarity_col)
    ann_mz_rows: List[Tuple[int, float, str]] = []

    for row_idx, row in anno.iterrows():
        neutral_mass = _to_float(row.get(mass_col, ""))
        if not np.isfinite(neutral_mass) or neutral_mass <= 0:
            continue
        adducts = _split_adducts(row.get(adduct_col, "")) if adduct_col else []
        if not adducts:
            adducts = _adducts_for_polarity(row.get(pol_col, "")) if pol_col else ALL_DEFAULT_ADDUCTS
        for adduct_name in adducts:
            mz = theoretical_mz(neutral_mass, adduct_name)
            if np.isfinite(mz):
                ann_mz_rows.append((int(row_idx), mz, adduct_name))

    return (
        _mass_candidates_from_table(
            adata,
            anno,
            ann_mz_rows,
            feature_names,
            feature_mz,
            tolerance_ppm,
            "exact_mass",
            output_cols,
        ),
        mass_col,
        adduct_col,
        pol_col,
    )


def _rank_candidates(candidates: pd.DataFrame, n_candidates_total: pd.Series, top_n: int) -> pd.DataFrame:
    if candidates.empty:
        return candidates
    source_priority = {"feature_id": 0, "observed_mz": 1, "exact_mass": 2}
    candidates = candidates.copy()
    candidates["_source_priority"] = candidates["annotation_source"].map(source_priority).fillna(9)
    candidates["_sort_ppm"] = candidates["abs_ppm_error"].fillna(-1.0)
    candidates.sort_values(
        ["feature_index", "_source_priority", "_sort_ppm", "annotation_row"],
        ascending=[True, True, True, True],
        inplace=True,
    )
    candidates["candidate_rank"] = candidates.groupby("feature_index").cumcount() + 1
    candidates["n_candidates_total"] = candidates["feature_index"].map(n_candidates_total).fillna(0).astype(int)
    candidates["within_top_n"] = candidates["candidate_rank"] <= int(top_n)
    candidates["selected_for_var"] = candidates["candidate_rank"] == 1
    return candidates.drop(columns=["_source_priority", "_sort_ppm"])


def _write_var_annotations(adata: ad.AnnData, ranked: pd.DataFrame, feature_names: Sequence[str]) -> int:
    string_cols = [col for col in OUTPUT_VAR_COLUMNS if col not in {"matched_mz", "ppm_error", "n_candidates"}]
    for col in string_cols:
        adata.var[col] = ""
    adata.var["matched_mz"] = np.nan
    adata.var["ppm_error"] = np.nan
    adata.var["n_candidates"] = 0

    if ranked.empty:
        return 0

    counts = ranked.groupby("feature_index").size()
    for feature_name in feature_names:
        if feature_name in counts.index:
            adata.var.loc[feature_name, "n_candidates"] = int(counts.loc[feature_name])

    selected = ranked[ranked["candidate_rank"] == 1]
    for _, row in selected.iterrows():
        feature_name = row["feature_index"]
        for col in string_cols:
            adata.var.loc[feature_name, col] = _as_str(row.get(col, ""))
        adata.var.loc[feature_name, "matched_mz"] = _to_float(row.get("matched_mz", np.nan))
        adata.var.loc[feature_name, "ppm_error"] = _to_float(row.get("ppm_error", np.nan))

    return int(selected["feature_index"].nunique())


def annotate_h5ad(
    h5ad_path: Union[str, Path],
    annotation_path: Union[str, Path],
    output_h5ad: Union[str, Path],
    mode: str = "auto",
    tolerance_ppm: float = 5.0,
    top_n: int = 1,
    only_sm_features: bool = True,
    var_mz_col: Optional[str] = None,
    anno_mz_col: Optional[str] = None,
    polarity_col: Optional[str] = None,
    summary_json: Optional[Union[str, Path]] = None,
    all_candidates_csv: Optional[Union[str, Path]] = None,
    logger: Any = None,
) -> Dict[str, Any]:
    start_time = time.time()
    h5ad_path = Path(h5ad_path).resolve()
    annotation_path = Path(annotation_path).resolve()
    output_h5ad = Path(output_h5ad).resolve()
    output_h5ad.parent.mkdir(parents=True, exist_ok=True)
    mode = str(mode or "auto").strip().lower()
    if mode not in {"auto", "feature_id", "observed_mz", "exact_mass"}:
        raise ValueError(f"Unsupported annotation mode: {mode}")
    tolerance_ppm = float(tolerance_ppm)
    top_n = max(1, int(top_n))

    def log(message: str) -> None:
        if logger is not None:
            logger.info(message)

    log("Loading AnnData file...")
    adata = ad.read_h5ad(str(h5ad_path))
    total_features = int(adata.n_vars)
    log(f"AnnData loaded: n_obs={adata.n_obs}, n_vars={adata.n_vars}")

    log("Loading annotation table...")
    anno = read_annotation_table(annotation_path)
    anno = anno.reset_index(drop=True)
    log(f"Annotation table loaded: rows={len(anno)}, columns={len(anno.columns)}")

    feature_index, sm_type_column = _select_sm_features(adata, only_sm_features)
    feature_names = list(feature_index)
    participating_features = len(feature_names)
    feature_mz, detected_var_mz_col = _extract_feature_mz(adata, manual_col=var_mz_col)
    output_cols = _build_annotation_column_map(anno)

    enabled_modes = [mode] if mode != "auto" else ["feature_id", "observed_mz", "exact_mass"]
    candidates: List[Dict[str, Any]] = []
    detected_anno_mz_col = None
    detected_mass_col = None
    detected_adduct_col = None
    detected_polarity_col = None

    if "feature_id" in enabled_modes:
        log("Running feature_id/name matching...")
        candidates.extend(_feature_id_candidates(adata, anno, feature_names, feature_mz, output_cols))
    if "observed_mz" in enabled_modes:
        log("Running observed m/z matching...")
        observed_candidates, detected_anno_mz_col = _observed_mz_candidates(
            adata,
            anno,
            feature_names,
            feature_mz,
            tolerance_ppm,
            output_cols,
            anno_mz_col=anno_mz_col,
        )
        candidates.extend(observed_candidates)
    if "exact_mass" in enabled_modes:
        log("Running exact_mass + adduct matching...")
        exact_candidates, detected_mass_col, detected_adduct_col, detected_polarity_col = _exact_mass_candidates(
            adata,
            anno,
            feature_names,
            feature_mz,
            tolerance_ppm,
            output_cols,
            polarity_col=polarity_col,
        )
        candidates.extend(exact_candidates)

    candidates_df = pd.DataFrame(candidates)
    if candidates_df.empty:
        candidates_df = pd.DataFrame(
            columns=[
                "feature_index",
                "feature_id",
                "feature_mz",
                "annotation_row",
                "annotation_source",
                "matched_mz",
                "adduct",
                "ppm_error",
                "candidate_rank",
                "n_candidates_total",
                "within_top_n",
                "selected_for_var",
            ]
            + [col for col in ANNOTATION_OUTPUT_ALIASES]
        )
        n_total = pd.Series(dtype=int)
    else:
        n_total = candidates_df.groupby("feature_index").size()
    ranked = _rank_candidates(candidates_df, n_total, top_n)
    success_features = _write_var_annotations(adata, ranked, feature_names)

    candidate_csv_path = Path(all_candidates_csv).resolve() if all_candidates_csv else output_h5ad.with_name("all_candidate_annotations.csv")
    candidate_csv_path.parent.mkdir(parents=True, exist_ok=True)
    ranked.to_csv(candidate_csv_path, index=False)
    log(f"Candidate table written: {candidate_csv_path}")

    summary = {
        "success": True,
        "annotation_type": "putative metabolite annotation",
        "message": "Putative metabolite annotation completed.",
        "input_h5ad": str(h5ad_path),
        "annotation_table": str(annotation_path),
        "output_h5ad": str(output_h5ad),
        "all_candidates_csv": str(candidate_csv_path),
        "mode": mode,
        "enabled_modes": enabled_modes,
        "tolerance_ppm": tolerance_ppm,
        "top_n": top_n,
        "only_sm_features": bool(only_sm_features),
        "total_features": total_features,
        "participating_features": participating_features,
        "successfully_annotated_features": success_features,
        "candidate_rows": int(len(ranked)),
        "detected_columns": {
            "adata_var_mz": detected_var_mz_col,
            "adata_sm_type": sm_type_column,
            "annotation_mz": detected_anno_mz_col,
            "annotation_exact_mass": detected_mass_col,
            "annotation_adduct": detected_adduct_col,
            "annotation_polarity": detected_polarity_col,
            "annotation_output_columns": output_cols,
        },
        "note": (
            "Annotations are putative candidates based on feature_id/name, m/z tolerance, "
            "and/or exact mass plus adduct assumptions; they are not confirmed identifications."
        ),
        "elapsed_seconds": round(time.time() - start_time, 3),
    }

    adata.uns["metabolite_annotation_info"] = json.loads(
        json.dumps(summary, default=_safe_json_value, ensure_ascii=False)
    )
    adata.write_h5ad(str(output_h5ad))
    log(f"Annotated h5ad written: {output_h5ad}")

    summary_path = Path(summary_json).resolve() if summary_json else output_h5ad.with_name("annotation_summary.json")
    summary["summary_json"] = str(summary_path)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=_safe_json_value), encoding="utf-8")
    log(f"Summary written: {summary_path}")

    del adata
    gc.collect()
    return summary
