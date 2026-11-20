# Extracted from /app/app/ST-SM.py. Feature: metabolite_annotation; ordered phases preserve original initialization.
from spashiny._shared import runtime_globals as _spashiny_globals


def _install_0(_spashiny_ctx):

    def _metabolite_annotation_parameters(*, example_id=""):
        try:
            tolerance_ppm = float(_spashiny_ctx.input.metabolite_annotation_tolerance_ppm() or 5)
        except Exception:
            tolerance_ppm = 5.0
        try:
            raw_adduct = str(_spashiny_ctx.input.metabolite_annotation_adduct() or "add:H")
        except Exception:
            raw_adduct = "add:H"
        adduct_method, separator, adduct_type = raw_adduct.partition(":")
        if separator != ":" or adduct_method not in {"add", "sub"} or (not adduct_type):
            adduct_method, adduct_type = ("add", "H")
        params = {
            "adduct_method": adduct_method,
            "adduct_type": adduct_type,
            "tolerance_ppm": max(0.1, min(100.0, tolerance_ppm)),
        }
        if example_id:
            params["input_origin"] = example_id
        return params

    _spashiny_ctx._metabolite_annotation_parameters = _metabolite_annotation_parameters

    def _resolve_metabolite_annotation_input(reference):
        """Resolve exactly one tab-scoped annotation input before submission."""
        if not isinstance(reference, dict):
            raise RuntimeError("Please upload an SM H5AD or select the Y7_T SM example first.")
        session_record = _spashiny_ctx._cloud_session_record()
        analysis_session_id = str(_spashiny_ctx._cloud_analysis_session_id() or "").strip()
        if session_record is None or not analysis_session_id:
            raise RuntimeError(
                "The current tab analysis session is not ready. Please wait and try again."
            )
        from cloud.input_resolver import InputResolver

        source = str(reference.get("source") or "").strip()
        if source == "upload":
            return InputResolver().resolve_interactive_local_input(
                session_id=session_record.session_id,
                analysis_session_id=analysis_session_id,
                upload_id=str(reference.get("upload_id") or ""),
                workflow_name="metabolite_annotation",
            )
        if source == "example":
            return InputResolver().resolve_interactive_local_input(
                session_id=session_record.session_id,
                analysis_session_id=analysis_session_id,
                action_id="y7-sm-metabolite-annotation-example",
                input_role="sm_qc_input_h5ad",
                workflow_name="metabolite_annotation",
            )
        raise RuntimeError("The selected Metabolite Annotation input source is invalid.")

    _spashiny_ctx._resolve_metabolite_annotation_input = _resolve_metabolite_annotation_input

    def _metabolite_annotation_input_parameters(resolved):
        """Persist safe source provenance in the job parameters, never a server path."""
        source = str(resolved.get("input_source_mode") or "").strip() or "UNKNOWN"
        reference_id = str(resolved.get("upload_id") or resolved.get("action_id") or "").strip()
        return {
            "source_mode": source,
            "input_reference": reference_id,
            "input_filename": str(resolved.get("filename") or ""),
            "input_sha256": str(resolved.get("sha256") or ""),
            "input_size_bytes": int(resolved.get("size_bytes") or 0),
            "analysis_session_id": str(_spashiny_ctx._cloud_analysis_session_id() or ""),
            "backend": "SpatialMETA",
        }

    _spashiny_ctx._metabolite_annotation_input_parameters = _metabolite_annotation_input_parameters

    def _submit_metabolite_annotation_upload(resolved):
        session_record = _spashiny_ctx._cloud_session_record()
        analysis_session_id = str(_spashiny_ctx._cloud_analysis_session_id() or "").strip()
        upload_id = str(resolved.get("upload_id") or "").strip()
        if session_record is None or not analysis_session_id or (not upload_id):
            raise RuntimeError("The completed annotation upload is not available to this tab.")
        from cloud.job_submission import JobSubmissionService

        parameters = _spashiny_ctx._metabolite_annotation_parameters()
        parameters.update(_spashiny_ctx._metabolite_annotation_input_parameters(resolved))
        job = JobSubmissionService().submit(
            session=session_record,
            workflow_name="metabolite_annotation",
            input_upload_ids=[upload_id],
            parameters=parameters,
            requested_resource="cpu",
            analysis_session_id=analysis_session_id,
        )
        _spashiny_ctx.metabolite_annotation_status_msg.set(
            f"Submitted SpatialMETA metabolite_annotation: {job.job_id} ({job.status})"
        )
        return job

    _spashiny_ctx._submit_metabolite_annotation_upload = _submit_metabolite_annotation_upload


