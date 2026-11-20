from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os
import re
import sqlite3
import zipfile
from typing import Any

from .common import (
    CPUWorkflowContext,
    CPUWorkflowError,
    find_local_db_path,
    read_h5ad,
    read_table,
    select_asset,
    save_figure_bundle,
    sha256_file,
    table_gene_list,
    write_csv,
    write_json,
)


DEFAULT_ENRICHMENT_ROOT = Path(os.environ.get("SPASHINY_ENRICHMENT_ROOT") or "/workspace/data/enrichment")
GENE_RESOURCE_ROOT = Path(os.environ.get("SPASHINY_GENE_ENRICHMENT_ROOT") or DEFAULT_ENRICHMENT_ROOT / "gene")
METABOLITE_RESOURCE_ROOT = Path(os.environ.get("SPASHINY_METABOLITE_ENRICHMENT_ROOT") or DEFAULT_ENRICHMENT_ROOT / "metabolite")


@dataclass(frozen=True)
class TermSet:
    database: str
    pathway_id: str
    pathway_name: str
    id_type: str
    ids: frozenset[str]
    source_file: str
    source_sha256: str
    version: str = ""


def run(ctx: CPUWorkflowContext) -> dict:
    """Backward-compatible entrypoint for the historical enrichment_analysis workflow."""
    return run_gene(ctx)


def run_gene(ctx: CPUWorkflowContext) -> dict:
    df = _gene_input_frame(ctx)
    gene_column = _first_existing_column(df, [str(ctx.parameters.get("gene_column") or ""), "gene", "Gene", "symbol", "Symbol", "feature", "feature_id", "name"])
    if not gene_column:
        raise CPUWorkflowError("INVALID_INPUT", "Gene enrichment input must include a gene column.")

    input_genes = [_clean_identifier(value) for value in df[gene_column].tolist()]
    input_genes = [value for value in input_genes if value]
    mapping, symbols, entrez_ids = _map_gene_identifiers(input_genes, ctx)
    write_csv(ctx.workspace / "mapping_results.csv", mapping, fieldnames=[
        "input_gene",
        "mapped",
        "canonical_symbol",
        "entrez_id",
        "mapping_status",
    ])

    database_ids = _parameter_list(ctx.parameters.get("database_ids") or ctx.parameters.get("databases"))
    terms = _load_gene_terms(ctx, database_ids)
    if not terms:
        raise CPUWorkflowError("DATABASE_RESOURCE_MISSING", "No local gene enrichment term database is available.")

    result_rows = _ora_results(
        terms=terms,
        query_by_type={"symbol": symbols, "entrez": entrez_ids},
        output_id_to_label=_gene_output_labeler(ctx),
        count_column="Gene_Count",
        ratio_column="Gene_Ratio",
        entity_column="Genes",
    )
    write_csv(ctx.workspace / "enrichment_results.csv", result_rows, fieldnames=[
        "Database",
        "Pathway_ID",
        "Pathway_Name",
        "Gene_Count",
        "Pathway_Size",
        "Gene_Ratio",
        "Background_Ratio",
        "P_Value",
        "Adjusted_P_Value",
        "Genes",
    ])
    plot_outputs = _write_enrichment_plots(
        ctx,
        result_rows,
        count_column="Gene_Count",
        ratio_column="Gene_Ratio",
        title="Gene enrichment",
    )
    resource_summary = _resource_summary(terms)
    metrics = {
        "status": "succeeded",
        "analysis_kind": "gene_enrichment",
        "runtime_internet_required": False,
        "input_gene_count": len(input_genes),
        "mapped_gene_count": len([row for row in mapping if row["mapped"]]),
        "unmapped_gene_count": len([row for row in mapping if not row["mapped"]]),
        "terms_tested": len(terms),
        "result_rows": len(result_rows),
        "database_resources": resource_summary,
        "background_type": str(ctx.parameters.get("background_type") or "database_universe"),
        "background_gene_count": len(_universe_for_terms(terms)),
    }
    write_json(ctx.workspace / "enrichment_summary.json", metrics)
    outputs = ["mapping_results.csv", "enrichment_results.csv", "enrichment_summary.json", *plot_outputs]
    outputs.extend(_write_enrichment_download_manifest(ctx, metrics=metrics, outputs=outputs, plot_outputs=plot_outputs))
    return {"metrics": metrics, "outputs": outputs}


