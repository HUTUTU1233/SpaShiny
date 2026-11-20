# Extracted from /app/app/ST-SM.py. Feature: alignment_manual; ordered phases preserve original initialization.
from spashiny._shared import runtime_globals as _spashiny_globals


def _install_0(_spashiny_ctx):
    _spashiny_ctx.rv = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.adata_sm_transformed = _spashiny_ctx.reactive.Value(None)
    import spatialmeta as smt

    _spashiny_globals.smt = smt
    from spatialmeta.model import AlignmentModule

    _spashiny_globals.AlignmentModule = AlignmentModule
    import numpy as np

    _spashiny_globals.np = np
    import pandas as pd

    _spashiny_ctx.pd = pd
    import scanpy as sc

    _spashiny_globals.sc = sc
    import torch

    _spashiny_globals.torch = torch
    import copy

    _spashiny_ctx.copy = copy
    import matplotlib

    _spashiny_ctx.matplotlib = matplotlib
    import matplotlib.pyplot as plt

    _spashiny_globals.plt = plt

    def configure_spashiny_matplotlib_fonts():
        """Use an installed font family and undo SpatialMETA's arial-only rcParams."""
        try:
            from matplotlib import font_manager

            installed = {str(font.name).lower() for font in font_manager.fontManager.ttflist}
            preferred = []
            if "arial" in installed:
                preferred.append("Arial")
            if "dejavu sans" in installed:
                preferred.append("DejaVu Sans")
            preferred.extend(["sans-serif"])
            _spashiny_ctx.matplotlib.rcParams["font.family"] = preferred
            _spashiny_ctx.matplotlib.rcParams["font.sans-serif"] = [
                name for name in preferred if name != "sans-serif"
            ] or ["DejaVu Sans"]
        except Exception:
            _spashiny_ctx.matplotlib.rcParams["font.family"] = ["DejaVu Sans", "sans-serif"]
            _spashiny_ctx.matplotlib.rcParams["font.sans-serif"] = ["DejaVu Sans"]

    _spashiny_ctx.configure_spashiny_matplotlib_fonts = configure_spashiny_matplotlib_fonts
    _spashiny_ctx.configure_spashiny_matplotlib_fonts()
    _spashiny_ctx.console_logs = _spashiny_ctx.reactive.Value("")

    def log(msg: str):
        """Write messages to both the console and frontend log panel"""
        msg = _spashiny_globals.sanitize_log_message(msg)
        _spashiny_globals.safe_console_print(msg, flush=True)
        old = _spashiny_ctx.console_logs.get()
        new = f"{old}\n{msg}" if old else msg
        _spashiny_ctx.console_logs.set(new)

    _spashiny_ctx.log = log

    @_spashiny_ctx.output
    @_spashiny_ctx.render.text
    def console_output():
        """Render logs to the frontend"""
        return _spashiny_ctx.console_logs.get()

    _spashiny_ctx.console_output = console_output

    @_spashiny_ctx.output
    @_spashiny_ctx.render.text
    def process_status_stsm_pre():
        txt = _spashiny_ctx.console_logs.get()
        return txt.splitlines()[-1] if txt else "Ready"

    _spashiny_ctx.process_status_stsm_pre = process_status_stsm_pre

    def _ssh_remote_enabled():
        return _spashiny_globals.ssh_connection_ready(_spashiny_ctx.ssh_state.get())

    _spashiny_ctx._ssh_remote_enabled = _ssh_remote_enabled

    def _run_remote_stsm_job(job_prefix, script_text, upload_files, output_names, command_args):
        import json
        import uuid

        state = _spashiny_ctx.ssh_state.get()
        client = _spashiny_globals.ssh_open_client(state)
        local_job_dir = (
            _spashiny_ctx.Path(_spashiny_ctx.create_temp_dir())
            / "ssh_remote_results"
            / f"{job_prefix}_{uuid.uuid4().hex[:12]}"
        )
        local_job_dir.mkdir(parents=True, exist_ok=True)
        try:
            remote_dir = _spashiny_globals.ssh_prepare_job_dir(client, state, job_prefix)
            _spashiny_ctx.log(f" SSH remote job directory: {remote_dir}")
            for local_path, remote_name in upload_files:
                _spashiny_ctx.log(
                    f" Uploading {_spashiny_ctx.Path(local_path).name} -> {remote_name}"
                )
                _spashiny_globals.ssh_upload_file(client, local_path, f"{remote_dir}/{remote_name}")
            _spashiny_globals.ssh_upload_text(client, f"{remote_dir}/run_job.py", script_text)
            python_cmd = (
                state.get("stsm_python_cmd") or state.get("python_cmd") or "python"
            ).strip()
            _spashiny_ctx.log(" Checking remote ST-SM Python environment dependencies...")
            _spashiny_globals.ssh_check_python_packages(
                client, python_cmd, _spashiny_globals.REQUIRED_STSM_PACKAGES, label="ST-SM"
            )
            arg_text = " ".join((_spashiny_globals.ssh_quote(arg) for arg in command_args))
            command = f"cd {_spashiny_globals.ssh_quote(remote_dir)} && {python_cmd} run_job.py {arg_text}"
            _spashiny_ctx.log(f" Running remote ST-SM job with: {python_cmd}")
            result = _spashiny_globals.ssh_exec_command(client, command, timeout=None)
            stdout = (result.get("stdout") or "").strip()
            stderr = (result.get("stderr") or "").strip()
            if stdout:
                _spashiny_ctx.log("[REMOTE STDOUT]\n" + stdout)
            if stderr:
                _spashiny_ctx.log("[REMOTE STDERR]\n" + stderr)
            if result.get("exit_status") != 0:
                raise RuntimeError(
                    f"Remote job failed with exit code {result.get('exit_status')}.\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
                )
            downloaded = {}
            for output_name in output_names:
                local_output = local_job_dir / output_name
                _spashiny_globals.ssh_download_file(
                    client, f"{remote_dir}/{output_name}", local_output
                )
                downloaded[output_name] = local_output
                _spashiny_ctx.log(f" Downloaded remote result: {local_output}")
            meta_path = downloaded.get("meta.json")
            if meta_path and meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    _spashiny_ctx.log(f" Remote metadata: {json.dumps(meta, ensure_ascii=False)}")
                except Exception as e:
                    _spashiny_ctx.log(f" Failed to read remote metadata: {e}")
            return downloaded
        finally:
            client.close()

    _spashiny_ctx._run_remote_stsm_job = _run_remote_stsm_job

    def run_remote_alignment_preprocessing(st_path, sm_path):
        outputs = _spashiny_ctx._run_remote_stsm_job(
            "stsm_preprocess",
            _spashiny_globals.REMOTE_STSM_ALIGNMENT_PRE_SCRIPT,
            [(st_path, "input_st.h5ad"), (sm_path, "input_sm.h5ad")],
            ["processed_st.h5ad", "processed_sm.h5ad", "meta.json"],
            [
                "--st",
                "input_st.h5ad",
                "--sm",
                "input_sm.h5ad",
                "--out-st",
                "processed_st.h5ad",
                "--out-sm",
                "processed_sm.h5ad",
                "--meta",
                "meta.json",
            ],
        )
        return (
            _spashiny_globals.compact_adata_X(
                _spashiny_globals.sc.read_h5ad(str(outputs["processed_st.h5ad"]))
            ),
            _spashiny_globals.compact_adata_X(
                _spashiny_globals.sc.read_h5ad(str(outputs["processed_sm.h5ad"]))
            ),
        )

    _spashiny_ctx.run_remote_alignment_preprocessing = run_remote_alignment_preprocessing

    def run_remote_knn_reassignment(adata_ST, adata_SM, k, dist_fold):
        import uuid

        local_job_dir = (
            _spashiny_ctx.Path(_spashiny_ctx.create_temp_dir())
            / "ssh_remote_inputs"
            / f"knn_{uuid.uuid4().hex[:12]}"
        )
        local_job_dir.mkdir(parents=True, exist_ok=True)
        st_upload_path = local_job_dir / "knn_input_st.h5ad"
        sm_upload_path = local_job_dir / "knn_input_sm.h5ad"
        adata_ST.write_h5ad(str(st_upload_path))
        adata_SM.write_h5ad(str(sm_upload_path))
        outputs = _spashiny_ctx._run_remote_stsm_job(
            "stsm_knn",
            _spashiny_globals.REMOTE_STSM_KNN_SCRIPT,
            [(st_upload_path, "input_st.h5ad"), (sm_upload_path, "input_sm.h5ad")],
            ["knn_st.h5ad", "knn_sm.h5ad", "meta.json"],
            [
                "--st",
                "input_st.h5ad",
                "--sm",
                "input_sm.h5ad",
                "--k",
                str(int(k)),
                "--dist-fold",
                str(float(dist_fold)),
                "--out-st",
                "knn_st.h5ad",
                "--out-sm",
                "knn_sm.h5ad",
                "--meta",
                "meta.json",
            ],
        )
        return (
            _spashiny_globals.compact_adata_X(
                _spashiny_globals.sc.read_h5ad(str(outputs["knn_sm.h5ad"]))
            ),
            _spashiny_globals.compact_adata_X(
                _spashiny_globals.sc.read_h5ad(str(outputs["knn_st.h5ad"]))
            ),
        )

    _spashiny_ctx.run_remote_knn_reassignment = run_remote_knn_reassignment
    _spashiny_ctx.st_h5ad_path = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.sm_h5ad_path = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.alignment_st_input_reference = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.alignment_sm_input_reference = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.adata_st = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.adata_sm = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.alignment_manual_source_st = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.alignment_manual_source_sm = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.alignment_manual_source_spatial = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.alignment_workflow_id = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.manual_transform_job_id = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.manual_transform_metadata_val = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.manual_transform_coordinates_val = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.alignment_step6_result_id = _spashiny_ctx.reactive.Value(None)

    def _resolve_alignment_interactive_input(reference, *, input_role, side_label):
        if not isinstance(reference, dict):
            raise RuntimeError(f"Please upload {side_label} data or load the Y7_T example first.")
        session_record = _spashiny_ctx._cloud_session_record()
        analysis_session_id = str(_spashiny_ctx._cloud_analysis_session_id() or "").strip()
        if session_record is None or not analysis_session_id:
            raise RuntimeError(
                "The current tab analysis session is not ready. Please wait and try again."
            )
        from cloud.input_resolver import InputResolver

        source = str(reference.get("source") or "").strip()
        if source == "upload":
            resolved = InputResolver().resolve_interactive_local_input(
                session_id=session_record.session_id,
                analysis_session_id=analysis_session_id,
                upload_id=str(reference.get("upload_id") or ""),
                workflow_name="alignment_rasterization",
            )
        elif source == "example":
            resolved = InputResolver().resolve_interactive_local_input(
                session_id=session_record.session_id,
                analysis_session_id=analysis_session_id,
                action_id="y7-alignment-raw-example",
                input_role=input_role,
                workflow_name="alignment_rasterization",
            )
        else:
            raise RuntimeError(f"The selected {side_label} Alignment input source is invalid.")
        requested_mode = "USER_UPLOAD" if source == "upload" else "EXAMPLE"
        if str(resolved.get("input_source_mode") or "") != requested_mode:
            raise RuntimeError(
                f"{side_label} input source verification failed: requested {requested_mode}, resolved {resolved.get('input_source_mode') or 'unknown'}."
            )
        return resolved

    _spashiny_ctx._resolve_alignment_interactive_input = _resolve_alignment_interactive_input

    def _alignment_input_provenance(resolved):
        """Persist safe input identity without exposing server paths or credentials."""
        return {
            "source_mode": str(resolved.get("input_source_mode") or ""),
            "reference": str(resolved.get("upload_id") or resolved.get("action_id") or ""),
            "filename": str(resolved.get("filename") or ""),
            "sha256": str(resolved.get("sha256") or ""),
            "size_bytes": int(resolved.get("size_bytes") or 0),
        }

    _spashiny_ctx._alignment_input_provenance = _alignment_input_provenance

    def _sha256_alignment_artifact(path):
        import hashlib

        digest = hashlib.sha256()
        with _spashiny_ctx.Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    _spashiny_ctx._sha256_alignment_artifact = _sha256_alignment_artifact

    def _persist_alignment_handoff_artifact(adata_sm_obj, *, best_key, source):
        """Persist the actual Step6 SM result as a scoped internal artifact.

        The manifest stores a relative path and provenance identifiers only.
        Parent resolution later reconstructs the real path from the exact owner
        and analysis-session scope, so a browser cannot select an arbitrary
        server file or a historic workflow.
        """
        owner_id, analysis_session_id = _spashiny_ctx._require_alignment_scope()
        workflow_id = _spashiny_ctx._current_alignment_workflow_id()
        if not workflow_id:
            raise RuntimeError("No current Alignment workflow is available for KNN handoff.")
        if "spatial_transformed" not in adata_sm_obj.obsm:
            raise RuntimeError("Alignment Step6 did not produce obsm['spatial_transformed'].")
        coordinate_context = _spashiny_ctx.alignment_step5_coordinate_context.get() or {}
        coordinate_contract = (coordinate_context.get("summary") or {}).get(
            "coordinate_contract"
        ) or {}
        if (
            coordinate_context.get("workflow_id") != workflow_id
            or coordinate_context.get("job_id") != _spashiny_ctx._current_step5_job_id()
            or coordinate_contract.get("schema") != "spashiny.alignment.coordinate_contract"
            or (coordinate_contract.get("fit_output_space") != "st_image_pixels")
            or (float(coordinate_contract.get("to_st_full_resolution_scale", 0)) <= 0)
        ):
            raise RuntimeError(
                "The current Step5 result has no verified coordinate-unit contract. Recreate Step4/Step5 in this analysis before saving; raw SM coordinates cannot be substituted."
            )
        adata_sm_obj.uns["spashiny_alignment_coordinate_contract"] = dict(coordinate_contract)
        state = _spashiny_ctx._read_alignment_workflow_state(workflow_id)
        expression = None
        to_save = adata_sm_obj
        if _spashiny_globals.SPASHINY_WEB_PLATFORM:
            from cloud.knn_expression import (
                EXPRESSION_KEY,
                expression_record,
                full_expression_with_alignment,
            )

            original = (state.get("input_provenance") or {}).get("sm") or {}
            reference = original.get("reference")
            if original.get("source_mode") == "USER_UPLOAD" and reference:
                raw_reference = {"source": "upload", "upload_id": reference}
            elif (
                original.get("source_mode") == "EXAMPLE" and reference == "y7-alignment-raw-example"
            ):
                raw_reference = {"source": "example"}
            else:
                raise RuntimeError(
                    "The original full SM input is not recorded for this alignment. Do not export the feature-selected alignment matrix to KNN."
                )
            resolved = _spashiny_ctx._resolve_alignment_interactive_input(
                raw_reference, input_role="sm_raw_h5ad", side_label="Raw SM"
            )
            raw_path = _spashiny_ctx.Path(resolved["local_path"])
            raw_sha = _spashiny_ctx._sha256_alignment_artifact(raw_path)
            if (
                not original.get("sha256")
                or raw_sha != resolved.get("sha256")
                or raw_sha != original["sha256"]
            ):
                raise RuntimeError(
                    "The original SM file no longer matches this workflow's recorded input."
                )
            raw_sm = _spashiny_globals.sc.read_h5ad(raw_path)
            to_save = full_expression_with_alignment(raw_sm, adata_sm_obj)
            expression = expression_record(raw_sha, to_save.shape)
            to_save.uns[EXPRESSION_KEY] = expression
            to_save.uns["spashiny_alignment_coordinate_contract"] = dict(coordinate_contract)
        root = _spashiny_ctx._alignment_workflow_root(workflow_id)
        artifacts_dir = root / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        target = artifacts_dir / (
            f"aligned_sm_full_raw_{_spashiny_globals.uuid.uuid4().hex}.h5ad"
            if expression
            else "aligned_sm.h5ad"
        )
        temporary = target.with_suffix(".pending.h5ad")
        temporary.unlink(missing_ok=True)
        try:
            to_save.write_h5ad(temporary)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        artifact = {
            "role": "aligned_sm_h5ad",
            "relative_path": target.relative_to(root).as_posix(),
            "filename": target.name,
            "sha256": _spashiny_ctx._sha256_alignment_artifact(target),
            "size_bytes": int(target.stat().st_size),
            "coordinate_key": "spatial_transformed",
            "coordinate_contract": dict(coordinate_contract),
            "observation_count": int(to_save.n_obs),
            "feature_count": int(to_save.n_vars),
        }
        if expression:
            artifact["expression_contract"] = expression
        manifest = {
            "schema": "spashiny.alignment.handoff",
            "version": 1,
            "parent_workflow_id": workflow_id,
            "owner_session_id": owner_id,
            "analysis_session_id": analysis_session_id,
            "source_step5_job_id": _spashiny_ctx._current_step5_job_id(),
            "best_alignment_key": str(best_key),
            "alignment_source": str(source or ""),
            "coordinate_contract": dict(coordinate_contract),
            "input_lineage": dict(state.get("input_provenance") or {}),
            "artifact": artifact,
        }
        (root / "alignment_handoff_manifest.json").write_text(
            _spashiny_ctx.json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return artifact

    _spashiny_ctx._persist_alignment_handoff_artifact = _persist_alignment_handoff_artifact

    def _alignment_input_display(reference, label):
        if not isinstance(reference, dict):
            text = f"{label}: none selected."
        elif str(reference.get("source") or "") == "upload":
            text = f"{label}: Uploaded — {reference.get('filename') or 'H5AD'}."
        else:
            text = f"{label}: Example — Y7_T raw H5AD."
        return _spashiny_ctx.ui.tags.div(
            text, class_="cloud-muted", style="font-size: 12px; margin-top: 8px;"
        )

    _spashiny_ctx._alignment_input_display = _alignment_input_display

    @_spashiny_ctx.output
    @_spashiny_ctx.render.ui
    def alignment_st_current_input():
        return _spashiny_ctx._alignment_input_display(
            _spashiny_ctx.alignment_st_input_reference.get(), "ST"
        )

    _spashiny_ctx.alignment_st_current_input = alignment_st_current_input

    @_spashiny_ctx.output
    @_spashiny_ctx.render.ui
    def alignment_sm_current_input():
        return _spashiny_ctx._alignment_input_display(
            _spashiny_ctx.alignment_sm_input_reference.get(), "SM"
        )

    _spashiny_ctx.alignment_sm_current_input = alignment_sm_current_input

    def _track_alignment_canonical_upload(payload, *, side_label, input_role, target_reference):
        if not isinstance(payload, dict):
            return
        status = str(payload.get("status") or "").upper()
        filename = str(payload.get("filename") or f"uploaded {side_label} h5ad")
        if status == "READY":
            upload_id = str(payload.get("upload_id") or "").strip()
            if not upload_id:
                _spashiny_ctx.log(
                    f"{side_label} Alignment upload failed: completion returned no upload reference."
                )
                return
            try:
                resolved = _spashiny_ctx._resolve_alignment_interactive_input(
                    {"source": "upload", "upload_id": upload_id},
                    input_role=input_role,
                    side_label=side_label,
                )
            except Exception as exc:
                target_reference.set(None)
                _spashiny_ctx.log(
                    f"{side_label} Alignment upload is not available to this tab: {exc}"
                )
                _spashiny_ctx.ui.notification_show(
                    f"{side_label} Alignment upload is not available to this tab: {exc}",
                    type="error",
                    duration=8,
                )
                return
            target_reference.set(
                {"source": "upload", "upload_id": upload_id, "filename": resolved["filename"]}
            )
            _spashiny_ctx.log(f"{side_label} Alignment upload ready: {resolved['filename']}.")
        elif status == "FAILED":
            target_reference.set(None)
            _spashiny_ctx.log(
                _spashiny_globals._upload_failure_text(
                    payload, filename, f"{side_label} Alignment upload"
                )
            )

    _spashiny_ctx._track_alignment_canonical_upload = _track_alignment_canonical_upload

    def _ensure_step7_pdf_artifact():
        persisted_pdf = _spashiny_ctx._step7_persisted_pdf_artifact()
        if persisted_pdf is not None:
            return persisted_pdf
        fig = None
        try:
            fig = _spashiny_ctx.build_step7_alignment_figure()
            if not getattr(fig, "_spashiny_alignment_ready", False):
                raise RuntimeError(
                    "Step7 is not ready for the current workflow. Complete Step5 and save its exact result in Step6; no placeholder PDF was exported."
                )
            colored = _spashiny_ctx.colorize_plot("align_step7_show_alignment_plot", fig)
            if colored is not fig:
                _spashiny_globals.plt.close(fig)
                fig = colored
            _spashiny_ctx._persist_step7_artifact(fig, _spashiny_ctx._current_step5_job_id())
            path = _spashiny_ctx._step7_persisted_pdf_artifact()
            if path is None:
                raise RuntimeError(
                    "Step7 PDF could not be validated for the current input lineage."
                )
            return path
        finally:
            if fig is not None:
                _spashiny_globals.plt.close(fig)

    _spashiny_ctx._ensure_step7_pdf_artifact = _ensure_step7_pdf_artifact

    @_spashiny_ctx.render.download(filename=lambda: "aligned_sm_alignment_preview.pdf")
    def download_alignment_step7_pdf():
        yield from _spashiny_ctx.stream_file(_spashiny_ctx._ensure_step7_pdf_artifact())

    _spashiny_ctx.download_alignment_step7_pdf = download_alignment_step7_pdf

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.alignment_st_canonical_upload)
    def _track_alignment_st_canonical_upload():
        if _spashiny_globals.SPASHINY_WEB_PLATFORM:
            try:
                payload = _spashiny_ctx.input.alignment_st_canonical_upload() or {}
            except Exception:
                payload = {}
            _spashiny_ctx._track_alignment_canonical_upload(
                payload,
                side_label="ST",
                input_role="st_raw_h5ad",
                target_reference=_spashiny_ctx.alignment_st_input_reference,
            )

    _spashiny_ctx._track_alignment_st_canonical_upload = _track_alignment_st_canonical_upload

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.alignment_sm_canonical_upload)
    def _track_alignment_sm_canonical_upload():
        if _spashiny_globals.SPASHINY_WEB_PLATFORM:
            try:
                payload = _spashiny_ctx.input.alignment_sm_canonical_upload() or {}
            except Exception:
                payload = {}
            _spashiny_ctx._track_alignment_canonical_upload(
                payload,
                side_label="SM",
                input_role="sm_raw_h5ad",
                target_reference=_spashiny_ctx.alignment_sm_input_reference,
            )

    _spashiny_ctx._track_alignment_sm_canonical_upload = _track_alignment_sm_canonical_upload

    def _activate_alignment_example_inputs(*, activate):
        """Validate both exact-scoped roles before changing either page input."""
        session_record = _spashiny_ctx._cloud_session_record()
        analysis_session_id = str(_spashiny_ctx._cloud_analysis_session_id() or "").strip()
        if session_record is None or not analysis_session_id:
            raise RuntimeError(
                "The current tab analysis session is not ready. Please wait and try again."
            )
        action_id = "y7-alignment-raw-example"
        if str(session_record.status or "") != "ACTIVE":
            raise RuntimeError("The owner session is no longer active. Start a new session.")
        from cloud.database import CloudDatabase

        try:
            analysis = CloudDatabase(read_only=True).get_analysis_session(
                analysis_session_id, owner_session_id=session_record.session_id
            )
        except KeyError as exc:
            raise RuntimeError(
                "This analysis is not available to the authenticated owner."
            ) from exc
        if str(analysis.get("status") or "") != "ACTIVE":
            raise RuntimeError(
                "This analysis has ended. Start a new analysis; the old one cannot be restored."
            )
        if activate:
            from cloud.example_action_bindings import ExampleActionBindingService

            result = ExampleActionBindingService().activate(
                session=session_record,
                analysis_session_id=analysis_session_id,
                action_id=action_id,
                page_name="alignment",
            )
            if not bool(result.get("ready")):
                missing = ", ".join((str(role) for role in result.get("missing_roles") or []))
                raise RuntimeError(
                    "Y7_T Alignment example inputs are unavailable"
                    + (f": {missing}." if missing else ".")
                )
        reference = {"source": "example", "action_id": action_id}
        st_resolved = _spashiny_ctx._resolve_alignment_interactive_input(
            reference, input_role="st_raw_h5ad", side_label="ST"
        )
        sm_resolved = _spashiny_ctx._resolve_alignment_interactive_input(
            reference, input_role="sm_raw_h5ad", side_label="SM"
        )
        _spashiny_ctx.alignment_st_input_reference.set(dict(reference))
        _spashiny_ctx.alignment_sm_input_reference.set(dict(reference))
        _spashiny_ctx.st_h5ad_path.set(str(st_resolved["local_path"]))
        _spashiny_ctx.sm_h5ad_path.set(str(sm_resolved["local_path"]))
        _spashiny_ctx.log(
            "Alignment inputs selected: Example — Y7_T raw ST and SM H5AD. Click Start Preprocessing before manual alignment."
        )
        _spashiny_ctx.ui.notification_show(
            "Y7_T ST and SM inputs are ready. Click Start Preprocessing to prepare manual alignment.",
            type="message",
            duration=7,
        )

    _spashiny_ctx._activate_alignment_example_inputs = _activate_alignment_example_inputs

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.load_example_raw_h5ad)
    def load_example_raw_h5ad():
        if _spashiny_globals.SPASHINY_WEB_PLATFORM:
            try:
                _spashiny_ctx._activate_alignment_example_inputs(activate=True)
            except Exception as exc:
                _spashiny_ctx.log(f"Failed to select Alignment example inputs: {exc}")
                _spashiny_ctx.ui.notification_show(
                    f"Failed to select Alignment example inputs: {exc}", type="error", duration=10
                )
            return
        try:
            st_path, sm_path = _spashiny_globals.get_example_raw_h5ad_paths()
            _spashiny_ctx.st_h5ad_path.set(str(st_path))
            _spashiny_ctx.sm_h5ad_path.set(str(sm_path))
            _spashiny_ctx.log(f"Example raw ST h5ad selected: {st_path}")
            _spashiny_ctx.log(f"Example raw SM h5ad selected: {sm_path}")
            _spashiny_ctx.ui.notification_show(
                "Example raw ST/SM h5ad files are ready. Continue with the next processing step.",
                type="message",
                duration=5,
            )
        except Exception as e:
            _spashiny_ctx.log(f"Failed to load example raw h5ad files: {e}")
            _spashiny_ctx.ui.notification_show(
                f"Failed to load example raw h5ad files: {e}", type="error", duration=8
            )

    _spashiny_ctx.load_example_raw_h5ad = load_example_raw_h5ad

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(
        _spashiny_ctx.input.cloud_example_action_activated, ignore_none=True
    )
    def _select_alignment_example_from_cloud_action():
        if not _spashiny_globals.SPASHINY_WEB_PLATFORM:
            return
        try:
            payload = _spashiny_ctx.input.cloud_example_action_activated() or {}
        except Exception:
            payload = {}
        if (
            not isinstance(payload, dict)
            or str(payload.get("action_id") or "") != "y7-alignment-raw-example"
            or (not bool(payload.get("ready")))
            or (not str(payload.get("analysis_session_id") or "").strip())
            or (
                str(payload.get("analysis_session_id") or "")
                != str(_spashiny_ctx._cloud_analysis_session_id() or "")
            )
        ):
            return
        try:
            _spashiny_ctx._activate_alignment_example_inputs(activate=False)
        except Exception as exc:
            _spashiny_ctx.log(f"Failed to select Alignment example inputs: {exc}")
            _spashiny_ctx.ui.notification_show(
                f"Failed to select Alignment example inputs: {exc}", type="error", duration=10
            )

    _spashiny_ctx._select_alignment_example_from_cloud_action = (
        _select_alignment_example_from_cloud_action
    )

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.process_alignment_pre)
    def process_alignment_pre():
        """Run preprocessing for ST and SM data to prepare for downstream alignment"""
        if not _spashiny_ctx._start_alignment_workflow_modal(
            "preprocess", "ST and SM preprocessing is running. Please wait..."
        ):
            return
        preprocessing_succeeded = False
        preprocessing_error = None
        try:
            if _spashiny_globals.SPASHINY_WEB_PLATFORM:
                st_resolved = _spashiny_ctx._resolve_alignment_interactive_input(
                    _spashiny_ctx.alignment_st_input_reference.get(),
                    input_role="st_raw_h5ad",
                    side_label="ST",
                )
                sm_resolved = _spashiny_ctx._resolve_alignment_interactive_input(
                    _spashiny_ctx.alignment_sm_input_reference.get(),
                    input_role="sm_raw_h5ad",
                    side_label="SM",
                )
                st_path = str(st_resolved["local_path"])
                sm_path = str(sm_resolved["local_path"])
                input_provenance = {
                    "analysis_session_id": str(_spashiny_ctx._cloud_analysis_session_id() or ""),
                    "alignment_method": "SpatialMETA alignment preprocessing",
                    "st": _spashiny_ctx._alignment_input_provenance(st_resolved),
                    "sm": _spashiny_ctx._alignment_input_provenance(sm_resolved),
                }
                _spashiny_ctx.st_h5ad_path.set(st_path)
                _spashiny_ctx.sm_h5ad_path.set(sm_path)
            else:
                st_path = _spashiny_ctx.st_h5ad_path.get()
                sm_path = _spashiny_ctx.sm_h5ad_path.get()
                input_provenance = {
                    "analysis_session_id": str(_spashiny_ctx._cloud_analysis_session_id() or ""),
                    "alignment_method": "SpatialMETA alignment preprocessing",
                    "st": {
                        "source_mode": "LOCAL",
                        "filename": _spashiny_ctx.Path(str(st_path or "")).name,
                    },
                    "sm": {
                        "source_mode": "LOCAL",
                        "filename": _spashiny_ctx.Path(str(sm_path or "")).name,
                    },
                }
            if not st_path or not sm_path:
                raise RuntimeError("Please upload both ST and SM h5ad files first.")
            if _spashiny_ctx._ssh_remote_enabled():
                _spashiny_ctx.log(
                    " SSH connected: running ST-SM preprocessing on the remote server."
                )
                adata_st_local, adata_sm_local = _spashiny_ctx.run_remote_alignment_preprocessing(
                    st_path, sm_path
                )
                from cloud.sm_coordinate_policy import initial_sm_display_coordinates

                initial_sm_display_coordinates(adata_sm_local)
                _spashiny_ctx.log(f"Remote ST data shape: {adata_st_local.shape}")
                _spashiny_ctx.log(f"Remote SM data shape: {adata_sm_local.shape}")
                input_provenance["st"]["shape"] = list(adata_st_local.shape)
                input_provenance["sm"]["shape"] = list(adata_sm_local.shape)
                _spashiny_ctx._begin_alignment_workflow(
                    st_path, sm_path, adata_sm_local, input_provenance=input_provenance
                )
                _spashiny_ctx.adata_st.set(adata_st_local)
                _spashiny_ctx.adata_sm.set(adata_sm_local)
                _spashiny_ctx.alignment_manual_source_st.set(adata_st_local)
                _spashiny_ctx.alignment_manual_source_sm.set(adata_sm_local)
                _spashiny_ctx.alignment_manual_source_spatial.set(
                    _spashiny_globals.np.asarray(adata_sm_local.obsm["spatial"]).copy()
                )
                try:
                    adata_st_obj = _spashiny_ctx.adata_st.get()
                    adata_sm_obj = _spashiny_ctx.adata_sm.get()
                    _spashiny_ctx.configure_spashiny_matplotlib_fonts()
                    _spashiny_globals.smt.pl.plot_spot_sm_st(
                        adata_SM=adata_sm_obj,
                        adata_ST=adata_st_obj,
                        marker="H",
                        SM_spatial_key="spatial",
                        stacked=True,
                    )
                    _spashiny_globals.plt.close("all")
                    _spashiny_ctx.log(
                        " Initial ST and SM overlay plot has been generated from remote results."
                    )
                except Exception as e:
                    _spashiny_ctx.log(
                        f" Failed to initialize image overlay from remote results: {e}"
                    )
                _spashiny_ctx.log(
                    " Remote ST and SM preprocessing completed successfully. Ready for alignment."
                )
                job_id, _ = _spashiny_ctx._submit_manual_preview("initial")
                _spashiny_ctx.initial_preview_job_id.set(job_id)
                _spashiny_ctx._update_alignment_workflow_state(
                    initial_preview_job_id=job_id, initial_preview_status="queued"
                )
                preprocessing_succeeded = True
                return
            _spashiny_ctx.log(" Starting ST and SM data loading ...")
            adata_st_local = _spashiny_globals.compact_adata_X(
                _spashiny_globals.smt.read_h5ad_st(st_path)
            )
            adata_sm_local = _spashiny_globals.compact_adata_X(
                _spashiny_globals.smt.read_h5ad_sm(sm_path)
            )
            from cloud.sm_coordinate_policy import (
                initialize_sm_coordinates,
                capture_sm_coordinate_state,
                restore_sm_coordinate_state,
            )

            initialize_sm_coordinates(adata_sm_local)
            sm_coordinate_snapshot = capture_sm_coordinate_state(adata_sm_local)
            _spashiny_ctx.log(f"ST data shape: {adata_st_local.shape}")
            _spashiny_ctx.log(f"SM data shape: {adata_sm_local.shape}")
            input_provenance["st"]["shape"] = list(adata_st_local.shape)
            input_provenance["sm"]["shape"] = list(adata_sm_local.shape)
            _spashiny_ctx.log(
                " Running normalization and spatial variable calculation for ST data ..."
            )

            def normalize_non_inplace(adata):
                _spashiny_globals.set_compact_layer(adata, "normalized")
                _spashiny_globals.sc.pp.normalize_total(adata, layer="normalized")
                _spashiny_globals.sc.pp.log1p(adata, layer="normalized")

            normalize_non_inplace(adata_st_local)
            _spashiny_globals.smt.pp.spatial_variable(
                adata_st_local,
                n_top_variable=2000,
                add_key="highly_variable_moranI",
                layer="normalized",
            )
            adata_st_local = adata_st_local[:, adata_st_local.var["highly_variable_moranI"]].copy()
            from stsm_data_metadata import normalize_alignment_coordinates

            normalize_alignment_coordinates(
                adata_st_local,
                modality="ST",
                source_sha256=input_provenance["st"].get("sha256", ""),
            )
            _spashiny_ctx.log("ST data preprocessing completed.")
            _spashiny_ctx.log(
                " Running normalization and spatial variable calculation for SM data ..."
            )
            _spashiny_globals.sc.pp.normalize_total(adata_sm_local, target_sum=1000.0)
            _spashiny_globals.smt.pp.spatial_variable(
                adata_sm_local, n_top_variable=500, add_key="highly_variable_moranI"
            )
            adata_sm_local = adata_sm_local[:, adata_sm_local.var["highly_variable_moranI"]].copy()
            restore_sm_coordinate_state(adata_sm_local, sm_coordinate_snapshot)
            from cloud.sm_coordinate_policy import initial_sm_display_coordinates

            coordinate_record = initial_sm_display_coordinates(adata_sm_local)
            _spashiny_ctx.log(
                f"SM coordinate state: {coordinate_record['state']} ({coordinate_record['evidence']}). Original/imported MSI coordinates preserved; authoritative normalization is deferred until the final manual transform."
            )
            _spashiny_ctx.log("SM data preprocessing completed.")
            _spashiny_ctx._begin_alignment_workflow(
                st_path, sm_path, adata_sm_local, input_provenance=input_provenance
            )
            _spashiny_ctx.adata_st.set(adata_st_local)
            _spashiny_ctx.adata_sm.set(adata_sm_local)
            _spashiny_ctx.alignment_manual_source_st.set(adata_st_local)
            _spashiny_ctx.alignment_manual_source_sm.set(adata_sm_local)
            _spashiny_ctx.alignment_manual_source_spatial.set(
                _spashiny_globals.np.asarray(adata_sm_local.obsm["spatial"]).copy()
            )
            try:
                adata_st_obj = _spashiny_ctx.adata_st.get()
                adata_sm_obj = _spashiny_ctx.adata_sm.get()
                _spashiny_ctx.configure_spashiny_matplotlib_fonts()
                _spashiny_globals.smt.pl.plot_spot_sm_st(
                    adata_SM=adata_sm_obj,
                    adata_ST=adata_st_obj,
                    marker="H",
                    SM_spatial_key="spatial",
                    stacked=True,
                )
                _spashiny_globals.plt.close("all")
                _spashiny_ctx.log(
                    " Initial ST and SM overlay plot has been generated. You can now perform rotation and translation in the interactive interface."
                )
            except Exception as e:
                _spashiny_ctx.log(f" Failed to initialize image overlay: {e}")
            _spashiny_ctx.log(
                " ST and SM preprocessing completed successfully. Ready for alignment."
            )
            job_id, _ = _spashiny_ctx._submit_manual_preview("initial")
            _spashiny_ctx.initial_preview_job_id.set(job_id)
            _spashiny_ctx._update_alignment_workflow_state(
                initial_preview_job_id=job_id, initial_preview_status="queued"
            )
            preprocessing_succeeded = True
        except Exception as e:
            preprocessing_error = e
            _spashiny_ctx.log(f"Error during alignment preprocessing: {e}")
        finally:
            if preprocessing_succeeded:
                _spashiny_ctx._complete_alignment_workflow_modal("preprocess")
            else:
                _spashiny_ctx._fail_alignment_workflow_modal(
                    "preprocess", preprocessing_error or "Preprocessing did not complete"
                )
            _spashiny_globals.release_unused_memory()

    _spashiny_ctx.process_alignment_pre = process_alignment_pre
    _spashiny_ctx.initial_preview_job_id = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.initial_preview_img_val = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.manual_preview_job_id = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.manual_preview_img_val = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.manual_transform_val = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.side_preview_job_id = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.side_preview_img_val = _spashiny_ctx.reactive.Value(None)

    def _manual_transform_from_inputs(kind="overlay"):
        if kind != "overlay":
            return {}
        coordinate_policy = {
            "profile": "manual",
            "coordinate_source": "current_spatial",
            "declared_state": "auto",
        }
        if _spashiny_ctx.one_stop_transform_override.get() is not None:
            return {**dict(_spashiny_ctx.one_stop_transform_override.get()), **coordinate_policy}
        return {
            **coordinate_policy,
            "rotation": float(_spashiny_ctx.input.angle_input() or 0),
            "horizontal_flip": bool(_spashiny_ctx.input.flip_horizontal()),
            "vertical_flip": bool(_spashiny_ctx.input.flip_vertical()),
            "scale_width": float(_spashiny_ctx.input.sm_uniform_scale()),
            "scale_height": float(_spashiny_ctx.input.sm_uniform_scale()),
            "translation_x": float(_spashiny_ctx.input.translation_x() or 0),
            "translation_y": float(_spashiny_ctx.input.translation_y() or 0),
            "mode": "overlay",
        }

    _spashiny_ctx._manual_transform_from_inputs = _manual_transform_from_inputs

    @_spashiny_ctx.render.text
    def sm_coordinate_policy_status():
        base = _spashiny_ctx.alignment_manual_source_sm.get()
        if base is None:
            return "Coordinate state: load the current ST/SM input pair first."
        try:
            from cloud.sm_coordinate_policy import resolved_transform

            _, state, params, policy = resolved_transform(
                base, _spashiny_ctx._manual_transform_from_inputs("overlay")
            )
            return f"Input: {state['state']} ({state['evidence']}); resolved rotation: {params['rotation']:g} degrees; uniform scale: {params['scale_width']:g}x; {policy['reason']}. These resolved values, not ignored controls, are saved with the artifact."
        except Exception as exc:
            return f"Coordinate policy requires attention: {exc}"

    _spashiny_ctx.sm_coordinate_policy_status = sm_coordinate_policy_status

    def _write_manual_preview_inputs(job_dir, *, require_raw=True):
        input_dir = _spashiny_ctx.Path(job_dir) / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        ad_st = _spashiny_ctx.alignment_manual_source_st.get()
        ad_sm = _spashiny_ctx.alignment_manual_source_sm.get()
        source_spatial = _spashiny_ctx.alignment_manual_source_spatial.get()
        if ad_st is None or ad_sm is None or source_spatial is None:
            raise RuntimeError("ST or SM data is not loaded. Run alignment preprocessing first.")
        current_spatial = _spashiny_globals.np.asarray(ad_sm.obsm["spatial"])
        if current_spatial.shape != source_spatial.shape:
            raise RuntimeError(
                "The original SM coordinates no longer match this preprocessing run. Run alignment preprocessing again."
            )
        if not _spashiny_globals.np.array_equal(current_spatial, source_spatial):
            from cloud.sm_coordinate_policy import copy_with_coordinate_state

            ad_sm = copy_with_coordinate_state(ad_sm)
            ad_sm.obsm["spatial"] = source_spatial.copy()
        st_path = input_dir / "manual_preview_st.h5ad"
        sm_path = input_dir / "manual_preview_sm.h5ad"
        if not require_raw:
            ad_st.write_h5ad(st_path)
            ad_sm.write_h5ad(sm_path)
            return (st_path, sm_path, None, {})
        raw_resolved = _spashiny_ctx._resolve_alignment_interactive_input(
            _spashiny_ctx.alignment_sm_input_reference.get(),
            input_role="sm_raw_h5ad",
            side_label="Raw SM",
        )
        raw_sm = _spashiny_globals.sc.read_h5ad(str(raw_resolved["local_path"]))
        if list(raw_sm.obs_names) != list(ad_sm.obs_names):
            raise RuntimeError(
                "Full Raw SM spot identity/order differs from the current preprocessing run."
            )
        from cloud.sm_coordinate_policy import initialize_sm_coordinates

        initialize_sm_coordinates(raw_sm)
        if not _spashiny_globals.np.array_equal(
            raw_sm.obsm["spatial_input_original"], ad_sm.obsm["spatial_input_original"]
        ):
            raise RuntimeError(
                "Full Raw SM imported coordinates differ from this preprocessing input."
            )
        raw_sm.obsm["spatial"] = _spashiny_globals.np.asarray(ad_sm.obsm["spatial"]).copy()
        raw_sm.uns["spashiny_sm_coordinate_input"] = dict(ad_sm.uns["spashiny_sm_coordinate_input"])
        raw_path = input_dir / "manual_preview_raw_sm.h5ad"
        raw_sm.write_h5ad(raw_path)
        ad_st.write_h5ad(st_path)
        ad_sm.write_h5ad(sm_path)
        return (st_path, sm_path, raw_path, _spashiny_ctx._alignment_input_provenance(raw_resolved))

    _spashiny_ctx._write_manual_preview_inputs = _write_manual_preview_inputs

    def _submit_manual_preview(kind="overlay", *, color_parameters=None, color_plot_id=None):
        workflow_id = _spashiny_ctx._current_alignment_workflow_id()
        if not workflow_id:
            raise RuntimeError(
                "Start ST-SM Alignment Preprocessing before creating a manual preview."
            )
        transform = _spashiny_ctx._manual_transform_from_inputs(kind)
        job_id = f"alignment_manual_preview_{kind}_{_spashiny_ctx.time.strftime('%Y%m%d_%H%M%S')}_{_spashiny_globals.uuid.uuid4().hex[:8]}"
        job_dir = _spashiny_ctx._alignment_jobs_root() / job_id
        output_dir = _spashiny_ctx._alignment_result_root(job_id)
        st_path, sm_path, raw_path, raw_provenance = _spashiny_ctx._write_manual_preview_inputs(
            job_dir, require_raw=kind == "overlay"
        )
        job = {
            "job_id": job_id,
            "task": "manual_preview",
            "session_id": _spashiny_ctx._alignment_session_token(),
            "workflow_id": workflow_id,
            "job_dir": str(job_dir),
            "output_dir": str(output_dir),
            "log_file": str(_spashiny_ctx._alignment_logs_root() / f"{job_id}.log"),
            "st_h5ad": str(st_path),
            "sm_h5ad": str(sm_path),
            "raw_sm_h5ad": str(raw_path) if raw_path is not None else "",
            "raw_sm_provenance": raw_provenance,
            "transform": transform,
            "preview_kind": kind,
            "max_preview_points": int(
                _spashiny_globals.os.environ.get("SPASHINY_MANUAL_PREVIEW_MAX_POINTS") or 6000
            ),
        }
        if color_parameters is not None:
            job["color_parameters"] = dict(color_parameters or {})
            job["plot_key"] = str(color_plot_id or "")
        _spashiny_ctx._launch_alignment_worker(job)
        return (job_id, transform)

    _spashiny_ctx._submit_manual_preview = _submit_manual_preview

    def _manual_preview_completed_image(job_id, expected_kind=None):
        if not job_id:
            return None
        status = _spashiny_ctx._alignment_status(job_id)
        if status.get("status") in {"queued", "running"}:
            return None
        manifest = _spashiny_ctx._completed_alignment_manifest(job_id)
        if manifest.get("status") != "completed":
            return None
        result_dir = _spashiny_ctx._alignment_output_dir(job_id)
        expected_names = {
            "initial": ("initial st / sm view", "initial_st_sm_view"),
            "overlay": ("manual registration preview", "registration preview", "manual_overlay"),
            "side": ("side-by-side view", "side_by_side"),
        }
        wanted = tuple(expected_names.get(str(expected_kind or "").lower(), ()))
        first_existing = None
        for item in manifest.get("plots") or []:
            name = str(item.get("name") or "").lower()
            rel = str(item.get("path") or "")
            path = result_dir / rel
            if not path.is_file():
                continue
            item_plot_id = str(item.get("plot_id") or "")
            if item_plot_id:
                _spashiny_ctx._register_alignment_worker_color_spec(
                    item_plot_id, item.get("color_spec")
                )
            if first_existing is None:
                first_existing = str(path)
            item_kind = str(item.get("preview_kind") or item.get("panel") or "").lower()
            if expected_kind and item_kind == str(expected_kind).lower():
                return str(path)
            if expected_kind and any((token in name or token in rel.lower() for token in wanted)):
                return str(path)
            if not expected_kind and ("preview" in name or "view" in name or "manual" in name):
                return str(path)
        return first_existing if expected_kind is None else None

    _spashiny_ctx._manual_preview_completed_image = _manual_preview_completed_image

    def _manual_preview_completed_vector_pdf(job_id, expected_kind=None, *, combined=False):
        if not job_id:
            return None
        status = _spashiny_ctx._alignment_status(job_id)
        if status.get("status") in {"queued", "running"}:
            try:
                _spashiny_ctx.reactive.invalidate_later(2)
            except Exception:
                pass
            return None
        manifest = _spashiny_ctx._completed_alignment_manifest(job_id)
        if manifest.get("status") != "completed":
            return None
        result_dir = _spashiny_ctx._alignment_output_dir(job_id).resolve()

        def _safe_result_path(rel_path):
            rel_path = str(rel_path or "")
            if not rel_path.lower().endswith(".pdf"):
                return None
            path = (result_dir / rel_path).resolve()
            try:
                path.relative_to(result_dir)
            except Exception:
                return None
            return str(path) if path.is_file() else None

        vector_pdfs = (
            manifest.get("vector_pdfs") if isinstance(manifest.get("vector_pdfs"), dict) else {}
        )
        if combined:
            path = _safe_result_path(vector_pdfs.get("combined"))
            if path:
                return path
        expected_names = {
            "initial": ("initial st / sm view", "initial_st_sm_view"),
            "overlay": ("manual registration preview", "registration preview", "manual_overlay"),
            "side": ("side-by-side view", "side_by_side"),
        }
        expected_kind_text = str(expected_kind or "").lower()
        wanted = tuple(expected_names.get(expected_kind_text, ()))
        preview_path = _safe_result_path(vector_pdfs.get("preview"))
        if preview_path and (not expected_kind):
            return preview_path
        first_existing = None
        for item in manifest.get("downloads") or []:
            rel = str(item.get("path") or "")
            path = _safe_result_path(rel)
            if not path:
                continue
            if bool(item.get("vector_pdf_bundle")):
                if combined:
                    return path
                continue
            if first_existing is None:
                first_existing = path
            item_kind = str(item.get("preview_kind") or "").lower()
            name = str(item.get("name") or "").lower()
            if expected_kind and item_kind == expected_kind_text:
                return path
            if expected_kind and any((token in name or token in rel.lower() for token in wanted)):
                return path
        if preview_path and expected_kind:
            return preview_path
        return first_existing if expected_kind is None else None

    _spashiny_ctx._manual_preview_completed_vector_pdf = _manual_preview_completed_vector_pdf

    def _restore_manual_transform_for_automatic():
        """Load the current workflow's worker-produced prealigned SM coordinates.

        This is deliberately invoked only by an explicit automatic-alignment
        action.  It performs no plotting and never falls back to a historical
        session/job result.
        """
        workflow_id = _spashiny_ctx._current_alignment_workflow_id()
        state = _spashiny_ctx._read_alignment_workflow_state(workflow_id) if workflow_id else {}
        job_id = _spashiny_ctx.manual_transform_job_id.get() or state.get("manual_transform_job_id")
        if not job_id:
            raise RuntimeError(
                "Apply Transformation first. Automatic Alignment requires the current manual transform artifact."
            )
        job = _spashiny_ctx._alignment_job_payload(job_id)
        if (
            job.get("workflow_id") != workflow_id
            or job.get("task") != "manual_preview"
            or job.get("preview_kind") != "overlay"
        ):
            raise RuntimeError(
                "The available manual transform does not belong to the current Alignment workflow."
            )
        status = _spashiny_ctx._alignment_status(job_id)
        if status.get("status") in {"queued", "running"}:
            raise RuntimeError(
                "Manual transformation worker is still running. Please wait for completion before Step1."
            )
        if status.get("status") != "completed":
            raise RuntimeError("Manual transformation worker did not complete successfully.")
        manifest = _spashiny_ctx._completed_alignment_manifest(job_id)
        artifact = manifest.get("manual_transform") if isinstance(manifest, dict) else None
        if not isinstance(artifact, dict):
            raise RuntimeError(
                "Manual transformation coordinates are missing from the worker result. Re-run Apply Transformation."
            )
        result_dir = _spashiny_ctx._alignment_output_dir(job_id)
        metadata_path = result_dir / str(artifact.get("metadata") or "")
        coordinate_path = result_dir / str(artifact.get("coordinates") or "")
        if not metadata_path.is_file() or not coordinate_path.is_file():
            raise RuntimeError(
                "Manual transformation artifact files are missing from the worker result."
            )
        metadata = _spashiny_ctx.json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("workflow_id") != workflow_id:
            raise RuntimeError(
                "Manual transformation metadata belongs to a different Alignment workflow."
            )
        coordinates = _spashiny_globals.np.load(coordinate_path, allow_pickle=False)
        if coordinates.ndim != 2 or coordinates.shape[1] < 2:
            raise RuntimeError(
                f"Manual transformation coordinate shape is invalid: {coordinates.shape}"
            )
        base = _spashiny_ctx.alignment_manual_source_sm.get()
        if base is None:
            raise RuntimeError(
                "SM preprocessing data is unavailable. Run ST-SM Alignment Preprocessing again."
            )
        if hasattr(base, "n_obs") and coordinates.shape[0] != base.n_obs:
            raise RuntimeError(
                "Manual transformation coordinates do not match the current SM observations."
            )
        from cloud.sm_coordinate_policy import restore_manual_coordinates

        prealigned = restore_manual_coordinates(
            base,
            _spashiny_globals.np.asarray(coordinates[:, :2], dtype=_spashiny_globals.np.float32),
            metadata.get("coordinate_policy") or {},
        )
        raw_artifact = artifact.get("raw_sm_artifact") or {}
        raw_path = (result_dir / str(raw_artifact.get("relative_path") or "")).resolve()
        if not raw_path.is_relative_to(result_dir.resolve()) or not raw_path.is_file():
            raise RuntimeError("The current manual transform has no valid full Raw SM artifact.")
        import hashlib

        digest = hashlib.sha256()
        with raw_path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != raw_artifact.get("sha256"):
            raise RuntimeError("Full Raw SM artifact SHA256 does not match this manual transform.")
        raw_check = _spashiny_globals.sc.read_h5ad(raw_path, backed="r")
        try:
            if (
                list(raw_check.obs_names) != list(base.obs_names)
                or list(raw_check.shape) != raw_artifact.get("shape")
                or (
                    not _spashiny_globals.np.array_equal(
                        raw_check.obsm["spatial"], prealigned.obsm["spatial"]
                    )
                )
            ):
                raise RuntimeError(
                    "Full Raw SM spot identity, shape or transformed coordinates do not match."
                )
        finally:
            raw_check.file.close()
        prealigned.uns["spashiny_manual_raw_sm_artifact"] = dict(raw_artifact)
        prealigned.uns["spashiny_alignment_manual_transform"] = metadata
        _spashiny_ctx.adata_sm_transformed.set(prealigned)
        _spashiny_ctx.manual_transform_job_id.set(job_id)
        _spashiny_ctx.manual_transform_metadata_val.set(metadata)
        _spashiny_ctx.manual_transform_coordinates_val.set(
            _spashiny_globals.np.asarray(coordinates[:, :2], dtype=_spashiny_globals.np.float32)
        )
        _spashiny_ctx._update_alignment_workflow_state(
            manual_transform_job_id=job_id,
            manual_transform_metadata=str(
                metadata_path.relative_to(_spashiny_ctx._alignment_session_result_root())
            ),
            manual_transform_coordinates=str(
                coordinate_path.relative_to(_spashiny_ctx._alignment_session_result_root())
            ),
            manual_transform_status="completed",
        )
        return (prealigned, metadata)

    _spashiny_ctx._restore_manual_transform_for_automatic = _restore_manual_transform_for_automatic

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.generate_initial)
    @_spashiny_ctx._one_stop_action("initial")
    def submit_initial_alignment_preview():
        if not _spashiny_ctx._start_alignment_workflow_modal(
            "initial",
            "Initial ST / SM rendering is running in the alignment worker...",
            defer_modal_until_job=True,
        ):
            return
        try:
            _spashiny_ctx.initial_preview_img_val.set(None)
            job_id, _ = _spashiny_ctx._submit_manual_preview("initial")
            _spashiny_ctx.initial_preview_job_id.set(job_id)
            _spashiny_ctx._update_alignment_workflow_state(
                initial_preview_job_id=job_id, initial_preview_status="queued"
            )
            _spashiny_ctx._bind_alignment_workflow_modal_job("initial", job_id)
            _spashiny_ctx.log(f"Initial ST / SM preview worker submitted: {job_id}")
            _spashiny_ctx.ui.notification_show(
                f"Initial ST / SM preview submitted as worker job {job_id}.",
                type="message",
                duration=6,
            )
        except Exception as e:
            _spashiny_ctx.log(f"submit_initial_alignment_preview error: {e}")
            _spashiny_ctx._fail_alignment_workflow_modal("initial", e)
            _spashiny_ctx.ui.notification_show(
                _spashiny_globals.user_facing_error("Failed to submit initial preview", e),
                type="error",
                duration=10,
            )

    _spashiny_ctx.submit_initial_alignment_preview = submit_initial_alignment_preview

    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("initial_plot")
    def initial_plot():
        job_id = _spashiny_ctx.initial_preview_job_id.get()
        img_path = _spashiny_ctx.initial_preview_img_val.get()
        if img_path and _spashiny_ctx.Path(img_path).is_file():
            return _spashiny_ctx.image_path_to_figure(img_path)
        if job_id:
            img_path = _spashiny_ctx._manual_preview_completed_image(job_id, "initial")
            if img_path and _spashiny_ctx.Path(img_path).is_file():
                _spashiny_ctx.initial_preview_img_val.set(img_path)
                return _spashiny_ctx.image_path_to_figure(img_path)
            status = _spashiny_ctx._alignment_status(job_id)
            if status.get("status") == "failed":
                return _spashiny_ctx.make_alignment_message_fig(
                    _spashiny_globals._analysis_status_error_text(
                        "Initial preview worker failed",
                        status,
                        job_id=job_id,
                        current_step="initial preview",
                    ),
                    "Initial ST / SM View",
                )
            return _spashiny_ctx.make_alignment_message_fig(
                f"Initial preview worker is {status.get('status') or 'queued'}...\nJob: {job_id}",
                "Initial ST / SM View",
            )
        return _spashiny_ctx.make_alignment_message_fig(
            "Click Generate Initial Plot to submit a worker-rendered initial ST / SM preview.",
            "Initial ST / SM View",
        )

    _spashiny_ctx.initial_plot = initial_plot
    import matplotlib.pyplot as plt

    _spashiny_globals.plt = plt
    import copy

    _spashiny_ctx.copy = copy
    import time

    _spashiny_ctx.time = time

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.generate_rotated)
    @_spashiny_ctx._one_stop_action("manual")
    def submit_manual_registration_preview():
        if not _spashiny_ctx._start_alignment_workflow_modal(
            "manual",
            "Applying manual SM transformation in the alignment worker...",
            defer_modal_until_job=True,
        ):
            return
        try:
            _spashiny_ctx.manual_preview_img_val.set(None)
            job_id, transform = _spashiny_ctx._submit_manual_preview("overlay")
            _spashiny_ctx.manual_preview_job_id.set(job_id)
            _spashiny_ctx.manual_transform_job_id.set(job_id)
            _spashiny_ctx.manual_transform_val.set(transform)
            _spashiny_ctx.adata_sm_transformed.set(None)
            _spashiny_ctx.adata_sm_norm.set(None)
            _spashiny_ctx.alignment_model.set(None)
            _spashiny_ctx.result_dict_val.set(None)
            _spashiny_ctx.alignment_result.set(None)
            _spashiny_ctx.alignment_step3_job_id.set(None)
            _spashiny_ctx.alignment_step4_job_id.set(None)
            _spashiny_ctx.alignment_step5_job_id.set(None)
            _spashiny_ctx.alignment_step5_coordinate_context.set(None)
            _spashiny_ctx.alignment_step6_result_id.set(None)
            _spashiny_ctx.raster_data.set(None)
            _spashiny_ctx.spot_data.set(None)
            _spashiny_ctx.raster_img_val.set(None)
            _spashiny_ctx.spot_fig_val.set(None)
            _spashiny_ctx.raster_panel_img_val.set({})
            _spashiny_ctx.spot_panel_img_val.set({})
            _spashiny_ctx._clear_alignment_panel_image_url_cache(
                *_spashiny_ctx.ALIGNMENT_PANEL_IMAGE_IDS
            )
            _spashiny_ctx._update_alignment_workflow_state(
                manual_transform_job_id=job_id,
                manual_transform_status="queued",
                manual_transform_parameters=transform,
                step1_completed_at=None,
                step2_created_at=None,
                step3_job_id=None,
                step4_job_id=None,
                step5_job_id=None,
                step6_result_id=None,
            )
            _spashiny_ctx._bind_alignment_workflow_modal_job("manual", job_id)
            _spashiny_ctx.log(f"Manual registration preview worker submitted: {job_id}")
            _spashiny_ctx.ui.notification_show(
                f"Manual registration preview submitted as worker job {job_id}.",
                type="message",
                duration=6,
            )
        except Exception as e:
            _spashiny_ctx.log(f"submit_manual_registration_preview error: {e}")
            _spashiny_ctx._fail_alignment_workflow_modal("manual", e)
            _spashiny_ctx.ui.notification_show(
                _spashiny_globals.user_facing_error(
                    "Failed to submit manual registration preview", e
                ),
                type="error",
                duration=10,
            )

    _spashiny_ctx.submit_manual_registration_preview = submit_manual_registration_preview

    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("overlay_plot")
    def overlay_plot():
        job_id = _spashiny_ctx.manual_preview_job_id.get()
        img_path = _spashiny_ctx.manual_preview_img_val.get()
        if img_path and _spashiny_ctx.Path(img_path).is_file():
            return _spashiny_ctx.image_path_to_figure(img_path)
        if job_id:
            img_path = _spashiny_ctx._manual_preview_completed_image(job_id, "overlay")
            if img_path and _spashiny_ctx.Path(img_path).is_file():
                _spashiny_ctx.manual_preview_img_val.set(img_path)
                return _spashiny_ctx.image_path_to_figure(img_path)
            status = _spashiny_ctx._alignment_status(job_id)
            if status.get("status") == "failed":
                return _spashiny_ctx.make_alignment_message_fig(
                    _spashiny_globals._analysis_status_error_text(
                        "Manual preview worker failed",
                        status,
                        job_id=job_id,
                        current_step="manual preview",
                    ),
                    "Manual Registration Preview",
                )
            return _spashiny_ctx.make_alignment_message_fig(
                f"Manual preview worker is {status.get('status') or 'queued'}...\nJob: {job_id}",
                "Manual Registration Preview",
            )
        return _spashiny_ctx.make_alignment_message_fig(
            "Click Apply Transformation to submit a worker-rendered preview.",
            "Manual Registration Preview",
        )

    _spashiny_ctx.overlay_plot = overlay_plot

    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("side_plot")
    def side_plot():
        job_id = _spashiny_ctx.side_preview_job_id.get()
        img_path = _spashiny_ctx.side_preview_img_val.get()
        if img_path and _spashiny_ctx.Path(img_path).is_file():
            return _spashiny_ctx.image_path_to_figure(img_path)
        if job_id:
            img_path = _spashiny_ctx._manual_preview_completed_image(job_id, "side")
            if img_path and _spashiny_ctx.Path(img_path).is_file():
                _spashiny_ctx.side_preview_img_val.set(img_path)
                return _spashiny_ctx.image_path_to_figure(img_path)
            status = _spashiny_ctx._alignment_status(job_id)
            if status.get("status") == "failed":
                return _spashiny_ctx.make_alignment_message_fig(
                    _spashiny_globals._analysis_status_error_text(
                        "Side preview worker failed",
                        status,
                        job_id=job_id,
                        current_step="side preview",
                    ),
                    "Side-by-Side View",
                )
            return _spashiny_ctx.make_alignment_message_fig(
                f"Side preview worker is {status.get('status') or 'queued'}...\nJob: {job_id}",
                "Side-by-Side View",
            )
        return _spashiny_ctx.make_alignment_message_fig(
            "Use Step 1 to view the original ST and SM panels.", "Side-by-Side View"
        )

    _spashiny_ctx.side_plot = side_plot


_STEPS = (_install_0,)


def server(_spashiny_ctx, step=0):
    return _STEPS[step](_spashiny_ctx)