def _install_1(_spashiny_ctx):

    def _metabolite_annotation_preview_ui(job, *, max_rows=25, max_columns=12):
        """Render a bounded preview of the worker-written SpatialMETA table only."""
        workspace = _spashiny_ctx.Path(str(getattr(job, "local_workspace", "") or "")).resolve()
        target = (workspace / "metabolite_annotations.csv").resolve()
        if (
            not workspace
            or (target != workspace and workspace not in target.parents)
            or (not target.is_file())
        ):
            return None
        try:
            table = _spashiny_ctx.pd.read_csv(target, nrows=max_rows)
        except Exception:
            return None
        if table.empty:
            return _spashiny_ctx.ui.tags.div(
                "SpatialMETA returned no candidate rows for these settings.", class_="cloud-muted"
            )
        columns = [str(column) for column in table.columns[:max_columns]]
        header = _spashiny_ctx.ui.tags.tr(*[_spashiny_ctx.ui.tags.th(column) for column in columns])
        body_rows = []
        for _, row in table.loc[:, columns].iterrows():
            values = []
            for column in columns:
                value = row[column]
                values.append("" if _spashiny_ctx.pd.isna(value) else str(value))
            body_rows.append(
                _spashiny_ctx.ui.tags.tr(*[_spashiny_ctx.ui.tags.td(value) for value in values])
            )
        return _spashiny_ctx.ui.tags.div(
            _spashiny_ctx.ui.tags.h5(f"SpatialMETA annotation preview (first {len(table)} rows)"),
            _spashiny_ctx.ui.tags.div(
                _spashiny_ctx.ui.tags.table(
                    _spashiny_ctx.ui.tags.thead(header),
                    _spashiny_ctx.ui.tags.tbody(*body_rows),
                    class_="table table-sm table-striped",
                ),
                style="overflow-x:auto;",
            ),
            class_="apple-card",
        )

    _spashiny_ctx._metabolite_annotation_preview_ui = _metabolite_annotation_preview_ui

    def _metabolite_annotation_job_result_ui(job_id):
        job_id = str(job_id or "").strip()
        if not job_id:
            return _spashiny_ctx.ui.tags.div(
                _spashiny_ctx.ui.tags.p(
                    "No Metabolite Annotation job submitted in this page yet.", class_="cloud-muted"
                )
            )
        session_id = _spashiny_ctx._cloud_session_id()
        analysis_session_id = _spashiny_ctx._cloud_analysis_session_id()
        if not session_id or not analysis_session_id:
            return _spashiny_ctx.ui.tags.div(
                _spashiny_ctx.ui.tags.p(
                    "Session is initializing. Job status will appear after the session is ready.",
                    class_="cloud-muted",
                )
            )
        try:
            from cloud.job_manager import JobManager

            job = JobManager().get_job_for_session(
                session_id, job_id, analysis_session_id=analysis_session_id
            )
        except Exception as exc:
            return _spashiny_ctx.ui.tags.div(
                _spashiny_ctx.ui.tags.p(
                    f"Job is not visible in this session: {exc}", class_="cloud-muted"
                )
            )
        status = str(job.status or "")
        try:
            from cloud.models import ACTIVE_JOB_STATUSES

            active_statuses = {str(item).lower() for item in ACTIVE_JOB_STATUSES}
        except Exception:
            active_statuses = {
                "queued_cpu",
                "queued_gpu",
                "queued",
                "running",
                "created",
                "packaging",
                "postprocessing",
                "verifying",
                "syncing",
            }
        if status.lower() in active_statuses:
            _spashiny_ctx.reactive.invalidate_later(2)
        rows = [
            _spashiny_ctx.ui.tags.strong(f"{job.workflow_name or job.workflow}: {status}"),
            _spashiny_ctx.ui.tags.div(f"Job ID: {job.job_id}", class_="cloud-muted"),
            _spashiny_ctx.ui.tags.div(
                f"Progress: {float(job.progress or 0):.1f}% | Step: {job.current_step or 'Waiting'}",
                class_="cloud-muted",
            ),
        ]
        if status.lower() in {"failed", "cancelled", "timed_out", "not_enabled", "queue_full"}:
            rows.append(
                _spashiny_globals._job_error_ui(
                    job, title=f"{job.workflow_name or job.workflow} did not complete"
                )
            )
        if status.lower() in {"succeeded", "completed"}:
            summary = _spashiny_ctx._cloud_result_json(job, "annotation_summary.json")
            if not summary:
                manifest = _spashiny_ctx._cloud_result_manifest(job)
                summary = manifest.get("summary") if isinstance(manifest, dict) else {}
            if isinstance(summary, dict):
                rows.append(
                    _spashiny_ctx.ui.tags.div(
                        f"SM features: {summary.get('input_feature_count', 0)} | Annotation rows: {summary.get('annotation_rows', 0)} | Adduct: {summary.get('adduct_method', '')} {summary.get('adduct_type', '')} | Tolerance: {summary.get('tolerance_ppm', '')} ppm",
                        class_="cloud-muted",
                    )
                )
            preview = _spashiny_ctx._metabolite_annotation_preview_ui(job)
            if preview is not None:
                rows.append(preview)
            link_specs = [
                (
                    "Download SpatialMETA Annotation CSV",
                    "metabolite_annotations.csv",
                    "btn-primary",
                ),
                ("Download Annotated SM H5AD", "annotated_result.h5ad", "btn-outline-primary"),
                ("Download Summary JSON", "annotation_summary.json", "btn-outline-secondary"),
                ("Download Result ZIP", "results.zip", "btn-success"),
                ("Download Manifest JSON", "result_manifest.json", "btn-outline-secondary"),
            ]
            links = [
                link
                for label, path, css in link_specs
                for link in [
                    _spashiny_ctx._enrichment_artifact_link(session_id, job, label, path, css=css)
                ]
                if link is not None
            ]
            rows.append(
                _spashiny_ctx.ui.tags.div(*links, class_="cloud-result-downloads")
                if links
                else _spashiny_ctx.ui.tags.div(
                    "No downloadable artifacts were found.", class_="cloud-muted"
                )
            )
        return _spashiny_ctx.ui.tags.div(*rows, class_="cloud-row")

    _spashiny_ctx._metabolite_annotation_job_result_ui = _metabolite_annotation_job_result_ui