def run_metabolite(ctx: CPUWorkflowContext) -> dict:
    df = _table_input_frame(ctx, default_role="metabolite_table")
    kegg_column = _first_existing_column(df, [str(ctx.parameters.get("kegg_column") or ""), "KEGG.ID", "KEGG_ID", "kegg_id", "kegg", "compound_id"])
    name_column = _first_existing_column(df, [str(ctx.parameters.get("metabolite_column") or ""), "metabolite", "Metabolite", "name", "Name"])
    db_path = _metabolite_kegg_membership_path(ctx)

    if not db_path.is_file():
        raise CPUWorkflowError(
            "DATABASE_RESOURCE_MISSING",
            f"Metabolite enrichment requires a local KEGG compound-pathway mapping TSV: {db_path}",
        )
    if not kegg_column and not name_column:
        raise CPUWorkflowError("INVALID_INPUT", "Metabolite enrichment input must include KEGG.ID or metabolite columns.")

    mapping = _map_metabolites(df, kegg_column=kegg_column, name_column=name_column)
    write_csv(ctx.workspace / "mapping_results.csv", mapping, fieldnames=[
        "input_metabolite",
        "input_kegg_id",
        "mapped",
        "canonical_kegg_id",
        "mapping_status",
    ])

    query = {row["canonical_kegg_id"] for row in mapping if row["mapped"] and row["canonical_kegg_id"]}
    terms = _load_metabolite_terms(db_path)
    result_rows = _ora_results(
        terms=terms,
        query_by_type={"kegg_compound": query},
        output_id_to_label=lambda value: value,
        count_column="Metabolite_Count",
        ratio_column="Metabolite_Ratio",
        entity_column="Metabolites",
    )
    write_csv(ctx.workspace / "enrichment_results.csv", result_rows, fieldnames=[
        "Database",
        "Pathway_ID",
        "Pathway_Name",
        "Metabolite_Count",
        "Pathway_Size",
        "Metabolite_Ratio",
        "Background_Ratio",
        "P_Value",
        "Adjusted_P_Value",
        "Metabolites",
    ])
    plot_outputs = _write_enrichment_plots(
        ctx,
        result_rows,
        count_column="Metabolite_Count",
        ratio_column="Metabolite_Ratio",
        title="Metabolite enrichment",
    )
    metrics = {
        "status": "succeeded",
        "analysis_kind": "metabolite_enrichment",
        "runtime_internet_required": False,
        "input_metabolite_count": len(mapping),
        "mapped_metabolite_count": len([row for row in mapping if row["mapped"]]),
        "unmapped_metabolite_count": len([row for row in mapping if row["mapping_status"] == "UNMAPPED"]),
        "ambiguous_metabolite_count": len([row for row in mapping if row["mapping_status"] == "AMBIGUOUS"]),
        "terms_tested": len(terms),
        "result_rows": len(result_rows),
        "database_resources": _resource_summary(terms),
        "background_type": str(ctx.parameters.get("background_type") or "database_universe"),
        "background_metabolite_count": len(_universe_for_terms(terms)),
    }
    write_json(ctx.workspace / "enrichment_summary.json", metrics)
    outputs = ["mapping_results.csv", "enrichment_results.csv", "enrichment_summary.json", *plot_outputs]
    outputs.extend(_write_enrichment_download_manifest(ctx, metrics=metrics, outputs=outputs, plot_outputs=plot_outputs))
    return {"metrics": metrics, "outputs": outputs}



def _write_enrichment_download_manifest(
    ctx: CPUWorkflowContext,
    *,
    metrics: dict[str, Any],
    outputs: list[str],
    plot_outputs: list[str],
) -> list[str]:
    ctx.ensure_dirs()
    files = []
    for rel in outputs:
        path = ctx.workspace / rel
        if path.is_file():
            files.append({"path": rel, "size_bytes": path.stat().st_size, "sha256": sha256_file(path)})
    plots = []
    for rel in plot_outputs:
        path = ctx.workspace / rel
        if path.is_file():
            plots.append({"name": Path(rel).stem.replace("_", " ").title(), "path": rel, "size_bytes": path.stat().st_size})
    manifest = {
        "status": "completed",
        "workflow": ctx.workflow_name,
        "job_id": ctx.job_id,
        "summary": metrics,
        "plots": plots,
        "files": files,
        "archive": {"path": "results.zip"},
        "downloads": [{"label": item["path"], "path": item["path"]} for item in files],
        "manifest_version": "spashiny_enrichment_result_manifest_v1",
    }
    write_json(ctx.workspace / "result_manifest.json", manifest)
    zip_inputs = [*outputs, "result_manifest.json"]
    zip_path = ctx.workspace / "results.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        for rel in zip_inputs:
            path = ctx.workspace / rel
            if path.is_file():
                archive.write(path, rel)
    return ["result_manifest.json", "results.zip"]


