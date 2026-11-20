"""Shared-service bindings for this view; no duplicate handler registration."""

REQUIRED_BINDINGS = ("_cloud_session_id", "_cloud_result_download_links")


def server(context):
    return {name: getattr(context, name) for name in REQUIRED_BINDINGS}