def _install_2(_spashiny_ctx):

    @_spashiny_ctx.output
    @_spashiny_ctx.render.ui
    def metabolite_annotation_mz_column_selector():
        columns = []
        return _spashiny_ctx._enrichment_column_select_ui(
            "metabolite_annotation_mz_column",
            "m/z column",
            columns,
            ["mz", "m/z", "mass_to_charge", "feature_mz"],
            "mz",
            "CSV/TSV uploads use this column. H5AD/imzML inputs use their embedded m/z values.",
        )

    _spashiny_ctx.metabolite_annotation_mz_column_selector = (
        metabolite_annotation_mz_column_selector
    )


def _install_3(_spashiny_ctx):

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.run_metabolite_annotation_csv)
    def _run_metabolite_annotation_csv():
        try:
            resolved = _spashiny_ctx._resolve_metabolite_annotation_input(
                _spashiny_ctx.metabolite_annotation_input_reference.get()
            )
            if str(resolved.get("input_source_mode") or "") != "USER_UPLOAD":
                raise RuntimeError(
                    "Current input is not an uploaded SM H5AD. Use the Y7_T example button for the example source."
                )
            if _spashiny_ctx.Path(str(resolved.get("filename") or "")).suffix.lower() != ".h5ad":
                raise RuntimeError("Metabolite Annotation accepts an SM H5AD file only.")
            job = _spashiny_ctx._submit_metabolite_annotation_upload(resolved)
            _spashiny_ctx.metabolite_annotation_job_id.set(job.job_id)
            _spashiny_ctx.ui.notification_show(
                f"Uploaded SM annotation submitted: {job.job_id}", type="message", duration=6
            )
        except Exception as exc:
            error_msg = _spashiny_globals.user_facing_error(
                "Metabolite annotation submit failed", exc
            )
            _spashiny_ctx.metabolite_annotation_status_msg.set(error_msg)
            _spashiny_ctx.ui.notification_show(error_msg, type="error", duration=10)

    _spashiny_ctx._run_metabolite_annotation_csv = _run_metabolite_annotation_csv

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.metabolite_annotation_canonical_upload)
    def _track_metabolite_annotation_canonical_upload():
        if not _spashiny_globals.SPASHINY_WEB_PLATFORM:
            return
        try:
            payload = _spashiny_ctx.input.metabolite_annotation_canonical_upload() or {}
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            return
        status = str(payload.get("status") or "").upper()
        filename = str(payload.get("filename") or "uploaded SM h5ad")
        if status == "READY":
            upload_id = str(payload.get("upload_id") or "").strip()
            if not upload_id:
                _spashiny_ctx.metabolite_annotation_status_msg.set(
                    "Metabolite annotation upload failed: completion returned no upload reference."
                )
                return
            try:
                resolved = _spashiny_ctx._resolve_metabolite_annotation_input(
                    {"source": "upload", "upload_id": upload_id}
                )
            except Exception as exc:
                _spashiny_ctx.metabolite_annotation_input_reference.set(None)
                _spashiny_ctx.metabolite_annotation_status_msg.set(
                    f"Metabolite annotation upload is not available to this tab: {exc}"
                )
                return
            _spashiny_ctx.metabolite_annotation_input_reference.set(
                {"source": "upload", "upload_id": upload_id, "filename": resolved["filename"]}
            )
            _spashiny_ctx.metabolite_annotation_status_msg.set(
                f"Current input: Uploaded file — {resolved['filename']}. Ready to run SpatialMETA Annotation."
            )
        elif status == "FAILED":
            _spashiny_ctx.metabolite_annotation_input_reference.set(None)
            _spashiny_ctx.metabolite_annotation_status_msg.set(
                _spashiny_globals._upload_failure_text(
                    payload, filename, "Metabolite annotation upload"
                )
            )

    _spashiny_ctx._track_metabolite_annotation_canonical_upload = (
        _track_metabolite_annotation_canonical_upload
    )


