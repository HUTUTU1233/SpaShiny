import argparse
import gc
import json
import os
import traceback
import sys
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
from scipy import sparse

from river.river import River
from river.preprocess import do_slat_pair, get_the_feature, seed_everything
sys.path.append(str(Path(__file__).resolve().parents[1]))
from cloud.river_input_contract import (
    input_settings, execution_settings, validate_parity_order, reference_sample_id,
    REFERENCE_GROUPS, validate_spatial, apply_plot_annotation, dense_feature_budget,
    adapt_feature_storage, PLATFORM_VERSION,
)
from river_platform_inputs import scanpy_sample, preprocess_expression, order_digest, versions, file_digest, matrix_digest
from river_pca_policy import apply_runner_pca
from cloud.river_unified_contract import V3, resolve_runner_settings


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


def materialize_for_processing(adata, target_n=None, analysis_mode='general'):
    if analysis_mode == 'original_python_parity':
        return scanpy_sample(adata, target_n=1052 if target_n is None else target_n)
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
    out.uns['_river_sampling_audit']={'algorithm':'numpy.default_rng.choice_sorted' if needs_subset else 'identity',
        'spots_before':int(adata.n_obs),'spots_after':int(out.n_obs),'random_state':0 if needs_subset else None,
        'general_selector_used':True,'scanpy_return_order_preserved':False,
        'obs_names_sha256':order_digest(out.obs_names)}
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


def extract_annotation_info(csv_path, adata, settings):
    apply_plot_annotation(adata, settings, csv_path=csv_path)
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


def read_uploaded_adata(data_path, target_n=None, analysis_mode='general'):
    data_path = str(data_path)
    suffix = Path(data_path).suffix.lower()

    if suffix == ".h5ad":
        backed = sc.read_h5ad(data_path, backed="r")
        try:
            adata = materialize_for_processing(backed, target_n=target_n, analysis_mode=analysis_mode)
            log(f"Loaded h5ad via backed subset: {data_path}, shape={adata.shape}")
            return adata
        finally:
            close_backed_adata(backed)

    if suffix == ".h5":
        try:
            adata = sc.read_10x_h5(data_path)
            adata = materialize_for_processing(adata, target_n=target_n, analysis_mode=analysis_mode)
            log(f"Loaded as 10x h5: {data_path}, shape={adata.shape}")
            return adata
        except Exception as e1:
            log(f"read_10x_h5 failed for {data_path}: {err_text(e1)}")

        try:
            backed = sc.read_h5ad(data_path, backed="r")
            try:
                adata = materialize_for_processing(backed, target_n=target_n, analysis_mode=analysis_mode)
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


def read_plot_metadata(data_path, analysis_mode='general'):
    """Read full-resolution obs/obsm metadata without a second X matrix."""
    try:
        if Path(data_path).suffix.lower() == ".h5ad":
            backed = sc.read_h5ad(data_path, backed="r")
            try:
                metadata = backed[:, []].to_memory()
            finally:
                close_backed_adata(backed)
            return metadata
    except Exception as exc:
        if analysis_mode=='original_python_parity':
            raise RuntimeError('Parity metadata reading failed; General input fallback is forbidden.') from exc
        log(f"Metadata-only read failed for {data_path}: {err_text(exc)}")
    return read_uploaded_adata(data_path, target_n=None)


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
            "original_h5ad":item.get('original_h5ad'),
            **({'resolved_input_scale':item['resolved_input_scale'],'validated_evidence':item.get('validated_evidence',{})} if cfg.get('execution_contract_version')==V3 else {}),
        })

    return normalized


def ensure_spatial(adata):
    validate_spatial(adata)
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


def prepare_basic_adata(adata, sample_id=None, condition=None, settings=None):
    parity=(settings or {}).get('analysis_mode')=='original_python_parity'
    if getattr(adata, "isbacked", False) or getattr(adata, "is_view", False):
        adata = materialize_for_processing(adata,analysis_mode='original_python_parity' if parity else 'general')
    if parity and not adata.var_names.is_unique:
        raise ValueError('Original H5AD parity rejects duplicate var_names; genes will not be renamed.')
    if not parity:adata.var_names_make_unique()

    adata.obs.index = adata.obs.index.astype(str)
    adata.var.index = adata.var.index.astype(str)

    adata = ensure_spatial(adata)

    if parity:
        reference_id=(settings or {}).get('verified_reference_sample_id') if (settings or {}).get('unified_contract') else reference_sample_id(sample_id)
        group=REFERENCE_GROUPS.get(reference_id,condition if condition else sample_id)
        adata.obs['sample']=reference_id or safe_str(sample_id)
        adata.obs['condition']=safe_str(group)
        adata.obs['batch']=safe_str(group)
    else:
        ensure_obs_column(adata, "condition", safe_str(condition if condition else sample_id))
        ensure_obs_column(adata, "batch", safe_str(condition if condition else sample_id))
    ensure_obs_column(adata, "sample_id", safe_str(sample_id if sample_id else "sample"))

    adata.obsm["spatial"] = np.asarray(adata.obsm["spatial"], dtype=float)[:, :2]
    return adata


