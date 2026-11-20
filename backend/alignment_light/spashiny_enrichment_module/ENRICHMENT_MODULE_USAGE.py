"""
Copy these lines into your main Python Shiny app, for example ST-SM.py.

Directory after copying files:
SpaShiny/
|-- ST-SM.py
|-- modules/
|   |-- enrichment_module_ui.py
|   `-- enrichment_module_server.py
`-- scripts/
    `-- run_clusterprofiler_enrichment.R
"""

from pathlib import Path
from shiny import ui

from modules.enrichment_module_ui import enrichment_module_ui
from modules.enrichment_module_server import enrichment_module_server


# =========================
# 1. Add this nav panel to app_ui
# =========================

ui.nav_panel(
    "Enrichment Analysis",
    enrichment_module_ui("enrichment")
)


# Example:
# app_ui = ui.page_navbar(
#     ui.nav_panel("Home", home_ui),
#     ui.nav_panel("ST", st_ui),
#     ui.nav_panel("SM", sm_ui),
#     ui.nav_panel("ST-SM", stsm_ui),
#     ui.nav_panel("Enrichment Analysis", enrichment_module_ui("enrichment")),
#     title="SpaShiny"
# )


# =========================
# 2. Add this inside server()
# =========================

def server(input, output, session):
    BASE_DIR = Path(__file__).parent

    enrichment_module_server(
        "enrichment",
        base_dir=BASE_DIR,
        rscript_bin="Rscript"
    )

    # Keep your original server code below.
