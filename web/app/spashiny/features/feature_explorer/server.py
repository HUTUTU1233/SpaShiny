# Extracted from /app/app/ST-SM.py. Feature: feature_explorer; ordered phases preserve original initialization.
from spashiny._shared import runtime_globals as _spashiny_globals


def _install_0(_spashiny_ctx):
    import matplotlib.pyplot as plt

    _spashiny_globals.plt = plt
    import numpy as np

    _spashiny_globals.np = np
    import scipy.sparse as sp

    _spashiny_ctx.sp = sp
    import re

    _spashiny_ctx.re = re
    import scanpy as sc

    _spashiny_globals.sc = sc
    _spashiny_ctx.selected_features = _spashiny_ctx.reactive.Value([])
    _spashiny_ctx.feature_map_status = _spashiny_ctx.reactive.Value(
        "Waiting for feature selection..."
    )

    def blank_plot():
        fig, ax = _spashiny_globals.plt.subplots(figsize=(8, 4))
        ax.axis("off")
        return fig

    _spashiny_ctx.blank_plot = blank_plot

    def extract_feature_values(adata, feature, layer="normalized"):
        if feature not in adata.var_names:
            return None
        vals = adata[:, feature].layers[layer] if layer in adata.layers else adata[:, feature].X
        if _spashiny_ctx.sp.issparse(vals):
            vals = vals.toarray().flatten()
        else:
            vals = _spashiny_globals.np.asarray(vals).flatten()
        return vals

    _spashiny_ctx.extract_feature_values = extract_feature_values

    def is_mz_feature(x):
        """ """
        x = str(x).strip()
        if _spashiny_ctx.re.fullmatch("\\d+(\\.\\d+)?", x):
            return True
        if _spashiny_ctx.re.fullmatch("(?i)(mz[_-]?|m)?\\d+(\\.\\d+)?", x):
            return True
        return False

    _spashiny_ctx.is_mz_feature = is_mz_feature

    def split_st_sm_features(adata):
        all_features = [str(x) for x in adata.var_names.tolist()]
        sm_features = [x for x in all_features if _spashiny_ctx.is_mz_feature(x)]
        st_features = [x for x in all_features if x not in sm_features]
        return (st_features, sm_features)

    _spashiny_ctx.split_st_sm_features = split_st_sm_features
    _spashiny_ctx.feature_choices_loaded = _spashiny_ctx.reactive.Value(False)

    def _feature_explorer_st_sm_features():
        """Read feature metadata from the persisted JointVAE result only."""
        adata, should_close = _spashiny_ctx.get_joint_vae_result_for_display()
        if adata is None:
            return ([], [])
        try:
            return _spashiny_ctx.split_st_sm_features(adata)
        finally:
            _spashiny_globals.close_display_h5ad(adata, should_close)

    _spashiny_ctx._feature_explorer_st_sm_features = _feature_explorer_st_sm_features

    @_spashiny_ctx.reactive.Effect
    def update_feature_select_choices():
        st_features, sm_features = _spashiny_ctx._feature_explorer_st_sm_features()
        if not st_features and (not sm_features):
            _spashiny_ctx.feature_choices_loaded.set(False)
            return
        if _spashiny_ctx.feature_choices_loaded.get():
            return
        try:
            _spashiny_ctx.ui.update_selectize(
                "selected_st_feature",
                choices=st_features,
                selected=st_features[0] if len(st_features) > 0 else None,
            )
            _spashiny_ctx.ui.update_selectize(
                "selected_sm_feature",
                choices=sm_features,
                selected=sm_features[0] if len(sm_features) > 0 else None,
            )
            _spashiny_ctx.feature_choices_loaded.set(True)
            _spashiny_ctx.log(
                f" [Feature Explorer] Loaded {len(st_features)} ST features and {len(sm_features)} SM features"
            )
        except Exception as e:
            _spashiny_ctx.ui.modal_show(
                _spashiny_ctx.ui.modal(
                    f"Failed to load feature list.\n\nError: {str(e)}",
                    title="Feature Explorer Error",
                    easy_close=True,
                    footer=_spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.input_action_button(
                            "close_modal_feature_load_error", "Close", class_="btn btn-secondary"
                        )
                    ),
                )
            )

    _spashiny_ctx.update_feature_select_choices = update_feature_select_choices
    _spashiny_ctx.selected_features = _spashiny_ctx.reactive.Value([])
    _spashiny_ctx.feature_map_status_val = _spashiny_ctx.reactive.Value(
        "Waiting for feature selection..."
    )

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.generate_feature_maps)
    def update_selected_features():
        st_features, sm_features = _spashiny_ctx._feature_explorer_st_sm_features()
        all_features = set(st_features) | set(sm_features)
        if not all_features:
            _spashiny_ctx.feature_map_status_val.set("Please complete post-processing first.")
            _spashiny_ctx.selected_features.set([])
            _spashiny_ctx.ui.modal_show(
                _spashiny_ctx.ui.modal(
                    "No processed VAE result found. Please complete post-processing analysis first.",
                    title="Feature Explorer Error",
                    easy_close=True,
                    footer=_spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.input_action_button(
                            "close_modal_feature_no_data", "Close", class_="btn btn-secondary"
                        )
                    ),
                )
            )
            return
        st_feature = _spashiny_ctx.input.selected_st_feature()
        sm_feature = _spashiny_ctx.input.selected_sm_feature()
        chosen = []
        if st_feature is not None and str(st_feature).strip() != "":
            if st_feature in all_features:
                chosen.append(st_feature)
        if sm_feature is not None and str(sm_feature).strip() != "":
            if sm_feature in all_features:
                chosen.append(sm_feature)
        if len(chosen) == 0:
            auto_st = st_features[0] if len(st_features) > 0 else None
            auto_sm = sm_features[0] if len(sm_features) > 0 else None
            if auto_st:
                chosen.append(auto_st)
            if auto_sm:
                chosen.append(auto_sm)
            if len(chosen) == 0:
                _spashiny_ctx.feature_map_status_val.set(
                    "No valid ST/SM features found in adata.var_names"
                )
                _spashiny_ctx.selected_features.set([])
                _spashiny_ctx.ui.modal_show(
                    _spashiny_ctx.ui.modal(
                        "No valid ST gene or SM m/z feature could be found in adata.var_names.",
                        title="Feature Explorer Error",
                        easy_close=True,
                        footer=_spashiny_ctx.ui.div(
                            _spashiny_ctx.ui.input_action_button(
                                "close_modal_feature_none_found",
                                "Close",
                                class_="btn btn-secondary",
                            )
                        ),
                    )
                )
                return
            _spashiny_ctx.feature_map_status_val.set(
                f" No feature selected. Auto-selected: {', '.join(chosen)}"
            )
            _spashiny_ctx.selected_features.set(chosen)
            _spashiny_ctx.log(f" [Feature Explorer] Auto-selected features: {', '.join(chosen)}")
            return
        _spashiny_ctx.selected_features.set(chosen)
        _spashiny_ctx.feature_map_status_val.set(f"Selected features: {', '.join(chosen)}")
        _spashiny_ctx.log(f" [Feature Explorer] Selected features: {', '.join(chosen)}")

    _spashiny_ctx.update_selected_features = update_selected_features

    def _spatialmeta_feature_map_figure(adata, features, *, layer):
        """Reproduce SpatialMETA's Scanpy spatial call without UI-added styling.

        The selected ST gene and SM m/z are submitted together in ``color``.
        Scanpy therefore controls axes, legends, aspect, tissue orientation, and
        layout exactly as in the original SpatialMETA plotting workflow.
        """
        import matplotlib.pyplot as plt
        import seaborn as _seaborn
        import scanpy as sc

        if adata is None:
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.text(
                0.5,
                0.5,
                "Please complete post-processing first.",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=14,
            )
            ax.axis("off")
            return fig
        valid_features = [str(feature) for feature in features if str(feature) in adata.var_names]
        if not valid_features:
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.text(
                0.5,
                0.5,
                "No selected feature is available in this result.",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=14,
            )
            ax.axis("off")
            return fig
        if layer not in adata.layers:
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.text(
                0.5,
                0.5,
                f"Required SpatialMETA layer is unavailable: {layer}",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=13,
            )
            ax.axis("off")
            return fig
        try:
            sc.pl.spatial(
                adata,
                img_key="hires",
                color_map="vlag",
                color=valid_features,
                layer=layer,
                show=False,
            )
            return plt.gcf()
        except Exception as exc:
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.text(
                0.5,
                0.5,
                f"SpatialMETA plotting failed:\n{exc}",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=12,
            )
            ax.axis("off")
            return fig

    _spashiny_ctx._spatialmeta_feature_map_figure = _spatialmeta_feature_map_figure

    def make_feature_original_figure(adata, features):
        return _spashiny_ctx._spatialmeta_feature_map_figure(adata, features, layer="normalized")

    _spashiny_ctx.make_feature_original_figure = make_feature_original_figure

    def make_feature_reconstruction_figure(adata, features):
        return _spashiny_ctx._spatialmeta_feature_map_figure(
            adata, features, layer="reconstruction"
        )

    _spashiny_ctx.make_feature_reconstruction_figure = make_feature_reconstruction_figure

    @_spashiny_ctx.output
    @_spashiny_ctx.render.plot
    def feature_original_plot():
        adata, should_close = _spashiny_ctx.get_joint_vae_result_for_display()
        try:
            return _spashiny_ctx.make_feature_original_figure(
                adata, _spashiny_ctx.selected_features.get()
            )
        finally:
            _spashiny_globals.close_display_h5ad(adata, should_close)

    _spashiny_ctx.feature_original_plot = feature_original_plot

    @_spashiny_ctx.output
    @_spashiny_ctx.render.plot
    def feature_reconstruction_plot():
        adata, should_close = _spashiny_ctx.get_joint_vae_result_for_display()
        try:
            return _spashiny_ctx.make_feature_reconstruction_figure(
                adata, _spashiny_ctx.selected_features.get()
            )
        finally:
            _spashiny_globals.close_display_h5ad(adata, should_close)

    _spashiny_ctx.feature_reconstruction_plot = feature_reconstruction_plot

    @_spashiny_ctx.render.download(filename="feature_original_expression.pdf")
    def download_feature_original_pdf():
        import io
        import matplotlib.pyplot as plt

        adata, should_close = _spashiny_ctx.get_joint_vae_result_for_display()
        try:
            fig = _spashiny_ctx.make_feature_original_figure(
                adata, _spashiny_ctx.selected_features.get()
            )
            buf = io.BytesIO()
            _spashiny_globals.save_native_figure(fig, buf, format="pdf", bbox_inches="tight")
            plt.close(fig)
            buf.seek(0)
            payload = buf.read()
        finally:
            _spashiny_globals.close_display_h5ad(adata, should_close)
        yield payload

    _spashiny_ctx.download_feature_original_pdf = download_feature_original_pdf

    @_spashiny_ctx.render.download(filename="feature_reconstructed_expression.pdf")
    def download_feature_reconstruction_pdf():
        import io
        import matplotlib.pyplot as plt

        adata, should_close = _spashiny_ctx.get_joint_vae_result_for_display()
        try:
            fig = _spashiny_ctx.make_feature_reconstruction_figure(
                adata, _spashiny_ctx.selected_features.get()
            )
            buf = io.BytesIO()
            _spashiny_globals.save_native_figure(fig, buf, format="pdf", bbox_inches="tight")
            plt.close(fig)
            buf.seek(0)
            payload = buf.read()
        finally:
            _spashiny_globals.close_display_h5ad(adata, should_close)
        yield payload

    _spashiny_ctx.download_feature_reconstruction_pdf = download_feature_reconstruction_pdf

    @_spashiny_ctx.render.download(filename="feature_comparison_report.pdf")
    def download_feature_comparison_pdf():
        import io
        import matplotlib.pyplot as plt
        from cloud.figure_export import EditablePdfPages as PdfPages

        adata = _spashiny_ctx.vae_processed_adata.get()
        features = _spashiny_ctx.selected_features.get()
        buf = io.BytesIO()
        with PdfPages(buf) as pdf:
            fig1 = _spashiny_ctx.make_feature_original_figure(adata, features)
            pdf.savefig(fig1, bbox_inches="tight")
            plt.close(fig1)
            fig2 = _spashiny_ctx.make_feature_reconstruction_figure(adata, features)
            pdf.savefig(fig2, bbox_inches="tight")
            plt.close(fig2)
        buf.seek(0)
        yield buf.read()

    _spashiny_ctx.download_feature_comparison_pdf = download_feature_comparison_pdf

    @_spashiny_ctx.render.download(filename="feature_current_maps.pdf")
    def download_feature_maps_pdf():
        import io
        import matplotlib.pyplot as plt
        from cloud.figure_export import EditablePdfPages as PdfPages

        adata = _spashiny_ctx.vae_processed_adata.get()
        features = _spashiny_ctx.selected_features.get()
        buf = io.BytesIO()
        with PdfPages(buf) as pdf:
            fig1 = _spashiny_ctx.make_feature_original_figure(adata, features)
            pdf.savefig(fig1, bbox_inches="tight")
            plt.close(fig1)
            fig2 = _spashiny_ctx.make_feature_reconstruction_figure(adata, features)
            pdf.savefig(fig2, bbox_inches="tight")
            plt.close(fig2)
        buf.seek(0)
        yield buf.read()

    _spashiny_ctx.download_feature_maps_pdf = download_feature_maps_pdf

    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("modality_contribution_violin_plot")
    def modality_contribution_violin_plot():
        try:
            return _spashiny_ctx.make_modality_contribution_violin_figure()
        except NameError:
            pass
        adata = _spashiny_ctx.vae_processed_adata.get()
        if adata is None:
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(figsize=(8, 6))
            ax.text(
                0.5,
                0.5,
                "Please complete the post-processing analysis first.",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=14,
            )
            ax.set_title(
                "The distribution of the contribution degrees of ST/SM modes in VAE clustering"
            )
            plt.tight_layout()
            return fig
        import matplotlib.pyplot as plt
        import pandas as pd
        import seaborn as sns

        obs_df = adata.obs
        cluster_key = _spashiny_globals.find_vae_cluster_key(adata)
        required = [cluster_key, "contribution_st", "contribution_sm"] if cluster_key else []
        if not cluster_key or any((col not in obs_df.columns for col in required)):
            fig, ax = plt.subplots(figsize=(8, 6))
            ax.text(
                0.5,
                0.5,
                "Required contribution columns are not available.",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=14,
            )
            ax.set_title("Modality Contribution Analysis")
            plt.tight_layout()
            return fig
        obs_filter_df = pd.concat(
            [
                obs_df[[cluster_key, "contribution_st"]]
                .rename(columns={"contribution_st": "contribution"})
                .assign(type="st"),
                obs_df[[cluster_key, "contribution_sm"]]
                .rename(columns={"contribution_sm": "contribution"})
                .assign(type="sm"),
            ]
        )
        fig, ax = plt.subplots(figsize=(12, 6))
        sns.violinplot(
            data=obs_filter_df,
            x=cluster_key,
            y="contribution",
            hue="type",
            split=True,
            inner="quart",
            palette=["#2ec4b6", "#FFCC70"],
            scale="width",
            bw=0.2,
            cut=0,
            ax=ax,
        )
        ax.set_xticklabels(ax.get_xticklabels(), rotation=90)
        ax.set_title(
            "The distribution of the contribution degrees of ST/SM modes in VAE clustering"
        )
        ax.set_xlabel("VAE Clustering")
        ax.set_ylabel("Contribution degree")
        plt.tight_layout()
        return fig

    _spashiny_ctx.modality_contribution_violin_plot = modality_contribution_violin_plot

    def make_modality_contribution_violin_figure():
        adata, should_close = _spashiny_ctx.get_joint_vae_result_for_display()
        if adata is None:
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(figsize=(8, 6))
            ax.text(
                0.5,
                0.5,
                "Please complete the post-processing analysis first.",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=14,
            )
            ax.set_title(
                "The distribution of the contribution degrees of ST/SM modes in VAE clustering"
            )
            plt.tight_layout()
            return fig
        import matplotlib.pyplot as plt
        import pandas as pd
        import seaborn as sns

        obs_df = adata.obs
        cluster_key = _spashiny_globals.find_vae_cluster_key(adata)
        required = [cluster_key, "contribution_st", "contribution_sm"] if cluster_key else []
        if not cluster_key or any((col not in obs_df.columns for col in required)):
            fig, ax = plt.subplots(figsize=(8, 6))
            ax.text(
                0.5,
                0.5,
                "Required contribution columns are not available.",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=14,
            )
            ax.set_title("Modality Contribution Analysis")
            plt.tight_layout()
            return fig
        obs_filter_df = pd.concat(
            [
                obs_df[[cluster_key, "contribution_st"]]
                .rename(columns={"contribution_st": "contribution"})
                .assign(type="st"),
                obs_df[[cluster_key, "contribution_sm"]]
                .rename(columns={"contribution_sm": "contribution"})
                .assign(type="sm"),
            ]
        )
        fig, ax = plt.subplots(figsize=(12, 6))
        sns.violinplot(
            data=obs_filter_df,
            x=cluster_key,
            y="contribution",
            hue="type",
            split=True,
            inner="quart",
            palette=["#2ec4b6", "#FFCC70"],
            scale="width",
            bw=0.2,
            cut=0,
            ax=ax,
        )
        ax.set_xticklabels(ax.get_xticklabels(), rotation=90)
        ax.set_title(
            "The distribution of the contribution degrees of ST/SM modes in VAE clustering"
        )
        ax.set_xlabel("VAE Clustering")
        ax.set_ylabel("Contribution degree")
        plt.tight_layout()
        _spashiny_globals.close_display_h5ad(adata, should_close)
        return fig

    _spashiny_ctx.make_modality_contribution_violin_figure = (
        make_modality_contribution_violin_figure
    )

    @_spashiny_ctx.render.download(filename="vae_modality_contribution_violin_plot.pdf")
    def download_modality_violin_pdf():
        import io
        import matplotlib.pyplot as plt

        fig = _spashiny_ctx.make_modality_contribution_violin_figure()
        buf = io.BytesIO()
        _spashiny_globals.save_native_figure(fig, buf, format="pdf", bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        yield buf.read()

    _spashiny_ctx.download_modality_violin_pdf = download_modality_violin_pdf

    @_spashiny_ctx.output
    @_spashiny_ctx.render.data_frame
    def cluster_statistics():
        import pandas as pd
        import numpy as np

        adata, should_close = _spashiny_ctx.get_joint_vae_result_for_display()
        if adata is None:
            return pd.DataFrame(
                {
                    "Cluster": [],
                    "Cell Count": [],
                    "Mean ST Contribution": [],
                    "Mean SM Contribution": [],
                    "ST Contribution SD": [],
                    "SM Contribution SD": [],
                }
            )
        cluster_key = _spashiny_globals.find_vae_cluster_key(adata)
        required_obs_cols = (
            [cluster_key, "contribution_st", "contribution_sm"] if cluster_key else []
        )
        missing_cols = [col for col in required_obs_cols if col not in adata.obs.columns]
        if not cluster_key or missing_cols:
            _spashiny_ctx.log(f" Missing columns for cluster statistics: {missing_cols}")
            return pd.DataFrame(
                {"Error": ["Required VAE cluster/contribution columns are missing."]}
            )
        cluster_stats = []
        try:
            clusters = sorted(pd.Series(adata.obs[cluster_key]).dropna().unique())
            for cluster in clusters:
                cluster_mask = adata.obs[cluster_key] == cluster
                cluster_data = adata[cluster_mask]
                st_vals = pd.to_numeric(cluster_data.obs["contribution_st"], errors="coerce")
                sm_vals = pd.to_numeric(cluster_data.obs["contribution_sm"], errors="coerce")
                stats = {
                    "Cluster": str(cluster),
                    "Cell Count": int(cluster_data.n_obs),
                    "Mean ST Contribution": round(float(np.nanmean(st_vals)), 4),
                    "Mean SM Contribution": round(float(np.nanmean(sm_vals)), 4),
                    "ST Contribution SD": round(float(np.nanstd(st_vals)), 4),
                    "SM Contribution SD": round(float(np.nanstd(sm_vals)), 4),
                }
                cluster_stats.append(stats)
            if len(cluster_stats) == 0:
                _spashiny_globals.close_display_h5ad(adata, should_close)
                return pd.DataFrame({"Message": ["No clusters available for summary."]})
            result_df = pd.DataFrame(cluster_stats)
            _spashiny_globals.close_display_h5ad(adata, should_close)
            return result_df
        except Exception as e:
            _spashiny_ctx.log(f"Failed to generate cluster statistics: {str(e)}")
            return pd.DataFrame({"Error": [f"Failed to generate cluster statistics: {str(e)}"]})

    _spashiny_ctx.cluster_statistics = cluster_statistics

    def build_cluster_statistics_dataframe():
        import pandas as pd
        import numpy as np

        adata, should_close = _spashiny_ctx.get_joint_vae_result_for_display()
        if adata is None:
            return pd.DataFrame(
                {
                    "Cluster": [],
                    "Cell Count": [],
                    "Mean ST Contribution": [],
                    "Mean SM Contribution": [],
                    "ST Contribution SD": [],
                    "SM Contribution SD": [],
                }
            )
        cluster_key = _spashiny_globals.find_vae_cluster_key(adata)
        required_obs_cols = (
            [cluster_key, "contribution_st", "contribution_sm"] if cluster_key else []
        )
        if not cluster_key or any((col not in adata.obs.columns for col in required_obs_cols)):
            _spashiny_globals.close_display_h5ad(adata, should_close)
            return pd.DataFrame(
                {"Error": ["Required VAE cluster/contribution columns are missing."]}
            )
        rows = []
        for cluster in sorted(pd.Series(adata.obs[cluster_key]).dropna().unique()):
            cluster_mask = adata.obs[cluster_key] == cluster
            cluster_data = adata[cluster_mask]
            st_vals = pd.to_numeric(cluster_data.obs["contribution_st"], errors="coerce")
            sm_vals = pd.to_numeric(cluster_data.obs["contribution_sm"], errors="coerce")
            rows.append(
                {
                    "Cluster": str(cluster),
                    "Cell Count": int(cluster_data.n_obs),
                    "Mean ST Contribution": round(float(np.nanmean(st_vals)), 4),
                    "Mean SM Contribution": round(float(np.nanmean(sm_vals)), 4),
                    "ST Contribution SD": round(float(np.nanstd(st_vals)), 4),
                    "SM Contribution SD": round(float(np.nanstd(sm_vals)), 4),
                }
            )
        result_df = pd.DataFrame(rows)
        _spashiny_globals.close_display_h5ad(adata, should_close)
        return result_df

    _spashiny_ctx.build_cluster_statistics_dataframe = build_cluster_statistics_dataframe

    @_spashiny_ctx.render.download(filename=lambda: "cluster_statistics.csv")
    def download_cluster_statistics_csv():
        df = _spashiny_ctx.build_cluster_statistics_dataframe()
        yield df.to_csv(index=False).encode("utf-8-sig")

    _spashiny_ctx.download_cluster_statistics_csv = download_cluster_statistics_csv

    @_spashiny_ctx.session.download(filename=lambda: "vae_analysis_results.h5ad")
    def download_analysis_results():
        result_path = _spashiny_ctx.training_result_path.get()
        if not result_path:
            result_path, _status, _job = _spashiny_ctx._cloud_integration_result_state(
                _spashiny_ctx.training_summary.get() or {},
                workflow_name="vit_single_sample_integration",
            )
        if (
            result_path
            and _spashiny_globals.os.path.isfile(result_path)
            and (_spashiny_globals.os.path.getsize(result_path) > 0)
        ):
            return result_path
        adata = _spashiny_ctx.vae_processed_adata.get()
        if adata is None:
            raise RuntimeError(
                "No completed worker-managed analysis result is available for download."
            )
        import tempfile

        temp_dir = tempfile.mkdtemp()
        output_path = _spashiny_globals.os.path.join(temp_dir, "vae_analysis_results.h5ad")
        adata.write(output_path)
        return output_path

    _spashiny_ctx.download_analysis_results = download_analysis_results
    import os

    _spashiny_globals.os = os
    import re

    _spashiny_ctx.re = re
    import shutil

    _spashiny_ctx.shutil = shutil
    import tempfile

    _spashiny_ctx.tempfile = tempfile
    import traceback

    _spashiny_ctx.traceback = traceback
    from pathlib import Path

    _spashiny_ctx.Path = Path
    from cloud.figure_export import EditablePdfPages as PdfPages

    _spashiny_ctx.PdfPages = PdfPages
    import anndata as ad

    _spashiny_ctx.ad = ad
    import numpy as np

    _spashiny_globals.np = np
    import pandas as pd

    _spashiny_ctx.pd = pd
    import matplotlib.pyplot as plt

    _spashiny_globals.plt = plt
    import scanpy as sc

    _spashiny_globals.sc = sc


_STEPS = (_install_0,)


def server(_spashiny_ctx, step=0):
    return _STEPS[step](_spashiny_ctx)