def finalize_adata_for_river(adata, target_n=None, settings=None, trace=None):
    settings = settings or input_settings({'input_scale':'raw_counts'})
    adata = maybe_subsample(adata, target_n)
    if getattr(adata, "isbacked", False) or getattr(adata, "is_view", False):
        if settings['analysis_mode']=='original_python_parity':
            raise RuntimeError('Parity finalization requires the single completed Scanpy sampling result; no implicit materialization/resampling fallback is permitted.')
        adata = materialize_for_processing(adata)

    preprocessing = preprocess_expression(adata, settings)
    # 102843 never calls a runner PCA. scSLAT's original joint PCA remains
    # inside do_slat_pair(feature='pca'); General keeps its existing extra call.
    adata = apply_runner_pca(
        adata, preparation_policy=settings['analysis_mode'],
        ensure_pca=ensure_pca, trace=trace,
    )
    if trace is not None:
        trace['preprocessing'] = preprocessing

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


def _river_expression_cmap():
    """River's blue-white-red Balance scale, with a dependency-free fallback."""
    try:
        from palettable.cmocean.diverging import Balance_20
        return Balance_20.mpl_colormap
    except Exception:
        return plt.get_cmap("RdBu_r")


def _river_annotation_series(adata):
    if 'river_plot_group' not in adata.obs:
        raise ValueError('Plot annotation was not explicitly prepared; no implicit column fallback is permitted.')
    return adata.obs['river_plot_group'].astype(str)


def _river_annotation_colors(values):
    # Match the compact categorical palette used by the River reference panels.
    palette = [
        "#2C7FB8", "#ABD9E9", "#F07818", "#FDAE61", "#2CA02C",
        "#8BD646", "#E31A1C", "#FB8A99", "#9467BD", "#A6761D",
    ]
    return {value: palette[index % len(palette)] for index, value in enumerate(values)}


def _river_spatial_scatter(ax, adata, values, *, cmap=None, norm=None, size=12, colors=None):
    coords = np.asarray(adata.obsm["spatial"], dtype=float)[:, :2]
    if colors is not None:
        artist = ax.scatter(
            coords[:, 0], coords[:, 1], c=colors, s=size, linewidths=0,
            alpha=0.9, edgecolors="none"
        )
    else:
        artist = ax.scatter(
            coords[:, 0], coords[:, 1], c=np.asarray(values), cmap=cmap,
            norm=norm, s=size, linewidths=0, alpha=0.9, edgecolors="none"
        )
    ax.set_aspect("equal", adjustable="box")
    try:
        # Keep every sample panel physically square, including rectangular
        # tissue footprints such as WT2; the data itself remains undistorted.
        ax.set_box_aspect(1)
    except AttributeError:
        pass
    ax.invert_yaxis()
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_facecolor("white")
    for spine in ax.spines.values():
        spine.set_color("#4a4a4a")
        spine.set_linewidth(0.8)
    return artist


