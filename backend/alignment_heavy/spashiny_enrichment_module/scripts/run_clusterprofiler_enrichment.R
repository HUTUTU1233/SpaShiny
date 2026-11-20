suppressPackageStartupMessages({
  library(clusterProfiler)
  library(enrichplot)
  library(KEGGREST)
  library(dplyr)
  library(readr)
  library(readxl)
  library(ggplot2)
})

`%||%` <- function(a, b) {
  if (!is.null(a)) a else b
}

parse_args <- function() {
  args <- commandArgs(trailingOnly = TRUE)
  res <- list()
  i <- 1

  while (i <= length(args)) {
    key <- gsub("^--", "", args[i])

    if (i + 1 <= length(args) && !grepl("^--", args[i + 1])) {
      res[[key]] <- args[i + 1]
      i <- i + 2
    } else {
      res[[key]] <- TRUE
      i <- i + 1
    }
  }

  res
}

read_table_auto <- function(path) {
  ext <- tolower(tools::file_ext(path))

  if (ext %in% c("xlsx", "xls")) {
    df <- readxl::read_excel(path)
    return(as.data.frame(df))
  }

  if (ext == "csv") {
    return(suppressMessages(readr::read_csv(path, show_col_types = FALSE)))
  }

  if (ext %in% c("tsv", "txt")) {
    return(suppressMessages(readr::read_tsv(path, show_col_types = FALSE)))
  }

  stop("Unsupported file type: ", ext)
}

standardize_columns <- function(df) {
  replace_if_missing <- function(target, candidates) {
    if (!(target %in% colnames(df))) {
      hit <- candidates[candidates %in% colnames(df)]
      if (length(hit) > 0) {
        colnames(df)[colnames(df) == hit[1]] <<- target
      }
    }
  }

  replace_if_missing("gene", c("Gene", "GENE", "symbol", "SYMBOL", "gene_symbol", "GeneSymbol"))
  replace_if_missing("metabolite", c("Metabolite", "METABOLITE", "compound", "Compound", "name", "Name"))
  replace_if_missing("KEGG.ID", c("KEGG ID", "KEGGID", "kegg_id", "kegg id", "KEGG", "kegg"))
  replace_if_missing("p_val_adj", c("padj", "FDR", "qvalue", "q_value", "adj.P.Val", "p.adjust"))
  replace_if_missing("log2(Fold Change)", c("logFC", "avg_log2FC", "avg_logFC", "log2FC", "log2_fold_change"))
  replace_if_missing("State", c("state", "Regulation", "regulation", "change", "Change", "status", "Status"))

  df
}

prepare_ids <- function(
    df,
    id_col,
    state_col = "State",
    p_col = "p_val_adj",
    logfc_col = "log2(Fold Change)",
    mode = "all",
    top_n = 300,
    id_prefix = NULL
) {
  df <- standardize_columns(df)

  if (!(id_col %in% colnames(df))) {
    stop("Input table must contain column: ", id_col)
  }

  if (!(state_col %in% colnames(df))) {
    if (logfc_col %in% colnames(df)) {
      logfc <- suppressWarnings(as.numeric(df[[logfc_col]]))
      df[[state_col]] <- ifelse(logfc > 0, "Up", ifelse(logfc < 0, "Down", "Non-significant"))
    } else {
      df[[state_col]] <- "Differential"
    }
  }

  df[[state_col]] <- as.character(df[[state_col]])
  df$.state_tmp <- tolower(df[[state_col]])

  df <- df %>%
    filter(!.state_tmp %in% c(
      "non-significant", "nonsignificant", "not significant", "ns", "no", "none"
    ))

  if (mode == "up") {
    df <- df %>% filter(.state_tmp %in% c("up", "up-regulated", "upregulated"))
  }

  if (mode == "down") {
    df <- df %>% filter(.state_tmp %in% c("down", "down-regulated", "downregulated"))
  }

  if (p_col %in% colnames(df)) {
    df[[p_col]] <- suppressWarnings(as.numeric(df[[p_col]]))
    df <- df %>% arrange(.data[[p_col]])
  }

  top_n <- suppressWarnings(as.numeric(top_n))
  if (!is.na(top_n) && nrow(df) > top_n) {
    df <- df %>% slice_head(n = top_n)
  }

  ids <- unique(as.character(df[[id_col]]))
  ids <- ids[!is.na(ids)]
  ids <- ids[ids != ""]

  ids <- gsub("^cpd:", "", ids)
  ids <- gsub("^ko:", "", ids)
  ids <- gsub("^path:", "", ids)
  ids <- trimws(ids)

  if (!is.null(id_prefix)) {
    ids <- ids[grepl(id_prefix, ids)]
  }

  ids
}

get_orgdb <- function(species) {
  if (species == "mmu") {
    suppressPackageStartupMessages(library(org.Mm.eg.db))
    return(org.Mm.eg.db)
  }

  if (species == "hsa") {
    suppressPackageStartupMessages(library(org.Hs.eg.db))
    return(org.Hs.eg.db)
  }

  stop("Unsupported species. Use mmu or hsa.")
}

