# Feature help: original callable implementation extracted from help_tutorial.py.
from spashiny._shared.feature_support import help_tutorial as _feature_shared
from spashiny._shared import runtime_globals as _spashiny_globals


def _view_1(_spashiny_ctx, module):
    return _spashiny_globals.help_tutorial_ui()


def ui(_spashiny_ctx, module):
    if module == "Help & Tutorial":
        return _view_1(_spashiny_ctx, module)
    raise ValueError("Unknown feature page: help")


def help_tutorial_ui():
    """Render the standalone public Help & Tutorial page."""
    video_url = (_feature_shared.os.environ.get("VIDEO_TUTORIAL_URL") or "").strip()
    video_section = ()
    if video_url:
        video_section = (
            _feature_shared._card(
                "Video tutorial",
                _feature_shared.ui.tags.p(
                    "A recorded walkthrough of the validated Y7_T workflow is available in a separate tab. Video playback never starts automatically."
                ),
                _feature_shared.ui.tags.a(
                    "Open video tutorial",
                    href=video_url,
                    target="_blank",
                    rel="noopener noreferrer",
                    class_="btn btn-outline-primary",
                ),
                anchor="video-tutorial",
            ),
        )
    return _feature_shared.ui.page_fluid(
        _feature_shared.ui.tags.style(
            """
            .help-shell { max-width:1420px; margin:0 auto; padding:28px 18px 60px; color:#1d1d1f; }
            .help-layout { display:grid; grid-template-columns:minmax(210px,250px) minmax(0,1fr); gap:24px; align-items:start; }
            .help-toc { position:sticky; top:82px; background:#fff; border:1px solid #e8edf4; border-radius:16px; padding:16px; box-shadow:0 7px 22px rgba(15,23,42,.05); }
            .help-toc-title { font-size:.84rem; color:#52616f; font-weight:700; letter-spacing:.04em; text-transform:uppercase; margin:0 0 8px; }
            .help-toc a { display:block; color:#245ea9; text-decoration:none; padding:6px 5px; border-radius:6px; font-size:.94rem; }
            .help-toc a:hover,.help-toc a:focus { background:#eef6ff; color:#133f73; }
            .help-hero { background:linear-gradient(135deg,#fff 0%,#f2f8ff 100%); border:1px solid #dceafa; border-radius:22px; padding:32px; margin-bottom:20px; box-shadow:0 10px 30px rgba(15,23,42,.06); }
            .help-eyebrow { color:#2764a7; font-weight:700; font-size:.9rem; letter-spacing:.06em; text-transform:uppercase; }
            .help-title { font-size:clamp(2rem,4vw,3.1rem); margin:8px 0 12px; line-height:1.12; }
            .help-lead { color:#425466; font-size:1.08rem; line-height:1.7; max-width:960px; }
            .help-card { scroll-margin-top:86px; background:#fff; border:1px solid #e7edf3; border-radius:18px; margin:18px 0; padding:25px; box-shadow:0 6px 20px rgba(15,23,42,.04); }
            .help-section-title { font-size:1.55rem; margin:0 0 14px; }
            .help-workflow { display:grid; grid-template-columns:repeat(4,minmax(130px,1fr)); gap:10px; margin:18px 0 4px; }
            .help-workflow-node { border:1px solid #cfe1f5; background:#f7fbff; color:#1e4e82; border-radius:12px; padding:13px 10px; text-align:center; font-weight:650; font-size:.92rem; }
            .help-step { display:grid; grid-template-columns:44px minmax(0,1fr); gap:14px; padding:16px 0; border-bottom:1px solid #edf1f5; }
            .help-step:last-child { border-bottom:0; }
            .help-step-number { width:36px; height:36px; border-radius:50%; background:#146cbd; color:white; display:grid; place-items:center; font-weight:750; }
            .help-step-title { margin:1px 0 8px; font-size:1.08rem; }
            .help-step p { margin:5px 0; color:#405060; line-height:1.55; }
            .help-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; }
            .help-callout { background:#fff8e8; border-left:4px solid #d89614; padding:13px 15px; border-radius:8px; color:#644b12; margin:14px 0; }
            .help-validated { background:#effaf4; border-left:4px solid #27975f; padding:13px 15px; border-radius:8px; color:#215f42; margin:14px 0; }
            .help-experimental { background:#fff4f3; border-left:4px solid #c65c50; padding:13px 15px; border-radius:8px; color:#813b33; margin:14px 0; }
            .help-table { width:100%; border-collapse:collapse; font-size:.92rem; }
            .help-table th { background:#f4f7fa; text-align:left; }
            .help-table th,.help-table td { padding:10px; border:1px solid #e3e9ef; vertical-align:top; }
            .help-table-wrap { overflow-x:auto; }
            .help-muted { color:#5d6b78; line-height:1.6; }
            .help-inline-actions { display:flex; flex-wrap:wrap; gap:10px; margin-top:14px; }
            .help-faq details { border-bottom:1px solid #e8edf3; padding:10px 0; }
            .help-faq summary { cursor:pointer; font-weight:650; color:#274d73; }
            .help-faq p { color:#405060; padding:8px 4px 0; margin:0; line-height:1.55; }
            @media (max-width:900px) { .help-layout { grid-template-columns:1fr; } .help-toc { position:static; } .help-workflow { grid-template-columns:repeat(2,minmax(130px,1fr)); } .help-grid { grid-template-columns:1fr; } }
            @media (max-width:520px) { .help-shell { padding:18px 10px 40px; } .help-hero,.help-card { padding:19px; } .help-workflow { grid-template-columns:1fr; } }
        """
        ),
        _feature_shared.ui.tags.div(
            _feature_shared.ui.tags.aside(
                _feature_shared.ui.tags.p("On this page", class_="help-toc-title"),
                *[
                    _feature_shared.ui.tags.a(label, href=target)
                    for label, target in (
                        ("Overview", "#overview"),
                        ("Quick Start", "#quick-start"),
                        ("Input data", "#input-data"),
                        ("Y7_T tutorial", "#y7t-tutorial"),
                        ("Interpret results", "#interpretation"),
                        ("Parameters", "#parameters"),
                        ("Jobs & reproducibility", "#jobs"),
                        ("Experimental features", "#experimental"),
                        ("FAQ", "#faq"),
                        ("Citation", "#citation"),
                    )
                ],
                class_="help-toc",
                aria_label="Help page table of contents",
            ),
            _feature_shared.ui.tags.main(
                _feature_shared.ui.tags.header(
                    _feature_shared.ui.tags.div("SpaShiny user guide", class_="help-eyebrow"),
                    _feature_shared.ui.h1("Help & Tutorial", class_="help-title"),
                    _feature_shared.ui.tags.p(
                        "A practical guide to the validated SpaShiny spatial transcriptomics (ST), spatial metabolomics (SM), and integrated ST–SM workflow.",
                        class_="help-lead",
                    ),
                    class_="help-hero",
                ),
                _feature_shared._card(
                    "Overview",
                    _feature_shared.ui.tags.p(
                        "SpaShiny is an interactive web platform for spatial transcriptomics, spatial metabolomics and integrated ST–SM analysis. You do not need to run Python or R directly: computationally intensive validated workflows are submitted as background jobs, while the browser remains available for reviewing status and results."
                    ),
                    _feature_shared.ui.tags.div(
                        *[
                            _feature_shared.ui.tags.div(label, class_="help-workflow-node")
                            for label in (
                                "ST / SM data",
                                "QC & preprocessing",
                                "Spatial alignment",
                                "KNN reassignment",
                                "SpatialMETA integration",
                                "Joint clustering",
                                "Downstream exploration",
                                "Results & downloads",
                            )
                        ],
                        class_="help-workflow",
                        role="img",
                        aria_label="SpaShiny core workflow from input data to results",
                    ),
                    _feature_shared.ui.tags.div(
                        _feature_shared.ui.tags.strong("Validated core workflow. "),
                        "Y7_T is the complete public example used in this guide. Other modules shown in the application are separately labelled where they remain experimental.",
                        class_="help-validated",
                    ),
                    anchor="overview",
                ),
                _feature_shared._card(
                    "Quick Start with Y7_T",
                    _feature_shared.ui.tags.p(
                        "Use the workflow below for the shortest supported end-to-end demonstration. Each action opens the relevant page; loading an example and running an analysis remain explicit user actions."
                    ),
                    _feature_shared._step(
                        1,
                        "Open Spatial Alignment",
                        "Spatial Alignment → Alignment Preprocessing.",
                        "Click “Load Example Raw ST/SM (Y7_T)”. No files need to be uploaded.",
                        "The Y7_T ST and SM input references are bound to your current analysis session.",
                    ),
                    _feature_shared._step(
                        2,
                        "Review QC",
                        "Data & QC → ST QC, then SM QC.",
                        "Use the example-compatible defaults first; inspect distributions before tightening filters.",
                        "QC tables, figures and filtered H5AD artifacts.",
                    ),
                    _feature_shared._step(
                        3,
                        "Align and reassign",
                        "Spatial Alignment, then KNN Reassignment.",
                        "Confirm the overlay before automatic alignment. For Y7_T, a validated KNN run used k=5 and dist_fold=2.0.",
                        "Aligned/reassigned coordinates and result artifacts.",
                    ),
                    _feature_shared._step(
                        4,
                        "Integrate",
                        "Multimodal Integration → Single-sample ST–SM Integration.",
                        "Keep model and training defaults for an initial run; choose a compute device only when appropriate.",
                        "A background ConditionalVAE job with progress, latent embedding and integrated H5AD.",
                    ),
                    _feature_shared._step(
                        5,
                        "Inspect and download",
                        "Visualization & Results and job/result controls.",
                        "Review UMAP, joint clusters and modality contribution before downloading.",
                        "Figures, tables, H5AD and the result ZIP.",
                    ),
                    _feature_shared.ui.tags.div(
                        _feature_shared.ui.input_action_button(
                            "help_open_alignment", "Open Y7_T Alignment", class_="btn btn-primary"
                        ),
                        _feature_shared.ui.input_action_button(
                            "help_open_st_qc", "Open ST QC", class_="btn btn-outline-primary"
                        ),
                        _feature_shared.ui.input_action_button(
                            "help_open_sm_qc", "Open SM QC", class_="btn btn-outline-primary"
                        ),
                        _feature_shared.ui.input_action_button(
                            "help_open_integration",
                            "Open Integration",
                            class_="btn btn-outline-primary",
                        ),
                        class_="help-inline-actions",
                    ),
                    anchor="quick-start",
                ),
                _feature_shared._card(
                    "Input data",
                    _feature_shared.ui.tags.div(
                        _feature_shared.ui.tags.div(
                            _feature_shared.ui.h3("Spatial transcriptomics"),
                            _feature_shared.ui.tags.ul(
                                _feature_shared.ui.tags.li(
                                    "A complete 10x Genomics Visium outs ZIP containing the expression matrix and spatial information."
                                ),
                                _feature_shared.ui.tags.li(
                                    "An AnnData/H5AD file with an expression matrix, observation and feature metadata, and spatial coordinates in obsm['spatial']."
                                ),
                            ),
                            _feature_shared.ui.tags.p(
                                "Do not assume that every 10x or generic HDF5 layout is accepted. A Visium ZIP needs the corresponding Cell Ranger outputs, including spatial information.",
                                class_="help-muted",
                            ),
                        ),
                        _feature_shared.ui.tags.div(
                            _feature_shared.ui.h3("Spatial metabolomics"),
                            _feature_shared.ui.tags.ul(
                                _feature_shared.ui.tags.li(
                                    "imzML together with its paired IBD file."
                                ),
                                _feature_shared.ui.tags.li(
                                    "A CSV intensity table with m/z features and spatial coordinates."
                                ),
                                _feature_shared.ui.tags.li(
                                    "Processed H5AD where the chosen workflow exposes H5AD input."
                                ),
                            ),
                            _feature_shared.ui.tags.p(
                                "The intensity matrix, m/z features and spatial coordinates must describe the same observations.",
                                class_="help-muted",
                            ),
                        ),
                        class_="help-grid",
                    ),
                    _feature_shared.ui.tags.div(
                        _feature_shared.ui.tags.strong("Integrated ST–SM analysis. "),
                        "Both modalities must carry spatial coordinates suitable for registration. For adjacent sections, complete spatial alignment and reassignment before integration.",
                        class_="help-callout",
                    ),
                    _feature_shared.ui.tags.div(
                        _feature_shared.ui.tags.strong(
                            "Example and uploaded files are mutually exclusive current inputs. "
                        ),
                        "On pages that support both, loading an Example selects the session-bound Example for the next calculation. Completing an upload selects that uploaded file instead. The page shows “Current input” before you run the analysis; selecting a new source does not delete the earlier file or Example binding.",
                        class_="help-validated",
                    ),
                    anchor="input-data",
                ),
                _feature_shared._card(
                    "Y7_T tutorial",
                    _feature_shared._step(
                        1,
                        "Load example data",
                        "Spatial Alignment → Alignment Preprocessing → Load Example Raw ST/SM (Y7_T).",
                        "No upload is required. The example is session-bound rather than copied into the web container.",
                        "ST and SM input references available to the alignment workflow.",
                    ),
                    _feature_shared._step(
                        2,
                        "ST quality control",
                        "Data & QC → ST QC.",
                        "Review total counts and detected features first. The current core defaults are minimum counts 3,000 and minimum genes 1,000; adjust only with a documented rationale.",
                        "QC distributions, QC tables and filtered ST H5AD. Low count/feature spots may indicate low-quality measurements.",
                    ),
                    _feature_shared._step(
                        3,
                        "SM quality control",
                        "Data & QC → SM QC.",
                        "Review spatial positions, detected m/z features and total intensity. The current SM total-intensity default is 100,000.",
                        "SM QC distributions/tables and filtered SM H5AD.",
                    ),
                    _feature_shared._step(
                        4,
                        "Spatial alignment",
                        "Spatial Alignment → Alignment Preprocessing and Auto Image Registration.",
                        "Use manual rotation, horizontal/vertical flip, translation and width/height scaling to establish a plausible starting overlay. Then use Automatic Alignment / AlignmentVAE when appropriate.",
                        "Before/after overlays and raster/spot artifacts. Compare tissue positions; alignment creates spatial correspondence, not biological clusters.",
                    ),
                    _feature_shared._step(
                        5,
                        "KNN reassignment",
                        "KNN Reassignment.",
                        "For Y7_T, k=5 and dist_fold=2.0 are a validated example setting. k sets the neighbourhood size; dist_fold controls spatial distance scaling.",
                        "SM information reassigned to shared ST-based spatial positions and resulting H5AD artifacts.",
                    ),
                    _feature_shared._step(
                        6,
                        "SpatialMETA integration",
                        "Multimodal Integration → Single-sample ST–SM Integration.",
                        "SpaShiny invokes SpatialMETA ConditionalVAESTSM. Start with the UI defaults: latent dimension 6, max epochs 8, batch size 8, learning rate 0.001, device auto. Use a recorded random seed for comparable runs.",
                        "Latent representation, UMAP, Leiden clusters, modality contribution and integrated H5AD.",
                    ),
                    _feature_shared._step(
                        7,
                        "Joint clustering",
                        "Integration result panels.",
                        "Inspect UMAP and the corresponding spatial cluster map. Adjust clustering only after documenting parameters.",
                        "Joint clusters from the integrated ST–SM latent representation; they are not a direct merge of independent ST and SM clusters.",
                    ),
                    _feature_shared._step(
                        8,
                        "Downstream exploration",
                        "Downstream Analysis.",
                        "Use validated result panels only. Marker and correlation interpretations require biological review.",
                        "Marker genes/m/z features and available cluster-wise gene–m/z correlation views.",
                    ),
                    _feature_shared._step(
                        9,
                        "Results and download",
                        "Jobs/Results controls and workflow result panels.",
                        "Wait for job status to become succeeded, then use the offered download controls.",
                        "H5AD, tables, figures, logs and result ZIPs where produced by the workflow.",
                    ),
                    _feature_shared.ui.tags.p(
                        "SCREENSHOT_PENDING: tutorial screenshots will be added only from formally reviewed production artifacts; no synthetic screenshots are used.",
                        class_="help-callout",
                    ),
                    anchor="y7t-tutorial",
                ),
                _feature_shared._card(
                    "Understanding your results",
                    _feature_shared.ui.tags.div(
                        _feature_shared.ui.tags.div(
                            _feature_shared.ui.h3("QC"),
                            _feature_shared.ui.tags.p(
                                "Total counts summarize captured signal per spatial observation; detected features summarize breadth. Look for low-quality tails and apply thresholds transparently."
                            ),
                            _feature_shared.ui.h3("Alignment and reassignment"),
                            _feature_shared.ui.tags.p(
                                "Alignment should make tissue structures spatially corresponding across modalities. KNN reassignment establishes shared spatial positions when sampling densities differ."
                            ),
                            _feature_shared.ui.h3("Joint latent representation"),
                            _feature_shared.ui.tags.p(
                                "The joint latent representation combines ST and SM information. It is an analysis representation, not a direct biological label."
                            ),
                        ),
                        _feature_shared.ui.tags.div(
                            _feature_shared.ui.h3("UMAP and Leiden clusters"),
                            _feature_shared.ui.tags.p(
                                "UMAP is a low-dimensional visualization; its distances are not precise biological distances. Leiden clusters are data-driven joint molecular states and do not automatically define cell types."
                            ),
                            _feature_shared.ui.h3("Modality contribution"),
                            _feature_shared.ui.tags.p(
                                "Contribution summarizes the relative ST/SM influence on the joint representation. It should be assessed with QC and spatial context."
                            ),
                            _feature_shared.ui.h3("Gene–m/z correlation"),
                            _feature_shared.ui.tags.p(
                                "Positive and negative correlations are associations, not causal relationships. An unannotated m/z feature must not be described as a confirmed metabolite."
                            ),
                        ),
                        class_="help-grid",
                    ),
                    anchor="interpretation",
                ),
                _feature_shared._card(
                    "Parameter reference",
                    _feature_shared.ui.tags.p(
                        "Values below are read from the current validated single-sample UI/configuration. Keep a record of any changes in your analysis report.",
                        class_="help-muted",
                    ),
                    _feature_shared.ui.tags.div(
                        _feature_shared.ui.tags.table(
                            _feature_shared.ui.tags.thead(
                                _feature_shared.ui.tags.tr(
                                    *[
                                        _feature_shared.ui.tags.th(x)
                                        for x in (
                                            "Parameter",
                                            "Description",
                                            "Current default",
                                            "Recommended use",
                                            "Workflow",
                                        )
                                    ]
                                )
                            ),
                            _feature_shared.ui.tags.tbody(
                                _feature_shared._parameter_row(
                                    "ST min counts",
                                    "Minimum counts used by the ST QC core default.",
                                    "3,000",
                                    "Inspect the QC distribution before changing.",
                                    "ST QC",
                                ),
                                _feature_shared._parameter_row(
                                    "ST min genes",
                                    "Minimum detected genes used by the ST QC core default.",
                                    "1,000",
                                    "Inspect the QC distribution before changing.",
                                    "ST QC",
                                ),
                                _feature_shared._parameter_row(
                                    "SM min total intensity",
                                    "Minimum total intensity used by the SM QC core default.",
                                    "100,000",
                                    "Inspect intensity distributions first.",
                                    "SM QC",
                                ),
                                _feature_shared._parameter_row(
                                    "k",
                                    "Number of nearest neighbours for reassignment.",
                                    "5",
                                    "Y7_T validated example uses 5.",
                                    "KNN",
                                ),
                                _feature_shared._parameter_row(
                                    "dist_fold",
                                    "Spatial distance scaling factor for reassignment.",
                                    "1.5 UI default; 2.0 validated Y7_T run",
                                    "Use the validated Y7_T setting for the tutorial.",
                                    "KNN",
                                ),
                                _feature_shared._parameter_row(
                                    "latent dimension",
                                    "Size of the ConditionalVAE latent representation.",
                                    "6",
                                    "Increase only with a documented modelling reason.",
                                    "Integration",
                                ),
                                _feature_shared._parameter_row(
                                    "max epochs",
                                    "Maximum ConditionalVAE training epochs.",
                                    "8",
                                    "Smoke-test overrides are not recommended analysis settings.",
                                    "Integration",
                                ),
                                _feature_shared._parameter_row(
                                    "batch size",
                                    "Observations per ConditionalVAE batch.",
                                    "8",
                                    "Raise only when memory allows.",
                                    "Integration",
                                ),
                                _feature_shared._parameter_row(
                                    "learning rate",
                                    "ConditionalVAE optimizer learning rate.",
                                    "0.001",
                                    "Change only when monitoring convergence.",
                                    "Integration",
                                ),
                                _feature_shared._parameter_row(
                                    "device",
                                    "Requested integration compute device.",
                                    "auto",
                                    "Use auto unless resource selection is required.",
                                    "Integration",
                                ),
                                _feature_shared._parameter_row(
                                    "random seed",
                                    "Recorded seed for validated stochastic workflows.",
                                    "42",
                                    "Keep fixed for direct comparisons; record it in the result summary.",
                                    "Alignment / Integration",
                                ),
                            ),
                            class_="help-table",
                        ),
                        class_="help-table-wrap",
                    ),
                    anchor="parameters",
                ),
                _feature_shared._card(
                    "Jobs and reproducibility",
                    _feature_shared.ui.tags.p(
                        "Computationally intensive workflows, including QC, automatic alignment and ConditionalVAE integration, use independent background jobs. Job status can be queued, running, succeeded or failed, with progress, logs and result artifacts where the workflow supports them."
                    ),
                    _feature_shared.ui.tags.p(
                        "Completed results can be revisited and downloaded. SpaShiny records key analysis settings and uses explicit random seeds for validated stochastic workflows to facilitate reproducible analyses. This does not claim that every interactive operation is bitwise deterministic."
                    ),
                    anchor="jobs",
                ),
                _feature_shared._card(
                    "Experimental features",
                    _feature_shared.ui.tags.div(
                        _feature_shared.ui.tags.strong(
                            "Experimental — not included in the validated SpaShiny workflow. "
                        ),
                        "Metabolite annotation, gene enrichment, metabolite enrichment, ROI, trajectory, embedded Dash/Plotly, River and multi-sample workflows should not be treated as part of this Y7_T Quick Start until each has completed formal production validation.",
                        class_="help-experimental",
                    ),
                    _feature_shared.ui.tags.p(
                        "The Metabolite Annotation page can expose local MS1 accurate-mass/adduct candidate matching. MS1 candidates are not definitive metabolite identities; ambiguous candidates remain possible."
                    ),
                    anchor="experimental",
                ),
                _feature_shared._card(
                    "FAQ and troubleshooting",
                    _feature_shared.ui.tags.div(
                        _feature_shared.ui.tags.details(
                            _feature_shared.ui.tags.summary("Why does my H5AD fail to load?"),
                            _feature_shared.ui.tags.p(
                                "Confirm that it is a readable AnnData file with a compatible expression matrix and the required metadata. Spatial workflows require obsm['spatial']."
                            ),
                        ),
                        _feature_shared.ui.tags.details(
                            _feature_shared.ui.tags.summary(
                                "Will an uploaded file and an Example be combined automatically?"
                            ),
                            _feature_shared.ui.tags.p(
                                "No. They are separate input sources. Each supported page uses exactly one current source: either its bound Example or the most recently completed upload selected on that page. Check the Current input line before starting a calculation."
                            ),
                        ),
                        _feature_shared.ui.tags.details(
                            _feature_shared.ui.tags.summary(
                                "What files are required for a Visium ZIP?"
                            ),
                            _feature_shared.ui.tags.p(
                                "Use a complete Cell Ranger Visium outs ZIP containing the expression matrix and spatial output, not an arbitrary HDF5 archive."
                            ),
                        ),
                        _feature_shared.ui.tags.details(
                            _feature_shared.ui.tags.summary("Why must imzML and IBD be paired?"),
                            _feature_shared.ui.tags.p(
                                "imzML stores metadata while IBD stores binary spectral intensity data; both are required to read the dataset."
                            ),
                        ),
                        _feature_shared.ui.tags.details(
                            _feature_shared.ui.tags.summary(
                                "Why can alignment take longer than QC?"
                            ),
                            _feature_shared.ui.tags.p(
                                "Automatic alignment includes model training and/or registration operations, whereas QC primarily calculates distributions and filters observations."
                            ),
                        ),
                        _feature_shared.ui.tags.details(
                            _feature_shared.ui.tags.summary("Why is GPU integration queued?"),
                            _feature_shared.ui.tags.p(
                                "GPU jobs share limited worker capacity. Wait for the job state and progress panel rather than re-submitting the same task."
                            ),
                        ),
                        _feature_shared.ui.tags.details(
                            _feature_shared.ui.tags.summary("What should I do if a job fails?"),
                            _feature_shared.ui.tags.p(
                                "Open its log and error message, verify the input requirements, and submit a corrected job. A failed job should not be assumed to have produced usable results."
                            ),
                        ),
                        _feature_shared.ui.tags.details(
                            _feature_shared.ui.tags.summary(
                                "Can I refresh or close the page during a long job?"
                            ),
                            _feature_shared.ui.tags.p(
                                "Submitted worker jobs are designed to continue independently; reconnect and use the Jobs/Results interface to find completed artifacts. Do not rely on unsaved browser-only selections."
                            ),
                        ),
                        _feature_shared.ui.tags.details(
                            _feature_shared.ui.tags.summary("How do I reproduce an analysis?"),
                            _feature_shared.ui.tags.p(
                                "Retain the input files, job summary, parameter values, software versions and random seed included with the result artifacts."
                            ),
                        ),
                        _feature_shared.ui.tags.details(
                            _feature_shared.ui.tags.summary(
                                "Why is an m/z feature not a confirmed metabolite?"
                            ),
                            _feature_shared.ui.tags.p(
                                "Accurate-mass MS1 matching can yield several candidates. Confirmation normally requires additional evidence such as MS/MS and validated standards."
                            ),
                        ),
                        class_="help-faq",
                    ),
                    anchor="faq",
                ),
                _feature_shared._card(
                    "Citation",
                    _feature_shared.ui.tags.p(
                        "SpaShiny manuscript: manuscript in preparation. Replace this entry with the formal citation after publication."
                    ),
                    _feature_shared.ui.tags.p(
                        "For the integrated workflow, cite SpatialMETA and the relevant underlying methods. SpaShiny provides a web-based implementation of established SpatialMETA analysis procedures and does not claim authorship of the SpatialMETA model."
                    ),
                    _feature_shared.ui.tags.p(
                        "Also cite Python Shiny where required by your publication or institutional guidance."
                    ),
                    anchor="citation",
                ),
                *video_section,
            ),
            class_="help-layout",
        ),
        class_="help-shell",
    )
