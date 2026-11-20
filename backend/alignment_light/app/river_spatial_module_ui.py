from shiny import ui
from plot_color_tools import plot_output_with_palette


RIVER_MODULE_CSS = """
<style>
.river-shell {
    padding: 12px 8px 32px 8px;
    max-width: 1280px;
    margin: 0 auto;
}

.river-hero {
    background: linear-gradient(135deg, rgba(255,255,255,0.96), rgba(246,248,252,0.92));
    border: 1px solid rgba(0,0,0,0.05);
    border-radius: 28px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.05);
    padding: 28px 30px;
    margin-bottom: 22px;
}

.river-title {
    font-size: 2rem;
    font-weight: 700;
    color: #1d1d1f;
    margin: 0 0 10px 0;
    letter-spacing: -0.02em;
}

.river-subtitle {
    color: #6e6e73;
    font-size: 0.98rem;
    line-height: 1.7;
    margin: 0;
}

.river-stack {
    display: flex;
    flex-direction: column;
    gap: 18px;
}

.river-card {
    background: rgba(255,255,255,0.94);
    border: 1px solid rgba(0,0,0,0.05);
    border-radius: 24px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.04);
    padding: 22px;
    width: 100%;
}

.river-card h4 {
    font-size: 1.08rem;
    font-weight: 700;
    margin-bottom: 16px;
    color: #1d1d1f;
}

.river-note {
    background: rgba(0,113,227,0.06);
    border: 1px solid rgba(0,113,227,0.08);
    color: #24456b;
    border-radius: 18px;
    padding: 14px 16px;
    line-height: 1.7;
    font-size: 0.94rem;
    margin-bottom: 16px;
}

.river-status {
    background: #f5f5f7;
    border-radius: 18px;
    padding: 14px 16px;
    line-height: 1.7;
    white-space: pre-wrap;
    border: 1px solid #e5e5ea;
}

.river-preview,
.river-log {
    background: #ffffff;
    border: 1px solid #e5e5ea;
    border-radius: 18px;
    overflow-y: auto;
    padding: 16px;
    font-family: SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 12.5px;
    line-height: 1.6;
    white-space: pre-wrap;
}

.river-preview {
    min-height: 240px;
    max-height: 240px;
}

.river-log {
    min-height: 320px;
    max-height: 320px;
}

.river-pan-hint {
    color: #6e6e73;
    font-size: 0.92rem;
    margin-bottom: 10px;
    line-height: 1.6;
}

.river-pan-stage {
    width: 100%;
    height: 860px;
    overflow: auto;
    background: #ffffff;
    border: 1px solid #e5e5ea;
    border-radius: 20px;
    padding: 14px;
    cursor: grab;
    user-select: none;
    -webkit-user-select: none;
    position: relative;
    scroll-behavior: auto;
}

.river-pan-stage.is-dragging {
    cursor: grabbing;
}

.river-pan-stage img {
    display: block;
    max-width: none !important;
    width: auto !important;
    height: auto !important;
    object-fit: unset !important;
    border-radius: 12px;
}

.river-pan-stage .shiny-image-output,
.river-pan-stage > div {
    width: max-content !important;
    max-width: none !important;
}

.river-pan-stage::-webkit-scrollbar {
    width: 10px;
    height: 10px;
}

.river-pan-stage::-webkit-scrollbar-thumb {
    background: #cfcfd6;
    border-radius: 999px;
}

.river-pan-stage::-webkit-scrollbar-track {
    background: #f5f5f7;
    border-radius: 999px;
}

.river-plot-box {
    width: 100%;
    min-height: 440px;
    background: #ffffff;
    border: 1px solid #e5e5ea;
    border-radius: 20px;
    padding: 14px;
    overflow: hidden;
}

.river-plot-box .shiny-plot-output {
    width: 100% !important;
}

.small-muted {
    color: #6e6e73;
    font-size: 0.9rem;
    line-height: 1.6;
    margin-top: 6px;
}

.upload-gap {
    height: 12px;
}

.river-sep {
    border: none;
    border-top: 1px solid #ececf1;
    margin: 18px 0;
}

/* Unified input control size( radio / checkbox / file) */
.river-card .shiny-input-container {
    width: 100%;
    margin-bottom: 14px;
}

.river-card .form-control,
.river-card .form-select,
.river-card input:not([type="radio"]):not([type="checkbox"]):not([type="file"]),
.river-card select,
.river-card textarea {
    width: 100% !important;
    min-height: 48px !important;
    border-radius: 16px !important;
    box-shadow: none !important;
    border: 1px solid #dcdce1 !important;
    padding-left: 14px !important;
    padding-right: 14px !important;
    background: #fff !important;
}

.river-card textarea {
    min-height: 120px !important;
}

/* Unified button size */
.river-card .btn,
.river-card .btn-primary,
.river-card .btn-secondary,
.river-card .btn-success,
.river-card .btn-warning,
.river-card .btn-default {
    width: 100% !important;
    min-height: 48px !important;
    border-radius: 16px !important;
    font-weight: 600 !important;
    margin-bottom: 12px;
}

.river-card .btn:last-child {
    margin-bottom: 0;
}

/* Unified upload control appearance */
.river-card input[type="file"] {
    min-height: 48px !important;
    padding: 10px 12px !important;
    background: #fff !important;
    border: 1px dashed #cfd3dc !important;
    border-radius: 16px !important;
}

/* ===== ST / SM / ST-SM highlight switching ===== */
.river-mode-switch .shiny-options-group {
    display: grid !important;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
    width: 100%;
    margin-top: 10px;
}

.river-mode-switch .radio {
    margin: 0 !important;
    opacity: 0.38;
    transform: scale(0.98);
    transition: all 0.22s ease;
}

.river-mode-switch .radio label {
    display: flex !important;
    align-items: center;
    justify-content: center;
    min-height: 52px;
    width: 100%;
    border-radius: 18px;
    border: 1px solid #dcdce1;
    background: #f5f5f7;
    color: #6e6e73;
    font-weight: 700;
    font-size: 0.96rem;
    cursor: pointer;
    padding: 0 14px;
    transition: all 0.22s ease;
}

.river-mode-switch .radio input[type="radio"] {
    display: none !important;
}

.river-mode-switch .radio.is-active,
.river-mode-switch .radio:has(input[type="radio"]:checked) {
    opacity: 1;
    transform: scale(1);
}

.river-mode-switch .radio.is-active label,
.river-mode-switch .radio:has(input[type="radio"]:checked) label {
    background: linear-gradient(135deg, #0a84ff, #0071e3);
    color: #ffffff;
    border: 1px solid rgba(0,113,227,0.22);
    box-shadow: 0 10px 24px rgba(0,113,227,0.20);
}

.river-mode-switch .radio.is-inactive label {
    background: #f5f5f7;
    color: #8b8b94;
    border: 1px solid #e5e5ea;
}

/* ===== TOP / Feature selection mode ===== */
.river-feature-switch .shiny-options-group {
    display: grid !important;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
    width: 100%;
    margin-top: 10px;
}

.river-feature-switch .radio {
    margin: 0 !important;
}

.river-feature-switch .radio label {
    display: flex !important;
    align-items: center;
    justify-content: center;
    min-height: 50px;
    width: 100%;
    border-radius: 16px;
    border: 1px solid #dcdce1;
    background: #f5f5f7;
    color: #4d4d57;
    font-weight: 700;
    cursor: pointer;
    padding: 0 14px;
    transition: all 0.22s ease;
}

.river-feature-switch .radio input[type="radio"] {
    display: none !important;
}

.river-feature-switch .radio:has(input[type="radio"]:checked) label {
    background: linear-gradient(135deg, rgba(10,132,255,0.12), rgba(0,113,227,0.16));
    color: #0a4d93;
    border: 1px solid rgba(0,113,227,0.20);
}
</style>
"""


