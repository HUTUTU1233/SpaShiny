# Actual feature UI extracted from production. Feature: metabolite_enrichment.
from spashiny._shared import runtime_globals as _spashiny_globals


def ui(_spashiny_ctx):
    return _spashiny_globals.ui.nav_panel(
        "Metabolite CSV Enrichment",
        _spashiny_globals.ui.div(
            _spashiny_globals.ui.h4("Metabolite Enrichment CSV"),
            _spashiny_globals.ui.p(
                "Offline metabolite enrichment currently requires KEGG Compound IDs and a local compound-pathway membership table. Names alone are reported as unmapped and are not guessed.",
                class_="cloud-muted",
            ),
            _spashiny_globals.ui.input_file(
                "metabolite_enrichment_csv",
                "Upload Metabolite CSV",
                accept=[".csv", ".tsv", ".txt"],
                multiple=False,
            ),
            _spashiny_globals.ui.output_ui("metabolite_enrichment_kegg_column_selector"),
            _spashiny_globals.ui.output_ui("metabolite_enrichment_name_column_selector"),
            _spashiny_globals.ui.input_numeric(
                "metabolite_enrichment_fdr_cutoff",
                "FDR cutoff",
                value=0.05,
                min=0,
                max=1,
                step=0.01,
            ),
            _spashiny_globals.ui.input_action_button(
                "run_metabolite_enrichment_csv",
                "Run Metabolite Enrichment",
                class_="btn btn-primary",
            ),
            _spashiny_globals.ui.input_action_button(
                "run_metabolite_enrichment_marker",
                "Run from current Marker Analysis met_df",
                class_="btn btn-secondary",
            ),
            _spashiny_globals.ui.div(
                _spashiny_globals.ui.output_text("metabolite_enrichment_status"),
                class_="cloud-muted",
                style="margin-top: 10px;",
            ),
            _spashiny_globals.ui.output_ui("metabolite_enrichment_job_results"),
            class_="apple-card",
        ),
    )
