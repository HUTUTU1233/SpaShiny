# Actual feature UI extracted from production. Feature: spatialmeta_dash.
from spashiny._shared import runtime_globals as _spashiny_globals


def _view_1(_spashiny_ctx, module):
    return _spashiny_ctx.ui.page_fluid(
        _spashiny_ctx.ui.tags.style(
            """
                    .dash-plotly-shell {
                        max-width: 1500px;
                        margin: 0 auto;
                        padding: 26px 12px 42px 12px;
                    }
                    .dash-plotly-hero {
                        background: #ffffff;
                        border: 1px solid rgba(15,23,42,0.08);
                        border-radius: 18px;
                        padding: 24px 28px;
                        margin-bottom: 18px;
                        box-shadow: 0 14px 34px rgba(15,23,42,0.07);
                    }
                    .dash-plotly-title {
                        font-size: 1.9rem;
                        font-weight: 760;
                        margin: 0 0 8px 0;
                        color: #111827;
                    }
                    .dash-plotly-subtitle {
                        color: #64748b;
                        line-height: 1.65;
                        max-width: 980px;
                    }
                    .dash-plotly-panel {
                        background: #ffffff;
                        border: 1px solid rgba(15,23,42,0.08);
                        border-radius: 18px;
                        min-height: 680px;
                        overflow: hidden;
                        box-shadow: 0 14px 34px rgba(15,23,42,0.07);
                    }
                    .dash-plotly-empty {
                        min-height: 520px;
                        display: flex;
                        flex-direction: column;
                        justify-content: center;
                        align-items: center;
                        text-align: center;
                        gap: 14px;
                        padding: 34px;
                        color: #475569;
                    }
                    .dash-plotly-empty h3 {
                        margin: 0;
                        color: #111827;
                        font-weight: 740;
                    }
                    .dash-plotly-status {
                        margin: 16px 20px 0 20px;
                        padding: 10px 12px;
                        border: 1px solid #bae6fd;
                        border-radius: 8px;
                        background: #f0f9ff;
                        color: #075985;
                        font-size: 0.95rem;
                        line-height: 1.45;
                    }
                    .dash-plotly-frame {
                        width: 100%;
                        height: calc(100vh - 230px);
                        min-height: 720px;
                        border: 0;
                        display: block;
                        background: #ffffff;
                    }
                """
        ),
        _spashiny_ctx.ui.div(
            {"class": "dash-plotly-shell"},
            _spashiny_ctx.ui.div(
                {"class": "dash-plotly-hero"},
                _spashiny_ctx.ui.div("SpatialMETA Dash", class_="dash-plotly-title"),
                _spashiny_ctx.ui.div(
                    "The original SpatialMETA Dash interface for the current analysis input or Marker result. Correlation analysis is not required.",
                    class_="dash-plotly-subtitle",
                ),
            ),
            _spashiny_ctx.ui.output_ui("dash_plotly_panel"),
        ),
    )


def _section_1(_spashiny_ctx):
    return _spashiny_ctx.ui.div(
        {"class": "apple-panel"},
        _spashiny_ctx.ui.div("SpatialMETA Dash", class_="apple-section-title"),
        _spashiny_ctx.ui.layout_columns(
            _spashiny_ctx.ui.input_selectize(
                "wrapper_feature",
                "Default feature",
                choices=[],
                selected=None,
                multiple=False,
                options={"placeholder": "Search default feature...", "maxOptions": 200},
            ),
            _spashiny_ctx.ui.input_action_button(
                "btn_native_spatialmeta",
                "Open SpatialMETA Dash Spatial Map",
                class_="btn btn-info w-100 mt-4",
            ),
            col_widths=(6, 6),
        ),
        _spashiny_ctx.ui.p(
            "Open the original SpatialMETA Dash controls for this analysis, including spatial expression, grouping, ROI annotation and trajectories. Correlation is not required.",
            class_="apple-muted mt-3",
        ),
    )


def ui(_spashiny_ctx, module):
    if module == "Dash Plotly":
        return _view_1(_spashiny_ctx, module)
    raise ValueError("Unknown feature page: spatialmeta_dash")
