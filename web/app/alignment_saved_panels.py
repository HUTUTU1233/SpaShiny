"""Plot-only builders copied verbatim from the accepted Alignment worker.

Source SHA256: 2ebd3df7139bd77ff46af6f491fa94a628c8d2dd1d78687bac1bf7c7cc6be1e0
No models, training, rasterization, sampling, alignment, or database code.
These builders consume already-saved arrays; callers serialize original artists.
"""
from __future__ import annotations
from typing import Any

def _to_numpy(value: Any):
    import numpy as np

    if value is None:
        return None
    if hasattr(value, "detach"):
        return value.detach().cpu().numpy()
    return np.asarray(value)

def _normalize(arr: Any):
    import numpy as np

    out = np.asarray(arr, dtype=float)
    out = out - np.nanmin(out)
    maxv = np.nanmax(out)
    if maxv > 0:
        out = out / maxv
    return out

def _alignment_colormaps():
    from matplotlib.colors import LinearSegmentedColormap

    return {
        "sm_raster": LinearSegmentedColormap.from_list(
            "sm_raster_cmap",
            ["#9F66BE", "#379155", "#8de9ac", "#84d43e"],
        ),
        "tissue": LinearSegmentedColormap.from_list(
            "tissue_cmap",
            ["#fff8f4", "#f7d9cf", "#eab7a8", "#d89c8a", "#b87c70"],
        ),
        "st_latent": LinearSegmentedColormap.from_list(
            "st_latent_cmap",
            ["#7B2F92", "#b699db", "#d6c9e6", "#f9f4fa"],
        ),
    }

def _clean_panel_colorbar(fig: Any, mappable: Any, ax: Any) -> Any:
    cbar = fig.colorbar(mappable, ax=ax, fraction=0.046, pad=0.03, shrink=0.88)
    cbar.set_ticks([])
    cbar.outline.set_visible(False)
    return cbar

def _style_alignment_panel(ax: Any, title: str) -> None:
    ax.set_title(title, fontsize=9, fontweight="normal", pad=6, loc="left")
    ax.tick_params(axis="both", which="both", labelsize=7, length=2.2, width=0.7, pad=1.5)
    ax.locator_params(nbins=4)
    for spine in ax.spines.values():
        spine.set_linewidth(0.7)
        spine.set_edgecolor("#666666")

def _mean_image(value: Any) -> Any:
    import numpy as np

    arr = _to_numpy(value)
    if arr is None:
        return None
    if arr.ndim >= 3:
        return arr.mean(axis=0)
    return arr

def _vector_grid(ax: Any, values: Any, **kwargs: Any) -> Any:
    """Represent a computed scalar grid by editable cells, not a screenshot."""
    import numpy as np

    grid = np.asarray(values)
    if grid.ndim != 2:
        raise ValueError("Vector heatmap requires a two-dimensional scalar grid")
    height, width = grid.shape
    result = ax.pcolormesh(
        np.arange(width + 1) - 0.5,
        np.arange(height + 1) - 0.5,
        grid, shading="flat", rasterized=False, edgecolors="none", **kwargs,
    )
    ax.set_xlim(-0.5, width - 0.5)
    ax.set_ylim(height - 0.5, -0.5)
    return result

def _raster_panel_figure(raster_result: dict[str, Any], panel: str) -> Any:
    import matplotlib.pyplot as plt
    import numpy as np

    data = raster_result.get("data", {}) if isinstance(raster_result, dict) else {}
    I = data.get("I")
    J = data.get("J")
    G = data.get("G")
    z_sm = _to_numpy(data.get("z_sm"))
    x_sm = _to_numpy(data.get("x_sm"))
    y_sm = _to_numpy(data.get("y_sm"))
    if I is None or J is None or G is None:
        raise ValueError("Raster result is missing required keys: I / J / G")

    I_np = _normalize(_mean_image(I))
    J_np = _normalize(_mean_image(J))
    G_np = _normalize(_mean_image(G))
    cmaps = _alignment_colormaps()

    fig, ax = plt.subplots(figsize=(6.4, 5.0), dpi=180)
    fig.patch.set_facecolor("white")

    if panel == "sm_feature":
        im = _vector_grid(ax, I_np, cmap=cmaps["sm_raster"])
        _style_alignment_panel(ax, "SM rasterized feature")
        _clean_panel_colorbar(fig, im, ax)
    elif panel == "sm_latent":
        if z_sm is not None and x_sm is not None and y_sm is not None:
            values = np.mean(z_sm, axis=1) if len(z_sm.shape) > 1 else z_sm
            values = _normalize(values)
            sc = ax.scatter(
                x_sm,
                y_sm,
                c=values,
                s=5.2,
                cmap=cmaps["sm_raster"],
                alpha=0.95,
                linewidths=0,
                rasterized=True,
            )
            _clean_panel_colorbar(fig, sc, ax)
        else:
            ax.text(0.5, 0.5, "latent feature unavailable", ha="center", va="center", fontsize=9)
        _style_alignment_panel(ax, "SM latent embedding")
        ax.set_xlabel("SM x", fontsize=8)
        ax.set_ylabel("SM y", fontsize=8)
    elif panel == "st_image":
        im = ax.imshow(J_np, cmap=cmaps["tissue"], origin="upper")
        _style_alignment_panel(ax, "ST spatial image")
        _clean_panel_colorbar(fig, im, ax)
    elif panel == "st_latent":
        im = _vector_grid(ax, G_np, cmap=cmaps["st_latent"])
        _style_alignment_panel(ax, "ST latent feature")
        _clean_panel_colorbar(fig, im, ax)
    else:
        raise ValueError(f"Unknown raster panel: {panel}")

    ax.set_aspect("equal", adjustable="box")
    fig.tight_layout(pad=1.0)
    return fig

