import argparse
import gc
import json
import os
import traceback
from pathlib import Path

import anndata as ad
import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42
matplotlib.rcParams["ps.fonttype"] = 42
matplotlib.rcParams["svg.fonttype"] = "none"
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd
import scanpy as sc
import torch

from river.river import River
from river.preprocess import do_slat_pair, get_the_feature, seed_everything


def log(msg):
    print(str(msg), flush=True)


def err_text(e: Exception) -> str:
    name = type(e).__name__
    msg = str(e).strip()
    if msg:
        return f"{name}: {msg}"
    return repr(e)


def safe_str(x):
    try:
        return str(x)
    except Exception:
        return "Unknown"


def close_backed_adata(adata):
    try:
        if getattr(adata, "isbacked", False) and getattr(adata, "file", None) is not None:
            adata.file.close()
    except Exception:
        pass


def force_memory_cleanup():
    gc.collect()
    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def choose_obs_indices(n_obs, target_n):
    try:
        target_n = int(target_n) if target_n is not None else None
    except Exception:
        target_n = None

    if target_n is None or target_n <= 0 or n_obs <= target_n:
        return slice(None)

    rng = np.random.default_rng(0)
    return np.sort(rng.choice(int(n_obs), size=int(target_n), replace=False))


def materialize_for_processing(adata, target_n=None):
    obs_idx = choose_obs_indices(adata.n_obs, target_n)
    needs_subset = not isinstance(obs_idx, slice)

    if getattr(adata, "isbacked", False):
        out = adata[obs_idx, :].to_memory() if needs_subset else adata.to_memory()
    elif needs_subset:
        out = adata[obs_idx, :].copy()
    elif getattr(adata, "is_view", False):
        out = adata.copy()
    else:
        out = adata

    out.var_names_make_unique()
    return out


def ensure_obs_column(adata, col, value):
    if col not in adata.obs.columns:
        adata.obs[col] = value
    else:
        adata.obs[col] = adata.obs[col].fillna(value).astype(str)


def try_read_csv_with_index(csv_path):
    index_cols = [
        "Barcode", "barcode", "BarcodeSpot", "spot_name", "Spot", "cell",
        "Cell", "index", "Index"
    ]

    for col in index_cols:
        try:
            df = pd.read_csv(csv_path, index_col=col)
            return df
        except Exception:
            continue

    df = pd.read_csv(csv_path)
    if df.shape[1] >= 1:
        df = df.set_index(df.columns[0])
    return df


def detect_annotation_column(df):
    candidate_cols = [
        "Region", "region",
        "annotation", "Annotation",
        "label", "Label",
        "cluster", "Cluster",
        "celltype", "CellType", "cell_type"
    ]
    for col in candidate_cols:
        if col in df.columns:
            return col
    if len(df.columns) > 0:
        return df.columns[0]
    return None


def extract_annotation_info(csv_path, adata):
    try:
        df = try_read_csv_with_index(csv_path)
        df.index = df.index.astype(str)
        adata.obs.index = adata.obs.index.astype(str)

        ann_col = detect_annotation_column(df)
        if ann_col is None:
            adata.obs["annotation"] = "Unknown"
            return adata

        adata.obs["annotation"] = (
            df[ann_col]
            .reindex(adata.obs.index)
            .fillna("Unknown")
            .astype(str)
        )
        return adata

    except Exception as e:
        log(f"Failed to read annotation file {csv_path}: {err_text(e)}")
        adata.obs["annotation"] = "Unknown"
        return adata


def inspect_uploaded_adata_shape(data_path):
    data_path = str(data_path)
    suffix = Path(data_path).suffix.lower()

    if suffix == ".h5ad":
        backed = sc.read_h5ad(data_path, backed="r")
        try:
            return tuple(backed.shape)
        finally:
            close_backed_adata(backed)

    if suffix == ".h5":
        try:
            adata = sc.read_10x_h5(data_path)
            shape = tuple(adata.shape)
            del adata
            force_memory_cleanup()
            return shape
        except Exception as e1:
            log(f"read_10x_h5 shape check failed for {data_path}: {err_text(e1)}")

        backed = sc.read_h5ad(data_path, backed="r")
        try:
            return tuple(backed.shape)
        finally:
            close_backed_adata(backed)

    raise RuntimeError(f"Unsupported file suffix: {suffix}")


