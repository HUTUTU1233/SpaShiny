"""One explicit source and one accepted CPU result for the whole KNN page."""
import base64
import hashlib
import json
import math
from pathlib import Path

from shiny import reactive, render, ui
from cloud.knn_results import read_scoped_result
from cloud.knn_tutorial import ACTION, POLICY, THRESHOLD, example_parameters

WORKFLOW = "integration_postprocessing"
PENDING = {"QUEUED_CPU", "QUEUED", "CLAIMED", "DOWNLOADING", "RUNNING", "PACKAGING", "POSTPROCESSING", "VERIFYING", "SYNCING"}
UPLOAD_MODE = "USER_UPLOAD_ALIGNED_PAIR"


def _qc_result_line(title, record, *, example, units, pending, source_label=""):
    """Describe the applied filter from its report, never from an editor value."""
    if not record:
        policy = f"Fixed example threshold: {THRESHOLD:,.0f}. " if example else ""
        return ui.p(ui.strong(title + ": "), policy + pending, class_="small mt-2")
    threshold = float(record["min_total_intensity"])
    value = f"{int(threshold):,}" if threshold.is_integer() else f"{threshold:,}"
    if "before_shape" in record:
        before, after = record["before_shape"][0], record["after_shape"][0]
    else:
        before, after = record["before_observations"], record["after_observations"]
    removed = record["removed_observations"]
    return ui.p(ui.strong(title + ": "),
        f"Applied threshold: {value}. {before:,} → {after:,} {units}; removed {removed:,}. {source_label}",
        class_="small mt-2")


