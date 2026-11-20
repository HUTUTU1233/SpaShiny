# Extracted from /app/app/ST-SM.py. Feature: session_bootstrap; ordered phases preserve original initialization.
from spashiny._shared import runtime_globals as _spashiny_globals


def _install_0(_spashiny_ctx):
    from shiny import reactive

    _spashiny_ctx.reactive = reactive
    from shiny import App, ui, reactive, render, req

    _spashiny_ctx.App = App
    _spashiny_ctx.ui = ui
    _spashiny_ctx.reactive = reactive
    _spashiny_ctx.render = render
    _spashiny_ctx.req = req
    _spashiny_ctx.one_stop_active = _spashiny_ctx.reactive.Value(False)
    _spashiny_ctx.one_stop_transform_override = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.one_stop_actions = {}

    def _one_stop_action(name):

        def register(function):
            _spashiny_ctx.one_stop_actions[name] = function
            return function

        return register

    _spashiny_ctx._one_stop_action = _one_stop_action
    _spashiny_ctx.temp_dir = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.raw_pos_dir = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.raw_neg_dir = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.csv_file_path = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.adata_final = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.adata_st = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.log_text = _spashiny_ctx.reactive.Value("")
    _spashiny_ctx.st_h5ad_path = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.sm_h5ad_path = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.st_example_dir_path = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.st_preprocess_source = _spashiny_ctx.reactive.Value("")
    _spashiny_ctx.sm_preprocess_source = _spashiny_ctx.reactive.Value("")
    _spashiny_ctx.adata_st = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.adata_sm = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.current_module = _spashiny_ctx.reactive.Value("home")
    _spashiny_ctx.transformed_sm_coords = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.dash_embed_state = _spashiny_ctx.reactive.Value(
        {
            "status": "idle",
            "url": "",
            "message": "Load this analysis input or finish Marker analysis, then open native SpatialMETA Dash. Correlation is not required.",
        }
    )
    _spashiny_ctx.gene_enrichment_job_id = _spashiny_ctx.reactive.Value("")
    _spashiny_ctx.metabolite_enrichment_job_id = _spashiny_ctx.reactive.Value("")
    _spashiny_ctx.metabolite_annotation_job_id = _spashiny_ctx.reactive.Value("")
    _spashiny_ctx.metabolite_annotation_input_reference = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.gene_enrichment_status_msg = _spashiny_ctx.reactive.Value(
        "Ready. Upload a Gene CSV or use current Marker Analysis results."
    )
    _spashiny_ctx.metabolite_enrichment_status_msg = _spashiny_ctx.reactive.Value(
        "Ready. Upload a Metabolite CSV with KEGG.ID values."
    )
    _spashiny_ctx.metabolite_annotation_status_msg = _spashiny_ctx.reactive.Value(
        "Ready. Upload a spatial-metabolomics H5AD or run the Y7_T SpatialMETA example annotation."
    )
    if _spashiny_globals.SPASHINY_WEB_PLATFORM:
        _spashiny_ctx.ssh_state = _spashiny_ctx.reactive.Value(
            {"status": "cloud", "message": "Control Plane"}
        )
    else:
        _spashiny_ctx.ssh_state = _spashiny_globals.ssh_module_server(
            _spashiny_ctx.input, _spashiny_ctx.output, _spashiny_ctx.session
        )
    if _spashiny_globals.SPASHINY_R_FEATURES_ENABLED:
        _spashiny_globals.enrichment_module_server(
            "enrichment",
            base_dir=_spashiny_globals.WORKSPACE_ROOT / "spashiny_enrichment_module",
            rscript_bin=_spashiny_globals.resolve_enrichment_rscript(),
        )
    _spashiny_ctx.plot_color_settings = _spashiny_ctx.reactive.Value({})
    _spashiny_ctx.plot_color_revision = _spashiny_ctx.reactive.Value(0)
    _spashiny_ctx.active_color_plot = _spashiny_ctx.reactive.Value("")
    _spashiny_ctx.generated_color_plots = set()
    _spashiny_ctx.plot_color_specs = {}
    _spashiny_ctx.alignment_color_panel_job_ids = _spashiny_ctx.reactive.Value({})
    _spashiny_ctx.ALIGNMENT_WORKER_COLOR_PLOTS = {
        "initial_plot": {
            "plot_key": "initial_st_sm",
            "title": "Initial ST / SM View",
            "workflow": "manual_preview",
            "preview_kind": "initial",
            "artifact": "plots/initial_st_sm_view.png",
            "fallback_spec": {
                "colors": [
                    {"label": "Spatial Transcriptomics", "color": "#1F77B4"},
                    {"label": "Spatial Metabolomics", "color": "#FF7F0E"},
                ],
                "colormap": None,
            },
        },
        "overlay_plot": {
            "plot_key": "manual_registration",
            "title": "Manual Registration Preview",
            "workflow": "manual_preview",
            "preview_kind": "overlay",
            "artifact": "plots/manual_overlay.png",
            "fallback_spec": {
                "colors": [
                    {"label": "Spatial Transcriptomics", "color": "#1F77B4"},
                    {"label": "Spatial Metabolomics", "color": "#FF7F0E"},
                ],
                "colormap": None,
            },
        },
        "side_plot": {
            "plot_key": "side_by_side",
            "title": "Side-by-Side View",
            "workflow": "manual_preview",
            "preview_kind": "side",
            "artifact": "plots/side_by_side.png",
            "fallback_spec": {
                "colors": [
                    {"label": "Spatial Transcriptomics", "color": "#1F77B4"},
                    {"label": "Spatial Metabolomics", "color": "#FF7F0E"},
                ],
                "colormap": None,
            },
        },
        "raster_panel_sm_feature": {
            "plot_key": "step4_sm_raster",
            "title": "SM rasterized feature",
            "workflow": "render_color_panel",
            "group": "raster",
            "panel": "sm_feature",
            "artifact": "plots/sm_rasterized_feature.png",
            "fallback_spec": {"colors": [], "colormap": ["#9F66BE", "#8DE9AC", "#84D43E"]},
        },
        "raster_panel_sm_latent": {
            "plot_key": "step4_sm_latent",
            "title": "SM latent embedding",
            "workflow": "render_color_panel",
            "group": "raster",
            "panel": "sm_latent",
            "artifact": "plots/sm_latent_embedding.png",
            "fallback_spec": {"colors": [], "colormap": ["#9F66BE", "#8DE9AC", "#84D43E"]},
        },
        "raster_panel_st_image": {
            "plot_key": "step4_st_spatial",
            "title": "ST spatial image",
            "workflow": "render_color_panel",
            "group": "raster",
            "panel": "st_image",
            "artifact": "plots/st_spatial_image.png",
            "fallback_spec": {"colors": [], "colormap": ["#FFF8F4", "#EAB7A8", "#B87C70"]},
        },
        "raster_panel_st_latent": {
            "plot_key": "step4_st_latent",
            "title": "ST latent feature",
            "workflow": "render_color_panel",
            "group": "raster",
            "panel": "st_latent",
            "artifact": "plots/st_latent_feature.png",
            "fallback_spec": {"colors": [], "colormap": ["#7B2F92", "#D6C9E6", "#F9F4FA"]},
        },
        "spot_panel_st_latent": {
            "plot_key": "random_st_tissue_latent",
            "title": "ST tissue and latent structure",
            "workflow": "render_color_panel",
            "group": "spot",
            "panel": "st_latent",
            "artifact": "plots/st_tissue_latent_structure.png",
            "fallback_spec": {"colors": [], "colormap": ["#FFF8F4", "#EAB7A8", "#B87C70"]},
        },
        "spot_panel_sampled": {
            "plot_key": "random_sampled_spots",
            "title": "Randomly sampled inside-tissue spots",
            "workflow": "render_color_panel",
            "group": "spot",
            "panel": "sampled",
            "artifact": "plots/sampled_inside_tissue_spots.png",
            "fallback_spec": {
                "colors": [{"label": "Sampled spots", "color": "#F8F8F8"}],
                "colormap": ["#FFF8F4", "#EAB7A8", "#B87C70"],
            },
        },
        "spot_panel_mask": {
            "plot_key": "random_binary_mask",
            "title": "Binary tissue mask",
            "workflow": "render_color_panel",
            "group": "spot",
            "panel": "mask",
            "artifact": "plots/binary_tissue_mask.png",
            "fallback_spec": {"colors": [], "colormap": ["#000000", "#777777", "#FFFFFF"]},
        },
    }


_STEPS = (_install_0,)


def server(_spashiny_ctx, step=0):
    return _STEPS[step](_spashiny_ctx)
