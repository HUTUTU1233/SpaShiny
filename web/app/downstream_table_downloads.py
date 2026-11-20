"""Current-analysis CSV downloads; no analysis or expression transformations."""
from __future__ import annotations

import pandas as pd
from shiny import render, ui


def summary_table(adata):
    if adata is None:
        raise ValueError("Load the current analysis input before downloading its summary.")
    return pd.DataFrame({"Metric": ["Number of cells", "Number of genes"],
                         "Value": [adata.n_obs, adata.n_vars]})


def observations_table(adata):
    if adata is None:
        raise ValueError("Load the current analysis input before downloading observations.")
    table = adata.obs.copy()
    name = "spot_id"
    while name in table.columns:
        name = "_" + name
    table.insert(0, name, adata.obs_names.to_numpy(copy=True))
    return table


def distribution_table(adata):
    if adata is None or "celltype1" not in adata.obs:
        raise ValueError("The displayed celltype1 distribution is not available for this input.")
    counts = adata.obs["celltype1"].value_counts()
    return pd.DataFrame({"celltype1": counts.index.to_numpy(), "count": counts.to_numpy()})


def marker_table(result, key):
    if not result or key not in result or not isinstance(result[key], pd.DataFrame) or result[key].empty:
        raise ValueError("Run Marker analysis for the current input before downloading this result.")
    # The page preview is head(50), but downloads preserve every existing row.
    return result[key].copy()


def csv_bytes(table):
    return table.to_csv(index=False).encode("utf-8-sig")


def register_downstream_table_downloads(output, *, get_adata, get_markers, assert_scope):
    def current_table(kind):
        assert_scope()
        if kind == "summary":return summary_table(get_adata())
        if kind == "observations":return observations_table(get_adata())
        if kind == "distribution":return distribution_table(get_adata())
        return marker_table(get_markers(), "gene_df" if kind == "marker_genes" else "met_df")

    def bind(kind, label):
        download_id = "download_downstream_" + kind + "_csv"
        def download():
            yield csv_bytes(current_table(kind))
        download.__name__ = download_id
        renderer = render.download(filename="downstream_" + kind + ".csv",
                                   media_type="text/csv; charset=utf-8")(download)

        @output(id="downstream_" + kind + "_download")
        @render.ui
        def controls():
            try:
                assert_scope()
                if kind in {"summary", "observations", "distribution"}:
                    adata = get_adata()
                    available = adata is not None and (kind != "distribution" or "celltype1" in adata.obs)
                else:
                    result = get_markers()
                    key = "gene_df" if kind == "marker_genes" else "met_df"
                    available = bool(result and key in result and isinstance(result[key], pd.DataFrame) and not result[key].empty)
            except Exception:
                return None
            if not available:return None
            return ui.download_button(download_id, label, class_="btn btn-outline-secondary btn-sm")
        return renderer, controls

    return [bind(kind, label) for kind, label in (
        ("summary", "Download Summary CSV"),
        ("observations", "Download All Observations CSV"),
        ("distribution", "Download Distribution CSV"),
        ("marker_genes", "Download All Marker Genes CSV"),
        ("marker_metabolites", "Download All Marker m/z CSV"),
    )]
