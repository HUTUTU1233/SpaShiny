# Feature river: original callable implementation extracted from river_st_module.py.
from spashiny._shared.feature_support import river_st_module as _feature_shared


def river_st_module_server(
    input,
    output,
    session,
    *,
    session_record_provider,
    analysis_session_id_provider,
    result_links_builder,
    result_previews_builder,
):
    status = _feature_shared.reactive.Value(
        "The built-in example is selected. Inspect inputs before running River."
    )
    preview = _feature_shared.reactive.Value("")
    inspection = _feature_shared.reactive.Value(None)
    inspection_busy = _feature_shared.reactive.Value(False)
    inspection_status = _feature_shared.reactive.Value(
        "Not inspected. Load/select inputs, then click Inspect package."
    )
    canonical_archive = _feature_shared.reactive.Value(None)
    example_archive = _feature_shared.reactive.Value(None)
    example_loading_failed = _feature_shared.reactive.Value(False)
    active_job_id = _feature_shared.reactive.Value("")
    replot_result = _feature_shared.reactive.Value(None)
    full_spot_result = _feature_shared.reactive.Value(None)
    full_spot_busy = _feature_shared.reactive.Value(False)
    full_plot_request = {"serial": 0, "signature": None}
    last_progress = {"value": None}
    completed_jobs = _feature_shared.reactive.Value([])
    completed_context = _feature_shared.reactive.Value(None)
    completed_scope = {"value": None}
    result_selection = _feature_shared.RiverResultSelection()
    selection_epoch = _feature_shared.reactive.Value(0)
    source_scope = {"value": None}
    confirmation_context = _feature_shared.reactive.Value(None)
    confirmation_generation = {"value": 0}

    def _data_source():
        value = str(_dynamic_value("river_st_data_source", "EXAMPLE"))
        if value not in ("EXAMPLE", "USER_UPLOAD"):
            raise ValueError("Select the built-in example or your own upload.")
        return value

    def _discard_inspection(message):
        inspection.set(None)
        preview.set("")
        confirmation_context.set(None)
        inspection_status.set(message)

    def _clear_result_context():
        completed_context.set(None)
        replot_result.set(None)
        full_plot_request["serial"] += 1
        full_plot_request["signature"] = None
        full_spot_result.set(None)
        full_spot_busy.set(False)
        selection_epoch.set(result_selection.generation)
        _feature_shared.ui.update_selectize(
            "river_st_representative_gene", choices=[], selected="", session=session
        )

    def _progress(action, *, title="", detail=""):
        try:
            _feature_shared.asyncio.get_running_loop().create_task(
                session.send_custom_message(
                    "river_st_progress", {"action": action, "title": title, "detail": detail}
                )
            )
        except Exception:
            pass

    def _files(input_id):
        try:
            return list(getattr(input, input_id)() or [])
        except Exception:
            return []

    def _entry_signature(entries):
        return _feature_shared.entry_signature(entries)

    def _natural_key(value):
        return [
            int(part) if part.isdigit() else part.casefold()
            for part in _feature_shared.re.split("(\\d+)", str(value))
        ]

    def _inspection_request():
        example_reference = example_archive.get() if _data_source() == "EXAMPLE" else None
        archive_reference = (
            example_reference if _data_source() == "EXAMPLE" else canonical_archive.get()
        )
        if _data_source() == "EXAMPLE" and (not archive_reference):
            raise ValueError(
                "The built-in example is not ready. Load it again; uploads will not be substituted."
            )
        archive_files = [archive_reference] if isinstance(archive_reference, dict) else []
        data_files = _files("river_st_h5_files")
        csv_files = _files("river_st_csv_files")
        if archive_files:
            if len(archive_files) != 1:
                raise ValueError("Select exactly one ZIP package.")
            return {
                "archive": archive_files[0],
                "csv_files": [] if example_reference else csv_files,
            }
        return {"data_files": data_files, "csv_files": csv_files}

    def _preferred_annotation_column(state):
        return ""

    def _resolve_canonical_archive(upload_id):
        session_record = session_record_provider()
        analysis_session_id = str(analysis_session_id_provider() or "").strip()
        if session_record is None or not analysis_session_id:
            raise RuntimeError(
                "The current tab analysis session is not ready. Please wait and try again."
            )
        from cloud.input_resolver import InputResolver

        resolved = InputResolver().resolve_interactive_local_input(
            session_id=session_record.session_id,
            analysis_session_id=analysis_session_id,
            upload_id=str(upload_id or "").strip(),
            workflow_name=_feature_shared.WORKFLOW,
        )
        path = _feature_shared.Path(str(resolved.get("local_path") or ""))
        filename = str(resolved.get("filename") or path.name)
        if path.suffix.lower() != ".zip" or not path.is_file():
            raise RuntimeError("The completed River upload is not an available ZIP package.")
        return {
            "datapath": str(path),
            "name": filename,
            "upload_id": str(resolved.get("upload_id") or upload_id),
            "size": int(resolved.get("size_bytes") or path.stat().st_size),
        }

    def _activate_bundled_example(action_id):
        example_loading_failed.set(False)
        try:
            session_record = session_record_provider()
            analysis_session_id = str(analysis_session_id_provider() or "").strip()
            if session_record is None or not analysis_session_id:
                raise RuntimeError("The current tab analysis session is not ready.")
            from cloud.example_action_bindings import ExampleActionBindingService
            from cloud.input_resolver import InputResolver

            binding = ExampleActionBindingService().activate(
                session=session_record,
                analysis_session_id=analysis_session_id,
                action_id=action_id,
                page_name="river",
            )
            if not binding.get("ready"):
                raise RuntimeError("The published River example archive is not available.")
            resolved = InputResolver().resolve_interactive_local_input(
                session_id=session_record.session_id,
                analysis_session_id=analysis_session_id,
                action_id=action_id,
                input_role=_feature_shared.RIVER_EXAMPLE_ROLE,
                workflow_name=_feature_shared.WORKFLOW,
            )
            path = _feature_shared.Path(str(resolved.get("local_path") or ""))
            if path.suffix.lower() != ".zip" or not path.is_file():
                raise RuntimeError("The published River example is not a readable ZIP archive.")
            example_archive.set(
                {
                    "datapath": str(path),
                    "name": str(resolved.get("filename") or path.name),
                    "size": int(resolved.get("size_bytes") or path.stat().st_size),
                    "action_id": action_id,
                }
            )
            canonical_archive.set(None)
            _discard_inspection("Example loaded; inspect it before Run.")
            label = (
                "spa5 SpatialMETA QC0 (5 samples)"
                if action_id == _feature_shared.RIVER_VISIUM_EXAMPLE_ACTION_ID
                else "WT/Diabetes Slide-seq (6 samples)"
            )
            status.set(
                f"Published {label} example bound to this tab. Click Inspect package, then review the sample order and group/time labels."
            )
            inspection_status.set("Example loaded; inspection is required before Run.")
        except Exception as exc:
            example_archive.set(None)
            example_loading_failed.set(True)
            status.set(f"River example could not be loaded: {exc}")
        finally:
            _progress("done")

    @_feature_shared.reactive.Effect
    @_feature_shared.reactive.event(input.river_st_load_example)
    def _load_bundled_example():
        if _data_source() == "EXAMPLE":
            _activate_bundled_example(_feature_shared.RIVER_EXAMPLE_ACTION_ID)

    @_feature_shared.reactive.Effect
    @_feature_shared.reactive.event(input.river_st_load_visium_example)
    def _load_visium_example():
        if _data_source() == "EXAMPLE":
            _activate_bundled_example(_feature_shared.RIVER_VISIUM_EXAMPLE_ACTION_ID)

    @output
    @_feature_shared.render.ui
    def river_st_example_retry():
        if _data_source() != "EXAMPLE":
            return None
        selected = example_archive.get() or {}
        if selected.get("action_id") == _feature_shared.RIVER_VISIUM_EXAMPLE_ACTION_ID:
            return None
        if selected:
            return _feature_shared.ui.input_action_button(
                "river_st_load_visium_example",
                "Return to default spa5 example",
                class_="btn btn-outline-secondary",
            )
        if example_loading_failed.get():
            return _feature_shared.ui.input_action_button(
                "river_st_load_visium_example",
                "Retry loading default spa5 example",
                class_="btn btn-outline-secondary",
            )
        return _feature_shared.ui.p(
            "Preparing the default spa5 example for this analysis…", class_="cloud-muted"
        )

    @_feature_shared.reactive.Effect
    def _switch_source_scope():
        owner = session_record_provider()
        analysis = str(analysis_session_id_provider() or "")
        source = _data_source()
        scope = (owner.session_id if owner else "", analysis, source)
        if not owner or not analysis or scope == source_scope["value"]:
            return
        source_scope["value"] = scope
        canonical_archive.set(None)
        example_archive.set(None)
        _discard_inspection("Data source changed. Inspect the selected inputs before Run.")
        if source == "EXAMPLE":
            _activate_bundled_example(_feature_shared.RIVER_VISIUM_EXAMPLE_ACTION_ID)
        else:
            status.set("Upload one ZIP or multiple H5AD files, then click Inspect package.")

    @_feature_shared.reactive.Effect
    @_feature_shared.reactive.event(input.river_st_canonical_archive_upload)
    def _track_canonical_archive_upload():
        if _data_source() != "USER_UPLOAD":
            return
        try:
            payload = input.river_st_canonical_archive_upload() or {}
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            return
        upload_status = str(payload.get("status") or "").upper()
        filename = str(payload.get("filename") or "River ZIP package")
        if upload_status == "SELECTED":
            canonical_archive.set(None)
            example_archive.set(None)
            _discard_inspection("New upload selected; inspection is not ready.")
            inspection_status.set("New upload selected; inspection is not ready.")
            status.set(f"Uploading {filename}…")
            return
        if upload_status == "READY":
            upload_id = str(payload.get("upload_id") or "").strip()
            if not upload_id:
                canonical_archive.set(None)
                status.set("River upload failed: completion returned no upload reference.")
                return
            try:
                reference = _resolve_canonical_archive(upload_id)
            except Exception as exc:
                canonical_archive.set(None)
                status.set(f"River upload is not available to this tab: {exc}")
                return
            canonical_archive.set(reference)
            example_archive.set(None)
            status.set(f"River package ready: {reference['name']}. Click Inspect package.")
            inspection_status.set("Upload complete; click Inspect package before Run.")
            _discard_inspection("Upload complete; click Inspect package before Run.")
            return
        if upload_status == "FAILED":
            canonical_archive.set(None)
            inspection.set(None)
            preview.set("")
            code = str(payload.get("code") or "UPLOAD_FAILED")
            detail = str(payload.get("message") or code)
            status.set(f"River package upload failed ({code}): {detail}")

    def _dynamic_value(input_id, default=None):
        try:
            value = getattr(input, input_id)()
            return default if value is None else value
        except Exception:
            return default

    @_feature_shared.reactive.Effect
    @_feature_shared.reactive.event(input.river_st_h5_files, ignore_init=True)
    def _direct_input_changed():
        if _data_source() != "USER_UPLOAD":
            return
        if _files("river_st_h5_files"):
            canonical_archive.set(None)
            example_archive.set(None)
        _discard_inspection("Direct input selection changed; click Inspect package.")

    @_feature_shared.reactive.Effect
    @_feature_shared.reactive.event(input.river_st_csv_files, ignore_init=True)
    def _csv_input_changed():
        if _data_source() == "USER_UPLOAD":
            _discard_inspection("Annotation file selection changed; click Inspect package.")

    def _validate_files():
        state = inspection.get()
        if not isinstance(state, dict) or not state.get("samples"):
            raise ValueError("Inspect the uploaded package before submitting River.")
        request = _inspection_request()
        current_entries = _feature_shared.request_entries(request)
        owner = session_record_provider()
        current_scope = (
            owner.session_id if owner else "",
            str(analysis_session_id_provider() or ""),
        )
        if tuple(state.get("inspection_scope") or ()) != current_scope:
            raise ValueError(
                "The analysis session changed. Inspect inputs in this analysis before submitting."
            )
        if _entry_signature(current_entries) != tuple(
            (tuple(x) for x in state.get("input_signature") or ())
        ):
            raise ValueError("The selected upload changed after inspection. Inspect it again.")
        ordered = []
        used_positions = set()
        for default_position, sample in enumerate(state["samples"], start=1):
            try:
                position = int(_dynamic_value(f"river_st_order_{sample['key']}", default_position))
            except (TypeError, ValueError):
                raise ValueError(f"Invalid order for {sample['file_name']}.")
            if position < 1 or position > len(state["samples"]) or position in used_positions:
                raise ValueError(
                    "Time-point order values must be unique integers from 1 to the number of samples."
                )
            used_positions.add(position)
            label = str(
                _dynamic_value(
                    f"river_st_time_{sample['key']}", sample.get("time_label", sample["sample_id"])
                )
                or ""
            ).strip()
            if not label:
                raise ValueError(f"Time label is required for {sample['file_name']}.")
            ordered.append((position, sample, label))
        ordered.sort(key=lambda item: item[0])
        source = _data_source()
        if bool(state.get("example_action_id")) != (source == "EXAMPLE"):
            raise ValueError(
                "The inspected data source changed. Inspect the selected source again."
            )
        target_n = 1052
        annotation_selection = str(_dynamic_value("river_st_annotation_column", "") or "").strip()
        annotation_source, annotation_column = (
            annotation_selection.split(":", 1) if ":" in annotation_selection else ("none", "")
        )
        annotation_value = str(_dynamic_value("river_st_annotation_value", "") or "").strip()
        common_columns = set(
            (
                str(value)
                for value in state.get(
                    "common_csv_columns" if annotation_source == "csv" else "common_obs_columns"
                )
                or []
            )
        )
        if annotation_column and annotation_column not in common_columns:
            raise ValueError("Choose a grouping column shared by every detected time point.")
        common_values = set(
            (
                str(value)
                for value in (
                    (
                        state.get(
                            "common_csv_values"
                            if annotation_source == "csv"
                            else "common_obs_values"
                        )
                        or {}
                    ).get(annotation_column, [])
                    if annotation_column
                    else []
                )
            )
        )
        if annotation_value and annotation_value not in common_values:
            raise ValueError("Choose a cluster/category reported by the selected grouping column.")
        settings = _feature_shared.normalize_unified(
            {
                "execution_contract_version": _feature_shared.V3,
                "execution_mode": _feature_shared.MODE,
                "data_source_mode": source,
                "sample_order": [item[1]["file_name"] for item in ordered],
                "time_labels": [item[2] for item in ordered],
                "sample_evidence": [dict(item[1].get("scale_evidence") or {}) for item in ordered],
                "subsample_size": target_n,
                "river_epochs": 100,
                "sampling_random_state": 0,
                "random_seed": 42,
                "annotation_source": annotation_source,
                "annotation_column": annotation_column,
                "annotation_value": annotation_value,
                "allow_missing_annotation": bool(
                    _dynamic_value("river_st_allow_missing_annotation", False)
                ),
            }
        )
        return {
            **settings,
            "upload_entries": list(state.get("upload_entries") or []),
            "csv_entries": list(state.get("csv_entries") or []),
            "existing_upload_ids": [
                str(item.get("upload_id") or "").strip()
                for item in state.get("upload_entries") or []
                if str(item.get("upload_id") or "").strip()
            ],
            "source_mode": str(state.get("source_mode") or ""),
            "example_action_id": str(state.get("example_action_id") or ""),
            "sample_order": [item[1]["file_name"] for item in ordered],
            "time_labels": [item[2] for item in ordered],
            "representative_gene": "",
            "subsample_size": target_n,
            "subsample_mode": "custom",
            "annotation_column": annotation_column,
            "annotation_value": annotation_value,
            "sample_manifest": [
                {
                    "order": item[0],
                    "file_name": item[1]["file_name"],
                    "archive_member": item[1]["member"],
                    "time_label": item[2],
                }
                for item in ordered
            ],
        }

    def _register_upload(file_entry):
        from cloud.upload_service import UploadPart, UploadService

        session_record = session_record_provider()
        analysis_session_id = str(analysis_session_id_provider() or "").strip()
        if session_record is None or not analysis_session_id:
            raise RuntimeError("Cloud session is not ready. Wait briefly, then try again.")
        data_path = _feature_shared.Path(str(file_entry.get("datapath") or ""))
        filename = str(file_entry.get("name") or data_path.name)
        size_bytes = data_path.stat().st_size
        service = UploadService()
        if not hasattr(service.storage, "put_part"):
            raise RuntimeError(
                "The configured storage backend cannot register Shiny uploads for River."
            )
        part_size = int(service.config.r2_multipart_part_size_bytes)
        upload = service.initiate_upload(
            session=session_record,
            analysis_session_id=analysis_session_id,
            filename=filename,
            size_bytes=size_bytes,
            content_type=(
                "text/csv"
                if data_path.suffix.lower() == ".csv"
                else (
                    "application/zip"
                    if data_path.suffix.lower() == ".zip"
                    else "application/octet-stream"
                )
            ),
            total_parts=max(1, _feature_shared.math.ceil(size_bytes / part_size)),
        )
        record = service.database.get_upload(
            str(upload["upload_id"]),
            session_id=session_record.session_id,
            analysis_session_id=analysis_session_id,
        )
        parts = []
        with data_path.open("rb") as handle:
            part_number = 1
            while chunk := handle.read(part_size):
                etag = service.storage.put_part(record.multipart_upload_id, part_number, chunk)
                parts.append(UploadPart(part_number=part_number, etag=etag))
                part_number += 1
        return service.complete_upload(
            session=session_record,
            analysis_session_id=analysis_session_id,
            upload_id=record.upload_id,
            parts=parts,
        )

    def _latest_completed_river_job():
        session_record = session_record_provider()
        analysis_session_id = str(analysis_session_id_provider() or "").strip()
        if session_record is None or not analysis_session_id:
            raise RuntimeError("The current tab analysis session is not ready.")
        from cloud.database import CloudDatabase

        jobs = [
            job
            for job in CloudDatabase(read_only=True).list_jobs(
                session_id=session_record.session_id,
                analysis_session_id=analysis_session_id,
                limit=30,
            )
            if str(job.workflow_name or job.workflow) == _feature_shared.WORKFLOW
            and str(job.status or "").upper() == "SUCCEEDED"
        ]
        if not jobs:
            raise RuntimeError("Run a River analysis successfully before redrawing a gene.")
        selection_epoch.get()
        if result_selection.scope != (session_record.session_id, analysis_session_id):
            raise RuntimeError("The result selection belongs to another analysis.")
        selected = result_selection.selected(jobs)
        if selected is None:
            raise RuntimeError(
                "Select a completed River job explicitly; no older result will be substituted."
            )
        return selected

    def _plot_options():
        context = completed_context.get() or {}
        return {
            name: _dynamic_value("river_st_plot_" + name, default)
            for name, default in {
                "width": 20,
                "height": 4,
                "size": 12,
                "ncols": context.get("sample_count", 1),
                "cmap": "Balance_20",
                "colorbar": False,
                "automatic_norm": True,
                "vmin": 0,
                "vmax": 5,
            }.items()
        }

    def _render_gene_from_saved_inputs(job, gene):
        return _feature_shared.render_saved_gene(job, gene, _plot_options())

    @_feature_shared.reactive.extended_task
    async def _full_spot_task(job, gene, palettes, settings, token, scope, serial):
        try:
            result = await _feature_shared.asyncio.to_thread(
                _feature_shared.render_full_spot_gene, job, gene, palettes, settings
            )
        except Exception as exc:
            result = {"error": str(exc), "gene": gene, "job_id": str(job.job_id)}
        return {"result": result, "token": token, "scope": scope, "serial": serial}

    @_feature_shared.reactive.Effect
    @_feature_shared.reactive.event(
        completed_context,
        input.river_st_full_gene,
        input.river_st_full_palettes,
        input.river_st_full_draw,
        ignore_none=False,
    )
    def _queue_full_spot_plot():
        context = completed_context.get() or {}
        if not context.get("genes") or context.get("error"):
            _full_spot_task.cancel()
            return
        try:
            job = _latest_completed_river_job()
        except Exception as exc:
            full_spot_busy.set(False)
            full_spot_result.set({"error": str(exc)})
            return
        gene = str(_dynamic_value("river_st_full_gene", "") or context["genes"][0]).strip()
        if gene not in context["genes"] or context.get("job_id") != str(job.job_id):
            return
        palettes = _dynamic_value("river_st_full_palettes", ["magma"])
        settings = {
            key: _dynamic_value("river_st_full_" + key, default)
            for key, default in {
                "width": 20,
                "height": 4,
                "size": 12,
                "ncols": context["sample_count"],
            }.items()
        }
        owner = session_record_provider()
        scope = (owner.session_id, str(analysis_session_id_provider() or ""), str(job.job_id))
        token = result_selection.token()
        signature = repr((token, gene, palettes, settings, _dynamic_value("river_st_full_draw", 0)))
        if signature == full_plot_request["signature"]:
            return
        full_plot_request["serial"] += 1
        full_plot_request["signature"] = signature
        full_spot_result.set(None)
        full_spot_busy.set(True)
        _full_spot_task.cancel()
        _full_spot_task(job, gene, palettes, settings, token, scope, full_plot_request["serial"])

    @_feature_shared.reactive.Effect
    def _publish_full_spot_plot():
        payload = _full_spot_task.result()
        if (
            not result_selection.is_current(payload["token"])
            or payload["serial"] != full_plot_request["serial"]
        ):
            return
        owner = session_record_provider()
        if owner is None:
            return
        try:
            job = _latest_completed_river_job()
        except Exception as exc:
            full_spot_busy.set(False)
            full_spot_result.set({"error": str(exc)})
            return
        if payload["scope"] != (
            owner.session_id,
            str(analysis_session_id_provider() or ""),
            str(job.job_id),
        ):
            return
        full_spot_result.set(payload["result"])
        full_spot_busy.set(False)

    @output
    @_feature_shared.render.ui
    def river_st_full_spot_controls():
        context = completed_context.get() or {}
        if not context.get("genes") or context.get("error"):
            return None
        token = result_selection.token()
        genes = context["genes"]
        session.on_flushed(
            lambda: (
                _feature_shared.ui.update_selectize(
                    "river_st_full_gene",
                    choices=genes,
                    selected=genes[0],
                    server=True,
                    session=session,
                )
                if result_selection.is_current(token)
                else None
            ),
            once=True,
        )
        return _feature_shared.ui.div(
            _feature_shared.ui.h4("Gene expression - all input spots"),
            _feature_shared.ui.p(
                "Automatically drawn below the spot results. No random spot sampling, matching or River training is run. Changing the gene or selected palettes redraws this companion plot only.",
                class_="cloud-muted",
            ),
            _feature_shared.ui.input_selectize(
                "river_st_full_gene",
                "Search gene (all-spot expression)",
                choices={},
                multiple=False,
            ),
            _feature_shared.ui.input_selectize(
                "river_st_full_palettes",
                "Color palettes (choose 1-4)",
                choices=_feature_shared.FULL_SPOT_PALETTES,
                selected=["magma"],
                multiple=True,
                options={"maxItems": 4, "plugins": ["remove_button"]},
            ),
            _feature_shared.ui.div(
                _feature_shared.ui.input_numeric(
                    "river_st_full_width",
                    "Full-spot figure width (inches)",
                    value=20,
                    min=4,
                    max=48,
                ),
                _feature_shared.ui.input_numeric(
                    "river_st_full_height",
                    "Full-spot figure height (inches)",
                    value=4,
                    min=2,
                    max=48,
                ),
                _feature_shared.ui.input_numeric(
                    "river_st_full_ncols",
                    "Panels per row",
                    value=context["sample_count"],
                    min=1,
                    max=context["sample_count"],
                ),
                _feature_shared.ui.input_numeric(
                    "river_st_full_size",
                    "Full-spot point size",
                    value=12,
                    min=0.05,
                    max=100,
                    step=0.25,
                ),
                style="display:flex;gap:12px;flex-wrap:wrap;",
            ),
            _feature_shared.ui.input_action_button(
                "river_st_full_draw",
                "Apply size / layout (no re-analysis)",
                class_="btn btn-outline-primary",
            ),
        )

    @output
    @_feature_shared.render.ui
    def river_st_full_spot_result():
        if full_spot_busy.get():
            return _feature_shared.ui.p(
                "Drawing all input spots from this job. No River training is running.",
                role="status",
                class_="cloud-muted",
            )
        result = full_spot_result.get()
        if not isinstance(result, dict):
            return None
        if result.get("error"):
            return _feature_shared.ui.p(
                "Full-spot expression plot: " + result["error"], class_="text-danger", role="alert"
            )
        gene = result["gene"]
        safe_gene = _feature_shared.re.sub("[^A-Za-z0-9_.-]", "_", gene)[:100] or "gene"
        counts = "; ".join((f"{p['label']}: {p['n_spots']:,}" for p in result["panels"]))
        plot_steps = sorted({step for p in result["panels"] for step in p["plot_preprocessing"]})
        return _feature_shared.ui.div(
            _feature_shared.ui.h4(f"{gene} - all {result['total_spots']:,} input spots"),
            _feature_shared.ui.p("Spots drawn per sample: " + counts, class_="cloud-muted"),
            _feature_shared.ui.p(
                "One expression scale is shared by all samples and palettes. "
                + (
                    "Raw counts are normalized on the full sample for visualization only, then log1p; this may use a different library-size median than the training subset. "
                    if any((p["input_scale"] == "raw_counts" for p in result["panels"]))
                    else ""
                )
                + "Already log1p inputs are used unchanged. Source H5AD files and River results are not modified.",
                class_="cloud-muted",
            ),
            (
                _feature_shared.ui.p(
                    "No expression was detected for this gene; the zero-valued spots are shown without inventing signal.",
                    class_="text-warning",
                )
                if result["all_zero_gene"]
                else None
            ),
            *[
                _feature_shared.ui.div(
                    _feature_shared.ui.h5(image["label"]),
                    _feature_shared.ui.tags.img(
                        src=image["png"],
                        alt=f"All input spots: {gene}, {image['palette']}",
                        style="display:block;width:100%;height:auto;",
                    ),
                    _feature_shared.ui.tags.a(
                        "Download editable PDF",
                        href=image["pdf"],
                        download=f"river_all_spots_{safe_gene}_{image['palette']}.pdf",
                        class_="btn btn-sm btn-outline-danger",
                    ),
                    _feature_shared.ui.tags.a(
                        "Download PNG",
                        href=image["png"],
                        download=f"river_all_spots_{safe_gene}_{image['palette']}.png",
                        class_="btn btn-sm btn-outline-success",
                        style="margin-left:8px;",
                    ),
                    style="margin:16px 0;",
                )
                for image in result["images"]
            ],
            _feature_shared.ui.p(
                "Plot-only processing: "
                + (
                    "; ".join(plot_steps)
                    if plot_steps
                    else "none; saved log1p expression used unchanged"
                ),
                class_="cloud-muted",
            ),
        )

    @_feature_shared.reactive.Effect
    @_feature_shared.reactive.event(input.river_st_replot_gene)
    async def _replot_selected_gene():
        token = result_selection.token()
        try:
            job = _latest_completed_river_job()
            gene = str(input.river_st_representative_gene() or "").strip()
            context = completed_context.get() or {}
            if context.get("job_id") != str(job.job_id) or gene not in context.get("genes", []):
                raise ValueError(
                    "Select an available gene and wait for the selector to finish loading before drawing."
                )
            owner = session_record_provider()
            scope = (owner.session_id, str(analysis_session_id_provider() or ""), str(job.job_id))
            token = result_selection.token()
            options = _plot_options()
            _progress(
                "show",
                title="Drawing saved River result",
                detail="No upload, matching or model training is being run.",
            )
            result = await _feature_shared.asyncio.to_thread(
                _feature_shared.render_saved_gene, job, gene, options
            )
            current = session_record_provider()
            current_job = _latest_completed_river_job()
            if (
                not result_selection.is_current(token)
                or current is None
                or scope
                != (
                    current.session_id,
                    str(analysis_session_id_provider() or ""),
                    str(current_job.job_id),
                )
            ):
                return
            replot_result.set(result)
            status.set(
                f"Redrew {gene} from the saved River result. No upload or re-analysis was required."
            )
        except Exception as exc:
            if not result_selection.is_current(token):
                return
            replot_result.set({"error": str(exc)})
            status.set(f"Gene redraw failed: {exc}")
        finally:
            _progress("done")

    @_feature_shared.reactive.Effect
    def _refresh_completed_river_jobs():
        _feature_shared.reactive.invalidate_later(5)
        owner = session_record_provider()
        analysis = str(analysis_session_id_provider() or "").strip()
        scope = (owner.session_id if owner else "", analysis)
        if scope != completed_scope["value"]:
            completed_scope["value"] = scope
            result_selection.reset_scope(*scope)
            _clear_result_context()
            active_job_id.set("")
            completed_jobs.set([])
            completed_context.set(None)
            replot_result.set(None)
        if owner is None or not analysis:
            return
        try:
            from cloud.database import CloudDatabase

            jobs = [
                job
                for job in CloudDatabase(read_only=True).list_jobs(
                    session_id=owner.session_id, analysis_session_id=analysis, limit=30
                )
                if str(job.workflow_name or job.workflow) == _feature_shared.WORKFLOW
                and str(job.status).upper() == "SUCCEEDED"
            ]
            if [str(j.job_id) for j in jobs] != [str(j.job_id) for j in completed_jobs.get()]:
                completed_jobs.set(jobs)
        except Exception as exc:
            if not completed_jobs.get():
                completed_context.set(
                    {"error": "Result status is temporarily unavailable: " + str(exc)}
                )

    @_feature_shared.reactive.Effect
    @_feature_shared.reactive.event(input.river_st_completed_job)
    def _select_completed_job():
        if result_selection.observe_client(
            _dynamic_value("river_st_completed_job", ""), [j.job_id for j in completed_jobs.get()]
        ):
            _clear_result_context()

    @_feature_shared.reactive.Effect
    def _restore_completed_gene_choices():
        selection_epoch.get()
        jobs = completed_jobs.get()
        if not jobs:
            return
        job = result_selection.selected(jobs)
        if job is None:
            return
        old_context = completed_context.get() or {}
        if old_context.get("job_id") == str(job.job_id):
            return
        try:
            context = _feature_shared.saved_result_context(job)
            completed_context.set(context)
            replot_result.set(None)
        except Exception as exc:
            completed_context.set({"job_id": str(job.job_id), "error": str(exc)})

    @output
    @_feature_shared.render.ui
    def river_st_completed_controls():
        selection_epoch.get()
        jobs = completed_jobs.get()
        selector = _feature_shared.ui.input_select(
            "river_st_completed_job",
            "Completed River result",
            choices={
                "": "Select a result explicitly",
                **{str(j.job_id): str(j.job_id) for j in jobs},
            },
            selected=result_selection.selected_job_id,
        )
        context = completed_context.get()
        if not isinstance(context, dict):
            return _feature_shared.ui.div(
                selector,
                _feature_shared.ui.p(
                    "Complete a new River job, or explicitly select a historical result.",
                    class_="cloud-muted",
                ),
            )
        if context.get("error"):
            return _feature_shared.ui.div(
                selector,
                _feature_shared.ui.p(
                    "Saved River result: " + context["error"], class_="text-danger"
                ),
            )
        jobs = completed_jobs.get()
        genes = context["genes"]
        token = result_selection.token()
        session.on_flushed(
            lambda: (
                _feature_shared.ui.update_selectize(
                    "river_st_representative_gene",
                    choices=genes,
                    selected=genes[0],
                    server=True,
                    session=session,
                )
                if result_selection.is_current(token)
                else None
            ),
            once=True,
        )
        return _feature_shared.ui.div(
            selector,
            _feature_shared.ui.p(
                "Execution record: "
                + str(
                    context.get("execution_record")
                    or "Legacy input-only contract; training environment was not recorded."
                ),
                class_="cloud-muted",
            ),
            _feature_shared.ui.input_numeric(
                "river_st_top_n",
                "Top N genes to display",
                value=min(20, context["rank_count"]),
                min=1,
                max=context["rank_count"],
                step=1,
            ),
            _feature_shared.ui.p(
                f"{context['rank_count']:,} ranked genes. The full ranked CSV remains available in the result downloads.",
                class_="cloud-muted",
            ),
            *(
                [
                    _feature_shared.ui.p(
                        f"This older result saved {context['cached_gene_count']:,} plotting genes; the selector lists the genes available in its saved artifact. No new upload is required.",
                        class_="cloud-muted",
                    )
                ]
                if context["partial_legacy_cache"]
                else []
            ),
            _feature_shared.ui.input_selectize(
                "river_st_representative_gene",
                "Gene to plot from the completed result",
                choices={},
                multiple=False,
            ),
            _feature_shared.ui.h4("Spatial expression plot settings"),
            _feature_shared.ui.p(
                "These options redraw the saved expression values only. Spot sampling and model training are not repeated.",
                class_="cloud-muted",
            ),
            _feature_shared.ui.div(
                _feature_shared.ui.input_numeric(
                    "river_st_plot_width", "Figure width (inches)", value=20, min=2, max=48, step=1
                ),
                _feature_shared.ui.input_numeric(
                    "river_st_plot_height", "Figure height (inches)", value=4, min=2, max=48, step=1
                ),
                _feature_shared.ui.input_numeric(
                    "river_st_plot_ncols",
                    "Sample panels per row",
                    value=context["sample_count"],
                    min=1,
                    max=context["sample_count"],
                    step=1,
                ),
                _feature_shared.ui.input_numeric(
                    "river_st_plot_size", "Point size", value=12, min=0.01, max=1000, step=0.5
                ),
                style="display:flex;gap:12px;flex-wrap:wrap;",
            ),
            _feature_shared.ui.input_select(
                "river_st_plot_cmap",
                "Expression color palette",
                choices=list(_feature_shared.PALETTES),
                selected="Balance_20",
            ),
            _feature_shared.ui.input_checkbox(
                "river_st_plot_colorbar", "Show expression color bar", value=False
            ),
            _feature_shared.ui.input_checkbox(
                "river_st_plot_automatic_norm",
                "Use one automatic color scale across all samples",
                value=True,
            ),
            _feature_shared.ui.panel_conditional(
                "!input.river_st_plot_automatic_norm",
                _feature_shared.ui.input_numeric(
                    "river_st_plot_vmin", "Color-scale minimum", value=0, step=0.1
                ),
                _feature_shared.ui.input_numeric(
                    "river_st_plot_vmax", "Color-scale maximum", value=5, step=0.1
                ),
            ),
            _feature_shared.ui.output_ui("river_st_replot_control"),
        )

    @output
    @_feature_shared.render.ui
    def river_st_replot_control():
        context = completed_context.get() or {}
        if not context.get("genes") or context.get("error"):
            return None
        gene = str(_dynamic_value("river_st_representative_gene", "") or "").strip()
        ready = gene in context["genes"]
        return _feature_shared.ui.div(
            (
                _feature_shared.ui.p(
                    "Choose a gene from the loaded search results before drawing.",
                    class_="cloud-muted",
                )
                if not ready
                else None
            ),
            _feature_shared.ui.input_action_button(
                "river_st_replot_gene",
                "Draw selected gene (no re-analysis)",
                class_="btn btn-outline-primary",
                **{} if ready else {"disabled": "disabled"},
            ),
        )

    @output
    @_feature_shared.render.ui
    def river_st_run_control():
        ready = False
        if not inspection_busy.get():
            try:
                _validate_files()
                ready = True
            except (ValueError, RuntimeError, KeyError):
                pass
        return _feature_shared.ui.div(
            _feature_shared.ui.p(inspection_status.get(), class_="cloud-muted"),
            _feature_shared.ui.input_action_button(
                "river_st_submit",
                "Run River analysis",
                class_="btn btn-primary",
                **{} if ready else {"disabled": "disabled"},
            ),
        )

    @output
    @_feature_shared.render.ui
    def river_st_scale_review():
        state = inspection.get() or {}
        unknown = [
            s
            for s in state.get("samples", [])
            if s.get("scale_evidence", {}).get("status") != "RESOLVED"
        ]
        if not unknown:
            return None
        return _feature_shared.ui.div(
            _feature_shared.ui.p(
                "The current .X processing state could not be verified. Run is blocked until you confirm it for these exact files.",
                class_="text-warning",
            ),
            _feature_shared.ui.input_action_button(
                "river_st_review_scale",
                "Confirm unknown expression state",
                class_="btn btn-outline-warning",
            ),
        )

    def _show_scale_confirmation():
        state = inspection.get() or {}
        unknown = [
            s
            for s in state.get("samples", [])
            if s.get("scale_evidence", {}).get("status") == "NEEDS_CONFIRMATION"
        ]
        if not unknown:
            return
        confirmation_generation["value"] += 1
        generation = str(confirmation_generation["value"])
        fields = []
        for sample in unknown:
            fields.append(
                _feature_shared.ui.input_radio_buttons(
                    "river_st_confirm_" + generation + "_" + sample["key"],
                    sample["file_name"],
                    choices={
                        "": "Choose the actual processing state",
                        "raw_counts": "Raw counts — normalize_total, then log1p",
                        "normalized_counts": "Already normalized, not logged — log1p only",
                        "log1p": "Already log1p-normalized — do not repeat either step",
                    },
                    selected="",
                )
            )
        confirmation_context.set(
            {
                "generation": generation,
                "scope": state["inspection_scope"],
                "signature": state["input_signature"],
                "source": _data_source(),
                "files": [(s["key"], s["scale_evidence"]["file_sha256"]) for s in unknown],
            }
        )
        _feature_shared.ui.modal_show(
            _feature_shared.ui.modal(
                _feature_shared.ui.p(
                    "No reliable, content-bound .X processing metadata was found. Values or filenames are not proof. Confirm using your preprocessing records; do not guess."
                ),
                *fields,
                _feature_shared.ui.input_checkbox(
                    "river_st_ack_" + generation,
                    "I checked the processing records for the current .X in each listed file.",
                    value=False,
                ),
                _feature_shared.ui.output_text("river_st_confirmation_error"),
                title="Confirm expression processing state",
                easy_close=False,
                footer=_feature_shared.ui.TagList(
                    _feature_shared.ui.input_action_button("river_st_cancel_scale", "Cancel"),
                    _feature_shared.ui.input_action_button(
                        "river_st_confirm_scale", "Confirm these files", class_="btn btn-primary"
                    ),
                ),
            )
        )

    @_feature_shared.reactive.Effect
    @_feature_shared.reactive.event(input.river_st_cancel_scale)
    def _cancel_scale_confirmation():
        confirmation_context.set(None)
        confirmation_error.set("")
        _feature_shared.ui.modal_remove()

    @_feature_shared.reactive.Effect
    @_feature_shared.reactive.event(input.river_st_review_scale)
    def _review_scale():
        _show_scale_confirmation()

    confirmation_error = _feature_shared.reactive.Value("")

    @output
    @_feature_shared.render.text
    def river_st_confirmation_error():
        return confirmation_error.get()

    @_feature_shared.reactive.Effect
    @_feature_shared.reactive.event(input.river_st_confirm_scale)
    def _confirm_scale():
        try:
            state = inspection.get() or {}
            context = confirmation_context.get() or {}
            owner = session_record_provider()
            scope = (owner.session_id if owner else "", str(analysis_session_id_provider() or ""))
            signature = _entry_signature(_feature_shared.request_entries(_inspection_request()))
            if (
                not context
                or tuple(context["scope"]) != scope
                or context["source"] != _data_source()
                or (signature != tuple((tuple(x) for x in context["signature"])))
                or (signature != tuple((tuple(x) for x in state.get("input_signature", ()))))
            ):
                raise ValueError(
                    "The files/source/analysis changed. Inspect again; this confirmation is no longer valid."
                )
            generation = context["generation"]
            if not _dynamic_value("river_st_ack_" + generation, False):
                raise ValueError("Acknowledge the checked processing records first.")
            pending = dict(context["files"])
            updated = []
            for position, sample in enumerate(state["samples"], start=1):
                evidence = sample.get("scale_evidence", {})
                if sample["key"] in pending:
                    if evidence.get("file_sha256") != pending[sample["key"]]:
                        raise ValueError("File content changed; inspect again.")
                    scale = str(
                        _dynamic_value("river_st_confirm_" + generation + "_" + sample["key"], "")
                    ).strip()
                    evidence = _feature_shared.confirmation_for(evidence, scale)
                updated.append(
                    dict(
                        sample,
                        scale_evidence=evidence,
                        display_order=_dynamic_value("river_st_order_" + sample["key"], position),
                        time_label=str(
                            _dynamic_value(
                                "river_st_time_" + sample["key"],
                                sample.get("time_label", sample["sample_id"]),
                            )
                        ),
                    )
                )
            inspection.set(dict(state, samples=updated))
            confirmation_context.set(None)
            confirmation_error.set("")
            _feature_shared.ui.modal_remove()
            inspection_status.set(
                "Expression state confirmed for the inspected file content. Review order and Run."
            )
        except Exception as exc:
            confirmation_error.set(str(exc))

    @output
    @_feature_shared.render.text
    def river_st_subsample_info():
        state = inspection.get()
        if not isinstance(state, dict) or not state.get("samples"):
            return "The fixed workflow samples 1,052 spots from every sample, including a sample with exactly 1,052 spots."
        counts = [sample["n_obs"] for sample in state["samples"]]
        minimum = min(counts)
        if minimum < 1052:
            return f"Smallest sample has {minimum:,} spots. At least 1,052 per sample are required; submission is blocked."
        return f"Smallest sample: {minimum:,} spots. Scanpy will subsample 1,052 per sample (random_state=0)."

    @output
    @_feature_shared.render.ui
    def river_st_top_gene_note():
        context = completed_context.get() or {}
        if not context.get("rank_count"):
            return None
        try:
            count = _feature_shared.positive_integer(
                _dynamic_value("river_st_top_n", 20), name="Top N"
            )
            if count > context["rank_count"]:
                raise ValueError(f"Top N cannot exceed {context['rank_count']:,} ranked genes.")
            return _feature_shared.ui.p(f"Top River genes: {count:,}", class_="cloud-muted")
        except ValueError as exc:
            return _feature_shared.ui.p(str(exc), class_="text-danger")

    @output
    @_feature_shared.render.data_frame
    def river_st_top_genes():
        import pandas as pd

        context = completed_context.get() or {}
        if not context.get("rank_count"):
            return None
        try:
            count = _feature_shared.positive_integer(
                _dynamic_value("river_st_top_n", 20), name="Top N"
            )
            if count > context["rank_count"]:
                return None
            rows = _feature_shared.read_ranking(_latest_completed_river_job(), limit=count)
            return _feature_shared.render.DataGrid(
                pd.DataFrame(rows, columns=["Rank", "Gene"]), height="320px"
            )
        except (ValueError, OSError):
            return None

    @_feature_shared.reactive.Effect
    @_feature_shared.reactive.event(input.river_st_preview)
    async def _preview():
        if inspection_busy.get():
            return
        inspection_busy.set(True)
        try:
            owner = session_record_provider()
            scope = (owner.session_id if owner else "", str(analysis_session_id_provider() or ""))
            request = _inspection_request()
            entries = _feature_shared.request_entries(request)
            prior = inspection.get()
            signature = _entry_signature(entries)
            inspection_status.set(
                "Inspecting package in a bounded background process; Run is disabled."
            )
            _progress(
                "show",
                title="Inspecting River inputs",
                detail="Validating files, real coordinates, common genes and optional annotations.",
            )
            if (
                isinstance(prior, dict)
                and tuple(prior.get("inspection_scope") or ()) == scope
                and (signature == tuple((tuple(x) for x in prior.get("input_signature") or ())))
            ):
                state = prior
            else:
                state = await _feature_shared.inspect_async(
                    request,
                    lambda index, count, name: _progress(
                        "update",
                        title="Inspecting River inputs",
                        detail=f"{index + 1}/{count}: {name}",
                    ),
                )
                state["samples"] = _feature_shared.apply_example_sample_defaults(
                    state["samples"], state.get("example_action_id")
                )
            current = session_record_provider()
            if scope != (
                current.session_id if current else "",
                str(analysis_session_id_provider() or ""),
            ):
                return
            now = _inspection_request()
            current_entries = _feature_shared.request_entries(now)
            if _entry_signature(current_entries) != signature:
                raise ValueError(
                    "Input selection changed while inspecting. Inspect the current selection again."
                )
            state["inspection_scope"] = scope
            inspection.set(state)
            confirmation_error.set("")
            unresolved = any(
                (s.get("scale_evidence", {}).get("status") != "RESOLVED" for s in state["samples"])
            )
            inspection_status.set(
                "Inspection complete. Confirm unknown .X processing states before Run."
                if unresolved
                else "Inspection complete; expression states verified. Review order and Run. Annotation is optional."
            )
            genes = list(state.get("common_genes") or [])
            annotation_column = _preferred_annotation_column(state)
            annotation_choices = {"": "No annotation (analysis is available)"}
            annotation_choices.update(
                {
                    "h5ad:" + column: "H5AD: " + column
                    for column in state.get("common_obs_columns") or []
                }
            )
            annotation_choices.update(
                {
                    "csv:" + column: "CSV: " + column
                    for column in state.get("common_csv_columns") or []
                }
            )
            _feature_shared.ui.update_selectize(
                "river_st_annotation_column",
                choices=annotation_choices,
                selected=annotation_column,
                server=True,
                session=session,
            )
            annotation_values = (
                list((state.get("common_obs_values") or {}).get(annotation_column, []))
                if annotation_column
                else []
            )
            value_choices = {"": "All clusters / categories"}
            value_choices.update({value: value for value in annotation_values})
            _feature_shared.ui.update_selectize(
                "river_st_annotation_value",
                choices=value_choices,
                selected="",
                server=True,
                session=session,
            )
            preview.set(
                f"Package recognized: {len(state['samples'])} time point(s), {len(genes)} shared gene(s), {len(state.get('common_obs_columns') or [])} shared grouping column(s). Review the order and labels, then run River. Gene plots are available from the completed result."
            )
            status.set("Inputs are recognized. No analysis has been submitted.")
            if unresolved:
                _show_scale_confirmation()
        except Exception as exc:
            inspection.set(None)
            inspection_status.set("Inspection failed; Run is disabled. " + str(exc))
            preview.set("")
            status.set(f"Package inspection failed: {exc}")
        finally:
            inspection_busy.set(False)
            _progress("done")

    @_feature_shared.reactive.Effect
    @_feature_shared.reactive.event(input.river_st_annotation_column)
    def _update_annotation_values():
        state = inspection.get()
        if not isinstance(state, dict):
            return
        selection = str(input.river_st_annotation_column() or "").strip()
        source, column = selection.split(":", 1) if ":" in selection else ("none", "")
        values = (
            list(
                (
                    state.get("common_csv_values" if source == "csv" else "common_obs_values") or {}
                ).get(column, [])
            )
            if column
            else []
        )
        choices = {"": "All clusters / categories"}
        choices.update({value: value for value in values})
        _feature_shared.ui.update_selectize(
            "river_st_annotation_value", choices=choices, selected="", server=True, session=session
        )

    @output
    @_feature_shared.render.ui
    def river_st_replot_result():
        result = replot_result.get()
        if not isinstance(result, dict):
            return None
        if result.get("error"):
            return _feature_shared.ui.tags.p(
                f"Gene redraw failed: {result['error']}", class_="text-danger"
            )
        gene = str(result.get("gene") or "gene")
        return _feature_shared.ui.div(
            _feature_shared.ui.tags.h4(f"Spatial plot for {gene}"),
            _feature_shared.ui.tags.p(
                "Rendered from the saved H5AD inputs; River training was not rerun.",
                class_="cloud-muted",
            ),
            _feature_shared.ui.p(
                f"Renderer: {result.get('renderer', 'unknown')} {result.get('renderer_version', '')}. "
                + (
                    "Squidpy is unavailable; this is a Scanpy rendering fallback, not an identical reproduction."
                    if result.get("renderer_fallback")
                    else "No expression normalization or model training was repeated."
                ),
                class_="cloud-muted",
            ),
            _feature_shared.ui.tags.img(
                src=result.get("png"),
                alt=f"River spatial expression for {gene}",
                style="display:block; width:100%; height:auto;",
            ),
            _feature_shared.ui.tags.a(
                "Download spatial PDF",
                href=result.get("pdf"),
                download=f"river_spatial_{gene}.pdf",
                class_="btn btn-sm btn-outline-danger",
                style="margin-top:8px;",
            ),
            style="padding:14px;border:1px solid #e5e7eb;border-radius:10px;margin:12px 0;",
        )

    @output
    @_feature_shared.render.ui
    def river_st_detected_inputs():
        state = inspection.get()
        if not isinstance(state, dict) or not state.get("samples"):
            return _feature_shared.ui.tags.p(
                "Inspect a package to configure its time-point order.", class_="cloud-muted"
            )
        rows = []
        for position, sample in enumerate(state["samples"], start=1):
            rows.append(
                _feature_shared.ui.div(
                    _feature_shared.ui.div(
                        _feature_shared.ui.tags.strong(sample["file_name"]),
                        _feature_shared.ui.tags.div(
                            f"{sample['n_obs']:,} observations × {sample['n_vars']:,} genes",
                            class_="cloud-muted",
                        ),
                        _feature_shared.ui.tags.div(
                            "Expression state: "
                            + str(
                                sample.get("scale_evidence", {}).get("scale")
                                or "confirmation required"
                            )
                            + " — "
                            + str(
                                sample.get("scale_evidence", {}).get("evidence_source")
                                or "not guessed"
                            ),
                            class_="cloud-muted",
                        ),
                        *(
                            [
                                _feature_shared.ui.tags.div(
                                    "Group: " + sample["group"], class_="cloud-muted"
                                )
                            ]
                            if sample.get("group")
                            else []
                        ),
                        style="flex: 2 1 320px;",
                    ),
                    _feature_shared.ui.div(
                        _feature_shared.ui.input_numeric(
                            f"river_st_order_{sample['key']}",
                            "Order",
                            value=sample.get("display_order", position),
                            min=1,
                            max=len(state["samples"]),
                            step=1,
                        ),
                        style="flex: 0 0 120px;",
                    ),
                    _feature_shared.ui.div(
                        _feature_shared.ui.input_text(
                            f"river_st_time_{sample['key']}",
                            "Time label",
                            value=sample.get("time_label", sample["sample_id"]),
                            placeholder="e.g. E10.5 or Day 7",
                        ),
                        style="flex: 1 1 220px;",
                    ),
                    style="display:flex; gap:12px; align-items:flex-end; padding:10px 0; border-bottom:1px solid #E5E7EB; flex-wrap:wrap;",
                )
            )
        common_columns = [str(value) for value in state.get("common_obs_columns") or []]
        default_column = _preferred_annotation_column(state)
        column_choices = {"": "No annotation (analysis is available)"}
        column_choices.update({"h5ad:" + column: "H5AD: " + column for column in common_columns})
        column_choices.update(
            {"csv:" + column: "CSV: " + column for column in state.get("common_csv_columns") or []}
        )
        value_choices = {"": "All clusters / categories"}
        if default_column:
            value_choices.update(
                {
                    value: value
                    for value in (state.get("common_obs_values") or {}).get(default_column, [])
                }
            )
        return _feature_shared.ui.div(
            _feature_shared.ui.h4("Detected time points", style="margin-top:16px;"),
            _feature_shared.ui.p(
                "Set unique order numbers (1 = earliest). Time labels are used on the generated temporal plot.",
                class_="cloud-muted",
            ),
            _feature_shared.ui.h4(
                "Spatial grouping for the combined River map", style="margin-top:16px;"
            ),
            _feature_shared.ui.p(
                "Choose any column shared by every H5AD (celltype is optional), then optionally highlight one cluster/category. These controls only affect figure rendering.",
                class_="cloud-muted",
            ),
            _feature_shared.ui.div(
                _feature_shared.ui.input_selectize(
                    "river_st_annotation_column",
                    "Shared grouping column",
                    choices=column_choices,
                    selected=default_column,
                    multiple=False,
                ),
                _feature_shared.ui.input_selectize(
                    "river_st_annotation_value",
                    "Highlight one cluster/category (optional)",
                    choices=value_choices,
                    selected="",
                    multiple=False,
                ),
                style="display:flex; gap:12px; flex-wrap:wrap; align-items:flex-end;",
            ),
            _feature_shared.ui.p(
                "Leave the category empty to show all groups. A selected category is highlighted while other spots are faded.",
                class_="cloud-muted",
            ),
            _feature_shared.ui.input_checkbox(
                "river_st_allow_missing_annotation",
                "Explicitly allow Unknown for missing selected annotations",
                value=False,
            ),
            *[
                _feature_shared.ui.p(
                    f"CSV {item['sample']}: {item['matched_barcodes']}/{item['total_barcodes']} barcodes matched.",
                    class_="cloud-muted",
                )
                for item in state.get("csv_match_summary") or []
            ],
            *rows,
        )

    @output
    @_feature_shared.render.ui
    def river_st_preview_result():
        value = preview.get()
        return _feature_shared.ui.tags.p(value, class_="cloud-muted") if value else None

    @output
    @_feature_shared.render.text
    def river_st_status():
        return status.get()

    @_feature_shared.reactive.Effect
    @_feature_shared.reactive.event(input.river_st_submit)
    def _submit():
        try:
            configuration = _validate_files()
            session_record = session_record_provider()
            if session_record is None:
                raise RuntimeError("Cloud session is not ready. Wait briefly, then try again.")
            analysis_session_id = analysis_session_id_provider()
            if not analysis_session_id:
                raise RuntimeError("Analysis session is not ready. Wait briefly, then try again.")
            existing_upload_ids = list(
                dict.fromkeys(configuration.get("existing_upload_ids") or [])
            )
            upload_ids = list(existing_upload_ids)
            if not configuration.get("example_action_id"):
                upload_ids.extend(
                    (
                        _register_upload(item).upload_id
                        for item in [
                            *configuration["upload_entries"],
                            *configuration["csv_entries"],
                        ]
                        if not str(item.get("upload_id") or "").strip()
                    )
                )
            from cloud.job_submission import JobSubmissionService

            submit_parameters = {
                **{
                    key: configuration[key]
                    for key in (
                        "execution_mode",
                        "data_source_mode",
                        "execution_contract_version",
                        "sample_evidence",
                        "sampling_random_state",
                        "annotation_source",
                        "allow_missing_annotation",
                    )
                },
                "source_mode": configuration["source_mode"],
                "input_source_mode": (
                    "EXAMPLE" if configuration["example_action_id"] else "USER_UPLOAD"
                ),
                "sample_order": configuration["sample_order"],
                "time_labels": configuration["time_labels"],
                "sample_labels": ",".join(configuration["time_labels"]),
                "sample_manifest": configuration["sample_manifest"],
                "representative_gene": configuration["representative_gene"],
                "annotation_column": configuration.get("annotation_column", ""),
                "annotation_value": configuration.get("annotation_value", ""),
                "subsample_size": configuration["subsample_size"],
                "subsample_mode": configuration["subsample_mode"],
                "river_epochs": configuration["river_epochs"],
                "random_seed": 42,
            }
            submission = JobSubmissionService()
            if configuration["example_action_id"]:
                job = submission.submit_with_example_action(
                    session=session_record,
                    workflow_name=_feature_shared.WORKFLOW,
                    example_action_id=configuration["example_action_id"],
                    parameters=submit_parameters,
                    requested_resource="auto",
                    analysis_session_id=analysis_session_id,
                )
            else:
                job = submission.submit(
                    session=session_record,
                    workflow_name=_feature_shared.WORKFLOW,
                    input_upload_ids=upload_ids,
                    parameters=submit_parameters,
                    requested_resource="auto",
                    analysis_session_id=analysis_session_id,
                )
            status.set(
                f"River job submitted: {job.job_id} ({job.status}); Original Python Parity. n_obs={configuration['subsample_size']:,} per sample. Gene plots will be available after analysis completes. GPU processing continues while this analysis session remains active; a prolonged disconnect can cancel it."
            )
            active_job_id.set(str(job.job_id))
            result_selection.reset_scope(session_record.session_id, str(analysis_session_id))
            result_selection.submitted(job.job_id)
            _clear_result_context()
            _feature_shared.ui.update_select("river_st_completed_job", selected="", session=session)
            _progress(
                "update",
                title="River analysis running",
                detail=f"Job {job.job_id}: {job.status}. You may continue in the background.",
            )
        except Exception as exc:
            status.set(f"River submission failed: {exc}")
            active_job_id.set("")
            _progress("failed")

    @_feature_shared.reactive.Effect
    def _poll_active_river_job():
        _feature_shared.reactive.invalidate_later(2)
        job_id = active_job_id.get()
        if not job_id:
            return
        session_record = session_record_provider()
        analysis_session_id = str(analysis_session_id_provider() or "").strip()
        if session_record is None or not analysis_session_id:
            return
        try:
            from cloud.database import CloudDatabase
            from cloud.models import TERMINAL_STATUSES

            job = next(
                (
                    item
                    for item in CloudDatabase(read_only=True).list_jobs(
                        session_id=session_record.session_id,
                        analysis_session_id=analysis_session_id,
                        limit=30,
                    )
                    if str(item.job_id) == job_id
                ),
                None,
            )
        except Exception:
            return
        if job is None:
            return
        job_status = str(job.status).upper()
        if job_status in {str(value).upper() for value in TERMINAL_STATUSES}:
            active_job_id.set("")
            last_progress["value"] = None
            if job_status == "SUCCEEDED":
                if result_selection.succeeded(job_id):
                    _clear_result_context()
                    jobs = list(completed_jobs.get())
                    if not any((str(j.job_id) == job_id for j in jobs)):
                        completed_jobs.set([job, *jobs])
                    _feature_shared.ui.update_select(
                        "river_st_completed_job", selected=job_id, session=session
                    )
                status.set(
                    f"River job {job_id} completed. Results and PDF downloads are available below."
                )
                _progress("done")
            else:
                if result_selection.failed(job_id):
                    _clear_result_context()
                status.set(
                    f"River job {job_id} ended with {job_status}: {job.current_step or 'See job details below.'}"
                )
                _progress("failed")
            return
        detail = f"Job {job_id}: {job_status}. {job.current_step or 'Waiting for worker progress.'}"
        if detail != last_progress["value"]:
            last_progress["value"] = detail
            _progress("update", title="River analysis running", detail=detail)

    @output
    @_feature_shared.render.ui
    def river_st_jobs():
        selection_epoch.get()
        current_job_id = active_job_id.get()
        session_record = session_record_provider()
        analysis_session_id = str(analysis_session_id_provider() or "").strip()
        if session_record is None or not analysis_session_id:
            return _feature_shared.ui.tags.p(
                "Waiting for the current tab analysis session.", class_="cloud-muted"
            )
        try:
            from cloud.database import CloudDatabase
            from cloud.models import ACTIVE_JOB_STATUSES

            jobs = [
                job
                for job in CloudDatabase(read_only=True).list_jobs(
                    session_id=session_record.session_id,
                    analysis_session_id=analysis_session_id,
                    limit=30,
                )
                if str(job.workflow_name or job.workflow) == _feature_shared.WORKFLOW
            ]
        except Exception as exc:
            _feature_shared.reactive.invalidate_later(2)
            return _feature_shared.ui.tags.p(
                f"River job status is temporarily unavailable: {exc}", class_="cloud-muted"
            )
        if not jobs:
            if current_job_id:
                _feature_shared.reactive.invalidate_later(2)
            return _feature_shared.ui.tags.p(
                "No River job has been submitted in this cloud session.", class_="cloud-muted"
            )
        if any((str(job.status).upper() in ACTIVE_JOB_STATUSES for job in jobs)) or (
            current_job_id and all((str(job.job_id) != current_job_id for job in jobs))
        ):
            _feature_shared.reactive.invalidate_later(2)
        rows = []
        for job in jobs[:5]:
            succeeded = str(job.status).lower() == "succeeded"
            links = result_links_builder(session_record.session_id, job) if succeeded else []
            previews = (
                result_previews_builder(session_record.session_id, job)
                if succeeded and str(job.job_id) == result_selection.selected_job_id
                else []
            )
            rows.append(
                _feature_shared.ui.div(
                    _feature_shared.ui.tags.strong(str(job.status)),
                    " — ",
                    str(job.job_id),
                    _feature_shared.ui.tags.div(str(job.current_step or ""), class_="cloud-muted"),
                    _feature_shared.ui.div(*links),
                    *previews,
                    style="padding: 8px 0; border-bottom: 1px solid #e5e7eb;",
                )
            )
        return _feature_shared.ui.div(*rows)


server = river_st_module_server