def _gene_input_frame(ctx: CPUWorkflowContext):
    if ctx.parameters.get("genes"):
        import pandas as pd

        genes = _parameter_list(ctx.parameters.get("genes"))
        return pd.DataFrame({"gene": genes})
    return _table_input_frame(ctx, default_role="gene_table")


def _table_input_frame(ctx: CPUWorkflowContext, *, default_role: str):
    path = select_asset(
        ctx,
        suffixes=(".csv", ".tsv", ".txt", ".h5ad"),
        roles=(default_role, "marker_table", "gene_list", "metabolite_table", "primary"),
        required=False,
    )
    if path is None:
        raise CPUWorkflowError("INPUT_REQUIRED", "A CSV/TSV/TXT/H5AD input is required for enrichment.")
    if path.suffix.lower() == ".h5ad":
        import pandas as pd

        adata = read_h5ad(path)
        if default_role == "metabolite_table":
            return pd.DataFrame({"metabolite": [str(item) for item in adata.var_names]})
        return pd.DataFrame({"gene": [str(item) for item in adata.var_names]})
    return read_table(path)


def _parameter_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        items = value
    else:
        items = re.split(r"[;,]\s*|\n+", str(value))
    return [_clean_identifier(item) for item in items if _clean_identifier(item)]


def _clean_identifier(value: Any) -> str:
    text = str(value or "").strip()
    if text.lower() in {"nan", "none", "null"}:
        return ""
    return text


def _first_existing_column(df, candidates: list[str]) -> str:
    for column in candidates:
        if column and column in df.columns:
            return column
    lowered = {str(column).lower(): str(column) for column in df.columns}
    for column in candidates:
        if column and column.lower() in lowered:
            return lowered[column.lower()]
    return ""


def _resource_root_from_params(ctx: CPUWorkflowContext, key: str, default: Path) -> Path:
    raw = str(ctx.parameters.get(key) or "").strip()
    return Path(raw).resolve() if raw else default


def _gene_resource_paths(ctx: CPUWorkflowContext) -> dict[str, Path]:
    root = _resource_root_from_params(ctx, "gene_resource_root", GENE_RESOURCE_ROOT)
    species = str(ctx.parameters.get("species") or "mouse").strip().lower()
    base = root / species
    return {
        "base": base,
        "hallmark": base / "gmt" / "msigdb_hallmark_v2026.1_mmu_symbols.gmt",
        "reactome": base / "gmt" / "reactome_mouse_fgsea_entrez.gmt",
        "go_cc_gmt": base / "gmt" / "go_cc_c5_v5_entrez.gmt",
        "orgdb": base / "id_mapping" / "org.Mm.eg.sqlite",
        "godb": base / "metadata" / "GO.sqlite",
    }


def _metabolite_kegg_membership_path(ctx: CPUWorkflowContext) -> Path:
    raw = str(ctx.parameters.get("compound_pathway_db") or ctx.parameters.get("database_path") or "").strip()
    if not raw:
        raw = str(os.environ.get("SPASHINY_METABOLITE_KEGG_PATHWAY_DB") or "")
    if not raw:
        raw = str(METABOLITE_RESOURCE_ROOT / "kegg" / "compound_pathway_membership.tsv")
    return Path(raw).resolve()


