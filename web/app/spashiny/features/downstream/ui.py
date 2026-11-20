# Actual feature UI extracted from production. Feature: downstream.
from spashiny._shared import runtime_globals as _spashiny_globals
from spashiny.features.celltype_annotation import ui as _section_ui_celltype_annotation
from spashiny.features.correlation import ui as _section_ui_correlation
from spashiny.features.marker import ui as _section_ui_marker
from spashiny.features.roi import ui as _section_ui_roi
from spashiny.features.spatialmeta_dash import ui as _section_ui_spatialmeta_dash
from spashiny.features.toi import ui as _section_ui_toi
from spashiny.features.volcano import ui as _section_ui_volcano


def _view_1(_spashiny_ctx, module):
    return _spashiny_ctx.ui.page_fluid(
        _spashiny_ctx.ui.HTML(_spashiny_ctx.at_sm_st1_apple_css),
        _spashiny_ctx.ui.div(
            {"class": "at-page-shell"},
            _spashiny_ctx.ui.div(
                {"class": "at-hero"},
                _spashiny_ctx.ui.h1("Spatial Omics Downstream Analysis", class_="at-title"),
                _spashiny_ctx.ui.p(
                    "Integrated workflow for AnnData upload, marker discovery, correlation analysis, volcano visualization, trajectory exploration, and ROI annotation.",
                    class_="at-subtitle",
                ),
            ),
            _spashiny_ctx.ui.div(
                {"class": "at-stack"},
                _spashiny_ctx.ui.div(
                    _spashiny_ctx.ui.div(
                        _spashiny_ctx.ui.layout_columns(
                            _spashiny_ctx.ui.div(
                                _spashiny_ctx.ui.div(
                                    "File Upload",
                                    class_="apple-section-title",
                                    style="margin-bottom: 5px; font-size: 1.2rem;",
                                ),
                                (
                                    _spashiny_ctx.ui.div(
                                        _spashiny_ctx.ui.tags.input(
                                            type="file",
                                            accept=".h5ad",
                                            class_="form-control",
                                            **{"data-spashiny-downstream-upload": "1"},
                                        ),
                                        _spashiny_ctx.ui.tags.div(
                                            "Select an H5AD file to upload.",
                                            id="downstream_upload_status",
                                            class_="cloud-muted",
                                            style="font-size: 12px; margin-top: 8px;",
                                        ),
                                        _spashiny_ctx.ui.output_ui("downstream_current_input"),
                                        _spashiny_ctx.ui.tags.script(
                                            """
                                                (function () {
                                                  function bindDownstreamUpload() {
                                                    var input = document.querySelector("input[data-spashiny-downstream-upload='1']");
                                                    var status = document.getElementById("downstream_upload_status");
                                                    if (!input || !status || input.dataset.spashinyBound === "1") return;
                                                    input.dataset.spashinyBound = "1";
                                                    function show(message) { status.textContent = message; }
                                                    function emit(payload) {
                                                      if (window.Shiny && typeof window.Shiny.setInputValue === "function") {
                                                        payload.nonce = Date.now();
                                                        window.Shiny.setInputValue("downstream_canonical_upload", payload, {priority: "event"});
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
                                                  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bindDownstreamUpload);
                                                  else bindDownstreamUpload();
                                                })();
                                                """
                                        ),
                                    )
                                    if _spashiny_globals.SPASHINY_WEB_PLATFORM
                                    else _spashiny_ctx.ui.input_file(
                                        "upload_h5ad", None, accept=[".h5ad"], width="100%"
                                    )
                                ),
                            ),
                            _spashiny_ctx.ui.div(
                                _spashiny_ctx.ui.div(
                                    _spashiny_ctx.ui.input_action_button(
                                        "btn_load",
                                        "Load",
                                        class_="btn-apple-action",
                                        style="flex: 1;",
                                    ),
                                    _spashiny_ctx.ui.input_action_button(
                                        "load_downstream_example",
                                        "Load Example",
                                        class_=_spashiny_globals.cloud_example_button_class(
                                            "btn-apple-action"
                                        ),
                                        style="flex: 1; background: var(--apple-green);",
                                        **_spashiny_globals.cloud_example_action_attrs(
                                            "y7-downstream-example",
                                            "downstream",
                                            "downstream-example-status",
                                        ),
                                    ),
                                    _spashiny_ctx.ui.input_action_button(
                                        "btn_process",
                                        "Process",
                                        class_="btn-apple-action",
                                        style="flex: 1; background: var(--apple-orange);",
                                    ),
                                    style="display: flex; gap: 10px; margin-top: 25px;",
                                ),
                                _spashiny_ctx.ui.div(
                                    _spashiny_globals.example_source_note(
                                        "Example source: user_data/input/joint/Y7_T_adata_joint_hvf2800_afterVAE_annoSM.h5ad",
                                        "Cloud example: click Load Example to bind and load the Y7_T downstream analysis h5ad for this page.",
                                    ),
                                    style="font-size:12px; color:#86868b; line-height:1.5; margin-top:8px;",
                                ),
                                *(
                                    [
                                        _spashiny_globals.cloud_example_status(
                                            "downstream-example-status"
                                        )
                                    ]
                                    if _spashiny_globals.SPASHINY_WEB_PLATFORM
                                    else []
                                ),
                            ),
                            col_widths=(7, 5),
                        ),
                        class_="at-hero",
                        style="padding: 12px 24px; min-height: 80px;",
                    ),
                    class_="at-compact-controls",
                ),
                _spashiny_ctx.ui.div(
                    {"class": "apple-panel"},
                    _spashiny_ctx.ui.div("Dataset Overview", class_="apple-section-title"),
                    _spashiny_ctx.ui.layout_columns(
                        _spashiny_ctx.ui.div(
                            {"class": "table-shell"},
                            _spashiny_ctx.ui.div("Upload Status", class_="plot-title"),
                            _spashiny_ctx.ui.output_ui("ui_upload_status"),
                        ),
                        _spashiny_ctx.ui.div(
                            {"class": "table-shell"},
                            _spashiny_ctx.ui.div("Data Summary", class_="plot-title"),
                            _spashiny_ctx.ui.output_ui("downstream_summary_download"),
                            _spashiny_ctx.ui.output_table("tbl_summary"),
                        ),
                        _spashiny_ctx.ui.div(
                            {"class": "table-shell"},
                            _spashiny_ctx.ui.div("Cell Type Distribution", class_="plot-title"),
                            _spashiny_ctx.ui.output_ui("downstream_distribution_download"),
                            _spashiny_ctx.ui.output_text("txt_celltype"),
                        ),
                        col_widths=(4, 4, 4),
                    ),
                    _spashiny_ctx.ui.div(
                        {"class": "table-shell mt-3"},
                        _spashiny_ctx.ui.div(
                            "Observation Table (Top 50 Rows)", class_="plot-title"
                        ),
                        _spashiny_ctx.ui.output_ui("downstream_observations_download"),
                        _spashiny_ctx.ui.output_data_frame("df_obs"),
                    ),
                ),
                _spashiny_ctx.ui.div(
                    {"class": "apple-panel"},
                    _spashiny_ctx.ui.div("Marker Analysis", class_="apple-section-title"),
                    _spashiny_ctx.ui.input_select(
                        "downstream_expression_source",
                        "Expression matrix for Marker and subsequent correlation",
                        choices={
                            "X": "X — as provided (SpatialMETA tutorial)",
                            "normalized": "Existing layers['normalized'] — no additional transform",
                        },
                        selected="X",
                        width="100%",
                    ),
                    _spashiny_ctx.ui.p(
                        "No automatic log1p or normalization is applied. Choose a matrix prepared for downstream analysis. Missing layers are reported, never substituted.",
                        class_="apple-muted",
                    ),
                    _section_ui_marker._section_1(_spashiny_ctx),
                ),
                _section_ui_marker._section_2(_spashiny_ctx),
                _section_ui_celltype_annotation._section_1(_spashiny_ctx),
                _section_ui_celltype_annotation._section_2(_spashiny_ctx),
                _section_ui_marker._section_3(_spashiny_ctx),
                _spashiny_ctx.ui.layout_columns(
                    _section_ui_correlation._section_1(_spashiny_ctx),
                    _spashiny_ctx.ui.div(
                        {"class": "apple-panel"},
                        _spashiny_ctx.ui.div(
                            "ST-SM Correlation Analysis", class_="apple-section-title"
                        ),
                        _spashiny_ctx.ui.div(
                            {"class": "correlation-plot-shell", "id": "correlation-heatmap-card"},
                            _spashiny_ctx.ui.div(
                                {"class": "plot-title-row"},
                                _spashiny_ctx.ui.div("Correlation Heatmap", class_="plot-title"),
                                _spashiny_ctx.ui.download_button(
                                    "download_corr_heatmap_png",
                                    "Save PNG",
                                    class_="btn plot-download-button",
                                ),
                                _spashiny_ctx.ui.download_button(
                                    "download_corr_heatmap_pdf",
                                    "Save Editable PDF",
                                    class_="btn plot-download-button",
                                ),
                            ),
                            _spashiny_globals.plot_output_with_palette(
                                "plt_corr_heatmap", width="100%", height="540px"
                            ),
                        ),
                    ),
                    col_widths=(6, 6),
                ),
                _section_ui_volcano._section_1(_spashiny_ctx),
                _section_ui_volcano._section_2(_spashiny_ctx),
                _spashiny_globals.network_panel_ui(),
                _section_ui_spatialmeta_dash._section_1(_spashiny_ctx),
                _section_ui_toi._section_1(_spashiny_ctx),
                _section_ui_roi._section_1(_spashiny_ctx),
            ),
        ),
    )


def ui(_spashiny_ctx, module):
    if module == "AT_SM_ST1":
        return _view_1(_spashiny_ctx, module)
    raise ValueError("Unknown feature page: downstream")