def read_uploaded_adata(data_path, target_n=None):
    data_path = str(data_path)
    suffix = Path(data_path).suffix.lower()

    if suffix == ".h5ad":
        backed = sc.read_h5ad(data_path, backed="r")
        try:
            adata = materialize_for_processing(backed, target_n=target_n)
            log(f"Loaded h5ad via backed subset: {data_path}, shape={adata.shape}")
            return adata
        finally:
            close_backed_adata(backed)

    if suffix == ".h5":
        try:
            adata = sc.read_10x_h5(data_path)
            adata = materialize_for_processing(adata, target_n=target_n)
            log(f"Loaded as 10x h5: {data_path}, shape={adata.shape}")
            return adata
        except Exception as e1:
            log(f"read_10x_h5 failed for {data_path}: {err_text(e1)}")

        try:
            backed = sc.read_h5ad(data_path, backed="r")
            try:
                adata = materialize_for_processing(backed, target_n=target_n)
                log(f"Loaded .h5 as backed AnnData/h5ad-like file: {data_path}, shape={adata.shape}")
                return adata
            finally:
                close_backed_adata(backed)
        except Exception as e2:
            raise RuntimeError(
                f"Unsupported .h5 file format. "
                f"read_10x_h5 failed and read_h5ad also failed: {err_text(e2)}"
            )

    raise RuntimeError(f"Unsupported file suffix: {suffix}")


def normalize_cfg_samples(cfg):
    samples = cfg.get("samples", [])
    normalized = []

    for i, item in enumerate(samples):
        sample_id = safe_str(item.get("sample_id", f"sample_{i+1}"))
        condition = safe_str(item.get("condition", sample_id))

        data_path = (
            item.get("h5ad_path", None)
            or item.get("h5_path", None)
            or item.get("data_path", None)
        )
        csv_path = item.get("csv_path", None)

        if data_path:
            data_path = str(Path(data_path).resolve())
        if csv_path:
            csv_path = str(Path(csv_path).resolve())

        normalized.append({
            "sample_id": sample_id,
            "condition": condition,
            "data_path": data_path,
            "csv_path": csv_path,
        })

    return normalized


def ensure_spatial(adata):
    if "spatial" in adata.obsm:
        arr = np.asarray(adata.obsm["spatial"])
        if arr.ndim == 2 and arr.shape[1] >= 2:
            adata.obsm["spatial"] = arr[:, :2].astype(float)
            return adata

    candidate_pairs = [
        ("x", "y"),
        ("X", "Y"),
        ("coord1", "coord2"),
        ("Coord1", "Coord2"),
        ("pxl_col_in_fullres", "pxl_row_in_fullres"),
        ("imagecol", "imagerow"),
        ("array_col", "array_row"),
    ]

    for xcol, ycol in candidate_pairs:
        if xcol in adata.obs.columns and ycol in adata.obs.columns:
            coords = adata.obs[[xcol, ycol]].to_numpy(dtype=float)
            adata.obsm["spatial"] = coords
            return adata

    n_obs = adata.n_obs
    adata.obsm["spatial"] = np.column_stack(
        [np.arange(n_obs, dtype=float), np.arange(n_obs, dtype=float)]
    )
    return adata


def ensure_pca(adata, force=False):
    if force and "X_pca" in adata.obsm:
        del adata.obsm["X_pca"]

    if "X_pca" in adata.obsm:
        x = np.asarray(adata.obsm["X_pca"])
        if x.ndim == 2 and x.shape[0] == adata.n_obs and x.shape[1] >= 2:
            return adata

    n_obs = adata.n_obs
    n_vars = adata.n_vars
    if n_obs < 3 or n_vars < 3:
        raise RuntimeError(f"Too few cells/features for PCA: shape={adata.shape}")

    try:
        n_comps = int(min(50, n_obs - 1, n_vars - 1))
        sc.pp.pca(adata, n_comps=n_comps)
        return adata
    except Exception as e:
        raise RuntimeError(f"Failed to compute PCA for sample: {err_text(e)}")


