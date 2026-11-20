# Actual feature UI extracted from production. Feature: knn.
from spashiny._shared import runtime_globals as _spashiny_globals


def _view_1(_spashiny_ctx, module):
    stsm_reassignment_css = """
            <style>
            body {
                background: #f5f5f7;
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", Arial, sans-serif;
                color: #1d1d1f;
            }

            .apple-page {
                padding: 24px 18px 50px 18px;
                max-width: 1500px;
                margin: 0 auto;
            }

            .apple-hero {
                padding: 8px 4px 24px 4px;
            }

            .apple-title {
                font-size: 2.4rem;
                font-weight: 700;
                color: #1d1d1f;
                margin-bottom: 8px;
                letter-spacing: -0.02em;
            }

            .apple-subtitle {
                font-size: 1rem;
                color: #6e6e73;
                max-width: 1100px;
                line-height: 1.75;
            }

            .apple-card {
                border: none !important;
                border-radius: 26px !important;
                background: rgba(255,255,255,0.92) !important;
                backdrop-filter: blur(12px);
                -webkit-backdrop-filter: blur(12px);
                box-shadow: 0 10px 30px rgba(0,0,0,0.06) !important;
                padding: 12px;
                margin-bottom: 22px;
            }

            .card-header {
                background: transparent !important;
                border-bottom: none !important;
                font-size: 1.08rem;
                font-weight: 600;
                color: #1d1d1f;
                padding-bottom: 8px;
            }

            .apple-section-note {
                color: #6e6e73;
                font-size: 0.94rem;
                line-height: 1.7;
                margin-bottom: 14px;
            }

            .upload-card {
                background: #f9f9fb;
                border: 1px solid #ececf1;
                border-radius: 18px;
                padding: 14px 16px;
                transition: all 0.2s ease;
            }

            .upload-card:hover {
                background: #ffffff;
                box-shadow: 0 4px 14px rgba(0,0,0,0.04);
            }

            /* ===== Light Console ===== */
            .apple-console {
                background: #f2f2f7;
                color: #1d1d1f;
                border: 1px solid #e5e5ea;
                border-radius: 18px;
                padding: 18px;
                font-size: 0.93rem;
                min-height: 240px;
                max-height: 420px;
                overflow-y: auto;
                white-space: pre-wrap;
                line-height: 1.65;
            }

            .btn {
                border-radius: 14px !important;
                font-weight: 500;
                padding: 10px 16px;
                transition: all 0.2s ease;
            }

            .btn-primary {
                background: #0071e3 !important;
                border: none !important;
            }

            .btn-primary:hover {
                background: #0062c3 !important;
            }

            .btn-success {
                border: none !important;
                border-radius: 14px !important;
            }

            .btn-light {
                background: #f2f2f7 !important;
                border: 1px solid #e5e5ea !important;
                color: #1d1d1f !important;
            }

            .btn-outline-dark,
            .btn-outline-primary,
            .btn-outline-secondary {
                border-radius: 14px !important;
            }

            .form-control, .form-select, .shiny-input-container input {
                border-radius: 14px !important;
                border: 1px solid #d2d2d7 !important;
                box-shadow: none !important;
            }

            .form-control:focus, .form-select:focus, .shiny-input-container input:focus {
                border-color: #0071e3 !important;
                box-shadow: 0 0 0 0.2rem rgba(0,113,227,0.15) !important;
            }

            hr {
                border-top: 1px solid #e5e5ea;
                margin-top: 18px;
                margin-bottom: 18px;
            }

            h5, h4 {
                font-weight: 600;
                color: #1d1d1f;
            }

            .text-muted {
                color: #6e6e73 !important;
            }

            .step-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
                gap: 18px;
                margin-bottom: 28px;
            }

            .result-stack {
                display: flex;
                flex-direction: column;
                gap: 20px;
            }
            </style>
            """
    return _spashiny_ctx.ui.page_fluid(
        _spashiny_ctx.ui.HTML(stsm_reassignment_css),
        _spashiny_ctx.ui.div(
            {"class": "apple-page"},
            _spashiny_ctx.ui.div(
                {"class": "apple-hero"},
                _spashiny_ctx.ui.h1("ST-SM Reassignment", class_="apple-title"),
                _spashiny_ctx.ui.p(
                    "Reassign single-cell metabolomics (SM) signals onto shared spatial transcriptomics (ST) coordinates, followed by quality control, KNN-based spot reassignment, filtering, and joint spatial visualization.",
                    class_="apple-subtitle",
                ),
            ),
            _spashiny_ctx.ui.div(
                {"class": "result-stack"},
                _spashiny_ctx.ui.card(
                    _spashiny_ctx.ui.card_header("Console Output"),
                    _spashiny_ctx.ui.div(
                        {"class": "apple-section-note"},
                        "Execution logs, diagnostic messages, and workflow progress will appear here.",
                    ),
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.output_text_verbatim("console_output"),
                        {"class": "apple-console"},
                    ),
                    class_="apple-card",
                ),
                _spashiny_ctx.ui.div(
                    {"class": "step-grid"},
                    _spashiny_ctx.ui.card(
                        _spashiny_ctx.ui.card_header("Step 1 - Upload & Initial QC"),
                        _spashiny_ctx.ui.div(
                            {"class": "apple-section-note"},
                            "Upload ST and SM .h5ad files and perform an initial intensity-based quality control.",
                        ),
                        _spashiny_ctx.ui.div(
                            {"class": "upload-card"},
                            _spashiny_ctx.ui.h5("ST Data (.h5ad, QC-ready)"),
                            (
                                _spashiny_ctx.ui.div(
                                    _spashiny_ctx.ui.tags.label("Choose ST File"),
                                    _spashiny_ctx.ui.tags.input(
                                        type="file",
                                        accept=".h5ad",
                                        class_="form-control",
                                        **{"data-spashiny-knn-upload": "st"},
                                    ),
                                    _spashiny_ctx.ui.tags.div(
                                        "Select a QC-ready ST H5AD.",
                                        **{"data-spashiny-knn-upload-status": "st"},
                                    ),
                                )
                                if _spashiny_globals.SPASHINY_WEB_PLATFORM
                                else _spashiny_ctx.ui.input_file(
                                    "reassign_st_h5ad",
                                    "Choose ST File",
                                    multiple=False,
                                    accept=[".h5ad"],
                                )
                            ),
                            _spashiny_ctx.ui.div(
                                {"class": "small text-muted mt-1"},
                                "Expected input: ST object with spatial metadata and QC-related information.",
                            ),
                        ),
                        _spashiny_ctx.ui.div(
                            {"class": "upload-card mt-3"},
                            _spashiny_ctx.ui.h5("SM Data (.h5ad, aligned input required)"),
                            (
                                _spashiny_ctx.ui.div(
                                    _spashiny_ctx.ui.tags.label("Choose Aligned SM File"),
                                    _spashiny_ctx.ui.tags.input(
                                        type="file",
                                        accept=".h5ad",
                                        class_="form-control",
                                        **{"data-spashiny-knn-upload": "sm"},
                                    ),
                                    _spashiny_ctx.ui.tags.div(
                                        "Select an aligned SM H5AD with spatial_transformed coordinates.",
                                        **{"data-spashiny-knn-upload-status": "sm"},
                                    ),
                                )
                                if _spashiny_globals.SPASHINY_WEB_PLATFORM
                                else _spashiny_ctx.ui.input_file(
                                    "reassign_sm_h5ad",
                                    "Choose Aligned SM File",
                                    multiple=False,
                                    accept=[".h5ad"],
                                )
                            ),
                            _spashiny_ctx.ui.div(
                                {"class": "small text-muted mt-1"},
                                "Upload aligned SM with complete expression and coordinate metadata, or use a current Alignment Step 6 result. Unknown units are rejected.",
                            ),
                        ),
                        _spashiny_ctx.ui.input_action_button(
                            "load_reassign_example_raw_h5ad",
                            "Load SpatialMETA Reassignment Example (Y7_T)",
                            class_=_spashiny_globals.cloud_example_button_class(
                                "btn btn-secondary w-100 mt-3"
                            ),
                            **_spashiny_globals.cloud_example_action_attrs(
                                "y7-knn-reassignment-example",
                                "knn_reassignment",
                                "knn-example-status",
                            ),
                        ),
                        _spashiny_ctx.ui.div(
                            {"class": "small text-muted mt-2"},
                            _spashiny_globals.example_source_note(
                                "Uses QC ST data from user_data/input/sample-1_Y7_T/ST/Y7_T_adata_ST_qc.h5ad and aligned SM data from user_data/input/SM/adata_SM_Y7_T_raw.aligned.h5ad.",
                                "Tutorial example: QC ST, 1299-feature Raw SM expression and official Aligned SM coordinates. Fixed QC > 2,000,000 before and after KNN; K=5, dist_fold=1.5.",
                            ),
                        ),
                        *(
                            [_spashiny_globals.cloud_example_status("knn-example-status")]
                            if _spashiny_globals.SPASHINY_WEB_PLATFORM
                            else []
                        ),
                        _spashiny_ctx.ui.input_action_button(
                            "use_alignment_knn_handoff",
                            "Use Current Alignment Result",
                            class_="btn btn-outline-primary w-100 mt-3",
                        ),
                        _spashiny_ctx.ui.div(
                            {"class": "small text-muted mt-2"},
                            "For a user-upload analysis, KNN uses the current Alignment Step 6 artifact and the original scoped ST upload. It never substitutes the Y7_T example.",
                        ),
                        class_="apple-card",
                    ),
                    _spashiny_ctx.ui.card(
                        _spashiny_ctx.ui.card_header("Step 2 - Data Inspection"),
                        _spashiny_ctx.ui.h5("Initial QC Threshold"),
                        _spashiny_ctx.ui.input_numeric(
                            "min_intensity_threshold",
                            (
                                "Minimum Total Intensity (custom inputs only)"
                                if _spashiny_globals.SPASHINY_WEB_PLATFORM
                                else "Minimum Total Intensity (min_total_intensity)"
                            ),
                            value=2000000 if _spashiny_globals.SPASHINY_WEB_PLATFORM else 100000.0,
                            min=0,
                            step=1 if _spashiny_globals.SPASHINY_WEB_PLATFORM else 10000.0,
                        ),
                        (
                            _spashiny_ctx.ui.p(
                                "For custom inputs, run QC or the spatial preview to apply this threshold before reassignment. The tutorial example uses its fixed threshold regardless of this field.",
                                class_="text-muted small",
                            )
                            if _spashiny_globals.SPASHINY_WEB_PLATFORM
                            else None
                        ),
                        _spashiny_ctx.ui.div(
                            {"class": "small text-muted mt-1"},
                            "Native SpatialMETA retains SM spots with total_intensity strictly greater than this threshold.",
                        ),
                        _spashiny_ctx.ui.hr(),
                        _spashiny_ctx.ui.input_action_button(
                            "load_h5ad", "Load Data & Run QC", class_="btn btn-primary w-100 mb-2"
                        ),
                        (
                            _spashiny_ctx.ui.output_ui("knn_input_worker_status")
                            if _spashiny_globals.SPASHINY_WEB_PLATFORM
                            else _spashiny_ctx.ui.div()
                        ),
                        (
                            _spashiny_ctx.ui.output_ui("knn_pre_qc_result")
                            if _spashiny_globals.SPASHINY_WEB_PLATFORM
                            else None
                        ),
                        _spashiny_ctx.ui.input_action_button(
                            "clear_log", "Clear Console", class_="btn btn-light w-100"
                        ),
                        _spashiny_ctx.ui.hr(),
                        _spashiny_ctx.ui.div(
                            {"class": "apple-section-note"},
                            "Inspect the structure of ST and SM AnnData objects, including obs/var, obsm, and uns.",
                        ),
                        _spashiny_ctx.ui.input_action_button(
                            "check_data_info",
                            "Inspect ST / SM Structure",
                            class_="btn btn-outline-dark w-100",
                        ),
                        class_="apple-card",
                    ),
                    _spashiny_ctx.ui.card(
                        _spashiny_ctx.ui.card_header("Step 3 - Spatial Scaling Preview"),
                        _spashiny_ctx.ui.div(
                            {"class": "apple-section-note"},
                            (
                                "Automatically uses tissue_hires_scalef from the ST H5AD to draw SM over the ST tissue image. The display scale is not written back to KNN coordinates."
                                if _spashiny_globals.SPASHINY_WEB_PLATFORM
                                else "Scale transformed SM coordinates into the ST histology image coordinate system for preview."
                            ),
                        ),
                        (
                            _spashiny_ctx.ui.input_text(
                                "sm_sample_name",
                                "Sample Name in ST.uns['spatial']",
                                placeholder="e.g. sample1",
                            )
                            if not _spashiny_globals.SPASHINY_WEB_PLATFORM
                            else None
                        ),
                        _spashiny_ctx.ui.input_action_button(
                            "scale_and_plot",
                            "Run Scaling & Preview",
                            class_="btn btn-primary w-100 mt-2",
                        ),
                        _spashiny_ctx.ui.div(
                            {"class": "small text-muted mt-2"},
                            "Use this step to verify whether SM coordinates are correctly overlaid onto the ST tissue image.",
                        ),
                        class_="apple-card",
                    ),
                ),
                _spashiny_ctx.ui.card(
                    _spashiny_ctx.ui.card_header("Scaled Spatial Preview"),
                    _spashiny_ctx.ui.div(
                        {"class": "apple-section-note"},
                        "Preview the scaled SM coordinates overlaid on the ST tissue image.",
                    ),
                    (
                        _spashiny_ctx.ui.output_ui("knn_scaling_worker_plot")
                        if _spashiny_globals.SPASHINY_WEB_PLATFORM
                        else _spashiny_globals.plot_output_with_palette(
                            "perform_scale_and_plot", height="650px"
                        )
                    ),
                    _spashiny_ctx.ui.download_button(
                        "download_scaled_preview_pdf",
                        "Download Scaling Preview PDF",
                        class_="btn btn-secondary w-100 mt-3",
                    ),
                    class_="apple-card",
                ),
                _spashiny_ctx.ui.div(
                    {"class": "step-grid"},
                    _spashiny_ctx.ui.card(
                        _spashiny_ctx.ui.card_header("Step 4 - KNN Spot Reassignment"),
                        _spashiny_ctx.ui.div(
                            {"class": "apple-section-note"},
                            "Reassign SM signals onto shared ST-based coordinates using K-nearest-neighbor mapping. Confirm that SM contains obsm['spatial_transformed'] from the alignment step before running.",
                        ),
                        _spashiny_ctx.ui.h5("KNN Parameters"),
                        _spashiny_ctx.ui.input_numeric(
                            "spot_knn_k",
                            "Number of Nearest Neighbors (K)",
                            value=5,
                            min=1,
                            max=50,
                            step=1,
                        ),
                        _spashiny_ctx.ui.input_numeric(
                            "spot_dist_fold",
                            "Distance Scaling Factor (dist_fold)",
                            value=1.5,
                            min=0.5,
                            max=5.0,
                            step=0.1,
                        ),
                        _spashiny_ctx.ui.hr(),
                        _spashiny_ctx.ui.input_action_button(
                            "run_knn_data", "Run KNN Reassignment", class_="btn btn-primary w-100"
                        ),
                        class_="apple-card",
                    ),
                    _spashiny_ctx.ui.card(
                        _spashiny_ctx.ui.card_header("Step 5 - Post-KNN Filtering"),
                        _spashiny_ctx.ui.div(
                            {"class": "apple-section-note"},
                            "Apply an additional filtering step to reassigned SM data using total intensity.",
                        ),
                        _spashiny_ctx.ui.input_numeric(
                            "min_total_intensity",
                            (
                                "Minimum Total Intensity After KNN (custom inputs only)"
                                if _spashiny_globals.SPASHINY_WEB_PLATFORM
                                else "Minimum Total Intensity After Reassignment"
                            ),
                            value=2000000 if _spashiny_globals.SPASHINY_WEB_PLATFORM else 2000000.0,
                            min=0,
                            step=1 if _spashiny_globals.SPASHINY_WEB_PLATFORM else 100000.0,
                        ),
                        _spashiny_ctx.ui.input_action_button(
                            "run_filter_and_update",
                            "Filter Reassigned SM Data",
                            class_="btn btn-outline-primary w-100 mt-2",
                        ),
                        (
                            _spashiny_ctx.ui.output_ui("knn_post_qc_result")
                            if _spashiny_globals.SPASHINY_WEB_PLATFORM
                            else None
                        ),
                        _spashiny_ctx.ui.div(
                            {"class": "small text-muted mt-2"},
                            "Tip: review the intensity histogram before choosing this threshold.",
                        ),
                        class_="apple-card",
                    ),
                    _spashiny_ctx.ui.card(
                        _spashiny_ctx.ui.card_header("Step 6 - Joint Visualization & Debug"),
                        _spashiny_ctx.ui.div(
                            {"class": "apple-section-note"},
                            "Generate the integrated ST-SM object for downstream spatial visualization and diagnostics.",
                        ),
                        _spashiny_ctx.ui.input_action_button(
                            "generate_joint_visualization",
                            "Generate Joint Visualization",
                            class_="btn btn-success w-100 mb-2",
                        ),
                        _spashiny_ctx.ui.input_action_button(
                            "debug_integration",
                            "Debug Data Integration",
                            class_="btn btn-outline-secondary w-100",
                        ),
                        class_="apple-card",
                    ),
                ),
                _spashiny_ctx.ui.card(
                    _spashiny_ctx.ui.card_header("KNN Reassignment Visualization"),
                    _spashiny_ctx.ui.div(
                        {"class": "apple-section-note"},
                        "Visualize the reassigned SM and ST distributions after KNN-based spot reassignment.",
                    ),
                    _spashiny_ctx.ui.input_action_button(
                        "run_knn_plot",
                        "Generate KNN Visualization",
                        class_="btn btn-success w-100 mb-3",
                    ),
                    (
                        _spashiny_ctx.ui.output_ui("knn_worker_result")
                        if _spashiny_globals.SPASHINY_WEB_PLATFORM
                        else _spashiny_globals.plot_output_with_palette("knn_plot", height="650px")
                    ),
                    _spashiny_ctx.ui.div(
                        {"class": "small text-muted mt-2"},
                        "Tip: use this panel to verify whether reassigned coordinates remain spatially coherent.",
                    ),
                    class_="apple-card",
                ),
                _spashiny_ctx.ui.card(
                    _spashiny_ctx.ui.card_header("SM Intensity Histograms"),
                    _spashiny_ctx.ui.div(
                        {"class": "apple-section-note"},
                        "Inspect intensity distributions of reassigned SM data to guide filtering threshold selection.",
                    ),
                    _spashiny_ctx.ui.input_action_button(
                        "run_st_histograms",
                        "Generate Intensity Histograms",
                        class_="btn btn-info w-100 mb-3",
                    ),
                    (
                        _spashiny_ctx.ui.output_ui("knn_histogram_result")
                        if _spashiny_globals.SPASHINY_WEB_PLATFORM
                        else _spashiny_globals.plot_output_with_palette(
                            "st_counts_histograms", height="480px"
                        )
                    ),
                    class_="apple-card",
                ),
                _spashiny_ctx.ui.card(
                    _spashiny_ctx.ui.card_header("Joint ST-SM Visualization"),
                    _spashiny_ctx.ui.div(
                        {"class": "apple-section-note"},
                        "Display the integrated ST-SM object using total intensity and total counts.",
                    ),
                    *(
                        [_spashiny_ctx.ui.output_ui("knn_joint_result")]
                        if _spashiny_globals.SPASHINY_WEB_PLATFORM
                        else [
                            _spashiny_globals.plot_output_with_palette(
                                "joint_spatial_plot1", height="600px"
                            ),
                            _spashiny_ctx.ui.hr(),
                            _spashiny_globals.plot_output_with_palette(
                                "joint_spatial_plot2", height="600px"
                            ),
                        ]
                    ),
                    _spashiny_ctx.ui.hr(),
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.download_button(
                            (
                                "download_knn_joint_h5ad"
                                if _spashiny_globals.SPASHINY_WEB_PLATFORM
                                else "download_joint_h5ad"
                            ),
                            " Download Joint h5ad",
                            class_="btn btn-success",
                        ),
                        *(
                            [
                                _spashiny_ctx.ui.download_button(
                                    "download_knn_sm_h5ad",
                                    "Download SM H5AD",
                                    class_="btn btn-outline-primary",
                                ),
                                _spashiny_ctx.ui.download_button(
                                    "download_knn_st_h5ad",
                                    "Download ST H5AD",
                                    class_="btn btn-outline-primary",
                                ),
                            ]
                            if _spashiny_globals.SPASHINY_WEB_PLATFORM
                            else []
                        ),
                        class_="d-flex flex-wrap gap-2",
                    ),
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.download_button(
                            "download_joint_pdf", " Download Joint PDF", class_="btn btn-danger"
                        ),
                        _spashiny_ctx.ui.download_button(
                            "download_knn_pdf", " Download KNN Plot PDF", class_="btn btn-warning"
                        ),
                        _spashiny_ctx.ui.download_button(
                            "download_sm_hist_pdf",
                            " Download SM Histogram PDF",
                            class_="btn btn-info",
                        ),
                        _spashiny_ctx.ui.download_button(
                            "download_full_report_pdf",
                            " Download Full Analysis Report PDF",
                            class_="btn btn-primary",
                        ),
                        class_="d-flex flex-wrap gap-2 mt-3",
                    ),
                    class_="apple-card",
                ),
            ),
        ),
    )


def ui(_spashiny_ctx, module):
    if module == "ST-SM Reassignment":
        return _view_1(_spashiny_ctx, module)
    raise ValueError("Unknown feature page: knn")
