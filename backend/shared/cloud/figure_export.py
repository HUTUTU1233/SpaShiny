"""Export live scientific figures without disguising a PNG as editable art.

PDF/SVG preserve vector marks and text.  Actual image layers (histology,
microscopy and image-valued scientific arrays) remain image layers; this
module never fabricates editable pixels or modifies source analysis data.
"""
from __future__ import annotations

import copy
import io
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class VectorExportError(RuntimeError):
    """An actionable export error; callers must show it instead of empty PDF."""


VECTOR_RCPARAMS = {"pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none"}


def _named_font_weight(weight: Any) -> Any:
    """Preserve numeric weight exactly using its standard Matplotlib alias.

    SpatialMETA sets weight=100. Matplotlib 3.10 SVG text serialization indexes
    weight_dict by name and raises KeyError for that numeric value. Never round
    nonstandard weights or mutate the process-wide font-manager dictionary.
    """
    from matplotlib.font_manager import weight_dict
    if isinstance(weight, str):
        return weight
    return next((name for name, value in weight_dict.items() if value == weight), weight)


def _vector_rcparams() -> dict[str, Any]:
    import matplotlib
    settings = dict(VECTOR_RCPARAMS)
    for key in ('font.weight', 'axes.labelweight', 'axes.titleweight'):
        settings[key] = _named_font_weight(matplotlib.rcParams[key])
    return settings


def mark_source_image(image_artist: Any) -> Any:
    """Keep an original tissue/photo layer raster, including grayscale H&E.

    This marks display provenance only. It does not touch the image array.
    RGB/RGBA source images are preserved automatically even without this tag.
    """
    image_artist._spashiny_source_image = True
    return image_artist


def figure_layer_report(fig: Any) -> dict[str, Any]:
    """Describe editable grids versus honest source-image layers to the UI."""
    from matplotlib.image import AxesImage

    grids, images = [], []
    for artist in fig.findobj(match=AxesImage):
        array = artist.get_array()
        entry = {"label": artist.get_label(), "shape": list(array.shape),
                 "source_image": bool(getattr(artist, "_spashiny_source_image", False))}
        if array.ndim == 2 and not entry["source_image"]:
            grids.append(entry)
        else:
            images.append(entry)
    return {"editable_scalar_grids": grids, "preserved_source_image_layers": images,
            "has_raster_source_layers": bool(images)}


def configure_illustrator_vector_output() -> None:
    import matplotlib

    matplotlib.rcParams.update(VECTOR_RCPARAMS)


