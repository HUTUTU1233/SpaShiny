# Actual feature UI extracted from production. Feature: home.
from spashiny._shared import runtime_globals as _spashiny_globals


def _view_1(_spashiny_ctx, module):
    return _spashiny_ctx.ui.page_fluid(
        _spashiny_ctx.ui.tags.style(
            """
                    .home-shell {
                        max-width: 1320px;
                        margin: 0 auto;
                        padding: 28px 12px 46px 12px;
                        color: #1d1d1f;
                    }

                    .home-hero {
                        position: relative;
                        overflow: hidden;
                        background: linear-gradient(135deg, #ffffff 0%, #f7fbff 58%, #f3fbf7 100%);
                        border: 1px solid rgba(15, 23, 42, 0.07);
                        border-radius: 26px;
                        box-shadow: 0 18px 45px rgba(15, 23, 42, 0.08);
                        padding: 42px;
                        margin-bottom: 24px;
                    }

                    .home-title {
                        font-size: clamp(2.15rem, 4vw, 4.1rem);
                        font-weight: 780;
                        color: #1d1d1f;
                        letter-spacing: 0;
                        line-height: 1.05;
                        margin-bottom: 16px;
                    }

                    .home-subtitle {
                        font-size: 1.05rem;
                        color: #6e6e73;
                        line-height: 1.75;
                        max-width: 780px;
                        margin-bottom: 22px;
                    }

                    .home-kicker {
                        display: inline-flex;
                        align-items: center;
                        width: fit-content;
                        padding: 7px 12px;
                        border-radius: 999px;
                        background: #eef6ff;
                        color: #0b63ce;
                        border: 1px solid #d8eaff;
                        font-size: 0.82rem;
                        font-weight: 700;
                        letter-spacing: 0.03em;
                        text-transform: uppercase;
                        margin-bottom: 16px;
                    }

                    .home-chip-row {
                        display: flex;
                        flex-wrap: wrap;
                        gap: 10px;
                        margin-top: 18px;
                    }

                    .home-chip {
                        padding: 8px 12px;
                        border-radius: 999px;
                        background: rgba(255,255,255,0.82);
                        border: 1px solid rgba(15, 23, 42, 0.08);
                        color: #334155;
                        font-size: 0.9rem;
                        font-weight: 650;
                    }

                    .home-logo-strip {
                        width: min(520px, 100%);
                        padding: 15px 18px;
                        margin-bottom: 22px;
                        border-radius: 18px;
                        background: rgba(255,255,255,0.78);
                        border: 1px solid rgba(15, 23, 42, 0.07);
                        box-shadow: inset 0 1px 0 rgba(255,255,255,0.75);
                    }

                    .home-logo-strip img {
                        width: 100%;
                        height: auto;
                        display: block;
                    }

                    .home-workflow-figure {
                        margin: 22px 0 4px;
                        padding: 22px;
                        background: rgba(255,255,255,0.92);
                        border: 1px solid rgba(15, 23, 42, 0.07);
                        border-radius: 18px;
                        box-shadow: 0 10px 28px rgba(15, 23, 42, 0.05);
                    }

                    .home-workflow-figure h2 {
                        font-size: 1.18rem;
                        color: #1d1d1f;
                        margin: 0 0 12px;
                    }

                    .home-workflow-figure figure { margin: 0; }

                    .home-workflow-figure img {
                        display: block;
                        width: 100%;
                        max-width: 1160px;
                        height: auto;
                        margin: 0 auto;
                        border-radius: 10px;
                        border: 1px solid #e5e7eb;
                    }

                    .home-workflow-figure figcaption {
                        color: #64748b;
                        font-size: 0.88rem;
                        margin-top: 10px;
                        text-align: center;
                    }

                    .home-grid {
                        display: grid;
                        grid-template-columns: repeat(3, minmax(0, 1fr));
                        gap: 14px;
                        margin-top: 18px;
                    }

                    .home-card {
                        background: rgba(255,255,255,0.92);
                        border: 1px solid rgba(15, 23, 42, 0.07);
                        border-radius: 18px;
                        box-shadow: 0 10px 28px rgba(15, 23, 42, 0.05);
                        padding: 22px 20px;
                        min-height: 172px;
                        transition: all 0.22s ease;
                    }

                    .home-card:hover {
                        transform: translateY(-3px);
                        box-shadow: 0 16px 36px rgba(15, 23, 42, 0.09);
                        border-color: rgba(0, 113, 227, 0.18);
                    }

                    .home-card-title {
                        font-size: 1.05rem;
                        font-weight: 700;
                        color: #1d1d1f;
                        margin-bottom: 12px;
                    }

                    .home-card-text {
                        font-size: 0.94rem;
                        color: #6e6e73;
                        line-height: 1.75;
                    }

                    .home-note {
                        margin-top: 22px;
                        padding: 16px 18px;
                        border-radius: 18px;
                        background: rgba(0,122,255,0.06);
                        border: 1px solid rgba(0,122,255,0.08);
                        color: #1d3f72;
                        font-size: 0.95rem;
                        line-height: 1.7;
                    }

                    .home-path-grid {
                        display: grid;
                        grid-template-columns: repeat(2, minmax(0, 1fr));
                        gap: 14px;
                        margin-top: 18px;
                    }

                    .home-path-card {
                        background: rgba(255,255,255,0.92);
                        border: 1px solid rgba(15, 23, 42, 0.07);
                        border-radius: 18px;
                        box-shadow: 0 10px 28px rgba(15, 23, 42, 0.05);
                        padding: 18px;
                    }

                    .home-path-title {
                        font-size: 1rem;
                        font-weight: 740;
                        color: #1d1d1f;
                        margin-bottom: 8px;
                    }

                    .home-path {
                        margin-top: 10px;
                        padding: 10px 12px;
                        border-radius: 12px;
                        background: #f8fafc;
                        border: 1px solid #e5e7eb;
                        color: #475569;
                        font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
                        font-size: 0.82rem;
                        line-height: 1.5;
                        word-break: break-word;
                    }

                    .home-note {
                        display: none;
                    }

                    .home-note-clean {
                        margin-top: 22px;
                        padding: 16px 18px;
                        border-radius: 18px;
                        background: rgba(0,122,255,0.06);
                        border: 1px solid rgba(0,122,255,0.08);
                        color: #1d3f72;
                        font-size: 0.95rem;
                        line-height: 1.7;
                    }

                    @media (max-width: 1200px) {
                        .home-grid,
                        .home-path-grid {
                            grid-template-columns: repeat(2, minmax(0, 1fr));
                        }
                    }

                    @media (max-width: 700px) {
                        .home-grid,
                        .home-path-grid {
                            grid-template-columns: 1fr;
                        }
                        .home-hero {
                            padding: 24px;
                            border-radius: 20px;
                        }
                    }
                """
        ),
        _spashiny_ctx.ui.div(
            {"class": "home-shell"},
            _spashiny_ctx.ui.div(
                {"class": "home-hero"},
                _spashiny_ctx.ui.div("Cloud spatial multi-omics workspace", class_="home-kicker"),
                _spashiny_ctx.ui.div(
                    {"class": "home-logo-strip"},
                    _spashiny_ctx.ui.tags.img(src="/Wang_lab.png", alt="Wang Lab"),
                ),
                _spashiny_ctx.ui.div("SpaShiny", class_="home-title"),
                _spashiny_ctx.ui.p(
                    "A cloud platform for spatial metabolomics and spatial transcriptomics: upload data, run quality control, annotate metabolites, align coordinates, integrate modalities, and generate downstream results.",
                    class_="home-subtitle",
                ),
                _spashiny_ctx.ui.div(
                    _spashiny_ctx.ui.span("Cloud worker execution", class_="home-chip"),
                    _spashiny_ctx.ui.span("SM + ST analysis", class_="home-chip"),
                    _spashiny_ctx.ui.span("SpatialMETA candidate annotation", class_="home-chip"),
                    _spashiny_ctx.ui.span("Example data ready", class_="home-chip"),
                    class_="home-chip-row",
                ),
                _spashiny_ctx.ui.div(
                    {"class": "home-note-clean"},
                    "Recommended workflow: Data Preparation / Preprocessing → Spatial Integration → River or Downstream Analysis.",
                ),
            ),
            _spashiny_ctx.ui.tags.section(
                _spashiny_ctx.ui.h2("Workflow Overview"),
                _spashiny_ctx.ui.tags.figure(
                    _spashiny_ctx.ui.tags.a(
                        _spashiny_ctx.ui.tags.img(
                            src="/Spa_F1.png?v=789496ec1d02", alt="SpaShiny workflow overview"
                        ),
                        href="/Spa_F1.png?v=789496ec1d02",
                        target="_blank",
                        rel="noopener noreferrer",
                        aria_label="Open the SpaShiny workflow overview at full size",
                    ),
                    _spashiny_ctx.ui.tags.figcaption(
                        "SpaShiny workflow overview. Select the figure to view it at full size."
                    ),
                ),
                class_="home-workflow-figure",
            ),
            _spashiny_ctx.ui.div(
                {"class": "home-grid"},
                _spashiny_ctx.ui.div(
                    {"class": "home-card"},
                    _spashiny_ctx.ui.div(
                        "Data Preparation / Preprocessing", class_="home-card-title"
                    ),
                    _spashiny_ctx.ui.div(
                        "Upload ST or SM data and review quality metrics before spatial integration.",
                        class_="home-card-text",
                    ),
                ),
                _spashiny_ctx.ui.div(
                    {"class": "home-card"},
                    _spashiny_ctx.ui.div("Spatial Integration", class_="home-card-title"),
                    _spashiny_ctx.ui.div(
                        "Prepare coordinates, perform manual or automatic registration, then run KNN reassignment.",
                        class_="home-card-text",
                    ),
                ),
                _spashiny_ctx.ui.div(
                    {"class": "home-card"},
                    _spashiny_ctx.ui.div("Multimodal workflows", class_="home-card-title"),
                    _spashiny_ctx.ui.div(
                        "Run single-sample and multi-sample ST–SM integration or multi-sample SM integration with background workers.",
                        class_="home-card-text",
                    ),
                ),
                _spashiny_ctx.ui.div(
                    {"class": "home-card"},
                    _spashiny_ctx.ui.div("Downstream Analysis", class_="home-card-title"),
                    _spashiny_ctx.ui.div(
                        "Explore markers, correlations, enrichment, SpatialMETA metabolite annotation, figures, and downloads.",
                        class_="home-card-text",
                    ),
                ),
                _spashiny_ctx.ui.div(
                    {"class": "home-card"},
                    _spashiny_ctx.ui.div("Help & Tutorial", class_="home-card-title"),
                    _spashiny_ctx.ui.div(
                        "Use the guided workflow: start with QC, continue with alignment, and submit integration jobs only after their inputs are ready.",
                        class_="home-card-text",
                    ),
                ),
                _spashiny_ctx.ui.div(
                    {"class": "home-card"},
                    _spashiny_ctx.ui.div("Session-safe analysis", class_="home-card-title"),
                    _spashiny_ctx.ui.div(
                        "Jobs continue in background workers and results remain associated with the current analysis session.",
                        class_="home-card-text",
                    ),
                ),
            ),
            _spashiny_ctx.ui.div(
                {"class": "home-path-grid"},
                _spashiny_ctx.ui.div(
                    {"class": "home-path-card"},
                    _spashiny_ctx.ui.div("Quick start", class_="home-path-title"),
                    _spashiny_ctx.ui.div(
                        "1. Open Data Preparation / Preprocessing and load an example or upload input data. 2. Complete QC. 3. Use Spatial Integration, then River or Downstream Analysis.",
                        class_="home-card-text",
                    ),
                    _spashiny_ctx.ui.input_action_button(
                        "help_open_st_qc", "Open ST QC", class_="btn btn-outline-primary"
                    ),
                    _spashiny_ctx.ui.input_action_button(
                        "help_open_alignment",
                        "Open Spatial Alignment",
                        class_="btn btn-outline-primary",
                        style="margin-left:8px;",
                    ),
                ),
                _spashiny_ctx.ui.div(
                    {"class": "home-path-card"},
                    _spashiny_ctx.ui.div("Need help?", class_="home-path-title"),
                    _spashiny_ctx.ui.div(
                        "The guided pages explain required inputs, valid next steps, persistent job status, result display, and downloads.",
                        class_="home-card-text",
                    ),
                    _spashiny_ctx.ui.input_action_button(
                        "help_open_integration",
                        "Open Multimodal Integration",
                        class_="btn btn-outline-primary",
                    ),
                    _spashiny_ctx.ui.input_action_button(
                        "show_help_tutorial",
                        "Open Full Tutorial",
                        class_="btn btn-outline-primary",
                        style="margin-left:8px;",
                    ),
                ),
            ),
        ),
    )


def ui(_spashiny_ctx, module):
    if module == "home":
        return _view_1(_spashiny_ctx, module)
    raise ValueError("Unknown feature page: home")
