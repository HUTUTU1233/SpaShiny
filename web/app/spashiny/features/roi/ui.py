# Actual feature UI extracted from production. Feature: roi.
from spashiny._shared import runtime_globals as _spashiny_globals


def _section_1(_spashiny_ctx):
    return _spashiny_ctx.ui.div(
        {"class": "apple-panel"},
        _spashiny_ctx.ui.div("Annotation Tools and ROI Analysis", class_="apple-section-title"),
        _spashiny_ctx.ui.input_action_button(
            "btn_probe_adata1",
            "Refresh Available ROI / Annotation Fields",
            class_="btn btn-primary w-100",
        ),
        _spashiny_ctx.ui.input_select(
            "roi_obs_key", "Detected ROI / Annotation Columns", choices={"": "Click refresh first"}
        ),
        _spashiny_ctx.ui.p(
            "This module reads the current adata_global object handed off from Plotly / Dash.",
            class_="apple-muted",
        ),
        _spashiny_ctx.ui.hr(),
        _spashiny_ctx.ui.layout_columns(
            _spashiny_ctx.ui.input_action_button(
                "btn_show_roi", "Show ROI Information", class_="btn btn-info w-100"
            ),
            _spashiny_ctx.ui.input_action_button(
                "btn_run_roi_analysis", "Run ROI Analysis", class_="btn btn-primary w-100"
            ),
            col_widths=(6, 6),
        ),
        _spashiny_ctx.ui.hr(),
        _spashiny_ctx.ui.div("ROI Cell Counts", class_="plot-title"),
        _spashiny_ctx.ui.download_button(
            "download_roi_counts_csv",
            "Download ROI Counts CSV",
            class_="btn btn-secondary w-100 mb-3",
        ),
        _spashiny_ctx.ui.output_data_frame("roi_counts_table"),
        _spashiny_ctx.ui.hr(),
        _spashiny_ctx.ui.div("ROI Spatial Plot", class_="plot-title"),
        _spashiny_globals.plot_output_with_palette(
            "roi_spatial_plot", height="600px", width="100%"
        ),
        _spashiny_ctx.ui.hr(),
        _spashiny_ctx.ui.div("ROI Marker Feature Plot", class_="plot-title"),
        _spashiny_globals.plot_output_with_palette("roi_marker_plot", height="600px", width="100%"),
        _spashiny_ctx.ui.hr(),
        _spashiny_ctx.ui.div("Export ROI Results", class_="plot-title"),
        _spashiny_ctx.ui.layout_columns(
            _spashiny_ctx.ui.download_button(
                "download_roi_spatial_pdf",
                "Download ROI Spatial PDF",
                class_="btn btn-secondary w-100",
            ),
            _spashiny_ctx.ui.download_button(
                "download_roi_marker_pdf",
                "Download ROI Marker PDF",
                class_="btn btn-secondary w-100",
            ),
            col_widths=(6, 6),
        ),
        _spashiny_ctx.ui.download_button(
            "download_roi_full_pdf",
            "Download ROI Full Report PDF",
            class_="btn btn-dark w-100 mt-3",
        ),
    )


def ui(_spashiny_ctx):
    return _spashiny_globals.ui.TagList(_section_1(_spashiny_ctx))
