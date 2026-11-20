"""Exact-scope bridge to the existing SpaShiny Web/JobManager implementation.

This module does not replace AlignmentVAE, KNN, ConditionalVAESTSM, the queue,
multipart transport, session heartbeat, lease expiry or the Dash wrapper.
"""
from __future__ import annotations

import asyncio
import copy
import json
import math
import sys
import uuid
from pathlib import Path

from single_sample_pipeline import Scope, PipelineError, atomic_json, inspect_h5ad, bounded_child, sha256_file
from spatialmeta_native_features import (
    ANNOTATION, export_ai_report, network_fingerprint, result_inventory, validate_network, native_downstream_tables,
)

_PLOT_LIMIT = asyncio.Semaphore(1)


def resolve_pipeline_result(owner, analysis, job_id):
    """Resume a specific current-analysis result, never an owner-only search."""
    from cloud.database import CloudDatabase
    from cloud.job_manager import JobManager
    s = Scope(owner, analysis)
    record = JobManager(database=CloudDatabase(read_only=True)).get_job_for_session(
        s.owner, str(job_id), analysis_session_id=s.analysis)
    if record.workflow != "vit_single_sample_integration" or record.status != "SUCCEEDED":
        raise PipelineError("INTEGRATION_RESULT_REQUIRED", "A succeeded single-sample integration job is required.")
    parent = Path(record.local_workspace).resolve()
    path = (parent / "integrated_result.h5ad").resolve()
    if parent not in path.parents or not path.is_file():
        raise PipelineError("ARTIFACT_MISSING", "The exact integration result is unavailable.")
    manifest = json.loads((parent / "result_manifest.json").read_text(encoding="utf-8"))
    entries = [x for x in manifest.get("files", []) if x.get("path") == "integrated_result.h5ad"]
    if manifest.get("job_id") != record.job_id or manifest.get("session_id") != record.session_id or len(entries) != 1:
        raise PipelineError("MANIFEST_SCOPE_INVALID", "Result manifest ownership is inconsistent.")
    if not entries[0].get("sha256") or sha256_file(path) != entries[0]["sha256"]:
        raise PipelineError("ARTIFACT_HASH_MISMATCH", "Integration result checksum mismatch.")
    return {"source": "pipeline", "local_path": str(path), "filename": path.name,
            "job_id": record.job_id, "analysis_session_id": s.analysis}


def preserve_downstream_labels(data, find_cluster_key):
    """Compatibility display labels, never invent C0 or overwrite annotations."""
    import pandas as pd
    if "celltype1" not in data.obs:
        cluster = find_cluster_key(data)
        if not cluster:
            cluster = next((key for key in ("leiden", "joint_clusters", "clusters", "louvain") if key in data.obs), None)
        if cluster:
            data.obs["celltype1"] = data.obs[cluster].astype(str)
        elif ANNOTATION in data.obs:
            data.obs["celltype1"] = data.obs[ANNOTATION].astype(str)
        # No valid grouping stays missing. Marker/network UI must explain it.
    if "celltype1" in data.obs and "a_celltype_ST_SM" not in data.obs:
        data.obs["a_celltype_ST_SM"] = data.obs["celltype1"].copy()
    return data


def _prepare_pair(st_path, sm_path, compact, set_layer):
    """Same native calls/parameters/order as process_alignment_pre, off the loop."""
    import numpy as np
    import scanpy as sc
    import spatialmeta as smt
    st = compact(smt.read_h5ad_st(str(st_path)))
    sm = compact(smt.read_h5ad_sm(str(sm_path)))
    set_layer(st, "normalized")
    sc.pp.normalize_total(st, layer="normalized")
    sc.pp.log1p(st, layer="normalized")
    smt.pp.spatial_variable(st, n_top_variable=2000, add_key="highly_variable_moranI", layer="normalized")
    st = st[:, st.var["highly_variable_moranI"]].copy()
    xmin, xmax = st.obsm["spatial"][:, 0].min(), st.obsm["spatial"][:, 0].max()
    st.obsm["spatial_normalized"] = (st.obsm["spatial"] - xmin) / (xmax - xmin) * 100
    sc.pp.normalize_total(sm, target_sum=1e3)
    smt.pp.spatial_variable(sm, n_top_variable=500, add_key="highly_variable_moranI")
    sm = sm[:, sm.var["highly_variable_moranI"]].copy()
    xmin, xmax = sm.obsm["spatial"][:, 0].min(), sm.obsm["spatial"][:, 0].max()
    sm.obsm["spatial_normalized"] = (sm.obsm["spatial"] - xmin) / (xmax - xmin) * 100
    return st, sm