@contextmanager
def _native_vector_artists(fig: Any):
    """Temporarily un-rasterize marks, including Scanpy/colourbar defaults.

    Two-dimensional scientific image grids become editable QuadMesh cells.
    RGB/RGBA and explicitly marked tissue images remain source image layers.
    All temporary artists and axis state are restored after export/failure.
    """
    import numpy as np
    from matplotlib.image import AxesImage, _ImageBase
    from matplotlib.text import Text

    changed = []
    axes_zorders = []
    axis_states = []
    image_visibility = []
    meshes = []
    font_weights = []
    try:
        for text in fig.findobj(match=Text):
            weight = text.get_fontweight()
            named = _named_font_weight(weight)
            if named != weight:
                font_weights.append((text, weight))
                text.set_fontweight(named)
        for axes in fig.axes:
            axis_states.append((axes, axes.get_xlim(), axes.get_ylim(),
                                axes.dataLim.frozen(), axes.get_autoscalex_on(),
                                axes.get_autoscaley_on(), axes.ignore_existing_data_limits))
            old = axes.get_rasterization_zorder()
            axes_zorders.append((axes, old))
            axes.set_rasterization_zorder(None)
            for image in list(axes.images):
                if not isinstance(image, AxesImage):
                    continue
                array = image.get_array()
                if array.ndim != 2 or getattr(image, "_spashiny_source_image", False):
                    continue
                height, width = array.shape
                left, right, bottom, top = image.get_extent()
                x_edges = np.linspace(left, right, width + 1)
                y_edges = np.linspace(top, bottom, height + 1) if image.origin == "upper" else np.linspace(bottom, top, height + 1)
                mesh = axes.pcolormesh(
                    x_edges, y_edges, array, norm=image.norm, cmap=image.get_cmap(),
                    alpha=image.get_alpha(), zorder=image.get_zorder(),
                    visible=image.get_visible(), transform=image.get_transform(),
                    shading="flat", edgecolors="none", antialiased=False,
                    rasterized=False, snap=False,
                )
                meshes.append(mesh)
                mesh.set_clip_on(image.get_clip_on())
                if image.get_clip_path() is not None:
                    mesh.set_clip_path(image.get_clip_path())
                if image.get_clip_box() is not None:
                    mesh.set_clip_box(image.get_clip_box())
                image_visibility.append((image, image.get_visible()))
                image.set_visible(False)
            # Adding the temporary grid must not autoscale the live viewport.
            state = axis_states[-1]
            axes.set_xlim(state[1], auto=state[4])
            axes.set_ylim(state[2], auto=state[5])
        for artist in fig.findobj():
            if isinstance(artist, _ImageBase):
                continue
            if hasattr(artist, "get_rasterized") and hasattr(artist, "set_rasterized"):
                old = artist.get_rasterized()
                if old:
                    changed.append((artist, old))
                    artist.set_rasterized(False)
        yield
    finally:
        for mesh in meshes:
            mesh.remove()
        for image, visible in image_visibility:
            image.set_visible(visible)
        for artist, value in changed:
            artist.set_rasterized(value)
        for text, weight in font_weights:
            text.set_fontweight(weight)
        for axes, value in axes_zorders:
            axes.set_rasterization_zorder(value)
        for axes, xlim, ylim, data_lim, auto_x, auto_y, ignore_limits in axis_states:
            axes.dataLim.set(data_lim)
            axes.set_xlim(xlim, auto=auto_x)
            axes.set_ylim(ylim, auto=auto_y)
            axes.ignore_existing_data_limits = ignore_limits


def _plotly_vector_copy(fig: Any):
    """Use SVG-backed 2D traces for static export; retain interactive WebGL."""
    import plotly.graph_objects as go

    data = copy.deepcopy(fig.to_plotly_json())
    replacements = {"scattergl": "scatter", "scatterpolargl": "scatterpolar"}
    unsupported = {
        "scatter3d", "surface", "mesh3d", "volume", "isosurface", "cone",
        "streamtube", "scattermapbox", "densitymapbox", "scattermap", "densitymap",
        "splom", "parcoords", "heatmap", "heatmapgl", "image",
    }
    for trace in data.get("data", []):
        kind = str(trace.get("type") or "scatter").lower()
        if kind in unsupported:
            raise VectorExportError(
                f"Plotly {kind} cannot be exported as editable 2D vector marks. "
                "Use the original 2D scientific figure or render saved matrix "
                "data as a native Matplotlib QuadMesh; "
                "a screenshot will not be labelled an editable vector export."
            )
        if kind in replacements:
            trace["type"] = replacements[kind]
    # Raster frames are not needed to export the current interactive state.
    data.pop("frames", None)
    try:
        return go.Figure(data)
    except Exception as exc:
        raise VectorExportError(f"Cannot construct the vector Plotly export: {exc}") from exc


