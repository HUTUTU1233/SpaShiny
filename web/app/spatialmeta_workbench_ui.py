"""Compatibility import path; implementation lives in feature UI/server files."""
from spashiny._shared.feature_support.spatialmeta_workbench_ui import *
from spashiny._shared.feature_support import spatialmeta_workbench_ui as _shared
globals().update({k:v for k,v in vars(_shared).items() if not k.startswith("__")})
from spashiny.features.network.ui import network_panel_ui
from spashiny.features.one_stop.ui import one_stop_ui
from spashiny.features.workbench.server import register_workbench
