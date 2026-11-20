from __future__ import annotations

from .common import CPUWorkflowContext, CPUWorkflowError, read_h5ad, select_asset, write_csv, write_json


def run(ctx: CPUWorkflowContext) -> dict:
    adata_path = select_asset(ctx, suffixes=(".h5ad",), roles=("processed_h5ad", "st_raw_h5ad", "sm_raw_h5ad", "joint_raw", "primary"), label="processed h5ad")
    adata = read_h5ad(adata_path)
    group_col = str(ctx.parameters.get("group_column") or ctx.parameters.get("groupby") or ctx.parameters.get("group_col") or "").strip()
    if not group_col or group_col not in adata.obs:
        raise CPUWorkflowError("GROUP_COLUMN_MISSING", "Marker analysis requires a valid group column in adata.obs.")
    rows = rank_features_by_group(adata, group_col=group_col)
    if not rows:
        raise CPUWorkflowError("MARKER_RESULTS_EMPTY", "Marker analysis produced no marker rows.")
    write_csv(ctx.workspace / "marker_results.csv", rows)
    metrics = {"input_file": adata_path.name, "group_column": group_col, "groups": sorted({str(row["group"]) for row in rows}), "result_rows": len(rows)}
    write_json(ctx.workspace / "marker_summary.json", {"status": "succeeded", **metrics})
    return {"metrics": metrics, "outputs": ["marker_results.csv", "marker_summary.json"]}


def rank_features_by_group(adata, *, group_col: str) -> list[dict]:
    import pandas as pd
    import scanpy as sc
    import spatialmeta as smt
    from cloud.spatialmeta_runtime_compat import pandas_legacy_api

    # SPATIALMETA_PARITY F07: use native ranking statistics and FDR, never a
    # hand-written Welch/log-ratio substitute or synthetic p-value/statistic.
    if adata.obs[group_col].isna().any():
        raise CPUWorkflowError("GROUP_COLUMN_MISSING_VALUES", "Every observation must have an explicit group label.")
    data = adata.copy()
    data.obs[group_col] = pd.Categorical(data.obs[group_col].astype(str))
    groups = list(data.obs[group_col].cat.categories)
    if len(groups) < 2:
        raise CPUWorkflowError("GROUP_COLUMN_TOO_FEW_GROUPS", "Marker analysis requires at least two groups.")
    if data.n_obs < 2 or data.n_vars < 1:
        raise CPUWorkflowError("INPUT_TOO_SMALL", "Marker analysis requires at least two observations and one feature.")
    types = set(data.var["type"].astype(str)) if "type" in data.var else set()
    if types == {"ST", "SM"}:
        with pandas_legacy_api():
            smt.pp.rank_gene_and_metabolite_groups(data, groupby_ST=group_col, groupby_SM=group_col)
        result_keys = ("rank_genes_groups", "rank_metabolites_groups")
    elif not types or types in ({"ST"}, {"SM"}):
        # Native SpatialMETA delegates each modality to this Scanpy API. Avoid
        # calling the joint wrapper with an empty second modality.
        sc.tl.rank_genes_groups(data, groupby=group_col, use_raw=False)
        result_keys = ("rank_genes_groups",)
    else:
        raise CPUWorkflowError("FEATURE_TYPE_INVALID", "Marker feature types must be exact ST/SM labels.")
    rows: list[dict] = []
    for key in result_keys:
        for group in groups:
            frame = sc.get.rank_genes_groups_df(data, group=group, key=key)
            for result in frame.to_dict("records"):
                feature = str(result["names"])
                selected = data.obs[group_col].astype(str).eq(str(group)).to_numpy()
                values = data[:, [feature]].X
                rows.append({
                    "group": str(group), "feature": feature,
                    "modality": "SM" if key == "rank_metabolites_groups" or types == {"SM"} else "ST",
                    "mean_in_group": float(values[selected].mean()),
                    "mean_rest": float(values[~selected].mean()),
                    "log2_fold_change": float(result["logfoldchanges"]),
                    "statistic": float(result["scores"]),
                    "p_value": float(result["pvals"]),
                    "p_value_adjusted": float(result["pvals_adj"]),
                    "method": "spatialmeta/scanpy native rank_genes_groups defaults",
                })
    return rows
