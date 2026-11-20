# Actual feature UI extracted from production. Feature: sm_qc.
from spashiny._shared import runtime_globals as _spashiny_globals


def _view_1(_spashiny_ctx, module):
    return _spashiny_ctx.ui.page_fluid(
        _spashiny_ctx.ui.HTML(_spashiny_ctx.qc_apple_style),
        _spashiny_ctx.ui.h2("SM Data Quality Control", class_="qc-header"),
        _spashiny_ctx.ui.accordion(
            _spashiny_ctx.ui.accordion_panel(
                "QC Analysis Configuration",
                _spashiny_ctx.ui.row(
                    _spashiny_ctx.ui.column(
                        4,
                        _spashiny_ctx.ui.div(
                            _spashiny_ctx.ui.div("Data Upload (.h5ad)", class_="control-label"),
                            (
                                _spashiny_ctx.ui.div(
                                    _spashiny_ctx.ui.tags.input(
                                        type="file",
                                        accept=".h5ad,.h5,.hdf5",
                                        class_="form-control",
                                        **{"data-spashiny-sm-qc-upload": "1"},
                                    ),
                                    _spashiny_ctx.ui.tags.div(
                                        "Select an H5AD file to upload.",
                                        id="sm_qc_upload_status",
                                        class_="cloud-muted",
                                        style="font-size: 12px; margin-top: 8px;",
                                    ),
                                    _spashiny_ctx.ui.output_ui("sm_qc_current_input"),
                                    _spashiny_ctx.ui.tags.script(
                                        """
                                            (function () {
                                              function bindSmQcUpload() {
                                                var input = document.querySelector("input[data-spashiny-sm-qc-upload='1']");
                                                var status = document.getElementById("sm_qc_upload_status");
                                                if (!input || !status || input.dataset.spashinyBound === "1") return;
                                                input.dataset.spashinyBound = "1";
                                                function show(message) { status.textContent = message; }
                                                function emit(payload) {
                                                  if (window.Shiny && typeof window.Shiny.setInputValue === "function") {
                                                    payload.nonce = Date.now();
                                                    window.Shiny.setInputValue("sm_qc_canonical_upload", payload, {priority: "event"});
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
                                                document.addEventListener("DOMContentLoaded", bindSmQcUpload, {once: true});
                                              } else {
                                                bindSmQcUpload();
                                              }
                                            })();
                                            """
                                    ),
                                )
                                if _spashiny_globals.SPASHINY_WEB_PLATFORM
                                else _spashiny_ctx.ui.input_file("st_file", None, multiple=False)
                            ),
                            _spashiny_ctx.ui.input_action_button(
                                "load_example_sm_qc",
                                "Load Example SM QC (Y7_T)",
                                class_=_spashiny_globals.cloud_example_button_class(
                                    "btn-apple btn-apple-secondary"
                                ),
                                **_spashiny_globals.cloud_example_action_attrs(
                                    "y7-sm-qc-example", "sm_qc", "sm-qc-example-status"
                                ),
                            ),
                            _spashiny_ctx.ui.div(
                                _spashiny_globals.example_source_note(
                                    f"Example source: {_spashiny_globals.workspace_relative_path(_spashiny_globals.USER_INPUT_DIR / _spashiny_globals.EXAMPLE_SAMPLE_NAME / 'SM' / _spashiny_globals.EXAMPLE_SM_QC_H5AD_NAME)}",
                                    "Cloud example: Y7_T SM raw h5ad is bound to this session on click.",
                                ),
                                style="font-size: 12px; color: #6e6e73; margin-top: 6px;",
                            ),
                            *(
                                [_spashiny_globals.cloud_example_status("sm-qc-example-status")]
                                if _spashiny_globals.SPASHINY_WEB_PLATFORM
                                else []
                            ),
                            _spashiny_ctx.ui.hr(
                                style="border-top: 1px solid #e5e5e5; margin: 20px 0;"
                            ),
                            _spashiny_ctx.ui.div("Parameter Settings", class_="control-label"),
                            _spashiny_ctx.ui.input_text(
                                "sm_qc_filename", None, placeholder="Enter export file name..."
                            ),
                            _spashiny_ctx.ui.div(
                                _spashiny_ctx.ui.input_numeric(
                                    "sm_qc_min_total_intensity",
                                    "Minimum total intensity",
                                    value=_spashiny_globals.DEFAULT_SM_QC_MIN_TOTAL_INTENSITY,
                                    min=0,
                                    step=10000.0,
                                ),
                                class_="qc-param-grid",
                            ),
                            _spashiny_ctx.ui.input_action_button(
                                "run_qc",
                                "Calculate QC Metrics",
                                class_="btn-apple btn-apple-primary",
                            ),
                            _spashiny_ctx.ui.download_button(
                                "download_sm_qc",
                                "Download QC Results",
                                class_="btn-apple btn-apple-secondary",
                            ),
                            _spashiny_ctx.ui.download_button(
                                "download_qc_pdf",
                                "Export QC PDF",
                                class_="btn-apple btn-apple-secondary",
                            ),
                            _spashiny_ctx.ui.div(
                                _spashiny_ctx.ui.output_text("qc_status"),
                                style="margin-top: 10px; font-size: 13px; color: #007aff;",
                            ),
                            class_="control-panel",
                        ),
                    ),
                    _spashiny_ctx.ui.column(
                        8,
                        _spashiny_ctx.ui.div(
                            _spashiny_ctx.ui.div("Processing Log", class_="control-label"),
                            _spashiny_ctx.ui.div(
                                _spashiny_ctx.ui.output_text_verbatim("sm_qc_console_output"),
                                class_="console-window",
                            ),
                            class_="control-panel",
                        ),
                    ),
                ),
            ),
            _spashiny_ctx.ui.accordion_panel(
                "Visualization and Evaluation Results",
                _spashiny_ctx.ui.row(
                    _spashiny_ctx.ui.column(
                        6,
                        _spashiny_ctx.ui.div(
                            _spashiny_ctx.ui.div("Violin Plot", class_="plot-title"),
                            _spashiny_globals.plot_output_with_palette("qc_violin"),
                            class_="plot-card",
                        ),
                    ),
                    _spashiny_ctx.ui.column(
                        6,
                        _spashiny_ctx.ui.div(
                            _spashiny_ctx.ui.div("Histogram Distribution", class_="plot-title"),
                            _spashiny_globals.plot_output_with_palette("qc_hist"),
                            class_="plot-card",
                        ),
                    ),
                ),
                _spashiny_ctx.ui.row(
                    _spashiny_ctx.ui.column(
                        9,
                        _spashiny_ctx.ui.div(
                            _spashiny_ctx.ui.div("Spatial Distribution Map", class_="plot-title"),
                            _spashiny_globals.plot_output_with_palette("qc_spatial"),
                            class_="plot-card",
                        ),
                        offset=1,
                    )
                ),
            ),
            id="sm_qc_accordion",
        ),
    )


def ui(_spashiny_ctx, module):
    if module == "SM_QC":
        return _view_1(_spashiny_ctx, module)
    raise ValueError("Unknown feature page: sm_qc")
