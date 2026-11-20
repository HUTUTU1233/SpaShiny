# Actual feature UI extracted from production. Feature: integration_multi_sm.
from spashiny._shared import runtime_globals as _spashiny_globals


def _view_1(_spashiny_ctx, module):
    hit_sm_css = """
            <style>
            :root {
                --hit-bg: #f5f5f7;
                --hit-card: rgba(255,255,255,0.92);
                --hit-border: rgba(0,0,0,0.06);
                --hit-text: #1d1d1f;
                --hit-subtext: #6e6e73;
                --hit-blue: #0071e3;
                --hit-green: #34c759;
                --hit-orange: #ff9f0a;
                --hit-gray: #8e8e93;
                --hit-shadow: 0 10px 30px rgba(0,0,0,0.06);
                --hit-shadow-hover: 0 16px 40px rgba(0,0,0,0.10);
                --hit-radius-xl: 28px;
                --hit-radius-lg: 22px;
                --hit-radius-md: 18px;
            }

            body {
                background: linear-gradient(180deg, #f8f9fb 0%, #f2f4f8 100%);
                color: var(--hit-text);
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display",
                            "SF Pro Text", "Helvetica Neue", Helvetica, Arial, sans-serif;
            }

            .hit-shell {
                max-width: 1580px;
                margin: 0 auto;
                padding: 20px 18px 42px 18px;
            }

            .hit-hero {
                background: linear-gradient(135deg, rgba(255,255,255,0.96), rgba(247,249,255,0.92));
                border: 1px solid rgba(255,255,255,0.7);
                border-radius: 34px;
                box-shadow: var(--hit-shadow);
                padding: 30px 34px;
                margin-bottom: 24px;
                backdrop-filter: blur(18px);
                -webkit-backdrop-filter: blur(18px);
            }

            .hit-title {
                font-size: 2.15rem;
                font-weight: 700;
                letter-spacing: -0.03em;
                margin: 0 0 8px 0;
                color: var(--hit-text);
            }

            .hit-subtitle {
                font-size: 1rem;
                color: var(--hit-subtext);
                line-height: 1.75;
                margin: 0;
                max-width: 1100px;
            }

            .hit-panel {
                background: var(--hit-card);
                border: 1px solid rgba(255,255,255,0.58);
                border-radius: var(--hit-radius-xl);
                box-shadow: var(--hit-shadow);
                padding: 24px;
                margin-bottom: 22px;
                backdrop-filter: blur(18px);
                -webkit-backdrop-filter: blur(18px);
                transition: all 0.25s ease;
            }

            .hit-panel:hover {
                transform: translateY(-2px);
                box-shadow: var(--hit-shadow-hover);
            }

            .hit-section-title {
                font-size: 1.2rem;
                font-weight: 700;
                letter-spacing: -0.02em;
                margin-bottom: 16px;
                color: var(--hit-text);
            }

            .hit-note {
                background: rgba(0,113,227,0.06);
                border: 1px solid rgba(0,113,227,0.08);
                border-radius: 18px;
                padding: 14px 16px;
                color: #1d3f72;
                font-size: 0.94rem;
                line-height: 1.7;
                margin-bottom: 16px;
            }

            .hit-soft-card {
                background: rgba(255,255,255,0.78);
                border: 1px solid rgba(0,0,0,0.04);
                border-radius: 24px;
                padding: 18px;
                margin-bottom: 16px;
            }

            .hit-status-card {
                background: rgba(255,255,255,0.78);
                border: 1px solid rgba(0,0,0,0.04);
                border-radius: 20px;
                padding: 16px 18px;
                min-height: 110px;
            }

            .hit-status-title {
                font-size: 0.82rem;
                font-weight: 600;
                color: var(--hit-subtext);
                margin-bottom: 8px;
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }

            .hit-status-value {
                font-size: 1.2rem;
                font-weight: 700;
                color: var(--hit-text);
            }

            .hit-plot-card {
                background: rgba(255,255,255,0.82);
                border: 1px solid rgba(0,0,0,0.04);
                border-radius: 24px;
                padding: 16px;
                margin-bottom: 18px;
            }

            .hit-plot-title {
                font-size: 1rem;
                font-weight: 700;
                margin-bottom: 12px;
                letter-spacing: -0.01em;
                color: var(--hit-text);
            }

            /* Square shell */
            .hit-pan-shell {
                width: 100%;
                aspect-ratio: 1 / 1;
                min-height: 760px;
                max-height: 78vh;
                background: #ffffff;
                border: 1px solid rgba(0,0,0,0.05);
                border-radius: 20px;
                overflow: auto;
                padding: 10px;
                position: relative;
            }

            /* Large inner canvas; do not compress, allow scrolling */
            .hit-pan-canvas {
                width: 1300px;
                height: 1300px;
                min-width: 1300px;
                min-height: 1300px;
            }

            .hit-pan-canvas .shiny-plot-output,
            .hit-pan-canvas img,
            .hit-pan-canvas canvas,
            .hit-pan-canvas svg {
                width: 1300px !important;
                height: 1300px !important;
                max-width: none !important;
                max-height: none !important;
                display: block;
            }

            .hit-table-shell {
                width: 100%;
                min-height: 300px;
                background: #ffffff;
                border: 1px solid rgba(0,0,0,0.05);
                border-radius: 20px;
                padding: 12px;
                overflow: auto;
            }

            .btn, .btn-default, .btn-primary, .btn-success, .btn-info, .btn-secondary, .btn-warning {
                border-radius: 999px !important;
                padding: 11px 18px !important;
                font-weight: 600 !important;
                border: none !important;
                box-shadow: 0 8px 18px rgba(0,0,0,0.08);
                transition: all 0.2s ease !important;
            }

            .btn:hover {
                transform: translateY(-1px);
                box-shadow: 0 12px 24px rgba(0,0,0,0.12);
            }

            .btn-primary {
                background: linear-gradient(135deg, #0a84ff, #0071e3) !important;
                color: white !important;
            }

            .btn-success {
                background: linear-gradient(135deg, #34c759, #30b958) !important;
                color: white !important;
            }

            .btn-info {
                background: linear-gradient(135deg, #5ac8fa, #0a84ff) !important;
                color: white !important;
            }

            .btn-warning {
                background: linear-gradient(135deg, #ffb340, #ff9500) !important;
                color: white !important;
            }

            .btn-secondary {
                background: linear-gradient(135deg, #8e8e93, #6e6e73) !important;
                color: white !important;
            }

            .form-control, .form-select, .shiny-input-number input, input, select, textarea {
                border-radius: 16px !important;
                border: 1px solid rgba(0,0,0,0.08) !important;
                background: rgba(255,255,255,0.94) !important;
                box-shadow: none !important;
                min-height: 46px;
                padding: 11px 14px !important;
            }

            label {
                font-weight: 600 !important;
                color: var(--hit-text) !important;
                margin-bottom: 8px !important;
            }

            .accordion {
                --bs-accordion-border-color: rgba(0,0,0,0.05);
                --bs-accordion-btn-focus-box-shadow: none;
                --bs-accordion-btn-bg: rgba(255,255,255,0.72);
                --bs-accordion-active-bg: rgba(0,113,227,0.06);
                --bs-accordion-active-color: #0a58ca;
                border-radius: 20px;
                overflow: hidden;
            }

            .accordion-item {
                border-radius: 18px !important;
                overflow: hidden;
                border: 1px solid rgba(0,0,0,0.05) !important;
                margin-bottom: 10px;
                background: rgba(255,255,255,0.72);
            }

            .accordion-button {
                font-weight: 700;
                border-radius: 18px !important;
            }

            .accordion-body {
                background: rgba(255,255,255,0.82);
            }

            @media (max-width: 992px) {
                .hit-pan-shell {
                    min-height: 560px;
                    max-height: none;
                }

                .hit-pan-canvas {
                    width: 1000px;
                    height: 1000px;
                    min-width: 1000px;
                    min-height: 1000px;
                }

                .hit-pan-canvas .shiny-plot-output,
                .hit-pan-canvas img,
                .hit-pan-canvas canvas,
                .hit-pan-canvas svg {
                    width: 1000px !important;
                    height: 1000px !important;
                }
            }
            </style>
            """
    return _spashiny_ctx.ui.page_fluid(
        _spashiny_ctx.ui.HTML(hit_sm_css),
        _spashiny_ctx.ui.div(
            {"class": "hit-shell"},
            _spashiny_ctx.ui.div(
                {"class": "hit-hero"},
                _spashiny_ctx.ui.h1("SM Horizontal Integration", class_="hit-title"),
                _spashiny_ctx.ui.p(
                    "Upload multiple SM datasets, merge them, compute spatially variable metabolites, run ConditionalVAE integration, and visualize debatched embeddings in a clean vertical layout.",
                    class_="hit-subtitle",
                ),
            ),
            _spashiny_ctx.ui.div(
                {"class": "hit-panel"},
                _spashiny_ctx.ui.div("Sample Setup and Data Upload", class_="hit-section-title"),
                _spashiny_ctx.ui.div(
                    "Define the sample list, upload .h5ad files, and prepare merged input data for downstream horizontal integration.",
                    class_="hit-note",
                ),
                _spashiny_ctx.ui.layout_columns(
                    _spashiny_ctx.ui.input_text_area(
                        "sm_sample_list",
                        "Sample List",
                        placeholder="Example: R114_T, S15_T, X49_T, Y27_T, Y7_T",
                        rows=3,
                    ),
                    _spashiny_ctx.ui.input_file(
                        "sm_upload", "Upload .h5ad Files", multiple=True, accept=[".h5ad"]
                    ),
                    col_widths=(6, 6),
                ),
                _spashiny_ctx.ui.layout_columns(
                    _spashiny_ctx.ui.input_action_button(
                        "load_hit_sm_example",
                        "Load bundled SM examples",
                        class_=_spashiny_globals.cloud_example_button_class("btn-info"),
                        width="100%",
                        **_spashiny_globals.cloud_example_action_attrs(
                            "sm-five-sample-batch-example", "hit_sm", "hit-sm-example-status"
                        ),
                    ),
                    _spashiny_ctx.ui.input_action_button(
                        "auto_detect_samples",
                        "Auto Detect Samples",
                        class_="btn-secondary",
                        width="100%",
                    ),
                    _spashiny_ctx.ui.input_action_button(
                        "run_sm_merge", "Run Merge", class_="btn-primary", width="100%"
                    ),
                    _spashiny_ctx.ui.download_button(
                        "download_hit_merged_data",
                        "Download Merged Data",
                        class_="btn-success",
                        width="100%",
                    ),
                    col_widths=(3, 3, 3, 3),
                ),
                _spashiny_ctx.ui.div(
                    _spashiny_globals.example_source_note(
                        "Example source: user_data/input/SM",
                        "Cloud example: five raw SM h5ad samples are bound to this session on click.",
                    ),
                    class_="hit-note",
                ),
                *(
                    [_spashiny_globals.cloud_example_status("hit-sm-example-status")]
                    if _spashiny_globals.SPASHINY_WEB_PLATFORM
                    else []
                ),
                _spashiny_ctx.ui.br(),
                _spashiny_ctx.ui.layout_columns(
                    _spashiny_ctx.ui.div(
                        {"class": "hit-soft-card"},
                        _spashiny_ctx.ui.div("Operation Status", class_="hit-plot-title"),
                        _spashiny_ctx.ui.output_ui("sm_merge_status_display"),
                    ),
                    _spashiny_ctx.ui.div(
                        {"class": "hit-soft-card"},
                        _spashiny_ctx.ui.div("Merge Summary", class_="hit-plot-title"),
                        _spashiny_ctx.ui.output_ui("sm_merge_result"),
                    ),
                    col_widths=(6, 6),
                ),
            ),
            _spashiny_ctx.ui.div(
                {"class": "hit-panel"},
                _spashiny_ctx.ui.div("Merge and SVM Analysis", class_="hit-section-title"),
                _spashiny_ctx.ui.div(
                    "Configure merge behavior and run spatially variable metabolite screening before model integration.",
                    class_="hit-note",
                ),
                _spashiny_ctx.ui.layout_columns(
                    _spashiny_ctx.ui.input_select(
                        "sm_merge_method",
                        "Merge Method",
                        {"concat": "Concatenate", "intersect": "Feature Intersection"},
                        selected="concat",
                    ),
                    _spashiny_ctx.ui.input_checkbox(
                        "sm_normalize", "Normalize After Merge", value=True
                    ),
                    _spashiny_ctx.ui.input_numeric(
                        "svm_top_genes", "Top Variable Features", value=2000, min=100, max=5000
                    ),
                    col_widths=(4, 4, 4),
                ),
                _spashiny_ctx.ui.layout_columns(
                    _spashiny_ctx.ui.input_action_button(
                        "run_svm_analysis", "Run SVM Analysis", class_="btn-warning", width="100%"
                    ),
                    col_widths=(12,),
                ),
            ),
            _spashiny_ctx.ui.div(
                {"class": "hit-panel"},
                _spashiny_ctx.ui.div("ConditionalVAE Integration", class_="hit-section-title"),
                _spashiny_ctx.ui.div(
                    "Model architecture and training use the installed SpatialMETA defaults; only data preparation and compute routing remain configurable.",
                    class_="hit-note",
                ),
                _spashiny_ctx.ui.layout_columns(_spashiny_ctx.ui.div(), col_widths=(6, 6)),
                _spashiny_ctx.ui.div(
                    {"class": "hit-note"}, _spashiny_ctx.ui.output_ui("vae_resource_mode_details")
                ),
                _spashiny_ctx.ui.input_select(
                    "vae_compute_resource",
                    "Compute resource",
                    _spashiny_globals.LAB_GPU_COMPUTE_RESOURCE_CHOICES,
                    selected="auto",
                ),
                _spashiny_ctx.ui.div(),
                _spashiny_ctx.ui.br(),
                _spashiny_ctx.ui.layout_columns(
                    _spashiny_ctx.ui.input_action_button(
                        "run_vae_integration",
                        "Run ConditionalVAE Integration",
                        class_="btn-primary",
                        width="100%",
                    ),
                    _spashiny_ctx.ui.download_button(
                        "download_integrated_sm",
                        "Download Integrated Data",
                        class_="btn-success",
                        width="100%",
                    ),
                    _spashiny_ctx.ui.download_button(
                        "download_vae_model",
                        "Download VAE Model",
                        class_="btn-secondary",
                        width="100%",
                    ),
                    _spashiny_ctx.ui.download_button(
                        "download_hit_tables_zip",
                        "Download Tables CSV",
                        class_="btn-secondary",
                        width="100%",
                    ),
                    col_widths=(3, 3, 3, 3),
                ),
                _spashiny_ctx.ui.output_ui("hit_sm_cloud_training_progress"),
            ),
            _spashiny_ctx.ui.div(
                {"class": "hit-panel"},
                _spashiny_ctx.ui.div("Clustering and Embedding", class_="hit-section-title"),
                _spashiny_ctx.ui.div(
                    "Neighborhood graph construction and UMAP parameters are hidden below as advanced adjustment controls.",
                    class_="hit-note",
                ),
                _spashiny_ctx.ui.accordion(
                    _spashiny_ctx.ui.accordion_panel(
                        "Advanced Adjustment - Clustering Parameters",
                        _spashiny_ctx.ui.layout_columns(
                            _spashiny_ctx.ui.input_numeric(
                                "clustering_neighbors", "Neighbors", value=15, min=5, max=50, step=1
                            ),
                            _spashiny_ctx.ui.input_numeric(
                                "clustering_resolution",
                                "Clustering Resolution",
                                value=1.0,
                                min=0.1,
                                max=2.0,
                                step=0.1,
                            ),
                            col_widths=(6, 6),
                        ),
                        _spashiny_ctx.ui.layout_columns(
                            _spashiny_ctx.ui.input_numeric(
                                "umap_min_dist",
                                "UMAP Min Distance",
                                value=1.0,
                                min=0.1,
                                max=5.0,
                                step=0.1,
                            ),
                            _spashiny_ctx.ui.input_numeric(
                                "umap_spread", "UMAP Spread", value=1.0, min=0.1, max=5.0, step=0.1
                            ),
                            col_widths=(6, 6),
                        ),
                    ),
                    open=False,
                    multiple=True,
                ),
                _spashiny_ctx.ui.br(),
                _spashiny_ctx.ui.layout_columns(
                    _spashiny_ctx.ui.input_action_button(
                        "run_clustering", "Run Clustering Analysis", class_="btn-info", width="100%"
                    ),
                    col_widths=(12,),
                ),
            ),
            _spashiny_ctx.ui.div(
                {"class": "hit-panel"},
                _spashiny_ctx.ui.div("Workflow Status", class_="hit-section-title"),
                _spashiny_ctx.ui.layout_columns(
                    _spashiny_ctx.ui.div(
                        {"class": "hit-status-card"},
                        _spashiny_ctx.ui.div("Samples", class_="hit-status-title"),
                        _spashiny_ctx.ui.div(
                            _spashiny_ctx.ui.output_text("sm_sample_count"),
                            class_="hit-status-value",
                        ),
                    ),
                    _spashiny_ctx.ui.div(
                        {"class": "hit-status-card"},
                        _spashiny_ctx.ui.div("Cells / Spots", class_="hit-status-title"),
                        _spashiny_ctx.ui.div(
                            _spashiny_ctx.ui.output_text("sm_total_cells"),
                            class_="hit-status-value",
                        ),
                    ),
                    _spashiny_ctx.ui.div(
                        {"class": "hit-status-card"},
                        _spashiny_ctx.ui.div("Features", class_="hit-status-title"),
                        _spashiny_ctx.ui.div(
                            _spashiny_ctx.ui.output_text("sm_total_features"),
                            class_="hit-status-value",
                        ),
                    ),
                    col_widths=(4, 4, 4),
                ),
                _spashiny_ctx.ui.br(),
                _spashiny_ctx.ui.div(
                    {"class": "hit-soft-card"},
                    _spashiny_ctx.ui.div("Integration Status", class_="hit-plot-title"),
                    _spashiny_ctx.ui.output_ui("vae_integration_status"),
                ),
                _spashiny_ctx.ui.div(
                    {"class": "hit-soft-card"},
                    _spashiny_ctx.ui.div("Model Information", class_="hit-plot-title"),
                    _spashiny_ctx.ui.output_ui("vae_model_info"),
                ),
                _spashiny_ctx.ui.div(
                    {"class": "hit-soft-card"},
                    _spashiny_ctx.ui.div("Debug Information", class_="hit-plot-title"),
                    _spashiny_ctx.ui.output_ui("vae_integration_debug_info"),
                ),
            ),
            _spashiny_ctx.ui.div(
                {"class": "hit-panel"},
                _spashiny_ctx.ui.div("Tables and Structured Outputs", class_="hit-section-title"),
                _spashiny_ctx.ui.div(
                    {"class": "hit-plot-card"},
                    _spashiny_ctx.ui.div("Sample Statistics", class_="hit-plot-title"),
                    _spashiny_ctx.ui.div(
                        {"class": "hit-table-shell"},
                        _spashiny_ctx.ui.output_table("sm_sample_stats_table"),
                    ),
                ),
                _spashiny_ctx.ui.div(
                    {"class": "hit-plot-card"},
                    _spashiny_ctx.ui.div("Merged Sample Statistics", class_="hit-plot-title"),
                    _spashiny_ctx.ui.div(
                        {"class": "hit-table-shell"},
                        _spashiny_ctx.ui.output_table("sm_merged_stats"),
                    ),
                ),
                _spashiny_ctx.ui.div(
                    {"class": "hit-plot-card"},
                    _spashiny_ctx.ui.div("SVM Results", class_="hit-plot-title"),
                    _spashiny_ctx.ui.div(
                        {"class": "hit-table-shell"},
                        _spashiny_ctx.ui.output_table("svm_results_table"),
                    ),
                ),
                _spashiny_ctx.ui.div(
                    {"class": "hit-plot-card"},
                    _spashiny_ctx.ui.div("Data Structure", class_="hit-plot-title"),
                    _spashiny_ctx.ui.div(
                        {"class": "hit-table-shell"},
                        _spashiny_ctx.ui.output_ui("data_structure_info"),
                    ),
                ),
            ),
            _spashiny_ctx.ui.div(
                {"class": "hit-panel"},
                _spashiny_ctx.ui.div("Visualization", class_="hit-section-title"),
                _spashiny_ctx.ui.div(
                    "Each figure is displayed inside a large square card. The plotting canvas is intentionally larger than the visible viewport, so you can scroll inside the card to inspect details without image compression.",
                    class_="hit-note",
                ),
                _spashiny_ctx.ui.div(
                    {"class": "hit-plot-card"},
                    _spashiny_ctx.ui.div("Sample Size Distribution", class_="hit-plot-title"),
                    _spashiny_ctx.ui.output_ui("hit_sm_sample_size_downloads"),
                    _spashiny_ctx.ui.br(),
                    _spashiny_ctx.ui.div(
                        {"class": "hit-pan-shell"},
                        _spashiny_ctx.ui.div(
                            {"class": "hit-pan-canvas"},
                            _spashiny_ctx.ui.output_ui("hit_sm_sample_size_worker_plot"),
                        ),
                    ),
                ),
                _spashiny_ctx.ui.div(
                    {"class": "hit-plot-card"},
                    _spashiny_ctx.ui.div("Feature Intensity Distribution", class_="hit-plot-title"),
                    _spashiny_ctx.ui.output_ui("hit_sm_feature_distribution_downloads"),
                    _spashiny_ctx.ui.br(),
                    _spashiny_ctx.ui.div(
                        {"class": "hit-pan-shell"},
                        _spashiny_ctx.ui.div(
                            {"class": "hit-pan-canvas"},
                            _spashiny_ctx.ui.output_ui("hit_sm_feature_distribution_worker_plot"),
                        ),
                    ),
                ),
                _spashiny_ctx.ui.div(
                    {"class": "hit-plot-card"},
                    _spashiny_ctx.ui.div("SVM Visualization", class_="hit-plot-title"),
                    _spashiny_ctx.ui.output_ui("hit_sm_svm_downloads"),
                    _spashiny_ctx.ui.br(),
                    _spashiny_ctx.ui.div(
                        {"class": "hit-pan-shell"},
                        _spashiny_ctx.ui.div(
                            {"class": "hit-pan-canvas"},
                            _spashiny_ctx.ui.output_ui("hit_sm_svm_worker_plot"),
                        ),
                    ),
                ),
                _spashiny_ctx.ui.div(
                    {"class": "hit-plot-card"},
                    _spashiny_ctx.ui.div("Debatched UMAP", class_="hit-plot-title"),
                    _spashiny_ctx.ui.download_button(
                        "download_sm_debatch_umap_plot",
                        "Download PNG",
                        class_="btn-secondary",
                        width="100%",
                    ),
                    _spashiny_ctx.ui.download_button(
                        "download_sm_debatch_umap_pdf",
                        "Download Editable PDF",
                        class_="btn-secondary",
                        width="100%",
                    ),
                    _spashiny_ctx.ui.br(),
                    _spashiny_ctx.ui.div(
                        {"class": "hit-pan-shell"},
                        _spashiny_ctx.ui.div(
                            {"class": "hit-pan-canvas"},
                            _spashiny_globals.plot_output_with_palette(
                                "sm_debatch_umap", width="1300px", height="1300px"
                            ),
                        ),
                    ),
                ),
                _spashiny_ctx.ui.div(
                    {"class": "hit-plot-card"},
                    _spashiny_ctx.ui.div("Batch Effect Evaluation", class_="hit-plot-title"),
                    _spashiny_ctx.ui.download_button(
                        "download_sm_batch_effect_evaluation_plot",
                        "Download PNG",
                        class_="btn-secondary",
                        width="100%",
                    ),
                    _spashiny_ctx.ui.download_button(
                        "download_sm_batch_effect_evaluation_pdf",
                        "Download Editable PDF",
                        class_="btn-secondary",
                        width="100%",
                    ),
                    _spashiny_ctx.ui.br(),
                    _spashiny_ctx.ui.div(
                        {"class": "hit-pan-shell"},
                        _spashiny_ctx.ui.div(
                            {"class": "hit-pan-canvas"},
                            _spashiny_globals.plot_output_with_palette(
                                "sm_batch_effect_evaluation", width="1300px", height="1300px"
                            ),
                        ),
                    ),
                ),
                _spashiny_ctx.ui.div(),
            ),
        ),
    )


def ui(_spashiny_ctx, module):
    if module == "HIT_SM":
        return _view_1(_spashiny_ctx, module)
    raise ValueError("Unknown feature page: integration_multi_sm")
