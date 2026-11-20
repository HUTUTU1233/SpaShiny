# Actual feature UI extracted from production. Feature: r_enrichment.
from spashiny._shared import runtime_globals as _spashiny_globals


def _view_1(_spashiny_ctx, module):
    return _spashiny_globals.enrichment_module_ui("enrichment")


def ui(_spashiny_ctx, module):
    if module == "Enrichment Module":
        return _view_1(_spashiny_ctx, module)
    raise ValueError("Unknown feature page: r_enrichment")