convert_gene_to_entrez <- function(genes, species = "mmu", id_type = "SYMBOL") {
  orgdb <- get_orgdb(species)
  id_type <- toupper(id_type)

  if (id_type == "ENTREZID") {
    return(unique(as.character(genes)))
  }

  converted <- suppressMessages(
    clusterProfiler::bitr(
      genes,
      fromType = id_type,
      toType = "ENTREZID",
      OrgDb = orgdb
    )
  )

  if (is.null(converted) || nrow(converted) == 0) {
    stop("No genes could be converted to ENTREZID. Please check gene ID type and species.")
  }

  unique(as.character(converted$ENTREZID))
}

save_empty_result <- function(outdir, message = "No enrichment result found.") {
  dir.create(outdir, recursive = TRUE, showWarnings = FALSE)
  empty_df <- data.frame(Message = message)
  readr::write_csv(empty_df, file.path(outdir, "enrichment_result.csv"))

  p <- ggplot() +
    annotate("text", x = 0, y = 0, label = message, size = 5) +
    theme_void()

  ggsave(
    filename = file.path(outdir, "dotplot.png"),
    plot = p,
    width = 8,
    height = 5,
    dpi = 300,
    bg = "white"
  )

  ggsave(
    filename = file.path(outdir, "dotplot.pdf"),
    plot = p,
    width = 8,
    height = 5,
    bg = "white"
  )
}

save_enrichment_result <- function(enrich_res, outdir, title = "Enrichment", show_category = 20) {
  dir.create(outdir, recursive = TRUE, showWarnings = FALSE)

  if (is.null(enrich_res)) {
    save_empty_result(outdir, "No enrichment result found.")
    return(invisible(NULL))
  }

  result_df <- as.data.frame(enrich_res)

  if (is.null(result_df) || nrow(result_df) == 0) {
    save_empty_result(outdir, "No significant enrichment result found.")
    return(invisible(NULL))
  }

  readr::write_csv(result_df, file.path(outdir, "enrichment_result.csv"))

  show_category <- suppressWarnings(as.numeric(show_category))
  if (is.na(show_category)) show_category <- 20
  show_n <- min(show_category, nrow(result_df))

  p <- enrichplot::dotplot(enrich_res, showCategory = show_n) +
    ggtitle(title) +
    theme_bw(base_size = 12) +
    theme(
      plot.title = element_text(hjust = 0.5, face = "bold"),
      axis.text.y = element_text(size = 9)
    )

  ggsave(
    filename = file.path(outdir, "dotplot.png"),
    plot = p,
    width = 8,
    height = 6,
    dpi = 300,
    bg = "white"
  )

  ggsave(
    filename = file.path(outdir, "dotplot.pdf"),
    plot = p,
    width = 8,
    height = 6,
    bg = "white"
  )
}

run_gene_enrichment <- function(args) {
  input_file <- args$input
  outdir <- args$outdir

  species <- args$species %||% "mmu"
  gene_col <- args$gene_col %||% "gene"
  id_type <- args$id_type %||% "SYMBOL"
  analysis <- args$analysis %||% "GO_BP"
  mode <- args$feature_mode %||% "all"
  top_n <- as.numeric(args$top_n %||% 300)
  pvalue_cutoff <- as.numeric(args$pvalue_cutoff %||% 0.05)
  qvalue_cutoff <- as.numeric(args$qvalue_cutoff %||% 0.2)
  show_category <- as.numeric(args$show_category %||% 20)
  state_col <- args$state_col %||% "State"
  p_col <- args$p_col %||% "p_val_adj"
  logfc_col <- args$logfc_col %||% "log2(Fold Change)"

  dir.create(outdir, recursive = TRUE, showWarnings = FALSE)

  df <- read_table_auto(input_file)
  df <- standardize_columns(df)

  genes <- prepare_ids(
    df = df,
    id_col = gene_col,
    state_col = state_col,
    p_col = p_col,
    logfc_col = logfc_col,
    mode = mode,
    top_n = top_n,
    id_prefix = NULL
  )

  if (length(genes) < 3) {
    save_empty_result(outdir, "Too few genes for enrichment analysis.")
    return(invisible(NULL))
  }

  entrez_ids <- convert_gene_to_entrez(
    genes = genes,
    species = species,
    id_type = id_type
  )

  if (length(entrez_ids) < 3) {
    save_empty_result(outdir, "Too few converted ENTREZID genes for enrichment analysis.")
    return(invisible(NULL))
  }

  orgdb <- get_orgdb(species)

  if (analysis %in% c("GO_BP", "GO_CC", "GO_MF")) {
    ont <- gsub("^GO_", "", analysis)

    enrich_res <- suppressMessages(
      clusterProfiler::enrichGO(
        gene = entrez_ids,
        OrgDb = orgdb,
        keyType = "ENTREZID",
        ont = ont,
        pAdjustMethod = "BH",
        pvalueCutoff = pvalue_cutoff,
        qvalueCutoff = qvalue_cutoff,
        readable = TRUE
      )
    )

    save_enrichment_result(
      enrich_res,
      outdir,
      title = paste0("Gene Enrichment: ", analysis),
      show_category = show_category
    )

  } else if (analysis == "KEGG") {
    enrich_res <- suppressMessages(
      clusterProfiler::enrichKEGG(
        gene = entrez_ids,
        organism = species,
        keyType = "ncbi-geneid",
        pAdjustMethod = "BH",
        pvalueCutoff = pvalue_cutoff,
        qvalueCutoff = qvalue_cutoff
      )
    )

    if (!is.null(enrich_res) && nrow(as.data.frame(enrich_res)) > 0) {
      enrich_res <- suppressMessages(
        clusterProfiler::setReadable(
          enrich_res,
          OrgDb = orgdb,
          keyType = "ENTREZID"
        )
      )
    }

    save_enrichment_result(
      enrich_res,
      outdir,
      title = "Gene Enrichment: KEGG",
      show_category = show_category
    )

  } else {
    stop("Unsupported gene enrichment analysis: ", analysis)
  }
}

