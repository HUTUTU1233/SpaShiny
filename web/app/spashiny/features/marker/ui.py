# Actual feature UI extracted from production. Feature: marker.
from spashiny._shared import runtime_globals as _spashiny_globals


def _section_1(_spashiny_ctx):
    return _spashiny_ctx.ui.layout_columns(
        _spashiny_ctx.ui.div(
            {"class": "metric-note"},
            "Run marker detection across genes and metabolites using the currently loaded AnnData object.",
        ),
        _spashiny_ctx.ui.div(
            _spashiny_ctx.ui.input_action_button(
                "btn_run_marker", "Run Marker Analysis", class_="btn btn-success w-100 mt-2"
            )
        ),
        col_widths=(8, 4),
    )


def _section_2(_spashiny_ctx):
    return _spashiny_ctx.ui.div(
        _spashiny_ctx.ui.div("Marker Results", class_="apple-section-title"),
        _spashiny_ctx.ui.layout_columns(
            {"class": "rect-plot mt-3"},
            _spashiny_ctx.ui.div(
                {"class": "table-shell"},
                _spashiny_ctx.ui.div("Marker Genes (Top 50 Rows)", class_="plot-title"),
                _spashiny_ctx.ui.output_ui("downstream_marker_genes_download"),
                _spashiny_ctx.ui.output_data_frame("tbl_markers_gene"),
            ),
            _spashiny_ctx.ui.div(
                {"class": "table-shell"},
                _spashiny_ctx.ui.div("Marker Metabolites (Top 50 Rows)", class_="plot-title"),
                _spashiny_ctx.ui.output_ui("downstream_marker_metabolites_download"),
                _spashiny_ctx.ui.output_data_frame("tbl_markers_met"),
            ),
            col_widths=(12, 12),
        ),
    )


def _section_3(_spashiny_ctx):
    return _spashiny_ctx.ui.div(
        _spashiny_ctx.ui.div("Marker Results", class_="apple-section-title"),
        _spashiny_ctx.ui.div(
            {"class": "rect-plot mt-3"},
            _spashiny_ctx.ui.div(
                {"class": "plot-title-row"},
                _spashiny_ctx.ui.div("Marker Visualization", class_="plot-title"),
                _spashiny_ctx.ui.download_button(
                    "download_marker_celltype_png", "Save PNG", class_="btn plot-download-button"
                ),
                _spashiny_ctx.ui.download_button(
                    "download_marker_celltype_pdf",
                    "Save Editable PDF",
                    class_="btn plot-download-button",
                ),
                _spashiny_ctx.ui.download_button(
                    "download_marker_celltype_svg",
                    "Save Editable SVG",
                    class_="btn plot-download-button",
                ),
            ),
            _spashiny_globals.plot_output_with_palette("plt_marker_celltype"),
        ),
    )


def ui(_spashiny_ctx):
    return _spashiny_globals.ui.TagList(
        _section_1(_spashiny_ctx), _section_2(_spashiny_ctx), _section_3(_spashiny_ctx)
    )
