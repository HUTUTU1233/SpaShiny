# Extracted from /app/app/ST-SM.py. Feature: enrichment_services; ordered phases preserve original initialization.
from spashiny._shared import runtime_globals as _spashiny_globals


def _install_0(_spashiny_ctx):

    def _enrichment_parse_csv_databases(value):
        return [
            item.strip()
            for item in _spashiny_ctx.re.split("[,;\\s]+", str(value or ""))
            if item.strip()
        ]

    _spashiny_ctx._enrichment_parse_csv_databases = _enrichment_parse_csv_databases

    def _enrichment_parse_database_selection(value):
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        return _spashiny_ctx._enrichment_parse_csv_databases(value)

    _spashiny_ctx._enrichment_parse_database_selection = _enrichment_parse_database_selection


def _install_1(_spashiny_ctx):

    def _enrichment_parse_fdr(value):
        try:
            parsed = float(value)
        except Exception:
            parsed = 0.05
        if parsed < 0 or parsed > 1:
            parsed = 0.05
        return parsed

    _spashiny_ctx._enrichment_parse_fdr = _enrichment_parse_fdr


def _install_2(_spashiny_ctx):

    def _enrichment_uploaded_columns(upload_value):
        files = upload_value or []
        if not files:
            return []
        file_entry = files[0]
        data_path = _spashiny_ctx.Path(str(file_entry.get("datapath") or ""))
        if not data_path.is_file():
            return []
        suffix = _spashiny_ctx.Path(str(file_entry.get("name") or data_path.name)).suffix.lower()
        try:
            sep = "\t" if suffix in {".tsv", ".txt"} else ","
            frame = _spashiny_ctx.pd.read_csv(data_path, sep=sep, nrows=0)
            return [str(col) for col in frame.columns]
        except Exception:
            return []

    _spashiny_ctx._enrichment_uploaded_columns = _enrichment_uploaded_columns

    def _preferred_enrichment_column(columns, preferred, fallback):
        available = [str(col) for col in columns or [] if str(col).strip()]
        if not available:
            return fallback
        lookup = {col.lower(): col for col in available}
        for item in preferred:
            match = lookup.get(str(item).lower())
            if match:
                return match
        return available[0]

    _spashiny_ctx._preferred_enrichment_column = _preferred_enrichment_column

    def _enrichment_column_select_ui(input_id, label, columns, preferred, fallback, note):
        choices = [str(col) for col in columns or [] if str(col).strip()]
        if not choices:
            choices = [fallback]
        selected = _spashiny_ctx._preferred_enrichment_column(choices, preferred, fallback)
        return _spashiny_ctx.ui.div(
            _spashiny_ctx.ui.input_select(input_id, label, choices=choices, selected=selected),
            _spashiny_ctx.ui.tags.div(
                note,
                class_="cloud-muted",
                style="font-size: 12px; margin-top: -8px; margin-bottom: 8px;",
            ),
        )

    _spashiny_ctx._enrichment_column_select_ui = _enrichment_column_select_ui

    def _register_enrichment_upload(file_entry, *, content_type="text/csv"):
        if not _spashiny_globals.SPASHINY_WEB_PLATFORM:
            raise RuntimeError(
                "CPU enrichment upload registration is only available in Lab/Web mode."
            )
        session_record = _spashiny_ctx._cloud_session_record()
        analysis_session_id = str(_spashiny_ctx._cloud_analysis_session_id() or "").strip()
        if session_record is None or not analysis_session_id:
            raise RuntimeError(
                "The current tab analysis session is not ready. Please wait for initialization."
            )
        if not file_entry:
            raise RuntimeError("Please choose an input file first.")
        data_path = _spashiny_ctx.Path(str(file_entry.get("datapath") or ""))
        if not data_path.is_file():
            raise RuntimeError("Uploaded file is not available to the web process.")
        filename = str(file_entry.get("name") or data_path.name)
        size_bytes = int(data_path.stat().st_size)
        if size_bytes <= 0:
            raise RuntimeError("Uploaded file is empty.")
        from cloud.upload_service import UploadPart, UploadService

        service = UploadService()
        upload_init = service.initiate_upload(
            session=session_record,
            analysis_session_id=analysis_session_id,
            filename=filename,
            size_bytes=size_bytes,
            content_type=content_type,
            total_parts=1,
        )
        upload_id = str(upload_init["upload_id"])
        record = service.database.get_upload(
            upload_id, session_id=session_record.session_id, analysis_session_id=analysis_session_id
        )
        if not hasattr(service.storage, "put_part"):
            raise RuntimeError(
                "Lab local upload storage does not support direct Shiny file registration."
            )
        etag = service.storage.put_part(record.multipart_upload_id, 1, data_path.read_bytes())
        return service.complete_upload(
            session=session_record,
            analysis_session_id=analysis_session_id,
            upload_id=upload_id,
            parts=[UploadPart(part_number=1, etag=etag)],
        )

    _spashiny_ctx._register_enrichment_upload = _register_enrichment_upload

    def _submit_enrichment_job_from_file(*, workflow_name, file_entry, parameters, status_value):
        session_record = _spashiny_ctx._cloud_session_record()
        if session_record is None:
            raise RuntimeError(
                "Anonymous cloud session is not ready. Please wait for session initialization."
            )
        analysis_session_id = _spashiny_ctx._cloud_analysis_session_id()
        if not analysis_session_id:
            raise RuntimeError("Analysis session is not ready. Please wait a moment and try again.")
        suffix = _spashiny_ctx.Path(str(file_entry.get("name") or "")).suffix.lower()
        content_type = {".tsv": "text/tab-separated-values", ".h5ad": "application/x-hdf5"}.get(
            suffix, "text/csv"
        )
        upload_record = _spashiny_ctx._register_enrichment_upload(
            file_entry, content_type=content_type
        )
        from cloud.job_submission import JobSubmissionService

        job = JobSubmissionService().submit(
            session=session_record,
            workflow_name=workflow_name,
            input_upload_ids=[upload_record.upload_id],
            parameters=dict(parameters or {}),
            requested_resource="cpu",
            analysis_session_id=analysis_session_id,
        )
        status_value.set(f"Submitted {workflow_name}: {job.job_id} ({job.status})")
        return job

    _spashiny_ctx._submit_enrichment_job_from_file = _submit_enrichment_job_from_file

    def _submit_enrichment_job_from_example_assets(
        *, workflow_name, asset_object_keys, parameters, status_value
    ):
        session_record = _spashiny_ctx._cloud_session_record()
        if session_record is None:
            raise RuntimeError(
                "Anonymous cloud session is not ready. Please wait for session initialization."
            )
        analysis_session_id = _spashiny_ctx._cloud_analysis_session_id()
        if not analysis_session_id:
            raise RuntimeError("Analysis session is not ready. Please wait a moment and try again.")
        from cloud.job_submission import JobSubmissionService

        job = JobSubmissionService().submit_with_assets(
            session=session_record,
            workflow_name=workflow_name,
            asset_object_keys=list(asset_object_keys or []),
            parameters=dict(parameters or {}),
            requested_resource="cpu",
            analysis_session_id=analysis_session_id,
        )
        status_value.set(f"Submitted {workflow_name}: {job.job_id} ({job.status})")
        return job

    _spashiny_ctx._submit_enrichment_job_from_example_assets = (
        _submit_enrichment_job_from_example_assets
    )

    def _marker_feature_table(kind):
        res = _spashiny_ctx.marker_res()
        if not res:
            raise RuntimeError("Please run Marker Analysis first.")
        source = res.get("gene_df" if kind == "gene" else "met_df")
        if source is None or getattr(source, "empty", True):
            raise RuntimeError(f"Current Marker Analysis has no {kind} table.")
        rows = []
        seen = set()
        value_column = "gene" if kind == "gene" else "metabolite"
        kegg_by_feature = {}
        if kind == "metabolite":
            adata_for_markers = res.get("adata") if isinstance(res, dict) else None
            var_df = getattr(adata_for_markers, "var", None)
            if var_df is not None and (not getattr(var_df, "empty", True)):
                kegg_col = None
                for candidate in [
                    "KEGG.ID",
                    "KEGG_ID",
                    "kegg_id",
                    "kegg",
                    "compound_id",
                    "kegg_compound_id",
                ]:
                    if candidate in var_df.columns:
                        kegg_col = candidate
                        break
                if kegg_col:
                    name_cols = [
                        col
                        for col in [
                            "metabolite",
                            "Metabolite",
                            "name",
                            "compound_name",
                            "feature_name",
                        ]
                        if col in var_df.columns
                    ]
                    for idx, var_row in var_df.iterrows():
                        raw_kegg = str(var_row.get(kegg_col, "") or "").strip()
                        raw_kegg = (
                            _spashiny_ctx.re.sub("(?i)^(kegg:|cpd:)", "", raw_kegg).strip().upper()
                        )
                        if not _spashiny_ctx.re.fullmatch("C\\d{5}", raw_kegg):
                            continue
                        keys = {str(idx).strip()}
                        for col in name_cols:
                            keys.add(str(var_row.get(col, "") or "").strip())
                        for key_name in keys:
                            if key_name and key_name.lower() not in {"nan", "none", "null"}:
                                kegg_by_feature.setdefault(key_name, raw_kegg)
        for state in list(source.columns):
            for rank, value in enumerate(source[state].tolist(), start=1):
                feature = str(value or "").strip()
                if not feature or feature.lower() in {"nan", "none", "null"}:
                    continue
                key = (feature, str(state))
                if key in seen:
                    continue
                seen.add(key)
                row = {value_column: feature, "State": str(state), "rank": rank}
                if kind == "metabolite":
                    direct = _spashiny_ctx.re.sub("(?i)^(kegg:|cpd:)", "", feature).strip().upper()
                    kegg_id = (
                        direct
                        if _spashiny_ctx.re.fullmatch("C\\d{5}", direct)
                        else kegg_by_feature.get(feature, "")
                    )
                    if kegg_id:
                        row["KEGG.ID"] = kegg_id
                rows.append(row)
        if not rows:
            raise RuntimeError(
                f"Current Marker Analysis {kind} table does not contain usable identifiers."
            )
        return _spashiny_ctx.pd.DataFrame(rows)

    _spashiny_ctx._marker_feature_table = _marker_feature_table

    def _submit_enrichment_job_from_dataframe(
        *, workflow_name, table, filename, parameters, status_value
    ):
        tmp_path = (
            _spashiny_ctx.Path(_spashiny_ctx.tempfile.mkdtemp(prefix="spashiny_enrichment_"))
            / filename
        )
        try:
            table.to_csv(tmp_path, index=False)
            return _spashiny_ctx._submit_enrichment_job_from_file(
                workflow_name=workflow_name,
                file_entry={"name": filename, "datapath": str(tmp_path)},
                parameters=parameters,
                status_value=status_value,
            )
        finally:
            try:
                _spashiny_ctx.shutil.rmtree(tmp_path.parent, ignore_errors=True)
            except Exception:
                pass

    _spashiny_ctx._submit_enrichment_job_from_dataframe = _submit_enrichment_job_from_dataframe

    def _enrichment_artifact_link(session_id, job, label, rel_path, *, css="btn-outline-primary"):
        url = _spashiny_ctx._cloud_result_download_url(
            session_id, getattr(job, "analysis_session_id", ""), job.job_id, rel_path
        )
        if not url:
            return None
        return _spashiny_ctx.ui.tags.a(
            label,
            href=url,
            download=_spashiny_ctx.Path(rel_path).name,
            class_=f"btn btn-sm {css}",
            style="margin: 4px 6px 4px 0;",
        )

    _spashiny_ctx._enrichment_artifact_link = _enrichment_artifact_link

    def _enrichment_job_result_ui(job_id, *, empty_message):
        job_id = str(job_id or "").strip()
        if not job_id:
            return _spashiny_ctx.ui.tags.div(
                _spashiny_ctx.ui.tags.p(empty_message, class_="cloud-muted")
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
        if status.lower() in {"queued_cpu", "queued_gpu", "queued", "running", "created"}:
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
            manifest = _spashiny_ctx._cloud_result_manifest(job)
            kind = "metabolite" if str(job.workflow) == "metabolite_enrichment" else "gene"
            rows.extend(
                _spashiny_globals.enrichment_artifact_ui(
                    owner=session_id, analysis=analysis_session_id, job=job, kind=kind
                )
            )
            if manifest:
                rows.append(
                    _spashiny_ctx.ui.tags.div(
                        f"Manifest files: {len(manifest.get('files') or [])}", class_="cloud-muted"
                    )
                )
        return _spashiny_ctx.ui.tags.div(*rows, class_="cloud-row")

    _spashiny_ctx._enrichment_job_result_ui = _enrichment_job_result_ui


def _install_3(_spashiny_ctx):

    def _bind_builtin_sm_annotation_example():
        """Bind the immutable Y7_T SM fixture to this exact tab analysis only."""
        session_record = _spashiny_ctx._cloud_session_record()
        analysis_session_id = str(_spashiny_ctx._cloud_analysis_session_id() or "").strip()
        if session_record is None or not analysis_session_id:
            raise RuntimeError(
                "The current tab analysis session is not ready. Please wait for initialization."
            )
        from cloud.example_action_bindings import ExampleActionBindingService

        action_id = "y7-sm-metabolite-annotation-example"
        payload = ExampleActionBindingService().activate(
            session=session_record,
            analysis_session_id=analysis_session_id,
            action_id=action_id,
            page_name="metabolite_annotation",
        )
        if not bool(payload.get("ready")):
            missing = ", ".join((str(item) for item in payload.get("missing_roles") or []))
            raise RuntimeError(
                "The built-in Y7_T spatial-metabolomics example is unavailable"
                + (f" (missing: {missing})." if missing else ".")
            )
        bindings = dict(_spashiny_ctx.cloud_example_action_bindings.get() or {})
        bindings[action_id] = dict(payload)
        _spashiny_ctx.cloud_example_action_bindings.set(bindings)
        return action_id

    _spashiny_ctx._bind_builtin_sm_annotation_example = _bind_builtin_sm_annotation_example


def _install_4(_spashiny_ctx):
    _spashiny_globals.register_enrichment_downloads(
        _spashiny_ctx.output,
        owner_provider=_spashiny_ctx._cloud_session_id,
        analysis_provider=_spashiny_ctx._cloud_analysis_session_id,
        job_providers={
            "gene": _spashiny_ctx.gene_enrichment_job_id.get,
            "metabolite": _spashiny_ctx.metabolite_enrichment_job_id.get,
        },
    )


def _install_5(_spashiny_ctx):

    @_spashiny_ctx.output
    @_spashiny_ctx.render.ui
    def cloud_my_files():
        try:
            from cloud.resource_manager import ResourceManager
            from cloud.file_manager import FileManager

            session_id = _spashiny_ctx._cloud_session_id()
            if not session_id:
                return _spashiny_ctx.ui.tags.div(
                    _spashiny_ctx.ui.tags.p(
                        "Anonymous cloud session is initializing. Cloud files are hidden until the session is ready.",
                        class_="cloud-muted",
                    )
                )
            resources = ResourceManager()
            files = FileManager()
            storage_used = resources.user_storage_bytes(session_id)
            recent_jobs = resources.database.list_jobs(session_id=session_id, limit=20)
            recent_uploads = resources.database.list_uploads(
                session_id=session_id,
                analysis_session_id=str(_spashiny_ctx._cloud_analysis_session_id() or ""),
                limit=20,
            )
            show_example_debug = bool(_spashiny_globals.SPASHINY_SHOW_EXAMPLE_ASSET_DEBUG)
            recent_references = (
                resources.database.list_example_asset_references(
                    session_id=session_id,
                    analysis_session_id=str(_spashiny_ctx._cloud_analysis_session_id() or ""),
                    limit=50,
                )
                if show_example_debug
                else []
            )
            input_count = 0
            for job in recent_jobs:
                input_count += len(files.list_job_files(job.user_id, job.job_id, "input"))
            upload_rows = []
            for upload in recent_uploads:
                upload_rows.append(
                    _spashiny_ctx.ui.tags.div(
                        _spashiny_ctx.ui.tags.strong(f"{upload.safe_filename} | {upload.status}"),
                        _spashiny_ctx.ui.tags.div(
                            f"Declared: {_spashiny_ctx._format_bytes(upload.declared_size_bytes)} | Actual: {_spashiny_ctx._format_bytes(upload.actual_size_bytes)}",
                            class_="cloud-muted",
                        ),
                        class_="cloud-row",
                    )
                )
            example_reference_rows = []
            for reference in recent_references:
                try:
                    import json

                    eligible = json.loads(reference.get("eligible_workflows_json") or "[]")
                except Exception:
                    eligible = []
                example_reference_rows.append(
                    _spashiny_ctx.ui.tags.div(
                        _spashiny_ctx.ui.tags.strong(
                            str(reference.get("display_name") or "Example Asset Reference")
                        ),
                        _spashiny_ctx.ui.tags.div(
                            "Type: Example Asset Reference", class_="cloud-muted"
                        ),
                        _spashiny_ctx.ui.tags.div(
                            f"Species: {reference.get('species') or 'Unknown'} | Modality: {reference.get('modality') or 'Unknown'} | Format: {reference.get('file_format') or 'Unknown'} | Size: {_spashiny_ctx._format_bytes(reference.get('size_bytes') or 0)}",
                            class_="cloud-muted",
                        ),
                        _spashiny_ctx.ui.tags.div(
                            f"Eligible workflows: {', '.join((str(item) for item in eligible)) or 'None'}",
                            class_="cloud-muted",
                        ),
                        _spashiny_ctx.ui.tags.div(
                            f"Manifest version: {reference.get('manifest_version') or 'unknown'} | Created: {reference.get('created_at') or ''}",
                            class_="cloud-muted",
                        ),
                        class_="cloud-row",
                    )
                )
            example_panel = None
            if show_example_debug:
                try:
                    from cloud.example_assets import ExampleAssetService

                    example_rows = []
                    for asset in ExampleAssetService().ui_rows()[:50]:
                        workflows = asset.get("applicable_workflows") or []
                        thumbnail = asset.get("thumbnail_url") or asset.get("preview_url") or ""
                        preview = (
                            _spashiny_ctx.ui.tags.div(
                                _spashiny_ctx.ui.tags.img(
                                    src=thumbnail,
                                    alt=f"{asset.get('name') or asset.get('display_name')} preview",
                                ),
                                class_="cloud-example-preview",
                            )
                            if thumbnail
                            else _spashiny_ctx.ui.tags.div(
                                "Preview", class_="cloud-example-preview"
                            )
                        )
                        example_rows.append(
                            _spashiny_ctx.ui.tags.div(
                                preview,
                                _spashiny_ctx.ui.tags.div(
                                    _spashiny_ctx.ui.tags.strong(
                                        asset.get("name")
                                        or asset.get("display_name")
                                        or asset.get("object_key")
                                    ),
                                    _spashiny_ctx.ui.tags.div(
                                        asset.get("description")
                                        or "Curated SpaShiny example data.",
                                        class_="cloud-muted",
                                    ),
                                    _spashiny_ctx.ui.tags.div(
                                        _spashiny_ctx.ui.tags.span(
                                            f"Species: {asset.get('species') or 'Unknown'}"
                                        ),
                                        _spashiny_ctx.ui.tags.span(
                                            f"Modality: {asset.get('data_modality') or asset.get('modality') or 'Unknown'}"
                                        ),
                                        _spashiny_ctx.ui.tags.span(
                                            f"Format: {asset.get('file_format') or 'Unknown'}"
                                        ),
                                        _spashiny_ctx.ui.tags.span(
                                            f"Size: {_spashiny_ctx._format_bytes(asset.get('file_size') or asset.get('size_bytes'))}"
                                        ),
                                        _spashiny_ctx.ui.tags.span(
                                            f"Workflow: {', '.join((str(item) for item in workflows)) or 'Auto'}"
                                        ),
                                        class_="cloud-example-meta",
                                    ),
                                ),
                                _spashiny_ctx.ui.tags.button(
                                    "Use Example Data",
                                    type="button",
                                    class_="cloud-use-example",
                                    **{
                                        "data-asset-id": asset.get("asset_id") or "",
                                        "data-manifest-version": asset.get("manifest_version")
                                        or "",
                                    },
                                ),
                                class_="cloud-row cloud-example-row",
                            )
                        )
                    example_panel = _spashiny_ctx.ui.tags.div(
                        _spashiny_ctx.ui.tags.h4("Example Assets"),
                        (
                            _spashiny_ctx.ui.tags.div(*example_rows, class_="cloud-list")
                            if example_rows
                            else _spashiny_ctx.ui.tags.p(
                                "No example assets found.", class_="cloud-muted"
                            )
                        ),
                    )
                except Exception:
                    example_panel = _spashiny_ctx.ui.tags.div(
                        _spashiny_ctx.ui.tags.h4("Example Assets"),
                        _spashiny_ctx.ui.tags.p(
                            "Example asset manifest is unavailable.", class_="cloud-muted"
                        ),
                    )
            metrics = [
                _spashiny_ctx.ui.tags.div(
                    _spashiny_ctx.ui.tags.div("Storage Used", class_="cloud-metric-title"),
                    _spashiny_ctx.ui.tags.div(
                        _spashiny_ctx._format_bytes(storage_used), class_="cloud-metric-value"
                    ),
                    class_="cloud-metric",
                ),
                _spashiny_ctx.ui.tags.div(
                    _spashiny_ctx.ui.tags.div("Recent Jobs", class_="cloud-metric-title"),
                    _spashiny_ctx.ui.tags.div(str(len(recent_jobs)), class_="cloud-metric-value"),
                    class_="cloud-metric",
                ),
                _spashiny_ctx.ui.tags.div(
                    _spashiny_ctx.ui.tags.div("Input Files", class_="cloud-metric-title"),
                    _spashiny_ctx.ui.tags.div(str(input_count), class_="cloud-metric-value"),
                    class_="cloud-metric",
                ),
            ]
            if show_example_debug:
                metrics.append(
                    _spashiny_ctx.ui.tags.div(
                        _spashiny_ctx.ui.tags.div(
                            "Example References", class_="cloud-metric-title"
                        ),
                        _spashiny_ctx.ui.tags.div(
                            str(len(recent_references)), class_="cloud-metric-value"
                        ),
                        class_="cloud-metric",
                    )
                )
            children = [
                _spashiny_ctx.ui.tags.div(*metrics, class_="cloud-grid"),
                (
                    _spashiny_ctx.ui.tags.div(*upload_rows, class_="cloud-list")
                    if upload_rows
                    else _spashiny_ctx.ui.tags.p("No temporary uploads yet.", class_="cloud-muted")
                ),
            ]
            if show_example_debug:
                children.extend(
                    [
                        _spashiny_ctx.ui.tags.h4("Example Data References"),
                        (
                            _spashiny_ctx.ui.tags.div(*example_reference_rows, class_="cloud-list")
                            if example_reference_rows
                            else _spashiny_ctx.ui.tags.p(
                                "No example data references yet.", class_="cloud-muted"
                            )
                        ),
                        example_panel,
                    ]
                )
            children.append(
                _spashiny_ctx.ui.tags.p(
                    "Files are isolated per user workspace and are managed by submitted jobs.",
                    class_="cloud-muted",
                )
            )
            return _spashiny_ctx.ui.tags.div(*[child for child in children if child is not None])
        except Exception as e:
            return _spashiny_ctx.ui.tags.div(
                _spashiny_ctx.ui.tags.p(
                    f"Cloud storage is not initialized yet: {e}", class_="cloud-muted"
                )
            )

    _spashiny_ctx.cloud_my_files = cloud_my_files


_STEPS = (_install_0, _install_1, _install_2, _install_3, _install_4, _install_5)


def server(_spashiny_ctx, step=0):
    return _STEPS[step](_spashiny_ctx)
