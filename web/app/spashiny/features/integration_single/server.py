# Extracted from /app/app/ST-SM.py. Feature: integration_single; ordered phases preserve original initialization.
from spashiny._shared import runtime_globals as _spashiny_globals


def _install_0(_spashiny_ctx):
    _spashiny_ctx.joint_h5ad_path = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.joint_input_source = _spashiny_ctx.reactive.Value("")

    def _invalidate_joint_preprocessing():
        _spashiny_ctx.joint_adata_processed.set(None)
        _spashiny_ctx.vae_processed_adata.set(None)
        _spashiny_ctx.feature_choices_loaded.set(False)
        _spashiny_ctx.knn_upload_chain_job_id.set("")
        _spashiny_ctx.joint_process_status.set(
            "Input changed; preprocess the selected joint data before training."
        )

    _spashiny_ctx._invalidate_joint_preprocessing = _invalidate_joint_preprocessing

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(
        _spashiny_ctx.input.cloud_example_action_activated, ignore_none=True
    )
    def _select_joint_example_from_cloud_action():
        if not _spashiny_globals.SPASHINY_WEB_PLATFORM:
            return
        payload = _spashiny_ctx.input.cloud_example_action_activated() or {}
        if (
            not isinstance(payload, dict)
            or not payload.get("ready")
            or payload.get("action_id") != "y7-joint-vit-example"
            or (
                str(payload.get("analysis_session_id") or "")
                != str(_spashiny_ctx._cloud_analysis_session_id() or "")
            )
        ):
            return
        try:
            from cloud.input_resolver import InputResolver

            resolved = InputResolver().resolve_interactive_local_input(
                session_id=_spashiny_ctx._require_cloud_session_id(),
                analysis_session_id=str(_spashiny_ctx._cloud_analysis_session_id() or ""),
                action_id="y7-joint-vit-example",
                input_role="joint_raw",
                workflow_name="st_sm_conditional_vae",
            )
            _spashiny_ctx.joint_h5ad_path.set(str(resolved["local_path"]))
            _spashiny_ctx.joint_data_loaded.set(True)
            _spashiny_ctx.joint_input_source.set("EXAMPLE")
            _spashiny_ctx._invalidate_joint_preprocessing()
            _spashiny_ctx.log(
                "Joint current input switched to Example — Y7_T raw joint H5AD. Click Process Joint Data or train the bound worker example."
            )
        except Exception as exc:
            _spashiny_ctx._invalidate_joint_preprocessing()
            _spashiny_ctx.joint_h5ad_path.set(None)
            _spashiny_ctx.joint_data_loaded.set(False)
            _spashiny_ctx.joint_input_source.set("")
            _spashiny_ctx.ui.notification_show(
                f"Joint Example input is unavailable: {exc}", type="error", duration=10
            )

    _spashiny_ctx._select_joint_example_from_cloud_action = _select_joint_example_from_cloud_action
    _spashiny_ctx.joint_data_loaded = _spashiny_ctx.reactive.Value(False)
    _spashiny_ctx.joint_adata_processed = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.joint_process_status = _spashiny_ctx.reactive.Value("Waiting for processing")
    _spashiny_ctx.joint_plot1 = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.joint_plot2 = _spashiny_ctx.reactive.Value(None)

    def _joint_processed_export_root():
        """Persistent, owner-scoped export root for processed joint h5ad files."""
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
            / "workflows"
            / "joint_preprocessing"
            / "exports"
        )

    _spashiny_ctx._joint_processed_export_root = _joint_processed_export_root

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.joint_data_upload)
    def save_joint_h5ad():
        """Save the uploaded joint data file"""
        try:
            file_info = _spashiny_ctx.input.joint_data_upload()
            if file_info is None:
                _spashiny_ctx.log("No file selected")
                _spashiny_ctx.joint_data_loaded.set(False)
                return
            _spashiny_ctx._invalidate_joint_preprocessing()
            _spashiny_ctx.joint_data_loaded.set(False)
            _spashiny_ctx.joint_h5ad_path.set(None)
            _spashiny_ctx.joint_input_source.set("")
            td = _spashiny_ctx.tempfile.mkdtemp()
            original_filename = file_info[0]["name"]
            dst = _spashiny_ctx.Path(td) / original_filename
            with open(dst, "wb") as out_f:
                out_f.write(_spashiny_ctx.Path(file_info[0]["datapath"]).read_bytes())
            _spashiny_ctx.joint_h5ad_path.set(str(dst))
            _spashiny_ctx.joint_data_loaded.set(True)
            _spashiny_ctx.joint_input_source.set("USER_UPLOAD")
            _spashiny_ctx.log(f"Joint data file saved to: {dst}")
            _spashiny_ctx.log(f" File size: {dst.stat().st_size / 1024 / 1024:.2f} MB")
            try:
                meta = _spashiny_globals.preview_h5ad_metadata(dst)
                adata = _spashiny_globals.SimpleNamespace(
                    shape=meta["shape"],
                    n_obs=meta["n_obs"],
                    n_vars=meta["n_vars"],
                    obs=_spashiny_ctx.pd.DataFrame(columns=meta["obs_columns"]),
                    var=_spashiny_ctx.pd.DataFrame(columns=meta["var_columns"]),
                )
                _spashiny_ctx.log(f" Data shape: {adata.shape}")
                _spashiny_ctx.log(f" Number of observations (cells/spots): {adata.n_obs}")
                _spashiny_ctx.log(f" Number of variables (genes/metabolites): {adata.n_vars}")
                _spashiny_ctx.log(f" Observation columns: {list(adata.obs.columns)[:5]}...")
                _spashiny_ctx.log(f" Variable columns: {list(adata.var.columns)[:5]}...")
            except Exception as e:
                _spashiny_ctx.log(f" Unable to preview file contents: {str(e)}")
        except Exception as e:
            error_msg = f"Failed to save joint data file: {str(e)}"
            _spashiny_ctx.log(error_msg)
            _spashiny_ctx.joint_data_loaded.set(False)

    _spashiny_ctx.save_joint_h5ad = save_joint_h5ad

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.process_joint_data)
    async def process_joint_data():
        import asyncio
        import traceback

        try:
            _spashiny_ctx.ui.modal_show(
                _spashiny_ctx.ui.modal(
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.h4(
                            "Processing Joint Data...", style="margin-bottom: 12px;"
                        ),
                        _spashiny_ctx.ui.p(
                            "Please wait while the uploaded joint dataset is being processed."
                        ),
                        _spashiny_ctx.ui.p(
                            "This may take a while depending on file size and selected parameters.",
                            style="color: #6e6e73;",
                        ),
                    ),
                    title="Running",
                    easy_close=False,
                    footer=None,
                )
            )
            with _spashiny_ctx.ui.Progress(min=1, max=9) as p:
                p.set(message="Initializing...", detail="Preparing workflow")
                p.set(1, message="Checking uploaded data...", detail="Validating input file")
                await asyncio.sleep(0.05)
                if (
                    _spashiny_globals.SPASHINY_WEB_PLATFORM
                    and _spashiny_ctx.joint_input_source.get() == "EXAMPLE"
                ):
                    from cloud.input_resolver import InputResolver

                    resolved = InputResolver().resolve_interactive_local_input(
                        session_id=_spashiny_ctx._require_cloud_session_id(),
                        analysis_session_id=str(_spashiny_ctx._cloud_analysis_session_id() or ""),
                        action_id="y7-joint-vit-example",
                        input_role="joint_raw",
                        workflow_name="st_sm_conditional_vae",
                    )
                    _spashiny_ctx.joint_h5ad_path.set(str(resolved["local_path"]))
                    _spashiny_ctx.joint_data_loaded.set(True)
                if not _spashiny_ctx.joint_data_loaded.get():
                    _spashiny_ctx.joint_process_status.set("Error: Please upload a data file first")
                    _spashiny_ctx.log("Error: Please upload a data file first")
                    _spashiny_ctx.ui.modal_remove()
                    _spashiny_ctx.ui.modal_show(
                        _spashiny_ctx.ui.modal(
                            "Please upload a joint data file (.h5ad) before processing.",
                            title="Processing Error",
                            easy_close=True,
                            footer=_spashiny_ctx.ui.div(
                                _spashiny_ctx.ui.input_action_button(
                                    "close_modal_process_no_file",
                                    "Close",
                                    class_="btn btn-secondary",
                                )
                            ),
                        )
                    )
                    return
                p.set(2, message="Checking file path...", detail="Verifying file existence")
                await asyncio.sleep(0.05)
                file_path = _spashiny_ctx.joint_h5ad_path.get()
                if file_path is None or not _spashiny_globals.os.path.exists(file_path):
                    _spashiny_ctx.joint_process_status.set("Error: Data file does not exist")
                    _spashiny_ctx.log("Error: Data file does not exist")
                    _spashiny_ctx.ui.modal_remove()
                    _spashiny_ctx.ui.modal_show(
                        _spashiny_ctx.ui.modal(
                            "The uploaded data file could not be found. Please re-upload the file.",
                            title="Processing Error",
                            easy_close=True,
                            footer=_spashiny_ctx.ui.div(
                                _spashiny_ctx.ui.input_action_button(
                                    "close_modal_process_missing_file",
                                    "Close",
                                    class_="btn btn-secondary",
                                )
                            ),
                        )
                    )
                    return
                _spashiny_ctx.joint_process_status.set("Starting processing...")
                _spashiny_ctx.log("Starting joint data processing...")
                sample_name = _spashiny_ctx.input.sample_name().strip()
                if not sample_name:
                    sample_name = "sample"
                with _spashiny_ctx.tempfile.TemporaryDirectory() as temp_dir:
                    _spashiny_ctx.log(f"Created temporary processing directory: {temp_dir}")
                    p.set(3, message="Reading data...", detail="Loading h5ad object")
                    _spashiny_ctx.joint_process_status.set("Reading data...")
                    _spashiny_ctx.log("Step 1: Reading data...")
                    await asyncio.sleep(0.05)
                    _spashiny_globals.preflight_memory(
                        "joint data processing",
                        bytes_needed=_spashiny_globals.os.path.getsize(file_path),
                        multiplier=4.0,
                        min_available_gb=2.0,
                        log_func=_spashiny_ctx.log,
                    )
                    joint_adata = _spashiny_globals.compact_adata_X(
                        _spashiny_globals.sc.read_h5ad(file_path)
                    )
                    _spashiny_ctx.log(f"Data read complete, shape: {joint_adata.shape}")
                    _spashiny_ctx.log(
                        f"Observations: {joint_adata.n_obs}, Variables: {joint_adata.n_vars}"
                    )
                    p.set(4, message="Filtering genes...", detail="Removing HSP / MT / RPL / DNAJ")
                    _spashiny_ctx.joint_process_status.set("Removing specific genes...")
                    _spashiny_ctx.log("Step 2: Removing HSP, MT, RPL, DNAJ genes...")
                    await asyncio.sleep(0.05)
                    joint_adata = _spashiny_globals.smt.pp.removeHSP_MT_RPL_DNAJ(joint_adata)
                    _spashiny_ctx.log(f"Gene filtering complete, new shape: {joint_adata.shape}")
                    p.set(5, message="Saving raw counts...", detail="Writing counts layer")
                    _spashiny_ctx.joint_process_status.set("Saving raw counts...")
                    _spashiny_ctx.log("Step 3: Saving raw counts to layers['counts']...")
                    await asyncio.sleep(0.05)
                    _spashiny_globals.set_compact_layer(joint_adata, "counts")
                    _spashiny_ctx.log("Raw counts saved")
                    p.set(
                        6,
                        message="Normalizing data...",
                        detail="Applying total count normalization",
                    )
                    _spashiny_ctx.joint_process_status.set("Normalizing data...")
                    _spashiny_ctx.log("Step 4: Normalizing data...")
                    await asyncio.sleep(0.05)
                    target_sum = _spashiny_ctx.input.target_sum()
                    _spashiny_globals.smt.pp.normalize_total_joint_adata_sm_st(
                        joint_adata, target_sum_SM=target_sum, target_sum_ST=target_sum
                    )
                    _spashiny_ctx.log(f"Normalization complete, target sum: {target_sum}")
                    _spashiny_ctx.joint_process_status.set("Saving normalized data...")
                    _spashiny_ctx.log("Step 5: Saving normalized data to layers['normalized']...")
                    _spashiny_globals.set_compact_layer(joint_adata, "normalized")
                    _spashiny_ctx.log("Normalized data saved")
                    _spashiny_ctx.joint_process_status.set("Saving raw data...")
                    _spashiny_ctx.log("Step 6: Saving raw data to .raw...")
                    joint_adata.raw = None
                    _spashiny_ctx.log("Raw data saved")
                    p.set(
                        7,
                        message="Selecting highly variable features...",
                        detail="Computing Moran's I",
                    )
                    _spashiny_ctx.joint_process_status.set("Selecting highly variable genes...")
                    _spashiny_ctx.log("Step 7: Selecting highly variable genes...")
                    await asyncio.sleep(0.05)
                    n_top_genes = _spashiny_ctx.input.n_top_genes()
                    n_top_metabolites = _spashiny_ctx.input.n_top_metabolites()
                    _spashiny_globals.smt.pp.spatial_variable_joint_adata_sm_st(
                        joint_adata,
                        n_top_genes=n_top_genes,
                        n_top_metabolites=n_top_metabolites,
                        add_key="highly_variable_moranI",
                    )
                    _spashiny_ctx.log(
                        f"Highly variable genes selected, genes: {n_top_genes}, metabolites: {n_top_metabolites}"
                    )
                    p.set(
                        8,
                        message="Filtering highly variable features...",
                        detail="Subsetting AnnData",
                    )
                    _spashiny_ctx.joint_process_status.set("Filtering highly variable genes...")
                    _spashiny_ctx.log("Step 8: Filtering highly variable genes...")
                    await asyncio.sleep(0.05)
                    if "highly_variable_moranI" in joint_adata.var.columns:
                        joint_adata = _spashiny_globals.compact_adata_X(
                            joint_adata[:, joint_adata.var.highly_variable_moranI].copy()
                        )
                        _spashiny_ctx.log(
                            f"Highly variable gene filtering complete, new shape: {joint_adata.shape}"
                        )
                    else:
                        _spashiny_ctx.log("Error: 'highly_variable_moranI' column not found")
                        _spashiny_ctx.joint_process_status.set(
                            "Error: Highly variable gene selection failed"
                        )
                        _spashiny_ctx.ui.modal_remove()
                        _spashiny_ctx.ui.modal_show(
                            _spashiny_ctx.ui.modal(
                                "The column 'highly_variable_moranI' was not found in joint_adata.var. Highly variable feature selection may have failed.",
                                title="Processing Error",
                                easy_close=True,
                                footer=_spashiny_ctx.ui.div(
                                    _spashiny_ctx.ui.input_action_button(
                                        "close_modal_process_hvg_fail",
                                        "Close",
                                        class_="btn btn-secondary",
                                    )
                                ),
                            )
                        )
                        return
                    p.set(9, message="Saving processed data...", detail="Writing final h5ad")
                    _spashiny_ctx.joint_process_status.set("Saving processed data...")
                    _spashiny_ctx.log("Step 9: Saving processed data...")
                    await asyncio.sleep(0.05)
                    output_filename = (
                        f"{sample_name}_adata_joint_hvf{n_top_genes + n_top_metabolites}.h5ad"
                    )
                    export_dir = (
                        _spashiny_ctx._joint_processed_export_root()
                        / f"{_spashiny_ctx.time.strftime('%Y%m%d_%H%M%S')}_{_spashiny_globals.uuid.uuid4().hex[:12]}"
                    )
                    export_dir.mkdir(parents=True, exist_ok=False)
                    output_path = export_dir / output_filename
                    joint_adata.write_h5ad(output_path)
                    output_size = output_path.stat().st_size if output_path.is_file() else 0
                    if output_size <= 0:
                        raise RuntimeError(
                            "Processed joint h5ad was not written to persistent result storage."
                        )
                    _spashiny_ctx.log(
                        f"Processed data saved persistently: {output_path} ({output_size} bytes)"
                    )
                    _spashiny_ctx.joint_adata_processed.set(
                        {
                            "adata": joint_adata,
                            "file_path": str(output_path),
                            "filename": output_filename,
                            "size_bytes": output_size,
                        }
                    )
                    _spashiny_ctx.vae_processed_adata.set(joint_adata)
                    _spashiny_ctx.feature_choices_loaded.set(False)
                    _spashiny_ctx.joint_process_status.set("Processing complete!")
                    _spashiny_ctx.log("Joint data preprocessing complete!")
                    _spashiny_ctx.log(f"Final data shape: {joint_adata.shape}")
                    _spashiny_ctx.log(f"Output file: {output_filename}")
            _spashiny_ctx.ui.modal_remove()
            _spashiny_ctx.ui.modal_show(
                _spashiny_ctx.ui.modal(
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.h4("Processing Complete", style="margin-bottom: 12px;"),
                        _spashiny_ctx.ui.p("Joint data preprocessing finished successfully."),
                        _spashiny_ctx.ui.p(
                            f"Final shape: {joint_adata.shape}", style="color: #6e6e73;"
                        ),
                        _spashiny_ctx.ui.p(
                            f"Output file: {output_filename}", style="color: #6e6e73;"
                        ),
                    ),
                    title="Success",
                    easy_close=True,
                    footer=_spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.input_action_button(
                            "close_modal_process_success", "Close", class_="btn btn-success"
                        )
                    ),
                )
            )
        except Exception as e:
            error_msg = _spashiny_globals.user_facing_error("Joint data processing failed", e)
            _spashiny_ctx.joint_process_status.set(error_msg)
            _spashiny_ctx.log(error_msg)
            _spashiny_globals.notify_memory_warning(
                error_msg, duration=14 if _spashiny_globals.is_memory_related_exception(e) else 8
            )
            print(error_msg)
            traceback.print_exc()
            _spashiny_ctx.ui.modal_remove()
            _spashiny_ctx.ui.modal_show(
                _spashiny_ctx.ui.modal(
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.h4(
                            "Joint Data Processing Failed",
                            style="margin-bottom: 12px; color: #ff3b30;",
                        ),
                        _spashiny_ctx.ui.p(
                            "An error occurred during joint data preprocessing. Please check the logs for details and try again.",
                            style="color: #6e6e73;Click outside the box to cancel this notification.",
                        ),
                        _spashiny_ctx.ui.pre(
                            error_msg,
                            style="white-space: pre-wrap; font-size: 0.92rem; color: #6e6e73;",
                        ),
                    ),
                    title="Processing Error",
                    easy_close=True,
                    footer=_spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.input_action_button(
                            "close_modal_process_error", "Close", class_="btn btn-danger"
                        )
                    ),
                )
            )

    _spashiny_ctx.process_joint_data = process_joint_data

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.close_modal_process_no_file)
    def _():
        _spashiny_ctx.ui.modal_remove()

    _spashiny_ctx._ = _

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.close_modal_process_missing_file)
    def _():
        _spashiny_ctx.ui.modal_remove()

    _spashiny_ctx._ = _

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.close_modal_process_hvg_fail)
    def _():
        _spashiny_ctx.ui.modal_remove()

    _spashiny_ctx._ = _

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.close_modal_process_success)
    def _():
        _spashiny_ctx.ui.modal_remove()

    _spashiny_ctx._ = _

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.close_modal_process_error)
    def _():
        _spashiny_ctx.ui.modal_remove()

    _spashiny_ctx._ = _

    @_spashiny_ctx.render.download(
        filename=lambda: (
            _spashiny_ctx.joint_adata_processed.get()["filename"]
            if _spashiny_ctx.joint_adata_processed.get() is not None
            else "processed_joint_data.h5ad"
        )
    )
    def download_joint_h5ad():
        data_info = _spashiny_ctx.joint_adata_processed.get() or {}
        file_path = _spashiny_ctx.Path(str(data_info.get("file_path") or ""))
        if not file_path.is_file() or file_path.stat().st_size <= 0:
            message = "Processed joint h5ad is unavailable. Please run joint preprocessing again before downloading."
            _spashiny_ctx.log(f"Download failed: {message} path={file_path}")
            raise FileNotFoundError(message)
        try:
            with file_path.open("rb") as handle:
                while True:
                    chunk = handle.read(1024 * 1024)
                    if not chunk:
                        break
                    yield chunk
        finally:
            _spashiny_globals.release_unused_memory()

    _spashiny_ctx.download_joint_h5ad = download_joint_h5ad

    @_spashiny_ctx.output
    @_spashiny_ctx.render.ui
    def joint_download_ui():
        data_info = _spashiny_ctx.joint_adata_processed.get() or {}
        file_path = _spashiny_ctx.Path(str(data_info.get("file_path") or ""))
        size_bytes = file_path.stat().st_size if file_path.is_file() else 0
        if size_bytes <= 0:
            return _spashiny_ctx.ui.div(
                "Processed h5ad is not available for download. Run joint preprocessing again.",
                class_="text-warning",
            )
        return _spashiny_ctx.ui.div(
            _spashiny_ctx.ui.strong("Ready for download: "),
            f"{data_info.get('filename', 'processed_joint_data.h5ad')} ({_spashiny_ctx._format_bytes(size_bytes)})",
            class_="text-success",
        )

    _spashiny_ctx.joint_download_ui = joint_download_ui

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.preview_joint_data)
    def preview_joint_data():
        """Preview processed joint data in a modal"""
        try:
            joint_data = _spashiny_ctx.joint_adata_processed.get()
            if joint_data is None:
                _spashiny_ctx.log("Error: Please process the data first.")
                _spashiny_ctx.ui.modal_show(
                    _spashiny_ctx.ui.modal(
                        _spashiny_ctx.ui.p(
                            "No processed joint data found. Please run preprocessing first."
                        ),
                        title="Preview Data",
                        easy_close=True,
                        footer=_spashiny_ctx.ui.modal_button("Close"),
                    )
                )
                return
            adata = joint_data["adata"]
            shape_text = f"{adata.shape[0]}  {adata.shape[1]}"
            obs_cols = ", ".join(list(adata.obs.columns)) if len(adata.obs.columns) > 0 else "None"
            var_cols = ", ".join(list(adata.var.columns)) if len(adata.var.columns) > 0 else "None"
            layer_keys = (
                ", ".join(list(adata.layers.keys())) if len(adata.layers.keys()) > 0 else "None"
            )
            if "highly_variable_moranI" in adata.var.columns:
                try:
                    n_high_var = int(adata.var["highly_variable_moranI"].sum())
                except Exception:
                    n_high_var = "Unavailable"
            else:
                n_high_var = "Not found"
            if "spatial" in adata.obsm:
                spatial_shape = str(adata.obsm["spatial"].shape)
                spatial_status = "Found"
            else:
                spatial_shape = "N/A"
                spatial_status = "Not found"
            obs_preview = adata.obs.head(8).to_html(
                classes="table table-striped table-sm", border=0
            )
            var_preview = adata.var.head(8).to_html(
                classes="table table-striped table-sm", border=0
            )
            _spashiny_ctx.log(" [Preview] Joint data preview opened.")
            _spashiny_ctx.ui.modal_show(
                _spashiny_ctx.ui.modal(
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.h3("Joint Data Preview", style="margin-bottom: 16px;"),
                        _spashiny_ctx.ui.p(
                            "This panel summarizes the processed joint AnnData object, including dimensions, metadata columns, layers, and spatial information.",
                            style="color: #6e6e73; line-height: 1.7;",
                        ),
                        _spashiny_ctx.ui.hr(),
                        _spashiny_ctx.ui.h5("Basic Information"),
                        _spashiny_ctx.ui.tags.ul(
                            _spashiny_ctx.ui.tags.li(f"Shape: {shape_text}"),
                            _spashiny_ctx.ui.tags.li(f"Observations (cells/spots): {adata.n_obs}"),
                            _spashiny_ctx.ui.tags.li(
                                f"Variables (genes/metabolites): {adata.n_vars}"
                            ),
                            _spashiny_ctx.ui.tags.li(f"Highly variable features: {n_high_var}"),
                        ),
                        _spashiny_ctx.ui.hr(),
                        _spashiny_ctx.ui.h5("Metadata Structure"),
                        _spashiny_ctx.ui.tags.ul(
                            _spashiny_ctx.ui.tags.li(f"obs columns: {obs_cols}"),
                            _spashiny_ctx.ui.tags.li(f"var columns: {var_cols}"),
                            _spashiny_ctx.ui.tags.li(f"layers: {layer_keys}"),
                        ),
                        _spashiny_ctx.ui.hr(),
                        _spashiny_ctx.ui.h5("Spatial Information"),
                        _spashiny_ctx.ui.tags.ul(
                            _spashiny_ctx.ui.tags.li(f"Spatial coordinates: {spatial_status}"),
                            _spashiny_ctx.ui.tags.li(f"Spatial shape: {spatial_shape}"),
                        ),
                        _spashiny_ctx.ui.hr(),
                        _spashiny_ctx.ui.h5("obs Preview"),
                        _spashiny_ctx.ui.HTML(
                            f'\n                            <div style="overflow-x:auto; max-height:260px; overflow-y:auto; border:1px solid #eee; border-radius:16px; padding:10px; background:#fafafa;">\n                                {obs_preview}\n                            </div>\n                            '
                        ),
                        _spashiny_ctx.ui.br(),
                        _spashiny_ctx.ui.h5("var Preview"),
                        _spashiny_ctx.ui.HTML(
                            f'\n                            <div style="overflow-x:auto; max-height:260px; overflow-y:auto; border:1px solid #eee; border-radius:16px; padding:10px; background:#fafafa;">\n                                {var_preview}\n                            </div>\n                            '
                        ),
                    ),
                    title="Preview Data",
                    easy_close=True,
                    size="xl",
                    footer=_spashiny_ctx.ui.modal_button("Close"),
                )
            )
        except Exception as e:
            _spashiny_ctx.log(f"[Preview] Data preview failed: {str(e)}")
            _spashiny_ctx.ui.modal_show(
                _spashiny_ctx.ui.modal(
                    _spashiny_ctx.ui.p(f"Data preview failed:\n{str(e)}"),
                    title="Preview Error",
                    easy_close=True,
                    footer=_spashiny_ctx.ui.modal_button("Close"),
                )
            )

    _spashiny_ctx.preview_joint_data = preview_joint_data

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.debug_data)
    def debug_data():
        """Debug current data state in a modal"""
        try:
            _spashiny_ctx.log("[Debug] Data status inspection opened.")
            loaded_status = _spashiny_ctx.joint_data_loaded.get()
            file_path = _spashiny_ctx.joint_h5ad_path.get()
            if file_path and _spashiny_globals.os.path.exists(file_path):
                file_exists = "Yes"
                file_size = f"{_spashiny_globals.os.path.getsize(file_path):,} bytes"
            else:
                file_exists = "No"
                file_size = "N/A"
            joint_data = _spashiny_ctx.joint_adata_processed.get()
            if joint_data is not None:
                processed_status = "Loaded"
                processed_shape = str(joint_data["adata"].shape)
                processed_filename = joint_data.get("filename", "Unknown")
            else:
                processed_status = "Not loaded"
                processed_shape = "N/A"
                processed_filename = "N/A"
            trained = _spashiny_ctx.trained_model.get() is not None
            loss_ready = _spashiny_ctx.loss_history.get() is not None
            _spashiny_ctx.ui.modal_show(
                _spashiny_ctx.ui.modal(
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.h3(
                            "System Debug Information", style="margin-bottom: 16px;"
                        ),
                        _spashiny_ctx.ui.p(
                            "This panel helps diagnose the current data and model state in the SM-ST joint analysis workflow.",
                            style="color: #6e6e73; line-height: 1.7;",
                        ),
                        _spashiny_ctx.ui.hr(),
                        _spashiny_ctx.ui.h5("Upload Status"),
                        _spashiny_ctx.ui.tags.ul(
                            _spashiny_ctx.ui.tags.li(f"joint_data_loaded: {loaded_status}"),
                            _spashiny_ctx.ui.tags.li(
                                f"joint_h5ad_path: {(file_path if file_path else 'None')}"
                            ),
                            _spashiny_ctx.ui.tags.li(f"File exists: {file_exists}"),
                            _spashiny_ctx.ui.tags.li(f"File size: {file_size}"),
                        ),
                        _spashiny_ctx.ui.hr(),
                        _spashiny_ctx.ui.h5("Processed Data Status"),
                        _spashiny_ctx.ui.tags.ul(
                            _spashiny_ctx.ui.tags.li(f"Processed joint data: {processed_status}"),
                            _spashiny_ctx.ui.tags.li(f"Processed shape: {processed_shape}"),
                            _spashiny_ctx.ui.tags.li(f"Processed filename: {processed_filename}"),
                        ),
                        _spashiny_ctx.ui.hr(),
                        _spashiny_ctx.ui.h5("Training State"),
                        _spashiny_ctx.ui.tags.ul(
                            _spashiny_ctx.ui.tags.li(
                                f"Training in progress: {_spashiny_ctx.training_in_progress.get()}"
                            ),
                            _spashiny_ctx.ui.tags.li(f"Trained model exists: {trained}"),
                            _spashiny_ctx.ui.tags.li(f"Loss history exists: {loss_ready}"),
                            _spashiny_ctx.ui.tags.li(
                                f"Training status: {_spashiny_ctx.training_status_reactive.get()}"
                            ),
                        ),
                    ),
                    title="Debug Data Status",
                    easy_close=True,
                    size="l",
                    footer=_spashiny_ctx.ui.modal_button("Close"),
                )
            )
        except Exception as e:
            _spashiny_ctx.log(f"[Debug] Debug modal failed: {str(e)}")
            _spashiny_ctx.ui.modal_show(
                _spashiny_ctx.ui.modal(
                    _spashiny_ctx.ui.p(f"Debug inspection failed:\n{str(e)}"),
                    title="Debug Error",
                    easy_close=True,
                    footer=_spashiny_ctx.ui.modal_button("Close"),
                )
            )

    _spashiny_ctx.debug_data = debug_data

    @_spashiny_ctx.render.text
    def joint_process_log():
        return _spashiny_ctx.joint_process_status.get()

    _spashiny_ctx.joint_process_log = joint_process_log
    _spashiny_ctx.trained_model = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.training_in_progress = _spashiny_ctx.reactive.Value(False)
    _spashiny_ctx.loss_history = _spashiny_ctx.reactive.Value({})
    _spashiny_ctx.training_status_reactive = _spashiny_ctx.reactive.Value("Not started")
    _spashiny_ctx.vae_processed_adata = _spashiny_ctx.reactive.Value(None)
    import spatialmeta as smt

    _spashiny_globals.smt = smt
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
    import matplotlib.pyplot as plt

    _spashiny_globals.plt = plt
    _spashiny_ctx.model_config = _spashiny_ctx.reactive.Value(
        _spashiny_globals.tutorial_model_defaults(_spashiny_globals.smt)
    )
    _spashiny_ctx.training_config = _spashiny_ctx.reactive.Value(
        _spashiny_globals.tutorial_training_defaults(_spashiny_globals.smt)
    )

    @_spashiny_ctx.output
    @_spashiny_ctx.render.text
    def model_config_summary():
        return "SpatialMETA tutorial parameters; no platform training overrides."

    _spashiny_ctx.model_config_summary = model_config_summary

    @_spashiny_ctx.render.ui
    def joint_resource_mode_details():
        return _spashiny_ctx.ui.div()

    _spashiny_ctx.joint_resource_mode_details = joint_resource_mode_details

    @_spashiny_ctx.output
    @_spashiny_ctx.render.text
    def training_config_summary():
        return ""

    _spashiny_ctx.training_config_summary = training_config_summary

    @_spashiny_ctx.render.ui
    def data_status_indicator():
        is_loaded = _spashiny_ctx.joint_data_loaded.get()
        if is_loaded:
            return _spashiny_ctx.ui.div(
                _spashiny_ctx.ui.span("[OK]", style="color: green; font-weight: bold;"),
                " Data loaded",
                style="color: green; font-weight: bold; margin: 10px 0;",
            )
        else:
            return _spashiny_ctx.ui.div(
                _spashiny_ctx.ui.span("[WAIT]", style="color: orange; font-weight: bold;"),
                " Waiting for data upload",
                style="color: orange; font-weight: bold; margin: 10px 0;",
            )

    _spashiny_ctx.data_status_indicator = data_status_indicator

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.open_model_config_modal)
    def open_model_config_modal():
        _spashiny_ctx.ui.modal_show(
            _spashiny_ctx.ui.modal(
                _spashiny_ctx.ui.div(),
                _spashiny_ctx.ui.pre(
                    _spashiny_ctx.json.dumps(
                        _spashiny_globals.tutorial_model_defaults(_spashiny_globals.smt),
                        indent=2,
                        default=str,
                    )
                ),
                title="SpatialMETA tutorial parameters (read only)",
                easy_close=True,
            )
        )

    _spashiny_ctx.open_model_config_modal = open_model_config_modal

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.close_model_config_modal)
    def close_model_config_modal():
        _spashiny_ctx.ui.modal_remove()

    _spashiny_ctx.close_model_config_modal = close_model_config_modal

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.save_model_config)
    def save_model_config():
        _spashiny_ctx.model_config.set(
            _spashiny_globals.tutorial_model_defaults(_spashiny_globals.smt)
        )
        _spashiny_ctx.training_config.set(
            _spashiny_globals.tutorial_training_defaults(_spashiny_globals.smt)
        )

    _spashiny_ctx.save_model_config = save_model_config

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.reset_model_config)
    def reset_model_config():
        _spashiny_ctx.model_config.set(
            _spashiny_globals.tutorial_model_defaults(_spashiny_globals.smt)
        )
        _spashiny_ctx.training_config.set(
            _spashiny_globals.tutorial_training_defaults(_spashiny_globals.smt)
        )

    _spashiny_ctx.reset_model_config = reset_model_config

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.use_original_model_config)
    def use_original_model_config():
        _spashiny_ctx.model_config.set(
            _spashiny_globals.tutorial_model_defaults(_spashiny_globals.smt)
        )
        _spashiny_ctx.training_config.set(
            _spashiny_globals.tutorial_training_defaults(_spashiny_globals.smt)
        )

    _spashiny_ctx.use_original_model_config = use_original_model_config

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.use_original_training_config)
    def use_original_training_config():
        _spashiny_ctx.model_config.set(
            _spashiny_globals.tutorial_model_defaults(_spashiny_globals.smt)
        )
        _spashiny_ctx.training_config.set(
            _spashiny_globals.tutorial_training_defaults(_spashiny_globals.smt)
        )

    _spashiny_ctx.use_original_training_config = use_original_training_config

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.open_training_config_modal)
    def open_training_config_modal():
        _spashiny_ctx.ui.modal_show(
            _spashiny_ctx.ui.modal(
                _spashiny_ctx.ui.div(),
                _spashiny_ctx.ui.pre(
                    _spashiny_ctx.json.dumps(
                        _spashiny_globals.tutorial_training_defaults(_spashiny_globals.smt),
                        indent=2,
                        default=str,
                    )
                ),
                title="SpatialMETA tutorial parameters (read only)",
                easy_close=True,
            )
        )

    _spashiny_ctx.open_training_config_modal = open_training_config_modal

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.close_training_config_modal)
    def close_training_config_modal():
        _spashiny_ctx.ui.modal_remove()

    _spashiny_ctx.close_training_config_modal = close_training_config_modal

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.save_training_config)
    def save_training_config():
        _spashiny_ctx.model_config.set(
            _spashiny_globals.tutorial_model_defaults(_spashiny_globals.smt)
        )
        _spashiny_ctx.training_config.set(
            _spashiny_globals.tutorial_training_defaults(_spashiny_globals.smt)
        )

    _spashiny_ctx.save_training_config = save_training_config

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.reset_training_config)
    def reset_training_config():
        _spashiny_ctx.model_config.set(
            _spashiny_globals.tutorial_model_defaults(_spashiny_globals.smt)
        )
        _spashiny_ctx.training_config.set(
            _spashiny_globals.tutorial_training_defaults(_spashiny_globals.smt)
        )

    _spashiny_ctx.reset_training_config = reset_training_config
    _spashiny_ctx.trained_model = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.loss_history = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.training_in_progress = _spashiny_ctx.reactive.Value(False)
    _spashiny_ctx.training_status_reactive = _spashiny_ctx.reactive.Value("Waiting for training")
    _spashiny_ctx.training_job_dir = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.training_result_path = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.training_summary = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.training_loss_path = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.MODEL_REUSE_CONFIG_SCHEMA = "spashiny.conditional_vae_model_config"
    _spashiny_ctx.MODEL_REUSE_CONFIG_VERSION = 1
    _spashiny_ctx.MODEL_CONFIG_KEYS = (
        "n_latent",
        "hidden_stacks",
        "batch_keys",
        "bias",
        "use_batch_norm",
        "use_layer_norm",
        "dropout_rate",
        "batch_embedding",
        "encode_libsize",
        "batch_hidden_dim",
        "reconstruction_method_st",
        "reconstruction_method_sm",
    )
    _spashiny_ctx.TRAINING_CONFIG_KEYS = (
        "max_epoch",
        "n_per_batch",
        "mode",
        "lr",
        "kl_weight",
        "reconstruction_st_weight",
        "reconstruction_sm_weight",
        "n_epochs_kl_warmup",
        "weight_decay",
    )

    def _resolve_imported_result_path(raw_path):
        if not raw_path:
            return None
        candidate = _spashiny_ctx.Path(str(raw_path)).expanduser()
        if not candidate.is_absolute():
            candidate = _spashiny_globals.WORKSPACE_ROOT / candidate
        return str(candidate)

    _spashiny_ctx._resolve_imported_result_path = _resolve_imported_result_path

    def _select_known_config_values(raw_cfg, required_keys, label):
        if not isinstance(raw_cfg, dict):
            raise ValueError(f"{label} must be a JSON object")
        missing = [key for key in required_keys if key not in raw_cfg]
        if missing:
            raise ValueError(f"{label} is missing required fields: {', '.join(missing)}")
        return {key: raw_cfg[key] for key in required_keys}

    _spashiny_ctx._select_known_config_values = _select_known_config_values

    def _sync_model_config_inputs(cfg):
        try:
            _spashiny_ctx.ui.update_numeric("n_latent", value=cfg["n_latent"])
            _spashiny_ctx.ui.update_text("hidden_stacks", value=cfg["hidden_stacks"])
            _spashiny_ctx.ui.update_text("batch_keys", value=cfg["batch_keys"])
            _spashiny_ctx.ui.update_checkbox("bias", value=cfg["bias"])
            _spashiny_ctx.ui.update_checkbox("use_batch_norm", value=cfg["use_batch_norm"])
            _spashiny_ctx.ui.update_checkbox("use_layer_norm", value=cfg["use_layer_norm"])
            _spashiny_ctx.ui.update_numeric("dropout_rate", value=cfg["dropout_rate"])
            _spashiny_ctx.ui.update_select("batch_embedding", selected=cfg["batch_embedding"])
            _spashiny_ctx.ui.update_checkbox("encode_libsize", value=cfg["encode_libsize"])
            _spashiny_ctx.ui.update_numeric("batch_hidden_dim", value=cfg["batch_hidden_dim"])
            _spashiny_ctx.ui.update_select(
                "reconstruction_method_st", selected=cfg["reconstruction_method_st"]
            )
            _spashiny_ctx.ui.update_select(
                "reconstruction_method_sm", selected=cfg["reconstruction_method_sm"]
            )
        except Exception:
            pass

    _spashiny_ctx._sync_model_config_inputs = _sync_model_config_inputs

    def _sync_training_config_inputs(cfg):
        try:
            _spashiny_ctx.ui.update_numeric("max_epoch", value=cfg["max_epoch"])
            _spashiny_ctx.ui.update_numeric("n_per_batch", value=cfg["n_per_batch"])
            _spashiny_ctx.ui.update_select("mode", selected=cfg["mode"])
            _spashiny_ctx.ui.update_numeric("lr", value=cfg["lr"])
            _spashiny_ctx.ui.update_numeric("kl_weight", value=cfg["kl_weight"])
            _spashiny_ctx.ui.update_numeric(
                "reconstruction_st_weight", value=cfg["reconstruction_st_weight"]
            )
            _spashiny_ctx.ui.update_numeric(
                "reconstruction_sm_weight", value=cfg["reconstruction_sm_weight"]
            )
            _spashiny_ctx.ui.update_numeric("n_epochs_kl_warmup", value=cfg["n_epochs_kl_warmup"])
            _spashiny_ctx.ui.update_numeric("weight_decay", value=cfg["weight_decay"])
            _spashiny_ctx.ui.update_select("device", selected=cfg["device"])
        except Exception:
            pass

    _spashiny_ctx._sync_training_config_inputs = _sync_training_config_inputs

    def _get_uploaded_model_config_path():
        file_info = _spashiny_ctx.input.import_model_config_file()
        if not file_info:
            raise ValueError("please select a SpaShiny model config .json file")
        file_entry = file_info[0]
        file_name = str(file_entry.get("name", ""))
        data_path = file_entry.get("datapath")
        if not file_name.lower().endswith(".json") or not data_path:
            raise ValueError("please select a SpaShiny model config .json file")
        return _spashiny_ctx.Path(data_path)

    _spashiny_ctx._get_uploaded_model_config_path = _get_uploaded_model_config_path

    def _read_uploaded_model_config_payload():
        config_path = _spashiny_ctx._get_uploaded_model_config_path()
        try:
            raw_text = config_path.read_text(encoding="utf-8")
            return _spashiny_ctx.json.loads(raw_text)
        except UnicodeDecodeError as exc:
            raise ValueError("file must be UTF-8 JSON") from exc
        except _spashiny_ctx.json.JSONDecodeError as exc:
            raise ValueError("file is not valid JSON") from exc

    _spashiny_ctx._read_uploaded_model_config_payload = _read_uploaded_model_config_payload

    def _validate_model_reuse_config_payload(payload):
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON must be an object")
        if payload.get("schema") != _spashiny_ctx.MODEL_REUSE_CONFIG_SCHEMA:
            raise ValueError("unsupported SpaShiny model config schema")
        if payload.get("version") != _spashiny_ctx.MODEL_REUSE_CONFIG_VERSION:
            raise ValueError("unsupported SpaShiny model config version")
        model_cfg = _spashiny_ctx._select_known_config_values(
            payload.get("model_config"), _spashiny_ctx.MODEL_CONFIG_KEYS, "model_config"
        )
        train_cfg = _spashiny_ctx._select_known_config_values(
            payload.get("training_config"), _spashiny_ctx.TRAINING_CONFIG_KEYS, "training_config"
        )
        training_meta = payload.get("training")
        if not isinstance(training_meta, dict):
            raise ValueError("training metadata must be a JSON object")
        result_path = _spashiny_ctx._resolve_imported_result_path(training_meta.get("result_h5ad"))
        if not result_path:
            raise ValueError("trained result path is missing")
        if not _spashiny_globals.os.path.exists(result_path):
            raise ValueError("trained result file was not found")
        loss_path = _spashiny_ctx._resolve_imported_result_path(training_meta.get("loss_json"))
        if loss_path and (not _spashiny_globals.os.path.exists(loss_path)):
            loss_path = None
        imported_loss_history = payload.get("loss_history")
        if imported_loss_history is not None and (not isinstance(imported_loss_history, dict)):
            raise ValueError("loss_history must be a JSON object")
        return {
            "model_config": model_cfg,
            "training_config": train_cfg,
            "training": training_meta,
            "result_h5ad": result_path,
            "loss_json": loss_path,
            "loss_history": imported_loss_history,
        }

    _spashiny_ctx._validate_model_reuse_config_payload = _validate_model_reuse_config_payload

    def _build_model_reuse_config_payload():
        try:
            current_resource_mode = "tutorial"
        except Exception:
            current_resource_mode = "tutorial"
        result_path = _spashiny_ctx.training_result_path.get()
        loss_path = _spashiny_ctx.training_loss_path.get()
        summary = _spashiny_ctx.training_summary.get() or {}
        model_state_path = summary.get("model_state_dict") if isinstance(summary, dict) else None
        result_exists = bool(result_path and _spashiny_globals.os.path.exists(result_path))
        payload = {
            "schema": _spashiny_ctx.MODEL_REUSE_CONFIG_SCHEMA,
            "version": _spashiny_ctx.MODEL_REUSE_CONFIG_VERSION,
            "exported_at": _spashiny_ctx.time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "model_config": dict(_spashiny_ctx.model_config.get()),
            "training_config": dict(_spashiny_ctx.training_config.get()),
            "training": {
                "ready_to_skip_training": result_exists,
                "status": _spashiny_ctx.training_status_reactive.get(),
                "resource_mode": current_resource_mode,
                "job_dir": _spashiny_ctx.training_job_dir.get(),
                "result_h5ad": result_path,
                "loss_json": loss_path,
                "model_state_dict": model_state_path,
                "model_state_available": bool(
                    model_state_path and _spashiny_globals.os.path.exists(model_state_path)
                ),
                "summary": summary,
            },
            "loss_history": _spashiny_ctx.loss_history.get() or {},
            "note": "Import this file in SpaShiny to reuse the trained result and skip model training.",
        }
        return payload

    _spashiny_ctx._build_model_reuse_config_payload = _build_model_reuse_config_payload

    @_spashiny_ctx.render.download(
        filename=lambda: f"spashiny_model_config_{_spashiny_ctx.time.strftime('%Y%m%d_%H%M%S')}.json"
    )
    def download_model_config():
        payload = _spashiny_ctx._build_model_reuse_config_payload()
        rendered = _spashiny_ctx.json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        yield rendered.encode("utf-8")

    _spashiny_ctx.download_model_config = download_model_config

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.import_model_config)
    def import_model_config():
        try:
            payload = _spashiny_ctx._read_uploaded_model_config_payload()
            imported = _spashiny_ctx._validate_model_reuse_config_payload(payload)
            _spashiny_ctx.model_config.set(imported["model_config"])
            _spashiny_ctx.training_config.set(imported["training_config"])
            _spashiny_ctx._sync_model_config_inputs(imported["model_config"])
            _spashiny_ctx._sync_training_config_inputs(imported["training_config"])
            _spashiny_ctx.training_summary.set(
                imported["training"].get("summary") or imported["training"]
            )
            _spashiny_ctx.training_result_path.set(imported["result_h5ad"])
            _spashiny_ctx.training_loss_path.set(imported["loss_json"])
            _spashiny_ctx.training_job_dir.set(imported["training"].get("job_dir"))
            imported_loss_history = imported["loss_history"]
            if imported_loss_history is not None:
                _spashiny_ctx.loss_history.set(_spashiny_ctx.clean_loss_dict(imported_loss_history))
            elif imported["loss_json"]:
                _spashiny_ctx.loss_history.set(
                    _spashiny_ctx.clean_loss_dict(
                        _spashiny_ctx.json.loads(
                            _spashiny_ctx.Path(imported["loss_json"]).read_text(encoding="utf-8")
                        )
                    )
                )
            else:
                _spashiny_ctx.loss_history.set(None)
            _spashiny_ctx.trained_model.set(
                {
                    "source": "imported_model_config",
                    "result_h5ad": imported["result_h5ad"],
                    "skip_training": True,
                }
            )
            _spashiny_ctx.training_in_progress.set(False)
            try:
                _spashiny_ctx.vae_analysis_result_adata.set(None)
            except Exception:
                pass
            success_msg = "Model config imported. Model training has been skipped and the trained result is ready to use."
            _spashiny_ctx.training_status_reactive.set(success_msg)
            _spashiny_ctx.log(
                "[Training] Imported model config and reused trained result; training step skipped."
            )
            _spashiny_ctx.ui.notification_show(success_msg, type="message", duration=8)
        except Exception as exc:
            error_msg = f"Imported file content or format is invalid: {exc}"
            _spashiny_ctx.training_status_reactive.set(error_msg)
            _spashiny_ctx.log(f"[Training] Model config import failed: {exc}")
            _spashiny_ctx.ui.notification_show(error_msg, type="error", duration=10)

    _spashiny_ctx.import_model_config = import_model_config

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.train_model)
    def train_conditional_vae():
        try:
            if _spashiny_ctx.training_in_progress.get():
                _spashiny_ctx.log("A training job is already running.")
                return
            joint_data = _spashiny_ctx.joint_adata_processed.get()
            knn_parent_job_id = str(_spashiny_ctx.knn_upload_chain_job_id.get() or "").strip()
            joint_example_action_id = (
                _spashiny_ctx._latest_example_action_for("y7-joint-vit-example")
                if _spashiny_globals.SPASHINY_LAB_PROFILE
                and _spashiny_ctx.joint_input_source.get() == "EXAMPLE"
                else ""
            )
            if (
                not joint_example_action_id
                and joint_data is not None
                and _spashiny_globals.SPASHINY_LAB_PROFILE
            ):
                joint_example_action_id = _spashiny_ctx._bind_builtin_joint_example_for_worker(
                    selected_path=_spashiny_ctx.joint_h5ad_path.get()
                )
            if joint_data is None and (not joint_example_action_id) and (not knn_parent_job_id):
                _spashiny_ctx.training_status_reactive.set(
                    "Error: Please complete data preprocessing first."
                )
                _spashiny_ctx.log("[Training] No processed joint data found.")
                return
            _spashiny_ctx.ui.modal_show(
                _spashiny_ctx.ui.modal(
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.h4(
                            "Conditional VAE Training Running...", style="margin-bottom: 12px;"
                        ),
                        _spashiny_ctx.ui.p(
                            "SpatialMETA training is running in a separate backend Python process."
                        ),
                        _spashiny_ctx.ui.p(
                            "The Shiny process will only keep output file paths and small loss summaries.",
                            style="color: #6e6e73;",
                        ),
                    ),
                    title="Training in Progress",
                    easy_close=False,
                    footer=None,
                )
            )
            _spashiny_ctx.training_in_progress.set(True)
            _spashiny_ctx.training_status_reactive.set("Preparing backend job...")
            _spashiny_ctx.trained_model.set(None)
            _spashiny_ctx.loss_history.set(None)
            _spashiny_ctx.training_job_dir.set(None)
            _spashiny_ctx.training_result_path.set(None)
            _spashiny_ctx.training_summary.set(None)
            _spashiny_ctx.training_loss_path.set(None)
            cloud_parameters = _spashiny_globals.tutorial_job_parameters("stsm", "single")
            requested_resource = _spashiny_globals.SINGLE_SAMPLE_COMPUTE_RESOURCE
            if knn_parent_job_id:
                try:
                    from cloud.job_submission import JobSubmissionService
                    from cloud.workflow_registry import VIT_SINGLE_SAMPLE_INTEGRATION

                    session_record = _spashiny_ctx._cloud_session_record()
                    analysis_session_id = str(
                        _spashiny_ctx._cloud_analysis_session_id() or ""
                    ).strip()
                    if session_record is None or not analysis_session_id:
                        raise RuntimeError("The current tab analysis session is not ready.")
                    cloud_job = JobSubmissionService().submit(
                        session=session_record,
                        workflow_name=VIT_SINGLE_SAMPLE_INTEGRATION,
                        input_upload_ids=[],
                        workflow_artifacts=[
                            {
                                "parent_type": "job",
                                "parent_job_id": knn_parent_job_id,
                                "role": "knn_joint_h5ad",
                            }
                        ],
                        parameters={
                            **cloud_parameters,
                            "source_mode": "USER_UPLOAD_ALIGNMENT_KNN",
                            "parent_knn_job_id": knn_parent_job_id,
                        },
                        requested_resource=requested_resource,
                        analysis_session_id=analysis_session_id,
                    )
                    _spashiny_ctx.training_job_dir.set(cloud_job.local_workspace)
                    _spashiny_ctx.training_summary.set(
                        {
                            "cloud_job_id": cloud_job.job_id,
                            "status": "QUEUED",
                            "input_source": "workflow_artifact",
                            "parent_knn_job_id": knn_parent_job_id,
                        }
                    )
                    _spashiny_ctx.training_status_reactive.set(
                        f"Cloud integration job submitted from KNN artifact: {cloud_job.job_id}"
                    )
                    _spashiny_ctx.log(
                        f"[Training] User-upload Alignment → KNN → ConditionalVAE job submitted: {cloud_job.job_id}"
                    )
                    _spashiny_ctx.ui.notification_show(
                        f"Cloud integration job created: {cloud_job.job_id}",
                        type="message",
                        duration=8,
                    )
                    return
                except Exception as cloud_exc:
                    raise RuntimeError(
                        f"KNN artifact integration job submission failed: {cloud_exc}"
                    ) from cloud_exc
            if joint_example_action_id:
                try:
                    from cloud.workflow_registry import VIT_SINGLE_SAMPLE_INTEGRATION

                    cloud_job = _spashiny_ctx._submit_cloud_example_action_job(
                        workflow_name=VIT_SINGLE_SAMPLE_INTEGRATION,
                        example_action_ids=("y7-joint-vit-example",),
                        parameters=cloud_parameters,
                        requested_resource=requested_resource,
                    )
                    _spashiny_ctx.training_job_dir.set(cloud_job.local_workspace)
                    _spashiny_ctx.training_summary.set(
                        {
                            "cloud_job_id": cloud_job.job_id,
                            "status": "QUEUED",
                            "input_source": "example_action",
                        }
                    )
                    _spashiny_ctx.training_status_reactive.set(
                        f"Cloud job submitted: {cloud_job.job_id}"
                    )
                    _spashiny_ctx.log(
                        f"[Training] Lab example GPU job submitted: {cloud_job.job_id}"
                    )
                    _spashiny_ctx.log(
                        f"[Training] Requested compute resource: {requested_resource}"
                    )
                    _spashiny_ctx.log("[Training] Open Job Center to monitor progress.")
                    _spashiny_ctx.ui.notification_show(
                        f"Cloud job created: {cloud_job.job_id}", type="message", duration=8
                    )
                    return
                except Exception as cloud_exc:
                    raise RuntimeError(
                        f"Lab example job submission failed: {cloud_exc}"
                    ) from cloud_exc
            raise RuntimeError(
                "No worker-managed input is bound to this page. Load the supported example or complete the Lab upload flow before training."
            )
        except Exception as e:
            error_msg = _spashiny_globals.user_facing_error("Training failed", e)
            _spashiny_ctx.training_status_reactive.set(error_msg)
            _spashiny_ctx.log(error_msg)
            _spashiny_globals.notify_memory_warning(
                error_msg, duration=14 if _spashiny_globals.is_memory_related_exception(e) else 8
            )
            __import__("traceback").print_exc()
        finally:
            _spashiny_ctx.training_in_progress.set(False)
            _spashiny_globals.release_unused_memory()
            _spashiny_ctx.ui.modal_remove()
        return

    _spashiny_ctx.train_conditional_vae = train_conditional_vae

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.stop_training)
    def stop_training():
        _spashiny_ctx.training_in_progress.set(False)
        _spashiny_ctx.training_status_reactive.set("Training stopped.")
        _spashiny_ctx.log(" [Training] Stop button clicked.")

    _spashiny_ctx.stop_training = stop_training

    @_spashiny_ctx.output
    @_spashiny_ctx.render.text
    def training_status():
        return _spashiny_ctx.training_status_reactive.get()

    _spashiny_ctx.training_status = training_status

    @_spashiny_ctx.render.ui
    def vit_cloud_training_progress():
        return (
            _spashiny_ctx._cloud_training_progress_card(
                _spashiny_ctx.training_summary.get(), title="Single-sample ConditionalVAE"
            )
            or _spashiny_ctx.ui.div()
        )

    _spashiny_ctx.vit_cloud_training_progress = vit_cloud_training_progress

    @_spashiny_ctx.reactive.Effect
    def _restore_vit_cloud_result():
        summary = _spashiny_ctx.training_summary.get() or {}
        result_path, status, _job = _spashiny_ctx._cloud_integration_result_state(
            summary, workflow_name="vit_single_sample_integration"
        )
        if _spashiny_ctx._cloud_result_still_active(status):
            _spashiny_ctx.reactive.invalidate_later(2)
        if result_path and _spashiny_ctx.training_result_path.get() != result_path:
            _spashiny_ctx.training_result_path.set(result_path)
            _spashiny_ctx.training_status_reactive.set(
                "Worker result restored from persistent storage."
            )
        _spashiny_ctx._sync_cloud_postprocess_modal(
            summary,
            title="Single-sample ConditionalVAE post-processing",
            workflow_name="vit_single_sample_integration",
        )

    _spashiny_ctx._restore_vit_cloud_result = _restore_vit_cloud_result

    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("loss_plot")
    def loss_plot():
        import matplotlib.pyplot as plt

        loss_dict_data = _spashiny_ctx.loss_history.get()
        if not loss_dict_data:
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.text(
                0.5,
                0.5,
                "Loss curves will be displayed after training is completed.",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=14,
            )
            ax.set_title("Training Loss Curves")
            ax.axis("off")
            plt.tight_layout()
            return fig
        fig, axes = plt.subplots(3, 3, figsize=(20, 10))
        axes = axes.flatten()
        for i, (key, values) in enumerate(loss_dict_data.items()):
            if i < len(axes):
                ax = axes[i]
                ax.plot(values)
                ax.set_title(str(key))
                ax.set_xlabel("Epoch")
                ax.set_ylabel("Loss")
                ax.grid(True, alpha=0.3)
        for i in range(len(loss_dict_data), len(axes)):
            axes[i].set_visible(False)
        plt.tight_layout()
        return fig

    _spashiny_ctx.loss_plot = loss_plot

    def make_loss_plot_figure():
        import matplotlib.pyplot as plt

        loss_dict_data = _spashiny_ctx.loss_history.get()
        if not loss_dict_data:
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.text(
                0.5,
                0.5,
                "Loss curves will be displayed after training is completed.",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=14,
            )
            ax.set_title("Training Loss Curves")
            ax.axis("off")
            plt.tight_layout()
            return fig
        fig, axes = plt.subplots(3, 3, figsize=(20, 10))
        axes = axes.flatten()
        for i, (key, values) in enumerate(loss_dict_data.items()):
            if i < len(axes):
                ax = axes[i]
                ax.plot(values)
                ax.set_title(str(key))
                ax.set_xlabel("Epoch")
                ax.set_ylabel("Loss")
                ax.grid(True, alpha=0.3)
        for i in range(len(loss_dict_data), len(axes)):
            axes[i].set_visible(False)
        plt.tight_layout()
        return fig

    _spashiny_ctx.make_loss_plot_figure = make_loss_plot_figure

    @_spashiny_ctx.render.download(filename="training_loss_plot.pdf")
    def download_loss_plot_pdf():
        import io
        import matplotlib.pyplot as plt

        fig = _spashiny_ctx.make_loss_plot_figure()
        buf = io.BytesIO()
        _spashiny_globals.save_native_figure(fig, buf, format="pdf", bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        yield buf.read()

    _spashiny_ctx.download_loss_plot_pdf = download_loss_plot_pdf
    _spashiny_ctx.vae_analysis_result_adata = _spashiny_ctx.reactive.Value(None)

    def get_joint_vae_result_for_display(adata_obj=None):
        if adata_obj is not None:
            return (adata_obj, False)
        try:
            cached = _spashiny_ctx.vae_analysis_result_adata.get()
            if cached is not None:
                return (cached, False)
        except Exception:
            pass
        try:
            result_path = _spashiny_ctx.training_result_path.get()
        except Exception:
            result_path = None
        if not result_path:
            result_path, _status, _job = _spashiny_ctx._cloud_integration_result_state(
                _spashiny_ctx.training_summary.get() or {},
                workflow_name="vit_single_sample_integration",
            )
        return _spashiny_globals.read_h5ad_for_display(result_path)

    _spashiny_ctx.get_joint_vae_result_for_display = get_joint_vae_result_for_display
    import numpy as np

    _spashiny_globals.np = np
    import random

    _spashiny_ctx.random = random

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.analyze_results)
    async def analyze_training_results():
        import asyncio
        import traceback
        import numpy as np
        import random

        cloud_job_id = str(
            (_spashiny_ctx.training_summary.get() or {}).get("cloud_job_id") or ""
        ).strip()
        if _spashiny_globals.SPASHINY_LAB_PROFILE and cloud_job_id:
            try:
                from cloud.job_manager import JobManager

                job = JobManager().get_job_for_session(
                    _spashiny_ctx._cloud_session_id(),
                    cloud_job_id,
                    analysis_session_id=_spashiny_ctx._cloud_analysis_session_id(),
                )
                status = str(job.status or "QUEUED").upper()
                progress = max(0.0, min(100.0, float(job.progress or 0.0)))
                step = str(job.current_step or "Waiting for the GPU worker")
                if _spashiny_ctx._cloud_result_still_active(status):
                    message = f"GPU worker post-processing is in progress: {progress:.1f}% | {step}"
                    _spashiny_ctx.training_status_reactive.set(message)
                    _spashiny_ctx.log(f"[Analysis] {message}")
                    _spashiny_ctx.notify(
                        "Post-processing runs in the background GPU worker. Follow the training progress card.",
                        type_="message",
                    )
                    return
                if status in {"COMPLETED", "SUCCEEDED"}:
                    message = "GPU worker post-processing is complete. Result artifacts are available from My Results."
                    _spashiny_ctx.training_status_reactive.set(message)
                    _spashiny_ctx.log(f"[Analysis] {message}")
                    _spashiny_ctx.notify(message, type_="message")
                    return
                message = f"GPU worker post-processing cannot continue because the training job is {status}."
                _spashiny_ctx.training_status_reactive.set(message)
                _spashiny_ctx.log(f"[Analysis] {message}")
                _spashiny_ctx.notify(message, type_="warning")
                return
            except Exception as exc:
                message = f"Training job status is temporarily unavailable: {exc}"
                _spashiny_ctx.training_status_reactive.set(message)
                _spashiny_ctx.log(f"[Analysis] {message}")
                _spashiny_ctx.notify(message, type_="warning")
                return
        try:
            _spashiny_ctx.ui.modal_show(
                _spashiny_ctx.ui.modal(
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.h4(
                            "Analyzing VAE Results...", style="margin-bottom: 12px;"
                        ),
                        _spashiny_ctx.ui.p(
                            "Please wait while the trained VAE model outputs are being post-processed."
                        ),
                        _spashiny_ctx.ui.p(
                            "This includes latent embedding extraction, reconstruction, UMAP, and clustering.",
                            style="color: #6e6e73;",
                        ),
                    ),
                    title="Running",
                    easy_close=False,
                    footer=None,
                )
            )
            with _spashiny_ctx.ui.Progress(min=1, max=8) as p:
                p.set(message="Initializing...", detail="Preparing post-processing workflow")
                SEED = 42
                np.random.seed(SEED)
                random.seed(SEED)
                try:
                    import torch

                    torch.manual_seed(SEED)
                    if torch.cuda.is_available():
                        torch.cuda.manual_seed(SEED)
                        torch.cuda.manual_seed_all(SEED)
                except Exception:
                    pass
                p.set(1, message="Checking trained model...", detail="Validating VAE model")
                await asyncio.sleep(0.05)
                model = _spashiny_ctx.trained_model.get()
                if isinstance(model, dict) and model.get("skip_training"):
                    result_path = (
                        model.get("result_h5ad") or _spashiny_ctx.training_result_path.get()
                    )
                    if result_path and _spashiny_globals.os.path.exists(result_path):
                        _spashiny_ctx.training_result_path.set(result_path)
                        p.set(
                            8,
                            message="Using imported trained result...",
                            detail="Training and model-object extraction skipped",
                        )
                        status_msg = "Model config imported. Model training has been skipped and the trained result is ready to use."
                        _spashiny_ctx.training_status_reactive.set(status_msg)
                        _spashiny_ctx.log(
                            "[Analysis] Reusing imported/backend trained result; live model extraction skipped."
                        )
                        _spashiny_ctx.ui.modal_remove()
                        _spashiny_ctx.ui.modal_show(
                            _spashiny_ctx.ui.modal(
                                _spashiny_ctx.ui.div(
                                    _spashiny_ctx.ui.h4(
                                        "Trained Result Ready", style="margin-bottom: 12px;"
                                    ),
                                    _spashiny_ctx.ui.p(
                                        "SpaShiny is using an imported trained model config and existing trained result."
                                    ),
                                    _spashiny_ctx.ui.p(
                                        "The model training step has been skipped. You can view or export the downstream results directly.",
                                        style="color: #6e6e73;",
                                    ),
                                ),
                                title="Training Skipped",
                                easy_close=True,
                                footer=_spashiny_ctx.ui.div(
                                    _spashiny_ctx.ui.input_action_button(
                                        "close_modal_analysis_imported_result",
                                        "Close",
                                        class_="btn btn-success",
                                    )
                                ),
                            )
                        )
                        return
                    missing_msg = "Imported trained result file is missing. Please import a valid SpaShiny model config again."
                    _spashiny_ctx.training_status_reactive.set(missing_msg)
                    _spashiny_ctx.log(f"[Analysis] {missing_msg}")
                    _spashiny_ctx.ui.modal_remove()
                    _spashiny_ctx.ui.modal_show(
                        _spashiny_ctx.ui.modal(
                            missing_msg,
                            title="Analysis Error",
                            easy_close=True,
                            footer=_spashiny_ctx.ui.div(
                                _spashiny_ctx.ui.input_action_button(
                                    "close_modal_analysis_missing_imported_result",
                                    "Close",
                                    class_="btn btn-secondary",
                                )
                            ),
                        )
                    )
                    return
                if model is None:
                    _spashiny_ctx.training_status_reactive.set(
                        "Error: Please complete model training first."
                    )
                    _spashiny_ctx.log("[Analysis] No trained model found.")
                    _spashiny_ctx.ui.modal_remove()
                    _spashiny_ctx.ui.modal_show(
                        _spashiny_ctx.ui.modal(
                            "No trained model was found. Please complete model training before running post-processing.",
                            title="Analysis Error",
                            easy_close=True,
                            footer=_spashiny_ctx.ui.div(
                                _spashiny_ctx.ui.input_action_button(
                                    "close_modal_analysis_no_model",
                                    "Close",
                                    class_="btn btn-secondary",
                                )
                            ),
                        )
                    )
                    return
                p.set(
                    2,
                    message="Checking processed data...",
                    detail="Loading processed joint AnnData",
                )
                await asyncio.sleep(0.05)
                joint_data = _spashiny_ctx.joint_adata_processed.get()
                if joint_data is None:
                    _spashiny_ctx.training_status_reactive.set(
                        "Error: Processed joint data unavailable."
                    )
                    _spashiny_ctx.log("[Analysis] Processed joint data not found.")
                    _spashiny_ctx.ui.modal_remove()
                    _spashiny_ctx.ui.modal_show(
                        _spashiny_ctx.ui.modal(
                            "Processed joint data was not found. Please run joint data preprocessing first.",
                            title="Analysis Error",
                            easy_close=True,
                            footer=_spashiny_ctx.ui.div(
                                _spashiny_ctx.ui.input_action_button(
                                    "close_modal_analysis_no_data",
                                    "Close",
                                    class_="btn btn-secondary",
                                )
                            ),
                        )
                    )
                    return
                _spashiny_globals.preflight_memory(
                    "VAE post-processing",
                    adata=joint_data["adata"],
                    multiplier=2.0,
                    min_available_gb=1.8,
                    log_func=_spashiny_ctx.log,
                )
                joint_adata = _spashiny_globals.compact_adata_X(joint_data["adata"])
                _spashiny_ctx.log(f"[Analysis] Loaded processed AnnData: {joint_adata.shape}")
                p.set(
                    3,
                    message="Extracting model outputs...",
                    detail="Latent embedding / reconstruction / contribution",
                )
                _spashiny_ctx.training_status_reactive.set("Extracting model outputs...")
                _spashiny_ctx.log("Step 3: Extracting latent embedding and reconstruction...")
                await asyncio.sleep(0.05)
                Z = model.get_latent_embedding()
                X = model.get_normalized_expression()
                C = model.get_modality_contribution()
                _spashiny_ctx.log(
                    f"Latent embedding shape: {(Z.shape if hasattr(Z, 'shape') else 'unknown')}"
                )
                _spashiny_ctx.log(
                    f"Reconstruction shape: {(X.shape if hasattr(X, 'shape') else 'unknown')}"
                )
                p.set(
                    4, message="Saving outputs...", detail="Writing reconstruction and embeddings"
                )
                _spashiny_ctx.training_status_reactive.set("Saving model outputs...")
                _spashiny_ctx.log("Step 4: Saving outputs to AnnData...")
                await asyncio.sleep(0.05)
                Z = Z.detach().cpu().numpy() if torch.is_tensor(Z) else np.asarray(Z)
                X = X.detach().cpu().numpy() if torch.is_tensor(X) else np.asarray(X)
                C = C.detach().cpu().numpy() if torch.is_tensor(C) else np.asarray(C)
                joint_adata.layers["reconstruction"] = _spashiny_globals.compact_matrix_copy(X)
                joint_adata.obsm["X_emb"] = np.asarray(Z, dtype=np.float32)
                joint_adata.obs["contribution_st"] = np.asarray(C, dtype=np.float32)
                joint_adata.obs["contribution_sm"] = np.asarray(1 - C, dtype=np.float32)
                del X, Z, C
                _spashiny_globals.release_unused_memory()
                _spashiny_ctx.log("Model outputs saved into AnnData")
                p.set(
                    5, message="Computing neighbors...", detail="Building graph from latent space"
                )
                _spashiny_ctx.training_status_reactive.set("Computing neighbor graph...")
                _spashiny_ctx.log("Step 5: Computing neighbors...")
                await asyncio.sleep(0.05)
                _spashiny_globals.preflight_memory(
                    "VAE neighbor graph and UMAP",
                    adata=joint_adata,
                    multiplier=1.3,
                    min_available_gb=1.2,
                    log_func=_spashiny_ctx.log,
                )
                _spashiny_globals.sc.pp.neighbors(
                    joint_adata, use_rep="X_emb", n_neighbors=15, random_state=SEED
                )
                _spashiny_ctx.log("Neighbor graph computed")
                p.set(6, message="Computing UMAP...", detail="Generating low-dimensional embedding")
                _spashiny_ctx.training_status_reactive.set("Computing UMAP...")
                _spashiny_ctx.log("Step 6: Computing UMAP...")
                await asyncio.sleep(0.05)
                _spashiny_globals.sc.tl.umap(joint_adata, min_dist=1, spread=1, random_state=SEED)
                _spashiny_ctx.log("UMAP embedding computed")
                p.set(
                    7, message="Running clustering...", detail="Leiden clustering in latent space"
                )
                _spashiny_ctx.training_status_reactive.set("Running Leiden clustering...")
                _spashiny_ctx.log("Step 7: Running Leiden clustering...")
                await asyncio.sleep(0.05)
                _spashiny_globals.sc.tl.leiden(
                    joint_adata, key_added="VAE_clusters_latent10", random_state=SEED
                )
                _spashiny_ctx.log("Leiden clustering complete")
                p.set(8, message="Saving results...", detail="Writing final processed AnnData")
                _spashiny_ctx.training_status_reactive.set("Saving analysis results...")
                _spashiny_ctx.log("Step 8: Saving final processed object...")
                await asyncio.sleep(0.05)
                _spashiny_ctx.vae_analysis_result_adata.set(joint_adata)
                _spashiny_ctx.vae_processed_adata.set(joint_adata)
                _spashiny_ctx.log(" [Analysis] Post-processing finished successfully.")
                _spashiny_ctx.log(f" Final obs columns: {list(joint_adata.obs.columns)}")
                _spashiny_ctx.log(f" Final layers: {list(joint_adata.layers.keys())}")
                _spashiny_ctx.log(f" Final obsm keys: {list(joint_adata.obsm.keys())}")
                _spashiny_ctx.training_status_reactive.set(
                    "Post-processing completed successfully."
                )
            _spashiny_ctx.ui.modal_remove()
            _spashiny_ctx.ui.modal_show(
                _spashiny_ctx.ui.modal(
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.h4("Analysis Complete", style="margin-bottom: 12px;"),
                        _spashiny_ctx.ui.p("VAE post-processing finished successfully."),
                        _spashiny_ctx.ui.p(
                            f"Final shape: {joint_adata.shape}", style="color: #6e6e73;"
                        ),
                        _spashiny_ctx.ui.p(
                            "UMAP, latent embedding, reconstruction, and clustering were saved.",
                            style="color: #6e6e73;",
                        ),
                    ),
                    title="Success",
                    easy_close=True,
                    footer=_spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.input_action_button(
                            "close_modal_analysis_success", "Close", class_="btn btn-success"
                        )
                    ),
                )
            )
        except Exception as e:
            error_msg = _spashiny_globals.user_facing_error("Post-processing failed", e)
            _spashiny_ctx.training_status_reactive.set(error_msg)
            _spashiny_ctx.log(error_msg)
            _spashiny_globals.notify_memory_warning(
                error_msg, duration=14 if _spashiny_globals.is_memory_related_exception(e) else 8
            )
            print(error_msg)
            traceback.print_exc()
            _spashiny_ctx.ui.modal_remove()
            _spashiny_ctx.ui.modal_show(
                _spashiny_ctx.ui.modal(
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.h4(
                            "VAE Post-processing Failed",
                            style="margin-bottom: 12px; color: #ff3b30;",
                        ),
                        _spashiny_ctx.ui.p(
                            "An error occurred during VAE post-processing. Please check the logs for details and try again.",
                            style="color: #6e6e73;",
                        ),
                        _spashiny_ctx.ui.pre(
                            error_msg,
                            style="white-space: pre-wrap; font-size: 0.92rem; color: #6e6e73;",
                        ),
                    ),
                    title="Analysis Error",
                    easy_close=True,
                    footer=_spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.input_action_button(
                            "close_modal_analysis_error", "Close", class_="btn btn-danger"
                        )
                    ),
                )
            )

    _spashiny_ctx.analyze_training_results = analyze_training_results

    def _cluster_categories_and_palette(adata, cluster_key):
        """Give UMAP and spatial plots one stable cluster-ID/color contract."""
        import matplotlib.pyplot as plt
        from matplotlib.colors import to_hex

        labels = [str(value) for value in adata.obs[cluster_key].astype(str)]

        def _natural_key(value):
            return (0, int(value)) if value.isdigit() else (1, value)

        categories = sorted(set(labels), key=_natural_key)
        adata.obs[cluster_key] = _spashiny_ctx.pd.Categorical(
            labels, categories=categories, ordered=True
        )
        cmap = plt.get_cmap("tab20")
        palette = [to_hex(cmap(index % cmap.N)) for index in range(len(categories))]
        adata.uns[f"{cluster_key}_colors"] = palette
        return (categories, palette)

    _spashiny_ctx._cluster_categories_and_palette = _cluster_categories_and_palette

    def _square_cluster_figure():
        fig, ax = _spashiny_globals.plt.subplots(figsize=(8, 8))
        fig.subplots_adjust(left=0.09, right=0.69, bottom=0.09, top=0.93)
        return (fig, ax)

    _spashiny_ctx._square_cluster_figure = _square_cluster_figure

    def _wide_umap_cluster_figure():
        fig, ax = _spashiny_globals.plt.subplots(figsize=(800 / 100, 560 / 100))
        fig.subplots_adjust(left=0.07, right=0.78, bottom=0.1, top=0.93)
        return (fig, ax)

    _spashiny_ctx._wide_umap_cluster_figure = _wide_umap_cluster_figure

    def _finalize_cluster_legend(ax, categories):
        legend = ax.get_legend()
        if legend is not None:
            legend.set_title(f"Cluster ({len(categories)})")
            legend.get_title().set_fontsize(10)

    _spashiny_ctx._finalize_cluster_legend = _finalize_cluster_legend

    def make_umap_figure(adata):
        import matplotlib.pyplot as plt
        import scanpy as sc

        fig, ax = _spashiny_ctx._wide_umap_cluster_figure()
        if adata is None:
            ax.text(
                0.5,
                0.5,
                "Please run post-processing analysis first.",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=14,
            )
            ax.set_title("UMAP Visualization")
            ax.axis("off")
            return fig
        cluster_key = _spashiny_globals.find_vae_cluster_key(adata)
        if cluster_key is None:
            ax.text(
                0.5,
                0.5,
                "Missing VAE clustering result.",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=14,
            )
            ax.set_title("UMAP Visualization")
            ax.axis("off")
            return fig
        try:
            categories, palette = _spashiny_ctx._cluster_categories_and_palette(adata, cluster_key)
            sc.pl.umap(
                adata,
                color=cluster_key,
                palette=palette,
                legend_loc="right margin",
                frameon=True,
                ax=ax,
                show=False,
            )
            ax.set_title("VAE Latent Space UMAP Clustering")
            _spashiny_ctx._finalize_cluster_legend(ax, categories)
            return fig
        except Exception as exc:
            ax.clear()
            ax.text(
                0.5,
                0.5,
                f"UMAP plot failed:\n{exc}",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=12,
            )
            ax.set_title("UMAP Visualization")
            ax.axis("off")
            return fig

    _spashiny_ctx.make_umap_figure = make_umap_figure

    def make_spatial_cluster_figure(adata):
        import matplotlib.pyplot as plt
        import scanpy as sc

        fig, ax = _spashiny_ctx._square_cluster_figure()
        if adata is None:
            ax.text(
                0.5,
                0.5,
                "Please run post-processing analysis first.",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=14,
            )
            ax.set_title("Spatial Cluster Plot")
            ax.axis("off")
            return fig
        cluster_key = _spashiny_globals.find_vae_cluster_key(adata)
        if cluster_key is None:
            ax.text(
                0.5,
                0.5,
                "Missing VAE clustering result.",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=14,
            )
            ax.set_title("Spatial Cluster Plot")
            ax.axis("off")
            return fig
        try:
            categories, palette = _spashiny_ctx._cluster_categories_and_palette(adata, cluster_key)
            sc.pl.spatial(
                adata,
                img_key="hires",
                color=cluster_key,
                palette=palette,
                legend_loc="right margin",
                ax=ax,
                show=False,
            )
            ax.set_title("Spatial Cluster Distribution")
            _spashiny_ctx._finalize_cluster_legend(ax, categories)
            return fig
        except Exception as exc:
            ax.clear()
            ax.text(
                0.5,
                0.5,
                f"Spatial cluster plot failed:\n{exc}",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=12,
            )
            ax.set_title("Spatial Cluster Plot")
            ax.axis("off")
            return fig

    _spashiny_ctx.make_spatial_cluster_figure = make_spatial_cluster_figure

    def make_modality_contribution_figure(adata):
        import matplotlib.pyplot as plt
        import scanpy as sc
        import spatialmeta.pl as smt_pl

        if adata is None:
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.text(
                0.5,
                0.5,
                "No final VAE analysis result found.",
                ha="center",
                va="center",
                fontsize=14,
                transform=ax.transAxes,
            )
            ax.axis("off")
            return fig
        required_cols = ["contribution_st", "contribution_sm"]
        missing_cols = [col for col in required_cols if col not in adata.obs.columns]
        if len(missing_cols) > 0:
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.text(
                0.5,
                0.5,
                f"Missing columns: {', '.join(missing_cols)}",
                ha="center",
                va="center",
                fontsize=14,
                transform=ax.transAxes,
            )
            ax.axis("off")
            return fig
        try:
            sc.pl.spatial(
                adata,
                img_key="hires",
                color_map=smt_pl.make_colormap(["#2ec4b6", "#ffffff", "#ff9f1c"]),
                color=["contribution_st", "contribution_sm"],
                layer="normalized",
                show=False,
                alpha_img=0.1,
                size=1.5,
            )
            fig = plt.gcf()
            plt.tight_layout()
            return fig
        except Exception as e:
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.text(
                0.5,
                0.5,
                f"Failed to generate plot.\nError: {str(e)}",
                ha="center",
                va="center",
                fontsize=12,
                transform=ax.transAxes,
            )
            ax.axis("off")
            return fig

    _spashiny_ctx.make_modality_contribution_figure = make_modality_contribution_figure

    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("umap_plot")
    def umap_plot():
        adata, should_close = _spashiny_ctx.get_joint_vae_result_for_display()
        try:
            return _spashiny_ctx.make_umap_figure(adata)
        finally:
            _spashiny_globals.close_display_h5ad(adata, should_close)

    _spashiny_ctx.umap_plot = umap_plot

    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("spatial_cluster_plot")
    def spatial_cluster_plot():
        adata, should_close = _spashiny_ctx.get_joint_vae_result_for_display()
        try:
            return _spashiny_ctx.make_spatial_cluster_figure(adata)
        finally:
            _spashiny_globals.close_display_h5ad(adata, should_close)

    _spashiny_ctx.spatial_cluster_plot = spatial_cluster_plot

    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("modality_contribution_spatial_plot")
    def modality_contribution_spatial_plot():
        adata, should_close = _spashiny_ctx.get_joint_vae_result_for_display()
        try:
            return _spashiny_ctx.make_modality_contribution_figure(adata)
        finally:
            _spashiny_globals.close_display_h5ad(adata, should_close)

    _spashiny_ctx.modality_contribution_spatial_plot = modality_contribution_spatial_plot

    @_spashiny_ctx.render.download(filename="vae_umap_plot.pdf")
    def download_umap_pdf():
        import io
        import matplotlib.pyplot as plt

        adata, should_close = _spashiny_ctx.get_joint_vae_result_for_display()
        fig = _spashiny_ctx.make_umap_figure(adata)
        _spashiny_globals.close_display_h5ad(adata, should_close)
        buf = io.BytesIO()
        _spashiny_globals.save_native_figure(fig, buf, format="pdf", bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        yield buf.read()

    _spashiny_ctx.download_umap_pdf = download_umap_pdf

    @_spashiny_ctx.render.download(filename="vae_modality_contribution_plot.pdf")
    def download_modality_pdf():
        import io
        import matplotlib.pyplot as plt

        adata, should_close = _spashiny_ctx.get_joint_vae_result_for_display()
        fig = _spashiny_ctx.make_modality_contribution_figure(adata)
        _spashiny_globals.close_display_h5ad(adata, should_close)
        buf = io.BytesIO()
        _spashiny_globals.save_native_figure(fig, buf, format="pdf", bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        yield buf.read()

    _spashiny_ctx.download_modality_pdf = download_modality_pdf

    @_spashiny_ctx.render.download(filename="vae_spatial_cluster_plot.pdf")
    def download_spatial_cluster_pdf():
        import io
        import matplotlib.pyplot as plt

        adata, should_close = _spashiny_ctx.get_joint_vae_result_for_display()
        fig = _spashiny_ctx.make_spatial_cluster_figure(adata)
        _spashiny_globals.close_display_h5ad(adata, should_close)
        buf = io.BytesIO()
        _spashiny_globals.save_native_figure(fig, buf, format="pdf", bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        yield buf.read()

    _spashiny_ctx.download_spatial_cluster_pdf = download_spatial_cluster_pdf

    @_spashiny_ctx.render.download(filename="vae_full_analysis_report.pdf")
    def download_full_analysis_pdf():
        import io
        import matplotlib.pyplot as plt
        from cloud.figure_export import EditablePdfPages as PdfPages

        adata, should_close = _spashiny_ctx.get_joint_vae_result_for_display()
        buf = io.BytesIO()
        try:
            with PdfPages(buf) as pdf:
                fig1 = _spashiny_ctx.make_umap_figure(adata)
                pdf.savefig(fig1, bbox_inches="tight")
                plt.close(fig1)
                fig2 = _spashiny_ctx.make_spatial_cluster_figure(adata)
                pdf.savefig(fig2, bbox_inches="tight")
                plt.close(fig2)
                fig3 = _spashiny_ctx.make_modality_contribution_figure(adata)
                pdf.savefig(fig3, bbox_inches="tight")
                plt.close(fig3)
        finally:
            _spashiny_globals.close_display_h5ad(adata, should_close)
        buf.seek(0)
        yield buf.read()

    _spashiny_ctx.download_full_analysis_pdf = download_full_analysis_pdf


_STEPS = (_install_0,)


def server(_spashiny_ctx, step=0):
    return _STEPS[step](_spashiny_ctx)
