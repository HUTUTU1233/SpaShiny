# Actual feature UI extracted from production. Feature: alignment_manual.
from spashiny._shared import runtime_globals as _spashiny_globals


def _view_1(_spashiny_ctx, module):
    return _spashiny_ctx.ui.page_fluid(
        _spashiny_ctx.ui.tags.style(
            """
                body {
                    background-color: #f5f5f7;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                    color: #1d1d1f;
                }

                h2 {
                    font-size: 30px;
                    font-weight: 600;
                    color: #1d1d1f;
                    margin-bottom: 28px;
                    letter-spacing: -0.02em;
                }

                h4 {
                    font-size: 18px;
                    font-weight: 600;
                    color: #1d1d1f;
                    margin-bottom: 16px;
                    letter-spacing: -0.01em;
                }

                .card-box, .apple-card {
                    background: rgba(255, 255, 255, 0.92);
                    backdrop-filter: blur(18px);
                    -webkit-backdrop-filter: blur(18px);
                    border: 1px solid rgba(0,0,0,0.06);
                    border-radius: 22px;
                    padding: 24px;
                    box-shadow: 0 8px 28px rgba(0,0,0,0.05);
                    transition: all 0.25s ease;
                    margin-bottom: 24px;
                }

                .card-box:hover, .apple-card:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 12px 32px rgba(0,0,0,0.07);
                }

                .section-title {
                    font-size: 24px;
                    font-weight: 600;
                    color: #1d1d1f;
                    margin-top: 8px;
                    margin-bottom: 22px;
                    letter-spacing: -0.02em;
                }

                .subtle-text {
                    color: #6e6e73;
                    font-size: 14px;
                    line-height: 1.6;
                    margin-bottom: 16px;
                }

                .form-control, .form-select, input, select, textarea {
                    border-radius: 14px !important;
                    border: 1px solid #d2d2d7 !important;
                    background: #ffffff !important;
                    min-height: 44px;
                    box-shadow: none !important;
                }

                .form-control:focus, .form-select:focus, input:focus, select:focus, textarea:focus {
                    border-color: #0071e3 !important;
                    box-shadow: 0 0 0 4px rgba(0,113,227,0.12) !important;
                }

                .btn, .btn-default, .btn-primary {
                    border-radius: 999px !important;
                    min-height: 42px;
                    padding: 10px 18px;
                    font-weight: 500;
                    border: none !important;
                    box-shadow: none !important;
                    transition: all 0.2s ease;
                }

                .btn-primary {
                    background: #0071e3 !important;
                    color: white !important;
                }

                .btn-primary:hover {
                    background: #0062c3 !important;
                    transform: translateY(-1px);
                }

                .btn-default {
                    background: #ffffff !important;
                    color: #1d1d1f !important;
                    border: 1px solid #d2d2d7 !important;
                }

                .btn-default:hover {
                    background: #f5f5f7 !important;
                }

                .apple-console {
                    background: #fbfbfd;
                    border: 1px solid #e5e5e7;
                    border-radius: 18px;
                    padding: 18px;
                    min-height: 520px;
                    max-height: 520px;
                    overflow-y: auto;
                    white-space: pre-wrap;
                    font-family: SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
                    font-size: 13px;
                    color: #1d1d1f;
                    line-height: 1.65;
                }

                .center-card-9 {
                    width: 75%;
                    margin: 0 auto 28px auto;
                }

                .center-card-4 {
                    width: 38%;
                    min-width: 420px;
                    margin: 0 auto 28px auto;
                }

                .plot-card {
                    text-align: center;
                }

                .shiny-plot-output {
                    width: 100% !important;
                    display: block;
                    margin: 0 auto;
                }

                hr {
                    border: none;
                    border-top: 1px solid #e5e5e7;
                    margin: 20px 0;
                }

                @media (max-width: 1200px) {
                    .center-card-9 {
                        width: 92%;
                    }
                    .center-card-4 {
                        width: 70%;
                        min-width: unset;
                    }
                }

                @media (max-width: 768px) {
                    .center-card-9,
                    .center-card-4 {
                        width: 100%;
                    }
                }
                .control-panel-card {
                    min-height: 560px;
                    display: flex;
                    flex-direction: column;
                    justify-content: flex-start;
                }

                .plot-panel-card {
                    min-height: 560px;
                    display: flex;
                    flex-direction: column;
                }

                .preview-card {
                    min-height: 470px;
                    height: 470px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    border-radius: 18px;
                    background: #fbfbfd;
                    border: 1px solid #e5e5e7;
                    padding: 12px;
                    overflow: hidden;
                }

                .preview-card .shiny-plot-output {
                    width: 100% !important;
                    max-width: 100%;
                    height: auto !important;
                }

                .control-block {
                    margin-bottom: 14px;
                }

                .control-block label,
                .checkbox-block label {
                    font-size: 13px !important;
                    font-weight: 500 !important;
                    color: #3a3a3c !important;
                    margin-bottom: 6px !important;
                    display: block;
                }

                .control-block input[type="number"] {
                    height: 44px !important;
                    border-radius: 14px !important;
                    border: 1px solid #d2d2d7 !important;
                    padding: 10px 14px !important;
                    font-size: 14px !important;
                    background: #ffffff !important;
                }

                .checkbox-block {
                    min-height: 72px;
                    display: flex;
                    align-items: center;
                    padding: 0 8px;
                    border: 1px solid #ececef;
                    border-radius: 16px;
                    background: #fbfbfd;
                }

                .checkbox-block .form-check {
                    margin-bottom: 0 !important;
                    width: 100%;
                }

                .checkbox-block .form-check-label {
                    font-size: 14px !important;
                    color: #1d1d1f !important;
                    font-weight: 500 !important;
                    margin-left: 6px;
                }

                .checkbox-block input[type="checkbox"] {
                    transform: scale(1.15);
                    margin-top: 0 !important;
                }

                .control-btn {
                    width: 100%;
                    margin-top: auto;
                    height: 46px;
                    font-size: 15px;
                }

                .plot-panel-card h4,
                .control-panel-card h4 {
                    margin-bottom: 18px;
                }
                """
        ),
        _spashiny_ctx.ui.h2("ST-SM Alignment Preprocessing"),
        _spashiny_ctx.ui.div(
            _spashiny_ctx.ui.div(
                _spashiny_ctx.ui.row(
                    _spashiny_ctx.ui.column(
                        4,
                        _spashiny_ctx.ui.card(
                            _spashiny_ctx.ui.h4("Upload and Processing"),
                            _spashiny_ctx.ui.p(
                                "Upload raw or QC-processed ST / SM .h5ad files.",
                                class_="subtle-text",
                            ),
                            _spashiny_ctx.ui.div(
                                _spashiny_ctx.ui.tags.label(
                                    "Upload ST Data (.h5ad)", class_="control-label"
                                ),
                                _spashiny_ctx.ui.tags.input(
                                    type="file",
                                    accept=".h5ad",
                                    class_="form-control",
                                    **{"data-spashiny-alignment-upload": "st"},
                                ),
                                _spashiny_ctx.ui.tags.div(
                                    "Select an ST H5AD file to upload.",
                                    id="alignment_st_upload_status",
                                    class_="cloud-muted",
                                    style="font-size: 12px; margin-top: 8px;",
                                ),
                                _spashiny_ctx.ui.output_ui("alignment_st_current_input"),
                            ),
                            _spashiny_ctx.ui.div(
                                _spashiny_ctx.ui.tags.label(
                                    "Upload SM Data (.h5ad)", class_="control-label"
                                ),
                                _spashiny_ctx.ui.tags.input(
                                    type="file",
                                    accept=".h5ad",
                                    class_="form-control",
                                    **{"data-spashiny-alignment-upload": "sm"},
                                ),
                                _spashiny_ctx.ui.tags.div(
                                    "Select an SM H5AD file to upload.",
                                    id="alignment_sm_upload_status",
                                    class_="cloud-muted",
                                    style="font-size: 12px; margin-top: 8px;",
                                ),
                                _spashiny_ctx.ui.output_ui("alignment_sm_current_input"),
                                _spashiny_ctx.ui.tags.script(
                                    """
                                        (function () {
                                          function bindAlignmentUpload(kind) {
                                            var input = document.querySelector("input[data-spashiny-alignment-upload='" + kind + "']");
                                            var status = document.getElementById("alignment_" + kind + "_upload_status");
                                            if (!input || !status || input.dataset.spashinyBound === "1") return;
                                            input.dataset.spashinyBound = "1";
                                            function show(message) { status.textContent = message; }
                                            function emit(payload) {
                                              if (window.Shiny && typeof window.Shiny.setInputValue === "function") {
                                                payload.nonce = Date.now();
                                                window.Shiny.setInputValue("alignment_" + kind + "_canonical_upload", payload, {priority: "event"});
                                              }
                                            }
                                            input.addEventListener("change", function () {
                                              var file = input.files && input.files[0];
                                              if (!file) return;
                                              if (!window.SpaShinyMultipartUpload || typeof window.SpaShinyMultipartUpload.uploadFile !== "function") {
                                                show("Upload service is still loading. Please wait a moment and select the file again.");
                                                emit({status: "FAILED", code: "UPLOAD_SERVICE_NOT_READY", filename: file.name, size_bytes: file.size});
                                                return;
                                              }
                                              show("Selected " + file.name + " (" + file.size.toLocaleString() + " bytes). Starting secure upload…");
                                              emit({status: "SELECTED", filename: file.name, size_bytes: file.size});
                                              window.SpaShinyMultipartUpload.uploadFile(file, {
                                                onProgress: function (detail) {
                                                  var total = Number(detail.total_bytes || file.size || 0);
                                                  var uploaded = Number(detail.uploaded_bytes || 0);
                                                  var pct = total ? Math.min(100, Math.round((uploaded / total) * 100)) : 0;
                                                  var state = String(detail.status || "UPLOADING");
                                                  show(state === "COMPLETING" ? "Finalizing secure upload…" : "Uploading " + file.name + ": " + pct + "%");
                                                },
                                                onComplete: function (result) {
                                                  show("Ready: " + file.name + " uploaded successfully.");
                                                  emit({status: "READY", upload_id: String(result.upload_id || ""), filename: file.name, size_bytes: file.size});
                                                  input.value = "";
                                                },
                                              onError: function (error) {
                                                  var code = String((error && error.code) || "UPLOAD_FAILED");
                                                  var detail = String((error && (error.userMessage || error.message)) || code);
                                                  show("Upload failed: " + detail);
                                                  emit({status: "FAILED", code: code, message: detail, category: String((error && error.category) || "internal"), filename: file.name, size_bytes: file.size});
                                                }
                                              });
                                            });
                                          }
                                          function bindAll() { bindAlignmentUpload("st"); bindAlignmentUpload("sm"); }
                                          if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bindAll);
                                          else bindAll();
                                        })();
                                        """
                                ),
                            ),
                            _spashiny_ctx.ui.input_action_button(
                                "load_example_raw_h5ad",
                                "Load Example Raw ST/SM (Y7_T)",
                                class_="btn btn-secondary",
                            ),
                            _spashiny_ctx.ui.download_button(
                                "download_alignment_example_inputs",
                                "Download Example Inputs",
                                class_="btn btn-default",
                            ),
                            _spashiny_ctx.ui.div(
                                _spashiny_globals.example_source_note(
                                    "Example raw files: ST/adata_ST_Y7_T_raw.h5ad and SM/adata_SM_Y7_T_raw.h5ad.",
                                    "Load Example selects both Y7_T inputs for this analysis. Then click Start Preprocessing before manual alignment.",
                                ),
                                class_="subtle-text",
                            ),
                            *(
                                [_spashiny_globals.cloud_example_status("alignment-example-status")]
                                if _spashiny_globals.SPASHINY_WEB_PLATFORM
                                else []
                            ),
                            _spashiny_ctx.ui.hr(),
                            _spashiny_ctx.ui.input_action_button(
                                "process_alignment_pre",
                                "Start Preprocessing",
                                class_="btn btn-primary",
                            ),
                            _spashiny_ctx.ui.hr(),
                            _spashiny_ctx.ui.output_text("process_status_stsm_pre"),
                            class_="apple-card",
                        ),
                    ),
                    _spashiny_ctx.ui.column(
                        8,
                        _spashiny_ctx.ui.div(
                            _spashiny_ctx.ui.h4("Run Log"),
                            _spashiny_ctx.ui.div(
                                _spashiny_ctx.ui.output_text_verbatim("console_output"),
                                class_="apple-console",
                            ),
                            class_="apple-card",
                        ),
                    ),
                )
            )
        ),
        _spashiny_ctx.ui.div(
            _spashiny_ctx.ui.div(
                "ST-SM Image Registration and Interactive Adjustment", class_="section-title"
            ),
            _spashiny_ctx.ui.div(
                _spashiny_ctx.ui.card(
                    _spashiny_ctx.ui.h4("Step 1 — Original ST / SM"),
                    _spashiny_ctx.ui.p(
                        "ST on the left, SM on the right. Original tissue coordinates only; no rotation, flip, or coordinate rescaling.",
                        class_="subtle-text",
                    ),
                    _spashiny_ctx.ui.input_action_button(
                        "generate_initial", "Show Original ST / SM", class_="btn btn-primary"
                    ),
                    _spashiny_ctx.ui.div(
                        _spashiny_globals.plot_output_with_palette("initial_plot"),
                        class_="plot-card",
                    ),
                    _spashiny_ctx.ui.download_button(
                        "download_alignment_initial_png", "Download PNG", class_="btn btn-default"
                    ),
                    class_="apple-card",
                ),
                class_="center-card-9",
            ),
            _spashiny_ctx.ui.div(
                _spashiny_ctx.ui.row(
                    _spashiny_ctx.ui.column(1),
                    _spashiny_ctx.ui.column(
                        5,
                        _spashiny_ctx.ui.card(
                            _spashiny_ctx.ui.h4("Step 2 — Manual SM Adjustment"),
                            _spashiny_ctx.ui.p(
                                "Rotate, flip, scale uniformly or translate from the original coordinates. Apply Transformation confirms these absolute settings once, not on top of an earlier preview.",
                                class_="subtle-text",
                            ),
                            _spashiny_ctx.ui.output_text("sm_coordinate_policy_status"),
                            _spashiny_ctx.ui.div(
                                _spashiny_ctx.ui.input_numeric(
                                    "angle_input",
                                    "Rotation (degrees; positive clockwise in image view)",
                                    value=0,
                                    step=5,
                                ),
                                class_="control-block",
                            ),
                            _spashiny_ctx.ui.row(
                                _spashiny_ctx.ui.column(
                                    6,
                                    _spashiny_ctx.ui.div(
                                        _spashiny_ctx.ui.input_checkbox(
                                            "flip_horizontal", "Flip Horizontally", value=False
                                        ),
                                        class_="control-block checkbox-block",
                                    ),
                                ),
                                _spashiny_ctx.ui.column(
                                    6,
                                    _spashiny_ctx.ui.div(
                                        _spashiny_ctx.ui.input_checkbox(
                                            "flip_vertical", "Flip Vertically", value=False
                                        ),
                                        class_="control-block checkbox-block",
                                    ),
                                ),
                            ),
                            _spashiny_ctx.ui.div(
                                _spashiny_ctx.ui.input_numeric(
                                    "sm_uniform_scale",
                                    "Uniform scale multiplier (x)",
                                    value=1,
                                    min=1e-06,
                                    step=0.1,
                                ),
                                class_="control-block",
                            ),
                            _spashiny_ctx.ui.row(
                                _spashiny_ctx.ui.column(
                                    6,
                                    _spashiny_ctx.ui.div(
                                        _spashiny_ctx.ui.input_numeric(
                                            "translation_x",
                                            "X Translation (coordinate units)",
                                            value=0,
                                            step=5,
                                        ),
                                        class_="control-block",
                                    ),
                                ),
                                _spashiny_ctx.ui.column(
                                    6,
                                    _spashiny_ctx.ui.div(
                                        _spashiny_ctx.ui.input_numeric(
                                            "translation_y",
                                            "Y Translation (coordinate units)",
                                            value=0,
                                            step=5,
                                        ),
                                        class_="control-block",
                                    ),
                                ),
                            ),
                            _spashiny_ctx.ui.div(style="height: 12px;"),
                            _spashiny_ctx.ui.input_action_button(
                                "generate_rotated",
                                "Apply Transformation",
                                class_="btn btn-primary control-btn",
                            ),
                            class_="apple-card control-panel-card",
                        ),
                    ),
                    _spashiny_ctx.ui.column(
                        5,
                        _spashiny_ctx.ui.card(
                            _spashiny_ctx.ui.h4("Registration Preview"),
                            _spashiny_ctx.ui.div(
                                _spashiny_globals.plot_output_with_palette(
                                    "overlay_plot", height="520px", width="100%"
                                ),
                                class_="plot-card",
                            ),
                            _spashiny_ctx.ui.download_button(
                                "download_alignment_manual_png",
                                "Download PNG",
                                class_="btn btn-default",
                            ),
                            _spashiny_ctx.ui.download_button(
                                "download_alignment_pre_pdf",
                                "Download Alignment Plots PDF",
                                class_="btn btn-default",
                            ),
                            class_="apple-card",
                        ),
                    ),
                    _spashiny_ctx.ui.column(1),
                )
            ),
            _spashiny_ctx.ui.div(
                _spashiny_ctx.ui.card(
                    _spashiny_ctx.ui.h4("Step 3 — Automatic Alignment"),
                    _spashiny_ctx.ui.p(
                        "Load the parameters and coordinates confirmed in Step 2. The automatic model receives the once-transformed coordinates; no second rotation is applied.",
                        class_="subtle-text",
                    ),
                    _spashiny_ctx.ui.input_action_button(
                        "show_stsm_model", "Use Confirmed Coordinates", class_="btn btn-primary"
                    ),
                    class_="apple-card",
                ),
                class_="center-card-9",
            ),
        ),
    )


def ui(_spashiny_ctx, module):
    if module == "ST-SM Alignment":
        return _view_1(_spashiny_ctx, module)
    raise ValueError("Unknown feature page: alignment_manual")
