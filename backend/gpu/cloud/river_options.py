"""River UI/worker option contracts; no model or attribution implementation."""
from __future__ import annotations

import math
from .river_input_contract import MIN_SAMPLE_SPOTS

PALETTES = ('Balance_20', 'RdBu_r', 'coolwarm', 'Spectral_r', 'viridis', 'plasma', 'magma')


def positive_integer(value, *, name):
    if isinstance(value, bool):
        raise ValueError(f'{name} must be a positive integer.')
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'{name} must be a positive integer.') from None
    if not math.isfinite(number) or number < 1 or number != int(number):
        raise ValueError(f'{name} must be a positive integer.')
    return int(number)


def resolve_subsample_size(counts, requested=None):
    available = [positive_integer(n, name='Sample spot count') for n in counts]
    if len(available) < 2:
        raise ValueError('River sampling requires at least two inspected samples.')
    minimum = min(available)
    if minimum < MIN_SAMPLE_SPOTS:
        raise ValueError(f'River requires at least {MIN_SAMPLE_SPOTS} spots in every sample for its unchanged KNN/FAISS settings.')
    target = minimum if requested is None or requested == 0 else positive_integer(requested, name='n_obs')
    if target < MIN_SAMPLE_SPOTS or target > minimum:
        raise ValueError(f'n_obs must be between {MIN_SAMPLE_SPOTS} and the smallest sample ({minimum:,} spots).')
    return target


def sampling_request(parameters):
    """New UI is exact/automatic; old queued jobs retain their prior cap semantics."""
    if str(parameters.get('analysis_mode') or 'general') == 'original_python_parity':
        if parameters.get('subsample_size') not in (None, 1052):
            raise ValueError('original_python_parity requires exactly n_obs=1052 per sample.')
        return 1052, 'custom'
    mode = str(parameters.get('subsample_mode') or ('legacy_limit' if parameters.get('subsample_size') else 'minimum'))
    if mode not in {'minimum','custom','legacy_limit'}:
        raise ValueError('Choose automatic or custom spot sampling.')
    size = 0 if mode == 'minimum' else positive_integer(parameters.get('subsample_size'), name='n_obs')
    return size, mode


def validate_plot_options(options, *, sample_count):
    options = dict(options or {})
    result = {}
    for name, default, lower, upper in (
        ('width', 20.0, 2.0, 48.0), ('height', 4.0, 2.0, 48.0),
        ('size', 12.0, 0.01, 1000.0),
    ):
        try:value = float(options.get(name, default))
        except (ValueError, TypeError):raise ValueError(f'Invalid plot {name}.') from None
        if not math.isfinite(value) or not lower <= value <= upper:
            raise ValueError(f'Plot {name} must be between {lower} and {upper}.')
        result[name] = value
    result['ncols'] = positive_integer(options.get('ncols', sample_count), name='Plot columns')
    if result['ncols'] > sample_count:
        raise ValueError('Plot columns cannot exceed the number of samples.')
    palette = str(options.get('cmap', 'Balance_20'))
    if palette not in PALETTES:
        raise ValueError('Choose one of the available color palettes.')
    result.update(cmap=palette, colorbar=bool(options.get('colorbar', False)), automatic_norm=bool(options.get('automatic_norm', True)))
    if not result['automatic_norm']:
        try:low, high = float(options['vmin']), float(options['vmax'])
        except (TypeError, ValueError, KeyError):raise ValueError('Enter both color-scale minimum and maximum.') from None
        if not math.isfinite(low) or not math.isfinite(high) or high <= low:
            raise ValueError('Color-scale maximum must be greater than minimum.')
        result.update(vmin=low, vmax=high)
    # Limit raster-preview memory without altering vector PDF resolution.
    if result['width'] * result['height'] > 768:
        raise ValueError('The requested figure is too large. Use a smaller width/height or more columns.')
    return result
