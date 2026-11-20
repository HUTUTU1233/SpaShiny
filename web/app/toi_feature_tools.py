"""Read-only adapters for SpatialMETA TOI figures.

The installed SpatialMETA functions are called unchanged.  The curve API only
accepts ``trajectory_1`` internally; we expose the selected trajectory under that
name in a private plotting object, never overwrite the live viewer's first path.
No normalization, model training, differential ranking or geometry is run here.
"""
from __future__ import annotations

import copy
import hashlib
import json
import threading
from collections.abc import Mapping

PLOT_LOCK = threading.RLock()
TOI_PLOT_ADAPTER_VERSION = "spatialmeta-native-toi-figures-v1"
MAX_SELECTED_FEATURES = 50
MAX_HEATMAP_FEATURES = 500
MAX_HEATMAP_ELEMENTS = 2_000_000
MAX_SMOOTHING_WORK = 500_000_000

_MODALITIES = {
    **dict.fromkeys(("ST", "GENE", "GENES", "RNA", "TRANSCRIPT", "TRANSCRIPTOMICS", "SPATIAL_TRANSCRIPTOMICS"), "ST"),
    **dict.fromkeys(("SM", "SM_POS", "SM_NEG", "METABOLITE", "METABOLITES", "MZ", "M/Z", "MSI", "MALDI", "METABOLOMICS", "SPATIAL_METABOLOMICS"), "SM"),
}


def _modality(value):
    result = _MODALITIES.get(str(value).strip().upper())
    if not result:
        raise ValueError("Choose an explicit gene (ST) or m/z (SM) feature type.")
    return result


def _feature_types(adata):
    if "type" not in adata.var:
        raise ValueError("The current input has no var['type'] ST/SM labels; feature types cannot be guessed.")
    result = adata.var["type"].astype(str).str.strip().str.upper().map(_MODALITIES)
    if result.isna().any():
        raise ValueError("The current input contains unrecognized feature type labels. Supply explicit ST/SM labels.")
    return result


def list_feature_choices(adata, modality):
    """Return original exact IDs, retaining their column order and m/z precision."""
    if adata is None:
        return []
    requested = _modality(modality)
    if not adata.var_names.is_unique:
        raise ValueError("Feature IDs are not unique; choose an input with unambiguous gene/m/z IDs.")
    types = _feature_types(adata)
    return [str(name) for name in adata.var_names[types.to_numpy() == requested]]


def list_trajectory_keys(adata):
    if adata is None:
        return []
    trajectories = adata.uns.get("trajectory", {})
    if not isinstance(trajectories, Mapping):
        return []
    def order(value):
        text = str(value)
        suffix = text.rsplit("_", 1)[-1]
        return (0, int(suffix), text) if suffix.isdigit() else (1, 0, text)
    return sorted((str(key) for key in trajectories), key=order)


def _trajectory(adata, key):
    import numpy as np
    if adata is None:
        raise ValueError("Load the current analysis input and draw a TOI first.")
    trajectories = adata.uns.get("trajectory", {})
    if not isinstance(trajectories, Mapping) or key not in trajectories:
        raise ValueError(f"TOI '{key}' is unavailable in the current viewer. Refresh the TOI list and select a drawn path.")
    entry = trajectories[key]
    if not isinstance(entry, Mapping):
        raise ValueError("The selected TOI metadata is invalid.")
    indices = np.asarray(entry.get("indices", []))
    locations = np.asarray(entry.get("locations", []), dtype=float)
    if indices.ndim != 1 or locations.ndim != 1 or indices.size != locations.size:
        raise ValueError("TOI indices and locations must be one-dimensional and have identical lengths.")
    if indices.size < 2:
        raise ValueError("The selected TOI contains fewer than two spots; draw a path covering more spots.")
    if indices.dtype.kind not in "iu" or indices.dtype.kind == "b":
        raise ValueError("TOI indices must be integer row positions, not labels or fractional positions.")
    indices = indices.astype("int64", copy=True)
    if (indices < 0).any() or (indices >= adata.n_obs).any():
        raise ValueError("TOI indices do not match the current input rows. Draw a new TOI for this input.")
    if len(np.unique(indices)) != len(indices):
        raise ValueError("The selected TOI contains repeated row indices.")
    if not np.isfinite(locations).all() or np.ptp(locations) <= 0:
        raise ValueError("TOI locations must be finite and span more than one position.")
    return entry, indices, locations


