# Actual feature UI extracted from production. Feature: feature_explorer.
from spashiny._shared import runtime_globals as _spashiny_globals


def _section_1(_spashiny_ctx):
    return _spashiny_ctx.ui.div(
        {"class": "wide-plot"},
        _spashiny_globals.plot_output_with_palette(
            "feature_original_plot", width="100%", height="560px"
        ),
    )


def _section_2(_spashiny_ctx):
    return _spashiny_ctx.ui.div(
        {"class": "apple-panel"},
        _spashiny_ctx.ui.div("Spatial Feature Map — Reconstructed Expression", class_="plot-title"),
        _spashiny_ctx.ui.div(
            {"class": "wide-plot"},
            _spashiny_globals.plot_output_with_palette(
                "feature_reconstruction_plot", width="100%", height="560px"
            ),
        ),
        _spashiny_ctx.ui.div(
            {"class": "apple-panel"},
            _spashiny_ctx.ui.div("Export Feature Explorer Figures", class_="apple-section-title"),
            _spashiny_ctx.ui.row(
                _spashiny_ctx.ui.column(
                    4,
                    _spashiny_ctx.ui.download_button(
                        "download_feature_original_pdf",
                        "Download Original PDF",
                        class_="btn btn-primary w-100",
                    ),
                ),
                _spashiny_ctx.ui.column(
                    4,
                    _spashiny_ctx.ui.download_button(
                        "download_feature_reconstruction_pdf",
                        "Download Reconstruction PDF",
                        class_="btn btn-primary w-100",
                    ),
                ),
                _spashiny_ctx.ui.column(
                    4,
                    _spashiny_ctx.ui.download_button(
                        "download_feature_comparison_pdf",
                        "Download Feature Comparison PDF",
                        class_="btn btn-success w-100",
                    ),
                ),
            ),
        ),
    )


def ui(_spashiny_ctx):
    return _spashiny_globals.ui.TagList(_section_1(_spashiny_ctx), _section_2(_spashiny_ctx))