def maybe_subsample(adata, target_n):
    if target_n is None:
        return adata
    try:
        target_n = int(target_n)
    except Exception:
        return adata

    if target_n > 0 and adata.n_obs > target_n:
        return sc.pp.subsample(adata, n_obs=target_n, random_state=0, copy=True)
    return adata


def prepare_basic_adata(adata, sample_id=None, condition=None):
    if getattr(adata, "isbacked", False) or getattr(adata, "is_view", False):
        adata = materialize_for_processing(adata)
    adata.var_names_make_unique()

    adata.obs.index = adata.obs.index.astype(str)
    adata.var.index = adata.var.index.astype(str)

    adata = ensure_spatial(adata)

    ensure_obs_column(adata, "annotation", "Unknown")
    ensure_obs_column(adata, "condition", safe_str(condition if condition else sample_id))
    ensure_obs_column(adata, "batch", safe_str(condition if condition else sample_id))
    ensure_obs_column(adata, "sample_id", safe_str(sample_id if sample_id else "sample"))

    adata.obsm["spatial"] = np.asarray(adata.obsm["spatial"], dtype=float)[:, :2]
    return adata


def finalize_adata_for_river(adata, target_n=None):
    adata = maybe_subsample(adata, target_n)
    if getattr(adata, "isbacked", False) or getattr(adata, "is_view", False):
        adata = materialize_for_processing(adata)

    sc.pp.normalize_total(adata)
    sc.pp.log1p(adata)

    adata = ensure_pca(adata, force=True)

    adata.obsm["spatial"] = np.asarray(adata.obsm["spatial"], dtype=float)[:, :2]
    return adata


def preprocess_adata(adata, sample_id=None, condition=None, target_n=None):
    adata = prepare_basic_adata(
        adata,
        sample_id=sample_id,
        condition=condition
    )
    adata = finalize_adata_for_river(adata, target_n=target_n)
    return adata


def stitch_slices_horizontally(adata_list, gap=50.0):
    """
    Concatenate multiple slices horizontally into one large coordinate system following the example.
    """
    if not adata_list:
        return []

    stitched = [a.copy() for a in adata_list]

    width = []
    length = []

    for adata in stitched:
        coords = np.asarray(adata.obsm["spatial"], dtype=float)
        adata.obsm["spatial"] = coords

        width.append(coords[:, 0].max() - coords[:, 0].min())
        length.append(coords[:, 1].max() - coords[:, 1].min())

    width = np.asarray(width, dtype=float)
    length = np.asarray(length, dtype=float)

    max_h = length.max()
    new_start = 0.0
    out = []

    for i, adata in enumerate(stitched):
        coords = np.asarray(adata.obsm["spatial"], dtype=float)

        x_new = coords[:, 0] - coords[:, 0].min() + new_start
        y_new = coords[:, 1] + (max_h - coords[:, 1].max())

        adata.obsm["spatial"] = np.stack([x_new, y_new], axis=1)
        out.append(adata)

        new_start += width[i] + gap

    return out


def to_valid_match_array(x, pair_name="unknown_pair"):
    arr = np.asarray(x)

    if arr.size == 0:
        raise RuntimeError(f"{pair_name}: empty matching result")

    arr = np.squeeze(arr)

    if arr.ndim == 0:
        raise RuntimeError(f"{pair_name}: invalid matching result with ndim=0")

    return arr


