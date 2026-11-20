# Actual feature UI extracted from production. Feature: uploads.
from spashiny._shared import runtime_globals as _spashiny_globals


def _view_1(_spashiny_ctx, module):
    return _spashiny_globals.cloud_platform_ui("files")


def ui(_spashiny_ctx, module):
    if module == "Cloud Files":
        return _view_1(_spashiny_ctx, module)
    raise ValueError("Unknown feature page: uploads")
