"""Compatibility import path; implementation lives in feature UI/server files."""
from spashiny._shared.feature_support.toi_feature_module import *
from spashiny._shared.feature_support import toi_feature_module as _shared
globals().update({k:v for k,v in vars(_shared).items() if not k.startswith("__")})
from spashiny.features.toi.server import register_toi_feature_server
