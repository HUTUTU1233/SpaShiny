"""Compatibility UI launcher; scientific workers retain their own entrypoints."""
from pathlib import Path
import importlib
import runpy
import sys

_project_root = Path(__file__).resolve().parents[3]
_web_root = _project_root / "web"
_web_app = _web_root / "app"
for _directory in (_web_root, _web_app):
    _directory_text = str(_directory)
    if _directory_text in sys.path:
        sys.path.remove(_directory_text)
    sys.path.insert(0, _directory_text)

# A backend proxy may already have loaded its own cloud package. Keep those
# modules and use the Web package only for UI dependencies missing there.
_cloud = importlib.import_module("cloud")
_web_cloud = str(_web_root / "cloud")
if _web_cloud not in _cloud.__path__:
    _cloud.__path__.append(_web_cloud)

app = runpy.run_path(str(_web_app / "ST-SM.py"))["app"]

