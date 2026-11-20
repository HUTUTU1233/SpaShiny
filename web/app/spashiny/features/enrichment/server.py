"""Shared-service bindings for this view; no duplicate handler registration."""

REQUIRED_BINDINGS = ("_enrichment_job_result_ui",)


def server(context):
    return {name: getattr(context, name) for name in REQUIRED_BINDINGS}
