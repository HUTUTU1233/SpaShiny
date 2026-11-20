from __future__ import annotations

import math
from pathlib import Path

from shiny import reactive, render, ui


WORKFLOW = "river_spatial_transcriptomics"


def river_st_module_ui():
    return ui.div(
        ui.h2("Spatial Transcriptomics River"),
        ui.p("Run the River spatial-transcriptomics ranking workflow across two or more ST samples.", class_="cloud-muted"),
        ui.div(
            ui.h4("Input samples"),
            ui.input_file("river_st_h5_files", "Spatial-transcriptomics files (.h5ad or .h5)", accept=[".h5ad", ".h5"], multiple=True),
            ui.input_file("river_st_csv_files", "Optional annotation CSV files", accept=[".csv"], multiple=True),
            ui.input_text("river_st_sample_labels", "Sample labels (optional, comma-separated)", placeholder="Leave blank to use filenames"),
            ui.input_numeric("river_st_subsample", "Unified subsampling size", value=6000, min=500, max=50000, step=500),
            ui.input_numeric("river_st_epochs", "River training epochs", value=100, min=10, max=1000, step=10),
            ui.input_action_button("river_st_preview", "Validate inputs", class_="btn btn-secondary"),
            ui.input_action_button("river_st_submit", "Run Spatial Transcriptomics River", class_="btn btn-primary"),
            ui.div(ui.output_text("river_st_status"), class_="cloud-muted", style="margin-top: 12px;"),
            ui.output_ui("river_st_preview_result"),
            class_="apple-card",
        ),
        ui.div(ui.h4("River jobs"), ui.output_ui("river_st_jobs"), class_="apple-card", style="margin-top: 16px;"),
    )


def river_st_module_server(input, output, session, *, session_record_provider, analysis_session_id_provider, result_links_builder):
    status = reactive.Value("Select at least two spatial-transcriptomics files to begin.")
    preview = reactive.Value("")

    def _files(input_id):
        try:
            return list(getattr(input, input_id)() or [])
        except Exception:
            return []

    def _validate_files():
        data_files = _files("river_st_h5_files")
        csv_files = _files("river_st_csv_files")
        if len(data_files) < 2:
            raise ValueError("Select at least two .h5ad or .h5 spatial-transcriptomics files.")
        invalid = []
        for item in data_files:
            name = str(item.get("name") or "")
            path = Path(str(item.get("datapath") or ""))
            if path.suffix.lower() not in {".h5ad", ".h5"} or not path.is_file() or path.stat().st_size <= 0:
                invalid.append(name or "unavailable file")
        for item in csv_files:
            name = str(item.get("name") or "")
            path = Path(str(item.get("datapath") or ""))
            if path.suffix.lower() != ".csv" or not path.is_file() or path.stat().st_size <= 0:
                invalid.append(name or "unavailable annotation")
        if invalid:
            raise ValueError("Invalid or unavailable files: " + ", ".join(invalid))
        labels = [item.strip() for item in str(input.river_st_sample_labels() or "").split(",") if item.strip()]
        if labels and len(labels) != len(data_files):
            raise ValueError("The number of comma-separated sample labels must equal the number of ST files.")
        return data_files, csv_files, labels

    def _register_upload(file_entry):
        from cloud.upload_service import UploadPart, UploadService

        session_record = session_record_provider()
        if session_record is None:
            raise RuntimeError("Cloud session is not ready. Wait briefly, then try again.")
        data_path = Path(str(file_entry.get("datapath") or ""))
        filename = str(file_entry.get("name") or data_path.name)
        size_bytes = data_path.stat().st_size
        service = UploadService()
        if not hasattr(service.storage, "put_part"):
            raise RuntimeError("The configured storage backend cannot register Shiny uploads for River.")
        part_size = int(service.config.r2_multipart_part_size_bytes)
        upload = service.initiate_upload(
            session=session_record,
            filename=filename,
            size_bytes=size_bytes,
            content_type="text/csv" if data_path.suffix.lower() == ".csv" else "application/octet-stream",
            total_parts=max(1, math.ceil(size_bytes / part_size)),
        )
        record = service.database.get_upload(str(upload["upload_id"]), session_id=session_record.session_id)
        parts = []
        with data_path.open("rb") as handle:
            part_number = 1
            while chunk := handle.read(part_size):
                etag = service.storage.put_part(record.multipart_upload_id, part_number, chunk)
                parts.append(UploadPart(part_number=part_number, etag=etag))
                part_number += 1
        return service.complete_upload(session=session_record, upload_id=record.upload_id, parts=parts)

    @reactive.Effect
    @reactive.event(input.river_st_preview)
    def _preview():
        try:
            data_files, csv_files, labels = _validate_files()
            names = labels or [str(item.get("name") or "") for item in data_files]
            preview.set(f"Validation passed: {len(data_files)} ST sample(s), {len(csv_files)} optional annotation CSV file(s). Labels: {', '.join(names)}")
            status.set("Inputs are valid. No analysis has been submitted.")
        except Exception as exc:
            preview.set("")
            status.set(f"Validation failed: {exc}")

    @output
    @render.ui
    def river_st_preview_result():
        value = preview.get()
        return ui.tags.p(value, class_="cloud-muted") if value else None

    @output
    @render.text
    def river_st_status():
        return status.get()

    @reactive.Effect
    @reactive.event(input.river_st_submit)
    def _submit():
        try:
            data_files, csv_files, labels = _validate_files()
            session_record = session_record_provider()
            if session_record is None:
                raise RuntimeError("Cloud session is not ready. Wait briefly, then try again.")
            analysis_session_id = analysis_session_id_provider()
            if not analysis_session_id:
                raise RuntimeError("Analysis session is not ready. Wait briefly, then try again.")
            upload_ids = [_register_upload(item).upload_id for item in [*data_files, *csv_files]]
            from cloud.job_submission import JobSubmissionService

            job = JobSubmissionService().submit(
                session=session_record,
                workflow_name=WORKFLOW,
                input_upload_ids=upload_ids,
                parameters={
                    "sample_labels": ",".join(labels),
                    "subsample_size": int(input.river_st_subsample() or 6000),
                    "river_epochs": int(input.river_st_epochs() or 100),
                    "random_seed": 42,
                },
                requested_resource="cpu",
                analysis_session_id=analysis_session_id,
            )
            status.set(f"River job submitted: {job.job_id} ({job.status}). It continues if the browser reconnects.")
        except Exception as exc:
            status.set(f"River submission failed: {exc}")

    @output
    @render.ui
    def river_st_jobs():
        reactive.invalidate_later(2)
        session_record = session_record_provider()
        if session_record is None:
            return ui.tags.p("Waiting for cloud session initialization.", class_="cloud-muted")
        try:
            from cloud.database import CloudDatabase

            jobs = [job for job in CloudDatabase().list_jobs(session_id=session_record.session_id, limit=30) if str(job.workflow_name or job.workflow) == WORKFLOW]
        except Exception as exc:
            return ui.tags.p(f"River job status is temporarily unavailable: {exc}", class_="cloud-muted")
        if not jobs:
            return ui.tags.p("No River job has been submitted in this cloud session.", class_="cloud-muted")
        rows = []
        for job in jobs[:5]:
            links = result_links_builder(session_record.session_id, job) if str(job.status).lower() == "succeeded" else []
            rows.append(ui.div(ui.tags.strong(str(job.status)), " — ", str(job.job_id), ui.tags.div(str(job.current_step or ""), class_="cloud-muted"), ui.div(*links), style="padding: 8px 0; border-bottom: 1px solid #e5e7eb;"))
        return ui.div(*rows)