def trajectory_fingerprint(adata, key):
    """Fingerprint geometry + row/column identity, not a full expression checksum."""
    import numpy as np
    entry, indices, locations = _trajectory(adata, key)
    digest = hashlib.sha256()
    for value in (str(key), str(entry.get("path", "")), "\0".join(map(str, adata.obs_names)), "\0".join(map(str, adata.var_names))):
        payload = value.encode("utf-8")
        digest.update(len(payload).to_bytes(8, "little")); digest.update(payload)
    digest.update(np.asarray(indices, dtype="<i8").tobytes())
    digest.update(np.asarray(locations, dtype="<f8").tobytes())
    return digest.hexdigest()


def _validate_features(adata, features, modality=None):
    if isinstance(features, (str, bytes)) or not features:
        raise ValueError("Select one or more exact gene or m/z IDs.")
    names = [str(value).strip() for value in features]
    if any(not name for name in names) or len(names) != len(set(names)):
        raise ValueError("Selected feature IDs must be nonempty and unique.")
    if not adata.var_names.is_unique:
        raise ValueError("The input contains duplicate feature IDs.")
    positions = adata.var_names.get_indexer(names)
    missing = [name for name, index in zip(names, positions) if index < 0]
    if missing:
        raise ValueError("Feature ID(s) not present in this input: " + ", ".join(missing[:8]))
    if modality is not None:
        types = _feature_types(adata)
        expected = _modality(modality)
        wrong = [name for name, index in zip(names, positions) if types.iloc[index] != expected]
        if wrong:
            raise ValueError("Feature ID(s) do not belong to the selected feature type: " + ", ".join(wrong[:8]))
    return names, positions


def _normalized(adata):
    import numpy as np
    if "normalized" not in adata.layers:
        raise ValueError("Feature Trajectory requires the existing layers['normalized']. No X fallback or automatic normalization is permitted.")
    matrix = adata.layers["normalized"]
    if tuple(matrix.shape) != tuple(adata.shape):
        raise ValueError("The normalized layer does not match the current input shape.")
    if matrix.dtype.kind not in "biuf":
        raise ValueError("The normalized layer must contain real numeric values.")
    return matrix


def _selected_matrix(matrix, rows, columns):
    """Slice columns first for sparse matrices; never copy all dense features."""
    import numpy as np
    from scipy import sparse
    if sparse.issparse(matrix):
        return matrix[:, columns][rows, :]
    return np.asarray(matrix)[np.ix_(np.asarray(rows, dtype=int), np.asarray(columns, dtype=int))]


def _dense_selected(matrix, rows, columns):
    import numpy as np
    from scipy import sparse
    values = _selected_matrix(matrix, rows, columns)
    values = values.toarray() if sparse.issparse(values) else np.asarray(values)
    return np.asarray(values)


def _private_adata(adata, columns, trajectory, rows=None):
    """Keep exact identity and values; only plotting-required metadata is copied."""
    import anndata as ad
    import numpy as np
    from scipy import sparse
    if rows is None:
        rows = np.arange(adata.n_obs, dtype=int)
    result = ad.AnnData(
        X=sparse.csr_matrix(_selected_matrix(adata.X, rows, columns), copy=True),
        obs=adata.obs.iloc[rows, :0].copy(),
        var=adata.var.iloc[columns].copy(),
        layers={"normalized": sparse.csr_matrix(_selected_matrix(_normalized(adata), rows, columns), copy=True)},
    )
    if "spatial" in adata.obsm:
        result.obsm["spatial"] = np.asarray(adata.obsm["spatial"])[rows].copy()
    result.uns["trajectory"] = {"trajectory_1": copy.deepcopy(dict(trajectory))}
    return result


def _native_figure(plotter, adata, **kwargs):
    """Capture an upstream return-None Figure without closing unrelated figures."""
    import matplotlib.pyplot as plt
    from matplotlib.figure import Figure
    with PLOT_LOCK:
        before = set(plt.get_fignums())
        original_show = plt.show
        result_figure = None
        try:
            plt.show = lambda *args, **kw: None
            returned = plotter(adata, **kwargs)
            created = set(plt.get_fignums()) - before
            if isinstance(returned, Figure):
                result_figure = returned
            elif len(created) == 1:
                result_figure = plt.figure(next(iter(created)))
            else:
                raise ValueError("SpatialMETA did not produce exactly one Figure for the selected TOI.")
            if not result_figure.axes:
                raise ValueError("SpatialMETA produced an empty Figure for the selected TOI.")
            return result_figure
        finally:
            plt.show = original_show
            for number in set(plt.get_fignums()) - before:
                figure = plt.figure(number)
                if figure is not result_figure:
                    plt.close(figure)


