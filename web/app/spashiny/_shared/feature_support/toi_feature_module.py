# Original feature imports, constants and direct helper functions; no duplicate UI/server bodies.
from __future__ import annotations
from pathlib import Path as _ExportPath

LEGACY_ENTRYPOINT_FILE = str(_ExportPath(__file__).resolve().parents[3] / "toi_feature_module.py")
"Session-scoped native SpatialMETA TOI figures, without changing TOI geometry."
import io
import re
import traceback
from shiny import reactive, render, ui
from toi_feature_tools import (
    PLOT_LOCK,
    build_feature_trajectory_figure,
    build_native_clustermap_figure,
    build_preview_image,
    list_feature_choices,
    list_trajectory_keys,
    trajectory_fingerprint,
)


def register_toi_feature_server(
    input,
    output,
    session,
    *,
    adata_rv,
    dash_state,
    get_input,
    get_owner,
    get_analysis,
    click_guard,
    show_modal,
    colorize_plot,
):
    from spashiny.features.toi.server import register_toi_feature_server as _entry

    return _entry(
        input,
        output,
        session,
        adata_rv=adata_rv,
        dash_state=dash_state,
        get_input=get_input,
        get_owner=get_owner,
        get_analysis=get_analysis,
        click_guard=click_guard,
        show_modal=show_modal,
        colorize_plot=colorize_plot,
    )
