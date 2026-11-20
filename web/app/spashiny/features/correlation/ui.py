# Actual feature UI extracted from production. Feature: correlation.
from spashiny._shared import runtime_globals as _spashiny_globals


def _section_1(_spashiny_ctx):
    return _spashiny_ctx.ui.div(
        {"id": "correlation-control-card"},
        _spashiny_ctx.ui.div("Correlation Analysis", class_="apple-section-title"),
        _spashiny_ctx.ui.div(
            _spashiny_ctx.ui.div(
                _spashiny_ctx.ui.output_ui("correlation_gene_selector"),
                class_="correlation-form-wide",
            ),
            _spashiny_ctx.ui.div(
                _spashiny_ctx.ui.input_text("corr_cluster", "Target cluster", value="C1"),
                class_="correlation-form-small",
            ),
            _spashiny_ctx.ui.div(
                _spashiny_ctx.ui.input_switch(
                    "correlation_row_cluster", "Cluster rows", value=True
                ),
                class_="correlation-form-switch",
            ),
            _spashiny_ctx.ui.div(
                _spashiny_ctx.ui.input_switch(
                    "correlation_col_cluster", "Cluster columns", value=True
                ),
                class_="correlation-form-switch",
            ),
            _spashiny_ctx.ui.div(
                _spashiny_ctx.ui.input_switch(
                    "corr_only_annotated_metabolites", "Only annotated metabolites", value=False
                ),
                class_="correlation-form-switch",
            ),
            _spashiny_ctx.ui.div(
                _spashiny_ctx.ui.input_numeric(
                    "correlation_figsize_width", "Figure width", value=8, min=5, max=14, step=0.5
                ),
                class_="correlation-form-small",
            ),
            _spashiny_ctx.ui.div(
                _spashiny_ctx.ui.input_numeric(
                    "correlation_figsize_height", "Figure height", value=7, min=4, max=12, step=0.5
                ),
                class_="correlation-form-small",
            ),
            _spashiny_ctx.ui.div(
                _spashiny_ctx.ui.input_numeric(
                    "corr_ntop", "Top metabolites per selected gene", value=5, min=1, step=1
                ),
                class_="correlation-form-small",
            ),
            _spashiny_ctx.ui.div(
                _spashiny_ctx.ui.input_action_button(
                    "btn_run_corr", "Run Correlation Analysis", class_="btn-apple-action w-100"
                ),
                class_="correlation-form-actions",
            ),
            class_="correlation-form-grid",
        ),
        class_="at-compact-controls",
    )


def ui(_spashiny_ctx):
    return _spashiny_globals.ui.TagList(_section_1(_spashiny_ctx))
