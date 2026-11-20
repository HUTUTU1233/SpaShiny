# Actual feature UI extracted from production. Feature: results.
from spashiny._shared import runtime_globals as _spashiny_globals


def _view_1(_spashiny_ctx, module):
    return _spashiny_globals.cloud_platform_ui("results")


def ui(_spashiny_ctx, module):
    if module == "Cloud Results":
        return _view_1(_spashiny_ctx, module)
    raise ValueError("Unknown feature page: results")