def choose_image_and_coords(adata):
    coords = np.asarray(adata.obsm["spatial"]).astype(float)

    if "spatial" not in adata.uns:
        return None, coords, None

    try:
        lib_id = list(adata.uns["spatial"].keys())[0]
        lib = adata.uns["spatial"][lib_id]
        images = lib.get("images", {})
        scalefactors = lib.get("scalefactors", {})

        if "lowres" in images:
            img = images["lowres"]
            sf = float(scalefactors.get("tissue_lowres_scalef", 1.0))
            return img, coords * sf, lib_id

        if "hires" in images:
            img = images["hires"]
            sf = float(scalefactors.get("tissue_hires_scalef", 1.0))
            return img, coords * sf, lib_id

    except Exception:
        pass

    return None, coords, None


def build_single_figure(adata_list, sample_labels, plot_png, plot_pdf):
    unique_ann = []
    for adata in adata_list:
        ann_series = adata.obs.get(
            "annotation",
            pd.Series(["Unknown"] * adata.n_obs, index=adata.obs.index)
        ).fillna("Unknown").astype(str)
        for v in ann_series.unique().tolist():
            if v not in unique_ann:
                unique_ann.append(v)

    if not unique_ann:
        unique_ann = ["Unknown"]

    cmap = plt.get_cmap("tab20")
    color_map = {ann: cmap(i % 20) for i, ann in enumerate(unique_ann)}

    fig, ax = plt.subplots(figsize=(18, 7))
    x_offset = 0.0
    pad = 180.0

    prepared = []
    for adata, label in zip(adata_list, sample_labels):
        img, coords, _ = choose_image_and_coords(adata)
        coords = np.asarray(coords, dtype=float).copy()
        coords[:, 0] = coords[:, 0] - coords[:, 0].min()
        coords[:, 1] = coords[:, 1] - coords[:, 1].min()

        width = coords[:, 0].max() if coords.shape[0] else 0
        height = coords[:, 1].max() if coords.shape[0] else 0
        prepared.append((adata, label, img, coords, width, height))

    for adata, label, img, coords, width, height in prepared:
        if img is not None:
            ax.imshow(
                img,
                extent=(x_offset, x_offset + img.shape[1], img.shape[0], 0),
                interpolation="nearest",
                alpha=0.92,
                zorder=0
            )
            plot_y = coords[:, 1]
            panel_width = img.shape[1]
        else:
            panel_width = max(width, 50)
            rect = Rectangle(
                (x_offset, 0),
                panel_width,
                max(height, 50),
                facecolor="#f4f5f7",
                edgecolor="#d9dbe0",
                lw=1.0,
                zorder=0
            )
            ax.add_patch(rect)
            plot_y = coords[:, 1]

        ann_series = adata.obs.get(
            "annotation",
            pd.Series(["Unknown"] * adata.n_obs, index=adata.obs.index)
        ).fillna("Unknown").astype(str)

        for ann in ann_series.unique():
            mask = ann_series == ann
            pts = coords[mask.values]
            if pts.shape[0] == 0:
                continue

                # Dot plot
            ax.scatter(
                pts[:, 0] + x_offset,
                plot_y[mask.values],
                s=10,
                c=[color_map.get(ann, "#999999")],
                alpha=0.85,
                linewidths=0,
                zorder=3
            )

        ax.text(
            x_offset + panel_width / 2,
            -25,
            safe_str(label),
            ha="center",
            va="top",
            fontsize=11,
            fontweight="bold"
        )

        x_offset += panel_width + pad

    handles = [
        Line2D([0], [0], marker="o", color="w", label=ann,
               markerfacecolor=color_map[ann], markersize=8)
        for ann in unique_ann
    ]
    ax.legend(
        handles=handles,
        title="annotation",
        loc="center left",
        bbox_to_anchor=(1.01, 0.5),
        frameon=False
    )

    ax.set_title("River combined spatial plot", fontsize=14, fontweight="bold")
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_facecolor("white")

    plt.tight_layout()
    fig.savefig(plot_png, dpi=300, bbox_inches="tight")
    fig.savefig(plot_pdf, dpi=300, bbox_inches="tight")
    plt.close(fig)


def normalize_feature_names(feature_names, limit=200):
    out = []
    for name in feature_names or []:
        name = safe_str(name)
        if name and name not in out:
            out.append(name)
        if limit and len(out) >= int(limit):
            break
    return out