def build_single_figure(adata_list, sample_labels, plot_png, plot_pdf, analysis_mode='general'):
    if analysis_mode=='original_python_parity':
        try:
            import squidpy as sq
        except ImportError:
            sq=None
            log('Plot renderer fallback: Squidpy is unavailable. Retaining platform Matplotlib panels; numerical input parity is separate from figure reproduction.')
        if sq is not None:
            plot=ad.concat(stitch_slices_horizontally(adata_list),join='inner',index_unique='__')
            annotated=any(str(a.uns.get('river_plot_annotation',{}).get('source') or 'none')!='none' for a in adata_list)
            axes=sq.pl.spatial_scatter(plot,shape=None,color=['river_plot_group'] if annotated else None,
                figsize=(20,4),ncols=1,size=12,colorbar=False,return_ax=True,show=False)
            ax=axes[0] if isinstance(axes,(list,tuple,np.ndarray)) else axes
            fig=ax.figure
            try:
                ax.set_xlabel('');ax.set_ylabel('');ax.set_xticks([]);ax.set_yticks([])
                for collection in ax.collections:collection.set_rasterized(False)
                fig.savefig(plot_png,dpi=300,bbox_inches='tight',facecolor='white')
                fig.savefig(plot_pdf,dpi=300,bbox_inches='tight',facecolor='white')
            finally:plt.close(fig)
            return {'renderer':'squidpy.pl.spatial_scatter','version':versions()['squidpy'],'original_layout':True,'fallback':False}
    unique_ann = []
    annotation_vectors = []
    for adata in adata_list:
        series = _river_annotation_series(adata)
        annotation_vectors.append(series)
        for value in series.unique().tolist():
            if value not in unique_ann:
                unique_ann.append(value)
    if not unique_ann:
        unique_ann = ["Unknown"]
    color_map = _river_annotation_colors(unique_ann)

    n_samples = max(1, len(adata_list))
    fig, axes = plt.subplots(
        1, n_samples, figsize=(4.15 * n_samples, 4.8), squeeze=False,
        sharex=False, sharey=False
    )
    axes_flat = axes.ravel()
    for index, (adata, label, annotations) in enumerate(
        zip(adata_list, sample_labels, annotation_vectors)
    ):
        ax = axes_flat[index]
        colors = [color_map.get(value, "#999999") for value in annotations.tolist()]
        highlighted = str(adata.uns.get('river_plot_annotation',{}).get('highlight') or '')
        if highlighted:
            colors = [color if str(value)==highlighted else '#dddddd' for value,color in zip(annotations.tolist(),colors)]
        _river_spatial_scatter(ax, adata, None, size=12, colors=colors)
        ax.set_title(safe_str(label), fontsize=11, fontweight="bold", pad=7)
    for index in range(len(adata_list), len(axes_flat)):
        axes_flat[index].axis("off")

    handles = [
        Line2D([0], [0], marker="o", color="w", label=value,
               markerfacecolor=color_map[value], markersize=6.5)
        for value in unique_ann
    ]
    fig.legend(
        handles=handles, title="annotation", loc="center left",
        bbox_to_anchor=(0.995, 0.5), frameon=False, borderaxespad=0.0
    )
    fig.suptitle("River combined spatial plot", fontsize=14, fontweight="bold", y=1.02)
    fig.subplots_adjust(left=0.02, right=0.88, bottom=0.06, top=0.86, wspace=0.08)
    fig.savefig(plot_png, dpi=300, bbox_inches="tight", facecolor="white")
    fig.savefig(plot_pdf, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return {'renderer':'matplotlib.axes.Axes.scatter','version':versions()['matplotlib'],'original_layout':False,
        'fallback':analysis_mode=='original_python_parity',
        'notice':'Squidpy unavailable: existing platform panel renderer retained; figure parity is not claimed.' if analysis_mode=='original_python_parity' else ''}


def _gene_expression_values(adata, gene):
    if gene not in adata.var_names:
        raise RuntimeError(f"Representative gene {gene!r} is missing from one or more time points.")
    values = adata[:, gene].X
    if sparse.issparse(values):
        values = values.toarray()
    values = np.asarray(values, dtype=float).reshape(-1)
    if values.size != adata.n_obs:
        raise RuntimeError(f"Representative gene {gene!r} produced an unexpected expression vector shape.")
    if not np.isfinite(values).all():
        raise RuntimeError(f"Representative gene {gene!r} contains NaN or Inf values.")
    return values


def build_representative_gene_figures(adata_list, sample_labels, gene, out_dir):
    gene = safe_str(gene).strip()
    if not gene:
        return {}
    expression_vectors = [_gene_expression_values(adata, gene) for adata in adata_list]
    rows = []
    for order, (label, values) in enumerate(zip(sample_labels, expression_vectors), start=1):
        std = float(np.std(values, ddof=1)) if values.size > 1 else 0.0
        rows.append(
            {
                "time_order": order,
                "time_label": safe_str(label),
                "representative_gene": gene,
                "n_spots": int(values.size),
                "mean_expression": float(np.mean(values)),
                "median_expression": float(np.median(values)),
                "std_expression": std,
                "sem_expression": float(std / np.sqrt(values.size)) if values.size else 0.0,
                "detected_fraction": float(np.mean(values > 0)) if values.size else 0.0,
            }
        )

    temporal_csv = out_dir / "river_selected_gene_temporal.csv"
    temporal_png = out_dir / "river_selected_gene_temporal.png"
    temporal_pdf = out_dir / "river_selected_gene_temporal.pdf"
    spatial_png = out_dir / "river_selected_gene_spatial.png"
    spatial_pdf = out_dir / "river_selected_gene_spatial.pdf"
    temporal_df = pd.DataFrame(rows)
    temporal_df.to_csv(temporal_csv, index=False)

    fig, ax = plt.subplots(figsize=(max(7, len(rows) * 1.2), 5.5))
    positions = np.arange(1, len(rows) + 1)
    means = temporal_df["mean_expression"].to_numpy(dtype=float)
    sems = temporal_df["sem_expression"].to_numpy(dtype=float)
    ax.errorbar(positions, means, yerr=sems, marker="o", linewidth=2.2, capsize=4, color="#2563EB")
    ax.set_xticks(positions)
    ax.set_xticklabels(temporal_df["time_label"].astype(str).tolist(), rotation=35, ha="right")
    ax.set_xlabel("User-defined time order")
    ax.set_ylabel("Mean log-normalized expression ± SEM")
    ax.set_title(f"Temporal expression of {gene}", fontweight="bold")
    ax.grid(axis="y", color="#E5E7EB", linewidth=0.8)
    fig.tight_layout()
    fig.savefig(temporal_png, dpi=300, bbox_inches="tight")
    fig.savefig(temporal_pdf, dpi=300, bbox_inches="tight")
    plt.close(fig)

    all_values = np.concatenate(expression_vectors) if expression_vectors else np.asarray([0.0])
    vmin = 0.0
    vmax = float(np.nanpercentile(all_values, 99))
    if not np.isfinite(vmin) or not np.isfinite(vmax):
        raise RuntimeError(f"Representative gene {gene!r} produced a non-finite plot scale.")
    if vmax <= vmin:
        vmax = vmin + 1.0
    n_samples = max(1, len(adata_list))
    fig, axes = plt.subplots(
        1,
        n_samples,
        figsize=(4.15 * n_samples, 4.8),
        squeeze=False,
    )
    axes_flat = axes.ravel()
    cmap = _river_expression_cmap()
    norm = matplotlib.colors.Normalize(vmin=vmin, vmax=vmax)
    mappable = None
    for index, (adata, label, values) in enumerate(zip(adata_list, sample_labels, expression_vectors)):
        ax = axes_flat[index]
        mappable = _river_spatial_scatter(
            ax, adata, values, cmap=cmap, norm=norm, size=12
        )
        ax.set_title(f"{index + 1}. {safe_str(label)}", fontsize=10, pad=7)
    for index in range(len(adata_list), len(axes_flat)):
        axes_flat[index].axis("off")
    if mappable is not None:
        colorbar_ax = fig.add_axes([0.955, 0.20, 0.014, 0.58])
        fig.colorbar(mappable, cax=colorbar_ax, label="Log-normalized expression")
    fig.suptitle(f"Spatial expression of {gene} across user-defined time points", fontweight="bold", y=1.02)
    fig.subplots_adjust(left=0.02, right=0.94, bottom=0.06, top=0.84, wspace=0.08)
    fig.savefig(spatial_png, dpi=300, bbox_inches="tight", facecolor="white")
    fig.savefig(spatial_pdf, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return {
        "representative_gene": gene,
        "temporal_csv": str(temporal_csv),
        "temporal_png": str(temporal_png),
        "temporal_pdf": str(temporal_pdf),
        "spatial_png": str(spatial_png),
        "spatial_pdf": str(spatial_pdf),
    }


def normalize_feature_names(feature_names, limit=200):
    out = []
    for name in feature_names or []:
        name = safe_str(name)
        if name and name not in out:
            out.append(name)
        if limit and len(out) >= int(limit):
            break
    return out


def save_plot_ready_adata(adata_list, sample_labels, out_dir, feature_names=None, feature_limit=None, analysis_mode='general',job_id=''):
    """
    Save an h5ad object that the Shiny frontend can use to redraw selected features.
    """
    selected_features = normalize_feature_names(feature_names, limit=feature_limit)
    prepared = []
    for i, (adata, label) in enumerate(zip(adata_list, sample_labels)):
        present = [f for f in selected_features if f in adata.var_names]
        if feature_limit is None:
            a = adata.copy()
        elif present:
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
    plot_adata.uns['river_plot_cache'] = {'version':3,'analysis_mode':analysis_mode,'platform_version':PLATFORM_VERSION,
        'feature_scope':'all' if feature_limit is None else 'limited',
        'expression_scale':'Existing River normalized/log1p values; no further normalization during redraw'}
    if job_id:plot_adata.uns['river_plot_cache']['job_id']=str(job_id)
    plot_adata.write_h5ad(plot_adata_path,compression='gzip',compression_opts=1)

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
    pd.DataFrame({'feature':final_rank[:200]}).to_csv(out_dir/'river_top200_genes.csv',index=False)

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
    settings = resolve_runner_settings(cfg,execution_settings)
    samples = normalize_cfg_samples(cfg)
    if len(samples)<2 or len({s['sample_id'] for s in samples})!=len(samples):
        raise ValueError('Select at least two samples with unique sample IDs.')
    order_policy='explicit_unified_sample_order' if cfg.get('execution_contract_version')==V3 else validate_parity_order([s['sample_id'] for s in samples],settings['analysis_mode'])
    trace = cfg.setdefault('_execution_trace', {'platform_version':PLATFORM_VERSION,
        'requested_samples':[s['sample_id'] for s in samples], 'loaded_samples':[], 'paired_samples':[],
        'model_samples':[], 'sample_checks':[], 'core_algorithm_modified':False})
    trace.update(analysis_mode=settings['analysis_mode'],requested_analysis_mode=settings['requested_analysis_mode'],
        execution_contract_version=settings['execution_contract_version'],
        input_scale='per_sample_verified' if cfg.get('execution_contract_version')==V3 else settings['input_scale'],
        requested_samples=[s['sample_id'] for s in samples],
        sample_order_policy=order_policy,sample_order=[s['sample_id'] for s in samples],
        reference_sample_order=[reference_sample_id(s['sample_id']) for s in samples],
        worker_mode_lineage=cfg.get('worker_mode_lineage',{}))
    subsample_size = cfg.get("subsample_size", 0) or 0

    sample_records = []
    invalid_samples = []

    for item in samples:
        sample_id = item["sample_id"]
        condition = item["condition"]
        data_path = item["data_path"]

        display_name = condition if condition else sample_id

        if not data_path or not os.path.exists(data_path):
            raise ValueError(f'{sample_id}: input inspection failed: missing required data file.')

        try:
            shape = inspect_uploaded_adata_shape(data_path)
            sample_records.append((item, display_name, shape))
            log(
                f"Inspected sample: sample_id={sample_id}, "
                f"condition={condition}, shape={shape}"
            )

        except Exception as e:
            raise ValueError(f'{sample_id}: input inspection failed: {err_text(e)}') from e

    min_n_obs = min(shape[0] for _, _, shape in sample_records)
    import sys
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from cloud.river_options import resolve_subsample_size
    parity = settings['analysis_mode']=='original_python_parity'
    requested = 1052 if parity else (min(min_n_obs,subsample_size) if cfg.get('subsample_mode')=='legacy_limit' and subsample_size>0 else subsample_size)
    target_n = resolve_subsample_size([shape[0] for _,_,shape in sample_records],requested)
    cfg['_resolved_sampling'] = {'minimum_sample_spots':min_n_obs,'resolved_n_obs':target_n,'random_state':0,
        'mode':'original_python_parity' if parity else cfg.get('subsample_mode','minimum' if subsample_size==0 else 'custom'),
        'requested_subsample_mode':cfg.get('subsample_mode'),
        'samples':{item['sample_id']:shape[0] for item,_,shape in sample_records}}

    log(f"Unified subsample size across all samples: {target_n}")

    adata_list = []
    plot_adata_list = []
    final_valid_samples = []

    for item, label, _shape in sample_records:
        sample_id = item["sample_id"]
        condition = item["condition"]
        data_path = item["data_path"]
        csv_path = item["csv_path"]

        try:
            sample_settings=settings
            if cfg.get('execution_contract_version')==V3:
                from cloud.river_trusted_inputs import FILES
                reference_ids={digest:name.split('_',1)[0] for name,digest in FILES.items()}
                sample_settings={**settings,'input_scale':item['resolved_input_scale'],'unified_contract':True,
                    'verified_reference_sample_id':reference_ids.get(item.get('original_h5ad',{}).get('sha256'))}
            prepared_file=file_digest(data_path)
            sample_trace={'sample_id':sample_id,'reference_sample_id':reference_sample_id(sample_id),
                'source_shape':list(_shape),'spots_before_sampling':int(_shape[0]),
                'original_h5ad':item.get('original_h5ad') or prepared_file,'prepared_h5ad':prepared_file}
            log(f"Loading data file: {data_path}")
            plot_adata = read_plot_metadata(data_path,analysis_mode=settings['analysis_mode'])
            sample_trace['spatial']=validate_spatial(plot_adata,sample=sample_id,allow_obs_coordinates=not parity)
            sample_trace['annotation']=apply_plot_annotation(plot_adata,settings,csv_path=csv_path,sample=sample_id)
            plot_adata = prepare_basic_adata(
                plot_adata,
                sample_id=sample_id,
                condition=condition,
                settings=sample_settings,
            )

            adata = read_uploaded_adata(data_path, target_n=target_n, analysis_mode=settings['analysis_mode'])
            validate_spatial(adata,sample=sample_id,allow_obs_coordinates=not parity)
            apply_plot_annotation(adata,settings,csv_path=csv_path,sample=sample_id)

            adata = prepare_basic_adata(
                adata,
                sample_id=sample_id,
                condition=condition,
                settings=sample_settings,
            )

            if adata.n_obs < 3:
                raise RuntimeError(f"Too few cells/spots after loading: n_obs={adata.n_obs}")

            adata2 = finalize_adata_for_river(adata, target_n=None,settings=sample_settings,trace=sample_trace)
            sample_trace.update(n_obs=adata2.n_obs,obs_order_sha256=order_digest(adata2.obs_names),var_order_sha256=order_digest(adata2.var_names))
            sample_trace.update(spots_after_sampling=int(adata2.n_obs),
                obs_names_sha256=order_digest(adata2.obs_names),var_names_sha256=order_digest(adata2.var_names),
                sampling=dict(adata2.uns.get('_river_sampling_audit',{})),
                expression=matrix_digest(adata2.X),spatial_coordinates=matrix_digest(adata2.obsm['spatial']))
            trace['sample_checks'].append(sample_trace)
            trace['loaded_samples'].append(sample_id)
            adata_list.append(adata2)
            plot_adata_list.append(plot_adata)
            final_valid_samples.append(label)

            coords = np.asarray(adata2.obsm["spatial"], dtype=float)
            w = coords[:, 0].max() - coords[:, 0].min()
            h = coords[:, 1].max() - coords[:, 1].min()

            log(
                f"Finalized sample: {label}, "
                f"shape={adata2.shape}, width={w:.2f}, height={h:.2f}"
            )

        except Exception as e:
            raise ValueError(f'{sample_id}: loading/preprocessing/annotation failed: {err_text(e)}. Strict mode does not omit failed samples.') from e
        finally:
            force_memory_cleanup()

    return adata_list, final_valid_samples, invalid_samples, plot_adata_list


def run_river_analysis(adata_list, sample_labels, out_dir, epochs=100, representative_gene=None, analysis_mode='general', trace=None,unified_config=None):
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
        if analysis_mode=='original_python_parity' and epochs!=100:
            raise ValueError('Original Python parity requires exactly 100 training epochs.')
        # Canonical model XY must never be shifted for a display layout.
        river_adata_list = adata_list
        original_xy = [np.asarray(a.obsm['spatial']).copy() for a in adata_list]
        budget = dense_feature_budget(river_adata_list)
        for a in river_adata_list:
            adapt_feature_storage(a)
        if trace is not None:
            trace['dense_feature_budget']=budget
        if analysis_mode=='original_python_parity':
            seed_everything(42)
            if trace is not None:trace['seed_before_slat']=42

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
            if not np.issubdtype(best0.dtype,np.integer) or best0.ndim!=1 or len(best0)!=cur_adata.n_obs or np.any(best0<0) or np.any(best0>=ref_adata.n_obs):
                raise ValueError(f'{pair_name}: invalid query-to-reference matching indices; refusing to continue.')
            matching_list.append(best0)
            if unified_config is not None and trace is not None:
                from river_passive_trace import array_fingerprint
                trace.setdefault('canonical_matching_fingerprints',[]).append(array_fingerprint(best0))
            if trace is not None:
                trace['paired_samples'].append({'reference':trace['loaded_samples'][0],'query':trace['loaded_samples'][i],
                    'matched_query_spots':len(best0),'unique_reference_spots':int(len(np.unique(best0)))})
                trace['paired_samples'][-1].update(matching_indices=matrix_digest(best0),
                    query_to_reference_indices=best0.tolist() if analysis_mode=='original_python_parity' else None,
                    feature='pca',direction='query_to_first_sample_reference',
                    reference_spots=int(ref_adata.n_obs),query_spots=int(cur_adata.n_obs),
                    matching_algorithm='unchanged river.preprocess.do_slat_pair')

            log(
                f"{pair_name}: matching type={type(best0)}, "
                f"shape={getattr(best0, 'shape', None)}"
            )

        gene_expression, spatial, y, overlap = get_the_feature(river_adata_list, matching_list)
        if not all(np.array_equal(a.obsm['spatial'],xy) for a,xy in zip(adata_list,original_xy)):
            raise RuntimeError('Canonical model coordinates changed during preparation; refusing to rank.')
        if trace is not None:
            trace['model_samples']=list(trace['loaded_samples'])
            trace['model_input_shape']=list(gene_expression.shape)
            trace['model_coordinates_unstitched']=True
            trace['model_inputs']={'gene_expression':matrix_digest(gene_expression),
                'spatial':matrix_digest(spatial),'y':matrix_digest(y),
                'gene_order_sha256':order_digest(overlap)}

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
        historical_v2=trace is not None and trace.get('execution_mode')=='original_python_parity'
        if historical_v2:
            from river_passive_trace import model_fingerprints,rng_fingerprints,array_fingerprint
            trace['initial_model']=model_fingerprints(model.model)
            trace['rng_before_training']=rng_fingerprints()
            trace['canonical_model_inputs']={name:array_fingerprint(value) for name,value in (
                ('gene_expression',gene_expression),('spatial',spatial),('y',y))}
        if unified_config is not None:
            from river_historical_rng_guard import maybe_restore_history_cuda0
            trace['historical_rng']=maybe_restore_history_cuda0(unified_config,trace,model)
        if trace is not None:trace['training']={'epochs':int(epochs),'random_seed':42,'status':'started'}
        model.train(epoch=epochs)
        if trace is not None:trace['training']['status']='completed'
        if historical_v2:
            trace['final_model']=model_fingerprints(model.model)
            trace['rng_after_training']=rng_fingerprints()

        ig, dl, sl = model.attribution()
        model.summary_attribution(ig, dl, sl, overlap)
        if historical_v2:
            trace['normalized_attribution']={name:array_fingerprint(value) for name,value in (
                ('IG',model.scores_ig),('DeepLiftShap',model.scores_dl),('GradientShap',model.scores_sl))}
        model.return_top_k_gene(top_k=200)
        if trace is not None:trace['top_200_genes']=[str(value) for value in model.final_rank.index[:200]]

        rank_info = save_rank_outputs(model, out_dir)
        plot_features = list(rank_info.get("features") or [])
        if representative_gene:
            plot_features = [representative_gene, *plot_features]
        plot_adata_path, plot_feature_csv = save_plot_ready_adata(
            stitch_slices_horizontally(adata_list, gap=50.0),
            sample_labels,
            out_dir,
            feature_names=plot_features,
            feature_limit=None,
            analysis_mode=analysis_mode,
            job_id=trace.get('job_id','') if trace else '',
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

    random_seed = cfg.get("random_seed", 42)
    settings={}
    cfg['_execution_trace']={'trace_schema':'river-execution-trace-v2','platform_version':PLATFORM_VERSION,
        'execution_mode':cfg.get('platform_execution',{}).get('execution_mode'),
        'job_id':cfg.get('job_id',''),
        'requested_analysis_mode':cfg.get('requested_analysis_mode',cfg.get('analysis_mode')),
        'analysis_mode':None,'requested_samples':[],'loaded_samples':[],'paired_samples':[],
        'model_samples':[],'sample_checks':[],'core_algorithm_modified':False,
        'training':{'epochs':cfg.get('river_epochs',100),'random_seed':random_seed,'status':'not_started'}}

    plot_png = str((out_dir / "river_combined_plot.png").resolve())
    plot_pdf = str((out_dir / "river_combined_plot.pdf").resolve())
    representative_gene = safe_str(cfg.get("representative_gene", "")).strip()

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
    gene_plot_info = {}

    try:
        log("=== river_runner.py started ===")
        log(f"Config path: {args.config}")
        log(f"Output dir : {args.output}")

        settings=resolve_runner_settings(cfg,execution_settings)
        seed_everything(random_seed)
        import inspect
        cfg['_execution_trace']['code_paths']={
            'runner':file_digest(__file__),'River':file_digest(inspect.getfile(River)),
            'SimpleNN':file_digest(inspect.getfile(sys.modules[River.__module__].SimpleNN)),
            'do_slat_pair':file_digest(inspect.getfile(do_slat_pair)),
            'get_the_feature':file_digest(inspect.getfile(get_the_feature))}
        adata_list, valid_samples, invalid_samples, plot_adata_list = process_uploaded_samples(cfg)

        if adata_list:
            plot_engine=build_single_figure(
                adata_list=plot_adata_list,
                sample_labels=valid_samples,
                plot_png=plot_png,
                plot_pdf=plot_pdf,
                analysis_mode=settings['analysis_mode'],
            )
            cfg['_execution_trace']['combined_plot_engine']=plot_engine
            river_res = run_river_analysis(
                adata_list=adata_list,
                sample_labels=valid_samples,
                out_dir=out_dir,
                epochs=int(cfg.get("river_epochs", 100)),
                representative_gene=representative_gene,
                analysis_mode=settings['analysis_mode'],trace=cfg['_execution_trace'],
                unified_config=cfg if cfg.get('execution_contract_version')==V3 else None,
            )

            river_success = river_res["river_success"]
            if river_success and representative_gene:
                gene_plot_info = build_representative_gene_figures(
                    adata_list=adata_list,sample_labels=valid_samples,gene=representative_gene,out_dir=out_dir)
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
        river_success = False
        msg = f"{err_text(e)}\n{traceback.format_exc()}"

    summary = {
        "mode": cfg.get("mode"),
        'analysis_mode':settings.get('analysis_mode'),
        'requested_analysis_mode':cfg.get('requested_analysis_mode',cfg.get('analysis_mode')),
        'input_scale':'per_sample_verified' if cfg.get('execution_contract_version')==V3 else settings.get('input_scale'),
        'sample_expression_states':[{k:row.get(k) for k in ('file_name','file_sha256','scale','evidence_source')}
            for row in cfg.get('platform_execution',{}).get('sample_evidence',[])],
        'river_epochs':cfg.get('river_epochs',100),
        "sampling": cfg.get('_resolved_sampling', {}),
        "plot_png": plot_png if os.path.exists(plot_png) else None,
        "plot_pdf": plot_pdf if os.path.exists(plot_pdf) else None,

        "rank_file": rank_file if rank_file and os.path.exists(rank_file) else None,
        "rank_csv": rank_csv if rank_csv and os.path.exists(rank_csv) else None,

        "ig_file": ig_file if ig_file and os.path.exists(ig_file) else None,
        "dl_file": dl_file if dl_file and os.path.exists(dl_file) else None,
        "sl_file": sl_file if sl_file and os.path.exists(sl_file) else None,

        "plot_adata": plot_adata if plot_adata and os.path.exists(plot_adata) else None,
        "plot_feature_csv": plot_feature_csv if plot_feature_csv and os.path.exists(plot_feature_csv) else None,
        "representative_gene": representative_gene or None,
        "representative_gene_plots": gene_plot_info,

        "river_success": river_success,
        "message": msg,
        "valid_samples": valid_samples,
        "invalid_samples": invalid_samples,
        "n_valid": len(valid_samples),
        "n_invalid": len(invalid_samples),
        'input_contract': {key:settings.get(key) for key in ('analysis_mode','input_scale','annotation_source','annotation_column','annotation_value','allow_missing_annotation')},
        'platform_version': PLATFORM_VERSION,
        'historical_rng':cfg.get('_execution_trace',{}).get('historical_rng',{}),
    }

    (out_dir / "river_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    trace=dict(cfg.get('_execution_trace') or {})
    trace.update(versions=versions(),random_seed=random_seed,subsample=cfg.get('_resolved_sampling',{}),
                 technical_success=bool(river_success),scientific_validity='UNVERIFIED_ORIGINAL_ALGORITHM')
    (out_dir/'river_execution_trace.json').write_text(json.dumps(trace,indent=2),encoding='utf-8')

    log(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
