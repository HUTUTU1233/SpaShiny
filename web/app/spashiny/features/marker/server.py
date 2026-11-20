# Extracted from /app/app/ST-SM.py. Feature: marker; ordered phases preserve original initialization.
from spashiny._shared import runtime_globals as _spashiny_globals


def _install_0(_spashiny_ctx):

    def _show_downstream_action_modal(title, message):
        _spashiny_ctx.ui.modal_show(
            _spashiny_ctx.ui.modal(
                _spashiny_ctx.ui.div(
                    _spashiny_ctx.ui.h4(title, class_="mb-3"),
                    _spashiny_ctx.ui.p(message),
                    _spashiny_ctx.ui.tags.div(class_="spinner-border text-primary"),
                ),
                title="Analysis in Progress",
                easy_close=False,
                footer=None,
            )
        )

    _spashiny_ctx._show_downstream_action_modal = _show_downstream_action_modal

    def _resolve_downstream_interactive_input(reference):
        """Resolve exactly one owner+analysis scoped downstream input."""
        if not isinstance(reference, dict):
            raise RuntimeError("Please upload an H5AD or select the Y7_T downstream example first.")
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
                workflow_name="marker_feature_analysis",
            )
        if source == "example":
            return InputResolver().resolve_interactive_local_input(
                session_id=session_record.session_id,
                analysis_session_id=analysis_session_id,
                action_id="y7-downstream-example",
                input_role="joint_downstream_reference_h5ad",
                workflow_name="marker_feature_analysis",
            )
        if source == "pipeline":
            return _spashiny_globals.resolve_pipeline_result(
                session_record.session_id, analysis_session_id, reference.get("job_id")
            )
        raise RuntimeError("The selected downstream input source is invalid.")

    _spashiny_ctx._resolve_downstream_interactive_input = _resolve_downstream_interactive_input

    def _downstream_input_display(reference):
        if not isinstance(reference, dict):
            return "Current input: none selected."
        if str(reference.get("source") or "") == "upload":
            return f"Current input: User upload — {reference.get('filename') or 'H5AD'}."
        if str(reference.get("source") or "") == "pipeline":
            return "Current input: this analysis's single-sample integration result."
        return "Current input: Example — Y7_T downstream H5AD."

    _spashiny_ctx._downstream_input_display = _downstream_input_display

    @_spashiny_ctx.output
    @_spashiny_ctx.render.ui
    def downstream_current_input():
        return _spashiny_ctx.ui.tags.div(
            _spashiny_ctx._downstream_input_display(_spashiny_ctx.downstream_input_reference.get()),
            class_="cloud-muted",
            style="font-size: 12px; margin-top: 8px;",
        )

    _spashiny_ctx.downstream_current_input = downstream_current_input

    def load_downstream_h5ad(path, source_label="uploaded file"):
        path = _spashiny_ctx.Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Downstream h5ad was not found: {path}")
        adata = _spashiny_globals.compact_adata_X(_spashiny_globals.sc.read_h5ad(path))
        _spashiny_globals.preserve_downstream_labels(adata, _spashiny_globals.find_vae_cluster_key)
        _spashiny_ctx.adata_obj.set(adata)
        _spashiny_ctx.marker_res.set(None)
        _spashiny_ctx.log_msg.set(f"Loaded downstream example/input from {source_label}: {path}")
        return adata

    _spashiny_ctx.load_downstream_h5ad = load_downstream_h5ad

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.downstream_canonical_upload)
    def _track_downstream_canonical_upload():
        if not _spashiny_globals.SPASHINY_WEB_PLATFORM:
            return
        try:
            payload = _spashiny_ctx.input.downstream_canonical_upload() or {}
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            return
        status = str(payload.get("status") or "").upper()
        filename = str(payload.get("filename") or "uploaded downstream h5ad")
        if status == "READY":
            upload_id = str(payload.get("upload_id") or "").strip()
            if not upload_id:
                _spashiny_ctx.log_msg.set(
                    "Downstream upload failed: completion returned no upload reference."
                )
                return
            try:
                resolved = _spashiny_ctx._resolve_downstream_interactive_input(
                    {"source": "upload", "upload_id": upload_id}
                )
            except Exception as exc:
                _spashiny_ctx.downstream_input_reference.set(None)
                _spashiny_ctx.adata_obj.set(None)
                _spashiny_ctx.marker_res.set(None)
                _spashiny_ctx.log_msg.set(f"Downstream upload is not available to this tab: {exc}")
                _spashiny_ctx.ui.notification_show(
                    f"Downstream upload is not available to this tab: {exc}",
                    type="error",
                    duration=8,
                )
                return
            _spashiny_ctx.downstream_input_reference.set(
                {"source": "upload", "upload_id": upload_id, "filename": resolved["filename"]}
            )
            _spashiny_ctx.adata_obj.set(None)
            _spashiny_ctx.marker_res.set(None)
            _spashiny_ctx.log_msg.set(
                f"Downstream upload ready: {resolved['filename']}. Click Load to continue."
            )
        elif status == "FAILED":
            _spashiny_ctx.downstream_input_reference.set(None)
            _spashiny_ctx.adata_obj.set(None)
            _spashiny_ctx.marker_res.set(None)
            _spashiny_ctx.log_msg.set(
                _spashiny_globals._upload_failure_text(payload, filename, "Downstream upload")
            )

    _spashiny_ctx._track_downstream_canonical_upload = _track_downstream_canonical_upload

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(
        _spashiny_ctx.input.cloud_example_action_activated, ignore_none=True
    )
    def _load_cloud_bound_downstream_example():
        if not _spashiny_globals.SPASHINY_WEB_PLATFORM:
            return
        try:
            payload = _spashiny_ctx.input.cloud_example_action_activated() or {}
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            return
        action_id = str(payload.get("action_id") or "").strip()
        if action_id != "y7-downstream-example" or not bool(payload.get("ready")):
            return
        try:
            _spashiny_ctx.downstream_input_reference.set(
                {"source": "example", "action_id": action_id}
            )
            _spashiny_ctx.adata_obj.set(None)
            _spashiny_ctx.marker_res.set(None)
            resolved = _spashiny_ctx._resolve_downstream_interactive_input(
                _spashiny_ctx.downstream_input_reference.get()
            )
            adata = _spashiny_ctx.load_downstream_h5ad(
                resolved["local_path"], "cloud-bound Y7_T downstream example"
            )
            _spashiny_ctx.ui.notification_show(
                f"Y7_T downstream analysis example loaded: {adata.shape}",
                type="message",
                duration=5,
            )
        except Exception as e:
            _spashiny_ctx.downstream_input_reference.set(None)
            _spashiny_ctx.adata_obj.set(None)
            _spashiny_ctx.marker_res.set(None)
            _spashiny_ctx.ui.notification_show(
                f"Failed to load downstream example: {e}", type="error", duration=8
            )

    _spashiny_ctx._load_cloud_bound_downstream_example = _load_cloud_bound_downstream_example

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.btn_load, ignore_none=True)
    def _load_uploaded_downstream_h5ad():
        if not _spashiny_ctx._downstream_click_guard("btn_load", "Load"):
            return
        _spashiny_ctx._show_downstream_action_modal(
            "Loading Downstream Data...",
            "Reading the selected h5ad file into the current analysis session.",
        )
        try:
            if _spashiny_globals.SPASHINY_WEB_PLATFORM:
                resolved = _spashiny_ctx._resolve_downstream_interactive_input(
                    _spashiny_ctx.downstream_input_reference.get()
                )
                source_label = (
                    "uploaded h5ad"
                    if resolved.get("source") == "upload"
                    else "Y7_T downstream example"
                )
                _spashiny_ctx.load_downstream_h5ad(resolved["local_path"], source_label)
            else:
                file_info = _spashiny_ctx.input.upload_h5ad()
                if not file_info:
                    raise RuntimeError("Please select a file first")
                _spashiny_ctx.load_downstream_h5ad(file_info[0]["datapath"], "uploaded h5ad")
            _spashiny_ctx.ui.notification_show("Data loaded successfully", type="message")
        except Exception as e:
            _spashiny_ctx.ui.notification_show(f"Failed to load data: {e}", type="error")
        finally:
            _spashiny_ctx.ui.modal_remove()

    _spashiny_ctx._load_uploaded_downstream_h5ad = _load_uploaded_downstream_h5ad

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.load_downstream_example, ignore_none=True)
    def _load_downstream_example():
        if _spashiny_globals.SPASHINY_WEB_PLATFORM:
            return
        if not _spashiny_ctx._downstream_click_guard("load_downstream_example", "Load Example"):
            return
        _spashiny_ctx._show_downstream_action_modal(
            "Loading Example Downstream Data...",
            "Binding and reading the Y7_T downstream reference h5ad.",
        )
        try:
            example_path = _spashiny_globals.get_example_downstream_joint_h5ad_path()
            adata = _spashiny_ctx.load_downstream_h5ad(example_path, "built-in downstream example")
            _spashiny_ctx.ui.notification_show(
                f"Example downstream data loaded: {adata.shape}", type="message", duration=5
            )
        except Exception as e:
            _spashiny_ctx.ui.notification_show(
                f"Failed to load downstream example: {e}", type="error", duration=8
            )
        finally:
            _spashiny_ctx.ui.modal_remove()

    _spashiny_ctx._load_downstream_example = _load_downstream_example

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.btn_run_marker)
    def _():
        if not _spashiny_ctx._downstream_click_guard("btn_run_marker", "Run Marker Analysis"):
            return
        adata = _spashiny_ctx.adata_obj()
        if adata is None:
            _spashiny_ctx.ui.notification_show("Please load the data first", type="error")
            return
        _spashiny_ctx.ui.modal_show(
            _spashiny_ctx.ui.modal(
                _spashiny_ctx.ui.div(
                    _spashiny_ctx.ui.h4("Running Marker Analysis...", class_="mb-3"),
                    _spashiny_ctx.ui.p(
                        "Please wait while the marker genes and metabolites are being analyzed."
                    ),
                    _spashiny_ctx.ui.p(
                        "This may take a few moments depending on dataset size.",
                        class_="text-muted",
                    ),
                ),
                title="Analysis in Progress",
                easy_close=False,
                footer=None,
            )
        )
        try:
            _spashiny_globals.preflight_memory(
                "marker analysis",
                adata=adata,
                multiplier=2.0,
                min_available_gb=1.5,
                log_func=lambda msg: print(msg, flush=True),
            )
            from cloud.portable_inputs import prepare_downstream_expression

            tmp = prepare_downstream_expression(
                adata, _spashiny_ctx.input.downstream_expression_source() or "X"
            )
            _spashiny_globals.smt.pp.rank_gene_and_metabolite_groups(
                tmp, groupby_ST="celltype1", groupby_SM="celltype1", use_raw=False
            )
            res = {"adata": tmp}
            if "rank_genes_groups" in tmp.uns:
                try:
                    res["gene_df"] = _spashiny_ctx.pd.DataFrame(
                        tmp.uns["rank_genes_groups"]["names"]
                    )
                except:
                    res["gene_df"] = _spashiny_ctx.pd.DataFrame()
            else:
                res["gene_df"] = _spashiny_ctx.pd.DataFrame()
            if "rank_metabolites_groups" in tmp.uns:
                try:
                    met_obj = tmp.uns["rank_metabolites_groups"]["names"]
                    res["met_df"] = _spashiny_ctx.pd.DataFrame(met_obj)
                except Exception as e:
                    print("metabolite parse error:", e)
                    res["met_df"] = _spashiny_ctx.pd.DataFrame()
            else:
                res["met_df"] = _spashiny_ctx.pd.DataFrame()
            _spashiny_ctx.marker_res.set(res)
            _spashiny_ctx.ui.modal_remove()
            _spashiny_ctx.ui.notification_show("Analysis completed successfully", type="message")
        except Exception as e:
            error_msg = _spashiny_globals.user_facing_error("Analysis failed", e)
            _spashiny_ctx.ui.modal_remove()
            _spashiny_ctx.ui.notification_show(
                error_msg,
                type="error",
                duration=14 if _spashiny_globals.is_memory_related_exception(e) else 8,
            )
            _spashiny_ctx.traceback.print_exc()

    _spashiny_ctx._ = _

    @_spashiny_ctx.render.ui
    def ui_upload_status():
        adata = _spashiny_ctx.adata_obj()
        return (
            _spashiny_ctx.ui.div(f"Loaded: {adata.shape}", class_="alert alert-success")
            if adata is not None
            else _spashiny_ctx.ui.div("No data loaded", class_="alert alert-danger")
        )

    _spashiny_ctx.ui_upload_status = ui_upload_status

    @_spashiny_ctx.render.table
    def tbl_summary():
        adata = _spashiny_ctx.adata_obj()
        return (
            _spashiny_ctx.pd.DataFrame(
                {
                    "Metric": ["Number of cells", "Number of genes"],
                    "Value": [adata.n_obs, adata.n_vars],
                }
            )
            if adata is not None
            else _spashiny_ctx.pd.DataFrame()
        )

    _spashiny_ctx.tbl_summary = tbl_summary

    @_spashiny_ctx.render.data_frame
    def tbl_markers_gene():
        res = _spashiny_ctx.marker_res()
        return res["gene_df"].head(50) if res and "gene_df" in res else _spashiny_ctx.pd.DataFrame()

    _spashiny_ctx.tbl_markers_gene = tbl_markers_gene

    @_spashiny_ctx.render.data_frame
    def tbl_markers_met():
        res = _spashiny_ctx.marker_res()
        return res["met_df"].head(50) if res and "met_df" in res else _spashiny_ctx.pd.DataFrame()

    _spashiny_ctx.tbl_markers_met = tbl_markers_met

    @_spashiny_ctx.render.data_frame
    def df_obs():
        adata = _spashiny_ctx.adata_obj()
        return (
            adata.obs.head(50).reset_index() if adata is not None else _spashiny_ctx.pd.DataFrame()
        )

    _spashiny_ctx.df_obs = df_obs