def save_plot_ready_adata(adata_list, sample_labels, out_dir, feature_names=None, feature_limit=200):
    """
    Save an h5ad object that the Shiny frontend can use to redraw selected features.
    """
    selected_features = normalize_feature_names(feature_names, limit=feature_limit)
    prepared = []
    for i, (adata, label) in enumerate(zip(adata_list, sample_labels)):
        present = [f for f in selected_features if f in adata.var_names]
        if present:
            a = adata[:, present].copy()
        else:
            fallback_n = min(int(feature_limit or 200), adata.n_vars)
            a = adata[:, :fallback_n].copy()
        ensure_obs_column(a, "river_panel", safe_str(label))
        ensure_obs_column(a, "river_panel_index", str(i + 1))
        a.var_names = a.var_names.astype(str)
        a.var_names_make_unique()
        prepared.append(a)

    plot_adata = ad.concat(
        prepared,
        join="outer",
        merge="same",
        uns_merge="first",
        label="river_concat_batch",
        keys=[safe_str(x) for x in sample_labels],
        index_unique="__"
    )

    plot_adata.var_names = plot_adata.var_names.astype(str)
    plot_adata.var_names_make_unique()

    if "spatial" in plot_adata.obsm:
        plot_adata.obsm["spatial"] = np.asarray(plot_adata.obsm["spatial"], dtype=float)[:, :2]

    plot_adata_path = out_dir / "river_plot_adata.h5ad"
    plot_adata.write_h5ad(plot_adata_path)

    feature_csv = out_dir / "river_plot_adata_features.csv"
    pd.DataFrame({"feature": plot_adata.var_names.astype(str)}).to_csv(
        feature_csv,
        index=False
    )

    del prepared
    force_memory_cleanup()

    return str(plot_adata_path), str(feature_csv)


def save_rank_outputs(model, out_dir):
    rank_npy = out_dir / "river_final_rank_temporal.npy"
    rank_csv = out_dir / "river_final_rank_temporal.csv"
    ig_npy = out_dir / "river_ig_temporal.npy"
    dl_npy = out_dir / "river_dl_temporal.npy"
    sl_npy = out_dir / "river_sl_temporal.npy"

    final_rank = [str(x) for x in model.final_rank.index.tolist()]

    np.save(rank_npy, np.array(final_rank, dtype=object))
    pd.DataFrame({"feature": final_rank}).to_csv(rank_csv, index=False)

    np.save(ig_npy, np.asarray(model.scores_ig))
    np.save(dl_npy, np.asarray(model.scores_dl))
    np.save(sl_npy, np.asarray(model.scores_sl))

    return {
        "rank_file": str(rank_npy),
        "rank_csv": str(rank_csv),
        "ig_file": str(ig_npy),
        "dl_file": str(dl_npy),
        "sl_file": str(sl_npy),
        "features": final_rank,
    }


