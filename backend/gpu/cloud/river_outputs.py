"""Explicit River-only public output contract, also used by host publication."""
RIVER_PUBLIC_OUTPUTS = (
    'river_summary.json','river_execution_trace.json',
    'river_combined_plot.png','river_combined_plot.pdf',
    'river_final_rank_temporal.csv','river_top200_genes.csv','river_final_rank_temporal.npy',
    'river_ig_temporal.npy','river_dl_temporal.npy','river_sl_temporal.npy',
    'river_plot_adata.h5ad','river_plot_adata_features.csv',
    'river_selected_gene_temporal.png','river_selected_gene_temporal.pdf','river_selected_gene_temporal.csv',
    'river_selected_gene_spatial.png','river_selected_gene_spatial.pdf',
)
RIVER_PUBLIC_RUNTIME_FILES = ('summary.json','manifest.json','session_info.txt')
RIVER_PUBLIC_LOGS = ('river_runner.log','stdout.log','stderr.log')
