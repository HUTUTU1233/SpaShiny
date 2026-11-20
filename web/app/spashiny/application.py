"""Modular application entrypoint; production remains unchanged."""

from pathlib import Path
from ._shared import runtime_globals as g
from .shell import app_ui
from .bootstrap import server

g.app_dir = Path(g.LEGACY_ENTRYPOINT_FILE).parent
app = g.App(app_ui, server, static_assets=g.app_dir / "www")
g.app_ui = app_ui
g.server = server
g.app = app