def _map_gene_identifiers(input_genes: list[str], ctx: CPUWorkflowContext) -> tuple[list[dict[str, Any]], set[str], set[str]]:
    paths = _gene_resource_paths(ctx)
    orgdb = paths["orgdb"]
    symbol_by_upper: dict[str, tuple[str, str]] = {}
    entrez_to_symbol: dict[str, str] = {}
    if orgdb.is_file():
        con = sqlite3.connect(str(orgdb))
        try:
            for entrez, symbol in con.execute(
                "select genes.gene_id, gene_info.symbol from genes join gene_info on genes._id = gene_info._id"
            ):
                entrez_text = str(entrez)
                symbol_text = str(symbol)
                symbol_by_upper[symbol_text.upper()] = (symbol_text, entrez_text)
                entrez_to_symbol[entrez_text] = symbol_text
        finally:
            con.close()
    rows: list[dict[str, Any]] = []
    symbols: set[str] = set()
    entrez_ids: set[str] = set()
    seen: set[str] = set()
    for gene in input_genes:
        if not gene or gene in seen:
            continue
        seen.add(gene)
        canonical_symbol = ""
        entrez_id = ""
        status = "UNMAPPED"
        if gene.upper() in symbol_by_upper:
            canonical_symbol, entrez_id = symbol_by_upper[gene.upper()]
            status = "MAPPED"
        elif gene in entrez_to_symbol:
            canonical_symbol = entrez_to_symbol[gene]
            entrez_id = gene
            status = "MAPPED"
        else:
            canonical_symbol = gene
        if status == "MAPPED":
            symbols.add(canonical_symbol)
            if entrez_id:
                entrez_ids.add(entrez_id)
        rows.append(
            {
                "input_gene": gene,
                "mapped": status == "MAPPED",
                "canonical_symbol": canonical_symbol,
                "entrez_id": entrez_id,
                "mapping_status": status,
            }
        )
    return rows, symbols, entrez_ids


def _gene_output_labeler(ctx: CPUWorkflowContext):
    paths = _gene_resource_paths(ctx)
    orgdb = paths["orgdb"]
    entrez_to_symbol: dict[str, str] = {}
    if orgdb.is_file():
        con = sqlite3.connect(str(orgdb))
        try:
            for entrez, symbol in con.execute(
                "select genes.gene_id, gene_info.symbol from genes join gene_info on genes._id = gene_info._id"
            ):
                entrez_to_symbol[str(entrez)] = str(symbol)
        finally:
            con.close()

    def label(value: str) -> str:
        return entrez_to_symbol.get(str(value), str(value))

    return label


def _load_gene_terms(ctx: CPUWorkflowContext, database_ids: list[str]) -> list[TermSet]:
    paths = _gene_resource_paths(ctx)
    requested = {item.lower() for item in database_ids} or {"hallmark", "reactome", "go_bp", "go_cc", "go_mf"}
    terms: list[TermSet] = []
    if {"hallmark", "msigdb_hallmark"} & requested and paths["hallmark"].is_file():
        terms.extend(_load_gmt(paths["hallmark"], database="MSigDB Hallmark Mouse", id_type="symbol", version="v2026.1"))
    if {"reactome", "mouse_reactome"} & requested and paths["reactome"].is_file():
        terms.extend(_load_gmt(paths["reactome"], database="Reactome Mouse", id_type="entrez", version="fgsea_extdata"))
    if {"go_cc_gmt", "c5_cc"} & requested and paths["go_cc_gmt"].is_file():
        terms.extend(_load_gmt(paths["go_cc_gmt"], database="GO Cellular Component", id_type="entrez", version="c5.v5.0"))
    if {"go_bp", "go_cc", "go_mf"} & requested:
        ontologies = [item for item in ("go_bp", "go_cc", "go_mf") if item in requested]
        terms.extend(_load_go_sqlite_terms(paths["orgdb"], paths["godb"], ontologies=ontologies))
    return terms


def _load_gmt(path: Path, *, database: str, id_type: str, version: str) -> list[TermSet]:
    digest = sha256_file(path)
    terms: list[TermSet] = []
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            name = parts[0].strip()
            desc = parts[1].strip()
            ids = frozenset(_clean_identifier(item) for item in parts[2:] if _clean_identifier(item))
            if not name or not ids:
                continue
            pathway_id = desc if desc and not desc.startswith("http") else name
            terms.append(
                TermSet(
                    database=database,
                    pathway_id=pathway_id,
                    pathway_name=name,
                    id_type=id_type,
                    ids=ids,
                    source_file=str(path),
                    source_sha256=digest,
                    version=version,
                )
            )
    return terms