def build_preview_image(figure, dpi=120):
    """Preview only: never hand the export Figure to Shiny's resizing renderer.

    Shiny's Matplotlib renderer mutates Figure size, DPI and layout. A detached
    PIL preview keeps the original vector Figure intact for PDF/SVG downloads.
    This bitmap is used only in the browser, never embedded in a PDF export.
    """
    import io
    from PIL import Image
    with PLOT_LOCK, io.BytesIO() as buffer:
        figure.savefig(buffer, format="png", dpi=dpi, bbox_inches="tight")
        buffer.seek(0)
        with Image.open(buffer) as image:
            return image.copy()


def _metadata(adata, key, features, values, kind, **extra):
    import numpy as np
    digest = hashlib.sha256()
    array = np.ascontiguousarray(values)
    digest.update(str(array.shape).encode()); digest.update(array.dtype.str.encode()); digest.update(array.tobytes())
    return {
        "adapter_version": TOI_PLOT_ADAPTER_VERSION,
        "original_key": key,
        "trajectory_key": key,
        "fingerprint": trajectory_fingerprint(adata, key),
        "matrix_source": "layers['normalized']",
        "selected_normalized_sha256": digest.hexdigest(),
        "features": list(features), "kind": kind,
        "normalization_executed": False, "trajectory_recomputed": False,
        "upstream_code_modified": False, **extra,
    }


def build_feature_trajectory_figure(adata, key, features, *, modality=None, bins=100,
                                    scale=True, figsize=(8, 6), plotter=None):
    """Call SpatialMETA's original curve function for this selected TOI only.

    Native semantics are retained: zero-expression spots are omitted per feature,
    bands are standard deviation, and min-max scaling is per nonzero feature.
    Invalid native edge cases fail explicitly rather than creating a success plot.
    """
    import numpy as np
    entry, indices, locations = _trajectory(adata, str(key))
    names, columns = _validate_features(adata, features, modality)
    if len(names) > MAX_SELECTED_FEATURES:
        raise ValueError(f"Select at most {MAX_SELECTED_FEATURES} features per curve figure.")
    if isinstance(bins, bool) or not isinstance(bins, (int, np.integer)) or not 2 <= int(bins) <= 1000:
        raise ValueError("Bins must be an integer between 2 and 1000.")
    if len(figsize) != 2 or any(not np.isfinite(value) or not 2 <= float(value) <= 24 for value in figsize):
        raise ValueError("Figure width and height must each be between 2 and 24 inches.")
    values = _dense_selected(_normalized(adata), indices, columns)
    if not np.isfinite(values).all():
        raise ValueError("Selected normalized feature values contain NaN or infinity; no values were replaced.")
    constant_features = []
    for column, name in enumerate(names):
        nz = values[:, column] != 0
        nonzero = values[nz, column]
        if len(nonzero) < 2 or np.ptp(locations[nz]) <= 0:
            raise ValueError(f"Feature '{name}' has fewer than two nonzero spots spanning the selected TOI. No valid trajectory curve was generated.")
        if np.ptp(nonzero) == 0:
            constant_features.append(name)
            if scale:
                raise ValueError(f"Feature '{name}' is constant on its nonzero TOI spots; native 0–1 scaling is undefined. Disable Scale to display a constant curve or choose another feature.")
    private = _private_adata(adata, columns, entry)
    if plotter is None:
        import spatialmeta as smt
        plotter = smt.pl.plot_features_trajectory
    figure = _native_figure(plotter, private, features=names, bins=int(bins), scale=bool(scale), figsize=tuple(figsize))
    figure._spashiny_toi_metadata = _metadata(adata, str(key), names, values,
        "native_feature_trajectory", bins=int(bins), scale=bool(scale), figsize=list(figsize),
        modality=_modality(modality) if modality is not None else "mixed",
        constant_features=constant_features, native_zero_filter=True,
        band="standard_deviation_of_nonzero_spots", native_function="spatialmeta.pl.plot_features_trajectory")
    return figure


