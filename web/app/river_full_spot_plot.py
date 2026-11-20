"""Full-input spatial expression companion; never invoke the River model.

Read only the authorized completed job's hash-bound, pre-sampling inputs.
The old sampled cache is deliberately not a fallback for missing full data.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import re
from pathlib import Path

from river_result_tools import _PLOT_LOCK, artifact_path

METHOD_VERSION = 'river-full-input-expression-v1'
FULL_SPOT_PALETTES = {
    'magma': 'Magma - reference PDF (black/purple to yellow)',
    'viridis': 'Viridis - purple/green/yellow',
    'plasma': 'Plasma - purple/pink/yellow',
    'inferno': 'Inferno - black/red/yellow',
    'RdBu_r': 'Blue / white / red',
    'coolwarm': 'Coolwarm - blue / red',
    'Spectral_r': 'Spectral - blue / yellow / red',
}
MAX_PALETTES = 4
MAX_TOTAL_SPOTS = 1_000_000
BLOCK_BYTES = 16 * 1024**2


def _json(path):
    if path.stat().st_size > 16 * 1024**2:
        raise ValueError('The saved plotting provenance is too large.')
    return json.loads(path.read_text(encoding='utf-8'))


def _sha256(path):
    before = path.stat()
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            h.update(block)
    after = path.stat()
    fingerprint = lambda s: (s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    if fingerprint(before) != fingerprint(after):
        raise ValueError('The full input changed during integrity checking.')
    return h.hexdigest(), fingerprint(after)


def resolve_full_inputs(job, jobs_root=None):
    """Call only after owner/analysis-scoped job selection (same as old redraw).

    Reconstruct paths under the configured job root, not an arbitrary trace
    path. Host-GPU and Web may have different mount prefixes; the required
    suffix, job ID, sample identity and content digest must all agree.
    """
    job_id = str(job.job_id)
    if not re.fullmatch(r'job_[A-Za-z0-9_-]+', job_id):
        raise ValueError('Invalid River job identity.')
    if str(getattr(job, 'status', '')).upper() != 'SUCCEEDED':
        raise ValueError('Full-spot plots require a completed River job.')
    trace = _json(artifact_path(job, 'river_execution_trace.json'))
    if str(trace.get('job_id', '')) != job_id:
        raise ValueError('Full-input provenance belongs to a different job.')
    if jobs_root is None:
        from cloud.config import load_cloud_config
        jobs_root = load_cloud_config().lab_jobs_root
    root = Path(jobs_root).resolve()
    working = (root / job_id / 'working').resolve()
    if not working.is_relative_to(root):
        raise ValueError('Full-input job directory escapes its controlled root.')
    config_path = working / 'river_unified_config.json'
    if not config_path.is_file() or not config_path.resolve().is_relative_to(working):
        raise ValueError('Full-spot inputs are unavailable for this older/cleaned job; the sampled cache will not be substituted.')
    config = _json(config_path)
    if str(config.get('job_id', '')) != job_id:
        raise ValueError('Saved input configuration belongs to a different job.')
    samples, checks = config.get('samples', []), trace.get('sample_checks', [])
    if not (2 <= len(samples) <= 64) or len(checks) != len(samples):
        raise ValueError('Full-input provenance is incomplete; no samples will be silently omitted.')
    by_id = {str(c.get('sample_id', '')): c for c in checks}
    if len(by_id) != len(checks):
        raise ValueError('Duplicate sample IDs in full-input provenance.')
    result, names = [], set()
    for sample in samples:
        sample_id = str(sample.get('sample_id', ''))
        if not sample_id or sample_id in names or sample_id not in by_id:
            raise ValueError('Saved sample identities are inconsistent.')
        names.add(sample_id)
        check = by_id[sample_id]
        name = Path(str(sample.get('data_path', ''))).name
        if not name or name != sample_id + '.h5ad':
            raise ValueError('Saved full-input filename does not match its sample.')
        record = check.get('prepared_h5ad', {})
        suffix = f'/{job_id}/working/river_unified_inputs/{name}'
        if not str(record.get('path', '')).replace('\\', '/').endswith(suffix):
            raise ValueError('Full-input provenance references a different job/path.')
        path = (working / 'river_unified_inputs' / name).resolve()
        if not path.is_relative_to(working) or not path.is_file():
            raise ValueError('The complete pre-sampling H5AD is no longer available; no sampled fallback is allowed.')
        digest = str(record.get('sha256', ''))
        if not re.fullmatch('[a-f0-9]{64}', digest):
            raise ValueError('The full input lacks a valid integrity fingerprint.')
        scale = sample.get('resolved_input_scale')
        if scale not in ('raw_counts', 'normalized_counts', 'log1p') or scale != check.get('preprocessing', {}).get('declared_input_scale'):
            raise ValueError('The full-input expression scale is missing or inconsistent; refusing to guess.')
        shape = check.get('source_shape')
        if not isinstance(shape, list) or len(shape) != 2 or min(shape) <= 0:
            raise ValueError('The full-input shape was not recorded.')
        result.append({'sample_id': sample_id, 'label': str(sample.get('condition') or sample_id),
                       'path': path, 'sha256': digest, 'shape': shape, 'input_scale': scale})
    expected_order = config.get('sample_order')
    if expected_order != [r['path'].name for r in result]:
        raise ValueError('The full-input sample order does not match the saved submission.')
    if sum(r['shape'][0] for r in result) > MAX_TOTAL_SPOTS:
        raise ValueError('The full-spot plotting limit is exceeded. No spots were downsampled; use a smaller input job.')
    return result


def read_full_gene(record, gene):
    """Keep all observations, native coordinates and row order; bounded I/O.

    Raw-count visualization uses normalize_total's default positive-total
    median across the *full sample*, then log1p. This is plot-only and may
    differ from the training subset's median. Already log1p .X is not logged
    again. Never substitute raw/layers or write back into the source H5AD.
    """
    import anndata as ad
    import numpy as np
    from scipy import sparse

    path, scale = record['path'], record['input_scale']
    digest, fingerprint = _sha256(path)
    if digest != record['sha256']:
        raise ValueError('The full input differs from this job\'s recorded SHA256; refusing stale/replaced data.')
    data = ad.read_h5ad(path, backed='r')
    try:
        if list(data.shape) != record['shape'] or not data.obs_names.is_unique or not data.var_names.is_unique:
            raise ValueError('The full-input shape or spot/gene identities are invalid.')
        if gene not in data.var_names:
            raise ValueError(f'{record["label"]}: the selected gene is absent from the complete input.')
        if 'spatial' not in data.obsm:
            raise ValueError('Full-spot plotting needs real saved spatial coordinates.')
        xy = np.array(data.obsm['spatial'], dtype=float, copy=True)
        if xy.shape != (data.n_obs, 2) or not np.isfinite(xy).all():
            raise ValueError('Full-input coordinates must be finite and two-dimensional.')
        if (np.ptp(xy, axis=0) <= 0).any():
            raise ValueError('Full-input spatial coordinates contain a degenerate axis.')
        if scale != 'log1p' and 'log1p' in data.uns:
            raise ValueError('Saved .X scale conflicts with a log1p marker; no repeated preprocessing is allowed.')
        values = np.empty(data.n_obs, dtype=np.float64)
        totals = np.empty(data.n_obs, dtype=np.float64) if scale == 'raw_counts' else None
        column = int(data.var_names.get_loc(gene))
        block_rows = max(1, min(1024, BLOCK_BYTES // max(1, data.n_vars * np.dtype(data.X.dtype).itemsize)))
        for start in range(0, data.n_obs, block_rows):
            stop = min(data.n_obs, start + block_rows)
            if totals is not None:
                block = data.X[start:stop, :]
                stored = block.data if sparse.issparse(block) else np.asarray(block)
                if not np.isfinite(stored).all() or (stored < 0).any():
                    raise ValueError('Raw counts contain negative or non-finite values.')
                totals[start:stop] = np.asarray(block.sum(axis=1, dtype=np.float64)).reshape(-1)
                selected = block[:, column:column + 1]
            else:
                selected = data.X[start:stop, column:column + 1]
            if sparse.issparse(selected):
                selected = selected.toarray()
            values[start:stop] = np.asarray(selected).reshape(-1)
        if not np.isfinite(values).all() or (values < 0).any():
            raise ValueError('The selected gene has negative or non-finite expression.')
        detected = int(np.count_nonzero(values))
        steps, target = [], None
        if totals is not None:
            positive = totals[totals > 0]
            if not len(positive) or not np.isfinite(totals).all():
                raise ValueError('The full input has no valid positive library totals.')
            target = float(np.median(positive))
            values *= np.divide(target, totals, out=np.zeros_like(totals), where=totals > 0)
            steps.append('plot-only normalize_total(target=full-sample median positive library total)')
        if scale != 'log1p':
            np.log1p(values, out=values)
            steps.append('plot-only log1p')
        after = path.stat()
        if fingerprint != (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError('The full input changed during plotting.')
        return {'coordinates': xy, 'values': values, 'sample_id': record['sample_id'], 'label': record['label'],
                'n_spots': int(data.n_obs), 'n_detected': detected, 'input_scale': scale,
                'source_sha256': digest, 'plot_preprocessing': steps, 'normalization_target': target,
                'obs_order_sha256': hashlib.sha256('\0'.join(map(str, data.obs_names)).encode()).hexdigest()}
    finally:
        data.file.close()


def validate_full_options(palettes=None, options=None, sample_count=1):
    options = options or {}
    palettes = ['magma'] if palettes is None else ([palettes] if isinstance(palettes, str) else list(palettes))
    if not 1 <= len(palettes) <= MAX_PALETTES or len(set(palettes)) != len(palettes) or any(p not in FULL_SPOT_PALETTES for p in palettes):
        raise ValueError('Choose 1-4 distinct full-spot color palettes, including Magma if desired.')
    settings = {}
    for key, default, low, high in (('width', 20, 4, 48), ('height', 4, 2, 48), ('size', 12, 0.05, 100)):
        value = options.get(key, default)
        if isinstance(value, bool):
            raise ValueError(f'Invalid full-spot {key}.')
        value = float(value)
        if not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f'Full-spot {key} must be between {low} and {high}.')
        settings[key] = value
    ncols = options.get('ncols', sample_count)
    if isinstance(ncols, bool) or int(ncols) != float(ncols) or not 1 <= int(ncols) <= sample_count:
        raise ValueError('Invalid full-spot panels per row.')
    settings['ncols'] = int(ncols)
    return palettes, settings


def render_full_spot_gene(job, gene, palettes=None, options=None, *, jobs_root=None):
    """Return transient native figures; do not modify jobs, models or results."""
    with _PLOT_LOCK:
        records = resolve_full_inputs(job, jobs_root)
        palettes, settings = validate_full_options(palettes, options, len(records))
        gene = str(gene or '').strip()
        if not gene:
            raise ValueError('Select a gene from the completed job.')
        panels = [read_full_gene(r, gene) for r in records]
        return _draw_panels(job, gene, panels, palettes, settings)


def _draw_panels(job, gene, panels, palettes, settings):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    from cloud.figure_export import save_native_figure

    vmax = max(float(p['values'].max()) for p in panels)
    # Shared real expression limits, not per-panel rescaling/percentile clipping.
    norm = plt.Normalize(0, vmax if vmax > 0 else 1)
    images = []
    for palette in palettes:
        ncols = settings['ncols']
        rows = math.ceil(len(panels) / ncols)
        fig, axes = plt.subplots(rows, ncols, figsize=(settings['width'], settings['height']), squeeze=False)
        try:
            for panel, ax in zip(panels, axes.ravel()):
                xy = panel['coordinates']
                ax.scatter(xy[:, 0], xy[:, 1], c=panel['values'], s=settings['size'],
                           cmap=palette, norm=norm, linewidths=0, edgecolors='none', rasterized=False)
                ax.set_aspect('equal', adjustable='box')
                ax.set_box_aspect(1)
                ax.invert_yaxis()  # Visium image axes; data coordinates stay intact.
                ax.set_xticks([]); ax.set_yticks([])
                ax.set_title(panel['label'], fontsize=10)
            for ax in axes.ravel()[len(panels):]:
                ax.set_visible(False)
            fig.suptitle(gene + ' - all input spots', fontsize=13)
            fig.subplots_adjust(left=.025, right=.91, bottom=.08, top=.83, hspace=.32, wspace=.15)
            bar_ax = fig.add_axes([.935, .18, .010, .60])
            bar = fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=palette), cax=bar_ax, label='Log-normalized expression')
            if bar.solids is not None:
                bar.solids.set_rasterized(False)
                bar.solids.set_edgecolor('face')
            if vmax == 0:
                bar.set_ticks([0])
            png, pdf = io.BytesIO(), io.BytesIO()
            fig.savefig(png, format='png', dpi=140, facecolor='white')
            save_native_figure(fig, pdf, format='pdf', bbox_inches=None)
            images.append({'palette': palette, 'label': FULL_SPOT_PALETTES[palette],
                           'png': 'data:image/png;base64,' + base64.b64encode(png.getvalue()).decode('ascii'),
                           'pdf': 'data:application/pdf;base64,' + base64.b64encode(pdf.getvalue()).decode('ascii')})
        finally:
            plt.close(fig)
    return {'job_id': str(job.job_id), 'gene': gene, 'version': METHOD_VERSION, 'settings': settings,
            'total_spots': sum(p['n_spots'] for p in panels), 'sampling_performed': False,
            'model_training_performed': False, 'input_files_modified': False,
            'value_min': min(float(p['values'].min()) for p in panels), 'value_max': vmax,
            'all_zero_gene': vmax == 0, 'images': images,
            'panels': [{k: v for k, v in p.items() if k not in ('coordinates', 'values')} for p in panels]}