def _install_4(_spashiny_ctx):

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.run_metabolite_annotation_y7t)
    def _run_metabolite_annotation_y7t():
        try:
            action_id = _spashiny_ctx._bind_builtin_sm_annotation_example()
            _spashiny_ctx.metabolite_annotation_input_reference.set(
                {"source": "example", "action_id": action_id}
            )
            resolved = _spashiny_ctx._resolve_metabolite_annotation_input(
                _spashiny_ctx.metabolite_annotation_input_reference.get()
            )
            parameters = _spashiny_ctx._metabolite_annotation_parameters(example_id="Y7_T SM H5AD")
            parameters.update(_spashiny_ctx._metabolite_annotation_input_parameters(resolved))
            job = _spashiny_ctx._submit_cloud_example_action_job(
                workflow_name="metabolite_annotation",
                example_action_ids=(action_id,),
                parameters=parameters,
                requested_resource="cpu",
            )
            _spashiny_ctx.metabolite_annotation_job_id.set(job.job_id)
            _spashiny_ctx.metabolite_annotation_status_msg.set(
                f"Submitted SpatialMETA metabolite_annotation: {job.job_id} ({job.status})"
            )
            _spashiny_ctx.ui.notification_show(
                f"Y7_T metabolite annotation submitted: {job.job_id}", type="message", duration=6
            )
        except Exception as exc:
            error_msg = _spashiny_globals.user_facing_error(
                "Y7_T metabolite annotation submit failed", exc
            )
            _spashiny_ctx.metabolite_annotation_status_msg.set(error_msg)
            _spashiny_ctx.ui.notification_show(error_msg, type="error", duration=10)

    _spashiny_ctx._run_metabolite_annotation_y7t = _run_metabolite_annotation_y7t

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(
        _spashiny_ctx.input.cloud_example_action_activated, ignore_none=True
    )
    def _select_metabolite_annotation_example_from_cloud_action():
        if not _spashiny_globals.SPASHINY_WEB_PLATFORM:
            return
        try:
            payload = _spashiny_ctx.input.cloud_example_action_activated() or {}
        except Exception:
            payload = {}
        if (
            not isinstance(payload, dict)
            or str(payload.get("action_id") or "") != "y7-sm-metabolite-annotation-example"
            or (not bool(payload.get("ready")))
        ):
            return
        _spashiny_ctx.metabolite_annotation_input_reference.set(
            {"source": "example", "action_id": "y7-sm-metabolite-annotation-example"}
        )
        _spashiny_ctx.metabolite_annotation_status_msg.set(
            "Current input: Example — Y7_T SM H5AD. Ready to run SpatialMETA Annotation."
        )

    _spashiny_ctx._select_metabolite_annotation_example_from_cloud_action = (
        _select_metabolite_annotation_example_from_cloud_action
    )


