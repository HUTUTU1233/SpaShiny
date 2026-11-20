# Actual feature UI extracted from production. Feature: enrichment.
from spashiny._shared import runtime_globals as _spashiny_globals
from spashiny.features.gene_enrichment import ui as _section_ui_gene_enrichment
from spashiny.features.metabolite_enrichment import ui as _section_ui_metabolite_enrichment


def _view_1(_spashiny_ctx, module):
    return _spashiny_globals.cpu_enrichment_module_ui()


def _view_2(_spashiny_ctx, module):
    return _spashiny_ctx.ui.div(
        _spashiny_ctx.ui.h2("Enrichment Analysis (Disabled)"),
        _spashiny_ctx.ui.p(
            "The legacy R enrichment module is disabled in the Lab container release. Use the Lab CPU enrichment workflow with a configured local database path."
        ),
        class_="apple-card",
    )


def cpu_enrichment_module_ui():
    return _spashiny_globals.ui.div(
        _spashiny_globals.ui.h2("Enrichment Analysis"),
        _spashiny_globals.ui.p(
            "Offline Python enrichment runs through the Lab CPU worker and uses local database resources only.",
            class_="cloud-muted",
        ),
        _spashiny_globals.ui.tags.div(
            _spashiny_globals.ui.tags.strong("Runtime mode: "),
            _spashiny_globals.ui.tags.span("CPU worker / JobManager / local enrichment resources"),
            class_="cloud-muted",
            style="margin-bottom: 12px;",
        ),
        _spashiny_globals.ui.navset_tab(
            _section_ui_gene_enrichment.ui(None), _section_ui_metabolite_enrichment.ui(None)
        ),
        class_="apple-card",
    )


def ui(_spashiny_ctx, module):
    if module == "CPU Enrichment Module":
        return _view_1(_spashiny_ctx, module)
    if module == "Enrichment Module Disabled":
        return _view_2(_spashiny_ctx, module)
    raise ValueError("Unknown feature page: enrichment")
