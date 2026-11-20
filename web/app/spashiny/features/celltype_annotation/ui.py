# Actual feature UI extracted from production. Feature: celltype_annotation.
from spashiny._shared import runtime_globals as _spashiny_globals


def _section_1(_spashiny_ctx):
    return _spashiny_ctx.ui.div(
        {"class": "apple-panel manual-annotation-panel"},
        _spashiny_ctx.ui.div("Manual Cluster Annotation", class_="apple-section-title"),
        _spashiny_ctx.ui.div(
            "Assign labels to clusters and create the final celltype_ST_SM column.",
            class_="manual-annotation-note",
        ),
        _spashiny_ctx.ui.div(
            _spashiny_ctx.ui.div(_spashiny_ctx.ui.output_ui("ui_cluster_selector")),
            _spashiny_ctx.ui.div(
                _spashiny_ctx.ui.input_text(
                    "annotation_text",
                    "Cell Type Annotation",
                    placeholder="e.g. Macrophage, T cell, Fibroblast...",
                )
            ),
            _spashiny_ctx.ui.div(
                _spashiny_ctx.ui.input_action_button(
                    "btn_add_annotation", "Add / Update Annotation", class_="btn btn-primary"
                )
            ),
            class_="manual-annotation-grid at-compact-controls",
        ),
        _spashiny_ctx.ui.div(
            _spashiny_ctx.ui.div(
                _spashiny_ctx.ui.output_text_verbatim("txt_annotation_preview"),
                class_="manual-annotation-preview",
            ),
            _spashiny_ctx.ui.div(
                _spashiny_ctx.ui.input_action_button(
                    "btn_create_celltype", "Create celltype_ST_SM Column", class_="btn btn-success"
                )
            ),
            class_="manual-annotation-actions",
        ),
    )


def _section_2(_spashiny_ctx):
    return _spashiny_ctx.ui.div(
        {"class": "apple-panel"},
        _spashiny_ctx.ui.div("Marker Analysis", class_="apple-section-title"),
        _spashiny_ctx.ui.layout_columns(
            _spashiny_ctx.ui.div(
                {"class": "metric-note"},
                "Run marker detection across genes and metabolites using the currently loaded AnnData object.",
            ),
            _spashiny_ctx.ui.div(
                _spashiny_ctx.ui.input_action_button(
                    "btn_run_marker_celltype",
                    "Run Marker Analysis",
                    class_="btn btn-success w-100 mt-2",
                )
            ),
            col_widths=(8, 4),
        ),
    )


def ui(_spashiny_ctx):
    return _spashiny_globals.ui.TagList(_section_1(_spashiny_ctx), _section_2(_spashiny_ctx))
