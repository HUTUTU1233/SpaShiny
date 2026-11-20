# Feature sm_tic_roi: original callable implementation extracted from sm_tic_roi_module.py.
from spashiny._shared.feature_support import sm_tic_roi_module as _feature_shared
from spashiny._shared import runtime_globals as _spashiny_globals


def _view_1(_spashiny_ctx, module):
    return _spashiny_globals.sm_tic_roi_module_ui()


def ui(_spashiny_ctx, module):
    if module == "SM TIC ROI":
        return _view_1(_spashiny_ctx, module)
    raise ValueError("Unknown feature page: sm_tic_roi")


def sm_tic_roi_module_ui():
    return _feature_shared.ui.div(
        _feature_shared.ui.h2("SM TIC / ROI → SpatialMETA CSV / POS–NEG H5AD"),
        _feature_shared.ui.p(
            "Upload imzML/IBD pairs, inspect TIC, select ROI pixels and export SpatialMETA-readable spectrum CSVs. Merge POS/NEG in this page, or upload two existing spectrum CSVs below. Original input files are never overwritten."
        ),
        _feature_shared.ui.div(
            _feature_shared.ui.h4("1. Upload paired MSI files"),
            _feature_shared.ui.tags.input(
                type="file",
                multiple=True,
                accept=".imzML,.imzml,.ibd,.IBD",
                class_="form-control",
                **{"data-sm-tic-roi-upload": "1"},
            ),
            _feature_shared.ui.p(
                "Select both files for each dataset (same filename stem). Up to 8 datasets. POS and NEG may be uploaded together.",
                class_="cloud-muted",
            ),
            _feature_shared.ui.tags.div(
                "No files uploaded yet.", id="sm_tic_roi_upload_status", role="status"
            ),
            _feature_shared.ui.input_action_button(
                "sm_tic_roi_preview", "Compute TIC preview", class_="btn btn-primary"
            ),
            class_="apple-card",
        ),
        _feature_shared.ui.div(
            _feature_shared.ui.h4("2. Select ROI pixels"),
            _feature_shared.ui.p(
                "Click a pixel to toggle it. Use Box select or Lasso select to add/remove pixels. The map includes all pixels; it is not subsampled. Multi-plane inputs must be exported one z plane at a time."
            ),
            _feature_shared.ui.div(
                _feature_shared.ui.tags.label(
                    "Dataset ",
                    _feature_shared.ui.tags.select(
                        id="sm_tic_roi_dataset", class_="form-select", style="min-width:220px;"
                    ),
                ),
                _feature_shared.ui.tags.label(
                    "Z plane ",
                    _feature_shared.ui.tags.select(id="sm_tic_roi_z", class_="form-select"),
                ),
                _feature_shared.ui.tags.label(
                    "Selection mode ",
                    _feature_shared.ui.tags.select(
                        _feature_shared.ui.tags.option("Add", value="add"),
                        _feature_shared.ui.tags.option("Remove", value="remove"),
                        id="sm_tic_roi_mode",
                        class_="form-select",
                    ),
                ),
                _feature_shared.ui.tags.button(
                    "Clear current ROI",
                    type="button",
                    id="sm_tic_roi_clear",
                    class_="btn btn-outline-danger",
                ),
                style="display:flex;gap:14px;align-items:flex-end;flex-wrap:wrap;",
            ),
            _feature_shared.ui.tags.div(
                "Compute a TIC preview first.",
                id="sm_tic_roi_selection_status",
                role="status",
                style="margin:12px 0;",
            ),
            _feature_shared.ui.tags.div(
                id="sm_tic_roi_plot", style="width:100%;height:650px;min-height:400px;"
            ),
            class_="apple-card",
            style="margin-top:16px;",
        ),
        _feature_shared.ui.div(
            _feature_shared.ui.h4("3. Export spectra"),
            _feature_shared.ui.input_checkbox(
                "sm_tic_roi_export_all",
                "Export all pixels in each chosen z plane (ignore ROI selection)",
                value=False,
            ),
            _feature_shared.ui.input_checkbox(
                "sm_tic_roi_match",
                "POS/NEG or matched datasets: export only exact shared ROI coordinates, in identical order",
                value=False,
            ),
            _feature_shared.ui.p(
                "Shared-coordinate matching is not registration. If the datasets have no common coordinates, export is stopped; coordinates are never rounded or altered."
            ),
            _feature_shared.ui.input_select(
                "sm_tic_roi_duplicate_policy",
                "Repeated native m/z values",
                choices={
                    "error": "Strict: stop if a pixel contains duplicate m/z (default)",
                    "sum_exact": "Explicitly sum intensities at exactly equal m/z (preserves TIC)",
                },
                selected="error",
            ),
            _feature_shared.ui.input_select(
                "sm_tic_roi_axis_mode",
                "Spectrum feature axis",
                choices={
                    "exact": "Exact native m/z union — no binning (default)",
                    "fixed_da": "Explicit fixed-width Da bins — sum intensities within each bin",
                },
                selected="exact",
            ),
            _feature_shared.ui.panel_conditional(
                "input.sm_tic_roi_axis_mode === 'fixed_da'",
                _feature_shared.ui.input_numeric(
                    "sm_tic_roi_bin_width",
                    "Bin width (Da; choose for your experiment)",
                    value=0.01,
                    min=1e-06,
                    step=0.001,
                ),
                _feature_shared.ui.p(
                    "Binning changes the feature axis: origin 0 Da; intervals [k×width,(k+1)×width); column labels are bin centers. It preserves summed intensity but is not peak picking, ppm matching, normalization or registration. Parameters are recorded in the summary.",
                    class_="text-warning",
                ),
            ),
            _feature_shared.ui.input_checkbox(
                "sm_tic_roi_merge_now",
                "Also merge the exported POS/NEG CSVs into H5AD in this job",
                value=False,
            ),
            _feature_shared.ui.panel_conditional(
                "input.sm_tic_roi_merge_now",
                _feature_shared.ui.input_select(
                    "sm_tic_roi_pos_dataset",
                    "Positive-ion (POS) dataset",
                    choices={"": "Compute a preview and select POS"},
                ),
                _feature_shared.ui.input_select(
                    "sm_tic_roi_neg_dataset",
                    "Negative-ion (NEG) dataset",
                    choices={"": "Compute a preview and select NEG"},
                ),
                _feature_shared.ui.p(
                    "Requires exactly two datasets. Roles must agree with available imzML polarity metadata. The official reader removes zero-TIC pixels; merge then uses exact shared coordinates in POS order."
                ),
            ),
            _feature_shared.ui.input_action_button(
                "sm_tic_roi_export", "Export SpatialMETA CSV", class_="btn btn-success"
            ),
            _feature_shared.ui.p(
                "Spectrum CSV: x,y,<numeric m/z>… . Exact mode retains native masses; aggregation only follows your explicit options above. TIC/pixel IDs and ROI masks are separate CSVs; unmeasured m/z entries are 0."
            ),
            _feature_shared.ui.p(
                "Limits: 250,000 pixels/dataset for interactive preview; 100,000 m/z columns and 50 million intensity cells/dataset per export. SpatialMETA removes zero-total-intensity pixels, so match POS/NEG coordinates after loading both CSVs."
            ),
            _feature_shared.ui.output_text("sm_tic_roi_status"),
            _feature_shared.ui.output_ui("sm_tic_roi_jobs"),
            class_="apple-card",
            style="margin-top:16px;",
        ),
        _feature_shared.ui.div(
            _feature_shared.ui.h4("4. Merge POS / NEG spectrum CSVs → H5AD"),
            _feature_shared.ui.p(
                "Already have CSVs? Upload them here, including CSVs downloaded from step 3. Choose one POS and one NEG; filenames must differ. Each CSV must contain x,y followed only by numeric m/z intensity columns."
            ),
            _feature_shared.ui.tags.label(
                "POS spectrum CSV",
                _feature_shared.ui.tags.input(
                    type="file",
                    accept=".csv",
                    class_="form-control",
                    **{"data-sm-pos-neg-csv": "pos"},
                ),
            ),
            _feature_shared.ui.tags.div(
                "No POS CSV uploaded.", id="sm_pos_neg_pos_upload_status", role="status"
            ),
            _feature_shared.ui.tags.label(
                "NEG spectrum CSV",
                _feature_shared.ui.tags.input(
                    type="file",
                    accept=".csv",
                    class_="form-control",
                    **{"data-sm-pos-neg-csv": "neg"},
                ),
            ),
            _feature_shared.ui.tags.div(
                "No NEG CSV uploaded.", id="sm_pos_neg_neg_upload_status", role="status"
            ),
            _feature_shared.ui.p(
                "Only exact shared XY coordinates are merged. Duplicate coordinates are rejected; inputs without shared positive-intensity pixels must be registered first. No normalization or coordinate rounding. The saved H5AD is reloaded and checked before publishing."
            ),
            _feature_shared.ui.input_action_button(
                "sm_pos_neg_merge", "Merge with SpatialMETA → H5AD", class_="btn btn-primary"
            ),
            _feature_shared.ui.output_text("sm_pos_neg_status"),
            class_="apple-card",
            style="margin-top:16px;",
        ),
        _feature_shared.ui.tags.script(src="/js/sm_tic_roi.js?v=20261014-1"),
    )