RIVER_MODULE_JS = """
<script>
document.addEventListener("DOMContentLoaded", function () {
    function syncRiverModeState() {
        const root = document.getElementById("river-mode-switch");
        if (!root) return;
        const radios = root.querySelectorAll(".radio");
        radios.forEach(function (item) {
            const input = item.querySelector('input[type="radio"]');
            const checked = input && input.checked;
            item.classList.toggle("is-active", checked);
            item.classList.toggle("is-inactive", !checked);
        });
    }

    document.addEventListener("change", function (e) {
        if (e.target && e.target.name === "river_mode") {
            syncRiverModeState();
        }
    });

    setTimeout(syncRiverModeState, 80);
    setTimeout(syncRiverModeState, 300);

    const pan = document.getElementById("river-pan-stage");
    if (pan) {
        let isDown = false;
        let startX = 0;
        let startY = 0;
        let scrollLeft = 0;
        let scrollTop = 0;

        pan.addEventListener("mousedown", function (e) {
            isDown = true;
            pan.classList.add("is-dragging");
            startX = e.pageX - pan.offsetLeft;
            startY = e.pageY - pan.offsetTop;
            scrollLeft = pan.scrollLeft;
            scrollTop = pan.scrollTop;
        });

        window.addEventListener("mouseup", function () {
            isDown = false;
            pan.classList.remove("is-dragging");
        });

        window.addEventListener("mousemove", function (e) {
            if (!isDown) return;
            e.preventDefault();
            const x = e.pageX - pan.offsetLeft;
            const y = e.pageY - pan.offsetTop;
            const walkX = x - startX;
            const walkY = y - startY;
            pan.scrollLeft = scrollLeft - walkX;
            pan.scrollTop = scrollTop - walkY;
        });

        pan.addEventListener("mouseleave", function () {
            isDown = false;
            pan.classList.remove("is-dragging");
        });
    }
});
</script>
"""


