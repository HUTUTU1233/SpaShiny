# Extracted from /app/app/ST-SM.py. Feature: correlation; ordered phases preserve original initialization.
from spashiny._shared import runtime_globals as _spashiny_globals


def _install_0(_spashiny_ctx):

    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("plt_marker_celltype")
    def plt_marker_celltype():
        return _spashiny_ctx.build_marker_celltype_figure()

    _spashiny_ctx.plt_marker_celltype = plt_marker_celltype

    @_spashiny_ctx.render.download(filename=lambda: "marker_visualization.png")
    def download_marker_celltype_png():
        fig = _spashiny_ctx.build_marker_celltype_figure()
        if fig is None:
            _spashiny_ctx.ui.notification_show("Please run marker analysis first.", type="error")
            return
        yield from _spashiny_ctx._stream_png_from_plot(
            fig, prefix="marker_visualization", close_after=True
        )

    _spashiny_ctx.download_marker_celltype_png = download_marker_celltype_png

    def _download_marker_vector(format):
        fig = _spashiny_ctx.build_marker_celltype_figure()
        if fig is None:
            raise RuntimeError(
                "Run Marker analysis for the current input before downloading its figure."
            )
        try:
            buffer = _spashiny_ctx.io.BytesIO()
            _spashiny_globals.save_native_figure(fig, buffer, format=format, bbox_inches="tight")
            yield buffer.getvalue()
        finally:
            _spashiny_globals.plt.close(fig)

    _spashiny_ctx._download_marker_vector = _download_marker_vector

    @_spashiny_ctx.render.download(filename=lambda: "marker_visualization.pdf")
    def download_marker_celltype_pdf():
        yield from _spashiny_ctx._download_marker_vector("pdf")

    _spashiny_ctx.download_marker_celltype_pdf = download_marker_celltype_pdf

    @_spashiny_ctx.render.download(filename=lambda: "marker_visualization.svg")
    def download_marker_celltype_svg():
        yield from _spashiny_ctx._download_marker_vector("svg")

    _spashiny_ctx.download_marker_celltype_svg = download_marker_celltype_svg

    def _matrix_to_dense_float(X):
        if hasattr(X, "toarray"):
            X = X.toarray()
        return _spashiny_globals.np.asarray(X, dtype=float)

    _spashiny_ctx._matrix_to_dense_float = _matrix_to_dense_float

    def _feature_names_from_mask(adata, mask):
        var_names = _spashiny_ctx.pd.Index([str(x) for x in adata.var_names])
        return list(var_names[_spashiny_globals.np.asarray(mask, dtype=bool)])

    _spashiny_ctx._feature_names_from_mask = _feature_names_from_mask

    def _correlation_gene_choices(adata):
        """Offer only ST features in this input's current matrix, never raw/another source."""
        if adata is None or "type" not in adata.var:
            return []
        names = _spashiny_ctx._feature_names_from_mask(
            adata, adata.var["type"].astype(str).eq("ST")
        )
        return list(dict.fromkeys((name for name in names if name.strip())))

    _spashiny_ctx._correlation_gene_choices = _correlation_gene_choices

    def _correlation_selected_genes(value):
        if value is None:
            return []
        items = value.split(",") if isinstance(value, str) else list(value)
        return list(dict.fromkeys((str(item).strip() for item in items if str(item).strip())))

    _spashiny_ctx._correlation_selected_genes = _correlation_selected_genes

    def _correlation_input_identity(data, reference):
        reference = reference if isinstance(reference, dict) else {}
        return (
            id(data),
            tuple(sorted(((str(key), str(value)) for key, value in reference.items()))),
        )

    _spashiny_ctx._correlation_input_identity = _correlation_input_identity

    def get_correlation_feature_indices(
        joint_adata, requested_genes, only_annotated_metabolites=False
    ):
        var = joint_adata.var
        if "type" not in var:
            raise ValueError(
                "Correlation requires SpatialMETA var['type'] with exact ST/SM labels."
            )
        type_s = var["type"].astype(str)
        if not set(type_s).issubset({"ST", "SM"}):
            raise ValueError(
                "Unrecognized feature types; ST/SM identity cannot be inferred from feature names."
            )
        sm_mask, st_mask = (type_s.eq("SM"), type_s.eq("ST"))
        if only_annotated_metabolites:
            if "metabolite_name" not in var.columns:
                raise ValueError(
                    "Only annotated metabolites is enabled, but adata.var['metabolite_name'] was not found. Please turn off this option or complete metabolite annotation first."
                )
            annotated_s = var["metabolite_name"].astype(str).str.strip()
            annotated_mask = annotated_s.ne("") & ~annotated_s.str.lower().isin(
                ["nan", "none", "na", "n/a", "null"]
            )
            sm_mask = sm_mask & annotated_mask
        all_gene_idx = _spashiny_ctx._feature_names_from_mask(joint_adata, st_mask)
        metabolite_idx = _spashiny_ctx._feature_names_from_mask(joint_adata, sm_mask)
        requested_genes = [str(g).strip() for g in requested_genes if str(g).strip()]
        st_feature_set = set(all_gene_idx)
        missing_genes = list(dict.fromkeys((g for g in requested_genes if g not in st_feature_set)))
        if missing_genes:
            raise ValueError(
                "Selected genes are not available in the current ST input: "
                + ", ".join(missing_genes[:20])
                + (" ..." if len(missing_genes) > 20 else "")
                + ". Please re-select genes from the current data."
            )
        gene_idx = list(dict.fromkeys([g for g in requested_genes if g in st_feature_set]))
        print("n_gene_features:", len(gene_idx))
        print("n_sm_features:", len(metabolite_idx))
        if len(gene_idx) == 0:
            raise ValueError("No gene/ST features selected for correlation analysis.")
        if len(metabolite_idx) == 0:
            if only_annotated_metabolites:
                raise ValueError(
                    "No annotated SM/metabolite features selected for correlation analysis. Please turn off 'Only annotated metabolites' or complete metabolite annotation first."
                )
            raise ValueError(
                "No SM/metabolite features selected for correlation analysis. Please check var['type'], annotation status, or filters."
            )
        return (gene_idx, metabolite_idx)

    _spashiny_ctx.get_correlation_feature_indices = get_correlation_feature_indices

    def _safe_gene_metabolite_corr_matrix(X_gene, X_met):
        if X_gene.shape[0] != X_met.shape[0]:
            raise ValueError("Gene and metabolite observations differ.")
        if X_gene.shape[0] < 2:
            return _spashiny_globals.np.full(
                (X_gene.shape[1], X_met.shape[1]), _spashiny_globals.np.nan
            )
        with _spashiny_globals.np.errstate(invalid="ignore", divide="ignore"):
            return _spashiny_globals.np.array(
                [
                    [
                        _spashiny_globals.np.corrcoef(X_gene[:, i], X_met[:, j])[0, 1]
                        for j in range(X_met.shape[1])
                    ]
                    for i in range(X_gene.shape[1])
                ]
            )

    _spashiny_ctx._safe_gene_metabolite_corr_matrix = _safe_gene_metabolite_corr_matrix

    def run_compatible_stsm_correlation(
        joint_adata, gene_idx, metabolite_idx, groupby="celltype_ST_SM", ntop=5
    ):
        from scipy import sparse

        if groupby not in joint_adata.obs or joint_adata.obs[groupby].isna().any():
            raise ValueError(
                "A complete, explicitly selected annotation column is required for correlation."
            )
        selected = list(dict.fromkeys(list(gene_idx) + list(metabolite_idx)))
        data = joint_adata[:, selected].copy()
        data.X = sparse.csr_matrix(data.X)
        data.obs[groupby] = data.obs[groupby].astype(str)
        _spashiny_globals.smt.pp.corrcoef_stsm_ingroup(
            data,
            inputlist=list(gene_idx),
            list_type="gene",
            groupby=groupby,
            use_raw=False,
            ntop=int(ntop),
        )
        for key in ("corrcoef_stsm_ingroup_top", "corrcoef_stsm_ingroup"):
            joint_adata.uns[key] = data.uns[key]
        joint_adata.uns["spashiny_native_downstream_v1"] = {
            "correlation": "spatialmeta.pp.corrcoef_stsm_ingroup",
            "input": "selected X; use_raw=False",
        }
        joint_adata.uns["corrcoef_stsm_ingroup_info"] = {
            "n_gene_features": len(gene_idx),
            "n_sm_features": len(metabolite_idx),
            "matrix_shape": [len(gene_idx), len(metabolite_idx)],
            "undefined_coefficients": "NaN (not imputed)",
        }
        return joint_adata

    _spashiny_ctx.run_compatible_stsm_correlation = run_compatible_stsm_correlation
    _spashiny_ctx.corr_plot_trigger = _spashiny_ctx.reactive.Value(0)
    _spashiny_ctx.corr_res = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx._correlation_gene_picker_source = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx._correlation_result_source = _spashiny_ctx.reactive.Value(None)

    @_spashiny_ctx.output
    @_spashiny_ctx.render.ui
    def correlation_gene_selector():
        loaded = _spashiny_ctx.adata_obj()
        result = _spashiny_ctx.marker_res()
        reference = _spashiny_ctx.downstream_input_reference.get()
        data = result.get("adata") if loaded is not None and isinstance(result, dict) else None
        if data is None:
            data = loaded
        choices = _spashiny_ctx._correlation_gene_choices(data)
        source_key = _spashiny_ctx._correlation_input_identity(loaded, reference)
        with _spashiny_ctx.reactive.isolate():
            previous_source = _spashiny_ctx._correlation_gene_picker_source.get()
            try:
                selected = _spashiny_ctx._correlation_selected_genes(
                    _spashiny_ctx.input.gene_list_corr()
                )
            except Exception:
                selected = []
        available = set(choices)
        selected = (
            [gene for gene in selected if gene in available]
            if previous_source == source_key
            else []
        )
        _spashiny_ctx._correlation_gene_picker_source.set(source_key)
        return _spashiny_ctx.ui.TagList(
            _spashiny_ctx.ui.input_selectize(
                "gene_list_corr",
                "Genes (search and select)",
                choices=choices,
                selected=selected,
                multiple=True,
                remove_button=True,
                options={
                    "placeholder": "Type to search ST genes in the current data",
                    "create": False,
                    "maxOptions": 200,
                    "closeAfterSelect": False,
                },
            ),
            _spashiny_ctx.ui.tags.div(
                (
                    f"{len(choices):,} ST genes available from the current input. Select one or more genes, then run correlation analysis."
                    if choices
                    else "Load a joint H5AD containing ST features to choose genes."
                ),
                class_="cloud-muted",
                style="font-size: 12px; margin-top: 6px;",
            ),
        )

    _spashiny_ctx.correlation_gene_selector = correlation_gene_selector

    @_spashiny_ctx.reactive.Effect
    def _invalidate_correlation_on_input_change():
        loaded = _spashiny_ctx.adata_obj()
        result = _spashiny_ctx.marker_res()
        source_key = (
            _spashiny_ctx._correlation_input_identity(
                loaded, _spashiny_ctx.downstream_input_reference.get()
            ),
            id(result),
        )
        with _spashiny_ctx.reactive.isolate():
            previous_source = _spashiny_ctx._correlation_result_source.get()
        if previous_source != source_key:
            _spashiny_ctx._correlation_result_source.set(source_key)
            _spashiny_ctx.corr_res.set(None)

    _spashiny_ctx._invalidate_correlation_on_input_change = _invalidate_correlation_on_input_change

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.btn_run_corr)
    async def run_corr_analysis():
        if not _spashiny_ctx._downstream_click_guard("btn_run_corr", "Run Correlation Analysis"):
            return
        res = _spashiny_ctx.marker_res()
        if not res or "adata" not in res:
            _spashiny_ctx.ui.notification_show(
                "Please complete marker analysis first.", type="error"
            )
            return
        joint_adata = res["adata"]
        if "celltype_ST_SM" not in joint_adata.obs:
            _spashiny_ctx.ui.notification_show(
                "The current input has no celltype_ST_SM annotation. Select/create its grouping in Marker first.",
                type="error",
            )
            return
        gene_list = _spashiny_ctx._correlation_selected_genes(_spashiny_ctx.input.gene_list_corr())
        if not gene_list:
            _spashiny_ctx.ui.notification_show(
                "Select at least one ST gene from the searchable dropdown.", type="error"
            )
            return
        _spashiny_ctx.ui.modal_show(
            _spashiny_ctx.ui.modal(
                _spashiny_ctx.ui.div(
                    _spashiny_ctx.ui.h4("Running Correlation Analysis...", class_="mb-3"),
                    _spashiny_ctx.ui.p(
                        "Please wait while the ST-SM correlation analysis is being performed."
                    ),
                    _spashiny_ctx.ui.p(
                        "The heatmap will be rendered automatically after the analysis is completed.",
                        class_="text-muted",
                    ),
                ),
                title="Analysis in Progress",
                easy_close=False,
                footer=None,
            )
        )
        try:
            only_annotated = bool(_spashiny_ctx.input.corr_only_annotated_metabolites())
            gene_idx, metabolite_idx = _spashiny_ctx.get_correlation_feature_indices(
                joint_adata, gene_list, only_annotated_metabolites=only_annotated
            )
            ntop = int(_spashiny_ctx.input.corr_ntop())

            def calculate_native_correlations():
                selected = list(dict.fromkeys(gene_idx + metabolite_idx))
                data = joint_adata[:, selected].copy()
                return _spashiny_ctx.run_compatible_stsm_correlation(
                    data, gene_idx, metabolite_idx, groupby="celltype_ST_SM", ntop=ntop
                )

            calculated = await _spashiny_globals.asyncio.to_thread(calculate_native_correlations)
            if _spashiny_ctx.marker_res() is not res:
                _spashiny_ctx.ui.notification_show(
                    "The input changed while correlation was running; stale results were not adopted.",
                    type="warning",
                )
                return
            for key in (
                "corrcoef_stsm_ingroup_top",
                "corrcoef_stsm_ingroup",
                "corrcoef_stsm_ingroup_info",
                "spashiny_native_downstream_v1",
            ):
                joint_adata.uns[key] = calculated.uns[key]
            _spashiny_ctx.corr_res.set(joint_adata)
            _spashiny_ctx.corr_plot_trigger.set(_spashiny_ctx.corr_plot_trigger.get() + 1)
            _spashiny_ctx.dash_embed_state.set(
                {
                    "status": "ready",
                    "url": "",
                    "message": "Correlation analysis is complete. Open Downstream Analysis → Dash Plotly, then start the embedded viewer.",
                }
            )
            _spashiny_ctx.ui.notification_show(
                "Correlation heatmap and volcano controls are ready below. To use Dash, open Downstream Analysis → Dash Plotly.",
                type="message",
                duration=7,
            )
            _spashiny_ctx.ui.notification_show(
                "ST-SM correlation analysis completed.", type="message"
            )
        except Exception as e:
            _spashiny_ctx.ui.notification_show(f"Correlation analysis failed: {e}", type="error")
            _spashiny_ctx.traceback.print_exc()
            _spashiny_ctx.corr_res.set(None)
        finally:
            _spashiny_ctx.ui.modal_remove()

    _spashiny_ctx.run_corr_analysis = run_corr_analysis

    def _format_correlation_mz_label(feature):
        """Use a compact, complete m/z label that is safe to render in the heatmap."""
        text = str(feature).strip()
        numeric_text = _spashiny_ctx.re.sub("(?i)^\\s*(?:m/z|mz[_\\-\\s]*)\\s*", "", text)
        try:
            return f"mz {float(numeric_text):.6f}"
        except (TypeError, ValueError):
            return text

    _spashiny_ctx._format_correlation_mz_label = _format_correlation_mz_label

    def _make_unique_display_labels(features):
        labels = []
        counts = {}
        for feature in features:
            base = _spashiny_ctx._format_correlation_mz_label(feature)
            counts[base] = counts.get(base, 0) + 1
            labels.append(base if counts[base] == 1 else f"{base} ({counts[base]})")
        return labels

    _spashiny_ctx._make_unique_display_labels = _make_unique_display_labels

    def _get_correlation_heatmap_frame(adata, cluster):
        top = adata.uns.get("corrcoef_stsm_ingroup_top")
        grouped = adata.uns.get("corrcoef_stsm_ingroup", {})
        if not isinstance(top, _spashiny_ctx.pd.DataFrame) or top.empty:
            raise ValueError(
                "No correlation results are available. Run correlation analysis first."
            )
        if cluster not in grouped:
            raise ValueError(f"No correlation matrix was found for cluster: {cluster}")
        selected = top.loc[top["cluster"].astype(str) == str(cluster)]
        if selected.empty:
            raise ValueError(f"No top correlations were found for cluster: {cluster}")
        genes = list(dict.fromkeys(selected["gene"].astype(str).tolist()))
        metabolites = list(dict.fromkeys(selected["metabolite"].astype(str).tolist()))
        matrix_info = grouped[cluster]
        matrix = _spashiny_globals.np.asarray(matrix_info["data"], dtype=float)
        all_genes = [str(value) for value in matrix_info["gene"]]
        all_metabolites = [str(value) for value in matrix_info["metabolite"]]
        frame = _spashiny_ctx.pd.DataFrame(matrix, index=all_genes, columns=all_metabolites)
        selected_frame = frame.reindex(index=genes, columns=metabolites)
        if adata.uns.get("spashiny_native_downstream_v1"):
            return selected_frame
        return selected_frame

    _spashiny_ctx._get_correlation_heatmap_frame = _get_correlation_heatmap_frame

    def build_correlation_heatmap_figure():
        adata = _spashiny_ctx.corr_res()
        if adata is None:
            return None
        cluster = str(_spashiny_ctx.input.corr_cluster() or "").strip()
        if "celltype_ST_SM" not in adata.obs.columns:
            _spashiny_ctx.ui.notification_show(
                "'celltype_ST_SM' is missing in adata.obs.", type="error"
            )
            return None
        cluster_values = [str(x) for x in adata.obs["celltype_ST_SM"].dropna().unique()]
        if cluster not in cluster_values:
            _spashiny_ctx.ui.notification_show(f"Cluster not found: {cluster}", type="error")
            return None
        _spashiny_globals.plt.close("all")
        try:
            import seaborn as sns

            corr_frame = _spashiny_ctx._get_correlation_heatmap_frame(adata, cluster)
            native_missing = bool(corr_frame.isna().any().any())
            fig_w = min(max(float(_spashiny_ctx.input.correlation_figsize_width() or 8), 7.0), 14.0)
            fig_h = min(
                max(float(_spashiny_ctx.input.correlation_figsize_height() or 7), 6.5), 12.0
            )
            grid = sns.clustermap(
                corr_frame,
                cmap="vlag",
                center=0,
                row_cluster=bool(_spashiny_ctx.input.correlation_row_cluster())
                and corr_frame.shape[0] > 1
                and (not native_missing),
                col_cluster=bool(_spashiny_ctx.input.correlation_col_cluster())
                and corr_frame.shape[1] > 1
                and (not native_missing),
                mask=corr_frame.isna() if native_missing else None,
                figsize=(fig_w, fig_h),
                linewidths=0.25,
                linecolor="#ffffff",
                cbar_kws={"label": "Pearson correlation"},
                dendrogram_ratio=(0.12, 0.1),
            )
            ordered_metabolites = [str(value) for value in grid.data2d.columns]
            ordered_genes = [str(value) for value in grid.data2d.index]
            x_font_size = 8 if len(ordered_metabolites) <= 15 else 7
            y_font_size = 9 if len(ordered_genes) <= 12 else 8
            grid.ax_heatmap.xaxis.tick_bottom()
            grid.ax_heatmap.set_xticks(
                _spashiny_globals.np.arange(len(ordered_metabolites), dtype=float) + 0.5
            )
            grid.ax_heatmap.set_xticklabels(
                _spashiny_ctx._make_unique_display_labels(ordered_metabolites),
                rotation=55,
                ha="right",
                rotation_mode="anchor",
                fontsize=x_font_size,
            )
            grid.ax_heatmap.set_yticks(
                _spashiny_globals.np.arange(len(ordered_genes), dtype=float) + 0.5
            )
            grid.ax_heatmap.set_yticklabels(ordered_genes, rotation=0, fontsize=y_font_size)
            grid.ax_heatmap.set_xlabel("Metabolite m/z", labelpad=14)
            grid.ax_heatmap.set_ylabel("Gene", labelpad=10)
            grid.fig.subplots_adjust(left=0.15, bottom=0.34, right=0.92, top=0.93)
            if native_missing:
                grid.fig.text(
                    0.15,
                    0.02,
                    "Blank cells: undefined native correlations. Clustering disabled rather than imputing zeros.",
                    fontsize=8,
                )
            return grid.fig
        except Exception as e:
            _spashiny_ctx.ui.notification_show(f"Heatmap rendering failed: {e}", type="error")
            _spashiny_ctx.traceback.print_exc()
            return None

    _spashiny_ctx.build_correlation_heatmap_figure = build_correlation_heatmap_figure

    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("plt_corr_heatmap")
    @_spashiny_ctx.reactive.event(_spashiny_ctx.corr_plot_trigger)
    def plt_corr_heatmap():
        return _spashiny_ctx.build_correlation_heatmap_figure()

    _spashiny_ctx.plt_corr_heatmap = plt_corr_heatmap

    @_spashiny_ctx.render.download(filename=lambda: "correlation_heatmap.png")
    def download_corr_heatmap_png():
        fig = _spashiny_ctx.build_correlation_heatmap_figure()
        if fig is None:
            _spashiny_ctx.ui.notification_show(
                "Please run correlation analysis first.", type="error"
            )
            return
        yield from _spashiny_ctx._stream_png_from_plot(
            fig, prefix="correlation_heatmap", close_after=True
        )

    _spashiny_ctx.download_corr_heatmap_png = download_corr_heatmap_png

    @_spashiny_ctx.render.download(
        filename=lambda: "correlation_heatmap.pdf", media_type="application/pdf"
    )
    def download_corr_heatmap_pdf():
        original = _spashiny_ctx.build_correlation_heatmap_figure()
        if original is None:
            raise RuntimeError(
                "Run correlation analysis for the current input and select a valid cluster before downloading its PDF."
            )
        exported = None
        try:
            exported = _spashiny_ctx.colorize_plot("plt_corr_heatmap", original)
            colorbars = [ax for ax in exported.axes if ax.get_ylabel() == "Pearson correlation"]
            if colorbars:
                exported.canvas.draw()
                renderer = exported.canvas.get_renderer()
                bounds = [ax.get_tightbbox(renderer) for ax in exported.axes if ax not in colorbars]
                right = max((box.x1 for box in bounds if box is not None)) / exported.bbox.width
                for ax in colorbars:
                    ax.set_position((right + 0.035, 0.5, 0.025, 0.35))
                    ax.set_ylabel("Pearson correlation", labelpad=10)
            buf = _spashiny_ctx.io.BytesIO()
            _spashiny_globals.save_native_figure(
                exported, buf, format="pdf", bbox_inches="tight", facecolor="white"
            )
            payload = buf.getvalue()
            if not payload.startswith(b"%PDF-"):
                raise RuntimeError(
                    "The editable correlation PDF could not be generated; no raster fallback was used."
                )
            yield payload
        finally:
            if exported is not None and exported is not original:
                _spashiny_globals.plt.close(exported)
            _spashiny_globals.plt.close(original)

    _spashiny_ctx.download_corr_heatmap_pdf = download_corr_heatmap_pdf

    def get_volcano_choices(adata):
        """Native volcano APIs compute from X; offer all explicit ST/SM features.

        The precomputed heatmap contains only its selected genes. It must not
        silently become a feature filter for the independent native volcano.
        Unknown modality labels are never guessed to be genes or metabolites.
        """
        clusters = []
        genes = []
        metabolites = []
        if adata is not None and "celltype_ST_SM" in adata.obs.columns:
            clusters = [str(x) for x in adata.obs["celltype_ST_SM"].dropna().unique().tolist()]
        if adata is not None and "type" in adata.var:
            var_names = [str(x) for x in adata.var_names.tolist()]
            types = adata.var["type"].astype(str)
            genes = [name for name, kind in zip(var_names, types) if kind == "ST"]
            metabolites = [name for name, kind in zip(var_names, types) if kind == "SM"]
        clusters = list(dict.fromkeys(clusters))
        genes = list(dict.fromkeys(genes))
        metabolites = list(dict.fromkeys(metabolites))
        return (clusters, genes, metabolites)

    _spashiny_ctx.get_volcano_choices = get_volcano_choices

    @_spashiny_ctx.render.text
    def volcano_feature_availability():
        _clusters, genes, metabolites = _spashiny_ctx.get_volcano_choices(_spashiny_ctx.corr_res())
        return f"{len(genes):,} ST genes and {len(metabolites):,} SM features available in the current input. Search the complete feature list; only up to 100 matching options are shown at once. Heatmap gene selection does not restrict the volcano targets."

    _spashiny_ctx.volcano_feature_availability = volcano_feature_availability

    @_spashiny_ctx.reactive.Effect
    def update_volcano_select_choices():
        adata = _spashiny_ctx.corr_res()
        if adata is None:
            return
        clusters, genes, metabolites = _spashiny_ctx.get_volcano_choices(adata)
        _spashiny_ctx.ui.update_selectize(
            "volcano_cluster",
            choices=clusters,
            selected=clusters[0] if clusters else None,
            session=_spashiny_ctx.session,
        )
        _spashiny_ctx.ui.update_selectize(
            "volcano_gene",
            choices=genes,
            selected=genes[0] if genes else None,
            session=_spashiny_ctx.session,
        )
        _spashiny_ctx.ui.update_selectize(
            "volcano_metabolite",
            choices=metabolites,
            selected=metabolites[0] if metabolites else None,
            session=_spashiny_ctx.session,
        )

    _spashiny_ctx.update_volcano_select_choices = update_volcano_select_choices


_STEPS = (_install_0,)


def server(_spashiny_ctx, step=0):
    return _STEPS[step](_spashiny_ctx)
