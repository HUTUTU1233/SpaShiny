# Feature river: original callable implementation extracted from river_st_module.py.
from spashiny._shared.feature_support import river_st_module as _feature_shared
from spashiny._shared import runtime_globals as _spashiny_globals


def _view_1(_spashiny_ctx, module):
    return _spashiny_globals.river_st_module_ui()


def ui(_spashiny_ctx, module):
    if module == "Spatial Transcriptomics River":
        return _view_1(_spashiny_ctx, module)
    raise ValueError("Unknown feature page: river")


def river_st_module_ui():
    return _feature_shared.ui.div(
        _feature_shared.ui.h2("Spatial Transcriptomics River"),
        _feature_shared.ui.p(
            "Choose the built-in dataset or upload your own ST samples, review their order, run River, then explore the ranked genes and draw expression plots from the completed result.",
            class_="cloud-muted",
        ),
        _feature_shared.ui.div(
            _feature_shared.ui.h4("Run River analysis"),
            _feature_shared.ui.input_radio_buttons(
                "river_st_data_source",
                "Data source",
                choices={
                    "EXAMPLE": "Built-in example dataset",
                    "USER_UPLOAD": "Upload my own data",
                },
                selected="EXAMPLE",
                inline=True,
            ),
            _feature_shared.ui.panel_conditional(
                "input.river_st_data_source === 'EXAMPLE'",
                _feature_shared.ui.p(
                    "The existing five-sample spa5 example is selected by default. No example files are regenerated.",
                    class_="cloud-muted",
                ),
                _feature_shared.ui.p(
                    "Five supplied spa5 H5AD inputs: V39 (Sham), V28 (D1), V38 (D3), V44 (D7), V27 (D28). Files record SpatialMETA QC min counts/genes=0 and removeHsp_mt_Rpl_Dnaj gene filtering. Loading preserves the stored expression and coordinates; the fixed River preparation runs only on submission. Sample order and labels remain editable. The model uses sample labels, not elapsed biological days. No cell-type annotations are inferred.",
                    class_="cloud-muted",
                ),
                _feature_shared.ui.output_ui("river_st_example_retry"),
                _feature_shared.ui.tags.details(
                    _feature_shared.ui.tags.summary("Other examples"),
                    _feature_shared.ui.input_action_button(
                        "river_st_load_example",
                        "Load WT/Diabetes Slide-seq example (6 samples)",
                        class_="btn btn-secondary",
                    ),
                    _feature_shared.ui.p(
                        "These are WT and Diabetes replicates, not known biological time points. Set their order and time labels explicitly.",
                        class_="cloud-muted",
                    ),
                ),
            ),
            _feature_shared.ui.panel_conditional(
                "input.river_st_data_source === 'USER_UPLOAD'",
                _feature_shared.ui.p(
                    "Upload one ZIP containing 2–64 H5AD samples, or multiple H5AD files directly. Each sample must have at least 1,052 spots, unique spot/gene IDs, a finite nonnegative .X matrix, and real two-dimensional coordinates in .obsm['spatial']. Annotation CSV is optional. Expression processing state is checked before submission.",
                    class_="cloud-muted",
                ),
                _feature_shared.ui.div(
                    _feature_shared.ui.tags.div(
                        "ZIP archive containing two or more .h5ad files", class_="control-label"
                    ),
                    _feature_shared.ui.tags.input(
                        type="file",
                        accept=".zip,application/zip",
                        class_="form-control",
                        **{"data-spashiny-river-archive-upload": "1"},
                    ),
                    _feature_shared.ui.tags.div(
                        "Select one ZIP package.",
                        id="river_st_archive_upload_status",
                        class_="cloud-muted",
                        style="font-size:12px; margin-top:8px;",
                    ),
                    _feature_shared.ui.tags.script(
                        """
                    (function () {
                      function bindRiverArchiveUpload() {
                        var picker = document.querySelector("input[data-spashiny-river-archive-upload='1']");
                        var status = document.getElementById("river_st_archive_upload_status");
                        if (!picker || !status || picker.dataset.spashinyBound === "1") return;
                        picker.dataset.spashinyBound = "1";
                        function show(message) { status.textContent = message; }
                        function emit(payload) {
                          if (window.Shiny && typeof window.Shiny.setInputValue === "function") {
                            payload.nonce = Date.now();
                            window.Shiny.setInputValue("river_st_canonical_archive_upload", payload, {priority: "event"});
                          }
                        }
                        picker.addEventListener("change", function () {
                          var file = picker.files && picker.files[0];
                          if (!file) return;
                          if (!/\\.zip$/i.test(file.name || "")) {
                            show("Upload failed: River requires a .zip package.");
                            emit({status: "FAILED", code: "INVALID_FILE_TYPE", filename: file.name, size_bytes: file.size});
                            picker.value = "";
                            return;
                          }
                          if (!window.SpaShinyMultipartUpload || typeof window.SpaShinyMultipartUpload.uploadFile !== "function") {
                            show("Upload service is still loading. Please wait and select the package again.");
                            emit({status: "FAILED", code: "UPLOAD_SERVICE_NOT_READY", filename: file.name, size_bytes: file.size});
                            return;
                          }
                          show("Starting secure upload: " + file.name);
                          if (window.SpaShinyRiverProgress) {
                            window.SpaShinyRiverProgress.show("Uploading River package", file.name);
                          }
                          emit({status: "SELECTED", filename: file.name, size_bytes: file.size});
                          window.SpaShinyMultipartUpload.uploadFile(file, {
                            onProgress: function (detail) {
                              var total = Number(detail.total_bytes || file.size || 0);
                              var uploaded = Number(detail.uploaded_bytes || 0);
                              var pct = total ? Math.min(100, Math.round((uploaded / total) * 100)) : 0;
                              var state = String(detail.status || "UPLOADING");
                              show(state === "COMPLETING" ? "Finalizing secure upload…" : "Uploading " + file.name + ": " + pct + "%");
                              if (window.SpaShinyRiverProgress) {
                                window.SpaShinyRiverProgress.update("Uploading River package", state === "COMPLETING" ? "Finalizing secure upload…" : file.name + ": " + pct + "%");
                              }
                            },
                            onComplete: function (result) {
                              show("Ready: " + file.name + " uploaded successfully. Click Inspect package.");
                              if (window.SpaShinyRiverProgress) window.SpaShinyRiverProgress.hide();
                              emit({status: "READY", upload_id: String(result.upload_id || ""), filename: file.name, size_bytes: file.size});
                              picker.value = "";
                            },
                            onError: function (error) {
                              var code = String((error && error.code) || "UPLOAD_FAILED");
                              var detail = String((error && (error.userMessage || error.message)) || code);
                              show("Upload failed: " + detail);
                              if (window.SpaShinyRiverProgress) window.SpaShinyRiverProgress.hide();
                              emit({status: "FAILED", code: code, message: detail, category: String((error && error.category) || "internal"), filename: file.name, size_bytes: file.size});
                            }
                          }).catch(function () {});
                        });
                      }
                      if (document.readyState === "loading") {
                        document.addEventListener("DOMContentLoaded", bindRiverArchiveUpload, {once: true});
                      } else {
                        bindRiverArchiveUpload();
                      }
                    })();
                    """
                    ),
                ),
                _feature_shared.ui.p(
                    "Each H5AD is treated as one time point. Nested folders are accepted; duplicate file names are not.",
                    class_="cloud-muted",
                ),
                _feature_shared.ui.tags.details(
                    _feature_shared.ui.tags.summary(
                        "Upload multiple H5AD files directly (instead of a ZIP)"
                    ),
                    _feature_shared.ui.input_file(
                        "river_st_h5_files",
                        "Spatial-transcriptomics files (.h5ad)",
                        accept=[".h5ad"],
                        multiple=True,
                    ),
                    _feature_shared.ui.input_file(
                        "river_st_csv_files",
                        "Optional annotation CSV files",
                        accept=[".csv"],
                        multiple=True,
                    ),
                    style="margin: 10px 0;",
                ),
            ),
            _feature_shared.ui.input_action_button(
                "river_st_preview", "Inspect package", class_="btn btn-secondary"
            ),
            _feature_shared.ui.output_ui("river_st_detected_inputs"),
            _feature_shared.ui.h4("Run settings", style="margin-top: 16px;"),
            _feature_shared.ui.p(
                "Original Python Parity — one execution core for examples and uploaded data. Annotation is optional; no celltype column is required.",
                class_="cloud-muted",
            ),
            _feature_shared.ui.output_text("river_st_subsample_info"),
            _feature_shared.ui.p(
                "Fixed workflow: Scanpy subsample 1052, random_state=0, seed=42, 100 training epochs. The original scSLAT joint PCA and historical training behavior are retained; no extra Runner PCA. A training fit is not independent biological validation.",
                class_="cloud-muted",
            ),
            _feature_shared.ui.output_ui("river_st_scale_review"),
            _feature_shared.ui.output_ui("river_st_run_control"),
            _feature_shared.ui.div(
                _feature_shared.ui.output_text("river_st_status"),
                class_="cloud-muted",
                style="margin-top: 12px;",
            ),
            _feature_shared.ui.output_ui("river_st_preview_result"),
            class_="apple-card",
        ),
        _feature_shared.ui.div(
            _feature_shared.ui.h4("River jobs"),
            _feature_shared.ui.output_ui("river_st_jobs"),
            class_="apple-card",
            style="margin-top: 16px;",
        ),
        _feature_shared.ui.div(
            _feature_shared.ui.output_ui("river_st_full_spot_controls"),
            _feature_shared.ui.output_ui("river_st_full_spot_result"),
            class_="apple-card",
            style="margin-top:16px;",
        ),
        _feature_shared.ui.div(
            _feature_shared.ui.h4("3. Explore completed River results"),
            _feature_shared.ui.output_ui("river_st_completed_controls"),
            _feature_shared.ui.output_ui("river_st_top_gene_note"),
            _feature_shared.ui.output_data_frame("river_st_top_genes"),
            _feature_shared.ui.output_ui("river_st_replot_result"),
            class_="apple-card",
            style="margin-top:16px;",
        ),
        _feature_shared.ui.p(
            "River PDF downloads keep chart/text elements editable in Adobe Illustrator; image-backed tissue layers remain raster images.",
            class_="cloud-muted",
            style="margin-top: 10px;",
        ),
    )