def _load_go_sqlite_terms(orgdb: Path, godb: Path, *, ontologies: list[str]) -> list[TermSet]:
    if not orgdb.is_file() or not godb.is_file():
        return []
    digest = sha256_file(orgdb) + "+" + sha256_file(godb)
    table_to_label = {
        "go_bp": "GO Biological Process",
        "go_cc": "GO Cellular Component",
        "go_mf": "GO Molecular Function",
    }
    terms: list[TermSet] = []
    con = sqlite3.connect(str(orgdb))
    try:
        con.execute("attach database ? as godb", (str(godb),))
        for table in ontologies:
            if table not in table_to_label:
                continue
            rows: dict[tuple[str, str], set[str]] = {}
            query = f"""
                select go.go_id, coalesce(godb.go_term.term, go.go_id) as term, genes.gene_id
                from {table} as go
                join genes on go._id = genes._id
                left join godb.go_term on go.go_id = godb.go_term.go_id
            """
            for go_id, term, gene_id in con.execute(query):
                key = (str(go_id), str(term))
                rows.setdefault(key, set()).add(str(gene_id))
            for (go_id, term), ids in rows.items():
                if ids:
                    terms.append(
                        TermSet(
                            database=table_to_label[table],
                            pathway_id=go_id,
                            pathway_name=term,
                            id_type="entrez",
                            ids=frozenset(ids),
                            source_file=f"{orgdb};{godb}",
                            source_sha256=digest,
                            version="org.Mm.eg.db+GO.db",
                        )
                    )
    finally:
        con.close()
    return terms


