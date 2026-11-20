# Extracted from /app/app/ST-SM.py. Feature: integration_multi_st_sm; ordered phases preserve original initialization.
from spashiny._shared import runtime_globals as _spashiny_globals


def _install_0(_spashiny_ctx):
    _spashiny_ctx.sample_names_reactive = _spashiny_ctx.reactive.Value([])
    _spashiny_ctx.uploaded_files_info = _spashiny_ctx.reactive.Value({})
    _spashiny_ctx.processed_files_reactive = _spashiny_ctx.reactive.Value({})
    _spashiny_ctx.sample_data_dict = _spashiny_ctx.reactive.Value({})
    _spashiny_ctx.merged_adata_reactive = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.processing_log_reactive = _spashiny_ctx.reactive.Value([])
    _spashiny_ctx.temp_directory = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.processed_data = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.normalization_log = _spashiny_ctx.reactive.Value([])
    _spashiny_ctx.vhit_cvae_model = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.vhit_cvae_result = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.vhit_cvae_job_dir = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.vhit_cvae_result_path = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.vhit_cvae_summary = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.vhit_cvae_loss_path = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.vhit_cvae_model_state_path = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.vhit_loss_dict = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.vhit_training_log = _spashiny_ctx.reactive.Value([])
    _spashiny_ctx.vhit_training_state = _spashiny_ctx.reactive.Value("Waiting")
    _spashiny_ctx.vhit_is_training = _spashiny_ctx.reactive.Value(False)
    _spashiny_ctx.vhit_example_merge_requested = _spashiny_ctx.reactive.Value(False)
    _spashiny_ctx.vhit_merge_summary = _spashiny_ctx.reactive.Value({})
    _spashiny_ctx.vhit_merge_metadata = _spashiny_ctx.reactive.Value({})
    _spashiny_ctx.vhit_merge_result_path = _spashiny_ctx.reactive.Value("")
    _spashiny_ctx.vhit_qc_summary = _spashiny_ctx.reactive.Value({})
    _spashiny_ctx.vhit_qc_metadata = _spashiny_ctx.reactive.Value({})
    _spashiny_ctx.vhit_qc_result_path = _spashiny_ctx.reactive.Value("")
    _spashiny_ctx.vhit_input_source_mode = _spashiny_ctx.reactive.Value("")

    def notify(message, type_="message", duration=4):
        """Shiny notification helper: English only, no icons."""
        try:
            _spashiny_ctx.ui.notification_show(message, type=type_, duration=duration)
        except Exception:
            pass

    _spashiny_ctx.notify = notify

    def show_busy_modal(title="Processing", message="Please wait..."):
        _spashiny_ctx.ui.modal_show(
            _spashiny_ctx.ui.modal(
                _spashiny_ctx.ui.p(message), title=title, easy_close=False, footer=None
            )
        )

    _spashiny_ctx.show_busy_modal = show_busy_modal

    def close_busy_modal():
        try:
            _spashiny_ctx.ui.modal_remove()
        except Exception:
            pass
        _spashiny_globals.release_unused_memory()

    _spashiny_ctx.close_busy_modal = close_busy_modal

    def add_log(message):
        current_log = _spashiny_ctx.processing_log_reactive.get()
        timestamp = _spashiny_ctx.pd.Timestamp.now().strftime("%H:%M:%S")
        current_log.append(f"{timestamp} - {message}")
        _spashiny_ctx.processing_log_reactive.set(current_log)
        print(message, flush=True)

    _spashiny_ctx.add_log = add_log

    def add_normalization_log(message):
        current_log = _spashiny_ctx.normalization_log.get()
        timestamp = _spashiny_ctx.pd.Timestamp.now().strftime("%H:%M:%S")
        current_log.append(f"{timestamp} - {message}")
        _spashiny_ctx.normalization_log.set(current_log)
        print(message, flush=True)

    _spashiny_ctx.add_normalization_log = add_normalization_log

    def add_vhit_training_log(message):
        current_log = list(_spashiny_ctx.vhit_training_log.get())
        timestamp = _spashiny_ctx.pd.Timestamp.now().strftime("%H:%M:%S")
        current_log.append(f"{timestamp} - {message}")
        _spashiny_ctx.vhit_training_log.set(current_log)
        print(f"[VHIT-CVAE] {message}", flush=True)

    _spashiny_ctx.add_vhit_training_log = add_vhit_training_log

    def safe_target_sum(value):
        if value is None:
            return None
        if isinstance(value, str) and value.strip() == "":
            return None
        try:
            if _spashiny_ctx.pd.isna(value):
                return None
        except Exception:
            pass
        return float(value)

    _spashiny_ctx.safe_target_sum = safe_target_sum

    def make_empty_plot(message, title="Waiting"):
        fig, ax = _spashiny_globals.plt.subplots(figsize=(8, 6))
        ax.text(0.5, 0.5, message, ha="center", va="center", transform=ax.transAxes, fontsize=13)
        ax.set_title(title)
        ax.axis("off")
        return fig

    _spashiny_ctx.make_empty_plot = make_empty_plot

    def clean_loss_dict(loss_dict):
        if loss_dict is None:
            return {}
        clean = {}
        for key, values in loss_dict.items():
            try:
                if _spashiny_globals.torch.is_tensor(values):
                    clean[key] = [float(x) for x in values.detach().cpu().numpy().reshape(-1)]
                elif isinstance(values, _spashiny_globals.np.ndarray):
                    clean[key] = [float(x) for x in values.reshape(-1)]
                elif isinstance(values, (list, tuple)):
                    clean[key] = [float(x) for x in values]
                else:
                    clean[key] = [float(values)]
            except Exception:
                clean[key] = values
        return clean

    _spashiny_ctx.clean_loss_dict = clean_loss_dict

    def get_vhit_result_for_display(adata_obj=None):
        if adata_obj is not None:
            return (adata_obj, False)
        try:
            cached = _spashiny_ctx.vhit_cvae_result.get()
            if cached is not None:
                return (cached, False)
        except Exception:
            pass
        try:
            result_path = _spashiny_ctx.vhit_cvae_result_path.get()
        except Exception:
            result_path = None
        if not result_path:
            result_path, _status, _job = _spashiny_ctx._cloud_integration_result_state(
                _spashiny_ctx.vhit_cvae_summary.get() or {},
                workflow_name="vhit_multi_sample_integration",
            )
        return _spashiny_globals.read_h5ad_for_display(result_path)

    _spashiny_ctx.get_vhit_result_for_display = get_vhit_result_for_display

    def get_vhit_reconstruction_diagnostics():
        try:
            summary = _spashiny_ctx.vhit_cvae_summary.get()
        except Exception:
            summary = None
        diag = (
            dict(summary.get("reconstruction_diagnostics") or {})
            if isinstance(summary, dict)
            else {}
        )
        result_path = _spashiny_ctx.vhit_cvae_result_path.get()
        if not result_path:
            result_path, _status, _job = _spashiny_ctx._cloud_integration_result_state(
                summary or {}, workflow_name="vhit_multi_sample_integration"
            )
        if not result_path:
            return diag
        if not diag:
            metadata, _losses = _spashiny_globals.read_worker_training_metadata(result_path)
            diag = dict(metadata.get("reconstruction_diagnostics") or {})
        try:
            result_root = _spashiny_ctx.Path(str(result_path)).resolve().parent
            for key, relative in {
                "scatter_csv": "output/reconstruction_scatter_sample.csv",
                "mse_csv": "output/reconstruction_mse_by_obs.csv",
            }.items():
                candidate = (result_root / relative).resolve()
                if candidate.is_file() and result_root in candidate.parents:
                    diag[key] = str(candidate)
        except Exception:
            pass
        return diag

    _spashiny_ctx.get_vhit_reconstruction_diagnostics = get_vhit_reconstruction_diagnostics

    def matrix_density_and_mean(X):
        try:
            if hasattr(X, "nnz"):
                total = X.shape[0] * X.shape[1]
                density = X.nnz / total * 100 if total else 0.0
                mean_expr = X.mean()
                if hasattr(mean_expr, "A1"):
                    mean_expr = float(mean_expr.A1[0])
                else:
                    mean_expr = float(mean_expr)
                return (density, mean_expr)
            else:
                arr = _spashiny_globals.np.asarray(X)
                density = (
                    _spashiny_globals.np.count_nonzero(arr) / arr.size * 100 if arr.size else 0.0
                )
                mean_expr = float(_spashiny_globals.np.mean(arr)) if arr.size else 0.0
                return (density, mean_expr)
        except Exception:
            return (None, None)

    _spashiny_ctx.matrix_density_and_mean = matrix_density_and_mean

    def write_figs_to_pdf(figures, pdf_path):
        with _spashiny_ctx.PdfPages(pdf_path) as pdf:
            for fig in figures:
                if fig is not None:
                    pdf.savefig(fig, bbox_inches="tight")
                    _spashiny_globals.plt.close(fig)

    _spashiny_ctx.write_figs_to_pdf = write_figs_to_pdf

    def intelligent_sample_matcher(filename, sample_list):
        """Flexible sample name matching."""
        filename_lower = filename.lower()
        for sample in sample_list:
            sample_lower = sample.lower()
            patterns = [
                sample_lower,
                sample_lower.replace("_", "[-_]"),
                sample_lower.replace("_", ""),
                f"sample[-_]{sample_lower}",
                f"{sample_lower}[-_]sample",
                f"data[-_]{sample_lower}",
                f"{sample_lower}[-_]data",
            ]
            for pattern in patterns:
                if _spashiny_ctx.re.search(pattern, filename_lower):
                    return sample
        return None

    _spashiny_ctx.intelligent_sample_matcher = intelligent_sample_matcher

    def infer_joint_example_sample_name(path):
        base_name = _spashiny_ctx.Path(path).stem
        patterns = [
            "^adata_joint_(.*?)_raw$",
            "^adata_joint_(.*?)$",
            "^(.*?)_adata_joint_raw$",
            "^(.*?)_joint_raw$",
            "^(.*?)_raw$",
        ]
        for pattern in patterns:
            match = _spashiny_ctx.re.match(pattern, base_name, flags=_spashiny_ctx.re.IGNORECASE)
            if match and match.group(1):
                return match.group(1)
        return base_name

    _spashiny_ctx.infer_joint_example_sample_name = infer_joint_example_sample_name

    def _unique_sample_ids(names):
        """Keep UI labels intact while rejecting ambiguous job sample IDs."""
        seen = set()
        result = []
        for value in names:
            sample_id = str(value or "").strip()
            if not sample_id or sample_id in seen:
                return None
            seen.add(sample_id)
            result.append(sample_id)
        return result

    _spashiny_ctx._unique_sample_ids = _unique_sample_ids

    def _reset_vhit_active_results():
        _spashiny_ctx.sample_data_dict.set({})
        _spashiny_ctx.merged_adata_reactive.set(None)
        _spashiny_ctx.processed_data.set(None)
        _spashiny_ctx.vhit_cvae_model.set(None)
        _spashiny_ctx.vhit_cvae_result.set(None)
        _spashiny_ctx.vhit_cvae_job_dir.set(None)
        _spashiny_ctx.vhit_cvae_result_path.set(None)
        _spashiny_ctx.vhit_cvae_summary.set(None)
        _spashiny_ctx.vhit_cvae_loss_path.set(None)
        _spashiny_ctx.vhit_cvae_model_state_path.set(None)
        _spashiny_ctx.vhit_loss_dict.set(None)
        _spashiny_ctx.vhit_training_state.set("Waiting")
        _spashiny_ctx.vhit_example_merge_requested.set(False)
        _spashiny_ctx.vhit_merge_summary.set({})
        _spashiny_ctx.vhit_merge_metadata.set({})
        _spashiny_ctx.vhit_merge_result_path.set("")
        _spashiny_ctx.vhit_qc_summary.set({})
        _spashiny_ctx.vhit_qc_metadata.set({})
        _spashiny_ctx.vhit_qc_result_path.set("")

    _spashiny_ctx._reset_vhit_active_results = _reset_vhit_active_results

    def align_var_metadata_to_merged(merged_adata, reference_adata, reference_name):
        ref_var = reference_adata.var.copy()
        if ref_var.index.has_duplicates:
            ref_var = ref_var[~ref_var.index.duplicated(keep="first")]
        aligned_var = ref_var.reindex(merged_adata.var_names)
        merged_adata.var = aligned_var.copy()
        missing_count = int(aligned_var.isna().all(axis=1).sum()) if aligned_var.shape[1] else 0
        if missing_count:
            _spashiny_ctx.add_log(
                f"Variable metadata copied from '{reference_name}' with {missing_count} feature(s) missing metadata."
            )
        else:
            _spashiny_ctx.add_log(
                f"Variable metadata was copied from reference sample '{reference_name}'."
            )

    _spashiny_ctx.align_var_metadata_to_merged = align_var_metadata_to_merged

    @_spashiny_ctx.reactive.Effect
    def init_temp_dir():
        if _spashiny_ctx.temp_directory.get() is None:
            td = _spashiny_ctx.tempfile.mkdtemp(prefix="spatial_merge_")
            _spashiny_ctx.temp_directory.set(td)
            _spashiny_ctx.add_log(f"Temporary directory created: {td}")

    _spashiny_ctx.init_temp_dir = init_temp_dir

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.confirm_samples_btn)
    def confirm_sample_names():
        names_input = _spashiny_ctx.input.sample_names_input()
        if not names_input or not names_input.strip():
            _spashiny_ctx.add_log("Sample name list is empty.")
            _spashiny_ctx.notify("Please enter at least one sample name.", type_="warning")
            return
        samples = _spashiny_ctx._unique_sample_ids(
            (name.strip() for name in names_input.split(","))
        )
        if samples is None:
            _spashiny_ctx.add_log("Sample names must be non-empty and unique within one analysis.")
            _spashiny_ctx.notify(
                "Sample names must be unique. Rename duplicate samples before processing.",
                type_="warning",
            )
            return
        _spashiny_ctx.sample_names_reactive.set(samples)
        sample_choices = {sample: sample for sample in samples}
        _spashiny_ctx.ui.update_select(
            "var_reference_sample", choices=sample_choices, selected=samples[0] if samples else None
        )
        _spashiny_ctx.add_log(f"Sample names confirmed: {', '.join(samples)}")
        _spashiny_ctx.notify(f"Sample names confirmed: {len(samples)} sample(s).", type_="message")

    _spashiny_ctx.confirm_sample_names = confirm_sample_names

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.load_vhit_joint_example)
    def load_vhit_joint_example():
        example_dir = _spashiny_globals.EXAMPLE_JOINT_BATCH_DIR
        if not example_dir.exists():
            _spashiny_ctx.add_log(f"Example joint directory was not found: {example_dir}")
            _spashiny_ctx.notify(
                "Example joint directory was not found.", type_="error", duration=8
            )
            return
        try:
            example_files = _spashiny_globals.get_allowlisted_example_files(
                example_dir, _spashiny_globals.EXAMPLE_JOINT_BATCH_RAW_FILES
            )
        except FileNotFoundError as exc:
            _spashiny_ctx.add_log(str(exc))
            _spashiny_ctx.notify(
                "One or more bundled raw joint examples are missing.", type_="warning"
            )
            return
        _spashiny_ctx.vhit_input_source_mode.set("EXAMPLE")
        processed_files = {}
        samples = []
        for path in example_files:
            sample_name = _spashiny_ctx.infer_joint_example_sample_name(path)
            unique_sample = sample_name
            counter = 2
            while unique_sample in processed_files:
                unique_sample = f"{sample_name}_{counter}"
                counter += 1
            processed_files[unique_sample] = {
                "original_name": path.name,
                "standardized_name": f"adata_joint_{unique_sample}_raw.h5ad",
                "file_path": str(path),
                "status": "success",
                "sample_id": unique_sample,
                "display_name": unique_sample,
                "source_type": "EXAMPLE",
            }
            samples.append(unique_sample)
        _spashiny_ctx.sample_names_reactive.set(samples)
        _spashiny_ctx.processed_files_reactive.set(processed_files)
        _spashiny_ctx._reset_vhit_active_results()
        sample_choices = {sample: sample for sample in samples}
        _spashiny_ctx.ui.update_text("sample_names_input", value=", ".join(samples))
        _spashiny_ctx.ui.update_select(
            "var_reference_sample", choices=sample_choices, selected=samples[0] if samples else None
        )
        _spashiny_ctx.add_log(f"Prepared example joint data from: {example_dir}")
        _spashiny_ctx.add_log(f"Example joint samples: {', '.join(samples)}")
        _spashiny_ctx.notify(
            f"Prepared {len(samples)} example joint sample(s). Click Merge Data to load and merge them.",
            type_="message",
            duration=6,
        )

    _spashiny_ctx.load_vhit_joint_example = load_vhit_joint_example

    def _hydrate_vhit_worker_managed_example(
        payload=None, *, force=False, reset_active_results=True
    ):
        """Reflect a session-bound example in UI state without loading H5AD in Web."""
        if not _spashiny_globals.SPASHINY_LAB_PROFILE:
            return False
        if not force and _spashiny_ctx.vhit_input_source_mode.get() not in {"", "EXAMPLE"}:
            return False
        payload = payload if isinstance(payload, dict) else {}
        action_id = str(payload.get("action_id") or "").strip()
        if action_id != "joint-five-sample-vhit-example":
            action_id = _spashiny_ctx._latest_example_action_for("joint-five-sample-vhit-example")
        if action_id != "joint-five-sample-vhit-example":
            return False
        samples = [str(x).strip() for x in payload.get("sample_ids") or [] if str(x).strip()]
        if not samples:
            samples = list(_spashiny_ctx.sample_names_reactive.get() or [])
        if not samples:
            samples = ["R114_T", "S15_T", "X49_T", "Y27_T", "Y7_T"]
        records = {
            sample: {
                "original_name": f"bound example: {sample}",
                "standardized_name": f"adata_joint_{sample}_raw.h5ad",
                "file_path": None,
                "status": "worker_bound",
                "input_source": "example_action",
                "sample_id": sample,
                "display_name": sample,
                "source_type": "EXAMPLE",
            }
            for sample in samples
        }
        _spashiny_ctx.sample_names_reactive.set(samples)
        _spashiny_ctx.processed_files_reactive.set(records)
        _spashiny_ctx.vhit_input_source_mode.set("EXAMPLE")
        if reset_active_results:
            _spashiny_ctx._reset_vhit_active_results()
        _spashiny_ctx.ui.update_text("sample_names_input", value=", ".join(samples))
        _spashiny_ctx.ui.update_select(
            "var_reference_sample",
            choices={sample: sample for sample in samples},
            selected=samples[0],
        )
        _spashiny_ctx.add_log(
            f"Bound {len(samples)} read-only joint example inputs to the GPU worker. No H5AD is loaded in the Shiny process."
        )
        return True

    _spashiny_ctx._hydrate_vhit_worker_managed_example = _hydrate_vhit_worker_managed_example

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(
        _spashiny_ctx.input.cloud_example_action_activated, ignore_none=True
    )
    def hydrate_vhit_worker_managed_example():
        try:
            payload = _spashiny_ctx.input.cloud_example_action_activated() or {}
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            return
        if str(payload.get("action_id") or "") != "joint-five-sample-vhit-example" or not bool(
            payload.get("ready")
        ):
            return
        if str(payload.get("analysis_session_id") or "") != str(
            _spashiny_ctx._cloud_analysis_session_id() or ""
        ):
            return
        if _spashiny_ctx._hydrate_vhit_worker_managed_example(payload, force=True):
            _spashiny_ctx._show_multisample_feedback_modal(
                "Example Inputs Ready",
                "Five read-only joint H5AD inputs are bound to this session.",
                detail="No large H5AD file is loaded in the Web process. Continue with Process Uploaded Files.",
            )
            _spashiny_ctx.notify(
                "Five example inputs are ready for worker-managed processing. Click Process Uploaded Files, then Merge Data.",
                type_="message",
                duration=8,
            )

    _spashiny_ctx.hydrate_vhit_worker_managed_example = hydrate_vhit_worker_managed_example
    _spashiny_ctx.vhit_example_reload_hydrated_analysis = _spashiny_ctx.reactive.Value("")

    @_spashiny_ctx.reactive.Effect
    def restore_vhit_example_binding_after_analysis_restore():
        """Hydrate an existing READY VHiT binding after same-tab reload only."""
        if _spashiny_ctx.vhit_input_source_mode.get() not in {"", "EXAMPLE"}:
            return
        token = str(_spashiny_ctx._cloud_session_token() or "").strip()
        try:
            raw_analysis_session_id = str(
                _spashiny_ctx.input.spashiny_analysis_session_id() or ""
            ).strip()
        except Exception:
            raw_analysis_session_id = ""
        analysis_session_id = _spashiny_ctx._safe_job_token(raw_analysis_session_id, "")
        if not token or not analysis_session_id:
            return
        if (
            str(_spashiny_ctx.vhit_example_reload_hydrated_analysis.get() or "")
            == analysis_session_id
        ):
            return
        try:
            from cloud.database import CloudDatabase
            from cloud.session_manager import SessionManager

            db = CloudDatabase(read_only=True)
            session_id = str(
                SessionManager(database=db).authenticate(token).session_id or ""
            ).strip()
            if not session_id:
                return
            analysis = db.get_analysis_session(analysis_session_id, owner_session_id=session_id)
            if str(analysis.get("status") or "").upper() != "ACTIVE":
                return
            record = db.get_example_action_binding(
                session_id=session_id,
                analysis_session_id=analysis_session_id,
                action_id="joint-five-sample-vhit-example",
            )
            if not bool(record.get("ready")):
                return
            try:
                sample_ids = _spashiny_ctx.json.loads(str(record.get("sample_ids_json") or "[]"))
            except Exception:
                sample_ids = []
            payload = {
                "action_id": "joint-five-sample-vhit-example",
                "binding_id": record.get("binding_id"),
                "ready": True,
                "sample_ids": sample_ids if isinstance(sample_ids, list) else [],
            }
        except Exception:
            return
        bindings = dict(_spashiny_ctx.cloud_example_action_bindings.get() or {})
        bindings["joint-five-sample-vhit-example"] = payload
        _spashiny_ctx.cloud_example_action_bindings.set(bindings)
        if _spashiny_ctx._hydrate_vhit_worker_managed_example(
            payload, force=False, reset_active_results=False
        ):
            _spashiny_ctx.vhit_example_reload_hydrated_analysis.set(analysis_session_id)

    _spashiny_ctx.restore_vhit_example_binding_after_analysis_restore = (
        restore_vhit_example_binding_after_analysis_restore
    )

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.data_upload)
    def activate_vhit_uploaded_input():
        """A real upload replaces only the active example selection, never files on disk."""
        try:
            files = _spashiny_ctx.input.data_upload() or []
        except Exception:
            files = []
        if not files:
            return
        replacing_example = _spashiny_ctx.vhit_input_source_mode.get() == "EXAMPLE"
        _spashiny_ctx.vhit_input_source_mode.set("USER_UPLOAD")
        _spashiny_ctx.processed_files_reactive.set({})
        _spashiny_ctx._reset_vhit_active_results()
        if replacing_example:
            _spashiny_ctx.ui.update_text("sample_names_input", value="")
            _spashiny_ctx.sample_names_reactive.set([])
            _spashiny_ctx.ui.update_select("var_reference_sample", choices={})
            _spashiny_ctx.add_log(
                "User upload selected. The active example selection was cleared; confirm upload sample names before processing."
            )

    _spashiny_ctx.activate_vhit_uploaded_input = activate_vhit_uploaded_input

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.process_files_btn)
    def process_uploaded_files():
        files = _spashiny_ctx.input.data_upload()
        samples = _spashiny_ctx.sample_names_reactive.get()
        if (
            _spashiny_ctx.vhit_input_source_mode.get() == "EXAMPLE"
            and _spashiny_ctx._hydrate_vhit_worker_managed_example()
        ):
            _spashiny_ctx.add_log(
                "Worker-managed example input validation completed: 5/5 inputs are bound."
            )
            _spashiny_ctx._show_multisample_feedback_modal(
                "File Processing Complete",
                "Validated 5/5 worker-managed example inputs.",
                detail="The files remain read-only and are authorized only for this session.",
            )
            _spashiny_ctx.notify(
                "Example files are ready. Click Merge Data to stage the worker merge.",
                type_="message",
                duration=6,
            )
            return
        if not files:
            existing_files = _spashiny_ctx.processed_files_reactive.get()
            if existing_files:
                success_count = len(
                    [f for f in existing_files.values() if f["status"] == "success"]
                )
                _spashiny_ctx.add_log(
                    f"No browser-uploaded files selected; {success_count} prepared example file(s) are already available."
                )
                _spashiny_ctx.notify(
                    "Example files are already prepared. Click Merge Data to load and merge them.",
                    type_="message",
                    duration=6,
                )
                return
            _spashiny_ctx.add_log("No files were selected for upload.")
            _spashiny_ctx.notify("Please select one or more .h5ad files.", type_="warning")
            return
        if not samples:
            _spashiny_ctx.add_log("Sample names have not been configured.")
            _spashiny_ctx.notify("Please confirm sample names first.", type_="warning")
            return
        _spashiny_ctx.show_busy_modal(
            "Processing Uploads",
            "Matching files to sample names and preparing standardized copies...",
        )
        try:
            _spashiny_ctx.add_log("Started processing uploaded files.")
            processed_files = {}
            temp_dir = _spashiny_ctx.temp_directory.get()
            for file_info in files:
                original_name = file_info["name"]
                original_path = file_info["datapath"]
                matched_sample = _spashiny_ctx.intelligent_sample_matcher(original_name, samples)
                if matched_sample:
                    if matched_sample in processed_files:
                        raise ValueError(
                            f"Multiple uploaded files map to sample '{matched_sample}'; use distinct sample names."
                        )
                    standardized_name = f"adata_joint_{matched_sample}_raw.h5ad"
                    standardized_path = _spashiny_globals.os.path.join(temp_dir, standardized_name)
                    try:
                        _spashiny_ctx.shutil.copy2(original_path, standardized_path)
                        processed_files[matched_sample] = {
                            "original_name": original_name,
                            "standardized_name": standardized_name,
                            "file_path": standardized_path,
                            "status": "success",
                            "sample_id": matched_sample,
                            "display_name": matched_sample,
                            "source_type": "USER_UPLOAD",
                        }
                        _spashiny_ctx.add_log(
                            f"Matched '{original_name}' to sample '{matched_sample}'."
                        )
                    except Exception as e:
                        processed_files[matched_sample] = {
                            "original_name": original_name,
                            "standardized_name": standardized_name,
                            "file_path": None,
                            "status": f"error: {str(e)}",
                        }
                        _spashiny_ctx.add_log(f"Failed to process '{original_name}': {str(e)}")
                else:
                    _spashiny_ctx.add_log(f"No sample match found for '{original_name}'.")
            _spashiny_ctx.processed_files_reactive.set(processed_files)
            success_count = len([f for f in processed_files.values() if f["status"] == "success"])
            total_count = len(files)
            if success_count > 0:
                _spashiny_ctx.notify(
                    f"Uploaded files processed: {success_count}/{total_count} succeeded.",
                    type_="message",
                )
                _spashiny_ctx.add_log(
                    f"Upload processing finished: {success_count}/{total_count} succeeded."
                )
            else:
                _spashiny_ctx.notify(
                    "No uploaded file could be matched to a sample name.", type_="error"
                )
                _spashiny_ctx.add_log("Upload processing finished with no successful matches.")
        except Exception as e:
            _spashiny_ctx.add_log(f"Unexpected error while processing uploads: {str(e)}")
            _spashiny_ctx.notify(f"Upload processing failed: {str(e)}", type_="error", duration=8)
            _spashiny_ctx.traceback.print_exc()
        finally:
            _spashiny_ctx.close_busy_modal()

    _spashiny_ctx.process_uploaded_files = process_uploaded_files

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.merge_data_btn)
    def load_and_merge_data():
        if _spashiny_ctx.vhit_input_source_mode.get() == "EXAMPLE" and (
            _spashiny_ctx._latest_example_action_for("joint-five-sample-vhit-example")
            if _spashiny_globals.SPASHINY_LAB_PROFILE
            else ""
        ):
            _spashiny_ctx._hydrate_vhit_worker_managed_example()
            try:
                from cloud.workflow_registry import VHIT_MULTI_SAMPLE_INTEGRATION

                requested_resource = _spashiny_ctx.input.vhit_compute_resource() or "auto"
                job = _spashiny_ctx._submit_cloud_example_action_job(
                    workflow_name=VHIT_MULTI_SAMPLE_INTEGRATION,
                    example_action_ids=("joint-five-sample-vhit-example",),
                    parameters={"stage": "merge", "custom_params": {"run_spatial_variable": False}},
                    requested_resource=requested_resource,
                )
                _spashiny_ctx.vhit_example_merge_requested.set(True)
                _spashiny_ctx.vhit_merge_summary.set(
                    {"cloud_job_id": job.job_id, "status": "QUEUED", "stage": "merge"}
                )
                _spashiny_ctx.vhit_training_state.set(f"Merge job submitted: {job.job_id}")
                _spashiny_ctx.add_log(
                    f"Five-sample merge submitted to the independent GPU worker: {job.job_id}"
                )
                _spashiny_ctx._show_multisample_prepare_modal(
                    job_id=job.job_id, title="Merging multi-sample data"
                )
                _spashiny_ctx.notify(
                    "Merge job submitted. Monitor the persisted job progress below.",
                    type_="message",
                    duration=8,
                )
            except Exception as exc:
                _spashiny_ctx.add_log(f"Worker merge submission failed: {exc}")
                _spashiny_ctx.notify(
                    f"Could not submit the merge job: {exc}", type_="error", duration=8
                )
            return
        processed_files = _spashiny_ctx.processed_files_reactive.get()
        if not processed_files:
            _spashiny_ctx.add_log("No processed files are available for merging.")
            _spashiny_ctx.notify("Please process uploaded files first.", type_="warning")
            return
        success_files = {k: v for k, v in processed_files.items() if v["status"] == "success"}
        if not success_files:
            _spashiny_ctx.add_log("There are no successfully processed files to merge.")
            _spashiny_ctx.notify(
                "No successfully processed files are available for merging.", type_="warning"
            )
            return
        _spashiny_ctx.show_busy_modal(
            "Merging Data", "Loading sample files and merging them into one AnnData object..."
        )
        try:
            _spashiny_ctx.add_log("Started loading and merging data.")
            sample_data = {}
            for sample_name, file_info in success_files.items():
                try:
                    joint_adata = _spashiny_globals.compact_adata_X(
                        _spashiny_globals.sc.read_h5ad(file_info["file_path"])
                    )
                    sample_data[sample_name] = joint_adata
                    _spashiny_ctx.add_log(
                        f"Loaded sample '{sample_name}' with shape {joint_adata.shape}."
                    )
                except Exception as e:
                    _spashiny_ctx.add_log(f"Failed to load sample '{sample_name}': {str(e)}")
            if not sample_data:
                _spashiny_ctx.add_log("No sample data could be loaded.")
                _spashiny_ctx.notify("Failed to load all selected samples.", type_="error")
                return
            merge_dict = dict(sample_data)
            if not merge_dict:
                _spashiny_ctx.add_log("No AnnData object is available for concatenation.")
                _spashiny_ctx.notify(
                    "No valid AnnData object is available for merging.", type_="error"
                )
                return
            merge_adata = _spashiny_ctx.ad.concat(merge_dict, label="sample", join="inner")
            merge_adata.obs_names_make_unique()
            var_ref = _spashiny_ctx.input.var_reference_sample()
            if not var_ref:
                var_ref = list(sample_data.keys())[0]
            if var_ref in sample_data:
                _spashiny_ctx.align_var_metadata_to_merged(
                    merge_adata, sample_data[var_ref], var_ref
                )
            else:
                first_sample = list(sample_data.keys())[0]
                _spashiny_ctx.align_var_metadata_to_merged(
                    merge_adata, sample_data[first_sample], first_sample
                )
                _spashiny_ctx.add_log(
                    f"Reference sample not found. Variable metadata fallback: '{first_sample}'."
                )
            _spashiny_ctx.sample_data_dict.set(sample_data)
            _spashiny_ctx.merged_adata_reactive.set(merge_adata)
            sample_counts = merge_adata.obs["sample"].value_counts().to_dict()
            sample_dist_text = ", ".join([f"{k}({v})" for k, v in sample_counts.items()])
            _spashiny_ctx.add_log(f"Merged data shape: {merge_adata.shape}.")
            _spashiny_ctx.add_log(f"Sample distribution: {sample_dist_text}")
            _spashiny_ctx.notify(
                f"Data merged successfully: {merge_adata.n_obs} cells/spots, {merge_adata.n_vars} features.",
                type_="message",
            )
        except Exception as e:
            _spashiny_ctx.add_log(f"Data merge failed: {str(e)}")
            _spashiny_ctx.notify(f"Data merge failed: {str(e)}", type_="error", duration=8)
            _spashiny_ctx.traceback.print_exc()
        finally:
            _spashiny_ctx.close_busy_modal()

    _spashiny_ctx.load_and_merge_data = load_and_merge_data

    @_spashiny_ctx.render.ui
    def status_display():
        samples = _spashiny_ctx.sample_names_reactive.get()
        processed_files = _spashiny_ctx.processed_files_reactive.get()
        merged_data = _spashiny_ctx.merged_adata_reactive.get()
        merge_meta = _spashiny_ctx.vhit_merge_metadata.get() or {}
        merge_summary = _spashiny_ctx.vhit_merge_summary.get() or {}
        status_items = []
        if not samples:
            status_items.append(
                _spashiny_ctx.ui.div(
                    _spashiny_ctx.ui.h5("Sample Setup"),
                    _spashiny_ctx.ui.p("Waiting for sample names."),
                )
            )
        else:
            status_items.append(
                _spashiny_ctx.ui.div(
                    _spashiny_ctx.ui.h5("Sample Setup"),
                    _spashiny_ctx.ui.p(f"{len(samples)} sample(s) configured."),
                    _spashiny_ctx.ui.p(f"Samples: {', '.join(samples)}"),
                )
            )
        if not processed_files:
            status_items.append(
                _spashiny_ctx.ui.div(
                    _spashiny_ctx.ui.h5("File Processing"),
                    _spashiny_ctx.ui.p("Waiting for uploaded files."),
                )
            )
        else:
            success_count = len([f for f in processed_files.values() if f["status"] == "success"])
            worker_bound_count = len(
                [f for f in processed_files.values() if f["status"] == "worker_bound"]
            )
            if worker_bound_count:
                status_items.append(
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.h5("File Processing"),
                        _spashiny_ctx.ui.p(
                            f"{worker_bound_count}/{len(processed_files)} read-only example input(s) bound to the GPU worker."
                        ),
                    )
                )
            else:
                status_items.append(
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.h5("File Processing"),
                        _spashiny_ctx.ui.p(
                            f"{success_count}/{len(processed_files)} file(s) processed successfully."
                        ),
                    )
                )
        if merged_data is None and merge_meta:
            counts = merge_meta.get("sample_counts") or {}
            samples_text = (
                ", ".join((f"{name}({count})" for name, count in counts.items())) or "N/A"
            )
            status_items.append(
                _spashiny_ctx.ui.div(
                    _spashiny_ctx.ui.h5("Data Merge"),
                    _spashiny_ctx.ui.p(
                        f"Worker merge completed: {merge_meta.get('n_obs', 'N/A')} cells/spots, {merge_meta.get('n_vars', 'N/A')} features."
                    ),
                    _spashiny_ctx.ui.p(f"Included samples: {samples_text}"),
                )
            )
        elif merged_data is None:
            if _spashiny_ctx.vhit_input_source_mode.get() == "EXAMPLE" and (
                _spashiny_ctx._latest_example_action_for("joint-five-sample-vhit-example")
                if _spashiny_globals.SPASHINY_LAB_PROFILE
                else ""
            ):
                message = (
                    "Merge job is running in the GPU worker."
                    if merge_summary.get("cloud_job_id")
                    else "Click Merge Data to submit the worker-managed merge."
                )
                status_items.append(
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.h5("Data Merge"), _spashiny_ctx.ui.p(message)
                    )
                )
            else:
                status_items.append(
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.h5("Data Merge"), _spashiny_ctx.ui.p("Waiting for merge.")
                    )
                )
        else:
            sample_counts = merged_data.obs["sample"].value_counts()
            samples_text = ", ".join([f"{k}({v})" for k, v in sample_counts.items()])
            status_items.append(
                _spashiny_ctx.ui.div(
                    _spashiny_ctx.ui.h5("Data Merge"),
                    _spashiny_ctx.ui.p(f"Merged shape: {merged_data.shape}"),
                    _spashiny_ctx.ui.p(f"Included samples: {samples_text}"),
                )
            )
        return _spashiny_ctx.ui.div(*status_items)

    _spashiny_ctx.status_display = status_display

    @_spashiny_ctx.render.ui
    def file_processing_results():
        processed_files = _spashiny_ctx.processed_files_reactive.get()
        if not processed_files:
            return _spashiny_ctx.ui.p("No processed upload results yet.")
        success_files = {k: v for k, v in processed_files.items() if v["status"] == "success"}
        bound_files = {k: v for k, v in processed_files.items() if v["status"] == "worker_bound"}
        error_files = {
            k: v
            for k, v in processed_files.items()
            if v["status"] not in {"success", "worker_bound"}
        }
        result_ui = []
        if success_files:
            result_ui.append(_spashiny_ctx.ui.h4("Successfully Processed Files"))
            success_list = []
            for sample, info in success_files.items():
                success_list.append(
                    _spashiny_ctx.ui.tags.li(
                        f"{info['original_name']} -> {info['standardized_name']}"
                    )
                )
            result_ui.append(_spashiny_ctx.ui.tags.ul(*success_list))
        if bound_files:
            result_ui.append(_spashiny_ctx.ui.h4("Worker-Managed Example Inputs"))
            result_ui.append(
                _spashiny_ctx.ui.p(
                    "These immutable H5AD inputs are authorized for the current session and will be read only by the GPU worker."
                )
            )
            result_ui.append(
                _spashiny_ctx.ui.tags.ul(
                    *[
                        _spashiny_ctx.ui.tags.li(
                            f"{info['standardized_name']} -> session-bound example input"
                        )
                        for info in bound_files.values()
                    ]
                )
            )
        if error_files:
            result_ui.append(_spashiny_ctx.ui.h4("Files With Errors"))
            error_list = []
            for sample, info in error_files.items():
                error_list.append(
                    _spashiny_ctx.ui.tags.li(f"{info['original_name']}: {info['status']}")
                )
            result_ui.append(_spashiny_ctx.ui.tags.ul(*error_list))
        return _spashiny_ctx.ui.div(*result_ui)

    _spashiny_ctx.file_processing_results = file_processing_results

    @_spashiny_ctx.render.ui
    def merge_results():
        merged_data = _spashiny_ctx.merged_adata_reactive.get()
        merge_meta = _spashiny_ctx.vhit_merge_metadata.get() or {}
        if merged_data is None:
            if merge_meta:
                counts = merge_meta.get("sample_counts") or {}
                return _spashiny_ctx.ui.div(
                    _spashiny_ctx.ui.h4("Merge Summary"),
                    _spashiny_ctx.ui.layout_columns(
                        _spashiny_ctx.ui.value_box(
                            "Total Cells/Spots",
                            f"{int(merge_meta.get('n_obs', 0)):,}",
                            theme="success",
                        ),
                        _spashiny_ctx.ui.value_box(
                            "Total Features", f"{int(merge_meta.get('n_vars', 0)):,}", theme="info"
                        ),
                        _spashiny_ctx.ui.value_box("Samples", f"{len(counts):,}", theme="warning"),
                        col_widths=(4, 4, 4),
                    ),
                    _spashiny_ctx.ui.card(
                        _spashiny_ctx.ui.card_header("Sample Distribution Details"),
                        _spashiny_ctx.ui.output_table("sample_distribution_table"),
                    ),
                )
            if _spashiny_ctx.vhit_input_source_mode.get() == "EXAMPLE" and (
                _spashiny_ctx._latest_example_action_for("joint-five-sample-vhit-example")
                if _spashiny_globals.SPASHINY_LAB_PROFILE
                else ""
            ):
                return _spashiny_ctx.ui.p(
                    "The five read-only example inputs are waiting for a Merge Data worker job.",
                    class_="text-muted",
                )
            return _spashiny_ctx.ui.p("Waiting for merged data.")
        sample_counts = merged_data.obs["sample"].value_counts()
        return _spashiny_ctx.ui.div(
            _spashiny_ctx.ui.h4("Merge Summary"),
            _spashiny_ctx.ui.layout_columns(
                _spashiny_ctx.ui.value_box(
                    "Total Cells/Spots", f"{merged_data.n_obs:,}", theme="success"
                ),
                _spashiny_ctx.ui.value_box(
                    "Total Features", f"{merged_data.n_vars:,}", theme="info"
                ),
                _spashiny_ctx.ui.value_box("Samples", f"{len(sample_counts):,}", theme="warning"),
                col_widths=(4, 4, 4),
            ),
            _spashiny_ctx.ui.card(
                _spashiny_ctx.ui.card_header("Sample Distribution Details"),
                _spashiny_ctx.ui.output_table("sample_distribution_table"),
            ),
        )

    _spashiny_ctx.merge_results = merge_results

    def build_sample_distribution_figure(merged_data):
        if isinstance(merged_data, dict):
            sample_counts = _spashiny_ctx.pd.Series(merged_data, dtype="int64").sort_index()
        else:
            sample_counts = merged_data.obs["sample"].value_counts().sort_index()
        fig, ax = _spashiny_globals.plt.subplots(
            figsize=(11.5, max(4.2, 0.82 * len(sample_counts) + 1.6))
        )
        if sample_counts.empty:
            ax.text(
                0.5,
                0.5,
                "No sample labels are available.",
                ha="center",
                va="center",
                transform=ax.transAxes,
            )
            ax.set_axis_off()
            return fig
        colors = _spashiny_globals.plt.cm.tab10(
            _spashiny_globals.np.arange(len(sample_counts)) % 10
        )
        bars = ax.barh(
            sample_counts.index.astype(str),
            sample_counts.values,
            color=colors,
            edgecolor="white",
            linewidth=0.8,
        )
        ax.invert_yaxis()
        ax.set_xlabel("Cells / spots")
        ax.set_ylabel("Sample")
        ax.grid(axis="x", alpha=0.25)
        ax.set_axisbelow(True)
        max_count = max(int(sample_counts.max()), 1)
        ax.set_xlim(0, max_count * 1.16)
        for bar, count in zip(bars, sample_counts.values):
            ax.text(
                float(count) + max_count * 0.012,
                bar.get_y() + bar.get_height() / 2,
                f"{int(count):,}",
                va="center",
                fontsize=10,
            )
        fig.tight_layout()
        return fig

    _spashiny_ctx.build_sample_distribution_figure = build_sample_distribution_figure

    @_spashiny_ctx.render.table
    def sample_distribution_table():
        merged_data = _spashiny_ctx.merged_adata_reactive.get()
        merge_meta = _spashiny_ctx.vhit_merge_metadata.get() or {}
        if merged_data is None and (not merge_meta):
            return None
        sample_counts = (
            _spashiny_ctx.pd.Series(merge_meta.get("sample_counts") or {}, dtype="int64")
            if merged_data is None
            else merged_data.obs["sample"].value_counts()
        )
        total_cells = (
            int(merge_meta.get("n_obs", sample_counts.sum()))
            if merged_data is None
            else merged_data.n_obs
        )
        distribution_data = []
        for sample, count in sample_counts.items():
            distribution_data.append(
                {
                    "Sample": sample,
                    "Cells/Spots": int(count),
                    "Percent": f"{count / total_cells * 100:.1f}%",
                }
            )
        return _spashiny_ctx.pd.DataFrame(distribution_data)

    _spashiny_ctx.sample_distribution_table = sample_distribution_table

    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("sample_distribution_plot")
    def sample_distribution_plot():
        merged_data = _spashiny_ctx.merged_adata_reactive.get()
        merge_meta = _spashiny_ctx.vhit_merge_metadata.get() or {}
        if merged_data is None and merge_meta.get("sample_counts"):
            return _spashiny_ctx.build_sample_distribution_figure(merge_meta["sample_counts"])
        if merged_data is None:
            fig, ax = _spashiny_globals.plt.subplots(figsize=(8, 6))
            ax.text(
                0.5,
                0.5,
                "Please merge data first.",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=14,
            )
            ax.set_title("Sample Distribution")
            return fig
        return _spashiny_ctx.build_sample_distribution_figure(merged_data)

    _spashiny_ctx.sample_distribution_plot = sample_distribution_plot

    @_spashiny_ctx.render.ui
    def sample_distribution_display():
        return _spashiny_ctx._cloud_worker_plot_ui(
            _spashiny_ctx.vhit_merge_summary.get(),
            workflow_name="vhit_multi_sample_integration",
            stage="merge",
            rel_path="figures/sample_distribution.png",
            fallback_output="sample_distribution_plot",
            alt="Sample distribution",
        )

    _spashiny_ctx.sample_distribution_display = sample_distribution_display

    @_spashiny_ctx.render.table
    def data_overview_table():
        merged_data = _spashiny_ctx.merged_adata_reactive.get()
        sample_data = _spashiny_ctx.sample_data_dict.get()
        worker_rows = _spashiny_ctx._cloud_worker_table(
            _spashiny_ctx.vhit_merge_summary.get(),
            workflow_name="vhit_multi_sample_integration",
            stage="merge",
            rel_path="tables/data_overview.json",
        )
        if merged_data is None and worker_rows:
            return _spashiny_ctx.pd.DataFrame(worker_rows)
        merge_meta = _spashiny_ctx.vhit_merge_metadata.get() or {}
        if merged_data is None and merge_meta:
            counts = merge_meta.get("sample_counts") or {}
            features = int(merge_meta.get("n_vars", 0))
            rows = [
                {
                    "Sample": name,
                    "Type": "Worker merged input",
                    "Cells/Spots": int(count),
                    "Features": features,
                    "Density": "Stored in worker result",
                    "Mean Expression": "Stored in worker result",
                }
                for name, count in counts.items()
            ]
            rows.append(
                {
                    "Sample": "Merged Data",
                    "Type": "Merged",
                    "Cells/Spots": int(merge_meta.get("n_obs", 0)),
                    "Features": features,
                    "Density": "Stored in worker result",
                    "Mean Expression": "Stored in worker result",
                }
            )
            return _spashiny_ctx.pd.DataFrame(rows)
        if merged_data is None or not sample_data:
            return None
        overview_data = []
        for sample_name, adata_obj in sample_data.items():
            density, mean_expr = _spashiny_ctx.matrix_density_and_mean(adata_obj.X)
            overview_data.append(
                {
                    "Sample": sample_name,
                    "Type": "Single Sample",
                    "Cells/Spots": adata_obj.n_obs,
                    "Features": adata_obj.n_vars,
                    "Density": f"{density:.1f}%" if density is not None else "N/A",
                    "Mean Expression": f"{mean_expr:.4f}" if mean_expr is not None else "N/A",
                }
            )
        density, mean_expr = _spashiny_ctx.matrix_density_and_mean(merged_data.X)
        overview_data.append(
            {
                "Sample": "Merged Data",
                "Type": "Merged",
                "Cells/Spots": merged_data.n_obs,
                "Features": merged_data.n_vars,
                "Density": f"{density:.1f}%" if density is not None else "N/A",
                "Mean Expression": f"{mean_expr:.4f}" if mean_expr is not None else "N/A",
            }
        )
        return _spashiny_ctx.pd.DataFrame(overview_data)

    _spashiny_ctx.data_overview_table = data_overview_table

    @_spashiny_ctx.render.download(filename=lambda: "merged_spatial_data.h5ad")
    def download_merged_data():
        merged_data = _spashiny_ctx.merged_adata_reactive.get()
        if merged_data is None:
            _spashiny_ctx.notify("No merged data is available for download.", type_="warning")
            return
        fd, output_path = _spashiny_ctx.tempfile.mkstemp(suffix=".h5ad")
        _spashiny_globals.os.close(fd)
        try:
            merged_data.write_h5ad(output_path)
            _spashiny_ctx.add_log(f"Merged data prepared for browser download: {output_path}")
            with open(output_path, "rb") as f:
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    yield chunk
        finally:
            if _spashiny_globals.os.path.exists(output_path):
                _spashiny_globals.os.remove(output_path)

    _spashiny_ctx.download_merged_data = download_merged_data

    @_spashiny_ctx.render.download(filename=lambda: "processing_report.txt")
    def download_processing_report():
        log_entries = _spashiny_ctx.processing_log_reactive.get()
        merged_data = _spashiny_ctx.merged_adata_reactive.get()
        report_lines = ["Spatial Merge Processing Report", "=" * 50, ""]
        report_lines.append(
            f"Generated at: {_spashiny_ctx.pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        report_lines.append("")
        report_lines.append("Processing Log:")
        report_lines.append("-" * 30)
        for log_entry in log_entries:
            report_lines.append(log_entry)
        report_lines.append("")
        if merged_data is not None:
            report_lines.append("Merged Data Summary:")
            report_lines.append("-" * 30)
            report_lines.append(f"Total cells/spots: {merged_data.n_obs}")
            report_lines.append(f"Total features: {merged_data.n_vars}")
            sample_counts = merged_data.obs["sample"].value_counts()
            for sample, count in sample_counts.items():
                report_lines.append(f"{sample}: {count} cells/spots")
        content = "\n".join(report_lines)
        _spashiny_ctx.add_log("Processing report prepared for browser download.")
        yield content.encode("utf-8")

    _spashiny_ctx.download_processing_report = download_processing_report

    @_spashiny_ctx.render.download(filename=lambda: "sample_distribution_report.pdf")
    def download_sample_distribution_pdf():
        merged_data = _spashiny_ctx.merged_adata_reactive.get()
        if merged_data is None:
            _spashiny_ctx.notify(
                "Please merge data before exporting the sample PDF.", type_="warning"
            )
            return
        fd, pdf_path = _spashiny_ctx.tempfile.mkstemp(suffix=".pdf")
        _spashiny_globals.os.close(fd)
        try:
            fig = _spashiny_ctx.build_sample_distribution_figure(merged_data)
            _spashiny_ctx.write_figs_to_pdf([fig], pdf_path)
            with open(pdf_path, "rb") as f:
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    yield chunk
        finally:
            if _spashiny_globals.os.path.exists(pdf_path):
                _spashiny_globals.os.remove(pdf_path)

    _spashiny_ctx.download_sample_distribution_pdf = download_sample_distribution_pdf

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.run_normalization_qc)
    def run_normalization_and_qc():
        _spashiny_globals.set_global_seed(_spashiny_globals.SEED)
        merged_data = _spashiny_ctx.merged_adata_reactive.get()
        if merged_data is None:
            vhit_example_action_id = (
                _spashiny_ctx._latest_example_action_for("joint-five-sample-vhit-example")
                if _spashiny_globals.SPASHINY_LAB_PROFILE
                and _spashiny_ctx.vhit_input_source_mode.get() == "EXAMPLE"
                else ""
            )
            merge_meta = _spashiny_ctx.vhit_merge_metadata.get() or {}
            if vhit_example_action_id and merge_meta:
                try:
                    from cloud.workflow_registry import VHIT_MULTI_SAMPLE_INTEGRATION

                    requested_resource = _spashiny_ctx.input.vhit_compute_resource() or "auto"
                    custom_params = {
                        "target_sum_sm": _spashiny_ctx.safe_target_sum(
                            _spashiny_ctx.input.vhit_target_sum_sm()
                        ),
                        "target_sum_st": _spashiny_ctx.safe_target_sum(
                            _spashiny_ctx.input.vhit_target_sum_st()
                        ),
                        "min_total_intensity": _spashiny_ctx.input.vhit_min_total_intensity(),
                        "max_total_counts": _spashiny_ctx.input.vhit_max_total_counts(),
                        "n_top_genes": int(_spashiny_ctx.input.vhit_n_top_genes()),
                        "n_top_metabolites": int(_spashiny_ctx.input.vhit_n_top_metabolites()),
                        "spatial_variable_batch_key": _spashiny_ctx.input.batch_key() or "sample",
                        "spatial_variable_min_samples": int(_spashiny_ctx.input.min_samples()),
                        "spatial_variable_min_frac": float(_spashiny_ctx.input.min_frac()),
                        "spatial_variable_min_logfc": float(_spashiny_ctx.input.min_logfc()),
                    }
                    job = _spashiny_ctx._submit_cloud_example_action_job(
                        workflow_name=VHIT_MULTI_SAMPLE_INTEGRATION,
                        example_action_ids=("joint-five-sample-vhit-example",),
                        parameters={"stage": "qc", "custom_params": custom_params},
                        requested_resource=requested_resource,
                    )
                    _spashiny_ctx.vhit_qc_summary.set(
                        {"cloud_job_id": job.job_id, "status": "QUEUED", "stage": "qc"}
                    )
                    _spashiny_ctx.vhit_training_state.set(f"QC job submitted: {job.job_id}")
                    _spashiny_ctx.add_normalization_log(
                        f"Worker normalization and QC submitted: {job.job_id}"
                    )
                    _spashiny_ctx._show_multisample_prepare_modal(
                        job_id=job.job_id, title="Multi-sample normalization and QC"
                    )
                    _spashiny_ctx.notify(
                        "Normalization and QC job submitted.", type_="message", duration=8
                    )
                except Exception as exc:
                    _spashiny_ctx.add_normalization_log(
                        f"Worker normalization and QC submission failed: {exc}"
                    )
                    _spashiny_ctx.notify(
                        f"Could not submit normalization and QC: {exc}", type_="error", duration=8
                    )
                return
            _spashiny_ctx.add_normalization_log("Merged data is not available.")
            _spashiny_ctx.notify(
                "Please merge data before running normalization and QC.", type_="warning"
            )
            return
        _spashiny_ctx.show_busy_modal(
            "Normalization and QC",
            "Running normalization, filtering, and spatial variable feature analysis...",
        )
        try:
            _spashiny_ctx.add_normalization_log("Started normalization and quality control.")
            _spashiny_globals.preflight_memory(
                "VHIT normalization and QC",
                adata=merged_data,
                multiplier=2.0,
                min_available_gb=1.8,
                log_func=_spashiny_ctx.add_normalization_log,
                notify_func=_spashiny_ctx.notify,
            )
            adata_obj = _spashiny_globals.compact_adata_X(merged_data)
            _spashiny_ctx.add_normalization_log(
                "Normalization and QC uses the existing AnnData object to avoid duplicating large matrices."
            )
            _spashiny_globals.set_compact_layer(adata_obj, "counts")
            _spashiny_ctx.add_normalization_log("Saved raw counts to layer 'counts'.")
            target_sum_sm = _spashiny_ctx.input.vhit_target_sum_sm()
            target_sum_st = _spashiny_ctx.input.vhit_target_sum_st()
            _spashiny_globals.smt.pp.normalize_total_joint_adata_sm_st(
                adata_obj, target_sum_SM=target_sum_sm, target_sum_ST=target_sum_st
            )
            _spashiny_globals.set_compact_layer(adata_obj, "normalized")
            _spashiny_ctx.add_normalization_log(
                f"Normalization completed with target_sum_SM={target_sum_sm}, target_sum_ST={target_sum_st}."
            )
            min_intensity = _spashiny_ctx.input.vhit_min_total_intensity()
            max_counts = _spashiny_ctx.input.vhit_max_total_counts()
            n_before = adata_obj.n_obs
            _spashiny_ctx.add_normalization_log(f"Cells/spots before filtering: {n_before}")
            if "total_intensity" in adata_obj.obs.columns:
                adata_obj = _spashiny_globals.compact_adata_X(
                    adata_obj[adata_obj.obs["total_intensity"] >= min_intensity].copy()
                )
                _spashiny_ctx.add_normalization_log(f"Applied total_intensity >= {min_intensity}")
            if "total_counts" in adata_obj.obs.columns:
                adata_obj = _spashiny_globals.compact_adata_X(
                    adata_obj[adata_obj.obs["total_counts"] <= max_counts].copy()
                )
                _spashiny_ctx.add_normalization_log(f"Applied total_counts <= {max_counts}")
            n_after = adata_obj.n_obs
            _spashiny_ctx.add_normalization_log(
                f"Filtering completed. Retained {n_after} cells/spots, removed {n_before - n_after}."
            )
            n_top_genes = _spashiny_ctx.input.vhit_n_top_genes()
            n_top_metabolites = _spashiny_ctx.input.vhit_n_top_metabolites()
            batch_key = _spashiny_ctx.input.batch_key()
            min_samples = _spashiny_ctx.input.min_samples()
            min_frac = _spashiny_ctx.input.min_frac()
            min_logfc = _spashiny_ctx.input.min_logfc()
            _spashiny_globals.smt.pp.spatial_variable_joint_adata_sm_st(
                adata_obj,
                n_top_genes=n_top_genes,
                n_top_metabolites=n_top_metabolites,
                batch_key=batch_key,
                min_samples=min_samples,
                min_frac=min_frac,
                min_logfc=min_logfc,
            )
            _spashiny_ctx.add_normalization_log("Spatially variable feature analysis completed.")
            if "highly_variable_moranI" in adata_obj.var.columns:
                hv_count = int(adata_obj.var["highly_variable_moranI"].sum())
                if hv_count == 0:
                    raise ValueError("Spatial-variable QC retained no features.")
                adata_high_var = _spashiny_globals.compact_adata_X(
                    adata_obj[:, adata_obj.var["highly_variable_moranI"]].copy()
                )
                _spashiny_ctx.add_normalization_log(
                    f"Retained {hv_count} highly variable Moran's I features."
                )
            else:
                raise ValueError(
                    "Native spatial-variable QC did not create its selection; unfiltered inputs were not substituted."
                )
            _spashiny_ctx.processed_data.set(adata_high_var)
            _spashiny_ctx.add_normalization_log(
                f"Normalization and QC completed successfully. Final shape: {adata_high_var.shape}"
            )
            _spashiny_ctx.notify("Normalization and QC completed successfully.", type_="message")
        except Exception as e:
            error_msg = _spashiny_globals.user_facing_error("Normalization and QC failed", e)
            _spashiny_ctx.add_normalization_log(error_msg)
            _spashiny_ctx.notify(
                error_msg,
                type_="error",
                duration=14 if _spashiny_globals.is_memory_related_exception(e) else 8,
            )
            _spashiny_ctx.traceback.print_exc()
        finally:
            _spashiny_ctx.close_busy_modal()

    _spashiny_ctx.run_normalization_and_qc = run_normalization_and_qc

    @_spashiny_ctx.render.ui
    def normalization_status():
        _qc_result_path = _spashiny_ctx.vhit_qc_result_path.get()
        _qc_metadata = _spashiny_ctx.vhit_qc_metadata.get()
        logs = _spashiny_ctx.normalization_log.get()
        cloud_card = _spashiny_ctx._cloud_training_progress_card(
            _spashiny_ctx.vhit_qc_summary.get(), title="Multi-sample normalization and QC"
        )
        if not logs:
            return _spashiny_ctx.ui.div(
                _spashiny_ctx.ui.h4("Waiting for Processing"),
                _spashiny_ctx.ui.p("Configure parameters and click 'Run Normalization and QC'."),
            )
        recent_logs = logs[-5:] if len(logs) > 5 else logs
        log_items = [_spashiny_ctx.ui.tags.li(log_line) for log_line in recent_logs]
        return _spashiny_ctx.ui.div(
            cloud_card if cloud_card is not None else _spashiny_ctx.ui.div(),
            _spashiny_ctx.ui.h4("Processing Log"),
            _spashiny_ctx.ui.tags.ul(*log_items),
            _spashiny_ctx.ui.p(f"Total log entries: {len(logs)}"),
        )

    _spashiny_ctx.normalization_status = normalization_status

    @_spashiny_ctx.render.text
    def vhit_qc_status():
        data = _spashiny_ctx.processed_data.get()
        if data is None and _spashiny_ctx.vhit_qc_metadata.get():
            return "Completed (worker)"
        if data is None:
            return "Waiting"
        return "Completed"

    _spashiny_ctx.vhit_qc_status = vhit_qc_status

    @_spashiny_ctx.render.text
    def cell_count():
        data = _spashiny_ctx.processed_data.get()
        metadata = _spashiny_ctx.vhit_qc_metadata.get() or {}
        if data is None and metadata:
            return f"{int(metadata.get('n_obs', 0)):,}"
        if data is None:
            return "N/A"
        return f"{data.n_obs:,}"

    _spashiny_ctx.cell_count = cell_count

    @_spashiny_ctx.render.text
    def gene_count():
        data = _spashiny_ctx.processed_data.get()
        metadata = _spashiny_ctx.vhit_qc_metadata.get() or {}
        if data is None and metadata:
            return f"{int(metadata.get('n_vars', 0)):,}"
        if data is None:
            return "N/A"
        return f"{data.n_vars:,}"

    _spashiny_ctx.gene_count = gene_count

    def build_qc_violin_figure(data):
        qc_metrics = []
        if "total_counts" in data.obs.columns:
            qc_metrics.append("total_counts")
        if "n_genes_by_counts" in data.obs.columns:
            qc_metrics.append("n_genes_by_counts")
        if "total_intensity" in data.obs.columns:
            qc_metrics.append("total_intensity")
        if not qc_metrics:
            fig, ax = _spashiny_globals.plt.subplots(figsize=(8, 6))
            ax.text(
                0.5,
                0.5,
                "No QC metrics are available.",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=14,
            )
            ax.set_title("QC Metrics")
            return fig
        n_metrics = len(qc_metrics)
        fig, axes = _spashiny_globals.plt.subplots(1, n_metrics, figsize=(5 * n_metrics, 6))
        if n_metrics == 1:
            axes = [axes]
        for i, metric in enumerate(qc_metrics):
            ax = axes[i]
            values = _spashiny_ctx.pd.to_numeric(data.obs[metric], errors="coerce").dropna().values
            if len(values) == 0:
                ax.text(
                    0.5,
                    0.5,
                    f"No valid values for {metric}.",
                    ha="center",
                    va="center",
                    transform=ax.transAxes,
                )
                ax.set_title(metric)
                continue
            ax.violinplot([values], showmeans=True, showmedians=True)
            ax.set_title(f"{metric} Distribution")
            ax.set_ylabel(metric)
            ax.set_xticks([1])
            ax.set_xticklabels([""])
            mean_val = _spashiny_globals.np.mean(values)
            median_val = _spashiny_globals.np.median(values)
            ax.text(
                0.05,
                0.95,
                f"Mean: {mean_val:.2f}",
                transform=ax.transAxes,
                va="top",
                bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
            )
            ax.text(
                0.05,
                0.85,
                f"Median: {median_val:.2f}",
                transform=ax.transAxes,
                va="top",
                bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
            )
        _spashiny_globals.plt.tight_layout()
        return fig

    _spashiny_ctx.build_qc_violin_figure = build_qc_violin_figure

    def build_qc_scatter_figure(data, min_intensity, max_counts):
        has_counts = "total_counts" in data.obs.columns
        has_genes = "n_genes_by_counts" in data.obs.columns
        has_intensity = "total_intensity" in data.obs.columns
        if not (has_counts and has_genes):
            fig, ax = _spashiny_globals.plt.subplots(figsize=(8, 6))
            ax.text(
                0.5,
                0.5,
                "Required QC metrics are missing.",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=14,
            )
            ax.set_title("QC Scatter Plot")
            return fig
        fig, ax = _spashiny_globals.plt.subplots(figsize=(10, 8))
        if has_intensity:
            scatter = ax.scatter(
                data.obs["total_counts"],
                data.obs["n_genes_by_counts"],
                c=data.obs["total_intensity"],
                alpha=0.6,
                s=10,
            )
            _spashiny_globals.plt.colorbar(scatter, ax=ax, label="Total Intensity")
        else:
            ax.scatter(data.obs["total_counts"], data.obs["n_genes_by_counts"], alpha=0.6, s=10)
        ax.set_xlabel("Total Counts")
        ax.set_ylabel("Number of Genes")
        ax.set_title("QC Scatter Plot")
        ax.grid(True, alpha=0.3)
        ax.axvline(
            x=max_counts, color="r", linestyle="--", alpha=0.7, label=f"Max Counts: {max_counts}"
        )
        ax.legend()
        _spashiny_globals.plt.tight_layout()
        return fig

    _spashiny_ctx.build_qc_scatter_figure = build_qc_scatter_figure

    def build_spatial_variable_figure(data):
        if "highly_variable_moranI" not in data.var.columns:
            fig, ax = _spashiny_globals.plt.subplots(figsize=(8, 6))
            ax.text(
                0.5,
                0.5,
                "Please run spatial variable feature analysis first.",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=14,
            )
            ax.set_title("Spatial Variable Features")
            return fig
        highly_variable = data.var["highly_variable_moranI"]
        n_high_var = int(highly_variable.sum())
        fig, (ax1, ax2) = _spashiny_globals.plt.subplots(1, 2, figsize=(12, 5))
        labels = ["Highly Variable", "Other Features"]
        sizes = [n_high_var, len(highly_variable) - n_high_var]
        colors = ["#ff9999", "#66b3ff"]
        ax1.pie(sizes, labels=labels, colors=colors, autopct="%1.1f%%", startangle=90)
        ax1.set_title("Highly Variable Feature Ratio")
        try:
            if "morans_i" in data.var.columns:
                vals = _spashiny_ctx.pd.to_numeric(data.var["morans_i"], errors="coerce").dropna()
                ax2.hist(vals, bins=50, alpha=0.7, color="skyblue")
                ax2.axvline(vals.median(), color="red", linestyle="--", label="Median")
                ax2.set_xlabel("Moran's I")
                ax2.set_ylabel("Feature Count")
                ax2.set_title("Spatial Autocorrelation Distribution")
                ax2.legend()
                ax2.grid(True, alpha=0.3)
            else:
                X = (
                    data.X.toarray()
                    if hasattr(data.X, "toarray")
                    else _spashiny_globals.np.asarray(data.X)
                )
                ax2.hist(
                    _spashiny_globals.np.var(X, axis=0), bins=50, alpha=0.7, color="lightgreen"
                )
                ax2.set_xlabel("Expression Variance")
                ax2.set_ylabel("Feature Count")
                ax2.set_title("Feature Variance Distribution")
                ax2.grid(True, alpha=0.3)
        except Exception:
            ax2.text(
                0.5,
                0.5,
                "Feature distribution could not be plotted.",
                ha="center",
                va="center",
                transform=ax2.transAxes,
            )
            ax2.set_title("Feature Distribution")
        _spashiny_globals.plt.suptitle(
            f"Spatial Variable Feature Analysis ({n_high_var} highly variable features)"
        )
        _spashiny_globals.plt.tight_layout()
        return fig

    _spashiny_ctx.build_spatial_variable_figure = build_spatial_variable_figure

    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("qc_violin_plot")
    def qc_violin_plot():
        data = _spashiny_ctx.processed_data.get()
        if data is None:
            fig, ax = _spashiny_globals.plt.subplots(figsize=(8, 6))
            ax.text(
                0.5,
                0.5,
                "Please complete normalization and QC first.",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=14,
            )
            ax.set_title("QC Violin Plot")
            return fig
        return _spashiny_ctx.build_qc_violin_figure(data)

    _spashiny_ctx.qc_violin_plot = qc_violin_plot

    @_spashiny_ctx.render.ui
    def qc_violin_display():
        _qc_result_path = _spashiny_ctx.vhit_qc_result_path.get()
        _qc_metadata = _spashiny_ctx.vhit_qc_metadata.get()
        return _spashiny_ctx._cloud_worker_plot_ui(
            _spashiny_ctx.vhit_qc_summary.get(),
            workflow_name="vhit_multi_sample_integration",
            stage="qc",
            rel_path="figures/qc_violin.png",
            fallback_output="qc_violin_plot",
            alt="QC violin plot",
        )

    _spashiny_ctx.qc_violin_display = qc_violin_display

    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("qc_scatter_plot")
    def qc_scatter_plot():
        data = _spashiny_ctx.processed_data.get()
        if data is None:
            fig, ax = _spashiny_globals.plt.subplots(figsize=(8, 6))
            ax.text(
                0.5,
                0.5,
                "Please complete normalization and QC first.",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=14,
            )
            ax.set_title("QC Scatter Plot")
            return fig
        return _spashiny_ctx.build_qc_scatter_figure(
            data,
            _spashiny_ctx.input.vhit_min_total_intensity(),
            _spashiny_ctx.input.vhit_max_total_counts(),
        )

    _spashiny_ctx.qc_scatter_plot = qc_scatter_plot

    @_spashiny_ctx.render.ui
    def qc_scatter_display():
        _qc_result_path = _spashiny_ctx.vhit_qc_result_path.get()
        _qc_metadata = _spashiny_ctx.vhit_qc_metadata.get()
        return _spashiny_ctx._cloud_worker_plot_ui(
            _spashiny_ctx.vhit_qc_summary.get(),
            workflow_name="vhit_multi_sample_integration",
            stage="qc",
            rel_path="figures/qc_scatter.png",
            fallback_output="qc_scatter_plot",
            alt="QC scatter plot",
        )

    _spashiny_ctx.qc_scatter_display = qc_scatter_display

    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("spatial_variable_genes_plot")
    def spatial_variable_genes_plot():
        data = _spashiny_ctx.processed_data.get()
        if data is None:
            fig, ax = _spashiny_globals.plt.subplots(figsize=(8, 6))
            ax.text(
                0.5,
                0.5,
                "Please complete spatial variable analysis first.",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=14,
            )
            ax.set_title("Spatial Variable Features")
            return fig
        return _spashiny_ctx.build_spatial_variable_figure(data)

    _spashiny_ctx.spatial_variable_genes_plot = spatial_variable_genes_plot

    @_spashiny_ctx.render.ui
    def spatial_variable_display():
        _qc_result_path = _spashiny_ctx.vhit_qc_result_path.get()
        _qc_metadata = _spashiny_ctx.vhit_qc_metadata.get()
        return _spashiny_ctx._cloud_worker_plot_ui(
            _spashiny_ctx.vhit_qc_summary.get(),
            workflow_name="vhit_multi_sample_integration",
            stage="qc",
            rel_path="figures/spatial_variable_features.png",
            fallback_output="spatial_variable_genes_plot",
            alt="Spatially variable features",
        )

    _spashiny_ctx.spatial_variable_display = spatial_variable_display

    @_spashiny_ctx.render.table
    def top_spatial_genes_table():
        _qc_result_path = _spashiny_ctx.vhit_qc_result_path.get()
        _qc_metadata = _spashiny_ctx.vhit_qc_metadata.get()
        data = _spashiny_ctx.processed_data.get()
        if data is None or "highly_variable_moranI" not in data.var.columns:
            worker_rows = _spashiny_ctx._cloud_worker_table(
                _spashiny_ctx.vhit_qc_summary.get(),
                workflow_name="vhit_multi_sample_integration",
                stage="qc",
                rel_path="tables/top_spatial_features.json",
            )
            if worker_rows:
                return _spashiny_ctx.pd.DataFrame(worker_rows)
            return None
        high_var_genes = data.var[data.var["highly_variable_moranI"]]
        if "morans_i" in high_var_genes.columns:
            top_genes = high_var_genes.nlargest(20, "morans_i")
        elif "spatial_variable_score" in high_var_genes.columns:
            top_genes = high_var_genes.nlargest(20, "spatial_variable_score")
        else:
            top_genes = high_var_genes.head(20)
        table_data = []
        for gene_id, row in top_genes.iterrows():
            gene_info = {
                "Feature ID": gene_id,
                "Feature Name": row.get("name", gene_id) if "name" in row else gene_id,
                "Type": row.get("type", "Unknown"),
            }
            if "morans_i" in row:
                gene_info["Moran's I"] = f"{row['morans_i']:.4f}"
            if "spatial_variable_score" in row:
                gene_info["Spatial Variable Score"] = f"{row['spatial_variable_score']:.4f}"
            if "mean_expression" in row:
                gene_info["Mean Expression"] = f"{row['mean_expression']:.4f}"
            table_data.append(gene_info)
        return _spashiny_ctx.pd.DataFrame(table_data)

    _spashiny_ctx.top_spatial_genes_table = top_spatial_genes_table

    @_spashiny_ctx.render.table
    def qc_statistics_table():
        _qc_result_path = _spashiny_ctx.vhit_qc_result_path.get()
        _qc_metadata = _spashiny_ctx.vhit_qc_metadata.get()
        data = _spashiny_ctx.processed_data.get()
        if data is None:
            worker_rows = _spashiny_ctx._cloud_worker_table(
                _spashiny_ctx.vhit_qc_summary.get(),
                workflow_name="vhit_multi_sample_integration",
                stage="qc",
                rel_path="tables/qc_statistics.json",
            )
            if worker_rows:
                return _spashiny_ctx.pd.DataFrame(worker_rows)
            return None
        stats_data = [
            {
                "Metric": "Total Cells/Spots",
                "Value": f"{data.n_obs:,}",
                "Description": "Total number of observations after processing",
            },
            {
                "Metric": "Total Features",
                "Value": f"{data.n_vars:,}",
                "Description": "Total number of variables after processing",
            },
        ]
        qc_metrics = ["total_counts", "n_genes_by_counts", "total_intensity"]
        for metric in qc_metrics:
            if metric in data.obs.columns:
                vals = _spashiny_ctx.pd.to_numeric(data.obs[metric], errors="coerce")
                stats_data.append(
                    {
                        "Metric": metric.replace("_", " ").title(),
                        "Value": f"{vals.mean():.2f} ({vals.std():.2f})",
                        "Description": f"Range: {vals.min():.2f} - {vals.max():.2f}",
                    }
                )
        if "highly_variable_moranI" in data.var.columns:
            n_high_var = int(data.var["highly_variable_moranI"].sum())
            stats_data.append(
                {
                    "Metric": "Highly Variable Features",
                    "Value": f"{n_high_var:,} ({n_high_var / data.n_vars * 100:.1f}%)",
                    "Description": "Selected by Moran's I-based spatial variability",
                }
            )
        return _spashiny_ctx.pd.DataFrame(stats_data)

    _spashiny_ctx.qc_statistics_table = qc_statistics_table

    @_spashiny_ctx.render.download(filename=lambda: "vhit_tables_csv.zip")
    def download_vhit_tables_zip():
        import io

        files = {}
        merged_data = _spashiny_ctx.merged_adata_reactive.get()
        sample_data = _spashiny_ctx.sample_data_dict.get()
        if merged_data is not None and "sample" in merged_data.obs:
            counts = merged_data.obs["sample"].value_counts()
            total = max(int(merged_data.n_obs), 1)
            files["sample_distribution.csv"] = _spashiny_ctx.pd.DataFrame(
                [
                    {
                        "Sample": sample,
                        "Cells/Spots": int(count),
                        "Percent": f"{count / total * 100:.1f}%",
                    }
                    for sample, count in counts.items()
                ]
            )
        if merged_data is not None and sample_data:
            overview_rows = []
            for sample_name, adata_obj in sample_data.items():
                density, mean_expr = _spashiny_ctx.matrix_density_and_mean(adata_obj.X)
                overview_rows.append(
                    {
                        "Sample": sample_name,
                        "Type": "Single Sample",
                        "Cells/Spots": adata_obj.n_obs,
                        "Features": adata_obj.n_vars,
                        "Density": f"{density:.1f}%" if density is not None else "N/A",
                        "Mean Expression": f"{mean_expr:.4f}" if mean_expr is not None else "N/A",
                    }
                )
            density, mean_expr = _spashiny_ctx.matrix_density_and_mean(merged_data.X)
            overview_rows.append(
                {
                    "Sample": "Merged Data",
                    "Type": "Merged",
                    "Cells/Spots": merged_data.n_obs,
                    "Features": merged_data.n_vars,
                    "Density": f"{density:.1f}%" if density is not None else "N/A",
                    "Mean Expression": f"{mean_expr:.4f}" if mean_expr is not None else "N/A",
                }
            )
            files["data_overview.csv"] = _spashiny_ctx.pd.DataFrame(overview_rows)
        data = _spashiny_ctx.processed_data.get()
        if data is not None:
            stats_rows = [
                {
                    "Metric": "Total Cells/Spots",
                    "Value": f"{data.n_obs:,}",
                    "Description": "Total observations",
                },
                {
                    "Metric": "Total Features",
                    "Value": f"{data.n_vars:,}",
                    "Description": "Total variables",
                },
            ]
            for metric in ["total_counts", "n_genes_by_counts", "total_intensity"]:
                if metric in data.obs.columns:
                    vals = _spashiny_ctx.pd.to_numeric(data.obs[metric], errors="coerce")
                    stats_rows.append(
                        {
                            "Metric": metric.replace("_", " ").title(),
                            "Value": f"{vals.mean():.2f} (+/- {vals.std():.2f})",
                            "Description": f"Range: {vals.min():.2f} - {vals.max():.2f}",
                        }
                    )
            files["qc_statistics.csv"] = _spashiny_ctx.pd.DataFrame(stats_rows)
            if "highly_variable_moranI" in data.var.columns:
                high_var_genes = data.var[data.var["highly_variable_moranI"]]
                if "morans_i" in high_var_genes.columns:
                    top_genes = high_var_genes.nlargest(20, "morans_i")
                elif "spatial_variable_score" in high_var_genes.columns:
                    top_genes = high_var_genes.nlargest(20, "spatial_variable_score")
                else:
                    top_genes = high_var_genes.head(20)
                rows = []
                for gene_id, row in top_genes.iterrows():
                    item = {
                        "Feature ID": gene_id,
                        "Feature Name": row.get("name", gene_id) if "name" in row else gene_id,
                        "Type": row.get("type", "Unknown"),
                    }
                    if "morans_i" in row:
                        item["Moran's I"] = row["morans_i"]
                    if "spatial_variable_score" in row:
                        item["Spatial Variable Score"] = row["spatial_variable_score"]
                    rows.append(item)
                files["top_spatial_variable_features.csv"] = _spashiny_ctx.pd.DataFrame(rows)
        try:
            loss_stats = _spashiny_ctx.build_vhit_loss_statistics_dataframe()
            if loss_stats is not None:
                files["vhit_loss_statistics.csv"] = loss_stats
        except Exception:
            pass
        try:
            latent_stats = _spashiny_ctx.build_vhit_latent_embedding_dataframe()
            if latent_stats is not None:
                files["vhit_latent_embedding_statistics.csv"] = latent_stats
        except Exception:
            pass
        try:
            cluster_stats = _spashiny_ctx.build_vhit_cluster_statistics_dataframe()
            if cluster_stats is not None:
                files["vhit_cluster_statistics.csv"] = cluster_stats
        except Exception:
            pass
        if not files:
            files["README.csv"] = _spashiny_ctx.pd.DataFrame(
                {"Message": ["No VHIT table data is available yet."]}
            )
        buf = io.BytesIO()
        with _spashiny_ctx.zipfile.ZipFile(buf, "w", _spashiny_ctx.zipfile.ZIP_DEFLATED) as zf:
            for name, df in files.items():
                zf.writestr(name, df.to_csv(index=False))
        buf.seek(0)
        yield buf.read()

    _spashiny_ctx.download_vhit_tables_zip = download_vhit_tables_zip

    @_spashiny_ctx.render.download(filename=lambda: "processed_spatial_data.h5ad")
    def download_processed_data():
        data = _spashiny_ctx.processed_data.get()
        if data is None:
            _spashiny_ctx.notify("No processed data is available for download.", type_="warning")
            return
        fd, output_path = _spashiny_ctx.tempfile.mkstemp(suffix=".h5ad")
        _spashiny_globals.os.close(fd)
        try:
            data.write_h5ad(output_path)
            _spashiny_ctx.add_normalization_log(
                f"Processed data prepared for browser download: {output_path}"
            )
            with open(output_path, "rb") as f:
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    yield chunk
        finally:
            if _spashiny_globals.os.path.exists(output_path):
                _spashiny_globals.os.remove(output_path)

    _spashiny_ctx.download_processed_data = download_processed_data

    @_spashiny_ctx.render.download(filename=lambda: "cvae_integration_results.h5ad")
    def download_cvae_results():
        result_path = _spashiny_ctx.vhit_cvae_result_path.get()
        if result_path and _spashiny_globals.os.path.exists(result_path):
            with open(result_path, "rb") as f:
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    yield chunk
            return
        data = None
        try:
            data = _spashiny_ctx.vhit_cvae_result.get()
        except Exception:
            data = None
        try:
            if data is None:
                data = _spashiny_ctx.vae_analysis_result_adata.get()
        except Exception:
            pass
        if data is None:
            try:
                data = _spashiny_ctx.vae_processed_adata.get()
            except Exception:
                data = None
        if data is None:
            data = _spashiny_ctx.processed_data.get()
        if data is None:
            _spashiny_ctx.notify(
                "No integration result is available for download.", type_="warning"
            )
            return
        fd, output_path = _spashiny_ctx.tempfile.mkstemp(suffix=".h5ad")
        _spashiny_globals.os.close(fd)
        try:
            data.write_h5ad(output_path)
            with open(output_path, "rb") as f:
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    yield chunk
        finally:
            if _spashiny_globals.os.path.exists(output_path):
                _spashiny_globals.os.remove(output_path)

    _spashiny_ctx.download_cvae_results = download_cvae_results

    @_spashiny_ctx.render.download(filename=lambda: "normalization_qc_report.pdf")
    def download_normalization_qc_pdf():
        data = _spashiny_ctx.processed_data.get()
        if data is None:
            _spashiny_ctx.notify(
                "Please run normalization and QC before exporting the PDF.", type_="warning"
            )
            return
        fd, pdf_path = _spashiny_ctx.tempfile.mkstemp(suffix=".pdf")
        _spashiny_globals.os.close(fd)
        try:
            figs = [
                _spashiny_ctx.build_qc_violin_figure(data),
                _spashiny_ctx.build_qc_scatter_figure(
                    data,
                    _spashiny_ctx.input.vhit_min_total_intensity(),
                    _spashiny_ctx.input.vhit_max_total_counts(),
                ),
                _spashiny_ctx.build_spatial_variable_figure(data),
            ]
            _spashiny_ctx.write_figs_to_pdf(figs, pdf_path)
            with open(pdf_path, "rb") as f:
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    yield chunk
        finally:
            if _spashiny_globals.os.path.exists(pdf_path):
                _spashiny_globals.os.remove(pdf_path)

    _spashiny_ctx.download_normalization_qc_pdf = download_normalization_qc_pdf

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.run_cvae_training)
    async def run_cvae_training():
        data = _spashiny_ctx.processed_data.get()
        vhit_example_action_id = (
            _spashiny_ctx._latest_example_action_for("joint-five-sample-vhit-example")
            if _spashiny_globals.SPASHINY_LAB_PROFILE
            and _spashiny_ctx.vhit_input_source_mode.get() == "EXAMPLE"
            else ""
        )
        if data is None and (not vhit_example_action_id):
            _spashiny_ctx.add_vhit_training_log("Processed data is not available.")
            _spashiny_ctx.notify(
                "Please run Normalization and QC before ConditionalVAE training.", type_="warning"
            )
            _spashiny_ctx.vhit_training_state.set("Failed: no processed data")
            return
        if vhit_example_action_id and (not _spashiny_ctx.vhit_merge_result_path.get()):
            _spashiny_ctx.add_vhit_training_log(
                "Worker-managed example inputs are bound, but the persisted merge step is not complete."
            )
            _spashiny_ctx.notify(
                "Click Merge Data and wait for its worker job to complete before training.",
                type_="warning",
            )
            _spashiny_ctx.vhit_training_state.set("Waiting for Merge Data")
            return
        if vhit_example_action_id and (not _spashiny_ctx.vhit_qc_result_path.get()):
            _spashiny_ctx.add_vhit_training_log(
                "The persisted merge is available, but worker normalization and QC has not completed."
            )
            _spashiny_ctx.notify(
                "Run Normalization and QC and wait for completion before ConditionalVAE training.",
                type_="warning",
            )
            _spashiny_ctx.vhit_training_state.set("Waiting for Normalization and QC")
            return
        if _spashiny_ctx.vhit_is_training.get():
            _spashiny_ctx.notify("ConditionalVAE training is already running.", type_="warning")
            return

        def read_input_value(getter, default=None):
            try:
                value = getter()
                return default if value is None else value
            except Exception:
                return default

        def add_custom_param(params, key, value, cast=None):
            if value is None or value == "":
                return
            try:
                params[key] = cast(value) if cast is not None else value
            except Exception:
                params[key] = value

        _spashiny_ctx.show_busy_modal(
            "ConditionalVAE Training",
            "Starting SpatialMETA in a separate backend Python process...",
        )
        _spashiny_ctx.vhit_is_training.set(True)
        _spashiny_ctx.vhit_training_state.set("Preparing backend job")
        _spashiny_ctx.vhit_cvae_model.set(None)
        _spashiny_ctx.vhit_cvae_result.set(None)
        _spashiny_ctx.vhit_cvae_result_path.set(None)
        _spashiny_ctx.vhit_cvae_summary.set(None)
        _spashiny_ctx.vhit_cvae_loss_path.set(None)
        _spashiny_ctx.vhit_cvae_model_state_path.set(None)
        _spashiny_ctx.vhit_loss_dict.set(None)
        cloud_job_submitted = False
        try:
            requested_resource = (
                read_input_value(_spashiny_ctx.input.vhit_compute_resource, "auto") or "auto"
            )
            cloud_parameters = _spashiny_globals.tutorial_job_parameters(
                "stsm", "multi", input_layer="counts", normalize_input=True
            )
            if vhit_example_action_id:
                try:
                    from cloud.workflow_registry import VHIT_MULTI_SAMPLE_INTEGRATION

                    cloud_job = _spashiny_ctx._submit_prepared_multisample_training(
                        workflow_name=VHIT_MULTI_SAMPLE_INTEGRATION,
                        prepared_summary=_spashiny_ctx.vhit_qc_summary.get(),
                        parameters=cloud_parameters,
                        requested_resource=requested_resource,
                    )
                    _spashiny_ctx.vhit_cvae_job_dir.set(cloud_job.local_workspace)
                    _spashiny_ctx.vhit_cvae_summary.set(
                        {
                            "cloud_job_id": cloud_job.job_id,
                            "status": "QUEUED",
                            "input_source": "example_action",
                        }
                    )
                    cloud_job_submitted = True
                    _spashiny_ctx.vhit_training_state.set(
                        f"Cloud job submitted: {cloud_job.job_id}"
                    )
                    _spashiny_ctx.add_vhit_training_log(
                        f"Lab example GPU job submitted: {cloud_job.job_id}"
                    )
                    _spashiny_ctx.add_vhit_training_log(
                        f"Requested compute resource: {requested_resource}"
                    )
                    _spashiny_ctx.add_vhit_training_log("Open Job Center to monitor progress.")
                    _spashiny_ctx.notify(f"Cloud job created: {cloud_job.job_id}", type_="message")
                    return
                except Exception as cloud_exc:
                    raise RuntimeError(
                        f"Lab example job submission failed: {cloud_exc}"
                    ) from cloud_exc
            from cloud.workflow_registry import VHIT_MULTI_SAMPLE_INTEGRATION

            cloud_job = await _spashiny_ctx._submit_uploaded_multisample_training(
                workflow_name=VHIT_MULTI_SAMPLE_INTEGRATION,
                data=data,
                parameters=cloud_parameters,
                requested_resource=requested_resource,
                source_mode=_spashiny_ctx.vhit_input_source_mode.get(),
            )
            _spashiny_ctx.vhit_cvae_job_dir.set(cloud_job.local_workspace)
            _spashiny_ctx.vhit_cvae_summary.set(
                {
                    "cloud_job_id": cloud_job.job_id,
                    "status": cloud_job.status,
                    "input_source": "upload",
                }
            )
            cloud_job_submitted = True
            _spashiny_ctx.vhit_training_state.set(f"Cloud job submitted: {cloud_job.job_id}")
            _spashiny_ctx.add_vhit_training_log(
                f"Same-analysis processed upload submitted: {cloud_job.job_id}"
            )
        except Exception as e:
            error_msg = _spashiny_globals.user_facing_error("ConditionalVAE training failed", e)
            _spashiny_ctx.vhit_training_state.set("Failed")
            _spashiny_ctx.add_vhit_training_log(error_msg)
            _spashiny_ctx.notify(
                error_msg,
                type_="error",
                duration=14 if _spashiny_globals.is_memory_related_exception(e) else 8,
            )
            __import__("traceback").print_exc()
        finally:
            _spashiny_ctx.vhit_is_training.set(False)
            _spashiny_globals.release_unused_memory()
            if not cloud_job_submitted:
                _spashiny_ctx.close_busy_modal()

    _spashiny_ctx.run_cvae_training = run_cvae_training

    def build_vhit_loss_statistics_dataframe(loss_dict=None):
        loss_dict = _spashiny_ctx.vhit_loss_dict.get() if loss_dict is None else loss_dict
        if not loss_dict:
            return None
        rows = []
        for key, values in loss_dict.items():
            try:
                arr = _spashiny_globals.np.asarray(values, dtype=float)
                rows.append(
                    {
                        "Loss": key,
                        "Start": float(arr[0]),
                        "End": float(arr[-1]),
                        "Min": float(_spashiny_globals.np.min(arr)),
                        "Max": float(_spashiny_globals.np.max(arr)),
                        "Epochs": len(arr),
                    }
                )
            except Exception:
                rows.append(
                    {
                        "Loss": key,
                        "Start": "N/A",
                        "End": "N/A",
                        "Min": "N/A",
                        "Max": "N/A",
                        "Epochs": "N/A",
                    }
                )
        return _spashiny_ctx.pd.DataFrame(rows)

    _spashiny_ctx.build_vhit_loss_statistics_dataframe = build_vhit_loss_statistics_dataframe

    def build_vhit_latent_embedding_dataframe(adata_obj=None):
        adata_obj, should_close = _spashiny_ctx.get_vhit_result_for_display(adata_obj)
        try:
            if adata_obj is None or "X_emb" not in adata_obj.obsm:
                return None
            Z = _spashiny_globals.np.asarray(adata_obj.obsm["X_emb"])
            rows = []
            for i in range(Z.shape[1]):
                values = Z[:, i]
                rows.append(
                    {
                        "Latent Dimension": f"Z{i + 1}",
                        "Mean": float(_spashiny_globals.np.mean(values)),
                        "Std": float(_spashiny_globals.np.std(values)),
                        "Min": float(_spashiny_globals.np.min(values)),
                        "Max": float(_spashiny_globals.np.max(values)),
                    }
                )
            return _spashiny_ctx.pd.DataFrame(rows)
        finally:
            _spashiny_globals.close_display_h5ad(adata_obj, should_close)

    _spashiny_ctx.build_vhit_latent_embedding_dataframe = build_vhit_latent_embedding_dataframe

    def build_vhit_cluster_statistics_dataframe(adata_obj=None):
        adata_obj, should_close = _spashiny_ctx.get_vhit_result_for_display(adata_obj)
        try:
            if adata_obj is None or "VAE_clusters" not in adata_obj.obs.columns:
                return None
            table = adata_obj.obs.groupby("VAE_clusters").size().reset_index(name="Spot Count")
            table["Fraction"] = table["Spot Count"] / adata_obj.n_obs
            if "sample" in adata_obj.obs.columns:
                sample_table = _spashiny_ctx.pd.crosstab(
                    adata_obj.obs["VAE_clusters"], adata_obj.obs["sample"], normalize="index"
                ).reset_index()
                table = table.merge(sample_table, on="VAE_clusters", how="left")
            return table
        finally:
            _spashiny_globals.close_display_h5ad(adata_obj, should_close)

    _spashiny_ctx.build_vhit_cluster_statistics_dataframe = build_vhit_cluster_statistics_dataframe

    def make_vhit_loss_curves_figure(loss_dict=None):
        loss_dict = _spashiny_ctx.vhit_loss_dict.get() if loss_dict is None else loss_dict
        if not loss_dict:
            return _spashiny_ctx.make_empty_plot(
                "Loss curves will be shown after ConditionalVAE training.", "Loss Curves"
            )
        n_items = len(loss_dict)
        ncols = 3
        nrows = int(_spashiny_globals.np.ceil(n_items / ncols))
        fig, axes = _spashiny_globals.plt.subplots(nrows, ncols, figsize=(18, 5 * nrows))
        axes = _spashiny_globals.np.asarray(axes).reshape(-1)
        for ax, (key, values) in zip(axes, loss_dict.items()):
            try:
                ax.plot(values, linewidth=2)
                ax.set_title(str(key))
                ax.set_xlabel("Epoch")
                ax.set_ylabel("Loss")
                ax.grid(True, alpha=0.3)
            except Exception:
                ax.text(0.5, 0.5, f"Cannot plot {key}", ha="center", va="center")
                ax.set_title(str(key))
        for ax in axes[n_items:]:
            ax.axis("off")
        _spashiny_globals.plt.tight_layout()
        return fig

    _spashiny_ctx.make_vhit_loss_curves_figure = make_vhit_loss_curves_figure

    def make_vhit_umap_sample_figure(adata_obj=None):
        adata_obj, should_close = _spashiny_ctx.get_vhit_result_for_display(adata_obj)
        try:
            if adata_obj is None or "X_umap" not in adata_obj.obsm:
                return _spashiny_ctx.make_empty_plot(
                    "UMAP will be shown after ConditionalVAE training.", "UMAP by Sample"
                )
            if "sample" not in adata_obj.obs.columns:
                return _spashiny_ctx.make_empty_plot(
                    "obs['sample'] was not found.", "UMAP by Sample"
                )
            fig, ax = _spashiny_globals.plt.subplots(figsize=(7, 7))
            _spashiny_globals.sc.pl.umap(adata_obj, color="sample", show=False, size=10, ax=ax)
            _spashiny_globals.plt.tight_layout()
            return fig
        finally:
            _spashiny_globals.close_display_h5ad(adata_obj, should_close)

    _spashiny_ctx.make_vhit_umap_sample_figure = make_vhit_umap_sample_figure

    def make_vhit_umap_cluster_figure(adata_obj=None):
        adata_obj, should_close = _spashiny_ctx.get_vhit_result_for_display(adata_obj)
        try:
            if adata_obj is None or "X_umap" not in adata_obj.obsm:
                return _spashiny_ctx.make_empty_plot(
                    "Cluster UMAP will be shown after ConditionalVAE training.", "UMAP by Cluster"
                )
            if "VAE_clusters" not in adata_obj.obs.columns:
                return _spashiny_ctx.make_empty_plot(
                    "VAE cluster column was not found.", "UMAP by Cluster"
                )
            fig, ax = _spashiny_globals.plt.subplots(figsize=(7, 7))
            _spashiny_globals.sc.pl.umap(
                adata_obj, color="VAE_clusters", show=False, size=10, ax=ax
            )
            _spashiny_globals.plt.tight_layout()
            return fig
        finally:
            _spashiny_globals.close_display_h5ad(adata_obj, should_close)

    _spashiny_ctx.make_vhit_umap_cluster_figure = make_vhit_umap_cluster_figure

    def make_vhit_modality_contribution_figure(adata_obj=None):
        adata_obj, should_close = _spashiny_ctx.get_vhit_result_for_display(adata_obj)
        try:
            if adata_obj is None:
                return _spashiny_ctx.make_empty_plot(
                    "Modality contribution will be shown after ConditionalVAE training.",
                    "Modality Contribution",
                )
            if (
                "contribution_st" not in adata_obj.obs.columns
                or "contribution_sm" not in adata_obj.obs.columns
            ):
                return _spashiny_ctx.make_empty_plot(
                    "contribution_st / contribution_sm was not found.", "Modality Contribution"
                )
            fig, ax = _spashiny_globals.plt.subplots(figsize=(8, 6))
            if "sample" in adata_obj.obs.columns:
                df = adata_obj.obs[["sample", "contribution_st", "contribution_sm"]].copy()
                df["contribution_st"] = _spashiny_ctx.pd.to_numeric(
                    df["contribution_st"], errors="coerce"
                )
                df["contribution_sm"] = _spashiny_ctx.pd.to_numeric(
                    df["contribution_sm"], errors="coerce"
                )
                grouped = df.groupby("sample")[["contribution_st", "contribution_sm"]].mean()
                grouped.plot(kind="bar", ax=ax)
                ax.set_xlabel("Sample")
                ax.set_ylabel("Mean Contribution")
                ax.set_title("Mean ST / SM Contribution by Sample")
                ax.legend(["ST", "SM"])
                _spashiny_globals.plt.xticks(rotation=45, ha="right")
            else:
                ax.boxplot(
                    [
                        _spashiny_ctx.pd.to_numeric(
                            adata_obj.obs["contribution_st"], errors="coerce"
                        ),
                        _spashiny_ctx.pd.to_numeric(
                            adata_obj.obs["contribution_sm"], errors="coerce"
                        ),
                    ],
                    labels=["ST", "SM"],
                )
                ax.set_ylabel("Contribution")
                ax.set_title("ST / SM Contribution")
            _spashiny_globals.plt.tight_layout()
            return fig
        finally:
            _spashiny_globals.close_display_h5ad(adata_obj, should_close)

    _spashiny_ctx.make_vhit_modality_contribution_figure = make_vhit_modality_contribution_figure

    def make_vhit_reconstruction_quality_figure(adata_obj=None):
        diag = _spashiny_ctx.get_vhit_reconstruction_diagnostics()
        if diag.get("status") == "skipped":
            return _spashiny_ctx.make_empty_plot(
                diag.get("message") or "Worker reconstruction diagnostics were explicitly skipped.",
                "Original vs Reconstructed",
            )
        scatter_csv = diag.get("scatter_csv")
        if scatter_csv and _spashiny_globals.os.path.exists(scatter_csv):
            df = _spashiny_ctx.pd.read_csv(scatter_csv)
            if {"original", "reconstructed"}.issubset(df.columns):
                fig, ax = _spashiny_globals.plt.subplots(figsize=(7, 7))
                ax.scatter(df["original"], df["reconstructed"], s=3, alpha=0.25)
                ax.set_xlabel("Original normalized value")
                ax.set_ylabel("Reconstructed value")
                ax.set_title("Original vs Reconstructed")
                try:
                    corr = _spashiny_globals.np.corrcoef(df["original"], df["reconstructed"])[0, 1]
                    ax.text(
                        0.05,
                        0.95,
                        f"Pearson r = {corr:.3f}",
                        transform=ax.transAxes,
                        va="top",
                        bbox=dict(boxstyle="round", facecolor="white", alpha=0.8),
                    )
                except Exception:
                    pass
                _spashiny_globals.plt.tight_layout()
                return fig
        adata_obj, should_close = _spashiny_ctx.get_vhit_result_for_display(adata_obj)
        try:
            if should_close or getattr(adata_obj, "isbacked", False):
                return _spashiny_ctx.make_empty_plot(
                    "Worker reconstruction diagnostics were not saved. The large backed matrix will not be loaded into the Web process.",
                    "Original vs Reconstructed",
                )
            if adata_obj is None or "reconstruction" not in adata_obj.layers:
                message = (
                    diag.get("message") or "Reconstruction diagnostics were not saved for this job."
                )
                return _spashiny_ctx.make_empty_plot(message, "Original vs Reconstructed")
            X0 = (
                adata_obj.layers["normalized_for_cvae"]
                if "normalized_for_cvae" in adata_obj.layers
                else adata_obj.X
            )
            X1 = adata_obj.layers["reconstruction"]
            X0 = X0.toarray() if hasattr(X0, "toarray") else _spashiny_globals.np.asarray(X0)
            X1 = X1.toarray() if hasattr(X1, "toarray") else _spashiny_globals.np.asarray(X1)
            if X0.size == 0 or X1.size == 0:
                return _spashiny_ctx.make_empty_plot(
                    "Reconstruction matrix is empty.", "Original vs Reconstructed"
                )
            rng = _spashiny_globals.np.random.default_rng(_spashiny_globals.SEED)
            n_points = min(5000, X0.size, X1.size)
            idx = rng.choice(min(X0.size, X1.size), size=n_points, replace=False)
            x = X0.reshape(-1)[idx]
            y = X1.reshape(-1)[idx]
            fig, ax = _spashiny_globals.plt.subplots(figsize=(7, 7))
            ax.scatter(x, y, s=3, alpha=0.25)
            ax.set_xlabel("Original normalized value")
            ax.set_ylabel("Reconstructed value")
            ax.set_title("Original vs Reconstructed")
            try:
                corr = _spashiny_globals.np.corrcoef(x, y)[0, 1]
                ax.text(
                    0.05,
                    0.95,
                    f"Pearson r = {corr:.3f}",
                    transform=ax.transAxes,
                    va="top",
                    bbox=dict(boxstyle="round", facecolor="white", alpha=0.8),
                )
            except Exception:
                pass
            _spashiny_globals.plt.tight_layout()
            return fig
        finally:
            _spashiny_globals.close_display_h5ad(adata_obj, should_close)

    _spashiny_ctx.make_vhit_reconstruction_quality_figure = make_vhit_reconstruction_quality_figure

    def make_vhit_reconstruction_error_figure(adata_obj=None):
        diag = _spashiny_ctx.get_vhit_reconstruction_diagnostics()
        if diag.get("status") == "skipped":
            return _spashiny_ctx.make_empty_plot(
                diag.get("message") or "Worker reconstruction diagnostics were explicitly skipped.",
                "Reconstruction Error",
            )
        mse_csv = diag.get("mse_csv")
        if mse_csv and _spashiny_globals.os.path.exists(mse_csv):
            df = _spashiny_ctx.pd.read_csv(mse_csv)
            if "mse" in df.columns:
                fig, ax = _spashiny_globals.plt.subplots(figsize=(8, 6))
                ax.hist(
                    _spashiny_ctx.pd.to_numeric(df["mse"], errors="coerce").dropna(),
                    bins=60,
                    alpha=0.8,
                )
                ax.set_xlabel("Per-spot MSE")
                ax.set_ylabel("Spot Count")
                ax.set_title("Reconstruction Error Distribution")
                ax.grid(True, alpha=0.3)
                _spashiny_globals.plt.tight_layout()
                return fig
        adata_obj, should_close = _spashiny_ctx.get_vhit_result_for_display(adata_obj)
        try:
            if should_close or getattr(adata_obj, "isbacked", False):
                return _spashiny_ctx.make_empty_plot(
                    "Worker reconstruction diagnostics were not saved. The large backed matrix will not be loaded into the Web process.",
                    "Reconstruction Error",
                )
            if adata_obj is None or "reconstruction" not in adata_obj.layers:
                message = (
                    diag.get("message") or "Reconstruction diagnostics were not saved for this job."
                )
                return _spashiny_ctx.make_empty_plot(message, "Reconstruction Error")
            X0 = (
                adata_obj.layers["normalized_for_cvae"]
                if "normalized_for_cvae" in adata_obj.layers
                else adata_obj.X
            )
            X1 = adata_obj.layers["reconstruction"]
            X0 = X0.toarray() if hasattr(X0, "toarray") else _spashiny_globals.np.asarray(X0)
            X1 = X1.toarray() if hasattr(X1, "toarray") else _spashiny_globals.np.asarray(X1)
            err = _spashiny_globals.np.mean((X0 - X1) ** 2, axis=1)
            fig, ax = _spashiny_globals.plt.subplots(figsize=(8, 6))
            ax.hist(err, bins=60, alpha=0.8)
            ax.set_xlabel("Per-spot MSE")
            ax.set_ylabel("Spot Count")
            ax.set_title("Reconstruction Error Distribution")
            ax.grid(True, alpha=0.3)
            _spashiny_globals.plt.tight_layout()
            return fig
        finally:
            _spashiny_globals.close_display_h5ad(adata_obj, should_close)

    _spashiny_ctx.make_vhit_reconstruction_error_figure = make_vhit_reconstruction_error_figure

    def make_vhit_cluster_analysis_figure(adata_obj=None):
        adata_obj, should_close = _spashiny_ctx.get_vhit_result_for_display(adata_obj)
        try:
            if adata_obj is None or "VAE_clusters" not in adata_obj.obs.columns:
                return _spashiny_ctx.make_empty_plot(
                    "Cluster analysis will be shown after ConditionalVAE training.",
                    "Cluster Analysis",
                )
            counts = adata_obj.obs["VAE_clusters"].astype(str).value_counts().sort_index()
            fig, ax = _spashiny_globals.plt.subplots(figsize=(8, 6))
            counts.plot(kind="bar", ax=ax)
            ax.set_xlabel("VAE Cluster")
            ax.set_ylabel("Spot Count")
            ax.set_title("VAE Cluster Size")
            _spashiny_globals.plt.xticks(rotation=45, ha="right")
            _spashiny_globals.plt.tight_layout()
            return fig
        finally:
            _spashiny_globals.close_display_h5ad(adata_obj, should_close)

    _spashiny_ctx.make_vhit_cluster_analysis_figure = make_vhit_cluster_analysis_figure

    @_spashiny_ctx.render.ui
    def vhit_resource_mode_details():
        return _spashiny_ctx.ui.div()

    _spashiny_ctx.vhit_resource_mode_details = vhit_resource_mode_details

    @_spashiny_ctx.render.ui
    def training_progress():
        logs = _spashiny_ctx.vhit_training_log.get()
        state = _spashiny_ctx.vhit_training_state.get()
        cloud_progress = _spashiny_ctx._cloud_training_progress_card(
            _spashiny_ctx.vhit_cvae_summary.get(),
            title="Multi-sample ConditionalVAE",
            read_only_db=True,
        )
        if not logs:
            return _spashiny_ctx.ui.div(
                cloud_progress if cloud_progress is not None else _spashiny_ctx.ui.div(),
                _spashiny_ctx.ui.h4("Waiting"),
                _spashiny_ctx.ui.p(
                    "Run Normalization and QC first, then click Run ConditionalVAE Training."
                ),
            )
        return _spashiny_ctx.ui.div(
            cloud_progress if cloud_progress is not None else _spashiny_ctx.ui.div(),
            _spashiny_ctx.ui.h4(state),
            _spashiny_ctx.ui.tags.ul(*[_spashiny_ctx.ui.tags.li(x) for x in logs[-6:]]),
        )

    _spashiny_ctx.training_progress = training_progress

    @_spashiny_ctx.output
    @_spashiny_ctx.render.text
    def vhit_training_status():
        return _spashiny_ctx.vhit_training_state.get()

    _spashiny_ctx.vhit_training_status = vhit_training_status

    @_spashiny_ctx.reactive.Effect
    def _restore_vhit_prepare_results():
        for summary_value, meta_value, path_value, label, stage in (
            (
                _spashiny_ctx.vhit_merge_summary,
                _spashiny_ctx.vhit_merge_metadata,
                _spashiny_ctx.vhit_merge_result_path,
                "merge",
                "merge",
            ),
            (
                _spashiny_ctx.vhit_qc_summary,
                _spashiny_ctx.vhit_qc_metadata,
                _spashiny_ctx.vhit_qc_result_path,
                "normalization and QC",
                "qc",
            ),
        ):
            summary = summary_value.get() or {}
            if _spashiny_ctx.vhit_input_source_mode.get() == "USER_UPLOAD" and (
                not summary.get("cloud_job_id")
            ):
                continue
            metadata, result_path, status, _job = _spashiny_ctx._cloud_prepare_result_state(
                summary,
                workflow_name="vhit_multi_sample_integration",
                stage=stage,
                read_only_db=True,
            )
            if not str(summary.get("cloud_job_id") or "") and _job is not None:
                summary = {
                    "cloud_job_id": str(_job.job_id),
                    "status": str(getattr(_job, "status", "") or ""),
                    "stage": stage,
                }
                summary_value.set(summary)
            from cloud.models import ACTIVE_JOB_STATUSES, TERMINAL_STATUSES

            if status in ACTIVE_JOB_STATUSES:
                _spashiny_ctx.reactive.invalidate_later(2)
            if (
                _job is not None
                and status in TERMINAL_STATUSES
                and (str(summary.get("status") or "").upper() != status)
            ):
                summary = dict(summary)
                summary["cloud_job_id"] = str(_job.job_id)
                summary["status"] = status
                summary["stage"] = stage
                summary_value.set(summary)
            if metadata and meta_value.get() != metadata:
                meta_value.set(metadata)
                path_value.set(result_path)
                if stage == "merge":
                    counts = metadata.get("sample_counts") or {}
                    if counts and (not _spashiny_ctx.sample_names_reactive.get()):
                        _spashiny_ctx.sample_names_reactive.set([str(name) for name in counts])
                _spashiny_ctx.add_log(f"Worker {label} result restored from persistent storage.")
            elif result_path and path_value.get() != result_path:
                path_value.set(result_path)
            _spashiny_ctx._sync_multisample_prepare_modal(
                summary,
                title=f"Multi-sample {label}",
                workflow_name="vhit_multi_sample_integration",
                read_only_db=True,
            )

    _spashiny_ctx._restore_vhit_prepare_results = _restore_vhit_prepare_results

    @_spashiny_ctx.reactive.Effect
    def _restore_vhit_cloud_result():
        summary = _spashiny_ctx.vhit_cvae_summary.get() or {}
        if _spashiny_ctx.vhit_input_source_mode.get() == "USER_UPLOAD" and (
            not summary.get("cloud_job_id")
        ):
            return
        result_path, status, _job = _spashiny_ctx._cloud_integration_result_state(
            summary, workflow_name="vhit_multi_sample_integration", read_only_db=True
        )
        if _job is not None:
            restored = dict(summary, cloud_job_id=str(_job.job_id), status=status)
            if result_path:
                metadata, losses = _spashiny_globals.read_worker_training_metadata(result_path)
                restored.update(metadata)
                if losses and _spashiny_ctx.vhit_loss_dict.get() != losses:
                    _spashiny_ctx.vhit_loss_dict.set(losses)
            if restored != summary:
                _spashiny_ctx.vhit_cvae_summary.set(restored)
                summary = restored
        from cloud.models import ACTIVE_JOB_STATUSES

        if status in ACTIVE_JOB_STATUSES:
            _spashiny_ctx.reactive.invalidate_later(2)
        if result_path and _spashiny_ctx.vhit_cvae_result_path.get() != result_path:
            _spashiny_ctx.vhit_cvae_result_path.set(result_path)
            _spashiny_ctx.vhit_training_state.set("Worker result restored from persistent storage.")
        _spashiny_ctx._sync_cloud_postprocess_modal(
            summary,
            title="Multi-sample ConditionalVAE post-processing",
            workflow_name="vhit_multi_sample_integration",
            read_only_db=True,
        )

    _spashiny_ctx._restore_vhit_cloud_result = _restore_vhit_cloud_result

    @_spashiny_ctx.render.text
    def training_epochs():
        loss_dict = _spashiny_ctx.vhit_loss_dict.get()
        if not loss_dict:
            return "N/A"
        max_len = 0
        for values in loss_dict.values():
            try:
                max_len = max(max_len, len(values))
            except Exception:
                pass
        summary = _spashiny_ctx.vhit_cvae_summary.get()
        if isinstance(summary, dict):
            cfg = summary.get("resolved_config", {})
            total = cfg.get("max_epoch")
            if total is not None:
                return f"{max_len} / {total}"
        total = _spashiny_globals.tutorial_training_defaults(_spashiny_globals.smt)["max_epoch"]
        return f"{max_len} / {int(total)}" if total is not None else f"{max_len}"

    _spashiny_ctx.training_epochs = training_epochs

    @_spashiny_ctx.render.text
    def final_loss():
        loss_dict = _spashiny_ctx.vhit_loss_dict.get()
        if not loss_dict:
            return "N/A"
        preferred_keys = [
            "epoch_total_loss_list",
            "total_loss",
            "loss",
            "elbo",
            "reconst_loss",
            "reconstruction_loss",
            "kl_loss",
        ]
        for key in preferred_keys:
            if key in loss_dict:
                try:
                    values = loss_dict[key]
                    if len(values) > 0:
                        return f"{float(values[-1]):.4f}"
                except Exception:
                    pass
        for values in loss_dict.values():
            try:
                if len(values) > 0:
                    return f"{float(values[-1]):.4f}"
            except Exception:
                pass
        return "N/A"

    _spashiny_ctx.final_loss = final_loss

    @_spashiny_ctx.render.ui
    def training_logs_display():
        logs = _spashiny_ctx.vhit_training_log.get()
        if not logs:
            return _spashiny_ctx.ui.p("No training logs yet.")
        return _spashiny_ctx.ui.div(*[_spashiny_ctx.ui.div(x) for x in logs[-40:]])

    _spashiny_ctx.training_logs_display = training_logs_display

    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("loss_curves_plot")
    def loss_curves_plot():
        return _spashiny_ctx.make_vhit_loss_curves_figure()

    _spashiny_ctx.loss_curves_plot = loss_curves_plot

    @_spashiny_ctx.render.table
    def loss_statistics_table():
        return _spashiny_ctx.build_vhit_loss_statistics_dataframe()

    _spashiny_ctx.loss_statistics_table = loss_statistics_table

    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("umap_by_sample_plot")
    def umap_by_sample_plot():
        return _spashiny_ctx.make_vhit_umap_sample_figure()

    _spashiny_ctx.umap_by_sample_plot = umap_by_sample_plot

    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("umap_by_cluster_plot")
    def umap_by_cluster_plot():
        return _spashiny_ctx.make_vhit_umap_cluster_figure()

    _spashiny_ctx.umap_by_cluster_plot = umap_by_cluster_plot

    @_spashiny_ctx.render.ui
    def vhit_latent10_cluster_display():
        return _spashiny_ctx._cloud_worker_plot_ui(
            _spashiny_ctx.vhit_cvae_summary.get(),
            workflow_name="vhit_multi_sample_integration",
            rel_path="glob:figures/vae_clusters_latent*.png",
            fallback_output="umap_by_cluster_plot",
            alt="VAE clusters from the trained latent embedding",
        )

    _spashiny_ctx.vhit_latent10_cluster_display = vhit_latent10_cluster_display

    @_spashiny_ctx.render.table
    def latent_embedding_table():
        return _spashiny_ctx.build_vhit_latent_embedding_dataframe()

    _spashiny_ctx.latent_embedding_table = latent_embedding_table

    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("modality_contribution_plot")
    def modality_contribution_plot():
        return _spashiny_ctx.make_vhit_modality_contribution_figure()

    _spashiny_ctx.modality_contribution_plot = modality_contribution_plot

    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("reconstruction_quality_plot")
    def reconstruction_quality_plot():
        return _spashiny_ctx.make_vhit_reconstruction_quality_figure()

    _spashiny_ctx.reconstruction_quality_plot = reconstruction_quality_plot

    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("reconstruction_error_plot")
    def reconstruction_error_plot():
        return _spashiny_ctx.make_vhit_reconstruction_error_figure()

    _spashiny_ctx.reconstruction_error_plot = reconstruction_error_plot

    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("cluster_analysis_plot")
    def cluster_analysis_plot():
        return _spashiny_ctx.make_vhit_cluster_analysis_figure()

    _spashiny_ctx.cluster_analysis_plot = cluster_analysis_plot

    @_spashiny_ctx.render.table
    def cluster_statistics_table():
        return _spashiny_ctx.build_vhit_cluster_statistics_dataframe()

    _spashiny_ctx.cluster_statistics_table = cluster_statistics_table

    @_spashiny_ctx.render.download(filename=lambda: "vhit_cvae_report.pdf")
    def download_vhit_cvae_report_pdf():
        data, should_close = _spashiny_ctx.get_vhit_result_for_display()
        if data is None and (not _spashiny_ctx.vhit_loss_dict.get()):
            _spashiny_ctx.notify(
                "No VHIT ConditionalVAE result is available for PDF export.", type_="warning"
            )
            return
        fd, pdf_path = _spashiny_ctx.tempfile.mkstemp(suffix=".pdf")
        _spashiny_globals.os.close(fd)
        try:
            figs = [
                _spashiny_ctx.make_vhit_loss_curves_figure(),
                _spashiny_ctx.make_vhit_umap_sample_figure(data),
                _spashiny_ctx.make_vhit_umap_cluster_figure(data),
                _spashiny_ctx.make_vhit_modality_contribution_figure(data),
                _spashiny_ctx.make_vhit_reconstruction_quality_figure(data),
                _spashiny_ctx.make_vhit_reconstruction_error_figure(data),
                _spashiny_ctx.make_vhit_cluster_analysis_figure(data),
            ]
            _spashiny_ctx.write_figs_to_pdf(figs, pdf_path)
            with open(pdf_path, "rb") as f:
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    yield chunk
        finally:
            _spashiny_globals.close_display_h5ad(data, should_close)
            if _spashiny_globals.os.path.exists(pdf_path):
                _spashiny_globals.os.remove(pdf_path)

    _spashiny_ctx.download_vhit_cvae_report_pdf = download_vhit_cvae_report_pdf


_STEPS = (_install_0,)


def server(_spashiny_ctx, step=0):
    return _STEPS[step](_spashiny_ctx)
