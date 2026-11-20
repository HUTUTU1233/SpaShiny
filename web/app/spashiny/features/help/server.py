"""Shared-service bindings for this view; no duplicate handler registration."""

REQUIRED_BINDINGS = ("main_content",)


def server(context):
    return {name: getattr(context, name) for name in REQUIRED_BINDINGS}
