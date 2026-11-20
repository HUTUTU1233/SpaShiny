from shiny import module, ui


ENRICHMENT_MODULE_CSS = """
<style>
.enrich-shell {
    padding: 12px 8px 36px 8px;
    max-width: 1480px;
    margin: 0 auto;
}
.enrich-hero {
    background: linear-gradient(135deg, rgba(255,255,255,0.98), rgba(247,249,252,0.96));
    border: 1px solid rgba(0,0,0,0.06);
    border-radius: 26px;
    box-shadow: 0 12px 34px rgba(15, 23, 42, 0.06);
    padding: 26px 30px;
    margin-bottom: 20px;
}
.enrich-title {
    font-size: 1.9rem;
    font-weight: 760;
    color: #111827;
    margin-bottom: 8px;
}
.enrich-subtitle {
    font-size: 0.98rem;
    color: #5f6b7a;
    line-height: 1.65;
    max-width: 1000px;
}
.enrich-card {
    background: #ffffff;
    border: 1px solid rgba(0,0,0,0.06);
    border-radius: 22px;
    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.045);
    padding: 22px;
    margin-bottom: 18px;
}
.enrich-card-title {
    font-size: 1.08rem;
    font-weight: 720;
    color: #111827;
    margin-bottom: 14px;
}
.enrich-grid-2 {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 18px;
}
.enrich-grid-3 {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 14px;
}
.enrich-note {
    font-size: 0.88rem;
    color: #6b7280;
    line-height: 1.6;
    margin-top: 8px;
}
.enrich-status {
    padding: 12px 14px;
    border-radius: 16px;
    background: #f8fafc;
    border: 1px solid rgba(0,0,0,0.06);
    color: #374151;
    font-size: 0.92rem;
    white-space: pre-wrap;
}
.enrich-btn-row {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    margin-top: 12px;
}
.enrich-table-wrap {
    overflow-x: auto;
    max-height: 520px;
    border-radius: 16px;
}
.enrich-plot-box {
    width: 100%;
    overflow: auto;
    border-radius: 18px;
    background: #ffffff;
}
.enrich-small-title {
    font-size: 0.94rem;
    font-weight: 650;
    color: #1f2937;
    margin: 6px 0 10px 0;
}
@media (max-width: 980px) {
    .enrich-grid-2,
    .enrich-grid-3 {
        grid-template-columns: 1fr;
    }
}
</style>
"""


