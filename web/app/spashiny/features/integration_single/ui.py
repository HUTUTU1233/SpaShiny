# Actual feature UI extracted from production. Feature: integration_single.
from spashiny._shared import runtime_globals as _spashiny_globals
from spashiny.features.feature_explorer import ui as _section_ui_feature_explorer


def _view_1(_spashiny_ctx, module):
    vit_sm_st_apple_css = """
            <style>
            :root {
                --apple-bg: #f5f5f7;
                --apple-card: rgba(255, 255, 255, 0.86);
                --apple-border: rgba(0, 0, 0, 0.06);
                --apple-shadow: 0 10px 30px rgba(0, 0, 0, 0.06);
                --apple-shadow-hover: 0 16px 40px rgba(0, 0, 0, 0.10);
                --apple-text: #1d1d1f;
                --apple-subtext: #6e6e73;
                --apple-blue: #0071e3;
                --apple-green: #34c759;
                --apple-red: #ff3b30;
                --apple-orange: #ff9f0a;
                --apple-radius-xl: 28px;
                --apple-radius-lg: 22px;
                --apple-radius-md: 18px;
            }

            body {
                background: linear-gradient(180deg, #f8f9fb 0%, #f2f4f8 100%);
                color: var(--apple-text);
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display",
                            "SF Pro Text", "Helvetica Neue", Helvetica, Arial, sans-serif;
            }

            .vit-page-shell {
                max-width: 1500px;
                margin: 0 auto;
                padding: 24px 20px 48px 20px;
            }

            .vit-hero {
                background: linear-gradient(135deg, rgba(255,255,255,0.94), rgba(248,250,255,0.90));
                border: 1px solid rgba(255,255,255,0.6);
                backdrop-filter: blur(18px);
                -webkit-backdrop-filter: blur(18px);
                border-radius: 34px;
                box-shadow: var(--apple-shadow);
                padding: 32px 36px;
                margin-bottom: 24px;
                position: relative;
                overflow: hidden;
            }

            .vit-hero::before {
                content: "";
                position: absolute;
                top: -80px;
                right: -80px;
                width: 220px;
                height: 220px;
                background: radial-gradient(circle, rgba(0,113,227,0.12) 0%, rgba(0,113,227,0.02) 65%, transparent 100%);
                border-radius: 50%;
            }

            .vit-title {
                font-size: 2.3rem;
                font-weight: 700;
                letter-spacing: -0.03em;
                margin: 0 0 8px 0;
            }

            .vit-subtitle {
                font-size: 1.02rem;
                color: var(--apple-subtext);
                margin: 0;
                max-width: 980px;
                line-height: 1.7;
            }

            .vit-stack {
                display: flex;
                flex-direction: column;
                gap: 22px;
            }

            .apple-panel {
                background: var(--apple-card);
                border: 1px solid rgba(255,255,255,0.55);
                backdrop-filter: blur(18px);
                -webkit-backdrop-filter: blur(18px);
                border-radius: var(--apple-radius-xl);
                box-shadow: var(--apple-shadow);
                padding: 26px;
                transition: all 0.28s ease;
            }

            .apple-panel:hover {
                transform: translateY(-2px);
                box-shadow: var(--apple-shadow-hover);
            }

            .apple-section-title {
                font-size: 1.25rem;
                font-weight: 700;
                letter-spacing: -0.02em;
                margin-bottom: 18px;
            }

            .apple-subsection-title {
                font-size: 1rem;
                font-weight: 600;
                color: var(--apple-text);
                margin: 18px 0 12px 0;
            }

            .apple-muted {
                color: var(--apple-subtext);
                font-size: 0.95rem;
                line-height: 1.7;
            }

            .btn, .btn-default, .btn-primary, .btn-success, .btn-danger, .btn-info, .btn-secondary {
                border-radius: 999px !important;
                padding: 12px 18px !important;
                font-weight: 600 !important;
                border: none !important;
                box-shadow: 0 8px 18px rgba(0,0,0,0.08);
                transition: all 0.22s ease !important;
            }

            .btn:hover {
                transform: translateY(-1px);
                box-shadow: 0 12px 24px rgba(0,0,0,0.12);
            }

            .btn-primary { background: linear-gradient(135deg, #0a84ff, #0071e3) !important; }
            .btn-success { background: linear-gradient(135deg, #34c759, #30b958) !important; }
            .btn-danger  { background: linear-gradient(135deg, #ff5e57, #ff3b30) !important; }
            .btn-info    { background: linear-gradient(135deg, #5ac8fa, #0a84ff) !important; }
            .btn-secondary { background: linear-gradient(135deg, #8e8e93, #6e6e73) !important; }

            .form-control, .form-select, .shiny-input-number input, input, select, textarea {
                border-radius: 18px !important;
                border: 1px solid rgba(0,0,0,0.08) !important;
                background: rgba(255,255,255,0.94) !important;
                box-shadow: none !important;
                padding: 12px 14px !important;
                min-height: 48px;
            }

            .control-label, label {
                font-weight: 600 !important;
                color: var(--apple-text) !important;
                margin-bottom: 8px !important;
            }

            .log-box {
                background: linear-gradient(180deg, #f9fafb 0%, #f3f4f6 100%);
                color: #1f2937;
                border-radius: 24px;
                padding: 18px;
                min-height: 260px;
                max-height: 420px;
                overflow-y: auto;
                font-family: "SFMono-Regular", Consolas, Menlo, monospace;
                font-size: 0.92rem;
                line-height: 1.6;
                border: 1px solid rgba(0,0,0,0.05);
            }

            .wide-plot {
                width: 100%;
                min-height: 520px;
                border-radius: 26px;
                overflow: hidden;
                background: rgba(255,255,255,0.68);
                border: 1px solid rgba(0,0,0,0.04);
                padding: 14px;
            }

            .square-plot {
                aspect-ratio: 1 / 1;
                width: 100%;
                border-radius: 24px;
                overflow: hidden;
                background: rgba(255,255,255,0.68);
                border: 1px solid rgba(0,0,0,0.04);
                padding: 12px;
            }

            .rect-plot {
                min-height: 520px;
                width: 100%;
                border-radius: 24px;
                overflow: hidden;
                background: rgba(255,255,255,0.68);
                border: 1px solid rgba(0,0,0,0.04);
                padding: 12px;
            }

            .plot-title {
                font-size: 1.05rem;
                font-weight: 700;
                margin-bottom: 12px;
                letter-spacing: -0.01em;
            }

            .metric-note {
                background: rgba(0,113,227,0.06);
                border: 1px solid rgba(0,113,227,0.08);
                border-radius: 20px;
                padding: 14px 16px;
                color: #1d3f72;
                font-size: 0.95rem;
                line-height: 1.65;
            }

            .table-shell {
                background: rgba(255,255,255,0.78);
                border-radius: 24px;
                padding: 18px;
                border: 1px solid rgba(0,0,0,0.04);
                overflow: hidden;
            }

            .config-summary-box {
                background: rgba(255,255,255,0.76);
                border: 1px solid rgba(0,0,0,0.04);
                border-radius: 20px;
                padding: 14px 18px;
                min-height: 56px;
                display: flex;
                align-items: center;
            }

            .training-control-bar {
                background: rgba(255,255,255,0.58);
                border-radius: 22px;
                padding: 16px;
                border: 1px solid rgba(0,0,0,0.04);
            }

            .download-stack {
                display: flex;
                flex-direction: column;
                gap: 14px;
            }

            .modal-content {
                border-radius: 30px !important;
                border: 1px solid rgba(255,255,255,0.55) !important;
                background: rgba(255,255,255,0.90) !important;
                backdrop-filter: blur(18px);
                -webkit-backdrop-filter: blur(18px);
                box-shadow: 0 20px 50px rgba(0,0,0,0.14) !important;
                padding: 8px;
            }

            .modal-header, .modal-footer {
                border: none !important;
                background: transparent !important;
            }

            .modal-body {
                padding: 24px 26px !important;
            }

            @media (max-width: 992px) {
                .wide-plot, .rect-plot {
                    min-height: 380px;
                }

                .square-plot {
                    min-height: 340px;
                }
            }
            </style>

            <script>
            document.addEventListener("DOMContentLoaded", function () {
                const cards = document.querySelectorAll(".apple-panel");
                cards.forEach((card, i) => {
                    card.style.opacity = "0";
                    card.style.transform = "translateY(18px)";
                    setTimeout(() => {
                        card.style.transition = "all 0.5s ease";
                        card.style.opacity = "1";
                        card.style.transform = "translateY(0)";
                    }, 60 * i);
                });
            });
            </script>
            """
    return (
        _spashiny_ctx.ui.page_fluid(
            _spashiny_ctx.ui.HTML(vit_sm_st_apple_css),
            _spashiny_ctx.ui.div(
                {"class": "vit-page-shell"},
                _spashiny_ctx.ui.div(
                    {"class": "vit-hero"},
                    _spashiny_ctx.ui.h1("SM-ST Joint Analysis", class_="vit-title"),
                    _spashiny_ctx.ui.p(
                        "A modern multimodal analysis workspace for Spatial Metabolomics and Spatial Transcriptomics integration, designed with an Apple-inspired interface for clean parameter control, model training, and rich visualization.",
                        class_="vit-subtitle",
                    ),
                ),
                _spashiny_ctx.ui.div(
                    {"class": "vit-stack"},
                    _spashiny_ctx.ui.div(
                        {"class": "apple-panel"},
                        _spashiny_ctx.ui.div("Processing Log", class_="apple-section-title"),
                        _spashiny_ctx.ui.div(
                            {"class": "log-box"},
                            _spashiny_ctx.ui.output_text_verbatim("console_output"),
                        ),
                    ),
                    _spashiny_ctx.ui.div(
                        {"class": "apple-panel"},
                        _spashiny_ctx.ui.div("Data Upload", class_="apple-section-title"),
                        _spashiny_ctx.ui.layout_columns(
                            _spashiny_ctx.ui.input_file(
                                "joint_data_upload",
                                "Upload Joint Data File (.h5ad)",
                                accept=[".h5ad"],
                                multiple=False,
                            ),
                            _spashiny_ctx.ui.input_text(
                                "sample_name", "Sample Name", value="Y7_T", placeholder="e.g. Y7_T"
                            ),
                            col_widths=(8, 4),
                        ),
                        _spashiny_ctx.ui.layout_columns(
                            _spashiny_ctx.ui.input_action_button(
                                "load_joint_y7_example",
                                "Load Y7_T Example",
                                class_=_spashiny_globals.cloud_example_button_class(
                                    "btn-secondary"
                                ),
                                width="100%",
                                **_spashiny_globals.cloud_example_action_attrs(
                                    "y7-joint-vit-example", "joint", "joint-example-status"
                                ),
                            ),
                            _spashiny_ctx.ui.div(
                                _spashiny_globals.example_source_note(
                                    "Example source: user_data/input/joint/adata_joint_Y7_T_raw.h5ad",
                                    "Cloud example: Y7_T raw joint h5ad is bound to this anonymous session on click.",
                                ),
                                class_="metric-note",
                            ),
                            col_widths=(4, 8),
                        ),
                        *(
                            [_spashiny_globals.cloud_example_status("joint-example-status")]
                            if _spashiny_globals.SPASHINY_WEB_PLATFORM
                            else []
                        ),
                        _spashiny_ctx.ui.br(),
                        _spashiny_ctx.ui.output_ui("data_status_indicator"),
                    ),
                    _spashiny_ctx.ui.div(
                        {"class": "apple-panel"},
                        _spashiny_ctx.ui.div(
                            "Data Preprocessing & Actions", class_="apple-section-title"
                        ),
                        _spashiny_ctx.ui.div(
                            "Preprocessing Parameters", class_="apple-subsection-title"
                        ),
                        _spashiny_ctx.ui.layout_columns(
                            _spashiny_ctx.ui.input_numeric(
                                "target_sum",
                                "Normalization Target Sum",
                                value=10000.0,
                                min=1000.0,
                                max=1000000.0,
                            ),
                            _spashiny_ctx.ui.input_numeric(
                                "n_top_genes",
                                "Number of Highly Variable Genes",
                                value=2000,
                                min=100,
                                max=5000,
                            ),
                            _spashiny_ctx.ui.input_numeric(
                                "n_top_metabolites",
                                "Number of Highly Variable Metabolites",
                                value=800,
                                min=100,
                                max=2000,
                            ),
                            col_widths=(4, 4, 4),
                        ),
                        _spashiny_ctx.ui.hr(),
                        _spashiny_ctx.ui.div("Actions", class_="apple-subsection-title"),
                        _spashiny_ctx.ui.layout_columns(
                            _spashiny_ctx.ui.input_action_button(
                                "process_joint_data",
                                "Process Joint Data",
                                class_="btn-primary",
                                width="100%",
                            ),
                            _spashiny_ctx.ui.input_action_button(
                                "preview_joint_data",
                                "Preview Data",
                                class_="btn-success",
                                width="100%",
                            ),
                            _spashiny_ctx.ui.input_action_button(
                                "debug_data", "Debug Data", class_="btn-secondary", width="100%"
                            ),
                            col_widths=(4, 4, 4),
                        ),
                    ),
                    _spashiny_ctx.ui.div(
                        {"class": "apple-panel"},
                        _spashiny_ctx.ui.div(
                            "Conditional VAE Training", class_="apple-section-title"
                        ),
                        _spashiny_ctx.ui.div("Data Preprocessing", class_="apple-subsection-title"),
                        _spashiny_ctx.ui.layout_columns(
                            _spashiny_ctx.ui.div(),
                            _spashiny_ctx.ui.input_numeric(
                                "target_sum_sm",
                                "SM Normalization Target Sum",
                                value=1000,
                                min=100,
                                max=10000,
                                step=100,
                            ),
                            _spashiny_ctx.ui.input_numeric(
                                "target_sum_st",
                                "ST Normalization Target Sum",
                                value=None,
                                min=100,
                                max=10000,
                                step=100,
                            ),
                            col_widths=(4, 4, 4),
                        ),
                        _spashiny_ctx.ui.div(
                            {"class": "metric-note"},
                            _spashiny_ctx.ui.output_ui("joint_resource_mode_details"),
                        ),
                        _spashiny_ctx.ui.tags.fieldset(
                            _spashiny_ctx.ui.input_select(
                                "joint_compute_resource",
                                "Compute resource",
                                {_spashiny_globals.SINGLE_SAMPLE_COMPUTE_RESOURCE: "GPU 1"},
                                selected=_spashiny_globals.SINGLE_SAMPLE_COMPUTE_RESOURCE,
                                selectize=False,
                            ),
                            disabled=True,
                        ),
                        _spashiny_ctx.ui.div(
                            "Model Configuration", class_="apple-subsection-title"
                        ),
                        _spashiny_ctx.ui.div(
                            {"class": "metric-note"},
                            "Default model settings are recommended for most workflows. Advanced architecture and reconstruction options can be customized if needed.",
                        ),
                        _spashiny_ctx.ui.br(),
                        _spashiny_ctx.ui.layout_columns(
                            _spashiny_ctx.ui.input_action_button(
                                "open_model_config_modal",
                                "Customize Model",
                                class_="btn-secondary",
                                width="100%",
                            ),
                            _spashiny_ctx.ui.div(
                                {"class": "config-summary-box apple-muted"},
                                _spashiny_ctx.ui.output_text("model_config_summary"),
                            ),
                            col_widths=(3, 9),
                        ),
                        _spashiny_ctx.ui.hr(),
                        _spashiny_ctx.ui.div(
                            "Training Configuration", class_="apple-subsection-title"
                        ),
                        _spashiny_ctx.ui.div(
                            {"class": "metric-note"},
                            "Default training settings are suitable for most analyses. Advanced optimization and hardware parameters can be adjusted if needed.",
                        ),
                        _spashiny_ctx.ui.br(),
                        _spashiny_ctx.ui.layout_columns(
                            _spashiny_ctx.ui.input_action_button(
                                "open_training_config_modal",
                                "Customize Training",
                                class_="btn-secondary",
                                width="100%",
                            ),
                            _spashiny_ctx.ui.div(
                                {"class": "config-summary-box apple-muted"},
                                _spashiny_ctx.ui.output_text("training_config_summary"),
                            ),
                            col_widths=(3, 9),
                        ),
                        _spashiny_ctx.ui.hr(),
                        _spashiny_ctx.ui.div("Training Controls", class_="apple-subsection-title"),
                        _spashiny_ctx.ui.div(
                            {"class": "training-control-bar"},
                            _spashiny_ctx.ui.layout_columns(
                                _spashiny_ctx.ui.input_action_button(
                                    "train_model",
                                    "Start Training",
                                    class_="btn-primary",
                                    width="100%",
                                ),
                                _spashiny_ctx.ui.input_action_button(
                                    "stop_training",
                                    "Stop Training",
                                    class_="btn-danger",
                                    width="100%",
                                ),
                                col_widths=(6, 6),
                            ),
                        ),
                        _spashiny_ctx.ui.br(),
                        _spashiny_ctx.ui.div(
                            "Reuse Trained Model", class_="apple-subsection-title"
                        ),
                        _spashiny_ctx.ui.div(),
                        _spashiny_ctx.ui.br(),
                        _spashiny_ctx.ui.layout_columns(
                            _spashiny_ctx.ui.download_button(
                                "download_model_config",
                                "Export Model Config",
                                class_="btn btn-secondary w-100",
                            ),
                            _spashiny_ctx.ui.input_file(
                                "import_model_config_file",
                                "Import Model Config (.json)",
                                accept=[".json"],
                                multiple=False,
                            ),
                            _spashiny_ctx.ui.input_action_button(
                                "import_model_config",
                                "Import Config and Skip Training",
                                class_="btn-secondary",
                                width="100%",
                            ),
                            col_widths=(3, 6, 3),
                        ),
                        _spashiny_ctx.ui.br(),
                        _spashiny_ctx.ui.output_text("training_status"),
                        _spashiny_ctx.ui.output_ui("vit_cloud_training_progress"),
                    ),
                    _spashiny_ctx.ui.div(
                        {"class": "apple-panel"},
                        _spashiny_ctx.ui.div(
                            "Post-processing & Analysis", class_="apple-section-title"
                        ),
                        _spashiny_ctx.ui.layout_columns(
                            _spashiny_ctx.ui.input_action_button(
                                "analyze_results",
                                "Analyze Training Results",
                                class_="btn-info",
                                width="100%",
                            ),
                            _spashiny_ctx.ui.download_button(
                                "download_analysis_results",
                                "Download Analysis Results",
                                class_="btn-success",
                                width="100%",
                            ),
                            col_widths=(6, 6),
                        ),
                    ),
                    _spashiny_ctx.ui.div(
                        {"class": "apple-panel"},
                        _spashiny_ctx.ui.div("UMAP Clustering", class_="plot-title"),
                        _spashiny_ctx.ui.div(
                            {
                                "class": "wide-plot",
                                "style": "width: min(800px, 100%); margin: 0 auto;",
                            },
                            _spashiny_globals.plot_output_with_palette(
                                "umap_plot", width="800px", height="560px"
                            ),
                        ),
                    ),
                    _spashiny_ctx.ui.div(
                        {"class": "apple-panel"},
                        _spashiny_ctx.ui.div("Spatial Clustering", class_="plot-title"),
                        _spashiny_ctx.ui.div(
                            {"class": "wide-plot"},
                            _spashiny_globals.plot_output_with_palette(
                                "spatial_cluster_plot", width="100%", height="560px"
                            ),
                        ),
                    ),
                    _spashiny_ctx.ui.div(
                        {"class": "apple-panel"},
                        _spashiny_ctx.ui.div(
                            "ST / SM Feature Explorer", class_="apple-section-title"
                        ),
                        _spashiny_ctx.ui.div(
                            {"class": "metric-note"},
                            "Select one ST gene and one SM m/z feature for spatial visualization. If nothing is selected, the app will automatically choose one gene and one m/z feature.",
                        ),
                        _spashiny_ctx.ui.br(),
                        _spashiny_ctx.ui.layout_columns(
                            _spashiny_ctx.ui.input_selectize(
                                "selected_st_feature",
                                "ST Feature (Gene)",
                                choices=[],
                                selected=None,
                                multiple=False,
                                options={"placeholder": "Search gene...", "maxOptions": 20},
                            ),
                            _spashiny_ctx.ui.input_selectize(
                                "selected_sm_feature",
                                "SM Feature (m/z)",
                                choices=[],
                                selected=None,
                                multiple=False,
                                options={"placeholder": "Search m/z...", "maxOptions": 20},
                            ),
                            col_widths=(6, 6),
                        ),
                        _spashiny_ctx.ui.br(),
                        _spashiny_ctx.ui.layout_columns(
                            _spashiny_ctx.ui.input_action_button(
                                "generate_feature_maps",
                                "Generate ST / SM Maps",
                                class_="btn-primary",
                                width="100%",
                            ),
                            _spashiny_ctx.ui.download_button(
                                "download_feature_maps_pdf",
                                "Download Current Feature Maps (PDF)",
                                class_="btn-success",
                                width="100%",
                            ),
                            col_widths=(6, 6),
                        ),
                        _spashiny_ctx.ui.br(),
                        _spashiny_ctx.ui.br(),
                        _spashiny_ctx.ui.div(
                            "Spatial Feature Map — Normalized Expression", class_="plot-title"
                        ),
                        _section_ui_feature_explorer._section_1(_spashiny_ctx),
                    ),
                    _section_ui_feature_explorer._section_2(_spashiny_ctx),
                    _spashiny_ctx.ui.div(
                        {"class": "apple-panel"},
                        _spashiny_ctx.ui.div("Modality Contribution", class_="plot-title"),
                        _spashiny_ctx.ui.div(
                            {"class": "wide-plot"},
                            _spashiny_globals.plot_output_with_palette(
                                "modality_contribution_spatial_plot", width="100%", height="560px"
                            ),
                        ),
                    ),
                    _spashiny_ctx.ui.div(
                        {"class": "apple-panel"},
                        _spashiny_ctx.ui.div("Modality Contribution Analysis", class_="plot-title"),
                        _spashiny_ctx.ui.div(
                            {"class": "wide-plot"},
                            _spashiny_globals.plot_output_with_palette(
                                "modality_contribution_violin_plot", width="100%", height="560px"
                            ),
                        ),
                        _spashiny_ctx.ui.download_button(
                            "download_modality_violin_pdf",
                            "Download Modality Contribution Violin PDF",
                            class_="btn btn-primary w-100 mt-3",
                        ),
                    ),
                    _spashiny_ctx.ui.div(
                        {"class": "apple-panel"},
                        _spashiny_ctx.ui.div("Cluster Statistics", class_="plot-title"),
                        _spashiny_ctx.ui.download_button(
                            "download_cluster_statistics_csv",
                            "Download Cluster Statistics CSV",
                            class_="btn btn-secondary w-100 mb-3",
                        ),
                        _spashiny_ctx.ui.div(
                            {"class": "table-shell"},
                            _spashiny_ctx.ui.output_data_frame("cluster_statistics"),
                        ),
                    ),
                    _spashiny_ctx.ui.div(
                        {"class": "apple-panel"},
                        _spashiny_ctx.ui.div("Downloads", class_="apple-section-title"),
                        _spashiny_ctx.ui.div(
                            {"class": "download-stack"},
                            _spashiny_ctx.ui.output_ui("joint_download_ui"),
                            _spashiny_ctx.ui.download_button(
                                "download_joint_h5ad", "Download Processed h5ad"
                            ),
                        ),
                        _spashiny_ctx.ui.div(
                            {"class": "apple-panel"},
                            _spashiny_ctx.ui.div(
                                "Export Analysis Figures", class_="apple-section-title"
                            ),
                            _spashiny_ctx.ui.row(
                                _spashiny_ctx.ui.column(
                                    3,
                                    _spashiny_ctx.ui.download_button(
                                        "download_umap_pdf",
                                        "Download UMAP PDF",
                                        class_="btn btn-primary w-100",
                                    ),
                                ),
                                _spashiny_ctx.ui.column(
                                    3,
                                    _spashiny_ctx.ui.download_button(
                                        "download_spatial_cluster_pdf",
                                        "Download Spatial Cluster PDF",
                                        class_="btn btn-primary w-100",
                                    ),
                                ),
                                _spashiny_ctx.ui.column(
                                    3,
                                    _spashiny_ctx.ui.download_button(
                                        "download_modality_pdf",
                                        "Download Modality Contribution PDF",
                                        class_="btn btn-primary w-100",
                                    ),
                                ),
                                _spashiny_ctx.ui.column(
                                    3,
                                    _spashiny_ctx.ui.download_button(
                                        "download_full_analysis_pdf",
                                        "Download Full Analysis Report PDF",
                                        class_="btn btn-success w-100",
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )


def ui(_spashiny_ctx, module):
    if module == "VIT_SM_ST":
        return _view_1(_spashiny_ctx, module)
    raise ValueError("Unknown feature page: integration_single")