build_kegg_compound_pathway_db <- function(cache_file = NULL) {
  if (!is.null(cache_file) && file.exists(cache_file)) {
    return(readRDS(cache_file))
  }

  cpd2path <- KEGGREST::keggLink("pathway", "compound")

  term2gene <- data.frame(
    pathway = sub("^path:", "", as.character(cpd2path)),
    compound = sub("^cpd:", "", names(cpd2path)),
    stringsAsFactors = FALSE
  )

  pathway_names <- KEGGREST::keggList("pathway")

  term2name <- data.frame(
    pathway = sub("^path:", "", names(pathway_names)),
    name = as.character(pathway_names),
    stringsAsFactors = FALSE
  )

  term2gene$pathway <- sub("^[a-z]{3}", "map", term2gene$pathway)
  term2name$pathway <- sub("^[a-z]{3}", "map", term2name$pathway)

  global_maps <- c("map01100", "map01110", "map01120")
  term2gene <- term2gene %>% filter(!pathway %in% global_maps)
  term2name <- term2name %>% filter(!pathway %in% global_maps)

  db <- list(
    TERM2GENE = unique(term2gene),
    TERM2NAME = unique(term2name)
  )

  if (!is.null(cache_file)) {
    dir.create(dirname(cache_file), recursive = TRUE, showWarnings = FALSE)
    saveRDS(db, cache_file)
  }

  db
}

run_metabolite_enrichment <- function(args) {
  input_file <- args$input
  outdir <- args$outdir

  kegg_col <- args$kegg_col %||% "KEGG.ID"
  mode <- args$feature_mode %||% "all"
  top_n <- as.numeric(args$top_n %||% 300)
  pvalue_cutoff <- as.numeric(args$pvalue_cutoff %||% 0.05)
  qvalue_cutoff <- as.numeric(args$qvalue_cutoff %||% 0.2)
  show_category <- as.numeric(args$show_category %||% 20)
  state_col <- args$state_col %||% "State"
  p_col <- args$p_col %||% "p_val_adj"
  logfc_col <- args$logfc_col %||% "log2(Fold Change)"

  dir.create(outdir, recursive = TRUE, showWarnings = FALSE)

  df <- read_table_auto(input_file)
  df <- standardize_columns(df)

  compounds <- prepare_ids(
    df = df,
    id_col = kegg_col,
    state_col = state_col,
    p_col = p_col,
    logfc_col = logfc_col,
    mode = mode,
    top_n = top_n,
    id_prefix = "^C[0-9]+"
  )

  if (length(compounds) < 3) {
    save_empty_result(outdir, "Too few KEGG Compound IDs for enrichment analysis.")
    return(invisible(NULL))
  }

  cache_file <- file.path(dirname(outdir), "kegg_compound_pathway_cache.rds")
  kegg_db <- build_kegg_compound_pathway_db(cache_file = cache_file)

  enrich_res <- suppressMessages(
    clusterProfiler::enricher(
      gene = compounds,
      TERM2GENE = kegg_db$TERM2GENE,
      TERM2NAME = kegg_db$TERM2NAME,
      pAdjustMethod = "BH",
      pvalueCutoff = pvalue_cutoff,
      qvalueCutoff = qvalue_cutoff,
      minGSSize = 2,
      maxGSSize = 500
    )
  )

  save_enrichment_result(
    enrich_res,
    outdir,
    title = "Metabolite KEGG Enrichment",
    show_category = show_category
  )
}

main <- function() {
  args <- parse_args()
  mode <- args$mode %||% "gene"

  if (mode == "gene") {
    run_gene_enrichment(args)
  } else if (mode == "metabolite") {
    run_metabolite_enrichment(args)
  } else {
    stop("Unsupported mode: ", mode)
  }
}

main()
