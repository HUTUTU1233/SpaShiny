# Actual feature UI extracted from production. Feature: st_import.
from spashiny._shared import runtime_globals as _spashiny_globals


def _view_1(_spashiny_ctx, module):
    return _spashiny_ctx.ui.page_fluid(
        _spashiny_ctx.ui.HTML(_spashiny_ctx.st_apple_style),
        _spashiny_ctx.ui.h2("ST Data Processing", class_="st-header"),
        _spashiny_ctx.ui.div(
            _spashiny_ctx.ui.h4("Module Overview", style="margin-bottom: 12px;"),
            _spashiny_ctx.ui.p(
                "This module supports loading spatial transcriptomics (ST) data generated from the 10x Genomics Visium platform and processed in a Scanpy-compatible format.",
                style="margin-bottom: 14px;",
            ),
            _spashiny_ctx.ui.tags.ul(
                _spashiny_ctx.ui.tags.li(
                    "Please upload a complete Visium output folder compressed as a .zip archive."
                ),
                _spashiny_ctx.ui.tags.li(
                    "The archive should include the gene expression matrix and the spatial/ image folder."
                ),
                _spashiny_ctx.ui.tags.li(
                    "Accepted expression input may include either filtered_feature_bc_matrix.h5 or the filtered_feature_bc_matrix/ directory."
                ),
                _spashiny_ctx.ui.tags.li(
                    "The filtered_feature_bc_matrix/ directory typically contains: barcodes.tsv.gz, features.tsv.gz, and matrix.mtx.gz."
                ),
                _spashiny_ctx.ui.tags.li(
                    "The spatial/ folder typically contains: tissue_hires_image.png, tissue_lowres_image.png, scalefactors_json.json, and tissue_positions_list.csv (or tissue_positions.csv)."
                ),
                _spashiny_ctx.ui.tags.li(
                    "Uploading only a single expression file or image file is not sufficient for proper Scanpy loading."
                ),
                _spashiny_ctx.ui.tags.li(
                    "After upload, click tart Processingto construct the AnnData object and initialize downstream analysis."
                ),
            ),
            class_="control-panel",
            style="margin-bottom: 20px;",
        ),
        _spashiny_ctx.ui.accordion(
            _spashiny_ctx.ui.accordion_panel(
                "Core Processing Panel",
                _spashiny_ctx.ui.row(
                    _spashiny_ctx.ui.column(
                        4,
                        _spashiny_ctx.ui.div(
                            _spashiny_ctx.ui.div("Data Upload", class_="control-label"),
                            _spashiny_ctx.ui.input_file(
                                "st_files",
                                "Upload ST Data (.zip or .h5ad)",
                                multiple=False,
                                accept=[".zip", ".h5ad"],
                                placeholder="Drag a Visium outs .zip or raw h5ad here",
                            ),
                            _spashiny_ctx.ui.div(
                                "Format: upload either one complete 10x Visium folder compressed as .zip, or one raw ST .h5ad file. The built-in raw Visium example is available under user_data/input/sample-1_Y7_T/ST/ST_raw and can also be packaged as ST_raw.zip. For a Visium zip, required contents are spatial/ plus filtered_feature_bc_matrix.h5 or filtered_feature_bc_matrix/.",
                                style="font-size: 12px; color: #6e6e73; line-height: 1.55; margin: 6px 0 14px 0;",
                            ),
                            _spashiny_ctx.ui.input_action_button(
                                "load_example_st",
                                "Load Example ST (Y7_T)",
                                class_=_spashiny_globals.cloud_example_button_class(
                                    "btn-apple btn-apple-secondary"
                                ),
                                **_spashiny_globals.cloud_example_action_attrs(
                                    "y7-st-upload-example", "st_upload", "st-upload-example-status"
                                ),
                            ),
                            _spashiny_ctx.ui.div(
                                _spashiny_globals.example_source_note(
                                    "Example source: user_data/input/sample-1_Y7_T/ST/ST_raw, with h5ad fallback at ST/adata_ST_Y7_T_raw.h5ad",
                                    "Cloud example: Y7_T ST raw Visium zip is bound to this session on click.",
                                ),
                                style="font-size: 12px; color: #6e6e73; margin-bottom: 12px;",
                            ),
                            *(
                                [_spashiny_globals.cloud_example_status("st-upload-example-status")]
                                if _spashiny_globals.SPASHINY_WEB_PLATFORM
                                else []
                            ),
                            _spashiny_ctx.ui.hr(
                                style="border-top: 1px solid #e5e5e5; margin: 24px 0;"
                            ),
                            _spashiny_ctx.ui.input_action_button(
                                "process_st",
                                "Start Processing",
                                class_="btn-apple btn-apple-primary",
                            ),
                            _spashiny_ctx.ui.input_action_button(
                                "save_st",
                                "Save Current Data",
                                class_="btn-apple btn-apple-secondary",
                            ),
                            _spashiny_ctx.ui.download_button(
                                "download_st",
                                "Export H5AD Result",
                                class_="btn-apple btn-apple-secondary",
                            ),
                            _spashiny_ctx.ui.div(
                                _spashiny_ctx.ui.output_text("process_status_st"),
                                style="margin-top: 15px; font-weight: 500; color: #007aff;",
                            ),
                            class_="control-panel",
                        ),
                    ),
                    _spashiny_ctx.ui.column(
                        8,
                        _spashiny_ctx.ui.div(
                            _spashiny_ctx.ui.div("System Run Log", class_="control-label"),
                            _spashiny_ctx.ui.div(
                                _spashiny_ctx.ui.output_text_verbatim("console_output"),
                                class_="console-window",
                            ),
                            class_="control-panel",
                        ),
                    ),
                ),
            ),
            id="st_accordion",
        ),
    )


def ui(_spashiny_ctx, module):
    if module == "ST":
        return _view_1(_spashiny_ctx, module)
    raise ValueError("Unknown feature page: st_import")
