from __future__ import annotations

import json
import re
from pathlib import Path

from .common import CPUWorkflowContext, CPUWorkflowError, ensure_dependency, save_figure_bundle, select_asset, sha256_file, write_csv, write_json


def _spatial_array(adata, *keys: str):
    for key in keys:
        if key in adata.obsm:
            return adata.obsm[key], key
    return None, ""


def _write_spatial_preview(ctx: CPUWorkflowContext, adata_st, adata_sm) -> list[str]:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except Exception:
        return []

    st_xy, st_key = _spatial_array(adata_st, "spatial", "spatial_transformed")
    sm_xy, sm_key = _spatial_array(adata_sm, "spatial_transformed", "spatial")
    if st_xy is None or sm_xy is None:
        return []

    st_xy = np.asarray(st_xy)
    sm_xy = np.asarray(sm_xy)
    if st_xy.ndim != 2 or st_xy.shape[1] < 2 or sm_xy.ndim != 2 or sm_xy.shape[1] < 2:
        return []

    fig, ax = plt.subplots(figsize=(7, 6))
    ax.scatter(st_xy[:, 0], st_xy[:, 1], s=8, alpha=0.55, label=f"ST ({st_key})")
    ax.scatter(sm_xy[:, 0], sm_xy[:, 1], s=8, alpha=0.55, label=f"SM ({sm_key})")
    ax.set_title("KNN reassigned spatial overlay")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.legend(loc="best")
    ax.set_aspect("equal", adjustable="box")
    fig.tight_layout()
    path, pdf_path = save_figure_bundle(fig, ctx.figures_dir / "knn_reassignment_spatial.png", dpi=150)
    plt.close(fig)
    return [path.relative_to(ctx.workspace).as_posix(), pdf_path.relative_to(ctx.workspace).as_posix()]


def _recover_st_total_counts(adata_st_new, adata_st):
    ensure_dependency("numpy")
    import numpy as np

    if "total_counts" not in adata_st.obs:
        adata_st_new.obs["total_counts"] = np.ones(adata_st_new.n_obs, dtype="float32")
        return {"method": "default_ones", "shared_observations": 0}

    common_obs = adata_st_new.obs_names.intersection(adata_st.obs_names)
    if len(common_obs) > 0:
        adata_st_new.obs["total_counts"] = np.nan
        adata_st_new.obs.loc[common_obs, "total_counts"] = adata_st.obs.loc[common_obs, "total_counts"]
        return {"method": "obs_name", "shared_observations": int(len(common_obs))}

    try:
        from scipy.spatial import cKDTree

        original_coords = adata_st.obsm["spatial"]
        new_coords = adata_st_new.obsm["spatial"]
        tree = cKDTree(original_coords)
        distances, indices = tree.query(new_coords, k=1)
        adata_st_new.obs["total_counts"] = adata_st.obs.iloc[indices]["total_counts"].values
        return {
            "method": "spatial_nearest_neighbor",
            "shared_observations": 0,
            "mean_distance": float(distances.mean()) if len(distances) else 0.0,
        }
    except Exception:
        adata_st_new.obs["total_counts"] = np.ones(adata_st_new.n_obs, dtype="float32")
        return {"method": "default_ones_after_nearest_neighbor_failure", "shared_observations": 0}


def _recover_sm_metadata(adata_sm_new, adata_sm) -> dict:
    ensure_dependency("numpy")
    import numpy as np

    recovered: list[str] = []
    common_obs = adata_sm_new.obs_names.intersection(adata_sm.obs_names)
    if len(common_obs) > 0:
        for col in ("total_intensity", "mean_intensity"):
            if col in adata_sm.obs:
                adata_sm_new.obs[col] = np.nan
                adata_sm_new.obs.loc[common_obs, col] = adata_sm.obs.loc[common_obs, col]
                recovered.append(col)
    return {"shared_observations": int(len(common_obs)), "recovered_columns": recovered}


