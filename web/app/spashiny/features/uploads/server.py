"""Shared-service bindings for this view; no duplicate handler registration."""

REQUIRED_BINDINGS = ("_cloud_session_id", "_cloud_analysis_session_id")


def server(context):
    return {name: getattr(context, name) for name in REQUIRED_BINDINGS}
