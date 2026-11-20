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
    import numpy as np
    from scipy import sparse
    from scipy.stats import ttest_ind

    labels = [str(item) for item in adata.obs[group_col].tolist()]
    groups = sorted({item for item in labels if item})
    if len(groups) < 2:
        raise CPUWorkflowError("GROUP_COLUMN_TOO_FEW_GROUPS", "Marker analysis requires at least two groups.")
    x = adata.X.toarray() if sparse.issparse(adata.X) else np.asarray(adata.X)
    if x.shape[0] < 2 or x.shape[1] < 1:
        raise CPUWorkflowError("INPUT_TOO_SMALL", "Marker analysis requires at least two observations and one feature.")
    rows: list[dict] = []
    labels_arr = np.asarray(labels)
    for group in groups:
        in_group = labels_arr == group
        out_group = ~in_group
        if in_group.sum() < 1 or out_group.sum() < 1:
            continue
        group_x = x[in_group, :]
        rest_x = x[out_group, :]
        group_mean = np.asarray(group_x.mean(axis=0)).ravel()
        rest_mean = np.asarray(rest_x.mean(axis=0)).ravel()
        with np.errstate(divide="ignore", invalid="ignore"):
            log2fc = np.log2((group_mean + 1e-9) / (rest_mean + 1e-9))
        stat, pvalue = ttest_ind(group_x, rest_x, axis=0, equal_var=False, nan_policy="omit")
        for idx, feature in enumerate(adata.var_names):
            rows.append(
                {
                    "group": group,
                    "feature": str(feature),
                    "mean_in_group": float(group_mean[idx]),
                    "mean_rest": float(rest_mean[idx]),
                    "log2_fold_change": float(log2fc[idx]),
                    "statistic": float(np.nan_to_num(stat[idx])),
                    "p_value": float(np.nan_to_num(pvalue[idx], nan=1.0)),
                }
            )
    rows.sort(key=lambda row: (row["p_value"], -abs(row["log2_fold_change"])))
    return rows
