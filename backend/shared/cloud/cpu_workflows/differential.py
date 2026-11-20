from __future__ import annotations

from .common import CPUWorkflowContext, CPUWorkflowError, read_h5ad, select_asset, write_csv, write_json
from .marker import rank_features_by_group


def run(ctx: CPUWorkflowContext) -> dict:
    adata_path = select_asset(ctx, suffixes=(".h5ad",), roles=("processed_h5ad", "st_raw_h5ad", "sm_raw_h5ad", "joint_raw", "primary"), label="processed h5ad")
    adata = read_h5ad(adata_path)
    group_col = str(ctx.parameters.get("group_column") or ctx.parameters.get("groupby") or ctx.parameters.get("group_col") or "").strip()
    if not group_col or group_col not in adata.obs:
        raise CPUWorkflowError("GROUP_COLUMN_MISSING", "Differential analysis requires a valid group column in adata.obs.")
    groups = sorted({str(item) for item in adata.obs[group_col].tolist() if str(item)})
    if len(groups) < 2:
        raise CPUWorkflowError("GROUP_COLUMN_TOO_FEW_GROUPS", "Differential analysis requires at least two groups.")
    target = str(ctx.parameters.get("target_group") or ctx.parameters.get("target") or groups[0])
    control = str(ctx.parameters.get("control_group") or ctx.parameters.get("control") or next(item for item in groups if item != target))
    if target not in groups or control not in groups or target == control:
        raise CPUWorkflowError("INVALID_GROUP_COMPARISON", "Differential analysis target/control groups are invalid.")
    temp = adata[adata.obs[group_col].astype(str).isin([target, control])].copy()
    temp.obs["_spashiny_diff_group"] = ["target" if str(item) == target else "control" for item in temp.obs[group_col].tolist()]
    rows = [row for row in rank_features_by_group(temp, group_col="_spashiny_diff_group") if row["group"] == "target"]
    for row in rows:
        row["target_group"] = target
        row["control_group"] = control
        row.pop("group", None)
    if not rows:
        raise CPUWorkflowError("DIFFERENTIAL_RESULTS_EMPTY", "Differential analysis produced no result rows.")
    write_csv(ctx.workspace / "differential_results.csv", rows)
    metrics = {"input_file": adata_path.name, "group_column": group_col, "target_group": target, "control_group": control, "result_rows": len(rows)}
    write_json(ctx.workspace / "differential_summary.json", {"status": "succeeded", **metrics})
    return {"metrics": metrics, "outputs": ["differential_results.csv", "differential_summary.json"]}
