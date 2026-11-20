# Extracted from /app/app/ST-SM.py. Feature: alignment_auto; ordered phases preserve original initialization.
from spashiny._shared import runtime_globals as _spashiny_globals


def _install_0(_spashiny_ctx):

    def make_alignment_message_fig(message, title="Alignment Plot"):
        fig, ax = _spashiny_globals.plt.subplots(figsize=(8, 5))
        ax.axis("off")
        ax.text(0.5, 0.5, message, ha="center", va="center", transform=ax.transAxes, fontsize=12)
        ax.set_title(title)
        _spashiny_globals.plt.tight_layout()
        return fig

    _spashiny_ctx.make_alignment_message_fig = make_alignment_message_fig

    @_spashiny_ctx.render.download(filename=lambda: "alignment_preprocessing_plots.pdf")
    def download_alignment_pre_pdf():
        import io
        import os
        import matplotlib.image as mpimg
        from cloud.figure_export import EditablePdfPages as PdfPages

        for job_id in (
            _spashiny_ctx.manual_preview_job_id.get(),
            _spashiny_ctx.initial_preview_job_id.get(),
            _spashiny_ctx.side_preview_job_id.get(),
        ):
            vector_pdf = _spashiny_ctx._manual_preview_completed_vector_pdf(job_id, combined=True)
            if vector_pdf and _spashiny_ctx.Path(vector_pdf).is_file():
                _spashiny_ctx.log(
                    f"Downloading editable vector Alignment preprocessing PDF: {vector_pdf}"
                )
                yield from _spashiny_ctx._yield_safe_file(
                    _spashiny_ctx.Path(vector_pdf),
                    roots=_spashiny_ctx._alignment_allowed_result_roots(),
                    label="alignment_preprocessing_vector_pdf",
                )
                return
        raise RuntimeError(
            "The editable Alignment preview PDF is unavailable for this result. Generate the preview with the current worker; PNG screenshots are not exported as editable PDFs."
        )

    _spashiny_ctx.download_alignment_pre_pdf = download_alignment_pre_pdf
    import spatialmeta.model._alignment_module as _align_mod

    _spashiny_ctx._align_mod = _align_mod
    _spashiny_ctx._align_mod.os = _spashiny_globals.os
    _spashiny_ctx.alignment_model = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.alignment_result = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.adata_st_norm = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.adata_sm_norm = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.rasterized_data_val = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.result_dict_val = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.loss_history_val = _spashiny_ctx.reactive.Value([])
    _spashiny_ctx.alignment_step3_job_id = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.alignment_step4_job_id = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.alignment_step5_job_id = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.alignment_step5_coordinate_context = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.alignment_worker_result_dir = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.alignment_panel_image_url_cache = _spashiny_ctx.reactive.Value({})
    _spashiny_ctx.alignment_workflow_modal_state = _spashiny_ctx.reactive.Value({"phase": "IDLE"})
    _spashiny_ctx.alignment_step7_request_sequence = _spashiny_ctx.reactive.Value(0)
    _spashiny_ctx.alignment_step7_processed_sequence = _spashiny_ctx.reactive.Value(0)
    _spashiny_ctx.alignment_action_last_accepted_at = {}
    _spashiny_ctx.ALIGNMENT_ACTION_CLICK_COOLDOWN_SECONDS = 10.0
    _spashiny_ctx.ALIGNMENT_WORKFLOW_BUTTON_IDS = (
        "process_alignment_pre",
        "generate_initial",
        "generate_rotated",
        "show_stsm_model",
        "align_step1_normalize",
        "align_step2_create_model",
        "align_step3_train_vae",
        "align_step4_get_raster",
        "align_step5_fit_alignment",
        "align_step6_save_result",
        "align_step7_show_alignment_btn",
        "align_step8_export_h5ad",
    )
    _spashiny_ctx.ALIGNMENT_MODAL_STATE_FIELDS = {
        "preprocess": "preprocessing_status",
        "initial": "initial_preview_status",
        "manual": "manual_transform_status",
        "side": "side_preview_status",
        "step1": "step1_status",
        "step2": "step2_status",
        "step3": "step3_status",
        "step4": "step4_status",
        "step5": "step5_status",
        "step6": "step6_status",
        "step7": "step7_status",
    }
    _spashiny_ctx.ALIGNMENT_MODAL_SUCCESS_MESSAGES = {
        "preprocess": "ST-SM Alignment Preprocessing completed successfully. You may now generate a preview or apply a manual transformation.",
        "initial": "Initial ST / SM view generated successfully.",
        "manual": "Manual preprocessing completed successfully. The prealigned SM coordinates have been saved and will be used by ST-SM Automatic Alignment. You may now continue to Automatic Alignment.",
        "side": "Side-by-side preview generated successfully.",
        "step1": "Step 1 completed successfully. Coordinates are normalized and ready for model creation.",
        "step2": "Step 2 completed successfully. The Alignment VAE model is ready for training.",
        "step3": "VAE training completed successfully. You may now generate the Step 4 rasterized features.",
        "step4": "Step 4 completed successfully. Rasterized features and spot-sampling state are ready. You may now continue to Step 5.",
        "step5": "Step 5 completed successfully. SpatialMETA alignment fitting is complete. You may now save the alignment result.",
        "step6": "Alignment result saved successfully. You may now generate the final aligned preview.",
        "step7": "Final aligned preview generated successfully.",
    }
    _spashiny_ctx.ALIGNMENT_CLICK_STEP_LABELS = {
        "preprocess": "ST-SM Alignment Preprocessing",
        "initial": "Generate Initial Plot",
        "manual": "Apply Transformation",
        "side": "Generate Side-by-Side View",
        "step1": "Normalize Coordinates",
        "step2": "Create Model",
        "step3": "Train VAE",
        "step4": "Generate Raster",
        "step5": "Run Alignment",
        "step6": "Save Result",
        "step7": "Show Alignment",
        "step8": "Export Aligned SM h5ad",
    }

    def _alignment_modal_state():
        value = _spashiny_ctx.alignment_workflow_modal_state.get() or {}
        return dict(value) if isinstance(value, dict) else {"phase": "IDLE"}

    _spashiny_ctx._alignment_modal_state = _alignment_modal_state

    def _alignment_modal_is_blocking():
        state = _spashiny_ctx._alignment_modal_state()
        if state.get("phase") != "RUNNING":
            return False
        modal_workflow_id = state.get("workflow_id")
        workflow_id = _spashiny_ctx._current_alignment_workflow_id()
        return (
            not modal_workflow_id or not workflow_id or str(modal_workflow_id) == str(workflow_id)
        )

    _spashiny_ctx._alignment_modal_is_blocking = _alignment_modal_is_blocking

    def _alignment_modal_title(step, phase, job_status=""):
        labels = {
            "preprocess": "ST-SM Alignment Preprocessing",
            "initial": "Initial ST / SM Rendering",
            "manual": "Applying Manual SM Transformation",
            "side": "Generating Side-by-Side Preview",
            "step1": "Step 1 - Normalizing Coordinates",
            "step2": "Step 2 - Creating Alignment Model",
            "step3": "Step 3 - Training VAE",
            "step4": "Step 4 - Generating Rasterized Features",
            "step5": "Step 5 - SpatialMETA Alignment Fit",
            "step6": "Saving Current Alignment Result",
            "step7": "Generating Final Aligned ST-SM Preview",
        }
        prefix = (
            "Completed"
            if phase == "COMPLETED"
            else (
                "Failed"
                if phase == "FAILED"
                else "Queued" if str(job_status) == "queued" else "Running"
            )
        )
        return f"{prefix}: {labels.get(step, 'Alignment workflow')}"

    _spashiny_ctx._alignment_modal_title = _alignment_modal_title

    def _alignment_modal_body(state):
        phase = str(state.get("phase") or "IDLE")
        job_status = str(state.get("job_status") or "")
        step = str(state.get("step") or "")
        children = [
            _spashiny_ctx.ui.h4(
                _spashiny_ctx._alignment_modal_title(state.get("step"), phase, job_status)
            )
        ]
        if phase == "RUNNING":
            queued = job_status == "queued"
            children.append(
                _spashiny_ctx.ui.tags.div(
                    _spashiny_ctx.ui.tags.div(
                        class_="spinner-border spinner-border-sm", role="status"
                    ),
                    _spashiny_ctx.ui.tags.span(
                        " Queued - Waiting for Alignment worker" if queued else " Running...",
                        style="margin-left:8px;",
                    ),
                    style="display:flex; align-items:center; margin-bottom:12px;",
                )
            )
        children.append(
            _spashiny_ctx.ui.p(str(state.get("message") or "Processing, please wait..."))
        )
        if state.get("job_id"):
            children.append(
                _spashiny_ctx.ui.p(
                    _spashiny_ctx.ui.strong("Job ID: "), _spashiny_ctx.ui.code(str(state["job_id"]))
                )
            )
        if state.get("details"):
            children.append(
                _spashiny_ctx.ui.p(
                    str(state["details"]), style="white-space:pre-line; color:#4b5563;"
                )
            )
        if phase == "RUNNING":
            if job_status == "queued":
                children.append(
                    _spashiny_ctx.ui.p(
                        f"Waiting for an available {_spashiny_ctx._alignment_queue_worker_label(state.get('queue_class'))}.",
                        style="font-weight:600;",
                    )
                )
            else:
                children.append(
                    _spashiny_ctx.ui.p(
                        "Please wait for this step to complete.", style="font-weight:600;"
                    )
                )
            current_step = str(state.get("current_step") or "").strip()
            if current_step:
                children.append(
                    _spashiny_ctx.ui.p(
                        _spashiny_ctx.ui.strong("Current worker status: "), current_step
                    )
                )
            try:
                progress = float(state.get("progress"))
            except Exception:
                progress = None
            if progress is not None:
                progress = max(0.0, min(100.0, progress))
                children.append(
                    _spashiny_ctx.ui.tags.div(
                        _spashiny_ctx.ui.tags.div(
                            f"{progress:.1f}%",
                            class_="progress-bar",
                            role="progressbar",
                            style=f"width:{progress:.1f}%;",
                            **{
                                "aria-valuenow": f"{progress:.1f}",
                                "aria-valuemin": "0",
                                "aria-valuemax": "100",
                            },
                        ),
                        class_="progress",
                        style="height:22px; margin:10px 0;",
                    )
                )
            iteration = state.get("alignment_iteration")
            total = state.get("alignment_total")
            if iteration is not None and total:
                children.append(
                    _spashiny_ctx.ui.p(
                        f"Iteration: {iteration} / {total}", style="margin-bottom:4px;"
                    )
                )
            if step == "step3":
                train_epoch = state.get("train_epoch")
                train_total = state.get("train_total_epochs")
                if train_epoch is not None and train_total:
                    children.append(
                        _spashiny_ctx.ui.p(
                            _spashiny_ctx.ui.strong("Training progress: "),
                            f"Epoch {train_epoch} / {train_total}",
                            style="margin-bottom:4px;",
                        )
                    )
                train_loss = state.get("train_loss")
                if train_loss is not None:
                    try:
                        loss_text = f"{float(train_loss):.6g}"
                    except Exception:
                        loss_text = str(train_loss)
                    children.append(
                        _spashiny_ctx.ui.p(
                            _spashiny_ctx.ui.strong("Latest loss: "),
                            loss_text,
                            style="margin-bottom:4px;",
                        )
                    )
                train_device = state.get("device")
                if train_device:
                    children.append(
                        _spashiny_ctx.ui.p(
                            _spashiny_ctx.ui.strong("Device: "),
                            str(train_device),
                            style="margin-bottom:4px; color:#4b5563;",
                        )
                    )
            elapsed = state.get("elapsed_seconds")
            remaining = state.get("estimated_remaining_seconds")
            timing = []
            try:
                if elapsed is not None:
                    timing.append(f"elapsed {float(elapsed):.0f}s")
                if remaining is not None:
                    timing.append(f"remaining ~{float(remaining):.0f}s")
            except Exception:
                timing = []
            if timing:
                children.append(
                    _spashiny_ctx.ui.p(
                        "Timing: " + "; ".join(timing), style="margin-bottom:4px; color:#4b5563;"
                    )
                )
            postfix = state.get("alignment_postfix")
            if isinstance(postfix, dict) and postfix:
                parts = []
                for key in ("EM", "ER", "EP", "angle"):
                    if key in postfix:
                        try:
                            parts.append(f"{key}={float(postfix[key]):.4g}")
                        except Exception:
                            parts.append(f"{key}={postfix[key]}")
                if parts:
                    children.append(
                        _spashiny_ctx.ui.p(
                            "Metrics: " + ", ".join(parts),
                            style="margin-bottom:4px; color:#4b5563;",
                        )
                    )
        return children

    _spashiny_ctx._alignment_modal_body = _alignment_modal_body

    def _render_alignment_workflow_modal(state):
        if _spashiny_ctx.one_stop_active.get():
            return
        if str(state.get("phase") or "IDLE") == "IDLE":
            return
        _spashiny_ctx.ui.modal_show(
            _spashiny_ctx.ui.modal(
                _spashiny_ctx.ui.output_ui("alignment_workflow_modal_content"),
                title="Alignment workflow",
                footer=None,
                easy_close=False,
            )
        )

    _spashiny_ctx._render_alignment_workflow_modal = _render_alignment_workflow_modal

    @_spashiny_ctx.output
    @_spashiny_ctx.render.ui
    def alignment_workflow_modal_content():
        state = _spashiny_ctx._alignment_modal_state()
        if state.get("phase") == "IDLE":
            return _spashiny_ctx.ui.div()
        children = list(_spashiny_ctx._alignment_modal_body(state))
        if state.get("phase") in {"COMPLETED", "FAILED"}:
            children.append(
                _spashiny_ctx.ui.div(
                    _spashiny_ctx.ui.modal_button("Close"),
                    style="display:flex; justify-content:flex-end; margin-top:18px;",
                )
            )
        return _spashiny_ctx.ui.div(*children)

    _spashiny_ctx.alignment_workflow_modal_content = alignment_workflow_modal_content

    def _set_alignment_workflow_modal(state, *, render_modal=True):
        state = dict(state or {})
        state.setdefault("phase", "IDLE")
        current = _spashiny_ctx._alignment_modal_state()
        should_render = False
        if render_modal and state.get("phase") != "IDLE":
            if not current.get("modal_rendered"):
                should_render = True
            state["modal_rendered"] = bool(current.get("modal_rendered") or should_render)
        if current != state:
            _spashiny_ctx.alignment_workflow_modal_state.set(state)
            if should_render:
                _spashiny_ctx._render_alignment_workflow_modal(state)
        _spashiny_ctx._sync_alignment_workflow_buttons()

    _spashiny_ctx._set_alignment_workflow_modal = _set_alignment_workflow_modal

    def _set_alignment_step_state(step, status, **extra):
        field = _spashiny_ctx.ALIGNMENT_MODAL_STATE_FIELDS.get(step)
        workflow_id = _spashiny_ctx._current_alignment_workflow_id()
        if field and workflow_id:
            try:
                _spashiny_ctx._update_alignment_workflow_state(**{field: status, **extra})
            except Exception as exc:
                _spashiny_ctx.log(f"Unable to persist Alignment {step} status: {exc}")

    _spashiny_ctx._set_alignment_step_state = _set_alignment_step_state

    def _alignment_action_too_fast(step):
        now = _spashiny_ctx.time.monotonic()
        workflow_id = _spashiny_ctx._current_alignment_workflow_id() or "pending"
        key = f"{workflow_id}:{step}"
        last = _spashiny_ctx.alignment_action_last_accepted_at.get(key)
        if last is not None:
            remaining = _spashiny_ctx.ALIGNMENT_ACTION_CLICK_COOLDOWN_SECONDS - (now - float(last))
            if remaining > 0:
                wait_seconds = max(1, int(remaining + 0.999))
                label = _spashiny_ctx.ALIGNMENT_CLICK_STEP_LABELS.get(step, str(step))
                message = f"{label} has already been received. Please wait {wait_seconds} seconds before retrying; repeated clicks within 10 seconds do not submit duplicate jobs."
                _spashiny_ctx.log(
                    f"Alignment action throttled: step={step} wait_seconds={wait_seconds}"
                )
                _spashiny_ctx.ui.notification_show(message, type="warning", duration=6)
                return True
        _spashiny_ctx.alignment_action_last_accepted_at[key] = now
        stale_cutoff = now - 300.0
        for old_key, old_value in list(_spashiny_ctx.alignment_action_last_accepted_at.items()):
            try:
                if float(old_value) < stale_cutoff:
                    _spashiny_ctx.alignment_action_last_accepted_at.pop(old_key, None)
            except Exception:
                _spashiny_ctx.alignment_action_last_accepted_at.pop(old_key, None)
        return False

    _spashiny_ctx._alignment_action_too_fast = _alignment_action_too_fast

    def _start_alignment_workflow_modal(step, message, *, details="", defer_modal_until_job=False):
        current = _spashiny_ctx._alignment_modal_state()
        workflow_id = _spashiny_ctx._current_alignment_workflow_id()
        if current.get("phase") in {"COMPLETED", "FAILED"}:
            try:
                if not _spashiny_ctx.one_stop_active.get():
                    _spashiny_ctx.ui.modal_remove()
            finally:
                _spashiny_ctx.alignment_workflow_modal_state.set({"phase": "IDLE"})
            current = _spashiny_ctx._alignment_modal_state()
        if _spashiny_ctx._alignment_action_too_fast(step):
            return False
        if _spashiny_ctx._alignment_modal_is_blocking():
            _spashiny_ctx.log(
                f"Alignment workflow action blocked while {current.get('step') or 'another step'} is {current.get('phase', '').lower()}."
            )
            return False
        state = {
            "phase": "RUNNING",
            "step": step,
            "workflow_id": workflow_id,
            "job_id": None,
            "message": message,
            "details": details,
            "base_details": details,
            "started_at": _spashiny_ctx.time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        _spashiny_ctx._set_alignment_step_state(step, "running")
        _spashiny_ctx._set_alignment_workflow_modal(state, render_modal=not defer_modal_until_job)
        return True

    _spashiny_ctx._start_alignment_workflow_modal = _start_alignment_workflow_modal

    def _bind_alignment_workflow_modal_job(step, job_id, *, details=""):
        state = _spashiny_ctx._alignment_modal_state()
        workflow_id = _spashiny_ctx._current_alignment_workflow_id()
        status = _spashiny_ctx._alignment_status(job_id)
        job_status = str(status.get("status") or "queued")
        queue_class = str(status.get("queue_class") or "")
        if state.get("phase") != "RUNNING" or state.get("step") != step:
            state = {
                "phase": "RUNNING",
                "step": step,
                "workflow_id": workflow_id,
                "message": "Processing, please wait...",
                "started_at": _spashiny_ctx.time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            }
        running_message = (
            state.get("running_message") or state.get("message") or "Processing, please wait..."
        )
        base_details = details or state.get("base_details") or state.get("details", "")
        state.update(
            {
                "workflow_id": workflow_id,
                "job_id": str(job_id),
                "details": base_details,
                "base_details": base_details,
                "job_status": job_status,
                "queue_class": queue_class,
                "current_step": str(status.get("current_step") or "").strip(),
                "progress": status.get("progress"),
                "device": status.get("device"),
                "train_epoch": status.get("train_epoch"),
                "train_total_epochs": status.get("train_total_epochs"),
                "train_loss": status.get("train_loss"),
                "train_loss_history_len": status.get("train_loss_history_len"),
                "updated_at": status.get("updated_at"),
                "heartbeat_at": status.get("heartbeat_at"),
                "alignment_iteration": status.get("alignment_iteration"),
                "alignment_total": status.get("alignment_total"),
                "elapsed_seconds": status.get("elapsed_seconds"),
                "estimated_remaining_seconds": status.get("estimated_remaining_seconds"),
                "alignment_postfix": status.get("alignment_postfix"),
                "running_message": running_message,
                "message": (
                    _spashiny_ctx._alignment_queued_message(step, queue_class)
                    if job_status == "queued"
                    else running_message
                ),
            }
        )
        _spashiny_ctx._set_alignment_step_state(step, job_status)
        _spashiny_ctx._set_alignment_workflow_modal(state)

    _spashiny_ctx._bind_alignment_workflow_modal_job = _bind_alignment_workflow_modal_job

    def _complete_alignment_workflow_modal(step, *, job_id=None, message=None, details=""):
        workflow_id = _spashiny_ctx._current_alignment_workflow_id()
        _spashiny_ctx._set_alignment_step_state(step, "completed")
        state = {
            "phase": "COMPLETED",
            "step": step,
            "workflow_id": workflow_id,
            "job_id": str(job_id) if job_id else None,
            "message": message
            or _spashiny_ctx.ALIGNMENT_MODAL_SUCCESS_MESSAGES.get(step, "Completed successfully."),
            "details": details,
            "finished_at": _spashiny_ctx.time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        _spashiny_ctx._set_alignment_workflow_modal(state)
        try:
            _spashiny_ctx._sync_alignment_workflow_buttons()
        except Exception:
            pass

    _spashiny_ctx._complete_alignment_workflow_modal = _complete_alignment_workflow_modal

    def _fail_alignment_workflow_modal(step, error, *, job_id=None):
        message = str(error or "Unknown error")
        error_info = _spashiny_globals._analysis_error_info(
            "ALIGNMENT_FAILED",
            message,
            job_id=job_id or "",
            workflow="Alignment",
            current_step=step,
        )
        _spashiny_ctx._set_alignment_step_state(step, "failed", **{f"{step}_error": message})
        state = {
            "phase": "FAILED",
            "step": step,
            "workflow_id": _spashiny_ctx._current_alignment_workflow_id(),
            "job_id": str(job_id) if job_id else None,
            "message": f"{_spashiny_ctx._alignment_modal_title(step, 'FAILED')}: {error_info['label']}.\n{error_info['message']}\n{error_info['guidance']}",
            "details": error_info["details"],
            "finished_at": _spashiny_ctx.time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        _spashiny_ctx._set_alignment_workflow_modal(state)
        try:
            _spashiny_ctx._sync_alignment_workflow_buttons()
        except Exception:
            pass

    _spashiny_ctx._fail_alignment_workflow_modal = _fail_alignment_workflow_modal

    def _step_worker_completed(step, job_id):
        """Validate only the light artifacts required before unlocking a step."""
        if step == "initial":
            path = _spashiny_ctx._manual_preview_completed_image(job_id, "initial")
            if not path:
                raise RuntimeError("Initial preview PNG is not ready")
            _spashiny_ctx.initial_preview_img_val.set(path)
        elif step == "manual":
            path = _spashiny_ctx._manual_preview_completed_image(job_id, "overlay")
            if not path:
                raise RuntimeError("Manual preview PNG is not ready")
            _spashiny_ctx.manual_preview_img_val.set(path)
            _spashiny_ctx._restore_manual_transform_for_automatic()
        elif step == "side":
            path = _spashiny_ctx._manual_preview_completed_image(job_id, "side")
            if not path:
                raise RuntimeError("Side-by-side preview PNG is not ready")
            _spashiny_ctx.side_preview_img_val.set(path)
        elif step == "step3":
            manifest = _spashiny_ctx._completed_alignment_manifest(job_id)
            if manifest.get("status") != "completed" or not manifest.get("state_dict"):
                raise RuntimeError("Step3 model artifact is not ready")
        elif step == "step4":
            manifest = _spashiny_ctx._completed_alignment_manifest(job_id)
            state_meta = manifest.get("step4_state") if isinstance(manifest, dict) else {}
            if (
                not isinstance(state_meta, dict)
                or state_meta.get("sampling_payload") != "step4_sampling_state.pkl"
            ):
                raise RuntimeError("Step4 persistent spot-sampling state is not ready")
            if not _spashiny_ctx._sync_alignment_render_results():
                raise RuntimeError("Step4 display artifacts are not ready")
        elif step == "step5":
            if not _spashiny_ctx._load_alignment_fit_summary(job_id):
                raise RuntimeError("Step5 alignment artifacts could not be restored")

    _spashiny_ctx._step_worker_completed = _step_worker_completed

    def _workflow_step_complete(state, step):
        if step == "manual":
            return str(state.get("manual_transform_status") or "") == "completed"
        if step == "step1":
            return str(state.get("step1_status") or "") == "completed" or bool(
                state.get("step1_completed_at")
            )
        if step == "step2":
            return str(state.get("step2_status") or "") == "completed" or bool(
                state.get("step2_created_at")
            )
        if step in {"step3", "step4", "step5"}:
            job_id = state.get(f"{step}_job_id")
            return bool(
                job_id and _spashiny_ctx._alignment_status(job_id).get("status") == "completed"
            )
        if step == "step6":
            return str(state.get("step6_status") or "") == "completed" or bool(
                state.get("step6_completed_at")
            )
        return str(state.get(f"{step}_status") or "") == "completed"

    _spashiny_ctx._workflow_step_complete = _workflow_step_complete

    def _sync_alignment_workflow_buttons():
        """Apply native Shiny disabled state; handler guards remain authoritative."""
        try:
            workflow_id = _spashiny_ctx._current_alignment_workflow_id()
            state = _spashiny_ctx._read_alignment_workflow_state(workflow_id) if workflow_id else {}
            blocked = _spashiny_ctx._alignment_modal_is_blocking()
            manual_done = _spashiny_ctx._workflow_step_complete(state, "manual")
            step1_done = _spashiny_ctx._workflow_step_complete(state, "step1")
            step2_done = _spashiny_ctx._workflow_step_complete(state, "step2")
            step3_done = _spashiny_ctx._workflow_step_complete(state, "step3")
            step4_done = _spashiny_ctx._workflow_step_complete(state, "step4")
            step5_done = _spashiny_ctx._workflow_step_complete(state, "step5")
            step6_done = _spashiny_ctx._workflow_step_complete(state, "step6")
            enabled = {
                "process_alignment_pre": not blocked,
                "generate_initial": bool(workflow_id) and (not blocked),
                "generate_rotated": bool(workflow_id) and (not blocked),
                "show_stsm_model": manual_done and (not blocked),
                "align_step1_normalize": manual_done and (not blocked),
                "align_step2_create_model": step1_done and (not blocked),
                "align_step3_train_vae": step2_done and (not blocked),
                "align_step4_get_raster": step3_done and (not blocked),
                "align_step5_fit_alignment": step4_done and (not blocked),
                "align_step6_save_result": step5_done and (not blocked),
                "align_step7_show_alignment_btn": step6_done and (not blocked),
                "align_step8_export_h5ad": step6_done and (not blocked),
            }
            for button_id in _spashiny_ctx.ALIGNMENT_WORKFLOW_BUTTON_IDS:
                _spashiny_ctx.ui.update_action_button(
                    button_id, disabled=not bool(enabled.get(button_id, False))
                )
        except Exception:
            return

    _spashiny_ctx._sync_alignment_workflow_buttons = _sync_alignment_workflow_buttons

    @_spashiny_ctx.reactive.Effect
    def _poll_alignment_workflow_modal():
        state = _spashiny_ctx._alignment_modal_state()
        if state.get("phase") != "RUNNING":
            _spashiny_ctx._sync_alignment_workflow_buttons()
            return
        step = str(state.get("step") or "")
        job_id = str(state.get("job_id") or "")
        if not job_id:
            _spashiny_ctx._sync_alignment_workflow_buttons()
            return
        workflow_id = _spashiny_ctx._current_alignment_workflow_id()
        if (
            state.get("workflow_id")
            and workflow_id
            and (str(state.get("workflow_id")) != str(workflow_id))
        ):
            return
        status = _spashiny_ctx._alignment_status(job_id)
        job_status = str(status.get("status") or "queued")
        if job_status in {"queued", "running"}:
            current_step = str(status.get("current_step") or "").strip()
            queue_class = str(status.get("queue_class") or state.get("queue_class") or "")
            base_details = state.get("base_details") or state.get("details") or ""
            progress = status.get("progress")
            device = status.get("device")
            train_epoch = status.get("train_epoch")
            train_total = status.get("train_total_epochs")
            train_loss = status.get("train_loss")
            train_loss_len = status.get("train_loss_history_len")
            iteration = status.get("alignment_iteration")
            total = status.get("alignment_total")
            heartbeat_at = status.get("heartbeat_at")
            updated_at = status.get("updated_at")
            if (
                state.get("job_status") != job_status
                or state.get("current_step") != current_step
                or state.get("queue_class") != queue_class
                or (state.get("progress") != progress)
                or (state.get("device") != device)
                or (state.get("train_epoch") != train_epoch)
                or (state.get("train_total_epochs") != train_total)
                or (state.get("train_loss") != train_loss)
                or (state.get("train_loss_history_len") != train_loss_len)
                or (state.get("alignment_iteration") != iteration)
                or (state.get("alignment_total") != total)
                or (state.get("heartbeat_at") != heartbeat_at)
                or (state.get("updated_at") != updated_at)
            ):
                running_message = (
                    state.get("running_message")
                    or state.get("message")
                    or "Processing, please wait..."
                )
                state.update(
                    {
                        "job_status": job_status,
                        "current_step": current_step,
                        "queue_class": queue_class,
                        "details": base_details,
                        "base_details": base_details,
                        "progress": progress,
                        "device": device,
                        "train_epoch": train_epoch,
                        "train_total_epochs": train_total,
                        "train_loss": train_loss,
                        "train_loss_history_len": train_loss_len,
                        "alignment_iteration": iteration,
                        "alignment_total": total,
                        "elapsed_seconds": status.get("elapsed_seconds"),
                        "estimated_remaining_seconds": status.get("estimated_remaining_seconds"),
                        "alignment_postfix": status.get("alignment_postfix"),
                        "heartbeat_at": heartbeat_at,
                        "updated_at": updated_at,
                        "message": (
                            _spashiny_ctx._alignment_queued_message(step, queue_class)
                            if job_status == "queued"
                            else running_message
                        ),
                    }
                )
                _spashiny_ctx._set_alignment_step_state(step, job_status)
                _spashiny_ctx._set_alignment_workflow_modal(state)
            _spashiny_ctx.reactive.invalidate_later(2)
            return
        if job_status == "completed":
            try:
                _spashiny_ctx._step_worker_completed(step, job_id)
                _spashiny_ctx._complete_alignment_workflow_modal(step, job_id=job_id)
            except Exception as exc:
                _spashiny_ctx._fail_alignment_workflow_modal(step, exc, job_id=job_id)
            return
        _spashiny_ctx._fail_alignment_workflow_modal(
            step,
            status.get("error")
            or status.get("error_message")
            or f"worker ended with status {job_status}",
            job_id=job_id,
        )

    _spashiny_ctx._poll_alignment_workflow_modal = _poll_alignment_workflow_modal

    @_spashiny_ctx.reactive.Effect
    def _restore_running_alignment_modal_after_navigation():
        try:
            if (
                _spashiny_ctx.current_module.get() != "ST-SM model"
                or _spashiny_ctx._alignment_modal_is_blocking()
            ):
                return
            workflow_id = _spashiny_ctx._current_alignment_workflow_id()
            state = _spashiny_ctx._read_alignment_workflow_state(workflow_id) if workflow_id else {}
            for step, key in (
                ("step5", "step5_job_id"),
                ("step4", "step4_job_id"),
                ("step3", "step3_job_id"),
                ("manual", "manual_transform_job_id"),
            ):
                job_id = state.get(key)
                if job_id and _spashiny_ctx._alignment_status(job_id).get("status") in {
                    "queued",
                    "running",
                }:
                    _spashiny_ctx._bind_alignment_workflow_modal_job(step, job_id)
                    return
            _spashiny_ctx._sync_alignment_workflow_buttons()
        except Exception:
            return

    _spashiny_ctx._restore_running_alignment_modal_after_navigation = (
        _restore_running_alignment_modal_after_navigation
    )
    _spashiny_ctx.ALIGNMENT_VAE_BUNDLE_SCHEMA = "spashiny.automatic_alignment_vae_bundle"
    _spashiny_ctx.ALIGNMENT_VAE_BUNDLE_VERSION = 1

    def _alignment_vae_device():
        return "cuda:0" if _spashiny_globals.torch.cuda.is_available() else "cpu"

    _spashiny_ctx._alignment_vae_device = _alignment_vae_device

    def _build_alignment_vae_config(model=None):
        if model is None:
            model = _spashiny_ctx.alignment_model.get()
        if model is None:
            raise ValueError("No automatic alignment VAE model is available")
        adata_st_obj = getattr(model, "adata_st", None)
        adata_sm_obj = getattr(model, "adata_sm", None)
        return {
            "schema": _spashiny_ctx.ALIGNMENT_VAE_BUNDLE_SCHEMA,
            "version": _spashiny_ctx.ALIGNMENT_VAE_BUNDLE_VERSION,
            "exported_at": _spashiny_ctx.time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "model_class": "spatialmeta.model._alignment_model.AlignmentVAE",
            "model_config": {
                "n_latent": int(getattr(model, "n_latent", 10)),
                "hidden_stacks": list(getattr(model, "hidden_stacks", [128])),
                "reconstruction_method_st": getattr(model, "reconstruction_method_st", "zinb"),
                "reconstruction_method_sm": getattr(model, "reconstruction_method_sm", "g"),
                "encode_libsize": bool(getattr(model, "encode_libsize", False)),
                "device": str(getattr(model, "device", _spashiny_ctx._alignment_vae_device())),
            },
            "data_signature": {
                "st_shape": (
                    list(getattr(adata_st_obj, "shape", [])) if adata_st_obj is not None else None
                ),
                "sm_shape": (
                    list(getattr(adata_sm_obj, "shape", [])) if adata_sm_obj is not None else None
                ),
                "st_var_names": (
                    [str(x) for x in list(getattr(adata_st_obj, "var_names", []))[:200]]
                    if adata_st_obj is not None
                    else []
                ),
                "sm_var_names": (
                    [str(x) for x in list(getattr(adata_sm_obj, "var_names", []))[:200]]
                    if adata_sm_obj is not None
                    else []
                ),
            },
            "training": {
                "trained_epochs": len(_spashiny_ctx.loss_history_val.get() or []),
                "loss_history": [float(x) for x in _spashiny_ctx.loss_history_val.get() or []],
                "ready_to_skip_step3": True,
            },
            "note": "Import this bundle in Automatic Alignment to load the trained VAE weights and skip Step 3.",
        }

    _spashiny_ctx._build_alignment_vae_config = _build_alignment_vae_config

    def _load_alignment_state_dict(path, device):
        try:
            return _spashiny_globals.torch.load(path, map_location=device, weights_only=True)
        except TypeError:
            return _spashiny_globals.torch.load(path, map_location=device)

    _spashiny_ctx._load_alignment_state_dict = _load_alignment_state_dict

    def _safe_job_token(value, fallback="session"):
        text = _spashiny_ctx.re.sub("[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
        return text.strip("._-") or fallback

    _spashiny_ctx._safe_job_token = _safe_job_token

    def _alignment_owner_id():
        try:
            session_id = _spashiny_ctx._cloud_session_id()
        except Exception:
            session_id = ""
        return _spashiny_ctx._safe_job_token(session_id, "")

    _spashiny_ctx._alignment_owner_id = _alignment_owner_id

    def _alignment_analysis_session_id():
        owner_id = _spashiny_ctx._alignment_owner_id()
        try:
            candidate = str(_spashiny_ctx.input.spashiny_analysis_session_id() or "").strip()
        except Exception:
            candidate = ""
        candidate = _spashiny_ctx._safe_job_token(candidate, "")
        if not owner_id or not candidate:
            return ""
        try:
            from cloud.database import CloudDatabase

            CloudDatabase().get_analysis_session(candidate, owner_session_id=owner_id)
            return candidate
        except Exception:
            return ""

    _spashiny_ctx._alignment_analysis_session_id = _alignment_analysis_session_id

    def _log_alignment_scope_diag(phase):
        try:
            raw_token = _spashiny_ctx._cloud_session_token()
        except Exception:
            raw_token = ""
        try:
            raw_session_input = str(_spashiny_ctx.input.spashiny_session_id() or "").strip()
        except Exception:
            raw_session_input = ""
        try:
            raw_analysis_input = str(
                _spashiny_ctx.input.spashiny_analysis_session_id() or ""
            ).strip()
        except Exception:
            raw_analysis_input = ""
        try:
            raw_browser_input = str(_spashiny_ctx.input.spashiny_browser_client_id() or "").strip()
        except Exception:
            raw_browser_input = ""
        try:
            raw_page_input = str(_spashiny_ctx.input.spashiny_page_instance_id() or "").strip()
        except Exception:
            raw_page_input = ""
        try:
            raw_workflow_input = str(_spashiny_ctx.alignment_workflow_id.get() or "").strip()
        except Exception:
            raw_workflow_input = ""
        auth = {"ok": False, "owner_session_id": "", "session_status": "", "error": ""}
        if raw_token:
            try:
                from cloud.session_manager import SessionManager

                record = SessionManager().authenticate(raw_token)
                auth.update(
                    {
                        "ok": True,
                        "owner_session_id": getattr(record, "session_id", "") or "",
                        "session_status": getattr(record, "status", "") or "",
                    }
                )
            except Exception as exc:
                auth["error"] = exc.__class__.__name__
        analysis_lookup = {"ok": False, "owner_session_id": "", "error": ""}
        if auth.get("owner_session_id") and raw_analysis_input:
            try:
                from cloud.database import CloudDatabase

                record = CloudDatabase().get_analysis_session(
                    _spashiny_ctx._safe_job_token(raw_analysis_input, ""),
                    owner_session_id=auth["owner_session_id"],
                )
                analysis_lookup.update(
                    {"ok": True, "owner_session_id": str(record.get("owner_session_id") or "")}
                )
            except Exception as exc:
                analysis_lookup["error"] = exc.__class__.__name__
        try:
            print(
                "SPASHINY_TEST_ALIGNMENT_SCOPE_DIAG "
                + _spashiny_ctx.json.dumps(
                    {
                        "phase": phase,
                        "token_present": bool(raw_token),
                        "token_prefix": raw_token[:8] if raw_token else "",
                        "session_input": raw_session_input,
                        "analysis_session_input": raw_analysis_input,
                        "browser_client_input": raw_browser_input,
                        "page_instance_input": raw_page_input,
                        "workflow_input": raw_workflow_input,
                        "session_auth_ok": bool(auth.get("ok")),
                        "session_auth_owner": auth.get("owner_session_id", ""),
                        "session_auth_status": auth.get("session_status", ""),
                        "session_auth_error": auth.get("error", ""),
                        "analysis_lookup_ok": bool(analysis_lookup.get("ok")),
                        "analysis_lookup_owner": analysis_lookup.get("owner_session_id", ""),
                        "analysis_lookup_error": analysis_lookup.get("error", ""),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
        except Exception:
            pass

    _spashiny_ctx._log_alignment_scope_diag = _log_alignment_scope_diag

    def _require_alignment_scope():
        _spashiny_ctx._log_alignment_scope_diag("require_alignment_scope")
        owner_id = _spashiny_ctx._alignment_owner_id()
        analysis_session_id = _spashiny_ctx._alignment_analysis_session_id()
        if not owner_id or not analysis_session_id:
            raise RuntimeError(
                "Analysis session is not ready. Wait for session initialization before starting Alignment work."
            )
        return (owner_id, analysis_session_id)

    _spashiny_ctx._require_alignment_scope = _require_alignment_scope

    def _alignment_session_token():
        """Compatibility name for legacy state fields; this is the owner id."""
        return _spashiny_ctx._alignment_owner_id() or "unbound"

    _spashiny_ctx._alignment_session_token = _alignment_session_token

    def _alignment_jobs_root():
        return _spashiny_ctx.Path(
            _spashiny_globals.os.environ.get("SPASHINY_LOCAL_JOBS_ROOT")
            or _spashiny_globals.os.environ.get("SPASHINY_TEMP_ROOT")
            or "/workspace/jobs"
        )

    _spashiny_ctx._alignment_jobs_root = _alignment_jobs_root

    def _alignment_logs_root():
        return (
            _spashiny_ctx.Path(
                _spashiny_globals.os.environ.get("SPASHINY_LOCAL_LOGS_ROOT")
                or _spashiny_globals.os.environ.get("SPASHINY_LOG_DIR")
                or "/workspace/logs"
            )
            / "jobs"
        )

    _spashiny_ctx._alignment_logs_root = _alignment_logs_root

    def _alignment_result_root(job_id):
        base = _spashiny_ctx.Path(
            _spashiny_globals.os.environ.get("SPASHINY_LOCAL_RESULT_ROOT")
            or _spashiny_globals.os.environ.get("SPASHINY_RESULTS_DIR")
            or "/workspace/results"
        )
        owner_id, analysis_session_id = _spashiny_ctx._require_alignment_scope()
        return (
            base
            / "sessions"
            / "owners"
            / owner_id
            / "analysis_sessions"
            / analysis_session_id
            / _spashiny_ctx._safe_job_token(job_id, "alignment_job")
        )

    _spashiny_ctx._alignment_result_root = _alignment_result_root

    def _alignment_session_result_root():
        base = _spashiny_ctx.Path(
            _spashiny_globals.os.environ.get("SPASHINY_LOCAL_RESULT_ROOT")
            or _spashiny_globals.os.environ.get("SPASHINY_RESULTS_DIR")
            or "/workspace/results"
        )
        owner_id = _spashiny_ctx._alignment_owner_id() or "unbound"
        analysis_session_id = _spashiny_ctx._alignment_analysis_session_id() or "unbound"
        return base / "sessions" / "owners" / owner_id / "analysis_sessions" / analysis_session_id

    _spashiny_ctx._alignment_session_result_root = _alignment_session_result_root

    def _alignment_workflow_root(workflow_id=None):
        workflow_id = workflow_id or _spashiny_ctx.alignment_workflow_id.get()
        if not workflow_id:
            raise RuntimeError(
                "No current Alignment workflow is available. Start alignment preprocessing first."
            )
        return (
            _spashiny_ctx._alignment_session_result_root()
            / "workflows"
            / _spashiny_ctx._safe_job_token(workflow_id, "workflow")
        )

    _spashiny_ctx._alignment_workflow_root = _alignment_workflow_root

    def _alignment_current_workflow_pointer():
        return _spashiny_ctx._alignment_session_result_root() / "current_alignment_workflow.json"

    _spashiny_ctx._alignment_current_workflow_pointer = _alignment_current_workflow_pointer

    def _read_alignment_workflow_state(workflow_id=None):
        try:
            path = (
                _spashiny_ctx._alignment_workflow_root(workflow_id)
                / "alignment_workflow_state.json"
            )
            data = _spashiny_ctx.json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    _spashiny_ctx._read_alignment_workflow_state = _read_alignment_workflow_state

    def _current_alignment_workflow_id():
        workflow_id = _spashiny_ctx.alignment_workflow_id.get()
        if workflow_id:
            return workflow_id
        try:
            pointer = _spashiny_ctx.json.loads(
                _spashiny_ctx._alignment_current_workflow_pointer().read_text(encoding="utf-8")
            )
            candidate = str(pointer.get("workflow_id") or "")
            if (
                candidate
                and pointer.get("owner_id") == _spashiny_ctx._alignment_owner_id()
                and (
                    pointer.get("analysis_session_id")
                    == _spashiny_ctx._alignment_analysis_session_id()
                )
            ):
                _spashiny_ctx.alignment_workflow_id.set(candidate)
                return candidate
        except Exception:
            pass
        return None

    _spashiny_ctx._current_alignment_workflow_id = _current_alignment_workflow_id

    def _write_alignment_workflow_state(state):
        workflow_id = str(
            state.get("workflow_id") or _spashiny_ctx._current_alignment_workflow_id() or ""
        )
        if not workflow_id:
            raise RuntimeError("Cannot persist Alignment workflow state without a workflow id")
        state = dict(state)
        state["workflow_id"] = workflow_id
        owner_id, analysis_session_id = _spashiny_ctx._require_alignment_scope()
        state["session_id"] = owner_id
        state["owner_id"] = owner_id
        state["analysis_session_id"] = analysis_session_id
        state["updated_at"] = _spashiny_ctx.time.strftime("%Y-%m-%dT%H:%M:%S%z")
        root = _spashiny_ctx._alignment_workflow_root(workflow_id)
        root.mkdir(parents=True, exist_ok=True)
        path = root / "alignment_workflow_state.json"
        path.write_text(
            _spashiny_ctx.json.dumps(state, ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        _spashiny_ctx._alignment_current_workflow_pointer().parent.mkdir(
            parents=True, exist_ok=True
        )
        _spashiny_ctx._alignment_current_workflow_pointer().write_text(
            _spashiny_ctx.json.dumps(
                {
                    "workflow_id": workflow_id,
                    "session_id": owner_id,
                    "owner_id": owner_id,
                    "analysis_session_id": analysis_session_id,
                },
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )
        return state

    _spashiny_ctx._write_alignment_workflow_state = _write_alignment_workflow_state

    def _update_alignment_workflow_state(**updates):
        workflow_id = _spashiny_ctx._current_alignment_workflow_id()
        if not workflow_id:
            raise RuntimeError(
                "No current Alignment workflow is available. Start alignment preprocessing first."
            )
        state = _spashiny_ctx._read_alignment_workflow_state(workflow_id)
        state.update(updates)
        return _spashiny_ctx._write_alignment_workflow_state(state)

    _spashiny_ctx._update_alignment_workflow_state = _update_alignment_workflow_state

    def _begin_alignment_workflow(st_path, sm_path, adata_sm_obj, *, input_provenance=None):
        """Start a fresh workflow without modifying the input/example files."""
        owner_id, analysis_session_id = _spashiny_ctx._require_alignment_scope()
        workflow_id = f"alignment_workflow_{_spashiny_ctx.time.strftime('%Y%m%d_%H%M%S')}_{_spashiny_globals.uuid.uuid4().hex[:8]}"
        removed = []
        for key in ("spatial_transformed", "spatial_transformed_scaled"):
            if key in adata_sm_obj.obsm:
                del adata_sm_obj.obsm[key]
                removed.append(key)
        _spashiny_ctx.alignment_workflow_id.set(workflow_id)
        _spashiny_ctx.manual_transform_job_id.set(None)
        _spashiny_ctx.manual_transform_metadata_val.set(None)
        _spashiny_ctx.manual_transform_coordinates_val.set(None)
        _spashiny_ctx.alignment_step3_job_id.set(None)
        _spashiny_ctx.alignment_step4_job_id.set(None)
        _spashiny_ctx.alignment_step5_job_id.set(None)
        _spashiny_ctx.alignment_step6_result_id.set(None)
        _spashiny_ctx.alignment_step5_coordinate_context.set(None)
        _spashiny_ctx.alignment_step7_request_sequence.set(0)
        _spashiny_ctx.alignment_step7_processed_sequence.set(0)
        _spashiny_ctx.alignment_model.set(None)
        _spashiny_ctx.alignment_result.set(None)
        _spashiny_ctx.result_dict_val.set(None)
        _spashiny_ctx.raster_data.set(None)
        _spashiny_ctx.spot_data.set(None)
        _spashiny_ctx.raster_img_val.set(None)
        _spashiny_ctx.spot_fig_val.set(None)
        _spashiny_ctx.raster_panel_img_val.set({})
        _spashiny_ctx.spot_panel_img_val.set({})
        _spashiny_ctx._clear_alignment_panel_image_url_cache()
        state = _spashiny_ctx._write_alignment_workflow_state(
            {
                "schema": "spashiny.alignment.workflow",
                "version": 1,
                "workflow_id": workflow_id,
                "owner_id": owner_id,
                "analysis_session_id": analysis_session_id,
                "created_at": _spashiny_ctx.time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "input_provenance": dict(input_provenance or {}),
                "manual_transform_job_id": None,
                "preprocessing_status": "completed",
                "initial_preview_status": "not_started",
                "manual_transform_status": "not_started",
                "side_preview_status": "not_started",
                "step1_status": "not_started",
                "step2_status": "not_started",
                "step3_status": "not_started",
                "step4_status": "not_started",
                "step5_status": "not_started",
                "step6_status": "not_started",
                "step7_status": "not_started",
                "step3_job_id": None,
                "step4_job_id": None,
                "step5_job_id": None,
                "step6_result_id": None,
                "step6_handoff_artifact": None,
                "step7_artifact_path": None,
                "step7_artifact_ready": False,
                "step7_source_step5_job_id": None,
                "ignored_input_alignment_keys": removed,
            }
        )
        if removed:
            _spashiny_ctx.log(
                "New Alignment workflow ignores historical input alignment fields: "
                + ", ".join(removed)
            )
        _spashiny_ctx.log(f"Alignment workflow started: {workflow_id}")
        return state

    _spashiny_ctx._begin_alignment_workflow = _begin_alignment_workflow

    def _alignment_job_payload(job_id):
        if not job_id:
            return {}
        job_path = (
            _spashiny_ctx._alignment_jobs_root()
            / _spashiny_ctx._safe_job_token(job_id, "alignment_job")
            / "job.json"
        )
        try:
            data = _spashiny_ctx.json.loads(job_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {}
            owner_id = _spashiny_ctx._alignment_owner_id()
            analysis_session_id = _spashiny_ctx._alignment_analysis_session_id()
            if not owner_id or not analysis_session_id:
                return {}
            if (
                data.get("owner_id") != owner_id
                or data.get("analysis_session_id") != analysis_session_id
            ):
                return {}
            return data
        except Exception:
            return {}

    _spashiny_ctx._alignment_job_payload = _alignment_job_payload

    def _alignment_output_dir(job_id):
        payload = _spashiny_ctx._alignment_job_payload(job_id)
        if payload.get("output_dir"):
            return _spashiny_ctx.Path(payload["output_dir"])
        return _spashiny_ctx._alignment_result_root(job_id)

    _spashiny_ctx._alignment_output_dir = _alignment_output_dir

    def _alignment_model_config_for_worker(model):
        cfg = _spashiny_ctx._build_alignment_vae_config(model).get("model_config", {})
        cfg["device"] = _spashiny_ctx._alignment_vae_device()
        return cfg

    _spashiny_ctx._alignment_model_config_for_worker = _alignment_model_config_for_worker

    def _alignment_status(job_id):
        if not job_id:
            return {}
        path = (
            _spashiny_ctx._alignment_jobs_root()
            / _spashiny_ctx._safe_job_token(job_id, "alignment_job")
            / "status.json"
        )
        try:
            data = _spashiny_ctx.json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    _spashiny_ctx._alignment_status = _alignment_status

    def _latest_alignment_job(task):
        root = _spashiny_ctx._alignment_jobs_root()
        owner_id = _spashiny_ctx._alignment_owner_id()
        analysis_session_id = _spashiny_ctx._alignment_analysis_session_id()
        workflow_id = _spashiny_ctx._current_alignment_workflow_id()
        if not workflow_id:
            return None
        session_candidates = []
        for path in root.glob(f"alignment_{task}_*"):
            job_json = path / "job.json"
            status_json = path / "status.json"
            if not job_json.is_file():
                continue
            try:
                payload = _spashiny_ctx.json.loads(job_json.read_text(encoding="utf-8"))
            except Exception:
                continue
            mtime = (
                status_json.stat().st_mtime if status_json.exists() else job_json.stat().st_mtime
            )
            candidate = (mtime, payload.get("job_id"))
            if (
                payload.get("owner_id") == owner_id
                and payload.get("analysis_session_id") == analysis_session_id
                and (payload.get("workflow_id") == workflow_id)
            ):
                session_candidates.append(candidate)
        if not session_candidates:
            return None
        return sorted(session_candidates)[-1][1]

    _spashiny_ctx._latest_alignment_job = _latest_alignment_job

    def _write_alignment_inputs(job_dir, model):
        input_dir = _spashiny_ctx.Path(job_dir) / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        adata_st_obj = getattr(model, "adata_st", None)
        if adata_st_obj is None:
            adata_st_obj = _spashiny_ctx.adata_st_norm.get()
        if adata_st_obj is None:
            adata_st_obj = _spashiny_ctx.adata_st.get()
        adata_sm_obj = getattr(model, "adata_sm", None)
        if adata_sm_obj is None:
            adata_sm_obj = _spashiny_ctx.adata_sm_norm.get()
        if adata_sm_obj is None:
            adata_sm_obj = _spashiny_ctx.adata_sm_transformed.get()
        if adata_st_obj is None or adata_sm_obj is None:
            raise RuntimeError("Alignment ST/SM data are not ready. Run Step1 and Step2 first.")
        st_path = input_dir / "alignment_st.h5ad"
        sm_path = input_dir / "alignment_sm.h5ad"
        adata_st_obj.write_h5ad(st_path)
        adata_sm_obj.write_h5ad(sm_path)
        return (st_path, sm_path)

    _spashiny_ctx._write_alignment_inputs = _write_alignment_inputs
    _spashiny_ctx.ALIGNMENT_QUEUE_CLASS_BY_TASK = {
        "manual_preview": "alignment_light",
        "render_color_panel": "alignment_light",
        "train": "alignment_heavy",
        "render": "alignment_heavy",
        "fit_alignment": "alignment_heavy",
    }

    def _alignment_queue_class_for_task(task):
        queue_class = _spashiny_ctx.ALIGNMENT_QUEUE_CLASS_BY_TASK.get(str(task or ""))
        if not queue_class:
            raise RuntimeError(f"Unsupported Alignment worker task for queue routing: {task!r}")
        return queue_class

    _spashiny_ctx._alignment_queue_class_for_task = _alignment_queue_class_for_task

    def _alignment_queue_worker_label(queue_class):
        if queue_class == "alignment_light":
            return "Alignment Light worker"
        if queue_class == "alignment_heavy":
            return "Alignment Heavy worker"
        return "Alignment worker"

    _spashiny_ctx._alignment_queue_worker_label = _alignment_queue_worker_label

    def _alignment_queued_message(step, queue_class):
        labels = {
            "initial": "Initial ST / SM rendering",
            "manual": "Manual registration preview",
            "side": "Side-by-side preview",
            "step3": "Step 3 VAE training",
            "step4": "Step 4 raster generation",
            "step5": "Step 5 SpatialMETA alignment",
        }
        return f"{labels.get(step, 'Alignment job')} is queued. Waiting for an available {_spashiny_ctx._alignment_queue_worker_label(queue_class)}."

    _spashiny_ctx._alignment_queued_message = _alignment_queued_message

    def _launch_alignment_worker(job):
        owner_id, analysis_session_id = _spashiny_ctx._require_alignment_scope()
        workflow_id = _spashiny_ctx._current_alignment_workflow_id()
        if not workflow_id:
            raise RuntimeError(
                "No current Alignment workflow is available. Run alignment preprocessing first."
            )
        job.setdefault("workflow_id", workflow_id)
        queue_class = _spashiny_ctx._alignment_queue_class_for_task(job.get("task"))
        job["queue_class"] = queue_class
        job["queue_name"] = queue_class
        job.setdefault("created_at", _spashiny_ctx.time.strftime("%Y-%m-%dT%H:%M:%S%z"))
        job.setdefault("queued_at", job["created_at"])
        job["owner_id"] = owner_id
        job["analysis_session_id"] = analysis_session_id
        job["session_id"] = owner_id
        job_dir = _spashiny_ctx.Path(job["job_dir"])
        job_dir.mkdir(parents=True, exist_ok=True)
        _spashiny_ctx.Path(job["output_dir"]).mkdir(parents=True, exist_ok=True)
        _spashiny_ctx.Path(job["log_file"]).parent.mkdir(parents=True, exist_ok=True)
        job_json = job_dir / "job.json"
        status_json = job_dir / "status.json"
        job["status_file"] = str(status_json)
        job_json.write_text(
            _spashiny_ctx.json.dumps(job, ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        status_json.write_text(
            _spashiny_ctx.json.dumps(
                {
                    "job_id": job["job_id"],
                    "task": job["task"],
                    "status": "queued",
                    "owner_id": owner_id,
                    "analysis_session_id": analysis_session_id,
                    "workflow_id": workflow_id,
                    "queue_class": queue_class,
                    "queue_name": queue_class,
                    "created_at": job["created_at"],
                    "queued_at": job["queued_at"],
                },
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )
        return job["job_id"]

    _spashiny_ctx._launch_alignment_worker = _launch_alignment_worker

    def _submit_alignment_train(model, max_epoch):
        job_id = f"alignment_train_{_spashiny_ctx.time.strftime('%Y%m%d_%H%M%S')}_{_spashiny_globals.uuid.uuid4().hex[:8]}"
        job_dir = _spashiny_ctx._alignment_jobs_root() / job_id
        st_path, sm_path = _spashiny_ctx._write_alignment_inputs(job_dir, model)
        output_dir = _spashiny_ctx._alignment_result_root(job_id)
        job = {
            "job_id": job_id,
            "task": "train",
            "session_id": _spashiny_ctx._alignment_session_token(),
            "job_dir": str(job_dir),
            "output_dir": str(output_dir),
            "log_file": str(_spashiny_ctx._alignment_logs_root() / f"{job_id}.log"),
            "st_h5ad": str(st_path),
            "sm_h5ad": str(sm_path),
            "max_epoch": _spashiny_globals.alignment_epochs(),
            "parameter_policy": _spashiny_globals.NATIVE_SPATIALMETA_POLICY,
            "device": _spashiny_ctx._alignment_vae_device(),
            "model_config": _spashiny_ctx._alignment_model_config_for_worker(model),
        }
        return _spashiny_ctx._launch_alignment_worker(job)

    _spashiny_ctx._submit_alignment_train = _submit_alignment_train

    def _completed_alignment_manifest(job_id):
        if not job_id:
            return {}
        manifest = _spashiny_ctx._alignment_output_dir(job_id) / "result_manifest.json"
        try:
            data = _spashiny_ctx.json.loads(manifest.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    _spashiny_ctx._completed_alignment_manifest = _completed_alignment_manifest

    def _submit_alignment_render(train_job_id):
        workflow_id = _spashiny_ctx._current_alignment_workflow_id()
        if not workflow_id:
            raise RuntimeError(
                "No current Alignment workflow is available. Run alignment preprocessing first."
            )
        train_job_path = (
            _spashiny_ctx._alignment_jobs_root()
            / _spashiny_ctx._safe_job_token(train_job_id, "alignment_job")
            / "job.json"
        )
        train_job = _spashiny_ctx.json.loads(train_job_path.read_text(encoding="utf-8"))
        if train_job.get("workflow_id") != workflow_id:
            raise RuntimeError(
                "Step3 model belongs to a different Alignment workflow. Re-run Step3 for the current workflow."
            )
        train_manifest = _spashiny_ctx._completed_alignment_manifest(train_job_id)
        if train_manifest.get("status") != "completed":
            raise RuntimeError("Step3 worker job is not completed yet.")
        job_id = f"alignment_render_{_spashiny_ctx.time.strftime('%Y%m%d_%H%M%S')}_{_spashiny_globals.uuid.uuid4().hex[:8]}"
        job_dir = _spashiny_ctx._alignment_jobs_root() / job_id
        output_dir = _spashiny_ctx._alignment_result_root(job_id)
        job = {
            "job_id": job_id,
            "task": "render",
            "session_id": _spashiny_ctx._alignment_session_token(),
            "workflow_id": workflow_id,
            "job_dir": str(job_dir),
            "output_dir": str(output_dir),
            "log_file": str(_spashiny_ctx._alignment_logs_root() / f"{job_id}.log"),
            "source_train_job_id": train_job_id,
            "st_h5ad": str(train_job["st_h5ad"]),
            "sm_h5ad": str(train_job["sm_h5ad"]),
            "state_dict": str(train_manifest["state_dict"]),
            "device": str(train_manifest.get("device") or _spashiny_ctx._alignment_vae_device()),
            "model_config": dict(train_job.get("model_config") or {}),
            "max_raster_cells": 1500000,
            "raster_dx": 0.4,
        }
        return _spashiny_ctx._launch_alignment_worker(job)

    _spashiny_ctx._submit_alignment_render = _submit_alignment_render

    def _submit_alignment_fit(render_job_id, alignment_config, save_debug_figures):
        workflow_id = _spashiny_ctx._current_alignment_workflow_id()
        if not workflow_id:
            raise RuntimeError(
                "No current Alignment workflow is available. Run alignment preprocessing first."
            )
        render_job_path = (
            _spashiny_ctx._alignment_jobs_root()
            / _spashiny_ctx._safe_job_token(render_job_id, "alignment_job")
            / "job.json"
        )
        render_job = _spashiny_ctx.json.loads(render_job_path.read_text(encoding="utf-8"))
        if render_job.get("workflow_id") != workflow_id:
            raise RuntimeError(
                "Step4 result belongs to a different Alignment workflow. Re-run Step4 for the current workflow."
            )
        render_manifest = _spashiny_ctx._completed_alignment_manifest(render_job_id)
        if render_manifest.get("status") != "completed":
            raise RuntimeError("Step4 worker job is not completed yet.")
        state = _spashiny_ctx._read_alignment_workflow_state(workflow_id)
        train_job_id = state.get("step3_job_id") or _spashiny_ctx.alignment_step3_job_id.get()
        if not train_job_id:
            raise RuntimeError("Step3 worker job was not found.")
        if str(render_job.get("source_train_job_id") or "") != str(train_job_id):
            raise RuntimeError(
                "Step4 result was not rendered from the current workflow's Step3 model."
            )
        train_job = _spashiny_ctx._alignment_job_payload(train_job_id)
        if train_job.get("workflow_id") != workflow_id:
            raise RuntimeError("Step3 model belongs to a different Alignment workflow.")
        train_manifest = _spashiny_ctx._completed_alignment_manifest(train_job_id)
        if train_manifest.get("status") != "completed":
            raise RuntimeError("Step3 worker job is not completed yet.")
        job_id = f"alignment_fit_{_spashiny_ctx.time.strftime('%Y%m%d_%H%M%S')}_{_spashiny_globals.uuid.uuid4().hex[:8]}"
        job_dir = _spashiny_ctx._alignment_jobs_root() / job_id
        output_dir = _spashiny_ctx._alignment_result_root(job_id)
        job = {
            "job_id": job_id,
            "task": "fit_alignment",
            "session_id": _spashiny_ctx._alignment_session_token(),
            "workflow_id": workflow_id,
            "job_dir": str(job_dir),
            "output_dir": str(output_dir),
            "log_file": str(_spashiny_ctx._alignment_logs_root() / f"{job_id}.log"),
            "source_render_job_id": render_job_id,
            "source_render_output_dir": str(_spashiny_ctx._alignment_output_dir(render_job_id)),
            "st_h5ad": str(render_job["st_h5ad"]),
            "sm_h5ad": str(render_job["sm_h5ad"]),
            "state_dict": str(train_manifest["state_dict"]),
            "device": str(train_manifest.get("device") or _spashiny_ctx._alignment_vae_device()),
            "model_config": dict(render_job.get("model_config") or {}),
            "alignment_config": dict(alignment_config or {}),
            "save_debug_figures": bool(save_debug_figures),
        }
        return _spashiny_ctx._launch_alignment_worker(job)

    _spashiny_ctx._submit_alignment_fit = _submit_alignment_fit

    def _set_reactive_if_changed(value, new_value):
        try:
            old_value = value.get()
        except Exception:
            old_value = None
        if old_value != new_value:
            value.set(new_value)

    _spashiny_ctx._set_reactive_if_changed = _set_reactive_if_changed

    def _sync_alignment_render_results():
        """Synchronize only lightweight Step4 metadata/PNG paths for UI display.

        Do not load raster_result.pkl or spot_result.pkl from render.plot paths:
        those payloads are large and previously caused Web CPU/RAM runaway.
        """
        workflow_id = _spashiny_ctx._current_alignment_workflow_id()
        state = _spashiny_ctx._read_alignment_workflow_state(workflow_id) if workflow_id else {}
        job_id = _spashiny_ctx.alignment_step4_job_id.get() or state.get("step4_job_id")
        if not job_id:
            return False
        job = _spashiny_ctx._alignment_job_payload(job_id)
        if job.get("workflow_id") != workflow_id:
            return False
        status = _spashiny_ctx._alignment_status(job_id)
        if status.get("status") in {"queued", "running"}:
            try:
                _spashiny_ctx.reactive.invalidate_later(2)
            except Exception:
                pass
            return False
        manifest = _spashiny_ctx._completed_alignment_manifest(job_id)
        if manifest.get("status") != "completed":
            return False
        result_dir = _spashiny_ctx._alignment_output_dir(job_id)
        try:
            raster_img = None
            spot_img = None
            raster_panels = {}
            spot_panels = {}
            raster_name_map = {
                "sm_feature": ("sm rasterized feature", "sm_rasterized_feature"),
                "sm_latent": ("sm latent embedding", "sm_latent_embedding"),
                "st_image": ("st spatial image", "st_spatial_image"),
                "st_latent": ("st latent feature", "st_latent_feature"),
            }
            spot_name_map = {
                "st_latent": ("st tissue and latent structure", "st_tissue_latent_structure"),
                "sampled": ("randomly sampled inside-tissue spots", "sampled_inside_tissue_spots"),
                "mask": ("binary tissue mask", "binary_tissue_mask"),
            }
            for item in manifest.get("plots") or []:
                name = str(item.get("name") or "").lower()
                rel = str(item.get("path") or "")
                img_path = result_dir / rel
                if not img_path.is_file():
                    continue
                suffix = img_path.suffix.lower()
                group = str(item.get("group") or "").lower()
                panel = str(item.get("panel") or "").lower()
                item_plot_id = str(item.get("plot_id") or "").strip()
                if item_plot_id:
                    _spashiny_ctx._register_alignment_worker_color_spec(
                        item_plot_id, item.get("color_spec")
                    )
                if suffix in {".png", ".jpg", ".jpeg"} and group == "raster" and panel:
                    raster_panels[panel] = str(img_path)
                elif suffix in {".png", ".jpg", ".jpeg"} and group == "spot" and panel:
                    spot_panels[panel] = str(img_path)
                elif suffix in {".png", ".jpg", ".jpeg"}:
                    for key, tokens in raster_name_map.items():
                        if any((token in name or token in rel.lower() for token in tokens)):
                            raster_panels[key] = str(img_path)
                    for key, tokens in spot_name_map.items():
                        if any((token in name or token in rel.lower() for token in tokens)):
                            spot_panels[key] = str(img_path)
                if suffix in {".png", ".jpg", ".jpeg"} and (
                    "alignment raster panels" in name or rel.endswith("alignment_raster_panels.png")
                ):
                    raster_img = str(img_path)
                if suffix in {".png", ".jpg", ".jpeg"} and (
                    "alignment spot" in name or rel.endswith("alignment_spot_panels.png")
                ):
                    spot_img = str(img_path)
            if not raster_img and raster_panels:
                raster_img = next(iter(raster_panels.values()))
            if not spot_img and spot_panels:
                spot_img = next(iter(spot_panels.values()))
            if raster_img:
                _spashiny_ctx._set_reactive_if_changed(_spashiny_ctx.raster_img_val, raster_img)
            if spot_img:
                _spashiny_ctx._set_reactive_if_changed(_spashiny_ctx.spot_fig_val, spot_img)
            if raster_panels:
                _spashiny_ctx._set_reactive_if_changed(
                    _spashiny_ctx.raster_panel_img_val, raster_panels
                )
            if spot_panels:
                _spashiny_ctx._set_reactive_if_changed(
                    _spashiny_ctx.spot_panel_img_val, spot_panels
                )
            _spashiny_ctx._set_reactive_if_changed(
                _spashiny_ctx.alignment_worker_result_dir, str(result_dir)
            )
            _spashiny_ctx._set_reactive_if_changed(_spashiny_ctx.alignment_step4_job_id, job_id)
            return bool(raster_img or spot_img or raster_panels or spot_panels)
        except Exception as exc:
            _spashiny_ctx.log(f"Failed to sync Step4 worker result metadata: {exc}")
            return False

    _spashiny_ctx._sync_alignment_render_results = _sync_alignment_render_results

    def _alignment_worker_color_spec_from_current_result(plot_id):
        plot_id = str(plot_id or "")
        job_ids = []
        if plot_id == "initial_plot":
            job_ids.append(_spashiny_ctx.initial_preview_job_id.get())
        elif plot_id == "overlay_plot":
            job_ids.append(_spashiny_ctx.manual_preview_job_id.get())
        elif plot_id == "side_plot":
            job_ids.append(_spashiny_ctx.side_preview_job_id.get())
        else:
            color_jobs = _spashiny_ctx.alignment_color_panel_job_ids.get() or {}
            job_ids.append(color_jobs.get(plot_id))
            job_ids.append(_spashiny_ctx.alignment_step4_job_id.get())
            job_ids.append(_spashiny_ctx._latest_alignment_job("render"))
        for job_id in [item for item in job_ids if item]:
            manifest = _spashiny_ctx._completed_alignment_manifest(job_id)
            result_dir = _spashiny_ctx._alignment_output_dir(job_id)
            if manifest.get("status") != "completed":
                continue
            for item in manifest.get("plots") or []:
                if str(item.get("plot_id") or "") == plot_id and item.get("color_spec"):
                    return item.get("color_spec")
                rel = str(item.get("path") or "")
                cfg = _spashiny_ctx.ALIGNMENT_WORKER_COLOR_PLOTS.get(plot_id) or {}
                if rel and rel == str(cfg.get("artifact") or "") and item.get("color_spec"):
                    return item.get("color_spec")
            if result_dir and (not result_dir.exists()):
                continue
        return _spashiny_ctx.plot_color_specs.get(
            plot_id
        ) or _spashiny_ctx._alignment_fallback_color_spec(plot_id)

    _spashiny_ctx._alignment_worker_color_spec_from_current_result = (
        _alignment_worker_color_spec_from_current_result
    )

    def _alignment_current_plot_path(plot_id):
        plot_id = str(plot_id or "")
        if plot_id == "initial_plot":
            path = _spashiny_ctx.initial_preview_img_val.get()
            if path and _spashiny_ctx.Path(path).is_file():
                return path
            path = _spashiny_ctx._manual_preview_completed_image(
                _spashiny_ctx.initial_preview_job_id.get(), "initial"
            )
            if path and _spashiny_ctx.Path(path).is_file():
                _spashiny_ctx.initial_preview_img_val.set(path)
                return path
            return None
        if plot_id == "overlay_plot":
            path = _spashiny_ctx.manual_preview_img_val.get()
            if path and _spashiny_ctx.Path(path).is_file():
                return path
            path = _spashiny_ctx._manual_preview_completed_image(
                _spashiny_ctx.manual_preview_job_id.get(), "overlay"
            )
            if path and _spashiny_ctx.Path(path).is_file():
                _spashiny_ctx.manual_preview_img_val.set(path)
                return path
            return None
        if plot_id == "side_plot":
            path = _spashiny_ctx.side_preview_img_val.get()
            if path and _spashiny_ctx.Path(path).is_file():
                return path
            path = _spashiny_ctx._manual_preview_completed_image(
                _spashiny_ctx.side_preview_job_id.get(), "side"
            )
            if path and _spashiny_ctx.Path(path).is_file():
                _spashiny_ctx.side_preview_img_val.set(path)
                return path
            return None
        _spashiny_ctx._sync_alignment_render_results()
        cfg = _spashiny_ctx.ALIGNMENT_WORKER_COLOR_PLOTS.get(plot_id) or {}
        panel = str(cfg.get("panel") or "")
        group = str(cfg.get("group") or "")
        if group == "raster":
            path = (_spashiny_ctx.raster_panel_img_val.get() or {}).get(panel)
        elif group == "spot":
            path = (_spashiny_ctx.spot_panel_img_val.get() or {}).get(panel)
        else:
            path = None
        return path if path and _spashiny_ctx.Path(path).is_file() else None

    _spashiny_ctx._alignment_current_plot_path = _alignment_current_plot_path

    def _alignment_color_completed_image(plot_id):
        color_jobs = _spashiny_ctx.alignment_color_panel_job_ids.get() or {}
        job_id = color_jobs.get(str(plot_id or ""))
        if not job_id:
            return None
        status = _spashiny_ctx._alignment_status(job_id)
        if status.get("status") in {"queued", "running"}:
            try:
                _spashiny_ctx.reactive.invalidate_later(2)
            except Exception:
                pass
            return None
        if status.get("status") == "failed":
            return None
        manifest = _spashiny_ctx._completed_alignment_manifest(job_id)
        if manifest.get("status") != "completed":
            return None
        result_dir = _spashiny_ctx._alignment_output_dir(job_id)
        for item in manifest.get("plots") or []:
            if str(item.get("plot_id") or "") != str(plot_id or ""):
                continue
            rel = str(item.get("path") or "")
            path = result_dir / rel
            if path.is_file():
                _spashiny_ctx._register_alignment_worker_color_spec(plot_id, item.get("color_spec"))
                cfg = _spashiny_ctx.ALIGNMENT_WORKER_COLOR_PLOTS.get(str(plot_id or "")) or {}
                panel = str(cfg.get("panel") or "")
                group = str(cfg.get("group") or "")
                if group == "raster":
                    panels = dict(_spashiny_ctx.raster_panel_img_val.get() or {})
                    panels[panel] = str(path)
                    _spashiny_ctx.raster_panel_img_val.set(panels)
                elif group == "spot":
                    panels = dict(_spashiny_ctx.spot_panel_img_val.get() or {})
                    panels[panel] = str(path)
                    _spashiny_ctx.spot_panel_img_val.set(panels)
                return str(path)
        return None

    _spashiny_ctx._alignment_color_completed_image = _alignment_color_completed_image

    def _alignment_artifact_url(job_id, rel_path, *, ttl_seconds=3600):
        import hashlib
        import hmac
        import time as _time
        from urllib.parse import quote, urlencode

        job_id = _spashiny_ctx._safe_job_token(job_id, "alignment_job")
        payload = _spashiny_ctx._alignment_job_payload(job_id)
        owner_id = _spashiny_ctx._safe_job_token(payload.get("owner_id"), "")
        analysis_session_id = _spashiny_ctx._safe_job_token(payload.get("analysis_session_id"), "")
        rel_path = _spashiny_ctx._safe_cloud_result_rel_path(rel_path)
        if not owner_id or not analysis_session_id or (not job_id) or (not rel_path):
            return ""
        secret = (_spashiny_globals.os.environ.get("SPASHINY_SESSION_HMAC_SECRET") or "").strip()
        if not secret:
            return ""
        expires = str(int(_time.time()) + int(ttl_seconds))
        signed_payload = "\n".join(
            [owner_id, analysis_session_id, job_id, rel_path, expires]
        ).encode("utf-8")
        sig = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
        return (
            f"/lab-alignment-artifact/{quote(owner_id, safe='')}/{quote(analysis_session_id, safe='')}/{quote(job_id, safe='')}/{quote(rel_path, safe='/')}"
            + "?"
            + urlencode({"expires": expires, "sig": sig})
        )

    _spashiny_ctx._alignment_artifact_url = _alignment_artifact_url

    def _clear_alignment_panel_image_url_cache(*plot_ids):
        try:
            if plot_ids:
                cache = dict(_spashiny_ctx.alignment_panel_image_url_cache.get() or {})
                for plot_id in plot_ids:
                    cache.pop(str(plot_id), None)
                _spashiny_ctx.alignment_panel_image_url_cache.set(cache)
            else:
                _spashiny_ctx.alignment_panel_image_url_cache.set({})
        except Exception:
            pass

    _spashiny_ctx._clear_alignment_panel_image_url_cache = _clear_alignment_panel_image_url_cache

    def _alignment_cached_artifact_url(plot_id, job_id, rel_path, *, ttl_seconds=3600):
        plot_id = str(plot_id or "")
        job_id = _spashiny_ctx._safe_job_token(job_id, "alignment_job")
        rel_path = _spashiny_ctx._safe_cloud_result_rel_path(rel_path)
        if not plot_id or not job_id or (not rel_path):
            return ""
        try:
            path = _spashiny_ctx._alignment_output_dir(job_id) / rel_path
            stat = path.stat()
            file_key = f"{stat.st_mtime_ns}:{stat.st_size}"
        except Exception:
            file_key = ""
        cache_key = plot_id
        try:
            cache = dict(_spashiny_ctx.alignment_panel_image_url_cache.get() or {})
            cached = cache.get(cache_key)
            if (
                isinstance(cached, dict)
                and cached.get("job_id") == job_id
                and (cached.get("rel_path") == rel_path)
                and (cached.get("file_key") == file_key)
                and cached.get("url")
            ):
                return str(cached.get("url") or "")
        except Exception:
            cache = {}
        url = _spashiny_ctx._alignment_artifact_url(job_id, rel_path, ttl_seconds=ttl_seconds)
        if url:
            cache[cache_key] = {
                "job_id": job_id,
                "rel_path": rel_path,
                "file_key": file_key,
                "url": url,
            }
            try:
                _spashiny_ctx.alignment_panel_image_url_cache.set(cache)
            except Exception:
                pass
        return url

    _spashiny_ctx._alignment_cached_artifact_url = _alignment_cached_artifact_url

    def _alignment_rel_path_for_job(job_id, path):
        try:
            root = _spashiny_ctx._alignment_output_dir(job_id).resolve()
            resolved = _spashiny_ctx.Path(path).resolve()
            return resolved.relative_to(root).as_posix()
        except Exception:
            return ""

    _spashiny_ctx._alignment_rel_path_for_job = _alignment_rel_path_for_job

    def _alignment_panel_image_source(plot_id):
        plot_id = str(plot_id or "")
        cfg = _spashiny_ctx.ALIGNMENT_WORKER_COLOR_PLOTS.get(plot_id) or {}
        color_job_id = (_spashiny_ctx.alignment_color_panel_job_ids.get() or {}).get(plot_id)
        if color_job_id:
            status = _spashiny_ctx._alignment_status(color_job_id)
            if status.get("status") in {"queued", "running"}:
                try:
                    _spashiny_ctx.reactive.invalidate_later(2)
                except Exception:
                    pass
                return (
                    "",
                    f"Color render is {status.get('status')} for {_spashiny_ctx._alignment_color_title(plot_id)}...\nJob: {color_job_id}",
                )
            if status.get("status") == "failed":
                return (
                    "",
                    _spashiny_globals._analysis_status_error_text(
                        f"Color render failed for {_spashiny_ctx._alignment_color_title(plot_id)}",
                        status,
                        job_id=color_job_id,
                        current_step="alignment color render",
                    ),
                )
            manifest = _spashiny_ctx._completed_alignment_manifest(color_job_id)
            result_dir = _spashiny_ctx._alignment_output_dir(color_job_id)
            if manifest.get("status") == "completed":
                for item in manifest.get("plots") or []:
                    rel = str(item.get("path") or "")
                    if str(item.get("plot_id") or "") != plot_id and rel != str(
                        cfg.get("artifact") or ""
                    ):
                        continue
                    path = result_dir / rel
                    if path.is_file():
                        _spashiny_ctx._register_alignment_worker_color_spec(
                            plot_id, item.get("color_spec")
                        )
                        rel_path = _spashiny_ctx._alignment_rel_path_for_job(color_job_id, path)
                        url = _spashiny_ctx._alignment_cached_artifact_url(
                            plot_id, color_job_id, rel_path
                        )
                        if url:
                            return (url, "")
        _spashiny_ctx._sync_alignment_render_results()
        panel = str(cfg.get("panel") or "")
        group = str(cfg.get("group") or "")
        if group == "raster":
            path = (_spashiny_ctx.raster_panel_img_val.get() or {}).get(panel)
            default_message = "Please run Step 4 to generate the raster panels first."
        elif group == "spot":
            path = (_spashiny_ctx.spot_panel_img_val.get() or {}).get(panel)
            default_message = "Please run Step 4 to generate the spot panels first."
        else:
            path = None
            default_message = "Please run the corresponding worker step first."
        source_job_id = (
            _spashiny_ctx.alignment_step4_job_id.get()
            or _spashiny_ctx._latest_alignment_job("render")
        )
        if path and source_job_id and _spashiny_ctx.Path(path).is_file():
            rel_path = _spashiny_ctx._alignment_rel_path_for_job(source_job_id, path)
            url = _spashiny_ctx._alignment_cached_artifact_url(plot_id, source_job_id, rel_path)
            if url:
                return (url, "")
        if source_job_id:
            status = _spashiny_ctx._alignment_status(source_job_id)
            if status.get("status") in {"queued", "running"}:
                try:
                    _spashiny_ctx.reactive.invalidate_later(2)
                except Exception:
                    pass
                return ("", f"Step4 render is {status.get('status')}...\nJob: {source_job_id}")
            if status.get("status") == "failed":
                return (
                    "",
                    _spashiny_globals._analysis_status_error_text(
                        "Step4 render failed",
                        status,
                        job_id=source_job_id,
                        current_step="Step4 render",
                    ),
                )
        return ("", default_message)

    _spashiny_ctx._alignment_panel_image_source = _alignment_panel_image_source

    def _alignment_panel_image_ui(plot_id, *, height="430px"):
        url, message = _spashiny_ctx._alignment_panel_image_source(plot_id)
        if url:
            return _spashiny_ctx.ui.div(
                "Loading image...",
                style=f"min-height:{height}; width:100%; display:flex; align-items:center; justify-content:center; text-align:center; color:#64748B; padding:16px;",
            )
        return _spashiny_ctx.ui.div(
            _spashiny_ctx.ui.tags.pre(
                message or "No image is available yet.", style="white-space:pre-wrap; margin:0;"
            ),
            style=f"min-height:{height}; width:100%; display:flex; align-items:center; justify-content:center; text-align:center; color:#64748B; padding:16px;",
        )

    _spashiny_ctx._alignment_panel_image_ui = _alignment_panel_image_ui

    @_spashiny_ctx.output
    @_spashiny_ctx.render.ui
    def raster_panel_sm_feature_img_ui():
        return _spashiny_ctx._alignment_panel_image_ui("raster_panel_sm_feature", height="430px")

    _spashiny_ctx.raster_panel_sm_feature_img_ui = raster_panel_sm_feature_img_ui

    @_spashiny_ctx.output
    @_spashiny_ctx.render.ui
    def raster_panel_sm_latent_img_ui():
        return _spashiny_ctx._alignment_panel_image_ui("raster_panel_sm_latent", height="430px")

    _spashiny_ctx.raster_panel_sm_latent_img_ui = raster_panel_sm_latent_img_ui

    @_spashiny_ctx.output
    @_spashiny_ctx.render.ui
    def raster_panel_st_image_img_ui():
        return _spashiny_ctx._alignment_panel_image_ui("raster_panel_st_image", height="430px")

    _spashiny_ctx.raster_panel_st_image_img_ui = raster_panel_st_image_img_ui

    @_spashiny_ctx.output
    @_spashiny_ctx.render.ui
    def raster_panel_st_latent_img_ui():
        return _spashiny_ctx._alignment_panel_image_ui("raster_panel_st_latent", height="430px")

    _spashiny_ctx.raster_panel_st_latent_img_ui = raster_panel_st_latent_img_ui

    @_spashiny_ctx.output
    @_spashiny_ctx.render.ui
    def spot_panel_st_latent_img_ui():
        return _spashiny_ctx._alignment_panel_image_ui("spot_panel_st_latent", height="420px")

    _spashiny_ctx.spot_panel_st_latent_img_ui = spot_panel_st_latent_img_ui

    @_spashiny_ctx.output
    @_spashiny_ctx.render.ui
    def spot_panel_sampled_img_ui():
        return _spashiny_ctx._alignment_panel_image_ui("spot_panel_sampled", height="420px")

    _spashiny_ctx.spot_panel_sampled_img_ui = spot_panel_sampled_img_ui

    @_spashiny_ctx.output
    @_spashiny_ctx.render.ui
    def spot_panel_mask_img_ui():
        return _spashiny_ctx._alignment_panel_image_ui("spot_panel_mask", height="420px")

    _spashiny_ctx.spot_panel_mask_img_ui = spot_panel_mask_img_ui
    _spashiny_ctx.ALIGNMENT_PANEL_IMAGE_IDS = [
        "raster_panel_sm_feature",
        "raster_panel_sm_latent",
        "raster_panel_st_image",
        "raster_panel_st_latent",
        "spot_panel_st_latent",
        "spot_panel_sampled",
        "spot_panel_mask",
    ]

    def _alignment_panel_image_payload():
        images = {}
        for plot_id in _spashiny_ctx.ALIGNMENT_PANEL_IMAGE_IDS:
            url, message = _spashiny_ctx._alignment_panel_image_source(plot_id)
            images[plot_id] = {
                "url": url or "",
                "message": message or "",
                "alt": _spashiny_ctx._alignment_color_title(plot_id),
            }
        return images

    _spashiny_ctx._alignment_panel_image_payload = _alignment_panel_image_payload

    async def _send_alignment_image_update():
        await _spashiny_ctx.session.send_custom_message(
            "alignment_image_update", {"images": _spashiny_ctx._alignment_panel_image_payload()}
        )

    _spashiny_ctx._send_alignment_image_update = _send_alignment_image_update

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.alignment_image_refresh_request)
    async def _on_alignment_image_refresh_request():
        await _spashiny_ctx._send_alignment_image_update()

    _spashiny_ctx._on_alignment_image_refresh_request = _on_alignment_image_refresh_request

    @_spashiny_ctx.reactive.Effect
    async def _poll_alignment_worker_image_slots():
        try:
            if _spashiny_ctx.current_module.get() != "ST-SM model":
                return
            has_running = False
            job_ids = [_spashiny_ctx.alignment_step4_job_id.get()]
            job_ids.extend((_spashiny_ctx.alignment_color_panel_job_ids.get() or {}).values())
            for job_id in [item for item in job_ids if item]:
                status = _spashiny_ctx._alignment_status(job_id).get("status")
                if status in {"queued", "running"}:
                    has_running = True
                    break
            await _spashiny_ctx._send_alignment_image_update()
            if has_running:
                _spashiny_ctx.reactive.invalidate_later(2)
        except Exception as exc:
            _spashiny_ctx.log(f"Alignment image refresh failed: {type(exc).__name__}: {exc}")
            raise

    _spashiny_ctx._poll_alignment_worker_image_slots = _poll_alignment_worker_image_slots

    def _submit_alignment_worker_color_rerender(plot_id, color_parameters):
        plot_id = str(plot_id or "")
        cfg = _spashiny_ctx.ALIGNMENT_WORKER_COLOR_PLOTS.get(plot_id)
        if not cfg:
            raise RuntimeError(f"Unsupported Alignment color plot: {plot_id}")
        color_parameters = dict(color_parameters or {})
        workflow = str(cfg.get("workflow") or "")
        if workflow == "manual_preview":
            kind = str(cfg.get("preview_kind") or "overlay")
            job_id, _ = _spashiny_ctx._submit_manual_preview(
                kind, color_parameters=color_parameters, color_plot_id=plot_id
            )
            if kind == "initial":
                _spashiny_ctx.initial_preview_img_val.set(None)
                _spashiny_ctx.initial_preview_job_id.set(job_id)
            elif kind == "side":
                _spashiny_ctx.side_preview_img_val.set(None)
                _spashiny_ctx.side_preview_job_id.set(job_id)
            else:
                _spashiny_ctx.manual_preview_img_val.set(None)
                _spashiny_ctx.manual_preview_job_id.set(job_id)
            _spashiny_ctx._clear_alignment_panel_image_url_cache(plot_id)
            _spashiny_ctx.log(
                f"Alignment color worker submitted for {_spashiny_ctx._alignment_color_title(plot_id)}: {job_id}"
            )
            _spashiny_ctx.ui.notification_show(
                f"Color render submitted for {_spashiny_ctx._alignment_color_title(plot_id)}.",
                type="message",
                duration=6,
            )
            return job_id
        if workflow != "render_color_panel":
            raise RuntimeError(f"Unsupported Alignment color workflow: {workflow}")
        if not _spashiny_ctx._sync_alignment_render_results():
            raise RuntimeError("Please generate Step4 plots before adjusting colors.")
        source_job_id = (
            _spashiny_ctx.alignment_step4_job_id.get()
            or _spashiny_ctx._latest_alignment_job("render")
        )
        if not source_job_id:
            raise RuntimeError("Step4 source render job was not found.")
        source_manifest = _spashiny_ctx._completed_alignment_manifest(source_job_id)
        if source_manifest.get("status") != "completed":
            raise RuntimeError("Step4 source render job is not completed.")
        source_output_dir = _spashiny_ctx._alignment_output_dir(source_job_id)
        job_id = f"alignment_color_{plot_id}_{_spashiny_ctx.time.strftime('%Y%m%d_%H%M%S')}_{_spashiny_globals.uuid.uuid4().hex[:8]}"
        job_dir = _spashiny_ctx._alignment_jobs_root() / job_id
        output_dir = _spashiny_ctx._alignment_result_root(job_id)
        job = {
            "job_id": job_id,
            "task": "render_color_panel",
            "session_id": _spashiny_ctx._alignment_session_token(),
            "job_dir": str(job_dir),
            "output_dir": str(output_dir),
            "log_file": str(_spashiny_ctx._alignment_logs_root() / f"{job_id}.log"),
            "source_render_job_id": source_job_id,
            "source_output_dir": str(source_output_dir),
            "plot_id": plot_id,
            "plot_key": str(cfg.get("plot_key") or plot_id),
            "plot_name": str(cfg.get("title") or _spashiny_globals.humanize_plot_id(plot_id)),
            "group": str(cfg.get("group") or ""),
            "panel": str(cfg.get("panel") or ""),
            "color_parameters": color_parameters,
        }
        _spashiny_ctx._launch_alignment_worker(job)
        color_jobs = dict(_spashiny_ctx.alignment_color_panel_job_ids.get() or {})
        color_jobs[plot_id] = job_id
        _spashiny_ctx.alignment_color_panel_job_ids.set(color_jobs)
        _spashiny_ctx._clear_alignment_panel_image_url_cache(plot_id)
        _spashiny_ctx.log(
            f"Alignment color worker submitted for {_spashiny_ctx._alignment_color_title(plot_id)}: {job_id}"
        )
        _spashiny_ctx.ui.notification_show(
            f"Color render submitted for {_spashiny_ctx._alignment_color_title(plot_id)}.",
            type="message",
            duration=6,
        )
        return job_id

    _spashiny_ctx._submit_alignment_worker_color_rerender = _submit_alignment_worker_color_rerender

    def _load_alignment_render_payloads():
        """Restore complete Step4 compute state only for an explicit downstream action.

        Display polling deliberately stays PNG/manifest-only.  This loader joins the
        separately persisted raster and random-spot payloads into the exact data
        mapping expected by the legacy Step5+ computation path.
        """
        job_id = _spashiny_ctx.alignment_step4_job_id.get() or _spashiny_ctx._latest_alignment_job(
            "render"
        )
        if not job_id:
            return False
        manifest = _spashiny_ctx._completed_alignment_manifest(job_id)
        if manifest.get("status") != "completed":
            return False
        result_dir = _spashiny_ctx._alignment_output_dir(job_id)
        try:
            import pickle

            raster_path = result_dir / "raster_result.pkl"
            spot_path = result_dir / "spot_result.pkl"
            sampling_path = result_dir / "step4_sampling_state.pkl"
            if not raster_path.is_file() or not spot_path.is_file():
                raise FileNotFoundError(
                    "Step4 raster or spot payload is missing from the completed worker result"
                )
            with raster_path.open("rb") as handle:
                raster_result = pickle.load(handle)
            with spot_path.open("rb") as handle:
                spot_result = pickle.load(handle)
            raster_payload = (
                raster_result.get("data", {}) if isinstance(raster_result, dict) else {}
            )
            spot_payload = spot_result.get("data", {}) if isinstance(spot_result, dict) else {}
            if not isinstance(raster_payload, dict) or not isinstance(spot_payload, dict):
                raise ValueError("Step4 worker payloads do not contain data mappings")
            sampling_payload = {}
            if sampling_path.is_file():
                with sampling_path.open("rb") as handle:
                    sampling_state = pickle.load(handle)
                if (
                    not isinstance(sampling_state, dict)
                    or sampling_state.get("schema") != "spashiny.alignment.step4_sampling_state"
                ):
                    raise ValueError("Step4 sampling state schema is invalid")
                sampling_payload = sampling_state.get("data", {})
                if not isinstance(sampling_payload, dict):
                    raise ValueError("Step4 sampling state data is invalid")
            else:
                sampling_payload = spot_payload
            required_sampling_keys = (
                "spot_coordinate",
                "spot_coordinate_edge",
                "pointsI_edge",
                "initial_scale",
            )
            missing_sampling_keys = [
                key for key in required_sampling_keys if sampling_payload.get(key) is None
            ]
            if missing_sampling_keys:
                raise ValueError(
                    "Step4 sampling state is incomplete: " + ", ".join(missing_sampling_keys)
                )
            complete_payload = dict(raster_payload)
            complete_payload.update({key: sampling_payload[key] for key in required_sampling_keys})
            _spashiny_ctx.raster_data.set({"data": complete_payload})
            _spashiny_ctx.spot_data.set(spot_result)
            _spashiny_ctx.log(
                "Step4 compute state restored from persistent worker result: "
                + ", ".join(required_sampling_keys)
            )
            return True
        except Exception as exc:
            _spashiny_ctx.log(f"Failed to load Step4 worker payloads for compute: {exc}")
            return False

    _spashiny_ctx._load_alignment_render_payloads = _load_alignment_render_payloads

    def _alignment_coordinate_metadata(value):
        arr = _spashiny_globals.np.asarray(value, dtype=_spashiny_globals.np.float32)
        if arr.ndim != 2 or arr.shape[1] < 2:
            raise ValueError(f"Alignment coordinates must be N x 2; got {arr.shape}")
        arr = _spashiny_globals.np.ascontiguousarray(arr[:, :2])
        finite = arr[_spashiny_globals.np.isfinite(arr).all(axis=1)]
        if finite.size == 0:
            raise ValueError("Alignment coordinates contain no finite rows")
        import hashlib

        return {
            "shape": [int(arr.shape[0]), int(arr.shape[1])],
            "dtype": str(arr.dtype),
            "x_range": [
                float(_spashiny_globals.np.min(finite[:, 0])),
                float(_spashiny_globals.np.max(finite[:, 0])),
            ],
            "y_range": [
                float(_spashiny_globals.np.min(finite[:, 1])),
                float(_spashiny_globals.np.max(finite[:, 1])),
            ],
            "sha256_f32": hashlib.sha256(arr.tobytes()).hexdigest(),
        }

    _spashiny_ctx._alignment_coordinate_metadata = _alignment_coordinate_metadata

    def _current_step5_job_id():
        workflow_id = _spashiny_ctx._current_alignment_workflow_id()
        state = _spashiny_ctx._read_alignment_workflow_state(workflow_id) if workflow_id else {}
        job_id = _spashiny_ctx.alignment_step5_job_id.get() or state.get("step5_job_id")
        if not job_id:
            return None
        job = _spashiny_ctx._alignment_job_payload(job_id)
        return job_id if job.get("workflow_id") == workflow_id else None

    _spashiny_ctx._current_step5_job_id = _current_step5_job_id

    def _load_alignment_fit_summary(job_id=None):
        """Load current-workflow-only compact Step5 coordinates for Step6/Step7.

        This never selects a historical 'latest' fit.  Both the fit job and its
        result manifest must trace to the current workflow and current Step4.
        """
        workflow_id = _spashiny_ctx._current_alignment_workflow_id()
        if not workflow_id:
            return False
        state = _spashiny_ctx._read_alignment_workflow_state(workflow_id)
        job_id = job_id or _spashiny_ctx._current_step5_job_id()
        if not job_id:
            return False
        job = _spashiny_ctx._alignment_job_payload(job_id)
        if job.get("workflow_id") != workflow_id:
            _spashiny_ctx.log("Rejected Step5 result from a different Alignment workflow.")
            return False
        expected_render = state.get("step4_job_id") or _spashiny_ctx.alignment_step4_job_id.get()
        if not expected_render or str(job.get("source_render_job_id") or "") != str(
            expected_render
        ):
            _spashiny_ctx.log(
                "Rejected Step5 result whose Step4 lineage does not match the current Alignment workflow."
            )
            return False
        status = _spashiny_ctx._alignment_status(job_id)
        if status.get("status") in {"queued", "running"}:
            try:
                _spashiny_ctx.reactive.invalidate_later(2)
            except Exception:
                pass
            return False
        if status.get("status") != "completed":
            return False
        result_dir = _spashiny_ctx._alignment_output_dir(job_id)
        try:
            summary_path = result_dir / "alignment_fit_summary.json"
            if not summary_path.is_file():
                raise FileNotFoundError("Step5 summary is missing from the completed worker result")
            summary = _spashiny_ctx.json.loads(summary_path.read_text(encoding="utf-8"))
            if summary.get("workflow_id") != workflow_id:
                raise ValueError("Step5 summary belongs to a different Alignment workflow")
            if str(summary.get("source_render_job_id") or "") != str(expected_render):
                raise ValueError("Step5 summary does not trace to the current Step4 job")
            points_path = result_dir / str(summary.get("points_path") or "aligned_points.npy")
            if not points_path.is_file():
                raise FileNotFoundError("Step5 aligned coordinate artifact is missing")
            points = _spashiny_globals.np.load(points_path, allow_pickle=False)
            if points.ndim != 2 or points.shape[1] < 2:
                raise ValueError(f"Step5 aligned coordinate shape is invalid: {points.shape}")
            st_points_path = result_dir / str(summary.get("st_points_path") or "")
            if not st_points_path.is_file():
                raise FileNotFoundError("Step5 ST raster coordinate artifact is missing")
            st_points = _spashiny_globals.np.load(st_points_path, allow_pickle=False)
            if st_points.ndim != 2 or st_points.shape[1] < 2:
                raise ValueError(f"Step5 ST raster coordinate shape is invalid: {st_points.shape}")
            best_key = str(summary.get("best_key") or "fit")
            final_loss = summary.get("final_loss")
            compact_result = {
                best_key: {
                    "pointsIt": _spashiny_globals.np.asarray(
                        points[:, :2], dtype=_spashiny_globals.np.float32
                    ),
                    "loss": [] if final_loss is None else [float(final_loss)],
                }
            }
            _spashiny_ctx.result_dict_val.set(compact_result)
            _spashiny_ctx.alignment_step5_job_id.set(job_id)
            _spashiny_ctx.alignment_step5_coordinate_context.set(
                {
                    "job_id": job_id,
                    "workflow_id": workflow_id,
                    "source_render_job_id": expected_render,
                    "coordinate_space": str(summary.get("coordinate_space") or "step4_raster"),
                    "aligned_points": _spashiny_globals.np.asarray(
                        points[:, :2], dtype=_spashiny_globals.np.float32
                    ),
                    "st_raster_points": _spashiny_globals.np.asarray(
                        st_points[:, :2], dtype=_spashiny_globals.np.float32
                    ),
                    "aligned_metadata": _spashiny_ctx._alignment_coordinate_metadata(points),
                    "st_raster_metadata": _spashiny_ctx._alignment_coordinate_metadata(st_points),
                    "summary": summary,
                }
            )
            _spashiny_ctx.log(
                f"Step5 compact alignment result restored from current workflow worker: {job_id}; best key: {best_key}"
            )
            return True
        except Exception as exc:
            _spashiny_ctx.log(f"Failed to load Step5 worker summary: {exc}")
            return False

    _spashiny_ctx._load_alignment_fit_summary = _load_alignment_fit_summary

    def _alignment_bundle_manifest(config, files, *, source):
        return {
            "schema": _spashiny_ctx.ALIGNMENT_VAE_BUNDLE_SCHEMA,
            "version": _spashiny_ctx.ALIGNMENT_VAE_BUNDLE_VERSION,
            "source": source,
            "created_at": _spashiny_ctx.time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "model_class": "spatialmeta.model._alignment_model.AlignmentVAE",
            "files": files,
            "training": config.get("training", {}),
            "model_config": config.get("model_config", {}),
            "data_signature": config.get("data_signature", {}),
        }

    _spashiny_ctx._alignment_bundle_manifest = _alignment_bundle_manifest

    def _normalize_alignment_bundle_config(config, *, source):
        config = dict(config or {})
        config.setdefault("schema", _spashiny_ctx.ALIGNMENT_VAE_BUNDLE_SCHEMA)
        config.setdefault("version", _spashiny_ctx.ALIGNMENT_VAE_BUNDLE_VERSION)
        config.setdefault("model_class", "spatialmeta.model._alignment_model.AlignmentVAE")
        config.setdefault("exported_at", _spashiny_ctx.time.strftime("%Y-%m-%dT%H:%M:%S%z"))
        config.setdefault("training", {})
        config["training"].setdefault("ready_to_skip_step3", True)
        config.setdefault("bundle_source", source)
        return config

    _spashiny_ctx._normalize_alignment_bundle_config = _normalize_alignment_bundle_config

    def _persist_imported_alignment_bundle(config, state_bytes, model):
        job_id = f"alignment_train_imported_{_spashiny_ctx.time.strftime('%Y%m%d_%H%M%S')}_{_spashiny_globals.uuid.uuid4().hex[:8]}"
        job_dir = _spashiny_ctx._alignment_jobs_root() / job_id
        output_dir = _spashiny_ctx._alignment_result_root(job_id)
        checkpoint_dir = output_dir / "checkpoints"
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        st_path, sm_path = _spashiny_ctx._write_alignment_inputs(job_dir, model)
        config = _spashiny_ctx._normalize_alignment_bundle_config(config, source="imported_bundle")
        state_path = checkpoint_dir / "alignment_vae_state_dict.pt"
        state_path.write_bytes(state_bytes)
        config_path = checkpoint_dir / "alignment_model_config.json"
        config_path.write_text(
            _spashiny_ctx.json.dumps(config, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        loss_path = checkpoint_dir / "alignment_vae_loss_history.json"
        loss_history = config.get("training", {}).get("loss_history", [])
        loss_path.write_text(
            _spashiny_ctx.json.dumps({"loss_history": loss_history}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        status_path = job_dir / "status.json"
        job = {
            "job_id": job_id,
            "task": "train",
            "session_id": _spashiny_ctx._alignment_session_token(),
            "job_dir": str(job_dir),
            "output_dir": str(output_dir),
            "log_file": str(_spashiny_ctx._alignment_logs_root() / f"{job_id}.log"),
            "status_file": str(status_path),
            "st_h5ad": str(st_path),
            "sm_h5ad": str(sm_path),
            "max_epoch": int(
                config.get("training", {}).get("trained_epochs") or len(loss_history) or 0
            ),
            "device": _spashiny_ctx._alignment_vae_device(),
            "model_config": dict(config.get("model_config") or {}),
            "imported_model_bundle": True,
        }
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "job.json").write_text(
            _spashiny_ctx.json.dumps(job, ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        status_path.write_text(
            _spashiny_ctx.json.dumps(
                {
                    "job_id": job_id,
                    "task": "train",
                    "status": "completed",
                    "current_step": "imported model bundle",
                    "progress": 100.0,
                    "result_manifest": str(output_dir / "result_manifest.json"),
                },
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        manifest = {
            "job_id": job_id,
            "task": "train",
            "status": "completed",
            "imported_model_bundle": True,
            "device": _spashiny_ctx._alignment_vae_device(),
            "state_dict": str(state_path),
            "config": str(config_path),
            "loss_history": str(loss_path),
            "downloads": [
                {
                    "name": "AlignmentVAE state dict",
                    "path": state_path.relative_to(output_dir).as_posix(),
                },
                {
                    "name": "AlignmentVAE config",
                    "path": config_path.relative_to(output_dir).as_posix(),
                },
                {
                    "name": "AlignmentVAE loss history",
                    "path": loss_path.relative_to(output_dir).as_posix(),
                },
            ],
            "plots": [],
            "finished_at": _spashiny_ctx.time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        (output_dir / "result_manifest.json").write_text(
            _spashiny_ctx.json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return job_id

    _spashiny_ctx._persist_imported_alignment_bundle = _persist_imported_alignment_bundle

    @_spashiny_ctx.render.download(
        filename=lambda: f"spashiny_alignment_vae_model_{_spashiny_ctx.time.strftime('%Y%m%d_%H%M%S')}.zip"
    )
    def download_alignment_vae_model_bundle():
        model = _spashiny_ctx.alignment_model.get()
        if model is None:
            train_job_id = (
                _spashiny_ctx.alignment_step3_job_id.get()
                or _spashiny_ctx._latest_alignment_job("train")
            )
            manifest = _spashiny_ctx._completed_alignment_manifest(train_job_id)
            if manifest.get("status") == "completed":
                tmp_dir = _spashiny_ctx.tempfile.mkdtemp(prefix="spashiny_alignment_vae_bundle_")
                zip_path = _spashiny_globals.os.path.join(
                    tmp_dir, "spashiny_alignment_vae_model.zip"
                )
                try:
                    config_data = _spashiny_ctx.json.loads(
                        _spashiny_ctx.Path(manifest["config"]).read_text(encoding="utf-8")
                    )
                    config_data = _spashiny_ctx._normalize_alignment_bundle_config(
                        config_data, source=f"worker_train_job:{train_job_id}"
                    )
                    config_path = _spashiny_ctx.Path(tmp_dir) / "alignment_model_config.json"
                    config_path.write_text(
                        _spashiny_ctx.json.dumps(
                            config_data, ensure_ascii=False, indent=2, default=str
                        ),
                        encoding="utf-8",
                    )
                    bundle_manifest = _spashiny_ctx._alignment_bundle_manifest(
                        config_data,
                        [
                            {"path": "alignment_model_config.json", "role": "config"},
                            {"path": "alignment_vae_state_dict.pt", "role": "state_dict"},
                            {"path": "alignment_vae_loss_history.json", "role": "loss_history"},
                        ],
                        source=f"worker_train_job:{train_job_id}",
                    )
                    with _spashiny_ctx.zipfile.ZipFile(
                        zip_path, "w", _spashiny_ctx.zipfile.ZIP_DEFLATED
                    ) as zf:
                        zf.write(config_path, arcname="alignment_model_config.json")
                        zf.write(manifest["state_dict"], arcname="alignment_vae_state_dict.pt")
                        zf.write(
                            manifest["loss_history"], arcname="alignment_vae_loss_history.json"
                        )
                        zf.writestr(
                            "alignment_bundle_manifest.json",
                            _spashiny_ctx.json.dumps(
                                bundle_manifest, ensure_ascii=False, indent=2, sort_keys=True
                            ),
                        )
                    with open(zip_path, "rb") as f:
                        while True:
                            chunk = f.read(1024 * 1024)
                            if not chunk:
                                break
                            yield chunk
                finally:
                    _spashiny_ctx.shutil.rmtree(tmp_dir, ignore_errors=True)
                return
            _spashiny_ctx.ui.notification_show(
                "No automatic alignment VAE model is available. Please run Step 2 and Step 3 first.",
                type="warning",
                duration=8,
            )
            return
        tmp_dir = _spashiny_ctx.tempfile.mkdtemp(prefix="spashiny_alignment_vae_")
        zip_path = _spashiny_globals.os.path.join(tmp_dir, "spashiny_alignment_vae_model.zip")
        try:
            config = _spashiny_ctx._build_alignment_vae_config(model)
            config_path = _spashiny_globals.os.path.join(tmp_dir, "alignment_model_config.json")
            loss_path = _spashiny_globals.os.path.join(tmp_dir, "alignment_vae_loss_history.json")
            state_path = _spashiny_globals.os.path.join(tmp_dir, "alignment_vae_state_dict.pt")
            with open(config_path, "w", encoding="utf-8") as f:
                _spashiny_ctx.json.dump(config, f, indent=2, ensure_ascii=False, default=str)
            with open(loss_path, "w", encoding="utf-8") as f:
                _spashiny_ctx.json.dump(
                    config["training"]["loss_history"], f, indent=2, ensure_ascii=False
                )
            state_dict = getattr(model, "trained_state_dict", None)
            if state_dict is None:
                state_dict = model.state_dict()
            _spashiny_globals.torch.save(state_dict, state_path)
            with _spashiny_ctx.zipfile.ZipFile(
                zip_path, "w", _spashiny_ctx.zipfile.ZIP_DEFLATED
            ) as zf:
                zf.write(config_path, arcname="alignment_model_config.json")
                zf.write(loss_path, arcname="alignment_vae_loss_history.json")
                zf.write(state_path, arcname="alignment_vae_state_dict.pt")
                zf.writestr(
                    "alignment_bundle_manifest.json",
                    _spashiny_ctx.json.dumps(
                        _spashiny_ctx._alignment_bundle_manifest(
                            config,
                            [
                                {"path": "alignment_model_config.json", "role": "config"},
                                {"path": "alignment_vae_state_dict.pt", "role": "state_dict"},
                                {"path": "alignment_vae_loss_history.json", "role": "loss_history"},
                            ],
                            source="web_memory_model",
                        ),
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    ),
                )
            with open(zip_path, "rb") as f:
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    yield chunk
        finally:
            _spashiny_ctx.shutil.rmtree(tmp_dir, ignore_errors=True)

    _spashiny_ctx.download_alignment_vae_model_bundle = download_alignment_vae_model_bundle

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.import_alignment_vae_model)
    def import_alignment_vae_model():
        file_info = _spashiny_ctx.input.import_alignment_vae_model_file()
        if not file_info:
            _spashiny_ctx.ui.notification_show(
                "Please choose an automatic alignment VAE model .zip file.",
                type="warning",
                duration=8,
            )
            return
        try:
            file_entry = file_info[0]
            file_name = str(file_entry.get("name", ""))
            data_path = file_entry.get("datapath")
            if not file_name.lower().endswith(".zip") or not data_path:
                raise ValueError("Imported file content or format is invalid")
            with _spashiny_ctx.zipfile.ZipFile(data_path, "r") as zf:
                names = set(zf.namelist())
                required = {"alignment_model_config.json", "alignment_vae_state_dict.pt"}
                if not required.issubset(names):
                    raise ValueError("Imported file content or format is invalid")
                config = _spashiny_ctx.json.loads(
                    zf.read("alignment_model_config.json").decode("utf-8")
                )
                state_bytes = zf.read("alignment_vae_state_dict.pt")
            if (
                config.get("schema") != _spashiny_ctx.ALIGNMENT_VAE_BUNDLE_SCHEMA
                or config.get("version") != _spashiny_ctx.ALIGNMENT_VAE_BUNDLE_VERSION
            ):
                raise ValueError("Imported file content or format is invalid")
            adata_st_obj = _spashiny_ctx.adata_st.get()
            adata_sm_obj = (
                _spashiny_ctx.adata_sm_transformed.get() or _spashiny_ctx.adata_sm_norm.get()
            )
            if adata_st_obj is None or adata_sm_obj is None:
                _spashiny_ctx.ui.notification_show(
                    "Please complete Automatic Alignment Step 1 data preparation before importing the model.",
                    type="warning",
                    duration=10,
                )
                return
            expected = config.get("data_signature", {})
            if expected.get("st_shape") and list(adata_st_obj.shape) != list(expected["st_shape"]):
                raise ValueError(
                    "Imported file content or format is invalid: ST data shape does not match this model"
                )
            if expected.get("sm_shape") and list(adata_sm_obj.shape) != list(expected["sm_shape"]):
                raise ValueError(
                    "Imported file content or format is invalid: SM data shape does not match this model"
                )
            model_cfg = config.get("model_config", {})
            from spatialmeta.model._alignment_model import AlignmentVAE

            device = _spashiny_ctx._alignment_vae_device()
            model = AlignmentVAE(
                adata_st=adata_st_obj,
                adata_sm=adata_sm_obj,
                hidden_stacks=model_cfg.get("hidden_stacks", [128]),
                n_latent=int(model_cfg.get("n_latent", 10)),
                device=device,
                reconstruction_method_st=model_cfg.get("reconstruction_method_st", "zinb"),
                reconstruction_method_sm=model_cfg.get("reconstruction_method_sm", "g"),
                encode_libsize=bool(model_cfg.get("encode_libsize", False)),
            )
            import io

            state_dict = _spashiny_ctx._load_alignment_state_dict(io.BytesIO(state_bytes), device)
            model.load_state_dict(state_dict, strict=True)
            model.trained_state_dict = state_dict
            model.eval()
            _spashiny_ctx.alignment_model.set(model)
            _spashiny_ctx.loss_history_val.set(config.get("training", {}).get("loss_history", []))
            imported_job_id = _spashiny_ctx._persist_imported_alignment_bundle(
                config, state_bytes, model
            )
            _spashiny_ctx.alignment_step3_job_id.set(imported_job_id)
            _spashiny_ctx.alignment_step4_job_id.set(None)
            _spashiny_ctx.alignment_step5_job_id.set(None)
            _spashiny_ctx.raster_data.set(None)
            _spashiny_ctx.result_dict_val.set(None)
            _spashiny_ctx.alignment_result.set(None)
            _spashiny_ctx.log(
                f"Imported automatic alignment VAE model bundle. Step 3 training is skipped. Imported job: {imported_job_id}"
            )
            _spashiny_ctx.ui.notification_show(
                "Automatic alignment VAE model imported. Step 3 training has been skipped.",
                type="message",
                duration=8,
            )
        except Exception as exc:
            msg = str(exc)
            if "Imported file content or format is invalid" not in msg:
                msg = f"Imported file content or format is invalid: {msg}"
            _spashiny_ctx.log(f"Automatic alignment VAE model import failed: {msg}")
            _spashiny_ctx.ui.notification_show(msg, type="error", duration=10)

    _spashiny_ctx.import_alignment_vae_model = import_alignment_vae_model

    def normalize_and_align_coords(adata_st, adata_sm, spatial_key="spatial"):
        from cloud.coordinate_guards import normalized_xy

        st_coords = adata_st.obsm[spatial_key]
        sm_coords = adata_sm.obsm[spatial_key]
        st_norm, _ = normalized_xy(st_coords)
        adata_st.obsm["spatial_normalized"] = st_norm
        if "spashiny_sm_coordinate_input" in adata_sm.uns:
            from cloud.sm_coordinate_policy import finalize_sm_coordinates

            finalize_sm_coordinates(adata_sm)
        else:
            sm_norm, _ = normalized_xy(sm_coords)
            adata_sm.obsm["spatial_normalized"] = sm_norm
        st_range = _spashiny_globals.np.ptp(st_coords, axis=0).mean()
        sm_range = _spashiny_globals.np.ptp(sm_coords, axis=0).mean()
        initial_scale = st_range / sm_range if sm_range > 0 else 1.0
        return (adata_st, adata_sm, float(initial_scale))

    _spashiny_ctx.normalize_and_align_coords = normalize_and_align_coords

    def to_tensor_2d(x, device):
        arr = _spashiny_globals.np.array(x, dtype=_spashiny_globals.np.float32)
        if arr.ndim == 1:
            arr = arr[:, None]
        if arr.size == 0:
            return _spashiny_globals.torch.zeros(
                (0, 2), dtype=_spashiny_globals.torch.float32, device=device
            )
        if arr.ndim == 2 and arr.shape[1] > 2:
            arr = arr[:, :2]
        if arr.ndim == 2 and arr.shape[1] == 1:
            arr = _spashiny_globals.np.concatenate(
                [
                    arr,
                    _spashiny_globals.np.zeros(
                        (arr.shape[0], 1), dtype=_spashiny_globals.np.float32
                    ),
                ],
                axis=1,
            )
        return _spashiny_globals.torch.tensor(
            arr, dtype=_spashiny_globals.torch.float32, device=device
        )

    _spashiny_ctx.to_tensor_2d = to_tensor_2d

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.align_step1_normalize)
    @_spashiny_ctx._one_stop_action("step1")
    def align_step1_normalize():
        _spashiny_ctx._prepare_confirmed_alignment_coordinates()

    _spashiny_ctx.align_step1_normalize = align_step1_normalize

    def _prepare_confirmed_alignment_coordinates():
        if not _spashiny_ctx._start_alignment_workflow_modal(
            "step1", "Loading the confirmed manual coordinates without reapplying the transform..."
        ):
            return
        step_succeeded = False
        step_error = None
        try:
            workflow_id = _spashiny_ctx._current_alignment_workflow_id()
            if not workflow_id:
                raise RuntimeError("Start ST-SM Alignment Preprocessing first.")
            adata_sm_obj, manual_metadata = _spashiny_ctx._restore_manual_transform_for_automatic()
            from stsm_data_metadata import normalize_alignment_coordinates

            definition = normalize_alignment_coordinates(adata_sm_obj, modality="SM")
            adata_sm_obj.uns["spashiny_alignment_normalization"] = {
                "source_key": "spatial",
                "normalized_key": "spatial_normalized",
                "origin": _spashiny_globals.np.repeat(definition["offset_scalar"], 2),
                "isotropic_scale": definition["scale_factor"],
                "normalization_version": definition["normalization_version"],
                "native_model_input_key": "spatial",
                "source_coordinates_unchanged": True,
            }
            _spashiny_ctx.adata_sm_transformed.set(adata_sm_obj)
            _spashiny_ctx.adata_sm_norm.set(adata_sm_obj)
            _spashiny_ctx.adata_st_norm.set(_spashiny_ctx.adata_st.get())
            _spashiny_ctx._update_alignment_workflow_state(
                step1_completed_at=_spashiny_ctx.time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                step1_status="completed",
                auto_alignment_coordinate_source="PREALIGNED_SM",
                auto_alignment_input_coordinate_key="spatial",
                manual_transform_job_id=_spashiny_ctx.manual_transform_job_id.get(),
                manual_transform_metadata=manual_metadata,
                step1_sm_coordinate_metadata=_spashiny_ctx._alignment_coordinate_metadata(
                    adata_sm_obj.obsm["spatial"]
                ),
            )
            _spashiny_ctx.log(
                "SM 2D normalization metadata saved with aspect ratio preserved; native model uses unchanged manual-prealigned spatial coordinates."
            )
            _spashiny_ctx.log(
                "Step1 coordinate source: PREALIGNED_SM (current manual worker artifact)."
            )
            step_succeeded = True
        except Exception as e:
            step_error = e
            _spashiny_ctx.log(f"align_step1_normalize error: {e}")
        finally:
            if step_succeeded:
                _spashiny_ctx._complete_alignment_workflow_modal("step1")
            else:
                _spashiny_ctx._fail_alignment_workflow_modal(
                    "step1", step_error or "Coordinate normalization did not complete"
                )
        return step_succeeded

    _spashiny_ctx._prepare_confirmed_alignment_coordinates = (
        _prepare_confirmed_alignment_coordinates
    )

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.align_step2_create_model)
    def align_step2_create_model():
        if not _spashiny_ctx._start_alignment_workflow_modal(
            "step2", "Step 2 - Creating Alignment Model"
        ):
            return
        step_succeeded = False
        step_error = None
        from spatialmeta.model._alignment_model import AlignmentVAE

        try:
            workflow_id = _spashiny_ctx._current_alignment_workflow_id()
            state = _spashiny_ctx._read_alignment_workflow_state(workflow_id) if workflow_id else {}
            adata_st_obj = _spashiny_ctx.adata_st.get()
            adata_sm_obj = _spashiny_ctx.adata_sm_transformed.get()
            if (
                not workflow_id
                or not state.get("step1_completed_at")
                or adata_st_obj is None
                or (adata_sm_obj is None)
            ):
                _spashiny_ctx.log(
                    "Please run Step1 Normalize Coordinates after Apply Transformation before creating the model."
                )
                return
            n_latent = 10
            _spashiny_ctx.log("Creating AlignmentVAE with tutorial n_latent=10...")
            model = AlignmentVAE(
                adata_st=adata_st_obj,
                adata_sm=adata_sm_obj,
                n_latent=10,
                device="cuda:0" if _spashiny_globals.torch.cuda.is_available() else "cpu",
            )
            _spashiny_ctx.alignment_model.set(model)
            _spashiny_ctx._update_alignment_workflow_state(
                step2_created_at=_spashiny_ctx.time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                step2_status="completed",
                step2_sm_coordinate_metadata=_spashiny_ctx._alignment_coordinate_metadata(
                    adata_sm_obj.obsm["spatial"]
                ),
            )
            _spashiny_ctx.log("If training is needed, please trigger Step3 (Train VAE).")
            step_succeeded = True
        except Exception as e:
            step_error = e
            _spashiny_ctx.log(f"align_step2_create_model error: {e}")
        finally:
            if step_succeeded:
                _spashiny_ctx._complete_alignment_workflow_modal("step2")
            else:
                _spashiny_ctx._fail_alignment_workflow_modal(
                    "step2", step_error or "Alignment model creation did not complete"
                )

    _spashiny_ctx.align_step2_create_model = align_step2_create_model

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.align_step3_train_vae)
    @_spashiny_ctx._one_stop_action("step3")
    def align_step3_train_vae():
        if not _spashiny_ctx._start_alignment_workflow_modal(
            "step3", "Step 3 - Training VAE", defer_modal_until_job=True
        ):
            return
        max_epoch = _spashiny_globals.alignment_epochs()
        estimated_seconds = max_epoch * 9
        estimated_minutes = estimated_seconds // 60
        remaining_seconds = estimated_seconds % 60
        if estimated_minutes > 0:
            eta_text = f"{estimated_minutes} min {remaining_seconds} sec"
        else:
            eta_text = f"{estimated_seconds} sec"
        try:
            workflow_id = _spashiny_ctx._current_alignment_workflow_id()
            state = _spashiny_ctx._read_alignment_workflow_state(workflow_id) if workflow_id else {}
            model = _spashiny_ctx.alignment_model.get()
            if not workflow_id or not state.get("step2_created_at") or model is None:
                raise RuntimeError("Model has not been created. Please run Step2 first.")
            job_id = _spashiny_ctx._submit_alignment_train(model, max_epoch)
            _spashiny_ctx.alignment_step3_job_id.set(job_id)
            _spashiny_ctx.alignment_step4_job_id.set(None)
            _spashiny_ctx.alignment_step5_job_id.set(None)
            _spashiny_ctx.alignment_step5_coordinate_context.set(None)
            _spashiny_ctx.alignment_step6_result_id.set(None)
            _spashiny_ctx.raster_img_val.set(None)
            _spashiny_ctx.spot_fig_val.set(None)
            _spashiny_ctx.raster_panel_img_val.set({})
            _spashiny_ctx.spot_panel_img_val.set({})
            _spashiny_ctx._clear_alignment_panel_image_url_cache(
                *_spashiny_ctx.ALIGNMENT_PANEL_IMAGE_IDS
            )
            _spashiny_ctx._update_alignment_workflow_state(
                step3_job_id=job_id,
                step3_status="queued",
                step4_job_id=None,
                step5_job_id=None,
                step6_result_id=None,
            )
            _spashiny_ctx._bind_alignment_workflow_modal_job(
                "step3", job_id, details=f"epochs: {max_epoch}\nstatus: queued"
            )
            _spashiny_ctx.log(f"Alignment Step3 worker submitted: {job_id}")
            _spashiny_ctx.log(f"  epochs: {max_epoch}; estimated runtime: ~ {eta_text}")
            _spashiny_ctx.log(
                f"  status: {_spashiny_ctx._alignment_jobs_root() / job_id / 'status.json'}"
            )
            _spashiny_ctx.log(f"  log: {_spashiny_ctx._alignment_logs_root() / (job_id + '.log')}")
            _spashiny_ctx.ui.notification_show(
                f"Alignment Step3 submitted as worker job {job_id}. It will continue if the page refreshes.",
                type="message",
                duration=8,
            )
        except Exception as e:
            _spashiny_ctx.log(f"align_step3_train_vae error: {e}")
            _spashiny_ctx._fail_alignment_workflow_modal("step3", e)

    _spashiny_ctx.align_step3_train_vae = align_step3_train_vae
    _spashiny_ctx.raster_data = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.raster_fig_val = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.spot_fig_val = _spashiny_ctx.reactive.Value(None)

    def build_pretty_raster_figure(raster_result):
        import matplotlib.pyplot as plt
        import numpy as np
        from matplotlib.colors import LinearSegmentedColormap

        data = raster_result.get("data", {})
        I = data.get("I", None)
        J = data.get("J", None)
        G = data.get("G", None)
        z_sm = data.get("z_sm", None)
        x_sm = data.get("x_sm", None)
        y_sm = data.get("y_sm", None)
        if I is None or J is None or G is None:
            raise ValueError("Raster result is missing required keys: I / J / G")
        I_np = I.mean(0).detach().cpu().numpy() if hasattr(I, "detach") else np.array(I)
        J_np = J.mean(0).detach().cpu().numpy() if hasattr(J, "detach") else np.array(J)
        G_np = G.detach().cpu().numpy().mean(0) if hasattr(G, "detach") else np.array(G)
        if z_sm is not None:
            z_sm_np = z_sm.detach().cpu().numpy() if hasattr(z_sm, "detach") else np.array(z_sm)
        else:
            z_sm_np = None
        x_sm_np = (
            x_sm.detach().cpu().numpy()
            if hasattr(x_sm, "detach")
            else np.array(x_sm) if x_sm is not None else None
        )
        y_sm_np = (
            y_sm.detach().cpu().numpy()
            if hasattr(y_sm, "detach")
            else np.array(y_sm) if y_sm is not None else None
        )

        def normalize_img(arr):
            arr = arr.astype(float)
            arr = arr - np.nanmin(arr)
            maxv = np.nanmax(arr)
            if maxv > 0:
                arr = arr / maxv
            return arr

        I_np = normalize_img(I_np)
        J_np = normalize_img(J_np)
        G_np = normalize_img(G_np)
        sm_raster_cmap = LinearSegmentedColormap.from_list(
            "sm_raster_cmap", ["#9F66BE", "#379155", "#8de9ac", "#84d43e"]
        )
        tissue_cmap = LinearSegmentedColormap.from_list(
            "tissue_cmap", ["#fff8f4", "#f7d9cf", "#eab7a8", "#d89c8a", "#b87c70"]
        )
        st_latent_cmap = LinearSegmentedColormap.from_list(
            "st_latent_cmap", ["#7B2F92", "#b699db", "#d6c9e6", "#f9f4fa"]
        )
        fig, axes = plt.subplots(1, 4, figsize=(24, 5.8), dpi=220)
        axes = axes.flatten()
        fig.patch.set_facecolor("white")
        panel_titles = [
            "SM rasterized feature",
            "SM latent embedding",
            "ST spatial image",
            "ST latent feature",
        ]

        def style_axis(ax, title):
            ax.set_title(title, fontsize=10, fontweight="normal", pad=8, loc="left")
            ax.tick_params(axis="both", which="both", labelsize=8, length=2.5, width=0.7, pad=2)
            ax.locator_params(nbins=4)
            for spine in ax.spines.values():
                spine.set_linewidth(0.7)
                spine.set_edgecolor("#666666")

        def clean_colorbar(mappable, ax):
            cbar = fig.colorbar(mappable, ax=ax, fraction=0.05, pad=0.03, shrink=0.95)
            cbar.set_ticks([])
            cbar.outline.set_visible(False)
            for spine in cbar.ax.spines.values():
                spine.set_visible(False)
            return cbar

        im0 = axes[0].imshow(I_np, cmap=sm_raster_cmap, origin="upper")
        style_axis(axes[0], panel_titles[0])
        clean_colorbar(im0, axes[0])
        if z_sm_np is not None and x_sm_np is not None and (y_sm_np is not None):
            color_values = np.mean(z_sm_np, axis=1) if len(z_sm_np.shape) > 1 else z_sm_np
            color_values = normalize_img(color_values)
            sc1 = axes[1].scatter(
                x_sm_np,
                y_sm_np,
                c=color_values,
                s=4.2,
                cmap=sm_raster_cmap,
                alpha=0.95,
                linewidths=0,
                rasterized=True,
            )
            clean_colorbar(sc1, axes[1])
        else:
            axes[1].text(
                0.5, 0.5, "latent feature unavailable", ha="center", va="center", fontsize=8
            )
        style_axis(axes[1], panel_titles[1])
        axes[1].set_aspect("equal")
        axes[1].set_xlabel("SM x", fontsize=8)
        axes[1].set_ylabel("SM y", fontsize=8)
        im2 = _spashiny_globals.mark_source_image(
            axes[2].imshow(J_np, cmap=tissue_cmap, origin="upper")
        )
        style_axis(axes[2], panel_titles[2])
        clean_colorbar(im2, axes[2])
        im3 = axes[3].imshow(G_np, cmap=st_latent_cmap, origin="upper")
        style_axis(axes[3], panel_titles[3])
        clean_colorbar(im3, axes[3])
        raster_dx = data.get("raster_dx", None)
        raster_dx_label = f"{float(raster_dx):.3g}" if raster_dx is not None else "auto"
        n_sm = len(x_sm_np) if x_sm_np is not None else "NA"
        fig.suptitle(
            f"Auto Image Registration preview | raster dx={raster_dx_label} | SM spots={n_sm}",
            fontsize=11,
            y=0.985,
        )
        for ax in axes:
            ax.set_aspect("equal", adjustable="box")
        plt.subplots_adjust(left=0.035, right=0.985, top=0.82, bottom=0.14, wspace=0.28)
        return fig

    _spashiny_ctx.build_pretty_raster_figure = build_pretty_raster_figure

    def build_pretty_spot_figure(result_dict):
        import matplotlib.pyplot as plt
        import numpy as np
        from matplotlib.colors import LinearSegmentedColormap

        data = result_dict.get("data", {})
        J = data.get("J", None)
        maskJ = data.get("maskJ", None)
        z_st = data.get("z_st", None)
        scale = data.get("scale", None)
        spot_coordinate = data.get("spot_coordinate", None)
        if J is None or spot_coordinate is None:
            raise ValueError("Spot result is missing required keys: J / spot_coordinate")
        try:
            adata_st = _spashiny_ctx.alignment_model.get().adata_st
            st_spatial = adata_st.obsm["spatial"]
        except Exception:
            st_spatial = None
        J_np = J[0].detach().cpu().numpy() if hasattr(J, "detach") else np.array(J)[0]
        J_np = J_np.astype(float)
        J_np = J_np - np.nanmin(J_np)
        if np.nanmax(J_np) > 0:
            J_np = J_np / np.nanmax(J_np)
        if maskJ is not None:
            maskJ_np = maskJ.detach().cpu().numpy() if hasattr(maskJ, "detach") else np.array(maskJ)
        else:
            maskJ_np = None
        if z_st is not None:
            z_st_np = z_st.detach().cpu().numpy() if hasattr(z_st, "detach") else np.array(z_st)
            z_st_color = np.mean(z_st_np, axis=1) if len(z_st_np.shape) > 1 else z_st_np
        else:
            z_st_color = None
        spot_np = (
            spot_coordinate.detach().cpu().numpy()
            if hasattr(spot_coordinate, "detach")
            else np.array(spot_coordinate)
        )
        try:
            if maskJ_np is not None:
                tissue_mean = J_np[maskJ_np.T > 0].mean()
            else:
                tissue_mean = np.nanmean(J_np)
            Jtrue = (J_np <= tissue_mean * 0.65).astype(float)
        except Exception:
            Jtrue = None
        tissue_cmap = LinearSegmentedColormap.from_list(
            "tissue_cmap", ["#fff8f4", "#f7d9cf", "#eab7a8", "#d89c8a", "#b87c70"]
        )
        fig, axes = plt.subplots(1, 3, figsize=(18, 5.8), dpi=180)
        fig.patch.set_facecolor("white")
        titles = [
            "ST tissue and latent structure",
            "Randomly sampled inside-tissue spots",
            "Binary tissue mask",
        ]

        def style_axis(ax, title):
            ax.set_title(title, fontsize=9, fontweight="semibold", pad=8, loc="left")
            ax.tick_params(axis="both", which="both", labelsize=7, length=2, width=0.6, pad=2)
            ax.locator_params(nbins=4)
            for spine in ax.spines.values():
                spine.set_linewidth(0.7)
                spine.set_edgecolor("#666666")

        _spashiny_globals.mark_source_image(axes[0].imshow(J_np, cmap=tissue_cmap, origin="upper"))
        if st_spatial is not None and scale is not None and (z_st_color is not None):
            axes[0].scatter(
                st_spatial[:, 0] * scale,
                st_spatial[:, 1] * scale,
                s=5,
                lw=0,
                c=z_st_color,
                cmap="magma",
                alpha=0.78,
                marker="s",
                rasterized=True,
            )
        if maskJ_np is not None:
            axes[0].imshow(maskJ_np.T, alpha=0.12, cmap="Greys", origin="upper")
        style_axis(axes[0], titles[0])
        axes[0].set_aspect("equal", adjustable="box")
        axes[0].set_xlabel("image x", fontsize=8)
        axes[0].set_ylabel("image y", fontsize=8)
        _spashiny_globals.mark_source_image(axes[1].imshow(J_np, cmap=tissue_cmap, origin="upper"))
        axes[1].scatter(
            spot_np[:, 0],
            spot_np[:, 1],
            s=7,
            lw=0,
            c="#f8f8f8",
            alpha=0.96,
            edgecolors="none",
            rasterized=True,
        )
        style_axis(axes[1], titles[1])
        axes[1].set_aspect("equal", adjustable="box")
        axes[1].set_xlim(0, J_np.shape[1])
        axes[1].set_ylim(J_np.shape[0], 0)
        axes[1].set_xlabel("image x", fontsize=8)
        axes[1].set_ylabel("image y", fontsize=8)
        if Jtrue is not None:
            _spashiny_globals.mark_source_image(axes[2].imshow(Jtrue, cmap="gray", origin="upper"))
        else:
            _spashiny_globals.mark_source_image(axes[2].imshow(J_np, cmap="gray", origin="upper"))
        style_axis(axes[2], titles[2])
        axes[2].set_aspect("equal", adjustable="box")
        axes[2].set_xlabel("image x", fontsize=8)
        axes[2].set_ylabel("image y", fontsize=8)
        fig.suptitle(
            f"Inside-tissue spot sampling | generated spots={spot_np.shape[0]}",
            fontsize=11,
            y=0.985,
        )
        plt.subplots_adjust(left=0.035, right=0.99, top=0.86, bottom=0.1, wspace=0.18)
        return fig

    _spashiny_ctx.build_pretty_spot_figure = build_pretty_spot_figure
    _spashiny_ctx.raster_data = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.raster_img_val = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.spot_fig_val = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.raster_panel_img_val = _spashiny_ctx.reactive.Value({})
    _spashiny_ctx.spot_panel_img_val = _spashiny_ctx.reactive.Value({})
    _spashiny_ctx.spot_data = _spashiny_ctx.reactive.Value(None)

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.align_step4_get_raster)
    @_spashiny_ctx._one_stop_action("step4")
    def generate_both_plots():
        workflow_id = _spashiny_ctx._current_alignment_workflow_id()
        state = _spashiny_ctx._read_alignment_workflow_state(workflow_id) if workflow_id else {}
        existing_job_id = _spashiny_ctx.alignment_step4_job_id.get() or state.get("step4_job_id")
        if existing_job_id and _spashiny_ctx._alignment_status(existing_job_id).get("status") in {
            "queued",
            "running",
        }:
            _spashiny_ctx._bind_alignment_workflow_modal_job("step4", existing_job_id)
            return
        if not _spashiny_ctx._start_alignment_workflow_modal(
            "step4", "Step 4 - Generating Rasterized Features", defer_modal_until_job=True
        ):
            return
        try:
            if _spashiny_ctx._sync_alignment_render_results():
                _spashiny_ctx.log("Step4 worker result loaded from persistent result directory.")
                _spashiny_ctx._step_worker_completed(
                    "step4", _spashiny_ctx.alignment_step4_job_id.get() or existing_job_id
                )
                _spashiny_ctx._complete_alignment_workflow_modal(
                    "step4", job_id=_spashiny_ctx.alignment_step4_job_id.get() or existing_job_id
                )
                return
            running_job = _spashiny_ctx.alignment_step4_job_id.get()
            if running_job:
                status = _spashiny_ctx._alignment_status(running_job)
                if status.get("status") in {"queued", "running"}:
                    _spashiny_ctx.log(
                        f"Step4 worker is still {status.get('status')}: {running_job}"
                    )
                    _spashiny_ctx.log(f"  current step: {status.get('current_step') or ''}")
                    _spashiny_ctx._bind_alignment_workflow_modal_job("step4", running_job)
                    return
                if status.get("status") == "failed":
                    _spashiny_ctx.log(f"Step4 worker failed: {status.get('error')}")
                    _spashiny_ctx._fail_alignment_workflow_modal(
                        "step4", status.get("error") or "Step4 worker failed", job_id=running_job
                    )
                    return
            train_job_id = _spashiny_ctx.alignment_step3_job_id.get() or state.get("step3_job_id")
            if not train_job_id:
                raise RuntimeError("Please submit Step3 worker training before Step4.")
            train_job = _spashiny_ctx._alignment_job_payload(train_job_id)
            if train_job.get("workflow_id") != workflow_id:
                raise RuntimeError(
                    "Step3 model belongs to a different Alignment workflow. Run Step3 again."
                )
            train_status = _spashiny_ctx._alignment_status(train_job_id)
            if train_status.get("status") in {"queued", "running"}:
                _spashiny_ctx.log(
                    f"Step3 worker is still {train_status.get('status')}: {train_job_id}"
                )
                _spashiny_ctx.log(f"  current step: {train_status.get('current_step') or ''}")
                raise RuntimeError(
                    "Step3 worker is still running. Step4 can start after it completes."
                )
            if train_status.get("status") == "failed":
                raise RuntimeError(f"Step3 worker failed: {train_status.get('error')}")
            manifest = _spashiny_ctx._completed_alignment_manifest(train_job_id)
            if manifest.get("status") != "completed":
                raise RuntimeError(
                    "Step3 worker status file is completed, but result_manifest.json is not ready yet."
                )
            job_id = _spashiny_ctx._submit_alignment_render(train_job_id)
            _spashiny_ctx.alignment_step3_job_id.set(train_job_id)
            _spashiny_ctx.alignment_step4_job_id.set(job_id)
            _spashiny_ctx.alignment_step5_job_id.set(None)
            _spashiny_ctx.alignment_step5_coordinate_context.set(None)
            _spashiny_ctx.alignment_step6_result_id.set(None)
            _spashiny_ctx.raster_img_val.set(None)
            _spashiny_ctx.spot_fig_val.set(None)
            _spashiny_ctx.raster_panel_img_val.set({})
            _spashiny_ctx.spot_panel_img_val.set({})
            _spashiny_ctx._clear_alignment_panel_image_url_cache(
                *_spashiny_ctx.ALIGNMENT_PANEL_IMAGE_IDS
            )
            _spashiny_ctx._update_alignment_workflow_state(
                step3_job_id=train_job_id,
                step4_job_id=job_id,
                step4_status="queued",
                step5_job_id=None,
                step6_result_id=None,
                step7_status="not_started",
                step7_artifact_ready=False,
                step7_export_key=None,
                step7_artifact_path=None,
                step7_pdf_artifact_path=None,
            )
            _spashiny_ctx._bind_alignment_workflow_modal_job("step4", job_id)
            _spashiny_ctx.log(f"Alignment Step4 worker submitted: {job_id}")
            _spashiny_ctx.log(
                f"  status: {_spashiny_ctx._alignment_jobs_root() / job_id / 'status.json'}"
            )
            _spashiny_ctx.log(f"  log: {_spashiny_ctx._alignment_logs_root() / (job_id + '.log')}")
            _spashiny_ctx.ui.notification_show(
                f"Alignment Step4 submitted as worker job {job_id}. It will continue if the page refreshes.",
                type="message",
                duration=8,
            )
        except Exception as e:
            import traceback

            _spashiny_ctx.log(f"generate_both_plots error: {e}")
            _spashiny_ctx.log(traceback.format_exc())
            _spashiny_ctx._fail_alignment_workflow_modal("step4", e)

    _spashiny_ctx.generate_both_plots = generate_both_plots

    def empty_alignment_preview(message):
        fig, ax = _spashiny_globals.plt.subplots(figsize=(8, 3), dpi=140)
        ax.axis("off")
        ax.text(0.5, 0.5, message, ha="center", va="center", fontsize=11, color="#64748B")
        fig.tight_layout(pad=1.0)
        return fig

    _spashiny_ctx.empty_alignment_preview = empty_alignment_preview

    def image_path_to_figure(img_path, title=None, *, figsize=None, dpi=180):
        import matplotlib.image as mpimg

        img = mpimg.imread(img_path)
        if figsize is None:
            h, w = img.shape[:2]
            fig_w = 6.8 if h >= w else 9.0
            fig_h = max(3.2, min(7.2, fig_w * h / max(w, 1)))
            figsize = (fig_w, fig_h)
        fig, ax = _spashiny_globals.plt.subplots(figsize=figsize, dpi=dpi)
        ax.imshow(img)
        ax.axis("off")
        if title:
            ax.set_title(title, fontsize=12, fontweight="bold", pad=10)
        fig.tight_layout(pad=0.2)
        return fig

    _spashiny_ctx.image_path_to_figure = image_path_to_figure

    def _normalize_alignment_img(arr):
        arr = _spashiny_globals.np.asarray(arr, dtype=float)
        arr = arr - _spashiny_globals.np.nanmin(arr)
        maxv = _spashiny_globals.np.nanmax(arr)
        if maxv > 0:
            arr = arr / maxv
        return arr

    _spashiny_ctx._normalize_alignment_img = _normalize_alignment_img

    def _alignment_colormaps():
        from matplotlib.colors import LinearSegmentedColormap

        return {
            "sm_raster": LinearSegmentedColormap.from_list(
                "sm_raster_cmap", ["#9F66BE", "#379155", "#8de9ac", "#84d43e"]
            ),
            "tissue": LinearSegmentedColormap.from_list(
                "tissue_cmap", ["#fff8f4", "#f7d9cf", "#eab7a8", "#d89c8a", "#b87c70"]
            ),
            "st_latent": LinearSegmentedColormap.from_list(
                "st_latent_cmap", ["#7B2F92", "#b699db", "#d6c9e6", "#f9f4fa"]
            ),
        }

    _spashiny_ctx._alignment_colormaps = _alignment_colormaps

    def _clean_panel_colorbar(fig, mappable, ax):
        cbar = fig.colorbar(mappable, ax=ax, fraction=0.046, pad=0.03, shrink=0.88)
        cbar.set_ticks([])
        cbar.outline.set_visible(False)
        return cbar

    _spashiny_ctx._clean_panel_colorbar = _clean_panel_colorbar

    def _style_alignment_panel(ax, title):
        ax.set_title(title, fontsize=9, fontweight="normal", pad=6, loc="left")
        ax.tick_params(axis="both", which="both", labelsize=7, length=2.2, width=0.7, pad=1.5)
        ax.locator_params(nbins=4)
        for spine in ax.spines.values():
            spine.set_linewidth(0.7)
            spine.set_edgecolor("#666666")

    _spashiny_ctx._style_alignment_panel = _style_alignment_panel

    def build_raster_panel_figure(raster_result, panel):
        data = raster_result.get("data", {})
        I = data.get("I", None)
        J = data.get("J", None)
        G = data.get("G", None)
        z_sm = data.get("z_sm", None)
        x_sm = data.get("x_sm", None)
        y_sm = data.get("y_sm", None)
        if I is None or J is None or G is None:
            raise ValueError("Raster result is missing required keys: I / J / G")
        I_np = (
            I.mean(0).detach().cpu().numpy()
            if hasattr(I, "detach")
            else _spashiny_globals.np.array(I)
        )
        J_np = (
            J.mean(0).detach().cpu().numpy()
            if hasattr(J, "detach")
            else _spashiny_globals.np.array(J)
        )
        G_np = (
            G.detach().cpu().numpy().mean(0)
            if hasattr(G, "detach")
            else _spashiny_globals.np.array(G)
        )
        z_sm_np = (
            z_sm.detach().cpu().numpy()
            if hasattr(z_sm, "detach")
            else _spashiny_globals.np.array(z_sm) if z_sm is not None else None
        )
        x_sm_np = (
            x_sm.detach().cpu().numpy()
            if hasattr(x_sm, "detach")
            else _spashiny_globals.np.array(x_sm) if x_sm is not None else None
        )
        y_sm_np = (
            y_sm.detach().cpu().numpy()
            if hasattr(y_sm, "detach")
            else _spashiny_globals.np.array(y_sm) if y_sm is not None else None
        )
        I_np = _spashiny_ctx._normalize_alignment_img(I_np)
        J_np = _spashiny_ctx._normalize_alignment_img(J_np)
        G_np = _spashiny_ctx._normalize_alignment_img(G_np)
        cmaps = _spashiny_ctx._alignment_colormaps()
        fig, ax = _spashiny_globals.plt.subplots(figsize=(6.4, 5.0), dpi=180)
        fig.patch.set_facecolor("white")
        if panel == "sm_feature":
            im = ax.imshow(I_np, cmap=cmaps["sm_raster"], origin="upper")
            _spashiny_ctx._style_alignment_panel(ax, "SM rasterized feature")
            _spashiny_ctx._clean_panel_colorbar(fig, im, ax)
        elif panel == "sm_latent":
            if z_sm_np is not None and x_sm_np is not None and (y_sm_np is not None):
                values = (
                    _spashiny_globals.np.mean(z_sm_np, axis=1)
                    if len(z_sm_np.shape) > 1
                    else z_sm_np
                )
                values = _spashiny_ctx._normalize_alignment_img(values)
                sc = ax.scatter(
                    x_sm_np,
                    y_sm_np,
                    c=values,
                    s=5.2,
                    cmap=cmaps["sm_raster"],
                    alpha=0.95,
                    linewidths=0,
                    rasterized=True,
                )
                _spashiny_ctx._clean_panel_colorbar(fig, sc, ax)
            else:
                ax.text(
                    0.5, 0.5, "latent feature unavailable", ha="center", va="center", fontsize=9
                )
            _spashiny_ctx._style_alignment_panel(ax, "SM latent embedding")
            ax.set_xlabel("SM x", fontsize=8)
            ax.set_ylabel("SM y", fontsize=8)
        elif panel == "st_image":
            im = _spashiny_globals.mark_source_image(
                ax.imshow(J_np, cmap=cmaps["tissue"], origin="upper")
            )
            _spashiny_ctx._style_alignment_panel(ax, "ST spatial image")
            _spashiny_ctx._clean_panel_colorbar(fig, im, ax)
        elif panel == "st_latent":
            im = ax.imshow(G_np, cmap=cmaps["st_latent"], origin="upper")
            _spashiny_ctx._style_alignment_panel(ax, "ST latent feature")
            _spashiny_ctx._clean_panel_colorbar(fig, im, ax)
        else:
            raise ValueError(f"Unknown raster panel: {panel}")
        ax.set_aspect("equal", adjustable="box")
        fig.tight_layout(pad=1.0)
        return fig

    _spashiny_ctx.build_raster_panel_figure = build_raster_panel_figure

    def build_spot_panel_figure(result_dict, panel):
        data = result_dict.get("data", {})
        J = data.get("J", None)
        maskJ = data.get("maskJ", None)
        z_st = data.get("z_st", None)
        scale = data.get("scale", None)
        spot_coordinate = data.get("spot_coordinate", None)
        if J is None or spot_coordinate is None:
            raise ValueError("Spot result is missing required keys: J / spot_coordinate")
        try:
            adata_st_obj = _spashiny_ctx.alignment_model.get().adata_st
            st_spatial = adata_st_obj.obsm["spatial"]
        except Exception:
            st_spatial = None
        J_np = (
            J[0].detach().cpu().numpy()
            if hasattr(J, "detach")
            else _spashiny_globals.np.array(J)[0]
        )
        J_np = _spashiny_ctx._normalize_alignment_img(J_np)
        maskJ_np = (
            maskJ.detach().cpu().numpy()
            if hasattr(maskJ, "detach")
            else _spashiny_globals.np.array(maskJ) if maskJ is not None else None
        )
        if z_st is not None:
            z_st_np = (
                z_st.detach().cpu().numpy()
                if hasattr(z_st, "detach")
                else _spashiny_globals.np.array(z_st)
            )
            z_st_color = (
                _spashiny_globals.np.mean(z_st_np, axis=1) if len(z_st_np.shape) > 1 else z_st_np
            )
        else:
            z_st_color = None
        spot_np = (
            spot_coordinate.detach().cpu().numpy()
            if hasattr(spot_coordinate, "detach")
            else _spashiny_globals.np.array(spot_coordinate)
        )
        try:
            tissue_mean = (
                J_np[maskJ_np.T > 0].mean()
                if maskJ_np is not None
                else _spashiny_globals.np.nanmean(J_np)
            )
            Jtrue = (J_np <= tissue_mean * 0.65).astype(float)
        except Exception:
            Jtrue = None
        cmaps = _spashiny_ctx._alignment_colormaps()
        fig, ax = _spashiny_globals.plt.subplots(figsize=(6.0, 5.2), dpi=180)
        fig.patch.set_facecolor("white")
        if panel == "st_latent":
            _spashiny_globals.mark_source_image(
                ax.imshow(J_np, cmap=cmaps["tissue"], origin="upper")
            )
            if st_spatial is not None and scale is not None and (z_st_color is not None):
                ax.scatter(
                    st_spatial[:, 0] * scale,
                    st_spatial[:, 1] * scale,
                    s=5,
                    lw=0,
                    c=z_st_color,
                    cmap="magma",
                    alpha=0.78,
                    marker="s",
                    rasterized=True,
                )
            if maskJ_np is not None:
                ax.imshow(maskJ_np.T, alpha=0.12, cmap="Greys", origin="upper")
            _spashiny_ctx._style_alignment_panel(ax, "ST tissue and latent structure")
        elif panel == "sampled":
            _spashiny_globals.mark_source_image(
                ax.imshow(J_np, cmap=cmaps["tissue"], origin="upper")
            )
            ax.scatter(
                spot_np[:, 0],
                spot_np[:, 1],
                s=8,
                lw=0,
                c="#f8f8f8",
                alpha=0.96,
                edgecolors="none",
                rasterized=True,
            )
            _spashiny_ctx._style_alignment_panel(ax, "Randomly sampled inside-tissue spots")
            ax.set_xlim(0, J_np.shape[1])
            ax.set_ylim(J_np.shape[0], 0)
        elif panel == "mask":
            _spashiny_globals.mark_source_image(
                ax.imshow(Jtrue if Jtrue is not None else J_np, cmap="gray", origin="upper")
            )
            _spashiny_ctx._style_alignment_panel(ax, "Binary tissue mask")
        else:
            raise ValueError(f"Unknown spot panel: {panel}")
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlabel("image x", fontsize=8)
        ax.set_ylabel("image y", fontsize=8)
        fig.tight_layout()
        return fig

    _spashiny_ctx.build_spot_panel_figure = build_spot_panel_figure

    def _raster_panel_or_empty(panel):
        import os

        plot_id = {
            "sm_feature": "raster_panel_sm_feature",
            "sm_latent": "raster_panel_sm_latent",
            "st_image": "raster_panel_st_image",
            "st_latent": "raster_panel_st_latent",
        }.get(str(panel or ""))
        if plot_id:
            color_img = _spashiny_ctx._alignment_color_completed_image(plot_id)
            if color_img and os.path.exists(color_img):
                return _spashiny_ctx.image_path_to_figure(color_img)
            color_job = (_spashiny_ctx.alignment_color_panel_job_ids.get() or {}).get(plot_id)
            if color_job:
                status = _spashiny_ctx._alignment_status(color_job)
                if status.get("status") in {"queued", "running"}:
                    return _spashiny_ctx.empty_alignment_preview(
                        f"Color render is {status.get('status')} for {_spashiny_ctx._alignment_color_title(plot_id)}...\nJob: {color_job}"
                    )
                if status.get("status") == "failed":
                    return _spashiny_ctx.empty_alignment_preview(
                        _spashiny_globals._analysis_status_error_text(
                            f"Color render failed for {_spashiny_ctx._alignment_color_title(plot_id)}",
                            status,
                            job_id=color_job,
                            current_step="alignment color render",
                        )
                    )
        _spashiny_ctx._sync_alignment_render_results()
        panel_paths = _spashiny_ctx.raster_panel_img_val.get() or {}
        img_path = panel_paths.get(panel)
        if img_path and os.path.exists(img_path):
            return _spashiny_ctx.image_path_to_figure(img_path)
        return _spashiny_ctx.empty_alignment_preview(
            "Please run Step 4 to generate the raster panels first."
        )

    _spashiny_ctx._raster_panel_or_empty = _raster_panel_or_empty

    def _spot_panel_or_empty(panel):
        import os

        plot_id = {
            "st_latent": "spot_panel_st_latent",
            "sampled": "spot_panel_sampled",
            "mask": "spot_panel_mask",
        }.get(str(panel or ""))
        if plot_id:
            color_img = _spashiny_ctx._alignment_color_completed_image(plot_id)
            if color_img and os.path.exists(color_img):
                return _spashiny_ctx.image_path_to_figure(color_img)
            color_job = (_spashiny_ctx.alignment_color_panel_job_ids.get() or {}).get(plot_id)
            if color_job:
                status = _spashiny_ctx._alignment_status(color_job)
                if status.get("status") in {"queued", "running"}:
                    return _spashiny_ctx.empty_alignment_preview(
                        f"Color render is {status.get('status')} for {_spashiny_ctx._alignment_color_title(plot_id)}...\nJob: {color_job}"
                    )
                if status.get("status") == "failed":
                    return _spashiny_ctx.empty_alignment_preview(
                        _spashiny_globals._analysis_status_error_text(
                            f"Color render failed for {_spashiny_ctx._alignment_color_title(plot_id)}",
                            status,
                            job_id=color_job,
                            current_step="alignment color render",
                        )
                    )
        _spashiny_ctx._sync_alignment_render_results()
        panel_paths = _spashiny_ctx.spot_panel_img_val.get() or {}
        img_path = panel_paths.get(panel)
        if img_path and os.path.exists(img_path):
            return _spashiny_ctx.image_path_to_figure(img_path)
        return _spashiny_ctx.empty_alignment_preview(
            "Please run Step 4 to generate the spot panels first."
        )

    _spashiny_ctx._spot_panel_or_empty = _spot_panel_or_empty

    @_spashiny_ctx.output
    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("raster_plot")
    def raster_plot():
        import os

        _spashiny_ctx._sync_alignment_render_results()
        img_path = _spashiny_ctx.raster_img_val.get()
        if img_path and os.path.exists(img_path):
            return _spashiny_ctx.image_path_to_figure(img_path)
        raster_result = _spashiny_ctx.raster_data.get()
        if raster_result is not None:
            return _spashiny_ctx.empty_alignment_preview(
                "Raster worker PNG is unavailable; rerun Step 4 to regenerate display artifacts."
            )
        return _spashiny_ctx.empty_alignment_preview(
            "Please run Step 4 to generate the raster plot first."
        )

    _spashiny_ctx.raster_plot = raster_plot

    @_spashiny_ctx.output
    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("spot_only_plot")
    def spot_only_plot():
        import os

        _spashiny_ctx._sync_alignment_render_results()
        img_path = _spashiny_ctx.spot_fig_val.get()
        if img_path and os.path.exists(img_path):
            return _spashiny_ctx.image_path_to_figure(img_path)
        spot_result = _spashiny_ctx.spot_data.get()
        if spot_result is not None:
            return _spashiny_ctx.empty_alignment_preview(
                "Spot worker PNG is unavailable; rerun Step 4 to regenerate display artifacts."
            )
        return _spashiny_ctx.empty_alignment_preview(
            "Please run Step 4 to generate the spot plot first."
        )

    _spashiny_ctx.spot_only_plot = spot_only_plot

    async def _current_step4_vector_export():
        """Exact analysis/workflow only; regenerate drawings, never analyses."""
        owner, analysis = _spashiny_ctx._require_alignment_scope()
        workflow_id = _spashiny_ctx._current_alignment_workflow_id()
        if not workflow_id:
            raise RuntimeError("Run the current Alignment workflow before exporting figures.")
        state = _spashiny_ctx._read_alignment_workflow_state(workflow_id)
        job_id = str(state.get("step4_job_id") or _spashiny_ctx.alignment_step4_job_id.get() or "")
        job = _spashiny_ctx._alignment_job_payload(job_id)
        if not job or job.get("workflow_id") != workflow_id or job.get("task") != "render":
            raise RuntimeError(
                "The Step4 plot data does not belong to the current analysis/workflow."
            )
        manifest = _spashiny_ctx._completed_alignment_manifest(job_id)
        if manifest.get("status") != "completed" or manifest.get("job_id") != job_id:
            raise RuntimeError("Complete Step4 before exporting its vector figures.")
        settings = _spashiny_ctx.plot_color_settings.get() or {}
        colors = {}
        for group, panels in (
            ("raster", ("sm_feature", "sm_latent", "st_image", "st_latent")),
            ("spot", ("st_latent", "sampled", "mask")),
        ):
            for panel in panels:
                plot_id = f"{group}_panel_{panel}"
                original = next(
                    (
                        item.get("color_parameters") or {}
                        for item in manifest.get("plots", [])
                        if item.get("plot_id") == plot_id
                    ),
                    {},
                )
                colors[plot_id] = dict(
                    settings.get(plot_id) or settings.get("__global__") or original
                )
        data = await _spashiny_globals.export_saved_step4(
            scope_root=_spashiny_ctx._alignment_session_result_root(),
            workflow_root=_spashiny_ctx._alignment_workflow_root(workflow_id),
            source_dir=_spashiny_ctx._alignment_output_dir(job_id),
            source_job_id=job_id,
            colors_by_plot=colors,
        )
        current = _spashiny_ctx._read_alignment_workflow_state(workflow_id)
        if (
            _spashiny_ctx._require_alignment_scope() != (owner, analysis)
            or _spashiny_ctx._current_alignment_workflow_id() != workflow_id
            or str(current.get("step4_job_id") or _spashiny_ctx.alignment_step4_job_id.get() or "")
            != job_id
        ):
            raise RuntimeError(
                "Alignment input lineage changed during export; download was blocked."
            )
        return data

    _spashiny_ctx._current_step4_vector_export = _current_step4_vector_export

    @_spashiny_ctx.render.download(filename="raster_and_spot.pdf")
    async def download_raster_spot_pdf():
        data = await _spashiny_ctx._current_step4_vector_export()
        path = _spashiny_globals.alignment_checked_path(
            _spashiny_ctx.Path(data["root"]) / "raster_and_spot.pdf",
            _spashiny_ctx._alignment_workflow_root(),
        )
        for chunk in _spashiny_ctx.stream_file(path):
            yield chunk

    _spashiny_ctx.download_raster_spot_pdf = download_raster_spot_pdf

    def _alignment_allowed_result_roots():
        roots = [
            _spashiny_ctx.Path(
                _spashiny_globals.os.environ.get("SPASHINY_LOCAL_RESULT_ROOT")
                or _spashiny_globals.os.environ.get("SPASHINY_RESULTS_DIR")
                or "/workspace/results"
            ),
            _spashiny_ctx.Path(
                _spashiny_globals.os.environ.get("SPASHINY_LOCAL_JOBS_ROOT")
                or _spashiny_globals.os.environ.get("SPASHINY_TEMP_ROOT")
                or "/workspace/jobs"
            ),
        ]
        return [root.resolve() for root in roots if root.exists()]

    _spashiny_ctx._alignment_allowed_result_roots = _alignment_allowed_result_roots

    def _alignment_examples_root():
        return _spashiny_ctx.Path(
            _spashiny_globals.os.environ.get("SPASHINY_EXAMPLES_ROOT")
            or _spashiny_globals.os.environ.get("SPASHINY_DATA_EXAMPLES_ROOT")
            or "/workspace/data/examples"
        )

    _spashiny_ctx._alignment_examples_root = _alignment_examples_root

    def _is_resolved_under(path, roots):
        resolved = _spashiny_ctx.Path(path).resolve()
        for root in roots:
            try:
                resolved.relative_to(_spashiny_ctx.Path(root).resolve())
                return True
            except Exception:
                continue
        return False

    _spashiny_ctx._is_resolved_under = _is_resolved_under

    def _yield_safe_file(path, *, roots, label="file"):
        path = _spashiny_ctx.Path(path).resolve()
        roots = [_spashiny_ctx.Path(root).resolve() for root in roots]
        if not path.is_file() or not _spashiny_ctx._is_resolved_under(path, roots):
            _spashiny_ctx.log(f"Download blocked or missing for {label}: {path}")
            return
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk

    _spashiny_ctx._yield_safe_file = _yield_safe_file

    def _alignment_plot_download_path(plot_id):
        path = _spashiny_ctx._alignment_current_plot_path(plot_id)
        if path and _spashiny_ctx.Path(path).is_file():
            return _spashiny_ctx.Path(path)
        color_path = _spashiny_ctx._alignment_color_completed_image(plot_id)
        if color_path and _spashiny_ctx.Path(color_path).is_file():
            return _spashiny_ctx.Path(color_path)
        return None

    _spashiny_ctx._alignment_plot_download_path = _alignment_plot_download_path

    def _current_alignment_plot_paths():
        plot_ids = [
            "initial_plot",
            "overlay_plot",
            "side_plot",
            "raster_panel_sm_feature",
            "raster_panel_sm_latent",
            "raster_panel_st_image",
            "raster_panel_st_latent",
            "spot_panel_st_latent",
            "spot_panel_sampled",
            "spot_panel_mask",
        ]
        out = []
        seen = set()
        for plot_id in plot_ids:
            path = _spashiny_ctx._alignment_plot_download_path(plot_id)
            if path and path.is_file():
                key = str(path.resolve())
                if key in seen:
                    continue
                seen.add(key)
                cfg = _spashiny_ctx.ALIGNMENT_WORKER_COLOR_PLOTS.get(plot_id) or {}
                out.append(
                    (
                        plot_id,
                        str(cfg.get("plot_key") or plot_id),
                        str(cfg.get("title") or _spashiny_globals.humanize_plot_id(plot_id)),
                        path,
                    )
                )
        return out

    _spashiny_ctx._current_alignment_plot_paths = _current_alignment_plot_paths

    def _yield_alignment_plot_png(plot_id):
        path = _spashiny_ctx._alignment_plot_download_path(plot_id)
        if not path:
            _spashiny_ctx.log(f"Alignment PNG has not been generated yet: {plot_id}")
            return
        yield from _spashiny_ctx._yield_safe_file(
            path, roots=_spashiny_ctx._alignment_allowed_result_roots(), label=plot_id
        )

    _spashiny_ctx._yield_alignment_plot_png = _yield_alignment_plot_png

    @_spashiny_ctx.render.download(filename=lambda: "alignment_editable_figures.zip")
    async def download_alignment_vectors_zip():
        allowed_roots = _spashiny_ctx._alignment_allowed_result_roots()
        entries = []
        state = _spashiny_ctx._read_alignment_workflow_state()
        if state.get("step4_job_id") or _spashiny_ctx.alignment_step4_job_id.get():
            data = await _spashiny_ctx._current_step4_vector_export()
            for item in data["files"]:
                path = _spashiny_globals.alignment_checked_path(
                    _spashiny_ctx.Path(data["root"]) / item["path"],
                    _spashiny_ctx._alignment_workflow_root(),
                )
                entries.append((item["path"], path))
        for plot_id, _key, _title, png in _spashiny_ctx._current_alignment_plot_paths():
            if plot_id not in {"initial_plot", "overlay_plot", "side_plot"}:
                continue
            for suffix in (".pdf", ".svg"):
                path = png.with_suffix(suffix).resolve()
                if path.is_file() and _spashiny_ctx._is_resolved_under(path, allowed_roots):
                    entries.append((f"{plot_id}{suffix}", path))
        step7 = _spashiny_ctx._step7_persisted_pdf_artifact()
        if (
            step7 is None
            and _spashiny_ctx._step7_current_export_key() is not None
            and (state.get("step7_status") == "completed")
        ):
            step7 = _spashiny_ctx._ensure_step7_pdf_artifact()
        if step7 is not None:
            for suffix in (".pdf", ".svg"):
                path = step7.with_suffix(suffix).resolve()
                if path.is_file() and _spashiny_ctx._is_resolved_under(path, allowed_roots):
                    entries.append((f"alignment_result{suffix}", path))
        if not entries:
            raise RuntimeError(
                "No editable figures exist for this workflow. Generate previews/Step 4 with the current worker; PNG previews are not converted to pretend-editable PDFs."
            )
        with _spashiny_ctx.tempfile.TemporaryDirectory(prefix="alignment_vectors_") as temporary:
            archive = _spashiny_ctx.Path(temporary) / "alignment_editable_figures.zip"
            with _spashiny_ctx.zipfile.ZipFile(
                archive, "w", _spashiny_ctx.zipfile.ZIP_DEFLATED
            ) as handle:
                for name, path in entries:
                    handle.write(path, arcname=name)
            for chunk in _spashiny_ctx.stream_file(archive):
                yield chunk

    _spashiny_ctx.download_alignment_vectors_zip = download_alignment_vectors_zip

    @_spashiny_ctx.render.download(filename=lambda: "Y7_T_alignment_example_inputs.zip")
    def download_alignment_example_inputs():
        examples_root = _spashiny_ctx._alignment_examples_root().resolve()
        action_id = "y7-alignment-raw-example"
        try:
            from cloud.example_action_registry import ExampleActionRegistry

            registry = ExampleActionRegistry()
            action = registry.get_action(action_id)
            bundle = registry.get_bundle(str(action.get("bundle_id") or ""))
            asset_manifest_path = examples_root / "manifest.json"
            asset_manifest = _spashiny_ctx.json.loads(
                asset_manifest_path.read_text(encoding="utf-8-sig")
            )
            by_object_key = {
                str(item.get("object_key") or ""): item
                for item in asset_manifest.get("files") or []
            }
            required_roles = set((str(role) for role in action.get("required_roles") or []))
            selected = []
            for component in bundle.get("components") or []:
                role = str(component.get("role") or "")
                if role not in required_roles:
                    continue
                object_key = str(component.get("object_key") or "")
                asset = by_object_key.get(object_key)
                if not asset:
                    raise RuntimeError(f"Example manifest is missing object_key: {object_key}")
                rel = str(asset.get("relative_path") or "")
                src = (examples_root / rel).resolve()
                if not src.is_file() or not _spashiny_ctx._is_resolved_under(src, [examples_root]):
                    raise RuntimeError(f"Example asset is missing or outside examples root: {role}")
                selected.append((role, component, asset, src))
            if not selected:
                raise RuntimeError(
                    "No downloadable Alignment example inputs were resolved from the manifest."
                )
            tmp_dir = _spashiny_ctx.tempfile.mkdtemp(prefix="spashiny_alignment_example_download_")
            zip_path = _spashiny_ctx.Path(tmp_dir) / "Y7_T_alignment_example_inputs.zip"
            download_manifest = {
                "action_id": action_id,
                "bundle_id": bundle.get("bundle_id"),
                "manifest_version": asset_manifest.get("manifest_version"),
                "files": [],
            }
            with _spashiny_ctx.zipfile.ZipFile(
                zip_path, "w", compression=_spashiny_ctx.zipfile.ZIP_STORED
            ) as zf:
                for role, component, asset, src in selected:
                    arcname = f"inputs/{role}/{src.name}"
                    zf.write(src, arcname=arcname)
                    download_manifest["files"].append(
                        {
                            "role": role,
                            "component_id": component.get("component_id"),
                            "asset_id": asset.get("asset_id"),
                            "object_key": asset.get("object_key"),
                            "relative_path": asset.get("relative_path"),
                            "zip_path": arcname,
                            "size_bytes": asset.get("size_bytes"),
                            "sha256": asset.get("sha256"),
                        }
                    )
                zf.writestr(
                    "manifest/alignment_example_download_manifest.json",
                    _spashiny_ctx.json.dumps(
                        download_manifest, ensure_ascii=False, indent=2, sort_keys=True
                    ),
                )
            _spashiny_ctx.log(
                "ALIGNMENT_EXAMPLE_DOWNLOAD_CONTENTS="
                + ", ".join((item["zip_path"] for item in download_manifest["files"]))
            )
            try:
                with zip_path.open("rb") as handle:
                    while True:
                        chunk = handle.read(1024 * 1024)
                        if not chunk:
                            break
                        yield chunk
            finally:
                _spashiny_ctx.shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception as exc:
            _spashiny_ctx.log(f"download_alignment_example_inputs error: {exc}")
            _spashiny_ctx.ui.notification_show(
                f"Failed to prepare Alignment example download: {exc}", type="error", duration=10
            )
            return

    _spashiny_ctx.download_alignment_example_inputs = download_alignment_example_inputs

    @_spashiny_ctx.render.download(filename=lambda: "initial_st_sm_view.png")
    def download_alignment_initial_png():
        yield from _spashiny_ctx._yield_alignment_plot_png("initial_plot")

    _spashiny_ctx.download_alignment_initial_png = download_alignment_initial_png

    @_spashiny_ctx.render.download(filename=lambda: "manual_registration_preview.png")
    def download_alignment_manual_png():
        yield from _spashiny_ctx._yield_alignment_plot_png("overlay_plot")

    _spashiny_ctx.download_alignment_manual_png = download_alignment_manual_png

    @_spashiny_ctx.render.download(filename=lambda: "side_by_side.png")
    def download_alignment_side_png():
        yield from _spashiny_ctx._yield_alignment_plot_png("side_plot")

    _spashiny_ctx.download_alignment_side_png = download_alignment_side_png

    @_spashiny_ctx.render.download(filename=lambda: "sm_rasterized_feature.png")
    def download_raster_panel_sm_feature_png():
        yield from _spashiny_ctx._yield_alignment_plot_png("raster_panel_sm_feature")

    _spashiny_ctx.download_raster_panel_sm_feature_png = download_raster_panel_sm_feature_png

    @_spashiny_ctx.render.download(filename=lambda: "sm_latent_embedding.png")
    def download_raster_panel_sm_latent_png():
        yield from _spashiny_ctx._yield_alignment_plot_png("raster_panel_sm_latent")

    _spashiny_ctx.download_raster_panel_sm_latent_png = download_raster_panel_sm_latent_png

    @_spashiny_ctx.render.download(filename=lambda: "st_spatial_image.png")
    def download_raster_panel_st_image_png():
        yield from _spashiny_ctx._yield_alignment_plot_png("raster_panel_st_image")

    _spashiny_ctx.download_raster_panel_st_image_png = download_raster_panel_st_image_png

    @_spashiny_ctx.render.download(filename=lambda: "st_latent_feature.png")
    def download_raster_panel_st_latent_png():
        yield from _spashiny_ctx._yield_alignment_plot_png("raster_panel_st_latent")

    _spashiny_ctx.download_raster_panel_st_latent_png = download_raster_panel_st_latent_png

    @_spashiny_ctx.render.download(filename=lambda: "st_tissue_latent_structure.png")
    def download_spot_panel_st_latent_png():
        yield from _spashiny_ctx._yield_alignment_plot_png("spot_panel_st_latent")

    _spashiny_ctx.download_spot_panel_st_latent_png = download_spot_panel_st_latent_png

    @_spashiny_ctx.render.download(filename=lambda: "sampled_inside_tissue_spots.png")
    def download_spot_panel_sampled_png():
        yield from _spashiny_ctx._yield_alignment_plot_png("spot_panel_sampled")

    _spashiny_ctx.download_spot_panel_sampled_png = download_spot_panel_sampled_png

    @_spashiny_ctx.render.download(filename=lambda: "binary_tissue_mask.png")
    def download_spot_panel_mask_png():
        yield from _spashiny_ctx._yield_alignment_plot_png("spot_panel_mask")

    _spashiny_ctx.download_spot_panel_mask_png = download_spot_panel_mask_png

    @_spashiny_ctx.render.download(
        filename=lambda: f"alignment_plots_{_spashiny_ctx.time.strftime('%Y%m%d_%H%M%S')}.zip"
    )
    def download_alignment_all_plots_zip():
        plots = _spashiny_ctx._current_alignment_plot_paths()
        if not plots:
            _spashiny_ctx.log("No Alignment PNG plots are available for ZIP download.")
            return
        tmp_dir = _spashiny_ctx.tempfile.mkdtemp(prefix="spashiny_alignment_plots_zip_")
        zip_path = _spashiny_ctx.Path(tmp_dir) / "alignment_plots.zip"
        manifest = {
            "created_at": _spashiny_ctx.time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "session_id": _spashiny_ctx._alignment_session_token(),
            "owner_id": _spashiny_ctx._alignment_owner_id(),
            "analysis_session_id": _spashiny_ctx._alignment_analysis_session_id(),
            "plots": [],
        }
        try:
            with _spashiny_ctx.zipfile.ZipFile(
                zip_path, "w", compression=_spashiny_ctx.zipfile.ZIP_DEFLATED
            ) as zf:
                for plot_id, plot_key, title, path in plots:
                    if not _spashiny_ctx._is_resolved_under(
                        path, _spashiny_ctx._alignment_allowed_result_roots()
                    ):
                        continue
                    arcname = f"plots/{plot_key}/{path.name}"
                    zf.write(path, arcname=arcname)
                    manifest["plots"].append(
                        {
                            "plot_id": plot_id,
                            "plot_key": plot_key,
                            "title": title,
                            "zip_path": arcname,
                        }
                    )
                zf.writestr(
                    "manifest/alignment_plots_download_manifest.json",
                    _spashiny_ctx.json.dumps(
                        manifest, ensure_ascii=False, indent=2, sort_keys=True
                    ),
                )
            with zip_path.open("rb") as handle:
                while True:
                    chunk = handle.read(1024 * 1024)
                    if not chunk:
                        break
                    yield chunk
        finally:
            _spashiny_ctx.shutil.rmtree(tmp_dir, ignore_errors=True)

    _spashiny_ctx.download_alignment_all_plots_zip = download_alignment_all_plots_zip

    @_spashiny_ctx.render.ui
    def alignment_resource_mode_details():
        return _spashiny_ctx.ui.div()

    _spashiny_ctx.alignment_resource_mode_details = alignment_resource_mode_details

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.align_step5_fit_alignment)
    @_spashiny_ctx._one_stop_action("step5")
    def align_step5_fit_alignment():
        workflow_id = _spashiny_ctx._current_alignment_workflow_id()
        existing_job_id = _spashiny_ctx._current_step5_job_id()
        if existing_job_id:
            existing_status = _spashiny_ctx._alignment_status(existing_job_id)
            if existing_status.get("status") in {"queued", "running"}:
                _spashiny_ctx._bind_alignment_workflow_modal_job(
                    "step5",
                    existing_job_id,
                    details="Iterations: 500\nMode: tutorial\nPlease wait for alignment fitting to complete.",
                )
                return
        if not _spashiny_ctx._start_alignment_workflow_modal(
            "step5",
            "Running SpatialMETA alignment...",
            details="Iterations: 500\nMode: tutorial\nPlease wait for alignment fitting to complete.",
            defer_modal_until_job=True,
        ):
            return
        try:
            state = _spashiny_ctx._read_alignment_workflow_state(workflow_id) if workflow_id else {}
            if not workflow_id:
                raise RuntimeError("Start ST-SM Alignment Preprocessing first.")
            existing_job_id = _spashiny_ctx._current_step5_job_id()
            if existing_job_id:
                existing_status = _spashiny_ctx._alignment_status(existing_job_id)
                if existing_status.get("status") in {"queued", "running"}:
                    _spashiny_ctx.log(
                        f"Alignment Step5 worker is still {existing_status.get('status')}: {existing_job_id}"
                    )
                    _spashiny_ctx.log(
                        f"  current step: {existing_status.get('current_step') or ''}"
                    )
                    _spashiny_ctx._bind_alignment_workflow_modal_job("step5", existing_job_id)
                    return
                if existing_status.get("status") == "completed":
                    if _spashiny_ctx._load_alignment_fit_summary(existing_job_id):
                        _spashiny_ctx.log(
                            f"Alignment Step5 worker result restored: {existing_job_id}"
                        )
                        _spashiny_ctx._complete_alignment_workflow_modal(
                            "step5", job_id=existing_job_id
                        )
                        return
                elif existing_status.get("status") == "failed":
                    _spashiny_ctx.log(
                        f"Previous Alignment Step5 worker failed: {existing_status.get('error') or existing_status.get('error_message') or 'unknown error'}"
                    )
            alignment_mode = "tutorial"
            alignment_cfg = {}
            try:
                save_debug_figures = bool(_spashiny_ctx.input.align_save_debug_figures())
            except Exception:
                save_debug_figures = False
            render_job_id = _spashiny_ctx.alignment_step4_job_id.get() or state.get("step4_job_id")
            if not render_job_id:
                _spashiny_ctx.log("Step4 is not available. Please run Step4 first.")
                _spashiny_ctx.ui.notification_show(
                    "Please complete Step4 before running alignment.", type="error", duration=8
                )
                return
            render_status = _spashiny_ctx._alignment_status(render_job_id)
            if render_status.get("status") != "completed":
                message = f"Step4 worker is {render_status.get('status') or 'not ready'}; wait for Step4 before running alignment."
                _spashiny_ctx.log(message)
                _spashiny_ctx.ui.notification_show(message, type="error", duration=8)
                return
            manifest = _spashiny_ctx._completed_alignment_manifest(render_job_id)
            state_meta = manifest.get("step4_state") if isinstance(manifest, dict) else {}
            if (
                not isinstance(state_meta, dict)
                or state_meta.get("sampling_payload") != "step4_sampling_state.pkl"
            ):
                message = "Step4 persistent sampling state is unavailable. Please rerun Step4."
                _spashiny_ctx.log(message)
                _spashiny_ctx.ui.notification_show(message, type="error", duration=10)
                return
            _spashiny_ctx.result_dict_val.set(None)
            _spashiny_ctx.alignment_step5_coordinate_context.set(None)
            job_id = _spashiny_ctx._submit_alignment_fit(
                render_job_id, alignment_cfg, save_debug_figures
            )
            _spashiny_ctx.alignment_step5_job_id.set(job_id)
            _spashiny_ctx.alignment_step6_result_id.set(None)
            _spashiny_ctx._update_alignment_workflow_state(
                step5_job_id=job_id,
                step5_status="queued",
                step6_result_id=None,
                step7_status="not_started",
                step7_artifact_ready=False,
                step7_export_key=None,
                step7_artifact_path=None,
                step7_pdf_artifact_path=None,
            )
            _spashiny_ctx._bind_alignment_workflow_modal_job(
                "step5",
                job_id,
                details=f"Iterations: {_spashiny_globals.alignment_iterations()}\nMode: {alignment_mode}\nPlease wait for alignment fitting to complete.",
            )
            _spashiny_ctx.log(f"Alignment Step5 worker submitted: {job_id}")
            _spashiny_ctx.log(
                f"  mode: {alignment_mode}; config: {alignment_cfg}; save_debug_figures={save_debug_figures}"
            )
            _spashiny_ctx.log(
                f"  status: {_spashiny_ctx._alignment_jobs_root() / job_id / 'status.json'}"
            )
            _spashiny_ctx.log(f"  log: {_spashiny_ctx._alignment_logs_root() / (job_id + '.log')}")
            _spashiny_ctx.ui.notification_show(
                f"Alignment Step5 submitted as worker job {job_id}. It will continue if the page refreshes.",
                type="message",
                duration=8,
            )
        except Exception as e:
            _spashiny_ctx.log(f"align_step5_fit_alignment error: {e}")
            _spashiny_ctx._fail_alignment_workflow_modal("step5", e)
            _spashiny_ctx.ui.notification_show(f"Alignment failed: {e}", type="error", duration=12)

    _spashiny_ctx.align_step5_fit_alignment = align_step5_fit_alignment


_STEPS = (_install_0,)


def server(_spashiny_ctx, step=0):
    return _STEPS[step](_spashiny_ctx)
