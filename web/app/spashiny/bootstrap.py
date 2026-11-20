"""Compatibility bootstrap preserving the production registration order."""

from importlib import import_module
from types import SimpleNamespace
from ._shared import runtime_globals as g

PLAN = (
    ("spashiny._shared.services.session_bootstrap.server", 0),
    ("spashiny._shared.services.plot_appearance.server", 0),
    ("spashiny._shared.services.cloud_services.server", 0),
    ("spashiny._shared.services.enrichment_services.server", 0),
    ("spashiny.features.gene_enrichment.server", 0),
    ("spashiny._shared.services.enrichment_services.server", 1),
    ("spashiny.features.metabolite_annotation.server", 0),
    ("spashiny._shared.services.enrichment_services.server", 2),
    ("spashiny.features.metabolite_annotation.server", 1),
    ("spashiny.features.gene_enrichment.server", 1),
    ("spashiny.features.metabolite_enrichment.server", 0),
    ("spashiny.features.metabolite_annotation.server", 2),
    ("spashiny.features.gene_enrichment.server", 2),
    ("spashiny.features.metabolite_annotation.server", 3),
    ("spashiny._shared.services.enrichment_services.server", 3),
    ("spashiny.features.metabolite_annotation.server", 4),
    ("spashiny.features.metabolite_enrichment.server", 1),
    ("spashiny.features.gene_enrichment.server", 3),
    ("spashiny.features.metabolite_enrichment.server", 2),
    ("spashiny.features.metabolite_annotation.server", 5),
    ("spashiny.features.gene_enrichment.server", 4),
    ("spashiny.features.metabolite_enrichment.server", 3),
    ("spashiny._shared.services.enrichment_services.server", 4),
    ("spashiny.features.metabolite_annotation.server", 6),
    ("spashiny._shared.services.enrichment_services.server", 5),
    ("spashiny._shared.services.navigation.server", 0),
    ("spashiny.features.metabolite_annotation.server", 7),
    ("spashiny._shared.services.navigation.server", 1),
    ("spashiny._shared.services.console.server", 0),
    ("spashiny.features.sm_import.server", 0),
    ("spashiny.features.st_import.server", 0),
    ("spashiny.features.sm_qc.server", 0),
    ("spashiny.features.st_qc.server", 0),
    ("spashiny.features.alignment_manual.server", 0),
    ("spashiny.features.alignment_auto.server", 0),
    ("spashiny.features.knn.server", 0),
    ("spashiny.features.integration_single.server", 0),
    ("spashiny.features.feature_explorer.server", 0),
    ("spashiny.features.integration_multi_st_sm.server", 0),
    ("spashiny.features.integration_multi_sm.server", 0),
    ("spashiny.features.marker.server", 0),
    ("spashiny.features.celltype_annotation.server", 0),
    ("spashiny.features.marker.server", 1),
    ("spashiny.features.celltype_annotation.server", 1),
    ("spashiny.features.marker.server", 2),
    ("spashiny.features.celltype_annotation.server", 2),
    ("spashiny.features.marker.server", 3),
    ("spashiny.features.celltype_annotation.server", 3),
    ("spashiny.features.correlation.server", 0),
    ("spashiny.features.volcano.server", 0),
    ("spashiny.features.spatialmeta_dash.server", 0),
    ("spashiny.features.roi.server", 0),
    ("spashiny._shared.services.workbench_bridge.server", 0),
)


def server(input, output, session):
    context = SimpleNamespace(input=input, output=output, session=session)
    for module, step in PLAN:
        import_module(module).server(context, step=step)
