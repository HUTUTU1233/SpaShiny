# Actual feature UI extracted from production. Feature: st_qc.
from spashiny._shared import runtime_globals as _spashiny_globals


def _view_1(_spashiny_ctx, module):
    return _spashiny_ctx.ui.page_fluid(
        _spashiny_ctx.ui.tags.style(
            """
                body {
                    background-color: #f5f5f7;
                    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif;
                    color: #1d1d1f;
                }

                /* Remove icons from titles and increase spacing */
                h2 { font-weight: 600; margin: 30px 0; letter-spacing: -0.02em; }
                h4 { font-weight: 500; margin-bottom: 15px; font-size: 16px; }

                .card-box {
                    background: #ffffff;
                    border-radius: 18px;
                    padding: 24px;
                    border: 1px solid rgba(0,0,0,0.05);
                    box-shadow: 0 8px 24px rgba(0,0,0,0.04);
                    transition: all 0.3s ease;
                }

                /* Run button - Apple blue */
                .btn-primary {
                    background-color: #007aff;
                    border: none;
                    border-radius: 10px;
                    padding: 10px;
                    font-weight: 500;
                    width: 100%;
                }

                /* Export button - light gray background + black text */
                .btn-secondary {
                    background-color: #f5f5f7;
                    border: 1px solid #d2d2d7;
                    border-radius: 10px;
                    color: #1d1d1f !important; /* Force black font */
                    font-weight: 500;
                    width: 100%;
                    padding: 10px;
                }
                .btn-secondary:hover { background-color: #e8e8ed; border-color: #86868b; }

                /* White-style log window */
                .console-box {
                    background: #ffffff; /* Changed to white */
                    color: #424245;      /* Dark gray text */
                    border-radius: 12px;
                    padding: 15px;
                    height: 350px;       /* Fixed height */
                    overflow-y: auto;
                    font-family: "SF Mono", Menlo, monospace;
                    font-size: 12px;
                    line-height: 1.6;
                    border: 1px solid #d2d2d7;
                    box-shadow: inset 0 2px 4px rgba(0,0,0,0.02);
                }

                /* Force remove input shadow */
                .form-control, .form-select {
                    border-radius: 10px;
                    border: 1px solid #d2d2d7;
                    background-color: #ffffff;
                }

                .section-gap { margin-top: 16px; }
                .qc-param-grid {
                    display: grid;
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                    gap: 8px 10px;
                    margin-top: 8px;
                    margin-bottom: 12px;
                }
                .qc-param-grid .shiny-input-container,
                .qc-param-grid .form-group {
                    margin-bottom: 0 !important;
                    width: 100%;
                }
                .qc-param-grid label {
                    font-size: 12px !important;
                    color: #424245 !important;
                    margin-bottom: 4px !important;
                }
                .qc-param-grid input {
                    min-height: 38px !important;
                    padding: 7px 10px !important;
                    border-radius: 8px !important;
                }

                 /* Center alignment helper */
                 .justify-content-center { display: flex; justify-content: center; }
                 """
        ),
        _spashiny_ctx.ui.h2("Quality Control"),
        _spashiny_ctx.ui.accordion(
            _spashiny_ctx.ui.accordion_panel(
                "Execution",
                _spashiny_ctx.ui.row(
                    _spashiny_ctx.ui.column(
                        4,
                        _spashiny_ctx.ui.div(
                            _spashiny_ctx.ui.div(
                                "Upload Data",
                                class_="control-label",
                                style="font-size:12px; color:#86868b; margin-bottom:5px;",
                            ),
                            (
                                _spashiny_ctx.ui.div(
                                    _spashiny_ctx.ui.tags.input(
                                        type="file",
                                        accept=".h5ad,.h5,.hdf5",
                                        class_="form-control",
                                        **{"data-spashiny-st-qc-upload": "1"},
                                    ),
                                    _spashiny_ctx.ui.tags.div(
                                        "Select an H5AD file to upload.",
                                        id="st_qc_upload_status",
                                        class_="cloud-muted",
                                        style="font-size: 12px; margin-top: 8px;",
                                    ),
                                    _spashiny_ctx.ui.output_ui("st_qc_current_input"),
                                    _spashiny_ctx.ui.tags.script(
                                        """
                                            (function () {
                                              function bindStQcUpload() {
                                                var input = document.querySelector("input[data-spashiny-st-qc-upload='1']");
                                                var status = document.getElementById("st_qc_upload_status");
                                                if (!input || !status || input.dataset.spashinyBound === "1") return;
                                                input.dataset.spashinyBound = "1";
                                                function show(message) { status.textContent = message; }
                                                function emit(payload) {
                                                  if (window.Shiny && typeof window.Shiny.setInputValue === "function") {
                                                    payload.nonce = Date.now();
                                                    window.Shiny.setInputValue("st_qc_canonical_upload", payload, {priority: "event"});
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
                                                  }).catch(function () {});
                                                });
                                              }
                                              if (document.readyState === "loading") {
                                                document.addEventListener("DOMContentLoaded", bindStQcUpload, {once: true});
                                              } else {
                                                bindStQcUpload();
                                              }
                                            })();
                                            """
                                    ),
                                )
                                if _spashiny_globals.SPASHINY_WEB_PLATFORM
                                else _spashiny_ctx.ui.input_file("st_qc_file", None, multiple=False)
                            ),
                            _spashiny_ctx.ui.input_action_button(
                                "load_example_st_qc",
                                "Load Example ST QC (Y7_T)",
                                class_=_spashiny_globals.cloud_example_button_class(
                                    "btn btn-secondary"
                                ),
                                style="margin-top:10px;",
                                **_spashiny_globals.cloud_example_action_attrs(
                                    "y7-st-qc-example", "st_qc", "st-qc-example-status"
                                ),
                            ),
                            _spashiny_ctx.ui.div(
                                _spashiny_globals.example_source_note(
                                    "Example source: user_data/input/sample-1_Y7_T/ST/adata_ST_Y7_T_raw.h5ad",
                                    "Cloud example: Y7_T ST h5ad is bound to this session on click.",
                                ),
                                style="font-size:12px; color:#86868b; line-height:1.5; margin-top:6px;",
                            ),
                            *(
                                [_spashiny_globals.cloud_example_status("st-qc-example-status")]
                                if _spashiny_globals.SPASHINY_WEB_PLATFORM
                                else []
                            ),
                            _spashiny_ctx.ui.div(class_="section-gap"),
                            _spashiny_ctx.ui.div(
                                "Species",
                                class_="control-label",
                                style="font-size:12px; color:#86868b; margin-bottom:5px;",
                            ),
                            _spashiny_ctx.ui.input_select(
                                "st_species",
                                None,
                                {"Human": "Homo sapiens", "Mouse": "Mus musculus"},
                            ),
                            _spashiny_ctx.ui.div(class_="section-gap"),
                            _spashiny_ctx.ui.div(
                                "Filtering thresholds",
                                class_="control-label",
                                style="font-size:12px; color:#86868b; margin-bottom:5px;",
                            ),
                            _spashiny_ctx.ui.div(
                                _spashiny_ctx.ui.input_numeric(
                                    "st_qc_min_counts",
                                    "Minimum counts",
                                    value=_spashiny_globals.DEFAULT_ST_QC_MIN_COUNTS,
                                    min=0,
                                    step=100,
                                ),
                                _spashiny_ctx.ui.input_numeric(
                                    "st_qc_min_genes",
                                    "Minimum genes",
                                    value=_spashiny_globals.DEFAULT_ST_QC_MIN_GENES,
                                    min=0,
                                    step=100,
                                ),
                                class_="qc-param-grid",
                            ),
                            _spashiny_ctx.ui.div(class_="section-gap"),
                            _spashiny_ctx.ui.input_action_button(
                                "run_st_qc", "Run Pipeline", class_="btn btn-primary"
                            ),
                            _spashiny_ctx.ui.div(class_="section-gap"),
                            _spashiny_ctx.ui.input_text(
                                "st_qc_filename", None, placeholder="File name..."
                            ),
                            _spashiny_ctx.ui.download_button(
                                "download_st_qc", "Export Data", class_="btn btn-secondary"
                            ),
                            _spashiny_ctx.ui.download_button(
                                "download_st_qc_pdf", "Export QC PDF", class_="btn btn-secondary"
                            ),
                            class_="card-box",
                        ),
                    ),
                    _spashiny_ctx.ui.column(
                        8,
                        _spashiny_ctx.ui.div(
                            _spashiny_ctx.ui.h4("System Log"),
                            _spashiny_ctx.ui.div(
                                _spashiny_ctx.ui.output_text_verbatim("st_console_output"),
                                class_="console-box",
                            ),
                            class_="card-box",
                        ),
                    ),
                ),
            ),
            _spashiny_ctx.ui.accordion_panel(
                "Visualization",
                _spashiny_ctx.ui.row(
                    _spashiny_ctx.ui.column(
                        6,
                        _spashiny_ctx.ui.div(
                            _spashiny_ctx.ui.h4("Violin Plot"),
                            _spashiny_globals.plot_output_with_palette("st_qc_violin"),
                            class_="card-box",
                        ),
                    ),
                    _spashiny_ctx.ui.column(
                        6,
                        _spashiny_ctx.ui.div(
                            _spashiny_ctx.ui.h4("Histogram"),
                            _spashiny_globals.plot_output_with_palette("st_qc_hist"),
                            class_="card-box",
                        ),
                    ),
                ),
                _spashiny_ctx.ui.div(class_="section-gap"),
                _spashiny_ctx.ui.row(
                    _spashiny_ctx.ui.column(
                        9,
                        _spashiny_ctx.ui.div(
                            _spashiny_ctx.ui.h4("Spatial Mapping"),
                            _spashiny_globals.plot_output_with_palette("st_qc_spatial"),
                            class_="card-box",
                        ),
                    ),
                    class_="justify-content-center",
                ),
            ),
            id="st_qc_accordion_main",
        ),
    )


def ui(_spashiny_ctx, module):
    if module == "ST_QC":
        return _view_1(_spashiny_ctx, module)
    raise ValueError("Unknown feature page: st_qc")
