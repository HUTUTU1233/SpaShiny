"""Compatibility entrypoint for the modular SpaShiny export."""
from pathlib import Path
import sys
app_dir=Path(__file__).resolve().parent
for directory in (app_dir,app_dir.parent):
    if str(directory) not in sys.path:sys.path.insert(0,str(directory))
from spashiny.application import app
