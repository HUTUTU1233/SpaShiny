# Actual feature UI extracted from production. Feature: sm_import.
from spashiny._shared import runtime_globals as _spashiny_globals


def _view_1(_spashiny_ctx, module):
    return _spashiny_ctx.ui.page_fluid(
        _spashiny_ctx.ui.tags.style(
            """
                    body {
                        background-color: #f5f5f7;
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto;
                    }

                    .card-box {
                        background: white;
                        border-radius: 12px;
                        padding: 20px;
                        border: 1px solid #e5e5e7;
                        box-shadow: 0 2px 6px rgba(0,0,0,0.04);
                    }

                    h2 {
                        font-weight: 600;
                        margin-bottom: 20px;
                    }

                    .btn-primary {
                        background-color: #007aff;
                        border: none;
                        border-radius: 8px;
                    }

                    .btn-primary:disabled {
                        background-color: #c7c7cc;
                    }

                    .btn-success {
                        background-color: #34c759;
                        border: none;
                        border-radius: 8px;
                    }

                    .log-box {
                        height: 400px;
                        overflow-y: auto;
                        background: #fafafa;
                        border-radius: 8px;
                        padding: 10px;
                        border: 1px solid #e5e5e7;
                        font-size: 13px;
                    }
                """
        ),
        _spashiny_ctx.ui.h2("SM Data Preprocessing"),
        _spashiny_ctx.ui.card(
            _spashiny_ctx.ui.h4("Module Overview"),
            _spashiny_ctx.ui.p(
                "This module is designed for preprocessing spatial metabolomics (SM) data and supports both ImzML / IBD input and CSV-format input."
            ),
            _spashiny_ctx.ui.tags.ul(
                _spashiny_ctx.ui.tags.li(
                    "Please first select the correct input format before uploading any files."
                ),
                _spashiny_ctx.ui.tags.li(
                    "This selection is required because the system will initialize the appropriate temporary workspace based on the chosen file type."
                ),
                _spashiny_ctx.ui.tags.li(
                    "For ImzML data, upload both the .imzML file and the corresponding .ibd file together."
                ),
                _spashiny_ctx.ui.tags.li(
                    "For CSV-format input, upload the required CSV file(s) according to your dataset structure."
                ),
                _spashiny_ctx.ui.tags.li(
                    "After upload, click tart Processingto construct the processed AnnData object."
                ),
                _spashiny_ctx.ui.tags.li(
                    "The resulting data can then be saved locally or downloaded as an H5AD file for downstream analysis."
                ),
                _spashiny_ctx.ui.tags.li(
                    "After export, it will be in raw file format. Please rename it promptly."
                ),
            ),
            class_="card-box",
        ),
        _spashiny_ctx.ui.accordion(
            _spashiny_ctx.ui.accordion_panel(
                "SM Data Upload and Processing",
                _spashiny_ctx.ui.row(
                    _spashiny_ctx.ui.column(
                        4,
                        _spashiny_ctx.ui.card(
                            _spashiny_ctx.ui.h4("Upload and Processing"),
                            _spashiny_ctx.ui.input_radio_buttons(
                                "data_type",
                                "Select Data Type:",
                                {"ImzML": "ImzML / ibd", "CSV": "CSV Format"},
                                selected="ImzML",
                            ),
                            _spashiny_ctx.ui.output_ui("file_inputs"),
                            _spashiny_ctx.ui.input_action_button(
                                "load_example_sm",
                                "Load Example SM (Y7_T)",
                                class_=_spashiny_globals.cloud_example_button_class(
                                    "btn btn-secondary"
                                ),
                                **_spashiny_globals.cloud_example_action_attrs(
                                    "y7-sm-upload-imzml-example",
                                    "sm_upload",
                                    "sm-upload-example-status",
                                ),
                            ),
                            _spashiny_ctx.ui.div(
                                _spashiny_globals.example_source_note(
                                    "Example source: user_data/input/sample-1_Y7_T/SM",
                                    "Cloud example: Y7_T positive/negative imzML and ibd pairs are bound to this session on click.",
                                ),
                                style="font-size: 12px; color: #6e6e73; margin-top: 6px;",
                            ),
                            *(
                                [_spashiny_globals.cloud_example_status("sm-upload-example-status")]
                                if _spashiny_globals.SPASHINY_WEB_PLATFORM
                                else []
                            ),
                            _spashiny_ctx.ui.hr(),
                            _spashiny_ctx.ui.input_action_button(
                                "process", "Start Processing", class_="btn btn-primary"
                            ),
                            _spashiny_ctx.ui.input_action_button(
                                "save_h5ad", "Save Merged Data", class_="btn btn-success"
                            ),
                            _spashiny_ctx.ui.download_button("download_h5ad", "Download H5AD File"),
                            _spashiny_ctx.ui.hr(),
                            _spashiny_ctx.ui.output_text("process_status"),
                            class_="card-box",
                        ),
                    ),
                    _spashiny_ctx.ui.column(
                        8,
                        _spashiny_ctx.ui.div(
                            _spashiny_ctx.ui.h4("Run Log"),
                            _spashiny_ctx.ui.div(
                                _spashiny_ctx.ui.output_text_verbatim("console_output"),
                                class_="log-box",
                            ),
                            class_="card-box",
                        ),
                    ),
                ),
            )
        ),
        _spashiny_ctx.ui.tags.script(
            """
                    document.addEventListener('DOMContentLoaded', function() {
                        const btn = document.getElementById('process');

                        if (btn) {
                            btn.addEventListener('click', function() {
                                btn.disabled = true;
                                btn.innerText = 'Processing...';
                            });
                        }
                    });
                """
        ),
    )


def ui(_spashiny_ctx, module):
    if module == "SM":
        return _view_1(_spashiny_ctx, module)
    raise ValueError("Unknown feature page: sm_import")
