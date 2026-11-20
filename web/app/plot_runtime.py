"""Plot-only compatibility and editable export, independent of scientific algorithms."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


def native_marker_figure(function: Callable[..., Any], adata, **kwargs):
    """Render the installed native Marker routine with its group-index bug fixed.

    SpatialMETA 0.0.3.0 derives c_ls from significant SM groups, then indexes
    it using *all* ranked groups. A valid group without significant SM values
    causes IndexError. It also reads `st` when no significant ST group exists.
    Adapt only categorical/display indices on a private callable; do not
    replace the installed function, statistics, thresholds or scatter code.
    Unknown upstream implementations require review, not a silent fallback.
    """
    import ast
    import hashlib
    import inspect
    import textwrap

    source = textwrap.dedent(inspect.getsource(function)).strip()
    if hashlib.sha256(source.encode()).hexdigest() != "76410ba435d6a8ad8d679fc405c956b9bd86f1b24df8286252f0fe9981c82bac":
        raise RuntimeError("The installed SpatialMETA Marker plotting implementation changed; its compatibility guard requires review.")
    tree = ast.parse(source)
    changes = {"categories": 0, "subset_index": 0, "axes": 0, "initialize": 0}
    group_order = 'list(pd.DataFrame(adata.uns[key_ST]["names"]).columns)'

    class NativeDisplayIndices(ast.NodeTransformer):
        def visit_Assign(self, node):
            target = ast.unparse(node.targets[0]) if len(node.targets) == 1 else ""
            if target in ('result_ST[groupby]', 'result_SM[groupby]') and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute) and node.value.func.attr == 'astype':
                frame = target.split('[')[0]
                key = 'key_ST' if frame == 'result_ST' else 'key_SM'
                node.value = ast.parse(f'pd.Categorical({frame}[groupby], categories=list(pd.DataFrame(adata.uns[{key}]["names"]).columns), ordered=True)', mode='eval').body
                changes['categories'] += 1
            elif target == 'c_ls':
                node.value = ast.parse(group_order, mode='eval').body
                changes['subset_index'] += 1
            elif target == 'all_text':
                changes['initialize'] += 1
                return [node, ast.parse('c_ls = ' + group_order).body[0]]
            return self.generic_visit(node)

        def visit_Call(self, node):
            if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == 'st' and node.func.attr == 'get_children':
                node.func.value.id = 'ax'
                changes['axes'] += 1
            return self.generic_visit(node)

    NativeDisplayIndices().visit(tree)
    if changes != {'categories': 2, 'subset_index': 1, 'axes': 1, 'initialize': 1}:
        raise RuntimeError("SpatialMETA Marker display compatibility structure did not match the reviewed implementation.")
    namespace = dict(function.__globals__)
    exec(compile(ast.fix_missing_locations(tree), '<native SpatialMETA Marker display indices>', 'exec'), namespace)
    compatible = namespace[function.__name__]
    return native_matplotlib_figure(compatible, adata, **kwargs)


def native_matplotlib_figure(function: Callable[..., Any], *args: Any, **kwargs: Any):
    """Capture the one new Figure created by a native API returning ``None``.

    SpatialMETA 0.0.3.0's volcano APIs have no return statement even with
    show=False. Capture immediately after each call, never after both calls
    and never fall back to an unrelated current Figure.
    """
    import matplotlib.pyplot as plt
    from matplotlib.figure import Figure

    before = set(plt.get_fignums())
    try:
        result = function(*args, **kwargs)
    except Exception:
        for number in set(plt.get_fignums()) - before:
            plt.close(number)
        raise
    if isinstance(result, Figure):
        return result
    for attr in ('figure', 'fig'):
        figure = getattr(result, attr, None)
        if isinstance(figure, Figure):
            return figure
    created = set(plt.get_fignums()) - before
    if result is None and len(created) == 1:
        return plt.figure(next(iter(created)))
    for number in created:
        plt.close(number)
    raise RuntimeError(
        f'{getattr(function, "__name__", "Native plotting API")} returned '
        f'{type(result).__name__} and created {len(created)} figures; '
        'refusing to export an unrelated or ambiguous plot.'
    )


def prepare_volcano_input(adata, cluster: Any, gene: str, metabolite: str):
    """Validate UI selections; adapt matrix storage only, never normalize values."""
    import numpy as np
    from scipy import sparse

    if 'celltype_ST_SM' not in adata.obs:
        raise ValueError("The selected input has no 'celltype_ST_SM' grouping column.")
    selected = str(cluster).strip()
    labels = adata.obs['celltype_ST_SM'].astype(str).str.strip()
    mask = labels.eq(selected).to_numpy()
    if not mask.any():
        raise ValueError(f'Cluster {selected!r} contains no observations in this input.')
    out = adata[mask, :].copy()
    if out.n_obs < 2:
        raise ValueError('Correlation volcano plotting requires at least two observations in the selected cluster.')
    if not out.var_names.is_unique:
        raise ValueError('Duplicate feature names make the selected volcano target ambiguous.')
    if 'type' not in out.var:
        raise ValueError("Volcano input requires an explicit ST/SM feature 'type' column.")
    # Native correlation splits exact ST/SM modalities. Known explicit aliases
    # may be adapted on this private copy, but unknown labels are not genes.
    from cloud.portable_inputs import canonical_feature_types
    out.var['type'] = canonical_feature_types(out.var['type'])
    for name, expected in ((gene, 'ST'), (metabolite, 'SM')):
        if name not in out.var_names:
            raise ValueError(f'The selected {expected} feature {name!r} is not present in the current input.')
        if str(out.var.loc[name, 'type']) != expected:
            raise ValueError(f'The selected feature {name!r} is not an {expected} feature.')
    # Native APIs unconditionally call X.toarray(). CSR conversion is lossless.
    if not sparse.issparse(out.X):
        out.X = sparse.csr_matrix(np.asarray(out.X))
    for name in (gene, metabolite):
        values = np.asarray(out[:, [name]].X.toarray(), dtype=float).reshape(-1)
        if not np.isfinite(values).all():
            raise ValueError(f'Target feature {name!r} has non-finite values in the selected cluster.')
        if np.ptp(values) == 0:
            raise ValueError(f'Target feature {name!r} is constant in the selected cluster; Pearson correlation is undefined.')
    return out


def editable_figure(fig):
    """Keep every chart primitive editable; biological image layers stay images."""
    import matplotlib

    matplotlib.rcParams['pdf.fonttype'] = 42
    matplotlib.rcParams['ps.fonttype'] = 42
    matplotlib.rcParams['svg.fonttype'] = 'none'
    for artist in fig.findobj():
        if hasattr(artist, 'set_rasterized'):
            artist.set_rasterized(False)
    for ax in fig.axes:
        ax.set_rasterization_zorder(None)
    return fig


def save_editable_figure(fig, path: str | Path, *, format: str | None = None):
    """Save the original vector Figure, never a PNG/PIL screenshot in a PDF."""
    target = Path(path)
    selected_format = format or target.suffix.lstrip('.').lower()
    if selected_format not in {'pdf', 'svg'}:
        raise ValueError('Editable exports support PDF or SVG.')
    from cloud.figure_export import save_native_figure
    save_native_figure(fig, target, format=selected_format,
                       bbox_inches='tight', facecolor='white')
    return target


def build_session_feature_plot(adata, feature: str, native_wrapper_class):
    """Read one feature using SpatialMETA's Wrapper; no listener or analysis rerun.

    The original Dash application (annotation, ROI/trajectory mutation) is not
    replaced by this read-only spatial viewer. It is an explicit safe subset.
    """
    from types import SimpleNamespace
    import numpy as np
    from scipy import sparse
    import matplotlib.pyplot as plt
    import plotly.graph_objects as go

    if feature not in adata.var_names or not adata.var_names.is_unique:
        raise ValueError('Select one uniquely named feature from the current analysis input.')
    if 'spatial' not in adata.obsm:
        raise ValueError("Interactive spatial plotting requires obsm['spatial'] coordinates.")
    xy = np.asarray(adata.obsm['spatial'], dtype=float)
    if xy.ndim != 2 or xy.shape[0] != adata.n_obs or xy.shape[1] < 2:
        raise ValueError('Spatial coordinates must have one XY pair per observation.')
    xy = xy[:, :2].copy()
    if not np.isfinite(xy).all():
        raise ValueError('Spatial coordinates contain non-finite values.')
    source_name = "layers['normalized']" if 'normalized' in adata.layers else 'X (unchanged; no normalization applied)'
    matrix = adata.layers['normalized'] if 'normalized' in adata.layers else adata.X

    class _SparseColumnView:
        # Native Wrapper.get_feature_value expects toarray() for flattening;
        # materialize only the selected column, not a dense copy of all genes.
        def __getitem__(self, key):
            result = matrix[key]
            return result if sparse.issparse(result) else sparse.csr_matrix(np.asarray(result))

    image = None
    image_scale = 1.0
    coordinate_label = 'Input spatial coordinates'
    spatial_meta = adata.uns.get('spatial', {})
    if isinstance(spatial_meta, dict) and len(spatial_meta) == 1:
        metadata = next(iter(spatial_meta.values()))
        images = metadata.get('images', {}) if isinstance(metadata, dict) else {}
        factors = metadata.get('scalefactors', {}) if isinstance(metadata, dict) else {}
        for kind in ('hires', 'lowres'):
            if kind not in images:
                continue
            candidate = np.asarray(images[kind])
            scale = float(factors.get(f'tissue_{kind}_scalef') or 0)
            if candidate.ndim in (2, 3) and candidate.size and np.isfinite(scale) and scale > 0:
                image, image_scale = candidate, scale
                coordinate_label = f'{kind} tissue-image pixels (spatial × {scale:g})'
                break
    xy *= image_scale
    facade = SimpleNamespace(
        layers={'normalized': _SparseColumnView()}, var=adata.var,
        obsm={'spatial': xy}, shape=adata.shape,
    )
    wrapper = native_wrapper_class(facade)
    values = np.asarray(wrapper.get_feature_value(feature), dtype=float).reshape(-1)
    if values.size != adata.n_obs or not np.isfinite(values).all():
        raise ValueError('The selected feature has missing/non-finite expression values.')
    # Use the original native trace where defined; the native API divides by
    # vmax and fails for an all-zero gene, so that case is displayed explicitly.
    used_native_trace = bool(values.size and values.max() > 0)
    if used_native_trace:
        trace, _native_colorbar = wrapper.to_feature_scatter(feature, 1.0)
    else:
        trace = go.Scatter(x=xy[:, 0].tolist(), y=xy[:, 1].tolist(), mode='markers')
    low, high = min(0.0, float(values.min())), max(0.0, float(values.max()))
    if high <= low:
        high = low + 1.0
    trace.update(
        x=xy[:, 0].tolist(), y=xy[:, 1].tolist(),
        customdata=[str(x) for x in adata.obs_names],
        marker=dict(color=values.tolist(), colorscale='Viridis', cmin=low, cmax=high,
                    size=4, showscale=True, colorbar={'title': {'text': feature}}),
        hoverinfo=None,
        hovertemplate='Observation: %{customdata}<br>X=%{x}<br>Y=%{y}<br>Value=%{marker.color}<extra></extra>',
        name=feature,
    )
    chart = go.Figure()
    if image is not None:
        image = np.asarray(image)
        if image.ndim == 2:
            image = np.repeat(image[:, :, None], 3, axis=2)
        if image.dtype.kind == 'f' and np.nanmax(image) <= 1:
            image = np.clip(image * 255.0, 0, 255).astype(np.uint8)
        chart.add_trace(go.Image(z=image.tolist(), hoverinfo='skip', name='Original tissue image'))
    chart.add_trace(trace)
    chart.update_layout(
        title=f'Spatial expression: {feature}', template='plotly_white',
        dragmode='pan', height=650, margin=dict(l=40, r=40, b=45, t=55),
        uirevision=f'{feature}:{adata.n_obs}',
        xaxis=dict(title=coordinate_label, constrain='domain'),
        yaxis=dict(scaleanchor='x', scaleratio=1, autorange='reversed'),
    )
    fig, ax = plt.subplots(figsize=(7.5, 7.5))
    if image is not None:
        from cloud.figure_export import mark_source_image
        mark_source_image(ax.imshow(image, origin='upper'))
    points = ax.scatter(xy[:, 0], xy[:, 1], c=values, cmap='viridis', vmin=low, vmax=high,
                        s=7.5, linewidths=0, rasterized=False)
    fig.colorbar(points, ax=ax, label=feature, fraction=0.045, pad=0.025)
    ax.set_aspect('equal', adjustable='box')
    if not ax.yaxis_inverted():
        ax.invert_yaxis()
    ax.set_title(f'Spatial expression: {feature}')
    ax.set_xlabel(coordinate_label)
    fig.tight_layout()
    return chart, editable_figure(fig), {
        'feature': feature, 'expression_source': source_name,
        'n_observations': int(adata.n_obs), 'image_present': image is not None,
        'all_zero_expression': bool(np.all(values == 0)),
        'native_wrapper_feature_reader': True, 'native_wrapper_trace': used_native_trace,
        'scope': 'current Shiny analysis session only; no listening port',
    }


def session_plotly_html(chart):
    """Use the local bundle copied from the same installed Plotly runtime."""
    return chart.to_html(
        full_html=True, include_plotlyjs='/js/plotly-session.min.js',
        config={'responsive': True, 'displaylogo': False, 'scrollZoom': True,
                'modeBarButtonsToAdd': ['select2d', 'lasso2d'],
                'toImageButtonOptions': {'format': 'svg', 'filename': 'spatial_feature'}},
    )
