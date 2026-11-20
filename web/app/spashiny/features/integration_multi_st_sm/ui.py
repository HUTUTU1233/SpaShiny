# Actual feature UI extracted from production. Feature: integration_multi_st_sm.
from spashiny._shared import runtime_globals as _spashiny_globals


def _view_1(_spashiny_ctx, module):
    vhit_css = """
            <style>
            :root {
                --vhit-bg: #f5f5f7;
                --vhit-card: rgba(255,255,255,0.90);
                --vhit-border: rgba(0,0,0,0.06);
                --vhit-text: #1d1d1f;
                --vhit-subtext: #6e6e73;
                --vhit-blue: #0071e3;
                --vhit-green: #34c759;
                --vhit-info: #5ac8fa;
                --vhit-gray: #8e8e93;
                --vhit-shadow: 0 10px 30px rgba(0,0,0,0.06);
                --vhit-shadow-hover: 0 16px 40px rgba(0,0,0,0.10);
                --vhit-radius-xl: 28px;
                --vhit-radius-lg: 22px;
                --vhit-radius-md: 18px;
            }

            body {
                background: linear-gradient(180deg, #f8f9fb 0%, #f2f4f8 100%);
                color: var(--vhit-text);
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display",
                            "SF Pro Text", "Helvetica Neue", Helvetica, Arial, sans-serif;
            }

            .vhit-shell {
                max-width: 1580px;
                margin: 0 auto;
                padding: 20px 18px 42px 18px;
            }

            .vhit-hero {
                background: linear-gradient(135deg, rgba(255,255,255,0.96), rgba(247,249,255,0.92));
                border: 1px solid rgba(255,255,255,0.7);
                border-radius: 34px;
                box-shadow: var(--vhit-shadow);
                padding: 30px 34px;
                margin-bottom: 24px;
                backdrop-filter: blur(18px);
                -webkit-backdrop-filter: blur(18px);
            }

            .vhit-title {
                font-size: 2.2rem;
                font-weight: 700;
                letter-spacing: -0.03em;
                margin: 0 0 8px 0;
                color: var(--vhit-text);
            }

            .vhit-subtitle {
                font-size: 1rem;
                color: var(--vhit-subtext);
                line-height: 1.75;
                margin: 0;
                max-width: 1000px;
            }

            .vhit-panel {
                background: var(--vhit-card);
                border: 1px solid rgba(255,255,255,0.58);
                border-radius: var(--vhit-radius-xl);
                box-shadow: var(--vhit-shadow);
                padding: 24px;
                margin-bottom: 22px;
                backdrop-filter: blur(18px);
                -webkit-backdrop-filter: blur(18px);
                transition: all 0.25s ease;
            }

            .vhit-panel:hover {
                transform: translateY(-2px);
                box-shadow: var(--vhit-shadow-hover);
            }

            .vhit-section-title {
                font-size: 1.18rem;
                font-weight: 700;
                letter-spacing: -0.02em;
                margin-bottom: 16px;
                color: var(--vhit-text);
            }

            .vhit-note {
                background: rgba(0,113,227,0.06);
                border: 1px solid rgba(0,113,227,0.08);
                border-radius: 18px;
                padding: 14px 16px;
                color: #1d3f72;
                font-size: 0.94rem;
                line-height: 1.7;
                margin-bottom: 16px;
            }

            .vhit-subnote {
                color: var(--vhit-subtext);
                font-size: 0.94rem;
                line-height: 1.7;
                margin-bottom: 12px;
            }

            .vhit-status-box {
                background: rgba(255,255,255,0.78);
                border: 1px solid rgba(0,0,0,0.04);
                border-radius: 20px;
                padding: 16px 18px;
                min-height: 96px;
            }

            .vhit-status-label {
                font-size: 0.82rem;
                font-weight: 600;
                color: var(--vhit-subtext);
                margin-bottom: 6px;
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }

            .vhit-status-value {
                font-size: 1.12rem;
                font-weight: 700;
                color: var(--vhit-text);
            }

            .vhit-soft-card {
                background: rgba(255,255,255,0.78);
                border: 1px solid rgba(0,0,0,0.04);
                border-radius: 24px;
                padding: 18px;
                margin-bottom: 16px;
            }

            .vhit-plot-card {
                background: rgba(255,255,255,0.80);
                border: 1px solid rgba(0,0,0,0.04);
                border-radius: 24px;
                padding: 16px;
                margin-bottom: 18px;
                height: 100%;
            }

            .vhit-plot-title {
                font-size: 1rem;
                font-weight: 700;
                margin-bottom: 12px;
                letter-spacing: -0.01em;
                color: var(--vhit-text);
            }

            .vhit-square-shell {
                width: 100%;
                aspect-ratio: 1 / 1;
                min-height: 520px;
                background: #ffffff;
                border: 1px solid rgba(0,0,0,0.05);
                border-radius: 20px;
                padding: 10px;
                overflow: hidden;
            }

            .vhit-square-shell .shiny-plot-output,
            .vhit-square-shell img,
            .vhit-square-shell canvas,
            .vhit-square-shell svg {
                width: 100% !important;
                height: 100% !important;
                display: block;
            }

            .vhit-rect-shell {
                width: 100%;
                min-height: 340px;
                background: #ffffff;
                border: 1px solid rgba(0,0,0,0.05);
                border-radius: 20px;
                padding: 12px;
                overflow: auto;
            }

            .vhit-log-shell {
                background: linear-gradient(180deg, #f9fafb 0%, #f3f4f6 100%);
                color: #1f2937;
                border-radius: 22px;
                padding: 16px 18px;
                min-height: 180px;
                max-height: 260px;
                overflow-y: auto;
                font-family: "SFMono-Regular", Consolas, Menlo, monospace;
                font-size: 0.92rem;
                line-height: 1.6;
                border: 1px solid rgba(0,0,0,0.05);
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
                color: var(--vhit-text) !important;
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

            .nav-tabs .nav-link {
                border: none !important;
                border-radius: 999px !important;
                color: var(--vhit-subtext);
                font-weight: 600;
                padding: 10px 16px;
                margin-right: 8px;
            }

            .nav-tabs .nav-link.active {
                background: rgba(0,113,227,0.10) !important;
                color: var(--vhit-blue) !important;
            }

            @media (max-width: 992px) {
                .vhit-square-shell {
                    min-height: 420px;
                }
            }
            </style>
            """
    return _spashiny_ctx.ui.page_fluid(
        _spashiny_ctx.ui.HTML(vhit_css),
        _spashiny_ctx.ui.div(
            {"class": "vhit-shell"},
            _spashiny_ctx.ui.div(
                {"class": "vhit-hero"},
                _spashiny_ctx.ui.h1("VHIT Multisample ST-SM Integration", class_="vhit-title"),
                _spashiny_ctx.ui.p(
                    "Sample setup, multisample upload, normalization, quality control, and ConditionalVAE-based multimodal integration in a clean vertical layout.",
                    class_="vhit-subtitle",
                ),
            ),
            _spashiny_ctx.ui.div(
                {"class": "vhit-panel"},
                _spashiny_ctx.ui.div("Sample Setup and Data Upload", class_="vhit-section-title"),
                _spashiny_ctx.ui.div(
                    "Set sample names first, then upload .h5ad files, and finally merge them into one working dataset.",
                    class_="vhit-note",
                ),
                _spashiny_ctx.ui.layout_columns(
                    _spashiny_ctx.ui.input_text(
                        "sample_names_input",
                        "Sample Name List",
                        value="R114_T, S15_T, X49_T, Y27_T, Y7_T",
                        placeholder="Enter sample names separated by commas",
                    ),
                    _spashiny_ctx.ui.input_action_button(
                        "confirm_samples_btn",
                        "Confirm Sample Names",
                        class_="btn-primary",
                        width="100%",
                    ),
                    col_widths=(9, 3),
                ),
                _spashiny_ctx.ui.layout_columns(
                    _spashiny_ctx.ui.input_file(
                        "data_upload",
                        "Select Data Files (.h5ad)",
                        multiple=True,
                        accept=[".h5ad"],
                        width="100%",
                    ),
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.input_action_button(
                            "load_vhit_joint_example",
                            "Load bundled joint examples",
                            class_=_spashiny_globals.cloud_example_button_class("btn-secondary"),
                            width="100%",
                            **_spashiny_globals.cloud_example_action_attrs(
                                "joint-five-sample-vhit-example", "vhit", "vhit-example-status"
                            ),
                        ),
                        _spashiny_ctx.ui.div(
                            _spashiny_globals.example_source_note(
                                "Example source: user_data/input/joint",
                                "Cloud example: five raw joint h5ad samples are bound to this session on click.",
                            ),
                            class_="vhit-subnote",
                        ),
                        *(
                            [_spashiny_globals.cloud_example_status("vhit-example-status")]
                            if _spashiny_globals.SPASHINY_WEB_PLATFORM
                            else []
                        ),
                    ),
                    col_widths=(8, 4),
                ),
                _spashiny_ctx.ui.layout_columns(
                    _spashiny_ctx.ui.input_select(
                        "var_reference_sample",
                        "Reference Sample for Variables",
                        choices={},
                        selected=None,
                    ),
                    _spashiny_ctx.ui.input_action_button(
                        "process_files_btn",
                        "Process Uploaded Files",
                        class_="btn-success",
                        width="100%",
                    ),
                    _spashiny_ctx.ui.input_action_button(
                        "merge_data_btn", "Merge Data", class_="btn-info", width="100%"
                    ),
                    col_widths=(6, 3, 3),
                ),
                _spashiny_ctx.ui.br(),
                _spashiny_ctx.ui.layout_columns(
                    _spashiny_ctx.ui.div(
                        {"class": "vhit-soft-card"},
                        _spashiny_ctx.ui.div("Status", class_="vhit-plot-title"),
                        _spashiny_ctx.ui.output_ui("status_display"),
                        _spashiny_ctx.ui.output_ui("file_processing_results"),
                        _spashiny_ctx.ui.output_ui("merge_results"),
                    ),
                    _spashiny_ctx.ui.div(
                        {"class": "vhit-soft-card"},
                        _spashiny_ctx.ui.div("Downloads", class_="vhit-plot-title"),
                        _spashiny_ctx.ui.layout_columns(
                            _spashiny_ctx.ui.download_button(
                                "download_merged_data",
                                "Download Merged Data",
                                class_="btn-primary",
                                width="100%",
                            ),
                            _spashiny_ctx.ui.download_button(
                                "download_processing_report",
                                "Download Processing Report",
                                class_="btn-secondary",
                                width="100%",
                            ),
                            col_widths=(6, 6),
                        ),
                        _spashiny_ctx.ui.download_button(
                            "download_vhit_tables_zip",
                            "Download Tables CSV",
                            class_="btn-secondary",
                            width="100%",
                        ),
                    ),
                    col_widths=(8, 4),
                ),
                _spashiny_ctx.ui.br(),
                _spashiny_ctx.ui.navset_tab(
                    _spashiny_ctx.ui.nav_panel(
                        "Sample Distribution",
                        _spashiny_ctx.ui.div(
                            {"class": "vhit-plot-card"},
                            _spashiny_ctx.ui.div("Sample Distribution", class_="vhit-plot-title"),
                            _spashiny_ctx.ui.div(
                                {"class": "vhit-rect-shell"},
                                _spashiny_ctx.ui.output_ui("sample_distribution_display"),
                            ),
                        ),
                    ),
                    _spashiny_ctx.ui.nav_panel(
                        "Data Overview",
                        _spashiny_ctx.ui.div(
                            {"class": "vhit-plot-card"},
                            _spashiny_ctx.ui.div("Data Overview", class_="vhit-plot-title"),
                            _spashiny_ctx.ui.div(
                                {"class": "vhit-rect-shell"},
                                _spashiny_ctx.ui.output_table("data_overview_table"),
                            ),
                        ),
                    ),
                ),
            ),
            _spashiny_ctx.ui.div(
                {"class": "vhit-panel"},
                _spashiny_ctx.ui.div(
                    "Normalization and Quality Control", class_="vhit-section-title"
                ),
                _spashiny_ctx.ui.div(
                    "Core controls remain visible. Advanced filtering options are collapsed below.",
                    class_="vhit-note",
                ),
                _spashiny_ctx.ui.layout_columns(
                    _spashiny_ctx.ui.input_numeric(
                        "vhit_target_sum_sm", "SM Target Sum", value=10000
                    ),
                    _spashiny_ctx.ui.input_numeric(
                        "vhit_target_sum_st", "ST Target Sum", value=10000
                    ),
                    _spashiny_ctx.ui.input_numeric(
                        "vhit_min_total_intensity", "Minimum Total Intensity", value=100000
                    ),
                    _spashiny_ctx.ui.input_numeric(
                        "vhit_max_total_counts", "Maximum Total Counts", value=40000
                    ),
                    _spashiny_ctx.ui.input_numeric(
                        "vhit_n_top_genes", "Top Variable Genes", value=2500
                    ),
                    _spashiny_ctx.ui.input_numeric(
                        "vhit_n_top_metabolites", "Top Variable Metabolites", value=1000
                    ),
                    col_widths=(4, 4, 4, 4, 4, 4),
                ),
                _spashiny_ctx.ui.accordion(
                    _spashiny_ctx.ui.accordion_panel(
                        "Advanced Adjustment",
                        _spashiny_ctx.ui.layout_columns(
                            _spashiny_ctx.ui.input_text("batch_key", "Batch Key", value="sample"),
                            _spashiny_ctx.ui.input_numeric(
                                "min_samples", "Minimum Samples", value=3
                            ),
                            _spashiny_ctx.ui.input_numeric(
                                "min_frac", "Minimum Fraction", value=0.9
                            ),
                            _spashiny_ctx.ui.input_numeric("min_logfc", "Minimum logFC", value=3.0),
                            col_widths=(3, 3, 3, 3),
                        ),
                        _spashiny_ctx.ui.div(
                            "Use these controls only when you want stricter feature filtering or batch-aware constraints.",
                            class_="vhit-subnote",
                        ),
                    ),
                    open=False,
                    multiple=True,
                ),
                _spashiny_ctx.ui.br(),
                _spashiny_ctx.ui.layout_columns(
                    _spashiny_ctx.ui.input_action_button(
                        "run_normalization_qc",
                        "Run Normalization and QC",
                        class_="btn-primary",
                        width="100%",
                    ),
                    _spashiny_ctx.ui.download_button(
                        "download_processed_data",
                        "Download Processed Data",
                        class_="btn-success",
                        width="100%",
                    ),
                    col_widths=(6, 6),
                ),
                _spashiny_ctx.ui.br(),
                _spashiny_ctx.ui.output_ui("normalization_status"),
                _spashiny_ctx.ui.br(),
                _spashiny_ctx.ui.layout_columns(
                    _spashiny_ctx.ui.div(
                        {"class": "vhit-status-box"},
                        _spashiny_ctx.ui.div("Status", class_="vhit-status-label"),
                        _spashiny_ctx.ui.div(
                            _spashiny_ctx.ui.output_text("vhit_qc_status"),
                            class_="vhit-status-value",
                        ),
                    ),
                    _spashiny_ctx.ui.div(
                        {"class": "vhit-status-box"},
                        _spashiny_ctx.ui.div("Cells", class_="vhit-status-label"),
                        _spashiny_ctx.ui.div(
                            _spashiny_ctx.ui.output_text("cell_count"), class_="vhit-status-value"
                        ),
                    ),
                    _spashiny_ctx.ui.div(
                        {"class": "vhit-status-box"},
                        _spashiny_ctx.ui.div("Genes", class_="vhit-status-label"),
                        _spashiny_ctx.ui.div(
                            _spashiny_ctx.ui.output_text("gene_count"), class_="vhit-status-value"
                        ),
                    ),
                    col_widths=(4, 4, 4),
                ),
                _spashiny_ctx.ui.br(),
                _spashiny_ctx.ui.layout_columns(
                    _spashiny_ctx.ui.div(
                        {"class": "vhit-plot-card"},
                        _spashiny_ctx.ui.div("QC Violin Plot", class_="vhit-plot-title"),
                        _spashiny_ctx.ui.div(
                            {"class": "vhit-rect-shell"},
                            _spashiny_ctx.ui.output_ui("qc_violin_display"),
                        ),
                    ),
                    _spashiny_ctx.ui.div(
                        {"class": "vhit-plot-card"},
                        _spashiny_ctx.ui.div("QC Scatter Plot", class_="vhit-plot-title"),
                        _spashiny_ctx.ui.div(
                            {"class": "vhit-rect-shell"},
                            _spashiny_ctx.ui.output_ui("qc_scatter_display"),
                        ),
                    ),
                    col_widths=(6, 6),
                ),
                _spashiny_ctx.ui.layout_columns(
                    _spashiny_ctx.ui.div(
                        {"class": "vhit-plot-card"},
                        _spashiny_ctx.ui.div(
                            "Spatially Variable Features", class_="vhit-plot-title"
                        ),
                        _spashiny_ctx.ui.div(
                            {"class": "vhit-rect-shell"},
                            _spashiny_ctx.ui.output_ui("spatial_variable_display"),
                        ),
                    ),
                    _spashiny_ctx.ui.div(
                        {"class": "vhit-plot-card"},
                        _spashiny_ctx.ui.div(
                            "Top Spatial Variable Features", class_="vhit-plot-title"
                        ),
                        _spashiny_ctx.ui.div(
                            {"class": "vhit-rect-shell"},
                            _spashiny_ctx.ui.output_table("top_spatial_genes_table"),
                        ),
                    ),
                    col_widths=(6, 6),
                ),
                _spashiny_ctx.ui.div(
                    {"class": "vhit-plot-card"},
                    _spashiny_ctx.ui.div("QC Statistics", class_="vhit-plot-title"),
                    _spashiny_ctx.ui.div(
                        {"class": "vhit-rect-shell"},
                        _spashiny_ctx.ui.output_table("qc_statistics_table"),
                    ),
                ),
            ),
            _spashiny_ctx.ui.div(
                {"class": "vhit-panel"},
                _spashiny_ctx.ui.div("ConditionalVAE Integration", class_="vhit-section-title"),
                _spashiny_ctx.ui.div(
                    "Training controls stay on top. Advanced model and training parameters are placed in collapsible panels.",
                    class_="vhit-note",
                ),
                _spashiny_ctx.ui.layout_columns(
                    _spashiny_ctx.ui.div(),
                    _spashiny_ctx.ui.input_numeric(
                        "vhit_cvae_target_sum_sm",
                        "SM Target Sum",
                        value=1000,
                        min=100,
                        max=10000,
                        step=100,
                    ),
                    _spashiny_ctx.ui.input_numeric(
                        "vhit_cvae_target_sum_st", "ST Target Sum", value=None
                    ),
                    col_widths=(4, 4, 4),
                ),
                _spashiny_ctx.ui.div(
                    {"class": "vhit-subnote"},
                    _spashiny_ctx.ui.output_ui("vhit_resource_mode_details"),
                ),
                _spashiny_ctx.ui.input_select(
                    "vhit_compute_resource",
                    "Compute resource",
                    _spashiny_globals.LAB_GPU_COMPUTE_RESOURCE_CHOICES,
                    selected="auto",
                ),
                _spashiny_ctx.ui.div(),
                _spashiny_ctx.ui.br(),
                _spashiny_ctx.ui.layout_columns(
                    _spashiny_ctx.ui.input_action_button(
                        "run_cvae_training",
                        "Run ConditionalVAE Training",
                        class_="btn-primary",
                        width="100%",
                    ),
                    _spashiny_ctx.ui.download_button(
                        "download_cvae_results",
                        "Download Integration Results",
                        class_="btn-success",
                        width="100%",
                    ),
                    _spashiny_ctx.ui.download_button(
                        "download_vhit_cvae_report_pdf",
                        "Download Report PDF",
                        class_="btn-secondary",
                        width="100%",
                    ),
                    col_widths=(4, 4, 4),
                ),
                _spashiny_ctx.ui.br(),
                _spashiny_ctx.ui.output_ui("training_progress"),
                _spashiny_ctx.ui.br(),
                _spashiny_ctx.ui.layout_columns(
                    _spashiny_ctx.ui.div(
                        {"class": "vhit-status-box"},
                        _spashiny_ctx.ui.div("Training Status", class_="vhit-status-label"),
                        _spashiny_ctx.ui.div(
                            _spashiny_ctx.ui.output_text("vhit_training_status"),
                            class_="vhit-status-value",
                        ),
                    ),
                    _spashiny_ctx.ui.div(
                        {"class": "vhit-status-box"},
                        _spashiny_ctx.ui.div("Training Epochs", class_="vhit-status-label"),
                        _spashiny_ctx.ui.div(
                            _spashiny_ctx.ui.output_text("training_epochs"),
                            class_="vhit-status-value",
                        ),
                    ),
                    _spashiny_ctx.ui.div(
                        {"class": "vhit-status-box"},
                        _spashiny_ctx.ui.div("Final Loss", class_="vhit-status-label"),
                        _spashiny_ctx.ui.div(
                            _spashiny_ctx.ui.output_text("final_loss"), class_="vhit-status-value"
                        ),
                    ),
                    col_widths=(4, 4, 4),
                ),
                _spashiny_ctx.ui.br(),
                _spashiny_ctx.ui.div(
                    {"class": "vhit-plot-card"},
                    _spashiny_ctx.ui.div("Training Logs", class_="vhit-plot-title"),
                    _spashiny_ctx.ui.div(
                        {"class": "vhit-log-shell"},
                        _spashiny_ctx.ui.output_ui("training_logs_display"),
                    ),
                ),
                _spashiny_ctx.ui.div(),
                _spashiny_ctx.ui.layout_columns(
                    _spashiny_ctx.ui.div(
                        {"class": "vhit-plot-card"},
                        _spashiny_ctx.ui.div("UMAP by Sample", class_="vhit-plot-title"),
                        _spashiny_ctx.ui.div(
                            {"class": "vhit-square-shell"},
                            _spashiny_globals.plot_output_with_palette(
                                "umap_by_sample_plot", width="100%", height="540px"
                            ),
                        ),
                    ),
                    _spashiny_ctx.ui.div(
                        {"class": "vhit-plot-card"},
                        _spashiny_ctx.ui.div(
                            "VAE Clusters (Latent Embedding)", class_="vhit-plot-title"
                        ),
                        _spashiny_ctx.ui.div(
                            {"class": "vhit-square-shell"},
                            _spashiny_ctx.ui.output_ui("vhit_latent10_cluster_display"),
                        ),
                    ),
                    col_widths=(6, 6),
                ),
                _spashiny_ctx.ui.layout_columns(
                    _spashiny_ctx.ui.div(
                        {"class": "vhit-plot-card"},
                        _spashiny_ctx.ui.div(
                            "Latent Embedding Statistics", class_="vhit-plot-title"
                        ),
                        _spashiny_ctx.ui.div(
                            {"class": "vhit-rect-shell"},
                            _spashiny_ctx.ui.output_table("latent_embedding_table"),
                        ),
                    ),
                    _spashiny_ctx.ui.div(
                        {"class": "vhit-plot-card"},
                        _spashiny_ctx.ui.div("Modality Contribution", class_="vhit-plot-title"),
                        _spashiny_ctx.ui.div(
                            {"class": "vhit-square-shell"},
                            _spashiny_globals.plot_output_with_palette(
                                "modality_contribution_plot", width="100%", height="540px"
                            ),
                        ),
                    ),
                    col_widths=(6, 6),
                ),
                _spashiny_ctx.ui.layout_columns(
                    _spashiny_ctx.ui.div(
                        {"class": "vhit-plot-card"},
                        _spashiny_ctx.ui.div("Original vs Reconstructed", class_="vhit-plot-title"),
                        _spashiny_ctx.ui.div(
                            {"class": "vhit-square-shell"},
                            _spashiny_globals.plot_output_with_palette(
                                "reconstruction_quality_plot", width="100%", height="540px"
                            ),
                        ),
                    ),
                    _spashiny_ctx.ui.div(
                        {"class": "vhit-plot-card"},
                        _spashiny_ctx.ui.div("Reconstruction Error", class_="vhit-plot-title"),
                        _spashiny_ctx.ui.div(
                            {"class": "vhit-square-shell"},
                            _spashiny_globals.plot_output_with_palette(
                                "reconstruction_error_plot", width="100%", height="540px"
                            ),
                        ),
                    ),
                    col_widths=(6, 6),
                ),
                _spashiny_ctx.ui.layout_columns(
                    _spashiny_ctx.ui.div(
                        {"class": "vhit-plot-card"},
                        _spashiny_ctx.ui.div("Cluster Analysis", class_="vhit-plot-title"),
                        _spashiny_ctx.ui.div(
                            {"class": "vhit-square-shell"},
                            _spashiny_globals.plot_output_with_palette(
                                "cluster_analysis_plot", width="100%", height="540px"
                            ),
                        ),
                    ),
                    _spashiny_ctx.ui.div(
                        {"class": "vhit-plot-card"},
                        _spashiny_ctx.ui.div("Cluster Statistics", class_="vhit-plot-title"),
                        _spashiny_ctx.ui.div(
                            {"class": "vhit-rect-shell"},
                            _spashiny_ctx.ui.output_table("cluster_statistics_table"),
                        ),
                    ),
                    col_widths=(6, 6),
                ),
            ),
        ),
    )


def ui(_spashiny_ctx, module):
    if module == "VHIT_SM_ST":
        return _view_1(_spashiny_ctx, module)
    raise ValueError("Unknown feature page: integration_multi_st_sm")
