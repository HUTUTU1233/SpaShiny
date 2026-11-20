# Actual feature UI extracted from production. Feature: gene_enrichment.
from spashiny._shared import runtime_globals as _spashiny_globals


def ui(_spashiny_ctx):
    return _spashiny_globals.ui.nav_panel(
        "Gene CSV Enrichment",
        _spashiny_globals.ui.div(
            _spashiny_globals.ui.h4("Gene Enrichment CSV"),
            _spashiny_globals.ui.p(
                "Upload a CSV/TSV/TXT file with a gene column. Optional columns such as p_val_adj, logFC, and State are preserved as input context.",
                class_="cloud-muted",
            ),
            _spashiny_globals.ui.input_file(
                "gene_enrichment_csv",
                "Upload Gene CSV",
                accept=[".csv", ".tsv", ".txt"],
                multiple=False,
            ),
            _spashiny_globals.ui.output_ui("gene_enrichment_gene_column_selector"),
            _spashiny_globals.ui.input_selectize(
                "gene_enrichment_database_ids",
                "Databases",
                choices={
                    "hallmark": "MSigDB Hallmark Mouse",
                    "reactome": "Reactome Mouse",
                    "go_bp": "GO Biological Process",
                    "go_cc": "GO Cellular Component",
                    "go_mf": "GO Molecular Function",
                },
                selected=["hallmark", "reactome", "go_bp", "go_cc", "go_mf"],
                multiple=True,
                options={"plugins": ["remove_button"], "placeholder": "Select local databases..."},
            ),
            _spashiny_globals.ui.input_numeric(
                "gene_enrichment_fdr_cutoff", "FDR cutoff", value=0.05, min=0, max=1, step=0.01
            ),
            _spashiny_globals.ui.input_action_button(
                "run_gene_enrichment_csv", "Run Gene Enrichment", class_="btn btn-primary"
            ),
            _spashiny_globals.ui.input_action_button(
                "run_gene_enrichment_marker",
                "Run from current Marker Analysis gene_df",
                class_="btn btn-secondary",
            ),
            _spashiny_globals.ui.div(
                _spashiny_globals.ui.output_text("gene_enrichment_status"),
                class_="cloud-muted",
                style="margin-top: 10px;",
            ),
            _spashiny_globals.ui.output_ui("gene_enrichment_job_results"),
            class_="apple-card",
        ),
    )
