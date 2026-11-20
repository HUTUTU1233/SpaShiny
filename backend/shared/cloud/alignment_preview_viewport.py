"""Display-only initial fitting and image-axis convention; no registration.

Fit is deliberately restricted to the initial visibility preview. Re-fitting
each transformed overlay would cancel the user's true scale/translation, so
manual previews always render the actual saved-coordinate frame.
"""
import numpy as np
from .coordinate_guards import finite_xy
from .sm_coordinate_policy import copy_with_coordinate_state, xy_hash

VERSION = "sm_initial_display_fit_v1"
DISPLAY_KEY = "spashiny_preview_xy"


def initial_display_view(sm, st, *, enabled=True, padding=0.08):
    source = finite_xy(sm.obsm["spatial"])
    target = finite_xy(st.obsm["spatial"])
    if not np.isfinite(padding) or not 0 <= padding < 0.5:
        raise ValueError("Display padding must be finite and in [0, 0.5).")
    extent, target_extent = np.ptp(source, axis=0), np.ptp(target, axis=0)
    if np.any(extent <= 0) or np.any(target_extent <= 0):
        raise ValueError("Display fit needs two non-degenerate coordinate axes.")
    scale = (1 - 2 * padding) * float(np.min(target_extent / extent)) if enabled else 1.0
    offset = ((target.min(0) + target.max(0)) / 2 - scale * (source.min(0) + source.max(0)) / 2
              if enabled else np.zeros(2))
    shown = source * scale + offset
    view = copy_with_coordinate_state(sm)
    # Keep even the view's authoritative spatial unchanged. The native plot
    # receives this dedicated display key; no analytical reader consumes it.
    view.obsm[DISPLAY_KEY] = shown
    metadata = {
        "version": VERSION, "enabled": bool(enabled), "display_only": True,
        "display_scale": scale, "display_translation": offset.tolist(),
        "source_coordinates_sha256": xy_hash(source), "display_coordinates_sha256": xy_hash(shown),
        "rotation": 0.0, "flip": False, "isotropic": True,
        "saved_transform_changed": False, "input_coordinates_changed": False,
        "used_for_Alignment_or_KNN": False, "registration_quality_claim": False,
        "display_coordinate_key": DISPLAY_KEY, "analytical_coordinate_key": "spatial",
    }
    return view, metadata


def image_coordinate_axes(fig, *, kind="overlay", display_fit=None):
    """Only axis rendering changes: X right, Y down, equal physical aspect."""
    for index, ax in enumerate(fig.axes):
        if ax.xaxis_inverted():
            ax.invert_xaxis()
        if not ax.yaxis_inverted():
            ax.invert_yaxis()
        ax.set_aspect("equal", adjustable="box")
        units = "SM coordinate units" if kind == "side" and index else "ST full-resolution coordinates"
        ax.set_xlabel("X (" + units + ")")
        ax.set_ylabel("Y (image direction: increases downward)")
    if display_fit and display_fit.get("enabled"):
        fig.suptitle("INITIAL DISPLAY FIT ONLY — NOT REGISTERED", fontsize=10)
        fig.text(0.5, 0.015,
                 f"SM visibility fit: {display_fit['display_scale']:.6g}x. Not saved or used by Alignment/KNN.\n"
                 "Manual preview and saved parameters use actual coordinates, not this display fit.",
                 ha="center", va="bottom", fontsize=7)
        # Keep the warning separate from the X-axis label in all export sizes.
        fig.tight_layout(rect=(0, 0.10, 1, 1))
    else:
        fig.tight_layout()
    fig._spashiny_display_viewport = display_fit or {
        "display_only": True, "display_scale": 1.0, "saved_transform_changed": False,
        "initial_fit_applied_to_manual_overlay": False,
    }
    return fig
