# Extracted from /app/app/ST-SM.py. Feature: st_qc; ordered phases preserve original initialization.
from spashiny._shared import runtime_globals as _spashiny_globals


def _install_0(_spashiny_ctx):
    import scanpy as sc

    _spashiny_globals.sc = sc
    import spatialmeta as smt

    _spashiny_globals.smt = smt
    import matplotlib.pyplot as plt

    _spashiny_globals.plt = plt
    import seaborn as sns

    _spashiny_ctx.sns = sns
    from pathlib import Path

    _spashiny_ctx.Path = Path
    _spashiny_ctx.st_qc_log = _spashiny_ctx.reactive.Value("")
    _spashiny_ctx.adata_ST = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.adata_ST_qc_base = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.st_qc_input_reference = _spashiny_ctx.reactive.Value(None)

    @_spashiny_ctx.output
    @_spashiny_ctx.render.text
    def st_qc_status():
        return _spashiny_ctx.st_qc_log.get()

    _spashiny_ctx.st_qc_status = st_qc_status

    @_spashiny_ctx.output
    @_spashiny_ctx.render.text
    def st_console_output():
        return _spashiny_ctx.st_qc_log.get()

    _spashiny_ctx.st_console_output = st_console_output

    @_spashiny_ctx.output
    @_spashiny_ctx.render.ui
    def st_qc_current_input():
        """Show the selected ST QC source without revealing server paths."""
        reference = _spashiny_ctx.st_qc_input_reference.get()
        if not isinstance(reference, dict):
            label = "Current input: none selected."
        elif str(reference.get("source") or "") == "example":
            label = "Current input: Example — Y7_T ST H5AD"
        else:
            label = "Current input: Uploaded file — " + str(
                reference.get("filename") or "uploaded ST H5AD"
            )
        return _spashiny_ctx.ui.tags.div(
            label, class_="cloud-muted", style="font-size: 12px; margin-top: 8px; font-weight: 600;"
        )

    _spashiny_ctx.st_qc_current_input = st_qc_current_input

    def append_st_qc_log(message):
        text = _spashiny_ctx.st_qc_log.get()
        if text and (not text.endswith("\n")):
            text += "\n"
        _spashiny_ctx.st_qc_log.set(text + str(message).rstrip("\n") + "\n")

    _spashiny_ctx.append_st_qc_log = append_st_qc_log

    def apply_st_qc_thresholds(reason="Thresholds applied"):
        base = _spashiny_ctx.adata_ST_qc_base.get()
        if base is None:
            return
        min_counts = _spashiny_globals.read_numeric_input(
            _spashiny_ctx.input.st_qc_min_counts, _spashiny_globals.DEFAULT_ST_QC_MIN_COUNTS, int, 0
        )
        min_genes = _spashiny_globals.read_numeric_input(
            _spashiny_ctx.input.st_qc_min_genes, _spashiny_globals.DEFAULT_ST_QC_MIN_GENES, int, 0
        )
        filtered = base.copy()
        before_shape = filtered.shape
        if min_counts > 0:
            _spashiny_globals.sc.pp.filter_cells(filtered, min_counts=min_counts)
        if min_genes > 0:
            _spashiny_globals.sc.pp.filter_cells(filtered, min_genes=min_genes)
        _spashiny_ctx.adata_ST.set(filtered)
        _spashiny_ctx.append_st_qc_log(
            f"{reason}: shape {before_shape} -> {filtered.shape} (min_counts={min_counts}, min_genes={min_genes})."
        )

    _spashiny_ctx.apply_st_qc_thresholds = apply_st_qc_thresholds

    def run_st_qc_from_path(filepath, source_label="uploaded ST data", input_provenance=None):
        filepath = _spashiny_ctx.Path(filepath)
        if not filepath.exists():
            _spashiny_ctx.st_qc_log.set("ST QC input file was not found.")
            return
        _spashiny_ctx.ui.modal_show(
            _spashiny_ctx.ui.modal(
                _spashiny_ctx.ui.p("Running QC, please wait..."),
                title="Processing",
                easy_close=False,
                footer=None,
            )
        )
        _spashiny_ctx.st_qc_log.set(f"Starting ST data loading from {source_label}...\n")
        provenance = dict(input_provenance or {})
        source_mode = str(provenance.get("input_source_mode") or "").strip().upper()
        filename = str(provenance.get("filename") or "").strip()
        if source_mode:
            _spashiny_ctx.st_qc_log.set(
                _spashiny_ctx.st_qc_log.get() + f"Input source: {source_mode}\n"
            )
        if filename:
            _spashiny_ctx.st_qc_log.set(_spashiny_ctx.st_qc_log.get() + f"Input file: {filename}\n")
        try:
            adata = _spashiny_globals.compact_adata_X(_spashiny_globals.sc.read_h5ad(filepath))
            _spashiny_ctx.st_qc_log.set(
                _spashiny_ctx.st_qc_log.get() + f"Data loaded successfully: {adata}\n"
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
            species = _spashiny_ctx.input.st_species()
            mt_prefix = "MT-" if species == "Human" else "mt-"
            adata.var["mt"] = adata.var_names.str.startswith(mt_prefix)
            _spashiny_globals.sc.pp.calculate_qc_metrics(adata, qc_vars=["mt"], inplace=True)
            _spashiny_ctx.st_qc_log.set(
                _spashiny_ctx.st_qc_log.get()
                + f" Mitochondrial QC metrics calculated using prefix '{mt_prefix}' based on species ({species}).\n"
            )
            _spashiny_ctx.st_qc_log.set(
                _spashiny_ctx.st_qc_log.get() + " Removing HSP/MT/RPL/DNAJ-related genes...\n"
            )
            adata = _spashiny_globals.smt.pp.removeHSP_MT_RPL_DNAJ(adata)
            _spashiny_ctx.st_qc_log.set(
                _spashiny_ctx.st_qc_log.get() + " QC data preparation completed.\n"
            )
            _spashiny_ctx.adata_ST_qc_base.set(adata)
            _spashiny_ctx.apply_st_qc_thresholds("Initial ST QC thresholds")
        except Exception as e:
            _spashiny_ctx.st_qc_log.set(_spashiny_ctx.st_qc_log.get() + f"Error: {e}\n")
        finally:
            _spashiny_ctx.ui.modal_remove()

    _spashiny_ctx.run_st_qc_from_path = run_st_qc_from_path

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.run_st_qc)
    def _run_uploaded_st_qc():
        if _spashiny_globals.SPASHINY_WEB_PLATFORM:
            try:
                resolved = _spashiny_ctx._resolve_st_qc_interactive_input(
                    _spashiny_ctx.st_qc_input_reference.get()
                )
            except Exception as exc:
                _spashiny_ctx.st_qc_log.set(
                    f"Please upload an .h5ad file first or click Load Example ST QC. ({exc})"
                )
                return
            label = (
                "uploaded ST h5ad"
                if resolved.get("source") == "upload"
                else "built-in Y7_T ST QC example"
            )
            _spashiny_ctx.run_st_qc_from_path(
                resolved["local_path"], label, input_provenance=resolved
            )
            return
        fileinfo = _spashiny_ctx.input.st_qc_file()
        if not fileinfo:
            _spashiny_ctx.st_qc_log.set(
                " Please upload an .h5ad file first or click Load Example ST QC."
            )
            return
        _spashiny_ctx.run_st_qc_from_path(fileinfo[0]["datapath"], "uploaded ST h5ad")

    _spashiny_ctx._run_uploaded_st_qc = _run_uploaded_st_qc

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(
        _spashiny_ctx.input.st_qc_min_counts, _spashiny_ctx.input.st_qc_min_genes
    )
    def _refilter_st_qc_when_thresholds_change():
        if _spashiny_ctx.adata_ST_qc_base.get() is None:
            return
        _spashiny_ctx.apply_st_qc_thresholds("Updated ST QC thresholds")

    _spashiny_ctx._refilter_st_qc_when_thresholds_change = _refilter_st_qc_when_thresholds_change

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.load_example_st_qc)
    def _load_example_st_qc():
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
                    action_id="y7-st-qc-example",
                    page_name="st_qc",
                )
                if not bool(binding.get("ready")):
                    raise RuntimeError(
                        "Example inputs are not ready: "
                        + ", ".join(binding.get("missing_roles") or [])
                    )
                _spashiny_ctx._select_qc_input(
                    "ST", {"source": "example", "action_id": "y7-st-qc-example"}
                )
            except Exception as e:
                _spashiny_ctx.st_qc_log.set(f"Failed to load ST QC example: {e}\n")
                _spashiny_ctx.ui.notification_show(
                    f"Failed to load ST QC example: {e}", type="error", duration=8
                )
            return
        try:
            example_path = _spashiny_globals.get_example_st_qc_h5ad_path()
            _spashiny_ctx.run_st_qc_from_path(example_path, "built-in Y7_T ST QC example")
        except Exception as e:
            _spashiny_ctx.st_qc_log.set(f"Failed to load ST QC example: {e}\n")
            _spashiny_ctx.ui.notification_show(
                f"Failed to load ST QC example: {e}", type="error", duration=8
            )

    _spashiny_ctx._load_example_st_qc = _load_example_st_qc

    def _resolve_st_qc_interactive_input(reference):
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
                workflow_name="st_quality_control",
            )
        if source == "example":
            return InputResolver().resolve_interactive_local_input(
                session_id=session_record.session_id,
                analysis_session_id=analysis_session_id,
                action_id="y7-st-qc-example",
                input_role="st_qc_input_h5ad",
                workflow_name="st_quality_control",
            )
        raise RuntimeError("The selected ST QC input source is invalid.")

    _spashiny_ctx._resolve_st_qc_interactive_input = _resolve_st_qc_interactive_input

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.st_qc_canonical_upload)
    def _track_st_qc_canonical_upload():
        if not _spashiny_globals.SPASHINY_WEB_PLATFORM:
            return
        try:
            payload = _spashiny_ctx.input.st_qc_canonical_upload() or {}
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            return
        status = str(payload.get("status") or "").upper()
        filename = str(payload.get("filename") or "uploaded ST h5ad")
        if status == "READY":
            upload_id = str(payload.get("upload_id") or "").strip()
            if not upload_id:
                _spashiny_ctx._select_qc_input("ST", None)
                _spashiny_ctx.append_st_qc_log(
                    "ST QC upload failed: completion returned no upload reference."
                )
                return
            try:
                resolved = _spashiny_ctx._resolve_st_qc_interactive_input(
                    {"source": "upload", "upload_id": upload_id}
                )
            except Exception as exc:
                _spashiny_ctx._select_qc_input("ST", None)
                _spashiny_ctx.append_st_qc_log(f"ST QC upload is not available to this tab: {exc}")
                return
            _spashiny_ctx._select_qc_input(
                "ST", {"source": "upload", "upload_id": upload_id, "filename": resolved["filename"]}
            )
            _spashiny_ctx.append_st_qc_log(
                f"ST QC upload ready: {resolved['filename']}. Click Run Pipeline to continue."
            )
        elif status == "FAILED":
            _spashiny_ctx._select_qc_input("ST", None)
            _spashiny_ctx.append_st_qc_log(
                _spashiny_globals._upload_failure_text(payload, filename, "ST QC upload")
            )

    _spashiny_ctx._track_st_qc_canonical_upload = _track_st_qc_canonical_upload

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(
        _spashiny_ctx.input.cloud_example_action_activated, ignore_none=True
    )
    def _select_st_qc_example_from_cloud_action():
        if not _spashiny_globals.SPASHINY_WEB_PLATFORM:
            return
        try:
            payload = _spashiny_ctx.input.cloud_example_action_activated() or {}
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            return
        if str(payload.get("action_id") or "") != "y7-st-qc-example" or not bool(
            payload.get("ready")
        ):
            return
        if str(payload.get("analysis_session_id") or "") != str(
            _spashiny_ctx._cloud_analysis_session_id() or ""
        ):
            return
        _spashiny_ctx._select_qc_input("ST", {"source": "example", "action_id": "y7-st-qc-example"})
        _spashiny_ctx.append_st_qc_log(
            "Current input switched to Example — Y7_T ST H5AD. Click Run Pipeline to continue."
        )

    _spashiny_ctx._select_st_qc_example_from_cloud_action = _select_st_qc_example_from_cloud_action

    @_spashiny_ctx.output
    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("st_qc_violin")
    def st_qc_violin():
        adata = _spashiny_ctx.adata_ST.get()
        if adata is None:
            return None
        _spashiny_globals.sc.pl.violin(
            adata, ["n_genes_by_counts", "total_counts"], jitter=0.4, multi_panel=True, show=False
        )

    _spashiny_ctx.st_qc_violin = st_qc_violin

    @_spashiny_ctx.output
    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("st_qc_hist")
    def st_qc_hist():
        adata = _spashiny_ctx.adata_ST.get()
        if adata is None:
            return None
        fig, axs = _spashiny_globals.plt.subplots(1, 2, figsize=(8, 4))
        _spashiny_ctx.sns.histplot(adata.obs["total_counts"], kde=False, ax=axs[0])
        axs[0].set_title("Total Counts")
        _spashiny_ctx.sns.histplot(adata.obs["n_genes_by_counts"], kde=False, ax=axs[1])
        axs[1].set_title("n Genes by Counts")
        _spashiny_globals.plt.tight_layout()
        return fig

    _spashiny_ctx.st_qc_hist = st_qc_hist

    @_spashiny_ctx.output
    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("st_qc_spatial")
    def st_qc_spatial():
        adata = _spashiny_ctx.adata_ST.get()
        if adata is None:
            return None
        _spashiny_globals.sc.pl.spatial(
            adata,
            img_key="hires",
            color=["n_genes_by_counts", "total_counts"],
            edges_width=0,
            color_map="vlag",
            size=1.5,
            show=False,
        )

    _spashiny_ctx.st_qc_spatial = st_qc_spatial

    @_spashiny_ctx.render.download(filename=lambda: "ST_QC_report.pdf")
    def download_st_qc_pdf():
        from cloud.figure_export import EditablePdfPages as PdfPages
        import matplotlib.pyplot as plt
        import seaborn as sns
        import scanpy as sc
        import tempfile, os

        adata = _spashiny_ctx.adata_ST.get()
        if adata is None:
            return None
        fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
        try:
            with PdfPages(tmp_path) as pdf:
                fig, axs = plt.subplots(1, 2, figsize=(8, 5))
                sc.pl.violin(adata, ["n_genes_by_counts"], jitter=0.4, ax=axs[0], show=False)
                sc.pl.violin(adata, ["total_counts"], jitter=0.4, ax=axs[1], show=False)
                plt.tight_layout()
                pdf.savefig(fig)
                plt.close(fig)
                fig, axs = plt.subplots(1, 2, figsize=(8, 5))
                sns.histplot(adata.obs["total_counts"], ax=axs[0], color="#007aff")
                axs[0].set_title("Total Counts")
                sns.histplot(adata.obs["n_genes_by_counts"], ax=axs[1], color="#007aff")
                axs[1].set_title("n Genes by Counts")
                plt.tight_layout()
                pdf.savefig(fig)
                plt.close(fig)
                fig, axs = plt.subplots(1, 2, figsize=(8, 4))
                sc.pl.spatial(
                    adata,
                    img_key="hires",
                    color="n_genes_by_counts",
                    color_map="vlag",
                    size=1.5,
                    ax=axs[0],
                    show=False,
                )
                sc.pl.spatial(
                    adata,
                    img_key="hires",
                    color="total_counts",
                    color_map="vlag",
                    size=1.5,
                    ax=axs[1],
                    show=False,
                )
                plt.tight_layout()
                pdf.savefig(fig)
                plt.close(fig)
            with open(tmp_path, "rb") as f:
                yield from f
        finally:
            os.close(fd)
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    _spashiny_ctx.download_st_qc_pdf = download_st_qc_pdf

    @_spashiny_ctx.render.download(
        filename=lambda: f"{_spashiny_ctx.input.st_qc_filename() or 'adata_ST_qc'}.h5ad"
    )
    def download_st_qc():
        """ST QC Download"""
        adata = _spashiny_ctx.adata_ST.get()
        if adata is None:
            raise RuntimeError(
                "Run ST QC for the current input before downloading its H5AD result."
            )
        with _spashiny_ctx.tempfile.TemporaryDirectory(prefix="st-qc-export-") as directory:
            path = _spashiny_ctx.Path(directory) / "adata_ST_qc.h5ad"
            adata.write_h5ad(path)
            yield from _spashiny_ctx.stream_file(path)

    _spashiny_ctx.download_st_qc = download_st_qc

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.save_st_qc)
    def trigger_st_qc_download():
        """Click save button -> automatically trigger download"""
        _spashiny_ctx.ui.notification_show(" Preparing ST QC data download...", type="message")
        _spashiny_ctx.session.send_custom_message("trigger_download", {"id": "download_st_qc"})

    _spashiny_ctx.trigger_st_qc_download = trigger_st_qc_download


_STEPS = (_install_0,)


def server(_spashiny_ctx, step=0):
    return _STEPS[step](_spashiny_ctx)