def _install_5(_spashiny_ctx):

    @_spashiny_ctx.output
    @_spashiny_ctx.render.text
    def metabolite_annotation_status():
        return _spashiny_ctx.metabolite_annotation_status_msg.get()

    _spashiny_ctx.metabolite_annotation_status = metabolite_annotation_status

    @_spashiny_ctx.output
    @_spashiny_ctx.render.ui
    def metabolite_annotation_current_input():
        """Render the single active annotation source without exposing server paths."""
        reference = _spashiny_ctx.metabolite_annotation_input_reference.get()
        if not isinstance(reference, dict):
            return _spashiny_ctx.ui.tags.div(
                "Current input: none selected.",
                class_="cloud-muted",
                style="font-size: 12px; margin-top: 8px;",
            )
        if str(reference.get("source") or "") == "upload":
            return _spashiny_ctx.ui.tags.div(
                f"Current input: Uploaded file — {reference.get('filename') or 'SM H5AD'}.",
                class_="cloud-muted",
                style="font-size: 12px; margin-top: 8px;",
            )
        if str(reference.get("source") or "") == "example":
            return _spashiny_ctx.ui.tags.div(
                "Current input: Example — Y7_T SM H5AD.",
                class_="cloud-muted",
                style="font-size: 12px; margin-top: 8px;",
            )
        return _spashiny_ctx.ui.tags.div(
            "Current input: none selected.",
            class_="cloud-muted",
            style="font-size: 12px; margin-top: 8px;",
        )

    _spashiny_ctx.metabolite_annotation_current_input = metabolite_annotation_current_input


def _install_6(_spashiny_ctx):

    @_spashiny_ctx.output
    @_spashiny_ctx.render.ui
    def metabolite_annotation_job_results():
        return _spashiny_ctx._metabolite_annotation_job_result_ui(
            _spashiny_ctx.metabolite_annotation_job_id.get()
        )

    _spashiny_ctx.metabolite_annotation_job_results = metabolite_annotation_job_results


def _install_7(_spashiny_ctx):

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.show_metabolite_annotation)
    def _on_show_metabolite_annotation():
        _spashiny_ctx.current_module.set("SpatialMETA Metabolite Annotation")

    _spashiny_ctx._on_show_metabolite_annotation = _on_show_metabolite_annotation


_STEPS = (
    _install_0,
    _install_1,
    _install_2,
    _install_3,
    _install_4,
    _install_5,
    _install_6,
    _install_7,
)


def server(_spashiny_ctx, step=0):
    return _STEPS[step](_spashiny_ctx)
