# Feature sm_tic_roi: original callable implementation extracted from sm_tic_roi_module.py.
from spashiny._shared.feature_support import sm_tic_roi_module as _feature_shared


def sm_tic_roi_module_server(
    input,
    output,
    session,
    *,
    session_record_provider,
    analysis_session_id_provider,
    result_json_reader,
    download_url_builder,
):
    status = _feature_shared.reactive.Value("Upload paired imzML/IBD files to start.")
    uploads = _feature_shared.reactive.Value([])
    csv_uploads = _feature_shared.reactive.Value({})
    preview = _feature_shared.reactive.Value(None)
    selection = _feature_shared.reactive.Value({})
    preview_job_id = _feature_shared.reactive.Value("")
    active_job_id = _feature_shared.reactive.Value("")
    identity = {"value": None}

    def scope():
        owner = session_record_provider()
        analysis = str(analysis_session_id_provider() or "").strip()
        if owner is None or not analysis:
            raise ValueError("The current tab analysis is not ready.")
        return (owner, analysis)

    def scoped_jobs():
        from cloud.database import CloudDatabase

        owner, analysis = scope()
        return [
            j
            for j in CloudDatabase(read_only=True).list_jobs(
                session_id=owner.session_id, analysis_session_id=analysis, limit=100
            )
            if (j.workflow_name or j.workflow) in _feature_shared.WORKFLOWS
        ]

    async def send_preview():
        data = preview.get()
        if not data:
            return
        choices = {"": "Select a dataset", **{d["id"]: d["name"] for d in data["datasets"]}}
        for role in ("pos", "neg"):
            preferred = next((d["id"] for d in data["datasets"] if d.get("polarity") == role), "")
            _feature_shared.ui.update_select(
                "sm_tic_roi_" + role + "_dataset",
                choices=choices,
                selected=preferred,
                session=session,
            )
        await session.send_custom_message(
            "sm_tic_roi_preview",
            {**data, "preview_job_id": preview_job_id.get(), "selections": selection.get()},
        )

    @_feature_shared.reactive.Effect
    def _reset_on_analysis_change():
        try:
            owner, analysis = scope()
            key = (owner.session_id, analysis)
        except ValueError:
            key = None
        if identity["value"] != key:
            identity["value"] = key
            uploads.set([])
            csv_uploads.set({})
            preview.set(None)
            selection.set({})
            preview_job_id.set("")
            active_job_id.set("")
            status.set("Upload paired imzML/IBD files to start.")

    @_feature_shared.reactive.Effect
    @_feature_shared.reactive.event(input.sm_pos_neg_uploaded)
    def _csv_uploads():
        value = input.sm_pos_neg_uploaded() or {}
        roles = value.get("roles")
        csv_uploads.set(dict(roles) if isinstance(roles, dict) else {})
        if value.get("status") == "FAILED":
            status.set(
                f"CSV upload failed: {value.get('message') or value.get('code') or 'unknown error'}"
            )
        elif value.get("status") == "READY":
            try:
                from cloud.database import CloudDatabase

                owner, analysis = scope()
                _feature_shared.validate_csv_uploads(
                    CloudDatabase(read_only=True), owner.session_id, analysis, csv_uploads.get()
                )
                status.set(
                    "POS and NEG spectrum CSVs uploaded. Click Merge with SpatialMETA → H5AD."
                )
            except Exception as exc:
                status.set(f"CSV inputs not ready: {exc}")

    @_feature_shared.reactive.Effect
    @_feature_shared.reactive.event(input.sm_tic_roi_uploaded)
    def _uploads():
        value = input.sm_tic_roi_uploaded() or {}
        if value.get("status") == "UPLOADING":
            uploads.set([])
            preview.set(None)
            selection.set({})
            preview_job_id.set("")
            status.set("Uploading paired MSI files…")
        elif value.get("status") == "READY":
            try:
                from cloud.database import CloudDatabase

                owner, analysis = scope()
                ids = _feature_shared.validate_uploads(
                    CloudDatabase(read_only=True),
                    owner.session_id,
                    analysis,
                    value.get("upload_ids"),
                )
                uploads.set(ids)
                status.set(f"{len(ids)} files ready. Compute TIC preview next.")
            except Exception as exc:
                status.set(f"Input pairing failed: {exc}")
        elif value.get("status") == "FAILED":
            status.set(
                f"Upload failed: {value.get('message') or value.get('code') or 'unknown error'}"
            )

    @_feature_shared.reactive.Effect
    @_feature_shared.reactive.event(input.sm_tic_roi_selection)
    def _selection():
        data = preview.get()
        payload = input.sm_tic_roi_selection() or {}
        if not data or payload.get("preview_job_id") != preview_job_id.get():
            return
        try:
            selection.set(_feature_shared.validate_selection(data, payload))
        except ValueError as exc:
            status.set(f"Selection rejected: {exc}")

    @_feature_shared.reactive.Effect
    @_feature_shared.reactive.event(input.sm_tic_roi_mount)
    async def _mount():
        try:
            if not preview.get():
                completed = next(
                    (
                        j
                        for j in scoped_jobs()
                        if j.workflow_name == "sm_tic_preview" and j.status == "SUCCEEDED"
                    ),
                    None,
                )
                if completed:
                    data = result_json_reader(completed, "tic_preview.json")
                    if data.get("datasets"):
                        preview.set(data)
                        preview_job_id.set(completed.job_id)
                        uploads.set(_feature_shared.json.loads(completed.input_upload_ids_json))
                        selection.set(
                            {
                                d["id"]: {
                                    "z": d["z_values"][0],
                                    "pixel_ids": [],
                                    "source_sha256": d["source_sha256"],
                                }
                                for d in data["datasets"]
                            }
                        )
            await send_preview()
        except Exception as exc:
            status.set(f"TIC preview restore failed: {exc}")

    def submit(workflow, parameters):
        from cloud.database import CloudDatabase
        from cloud.job_submission import JobSubmissionService
        from cloud.models import TERMINAL_STATUSES

        if active_job_id.get():
            existing = next((j for j in scoped_jobs() if j.job_id == active_job_id.get()), None)
            if existing is None or existing.status not in TERMINAL_STATUSES:
                raise ValueError("Wait for the current TIC/ROI job to finish.")
        owner, analysis = scope()
        if workflow == "sm_pos_neg_merge":
            ids, role_names = _feature_shared.validate_csv_uploads(
                CloudDatabase(read_only=True), owner.session_id, analysis, csv_uploads.get()
            )
            parameters = {**parameters, **role_names}
        else:
            ids = _feature_shared.validate_uploads(
                CloudDatabase(read_only=True), owner.session_id, analysis, uploads.get()
            )
        job = JobSubmissionService().submit(
            session=owner,
            analysis_session_id=analysis,
            workflow_name=workflow,
            input_upload_ids=ids,
            parameters=parameters,
            requested_resource="cpu",
        )
        active_job_id.set(job.job_id)
        status.set(
            f"{job.status} — {job.job_id}. Computation runs on the CPU worker, not in the browser."
        )

    @_feature_shared.reactive.Effect
    @_feature_shared.reactive.event(input.sm_tic_roi_preview)
    def _preview():
        try:
            submit("sm_tic_preview", {})
        except Exception as exc:
            status.set(f"TIC preview submission failed: {exc}")

    @_feature_shared.reactive.Effect
    @_feature_shared.reactive.event(input.sm_tic_roi_export)
    def _export():
        try:
            data = preview.get()
            if not data or not preview_job_id.get():
                raise ValueError("Compute a TIC preview before exporting.")
            selected = _feature_shared.validate_selection(data, {"selections": selection.get()})
            export_all = bool(input.sm_tic_roi_export_all())
            if not export_all and any((not value["pixel_ids"] for value in selected.values())):
                raise ValueError("Select an ROI in every dataset, or explicitly export all pixels.")
            submit(
                "sm_roi_export",
                {
                    "selections": selected,
                    "export_all": export_all,
                    "match_common_coordinates": bool(input.sm_tic_roi_match()),
                    "preview_job_id": preview_job_id.get(),
                    "duplicate_mz_policy": str(input.sm_tic_roi_duplicate_policy()),
                    "mz_axis_mode": str(input.sm_tic_roi_axis_mode()),
                    "mz_bin_width_da": input.sm_tic_roi_bin_width(),
                    "merge_pos_neg": bool(input.sm_tic_roi_merge_now()),
                    "pos_dataset_id": str(input.sm_tic_roi_pos_dataset() or ""),
                    "neg_dataset_id": str(input.sm_tic_roi_neg_dataset() or ""),
                },
            )
        except Exception as exc:
            status.set(f"ROI export submission failed: {exc}")

    @_feature_shared.reactive.Effect
    @_feature_shared.reactive.event(input.sm_pos_neg_merge)
    def _merge():
        try:
            submit("sm_pos_neg_merge", {})
        except Exception as exc:
            status.set(f"POS/NEG merge submission failed: {exc}")

    @_feature_shared.reactive.Effect
    async def _poll():
        job_id = active_job_id.get()
        if not job_id:
            return
        _feature_shared.reactive.invalidate_later(2)
        try:
            from cloud.models import TERMINAL_STATUSES

            job = next((j for j in scoped_jobs() if j.job_id == job_id), None)
            if not job:
                return
            status.set(f"{job.status} — {job.job_id}: {job.current_step or job.message or ''}")
            if job.status not in TERMINAL_STATUSES:
                return
            active_job_id.set("")
            if job.status != "SUCCEEDED":
                status.set(
                    f"{job.status} — {job.job_id}: {job.error_code}: {job.error_message or job.message or job.current_step}"
                )
            elif job.workflow_name == "sm_tic_preview":
                data = result_json_reader(job, "tic_preview.json")
                if not data.get("datasets"):
                    raise ValueError("Completed preview payload is unavailable.")
                preview.set(data)
                preview_job_id.set(job.job_id)
                selection.set(
                    {
                        d["id"]: {
                            "z": d["z_values"][0],
                            "pixel_ids": [],
                            "source_sha256": d["source_sha256"],
                        }
                        for d in data["datasets"]
                    }
                )
                await send_preview()
                status.set("TIC preview ready. Select ROI pixels in each dataset.")
            elif job.workflow_name == "sm_pos_neg_merge":
                summary = result_json_reader(job, "pos_neg_merge_summary.json")
                status.set(
                    f"H5AD ready: {summary.get('shared_pixels')} shared pixels; {summary.get('pos_features')} POS + {summary.get('neg_features')} NEG features; reload {summary.get('h5ad_reload')}. Download below."
                )
            else:
                status.set("SpatialMETA CSVs (and H5AD if requested) are ready. Download below.")
        except Exception as exc:
            status.set(f"TIC/ROI status check failed: {exc}")

    @output
    @_feature_shared.render.text
    def sm_tic_roi_status():
        return status.get()

    @output
    @_feature_shared.render.text
    def sm_pos_neg_status():
        return status.get()

    @output
    @_feature_shared.render.ui
    def sm_tic_roi_jobs():
        active_job_id.get()
        try:
            owner, _ = scope()
            jobs = scoped_jobs()
            from cloud.models import ACTIVE_JOB_STATUSES

            if any((j.status in ACTIVE_JOB_STATUSES for j in jobs)):
                _feature_shared.reactive.invalidate_later(2)
            cards = []
            for job in jobs[:6]:
                links = []
                if job.status == "SUCCEEDED":
                    paths = (
                        [("tic_pixels.csv", "Download TIC / coordinates CSV")]
                        if job.workflow_name == "sm_tic_preview"
                        else []
                    )
                    if job.workflow_name == "sm_roi_export":
                        paths.append(
                            ("spatialmeta_csv.zip", "Download spectrum CSVs + metadata / H5AD ZIP")
                        )
                        summary = result_json_reader(job, "tic_roi_summary.json")
                        for dataset in summary.get("datasets") or []:
                            paths.append(
                                (
                                    dataset["spectrum_csv"],
                                    f"Download {dataset['sample']} spectrum CSV",
                                )
                            )
                            paths.append(
                                (
                                    dataset["roi_metadata_csv"],
                                    f"Download {dataset['sample']} ROI metadata",
                                )
                            )
                        if summary.get("pos_neg_merge"):
                            paths.extend(
                                [
                                    ("sm_pos_neg_merged.h5ad", "Download POS/NEG merged H5AD"),
                                    (
                                        "pos_neg_merge_summary.json",
                                        "Download merge / reload report",
                                    ),
                                ]
                            )
                    elif job.workflow_name == "sm_pos_neg_merge":
                        paths.extend(
                            [
                                ("sm_pos_neg_merged.h5ad", "Download POS/NEG merged H5AD"),
                                ("pos_neg_merge_summary.json", "Download merge / reload report"),
                                (
                                    "pos_neg_matched_coordinates.csv",
                                    "Download shared coordinates CSV",
                                ),
                                ("pos_neg_results.zip", "Download H5AD + reports ZIP"),
                            ]
                        )
                    for path, label in paths:
                        url = download_url_builder(
                            owner.session_id, job.analysis_session_id, job.job_id, path
                        )
                        if url:
                            links.append(
                                _feature_shared.ui.tags.a(
                                    label,
                                    href=url,
                                    download=_feature_shared.Path(path).name,
                                    **{"data-sm-tic-roi-download": "1"},
                                    class_="btn btn-sm btn-outline-primary",
                                    style="margin:4px;",
                                )
                            )
                cards.append(
                    _feature_shared.ui.div(
                        _feature_shared.ui.tags.strong(
                            f"{job.status} — {job.workflow_name} — {job.job_id}"
                        ),
                        _feature_shared.ui.p(job.error_message or job.current_step or ""),
                        *links,
                        style="padding:12px 0;border-bottom:1px solid #e5e7eb;",
                    )
                )
            return _feature_shared.ui.div(*cards)
        except Exception as exc:
            return _feature_shared.ui.p(f"Job status unavailable: {exc}", class_="text-danger")


server = sm_tic_roi_module_server