def river_module_ui():
    return ui.page_fluid(
        ui.HTML(RIVER_MODULE_CSS),
        ui.HTML(RIVER_MODULE_JS),

        ui.div(
            {"class": "river-shell"},

            ui.div(
                {"class": "river-hero"},
                ui.h2("River Temporal / Spatial Ranking Module", class_="river-title"),
                ui.p(
                    "Web upload version: upload sample-level .h5ad or .h5 files directly, and optionally upload CSV annotation files. "
                    "The server will match data files and CSV files by filename, run the River workflow, "
                    "and generate a combined figure with sample labels, annotation legend, ranked features, "
                    "feature-level plotting, and PDF export.",
                    class_="river-subtitle"
                ),
            ),

            ui.div(
                {"class": "river-stack"},

                # =========================
                # 1. Analysis Mode
                # =========================
                ui.div(
                    {"class": "river-card"},
                    ui.h4("1. Analysis Mode and Environment"),

                    ui.div(
                        {"class": "river-mode-switch", "id": "river-mode-switch"},
                        ui.input_radio_buttons(
                            "river_mode",
                            "Select analysis mode",
                            {
                                "ST": "ST",
                                "SM": "SM",
                                "ST-SM": "ST-SM"
                            },
                            selected="ST",
                            inline=True
                        ),
                    ),

                    ui.input_text(
                        "river_python",
                        "Local Python path for River (only used when SSH is disconnected)",
                        value="",
                        placeholder="Leave empty to use the current desktop Python environment"
                    ),

                    ui.div(
                        "When SSH is connected, River uses the remote environment selected on the SSH Connection page. "
                        "This local path is only used in local mode.",
                        class_="small-muted"
                    ),
                ),

                # =========================
                # 2. Upload
                # =========================
                ui.div(
                    {"class": "river-card"},
                    ui.h4("2. Upload .h5ad / .h5 Files and CSV Annotations"),

                    ui.input_file(
                        "river_h5ad_files",
                        "Upload .h5ad / .h5 files",
                        multiple=True,
                        accept=[".h5ad", ".h5"],
                        placeholder="Select one or more .h5ad or .h5 files"
                    ),

                    ui.div(class_="upload-gap"),

                    ui.input_file(
                        "river_csv_files",
                        "Upload CSV annotation files",
                        multiple=True,
                        accept=[".csv"],
                        placeholder="Select one or more CSV files"
                    ),

                    ui.div(
                        "Please upload multiple sample-level .h5ad or .h5 files and optional matching CSV annotation files. "
                        "Files will be matched by filename stem whenever possible.",
                        class_="small-muted"
                    ),

                    ui.hr(class_="river-sep"),

                    ui.input_numeric(
                        "river_subsample",
                        "Unified subsampling size",
                        value=6000,
                        min=500,
                        max=50000,
                        step=500
                    ),

                    ui.input_numeric(
                        "river_epochs",
                        "River training epochs",
                        value=100,
                        min=10,
                        max=1000,
                        step=10
                    ),

                    ui.input_text(
                        "river_sample_names",
                        "Sample name / condition order (optional, comma-separated)",
                        value="",
                        placeholder="Example: C1, MI1D, MI3D, MI7D"
                    ),

                    ui.div(
                        "If provided, these names will be assigned to uploaded files in order. "
                        "If left empty, the system will use filenames as sample labels.",
                        class_="small-muted"
                    ),

                    ui.hr(class_="river-sep"),

                    ui.input_action_button(
                        "river_preview_btn",
                        "Preview files",
                        class_="btn btn-secondary"
                    ),

                    ui.input_action_button(
                        "river_run_btn",
                        "Run analysis",
                        class_="btn btn-primary"
                    ),
                ),

                # =========================
                # 3. Export
                # =========================
                ui.div(
                    {"class": "river-card"},
                    ui.h4("3. Export Basic Results"),

                    ui.download_button(
                        "river_download_pdf",
                        "Export combined PDF",
                        class_="btn btn-success"
                    ),

                    ui.download_button(
                        "river_download_rank",
                        "Download River ranking (.npy)",
                        class_="btn btn-secondary"
                    ),

                    ui.download_button(
                        "river_download_summary",
                        "Download run summary (.json)",
                        class_="btn btn-secondary"
                    ),
                ),

                # =========================
                # 4. Guide + Status
                # =========================
                ui.div(
                    {"class": "river-card"},
                    ui.h4("H5AD / H5 / CSV Upload Guide"),

                    ui.div(
                        {"class": "river-note"},
                        ui.HTML(
                            "<b>Input style:</b> upload one or more <code>.h5ad</code> or <code>.h5</code> files, one per sample. "
                            "Each file should ideally contain spatial information in <code>obsm['spatial']</code>. "
                            "If spatial coordinates are not found there, the runner will try to infer them from "
                            "common coordinate columns in <code>obs</code>.<br><br>"

                            "<b>CSV annotations:</b> optional but recommended. "
                            "Please keep one CSV per sample, and let the CSV filename match the data filename stem as much as possible.<br>"
                            "Recommended naming:<br>"
                            "<code>D1.h5ad <-> D1.csv</code><br>"
                            "<code>D3.h5ad <-> D3.csv</code><br>"
                            "<code>D7.h5 <-> D7.csv</code><br><br>"

                            "<b>Matching rule:</b> the app matches files mainly by filename stem. "
                            "If a CSV is missing, the sample can still run, but its annotation will be set to "
                            "<code>Unknown</code>.<br><br>"

                            "<b>Sample name / condition order:</b> if you fill the optional text box, those names will be assigned in the same order as the uploaded data files. "
                            "Otherwise, filenames will be used directly."
                        )
                    ),

                    ui.div(
                        ui.output_text_verbatim("river_status"),
                        class_="river-status"
                    ),
                ),

                # =========================
                # 5. File Preview
                # =========================
                ui.div(
                    {"class": "river-card"},
                    ui.h4("Uploaded File Preview"),
                    ui.div(
                        ui.output_text_verbatim("river_folder_preview"),
                        class_="river-preview"
                    ),
                ),

                # =========================
                # 6. Run Log
                # =========================
                ui.div(
                    {"class": "river-card"},
                    ui.h4("Run Log"),
                    ui.div(
                        ui.output_text_verbatim("river_console_output"),
                        class_="river-log"
                    ),
                ),

                # =========================
                # 7. Result Figure
                # =========================
                ui.div(
                    {"class": "river-card"},
                    ui.h4("Result Figure (image + labels + legend in one figure)"),
                    ui.div(
                        "Original-size display. Drag inside the panel to move horizontally and vertically.",
                        class_="river-pan-hint"
                    ),
                    ui.div(
                        {"class": "river-pan-stage", "id": "river-pan-stage"},
                        ui.output_image("river_result_image")
                    ),
                ),

                # =========================
                # 8. Feature Explorer
                # =========================
                ui.div(
                    {"class": "river-card"},
                    ui.h4("Feature Explorer"),

                    ui.div(
                        {"class": "river-note"},
                        ui.HTML(
                            "After River finishes, you can either choose a <b>TOP-ranked feature</b> "
                            "or directly search a <b>feature name</b>, then click "
                            "<b>Generate Feature Plot</b>. The current plot can be exported as PDF directly."
                        )
                    ),

                    ui.div(
                        {"class": "river-feature-switch"},
                        ui.input_radio_buttons(
                            "river_feature_mode",
                            "Feature selection mode",
                            {
                                "top": "TOP rank",
                                "name": "Feature name"
                            },
                            selected="top",
                            inline=True
                        ),
                    ),

                    ui.panel_conditional(
                        "input.river_feature_mode === 'top'",
                        ui.input_numeric(
                            "river_top_index",
                            "TOP index",
                            value=1,
                            min=1,
                            step=1
                        )
                    ),

                    ui.panel_conditional(
                        "input.river_feature_mode === 'name'",
                        ui.output_ui("river_feature_name_ui")
                    ),

                    ui.input_select(
                        "river_feature_cmap",
                        "Colormap",
                        {
                            "Balance_20": "Balance_20",
                            "Delta_20": "Delta_20",
                            "Viridis": "Viridis",
                            "Magma": "Magma",
                            "BlueWhiteRed": "Blue-White-Red"
                        },
                        selected="Balance_20"
                    ),

                    ui.input_action_button(
                        "river_generate_feature_btn",
                        "Generate Feature Plot",
                        class_="btn btn-primary"
                    ),

                    ui.download_button(
                        "river_download_feature_pdf",
                        "Download Current Feature PDF",
                        class_="btn btn-success"
                    ),

                    ui.div(
                        "TOP mode uses the River ranking order. Feature-name mode searches all plottable features in the generated plot-ready AnnData object.",
                        class_="small-muted"
                    ),
                ),

                # =========================
                # 9. Feature Plot
                # =========================
                ui.div(
                    {"class": "river-card"},
                    ui.h4("Feature Plot"),
                    ui.div(
                        "Select the feature above, click Generate Feature Plot, then export the current figure as PDF if needed.",
                        class_="river-pan-hint"
                    ),
                    ui.div(
                        {"class": "river-plot-box"},
                        plot_output_with_palette("river_feature_plot", height="420px", width="100%")
                    ),
                ),
            ),
        )
    )
