# Extracted from /app/app/ST-SM.py. Feature: knn; ordered phases preserve original initialization.
from spashiny._shared import runtime_globals as _spashiny_globals


def _install_0(_spashiny_ctx):

    def get_current_alignment_sm_object():
        candidates = [
            ("adata_sm_norm", _spashiny_ctx.adata_sm_norm.get()),
            ("adata_sm_transformed", _spashiny_ctx.adata_sm_transformed.get()),
            ("adata_sm", _spashiny_ctx.adata_sm.get()),
        ]
        for source, obj in candidates:
            if obj is not None:
                return (obj, source)
        return (None, None)

    _spashiny_ctx.get_current_alignment_sm_object = get_current_alignment_sm_object

    def select_best_alignment_key(result_dict):
        if not isinstance(result_dict, dict) or not result_dict:
            raise RuntimeError("Step5 result is empty or invalid.")

        def score(key):
            loss = result_dict[key].get("loss", [])
            if loss is None or len(loss) == 0:
                return float("inf")
            return float(loss[-1])

        return min(result_dict.keys(), key=score)

    _spashiny_ctx.select_best_alignment_key = select_best_alignment_key

    def apply_alignment_result_to_sm(result_dict=None, update_reactive=True):
        if result_dict is None:
            result_dict = _spashiny_ctx.result_dict_val.get()
        best_key = _spashiny_ctx.select_best_alignment_key(result_dict)
        adata_sm_obj, source = _spashiny_ctx.get_current_alignment_sm_object()
        if adata_sm_obj is None:
            raise RuntimeError(
                "SM object is missing. Please complete Step1/Step2 before saving alignment."
            )
        points = result_dict[best_key].get("pointsIt")
        if points is None:
            raise RuntimeError(f"Step5 result key {best_key} does not contain pointsIt.")
        points = _spashiny_globals.np.asarray(points, dtype=_spashiny_globals.np.float32)
        if points.ndim != 2 or points.shape[1] < 2:
            raise RuntimeError(f"Invalid pointsIt shape: {points.shape}")
        points = points[:, :2]
        if hasattr(adata_sm_obj, "n_obs") and points.shape[0] != adata_sm_obj.n_obs:
            raise RuntimeError(
                f"Alignment points do not match SM observations: points={points.shape[0]}, SM={adata_sm_obj.n_obs}"
            )
        adata_sm_obj.obsm["spatial_transformed"] = points
        if update_reactive:
            _spashiny_ctx.adata_sm_norm.set(adata_sm_obj)
            _spashiny_ctx.adata_sm_transformed.set(adata_sm_obj)
            _spashiny_ctx.alignment_result.set(result_dict)
        return (adata_sm_obj, best_key, source)

    _spashiny_ctx.apply_alignment_result_to_sm = apply_alignment_result_to_sm

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.align_step6_save_result)
    @_spashiny_ctx._one_stop_action("step6")
    def align_step6_save_result():
        current_step5_job_id = _spashiny_ctx._current_step5_job_id()
        current_step5_status = (
            _spashiny_ctx._alignment_status(current_step5_job_id) if current_step5_job_id else {}
        )
        if current_step5_status.get("status") in {"queued", "running"}:
            _spashiny_ctx._bind_alignment_workflow_modal_job("step5", current_step5_job_id)
            return
        if not _spashiny_ctx._start_alignment_workflow_modal(
            "step6", "Saving current alignment result..."
        ):
            return
        try:
            step5_job_id = _spashiny_ctx._current_step5_job_id()
            if not _spashiny_ctx._load_alignment_fit_summary(step5_job_id):
                step5_status = _spashiny_ctx._alignment_status(step5_job_id) if step5_job_id else {}
                if step5_status.get("status") in {"queued", "running"}:
                    message = "Alignment Step5 worker is still running. Please wait for completion before saving."
                elif step5_status.get("status") == "failed":
                    message = _spashiny_globals._analysis_status_error_text(
                        "Alignment Step5 worker failed",
                        step5_status,
                        job_id=step5_job_id,
                        current_step="Step5",
                    )
                else:
                    message = (
                        "Please complete the current workflow's Step5 successfully before saving."
                    )
                _spashiny_ctx.log(message)
                raise RuntimeError(message)
            result_dict = _spashiny_ctx.result_dict_val.get()
            adata_sm_obj, best_key, source = _spashiny_ctx.apply_alignment_result_to_sm(result_dict)
            current_job_id = _spashiny_ctx._current_step5_job_id()
            handoff_artifact = _spashiny_ctx._persist_alignment_handoff_artifact(
                adata_sm_obj, best_key=best_key, source=source
            )
            _spashiny_ctx.alignment_step6_result_id.set(current_job_id)
            _spashiny_ctx._update_alignment_workflow_state(
                step6_result_id=current_job_id,
                step6_completed_at=_spashiny_ctx.time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                step6_status="completed",
                step6_sm_coordinate_metadata=_spashiny_ctx._alignment_coordinate_metadata(
                    adata_sm_obj.obsm["spatial_transformed"]
                ),
                step6_handoff_artifact=handoff_artifact,
            )
            _spashiny_ctx.log(
                f"Alignment completed and registered aligned SM handoff artifact. Best configuration: {best_key}; source: {source}."
            )
            _spashiny_ctx._complete_alignment_workflow_modal("step6", job_id=current_job_id)
            _spashiny_ctx.ui.notification_show(
                "Alignment result saved.", type="message", duration=5
            )
        except Exception as e:
            _spashiny_ctx.log(f"align_step6_save_result error: {e}")
            _spashiny_ctx._fail_alignment_workflow_modal("step6", e, job_id=current_step5_job_id)
            _spashiny_ctx.ui.notification_show(
                _spashiny_globals.user_facing_error("Failed to save alignment result", e),
                type="error",
                duration=10,
            )

    _spashiny_ctx.align_step6_save_result = align_step6_save_result

    def _step7_current_export_key(workflow_id=None):
        """Fingerprint the exact current lineage, exporter and active palette."""
        workflow_id = workflow_id or _spashiny_ctx._current_alignment_workflow_id()
        if not workflow_id:
            return None
        state = _spashiny_ctx._read_alignment_workflow_state(workflow_id)
        step5 = _spashiny_ctx._current_step5_job_id()
        if not step5 or _spashiny_ctx._alignment_status(step5).get("status") != "completed":
            return None
        _spashiny_ctx.plot_color_revision.get()
        settings = _spashiny_ctx.plot_color_settings.get() or {}
        try:
            owner, analysis = _spashiny_ctx._require_alignment_scope()
            return _spashiny_globals.step7_cache_key(
                owner=owner,
                analysis=analysis,
                workflow=workflow_id,
                step4=str(
                    state.get("step4_job_id") or _spashiny_ctx.alignment_step4_job_id.get() or ""
                ),
                step5=str(step5),
                step6=str(
                    state.get("step6_result_id")
                    or _spashiny_ctx.alignment_step6_result_id.get()
                    or ""
                ),
                colors=dict(
                    settings.get("align_step7_show_alignment_plot")
                    or settings.get("__global__")
                    or {}
                ),
            )
        except (ValueError, RuntimeError):
            return None

    _spashiny_ctx._step7_current_export_key = _step7_current_export_key

    def _step7_validated_artifact(suffix, workflow_id=None):
        workflow_id = workflow_id or _spashiny_ctx._current_alignment_workflow_id()
        key = _spashiny_ctx._step7_current_export_key(workflow_id)
        if not key:
            return None
        state = _spashiny_ctx._read_alignment_workflow_state(workflow_id)
        if (
            state.get("step7_export_version") != _spashiny_globals.ALIGNMENT_EXPORT_VERSION
            or state.get("step7_export_key") != key
            or state.get("step7_source_step5_job_id") != _spashiny_ctx._current_step5_job_id()
        ):
            return None
        field = "step7_pdf_artifact_path" if suffix == ".pdf" else "step7_artifact_path"
        raw_path = str(state.get(field) or "")
        if not raw_path:
            return None
        try:
            path = _spashiny_globals.alignment_checked_path(
                raw_path, _spashiny_ctx._alignment_workflow_root(workflow_id)
            )
        except (ValueError, FileNotFoundError):
            return None
        return path if path.suffix.lower() == suffix and path.stat().st_size else None

    _spashiny_ctx._step7_validated_artifact = _step7_validated_artifact

    def _step7_persisted_artifact(workflow_id=None):
        return _spashiny_ctx._step7_validated_artifact(".png", workflow_id)

    _spashiny_ctx._step7_persisted_artifact = _step7_persisted_artifact

    def _persist_step7_artifact(fig, step5_job_id):
        """Publish original vector artists, already colored, with exact lineage."""
        workflow_id = _spashiny_ctx._current_alignment_workflow_id()
        if not workflow_id:
            raise RuntimeError("Cannot persist Step7 without a current Alignment workflow")
        if not getattr(fig, "_spashiny_alignment_ready", False):
            raise RuntimeError("An incomplete/message figure cannot be an Alignment result.")
        export_key = _spashiny_ctx._step7_current_export_key(workflow_id)
        if not export_key or str(step5_job_id) != str(_spashiny_ctx._current_step5_job_id()):
            raise RuntimeError("Step7 source lineage changed before export.")
        workflow_root = _spashiny_ctx._alignment_workflow_root(workflow_id)
        plots_dir = workflow_root / "plots"
        plots_dir.mkdir(parents=True, exist_ok=True)
        artifact = plots_dir / f"step7_aligned_preview_{export_key[:20]}.png"
        editable_pdf = artifact.with_suffix(".pdf")
        fig.savefig(artifact, format="png", dpi=180, bbox_inches="tight")
        _spashiny_globals.save_editable_figure(fig, editable_pdf)
        _spashiny_globals.save_editable_figure(fig, artifact.with_suffix(".svg"))
        if not artifact.is_file() or artifact.stat().st_size <= 0:
            raise RuntimeError("Step7 preview PNG was not written")
        if not editable_pdf.is_file() or editable_pdf.stat().st_size <= 0:
            raise RuntimeError("Step7 editable PDF was not written")
        _spashiny_ctx._update_alignment_workflow_state(
            step7_artifact_path=str(artifact),
            step7_pdf_artifact_path=str(editable_pdf),
            step7_artifact_ready=True,
            step7_source_step5_job_id=str(step5_job_id),
            step7_export_version=_spashiny_globals.ALIGNMENT_EXPORT_VERSION,
            step7_export_key=export_key,
            step7_artifact_completed_at=_spashiny_ctx.time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            step7_color_source=getattr(fig, "_spashiny_step7_plot_contract", {}).get(
                "color_source", {}
            ),
        )
        return artifact

    _spashiny_ctx._persist_step7_artifact = _persist_step7_artifact

    def _step7_persisted_pdf_artifact(workflow_id=None):
        return _spashiny_ctx._step7_validated_artifact(".pdf", workflow_id)

    _spashiny_ctx._step7_persisted_pdf_artifact = _step7_persisted_pdf_artifact

    def _step7_saved_plot_inputs(workflow_id, state):
        """Never use a different page's current input for an existing fit."""
        render_id = str(
            state.get("step4_job_id") or _spashiny_ctx.alignment_step4_job_id.get() or ""
        )
        render_job = _spashiny_ctx._alignment_job_payload(render_id)
        if render_job.get("workflow_id") != workflow_id or render_job.get("task") != "render":
            raise RuntimeError("The saved Step4 input lineage does not match this workflow.")
        train_id = str(render_job.get("source_train_job_id") or "")
        train_job = _spashiny_ctx._alignment_job_payload(train_id)
        if train_job.get("workflow_id") != workflow_id or train_job.get("task") != "train":
            raise RuntimeError("The saved Step3 input lineage does not match this workflow.")
        paths = []
        for key in ("st_h5ad", "sm_h5ad"):
            path = _spashiny_globals.alignment_checked_path(
                str(render_job.get(key) or ""),
                _spashiny_ctx._alignment_jobs_root()
                / _spashiny_ctx._safe_job_token(train_id, "alignment_job")
                / "input",
            )
            if path != _spashiny_ctx.Path(str(train_job.get(key) or "")).resolve():
                raise RuntimeError(
                    "The saved Alignment plotting input changed between Step3 and Step4."
                )
            paths.append(path)
        return _spashiny_globals.read_step7_plot_inputs(*paths)

    _spashiny_ctx._step7_saved_plot_inputs = _step7_saved_plot_inputs

    def build_step7_alignment_figure():
        import matplotlib.pyplot as plt
        import numpy as np

        workflow_id = _spashiny_ctx._current_alignment_workflow_id()
        state = _spashiny_ctx._read_alignment_workflow_state(workflow_id) if workflow_id else {}
        step5_job_id = _spashiny_ctx._current_step5_job_id()
        if not workflow_id or not step5_job_id:
            fig = _spashiny_ctx.make_alignment_message_fig(
                "Complete the current workflow's Step5 and Step6 before generating Step7.",
                "Step7 Alignment Result",
            )
            fig._spashiny_alignment_ready = False
            return fig
        step5_status = _spashiny_ctx._alignment_status(step5_job_id)
        if step5_status.get("status") in {"queued", "running"}:
            fig = _spashiny_ctx.make_alignment_message_fig(
                f"Step5 worker is {step5_status.get('status')} for the current workflow. Step7 is blocked until Step5 completes.\nJob: {step5_job_id}",
                "Step7 Alignment Result",
            )
            fig._spashiny_alignment_ready = False
            return fig
        if step5_status.get("status") != "completed":
            fig = _spashiny_ctx.make_alignment_message_fig(
                f"Current workflow Step5 did not complete successfully: {step5_status.get('error') or step5_status.get('error_message') or 'unknown error'}",
                "Step7 Alignment Result",
            )
            fig._spashiny_alignment_ready = False
            return fig
        if str(
            state.get("step6_result_id") or _spashiny_ctx.alignment_step6_result_id.get() or ""
        ) != str(step5_job_id):
            fig = _spashiny_ctx.make_alignment_message_fig(
                "Step5 completed, but Step6 has not saved this exact current workflow result. Click Save Alignment Result first.",
                "Step7 Alignment Result",
            )
            fig._spashiny_alignment_ready = False
            return fig
        if not _spashiny_ctx._load_alignment_fit_summary(step5_job_id):
            fig = _spashiny_ctx.make_alignment_message_fig(
                "The current workflow Step5 coordinate artifacts could not be restored. Re-run Step5.",
                "Step7 Alignment Result",
            )
            fig._spashiny_alignment_ready = False
            return fig
        coordinate_context = _spashiny_ctx.alignment_step5_coordinate_context.get() or {}
        if (
            coordinate_context.get("workflow_id") != workflow_id
            or coordinate_context.get("job_id") != step5_job_id
        ):
            fig = _spashiny_ctx.make_alignment_message_fig(
                "Step7 rejected a stale Step5 coordinate context. Re-run Step5 for this workflow.",
                "Step7 Alignment Result",
            )
            fig._spashiny_alignment_ready = False
            return fig
        adata_st_obj, adata_sm_obj = _spashiny_ctx._step7_saved_plot_inputs(workflow_id, state)
        if adata_st_obj is None or adata_sm_obj is None:
            fig = _spashiny_ctx.make_alignment_message_fig(
                "ST or SM data is not ready. Please complete the previous steps first.",
                "Step7 Alignment Result",
            )
            fig._spashiny_alignment_ready = False
            return fig
        if "spatial" not in adata_st_obj.obsm:
            fig = _spashiny_ctx.make_alignment_message_fig(
                "ST spatial coordinates are missing.", "Step7 Alignment Result"
            )
            fig._spashiny_alignment_ready = False
            return fig
        st_xy = np.asarray(coordinate_context.get("st_raster_points"), dtype=float)
        sm_xy = np.asarray(coordinate_context.get("aligned_points"), dtype=float)
        for label, points, data_obj in (("ST", st_xy, adata_st_obj), ("SM", sm_xy, adata_sm_obj)):
            if (
                points.ndim != 2
                or points.shape[1] < 2
                or points.shape[0] != data_obj.n_obs
                or (not len(points))
                or (not np.isfinite(points[:, :2]).all())
            ):
                raise ValueError(
                    f"Step7 rejected invalid/mismatched {label} coordinates from the current Step5."
                )
        st_xy = st_xy[:, :2]
        sm_xy = sm_xy[:, :2]
        if coordinate_context.get("coordinate_space") != "step4_raster":
            raise ValueError(
                "Step7 cannot overlay an unrecognized coordinate space; no coordinate conversion was guessed."
            )
        return _spashiny_globals.build_step7_tutorial_figure(
            adata_st_obj,
            adata_sm_obj,
            st_raster_points=st_xy,
            aligned_points=sm_xy,
            source_step5_job_id=step5_job_id,
        )

    _spashiny_ctx.build_step7_alignment_figure = build_step7_alignment_figure

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(
        _spashiny_ctx.input.align_step7_show_alignment_btn, ignore_init=True
    )
    def _request_step7_alignment_preview():
        _spashiny_ctx.alignment_step7_request_sequence.set(
            _spashiny_ctx.alignment_step7_request_sequence.get() + 1
        )

    _spashiny_ctx._request_step7_alignment_preview = _request_step7_alignment_preview

    @_spashiny_ctx.render.plot
    def align_step7_show_alignment_plot():
        request_sequence = _spashiny_ctx.alignment_step7_request_sequence.get()
        processed_sequence = _spashiny_ctx.alignment_step7_processed_sequence.get()
        workflow_id = _spashiny_ctx._current_alignment_workflow_id()
        state = _spashiny_ctx._read_alignment_workflow_state(workflow_id) if workflow_id else {}
        persisted_artifact = _spashiny_ctx._step7_persisted_artifact(workflow_id)
        if request_sequence <= processed_sequence and persisted_artifact:
            return _spashiny_ctx.image_path_to_figure(
                str(persisted_artifact), figsize=(10, 9), dpi=180
            )
        refresh_saved_plot = (
            str(state.get("step7_status") or "") == "completed"
            and _spashiny_ctx._step7_current_export_key(workflow_id) is not None
        )
        if request_sequence <= processed_sequence and (not refresh_saved_plot):
            return _spashiny_ctx.empty_alignment_preview(
                "Generate the final aligned preview after Step5 and Step6 complete."
            )
        _spashiny_ctx.alignment_step7_processed_sequence.set(request_sequence)
        step5_job_id = _spashiny_ctx._current_step5_job_id()
        step5_status = _spashiny_ctx._alignment_status(step5_job_id) if step5_job_id else {}
        if step5_status.get("status") in {"queued", "running"}:
            _spashiny_ctx._bind_alignment_workflow_modal_job("step5", step5_job_id)
            return _spashiny_ctx.make_alignment_message_fig(
                "Step5 is still running for the current workflow. Step7 remains blocked until it completes.",
                "Step7 Alignment Result",
            )
        if not _spashiny_ctx._start_alignment_workflow_modal(
            "step7", "Generating final aligned ST-SM preview..."
        ):
            return _spashiny_ctx.make_alignment_message_fig(
                "Another Alignment workflow step is active. Close its completed modal before continuing.",
                "Step7 Alignment Result",
            )
        try:
            fig = _spashiny_ctx.build_step7_alignment_figure()
            if getattr(fig, "_spashiny_alignment_ready", False):
                colored = _spashiny_ctx.colorize_plot("align_step7_show_alignment_plot", fig)
                if colored is not fig:
                    _spashiny_globals.plt.close(fig)
                    fig = colored
                artifact = _spashiny_ctx._persist_step7_artifact(fig, step5_job_id)
                _spashiny_ctx.log("Step7: Alignment result plot generated successfully.")
                _spashiny_ctx._complete_alignment_workflow_modal(
                    "step7", job_id=step5_job_id, details=f"Persistent preview: {artifact.name}"
                )
            else:
                message = "Step7: Alignment result is not ready yet. Complete the current workflow's Step5 and Step6 first."
                _spashiny_ctx.log(message)
                _spashiny_ctx._fail_alignment_workflow_modal("step7", message, job_id=step5_job_id)
            return fig
        except Exception as e:
            _spashiny_ctx.log(f"Failed to generate Step7 alignment plot: {e}")
            _spashiny_ctx._fail_alignment_workflow_modal("step7", e, job_id=step5_job_id)
            _spashiny_ctx.ui.notification_show(
                f"Failed to generate Step7 alignment plot: {e}", type="error", duration=10
            )
            return _spashiny_ctx.make_alignment_message_fig(str(e), "Step7 Alignment Result")

    _spashiny_ctx.align_step7_show_alignment_plot = align_step7_show_alignment_plot

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(
        _spashiny_ctx.input.reassign_st_h5ad, _spashiny_ctx.input.reassign_sm_h5ad
    )
    def save_reassign_uploaded_h5ad():
        """Save reassignment ST and SM files only after both are uploaded."""
        st_files = _spashiny_ctx.input.reassign_st_h5ad() or []
        sm_files = _spashiny_ctx.input.reassign_sm_h5ad() or []
        if _spashiny_globals.SPASHINY_WEB_PLATFORM and (st_files or sm_files):
            _spashiny_ctx.knn_input_source.set("USER_UPLOAD")
            _spashiny_ctx.knn_input_bridge.reset()
            _spashiny_ctx.log(
                "KNN upload selection cleared the Example source. For Web execution, complete Alignment Step 6 and choose Use Current Alignment Result."
            )
            return
        if not st_files or not sm_files:
            _spashiny_ctx.log("Waiting until both ST and SM files are uploaded before loading.")
            return
        td = _spashiny_ctx.create_temp_dir()
        st_dst = _spashiny_ctx.Path(td) / st_files[0]["name"]
        with open(st_dst, "wb") as out_f:
            out_f.write(_spashiny_ctx.Path(st_files[0]["datapath"]).read_bytes())
        st_path = str(st_dst)
        _spashiny_ctx.st_h5ad_path.set(st_path)
        _spashiny_ctx.log(f"ST file saved to: {st_dst}")
        sm_dst = _spashiny_ctx.Path(td) / sm_files[0]["name"]
        with open(sm_dst, "wb") as out_f:
            out_f.write(_spashiny_ctx.Path(sm_files[0]["datapath"]).read_bytes())
        sm_path = str(sm_dst)
        _spashiny_ctx.sm_h5ad_path.set(sm_path)
        _spashiny_ctx.log(f"SM file saved to: {sm_dst}")

    _spashiny_ctx.save_reassign_uploaded_h5ad = save_reassign_uploaded_h5ad

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.load_reassign_example_raw_h5ad)
    def load_reassign_example_raw_h5ad():
        if _spashiny_globals.SPASHINY_WEB_PLATFORM:
            try:
                st_path = _spashiny_globals.resolve_y7_example_input(
                    "integration_postprocessing", "knn_reassignment", "knn_st_h5ad"
                )
                sm_path = _spashiny_globals.resolve_y7_example_input(
                    "integration_postprocessing", "knn_reassignment", "knn_sm_h5ad"
                )
                _spashiny_ctx.st_h5ad_path.set(str(st_path))
                _spashiny_ctx.sm_h5ad_path.set(str(sm_path))
                _spashiny_ctx.log(f"Lab Y7_T QC ST h5ad selected for KNN reassignment: {st_path}")
                _spashiny_ctx.log(
                    f"Lab Y7_T aligned SM h5ad selected for KNN reassignment: {sm_path}"
                )
                _spashiny_ctx.ui.notification_show(
                    "Y7_T QC ST and aligned SM h5ad files are ready for KNN reassignment.",
                    type="message",
                    duration=6,
                )
            except Exception as e:
                _spashiny_ctx.log(f"Failed to load Lab Y7_T KNN example h5ad files: {e}")
                _spashiny_ctx.ui.notification_show(
                    f"Failed to load Lab Y7_T KNN example: {e}", type="error", duration=8
                )
            return
        try:
            st_path, sm_path = _spashiny_globals.get_example_knn_h5ad_paths()
            _spashiny_ctx.st_h5ad_path.set(str(st_path))
            _spashiny_ctx.sm_h5ad_path.set(str(sm_path))
            _spashiny_ctx.log(f"Example QC ST h5ad selected for KNN reassignment: {st_path}")
            _spashiny_ctx.log(f"Example aligned SM h5ad selected for KNN reassignment: {sm_path}")
            _spashiny_ctx.ui.notification_show(
                "Example QC ST and aligned SM h5ad files are ready for KNN reassignment.",
                type="message",
                duration=5,
            )
        except Exception as e:
            _spashiny_ctx.log(f"Failed to load KNN reassignment example h5ad files: {e}")
            _spashiny_ctx.ui.notification_show(
                f"Failed to load KNN reassignment example h5ad files: {e}", type="error", duration=8
            )

    _spashiny_ctx.load_reassign_example_raw_h5ad = load_reassign_example_raw_h5ad

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.align_step8_export_h5ad)
    def align_step8_export_h5ad():
        if _spashiny_ctx._alignment_action_too_fast("step8"):
            return
        try:
            import os
            import traceback

            _spashiny_ctx.log("Step8 started: Export aligned SM h5ad data.")
            if _spashiny_globals.SPASHINY_WEB_PLATFORM:
                workflow_id = _spashiny_ctx._current_alignment_workflow_id()
                state = (
                    _spashiny_ctx._read_alignment_workflow_state(workflow_id) if workflow_id else {}
                )
                artifact = (
                    state.get("step6_handoff_artifact")
                    if isinstance(state.get("step6_handoff_artifact"), dict)
                    else {}
                )
                if (
                    str(state.get("step6_status") or "").lower() != "completed"
                    or artifact.get("role") != "aligned_sm_h5ad"
                ):
                    raise RuntimeError(
                        "No completed Alignment Step6 handoff artifact is available."
                    )
                _spashiny_ctx.log(
                    "Aligned SM H5AD is registered for the current workflow's authorized KNN handoff."
                )
                _spashiny_ctx.ui.notification_show(
                    "Aligned SM result is ready for downstream KNN reassignment.",
                    type="message",
                    duration=6,
                )
                return
            adata_sm_obj = _spashiny_ctx.adata_sm_norm.get()
            if adata_sm_obj is None:
                _spashiny_ctx.log("No aligned SM object found. Please complete Step6 first.")
                return
            if "spatial_transformed" not in adata_sm_obj.obsm.keys():
                _spashiny_ctx.log(
                    "'spatial_transformed' not found in adata_sm.obsm. Please complete Step6 first."
                )
                return
            _spashiny_ctx.log(f"Aligned SM data shape: {adata_sm_obj.shape}")
            _spashiny_ctx.log(f"Aligned SM obsm keys: {list(adata_sm_obj.obsm.keys())}")
            sm_file = _spashiny_ctx.input.align_sm_h5ad()
            if sm_file is None or len(sm_file) == 0:
                _spashiny_ctx.log("No SM h5ad file uploaded. Cannot determine export filename.")
                return
            sm_path = sm_file[0]["datapath"]
            sm_name = sm_file[0]["name"]
            _spashiny_ctx.log(f"Original uploaded SM file: {sm_name}")
            if sm_name.lower().endswith(".h5ad"):
                out_name = sm_name[:-5] + ".aligned.h5ad"
            else:
                out_name = sm_name + ".aligned.h5ad"
            out_dir = os.path.dirname(sm_path)
            out_path = os.path.join(out_dir, out_name)
            adata_sm_obj.write_h5ad(out_path)
            _spashiny_ctx.log("Step8 completed successfully.")
            _spashiny_ctx.log(f"Exported aligned SM h5ad file: {out_path}")
        except Exception as e:
            _spashiny_ctx.log(f"Failed to export aligned SM h5ad: {e}")
            _spashiny_ctx.log(traceback.format_exc())

    _spashiny_ctx.align_step8_export_h5ad = align_step8_export_h5ad

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.load_h5ad)
    def save_and_load_h5ad():
        """Load h5ad files, apply SM alignment if available, and perform QC."""
        if _spashiny_globals.SPASHINY_WEB_PLATFORM:
            _spashiny_ctx.knn_input_bridge.submit("input_qc")
            return
        td = _spashiny_ctx.create_temp_dir()
        st_path = _spashiny_ctx.st_h5ad_path.get()
        sm_path = _spashiny_ctx.sm_h5ad_path.get()
        import scanpy as sc
        import spatialmeta as smt
        import numpy as np

        if not (
            st_path
            and _spashiny_ctx.Path(st_path).exists()
            and sm_path
            and _spashiny_ctx.Path(sm_path).exists()
        ):
            _spashiny_ctx.log(
                "KNN inputs are not selected. Choose an explicit example or use the current Alignment result; no silent example fallback is permitted."
            )
            _spashiny_ctx.adata_sm_aligned.set(None)
            _spashiny_ctx.adata_st_aligned.set(None)
            return
        aligned_path = _spashiny_ctx.Path(sm_path).with_name(
            _spashiny_ctx.Path(sm_path).stem + ".aligned.h5ad"
        )
        try:
            _spashiny_ctx.log(" Loading ST and SM datasets ...")
            adata_ST = _spashiny_globals.compact_adata_X(sc.read_h5ad(st_path))
            adata_SM = _spashiny_globals.compact_adata_X(sc.read_h5ad(sm_path))
            if "spatial_transformed" in adata_SM.obsm:
                _spashiny_ctx.log(
                    "Aligned SM coordinates detected in the uploaded SM file: obsm['spatial_transformed']."
                )
                _spashiny_ctx.adata_sm_aligned.set(adata_SM)
            elif _spashiny_ctx.Path(aligned_path).exists():
                _spashiny_ctx.log(f" Aligned SM file detected: {aligned_path.name}")
                adata_SM_aligned_obj = _spashiny_globals.compact_adata_X(
                    sc.read_h5ad(str(aligned_path))
                )
                adata_SM.obsm = adata_SM_aligned_obj.obsm
                _spashiny_ctx.adata_sm_aligned.set(adata_SM_aligned_obj)
            else:
                _spashiny_ctx.log(
                    "No aligned SM coordinates were found. KNN reassignment requires SM data with obsm['spatial_transformed']."
                )
                _spashiny_ctx.adata_sm_aligned.set(None)
            _spashiny_ctx.log(" Calculating QC metrics ...")
            smt.pp.calculate_qc_metrics_sm(adata_SM)
            user_threshold = float(_spashiny_ctx.input.min_intensity_threshold())
            _spashiny_ctx.log(f" Using user-defined min_total_intensity = {user_threshold:.2e}")
            total_intensity = adata_SM.obs["total_intensity"].values
            _spashiny_ctx.log(
                f"SM intensity range: min={np.min(total_intensity):.2e}, max={np.max(total_intensity):.2e}"
            )
            _spashiny_ctx.log(f"SM shape before filtering: {adata_SM.shape}")
            adata_SM = smt.pp.filter_cells_sm(adata_SM, min_total_intensity=user_threshold)
            _spashiny_ctx.log(f"SM shape after filtering: {adata_SM.shape}")
            _spashiny_ctx.adata_st.set(adata_ST)
            _spashiny_ctx.adata_sm.set(adata_SM)
            _spashiny_ctx.log("Data loading and QC completed successfully!")
        except Exception as e:
            _spashiny_ctx.log(f"An error occurred during processing: {str(e)}")

    _spashiny_ctx.save_and_load_h5ad = save_and_load_h5ad

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.check_data_info)
    def show_data_info():
        if _spashiny_globals.SPASHINY_WEB_PLATFORM:
            _spashiny_ctx.knn_input_bridge.inspect()
            return
        ad_st = _spashiny_ctx.adata_st.get()
        ad_sm = _spashiny_ctx.adata_sm.get()
        try:
            if ad_st is None and ad_sm is None:
                _spashiny_ctx.ui.notification_show(
                    "No ST or SM data is currently loaded.", type="warning", duration=4
                )
                return
            if ad_st is not None:
                st_info = f"\n    Type: {type(ad_st)}\n    Shape: {ad_st.shape}\n    obs columns: {list(ad_st.obs.columns)[:10]}\n    var columns: {list(ad_st.var.columns)[:10]}\n    obsm keys: {list(ad_st.obsm.keys())}\n    uns keys: {list(ad_st.uns.keys())}\n    "
            else:
                st_info = "ST data is not loaded."
            if ad_sm is not None:
                sm_info = f"\n    Type: {type(ad_sm)}\n    Shape: {ad_sm.shape}\n    obs columns: {list(ad_sm.obs.columns)[:10]}\n    var columns: {list(ad_sm.var.columns)[:10]}\n    obsm keys: {list(ad_sm.obsm.keys())}\n    uns keys: {list(ad_sm.uns.keys())}\n    "
            else:
                sm_info = "SM data is not loaded."
            _spashiny_ctx.ui.modal_show(
                _spashiny_ctx.ui.modal(
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.h3("Data Structure Summary", class_="mb-3"),
                        _spashiny_ctx.ui.div(
                            _spashiny_ctx.ui.h5("ST Data", class_="mt-3"),
                            _spashiny_ctx.ui.tags.pre(
                                st_info,
                                style="""
                                background:#f5f5f7;
                                padding:14px;
                                border-radius:14px;
                                font-size:13px;
                                color:#1d1d1f;
                                white-space:pre-wrap;
                                word-break:break-word;
                                border:1px solid #e5e5e7;
                            """,
                            ),
                        ),
                        _spashiny_ctx.ui.div(
                            _spashiny_ctx.ui.h5("SM Data", class_="mt-4"),
                            _spashiny_ctx.ui.tags.pre(
                                sm_info,
                                style="""
                                background:#f5f5f7;
                                padding:14px;
                                border-radius:14px;
                                font-size:13px;
                                color:#1d1d1f;
                                white-space:pre-wrap;
                                word-break:break-word;
                                border:1px solid #e5e5e7;
                            """,
                            ),
                        ),
                    ),
                    title="Inspect Data",
                    easy_close=True,
                    size="l",
                    footer=None,
                )
            )
            _spashiny_ctx.ui.notification_show(
                "Data structure summary generated successfully.", type="message", duration=3
            )
        except Exception as e:
            _spashiny_ctx.ui.notification_show(
                f"Failed to inspect data: {str(e)}", type="error", duration=5
            )
            _spashiny_ctx.log(f"Failed to inspect data: {str(e)}")

    _spashiny_ctx.show_data_info = show_data_info
    _spashiny_ctx.adata_sm = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.adata_st = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.adata_sm_aligned = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.adata_st_aligned = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.knn_upload_chain_job_id = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.knn_example_job_id = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.knn_input_source = _spashiny_ctx.reactive.Value("")
    from knn_input_bridge import KNNInputBridge

    _spashiny_ctx.KNNInputBridge = KNNInputBridge
    _spashiny_ctx.knn_input_bridge = (
        _spashiny_ctx.KNNInputBridge(
            input=_spashiny_ctx.input,
            output=_spashiny_ctx.output,
            session=_spashiny_ctx.session,
            get_owner=_spashiny_ctx._cloud_session_record,
            get_analysis=_spashiny_ctx._cloud_analysis_session_id,
            get_source=_spashiny_ctx.knn_input_source.get,
            set_source=_spashiny_ctx.knn_input_source.set,
            get_alignment=lambda: (
                _spashiny_ctx._current_alignment_workflow_id(),
                (
                    _spashiny_ctx._read_alignment_workflow_state(
                        _spashiny_ctx._current_alignment_workflow_id()
                    )
                    if _spashiny_ctx._current_alignment_workflow_id()
                    else {}
                ),
            ),
            get_binding=lambda: (_spashiny_ctx.cloud_example_action_bindings.get() or {}).get(
                "y7-knn-reassignment-example"
            ),
            submit_example=_spashiny_ctx._submit_cloud_example_action_job,
            set_example_job=_spashiny_ctx.knn_example_job_id.set,
            set_upload_job=_spashiny_ctx.knn_upload_chain_job_id.set,
            current_module=_spashiny_ctx.current_module.get,
            log=_spashiny_ctx.log,
        )
        if _spashiny_globals.SPASHINY_WEB_PLATFORM
        else None
    )

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.knn_canonical_upload_event, ignore_none=True)
    def _receive_knn_canonical_upload():
        if _spashiny_globals.SPASHINY_WEB_PLATFORM:
            _spashiny_ctx.knn_input_bridge.upload_event(
                _spashiny_ctx.input.knn_canonical_upload_event()
            )

    _spashiny_ctx._receive_knn_canonical_upload = _receive_knn_canonical_upload

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.run_knn_plot)
    def _show_cloud_knn_figure():
        if _spashiny_globals.SPASHINY_WEB_PLATFORM:
            _spashiny_ctx.knn_input_bridge.show_saved("spatial visualization")

    _spashiny_ctx._show_cloud_knn_figure = _show_cloud_knn_figure

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.run_st_histograms)
    def _show_cloud_knn_histogram():
        if _spashiny_globals.SPASHINY_WEB_PLATFORM:
            _spashiny_ctx.knn_input_bridge.show_saved("intensity histograms")

    _spashiny_ctx._show_cloud_knn_histogram = _show_cloud_knn_histogram

    @_spashiny_ctx.render.download(filename=lambda: "knn_joint_ready.h5ad")
    def download_knn_joint_h5ad():
        yield from _spashiny_ctx.knn_input_bridge.stream_result("knn_joint_ready.h5ad")

    _spashiny_ctx.download_knn_joint_h5ad = download_knn_joint_h5ad

    @_spashiny_ctx.render.download(filename=lambda: "knn_sm_reassigned.h5ad")
    def download_knn_sm_h5ad():
        yield from _spashiny_ctx.knn_input_bridge.stream_result("knn_sm_reassigned.h5ad")

    _spashiny_ctx.download_knn_sm_h5ad = download_knn_sm_h5ad

    @_spashiny_ctx.render.download(filename=lambda: "knn_st_reassigned.h5ad")
    def download_knn_st_h5ad():
        yield from _spashiny_ctx.knn_input_bridge.stream_result("knn_st_reassigned.h5ad")

    _spashiny_ctx.download_knn_st_h5ad = download_knn_st_h5ad

    @_spashiny_ctx.render.download(filename=lambda: "knn_spot_mapping.json")
    def download_knn_spot_mapping():
        yield from _spashiny_ctx.knn_input_bridge.stream_result("knn_spot_mapping.json")

    _spashiny_ctx.download_knn_spot_mapping = download_knn_spot_mapping

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.scale_and_plot)
    def _submit_cloud_knn_scaling_preview():
        if _spashiny_globals.SPASHINY_WEB_PLATFORM:
            _spashiny_ctx.knn_input_bridge.submit("input_preview")

    _spashiny_ctx._submit_cloud_knn_scaling_preview = _submit_cloud_knn_scaling_preview

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(
        _spashiny_ctx.input.cloud_example_action_activated, ignore_none=True
    )
    def _select_knn_example_from_cloud_action():
        if not _spashiny_globals.SPASHINY_WEB_PLATFORM:
            return
        payload = _spashiny_ctx.input.cloud_example_action_activated() or {}
        if (
            not isinstance(payload, dict)
            or not payload.get("ready")
            or payload.get("action_id") != "y7-knn-reassignment-example"
            or (
                str(payload.get("analysis_session_id") or "")
                != str(_spashiny_ctx._cloud_analysis_session_id() or "")
            )
        ):
            return
        _spashiny_ctx.knn_input_source.set("EXAMPLE")
        _spashiny_ctx.knn_input_bridge.reset()
        _spashiny_ctx.log(
            "Official Y7_T example selected: QC ST, 1299-feature Raw SM and official aligned coordinates. Click Load Data & Run QC, then Run KNN Reassignment."
        )

    _spashiny_ctx._select_knn_example_from_cloud_action = _select_knn_example_from_cloud_action
    _spashiny_ctx.joint_plot1 = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.joint_plot2 = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.joint_adata_reactive = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.knn_plot_reactive = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.sm_hist_plot_reactive = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.alignment_step7_fig_reactive = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.scaled_preview_fig_reactive = _spashiny_ctx.reactive.Value(None)

    def show_busy_modal(title="Running", message="Processing, please wait..."):
        _spashiny_ctx.ui.modal_show(
            _spashiny_ctx.ui.modal(
                _spashiny_ctx.ui.div(
                    _spashiny_ctx.ui.p(message, class_="mb-2"),
                    _spashiny_ctx.ui.p("Please wait...", class_="text-muted small"),
                ),
                title=title,
                easy_close=False,
                footer=None,
            )
        )

    _spashiny_ctx.show_busy_modal = show_busy_modal

    def close_busy_modal():
        _spashiny_ctx.ui.modal_remove()
        _spashiny_globals.release_unused_memory()

    _spashiny_ctx.close_busy_modal = close_busy_modal

    def show_success(msg):
        _spashiny_ctx.ui.notification_show(msg, type="message", duration=3)

    _spashiny_ctx.show_success = show_success

    def show_warning(msg):
        _spashiny_ctx.ui.notification_show(msg, type="warning", duration=4)

    _spashiny_ctx.show_warning = show_warning

    def show_error(msg):
        _spashiny_ctx.ui.notification_show(msg, type="error", duration=5)

    _spashiny_ctx.show_error = show_error

    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("perform_scale_and_plot")
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.scale_and_plot)
    def perform_scale_and_plot():
        if _spashiny_globals.SPASHINY_WEB_PLATFORM:
            return None
        try:
            import matplotlib.pyplot as plt
            import scanpy as sc
            import numpy as np

            _spashiny_ctx.show_busy_modal(
                "Scaling Coordinates",
                "Scaling transformed SM coordinates and generating spatial plot...",
            )
            adata_ST = _spashiny_ctx.adata_st.get()
            adata_SM = _spashiny_ctx.adata_sm.get()
            sample_name = _spashiny_ctx.input.sm_sample_name()
            if adata_ST is None or adata_SM is None:
                _spashiny_ctx.close_busy_modal()
                _spashiny_ctx.log(" Please load both ST and SM data first.")
                _spashiny_ctx.show_warning("Please load both ST and SM data first.")
                return None
            if not sample_name:
                _spashiny_ctx.close_busy_modal()
                _spashiny_ctx.log(" Please enter a sample name first.")
                _spashiny_ctx.show_warning("Please enter a sample name first.")
                return None
            if "spatial" not in adata_ST.uns or sample_name not in adata_ST.uns["spatial"]:
                _spashiny_ctx.close_busy_modal()
                _spashiny_ctx.log(
                    f" Sample name '{sample_name}' was not found in ST.uns['spatial']."
                )
                _spashiny_ctx.show_warning(f"Sample name '{sample_name}' was not found.")
                return None
            if "spatial_transformed" not in adata_SM.obsm:
                _spashiny_ctx.close_busy_modal()
                _spashiny_ctx.log(
                    " SM data does not contain 'spatial_transformed'. Please run alignment first."
                )
                _spashiny_ctx.show_warning(
                    "SM transformed coordinates are missing. Please run alignment first."
                )
                return None
            _spashiny_ctx.log(" Scaling transformed SM coordinates...")
            scale_factor = adata_ST.uns["spatial"][sample_name]["scalefactors"][
                "tissue_hires_scalef"
            ]
            adata_SM.obsm["spatial_transformed_scaled"] = (
                adata_SM.obsm["spatial_transformed"] / scale_factor
            )
            adata_SM.obsm["spatial"] = adata_SM.obsm["spatial_transformed_scaled"]
            adata_SM.uns["spatial"] = {
                sample_name: {
                    "images": {"hires": adata_ST.uns["spatial"][sample_name]["images"]["hires"]},
                    "scalefactors": adata_ST.uns["spatial"][sample_name]["scalefactors"],
                }
            }
            _spashiny_ctx.log(" Generating scaled spatial plot...")
            fig, ax = plt.subplots(figsize=(6, 6))
            sc.pl.spatial(
                adata_SM,
                img_key="hires",
                color=["total_intensity" if "total_intensity" in adata_SM.obs.columns else None],
                show=False,
                ax=ax,
            )
            _spashiny_ctx.close_busy_modal()
            _spashiny_ctx.log(
                f"Coordinate scaling and plotting completed for sample '{sample_name}'."
            )
            _spashiny_ctx.show_success(f"Coordinate scaling completed for sample '{sample_name}'.")
            _spashiny_ctx.scaled_preview_fig_reactive.set(fig)
            return fig
        except Exception as e:
            _spashiny_ctx.close_busy_modal()
            _spashiny_ctx.log(f"Error during coordinate scaling and plotting: {str(e)}")
            _spashiny_ctx.show_error(f"Scaling/plotting failed: {str(e)}")
            return None

    _spashiny_ctx.perform_scale_and_plot = perform_scale_and_plot

    @_spashiny_ctx.render.download(filename=lambda: "scaled_spatial_preview.pdf")
    def download_scaled_preview_pdf():
        if _spashiny_globals.SPASHINY_WEB_PLATFORM:
            yield from _spashiny_ctx.knn_input_bridge.stream_preview_pdf()
            return
        import io

        fig = _spashiny_ctx.scaled_preview_fig_reactive.get()
        if fig is None:
            fig = _spashiny_ctx.make_alignment_message_fig(
                "No scaling preview is available. Please run Scaling & Preview first.",
                "Scaled Spatial Preview",
            )
        buf = io.BytesIO()
        _spashiny_globals.save_native_figure(fig, buf, format="pdf", bbox_inches="tight")
        buf.seek(0)
        yield buf.read()

    _spashiny_ctx.download_scaled_preview_pdf = download_scaled_preview_pdf

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.use_alignment_knn_handoff)
    def use_current_alignment_for_knn():
        workflow_id = _spashiny_ctx._current_alignment_workflow_id()
        state = _spashiny_ctx._read_alignment_workflow_state(workflow_id) if workflow_id else {}
        provenance = (
            state.get("input_provenance") if isinstance(state.get("input_provenance"), dict) else {}
        )
        st_lineage = provenance.get("st") if isinstance(provenance.get("st"), dict) else {}
        sm_lineage = provenance.get("sm") if isinstance(provenance.get("sm"), dict) else {}
        if (
            not workflow_id
            or str(state.get("step6_status") or "").lower() != "completed"
            or str(st_lineage.get("source_mode") or "").upper() != "USER_UPLOAD"
            or (str(sm_lineage.get("source_mode") or "").upper() != "USER_UPLOAD")
        ):
            _spashiny_ctx.ui.notification_show(
                "Complete Alignment Step 6 with user-uploaded ST and SM inputs before using this KNN handoff.",
                type="error",
                duration=8,
            )
            return
        _spashiny_ctx.log(
            f"KNN source selected: current user-upload Alignment workflow {workflow_id}."
        )
        _spashiny_ctx.knn_input_source.set("USER_UPLOAD_ALIGNMENT")
        _spashiny_ctx.knn_input_bridge.reset()
        _spashiny_ctx.ui.notification_show(
            "Current Alignment result is selected. Click Run KNN Reassignment to submit the CPU job.",
            type="message",
            duration=6,
        )

    _spashiny_ctx.use_current_alignment_for_knn = use_current_alignment_for_knn

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.run_knn_data)
    def process_knn_alignment():
        if _spashiny_globals.SPASHINY_WEB_PLATFORM:
            _spashiny_ctx.knn_input_bridge.submit("reassign")
            return
        import spatialmeta as smt
        import numpy as np
        import pandas as pd

        try:
            if _spashiny_globals.SPASHINY_WEB_PLATFORM:
                if _spashiny_ctx.knn_input_source.get() == "EXAMPLE":
                    from cloud.workflow_registry import INTEGRATION_POSTPROCESSING

                    cloud_job = _spashiny_ctx._submit_cloud_example_action_job(
                        workflow_name=INTEGRATION_POSTPROCESSING,
                        example_action_ids=("y7-knn-reassignment-example",),
                        parameters={
                            "n_neighbors": int(_spashiny_ctx.input.spot_knn_k()),
                            "dist_fold": float(_spashiny_ctx.input.spot_dist_fold()),
                            "source_mode": "EXAMPLE",
                        },
                        requested_resource="cpu",
                    )
                    _spashiny_ctx.knn_example_job_id.set(cloud_job.job_id)
                    _spashiny_ctx.log(
                        f"KNN Example worker job submitted: {cloud_job.job_id}. Open Job Center for status and downloads."
                    )
                    _spashiny_ctx.ui.notification_show(
                        f"KNN Example CPU job created: {cloud_job.job_id}",
                        type="message",
                        duration=8,
                    )
                    return
                workflow_id = _spashiny_ctx._current_alignment_workflow_id()
                state = (
                    _spashiny_ctx._read_alignment_workflow_state(workflow_id) if workflow_id else {}
                )
                provenance = (
                    state.get("input_provenance")
                    if isinstance(state.get("input_provenance"), dict)
                    else {}
                )
                st_lineage = provenance.get("st") if isinstance(provenance.get("st"), dict) else {}
                sm_lineage = provenance.get("sm") if isinstance(provenance.get("sm"), dict) else {}
                st_upload_id = str(st_lineage.get("reference") or "").strip()
                if (
                    not workflow_id
                    or str(state.get("step6_status") or "").lower() != "completed"
                    or str(st_lineage.get("source_mode") or "").upper() != "USER_UPLOAD"
                    or (str(sm_lineage.get("source_mode") or "").upper() != "USER_UPLOAD")
                    or (not st_upload_id)
                ):
                    raise RuntimeError(
                        "KNN requires the current Alignment Step 6 result derived from this tab's user-uploaded ST and SM inputs."
                    )
                session_record = _spashiny_ctx._cloud_session_record()
                analysis_session_id = str(_spashiny_ctx._cloud_analysis_session_id() or "").strip()
                if session_record is None or not analysis_session_id:
                    raise RuntimeError("The current tab analysis session is not ready.")
                from cloud.job_submission import JobSubmissionService
                from cloud.workflow_registry import INTEGRATION_POSTPROCESSING

                cloud_job = JobSubmissionService().submit(
                    session=session_record,
                    workflow_name=INTEGRATION_POSTPROCESSING,
                    input_upload_ids=[st_upload_id],
                    workflow_artifacts=[
                        {
                            "parent_type": "alignment_workflow",
                            "parent_workflow_id": workflow_id,
                            "role": "aligned_sm_h5ad",
                        }
                    ],
                    parameters={
                        "n_neighbors": int(_spashiny_ctx.input.spot_knn_k()),
                        "dist_fold": float(_spashiny_ctx.input.spot_dist_fold()),
                        "source_mode": "USER_UPLOAD_ALIGNMENT",
                        "input_asset_roles": {st_upload_id: "knn_st_h5ad"},
                    },
                    requested_resource="cpu",
                    analysis_session_id=analysis_session_id,
                )
                _spashiny_ctx.knn_upload_chain_job_id.set(cloud_job.job_id)
                _spashiny_ctx.log(
                    f"KNN worker job submitted from the current Alignment artifact: {cloud_job.job_id} (parent workflow {workflow_id})."
                )
                _spashiny_ctx.ui.notification_show(
                    "KNN reassignment job submitted to the CPU worker.", type="message", duration=6
                )
                return
            _spashiny_ctx.show_busy_modal(
                "Running KNN Reassignment", "Performing shared-location KNN spot reassignment..."
            )
            adata_ST = _spashiny_ctx.adata_st.get()
            adata_SM = _spashiny_ctx.adata_sm.get()
            if adata_ST is None or adata_SM is None:
                _spashiny_ctx.close_busy_modal()
                _spashiny_ctx.log(" Please complete ST and SM data loading first.")
                _spashiny_ctx.show_warning("Please load ST and SM data first.")
                _spashiny_ctx.adata_sm_aligned.set(None)
                _spashiny_ctx.adata_st_aligned.set(None)
                return
            k = int(_spashiny_ctx.input.spot_knn_k())
            dist_fold = float(_spashiny_ctx.input.spot_dist_fold())
            if _spashiny_ctx._ssh_remote_enabled():
                _spashiny_ctx.log(" SSH connected: running KNN reassignment on the remote server.")
                adata_SM_new, adata_ST_new = _spashiny_ctx.run_remote_knn_reassignment(
                    adata_ST, adata_SM, k, dist_fold
                )
                _spashiny_ctx.log(f"Remote KNN reassigned SM shape: {adata_SM_new.shape}")
                _spashiny_ctx.log(f"Remote KNN reassigned ST shape: {adata_ST_new.shape}")
                _spashiny_ctx.adata_sm_aligned.set(adata_SM_new)
                _spashiny_ctx.adata_st_aligned.set(adata_ST_new)
                _spashiny_ctx.close_busy_modal()
                _spashiny_ctx.show_success("Remote KNN spot reassignment completed successfully.")
                return
            _spashiny_ctx.log(" Checking original ST data...")
            _spashiny_ctx.log(f"  Original ST shape: {adata_ST.shape}")
            _spashiny_ctx.log(f"  Does total_counts exist? {'total_counts' in adata_ST.obs}")
            if "total_counts" in adata_ST.obs:
                counts_data = adata_ST.obs["total_counts"]
                _spashiny_ctx.log(
                    f"  total_counts stats: min={counts_data.min():.4f}, max={counts_data.max():.4f}"
                )
                _spashiny_ctx.log(f"  NaN count: {counts_data.isna().sum()}/{len(counts_data)}")
            _spashiny_ctx.log(" Step 1: Extracting spatial positions of ST spots...")
            ST_dot_in_df = smt.pp.ST_spot_sample(adata_ST, "spatial")
            _spashiny_ctx.log(f"ST spot sampling completed: {ST_dot_in_df.shape[0]} spots.")
            _spashiny_ctx.log(" Step 2: Calculating minimum ST spot distance...")
            min_dist = smt.pp.calculate_min_dist(adata_ST)
            _spashiny_ctx.log(f"Minimum distance: {min_dist:.4f}")
            _spashiny_ctx.log(
                f" Step 3: Running spot_align_byknn (K={k}, dist_fold={dist_fold})..."
            )
            adata_SM_new, adata_ST_new = smt.pp.spot_align_byknn(
                new_dot_in_df=ST_dot_in_df,
                adata_SM=adata_SM,
                adata_ST=adata_ST,
                min_dist=min_dist,
                n_neighbors=k,
                dist_fold=dist_fold,
            )
            _spashiny_ctx.log(" Post-KNN reassignment data check:")
            _spashiny_ctx.log(f"  New ST shape: {adata_ST_new.shape}")
            _spashiny_ctx.log(f"  New ST obs names (example): {list(adata_ST_new.obs_names[:5])}")
            _spashiny_ctx.log(f"  Original ST obs names (example): {list(adata_ST.obs_names[:5])}")
            _spashiny_ctx.log(" Recovering total_counts by index matching...")
            common_obs = adata_ST_new.obs_names.intersection(adata_ST.obs_names)
            _spashiny_ctx.log(f"  Shared observations: {len(common_obs)}")
            if len(common_obs) > 0:
                adata_ST_new.obs["total_counts"] = np.nan
                adata_ST_new.obs.loc[common_obs, "total_counts"] = adata_ST.obs.loc[
                    common_obs, "total_counts"
                ]
                _spashiny_ctx.log(
                    f"  Successfully inherited total_counts for {len(common_obs)} spots."
                )
                inherited_counts = adata_ST_new.obs.loc[common_obs, "total_counts"]
                _spashiny_ctx.log(
                    f"  Inherited range: {inherited_counts.min():.4f} - {inherited_counts.max():.4f}"
                )
            else:
                _spashiny_ctx.log(
                    " No shared observations found. Switching to spatial nearest-neighbor matching..."
                )
                from scipy.spatial import cKDTree

                original_coords = adata_ST.obsm["spatial"]
                tree = cKDTree(original_coords)
                new_coords = adata_ST_new.obsm["spatial"]
                distances, indices = tree.query(new_coords, k=1)
                adata_ST_new.obs["total_counts"] = adata_ST.obs.iloc[indices]["total_counts"].values
                _spashiny_ctx.log(
                    f"  Spatial nearest-neighbor mapping completed. Mean distance: {distances.mean():.2f}"
                )
            if "total_counts" in adata_ST_new.obs:
                final_counts = adata_ST_new.obs["total_counts"]
                nan_count = final_counts.isna().sum()
                valid_count = len(final_counts) - nan_count
                _spashiny_ctx.log(" Final ST validation:")
                _spashiny_ctx.log(f"  Total spots: {len(final_counts)}")
                _spashiny_ctx.log(f"  Valid values: {valid_count}")
                _spashiny_ctx.log(f"  NaN values: {nan_count}")
                if valid_count > 0:
                    _spashiny_ctx.log(
                        f"  total_counts range: {final_counts.min():.4f} - {final_counts.max():.4f}"
                    )
                else:
                    _spashiny_ctx.log("All total_counts are NaN. Applying fallback values.")
                    adata_ST_new.obs["total_counts"] = np.linspace(1, 100, len(adata_ST_new))
            else:
                _spashiny_ctx.log("total_counts column creation failed. Using default values.")
                adata_ST_new.obs["total_counts"] = np.ones(len(adata_ST_new))
            _spashiny_ctx.log(" Recovering SM metadata...")
            common_obs_sm = adata_SM_new.obs_names.intersection(adata_SM.obs_names)
            _spashiny_ctx.log(f"  Shared SM observations: {len(common_obs_sm)}")
            if len(common_obs_sm) > 0:
                for col in ["total_intensity", "mean_intensity"]:
                    if col in adata_SM.obs:
                        adata_SM_new.obs[col] = np.nan
                        adata_SM_new.obs.loc[common_obs_sm, col] = adata_SM.obs.loc[
                            common_obs_sm, col
                        ]
                        _spashiny_ctx.log(f"  Recovered SM column: {col}")
            smt.pp.calculate_qc_metrics_sm(adata_SM_new)
            _spashiny_ctx.log("KNN reassignment completed successfully.")
            _spashiny_ctx.adata_sm_aligned.set(adata_SM_new)
            _spashiny_ctx.adata_st_aligned.set(adata_ST_new)
            _spashiny_ctx.close_busy_modal()
            _spashiny_ctx.show_success("KNN spot reassignment completed successfully.")
        except Exception as e:
            _spashiny_ctx.close_busy_modal()
            _spashiny_ctx.log(f"KNN reassignment failed: {str(e)}")
            import traceback

            _spashiny_ctx.log(f"Detailed traceback: {traceback.format_exc()}")
            _spashiny_ctx.show_error(f"KNN reassignment failed: {str(e)}")
            _spashiny_ctx.adata_sm_aligned.set(None)
            _spashiny_ctx.adata_st_aligned.set(None)

    _spashiny_ctx.process_knn_alignment = process_knn_alignment

    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("knn_plot")
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.run_knn_plot)
    def knn_plot():
        if _spashiny_globals.SPASHINY_WEB_PLATFORM:
            return None
        import scanpy as sc
        import matplotlib.pyplot as plt
        import spatialmeta as smt
        import traceback

        try:
            _spashiny_ctx.show_busy_modal(
                "Generating Visualization", "Rendering reassigned ST and SM spatial plots..."
            )
            adata_SM_new = _spashiny_ctx.adata_sm_aligned.get()
            adata_ST_new = _spashiny_ctx.adata_st_aligned.get()
            if adata_SM_new is None or adata_ST_new is None:
                _spashiny_ctx.close_busy_modal()
                _spashiny_ctx.log(" Please complete KNN reassignment first.")
                _spashiny_ctx.show_warning("Please complete KNN reassignment first.")
                return None
            _spashiny_ctx.log(" Step 4: Generating spatial visualization with H&E background...")
            smt.pp.calculate_qc_metrics_sm(adata_SM_new)
            _spashiny_ctx.log("SM QC metrics recalculated.")
            fig, axes = plt.subplots(1, 2, figsize=(15, 6))
            try:
                sc.pl.spatial(
                    adata_SM_new,
                    img_key="hires",
                    color=["total_intensity"],
                    cmap=smt.pl.make_colormap(["#3c096c", "#FFFFFF", "#ff6b35"]),
                    show=False,
                    ax=axes[0],
                )
                axes[0].set_title("SM (Reassigned, total_intensity)")
                _spashiny_ctx.log("SM plot rendered with H&E background.")
            except Exception as e:
                _spashiny_ctx.log(f"SM plot rendering failed: {str(e)}")
                if "spatial" in adata_SM_new.obsm:
                    spatial_coords = adata_SM_new.obsm["spatial"]
                    intensity = adata_SM_new.obs["total_intensity"].values
                    axes[0].scatter(
                        spatial_coords[:, 0],
                        spatial_coords[:, 1],
                        c=intensity,
                        cmap=smt.pl.make_colormap(["#3c096c", "#FFFFFF", "#ff6b35"]),
                        s=30,
                        alpha=0.8,
                    )
                    axes[0].set_title("SM (No H&E Background)")
                    axes[0].set_xlabel("X")
                    axes[0].set_ylabel("Y")
            try:
                sc.pl.spatial(
                    adata_ST_new,
                    img_key="hires",
                    color=["total_counts"],
                    cmap="vlag",
                    show=False,
                    ax=axes[1],
                )
                axes[1].set_title("ST (total_counts)")
                _spashiny_ctx.log("ST plot rendered with H&E background.")
            except Exception as e:
                _spashiny_ctx.log(f"ST plot rendering failed: {str(e)}")
                if "spatial" in adata_ST_new.obsm:
                    spatial_coords = adata_ST_new.obsm["spatial"]
                    counts = adata_ST_new.obs["total_counts"].values
                    axes[1].scatter(
                        spatial_coords[:, 0],
                        spatial_coords[:, 1],
                        c=counts,
                        cmap="vlag",
                        s=30,
                        alpha=0.8,
                    )
                    axes[1].set_title("ST (No H&E Background)")
                    axes[1].set_xlabel("X")
                    axes[1].set_ylabel("Y")
            plt.tight_layout()
            _spashiny_ctx.knn_plot_reactive.set(fig)
            _spashiny_ctx.close_busy_modal()
            _spashiny_ctx.log("Visualization completed successfully.")
            _spashiny_ctx.show_success("KNN reassignment visualization generated.")
            return fig
        except Exception as e:
            _spashiny_ctx.close_busy_modal()
            _spashiny_ctx.log(f"Plotting failed: {str(e)}")
            _spashiny_ctx.log(f"Detailed traceback: {traceback.format_exc()}")
            _spashiny_ctx.show_error(f"Plotting failed: {str(e)}")
            return None

    _spashiny_ctx.knn_plot = knn_plot

    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("st_counts_histograms")
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.run_st_histograms)
    def st_counts_histograms():
        if _spashiny_globals.SPASHINY_WEB_PLATFORM:
            return None
        import matplotlib.pyplot as plt
        import seaborn as sns
        import numpy as np
        import pandas as pd
        import traceback

        try:
            _spashiny_ctx.show_busy_modal(
                "Generating Histograms", "Creating SM intensity distribution plots..."
            )
            adata_SM_new = _spashiny_ctx.adata_sm_aligned.get()
            if adata_SM_new is None:
                _spashiny_ctx.close_busy_modal()
                fig, ax = plt.subplots(figsize=(6, 4))
                ax.text(
                    0.5,
                    0.5,
                    "Please complete KNN reassignment first.",
                    ha="center",
                    va="center",
                    transform=ax.transAxes,
                    fontsize=12,
                )
                ax.set_title("SM Intensity Distribution")
                _spashiny_ctx.show_warning("Please complete KNN reassignment first.")
                return fig
            _spashiny_ctx.log(" Generating SM intensity distribution histograms...")
            available_columns = list(adata_SM_new.obs.columns)
            intensity_columns = [col for col in available_columns if "intensity" in col.lower()]
            _spashiny_ctx.log(f"Available columns: {available_columns}")
            _spashiny_ctx.log(f"Intensity-related columns: {intensity_columns}")
            fig, axs = plt.subplots(1, 2, figsize=(10, 4))
            if "total_intensity" in adata_SM_new.obs:
                data = adata_SM_new.obs["total_intensity"]
                sns.histplot(data, kde=True, ax=axs[0], color="#ff6b35", alpha=0.7)
                axs[0].set_title("Total Intensity Distribution")
                axs[0].set_xlabel("Total Intensity")
                axs[0].set_ylabel("Frequency")
                if data.notna().any():
                    mean_val = np.mean(data)
                    median_val = np.median(data)
                    axs[0].axvline(
                        mean_val,
                        color="red",
                        linestyle="--",
                        alpha=0.8,
                        label=f"Mean: {mean_val:.2f}",
                    )
                    axs[0].axvline(
                        median_val,
                        color="blue",
                        linestyle="--",
                        alpha=0.8,
                        label=f"Median: {median_val:.2f}",
                    )
                    axs[0].legend()
            else:
                axs[0].text(
                    0.5,
                    0.5,
                    "Missing total_intensity data",
                    ha="center",
                    va="center",
                    transform=axs[0].transAxes,
                )
                axs[0].set_title("Total Intensity Distribution")
            plotted = False
            preferred_columns = [
                "mean_intensity",
                "mean_intensity_neg",
                "mean_intensity_pos",
                "intensity_mean",
                "average_intensity",
            ]
            for col in preferred_columns:
                if col in adata_SM_new.obs:
                    data = adata_SM_new.obs[col]
                    if data.notna().any() and (not (data == 0).all()):
                        sns.histplot(data, kde=True, ax=axs[1], color="#3c096c", alpha=0.7)
                        axs[1].set_title(f"{col} Distribution")
                        axs[1].set_xlabel(col)
                        axs[1].set_ylabel("Frequency")
                        mean_val = np.mean(data)
                        median_val = np.median(data)
                        axs[1].axvline(
                            mean_val,
                            color="red",
                            linestyle="--",
                            alpha=0.8,
                            label=f"Mean: {mean_val:.2f}",
                        )
                        axs[1].axvline(
                            median_val,
                            color="blue",
                            linestyle="--",
                            alpha=0.8,
                            label=f"Median: {median_val:.2f}",
                        )
                        axs[1].legend()
                        plotted = True
                        _spashiny_ctx.log(f"Using column '{col}' for the right histogram.")
                        break
                    else:
                        _spashiny_ctx.log(
                            f" Column '{col}' exists but contains invalid or empty values."
                        )
            if not plotted:
                axs[1].text(
                    0.5,
                    0.5,
                    "No valid mean_intensity-like data found.\nAvailable columns:\n"
                    + ", ".join(intensity_columns),
                    ha="center",
                    va="center",
                    transform=axs[1].transAxes,
                    fontsize=10,
                )
                axs[1].set_title("Mean Intensity Distribution")
                _spashiny_ctx.log(" No valid mean-intensity column found.")
            plt.tight_layout()
            _spashiny_ctx.sm_hist_plot_reactive.set(fig)
            _spashiny_ctx.close_busy_modal()
            _spashiny_ctx.log("SM intensity histograms generated successfully.")
            _spashiny_ctx.show_success("SM intensity histograms generated.")
            return fig
        except Exception as e:
            _spashiny_ctx.close_busy_modal()
            _spashiny_ctx.log(f"Failed to generate SM histograms: {str(e)}")
            _spashiny_ctx.log(f"Detailed traceback: {traceback.format_exc()}")
            _spashiny_ctx.show_error(f"Histogram generation failed: {str(e)}")
            fig, ax = plt.subplots(figsize=(6, 4))
            ax.text(
                0.5,
                0.5,
                f"Plot error: {str(e)}",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=10,
            )
            ax.set_title("SM Intensity Distribution - Error")
            return fig

    _spashiny_ctx.st_counts_histograms = st_counts_histograms

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.run_filter_and_update)
    def filter_knn_results():
        if _spashiny_globals.SPASHINY_WEB_PLATFORM:
            _spashiny_ctx.knn_input_bridge.submit("postprocess")
            return
        try:
            import spatialmeta as smt

            _spashiny_ctx.show_busy_modal(
                "Filtering SM Cells", "Filtering SM cells and updating coordinate metadata..."
            )
            _spashiny_ctx.log(" Running SM cell filtering...")
            min_intensity = _spashiny_ctx.input.min_total_intensity()
            adata_SM_new = _spashiny_ctx.adata_sm_aligned.get()
            adata_ST_new = _spashiny_ctx.adata_st_aligned.get()
            if adata_SM_new is None:
                _spashiny_ctx.close_busy_modal()
                _spashiny_ctx.log("Please complete KNN reassignment first.")
                _spashiny_ctx.show_error("Please complete KNN reassignment first.")
                return
            if adata_ST_new is None:
                _spashiny_ctx.close_busy_modal()
                _spashiny_ctx.log("Missing adata_ST_new object.")
                _spashiny_ctx.show_error("Missing aligned ST object.")
                return
            adata_SM_new_filtered = smt.pp.filter_cells_sm(
                adata_SM_new, min_total_intensity=min_intensity
            )
            filtered_cells = adata_SM_new_filtered.n_obs
            original_cells = adata_SM_new.n_obs
            removed_cells = original_cells - filtered_cells
            _spashiny_ctx.log(
                f"Filtering completed. Original cells: {original_cells}, Retained: {filtered_cells}, Removed: {removed_cells}"
            )
            _spashiny_ctx.log(f"Minimum total intensity threshold: {min_intensity}")
            required_columns = ["x_coord", "y_coord", "spot_name"]
            missing_columns = [
                col for col in required_columns if col not in adata_ST_new.obs.columns
            ]
            if missing_columns:
                _spashiny_ctx.log(
                    f" Missing coordinate-related columns in aligned ST: {missing_columns}"
                )
                if "spatial" in adata_ST_new.obsm:
                    spatial_coords = adata_ST_new.obsm["spatial"]
                    if spatial_coords.shape[1] >= 2:
                        adata_ST_new.obs["x_coord"] = spatial_coords[:, 0]
                        adata_ST_new.obs["y_coord"] = spatial_coords[:, 1]
                        _spashiny_ctx.log("Extracted x_coord and y_coord from obsm['spatial'].")
                        if "spot_name" not in adata_ST_new.obs.columns:
                            adata_ST_new.obs["spot_name"] = adata_ST_new.obs.index
                            _spashiny_ctx.log("Created spot_name from observation index.")
            if all((col in adata_ST_new.obs.columns for col in required_columns)):
                _spashiny_ctx.log("ST coordinate metadata update completed.")
            else:
                _spashiny_ctx.log(" Coordinate metadata is still incomplete after update.")
            _spashiny_ctx.adata_sm_aligned.set(adata_SM_new_filtered)
            _spashiny_ctx.adata_st_aligned.set(adata_ST_new)
            _spashiny_ctx.close_busy_modal()
            _spashiny_ctx.show_success("SM filtering and coordinate update completed.")
        except Exception as e:
            _spashiny_ctx.close_busy_modal()
            error_msg = f"Error during SM filtering/update: {str(e)}"
            _spashiny_ctx.log(error_msg)
            _spashiny_ctx.show_error(error_msg)
            print(error_msg)

    _spashiny_ctx.filter_knn_results = filter_knn_results

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.generate_joint_visualization)
    def generate_joint_visualization():
        if _spashiny_globals.SPASHINY_WEB_PLATFORM:
            _spashiny_ctx.knn_input_bridge.show_saved("joint spatial visualization")
            return
        try:
            import scanpy as sc
            import spatialmeta as smt
            import matplotlib.pyplot as plt

            _spashiny_ctx.show_busy_modal(
                "Generating Joint Visualization",
                "Building integrated ST-SM object and rendering plots...",
            )
            _spashiny_ctx.log(" Generating joint ST-SM visualization...")
            adata_SM_new = _spashiny_ctx.adata_sm_aligned.get()
            adata_ST_new = _spashiny_ctx.adata_st_aligned.get()
            if adata_SM_new is None or adata_ST_new is None:
                _spashiny_ctx.close_busy_modal()
                _spashiny_ctx.log("Please complete filtering and alignment first.")
                _spashiny_ctx.show_error("Please complete filtering and alignment first.")
                return
            _spashiny_ctx.log(" Creating integrated ST-SM object...")
            joint_adata = smt.pp.joint_adata_sm_st(
                adata_SM_new=adata_SM_new, adata_ST_new=adata_ST_new
            )
            _spashiny_ctx.log("Integrated object created successfully.")
            _spashiny_ctx.log(" Rendering total_intensity spatial map...")
            fig1 = plt.figure(figsize=(10, 8))
            ax1 = fig1.add_subplot(111)
            sc.pl.spatial(
                joint_adata,
                img_key="hires",
                color=["total_intensity"],
                cmap=smt.pl.make_colormap(["#3c096c", "#FFFFFF", "#ff6b35"]),
                show=False,
                ax=ax1,
            )
            ax1.set_title("Total Intensity Distribution")
            plt.tight_layout()
            _spashiny_ctx.log("Total intensity spatial plot generated.")
            _spashiny_ctx.log(" Rendering total_counts spatial map...")
            fig2 = plt.figure(figsize=(10, 8))
            ax2 = fig2.add_subplot(111)
            sc.pl.spatial(
                joint_adata,
                img_key="hires",
                color=["total_counts"],
                cmap="vlag",
                show=False,
                ax=ax2,
            )
            ax2.set_title("Total Counts Distribution")
            plt.tight_layout()
            _spashiny_ctx.log("Total counts spatial plot generated.")
            _spashiny_ctx.joint_plot1.set(fig1)
            _spashiny_ctx.joint_plot2.set(fig2)
            _spashiny_ctx.joint_adata_reactive.set(joint_adata)
            _spashiny_ctx.close_busy_modal()
            _spashiny_ctx.log("Joint ST-SM visualization completed successfully.")
            _spashiny_ctx.show_success("Joint visualization generated successfully.")
        except Exception as e:
            _spashiny_ctx.close_busy_modal()
            error_msg = f"Joint visualization failed: {str(e)}"
            _spashiny_ctx.log(error_msg)
            _spashiny_ctx.show_error(error_msg)
            print(error_msg)
            import traceback

            traceback.print_exc()

    _spashiny_ctx.generate_joint_visualization = generate_joint_visualization

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.debug_integration)
    def debug_integration():
        """Debug the ST-SM integration process."""
        if _spashiny_globals.SPASHINY_WEB_PLATFORM:
            _spashiny_ctx.knn_input_bridge.inspect_result()
            return
        try:
            import spatialmeta as smt

            _spashiny_ctx.show_busy_modal(
                "Debugging Integration", "Inspecting ST-SM integration consistency..."
            )
            adata_SM_new = _spashiny_ctx.adata_sm_aligned.get()
            adata_ST_new = _spashiny_ctx.adata_st_aligned.get()
            _spashiny_ctx.log("=== ST-SM Integration Debugging ===")
            if adata_SM_new is None or adata_ST_new is None:
                _spashiny_ctx.close_busy_modal()
                _spashiny_ctx.log("Data is empty. Cannot run integration debugging.")
                _spashiny_ctx.show_error("Data is empty. Cannot debug integration.")
                return
            _spashiny_ctx.log(f"adata_SM_new cell count: {adata_SM_new.n_obs}")
            _spashiny_ctx.log(
                f"adata_SM_new cell index examples: {list(adata_SM_new.obs.index[:5])}"
            )
            _spashiny_ctx.log(f"adata_ST_new spot count: {adata_ST_new.n_obs}")
            _spashiny_ctx.log(
                f"adata_ST_new spot index examples: {list(adata_ST_new.obs.index[:5])}"
            )
            sm_cells = set(adata_SM_new.obs.index)
            st_spots = set(adata_ST_new.obs.index)
            overlap = sm_cells.intersection(st_spots)
            _spashiny_ctx.log("Index overlap analysis:")
            _spashiny_ctx.log(f"  - adata_SM_new cells: {len(sm_cells)}")
            _spashiny_ctx.log(f"  - adata_ST_new spots: {len(st_spots)}")
            _spashiny_ctx.log(f"  - Overlapping IDs: {len(overlap)}")
            if overlap:
                _spashiny_ctx.log(f"  - Example overlapping IDs: {list(overlap)[:5]}")
            else:
                _spashiny_ctx.log("  - No overlapping IDs found.")
                _spashiny_ctx.log("  - Possible reasons:")
                _spashiny_ctx.log("    * Cells and spots use different naming conventions")
                _spashiny_ctx.log("    * Data come from different samples or batches")
                _spashiny_ctx.log("    * Manual mapping may be required")
            try:
                joint_test = smt.pp.joint_adata_sm_st(
                    adata_SM_new=adata_SM_new, adata_ST_new=adata_ST_new
                )
                _spashiny_ctx.log(f"Test integration result shape: {joint_test.shape}")
            except Exception as e:
                _spashiny_ctx.log(f"Integration test failed: {str(e)}")
                import traceback

                _spashiny_ctx.log(f"Detailed traceback: {traceback.format_exc()}")
            _spashiny_ctx.log("=== Integration Debugging Finished ===")
            _spashiny_ctx.close_busy_modal()
            _spashiny_ctx.show_success("Integration debugging completed.")
        except Exception as e:
            _spashiny_ctx.close_busy_modal()
            _spashiny_ctx.log(f"Integration debugging failed: {str(e)}")
            _spashiny_ctx.show_error(f"Integration debugging failed: {str(e)}")

    _spashiny_ctx.debug_integration = debug_integration

    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("joint_spatial_plot1")
    def joint_spatial_plot1():
        try:
            import matplotlib.pyplot as plt

            fig = _spashiny_ctx.joint_plot1.get()
            if fig is None:
                fig, ax = plt.subplots(figsize=(8, 6))
                ax.text(
                    0.5,
                    0.5,
                    "Click 'Generate Joint Visualization' to create this plot.",
                    ha="center",
                    va="center",
                    transform=ax.transAxes,
                    fontsize=12,
                )
                ax.set_title("Total Intensity Distribution - Waiting")
                plt.tight_layout()
                return fig
            return fig
        except Exception as e:
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(figsize=(8, 6))
            ax.text(
                0.5,
                0.5,
                f"Render error: {str(e)}",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=10,
                color="red",
            )
            ax.set_title("Total Intensity Distribution - Render Error")
            plt.tight_layout()
            return fig

    _spashiny_ctx.joint_spatial_plot1 = joint_spatial_plot1

    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("joint_spatial_plot2")
    def joint_spatial_plot2():
        try:
            import matplotlib.pyplot as plt

            fig = _spashiny_ctx.joint_plot2.get()
            if fig is None:
                fig, ax = plt.subplots(figsize=(8, 6))
                ax.text(
                    0.5,
                    0.5,
                    "Click 'Generate Joint Visualization' to create this plot.",
                    ha="center",
                    va="center",
                    transform=ax.transAxes,
                    fontsize=12,
                )
                ax.set_title("Total Counts Distribution - Waiting")
                plt.tight_layout()
                return fig
            return fig
        except Exception as e:
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(figsize=(8, 6))
            ax.text(
                0.5,
                0.5,
                f"Render error: {str(e)}",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=10,
                color="red",
            )
            ax.set_title("Total Counts Distribution - Render Error")
            plt.tight_layout()
            return fig

    _spashiny_ctx.joint_spatial_plot2 = joint_spatial_plot2

    def _empty_pdf_message_pdf(message="No plot available. Please generate the plot first."):
        import os
        import tempfile
        import matplotlib.pyplot as plt
        from cloud.figure_export import EditablePdfPages as PdfPages

        temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        temp_pdf.close()
        with PdfPages(temp_pdf.name) as pdf:
            fig, ax = plt.subplots(figsize=(8.27, 11.69))
            ax.axis("off")
            ax.text(0.5, 0.5, message, ha="center", va="center", fontsize=16)
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)
        return temp_pdf.name

    _spashiny_ctx._empty_pdf_message_pdf = _empty_pdf_message_pdf

    @_spashiny_ctx.render.download(filename=lambda: "joint_visualization_report.pdf")
    def download_joint_pdf():
        if _spashiny_globals.SPASHINY_WEB_PLATFORM:
            yield from _spashiny_ctx.knn_input_bridge.stream_result("knn_joint_plots.pdf")
            return
        import os
        import tempfile
        from cloud.figure_export import EditablePdfPages as PdfPages

        try:
            fig1 = _spashiny_ctx.joint_plot1.get()
            fig2 = _spashiny_ctx.joint_plot2.get()
            if fig1 is None and fig2 is None:
                _spashiny_ctx.log(
                    " No joint plots available. Please generate joint visualization first."
                )
                _spashiny_ctx.show_warning(
                    "No joint plots available. Please generate joint visualization first."
                )
                temp_path = _spashiny_ctx._empty_pdf_message_pdf(
                    "No joint visualization available.\n\nPlease click 'Generate Joint Visualization' first."
                )
                with open(temp_path, "rb") as f:
                    yield f.read()
                os.unlink(temp_path)
                return
            _spashiny_ctx.log(" Exporting joint visualization PDF...")
            temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            temp_pdf.close()
            with PdfPages(temp_pdf.name) as pdf:
                if fig1 is not None:
                    pdf.savefig(fig1, bbox_inches="tight")
                if fig2 is not None:
                    pdf.savefig(fig2, bbox_inches="tight")
            _spashiny_ctx.log("Joint visualization PDF export completed.")
            _spashiny_ctx.show_success("Joint visualization PDF is ready for download.")
            with open(temp_pdf.name, "rb") as f:
                yield f.read()
            os.unlink(temp_pdf.name)
        except Exception as e:
            _spashiny_ctx.log(f"Failed to export Joint PDF: {str(e)}")
            _spashiny_ctx.show_error(f"Joint PDF export failed: {str(e)}")

    _spashiny_ctx.download_joint_pdf = download_joint_pdf

    @_spashiny_ctx.render.download(filename=lambda: "knn_reassignment_plot.pdf")
    def download_knn_pdf():
        if _spashiny_globals.SPASHINY_WEB_PLATFORM:
            yield from _spashiny_ctx.knn_input_bridge.stream_result(
                "figures/knn_reassignment_spatial.pdf"
            )
            return
        import os
        import tempfile
        from cloud.figure_export import EditablePdfPages as PdfPages

        try:
            fig = _spashiny_ctx.knn_plot_reactive.get()
            if fig is None:
                _spashiny_ctx.log(
                    " No KNN plot available. Please generate KNN visualization first."
                )
                _spashiny_ctx.show_warning(
                    "No KNN plot available. Please generate KNN visualization first."
                )
                temp_path = _spashiny_ctx._empty_pdf_message_pdf(
                    "No KNN visualization available.\n\nPlease click 'Run KNN Plot' first."
                )
                with open(temp_path, "rb") as f:
                    yield f.read()
                os.unlink(temp_path)
                return
            _spashiny_ctx.log(" Exporting KNN plot PDF...")
            temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            temp_pdf.close()
            with PdfPages(temp_pdf.name) as pdf:
                pdf.savefig(fig, bbox_inches="tight")
            _spashiny_ctx.log("KNN plot PDF export completed.")
            _spashiny_ctx.show_success("KNN plot PDF is ready for download.")
            with open(temp_pdf.name, "rb") as f:
                yield f.read()
            os.unlink(temp_pdf.name)
        except Exception as e:
            _spashiny_ctx.log(f"Failed to export KNN PDF: {str(e)}")
            _spashiny_ctx.show_error(f"KNN PDF export failed: {str(e)}")

    _spashiny_ctx.download_knn_pdf = download_knn_pdf

    @_spashiny_ctx.render.download(filename=lambda: "sm_intensity_histograms.pdf")
    def download_sm_hist_pdf():
        if _spashiny_globals.SPASHINY_WEB_PLATFORM:
            yield from _spashiny_ctx.knn_input_bridge.stream_result(
                "figures/knn_intensity_histograms.pdf"
            )
            return
        import os
        import tempfile
        from cloud.figure_export import EditablePdfPages as PdfPages

        try:
            fig = _spashiny_ctx.sm_hist_plot_reactive.get()
            if fig is None:
                _spashiny_ctx.log(" No SM histogram available. Please generate histogram first.")
                _spashiny_ctx.show_warning(
                    "No SM histogram available. Please generate histogram first."
                )
                temp_path = _spashiny_ctx._empty_pdf_message_pdf(
                    "No SM histogram available.\n\nPlease click 'Run SM Histogram' first."
                )
                with open(temp_path, "rb") as f:
                    yield f.read()
                os.unlink(temp_path)
                return
            _spashiny_ctx.log(" Exporting SM histogram PDF...")
            temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            temp_pdf.close()
            with PdfPages(temp_pdf.name) as pdf:
                pdf.savefig(fig, bbox_inches="tight")
            _spashiny_ctx.log("SM histogram PDF export completed.")
            _spashiny_ctx.show_success("SM histogram PDF is ready for download.")
            with open(temp_pdf.name, "rb") as f:
                yield f.read()
            os.unlink(temp_pdf.name)
        except Exception as e:
            _spashiny_ctx.log(f"Failed to export SM histogram PDF: {str(e)}")
            _spashiny_ctx.show_error(f"SM histogram PDF export failed: {str(e)}")

    _spashiny_ctx.download_sm_hist_pdf = download_sm_hist_pdf

    @_spashiny_ctx.render.download(filename=lambda: "full_analysis_report.pdf")
    def download_full_report_pdf():
        if _spashiny_globals.SPASHINY_WEB_PLATFORM:
            yield from _spashiny_ctx.knn_input_bridge.stream_result("knn_full_report.pdf")
            return
        import os
        import tempfile
        import matplotlib.pyplot as plt
        from cloud.figure_export import EditablePdfPages as PdfPages
        from datetime import datetime

        try:
            fig_knn = _spashiny_ctx.knn_plot_reactive.get()
            fig_hist = _spashiny_ctx.sm_hist_plot_reactive.get()
            fig_joint1 = _spashiny_ctx.joint_plot1.get()
            fig_joint2 = _spashiny_ctx.joint_plot2.get()
            if all((fig is None for fig in [fig_knn, fig_hist, fig_joint1, fig_joint2])):
                _spashiny_ctx.log(" No figures available for full report export.")
                _spashiny_ctx.show_warning("No figures available for full report export.")
                temp_path = _spashiny_ctx._empty_pdf_message_pdf(
                    "No analysis figures available.\n\nPlease generate plots before exporting the full report."
                )
                with open(temp_path, "rb") as f:
                    yield f.read()
                os.unlink(temp_path)
                return
            _spashiny_ctx.log(" Exporting full analysis report PDF...")
            temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            temp_pdf.close()
            with PdfPages(temp_pdf.name) as pdf:
                fig_cover, ax_cover = plt.subplots(figsize=(8.27, 11.69))
                ax_cover.axis("off")
                sample_name = (
                    _spashiny_ctx.input.sm_sample_name()
                    if hasattr(_spashiny_ctx.input, "sm_sample_name")
                    else "Unknown Sample"
                )
                export_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cover_text = f"\n    SpatialMeta Analysis Report\n\n    Sample Name: {sample_name}\n    Export Time: {export_time}\n\n    Included Sections:\n    1. KNN Reassignment Visualization\n    2. SM Intensity Histograms\n    3. Joint Total Intensity Visualization\n    4. Joint Total Counts Visualization\n                "
                ax_cover.text(0.5, 0.6, cover_text, ha="center", va="center", fontsize=16)
                pdf.savefig(fig_cover, bbox_inches="tight")
                plt.close(fig_cover)
                if fig_knn is not None:
                    pdf.savefig(fig_knn, bbox_inches="tight")
                if fig_hist is not None:
                    pdf.savefig(fig_hist, bbox_inches="tight")
                if fig_joint1 is not None:
                    pdf.savefig(fig_joint1, bbox_inches="tight")
                if fig_joint2 is not None:
                    pdf.savefig(fig_joint2, bbox_inches="tight")
            _spashiny_ctx.log("Full analysis report PDF export completed.")
            _spashiny_ctx.show_success("Full analysis report PDF is ready for download.")
            with open(temp_pdf.name, "rb") as f:
                yield f.read()
            os.unlink(temp_pdf.name)
        except Exception as e:
            _spashiny_ctx.log(f"Failed to export full analysis report PDF: {str(e)}")
            _spashiny_ctx.show_error(f"Full report export failed: {str(e)}")

    _spashiny_ctx.download_full_report_pdf = download_full_report_pdf

    @_spashiny_ctx.render.download(
        filename=lambda: f"{(_spashiny_ctx.input.sm_sample_name().strip().replace(' ', '_') if _spashiny_ctx.input.sm_sample_name() else 'sample')}_adata_joint_raw.h5ad"
    )
    def _legacy_download_joint_h5ad_raw():
        try:
            import tempfile
            from pathlib import Path

            joint_adata = _spashiny_ctx.joint_adata_reactive.get()
            if joint_adata is None:
                _spashiny_ctx.log(" No joint AnnData object available for download.")
                _spashiny_ctx.ui.notification_show(
                    "No joint AnnData object found. Please generate joint data first.",
                    type="warning",
                    duration=4,
                )
                return
            _spashiny_ctx.ui.modal_show(
                _spashiny_ctx.ui.modal(
                    "Preparing joint h5ad file for download...",
                    title="Preparing Download",
                    easy_close=False,
                    footer=None,
                )
            )
            _spashiny_ctx.log(" Preparing joint AnnData for local download...")
            tmp_dir = Path(tempfile.mkdtemp())
            sample_name = _spashiny_ctx.input.sm_sample_name()
            if sample_name and str(sample_name).strip():
                safe_sample_name = str(sample_name).strip().replace(" ", "_")
                out_file = tmp_dir / f"{safe_sample_name}_adata_joint_raw.h5ad"
            else:
                out_file = tmp_dir / "sample_adata_joint_raw.h5ad"
            joint_adata.write_h5ad(str(out_file))
            _spashiny_ctx.log(f"Joint h5ad prepared successfully: {out_file.name}")
            _spashiny_ctx.ui.modal_remove()
            return str(out_file)
        except Exception as e:
            _spashiny_ctx.ui.modal_remove()
            error_msg = f"Failed to prepare joint h5ad download: {str(e)}"
            _spashiny_ctx.log(error_msg)
            import traceback

            _spashiny_ctx.log(traceback.format_exc())
            _spashiny_ctx.ui.notification_show(
                f"Download failed: {str(e)}", type="error", duration=6
            )
            return

    _spashiny_ctx._legacy_download_joint_h5ad_raw = _legacy_download_joint_h5ad_raw


_STEPS = (_install_0,)


def server(_spashiny_ctx, step=0):
    return _STEPS[step](_spashiny_ctx)