def _install_1(_spashiny_ctx):

    def _assert_downstream_table_scope():
        from cloud.database import CloudDatabase

        owner = _spashiny_ctx._require_cloud_session_id()
        analysis = _spashiny_ctx._cloud_analysis_session_id()
        if (
            not owner
            or not analysis
            or CloudDatabase(read_only=True)
            .get_analysis_session(analysis, owner_session_id=owner)
            .get("status")
            != "ACTIVE"
        ):
            raise ValueError("Download requires the current active analysis.")

    _spashiny_ctx._assert_downstream_table_scope = _assert_downstream_table_scope
    from downstream_table_downloads import register_downstream_table_downloads

    _spashiny_ctx.register_downstream_table_downloads = register_downstream_table_downloads
    _spashiny_ctx.downstream_table_downloads = _spashiny_ctx.register_downstream_table_downloads(
        _spashiny_ctx.output,
        get_adata=_spashiny_ctx.adata_obj.get,
        get_markers=_spashiny_ctx.marker_res.get,
        assert_scope=_spashiny_ctx._assert_downstream_table_scope,
    )
    _spashiny_ctx.annotation_df = _spashiny_ctx.reactive.Value(
        _spashiny_ctx.pd.DataFrame(columns=["cluster", "celltype_ST_SM"])
    )
    _spashiny_ctx.annotation_source_identity = _spashiny_ctx.reactive.Value(None)


