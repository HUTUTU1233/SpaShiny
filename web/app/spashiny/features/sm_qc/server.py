# Extracted from /app/app/ST-SM.py. Feature: sm_qc; ordered phases preserve original initialization.
from spashiny._shared import runtime_globals as _spashiny_globals


def _install_0(_spashiny_ctx):

    @_spashiny_ctx.output
    @_spashiny_ctx.render.text
    def qc_status():
        return _spashiny_ctx.qc_log.get()

    _spashiny_ctx.qc_status = qc_status

    @_spashiny_ctx.output
    @_spashiny_ctx.render.text
    def sm_qc_console_output():
        return _spashiny_ctx.qc_log.get()

    _spashiny_ctx.sm_qc_console_output = sm_qc_console_output

    @_spashiny_ctx.output
    @_spashiny_ctx.render.ui
    def sm_qc_current_input():
        """Show the one active SM QC source without exposing internal paths."""
        reference = _spashiny_ctx.sm_qc_input_reference.get()
        if not isinstance(reference, dict):
            return _spashiny_ctx.ui.tags.div(
                "Current input: none selected.",
                class_="cloud-muted",
                style="font-size: 12px; margin-top: 8px;",
            )
        if str(reference.get("source") or "") == "example":
            label = "Current input: Example — Y7_T SM H5AD"
        else:
            filename = str(reference.get("filename") or "uploaded SM H5AD")
            label = f"Current input: Uploaded file — {filename}"
        return _spashiny_ctx.ui.tags.div(
            label, class_="cloud-muted", style="font-size: 12px; margin-top: 8px; font-weight: 600;"
        )

    _spashiny_ctx.sm_qc_current_input = sm_qc_current_input

    def append_sm_qc_log(message):
        text = _spashiny_ctx.qc_log.get()
        if text and (not text.endswith("\n")):
            text += "\n"
        _spashiny_ctx.qc_log.set(text + str(message).rstrip("\n") + "\n")

    _spashiny_ctx.append_sm_qc_log = append_sm_qc_log

    def apply_sm_qc_threshold(reason="Threshold applied"):
        base = _spashiny_ctx.adata_SM_qc_base.get()
        if base is None:
            return
        min_total_intensity = _spashiny_globals.read_numeric_input(
            _spashiny_ctx.input.sm_qc_min_total_intensity,
            _spashiny_globals.DEFAULT_SM_QC_MIN_TOTAL_INTENSITY,
            float,
            0.0,
        )
        if "total_intensity" not in base.obs.columns:
            _spashiny_ctx.adata_SM.set(base)
            _spashiny_ctx.append_sm_qc_log(
                "SM QC threshold was skipped because total_intensity is missing."
            )
            return
        before_shape = base.shape
        if min_total_intensity > 0:
            intensity = _spashiny_ctx.pd.to_numeric(base.obs["total_intensity"], errors="coerce")
            keep_mask = intensity >= min_total_intensity
            filtered = _spashiny_globals.compact_adata_X(
                base[keep_mask.fillna(False).to_numpy()].copy()
            )
            detail = f"{reason}: min_total_intensity={min_total_intensity:.2e}; shape {before_shape} -> {filtered.shape}."
        else:
            filtered = base.copy()
            detail = (
                f"{reason}: total-intensity filtering disabled; shape remains {filtered.shape}."
            )
        _spashiny_ctx.adata_SM.set(filtered)
        _spashiny_ctx.append_sm_qc_log(detail)

    _spashiny_ctx.apply_sm_qc_threshold = apply_sm_qc_threshold

    def run_sm_qc_from_path(filepath, source_label="SM h5ad", input_provenance=None):
        filepath = _spashiny_ctx.Path(filepath)
        if not filepath.exists():
            _spashiny_ctx.qc_log.set("SM QC input file was not found.")
            _spashiny_ctx.ui.notification_show(
                "SM QC input file was not found.", type="error", duration=8
            )
            return
        _spashiny_ctx.ui.modal_show(
            _spashiny_ctx.ui.modal(
                _spashiny_ctx.ui.div(
                    _spashiny_ctx.ui.h4("Running QC Calculation"),
                    _spashiny_ctx.ui.p(
                        "Reading data and calculating quality control metrics, please wait..."
                    ),
                ),
                easy_close=False,
                footer=None,
            )
        )
        try:
            _spashiny_ctx.qc_log.set(f"Reading data from {source_label}...\n")
            provenance = dict(input_provenance or {})
            source_mode = str(provenance.get("input_source_mode") or "").strip().upper()
            if source_mode:
                _spashiny_ctx.qc_log.set(
                    _spashiny_ctx.qc_log.get() + f"Input source: {source_mode}\n"
                )
            filename = str(provenance.get("filename") or "").strip()
            if filename:
                _spashiny_ctx.qc_log.set(_spashiny_ctx.qc_log.get() + f"Input file: {filename}\n")
            adata = _spashiny_globals.compact_adata_X(_spashiny_globals.sc.read_h5ad(filepath))
            _spashiny_ctx.qc_log.set(
                _spashiny_ctx.qc_log.get() + f"Data loaded successfully: {adata}\n"
            )
            adata.uns["spashiny_input_provenance"] = {
                "input_source_mode": source_mode or "UNKNOWN",
                "input_reference_id": str(
                    provenance.get("upload_id") or provenance.get("action_id") or ""
                ),
                "input_filename": filename or filepath.name,
                "input_sha256": str(provenance.get("sha256") or ""),
                "input_size_bytes": int(provenance.get("size_bytes") or 0),
                "input_shape": [int(adata.n_obs), int(adata.n_vars)],
                "analysis_session_id": str(_spashiny_ctx._cloud_analysis_session_id() or ""),
            }
            _spashiny_ctx.qc_log.set(
                _spashiny_ctx.qc_log.get() + "Starting QC metric calculation...\n"
            )
            _spashiny_globals.smt.pp.calculate_qc_metrics_sm(adata)
            _spashiny_ctx.adata_SM_qc_base.set(adata)
            _spashiny_ctx.apply_sm_qc_threshold("Initial SM QC threshold")
            _spashiny_ctx.qc_log.set(_spashiny_ctx.qc_log.get() + "QC calculation completed.\n")
        except Exception as e:
            _spashiny_ctx.qc_log.set(_spashiny_ctx.qc_log.get() + f"Error: {e}\n")
        finally:
            _spashiny_ctx.ui.modal_remove()
            _spashiny_globals.release_unused_memory()

    _spashiny_ctx.run_sm_qc_from_path = run_sm_qc_from_path

    def _resolve_sm_qc_interactive_input(reference):
        if not isinstance(reference, dict):
            raise RuntimeError("Please select an H5AD input or load the example first.")
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
                workflow_name="sm_quality_control",
            )
        if source == "example":
            return InputResolver().resolve_interactive_local_input(
                session_id=session_record.session_id,
                analysis_session_id=analysis_session_id,
                action_id="y7-sm-qc-example",
                input_role="sm_qc_input_h5ad",
                workflow_name="sm_quality_control",
            )
        raise RuntimeError("The selected SM QC input source is invalid.")

    _spashiny_ctx._resolve_sm_qc_interactive_input = _resolve_sm_qc_interactive_input

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.sm_qc_canonical_upload)
    def _track_sm_qc_canonical_upload():
        if not _spashiny_globals.SPASHINY_WEB_PLATFORM:
            return
        try:
            payload = _spashiny_ctx.input.sm_qc_canonical_upload() or {}
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            return
        status = str(payload.get("status") or "").upper()
        filename = str(payload.get("filename") or "uploaded SM h5ad")
        if status == "READY":
            upload_id = str(payload.get("upload_id") or "").strip()
            if not upload_id:
                _spashiny_ctx._select_qc_input("SM", None)
                _spashiny_ctx.append_sm_qc_log(
                    "SM QC upload failed: completion returned no upload reference."
                )
                return
            try:
                resolved = _spashiny_ctx._resolve_sm_qc_interactive_input(
                    {"source": "upload", "upload_id": upload_id}
                )
            except Exception as exc:
                _spashiny_ctx._select_qc_input("SM", None)
                _spashiny_ctx.append_sm_qc_log(f"SM QC upload is not available to this tab: {exc}")
                return
            _spashiny_ctx._select_qc_input(
                "SM", {"source": "upload", "upload_id": upload_id, "filename": resolved["filename"]}
            )
            _spashiny_ctx.append_sm_qc_log(
                f"SM QC upload ready: {resolved['filename']}. Click Calculate QC Metrics to continue."
            )
        elif status == "FAILED":
            _spashiny_ctx._select_qc_input("SM", None)
            _spashiny_ctx.append_sm_qc_log(
                _spashiny_globals._upload_failure_text(payload, filename, "SM QC upload")
            )

    _spashiny_ctx._track_sm_qc_canonical_upload = _track_sm_qc_canonical_upload

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.run_qc)
    def _():
        if _spashiny_globals.SPASHINY_WEB_PLATFORM:
            try:
                resolved = _spashiny_ctx._resolve_sm_qc_interactive_input(
                    _spashiny_ctx.sm_qc_input_reference.get()
                )
            except Exception as exc:
                _spashiny_ctx.qc_log.set(
                    f"Please upload an .h5ad file first or click Load Example SM QC. ({exc})"
                )
                return
            label = (
                "uploaded SM h5ad"
                if resolved.get("source") == "upload"
                else "built-in Y7_T SM QC example"
            )
            _spashiny_ctx.run_sm_qc_from_path(
                resolved["local_path"], label, input_provenance=resolved
            )
            return
        fileinfo = _spashiny_ctx.input.st_file()
        if not fileinfo:
            _spashiny_ctx.qc_log.set(
                "Please upload an .h5ad file first or click Load Example SM QC."
            )
            return
        _spashiny_ctx.run_sm_qc_from_path(fileinfo[0]["datapath"], "uploaded SM h5ad")

    _spashiny_ctx._ = _

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.sm_qc_min_total_intensity)
    def _refilter_sm_qc_when_threshold_changes():
        if _spashiny_ctx.adata_SM_qc_base.get() is None:
            return
        _spashiny_ctx.apply_sm_qc_threshold("Updated SM QC threshold")

    _spashiny_ctx._refilter_sm_qc_when_threshold_changes = _refilter_sm_qc_when_threshold_changes

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.load_example_sm_qc)
    def _load_example_sm_qc():
        if _spashiny_globals.SPASHINY_WEB_PLATFORM:
            try:
                session_record = _spashiny_ctx._cloud_session_record()
                analysis_session_id = str(_spashiny_ctx._cloud_analysis_session_id() or "").strip()
                if session_record is None or not analysis_session_id:
                    raise RuntimeError(
                        "The current tab analysis session is not ready. Please wait and try again."
                    )
                from cloud.example_action_bindings import ExampleActionBindingService

                binding = ExampleActionBindingService().activate(
                    session=session_record,
                    analysis_session_id=analysis_session_id,
                    action_id="y7-sm-qc-example",
                    page_name="sm_qc",
                )
                if not bool(binding.get("ready")):
                    raise RuntimeError(
                        "Example inputs are not ready: "
                        + ", ".join(binding.get("missing_roles") or [])
                    )
                _spashiny_ctx._select_qc_input(
                    "SM", {"source": "example", "action_id": "y7-sm-qc-example"}
                )
                resolved = _spashiny_ctx._resolve_sm_qc_interactive_input(
                    _spashiny_ctx.sm_qc_input_reference.get()
                )
                _spashiny_ctx.run_sm_qc_from_path(
                    resolved["local_path"], "built-in Y7_T SM QC example", input_provenance=resolved
                )
            except Exception as e:
                _spashiny_ctx.qc_log.set(f"Failed to load SM QC example: {e}\n")
                _spashiny_ctx.ui.notification_show(
                    f"Failed to load SM QC example: {e}", type="error", duration=8
                )
            return
        try:
            example_path = _spashiny_globals.get_example_sm_qc_h5ad_path()
            _spashiny_ctx.run_sm_qc_from_path(example_path, "built-in Y7_T SM QC example")
        except Exception as e:
            _spashiny_ctx.qc_log.set(f"Failed to load SM QC example: {e}\n")
            _spashiny_ctx.ui.notification_show(
                f"Failed to load SM QC example: {e}", type="error", duration=8
            )

    _spashiny_ctx._load_example_sm_qc = _load_example_sm_qc

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(
        _spashiny_ctx.input.cloud_example_action_activated, ignore_none=True
    )
    def _select_sm_qc_example_from_cloud_action():
        """Make generic cloud Example activation select the SM QC source explicitly.

        The generic action creates only an analysis-scoped binding.  This page
        additionally owns the user's current SM QC source selection, which must
        not silently remain on a prior upload after the Example button is used.
        """
        if not _spashiny_globals.SPASHINY_WEB_PLATFORM:
            return
        try:
            payload = _spashiny_ctx.input.cloud_example_action_activated() or {}
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            return
        if str(payload.get("action_id") or "") != "y7-sm-qc-example":
            return
        if not bool(payload.get("ready")):
            return
        if str(payload.get("analysis_session_id") or "") != str(
            _spashiny_ctx._cloud_analysis_session_id() or ""
        ):
            return
        _spashiny_ctx._select_qc_input("SM", {"source": "example", "action_id": "y7-sm-qc-example"})
        _spashiny_ctx.append_sm_qc_log(
            "Current input switched to Example — Y7_T SM H5AD. Click Calculate QC Metrics to continue."
        )

    _spashiny_ctx._select_sm_qc_example_from_cloud_action = _select_sm_qc_example_from_cloud_action

    @_spashiny_ctx.output
    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("qc_violin")
    def qc_violin():
        adata = _spashiny_ctx.adata_SM.get()
        if adata is None:
            return None
        fig, axs = _spashiny_globals.plt.subplots(1, 2, figsize=(10, 5))
        _spashiny_globals.sc.pl.violin(
            adata, ["total_intensity"], jitter=0.4, ax=axs[0], show=False
        )
        axs[0].set_title("Total Intensity")
        _spashiny_globals.sc.pl.violin(adata, ["mean_intensity"], jitter=0.4, ax=axs[1], show=False)
        axs[1].set_title("Mean Intensity")
        _spashiny_globals.plt.tight_layout()
        return fig

    _spashiny_ctx.qc_violin = qc_violin

    @_spashiny_ctx.output
    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("qc_hist")
    def qc_hist():
        adata = _spashiny_ctx.adata_SM.get()
        if adata is None:
            return None
        fig, axs = _spashiny_globals.plt.subplots(1, 2, figsize=(6, 5))
        _spashiny_ctx.sns.histplot(adata.obs["total_intensity"], kde=False, ax=axs[0])
        axs[0].set_title("Total Intensity")
        _spashiny_ctx.sns.histplot(adata.obs["mean_intensity"], kde=False, ax=axs[1])
        axs[1].set_title("Mean Intensity")
        _spashiny_globals.plt.tight_layout()
        return fig

    _spashiny_ctx.qc_hist = qc_hist

    @_spashiny_ctx.output
    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("qc_spatial")
    def qc_spatial():
        adata = _spashiny_ctx.adata_SM.get()
        if adata is None:
            return None
        cmap = _spashiny_ctx.make_colormap(["#3c096c", "#FFFFFF", "#ff6b35"])
        fig, axs = _spashiny_globals.plt.subplots(1, 2, figsize=(6, 5))
        _spashiny_globals.sc.pl.embedding(
            adata, basis="spatial", color="total_intensity", cmap=cmap, ax=axs[0], show=False
        )
        axs[0].set_title("Total Intensity")
        _spashiny_globals.sc.pl.embedding(
            adata, basis="spatial", color="mean_intensity", cmap=cmap, ax=axs[1], show=False
        )
        axs[1].set_title("Mean Intensity")
        _spashiny_globals.plt.tight_layout()
        return fig

    _spashiny_ctx.qc_spatial = qc_spatial

    @_spashiny_ctx.render.download(filename=lambda: "SM_QC_report.pdf")
    def download_qc_pdf():
        from cloud.figure_export import EditablePdfPages as PdfPages
        import matplotlib.pyplot as plt
        import tempfile, os

        adata = _spashiny_ctx.adata_SM.get()
        if adata is None:
            _spashiny_ctx.log(" No data available for export. Please run QC first!")
            return
        fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
        try:
            with PdfPages(tmp_path) as pdf:
                fig, axs = plt.subplots(1, 2, figsize=(9, 8))
                _spashiny_globals.sc.pl.violin(
                    adata, ["total_intensity"], jitter=0.4, ax=axs[0], show=False
                )
                axs[0].set_title("Total Intensity")
                _spashiny_globals.sc.pl.violin(
                    adata, ["mean_intensity"], jitter=0.4, ax=axs[1], show=False
                )
                axs[1].set_title("Mean Intensity")
                plt.tight_layout()
                pdf.savefig(fig)
                plt.close(fig)
                fig, axs = plt.subplots(1, 2, figsize=(9, 8))
                _spashiny_ctx.sns.histplot(adata.obs["total_intensity"], ax=axs[0])
                axs[0].set_title("Total Intensity")
                _spashiny_ctx.sns.histplot(adata.obs["mean_intensity"], ax=axs[1])
                axs[1].set_title("Mean Intensity")
                plt.tight_layout()
                pdf.savefig(fig)
                plt.close(fig)
                cmap = _spashiny_ctx.make_colormap(["#4d0c89", "#FFFFFF", "#eb2020"])
                fig, axs = plt.subplots(2, 1, figsize=(6, 9))
                _spashiny_globals.sc.pl.embedding(
                    adata,
                    basis="spatial",
                    color="total_intensity",
                    cmap=cmap,
                    ax=axs[0],
                    show=False,
                )
                axs[0].set_title("Total Intensity")
                _spashiny_globals.sc.pl.embedding(
                    adata, basis="spatial", color="mean_intensity", cmap=cmap, ax=axs[1], show=False
                )
                axs[1].set_title("Mean Intensity")
                plt.tight_layout()
                pdf.savefig(fig)
                plt.close(fig)
            with open(tmp_path, "rb") as f:
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    yield chunk
        finally:
            os.close(fd)
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    _spashiny_ctx.download_qc_pdf = download_qc_pdf

    @_spashiny_ctx.render.download(
        filename=lambda: f"{_spashiny_ctx.input.sm_qc_filename() or 'adata_SM_qc'}.h5ad"
    )
    def download_sm_qc():
        import tempfile, os

        adata = _spashiny_ctx.adata_SM.get()
        if adata is None:
            _spashiny_ctx.log(" No data available for export. Please run QC first!")
            return None
        if not adata.var_names.is_unique:
            adata.var_names_make_unique()
        fd, tmp_path = tempfile.mkstemp(suffix=".h5ad")
        try:
            adata.write_h5ad(tmp_path)
            with open(tmp_path, "rb") as f:
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    yield chunk
        finally:
            os.close(fd)
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    _spashiny_ctx.download_sm_qc = download_sm_qc


_STEPS = (_install_0,)


def server(_spashiny_ctx, step=0):
    return _STEPS[step](_spashiny_ctx)