class KNNInputBridge:
    def __init__(self, *, input, output, session, get_owner, get_analysis, get_source, set_source,
                 get_alignment, get_binding, submit_example, set_example_job, set_upload_job, current_module, log):
        self.input, self.session = input, session
        self.get_owner, self.get_analysis = get_owner, get_analysis
        self.get_source, self.set_source = get_source, set_source
        self.get_alignment, self.get_binding, self.submit_example = get_alignment, get_binding, submit_example
        self.set_example_job, self.set_upload_job, self.log = set_example_job, set_upload_job, log
        for name, value in (("qc_job", ""), ("run_job", ""), ("qc_key", ""), ("run_key", ""),
                ("result_job", ""), ("result_key", ""), ("report", None), ("result", None),
                ("status", {}), ("uploads", {}), ("upload_nonces", {}), ("refresh", 0)):
            setattr(self, name, reactive.Value(value))
        self.logged, self.restore_errors = set(), {}

        @reactive.Effect
        def _poll_knn_inputs():
            if current_module() != "ST-SM Reassignment":
                return
            for purpose, job_id, key in (("qc", self.qc_job.get(), self.qc_key.get()), ("knn", self.run_job.get(), self.run_key.get())):
                if not job_id:
                    continue
                try:
                    if self.source()["key"] != key:
                        self.clear_results()
                        self.log("KNN source changed. Old QC, figures and downloads were cleared; select and process the new input explicitly.")
                        return
                    job = self.job(job_id)
                    state = str(job.status).upper()
                    status = dict(self.status.get())
                    value = {"job_id": job_id, "status": state, "message": str(job.error_message or "")}
                    if status.get(purpose) != value:
                        status[purpose] = value
                        self.status.set(status)
                    if state in PENDING:
                        reactive.invalidate_later(2)
                    elif (job_id, state) not in self.logged:
                        if state == "SUCCEEDED":
                            name = "knn_input_inspection.json" if purpose == "qc" else "knn_summary.json"
                            target = self.artifact(job_id, key, name)
                            if target.stat().st_size > 512 * 1024:
                                raise ValueError("KNN display metadata is too large.")
                            report = json.loads(target.read_text())
                            if purpose == "qc":
                                if (report.get("job_id") != job_id or report.get("owner_session_id") != self.owner_id()
                                        or report.get("analysis_session_id") != self.get_analysis()):
                                    raise ValueError("The KNN inspection belongs to a different analysis.")
                                self.report.set(report)
                                qc = report["initial_sm_qc"]
                                self.log(f"KNN input QC completed: ST {report['st']['shape']}; SM {qc['before_shape']} -> {qc['after_shape']}; threshold={qc['min_total_intensity']:g}; job={job_id}.")
                            else:
                                self.check_quality(report, job_id)
                                self.result.set(report)
                                self.result_job.set(job_id)
                                self.result_key.set(key)
                                source = self.source()["source_mode"]
                                self.set_example_job(job_id if source == "EXAMPLE" else None)
                                self.set_upload_job(job_id if source == "USER_UPLOAD_ALIGNMENT" else None)
                                quality = report["quality"]
                                self.log(f"KNN result ready: {job_id}; ST {report['st_output_shape']}, SM {report['sm_output_shape']}; non-zero SM values={quality['sm']['nonzero_values']}; matched ST={report['spatial_coverage']['st_with_sm_neighbor']}. Figures, post-filter and downloads now use this exact result.")
                            ui.notification_show("KNN input QC completed." if purpose == "qc" else "KNN result and quality checks completed.", type="message")
                        else:
                            self.log(f"KNN {purpose} failed: {job.error_code}: {job.error_message}")
                            ui.notification_show(f"KNN {purpose} failed: {job.error_message}", type="error", duration=10)
                        self.logged.add((job_id, state))
                except Exception as exc:
                    self.restore_errors[job_id] = self.restore_errors.get(job_id, 0) + 1
                    if (job_id, str(exc)) not in self.logged:
                        self.logged.add((job_id, str(exc)))
                        self.log(f"KNN restore failed: {type(exc).__name__}: {exc}")
                        ui.notification_show(str(exc), type="error", duration=10)
                    if self.restore_errors[job_id] <= 5:
                        reactive.invalidate_later(3)

        @output
        @render.ui
        def knn_input_worker_status():
            mode = str(get_source() or "")
            lines = [ui.p("Current input: " + (mode or "Not selected"))]
            if mode == "EXAMPLE":
                lines.append(ui.p("SpatialMETA tutorial: complete Raw SM expression, official aligned coordinates, K=5, dist_fold=1.5."))
            if mode == UPLOAD_MODE:
                for kind in ("st", "sm"):
                    ref = self.uploads.get().get(kind)
                    lines.append(ui.p(kind.upper() + ": " + (ref["filename"] if ref else "Upload not ready")))
            for purpose, state in self.status.get().items():
                lines.append(ui.p(f"{purpose.upper()}: {state['status']} - {state['job_id']}"))
                if state["message"]:
                    lines.append(ui.p(state["message"], class_="text-danger"))
            report = self.report.get()
            if report:
                lines.append(ui.p(f"Prepared inputs: ST {report['st']['shape']}; SM {report['sm']['shape']}."))
            return ui.div(*lines)

        @output
        @render.ui
        def knn_pre_qc_result():
            result, inspection = self.result.get(), self.report.get()
            report = result if result is not None else inspection
            return _qc_result_line("Pre-KNN SM filter", (report or {}).get("initial_sm_qc"),
                example=get_source() == "EXAMPLE", units="SM pixels",
                pending="Not applied to this KNN result." if result is not None else "No pre-KNN filter result yet.",
                source_label="Last completed KNN result." if result is not None else "Last completed QC or preview.")

        @output
        @render.ui
        def knn_post_qc_result():
            result = self.result.get()
            example = get_source() == "EXAMPLE"
            return _qc_result_line("Post-KNN SM filter", (result or {}).get("post_filter"),
                example=example, units="reassigned positions", source_label="Last completed KNN result.",
                pending=("Applied automatically by the example reassignment; no result yet." if example
                         else "Not applied. Use Filter Reassigned SM Data after KNN."))

        @output
        @render.ui
        def knn_scaling_worker_plot():
            self.refresh.get()
            report = self.report.get()
            if not report:
                return ui.p("Select the inputs and run Scaling & Preview to display the tissue overlay.")
            relative = report.get("preview_png") or "figures/knn_input_overlay.png"
            try:
                if report.get("preview_png"):
                    scale = (report.get("coordinate_contract") or {}).get("st_tissue_hires_scalef")
                    scale_note = f"ST tissue_hires_scalef: {scale:.8g}. " if scale is not None else ""
                    image = self.image(self.artifact(self.qc_job.get(), self.qc_key.get(), relative), "SM over the ST hires tissue image")
                    return ui.div(ui.p(scale_note + "Display only; KNN still uses ST full-resolution coordinates.", class_="small text-muted"), image)
                image = self.image(self.artifact(self.qc_job.get(), self.qc_key.get(), relative), "QC overlay in ST full-resolution coordinates")
                return ui.div(ui.p("QC overlay only. Run Scaling & Preview for the tissue image.", class_="small text-muted"), image)
            except Exception as exc:
                return ui.p(str(exc), class_="text-danger")

        @output
        @render.ui
        def knn_worker_result():
            self.refresh.get()
            report = self.result.get()
            if not report:
                return ui.p("A completed, quality-validated KNN result will appear here.")
            quality = report["quality"]
            mapping = report.get("spot_mapping")
            tutorial = [
                ui.p(f"{mapping['verified_spots']:,} spots matched by original ST barcode and native KNN spot ID."),
                ui.download_button("download_knn_spot_mapping", "Download Spot Mapping JSON", class_="btn btn-outline-primary btn-sm"),
                ui.row(
                    ui.column(6, ui.h6("Reassigned SM — total_intensity"), self.result_image("figures/knn_sm_total_intensity.png", "Reassigned SM total_intensity on the ST tissue image")),
                    ui.column(6, ui.h6("QC ST — total_counts"), self.result_image("figures/knn_st_total_counts.png", "Original QC ST total_counts on the ST tissue image")),
                    class_="mt-3",
                ),
            ] if mapping else []
            return ui.div(ui.h5("Validated KNN worker result"),
                ui.p(f"ST {report['st_output_shape']}; SM {report['sm_output_shape']}; non-zero SM values: {quality['sm']['nonzero_values']}."),
                *tutorial,
                ui.p("Reassigned ST and SM share coordinates. Blue rings and orange centers show both modalities without shifting data."),
                self.result_image("figures/knn_reassignment_spatial.png", "KNN ST, SM and shared-position overlay"))

        @output
        @render.ui
        def knn_histogram_result():
            self.refresh.get()
            return self.result_image("figures/knn_intensity_histograms.png", "KNN SM intensity histograms") if self.result.get() else ui.p("Run KNN to view its saved intensity histograms.")

        @output
        @render.ui
        def knn_joint_result():
            self.refresh.get()
            report = self.result.get()
            if not report:
                return ui.p("Run KNN to create the native joint H5AD and spatial plots.")
            return ui.div(ui.p(f"Native joint shape: {report['joint_handoff_shape']}; source: {report['input_lineage']['source_mode']}"),
                self.result_image("figures/knn_joint_intensity.png", "Joint SM total intensity"),
                self.result_image("figures/knn_joint_counts.png", "Joint ST total counts"))

    @staticmethod
    def image(path, alt):
        return ui.tags.img(src="data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii"),
            alt=alt, style="max-width:100%;height:auto;object-fit:contain;")

    def owner_id(self):
        owner = self.get_owner()
        return str(owner.session_id if owner is not None else "")

    def clear_results(self):
        for name in ("qc_job", "run_job", "qc_key", "run_key", "result_job", "result_key"):
            getattr(self, name).set("")
        self.report.set(None)
        self.result.set(None)
        self.status.set({})
        self.set_example_job(None)
        self.set_upload_job(None)

    def reset(self):
        self.clear_results()
        self.uploads.set({})
        self.upload_nonces.set({})

    def upload_event(self, payload):
        try:
            if not isinstance(payload, dict) or payload.get("kind") not in {"st", "sm"}:
                raise ValueError("Invalid KNN upload event.")
            analysis = str(self.get_analysis() or "")
            if not analysis or payload.get("analysis_session_id") != analysis:
                raise ValueError("KNN upload belongs to a different analysis.")
            kind, nonce = payload["kind"], str(payload.get("selection_id") or "")
            if not nonce:
                raise ValueError("KNN upload selection identity is missing.")
            if payload.get("status") == "SELECTED":
                if self.get_source() != UPLOAD_MODE:
                    self.reset()
                    self.set_source(UPLOAD_MODE)
                self.clear_results()
                refs = dict(self.uploads.get()); refs.pop(kind, None); self.uploads.set(refs)
                pending = dict(self.upload_nonces.get()); pending[kind] = nonce; self.upload_nonces.set(pending)
                self.log(f"KNN {kind.upper()} upload selected. Old Example/QC/KNN results were cleared.")
                return
            if self.get_source() != UPLOAD_MODE or self.upload_nonces.get().get(kind) != nonce:
                self.log("Ignored completion from an older KNN upload selection; the current source was not replaced.")
                return
            if payload.get("status") != "READY":
                self.log("KNN upload failed: " + str(payload.get("message") or payload.get("code") or "Upload did not complete."))
                return
            from cloud.database import CloudDatabase
            upload_id = str(payload.get("upload_id") or "")
            record = CloudDatabase(read_only=True).get_upload(upload_id, session_id=self.owner_id(), analysis_session_id=analysis)
            if (record.status != "COMPLETED" or Path(record.safe_filename).suffix.lower() != ".h5ad"
                    or not record.sha256 or int(record.actual_size_bytes or 0) <= 0):
                raise ValueError("The exact uploaded H5AD is not completed and hash-verified.")
            refs = dict(self.uploads.get())
            refs[kind] = {"upload_id": upload_id, "filename": record.safe_filename, "sha256": record.sha256}
            self.uploads.set(refs)
            self.log(f"KNN {kind.upper()} upload ready: {record.safe_filename}; source remains USER_UPLOAD_ALIGNED_PAIR.")
        except Exception as exc:
            self.log(f"KNN upload rejected: {type(exc).__name__}: {exc}")
            ui.notification_show(str(exc), type="error", duration=8)

    def source(self):
        mode = str(self.get_source() or "")
        owner, analysis = self.owner_id(), str(self.get_analysis() or "")
        if not owner or not analysis:
            raise ValueError("The authenticated analysis is not ready.")
        data = {"source_mode": mode, "owner": owner, "analysis": analysis}
        if mode == "EXAMPLE":
            binding = self.get_binding() or {}
            if not binding.get("ready") or binding.get("analysis_session_id") != analysis:
                raise ValueError("Load the KNN example explicitly in this analysis.")
            data.update(binding_id=binding.get("binding_id"), asset_version=binding.get("asset_version"),
                        manifest_version=binding.get("manifest_version"), tutorial_policy=POLICY)
        elif mode == UPLOAD_MODE:
            refs = self.uploads.get()
            if not all(refs.get(kind, {}).get("upload_id") for kind in ("st", "sm")):
                raise ValueError("Complete both ST and aligned SM uploads in this analysis. No example fallback was used.")
            if refs["st"]["upload_id"] == refs["sm"]["upload_id"]:
                raise ValueError("ST and SM must be different uploaded assets.")
            data.update(uploads=refs, coordinate_policy="h5ad_metadata_only")
        elif mode == "USER_UPLOAD_ALIGNMENT":
            workflow, state = self.get_alignment()
            provenance = state.get("input_provenance") or {}
            st, sm = provenance.get("st") or {}, provenance.get("sm") or {}
            if (not workflow or str(state.get("step6_status") or "").lower() != "completed"
                    or st.get("source_mode") != "USER_UPLOAD" or sm.get("source_mode") != "USER_UPLOAD" or not st.get("reference")):
                raise ValueError("Use the completed current-analysis Alignment Step6 result from user-uploaded ST and SM.")
            data.update(workflow_id=workflow, st_upload_id=st["reference"], step6_sha256=(state.get("step6_handoff_artifact") or {}).get("sha256"))
        else:
            raise ValueError("Choose an explicit KNN Example, an uploaded aligned ST/SM pair, or the current Alignment Step6 result. No example fallback was used.")
        return {**data, "key": hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()}

    def job(self, job_id):
        from cloud.database import CloudDatabase
        from cloud.job_manager import JobManager
        return JobManager(database=CloudDatabase(read_only=True)).get_job_for_session(self.owner_id(), job_id, analysis_session_id=self.get_analysis())

    def artifact(self, job_id, key, relative):
        return read_scoped_result(owner=self.owner_id(), analysis=self.get_analysis(), job_id=job_id, key=key, relative=relative)

    def check_quality(self, report, job_id):
        quality = report.get("quality") or {}
        if (quality.get("status") != "PASS" or quality.get("job_id") != job_id
                or quality.get("analysis_session_id") != self.get_analysis()
                or any(quality.get(kind, {}).get("nonzero_values", 0) <= 0 for kind in ("st", "sm"))
                or not quality.get("same_spatial_coordinates") or not report.get("coordinate_contract")):
            raise ValueError("This KNN result has no accepted coordinate/non-zero-signal quality check. Run KNN again; older zero-filled results cannot be used.")
        if report.get("input_lineage", {}).get("source_mode") == "EXAMPLE" and report.get("tutorial_policy") != POLICY:
            raise ValueError("Reload and run the official Y7_T example to use the complete 1299-feature Raw SM result.")

    def accepted_result(self):
        scope = self.source()
        job_id, key = self.result_job.get(), self.result_key.get()
        if not job_id or key != scope["key"]:
            raise ValueError("There is no quality-validated KNN result for the current input selection.")
        report = json.loads(self.artifact(job_id, key, "knn_summary.json").read_text())
        self.check_quality(report, job_id)
        return report

    def submit(self, operation):
        try:
            source = self.source()
            if any(item.get("status") in PENDING for item in self.status.get().values()):
                raise ValueError("A KNN input/result job is still running. Wait before submitting again.")
            official = source["source_mode"] == "EXAMPLE"
            threshold = THRESHOLD if official else float(self.input.min_intensity_threshold())
            if not math.isfinite(threshold) or threshold < 0:
                raise ValueError("Initial SM intensity threshold must be finite and non-negative.")
            params = {"operation": operation, "source_mode": source["source_mode"], "knn_input_key": source["key"],
                "knn_result_contract": "r19"}
            if official:
                params.update(example_parameters())
            else:
                params.update(n_neighbors=int(self.input.spot_knn_k()), dist_fold=float(self.input.spot_dist_fold()))
            if operation in {"input_qc", "input_preview"}:
                params["initial_min_total_intensity"] = threshold
                self.clear_results()
            else:
                report = self.report.get()
                if report:
                    if self.qc_key.get() != source["key"] or report["initial_sm_qc"]["min_total_intensity"] != threshold:
                        raise ValueError("KNN source or QC threshold changed. Run input QC again.")
                    params["initial_min_total_intensity"] = threshold
                    roles = ("st", "sm", "sm_raw") if official else ("st", "sm")
                    params["initial_qc_input_sha256"] = {kind: report["inputs"][kind]["sha256"] for kind in roles}
                if operation == "postprocess":
                    parent = self.accepted_result()
                    params.update(knn_parent_job_id=self.result_job.get(), post_min_total_intensity=THRESHOLD if official else float(self.input.min_total_intensity()),
                        n_neighbors=parent["n_neighbors"], dist_fold=parent["dist_fold"])
                else:
                    self.result.set(None); self.result_job.set(""); self.result_key.set("")
                    self.set_example_job(None); self.set_upload_job(None)
            if source["source_mode"] == "EXAMPLE":
                job = self.submit_example(workflow_name=WORKFLOW, example_action_ids=(ACTION,), parameters=params, requested_resource="cpu")
            else:
                from cloud.job_submission import JobSubmissionService
                if source["source_mode"] == UPLOAD_MODE:
                    ids = [source["uploads"][kind]["upload_id"] for kind in ("st", "sm")]
                    artifacts = []
                    roles = {ids[0]: "knn_st_h5ad", ids[1]: "knn_sm_h5ad"}
                else:
                    ids = [source["st_upload_id"]]
                    artifacts = [{"parent_type": "alignment_workflow", "parent_workflow_id": source["workflow_id"], "role": "aligned_sm_h5ad"}]
                    roles = {ids[0]: "knn_st_h5ad"}
                job = JobSubmissionService().submit(session=self.get_owner(), workflow_name=WORKFLOW, input_upload_ids=ids,
                    workflow_artifacts=artifacts, parameters={**params, "input_asset_roles": roles}, requested_resource="cpu", analysis_session_id=self.get_analysis())
            if str(job.status) not in PENDING:
                raise ValueError(f"KNN job was not queued: {job.status}: {job.error_message}")
            purpose = "qc" if operation in {"input_qc", "input_preview"} else "knn"
            getattr(self, "qc_job" if purpose == "qc" else "run_job").set(job.job_id)
            getattr(self, "qc_key" if purpose == "qc" else "run_key").set(source["key"])
            status = dict(self.status.get()); status[purpose] = {"job_id": job.job_id, "status": job.status, "message": ""}; self.status.set(status)
            self.log(f"KNN {operation} submitted: {job.job_id}; source={source['source_mode']}.")
            ui.notification_show(f"KNN {operation} job submitted.", type="message")
        except Exception as exc:
            self.log(f"KNN {operation} failed: {type(exc).__name__}: {exc}")
            ui.notification_show(str(exc), type="error", duration=10)

    def result_image(self, relative, alt):
        try:
            return self.image(self.artifact(self.result_job.get(), self.result_key.get(), relative), alt)
        except Exception as exc:
            return ui.p(f"KNN figure unavailable: {exc}", class_="text-danger")

    def show_saved(self, kind):
        try:
            self.accepted_result()
            self.refresh.set(self.refresh.get() + 1)
            self.log(f"KNN {kind} restored from completed job {self.result_job.get()}; no new KNN calculation was run.")
            ui.notification_show("Saved KNN figures restored.", type="message")
        except Exception as exc:
            self.log(str(exc)); ui.notification_show(str(exc), type="error", duration=8)

    def inspect(self):
        report = self.report.get()
        if not report:
            ui.notification_show("Run input QC for the current KNN source first.", type="warning")
            return
        self.modal("Current KNN Input Structure", {"ST": report["st"], "SM": report["sm"], "initial_sm_qc": report["initial_sm_qc"], "coordinate_contract": report["coordinate_contract"]})

    def inspect_result(self):
        try:
            report = self.accepted_result()
            self.modal("Current KNN Result Quality", {key: report[key] for key in ("quality", "spatial_coverage", "coordinate_contract", "post_filter", "input_lineage")})
        except Exception as exc:
            ui.notification_show(str(exc), type="error", duration=8)

    @staticmethod
    def modal(title, payload):
        ui.modal_show(ui.modal(ui.tags.pre(json.dumps(payload, indent=2)), title=title, easy_close=True, footer=ui.modal_button("Close"), size="l"))

    def stream_preview_pdf(self):
        report = self.report.get()
        if not report:
            raise ValueError("Run KNN input QC before downloading the preview.")
        relative = "figures/knn_scaled_preview.pdf" if report.get("preview_png") else "figures/knn_input_overlay.pdf"
        yield from self.stream_path(self.artifact(self.qc_job.get(), self.qc_key.get(), relative))

    def stream_result(self, relative):
        self.accepted_result()
        yield from self.stream_path(self.artifact(self.result_job.get(), self.result_key.get(), relative))

    @staticmethod
    def stream_path(path):
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                yield chunk