def _install_2(_spashiny_ctx):

    @_spashiny_ctx.render.ui
    def ui_cluster_selector():
        adata = _spashiny_ctx.adata_obj()
        if adata is None or "celltype1" not in adata.obs.columns:
            return _spashiny_ctx.ui.div("Please load data first", class_="text-muted")
        clusters = sorted(adata.obs["celltype1"].astype(str).unique().tolist())
        return _spashiny_ctx.ui.input_select(
            "cluster_to_annotate",
            "Select Cluster",
            choices=clusters,
            selected=clusters[0] if len(clusters) > 0 else None,
        )

    _spashiny_ctx.ui_cluster_selector = ui_cluster_selector


def _install_3(_spashiny_ctx):

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.btn_run_marker_celltype)
    def _():
        if not _spashiny_ctx._downstream_click_guard(
            "btn_run_marker_celltype", "Run Marker Analysis"
        ):
            return
        adata = _spashiny_ctx.adata_obj()
        if adata is None:
            _spashiny_ctx.ui.notification_show("Please load the data first", type="error")
            return
        if "celltype_ST_SM" not in adata.obs.columns:
            _spashiny_ctx.ui.notification_show(
                "Please create 'celltype_ST_SM' column first!", type="error"
            )
            return
        _spashiny_ctx.ui.update_action_button("btn_run_marker_celltype", disabled=True)
        _spashiny_ctx.ui.modal_show(
            _spashiny_ctx.ui.modal(
                _spashiny_ctx.ui.div(
                    _spashiny_ctx.ui.h4(
                        "Running Marker Analysis on celltype_ST_SM...", class_="mb-3"
                    ),
                    _spashiny_ctx.ui.p(
                        "Please wait while the marker genes and metabolites are being analyzed."
                    ),
                    _spashiny_ctx.ui.p(
                        "This may take a few moments depending on dataset size.",
                        class_="text-muted",
                    ),
                    _spashiny_ctx.ui.tags.div(class_="spinner-border text-primary"),
                ),
                title="Analysis in Progress",
                easy_close=False,
                footer=None,
            )
        )
        try:
            _spashiny_ctx.ui.notification_show("Running analysis...", type="message")
            _spashiny_globals.preflight_memory(
                "celltype marker analysis",
                adata=adata,
                multiplier=2.0,
                min_available_gb=1.5,
                log_func=lambda msg: print(msg, flush=True),
            )
            from cloud.portable_inputs import prepare_downstream_expression

            tmp = prepare_downstream_expression(
                adata, _spashiny_ctx.input.downstream_expression_source() or "X"
            )
            labels = tmp.obs["celltype_ST_SM"].astype(str).str.strip()
            labels = (
                labels.replace("", _spashiny_globals.np.nan)
                .replace("nan", _spashiny_globals.np.nan)
                .replace("None", _spashiny_globals.np.nan)
            )
            labels = labels.fillna("Unknown")
            actual_cats = _spashiny_ctx.pd.unique(labels).tolist()
            tmp.obs["celltype_ST_SM_clean"] = _spashiny_ctx.pd.Categorical(
                labels, categories=actual_cats, ordered=True
            )
            base_colors = [
                "#4A6BA0",
                "#9DBCED",
                "#28497F",
                "#4A8BD1",
                "#522188",
                "#7A58A5",
                "#BB94ED",
                "#AC4EDD",
                "#C58DE2",
                "#9DE86D",
                "#499E12",
                "#097A39",
                "#00C67F",
                "#6CE0AB",
                "#9DCEA2",
                "#597C5C",
                "#005908",
                "#EA4E00",
                "#EF915E",
                "#E5BE1C",
                "#4F46E5",
                "#14B8A6",
                "#F43F5E",
                "#84CC16",
                "#F59E0B",
                "#06B6D4",
                "#8B5CF6",
                "#10B981",
                "#EF4444",
                "#A855F7",
            ]
            color_map = {c: base_colors[i % len(base_colors)] for i, c in enumerate(actual_cats)}
            tmp.uns["celltype_ST_SM_clean_colors"] = [
                color_map.get(c, "#CCCCCC") for c in actual_cats
            ]
            palette_text = "palette = {\n"
            for k, v in color_map.items():
                palette_text += f'    "{k}": "{v}",\n'
            palette_text += "}"
            print("\n===== Auto-generated palette =====")
            print(palette_text)
            print("=================================\n")
            print("Actual categories:", [repr(x) for x in actual_cats])
            _spashiny_globals.smt.pp.rank_gene_and_metabolite_groups(
                tmp,
                groupby_ST="celltype_ST_SM_clean",
                groupby_SM="celltype_ST_SM_clean",
                use_raw=False,
            )
            res = {"adata": tmp}
            if "rank_genes_groups" in tmp.uns and "names" in tmp.uns["rank_genes_groups"]:
                gene_df = _spashiny_ctx.pd.DataFrame(tmp.uns["rank_genes_groups"]["names"])
                gene_df.columns = [str(x).strip() for x in gene_df.columns]
            else:
                gene_df = _spashiny_ctx.pd.DataFrame()
            if (
                "rank_metabolites_groups" in tmp.uns
                and "names" in tmp.uns["rank_metabolites_groups"]
            ):
                met_df = _spashiny_ctx.pd.DataFrame(tmp.uns["rank_metabolites_groups"]["names"])
                met_df.columns = [str(x).strip() for x in met_df.columns]
            else:
                met_df = _spashiny_ctx.pd.DataFrame()
            res["gene_df"] = gene_df
            res["met_df"] = met_df
            res["actual_cats"] = actual_cats
            res["palette"] = color_map
            res["palette_text"] = palette_text
            _spashiny_ctx.marker_res.set(res)
            _spashiny_ctx.ui.modal_remove()
            _spashiny_ctx.ui.update_action_button("btn_run_marker_celltype", disabled=False)
            _spashiny_ctx.ui.notification_show("Analysis completed successfully", type="message")
        except Exception as e:
            error_msg = _spashiny_globals.user_facing_error("Analysis failed", e)
            _spashiny_ctx.ui.modal_remove()
            _spashiny_ctx.ui.update_action_button("btn_run_marker_celltype", disabled=False)
            _spashiny_ctx.ui.notification_show(
                error_msg,
                type="error",
                duration=14 if _spashiny_globals.is_memory_related_exception(e) else 8,
            )
            _spashiny_ctx.traceback.print_exc()

    _spashiny_ctx._ = _

    def _as_matplotlib_figure(plot_obj):
        if plot_obj is None:
            raise ValueError("No plot is available. Please run the analysis first.")
        if hasattr(plot_obj, "savefig"):
            return plot_obj
        if hasattr(plot_obj, "figure") and hasattr(plot_obj.figure, "savefig"):
            return plot_obj.figure
        if hasattr(plot_obj, "fig") and hasattr(plot_obj.fig, "savefig"):
            return plot_obj.fig
        raise TypeError(f"Unsupported plot object type: {type(plot_obj).__name__}")

    _spashiny_ctx._as_matplotlib_figure = _as_matplotlib_figure

    def _stream_png_from_plot(plot_obj, prefix, close_after=False):
        fig = _spashiny_ctx._as_matplotlib_figure(plot_obj)
        path = _spashiny_ctx.save_fig_to_temp_png(fig, prefix=prefix)
        try:
            yield from _spashiny_ctx.stream_file(path)
        finally:
            if close_after:
                _spashiny_globals.plt.close(fig)
            if _spashiny_globals.os.path.exists(path):
                _spashiny_globals.os.remove(path)

    _spashiny_ctx._stream_png_from_plot = _stream_png_from_plot


_STEPS = (_install_0, _install_1, _install_2, _install_3)


def server(_spashiny_ctx, step=0):
    return _STEPS[step](_spashiny_ctx)