def _handoff_lineage(ctx: CPUWorkflowContext, st_path: Path, sm_path: Path, st_shape, sm_shape) -> dict:
    """Bind the consumed inputs to the exact read-only Step6 manifest."""
    entries = ctx.metadata.get("workflow_artifact_lineage")
    if not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0], dict):
        raise CPUWorkflowError("HANDOFF_LINEAGE_INVALID", "KNN handoff requires one registered Alignment Step6 input.")
    entry = entries[0]
    analysis = str(ctx.metadata.get("analysis_session_id") or "")
    parent = str(entry.get("parent_id") or "")
    for value in (ctx.owner_session_id, analysis, parent):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise CPUWorkflowError("HANDOFF_SCOPE_INVALID", "KNN handoff scope is missing or unsafe.")
    if entry.get("parent_type") != "alignment_workflow" or entry.get("role") != "sm_aligned_h5ad":
        raise CPUWorkflowError("HANDOFF_LINEAGE_INVALID", "KNN handoff input is not a registered Alignment artifact.")
    if ctx.workspace.parent.name != ctx.owner_session_id or ctx.workspace.parent.parent.name != "sessions":
        raise CPUWorkflowError("HANDOFF_SCOPE_INVALID", "KNN workspace does not match its owner namespace.")
    root = ctx.workspace.parent.parent / "owners" / ctx.owner_session_id / "analysis_sessions" / analysis / "workflows" / parent
    try:
        manifest = json.loads((root / "alignment_handoff_manifest.json").read_text(encoding="utf-8"))
        state = json.loads((root / "alignment_workflow_state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CPUWorkflowError("HANDOFF_LINEAGE_INVALID", "The exact Alignment Step6 manifest is unavailable.") from exc
    if (
        manifest.get("owner_session_id") != ctx.owner_session_id
        or manifest.get("analysis_session_id") != analysis
        or manifest.get("parent_workflow_id") != parent
        or state.get("owner_id") != ctx.owner_session_id
        or state.get("analysis_session_id") != analysis
        or state.get("workflow_id") != parent
        or state.get("step6_status") != "completed"
    ):
        raise CPUWorkflowError("HANDOFF_SCOPE_INVALID", "Alignment Step6 does not belong to this completed analysis workflow.")
    artifact = manifest.get("artifact") or {}
    relative = Path(str(artifact.get("relative_path") or ""))
    if relative.is_absolute() or ".." in relative.parts or artifact.get("role") != "aligned_sm_h5ad":
        raise CPUWorkflowError("HANDOFF_LINEAGE_INVALID", "Alignment Step6 artifact reference is invalid.")
    expected_path = (root / relative).resolve()
    if root.resolve() not in expected_path.parents or expected_path != Path(sm_path).resolve():
        raise CPUWorkflowError("HANDOFF_LINEAGE_INVALID", "KNN did not consume the registered Step6 artifact.")
    actual_sm_sha = sha256_file(Path(sm_path))
    actual_sm_shape = [int(v) for v in sm_shape]
    if (
        not actual_sm_sha
        or actual_sm_sha != artifact.get("sha256")
        or actual_sm_sha != entry.get("sha256")
        or actual_sm_shape != [artifact.get("observation_count"), artifact.get("feature_count")]
    ):
        raise CPUWorkflowError("HANDOFF_LINEAGE_INVALID", "Consumed Step6 input hash or shape does not match its manifest.")
    inputs = manifest.get("input_lineage") or {}
    submitted = entry.get("lineage") or {}
    submitted_inputs = submitted.get("inputs") or {}
    safe_inputs = {}
    for key in ("st", "sm"):
        item = inputs.get(key) or {}
        submitted_item = submitted_inputs.get(key) or {}
        if (
            item.get("source_mode") != "USER_UPLOAD"
            or submitted.get("source_mode") != "USER_UPLOAD"
            or not item.get("sha256")
            or not item.get("reference")
            or any(submitted_item.get(k) != item.get(k) for k in ("filename", "sha256", "reference"))
            or Path(str(item.get("filename") or "")).name != item.get("filename")
        ):
            raise CPUWorkflowError("HANDOFF_LINEAGE_INVALID", "Original uploaded ST/SM provenance does not match Step6.")
        safe_inputs[key] = {k: item[k] for k in ("source_mode", "reference", "filename", "sha256", "size_bytes", "shape") if k in item}
    if sha256_file(Path(st_path)) != safe_inputs["st"]["sha256"] or [int(v) for v in st_shape] != inputs["st"].get("shape"):
        raise CPUWorkflowError("HANDOFF_LINEAGE_INVALID", "KNN did not consume the original ST upload bound to Step6.")
    return {
        # Preserve the frozen Control resolver's origin contract. The derived
        # output is labelled USER_UPLOAD_DERIVED separately in the manifest.
        "source_mode": "USER_UPLOAD",
        "parent_workflow_id": parent,
        "analysis_session_id": analysis,
        "inputs": safe_inputs,
        "step6_artifact_role": "aligned_sm_h5ad",
        "step6_artifact_reference": {
            "parent_type": "alignment_workflow",
            "parent_workflow_id": parent,
            "role": "aligned_sm_h5ad",
            "relative_path": relative.as_posix(),
        },
        "step6_artifact_sha256": actual_sm_sha,
        "step6_artifact_shape": actual_sm_shape,
    }


def _write_joint_handoff(ctx: CPUWorkflowContext, smt, sc, adata_st_new, adata_sm_new, lineage: dict) -> dict:
    """Serialize native joint assembly; no normalization, selection or training."""
    joint = smt.pp.joint_adata_sm_st(adata_SM_new=adata_sm_new, adata_ST_new=adata_st_new)
    joint.uns["spashiny_handoff_provenance"] = {
        "source_mode": "USER_UPLOAD_DERIVED",
        "analysis_session_id": lineage["analysis_session_id"],
        "knn_job_id": ctx.job_id,
        "parent_alignment_workflow_id": lineage["parent_workflow_id"],
        "step6_artifact_reference": lineage["step6_artifact_reference"],
        "step6_artifact_sha256": lineage["step6_artifact_sha256"],
        "step6_artifact_shape": lineage["step6_artifact_shape"],
        "original_st_filename": lineage["inputs"]["st"]["filename"],
        "original_st_sha256": lineage["inputs"]["st"]["sha256"],
        "original_sm_filename": lineage["inputs"]["sm"]["filename"],
        "original_sm_sha256": lineage["inputs"]["sm"]["sha256"],
        "construction": "spatialmeta.pp.joint_adata_sm_st",
        "normalization_applied": False,
        "feature_selection_applied": False,
        "model_training_applied": False,
    }
    path = ctx.workspace / "knn_joint_ready.h5ad"
    joint.write_h5ad(path)
    persisted = sc.read_h5ad(str(path), backed="r")
    try:
        shape = [int(v) for v in persisted.shape]
    finally:
        persisted.file.close()
    if min(shape) <= 0:
        raise CPUWorkflowError("HANDOFF_CONTRACT_INVALID", "Persisted KNN joint output is empty.")
    digest = sha256_file(path)
    manifest = {
        "schema": "spashiny.knn.handoff",
        "version": 1,
        "source_mode": "USER_UPLOAD_DERIVED",
        "owner_session_id": ctx.owner_session_id,
        "analysis_session_id": lineage["analysis_session_id"],
        "knn_job_id": ctx.job_id,
        "parent_job_id": ctx.job_id,
        "parent_alignment_workflow_id": lineage["parent_workflow_id"],
        "input_lineage": lineage,
        "step6_artifact_role": lineage["step6_artifact_role"],
        "step6_artifact_reference": lineage["step6_artifact_reference"],
        "step6_artifact_sha256": lineage["step6_artifact_sha256"],
        "step6_artifact_shape": lineage["step6_artifact_shape"],
        "original_st_filename": lineage["inputs"]["st"]["filename"],
        "original_st_sha256": lineage["inputs"]["st"]["sha256"],
        "original_sm_filename": lineage["inputs"]["sm"]["filename"],
        "original_sm_sha256": lineage["inputs"]["sm"]["sha256"],
        "artifact_role": "knn_joint_ready_h5ad",
        "artifact_sha256": digest,
        "artifact_shape": shape,
        "joint_shape": shape,
        "joint_shape_source": "ACTUAL_H5AD",
        "artifact": {
            # This role name is the frozen Control resolver's wire contract.
            "role": "knn_joint_h5ad",
            "relative_path": path.name,
            "filename": path.name,
            "sha256": digest,
            "size_bytes": int(path.stat().st_size),
            "shape": shape,
            "observation_count": shape[0],
            "feature_count": shape[1],
        },
    }
    write_json(ctx.workspace / "knn_handoff_manifest.json", manifest)
    return {"joint_handoff_shape": shape, "joint_handoff_sha256": digest, "input_lineage": lineage}


def _example_lineage(ctx, st_path, sm_path, st_shape, sm_shape):
    """Accept only an authenticated, exact-analysis example-action job plan."""
    analysis = str(ctx.metadata.get("analysis_session_id") or "")
    binding = ctx.metadata.get("session_input_binding") or {}
    plan_binding = ctx.plan.get("session_input_binding") or {}
    if (not all(re.fullmatch(r"[A-Za-z0-9_-]+", str(v)) for v in (ctx.owner_session_id, analysis, ctx.job_id))
        or ctx.owner_session_id != ctx.session_id
        or ctx.metadata.get("input_source") != "example_action"
        or ctx.plan.get("input_source") != "example_action"
        or ctx.plan.get("session_id") != ctx.owner_session_id
        or ctx.metadata.get("example_action_id") != "y7-knn-reassignment-example"
        or ctx.metadata.get("workflow_artifact_lineage")
        or binding.get("input_upload_ids") or binding.get("workflow_artifacts")
        or any(binding.get(k) != value or plan_binding.get(k) != value for k, value in (
            ("session_id", ctx.owner_session_id), ("analysis_session_id", analysis), ("job_id", ctx.job_id),
            ("workflow_name", "integration_postprocessing"), ("source", "example_action"),
            ("example_action_id", "y7-knn-reassignment-example")))):
        raise CPUWorkflowError("EXAMPLE_SCOPE_INVALID", "KNN example inputs do not match this authenticated owner and analysis.")
    inputs = {}
    for key, path, roles, shape in (("st", st_path, {"st_qc_h5ad", "knn_st_h5ad"}, st_shape),
                                    ("sm", sm_path, {"sm_aligned_h5ad", "knn_sm_h5ad"}, sm_shape)):
        assets = [item for item in ctx.downloaded_assets if item.get("role") in roles]
        if len(assets) != 1:
            raise CPUWorkflowError("EXAMPLE_SCOPE_INVALID", "KNN requires exactly one example asset for each modality.")
        asset = assets[0]
        digest = sha256_file(Path(path))
        if (Path(str(asset.get("path") or "")).resolve() != Path(path).resolve()
            or not asset.get("sha256") or digest != asset.get("sha256")
            or asset.get("source") not in (None, "", "example_action")
            or asset.get("action_id") not in (None, "", "y7-knn-reassignment-example")):
            raise CPUWorkflowError("EXAMPLE_ASSET_INVALID", "KNN example asset path, source or SHA256 is invalid.")
        inputs[key] = {"source_mode": "EXAMPLE", "filename": Path(path).name,
            "sha256": digest, "shape": [int(v) for v in shape], "role": asset["role"]}
    return {"source_mode": "EXAMPLE", "analysis_session_id": analysis,
        "example_action_id": "y7-knn-reassignment-example", "inputs": inputs}


def _official_example_expression(ctx, sc, aligned, lineage):
    from ..knn_expression import full_expression_with_alignment
    from ..knn_tutorial import ACTION, INPUTS, POLICY

    assets = [item for item in ctx.downloaded_assets if item.get("role") == "sm_raw_h5ad"]
    if len(assets) != 1:
        raise CPUWorkflowError("RAW_SM_REQUIRED", "Reload the official Y7_T example to bind its full Raw SM file. The aligned file supplies coordinates only.")
    asset = assets[0]
    path = Path(str(asset.get("path") or ""))
    if (not path.is_file() or asset.get("source") not in (None, "", "example_action")
            or asset.get("action_id") not in (None, "", ACTION)):
        raise CPUWorkflowError("EXAMPLE_ASSET_INVALID", "Raw SM does not belong to the scoped Y7_T example action.")
    digest = sha256_file(path)
    if digest != asset.get("sha256") or digest != INPUTS["sm_raw"][1]:
        raise CPUWorkflowError("EXAMPLE_ASSET_INVALID", "The bound Raw SM is not the published full Y7_T input.")
    raw = sc.read_h5ad(path)
    raw_info = {"source_mode": "EXAMPLE", "filename": path.name, "sha256": digest,
                "shape": list(raw.shape), "role": "sm_raw_h5ad", "expression_source": "complete_raw_sm.X"}
    inputs = {**lineage["inputs"], "sm_raw": raw_info}
    if any(tuple(inputs[key]["shape"]) != shape or inputs[key]["sha256"] != checksum
           for key, (shape, checksum) in INPUTS.items()):
        raise CPUWorkflowError("EXAMPLE_ASSET_INVALID", "A Y7_T example file differs from the pinned tutorial shape or checksum.")
    try:
        working = full_expression_with_alignment(raw, aligned, require_original_pixels=True)
    except ValueError as exc:
        raise CPUWorkflowError("EXAMPLE_ASSET_INVALID", str(exc)) from exc
    return working, {**lineage, "inputs": inputs, "tutorial_policy": POLICY,
                     "aligned_sm_usage": "coordinates_only", "sm_expression_source": "complete_raw_sm.X"}


def _write_example_joint(ctx, smt, sc, adata_st, adata_sm, lineage, *, original_st=None):
    # Never mislabel example data as USER_UPLOAD_DERIVED. The existing Control
    # upload-chain resolver continues to reject this manifest as an upload.
    joint = smt.pp.joint_adata_sm_st(adata_SM_new=adata_sm, adata_ST_new=adata_st)
    spot_mapping = None
    if original_st is not None:
        from .knn_postprocessing import write_tutorial_spot_mapping
        spot_mapping = write_tutorial_spot_mapping(ctx, original_st, adata_st, adata_sm, joint)
    joint.uns["spashiny_handoff_provenance"] = {"source_mode": lineage["source_mode"], "analysis_session_id": lineage["analysis_session_id"],
        "knn_job_id": ctx.job_id, "example_action_id": lineage.get("example_action_id", ""), "construction": "spatialmeta.pp.joint_adata_sm_st"}
    path = ctx.workspace / "knn_joint_ready.h5ad"
    joint.write_h5ad(path)
    saved = sc.read_h5ad(path, backed="r")
    try:
        shape = [int(v) for v in saved.shape]
    finally:
        saved.file.close()
    if min(shape) <= 0:
        raise CPUWorkflowError("HANDOFF_CONTRACT_INVALID", "The native KNN example joint result is empty.")
    digest = sha256_file(path)
    write_json(ctx.workspace / "knn_handoff_manifest.json", {"schema": "spashiny.knn.handoff", "version": 1,
        "source_mode": lineage["source_mode"], "owner_session_id": ctx.owner_session_id, "analysis_session_id": lineage["analysis_session_id"],
        "knn_job_id": ctx.job_id, "parent_job_id": ctx.job_id, "input_lineage": lineage,
        "artifact": {"role": "knn_joint_h5ad", "relative_path": path.name, "filename": path.name,
            "sha256": digest, "size_bytes": path.stat().st_size, "shape": shape,
            "observation_count": shape[0], "feature_count": shape[1]}})
    return {"joint_handoff_shape": shape, "joint_handoff_sha256": digest, "input_lineage": lineage,
            **({"spot_mapping": spot_mapping} if spot_mapping else {})}


def _uploaded_pair_lineage(ctx, st_path, sm_path, st_shape, sm_shape):
    """An explicitly uploaded aligned pair is not a forged Step6 artifact."""
    analysis = str(ctx.metadata.get("analysis_session_id") or "")
    binding = ctx.metadata.get("session_input_binding") or {}
    plan_binding = ctx.plan.get("session_input_binding") or {}
    ids = binding.get("input_upload_ids") or []
    if (not analysis or ctx.owner_session_id != ctx.session_id or len(ids) != 2 or len(set(ids)) != 2
            or ctx.plan.get("input_source") != "upload" or ctx.plan.get("session_id") != ctx.owner_session_id
            or binding.get("workflow_artifacts") or ctx.metadata.get("workflow_artifact_lineage")
            or any(binding.get(k) != v or plan_binding.get(k) != v for k, v in (
                ("session_id", ctx.owner_session_id), ("analysis_session_id", analysis),
                ("job_id", ctx.job_id), ("workflow_name", "integration_postprocessing"), ("source", "upload")))
            or plan_binding.get("input_upload_ids") != ids):
        raise CPUWorkflowError("UPLOAD_SCOPE_INVALID", "The uploaded pair does not belong to this exact authenticated analysis.")
    inputs = {}
    for key, path, role, shape in (("st", st_path, "knn_st_h5ad", st_shape), ("sm", sm_path, "knn_sm_h5ad", sm_shape)):
        assets = [x for x in ctx.downloaded_assets if x.get("role") == role]
        if len(assets) != 1:
            raise CPUWorkflowError("UPLOAD_SCOPE_INVALID", "One exact uploaded file is required for each KNN modality.")
        asset = assets[0]
        if (asset.get("source") != "upload" or asset.get("upload_id") not in ids
                or Path(asset.get("path", "")).resolve() != Path(path).resolve()
                or sha256_file(path) != asset.get("sha256")):
            raise CPUWorkflowError("UPLOAD_SCOPE_INVALID", "KNN upload identity or SHA256 changed after authorization.")
        inputs[key] = {"source_mode": "USER_UPLOAD", "reference": asset["upload_id"], "filename": Path(path).name,
            "sha256": asset["sha256"], "shape": list(shape)}
    if inputs["st"]["reference"] == inputs["sm"]["reference"]:
        raise CPUWorkflowError("UPLOAD_SCOPE_INVALID", "ST and SM must be distinct uploaded assets.")
    return {"source_mode": "USER_UPLOAD_ALIGNED_PAIR", "analysis_session_id": analysis, "inputs": inputs}


def run(ctx: CPUWorkflowContext) -> dict:
    ensure_dependency("scanpy")
    ensure_dependency("spatialmeta")
    import scanpy as sc
    import spatialmeta as smt

    st_path = select_asset(
        ctx,
        suffixes=(".h5ad",),
        roles=("st_qc_h5ad", "knn_st_h5ad", "st_h5ad", "primary"),
        label="KNN ST h5ad",
    )
    sm_path = select_asset(
        ctx,
        suffixes=(".h5ad",),
        roles=("sm_aligned_h5ad", "knn_sm_h5ad", "sm_h5ad"),
        label="KNN aligned SM h5ad",
    )
    if st_path is None or sm_path is None:
        raise CPUWorkflowError("INPUT_REQUIRED", "KNN reassignment requires ST and aligned SM h5ad inputs.")
    if Path(st_path).resolve() == Path(sm_path).resolve():
        raise CPUWorkflowError("INPUT_CONTRACT_INVALID", "KNN reassignment received the same h5ad for ST and SM inputs.")

    from ..knn_tutorial import POLICY, example_parameters
    official = ctx.parameters.get("source_mode") == "EXAMPLE"
    if official:
        # The browser cannot override the notebook policy or omit either QC.
        ctx.parameters = {**ctx.parameters, **example_parameters(), "spot_knn_k": 5, "spot_dist_fold": 1.5}
    k = int(ctx.parameters.get("spot_knn_k") or ctx.parameters.get("n_neighbors") or ctx.parameters.get("k") or 5)
    dist_fold = float(ctx.parameters.get("spot_dist_fold") or ctx.parameters.get("dist_fold") or 2.0)
    if k <= 0:
        raise CPUWorkflowError("PARAMETER_INVALID", "KNN n_neighbors must be positive.")
    if dist_fold <= 0:
        raise CPUWorkflowError("PARAMETER_INVALID", "KNN dist_fold must be positive.")

    adata_st = sc.read_h5ad(str(st_path))
    adata_sm = sc.read_h5ad(str(sm_path))
    if "spatial" not in adata_st.obsm:
        raise CPUWorkflowError("INPUT_CONTRACT_INVALID", "ST h5ad must contain obsm['spatial'].")
    operation = str(ctx.parameters.get("operation") or "reassign")
    from ..knn_contract import KNN_INPUT_OPERATIONS
    if operation not in {*KNN_INPUT_OPERATIONS, "reassign", "postprocess"}:
        raise CPUWorkflowError("PARAMETER_INVALID", "Unknown KNN operation.")
    if official:
        input_lineage = _example_lineage(ctx, st_path, sm_path, adata_st.shape, adata_sm.shape)
        adata_sm, input_lineage = _official_example_expression(ctx, sc, adata_sm, input_lineage)
    elif ctx.parameters.get("source_mode") == "USER_UPLOAD_ALIGNED_PAIR":
        input_lineage = _uploaded_pair_lineage(ctx, st_path, sm_path, adata_st.shape, adata_sm.shape)
        from ..knn_expression import is_full_source_export
        selected_for_alignment = (
            "spashiny_alignment_normalization" in adata_sm.uns
            or ("highly_variable_moranI" in adata_sm.var and bool(adata_sm.var["highly_variable_moranI"].eq(True).all()))
        )
        if selected_for_alignment and not is_full_source_export(adata_sm):
            raise CPUWorkflowError("RAW_SM_REQUIRED", "This aligned SM is an Alignment feature-selection input. Use an export with complete original SM expression.")
    else:
        # The original upload -> Alignment Step6 hash and owner checks remain
        # unchanged and cannot be replaced by a source_mode parameter.
        input_lineage = _handoff_lineage(ctx, st_path, sm_path, adata_st.shape, adata_sm.shape)
        from ..knn_expression import is_full_source_export
        if not is_full_source_export(adata_sm, input_lineage["inputs"]["sm"]["sha256"]):
            raise CPUWorkflowError("RAW_SM_REQUIRED", "This earlier Step6 result does not verify complete SM expression. Re-save Step6 from the original SM input; the saved coordinates can be reused.")
    from .knn_coordinates import prepare_coordinates, coverage, matrix_quality
    adata_sm, coordinate_info = prepare_coordinates(ctx, adata_st, adata_sm, input_lineage)
    input_lineage = {**input_lineage, "coordinate_contract": coordinate_info}
    if operation in KNN_INPUT_OPERATIONS:
        from .knn_input_preparation import run as inspect_inputs
        return inspect_inputs(ctx, smt, adata_st, adata_sm, st_path, sm_path, input_lineage)

    initial_qc = None
    sm_full_input_shape = list(adata_sm.shape)
    if "initial_min_total_intensity" in ctx.parameters:
        expected = ctx.parameters.get("initial_qc_input_sha256") or {}
        actual = {"st": sha256_file(st_path), "sm": sha256_file(sm_path)} if expected else {}
        if official and expected:
            actual["sm_raw"] = input_lineage["inputs"]["sm_raw"]["sha256"]
        if expected and expected != actual:
            raise CPUWorkflowError("QC_INPUT_CHANGED", "KNN inputs changed after initial QC. Run input QC again.")
        from .knn_input_preparation import apply_initial_qc
        adata_sm, initial_qc = apply_initial_qc(smt, adata_sm, ctx.parameters["initial_min_total_intensity"])
        input_lineage = {**input_lineage, "initial_sm_qc": initial_qc}

    before_post = None
    if operation == "postprocess":
        from .knn_postprocessing import load_parent_and_filter
        adata_st_new, adata_sm_new, parent_metrics, post_filter, before_post = load_parent_and_filter(ctx, sc, smt)
        if official and parent_metrics.get("tutorial_policy") != POLICY:
            raise CPUWorkflowError("KNN_PARENT_INVALID", "Re-run the official tutorial KNN before post-filtering an older example result.")
        min_dist = float(parent_metrics["min_dist"])
        k, dist_fold = int(parent_metrics["n_neighbors"]), float(parent_metrics["dist_fold"])
        coordinate_info = parent_metrics["coordinate_contract"]
        initial_qc = parent_metrics.get("initial_sm_qc")
        coverage_info = parent_metrics["spatial_coverage"]
        input_lineage = {**input_lineage, "parent_knn_job_id": str(ctx.parameters["knn_parent_job_id"]), "post_filter": post_filter}
    else:
        st_dot_in_df = smt.pp.ST_spot_sample(adata_st, "spatial")
        min_dist = smt.pp.calculate_min_dist(adata_st)
        coverage_info = coverage(adata_st, adata_sm, min_dist * dist_fold)
        adata_sm_new, adata_st_new = smt.pp.spot_align_byknn(
            new_dot_in_df=st_dot_in_df,
            adata_SM=adata_sm,
            adata_ST=adata_st,
            min_dist=min_dist,
            n_neighbors=k,
            dist_fold=dist_fold,
        )
        post_filter = None
        if official:
            # Keep the tutorial's original QC ST expression, but join the
            # native coordinate metadata by verified spot identity, not row number.
            from .knn_input_preparation import apply_initial_qc
            from .knn_postprocessing import pair_tutorial_st, restore_tutorial_st
            st_original = restore_tutorial_st(adata_st, adata_st_new, st_dot_in_df)
            before_post = (pair_tutorial_st(st_original, adata_sm_new, require_complete=True), adata_sm_new)
            adata_sm_new, qc = apply_initial_qc(smt, adata_sm_new, ctx.parameters["post_min_total_intensity"])
            adata_st_new = pair_tutorial_st(st_original, adata_sm_new)
            post_filter = {**qc, "before_observations": qc["before_shape"][0],
                           "after_observations": qc["after_shape"][0], "knn_recomputed": False}
            input_lineage = {**input_lineage, "post_filter": post_filter, "st_expression_source": "original_qc_st.X"}
    if official and (tuple(adata_st_new.shape) != (1914, 36404) or tuple(adata_sm_new.shape) != (1914, 1299)):
        raise CPUWorkflowError("TUTORIAL_PARITY_FAILED", f"Y7_T did not reproduce 1914 matched spots with full expression: ST {adata_st_new.shape}, SM {adata_sm_new.shape}. No counts were forced.")

    import numpy as np
    if official:
        from .knn_postprocessing import pair_tutorial_st
        adata_st_new = pair_tutorial_st(adata_st_new, adata_sm_new, require_complete=True)
        # For new and historical official parents, read counts by barcode from
        # the pinned QC ST input. Its assay and plotting metadata are authoritative.
        counts = adata_st.obs["total_counts"].reindex(adata_st_new.obs_names)
        if not np.isfinite(counts.to_numpy()).all():
            raise CPUWorkflowError("KNN_PAIR_MISMATCH", "Original QC ST counts are unavailable for the saved barcodes.")
        adata_st_new.obs["total_counts"] = counts
        before_post[0].obs["total_counts"] = adata_st.obs["total_counts"].reindex(before_post[0].obs_names)
        st_recovery = {"method": "verified_original_st_barcode", "shared_observations": int(adata_st_new.n_obs),
                       "total_counts_source": "original_qc_st.obs.total_counts"}
        sm_recovery = {"method": "native_qc_on_reassigned_sm"}
    else:
        st_recovery = _recover_st_total_counts(adata_st_new, adata_st)
        adata_st_new.obs["total_counts"] = np.asarray(adata_st_new.X.sum(axis=1)).ravel()
        st_recovery["total_counts_source"] = "actual_reassigned_matrix_sum"
        sm_recovery = _recover_sm_metadata(adata_sm_new, adata_sm)
        try:
            smt.pp.calculate_qc_metrics_sm(adata_sm_new)
        except Exception as exc:
            # Keep the real KNN result but surface the QC issue in the manifest.
            sm_recovery["qc_warning"] = f"{type(exc).__name__}: {exc}"

    quality = matrix_quality(adata_st_new, adata_sm_new)
    quality.update(coordinate_contract=coordinate_info, spatial_coverage=coverage_info,
        analysis_session_id=str(ctx.metadata["analysis_session_id"]), job_id=ctx.job_id,
        source_mode=input_lineage["source_mode"])
    write_json(ctx.workspace / "knn_quality.json", quality)
    adata_sm_new.write_h5ad(ctx.workspace / "knn_sm_reassigned.h5ad")
    adata_st_new.write_h5ad(ctx.workspace / "knn_st_reassigned.h5ad")

    handoff_metrics = (_write_example_joint(ctx, smt, sc, adata_st_new, adata_sm_new, input_lineage,
                                            original_st=adata_st if official else None)
        if input_lineage["source_mode"] in {"EXAMPLE", "USER_UPLOAD_ALIGNED_PAIR"}
        else _write_joint_handoff(ctx, smt, sc, adata_st_new, adata_sm_new, input_lineage))

    obs_rows = [
        {
            "dataset": "ST",
            "observations": int(adata_st_new.n_obs),
            "features": int(adata_st_new.n_vars),
        },
        {
            "dataset": "SM",
            "observations": int(adata_sm_new.n_obs),
            "features": int(adata_sm_new.n_vars),
        },
    ]
    write_csv(ctx.workspace / "knn_observation_summary.csv", obs_rows)

    from .knn_postprocessing import write_figures
    figures = write_figures(ctx, smt, sc, adata_st_new, adata_sm_new, quality, before_post=before_post, post_filter=post_filter)
    metrics = {
        "st_input_file": st_path.name,
        "sm_input_file": sm_path.name,
        "st_input_shape": [int(adata_st.n_obs), int(adata_st.n_vars)],
        "sm_input_shape": sm_full_input_shape,
        **({"tutorial_policy": POLICY, "raw_sm_input": input_lineage["inputs"]["sm_raw"]} if official else {}),
        "st_output_shape": [int(adata_st_new.n_obs), int(adata_st_new.n_vars)],
        "sm_output_shape": [int(adata_sm_new.n_obs), int(adata_sm_new.n_vars)],
        "min_dist": float(min_dist),
        "n_neighbors": int(k),
        "dist_fold": float(dist_fold),
        "st_total_counts_recovery": st_recovery,
        "sm_metadata_recovery": sm_recovery,
        "initial_sm_qc": initial_qc,
        "post_filter": post_filter,
        "coordinate_contract": coordinate_info,
        "spatial_coverage": coverage_info,
        "quality": quality,
        **handoff_metrics,
    }
    write_json(ctx.workspace / "knn_summary.json", {"status": "succeeded", **metrics})
    return {
        "metrics": metrics,
        "outputs": [
            "knn_summary.json",
            "knn_observation_summary.csv",
            "knn_sm_reassigned.h5ad",
            "knn_st_reassigned.h5ad",
            "knn_joint_ready.h5ad",
            "knn_handoff_manifest.json",
            "knn_quality.json",
            *( ["knn_spot_mapping.json"] if "spot_mapping" in handoff_metrics else [] ),
            *figures,
        ],
    }