def create_adapter(e):
    def scope():
        from cloud.database import CloudDatabase
        from cloud.session_manager import SessionManager
        db = CloudDatabase(read_only=True)
        session = SessionManager(database=db).authenticate(e["_cloud_session_token"]())
        analysis_id = str(e["_cloud_analysis_session_id"]() or "")
        record = db.get_analysis_session(analysis_id, owner_session_id=session.session_id)
        if str(record.get("status")) != "ACTIVE":
            raise PipelineError("ANALYSIS_ENDED", "This analysis is no longer ACTIVE. Open a new analysis; ended sessions cannot be resumed.")
        return Scope(session.session_id, analysis_id)

    def root():
        s = scope()
        path = Path(e["_alignment_session_result_root"]()).resolve()
        if path.name != s.analysis or path.parent.parent.name != s.owner:
            raise PipelineError("RESULT_SCOPE_INVALID", "Result namespace does not match the authenticated analysis.")
        return path / "single_sample_pipeline"

    def manager():
        from cloud.database import CloudDatabase
        from cloud.job_manager import JobManager
        return JobManager(database=CloudDatabase(read_only=True))

    def job(job_id, expected_workflow=None):
        s = scope()
        record = manager().get_job_for_session(s.owner, str(job_id), analysis_session_id=s.analysis)
        if expected_workflow and str(record.workflow) != expected_workflow:
            raise PipelineError("WORKFLOW_MISMATCH", "Checkpoint is not from the required workflow.")
        return record

    def job_file(record, name, *, verify_hash=True):
        path = Path(record.local_workspace).resolve()
        target = (path / name).resolve()
        if path not in target.parents or not target.is_file():
            raise PipelineError("ARTIFACT_MISSING", "The completed job does not contain the required artifact.")
        manifest = json.loads((path / "result_manifest.json").read_text(encoding="utf-8"))
        if manifest.get("job_id") != record.job_id or manifest.get("session_id") != record.session_id:
            raise PipelineError("MANIFEST_SCOPE_INVALID", "Artifact manifest identity does not match the authorized job.")
        entries = [x for x in manifest.get("files", []) if x.get("path") == name]
        if len(entries) != 1 or not entries[0].get("sha256"):
            raise PipelineError("MANIFEST_ARTIFACT_MISSING", "Artifact is not uniquely declared with a checksum.")
        if verify_hash and sha256_file(target) != entries[0]["sha256"]:
            raise PipelineError("ARTIFACT_HASH_MISMATCH", "Result file checksum does not match its manifest.")
        return target

    def resolve_upload(upload_id, role):
        from cloud.input_resolver import InputResolver
        s = scope()
        if not upload_id:
            raise PipelineError("UPLOAD_REQUIRED", "A completed upload is required.")
        return InputResolver().resolve_interactive_local_input(
            session_id=s.owner, analysis_session_id=s.analysis, upload_id=upload_id,
            workflow_name="vit_single_sample_integration" if role == "joint" else "alignment_preprocessing")

    def workflow():
        s = scope()
        wid = e["_current_alignment_workflow_id"]()
        state = e["_read_alignment_workflow_state"](wid) if wid else {}
        if not wid or state.get("owner_id") != s.owner or state.get("analysis_session_id") != s.analysis:
            raise PipelineError("ALIGNMENT_CHECKPOINT_REQUIRED", "No Alignment checkpoint belongs to this exact analysis.")
        return wid, state

    def validate_start(start, refs):
        scope()
        if start == "raw_pair":
            for role in ("st", "sm"):
                resolve_upload((refs.get(role) or {}).get("upload_id"), role)
        elif start == "joint":
            resolve_upload((refs.get("joint") or {}).get("upload_id"), "joint")
        elif start in {"manual", "step6"}:
            wid, state = workflow()
            if start == "manual" and (e["adata_st"].get() is None or e["alignment_manual_source_sm"].get() is None):
                raise PipelineError("PREPROCESS_CONTEXT_REQUIRED", "Load this workflow's preprocessed ST and SM before starting at manual alignment.")
            if start == "step6" and state.get("step6_status") != "completed":
                raise PipelineError("STEP6_REQUIRED", "This analysis has no completed Step6 handoff.")
            return {"workflow_id": wid}
        elif start == "knn":
            record = job(e["knn_upload_chain_job_id"].get(), "integration_postprocessing")
            if record.status != "SUCCEEDED":
                raise PipelineError("KNN_REQUIRED", "Wait for the exact KNN parent job to succeed.")
            return {"jobs": {"knn": record.job_id}}
        else:
            raise PipelineError("START_INVALID", "Unsupported starting stage.")
        return {}

    def validate_resume(run):
        run.assert_scope(scope())
        if run.workflow_id and run.workflow_id != e["_current_alignment_workflow_id"]():
            raise PipelineError("WORKFLOW_CHANGED", "The current Alignment workflow changed; no old artifacts were adopted.")
        if run.index < 10 and run.index > 1 and e["adata_st"].get() is None:
            raise PipelineError("CONTEXT_RELOAD_REQUIRED", "The browser was reloaded. Already submitted jobs continue; restore this workflow's input context before resuming orchestration.")

    def parameters():
        # Freeze actual configurations once, not values from a hidden page at
        # the time a later stage happens to be submitted.
        from spatialmeta_native_policy import alignment_epochs
        try:
            downstream = bool(e["input"].one_stop_native_downstream())
            gene_limit = int(e["input"].one_stop_correlation_genes() or 10)
        except Exception:
            downstream, gene_limit = True, 10
        if not 1 <= gene_limit <= 50:
            raise PipelineError("GENE_LIMIT_INVALID", "Choose 1-50 native Marker genes for correlation.")
        return {"parameter_policy": "spatialmeta_native_defaults_v1",
            "alignment_epochs": alignment_epochs(), "knn_k": 5, "knn_dist_fold": 2.0,
            "integration_mode": "tutorial", "requested_resource": "auto",
            "native_downstream": downstream, "correlation_gene_limit": gene_limit}

    def get_alignment_status(run, job_id):
        s = scope()
        payload = e["_alignment_job_payload"](job_id)
        if payload.get("workflow_id") != run.workflow_id:
            raise PipelineError("JOB_LINEAGE_INVALID", "Alignment job is outside this run's workflow.")
        if str(payload.get("analysis_session_id") or "") != s.analysis:
            raise PipelineError("CROSS_ANALYSIS_DENIED", "Alignment job belongs to another analysis.")
        return e["_alignment_status"](job_id)

    def observe(run):
        run.assert_scope(scope())
        job_id = run.jobs[run.step]
        if run.step in {"knn", "integration"}:
            record = job(job_id)
            return {"job_id": job_id, "status": record.status,
                    "progress": getattr(record, "progress", None), "error": getattr(record, "error_message", "") or ""}
        state = get_alignment_status(run, job_id)
        return {"job_id": job_id, "status": state.get("status", "queued"),
                "progress": state.get("progress"), "error": state.get("error") or state.get("error_message") or ""}

    alignment_steps = {"initial_preview": "initial", "manual_alignment": "manual",
        "alignment_training": "step3", "alignment_raster": "step4", "alignment_fitting": "step5"}

    def accept_artifacts(run):
        run.assert_scope(scope())
        jid = run.jobs[run.step]
        if run.step in {"knn", "integration"}:
            record = job(jid)
            filename = "knn_joint_ready.h5ad" if run.step == "knn" else "integrated_result.h5ad"
            # Recompute the checksum in the subsequent background read, not on
            # every progress poll. Here require manifest and nonempty output.
            path = job_file(record, filename, verify_hash=False)
            if path.stat().st_size == 0:
                raise PipelineError("ARTIFACT_EMPTY", "The completed artifact is empty.")
            return {"job_id": jid, "artifact": filename, "status": record.status}
        e["_step_worker_completed"](alignment_steps[run.step], jid)
        e["_complete_alignment_workflow_modal"](alignment_steps[run.step], job_id=jid)
        return {"job_id": jid, "artifact_validation": "PASS"}

    def _invoke(action):
        # Captured below the Shiny decorators: original function, not a forged
        # input or a second API path. Errors are checked after its execution.
        e["one_stop_actions"][action]()
        state = e["_alignment_modal_state"]()
        if state.get("phase") == "FAILED":
            raise PipelineError("ALIGNMENT_ACTION_FAILED", state.get("message", "Alignment action failed."))

    def validate_manual(transform):
        for key in ("rotation", "scale_width", "scale_height", "translation_x", "translation_y"):
            if not math.isfinite(float(transform[key])):
                raise PipelineError("TRANSFORM_NONFINITE", "Manual transform parameters must be finite.")
        if min(transform["scale_width"], transform["scale_height"]) <= 0:
            raise PipelineError("TRANSFORM_SCALE_INVALID", "Width and height must be positive.")

    def preview_manual(transform):
        validate_manual(transform)
        s = scope()
        e["one_stop_transform_override"].set(dict(transform))
        try:
            _invoke("manual")
        finally:
            e["one_stop_transform_override"].set(None)

    def manual_preview():
        scope()
        jid = e["manual_preview_job_id"].get() or e["initial_preview_job_id"].get()
        if not jid:
            return None
        kind = "overlay" if e["manual_preview_job_id"].get() else "initial"
        return e["_manual_preview_completed_image"](jid, kind)

    def manual_ready(transform):
        scope()
        if e["manual_transform_val"].get() != transform:
            raise PipelineError("MANUAL_PREVIEW_REQUIRED", "Preview this exact transformation before confirming.")
        jid = e["manual_transform_job_id"].get()
        if not jid or e["_alignment_status"](jid).get("status") != "completed":
            raise PipelineError("MANUAL_PREVIEW_PENDING", "Wait for the exact manual preview to complete.")
        return jid

    def dispatch(run, manual=None):
        s = scope(); run.assert_scope(s)
        step = run.step
        if run.workflow_id and step not in {"integration", "prepare_downstream", "report"}:
            if e["_current_alignment_workflow_id"]() != run.workflow_id:
                raise PipelineError("WORKFLOW_CHANGED", "The current Alignment workflow changed while the pipeline was running.")
        if step in {"normalize_coordinates", "create_alignment_model", "alignment_training", "alignment_step6"}:
            if e["adata_st"].get() is not e["alignment_manual_source_st"].get():
                raise PipelineError("INPUT_CHANGED", "Another module replaced the ST input; no new job adopted it.")
        if step == "preflight":
            paths = {role: resolve_upload(ref["upload_id"], role)["local_path"]
                     for role, ref in run.inputs.items() if role in {"st", "sm"}}
            if set(paths) != {"st", "sm"}:
                raise PipelineError("PAIRED_UPLOAD_REQUIRED", "Both ST and SM uploads are required.")
            async def work():
                return await asyncio.to_thread(lambda: {role: inspect_h5ad(path, role=role,
                    require_image=role == "st") for role, path in paths.items()})
            def commit(result):
                run.inputs = {role: {**run.inputs[role], "validation": value} for role, value in result.items()}
                return {"evidence": result}
            return {"background": work(), "commit": commit}
        if step == "preprocess":
            paths = {r: resolve_upload(run.inputs[r]["upload_id"], r)["local_path"] for r in ("st", "sm")}
            # Source hash is verified again before starting a scientific stage.
            def compute():
                for r, path in paths.items():
                    if sha256_file(path) != run.inputs[r]["validation"]["sha256"]:
                        raise PipelineError("INPUT_CHANGED", "An input changed after preflight.")
                return _prepare_pair(paths["st"], paths["sm"], e["compact_adata_X"], e["set_compact_layer"])
            async def work():
                return await asyncio.to_thread(compute)
            def commit(pair):
                st, sm = pair
                provenance = {"analysis_session_id": s.analysis, "alignment_method": "SpatialMETA alignment preprocessing"}
                for r in ("st", "sm"):
                    resolved = resolve_upload(run.inputs[r]["upload_id"], r)
                    provenance[r] = e["_alignment_input_provenance"](resolved)
                    provenance[r]["shape"] = run.inputs[r]["validation"]["shape"]
                e["_begin_alignment_workflow"](paths["st"], paths["sm"], sm, input_provenance=provenance)
                for name, value in (("adata_st", st), ("adata_sm", sm), ("alignment_manual_source_st", st), ("alignment_manual_source_sm", sm)):
                    e[name].set(value)
                e["alignment_manual_source_spatial"].set(sm.obsm["spatial"].copy())
                e["alignment_st_input_reference"].set(run.inputs["st"])
                e["alignment_sm_input_reference"].set(run.inputs["sm"])
                return {"workflow_id": e["_current_alignment_workflow_id"](),
                        "evidence": {"native_preprocessing": True, "st_shape": list(st.shape), "sm_shape": list(sm.shape)}}
            return {"background": work(), "commit": commit}
        if step == "initial_preview":
            _invoke("initial")
            return {"workflow_id": e["_current_alignment_workflow_id"](), "job_id": e["initial_preview_job_id"].get()}
        if step == "manual_alignment":
            validate_manual(manual)
            return {"job_id": manual_ready(manual)}
        if step == "normalize_coordinates":
            _invoke("step1")
            if not workflow()[1].get("step1_completed_at"):
                raise PipelineError("STEP1_NOT_COMPLETED", "Coordinate normalization did not complete.")
            return {"evidence": {"coordinate_source": "PREALIGNED_SM"}}
        if step == "create_alignment_model":
            st, sm = e["adata_st"].get(), e["adata_sm_transformed"].get()
            if st is None or sm is None:
                raise PipelineError("ALIGNMENT_INPUT_MISSING", "Prealigned ST and SM inputs are required.")
            async def work():
                def create():
                    import torch
                    from spatialmeta.model._alignment_model import AlignmentVAE
                    return AlignmentVAE(adata_st=st, adata_sm=sm,
                        device="cuda:0" if torch.cuda.is_available() else "cpu")
                return await asyncio.to_thread(create)
            def commit(model):
                from single_sample_pipeline import utcnow
                e["alignment_model"].set(model)
                e["_update_alignment_workflow_state"](step2_created_at=utcnow(), step2_status="completed",
                    step2_sm_coordinate_metadata=e["_alignment_coordinate_metadata"](sm.obsm["spatial"]))
                return {"evidence": {"model": "SpatialMETA.AlignmentVAE", "n_latent": int(model.n_latent),
                                     "parameter_policy": "spatialmeta_native_defaults_v1"}}
            return {"background": work(), "commit": commit}
        actions = {"alignment_training": ("step3", "alignment_step3_job_id"),
                   "alignment_raster": ("step4", "alignment_step4_job_id"),
                   "alignment_fitting": ("step5", "alignment_step5_job_id")}
        if step in actions:
            action, cell = actions[step]
            _invoke(action)
            return {"job_id": e[cell].get()}
        if step == "alignment_step6":
            _invoke("step6")
            if workflow()[1].get("step6_status") != "completed":
                raise PipelineError("STEP6_NOT_COMPLETED", "The current workflow's aligned SM artifact was not saved.")
            return {"evidence": {"artifact": "aligned_sm.h5ad", "scope": "exact owner/analysis/workflow"}}
        if step == "knn":
            from cloud.job_submission import JobSubmissionService
            from cloud.workflow_registry import INTEGRATION_POSTPROCESSING
            wid, state = workflow()
            provenance = state.get("input_provenance") or {}
            st, sm = provenance.get("st") or {}, provenance.get("sm") or {}
            if state.get("step6_status") != "completed" or any(x.get("source_mode") != "USER_UPLOAD" for x in (st, sm)):
                raise PipelineError("STEP6_UPLOAD_LINEAGE_REQUIRED", "KNN requires this analysis's completed user-upload Step6 checkpoint.")
            original_st = str(st.get("reference") or "")
            resolve_upload(original_st, "st")
            submitted = JobSubmissionService().submit(session=e["_cloud_session_record"](),
                workflow_name=INTEGRATION_POSTPROCESSING, input_upload_ids=[original_st],
                workflow_artifacts=[{"parent_type": "alignment_workflow", "parent_workflow_id": wid, "role": "aligned_sm_h5ad"}],
                parameters={"n_neighbors": run.parameters["knn_k"], "dist_fold": run.parameters["knn_dist_fold"],
                    "source_mode": "USER_UPLOAD_ALIGNMENT", "input_asset_roles": {original_st: "knn_st_h5ad"}},
                requested_resource="cpu", analysis_session_id=s.analysis)
            e["knn_upload_chain_job_id"].set(submitted.job_id)
            return {"workflow_id": wid, "job_id": submitted.job_id}
        if step == "integration":
            from cloud.job_submission import JobSubmissionService
            from cloud.workflow_registry import VIT_SINGLE_SAMPLE_INTEGRATION
            record = e["_cloud_session_record"]()
            from spatialmeta_native_policy import native_job_parameters
            params = native_job_parameters("stsm", "single")
            uploads, artifacts = [], []
            if run.start == "joint":
                ref = run.inputs.get("joint") or {}
                upload = resolve_upload(ref.get("upload_id"), "joint")
                # This must be preflighted even when earlier alignment is skipped.
                path = upload["local_path"]
                async def work():
                    return await asyncio.to_thread(inspect_h5ad, path, role="joint")
                def commit(check):
                    run.inputs["joint"]["validation"] = check
                    params.update(source_mode="USER_UPLOAD", input_asset_roles={ref["upload_id"]: "joint_raw"})
                    submitted = JobSubmissionService().submit(session=record, workflow_name=VIT_SINGLE_SAMPLE_INTEGRATION,
                        input_upload_ids=[ref["upload_id"]], parameters=params,
                        requested_resource=run.parameters["requested_resource"], analysis_session_id=s.analysis)
                    return {"job_id": submitted.job_id}
                return {"background": work(), "commit": commit}
            parent = run.jobs.get("knn") or e["knn_upload_chain_job_id"].get()
            previous = job(parent, "integration_postprocessing")
            if previous.status != "SUCCEEDED":
                raise PipelineError("KNN_NOT_SUCCEEDED", "Integration requires a succeeded same-analysis KNN job.")
            params.update(source_mode="USER_UPLOAD_ALIGNMENT_KNN", parent_knn_job_id=parent)
            submitted = JobSubmissionService().submit(session=record, workflow_name=VIT_SINGLE_SAMPLE_INTEGRATION,
                input_upload_ids=[], workflow_artifacts=[{"parent_type": "job", "parent_job_id": parent, "role": "knn_joint_h5ad"}],
                parameters=params, requested_resource=run.parameters["requested_resource"], analysis_session_id=s.analysis)
            return {"job_id": submitted.job_id}
        if step == "prepare_downstream":
            record = job(run.jobs["integration"], "vit_single_sample_integration")
            path = job_file(record, "integrated_result.h5ad", verify_hash=False)
            async def work():
                def load():
                    import scanpy as sc
                    job_file(record, "integrated_result.h5ad", verify_hash=True)
                    data = preserve_downstream_labels(e["compact_adata_X"](sc.read_h5ad(path)), e["find_vae_cluster_key"])
                    if run.parameters.get("native_downstream"):
                        downstream, evidence = native_downstream_tables(data, gene_limit=run.parameters["correlation_gene_limit"])
                    else:
                        downstream, evidence = None, {"status": "NOT_RUN", "reason": "Not selected by the user."}
                    return data, downstream, evidence
                return await asyncio.to_thread(load)
            def commit(result):
                data, downstream, native_evidence = result
                e["adata_obj"].set(data)
                e["marker_res"].set(downstream)
                e["corr_res"].set(downstream["adata"] if downstream else None)
                e["corr_plot_trigger"].set(e["corr_plot_trigger"].get() + 1)
                e["downstream_input_reference"].set({"source": "pipeline", "job_id": record.job_id, "filename": path.name})
                return {"evidence": {"shape": list(data.shape), "annotation_present": ANNOTATION in data.obs,
                    "dash_started": False, "native_marker_correlation": native_evidence}}
            return {"background": work(), "commit": commit}
        if step == "report":
            return prepare_report(run, pipeline=True)
        raise PipelineError("STAGE_INVALID", "Unsupported pipeline stage.")

    def set_active(active):
        e["one_stop_active"].set(bool(active))

    def snapshot():
        import anndata as ad
        import numpy as np
        data = e["adata_obj"].get()
        if data is None:
            raise PipelineError("DOWNSTREAM_INPUT_REQUIRED", "Load the current analysis's data first.")
        # The native network only uses obs, spatial coordinates and colors.
        # Retain every observation, with no expression downsampling/copy.
        return ad.AnnData(X=np.empty((data.n_obs, 0)), obs=data.obs.copy(),
            obsm={"spatial": data.obsm["spatial"].copy()} if "spatial" in data.obsm else {},
            uns={ANNOTATION + "_colors": copy.deepcopy(data.uns[ANNOTATION + "_colors"])}
                if ANNOTATION + "_colors" in data.uns else {})

    def prepare_network(params):
        s = scope()
        data = snapshot()
        if params.get("split_by") == "auto":
            params["split_by"] = "sample" if "sample" in data.obs else None
        p = validate_network(data, params)
        fingerprint = network_fingerprint(data, p)
        base = root() / ("network_" + uuid.uuid4().hex)
        input_path, output_path = base / "input.h5ad", base / "output"
        async def work():
            async with _PLOT_LIMIT:
                def save():
                    base.mkdir(parents=True, exist_ok=False)
                    data.write_h5ad(input_path)
                await asyncio.to_thread(save)
                await bounded_child([sys.executable, str(Path(__file__).with_name("spatialmeta_native_features.py")),
                    "network", "--input", input_path, "--output", output_path, "--parameters", json.dumps(p)])
                return output_path
        def commit(value):
            if scope() != s or network_fingerprint(snapshot(), p) != fingerprint:
                raise PipelineError("INPUT_CHANGED", "Data or annotations changed while the plot was generated; stale results were not adopted.")
            return {"root": Path(value), "scope": s, "fingerprint": fingerprint, "parameters": p}
        return {"background": work(), "commit": commit}

    def network_current(result):
        try:
            return result["scope"] == scope() and root().resolve() in result["root"].resolve().parents and \
                network_fingerprint(snapshot(), result["parameters"]) == result["fingerprint"]
        except Exception:
            return False

    def prepare_report(run, pipeline=False):
        s = scope()
        data = e["adata_obj"].get()
        if data is None:
            raise PipelineError("RESULT_REQUIRED", "Load a real analysis result before exporting a report.")
        inventory = result_inventory(data)
        stable_inventory = copy.deepcopy(inventory)
        source_reference = copy.deepcopy(e["downstream_input_reference"].get())
        dest = root() / ("report_" + uuid.uuid4().hex)
        tables = {}
        result = e["marker_res"].get()
        if result:
            ranked = result.get("adata")
            same_labels = ranked is not None and ranked.obs_names.equals(data.obs_names)
            if same_labels and ANNOTATION in data.obs:
                same_labels = ANNOTATION in ranked.obs and ranked.obs[ANNOTATION].astype(str).equals(data.obs[ANNOTATION].astype(str))
            if same_labels:
                import pandas as pd
                for key in ("rank_genes_groups", "rank_metabolites_groups"):
                    if key not in ranked.uns:
                        continue
                    result_dict = ranked.uns[key]
                    names = pd.DataFrame(result_dict["names"])
                    rows = []
                    fields = {field: pd.DataFrame(result_dict[field]) for field in
                        ("scores", "logfoldchanges", "pvals", "pvals_adj") if field in result_dict}
                    for group in names.columns:
                        for rank, feature in enumerate(names[group]):
                            row = {"group": str(group), "rank": rank + 1, "feature": feature}
                            row.update({field: value[group].iloc[rank] for field, value in fields.items()})
                            rows.append(row)
                    tables[key] = pd.DataFrame(rows)
                correlations = ranked.uns.get("corrcoef_stsm_ingroup") or {}
                correlation_rows = []
                for group, item in correlations.items():
                    for i, gene in enumerate(item.get("gene", [])):
                        for j, metabolite in enumerate(item.get("metabolite", [])):
                            correlation_rows.append({"group": str(group), "gene": str(gene),
                                "metabolite": str(metabolite), "pearson_r": item["data"][i, j]})
                if correlation_rows:
                    tables["gene_metabolite_correlations"] = pd.DataFrame(correlation_rows)
            else:
                inventory["marker_report_warning"] = "Existing Marker output no longer matches the current observations/annotations; stale tables were not exported."
        state = copy.deepcopy(run.to_dict()) if run else None
        async def work():
            return await asyncio.to_thread(export_ai_report, dest, run_state=state,
                summaries={"observed_results": inventory, "source_reference": source_reference}, tables=tables)
        def commit(path):
            if scope() != s or result_inventory(e["adata_obj"].get()) != stable_inventory:
                raise PipelineError("INPUT_CHANGED", "Results changed while the report was generated.")
            atomic_json(root() / "latest_report.json", {"owner": s.owner, "analysis": s.analysis,
                "relative_path": str(Path(path).relative_to(root())), "sha256": sha256_file(path), "inventory": stable_inventory})
            return {"evidence": {"report": "analysis_report.zip", "external_ai_called": False,
                "stopped_before_dash": True}} if pipeline else path
        return {"background": work(), "commit": commit}

    def existing_report(run):
        s = scope()
        pointer = root() / "latest_report.json"
        if not pointer.is_file():
            return None
        record = json.loads(pointer.read_text(encoding="utf-8"))
        path = (root() / record["relative_path"]).resolve()
        if record.get("owner") != s.owner or record.get("analysis") != s.analysis or root().resolve() not in path.parents:
            raise PipelineError("REPORT_SCOPE_INVALID", "Report does not belong to this exact analysis.")
        if record.get("inventory") != result_inventory(e["adata_obj"].get()) or sha256_file(path) != record["sha256"]:
            raise PipelineError("REPORT_STALE", "The data changed; generate a new report.")
        return path

    def error(exc):
        return e["user_facing_error"]("Analysis", exc)

    return {name: value for name, value in locals().copy().items() if name in {
        "scope", "root", "resolve_upload", "validate_start", "validate_resume", "parameters", "dispatch",
        "observe", "accept_artifacts", "set_active", "preview_manual", "validate_manual", "manual_preview", "manual_ready",
        "prepare_network", "network_current", "prepare_report", "existing_report", "error"}}