def process_uploaded_samples(cfg):
    samples = normalize_cfg_samples(cfg)
    subsample_size = int(cfg.get("subsample_size", 6000) or 6000)

    sample_records = []
    invalid_samples = []

    for item in samples:
        sample_id = item["sample_id"]
        condition = item["condition"]
        data_path = item["data_path"]

        display_name = condition if condition else sample_id

        if not data_path or not os.path.exists(data_path):
            invalid_samples.append(f"{sample_id} (missing data file)")
            continue

        try:
            shape = inspect_uploaded_adata_shape(data_path)
            sample_records.append((item, display_name, shape))
            log(
                f"Inspected sample: sample_id={sample_id}, "
                f"condition={condition}, shape={shape}"
            )

        except Exception as e:
            invalid_samples.append(f"{sample_id} ({err_text(e)})")
            log(f"Failed shape check for sample {sample_id}: {err_text(e)}")
            log(traceback.format_exc())

    if not sample_records:
        return [], [], invalid_samples

    min_n_obs = min(shape[0] for _, _, shape in sample_records)
    target_n = min(min_n_obs, subsample_size) if subsample_size > 0 else min_n_obs

    log(f"Unified subsample size across all samples: {target_n}")

    adata_list = []
    final_valid_samples = []

    for item, label, _shape in sample_records:
        sample_id = item["sample_id"]
        condition = item["condition"]
        data_path = item["data_path"]
        csv_path = item["csv_path"]

        try:
            log(f"Loading data file: {data_path}")
            adata = read_uploaded_adata(data_path, target_n=target_n)

            if csv_path and os.path.exists(csv_path):
                log(f"Applying annotation csv: {csv_path}")
                adata = extract_annotation_info(csv_path, adata)
            else:
                adata.obs["annotation"] = "Unknown"

            adata = prepare_basic_adata(
                adata,
                sample_id=sample_id,
                condition=condition
            )

            if adata.n_obs < 3:
                raise RuntimeError(f"Too few cells/spots after loading: n_obs={adata.n_obs}")

            adata2 = finalize_adata_for_river(adata, target_n=None)
            adata_list.append(adata2)
            final_valid_samples.append(label)

            coords = np.asarray(adata2.obsm["spatial"], dtype=float)
            w = coords[:, 0].max() - coords[:, 0].min()
            h = coords[:, 1].max() - coords[:, 1].min()

            log(
                f"Finalized sample: {label}, "
                f"shape={adata2.shape}, width={w:.2f}, height={h:.2f}"
            )

        except Exception as e:
            invalid_samples.append(f"{sample_id} ({err_text(e)})")
            log(f"Failed sample {sample_id}: {err_text(e)}")
            log(traceback.format_exc())
        finally:
            force_memory_cleanup()

    return adata_list, final_valid_samples, invalid_samples


