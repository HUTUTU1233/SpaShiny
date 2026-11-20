# Actual feature UI extracted from production. Feature: alignment_auto.
from spashiny._shared import runtime_globals as _spashiny_globals


def _view_1(_spashiny_ctx, module):
    return _spashiny_ctx.ui.page_fluid(
        _spashiny_ctx.ui.HTML(
            """
                <style>
                    body {
                        background: #f5f5f7;
                        color: #1d1d1f;
                        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", Arial, sans-serif;
                    }

                    .apple-page-title {
                        font-size: 30px;
                        font-weight: 700;
                        margin: 20px 0 28px 0;
                        color: #1d1d1f;
                        letter-spacing: -0.4px;
                    }

                    .apple-card {
                        background: rgba(255, 255, 255, 0.88);
                        backdrop-filter: blur(18px);
                        -webkit-backdrop-filter: blur(18px);
                        border: 1px solid rgba(0, 0, 0, 0.06);
                        border-radius: 24px;
                        padding: 18px;
                        box-shadow: 0 8px 28px rgba(0, 0, 0, 0.05);
                        margin-bottom: 22px;
                        height: 100%;
                    }

                    .apple-subtitle {
                        font-size: 20px;
                        font-weight: 600;
                        margin-bottom: 12px;
                        color: #1d1d1f;
                    }

                    .apple-muted {
                        color: #6e6e73;
                        font-size: 14px;
                        line-height: 1.6;
                        margin-bottom: 16px;
                    }

                    /* =========================
                    Step cards: uniform height
                    ========================= */
                    .step-card {
                        background: #fbfbfd;
                        border: 1px solid #e5e5ea;
                        border-radius: 20px;
                        padding: 20px;
                        min-height: 250px;
                        height: 100%;
                        display: flex;
                        flex-direction: column;
                        justify-content: space-between;
                        transition: all 0.2s ease;
                    }

                    .step-card:hover {
                        transform: translateY(-2px);
                        box-shadow: 0 8px 20px rgba(0,0,0,0.05);
                    }

                    .step-title {
                        font-size: 17px;
                        font-weight: 600;
                        color: #1d1d1f;
                        margin-bottom: 12px;
                    }

                    .step-body {
                        flex: 1;
                        display: flex;
                        flex-direction: column;
                    }

                    .step-controls {
                        margin-top: auto;
                    }

                    .step-meta {
                        display: inline-block;
                        margin-top: 8px;
                        padding: 6px 12px;
                        border-radius: 999px;
                        background: #f2f2f7;
                        border: 1px solid #e5e5ea;
                        color: #4a4a4f;
                        font-size: 13px;
                        font-weight: 500;
                        width: fit-content;
                    }

                    /* =========================
                    Log box
                    ========================= */
                    .apple-log-box {
                        background: #ffffff;
                        border: 1px solid #e5e5ea;
                        border-radius: 20px;
                        padding: 18px;
                        height: 260px;
                        overflow-y: auto;
                        font-family: SFMono-Regular, Menlo, Monaco, Consolas, monospace;
                        font-size: 12px;
                        line-height: 1.55;
                        color: #1d1d1f;
                        white-space: pre-wrap;
                    }

                    /* =========================
                    Plot boxes
                    ========================= */
                    .square-plot-box,
                    .raster-strip-plot-box,
                    .rect-plot-box,
                    .square-plot-box-large {
                        background: #ffffff;
                        border: 1px solid #e5e5ea;
                        border-radius: 20px;
                        padding: 12px;
                        overflow: hidden;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                    }

                    /* Step4 Raster: square */
                    .square-plot-box {
                        width: 100%;
                        height: 620px;
                    }

                    /* Step4 Spot: rectangle */
                    .raster-strip-plot-box {
                        width: 100%;
                        height: 540px;
                    }

                    .rect-plot-box {
                        width: 100%;
                        height: 640px;
                    }

                    .raster-strip-plot-box,
                    .rect-plot-box,
                    .square-plot-box-large {
                        display: block;
                        overflow: visible;
                    }

                    .raster-strip-plot-box .plot-color-shell,
                    .rect-plot-box .plot-color-shell,
                    .square-plot-box-large .plot-color-shell {
                        width: 100%;
                        height: 100%;
                        display: flex;
                        flex-direction: column;
                    }

                    .raster-strip-plot-box .plot-color-shell .shiny-plot-output,
                    .rect-plot-box .plot-color-shell .shiny-plot-output,
                    .square-plot-box-large .plot-color-shell .shiny-plot-output {
                        width: 100% !important;
                        flex: 1 1 auto;
                        min-height: 0;
                    }

                    .alignment-panel-grid {
                        width: 100%;
                        height: 100%;
                        display: grid;
                        gap: 14px;
                    }

                    .alignment-raster-grid {
                        grid-template-columns: repeat(4, minmax(260px, 1fr));
                    }

                    .alignment-spot-grid {
                        grid-template-columns: repeat(3, minmax(320px, 1fr));
                    }

                    .alignment-panel-card {
                        min-width: 0;
                        min-height: 0;
                        border: 1px solid #e5e5ea;
                        border-radius: 16px;
                        padding: 10px;
                        background: #ffffff;
                        overflow: visible;
                    }

                    .alignment-panel-title {
                        font-size: 14px;
                        font-weight: 600;
                        color: #1d1d1f;
                        margin-bottom: 8px;
                        line-height: 1.25;
                    }

                    /* Step7 final figure */
                    .square-plot-box-large {
                        width: 100%;
                        height: 860px;
                    }

                    /* Force images to display completely */
                    .square-plot-box img,
                    .raster-strip-plot-box img,
                    .rect-plot-box img,
                    .square-plot-box-large img {
                        width: 100% !important;
                        height: 100% !important;
                        object-fit: contain !important;
                        display: block;
                        margin: 0 auto;
                    }

                    /* Center plot output as well */
                    @media (max-width: 1100px) {
                        .alignment-raster-grid,
                        .alignment-spot-grid {
                            grid-template-columns: 1fr;
                        }

                        .raster-strip-plot-box {
                            height: 1980px;
                        }

                        .rect-plot-box {
                            height: 1020px;
                        }
                    }

                    /* =========================
                    Buttons & inputs
                    ========================= */
                    .btn,
                    .btn-default,
                    .btn-primary {
                        border-radius: 999px !important;
                        font-weight: 500 !important;
                        padding: 9px 18px !important;
                        border: none !important;
                        box-shadow: none !important;
                        transition: all 0.18s ease !important;
                        margin-right: 8px;
                        margin-top: 8px;
                    }

                    .btn-primary {
                        background: #0071e3 !important;
                        color: white !important;
                    }

                    .btn-primary:hover {
                        background: #0066cc !important;
                        transform: translateY(-1px);
                    }

                    .btn-default, .btn-secondary {
                        background: #f2f2f7 !important;
                        color: #1d1d1f !important;
                        border: 1px solid #d2d2d7 !important;
                    }

                    .btn-default:hover, .btn-secondary:hover {
                        background: #eaeaef !important;
                        transform: translateY(-1px);
                    }

                    .form-control, .shiny-input-number input, .shiny-input-text input, select {
                        border-radius: 14px !important;
                        border: 1px solid #d2d2d7 !important;
                        box-shadow: none !important;
                        min-height: 42px !important;
                        background: #ffffff !important;
                    }

                    .shiny-input-container {
                        margin-bottom: 14px;
                    }

                    .row-gap {
                        margin-bottom: 18px;
                    }

                    .full-width-card {
                        width: 100%;
                    }
                </style>
                """
        ),
        _spashiny_ctx.ui.div("ST-SM Automatic Alignment", class_="apple-page-title"),
        _spashiny_ctx.ui.row(
            _spashiny_ctx.ui.column(
                12,
                _spashiny_ctx.ui.card(
                    _spashiny_ctx.ui.div("Log Output", class_="apple-subtitle"),
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.output_text_verbatim("console_output"),
                        class_="apple-log-box",
                    ),
                    class_="apple-card full-width-card",
                ),
            ),
            class_="row-gap",
        ),
        _spashiny_ctx.ui.row(
            _spashiny_ctx.ui.column(
                12,
                _spashiny_ctx.ui.card(
                    _spashiny_ctx.ui.div(
                        "Reuse Automatic Alignment VAE Model", class_="apple-subtitle"
                    ),
                    _spashiny_ctx.ui.div(
                        "Upload an automatic alignment VAE model bundle to skip Step 3 Train VAE. Complete Step 1 data preparation first. If the imported file content or format is invalid, SpaShiny will show an error.",
                        class_="apple-muted",
                    ),
                    _spashiny_ctx.ui.br(),
                    _spashiny_ctx.ui.layout_columns(
                        _spashiny_ctx.ui.download_button(
                            "download_alignment_vae_model_bundle",
                            "Export Alignment VAE Model",
                            class_="btn btn-default",
                            width="100%",
                        ),
                        _spashiny_ctx.ui.input_file(
                            "import_alignment_vae_model_file",
                            "Upload Alignment VAE Model (.zip)",
                            accept=[".zip"],
                            multiple=False,
                        ),
                        _spashiny_ctx.ui.input_action_button(
                            "import_alignment_vae_model",
                            "Import Model and Skip Step 3",
                            class_="btn btn-primary",
                            width="100%",
                        ),
                        col_widths=(3, 6, 3),
                    ),
                    class_="apple-card full-width-card",
                ),
            ),
            class_="row-gap",
        ),
        _spashiny_ctx.ui.row(
            _spashiny_ctx.ui.column(
                3,
                _spashiny_ctx.ui.card(
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.div("Step 1 - Confirmed Coordinates", class_="step-title"),
                        _spashiny_ctx.ui.div(
                            "Use the saved manual coordinates. Restoring these coordinates does not repeat the transform.",
                            class_="apple-muted",
                        ),
                        _spashiny_ctx.ui.div(
                            _spashiny_ctx.ui.input_action_button(
                                "align_step1_normalize",
                                "Restore Confirmed Coordinates",
                                class_="btn btn-default",
                            ),
                            class_="step-controls",
                        ),
                        class_="step-body",
                    ),
                    class_="step-card",
                ),
            ),
            _spashiny_ctx.ui.column(
                3,
                _spashiny_ctx.ui.card(
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.div(
                            "Step 2 - Create Alignment Model", class_="step-title"
                        ),
                        _spashiny_ctx.ui.div(
                            "Initialize the latent alignment model using the default latent dimension.",
                            class_="apple-muted",
                        ),
                        _spashiny_ctx.ui.div("Latent Dimension: 10", class_="step-meta"),
                        class_="step-body",
                    ),
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.input_action_button(
                            "align_step2_create_model", "Create Model", class_="btn btn-primary"
                        ),
                        class_="step-controls",
                    ),
                    class_="step-card",
                ),
            ),
            _spashiny_ctx.ui.column(
                3,
                _spashiny_ctx.ui.card(
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.div("Step 3 - Train VAE", class_="step-title"),
                        _spashiny_ctx.ui.div(
                            "Train the variational autoencoder using the default number of epochs.",
                            class_="apple-muted",
                        ),
                        _spashiny_ctx.ui.div("Training Epochs: 128", class_="step-meta"),
                        class_="step-body",
                    ),
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.input_action_button(
                            "align_step3_train_vae", "Train VAE", class_="btn btn-primary"
                        ),
                        class_="step-controls",
                    ),
                    class_="step-card",
                ),
            ),
            _spashiny_ctx.ui.column(
                3,
                _spashiny_ctx.ui.card(
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.div(
                            "Step 4 - Rasterized Feature Map", class_="step-title"
                        ),
                        _spashiny_ctx.ui.div(
                            "Generate rasterized features and random spot sampling for downstream alignment.",
                            class_="apple-muted",
                        ),
                        class_="step-body",
                    ),
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.input_action_button(
                            "align_step4_get_raster", "Generate Raster", class_="btn btn-primary"
                        ),
                        _spashiny_ctx.ui.download_button(
                            "download_raster_spot_pdf", "Download PDF", class_="btn btn-default"
                        ),
                        _spashiny_ctx.ui.download_button(
                            "download_alignment_vectors_zip",
                            "Download Editable PDF/SVG Bundle",
                            class_="btn btn-default",
                        ),
                        _spashiny_ctx.ui.download_button(
                            "download_alignment_all_plots_zip",
                            "Download All Plots ZIP",
                            class_="btn btn-default",
                        ),
                        _spashiny_ctx.ui.div(
                            "PDF/SVG: editable labels, points and feature-grid cells. Original H&E photographs remain image layers. Older reports are redrawn from saved data without rerunning alignment.",
                            class_="apple-muted",
                        ),
                        class_="step-controls",
                    ),
                    class_="step-card",
                ),
            ),
            class_="row-gap",
        ),
        _spashiny_ctx.ui.row(
            _spashiny_ctx.ui.column(
                12,
                _spashiny_ctx.ui.card(
                    _spashiny_ctx.ui.div("Rasterized Feature Map", class_="apple-subtitle"),
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.div(
                            _spashiny_ctx.ui.div(
                                _spashiny_ctx.ui.div(
                                    "SM rasterized feature", class_="alignment-panel-title"
                                ),
                                _spashiny_globals.alignment_image_output_with_palette(
                                    "raster_panel_sm_feature", height="430px"
                                ),
                                _spashiny_ctx.ui.download_button(
                                    "download_raster_panel_sm_feature_png",
                                    "Download PNG",
                                    class_="btn btn-default btn-sm",
                                ),
                                class_="alignment-panel-card",
                            ),
                            _spashiny_ctx.ui.div(
                                _spashiny_ctx.ui.div(
                                    "SM latent embedding", class_="alignment-panel-title"
                                ),
                                _spashiny_globals.alignment_image_output_with_palette(
                                    "raster_panel_sm_latent", height="430px"
                                ),
                                _spashiny_ctx.ui.download_button(
                                    "download_raster_panel_sm_latent_png",
                                    "Download PNG",
                                    class_="btn btn-default btn-sm",
                                ),
                                class_="alignment-panel-card",
                            ),
                            _spashiny_ctx.ui.div(
                                _spashiny_ctx.ui.div(
                                    "ST spatial image", class_="alignment-panel-title"
                                ),
                                _spashiny_globals.alignment_image_output_with_palette(
                                    "raster_panel_st_image", height="430px"
                                ),
                                _spashiny_ctx.ui.download_button(
                                    "download_raster_panel_st_image_png",
                                    "Download PNG",
                                    class_="btn btn-default btn-sm",
                                ),
                                class_="alignment-panel-card",
                            ),
                            _spashiny_ctx.ui.div(
                                _spashiny_ctx.ui.div(
                                    "ST latent feature", class_="alignment-panel-title"
                                ),
                                _spashiny_globals.alignment_image_output_with_palette(
                                    "raster_panel_st_latent", height="430px"
                                ),
                                _spashiny_ctx.ui.download_button(
                                    "download_raster_panel_st_latent_png",
                                    "Download PNG",
                                    class_="btn btn-default btn-sm",
                                ),
                                class_="alignment-panel-card",
                            ),
                            class_="alignment-panel-grid alignment-raster-grid",
                        ),
                        class_="raster-strip-plot-box",
                    ),
                    class_="apple-card",
                ),
            ),
            class_="row-gap",
        ),
        _spashiny_ctx.ui.row(
            _spashiny_ctx.ui.column(
                12,
                _spashiny_ctx.ui.card(
                    _spashiny_ctx.ui.div(
                        "Random Sample Inside Image Spot", class_="apple-subtitle"
                    ),
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.div(
                            _spashiny_ctx.ui.div(
                                _spashiny_ctx.ui.div(
                                    "ST tissue and latent structure", class_="alignment-panel-title"
                                ),
                                _spashiny_globals.alignment_image_output_with_palette(
                                    "spot_panel_st_latent", height="420px"
                                ),
                                _spashiny_ctx.ui.download_button(
                                    "download_spot_panel_st_latent_png",
                                    "Download PNG",
                                    class_="btn btn-default btn-sm",
                                ),
                                class_="alignment-panel-card",
                            ),
                            _spashiny_ctx.ui.div(
                                _spashiny_ctx.ui.div(
                                    "Randomly sampled inside-tissue spots",
                                    class_="alignment-panel-title",
                                ),
                                _spashiny_globals.alignment_image_output_with_palette(
                                    "spot_panel_sampled", height="420px"
                                ),
                                _spashiny_ctx.ui.download_button(
                                    "download_spot_panel_sampled_png",
                                    "Download PNG",
                                    class_="btn btn-default btn-sm",
                                ),
                                class_="alignment-panel-card",
                            ),
                            _spashiny_ctx.ui.div(
                                _spashiny_ctx.ui.div(
                                    "Binary tissue mask", class_="alignment-panel-title"
                                ),
                                _spashiny_globals.alignment_image_output_with_palette(
                                    "spot_panel_mask", height="420px"
                                ),
                                _spashiny_ctx.ui.download_button(
                                    "download_spot_panel_mask_png",
                                    "Download PNG",
                                    class_="btn btn-default btn-sm",
                                ),
                                class_="alignment-panel-card",
                            ),
                            class_="alignment-panel-grid alignment-spot-grid",
                        ),
                        class_="rect-plot-box",
                    ),
                    class_="apple-card",
                ),
            ),
            class_="row-gap",
        ),
        _spashiny_ctx.ui.row(
            _spashiny_ctx.ui.column(
                3,
                _spashiny_ctx.ui.card(
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.div("Step 5 - Fit Alignment", class_="step-title"),
                        _spashiny_ctx.ui.div(
                            "Run the final alignment process using the generated feature map.",
                            class_="apple-muted",
                        ),
                        _spashiny_ctx.ui.div(),
                        _spashiny_ctx.ui.div(
                            _spashiny_ctx.ui.output_ui("alignment_resource_mode_details"),
                            class_="apple-muted",
                        ),
                        _spashiny_ctx.ui.input_checkbox(
                            "align_save_debug_figures", "Save debug figures", value=False
                        ),
                        class_="step-body",
                    ),
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.input_action_button(
                            "align_step5_fit_alignment", "Run Alignment", class_="btn btn-primary"
                        ),
                        class_="step-controls",
                    ),
                    class_="step-card",
                ),
            ),
            _spashiny_ctx.ui.column(
                3,
                _spashiny_ctx.ui.card(
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.div("Step 6 - Save Result", class_="step-title"),
                        _spashiny_ctx.ui.div(
                            "Save transformed spatial coordinates into the aligned SM object.",
                            class_="apple-muted",
                        ),
                        class_="step-body",
                    ),
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.input_action_button(
                            "align_step6_save_result", "Save Result", class_="btn btn-default"
                        ),
                        class_="step-controls",
                    ),
                    class_="step-card",
                ),
            ),
            _spashiny_ctx.ui.column(
                3,
                _spashiny_ctx.ui.card(
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.div("Step 7 - Preview Aligned SM", class_="step-title"),
                        _spashiny_ctx.ui.div(
                            "Preview aligned SM over the ST image. Color is the sum of the current preprocessed SM X (tutorial QC), not the original raw TIC. X increases right; image Y increases downward.",
                            class_="apple-muted",
                        ),
                        class_="step-body",
                    ),
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.input_action_button(
                            "align_step7_show_alignment_btn",
                            "Show Alignment",
                            class_="btn btn-primary",
                        ),
                        class_="step-controls",
                    ),
                    class_="step-card",
                ),
            ),
            _spashiny_ctx.ui.column(
                3,
                _spashiny_ctx.ui.card(
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.div(
                            "Step 8 - Export Aligned SM Data", class_="step-title"
                        ),
                        _spashiny_ctx.ui.div(
                            "Export the aligned SM AnnData object (.h5ad) with obsm['spatial_transformed'].",
                            class_="apple-muted",
                        ),
                        class_="step-body",
                    ),
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.input_action_button(
                            "align_step8_export_h5ad",
                            "Export Aligned SM h5ad",
                            class_="btn btn-default",
                        ),
                        class_="step-controls",
                    ),
                    class_="step-card",
                ),
            ),
            class_="row-gap",
        ),
        _spashiny_ctx.ui.row(
            _spashiny_ctx.ui.column(
                12,
                _spashiny_ctx.ui.card(
                    _spashiny_ctx.ui.div("Aligned SM Preview", class_="apple-subtitle"),
                    _spashiny_ctx.ui.div(
                        _spashiny_globals.plot_output_with_palette(
                            "align_step7_show_alignment_plot", height="780px", width="100%"
                        ),
                        class_="square-plot-box-large",
                    ),
                    _spashiny_ctx.ui.download_button(
                        "download_alignment_step7_pdf",
                        "Download Aligned SM Preview PDF",
                        class_="btn btn-default",
                    ),
                    _spashiny_ctx.ui.div(
                        "Editable vector points, labels and colorbar; H&E remains an original image layer. Downloads use this workflow's exact saved Step5/Step6 coordinates.",
                        class_="apple-muted",
                    ),
                    class_="apple-card",
                ),
            )
        ),
    )


def ui(_spashiny_ctx, module):
    if module == "ST-SM model":
        return _view_1(_spashiny_ctx, module)
    raise ValueError("Unknown feature page: alignment_auto")
