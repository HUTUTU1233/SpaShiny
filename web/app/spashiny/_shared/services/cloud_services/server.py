# Extracted from /app/app/ST-SM.py. Feature: cloud_services; ordered phases preserve original initialization.
from spashiny._shared import runtime_globals as _spashiny_globals


def _install_0(_spashiny_ctx):

    def _cloud_session_token():
        try:
            return str(_spashiny_ctx.input.spashiny_session_token() or "").strip()
        except Exception:
            return ""

    _spashiny_ctx._cloud_session_token = _cloud_session_token

    def _cloud_session_record():
        token = _spashiny_ctx._cloud_session_token()
        if not token:
            return None
        try:
            from cloud.session_manager import SessionManager

            return SessionManager().authenticate(token)
        except Exception:
            return None

    _spashiny_ctx._cloud_session_record = _cloud_session_record

    def _cloud_session_id():
        record = _spashiny_ctx._cloud_session_record()
        return record.session_id if record is not None else None

    _spashiny_ctx._cloud_session_id = _cloud_session_id

    def _require_cloud_session_id():
        session_id = _spashiny_ctx._cloud_session_id()
        if not session_id:
            raise RuntimeError(
                "Anonymous cloud session is not ready. Please wait for session initialization before submitting cloud tasks."
            )
        return session_id

    _spashiny_ctx._require_cloud_session_id = _require_cloud_session_id

    def _cloud_analysis_session_id():
        return _spashiny_ctx._alignment_analysis_session_id()

    _spashiny_ctx._cloud_analysis_session_id = _cloud_analysis_session_id

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.spashiny_idle_timeout)
    async def _close_idle_shiny_connection():
        payload = _spashiny_ctx.input.spashiny_idle_timeout() or {}
        owner = _spashiny_ctx._cloud_session_id()
        analysis = (
            str(payload.get("analysis_session_id") or "") if isinstance(payload, dict) else ""
        )
        if (
            not owner
            or not analysis
            or analysis != str(_spashiny_ctx._cloud_analysis_session_id() or "")
        ):
            return
        from cloud.analysis_idle_policy import POLICY_KEY, IDLE_REASON
        from cloud.database import CloudDatabase

        with CloudDatabase(read_only=True).connect() as conn:
            row = conn.execute(
                "SELECT status,metadata_json FROM analysis_sessions WHERE owner_session_id=? AND analysis_session_id=?",
                (owner, analysis),
            ).fetchone()
        if row is None or row["status"] != "ENDED":
            return
        policy = _spashiny_ctx.json.loads(row["metadata_json"] or "{}").get(POLICY_KEY, {})
        if policy.get("ended_reason") == IDLE_REASON:
            await _spashiny_ctx.session.close(code=1000)

    _spashiny_ctx._close_idle_shiny_connection = _close_idle_shiny_connection
    _spashiny_ctx.cloud_example_action_bindings = _spashiny_ctx.reactive.Value({})

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.cloud_example_action_activated)
    def _track_cloud_example_action_activation():
        try:
            payload = _spashiny_ctx.input.cloud_example_action_activated() or {}
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            return
        action_id = str(payload.get("action_id") or "").strip()
        if not action_id:
            return
        bindings = dict(_spashiny_ctx.cloud_example_action_bindings.get() or {})
        bindings[action_id] = dict(payload)
        _spashiny_ctx.cloud_example_action_bindings.set(bindings)

    _spashiny_ctx._track_cloud_example_action_activation = _track_cloud_example_action_activation

    def _latest_example_action_for(*action_ids):
        bindings = _spashiny_ctx.cloud_example_action_bindings.get() or {}
        for action_id in action_ids:
            payload = bindings.get(action_id)
            if (
                isinstance(payload, dict)
                and payload.get("ready")
                and (
                    str(payload.get("analysis_session_id") or "")
                    == str(_spashiny_ctx._cloud_analysis_session_id() or "")
                )
            ):
                return str(action_id)
        session_id = _spashiny_ctx._cloud_session_id()
        if not session_id:
            return ""
        try:
            from cloud.database import CloudDatabase

            db = CloudDatabase()
            for action_id in action_ids:
                try:
                    record = db.get_example_action_binding(
                        session_id=session_id,
                        analysis_session_id=str(_spashiny_ctx._cloud_analysis_session_id() or ""),
                        action_id=str(action_id),
                    )
                except KeyError:
                    continue
                if bool(record.get("ready")):
                    return str(action_id)
        except Exception:
            return ""
        return ""

    _spashiny_ctx._latest_example_action_for = _latest_example_action_for

    def _bind_builtin_joint_example_for_worker(*, selected_path):
        """Bind only the canonical Y7_T fallback to the worker input contract."""
        if not _spashiny_globals.SPASHINY_LAB_PROFILE:
            return ""
        try:
            selected = _spashiny_ctx.Path(str(selected_path or "")).resolve(strict=True)
            builtin = _spashiny_globals.resolve_y7_example_input(
                "st_sm_conditional_vae", "joint", "joint_raw"
            ).resolve(strict=True)
        except Exception:
            return ""
        if selected != builtin:
            return ""
        session_record = _spashiny_ctx._cloud_session_record()
        if session_record is None:
            raise RuntimeError(
                "Cloud session is still initializing. Please wait a moment and try training again."
            )
        from cloud.example_action_bindings import ExampleActionBindingService

        payload = ExampleActionBindingService().activate(
            session=session_record,
            analysis_session_id=str(_spashiny_ctx._cloud_analysis_session_id() or ""),
            action_id="y7-joint-vit-example",
            page_name="joint",
        )
        if not bool(payload.get("ready")):
            missing = ", ".join((str(x) for x in payload.get("missing_roles") or []))
            raise RuntimeError(
                "The built-in Y7_T joint example is unavailable"
                + (f" (missing: {missing})." if missing else ".")
            )
        bindings = dict(_spashiny_ctx.cloud_example_action_bindings.get() or {})
        bindings["y7-joint-vit-example"] = dict(payload)
        _spashiny_ctx.cloud_example_action_bindings.set(bindings)
        return "y7-joint-vit-example"

    _spashiny_ctx._bind_builtin_joint_example_for_worker = _bind_builtin_joint_example_for_worker

    def _submit_cloud_example_action_job(
        *, workflow_name, example_action_ids, parameters, requested_resource
    ):
        session_record = _spashiny_ctx._cloud_session_record()
        if session_record is None:
            raise RuntimeError(
                "Anonymous cloud session is not ready. Please wait for session initialization before submitting cloud tasks."
            )
        action_id = _spashiny_ctx._latest_example_action_for(*example_action_ids)
        if not action_id:
            raise RuntimeError(
                "Load the Lab example for this page before submitting this Lab workflow."
            )
        from cloud.job_submission import JobSubmissionService

        return JobSubmissionService().submit_with_example_action(
            session=session_record,
            workflow_name=workflow_name,
            example_action_id=action_id,
            parameters=parameters,
            requested_resource=requested_resource,
            analysis_session_id=_spashiny_ctx._cloud_analysis_session_id(),
        )

    _spashiny_ctx._submit_cloud_example_action_job = _submit_cloud_example_action_job

    def _submit_prepared_multisample_training(
        *, workflow_name, prepared_summary, parameters, requested_resource
    ):
        """M03: no raw-example fallback after the user completed QC/SVM."""
        from cloud.job_submission import JobSubmissionService

        parent_id = str((prepared_summary or {}).get("cloud_job_id") or "").strip()
        roles = {
            "vhit_multi_sample_integration": "vhit_prepared_h5ad",
            "hit_sm_multi_sample_integration": "hit_sm_prepared_h5ad",
        }
        if workflow_name not in roles or not parent_id:
            raise RuntimeError(
                "Complete this analysis's worker QC/SVM stage before training; no raw input was substituted."
            )
        session_record = _spashiny_ctx._cloud_session_record()
        analysis = str(_spashiny_ctx._cloud_analysis_session_id() or "").strip()
        if session_record is None or not analysis:
            raise RuntimeError("The current tab's authenticated analysis is not ready.")
        return JobSubmissionService().submit(
            session=session_record,
            workflow_name=workflow_name,
            input_upload_ids=[],
            workflow_artifacts=[
                {"parent_type": "job", "parent_job_id": parent_id, "role": roles[workflow_name]}
            ],
            parameters={**parameters, "prepared_parent_job_id": parent_id},
            requested_resource=requested_resource,
            analysis_session_id=analysis,
        )

    _spashiny_ctx._submit_prepared_multisample_training = _submit_prepared_multisample_training
    _spashiny_ctx.cloud_postprocess_modal_state = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.cloud_prepare_modal_state = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.cloud_task_modal_owner = _spashiny_ctx.reactive.Value(None)

    async def _submit_uploaded_multisample_training(
        *, workflow_name, data, parameters, requested_resource, source_mode
    ):
        """Register the actual selected QC result through normal exact-scope upload APIs.

        The browser cannot supply a server path. No example binding is consulted.
        Large H5AD serialization and part I/O run outside the Shiny event loop.
        """
        if str(source_mode) != "USER_UPLOAD":
            raise RuntimeError("Uploaded multi-sample training requires USER_UPLOAD source mode.")
        owner = _spashiny_ctx._cloud_session_record()
        analysis = str(_spashiny_ctx._cloud_analysis_session_id() or "").strip()
        if owner is None or not analysis:
            raise RuntimeError("The current authenticated analysis is not ready.")
        if (
            data is None
            or "sample" not in data.obs
            or data.obs["sample"].isna().any()
            or (data.obs["sample"].nunique() < 2)
        ):
            raise ValueError("Processed upload must retain at least two actual samples.")
        if (
            "highly_variable_moranI" not in data.var
            or not data.var["highly_variable_moranI"].astype(bool).all()
        ):
            raise ValueError(
                "Complete spatial-variable feature filtering before training uploaded samples."
            )
        needed = "normalized" if workflow_name == "hit_sm_multi_sample_integration" else "counts"
        if needed not in data.layers:
            raise ValueError(f"Prepared upload is missing the tutorial input layer: {needed}")
        root = _spashiny_ctx.Path(_spashiny_ctx.temp_directory.get())

        def register_and_submit():
            import math
            from cloud.upload_service import UploadService, UploadPart
            from cloud.job_submission import JobSubmissionService

            service = UploadService()
            upload_id = None
            with _spashiny_ctx.tempfile.TemporaryDirectory(
                prefix="prepared-upload-", dir=root
            ) as private:
                path = _spashiny_ctx.Path(private) / "prepared_multisample.h5ad"
                data.write_h5ad(path)
                size = path.stat().st_size
                part_size = 8 * 1024 * 1024
                init = service.initiate_upload(
                    session=owner,
                    analysis_session_id=analysis,
                    filename=path.name,
                    size_bytes=size,
                    content_type="application/x-hdf5",
                    total_parts=math.ceil(size / part_size),
                )
                upload_id = str(init["upload_id"])
                try:
                    record = service.database.get_upload(
                        upload_id, session_id=owner.session_id, analysis_session_id=analysis
                    )
                    if not hasattr(service.storage, "put_part"):
                        raise RuntimeError(
                            "Prepared upload handoff requires configured local multipart storage."
                        )
                    parts = []
                    with path.open("rb") as stream:
                        for number in range(1, math.ceil(size / part_size) + 1):
                            etag = service.storage.put_part(
                                record.multipart_upload_id, number, stream.read(part_size)
                            )
                            parts.append(UploadPart(part_number=number, etag=etag))
                    service.complete_upload(
                        session=owner,
                        analysis_session_id=analysis,
                        upload_id=upload_id,
                        parts=parts,
                    )
                    submitted = dict(parameters)
                    submitted.update(
                        source_mode="USER_UPLOAD", prepared_input_origin="same_analysis_qc_upload"
                    )
                    return JobSubmissionService().submit(
                        session=owner,
                        workflow_name=workflow_name,
                        input_upload_ids=[upload_id],
                        parameters=submitted,
                        requested_resource=requested_resource,
                        analysis_session_id=analysis,
                    )
                except Exception:
                    current = service.database.get_upload(
                        upload_id, session_id=owner.session_id, analysis_session_id=analysis
                    )
                    if str(current.status) != "COMPLETED":
                        service.abort_upload(
                            session=owner, analysis_session_id=analysis, upload_id=upload_id
                        )
                    raise

        return await _spashiny_globals.asyncio.to_thread(register_and_submit)

    _spashiny_ctx._submit_uploaded_multisample_training = _submit_uploaded_multisample_training

    def _set_cloud_task_modal_owner(*, job_id, kind, title):
        _spashiny_ctx.cloud_task_modal_owner.set(
            {
                "job_id": str(job_id),
                "kind": str(kind),
                "title": str(title),
                "analysis_session_id": str(_spashiny_ctx._cloud_analysis_session_id() or ""),
            }
        )

    _spashiny_ctx._set_cloud_task_modal_owner = _set_cloud_task_modal_owner

    def _cleanup_task_modal_state(*, job_id):
        """Remove only the terminal job's modal and its Bootstrap scroll lock."""
        owner = _spashiny_ctx.cloud_task_modal_owner.get() or {}
        current_analysis_session = str(_spashiny_ctx._cloud_analysis_session_id() or "")
        if (
            not job_id
            or str(owner.get("job_id") or "") != str(job_id)
            or str(owner.get("analysis_session_id") or "") != current_analysis_session
        ):
            return False
        _spashiny_ctx.cloud_prepare_modal_state.set(None)
        _spashiny_ctx.cloud_postprocess_modal_state.set(None)
        _spashiny_ctx.cloud_task_modal_owner.set(None)
        try:
            _spashiny_ctx.ui.modal_remove()
        finally:

            async def cleanup_after_flush():
                await _spashiny_ctx.session.send_custom_message(
                    "spashiny_cleanup_task_modal", {"job_id": str(job_id)}
                )

            _spashiny_ctx.session.on_flushed(cleanup_after_flush, once=True)
        return True

    _spashiny_ctx._cleanup_task_modal_state = _cleanup_task_modal_state

    def _show_multisample_feedback_modal(title, message, *, progress=100.0, detail=""):
        """Show completion/staging feedback without executing work in Shiny."""
        value = max(0.0, min(100.0, float(progress)))
        _spashiny_ctx.ui.modal_show(
            _spashiny_ctx.ui.modal(
                _spashiny_ctx.ui.div(
                    _spashiny_ctx.ui.p(message),
                    _spashiny_ctx.ui.tags.progress(
                        value=value, max=100, style="width:100%; height:18px;"
                    ),
                    _spashiny_ctx.ui.div(
                        f"{value:.0f}%", class_="cloud-muted", style="margin-top:6px;"
                    ),
                    (
                        _spashiny_ctx.ui.p(detail, class_="cloud-muted")
                        if detail
                        else _spashiny_ctx.ui.div()
                    ),
                ),
                title=title,
                easy_close=True,
                footer=_spashiny_ctx.ui.modal_button("Close"),
            )
        )

    _spashiny_ctx._show_multisample_feedback_modal = _show_multisample_feedback_modal

    def _show_multisample_prepare_modal(*, job_id, title):
        """Show the persisted progress for one merge/QC worker job.

        The modal is only a view of JobManager state: it never performs H5AD
        work in Shiny.  The matching restore effect closes it once the worker
        reaches a terminal state.
        """
        _spashiny_ctx.cloud_prepare_modal_state.set({"job_id": str(job_id), "title": str(title)})
        _spashiny_ctx._set_cloud_task_modal_owner(job_id=job_id, kind="prepare", title=title)
        _spashiny_ctx.ui.modal_show(
            _spashiny_ctx.ui.modal(
                _spashiny_ctx.ui.output_ui("cloud_prepare_modal_progress"),
                title="Workflow Progress",
                easy_close=False,
                footer=None,
            )
        )

    _spashiny_ctx._show_multisample_prepare_modal = _show_multisample_prepare_modal

    def _cloud_job_stage(job):
        """Return a small persisted workflow stage without trusting UI state."""
        try:
            payload = _spashiny_ctx.json.loads(str(getattr(job, "parameters_json", "") or "{}"))
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            return ""
        return str(payload.get("stage") or "").strip().lower()

    _spashiny_ctx._cloud_job_stage = _cloud_job_stage

    def _cloud_integration_result_state(summary, *, workflow_name="", stage="", read_only_db=False):
        """Resolve a completed worker result without loading h5ad data in Web.

        The VHiT restore/poll path issues SELECTs only and must not initialize,
        migrate, heartbeat, claim, or otherwise write JobManager SQLite.
        """
        job_id = str((summary or {}).get("cloud_job_id") or "").strip()
        if not job_id and workflow_name in {
            "vhit_multi_sample_integration",
            "hit_sm_multi_sample_integration",
        }:
            source_mode = (
                _spashiny_ctx.vhit_input_source_mode
                if workflow_name == "vhit_multi_sample_integration"
                else _spashiny_ctx.hit_sm_input_source_mode
            )
            if source_mode.get() == "USER_UPLOAD":
                return ("", "", None)
        expected_stage = str(stage or (summary or {}).get("stage") or "").strip().lower()
        if not expected_stage and workflow_name in {
            "vhit_multi_sample_integration",
            "hit_sm_multi_sample_integration",
        }:
            expected_stage = "train"

        def matches_result_stage(item):
            if workflow_name and str(item.workflow) != workflow_name:
                return False
            return (
                not expected_stage
                or (_spashiny_ctx._cloud_job_stage(item) or "train") == expected_stage
            )

        session_id = _spashiny_ctx._cloud_session_id()
        analysis_session_id = _spashiny_ctx._cloud_analysis_session_id()
        if not session_id or not analysis_session_id:
            return ("", "", None)
        try:
            from cloud.job_manager import JobManager

            if read_only_db:
                from cloud.database import CloudDatabase

                manager = JobManager(database=CloudDatabase(read_only=True))
            else:
                manager = JobManager()
            job = None
            if job_id:
                try:
                    job = manager.get_job_for_session(
                        session_id, job_id, analysis_session_id=analysis_session_id
                    )
                except Exception:
                    job = None
                if job is not None and (not matches_result_stage(job)):
                    return ("", "", None)
            if job is None and workflow_name:
                for item in manager.list_jobs_for_session(
                    session_id, analysis_session_id=analysis_session_id, limit=100
                ):
                    if not matches_result_stage(item):
                        continue
                    job = item
                    break
            if job is None:
                return ("", "", None)
        except Exception:
            return ("", "", None)
        status = str(job.status or "").upper()
        if status not in {"SUCCEEDED", "COMPLETED"}:
            return ("", status, job)
        try:
            root = _spashiny_ctx.Path(str(job.local_workspace or "")).resolve()
            for rel_path in ("integrated_result.h5ad", "output/spatialmeta_result.h5ad"):
                candidate = (root / rel_path).resolve()
                if (
                    candidate.is_file()
                    and candidate.stat().st_size > 0
                    and (root in candidate.parents)
                ):
                    return (str(candidate), status, job)
        except Exception:
            pass
        return ("", status, job)

    _spashiny_ctx._cloud_integration_result_state = _cloud_integration_result_state

    def _cloud_result_still_active(status):
        from cloud.models import ACTIVE_JOB_STATUSES

        return str(status or "").upper() in ACTIVE_JOB_STATUSES

    _spashiny_ctx._cloud_result_still_active = _cloud_result_still_active

    def _cloud_prepare_result_state(summary, *, workflow_name="", stage="", read_only_db=False):
        """Read a tiny worker-preparation summary; never load its H5AD in Web.

        Multi-sample merge/QC runs in the host GPU worker.  The Web process only
        restores the persisted JSON summary and an authorized result path, so a
        page refresh cannot turn a completed merge back into "not merged".
        """
        result_path, status, job = _spashiny_ctx._cloud_integration_result_state(
            summary, workflow_name=workflow_name, stage=stage, read_only_db=read_only_db
        )
        metadata = {}
        if result_path and job is not None:
            try:
                root = _spashiny_ctx.Path(str(job.local_workspace or "")).resolve()
                summary_path = (root / "merge_summary.json").resolve()
                if summary_path.is_file() and root in summary_path.parents:
                    metadata = _spashiny_ctx.json.loads(summary_path.read_text(encoding="utf-8"))
                    if not isinstance(metadata, dict):
                        metadata = {}
            except Exception:
                metadata = {}
        return (metadata, result_path, status, job)

    _spashiny_ctx._cloud_prepare_result_state = _cloud_prepare_result_state

    def _cloud_training_progress_card(summary, *, title, read_only_db=False):
        """Render persisted JobManager progress without running work in Shiny."""
        job_id = str((summary or {}).get("cloud_job_id") or "").strip()
        if not job_id:
            return None
        session_id = _spashiny_ctx._cloud_session_id()
        analysis_session_id = _spashiny_ctx._cloud_analysis_session_id()
        if not session_id or not analysis_session_id:
            return _spashiny_ctx.ui.div(
                "Session is initializing; training status will appear shortly.",
                class_="cloud-muted",
            )
        try:
            from cloud.job_manager import JobManager

            if read_only_db:
                from cloud.database import CloudDatabase

                manager = JobManager(database=CloudDatabase(read_only=True))
            else:
                manager = JobManager()
            job = manager.get_job_for_session(
                session_id, job_id, analysis_session_id=analysis_session_id
            )
        except Exception as exc:
            return _spashiny_ctx.ui.div(
                f"Training job status is temporarily unavailable: {exc}",
                class_="alert alert-warning",
            )
        from cloud.models import ACTIVE_JOB_STATUSES

        status = str(job.status or "QUEUED").upper()
        progress = max(0.0, min(100.0, float(job.progress or 0.0)))
        step = str(job.current_step or "Waiting for a worker")
        active = status in ACTIVE_JOB_STATUSES
        if active:
            _spashiny_ctx.reactive.invalidate_later(2)
        state_class = (
            "alert alert-danger"
            if status.lower() in {"failed", "cancelled", "queue_full", "not_enabled"}
            else "apple-card"
        )
        rows = [
            _spashiny_ctx.ui.tags.div(f"{title}: {status}", class_="fw-semibold"),
            _spashiny_ctx.ui.tags.div(f"Job ID: {job.job_id}", class_="cloud-muted"),
            _spashiny_ctx.ui.tags.progress(
                value=progress, max=100, style="width:100%; height:18px;"
            ),
            _spashiny_ctx.ui.tags.div(f"{progress:.1f}% | {step}", class_="cloud-muted"),
        ]
        detail = str(job.message or "").strip()
        if detail and detail != step:
            rows.append(
                _spashiny_ctx.ui.tags.div(
                    detail[:500],
                    class_="cloud-muted",
                    style="margin-top:4px; white-space:pre-wrap;",
                )
            )
        if status.lower() in {"failed", "cancelled", "timed_out", "queue_full", "not_enabled"}:
            rows.append(_spashiny_globals._job_error_ui(job, title=f"{title} did not complete"))
        return _spashiny_ctx.ui.div(
            *rows, class_=state_class, style="margin-top:10px; padding:12px;"
        )

    _spashiny_ctx._cloud_training_progress_card = _cloud_training_progress_card

    @_spashiny_ctx.render.ui
    def cloud_prepare_modal_progress():
        state = _spashiny_ctx.cloud_prepare_modal_state.get() or {}
        job_id = str(state.get("job_id") or "")
        if not job_id:
            return _spashiny_ctx.ui.div()
        title = str(state.get("title") or "Worker job")
        return _spashiny_ctx._cloud_training_progress_card(
            {"cloud_job_id": job_id}, title=title, read_only_db=True
        ) or _spashiny_ctx.ui.div("Waiting for worker progress.", class_="cloud-muted")

    _spashiny_ctx.cloud_prepare_modal_progress = cloud_prepare_modal_progress

    def _sync_multisample_prepare_modal(summary, *, title, workflow_name, read_only_db=False):
        """Refresh a merge/QC modal and close it only after the job is terminal."""
        _result_path, status, job = _spashiny_ctx._cloud_integration_result_state(
            summary, workflow_name=workflow_name, read_only_db=read_only_db
        )
        job_id = str((summary or {}).get("cloud_job_id") or getattr(job, "job_id", "")).strip()
        current = _spashiny_ctx.cloud_prepare_modal_state.get() or {}
        from cloud.models import ACTIVE_JOB_STATUSES

        active = status in ACTIVE_JOB_STATUSES
        if active:
            _spashiny_ctx.reactive.invalidate_later(2)
        if (
            job is not None
            and status
            and (current.get("job_id") == job_id)
            and job_id
            and (not active)
        ):
            _spashiny_ctx._cleanup_task_modal_state(job_id=job_id)

    _spashiny_ctx._sync_multisample_prepare_modal = _sync_multisample_prepare_modal

    def _sync_cloud_postprocess_modal(summary, *, title, workflow_name="", read_only_db=False):
        _result_path, status, job = _spashiny_ctx._cloud_integration_result_state(
            summary, workflow_name=workflow_name, read_only_db=read_only_db
        )
        job_id = str((summary or {}).get("cloud_job_id") or getattr(job, "job_id", "")).strip()
        from cloud.models import ACTIVE_JOB_STATUSES

        active = status in ACTIVE_JOB_STATUSES
        progress = float(getattr(job, "progress", 0.0) or 0.0) if job is not None else 0.0
        current = _spashiny_ctx.cloud_postprocess_modal_state.get() or {}
        if active:
            _spashiny_ctx.reactive.invalidate_later(2)
        if active and job_id:
            phase = "Analyzing VAE Results" if progress >= 90.0 else "Training in Progress"
            if current.get("job_id") != job_id:
                _spashiny_ctx.cloud_postprocess_modal_state.set(
                    {
                        "job_id": job_id,
                        "title": title,
                        "phase": phase,
                        "read_only_db": bool(read_only_db),
                    }
                )
                _spashiny_ctx._set_cloud_task_modal_owner(
                    job_id=job_id, kind="postprocess", title=title
                )
                _spashiny_ctx.ui.modal_show(
                    _spashiny_ctx.ui.modal(
                        _spashiny_ctx.ui.output_ui("cloud_postprocess_modal_progress"),
                        title="Workflow Progress",
                        easy_close=False,
                        footer=None,
                    )
                )
            elif current.get("phase") != phase:
                _spashiny_ctx.cloud_postprocess_modal_state.set(
                    {
                        "job_id": job_id,
                        "title": title,
                        "phase": phase,
                        "read_only_db": bool(read_only_db),
                    }
                )
            return
        if job_id and (not active):
            _spashiny_ctx._cleanup_task_modal_state(job_id=job_id)

    _spashiny_ctx._sync_cloud_postprocess_modal = _sync_cloud_postprocess_modal

    @_spashiny_ctx.render.ui
    def cloud_postprocess_modal_progress():
        state = _spashiny_ctx.cloud_postprocess_modal_state.get() or {}
        job_id = str(state.get("job_id") or "")
        if not job_id:
            return _spashiny_ctx.ui.div()
        title = str(state.get("title") or "ConditionalVAE")
        phase = str(state.get("phase") or "Training in Progress")
        return _spashiny_ctx._cloud_training_progress_card(
            {"cloud_job_id": job_id},
            title=f"{title}: {phase}",
            read_only_db=bool(state.get("read_only_db")),
        ) or _spashiny_ctx.ui.div("Waiting for worker progress.", class_="cloud-muted")

    _spashiny_ctx.cloud_postprocess_modal_progress = cloud_postprocess_modal_progress

    def _format_bytes(value):
        value = float(value or 0)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if value < 1024 or unit == "TB":
                return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"
            value /= 1024
        return f"{value:.1f} TB"

    _spashiny_ctx._format_bytes = _format_bytes

    def _safe_cloud_result_rel_path(value):
        raw = str(value or "").strip().replace("\\", "/")
        if not raw or raw.startswith("/") or "\x00" in raw:
            return ""
        parts = [part for part in raw.split("/") if part not in {"", "."}]
        if any((part == ".." for part in parts)):
            return ""
        return "/".join(parts)

    _spashiny_ctx._safe_cloud_result_rel_path = _safe_cloud_result_rel_path

    def _cloud_result_download_url(
        session_id, analysis_session_id, job_id, rel_path, *, ttl_seconds=3600
    ):
        import hashlib
        import hmac
        import time as _time
        from urllib.parse import quote, urlencode

        session_id = str(session_id or "")
        analysis_session_id = str(analysis_session_id or "")
        job_id = str(job_id or "")
        rel_path = _spashiny_ctx._safe_cloud_result_rel_path(rel_path)
        if not session_id or not analysis_session_id or (not job_id) or (not rel_path):
            return ""
        expires = str(int(_time.time()) + int(ttl_seconds))
        secret = (_spashiny_globals.os.environ.get("SPASHINY_SESSION_HMAC_SECRET") or "").strip()
        if not secret:
            return ""
        payload = "\n".join([session_id, analysis_session_id, job_id, rel_path, expires]).encode(
            "utf-8"
        )
        sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        return (
            f"/lab-result-download/{quote(job_id, safe='')}/{quote(rel_path, safe='/')}"
            + "?"
            + urlencode(
                {
                    "session_id": session_id,
                    "analysis_session_id": analysis_session_id,
                    "expires": expires,
                    "sig": sig,
                }
            )
        )

    _spashiny_ctx._cloud_result_download_url = _cloud_result_download_url

    def _cloud_result_preview_url(
        session_id, analysis_session_id, job_id, rel_path, *, ttl_seconds=3600
    ):
        """Return a signed, same-session inline preview URL for a worker plot."""
        url = _spashiny_ctx._cloud_result_download_url(
            session_id, analysis_session_id, job_id, rel_path, ttl_seconds=ttl_seconds
        )
        return f"{url}&inline=1" if url else ""

    _spashiny_ctx._cloud_result_preview_url = _cloud_result_preview_url
    _spashiny_ctx.cloud_plot_preview_url_cache = {}

    def _cloud_cached_result_preview_url(
        session_id, analysis_session_id, job_id, rel_path, artifact_path
    ):
        try:
            artifact_mtime_ns = int(artifact_path.stat().st_mtime_ns)
        except OSError:
            artifact_mtime_ns = -1
        cache_key = (
            str(session_id or ""),
            str(analysis_session_id or ""),
            str(job_id or ""),
            str(rel_path or ""),
        )
        cached = _spashiny_ctx.cloud_plot_preview_url_cache.get(cache_key)
        if cached and cached.get("mtime_ns") == artifact_mtime_ns:
            return str(cached.get("url") or "")
        url = _spashiny_ctx._cloud_result_preview_url(
            session_id, analysis_session_id, job_id, rel_path
        )
        if url:
            _spashiny_ctx.cloud_plot_preview_url_cache[cache_key] = {
                "mtime_ns": artifact_mtime_ns,
                "url": url,
            }
        return url

    _spashiny_ctx._cloud_cached_result_preview_url = _cloud_cached_result_preview_url

    def _cloud_worker_plot_ui(
        summary, *, workflow_name, rel_path, fallback_output, alt, stage="", read_only_db=False
    ):
        """Send a verified worker PNG over this tab's authenticated Shiny connection."""
        _result_path, _status, job = _spashiny_ctx._cloud_integration_result_state(
            summary or {}, workflow_name=workflow_name, stage=stage, read_only_db=True
        )
        if job is not None and _status in {"SUCCEEDED", "COMPLETED"}:
            target = _spashiny_ctx._cloud_authorized_worker_figure(
                dict(summary or {}, cloud_job_id=str(job.job_id)),
                workflow_name=workflow_name,
                stage=stage or _spashiny_ctx._cloud_job_stage(job) or "train",
                rel_path=rel_path,
            )
            if target is not None:
                import base64

                return _spashiny_ctx.ui.tags.img(
                    src="data:image/png;base64,"
                    + base64.b64encode(target.read_bytes()).decode("ascii"),
                    alt=alt,
                    style="display:block; width:100%; height:auto; max-height:540px; object-fit:contain; background:#fff;",
                )
        if _spashiny_globals.SPASHINY_LAB_PROFILE:
            return _spashiny_ctx.ui.div(
                "This worker-generated plot will appear after the corresponding job completes.",
                class_="cloud-muted",
                style="min-height:260px; display:flex; align-items:center; justify-content:center; text-align:center;",
            )
        return _spashiny_globals.plot_output_with_palette(
            fallback_output, width="100%", height="540px"
        )

    _spashiny_ctx._cloud_worker_plot_ui = _cloud_worker_plot_ui

    def _cloud_result_manifest(job):
        import json

        workspace = _spashiny_ctx.Path(str(getattr(job, "local_workspace", "") or ""))
        manifest = workspace / "result_manifest.json"
        if not manifest.is_file():
            return {}
        try:
            return json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            return {}

    _spashiny_ctx._cloud_result_manifest = _cloud_result_manifest

    def _cloud_result_json(job, rel_path):
        import json

        rel = _spashiny_ctx._safe_cloud_result_rel_path(rel_path)
        if not rel:
            return {}
        workspace = _spashiny_ctx.Path(str(getattr(job, "local_workspace", "") or "")).resolve()
        target = (workspace / rel).resolve()
        if not workspace or (target != workspace and workspace not in target.parents):
            return {}
        if not target.is_file():
            return {}
        try:
            return json.loads(target.read_text(encoding="utf-8"))
        except Exception:
            return {}

    _spashiny_ctx._cloud_result_json = _cloud_result_json

    def _cloud_worker_table(summary, *, workflow_name, rel_path, stage=""):
        """Read a compact JSON table emitted by a worker, never its H5AD."""
        _result_path, _status, job = _spashiny_ctx._cloud_integration_result_state(
            summary or {}, workflow_name=workflow_name, stage=stage
        )
        if job is None:
            return []
        data = _spashiny_ctx._cloud_result_json(job, rel_path)
        return data if isinstance(data, list) else []

    _spashiny_ctx._cloud_worker_table = _cloud_worker_table

    def _cloud_result_download_links(session_id, job):
        manifest = _spashiny_ctx._cloud_result_manifest(job)
        entries = []
        is_river = (
            str(getattr(job, "workflow_name", "") or getattr(job, "workflow", ""))
            == "river_spatial_transcriptomics"
        )

        def add(label, rel_path, *, css="btn-outline-primary"):
            rel = _spashiny_ctx._safe_cloud_result_rel_path(rel_path)
            if not rel:
                return
            url = _spashiny_ctx._cloud_result_download_url(
                session_id, getattr(job, "analysis_session_id", ""), job.job_id, rel
            )
            if not url:
                return
            path = _spashiny_ctx.Path(rel)
            entries.append(
                _spashiny_ctx.ui.tags.a(
                    label,
                    href=url,
                    download=path.name,
                    class_=f"btn btn-sm {css}",
                    style="margin: 4px 6px 4px 0;",
                    **{"data-spashiny-river-artifact-download": "1"} if is_river else {},
                )
            )

        archive = manifest.get("archive") if isinstance(manifest, dict) else {}
        add("Download Result ZIP", (archive or {}).get("path") or "results.zip", css="btn-primary")
        add("Download Manifest JSON", "result_manifest.json", css="btn-outline-secondary")
        plots = manifest.get("plots") if isinstance(manifest, dict) else []
        if isinstance(plots, list):
            for item in plots[:3]:
                if isinstance(item, dict):
                    add("Download Plots", item.get("path"), css="btn-outline-success")
                    break
        files = manifest.get("files") if isinstance(manifest, dict) else []
        if isinstance(files, list):
            available_paths = {
                str(item.get("path") or "")
                for item in files
                if isinstance(item, dict) and str(item.get("path") or "")
            }
            for rel_path, label, css in (
                (
                    "river_selected_gene_temporal.png",
                    "Representative Gene Time Plot",
                    "btn-outline-success",
                ),
                (
                    "river_selected_gene_spatial.png",
                    "Representative Gene Spatial Plot",
                    "btn-outline-success",
                ),
                (
                    "river_selected_gene_temporal.csv",
                    "Representative Gene Time Statistics",
                    "btn-outline-primary",
                ),
            ):
                if rel_path in available_paths:
                    add(label, rel_path, css=css)
            if is_river:
                if "river_final_rank_temporal.csv" in available_paths:
                    add(
                        "Download River Top-Gene Ranking CSV",
                        "river_final_rank_temporal.csv",
                        css="btn-outline-primary",
                    )
                for rel_path, label in (
                    ("river_combined_plot.pdf", "Download Combined Figure PDF"),
                    ("river_selected_gene_temporal.pdf", "Download Gene Time PDF"),
                    ("river_selected_gene_spatial.pdf", "Download Gene Spatial PDF"),
                ):
                    if rel_path in available_paths:
                        add(label, rel_path, css="btn-outline-danger")
            for suffix, label, css in (
                (".h5ad", "Download H5AD", "btn-outline-info"),
                (".json", "Download JSON", "btn-outline-secondary"),
                (".png", "Download PNG", "btn-outline-success"),
                (".pdf", "Download Editable PDF", "btn-outline-danger"),
                (".svg", "Download Editable SVG", "btn-outline-danger"),
            ):
                if is_river and suffix == ".pdf":
                    continue
                for item in files:
                    rel = str(item.get("path") or "") if isinstance(item, dict) else ""
                    if rel.lower().endswith(suffix):
                        add(label, rel, css=css)
                        break
            log_rel = ""
            for require_nonempty in (True, False):
                for item in files:
                    rel = str(item.get("path") or "") if isinstance(item, dict) else ""
                    if not (rel.startswith("logs/") or rel.endswith(".log")):
                        continue
                    try:
                        size_bytes = (
                            int(item.get("size_bytes") or 0) if isinstance(item, dict) else 0
                        )
                    except Exception:
                        size_bytes = 0
                    if require_nonempty and size_bytes <= 0:
                        continue
                    log_rel = rel
                    break
                if log_rel:
                    break
            if log_rel:
                add("Download Logs", log_rel, css="btn-outline-warning")
        return entries

    _spashiny_ctx._cloud_result_download_links = _cloud_result_download_links

    def _cloud_river_figure_previews(session_id, job):
        """Render published River PNGs without exposing an owner-only image URL."""
        analysis_session_id = str(_spashiny_ctx._cloud_analysis_session_id() or "")
        if (
            str(getattr(job, "status", "")).lower() != "succeeded"
            or not analysis_session_id
            or str(getattr(job, "analysis_session_id", "") or "") != analysis_session_id
            or (str(getattr(job, "session_id", "") or "") != str(session_id or ""))
        ):
            return []
        manifest = _spashiny_ctx._cloud_result_manifest(job)
        files = manifest.get("files") if isinstance(manifest, dict) else None
        if not isinstance(files, list):
            return []
        published = {
            str(item.get("path") or ""): item
            for item in files
            if isinstance(item, dict) and str(item.get("path") or "")
        }
        cards = []
        for rel_path, title, description in (
            (
                "river_combined_plot.png",
                "Combined spatial map",
                "Samples arranged in the selected time order.",
            ),
            (
                "river_selected_gene_temporal.png",
                "Representative gene over time",
                "Mean expression with uncertainty across the selected time points.",
            ),
            (
                "river_selected_gene_spatial.png",
                "Representative gene spatial map",
                "One shared expression color scale across all time points.",
            ),
        ):
            if rel_path not in published:
                continue
            url = _spashiny_ctx._cloud_result_preview_url(
                session_id, analysis_session_id, job.job_id, rel_path
            )
            if not url:
                continue
            cards.append(
                _spashiny_ctx.ui.div(
                    _spashiny_ctx.ui.h5(title),
                    _spashiny_ctx.ui.p(description, class_="cloud-muted"),
                    _spashiny_ctx.ui.div(
                        "Loading figure…",
                        class_="cloud-muted",
                        style="min-height:180px;display:flex;align-items:center;justify-content:center;background:#f8fafc;border-radius:8px;",
                        **{
                            "data-spashiny-river-preview": "1",
                            "data-spashiny-river-preview-url": url,
                            "data-spashiny-river-preview-key": f"{job.job_id}:{rel_path}:{published[rel_path].get('sha256') or ''}",
                            "data-spashiny-river-preview-alt": title,
                        },
                    ),
                    style="padding:14px;border:1px solid #e5e7eb;border-radius:10px;margin:10px 0;",
                )
            )
        return [_spashiny_ctx.ui.div(_spashiny_ctx.ui.h4("River figures"), *cards)] if cards else []

    _spashiny_ctx._cloud_river_figure_previews = _cloud_river_figure_previews
    _spashiny_globals.river_st_module_server(
        _spashiny_ctx.input,
        _spashiny_ctx.output,
        _spashiny_ctx.session,
        session_record_provider=_spashiny_ctx._cloud_session_record,
        analysis_session_id_provider=_spashiny_ctx._cloud_analysis_session_id,
        result_links_builder=_spashiny_ctx._cloud_result_download_links,
        result_previews_builder=_spashiny_ctx._cloud_river_figure_previews,
    )
    _spashiny_globals.sm_tic_roi_module_server(
        _spashiny_ctx.input,
        _spashiny_ctx.output,
        _spashiny_ctx.session,
        session_record_provider=_spashiny_ctx._cloud_session_record,
        analysis_session_id_provider=_spashiny_ctx._cloud_analysis_session_id,
        result_json_reader=_spashiny_ctx._cloud_result_json,
        download_url_builder=_spashiny_ctx._cloud_result_download_url,
    )


_STEPS = (_install_0,)


def server(_spashiny_ctx, step=0):
    return _STEPS[step](_spashiny_ctx)
