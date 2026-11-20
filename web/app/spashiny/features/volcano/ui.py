# Actual feature UI extracted from production. Feature: volcano.
from spashiny._shared import runtime_globals as _spashiny_globals


def _section_1(_spashiny_ctx):
    return _spashiny_ctx.ui.div(
        {"class": "apple-panel"},
        _spashiny_ctx.ui.div("Volcano Controls", class_="apple-section-title"),
        _spashiny_ctx.ui.div(
            {"class": "at-compact-controls"},
            _spashiny_ctx.ui.layout_columns(
                _spashiny_ctx.ui.input_selectize(
                    "volcano_cluster",
                    "Target cluster",
                    choices=[],
                    selected=None,
                    multiple=False,
                    options={"placeholder": "Search cluster...", "maxOptions": 100},
                ),
                _spashiny_ctx.ui.input_selectize(
                    "volcano_gene",
                    "Gene",
                    choices=[],
                    selected=None,
                    multiple=False,
                    options={"placeholder": "Search gene...", "maxOptions": 100},
                ),
                _spashiny_ctx.ui.input_selectize(
                    "volcano_metabolite",
                    "Metabolite m/z",
                    choices=[],
                    selected=None,
                    multiple=False,
                    options={"placeholder": "Search metabolite m/z...", "maxOptions": 100},
                ),
                _spashiny_ctx.ui.input_numeric(
                    "volcano_threshold", "Threshold", value=0.3, min=0, max=1, step=0.05
                ),
                col_widths=(3, 3, 3, 3),
            ),
            _spashiny_ctx.ui.output_text("volcano_feature_availability"),
            _spashiny_ctx.ui.input_action_button(
                "btn_run_volcano", "Generate Volcano Plot", class_="btn btn-info w-100"
            ),
        ),
    )


def _section_2(_spashiny_ctx):
    return _spashiny_ctx.ui.div(
        {"class": "apple-panel"},
        _spashiny_ctx.ui.div("Volcano Plot Analysis", class_="apple-section-title"),
        _spashiny_ctx.ui.layout_columns(
            _spashiny_ctx.ui.div(
                {"class": "square-plot"},
                _spashiny_ctx.ui.div(
                    {"class": "plot-title-row"},
                    _spashiny_ctx.ui.div("Gene to Metabolite", class_="plot-title"),
                    _spashiny_ctx.ui.download_button(
                        "download_gene_volcano_png", "Save PNG", class_="btn plot-download-button"
                    ),
                    _spashiny_ctx.ui.download_button(
                        "download_gene_volcano_pdf",
                        "Save Editable PDF",
                        class_="btn plot-download-button",
                    ),
                    _spashiny_ctx.ui.download_button(
                        "download_gene_volcano_svg",
                        "Save Editable SVG",
                        class_="btn plot-download-button",
                    ),
                ),
                _spashiny_globals.plot_output_with_palette("plt_gene_volcano"),
            ),
            _spashiny_ctx.ui.div(
                {"class": "square-plot"},
                _spashiny_ctx.ui.div(
                    {"class": "plot-title-row"},
                    _spashiny_ctx.ui.div("Metabolite to Gene", class_="plot-title"),
                    _spashiny_ctx.ui.download_button(
                        "download_metabolite_volcano_png",
                        "Save PNG",
                        class_="btn plot-download-button",
                    ),
                    _spashiny_ctx.ui.download_button(
                        "download_metabolite_volcano_pdf",
                        "Save Editable PDF",
                        class_="btn plot-download-button",
                    ),
                    _spashiny_ctx.ui.download_button(
                        "download_metabolite_volcano_svg",
                        "Save Editable SVG",
                        class_="btn plot-download-button",
                    ),
                ),
                _spashiny_globals.plot_output_with_palette("plt_metabolite_volcano"),
            ),
            col_widths=(6, 6),
        ),
    )


def ui(_spashiny_ctx):
    return _spashiny_globals.ui.TagList(_section_1(_spashiny_ctx), _section_2(_spashiny_ctx))
