# Actual feature UI extracted from production. Feature: metabolite_annotation.
from spashiny._shared import runtime_globals as _spashiny_globals


def _view_1(_spashiny_ctx, module):
    return _spashiny_globals.spatialmeta_metabolite_annotation_module_ui()


def spatialmeta_metabolite_annotation_module_ui():
    """Public annotation surface: exactly the canonical SpatialMETA procedure."""
    return _spashiny_globals.ui.div(
        _spashiny_globals.ui.h2("Metabolite Annotation"),
        _spashiny_globals.ui.p(
            "Metabolite Annotation uses the annotation procedure implemented in SpatialMETA to assign candidate metabolites to spatial metabolomics features based on m/z and the selected adduct/tolerance settings.",
            class_="cloud-muted",
        ),
        _spashiny_globals.ui.tags.div(
            _spashiny_globals.ui.tags.strong("Interpretation: "),
            _spashiny_globals.ui.tags.span(
                "results are putative candidates, not confirmed metabolite identifications."
            ),
            class_="cloud-muted",
            style="margin-bottom: 12px;",
        ),
        _spashiny_globals.ui.div(
            _spashiny_globals.ui.h4("Spatial metabolomics input"),
            _spashiny_globals.ui.p(
                "Upload one spatial-metabolomics H5AD for the current analysis tab, or run the built-in Y7_T SM example. Inputs and results remain bound to this analysis session.",
                class_="cloud-muted",
            ),
            _spashiny_globals.ui.div(
                _spashiny_globals.ui.tags.input(
                    type="file",
                    accept=".h5ad",
                    class_="form-control",
                    **{"data-spashiny-metabolite-annotation-upload": "1"},
                ),
                _spashiny_globals.ui.tags.div(
                    "Select an H5AD file to upload.",
                    id="metabolite_annotation_upload_status",
                    class_="cloud-muted",
                    style="font-size: 12px; margin-top: 8px;",
                ),
                _spashiny_globals.ui.output_ui("metabolite_annotation_current_input"),
                _spashiny_globals.ui.tags.script(
                    """
                (function () {
                  function bindMetaboliteAnnotationUpload() {
                    var input = document.querySelector("input[data-spashiny-metabolite-annotation-upload='1']");
                    var status = document.getElementById("metabolite_annotation_upload_status");
                    if (!input || !status || input.dataset.spashinyBound === "1") return;
                    input.dataset.spashinyBound = "1";
                    function show(message) { status.textContent = message; }
                    function emit(payload) {
                      if (window.Shiny && typeof window.Shiny.setInputValue === "function") {
                        payload.nonce = Date.now();
                        window.Shiny.setInputValue("metabolite_annotation_canonical_upload", payload, {priority: "event"});
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
                  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bindMetaboliteAnnotationUpload);
                  else bindMetaboliteAnnotationUpload();
                })();
                """
                ),
            ),
            _spashiny_globals.ui.input_select(
                "metabolite_annotation_adduct",
                "Adduct",
                choices={
                    "add:H": "[M+H]+ (add H)",
                    "add:Na": "[M+Na]+ (add Na)",
                    "add:K": "[M+K]+ (add K)",
                    "sub:H": "[M-H]- (sub H)",
                    "sub:Cl": "[M+Cl]- (sub Cl)",
                },
                selected="add:H",
            ),
            _spashiny_globals.ui.input_numeric(
                "metabolite_annotation_tolerance_ppm",
                "Mass tolerance (ppm)",
                value=5,
                min=0.1,
                max=100,
                step=0.1,
            ),
            _spashiny_globals.ui.layout_columns(
                _spashiny_globals.ui.input_action_button(
                    "run_metabolite_annotation_csv",
                    "Run SpatialMETA Annotation",
                    class_="btn btn-primary w-100",
                ),
                _spashiny_globals.ui.input_action_button(
                    "run_metabolite_annotation_y7t",
                    "Run Y7_T SM Example",
                    class_="btn btn-secondary w-100",
                ),
                col_widths=(6, 6),
            ),
            _spashiny_globals.ui.div(
                _spashiny_globals.ui.output_text("metabolite_annotation_status"),
                class_="cloud-muted",
                style="margin-top: 10px;",
            ),
            _spashiny_globals.ui.output_ui("metabolite_annotation_job_results"),
            class_="apple-card",
        ),
        class_="apple-card",
    )


def ui(_spashiny_ctx, module):
    if module == "SpatialMETA Metabolite Annotation":
        return _view_1(_spashiny_ctx, module)
    raise ValueError("Unknown feature page: metabolite_annotation")
