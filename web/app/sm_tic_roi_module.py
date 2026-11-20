"""Compatibility import path; implementation lives in feature UI/server files."""
from spashiny._shared.feature_support.sm_tic_roi_module import *
from spashiny._shared.feature_support import sm_tic_roi_module as _shared
globals().update({k:v for k,v in vars(_shared).items() if not k.startswith("__")})
from spashiny.features.sm_tic_roi.ui import sm_tic_roi_module_ui
from spashiny.features.sm_tic_roi.server import sm_tic_roi_module_server
