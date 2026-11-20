# Feature network: original callable implementation extracted from spatialmeta_workbench_ui.py.
from spashiny._shared.feature_support import spatialmeta_workbench_ui as _feature_shared

"Native SpatialMETA network panel UI."


def ui():
    return network_panel_ui()


"Native SpatialMETA network panel UI."


def network_panel_ui():
    return _feature_shared.ui.div(
        _feature_shared.ui.h3("SpatialMETA spatial proximity network"),
        _feature_shared.ui.tags.style(
            """
        #native_network_preview {height:auto !important; max-width:720px; margin:16px auto;}
        #native_network_preview img, #one_stop_manual_preview img {
            position:static !important; display:block; max-width:100%; height:auto !important;
        }
        #one_stop_manual_preview {height:auto !important; margin:12px 0;}
        """
        ),
        _feature_shared.ui.p(
            "Uses your existing celltype_ST_SM annotation. Edges represent spatial proximity of annotation groups, not gene-metabolite correlation or causality."
        ),
        _feature_shared.ui.input_select(
            "native_network_split",
            "Sample split",
            {"auto": "Use sample when available", "none": "No split"},
        ),
        _feature_shared.ui.layout_columns(
            _feature_shared.ui.input_numeric(
                "native_network_neighbors", "Top neighbors", value=3, min=1, max=100
            ),
            _feature_shared.ui.input_numeric(
                "native_network_threshold", "Edge weight threshold", value=0.1, min=0, step=0.05
            ),
            _feature_shared.ui.input_checkbox(
                "native_network_node_scale", "Native min-max node scaling", value=True
            ),
            _feature_shared.ui.input_checkbox(
                "native_network_edge_scale", "Native min-max edge scaling", value=True
            ),
        ),
        _feature_shared.ui.p(
            "Defaults: seed=2, node scale=800, edge scale=10, minimum node size=100. Existing annotation colors are preserved; reference palette applies only to matching labels."
        ),
        _feature_shared.ui.input_action_button(
            "run_native_spatial_network", "Generate native network", class_="btn btn-primary"
        ),
        _feature_shared.ui.output_ui("native_network_status"),
        _feature_shared.ui.output_image("native_network_preview", height="auto"),
        _feature_shared.ui.download_button("download_native_network_pdf", "Editable PDF"),
        _feature_shared.ui.download_button("download_native_network_svg", "Editable SVG"),
        _feature_shared.ui.download_button("download_native_network_edges", "Edges CSV"),
        _feature_shared.ui.download_button("download_native_network_nodes", "Nodes CSV"),
        _feature_shared.ui.input_action_button(
            "create_ai_result_report", "Prepare AI-readable analysis report"
        ),
        _feature_shared.ui.download_button("download_ai_result_report", "Download report (.zip)"),
        _feature_shared.ui.output_text("ai_result_report_status"),
        class_="apple-panel",
        style="padding:20px;",
    )
