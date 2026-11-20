"""Compatibility import path; implementation lives in feature UI/server files."""
from spashiny._shared.feature_support.river_st_module import *
from spashiny._shared.feature_support import river_st_module as _shared
globals().update({k:v for k,v in vars(_shared).items() if not k.startswith("__")})
from spashiny.features.river.ui import river_st_module_ui
from spashiny.features.river.server import river_st_module_server