def run_river_analysis(adata_list, sample_labels, out_dir, epochs=100):
    if len(adata_list) < 2:
        return {
            "river_success": False,
            "message": "River requires at least 2 samples.",
            "rank_file": None,
            "rank_csv": None,
            "ig_file": None,
            "dl_file": None,
            "sl_file": None,
            "plot_adata": None,
            "plot_feature_csv": None,
        }

    try:
        river_adata_list = stitch_slices_horizontally(adata_list, gap=50.0)

        matching_list = []
        ref_adata = river_adata_list[0]

        for i in range(1, len(river_adata_list)):
            cur_adata = river_adata_list[i]
            pair_name = f"{sample_labels[0]} vs {sample_labels[i]}"

            log(f"Running do_slat_pair for {pair_name}")

            try:
                _, best = do_slat_pair(ref_adata, cur_adata, feature="pca")
            except Exception as e:
                raise RuntimeError(f"{pair_name}: do_slat_pair failed: {err_text(e)}")

            if best is None or len(best) == 0 or best[0] is None:
                raise RuntimeError(f"{pair_name}: do_slat_pair returned empty result")

            best0 = to_valid_match_array(best[0], pair_name=pair_name)
            matching_list.append(best0)

            log(
                f"{pair_name}: matching type={type(best0)}, "
                f"shape={getattr(best0, 'shape', None)}"
            )

        gene_expression, spatial, y, overlap = get_the_feature(river_adata_list, matching_list)

        log(f"gene_expression type: {type(gene_expression)}")
        log(f"spatial type: {type(spatial)}")
        log(f"y type: {type(y)}")
        try:
            log(f"gene_expression shape: {np.asarray(gene_expression).shape}")
        except Exception:
            pass
        try:
            log(f"spatial shape: {np.asarray(spatial).shape}")
        except Exception:
            pass
        try:
            log(f"label shape: {np.asarray(y).shape}")
        except Exception:
            pass
        try:
            log(f"overlap size: {len(overlap)}")
        except Exception:
            pass

        device = "cuda" if torch.cuda.is_available() else "cpu"
        log(f"Running River on device: {device}")

        model = River(gene_expression, spatial, y, device=device)
        model.train(epoch=epochs)

        ig, dl, sl = model.attribution()
        model.summary_attribution(ig, dl, sl, overlap)
        model.return_top_k_gene(top_k=200)

        rank_info = save_rank_outputs(model, out_dir)
        plot_adata_path, plot_feature_csv = save_plot_ready_adata(
            river_adata_list,
            sample_labels,
            out_dir,
            feature_names=rank_info.get("features"),
            feature_limit=200,
        )
        del model, gene_expression, spatial, y, ig, dl, sl
        force_memory_cleanup()

        return {
            "river_success": True,
            "message": "OK",
            "rank_file": rank_info["rank_file"],
            "rank_csv": rank_info["rank_csv"],
            "ig_file": rank_info["ig_file"],
            "dl_file": rank_info["dl_file"],
            "sl_file": rank_info["sl_file"],
            "plot_adata": plot_adata_path,
            "plot_feature_csv": plot_feature_csv,
        }

    except Exception as e:
        return {
            "river_success": False,
            "message": f"{err_text(e)}\n{traceback.format_exc()}",
            "rank_file": None,
            "rank_csv": None,
            "ig_file": None,
            "dl_file": None,
            "sl_file": None,
            "plot_adata": None,
            "plot_feature_csv": None,
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    random_seed = int(cfg.get("random_seed", 42))
    if random_seed != 42:
        raise ValueError("River ST-only requires the fixed random_seed=42.")
    seed_everything(random_seed)

    plot_png = str((out_dir / "river_combined_plot.png").resolve())
    plot_pdf = str((out_dir / "river_combined_plot.pdf").resolve())

    river_success = False
    msg = "OK"
    valid_samples = []
    invalid_samples = []

    rank_file = None
    rank_csv = None
    ig_file = None
    dl_file = None
    sl_file = None
    plot_adata = None
    plot_feature_csv = None

    try:
        log("=== river_runner.py started ===")
        log(f"Config path: {args.config}")
        log(f"Output dir : {args.output}")

        adata_list, valid_samples, invalid_samples = process_uploaded_samples(cfg)

        if adata_list:
            build_single_figure(
                adata_list=adata_list,
                sample_labels=valid_samples,
                plot_png=plot_png,
                plot_pdf=plot_pdf,
            )

            river_res = run_river_analysis(
                adata_list=adata_list,
                sample_labels=valid_samples,
                out_dir=out_dir,
                epochs=int(cfg.get("river_epochs", 100)),
            )

            river_success = river_res["river_success"]
            msg = river_res["message"]
            rank_file = river_res["rank_file"]
            rank_csv = river_res["rank_csv"]
            ig_file = river_res["ig_file"]
            dl_file = river_res["dl_file"]
            sl_file = river_res["sl_file"]
            plot_adata = river_res["plot_adata"]
            plot_feature_csv = river_res["plot_feature_csv"]

        else:
            msg = "No analyzable samples were found."

    except Exception as e:
        msg = f"{err_text(e)}\n{traceback.format_exc()}"

    summary = {
        "mode": cfg.get("mode"),
        "plot_png": plot_png if os.path.exists(plot_png) else None,
        "plot_pdf": plot_pdf if os.path.exists(plot_pdf) else None,

        "rank_file": rank_file if rank_file and os.path.exists(rank_file) else None,
        "rank_csv": rank_csv if rank_csv and os.path.exists(rank_csv) else None,

        "ig_file": ig_file if ig_file and os.path.exists(ig_file) else None,
        "dl_file": dl_file if dl_file and os.path.exists(dl_file) else None,
        "sl_file": sl_file if sl_file and os.path.exists(sl_file) else None,

        "plot_adata": plot_adata if plot_adata and os.path.exists(plot_adata) else None,
        "plot_feature_csv": plot_feature_csv if plot_feature_csv and os.path.exists(plot_feature_csv) else None,

        "river_success": river_success,
        "message": msg,
        "valid_samples": valid_samples,
        "invalid_samples": invalid_samples,
        "n_valid": len(valid_samples),
        "n_invalid": len(invalid_samples),
        "config": cfg,
    }

    (out_dir / "river_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    log(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