def build_native_clustermap_figure(adata, modality, *, feature_top=None,
                                   window_size=None, figsize=(5, 8), plotter=None):
    """Unmodified SpatialMETA clustermap semantics, matching the supplied examples.

    All input rows remain in their existing order. The ranking payload is not
    rewritten, and zero/constant ranked features are not removed. Only a private
    copy of the columns the native function itself selects is allocated, with
    dense normalized values converted losslessly to CSR for its .toarray() API.
    """
    import anndata as ad
    import numpy as np
    import pandas as pd
    import seaborn as sns
    from scipy import sparse
    requested = _modality(modality)
    feature_top = (10 if requested == "ST" else 20) if feature_top is None else feature_top
    window_size = (1000 if requested == "ST" else 300) if window_size is None else window_size
    rank_key = "rank_genes_groups" if requested == "ST" else "rank_metabolites_groups"
    rank = adata.uns.get(rank_key)
    if not isinstance(rank, Mapping) or "names" not in rank:
        raise ValueError(f"The current input has no existing {rank_key} names. Run Marker analysis for this input first; no ranking was generated automatically.")
    if isinstance(feature_top, bool) or not isinstance(feature_top, (int, np.integer)) or not 1 <= int(feature_top) <= 100:
        raise ValueError("Top features must be an integer between 1 and 100 per existing ranking group.")
    if isinstance(window_size, bool) or not isinstance(window_size, (int, np.integer)) or not 1 <= int(window_size) <= 10000:
        raise ValueError("Smoothing window must be an integer between 1 and 10000.")
    frame = pd.DataFrame(rank["names"])
    if frame.empty:
        raise ValueError(f"The existing {rank_key} table has no ranked features.")
    selected = frame.head(int(feature_top)).to_numpy().T.flatten()
    # Same unique-preserving order used by the installed native plotter.
    _, first = np.unique(selected, return_index=True)
    names = list(selected[np.sort(first)])
    names, columns = _validate_features(adata, names, requested)
    if len(names) > MAX_HEATMAP_FEATURES:
        raise ValueError(f"The per-group selection contains {len(names)} unique features. Reduce Top features to at most {MAX_HEATMAP_FEATURES} unique heatmap rows.")
    if len(names) * adata.n_obs > MAX_HEATMAP_ELEMENTS or len(names) * adata.n_obs * int(window_size) > MAX_SMOOTHING_WORK:
        raise ValueError("This clustermap exceeds the bounded plotting budget. Reduce Top features or the smoothing window; the input data was not changed.")
    rows = np.arange(adata.n_obs)
    values = _dense_selected(_normalized(adata), rows, columns)
    if not np.isfinite(values).all():
        raise ValueError("Selected normalized values contain NaN or infinity; no values were replaced.")
    private = ad.AnnData(
        X=sparse.csr_matrix(_selected_matrix(adata.X, rows, columns), copy=True),
        obs=adata.obs.iloc[:, :0].copy(), var=adata.var.iloc[columns].copy(),
        layers={"normalized": sparse.csr_matrix(values, copy=True)},
    )
    private.uns[rank_key] = copy.deepcopy(dict(rank))
    if plotter is None:
        import spatialmeta as smt
        plotter = smt.pl.plot_clustermap_with_smoothing
    returned = {}
    def native_call(data, **kwargs):
        returned["data"] = plotter(data, **kwargs)
        return returned["data"]
    color = "#79C" if requested == "ST" else "#a275ac"
    figure = _native_figure(native_call, private, window_size=int(window_size),
        cmap=sns.light_palette(color, as_cmap=True), figsize=tuple(figsize),
        key=rank_key, feature_top=int(feature_top), return_data=requested == "ST")
    figure._spashiny_clustermap_data = returned.get("data")
    figure._spashiny_toi_metadata = {
        "kind": "native_clustermap", "modality": requested, "rank_key": rank_key,
        "feature_top_per_existing_group": int(feature_top), "window_size": int(window_size),
        "input_row_count": int(adata.n_obs), "row_order": "unchanged_input_order",
        "platform_row_filtering": False, "platform_row_reordering": False,
        "ranking_recomputed": False, "rank_payload_rewritten": False,
        "constant_features_removed": False, "normalization_executed": False,
        "palette_seed": color, "return_data": requested == "ST",
        "native_function": "spatialmeta.pl.plot_clustermap_with_smoothing",
    }
    return figure