def _spot_panel_figure(result_dict: dict[str, Any], panel: str, raster_result: dict[str, Any] | None = None) -> Any:
    import matplotlib.pyplot as plt
    import numpy as np

    data = {}
    if isinstance(raster_result, dict):
        data.update(raster_result.get("data", {}) or {})
    if isinstance(result_dict, dict):
        data.update(result_dict.get("data", {}) or {})
    J = data.get("J")
    maskJ = data.get("maskJ")
    z_st = data.get("z_st")
    spot_coordinate = data.get("spot_coordinate")
    scale = data.get("scale")
    x_st = data.get("x_st")
    y_st = data.get("y_st")
    st_spatial = data.get("st_spatial")

    if J is None or spot_coordinate is None:
        raise ValueError("Spot result is missing required keys: J / spot_coordinate")

    J_arr = _to_numpy(J)
    J_np = J_arr[0] if getattr(J_arr, "ndim", 0) >= 3 else J_arr
    J_np = _normalize(J_np)
    maskJ_np = _to_numpy(maskJ) if maskJ is not None else None
    z_st_np = _to_numpy(z_st) if z_st is not None else None
    z_st_color = np.mean(z_st_np, axis=1) if z_st_np is not None and len(z_st_np.shape) > 1 else z_st_np
    spot_np = _to_numpy(spot_coordinate)
    x_st_np = _to_numpy(x_st) if x_st is not None else None
    y_st_np = _to_numpy(y_st) if y_st is not None else None
    if (x_st_np is None or y_st_np is None) and st_spatial is not None:
        spatial = _to_numpy(st_spatial)
        if spatial is not None and getattr(spatial, "ndim", 0) == 2 and spatial.shape[1] >= 2:
            factor = float(scale or 1.0)
            x_st_np = spatial[:, 0] * factor
            y_st_np = spatial[:, 1] * factor

    try:
        if maskJ_np is not None:
            mask_source = maskJ_np.T if maskJ_np.T.shape == J_np.shape else maskJ_np
            tissue_mean = J_np[mask_source > 0].mean()
        else:
            tissue_mean = np.nanmean(J_np)
        Jtrue = (J_np <= tissue_mean * 0.65).astype(float)
    except Exception:
        Jtrue = None

    cmaps = _alignment_colormaps()
    fig, ax = plt.subplots(figsize=(6.0, 5.2), dpi=180)
    fig.patch.set_facecolor("white")

    if panel == "st_latent":
        ax.imshow(J_np, cmap=cmaps["tissue"], origin="upper")
        if x_st_np is not None and y_st_np is not None and z_st_color is not None:
            ax.scatter(
                x_st_np,
                y_st_np,
                s=5,
                lw=0,
                c=z_st_color,
                cmap="magma",
                alpha=0.78,
                marker="s",
                rasterized=True,
            )
        if maskJ_np is not None:
            overlay = maskJ_np.T if maskJ_np.T.shape == J_np.shape else maskJ_np
            _vector_grid(ax, overlay, alpha=0.12, cmap="Greys")
        _style_alignment_panel(ax, "ST tissue and latent structure")
    elif panel == "sampled":
        ax.imshow(J_np, cmap=cmaps["tissue"], origin="upper")
        ax.scatter(
            spot_np[:, 0],
            spot_np[:, 1],
            s=8,
            lw=0,
            c="#f8f8f8",
            alpha=0.96,
            edgecolors="none",
            rasterized=True,
        )
        _style_alignment_panel(ax, "Randomly sampled inside-tissue spots")
        ax.set_xlim(0, J_np.shape[1])
        ax.set_ylim(J_np.shape[0], 0)
    elif panel == "mask":
        _vector_grid(ax, Jtrue if Jtrue is not None else J_np, cmap="gray")
        _style_alignment_panel(ax, "Binary tissue mask")
    else:
        raise ValueError(f"Unknown spot panel: {panel}")

    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("image x", fontsize=8)
    ax.set_ylabel("image y", fontsize=8)
    fig.tight_layout()
    return fig

