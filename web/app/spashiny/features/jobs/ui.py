# Actual feature UI extracted from production. Feature: jobs.
from spashiny._shared import runtime_globals as _spashiny_globals


def _view_1(_spashiny_ctx, module):
    return _spashiny_globals.cloud_platform_ui("jobs")


def ui(_spashiny_ctx, module):
    if module == "Cloud Jobs":
        return _view_1(_spashiny_ctx, module)
    raise ValueError("Unknown feature page: jobs")
