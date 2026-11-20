"""Compatibility import path; implementation lives in feature UI/server files."""
from spashiny._shared.feature_support.ssh_module import *
from spashiny._shared.feature_support import ssh_module as _shared
globals().update({k:v for k,v in vars(_shared).items() if not k.startswith("__")})
from spashiny.features.connection.ui import ssh_module_ui
from spashiny.features.connection.ui import ssh_status_indicator_ui
from spashiny.features.connection.server import ssh_module_server