def _map_metabolites(df, *, kegg_column: str, name_column: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        name = _clean_identifier(row.get(name_column, "")) if name_column else ""
        raw_kegg = _clean_identifier(row.get(kegg_column, "")) if kegg_column else ""
        canonical = _normalize_kegg_compound(raw_kegg)
        if canonical:
            status = "MAPPED"
            mapped = True
        elif name:
            status = "UNMAPPED"
            mapped = False
        else:
            status = "UNMAPPED"
            mapped = False
        rows.append(
            {
                "input_metabolite": name,
                "input_kegg_id": raw_kegg,
                "mapped": mapped,
                "canonical_kegg_id": canonical,
                "mapping_status": status,
            }
        )
    return rows


def _normalize_kegg_compound(value: str) -> str:
    text = _clean_identifier(value)
    if not text:
        return ""
    text = text.replace("cpd:", "").replace("CPD:", "").strip()
    match = re.fullmatch(r"C\d{5}", text.upper())
    return match.group(0) if match else ""


def _load_metabolite_terms(path: Path) -> list[TermSet]:
    df = read_table(path)
    compound_col = _first_existing_column(df, ["kegg_compound_id", "compound_id", "KEGG.ID", "KEGG_ID", "kegg_id"])
    pathway_col = _first_existing_column(df, ["pathway_id", "Pathway_ID", "pathway"])
    name_col = _first_existing_column(df, ["pathway_name", "Pathway_Name", "name", "term"])
    database_col = _first_existing_column(df, ["database", "Database"])
    if not compound_col or not pathway_col:
        raise CPUWorkflowError("ENRICHMENT_DATABASE_INVALID", "Metabolite DB must include compound and pathway columns.")
    grouped: dict[tuple[str, str, str], set[str]] = {}
    for _, row in df.iterrows():
        compound = _normalize_kegg_compound(row.get(compound_col, ""))
        pathway_id = _clean_identifier(row.get(pathway_col, ""))
        if not compound or not pathway_id:
            continue
        pathway_name = _clean_identifier(row.get(name_col, "")) if name_col else pathway_id
        database = _clean_identifier(row.get(database_col, "")) if database_col else "KEGG Compound Pathway"
        grouped.setdefault((database or "KEGG Compound Pathway", pathway_id, pathway_name or pathway_id), set()).add(compound)
    digest = sha256_file(path)
    return [
        TermSet(
            database=database,
            pathway_id=pathway_id,
            pathway_name=pathway_name,
            id_type="kegg_compound",
            ids=frozenset(ids),
            source_file=str(path),
            source_sha256=digest,
            version="local_tsv",
        )
        for (database, pathway_id, pathway_name), ids in grouped.items()
        if ids
    ]


def _universe_for_terms(terms: list[TermSet]) -> set[str]:
    universe: set[str] = set()
    for term in terms:
        universe.update(term.ids)
    return universe


def _ora_results(
    *,
    terms: list[TermSet],
    query_by_type: dict[str, set[str]],
    output_id_to_label,
    count_column: str,
    ratio_column: str,
    entity_column: str,
) -> list[dict[str, Any]]:
    from scipy.stats import hypergeom

    universe_by_type: dict[str, set[str]] = {}
    for term in terms:
        universe_by_type.setdefault(term.id_type, set()).update(term.ids)

    rows: list[dict[str, Any]] = []
    pvalues: list[float] = []
    for term in terms:
        universe = universe_by_type.get(term.id_type, set())
        query = set(query_by_type.get(term.id_type, set())) & universe
        if not universe or not query:
            continue
        overlap = sorted(query & set(term.ids))
        k = len(overlap)
        if k <= 0:
            continue
        n_total = len(universe)
        term_size = len(set(term.ids) & universe)
        query_size = len(query)
        pvalue = float(hypergeom.sf(k - 1, n_total, term_size, query_size))
        pvalues.append(pvalue)
        rows.append(
            {
                "Database": term.database,
                "Pathway_ID": term.pathway_id,
                "Pathway_Name": term.pathway_name,
                count_column: k,
                "Pathway_Size": term_size,
                ratio_column: k / query_size if query_size else 0.0,
                "Background_Ratio": term_size / n_total if n_total else 0.0,
                "P_Value": pvalue,
                "Adjusted_P_Value": 1.0,
                entity_column: ";".join(output_id_to_label(item) for item in overlap),
            }
        )
    adjusted = _bh_fdr(pvalues)
    for row, value in zip(rows, adjusted):
        row["Adjusted_P_Value"] = value
    rows.sort(key=lambda row: (float(row["Adjusted_P_Value"]), float(row["P_Value"]), str(row["Pathway_Name"])))
    return rows


def _bh_fdr(pvalues: list[float]) -> list[float]:
    n = len(pvalues)
    if n == 0:
        return []
    indexed = sorted(enumerate(pvalues), key=lambda item: item[1])
    adjusted = [1.0] * n
    prev = 1.0
    for rank_from_end, (idx, pvalue) in enumerate(reversed(indexed), start=1):
        rank = n - rank_from_end + 1
        value = min(prev, float(pvalue) * n / rank)
        value = max(0.0, min(1.0, value))
        adjusted[idx] = value
        prev = value
    return adjusted


def _write_enrichment_plots(
    ctx: CPUWorkflowContext,
    rows: list[dict[str, Any]],
    *,
    count_column: str,
    ratio_column: str,
    title: str,
) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    outputs: list[str] = []
    top = rows[: min(20, len(rows))]
    if not top:
        fig, ax = plt.subplots(figsize=(7, 3))
        ax.axis("off")
        ax.text(0.5, 0.5, "No enrichment results.", ha="center", va="center")
        fig.tight_layout()
        for name in ("dotplot", "barplot"):
            png_path, pdf_path = save_figure_bundle(fig, ctx.workspace / f"{name}.png", dpi=140)
            outputs.extend([png_path.name, pdf_path.name])
        plt.close(fig)
        plt.close("all")
        return outputs

    labels = [str(row["Pathway_Name"])[:70] for row in top][::-1]
    ratios = [float(row[ratio_column]) for row in top][::-1]
    counts = [float(row[count_column]) for row in top][::-1]
    adj = [float(row["Adjusted_P_Value"]) for row in top][::-1]

    fig, ax = plt.subplots(figsize=(8, max(4, 0.34 * len(labels) + 1.5)))
    size = [30 + value * 18 for value in counts]
    scatter = ax.scatter(ratios, range(len(labels)), s=size, c=adj, cmap="viridis_r")
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlabel(ratio_column.replace("_", " "))
    ax.set_title(title + " dot plot")
    cbar = fig.colorbar(scatter, ax=ax)
    cbar.set_label("Adjusted P value")
    fig.tight_layout()
    _, pdf_path = save_figure_bundle(fig, ctx.workspace / "dotplot.png", dpi=160)
    plt.close(fig)
    outputs.extend(["dotplot.png", pdf_path.name])

    fig, ax = plt.subplots(figsize=(8, max(4, 0.34 * len(labels) + 1.5)))
    ax.barh(range(len(labels)), counts)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlabel(count_column.replace("_", " "))
    ax.set_title(title + " bar plot")
    fig.tight_layout()
    _, pdf_path = save_figure_bundle(fig, ctx.workspace / "barplot.png", dpi=160)
    plt.close(fig)
    outputs.extend(["barplot.png", pdf_path.name])
    plt.close("all")
    return outputs


def _resource_summary(terms: list[TermSet]) -> list[dict[str, Any]]:
    seen: dict[tuple[str, str, str], dict[str, Any]] = {}
    for term in terms:
        key = (term.database, term.source_file, term.source_sha256)
        item = seen.setdefault(
            key,
            {
                "database_name": term.database,
                "database_version": term.version,
                "resource_file": term.source_file,
                "resource_checksum": term.source_sha256,
                "term_count": 0,
                "id_type": term.id_type,
            },
        )
        item["term_count"] += 1
    return sorted(seen.values(), key=lambda item: str(item["database_name"]))
