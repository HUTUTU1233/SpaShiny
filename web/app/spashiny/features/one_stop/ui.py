# Feature one_stop: original callable implementation extracted from spatialmeta_workbench_ui.py.
from spashiny._shared.feature_support import spatialmeta_workbench_ui as _feature_shared
from spashiny._shared import runtime_globals as _spashiny_globals


def _view_1(_spashiny_ctx, module):
    return _spashiny_globals.one_stop_ui()


def ui(_spashiny_ctx, module):
    if module == "ONE_STOP":
        return _view_1(_spashiny_ctx, module)
    raise ValueError("Unknown feature page: one_stop")


def one_stop_ui():
    return _feature_shared.ui.div(
        _feature_shared.ui.h2("Single-sample one-stop ST-SM analysis"),
        _feature_shared.ui.p(
            "Native SpatialMETA stages, using one authenticated analysis. No multi-sample analysis and no automatic launch of Dash/Plotly."
        ),
        _feature_shared.ui.input_select(
            "one_stop_start",
            "Start from",
            choices={
                "raw_pair": "Uploaded ST + SM: preflight, alignment, KNN and integration",
                "manual": "Current workflow: manual alignment",
                "step6": "Current completed Alignment Step6: KNN and integration",
                "knn": "Current completed KNN: integration",
                "joint": "Uploaded joint ST-SM H5AD: integration",
            },
        ),
        _feature_shared.upload_controls(),
        _feature_shared.ui.input_checkbox(
            "one_stop_native_downstream",
            "Run native Marker/correlation on an existing celltype_ST_SM annotation and normalized layer",
            value=True,
        ),
        _feature_shared.ui.input_numeric(
            "one_stop_correlation_genes",
            "Maximum native Marker genes for correlation",
            value=10,
            min=1,
            max=50,
        ),
        _feature_shared.ui.p(
            "Missing annotations or a missing normalized layer are reported as NOT_RUN, never substituted with C0 or made-up cell types."
        ),
        _feature_shared.ui.p(
            "Raw alignment needs ST spatial coordinates, its hires tissue image and the matching scale factor. Later starts require a verified checkpoint from this analysis."
        ),
        _feature_shared.ui.p(
            "Integration keeps all supplied features and uses the installed SpatialMETA model/training defaults. No Low memory/Balanced/Performance preset or first-N feature cap is applied. Official tutorial parameters and the single-sample workflow mode are recorded in the report; insufficient hardware fails clearly instead of silently changing the model."
        ),
        _feature_shared.ui.input_action_button(
            "one_stop_begin", "Validate and start", class_="btn btn-primary"
        ),
        _feature_shared.ui.input_action_button(
            "one_stop_show_progress", "Show progress", class_="btn btn-outline-primary"
        ),
        _feature_shared.ui.input_action_button(
            "one_stop_resume", "Resume paused run", class_="btn btn-outline-primary"
        ),
        _feature_shared.ui.output_ui("one_stop_status"),
        _feature_shared.ui.download_button(
            "download_one_stop_report", "Download AI-readable report (.zip)"
        ),
        _feature_shared.ui.p(
            "The report contains JSON, Markdown, provenance and available tables. No data is sent to an external AI service. Missing annotations or analyses are explicitly reported, not invented."
        ),
        class_="apple-panel",
        style="padding:24px;",
    )
