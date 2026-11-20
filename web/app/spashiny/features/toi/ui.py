# Actual feature UI extracted from production. Feature: toi.
from spashiny._shared import runtime_globals as _spashiny_globals


def _section_1(_spashiny_ctx):
    return _spashiny_ctx.ui.div(
        {"class": "apple-panel toi-feature-panel", "style": "white-space: normal;"},
        _spashiny_ctx.ui.div("Trajectory Downstream Analysis", class_="apple-section-title"),
        _spashiny_ctx.ui.div(
            {"class": "table-shell mb-3"},
            _spashiny_ctx.ui.div(
                "Step 1: Register Trajectory and Spatial Arrow Plot", class_="plot-title"
            ),
            _spashiny_ctx.ui.layout_columns(
                _spashiny_ctx.ui.input_selectize(
                    "traj_selected_key",
                    "Select an existing TOI",
                    choices=[],
                    selected=None,
                    options={"placeholder": "Draw a TOI in Dash, then refresh...", "create": False},
                ),
                _spashiny_ctx.ui.input_action_button(
                    "btn_refresh_toi", "Refresh TOI list", class_="btn btn-secondary w-100 mt-4"
                ),
                _spashiny_ctx.ui.input_action_button(
                    "btn_run_traj_register",
                    "Run Registration and Arrow Plot",
                    class_="btn btn-primary w-100 mt-4",
                ),
                col_widths=(5, 3, 4),
            ),
            _spashiny_ctx.ui.p(
                "Draw an open trajectory in SpatialMETA Dash, wait for its success message, then refresh this list. Every plot below uses the selected TOI; no trajectory is recomputed.",
                class_="apple-muted mt-2",
            ),
            _spashiny_ctx.ui.output_ui("toi_current_selection"),
            _spashiny_globals.plot_output_with_palette(
                "traj_arrow_plot", height="560px", width="100%"
            ),
        ),
        _spashiny_ctx.ui.div(
            {"class": "table-shell mb-3"},
            _spashiny_ctx.ui.div("SpatialMETA Feature Trajectory", class_="plot-title"),
            _spashiny_ctx.ui.layout_columns(
                _spashiny_ctx.ui.input_numeric(
                    "traj_bins", "Bins", value=100, min=2, max=500, step=1
                ),
                _spashiny_ctx.ui.input_switch("traj_scale", "Scale", value=True),
                col_widths=(6, 6),
            ),
            _spashiny_ctx.ui.layout_columns(
                _spashiny_ctx.ui.div(
                    _spashiny_ctx.ui.input_selectize(
                        "traj_features",
                        "Genes (search and select multiple)",
                        choices=[],
                        selected=[],
                        multiple=True,
                        options={
                            "placeholder": "Type a gene name...",
                            "create": False,
                            "maxOptions": 200,
                        },
                    ),
                    _spashiny_ctx.ui.input_action_button(
                        "btn_run_feature_traj",
                        "Generate Gene Trajectories",
                        class_="btn btn-success mt-3",
                    ),
                    _spashiny_ctx.ui.output_ui("toi_downloads_gene_curve"),
                    _spashiny_globals.plot_output_with_palette(
                        "traj_feature_plot", height="560px", width="100%"
                    ),
                ),
                _spashiny_ctx.ui.div(
                    _spashiny_ctx.ui.input_selectize(
                        "toi_mz_features",
                        "m/z IDs (search and select multiple)",
                        choices=[],
                        selected=[],
                        multiple=True,
                        options={
                            "placeholder": "Type an exact m/z ID...",
                            "create": False,
                            "maxOptions": 200,
                        },
                    ),
                    _spashiny_ctx.ui.input_action_button(
                        "btn_toi_mz_feature",
                        "Generate m/z Trajectories",
                        class_="btn btn-success mt-3",
                    ),
                    _spashiny_ctx.ui.output_ui("toi_downloads_mz_curve"),
                    _spashiny_globals.plot_output_with_palette(
                        "toi_mz_feature_plot", height="560px", width="100%"
                    ),
                ),
                col_widths=(6, 6),
            ),
            _spashiny_ctx.ui.p(
                "Curves call SpatialMETA's plot_features_trajectory on the selected TOI using the existing normalized layer. Scale applies per feature to its non-zero values; shading is mean ± standard deviation, not a confidence interval.",
                class_="apple-muted mt-2",
            ),
        ),
        _spashiny_ctx.ui.div(
            {"class": "table-shell mb-3"},
            _spashiny_ctx.ui.div("Native SpatialMETA Smoothed Clustermaps", class_="plot-title"),
            _spashiny_ctx.ui.p(
                "Original plot_clustermap_with_smoothing: existing normalized values and input row order are preserved. No platform-side TOI filtering, reordering or re-ranking is applied. Top N is selected per existing ranking group.",
                class_="apple-muted",
            ),
            _spashiny_ctx.ui.layout_columns(
                _spashiny_ctx.ui.div(
                    _spashiny_ctx.ui.h4("Genes"),
                    _spashiny_ctx.ui.input_numeric(
                        "native_gene_clustermap_top",
                        "Top genes per ranking group",
                        value=10,
                        min=1,
                        max=100,
                        step=1,
                    ),
                    _spashiny_ctx.ui.input_numeric(
                        "native_gene_clustermap_window",
                        "Gene smoothing window",
                        value=1000,
                        min=1,
                        max=10000,
                        step=10,
                    ),
                    _spashiny_ctx.ui.input_action_button(
                        "btn_toi_gene_heatmap", "Generate Gene Clustermap", class_="btn btn-primary"
                    ),
                    _spashiny_ctx.ui.output_ui("toi_downloads_gene_heatmap"),
                    _spashiny_globals.plot_output_with_palette(
                        "toi_gene_heatmap", height="780px", width="100%"
                    ),
                ),
                _spashiny_ctx.ui.div(
                    _spashiny_ctx.ui.h4("m/z features"),
                    _spashiny_ctx.ui.input_numeric(
                        "native_mz_clustermap_top",
                        "Top m/z features per ranking group",
                        value=20,
                        min=1,
                        max=100,
                        step=1,
                    ),
                    _spashiny_ctx.ui.input_numeric(
                        "native_mz_clustermap_window",
                        "m/z smoothing window",
                        value=300,
                        min=1,
                        max=10000,
                        step=10,
                    ),
                    _spashiny_ctx.ui.input_action_button(
                        "btn_toi_mz_heatmap", "Generate m/z Clustermap", class_="btn btn-primary"
                    ),
                    _spashiny_ctx.ui.output_ui("toi_downloads_mz_heatmap"),
                    _spashiny_globals.plot_output_with_palette(
                        "toi_mz_heatmap", height="780px", width="100%"
                    ),
                ),
                col_widths=(6, 6),
            ),
        ),
        _spashiny_ctx.ui.div(
            {"class": "table-shell"},
            _spashiny_ctx.ui.div("Step 4: Export Current TOI Figures", class_="plot-title"),
            _spashiny_ctx.ui.input_text(
                "export_prefix", "Export file prefix", value="trajectory_analysis"
            ),
            _spashiny_ctx.ui.output_ui("toi_combined_download"),
        ),
    )


def ui(_spashiny_ctx):
    return _spashiny_globals.ui.TagList(_section_1(_spashiny_ctx))