@module.ui
def enrichment_module_ui():
    return ui.div(
        ui.HTML(ENRICHMENT_MODULE_CSS),

        ui.div(
            ui.div("Enrichment Analysis", class_="enrich-title"),
            ui.div(
                "Run gene GO/KEGG enrichment and metabolite KEGG compound pathway enrichment. "
                "Upload a differential result table, choose feature direction, and download the enrichment table and DotPlot.",
                class_="enrich-subtitle",
            ),
            class_="enrich-hero",
        ),

        ui.navset_tab(
            ui.nav_panel(
                "Gene Enrichment",

                ui.div(
                    ui.div("Input file", class_="enrich-card-title"),
                    ui.input_file(
                        "gene_file",
                        "Differential gene table",
                        accept=[".csv", ".tsv", ".txt", ".xlsx", ".xls"],
                        multiple=False,
                    ),
                    ui.div(
                        "Recommended columns: gene, p_val_adj, log2(Fold Change), State. "
                        "State supports Up / Down / Non-significant. If State is absent, direction will be inferred from log2FC.",
                        class_="enrich-note",
                    ),
                    ui.div(
                        ui.download_button("download_gene_example_csv", "Download Example CSV"),
                        class_="enrich-btn-row",
                    ),
                    class_="enrich-card",
                ),

                ui.div(
                    ui.div("Parameters", class_="enrich-card-title"),
                    ui.div(
                        ui.input_select(
                            "gene_species",
                            "Species",
                            choices={"mmu": "Mouse / mmu", "hsa": "Human / hsa"},
                            selected="mmu",
                        ),
                        ui.input_select(
                            "gene_id_type",
                            "Gene ID type",
                            choices={
                                "SYMBOL": "Gene Symbol",
                                "ENTREZID": "Entrez ID",
                                "ENSEMBL": "Ensembl ID",
                            },
                            selected="SYMBOL",
                        ),
                        ui.input_select(
                            "gene_analysis",
                            "Enrichment type",
                            choices={
                                "GO_BP": "GO Biological Process",
                                "GO_CC": "GO Cellular Component",
                                "GO_MF": "GO Molecular Function",
                                "KEGG": "KEGG Pathway",
                            },
                            selected="GO_BP",
                        ),
                        class_="enrich-grid-3",
                    ),
                    ui.div(
                        ui.input_select(
                            "gene_feature_mode",
                            "Feature mode",
                            choices={
                                "all": "All differential features",
                                "up": "Up-regulated only",
                                "down": "Down-regulated only",
                            },
                            selected="all",
                        ),
                        ui.input_numeric(
                            "gene_top_n",
                            "Top N by adjusted p value",
                            value=300,
                            min=10,
                            max=5000,
                            step=10,
                        ),
                        ui.input_text("gene_col", "Gene column", value="gene"),
                        class_="enrich-grid-3",
                    ),
                    ui.div(
                        ui.input_text("gene_p_col", "Adjusted p value column", value="p_val_adj"),
                        ui.input_text("gene_logfc_col", "log2FC column", value="log2(Fold Change)"),
                        ui.input_text("gene_state_col", "State column", value="State"),
                        class_="enrich-grid-3",
                    ),
                    ui.div(
                        ui.input_numeric("gene_pvalue_cutoff", "p value cutoff", value=0.05, min=0, max=1, step=0.01),
                        ui.input_numeric("gene_qvalue_cutoff", "q value cutoff", value=0.20, min=0, max=1, step=0.01),
                        ui.input_numeric("gene_show_category", "Show top categories", value=20, min=5, max=50, step=1),
                        class_="enrich-grid-3",
                    ),
                    ui.div(
                        ui.input_action_button(
                            "run_gene_enrichment",
                            "Run Gene Enrichment",
                            class_="btn btn-dark",
                        ),
                        class_="enrich-btn-row",
                    ),
                    class_="enrich-card",
                ),

                ui.div(
                    ui.div("Status", class_="enrich-card-title"),
                    ui.div(ui.output_ui("gene_status"), class_="enrich-status"),
                    class_="enrich-card",
                ),

                ui.div(
                    ui.div("DotPlot", class_="enrich-card-title"),
                    ui.div(ui.output_image("gene_dotplot"), class_="enrich-plot-box"),
                    ui.div(
                        ui.download_button("download_gene_result", "Download result table"),
                        ui.download_button("download_gene_dotplot", "Download DotPlot PDF"),
                        class_="enrich-btn-row",
                    ),
                    class_="enrich-card",
                ),

                ui.div(
                    ui.div("Result table", class_="enrich-card-title"),
                    ui.div(ui.output_table("gene_result_table"), class_="enrich-table-wrap"),
                    class_="enrich-card",
                ),
            ),

            ui.nav_panel(
                "Metabolite Enrichment",

                ui.div(
                    ui.div("Input file", class_="enrich-card-title"),
                    ui.input_file(
                        "metab_file",
                        "Differential metabolite table",
                        accept=[".csv", ".tsv", ".txt", ".xlsx", ".xls"],
                        multiple=False,
                    ),
                    ui.div(
                        "Required column: KEGG.ID. Values should be KEGG Compound IDs such as C00186, C00158, C00031. "
                        "Recommended columns: p_val_adj, log2(Fold Change), State.",
                        class_="enrich-note",
                    ),
                    ui.div(
                        "Metabolite annotation resource: ",
                        ui.tags.a(
                            "MetDNA",
                            href="http://metdna.zhulab.cn/",
                            target="_blank",
                            rel="noopener noreferrer",
                        ),
                        " (Zhengjiang Zhu lab metabolite annotation website).",
                        class_="enrich-note",
                    ),
                    ui.div(
                        "For local putative metabolite annotation of h5ad files, use the "
                        "Metabolite Annotation / Metabolite Annotation tab below.",
                        class_="enrich-note",
                    ),
                    ui.div(
                        ui.download_button("download_metab_example_csv", "Download Example CSV"),
                        class_="enrich-btn-row",
                    ),
                    class_="enrich-card",
                ),

                ui.div(
                    ui.div("Parameters", class_="enrich-card-title"),
                    ui.div(
                        ui.input_select(
                            "metab_feature_mode",
                            "Feature mode",
                            choices={
                                "all": "All differential features",
                                "up": "Up-regulated only",
                                "down": "Down-regulated only",
                            },
                            selected="all",
                        ),
                        ui.input_numeric(
                            "metab_top_n",
                            "Top N by adjusted p value",
                            value=300,
                            min=10,
                            max=5000,
                            step=10,
                        ),
                        ui.input_text("metab_kegg_col", "KEGG Compound ID column", value="KEGG.ID"),
                        class_="enrich-grid-3",
                    ),
                    ui.div(
                        ui.input_text("metab_p_col", "Adjusted p value column", value="p_val_adj"),
                        ui.input_text("metab_logfc_col", "log2FC column", value="log2(Fold Change)"),
                        ui.input_text("metab_state_col", "State column", value="State"),
                        class_="enrich-grid-3",
                    ),
                    ui.div(
                        ui.input_numeric("metab_pvalue_cutoff", "p value cutoff", value=0.05, min=0, max=1, step=0.01),
                        ui.input_numeric("metab_qvalue_cutoff", "q value cutoff", value=0.20, min=0, max=1, step=0.01),
                        ui.input_numeric("metab_show_category", "Show top categories", value=20, min=5, max=50, step=1),
                        class_="enrich-grid-3",
                    ),
                    ui.div(
                        ui.input_action_button(
                            "run_metab_enrichment",
                            "Run Metabolite Enrichment",
                            class_="btn btn-dark",
                        ),
                        class_="enrich-btn-row",
                    ),
                    class_="enrich-card",
                ),

                ui.div(
                    ui.div("Status", class_="enrich-card-title"),
                    ui.div(ui.output_ui("metab_status"), class_="enrich-status"),
                    class_="enrich-card",
                ),

                ui.div(
                    ui.div("DotPlot", class_="enrich-card-title"),
                    ui.div(ui.output_image("metab_dotplot"), class_="enrich-plot-box"),
                    ui.div(
                        ui.download_button("download_metab_result", "Download result table"),
                        ui.download_button("download_metab_dotplot", "Download DotPlot PDF"),
                        class_="enrich-btn-row",
                    ),
                    class_="enrich-card",
                ),

                ui.div(
                    ui.div("Result table", class_="enrich-card-title"),
                    ui.div(ui.output_table("metab_result_table"), class_="enrich-table-wrap"),
                    class_="enrich-card",
                ),
            ),

            ui.nav_panel(
                "Metabolite Annotation / Metabolite Annotation",

                ui.div(
                    ui.div("Putative metabolite annotation", class_="enrich-card-title"),
                    ui.div(
                        "Upload a spatial metabolomics or joint omics .h5ad file and a metabolite annotation table. "
                        "The backend writes putative annotation candidates into adata.var and exports an annotated h5ad. "
                        "This is candidate annotation based on feature_id/name, m/z tolerance, and adduct assumptions; "
                        "it is not confirmed identification.",
                        class_="enrich-note",
                    ),
                    class_="enrich-card",
                ),

                ui.div(
                    ui.div("Input files", class_="enrich-card-title"),
                    ui.div(
                        ui.input_file(
                            "annot_h5ad",
                            "Spatial metabolomics / joint omics h5ad",
                            accept=[".h5ad"],
                            multiple=False,
                        ),
                        ui.input_file(
                            "annot_table",
                            "Metabolite annotation table",
                            accept=[".csv", ".tsv", ".txt", ".xlsx", ".xls"],
                            multiple=False,
                        ),
                        class_="enrich-grid-2",
                    ),
                    ui.div(
                        "Supported optional columns include feature_id, name, mz, observed_mz, exact_mass, neutral_mass, "
                        "polarity, ion_mode, adduct, accession, metabolite_name, compound_name, iupac_name, "
                        "chemical_formula, formula, kegg, hmdb, lipidmaps, direct_parent, class, and sub_class.",
                        class_="enrich-note",
                    ),
                    class_="enrich-card",
                ),

                ui.div(
                    ui.div("Parameters", class_="enrich-card-title"),
                    ui.div(
                        ui.input_select(
                            "annot_mode",
                            "Annotation mode",
                            choices={
                                "auto": "auto: feature_id, observed m/z, then exact_mass + adduct",
                                "feature_id": "feature_id: direct merge by feature_id/name",
                                "observed_mz": "observed_mz: match annotation mz/observed_mz",
                                "exact_mass": "exact_mass: generate theoretical m/z from exact_mass + adduct",
                            },
                            selected="auto",
                        ),
                        ui.input_numeric(
                            "annot_tolerance_ppm",
                            "ppm tolerance",
                            value=5,
                            min=0.1,
                            max=100,
                            step=0.1,
                        ),
                        ui.input_numeric(
                            "annot_top_n",
                            "top_n candidates",
                            value=1,
                            min=1,
                            max=50,
                            step=1,
                        ),
                        class_="enrich-grid-3",
                    ),
                    ui.input_checkbox(
                        "annot_only_sm",
                        "Only annotate SM/metabolite features when modality/type metadata is available",
                        value=True,
                    ),
                    ui.div(
                        ui.input_text(
                            "annot_var_mz_col",
                            "AnnData var m/z column override (optional)",
                            value="",
                            placeholder="auto",
                        ),
                        ui.input_text(
                            "annot_anno_mz_col",
                            "Annotation table m/z column override (optional)",
                            value="",
                            placeholder="auto",
                        ),
                        ui.input_text(
                            "annot_polarity_col",
                            "Annotation polarity/type column override (optional)",
                            value="",
                            placeholder="auto",
                        ),
                        class_="enrich-grid-3",
                    ),
                    ui.div(
                        ui.input_action_button(
                            "run_metabolite_annotation",
                            "Run Putative Metabolite Annotation",
                            class_="btn btn-dark",
                        ),
                        class_="enrich-btn-row",
                    ),
                    class_="enrich-card",
                ),

                ui.div(
                    ui.div("Status and result paths", class_="enrich-card-title"),
                    ui.div(ui.output_ui("annotation_status"), class_="enrich-status"),
                    ui.div(
                        ui.download_button("download_annotated_h5ad", "Download annotated h5ad"),
                        ui.download_button("download_annotation_summary", "Download summary JSON"),
                        ui.download_button("download_annotation_candidates", "Download candidate CSV"),
                        ui.download_button("download_annotation_log", "Download run log"),
                        class_="enrich-btn-row",
                    ),
                    class_="enrich-card",
                ),

                ui.div(
                    ui.div("Candidate preview", class_="enrich-card-title"),
                    ui.div(ui.output_table("annotation_candidate_table"), class_="enrich-table-wrap"),
                    class_="enrich-card",
                ),
            ),
        ),

        class_="enrich-shell",
    )