def figure_bytes(fig: Any, *, format: str = "pdf", dpi: int = 180,
                 bbox_inches: str | None = "tight", **kwargs: Any) -> bytes:
    """Return PDF/SVG from an original Matplotlib/Plotly Figure, never PNG.

    Scalar imshow grids become vector cells. Real RGB/RGBA or marked tissue
    images remain honestly labelled raster layers, not invented vector tissue.
    """
    kind = str(format).lower().lstrip(".")
    if kind not in {"pdf", "svg"}:
        raise VectorExportError("Editable figure export supports PDF or SVG only.")
    from matplotlib.figure import Figure

    if isinstance(fig, Figure):
        import matplotlib

        stream = io.BytesIO()
        with matplotlib.rc_context(_vector_rcparams()), _native_vector_artists(fig):
            fig.savefig(stream, format=kind, dpi=int(dpi), bbox_inches=bbox_inches, **kwargs)
        return stream.getvalue()
    if hasattr(fig, "to_plotly_json"):
        export_fig = _plotly_vector_copy(fig)
        try:
            return export_fig.to_image(format=kind, engine="kaleido")
        except Exception as exc:
            raise VectorExportError(
                "Plotly vector export failed. Check the compatible Plotly/Kaleido "
                f"runtime; no raster PDF fallback was used. Original error: {exc}"
            ) from exc
    raise VectorExportError(
        "The original Matplotlib or Plotly Figure is required for editable "
        "PDF/SVG. A PNG, PIL image, array, or screenshot cannot be converted "
        "into editable scientific marks. Regenerate the figure from saved plot data."
    )


def _write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(prefix=path.stem + "-", suffix=".tmp",
                                         dir=path.parent, delete=False)
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(payload)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def save_native_figure(fig: Any, target: Any, *, format: str | None = None,
                       **kwargs: Any) -> None:
    """Figure.savefig-compatible PDF/SVG adapter for existing UI downloads.

    The caller still constructs exactly its original Figure. Only serialization
    changes; no data preparation, statistics, sampling or palette is changed.
    """
    kind = format or (Path(target).suffix.lstrip('.') if isinstance(target, (str, os.PathLike)) else '')
    payload = figure_bytes(fig, format=kind, **kwargs)
    if hasattr(target, 'write'):
        target.write(payload)
    else:
        _write_atomic(Path(target), payload)


class EditablePdfPages:
    """Native multipage reports, with vector marks on each original Figure."""

    def __init__(self, *args: Any, **kwargs: Any):
        from matplotlib.backends.backend_pdf import PdfPages
        self._pdf = PdfPages(*args, **kwargs)

    def __enter__(self):
        self._pdf.__enter__()
        return self

    def __exit__(self, *args: Any):
        return self._pdf.__exit__(*args)

    def __getattr__(self, name: str):
        return getattr(self._pdf, name)

    def savefig(self, figure: Any = None, **kwargs: Any) -> None:
        import matplotlib
        from matplotlib.figure import Figure
        if not isinstance(figure, Figure):
            raise VectorExportError('Multipage export requires each original Figure explicitly, not a screenshot.')
        with matplotlib.rc_context(_vector_rcparams()), _native_vector_artists(figure):
            self._pdf.savefig(figure, **kwargs)


def save_figure_bundle(fig: Any, png_path: Path, *, dpi: int = 150,
                       pad_inches: float = 0.1) -> tuple[Path, Path, Path]:
    """Publish preview PNG plus native PDF and SVG; keep Figure ownership."""
    from matplotlib.figure import Figure

    png_path = Path(png_path)
    if png_path.suffix.lower() != ".png":
        raise ValueError("The preview path must end in .png.")
    if not isinstance(fig, Figure):
        raise VectorExportError("save_figure_bundle requires the original Matplotlib Figure.")
    preview = io.BytesIO()
    fig.savefig(preview, format="png", dpi=int(dpi), bbox_inches="tight",
                facecolor="white", pad_inches=pad_inches)
    # Finish vector rendering before publishing any files.  Failure is explicit.
    pdf = figure_bytes(fig, format="pdf", dpi=dpi, facecolor="white", pad_inches=pad_inches)
    svg = figure_bytes(fig, format="svg", dpi=dpi, facecolor="white", pad_inches=pad_inches)
    pdf_path, svg_path = png_path.with_suffix(".pdf"), png_path.with_suffix(".svg")
    for path, payload in ((png_path, preview.getvalue()), (pdf_path, pdf), (svg_path, svg)):
        _write_atomic(path, payload)
    return png_path, pdf_path, svg_path
