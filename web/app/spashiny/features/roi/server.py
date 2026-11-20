# Extracted from /app/app/ST-SM.py. Feature: roi; ordered phases preserve original initialization.
from spashiny._shared import runtime_globals as _spashiny_globals


def _install_0(_spashiny_ctx):
    import io

    _spashiny_ctx.io = io
    import scanpy as sc

    _spashiny_globals.sc = sc
    import pandas as pd

    _spashiny_ctx.pd = pd
    import numpy as np

    _spashiny_globals.np = np
    import matplotlib.pyplot as plt

    _spashiny_globals.plt = plt
    import traceback

    _spashiny_ctx.traceback = traceback
    from cloud.figure_export import EditablePdfPages as PdfPages

    _spashiny_ctx.PdfPages = PdfPages
    _spashiny_ctx.adata_probe_info_rv = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.obs_summary_rv = _spashiny_ctx.reactive.Value("No obs field inspected yet.")
    _spashiny_ctx.roi_table_data = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.roi_spatial_fig_rv = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.roi_marker_fig_rv = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.roi_last_result_rv = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.ROI_BLOCKLIST = {
        "x_coord",
        "y_coord",
        "spot_name",
        "total_intensity",
        "mean_intensity",
        "n_genes_by_counts",
        "log1p_n_genes_by_counts",
        "total_counts",
        "log1p_total_counts",
        "pct_counts_in_top_50_genes",
        "pct_counts_in_top_100_genes",
        "pct_counts_in_top_200_genes",
        "pct_counts_in_top_500_genes",
        "total_counts_mt",
        "log1p_total_counts_mt",
        "pct_counts_mt",
        "n_counts",
        "n_genes",
        "VAE_clusters_latent10",
        "celltype1",
        "a_celltype_ST_SM",
        "celltype_ST_SM",
        "celltype_ST_SM_clean",
    }
    _spashiny_ctx.ROI_BLOCK_PREFIXES = ("trajectory_",)

    def is_valid_roi_column(adata, col_name):
        """
        Decide whether an obs column is suitable for ROI analysis.
        """
        if adata is None:
            return (False, "AnnData is not available.")
        if not col_name:
            return (False, "Please select an ROI / annotation column.")
        if col_name not in adata.obs.columns:
            return (False, f"Column '{col_name}' does not exist in adata.obs.")
        col_name_str = str(col_name)
        if col_name_str in _spashiny_ctx.ROI_BLOCKLIST:
            return (False, f"'{col_name_str}' is a system/meta column, not an ROI column.")
        for pfx in _spashiny_ctx.ROI_BLOCK_PREFIXES:
            if col_name_str.startswith(pfx):
                return (False, f"'{col_name_str}' is a trajectory column, not an ROI column.")
        col = adata.obs[col_name]
        if _spashiny_ctx.pd.api.types.is_numeric_dtype(col):
            return (
                False,
                f"'{col_name_str}' is numeric and does not look like an ROI category column.",
            )
        nunique = col.astype(str).nunique(dropna=True)
        if nunique < 2:
            return (False, f"'{col_name_str}' has fewer than 2 categories.")
        return (True, "OK")

    _spashiny_ctx.is_valid_roi_column = is_valid_roi_column

    def get_valid_roi_columns(adata):
        """
        Return only obs columns suitable for ROI analysis.
        """
        if adata is None:
            return []
        valid_cols = []
        for col in adata.obs.columns:
            ok, _ = _spashiny_ctx.is_valid_roi_column(adata, col)
            if ok:
                valid_cols.append(col)
        return valid_cols

    _spashiny_ctx.get_valid_roi_columns = get_valid_roi_columns

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.btn_probe_adata)
    def probe_adata():
        adata_global = _spashiny_ctx.trajectory_adata_rv.get()
        if adata_global is None:
            _spashiny_ctx.ui.notification_show("No AnnData detected", type="error")
            return
        info = {
            "n_cells": adata_global.n_obs,
            "n_genes": adata_global.n_vars,
            "obs_keys": list(adata_global.obs.columns),
            "uns_keys": list(adata_global.uns.keys()),
            "obsm_keys": list(adata_global.obsm.keys()),
        }
        _spashiny_ctx.adata_probe_info_rv.set(info)
        _spashiny_ctx.ui.notification_show(
            f" AnnData probe completed: {info['n_cells']} cells / {info['n_genes']} variables",
            type="message",
        )

    _spashiny_ctx.probe_adata = probe_adata

    @_spashiny_ctx.output
    @_spashiny_ctx.render.text
    def adata_overview():
        info = _spashiny_ctx.adata_probe_info_rv.get()
        if info is None:
            return "AnnData has not been probed yet."
        return f"Cells: {info['n_cells']}\nGenes: {info['n_genes']}\nObs fields: {len(info['obs_keys'])}\nUns keys: {len(info['uns_keys'])}\nObsm keys: {len(info['obsm_keys'])}"

    _spashiny_ctx.adata_overview = adata_overview

    @_spashiny_ctx.output
    @_spashiny_ctx.render.ui
    def obs_key_selector():
        info = _spashiny_ctx.adata_probe_info_rv.get()
        if info is None:
            return _spashiny_ctx.ui.markdown("_Please click 'Probe Current AnnData' first_")
        return _spashiny_ctx.ui.input_select(
            "selected_obs_key", "Select one obs field", choices=info["obs_keys"]
        )

    _spashiny_ctx.obs_key_selector = obs_key_selector

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.btn_inspect_obs)
    def inspect_selected_obs():
        adata_global = _spashiny_ctx.trajectory_adata_rv.get()
        info = _spashiny_ctx.adata_probe_info_rv.get()
        if info is None or adata_global is None:
            _spashiny_ctx.obs_summary_rv.set("Data has not been probed yet.")
            return
        key = _spashiny_ctx.input.selected_obs_key()
        if not key or key not in adata_global.obs.columns:
            _spashiny_ctx.obs_summary_rv.set("Please select a valid obs field.")
            return
        col = adata_global.obs[key]
        if _spashiny_ctx.pd.api.types.is_numeric_dtype(col):
            txt = f"Field: {key}\nType: Numeric\nMinimum: {float(col.min()):.4g}\nMaximum: {float(col.max()):.4g}\nMean: {float(col.mean()):.4g}"
        else:
            vc = col.astype(str).value_counts(dropna=True).head(10)
            txt = (
                f"Field: {key}\nType: Categorical\nNumber of categories: {col.astype(str).nunique(dropna=True)}\n\n"
                + "\n".join([f"{k}: {v}" for k, v in vc.items()])
            )
        _spashiny_ctx.obs_summary_rv.set(txt)

    _spashiny_ctx.inspect_selected_obs = inspect_selected_obs

    @_spashiny_ctx.output
    @_spashiny_ctx.render.text
    def obs_summary():
        return _spashiny_ctx.obs_summary_rv.get()

    _spashiny_ctx.obs_summary = obs_summary

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.btn_probe_adata1)
    def fill_roi_selector_from_dash():
        adata_global = _spashiny_ctx.trajectory_adata_rv.get()
        if adata_global is None:
            _spashiny_ctx.ui.notification_show(
                "No Dash-transferred AnnData detected. Please run Plotly / Dash first.",
                type="error",
            )
            return
        valid_cols = _spashiny_ctx.get_valid_roi_columns(adata_global)
        if len(valid_cols) == 0:
            _spashiny_ctx.ui.update_select(
                "roi_obs_key",
                choices={"": "No valid ROI / annotation columns found"},
                selected="",
                session=_spashiny_ctx.session,
            )
            _spashiny_ctx.ui.notification_show(
                "No valid ROI / annotation columns were found after filtering system columns.",
                type="error",
            )
            return
        preferred = None
        for cand in ["area", "roi", "ROI", "annotation", "region", "group"]:
            if cand in valid_cols:
                preferred = cand
                break
        if preferred is None:
            preferred = valid_cols[0]
        _spashiny_ctx.ui.update_select(
            "roi_obs_key", choices=valid_cols, selected=preferred, session=_spashiny_ctx.session
        )
        _spashiny_ctx.ui.notification_show(
            f"ROI field list refreshed: {len(valid_cols)} valid columns available", type="message"
        )

    _spashiny_ctx.fill_roi_selector_from_dash = fill_roi_selector_from_dash

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.btn_show_roi)
    def handle_show_roi_info():
        adata_global = _spashiny_ctx.trajectory_adata_rv.get()
        key = _spashiny_ctx.input.roi_obs_key()
        if adata_global is None:
            _spashiny_ctx.ui.notification_show("Data is not loaded", type="error")
            return
        ok, msg = _spashiny_ctx.is_valid_roi_column(adata_global, key)
        if not ok:
            _spashiny_ctx.ui.notification_show(f"{msg}", type="error")
            return
        counts = adata_global.obs[key].astype(str).value_counts(dropna=True).reset_index()
        counts.columns = ["ROI name", "Cell count"]
        _spashiny_ctx.roi_table_data.set(counts)
        _spashiny_ctx.ui.notification_show(f"ROI information updated: {key}", type="message")

    _spashiny_ctx.handle_show_roi_info = handle_show_roi_info

    @_spashiny_ctx.output
    @_spashiny_ctx.render.data_frame
    def roi_counts_table():
        df = _spashiny_ctx.roi_table_data.get()
        if df is None:
            df = _spashiny_ctx.pd.DataFrame(
                {"Message": ["Please click 'Show ROI Information' first."]}
            )
        return _spashiny_ctx.render.DataTable(df, editable=False)

    _spashiny_ctx.roi_counts_table = roi_counts_table

    @_spashiny_ctx.render.download(filename=lambda: "roi_counts.csv")
    def download_roi_counts_csv():
        df = _spashiny_ctx.roi_table_data.get()
        if df is None:
            df = _spashiny_ctx.pd.DataFrame(
                {"Message": ["Please click 'Show ROI Information' first."]}
            )
        yield df.to_csv(index=False).encode("utf-8-sig")

    _spashiny_ctx.download_roi_counts_csv = download_roi_counts_csv

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.btn_run_roi_analysis)
    def run_roi_analysis():
        if not _spashiny_ctx._downstream_click_guard("btn_run_roi_analysis", "Run ROI Analysis"):
            return
        adata_global = _spashiny_ctx.trajectory_adata_rv.get()
        roi_col = _spashiny_ctx.input.roi_obs_key()
        if adata_global is None:
            _spashiny_ctx.ui.notification_show(
                "Data is not loaded. Please run Plotly / Dash first.", type="error"
            )
            return
        ok, msg = _spashiny_ctx.is_valid_roi_column(adata_global, roi_col)
        if not ok:
            _spashiny_ctx.ui.notification_show(f"{msg}", type="error")
            return
        _spashiny_ctx._show_downstream_action_modal(
            "Running ROI Analysis...",
            "Computing ROI summaries, differential markers, and ROI plots.",
        )
        try:
            joint_adata_ROI = adata_global.copy()
            joint_adata_ROI.obs[roi_col] = joint_adata_ROI.obs[roi_col].astype(str)
            roi_counts = joint_adata_ROI.obs[roi_col].value_counts(dropna=True)
            roi_count_df = roi_counts.reset_index()
            roi_count_df.columns = ["ROI name", "Cell count"]
            _spashiny_ctx.roi_table_data.set(roi_count_df)
            all_cats = joint_adata_ROI.obs[roi_col].astype(str).unique().tolist()
            color_pool = _spashiny_globals.sc.pl.palettes.default_102
            my_palette = {}
            color_idx = 0
            for cat in all_cats:
                cat_str = str(cat)
                if cat_str == "undefined":
                    my_palette[cat_str] = "#FFFFFF"
                else:
                    my_palette[cat_str] = color_pool[color_idx % len(color_pool)]
                    color_idx += 1
            _spashiny_globals.plt.close("all")
            try:
                _spashiny_globals.sc.pl.spatial(
                    joint_adata_ROI,
                    img_key="hires",
                    color=[roi_col],
                    show=False,
                    alpha_img=0.8,
                    size=1.2,
                    palette=my_palette,
                )
            except Exception:
                _spashiny_globals.sc.pl.embedding(
                    joint_adata_ROI, basis="spatial", color=roi_col, show=False, palette=my_palette
                )
            _spashiny_globals.plt.title(f"Spatial ROI: {roi_col}")
            fig1 = _spashiny_globals.plt.gcf()
            joint_adata_ROI_filter = joint_adata_ROI[
                joint_adata_ROI.obs[roi_col].astype(str) != "undefined"
            ].copy()
            if joint_adata_ROI_filter.n_obs == 0:
                raise ValueError("No cells/spots remain after filtering out 'undefined'.")
            joint_adata_ROI_filter.obs[roi_col] = joint_adata_ROI_filter.obs[roi_col].astype(
                "category"
            )
            joint_adata_ROI_filter.obs[roi_col] = joint_adata_ROI_filter.obs[
                roi_col
            ].cat.remove_unused_categories()
            safe_roi_col = "".join([c if c.isalnum() or c == "_" else "_" for c in str(roi_col)])
            key_st = f"rank_genes_groups_by{safe_roi_col}"
            key_sm = f"rank_metabolites_groups_by{safe_roi_col}"
            _spashiny_globals.smt.pp.rank_gene_and_metabolite_groups(
                joint_adata_ROI_filter,
                groupby_ST=roi_col,
                groupby_SM=roi_col,
                key_added_ST=key_st,
                key_added_SM=key_sm,
                method="t-test",
            )
            gene_df = _spashiny_ctx.pd.DataFrame(joint_adata_ROI_filter.uns[key_st]["names"]).head(
                5
            )
            ST_marker_feature_list = [
                gene_df[col].dropna().astype(str).tolist() for col in gene_df.columns
            ]
            metabolite_df = _spashiny_ctx.pd.DataFrame(
                joint_adata_ROI_filter.uns[key_sm]["names"]
            ).head(3)
            SM_marker_feature_list = [
                metabolite_df[col].dropna().astype(str).tolist() for col in metabolite_df.columns
            ]
            filtered_cats = joint_adata_ROI_filter.obs[roi_col].astype(str).unique().tolist()
            filtered_palette = {k: v for k, v in my_palette.items() if k in filtered_cats}
            _spashiny_globals.plt.close("all")
            _spashiny_globals.smt.pl.plot_marker_gene_metabolite(
                joint_adata_ROI_filter,
                groupby=roi_col,
                palette=filtered_palette,
                ST_marker_feature_list=ST_marker_feature_list,
                SM_marker_feature_list=SM_marker_feature_list,
                figsize=(5, 4),
                key_ST=key_st,
                key_SM=key_sm,
            )
            fig2 = _spashiny_globals.plt.gcf()
            _spashiny_ctx.roi_spatial_fig_rv.set(fig1)
            _spashiny_ctx.roi_marker_fig_rv.set(fig2)
            _spashiny_ctx.roi_last_result_rv.set(
                {
                    "roi_col": roi_col,
                    "key_st": key_st,
                    "key_sm": key_sm,
                    "palette": my_palette,
                    "filtered_palette": filtered_palette,
                    "ST_marker_feature_list": ST_marker_feature_list,
                    "SM_marker_feature_list": SM_marker_feature_list,
                }
            )
            _spashiny_ctx.ui.notification_show(
                "ROI analysis completed. Figures have been updated in the page.", type="message"
            )
        except Exception as e:
            _spashiny_ctx.ui.notification_show(f"ROI analysis failed: {e}", type="error")
            _spashiny_ctx.traceback.print_exc()
        finally:
            _spashiny_ctx.ui.modal_remove()

    _spashiny_ctx.run_roi_analysis = run_roi_analysis

    @_spashiny_ctx.output
    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("roi_spatial_plot")
    def roi_spatial_plot():
        fig = _spashiny_ctx.roi_spatial_fig_rv.get()
        if fig is None:
            fig, ax = _spashiny_globals.plt.subplots(figsize=(6, 5))
            ax.text(
                0.5,
                0.5,
                "No ROI spatial plot yet.",
                ha="center",
                va="center",
                transform=ax.transAxes,
            )
            ax.axis("off")
            return fig
        return fig

    _spashiny_ctx.roi_spatial_plot = roi_spatial_plot

    @_spashiny_ctx.output
    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("roi_marker_plot")
    def roi_marker_plot():
        fig = _spashiny_ctx.roi_marker_fig_rv.get()
        if fig is None:
            fig, ax = _spashiny_globals.plt.subplots(figsize=(6, 5))
            ax.text(
                0.5,
                0.5,
                "No ROI marker feature plot yet.",
                ha="center",
                va="center",
                transform=ax.transAxes,
            )
            ax.axis("off")
            return fig
        return fig

    _spashiny_ctx.roi_marker_plot = roi_marker_plot

    @_spashiny_ctx.render.download(filename=lambda: "roi_spatial_plot.pdf")
    def download_roi_spatial_pdf():
        fig = _spashiny_ctx.roi_spatial_fig_rv.get()
        buf = _spashiny_ctx.io.BytesIO()
        with _spashiny_ctx.PdfPages(buf) as pdf:
            if fig is None:
                empty_fig, ax = _spashiny_globals.plt.subplots(figsize=(8.27, 11.69))
                ax.axis("off")
                ax.text(
                    0.5,
                    0.5,
                    "No ROI spatial figure available.\nPlease run ROI analysis first.",
                    ha="center",
                    va="center",
                    fontsize=16,
                )
                pdf.savefig(empty_fig, bbox_inches="tight")
                _spashiny_globals.plt.close(empty_fig)
            else:
                pdf.savefig(fig, bbox_inches="tight")
        buf.seek(0)
        yield buf.read()

    _spashiny_ctx.download_roi_spatial_pdf = download_roi_spatial_pdf

    @_spashiny_ctx.render.download(filename=lambda: "roi_marker_plot.pdf")
    def download_roi_marker_pdf():
        fig = _spashiny_ctx.roi_marker_fig_rv.get()
        buf = _spashiny_ctx.io.BytesIO()
        with _spashiny_ctx.PdfPages(buf) as pdf:
            if fig is None:
                empty_fig, ax = _spashiny_globals.plt.subplots(figsize=(8.27, 11.69))
                ax.axis("off")
                ax.text(
                    0.5,
                    0.5,
                    "No ROI marker figure available.\nPlease run ROI analysis first.",
                    ha="center",
                    va="center",
                    fontsize=16,
                )
                pdf.savefig(empty_fig, bbox_inches="tight")
                _spashiny_globals.plt.close(empty_fig)
            else:
                pdf.savefig(fig, bbox_inches="tight")
        buf.seek(0)
        yield buf.read()

    _spashiny_ctx.download_roi_marker_pdf = download_roi_marker_pdf

    @_spashiny_ctx.render.download(
        filename=lambda: (
            f"roi_full_report_{_spashiny_ctx.roi_last_result_rv.get().get('roi_col', 'unknown')}.pdf"
            if _spashiny_ctx.roi_last_result_rv.get() is not None
            else "roi_full_report.pdf"
        )
    )
    def download_roi_full_pdf():
        spatial_fig = _spashiny_ctx.roi_spatial_fig_rv.get()
        marker_fig = _spashiny_ctx.roi_marker_fig_rv.get()
        roi_info = _spashiny_ctx.roi_last_result_rv.get()
        roi_table = _spashiny_ctx.roi_table_data.get()
        buf = _spashiny_ctx.io.BytesIO()
        with _spashiny_ctx.PdfPages(buf) as pdf:
            cover_fig, ax = _spashiny_globals.plt.subplots(figsize=(8.27, 11.69))
            ax.axis("off")
            roi_col = "None"
            key_st = "None"
            key_sm = "None"
            if roi_info is not None:
                roi_col = roi_info.get("roi_col", "None")
                key_st = roi_info.get("key_st", "None")
                key_sm = roi_info.get("key_sm", "None")
            ax.text(
                0.5,
                0.82,
                "ROI Analysis Report",
                ha="center",
                va="center",
                fontsize=20,
                fontweight="bold",
            )
            ax.text(0.5, 0.68, f"ROI Column: {roi_col}", ha="center", va="center", fontsize=13)
            ax.text(0.5, 0.62, f"Gene Marker Key: {key_st}", ha="center", va="center", fontsize=11)
            ax.text(
                0.5, 0.57, f"Metabolite Marker Key: {key_sm}", ha="center", va="center", fontsize=11
            )
            if roi_table is not None and len(roi_table) > 0:
                summary_lines = []
                for _, row in roi_table.head(12).iterrows():
                    summary_lines.append(f"{row.iloc[0]}: {row.iloc[1]}")
                ax.text(
                    0.5,
                    0.38,
                    "ROI Counts\n\n" + "\n".join(summary_lines),
                    ha="center",
                    va="center",
                    fontsize=11,
                )
            pdf.savefig(cover_fig, bbox_inches="tight")
            _spashiny_globals.plt.close(cover_fig)
            if spatial_fig is not None:
                pdf.savefig(spatial_fig, bbox_inches="tight")
            else:
                empty_fig, ax = _spashiny_globals.plt.subplots(figsize=(8.27, 11.69))
                ax.axis("off")
                ax.text(
                    0.5,
                    0.5,
                    "No ROI spatial figure available.",
                    ha="center",
                    va="center",
                    fontsize=16,
                )
                pdf.savefig(empty_fig, bbox_inches="tight")
                _spashiny_globals.plt.close(empty_fig)
            if marker_fig is not None:
                pdf.savefig(marker_fig, bbox_inches="tight")
            else:
                empty_fig, ax = _spashiny_globals.plt.subplots(figsize=(8.27, 11.69))
                ax.axis("off")
                ax.text(
                    0.5,
                    0.5,
                    "No ROI marker figure available.",
                    ha="center",
                    va="center",
                    fontsize=16,
                )
                pdf.savefig(empty_fig, bbox_inches="tight")
                _spashiny_globals.plt.close(empty_fig)
        buf.seek(0)
        yield buf.read()

    _spashiny_ctx.download_roi_full_pdf = download_roi_full_pdf


_STEPS = (_install_0,)


def server(_spashiny_ctx, step=0):
    return _STEPS[step](_spashiny_ctx)
