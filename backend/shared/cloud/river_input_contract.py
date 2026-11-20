"""Platform input/security contracts. No River, SLAT or Captum algorithms."""
from __future__ import annotations

import hashlib
import math
import shutil
import stat
from pathlib import Path, PurePosixPath

PLATFORM_VERSION = 'river-platform-input-v3-parity-audit'
EXECUTION_CONTRACT = 'river-parity-execution-v1'
REFERENCE_ORDER = ('V39', 'V28', 'V38', 'V44', 'V27')
REFERENCE_GROUPS = dict(zip(REFERENCE_ORDER, ('Sham', 'D1', 'D3', 'D7', 'D28')))
MIN_SAMPLE_SPOTS = 20  # Cal_Spatial_Net(k_cutoff=20, loop=True); FAISS smooth_range=20.
MAX_ARCHIVE_MEMBERS = 256
MAX_ARCHIVE_H5AD_FILES = 64
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 80 * 1024**3
MAX_SINGLE_H5AD_BYTES = 20 * 1024**3
MAX_SINGLE_CSV_BYTES = 256 * 1024**2
MAX_ARCHIVE_RATIO = 2000
MAX_DENSE_MODEL_BYTES = 2 * 1024**3
SCALES = ('raw_counts', 'normalized_counts', 'log1p')


def execution_settings(parameters):
    """Fail closed at submission/worker boundaries; never silently select General."""
    mode = str(parameters.get('analysis_mode') or '').strip()
    if parameters.get('execution_contract_version') and not parameters.get('requested_analysis_mode'):
        raise ValueError('The versioned River request is missing requested_analysis_mode; refusing an unauditable mode fallback.')
    requested = str(parameters.get('requested_analysis_mode') or mode).strip()
    if mode not in ('general', 'original_python_parity'):
        raise ValueError('Explicitly select General or Original Python parity before submitting River.')
    if requested != mode:
        raise ValueError(f'River mode mismatch: requested {requested!r}, received {mode!r}; no analysis will run.')
    contract = str(parameters.get('execution_contract_version') or EXECUTION_CONTRACT)
    if contract != EXECUTION_CONTRACT:
        raise ValueError('Unsupported River execution contract; inspect and resubmit with the current UI.')
    settings = input_settings(parameters)
    epochs = parameters.get('river_epochs', 100)
    seed = parameters.get('random_seed', 42)
    if isinstance(seed, bool) or seed != 42:
        raise ValueError('River requires random_seed=42.')
    if mode == 'original_python_parity':
        size = parameters.get('subsample_size', 1052)
        if isinstance(size, bool) or size != 1052:
            raise ValueError('Original Python parity requires exactly 1052 spots per sample.')
        if isinstance(epochs, bool) or epochs != 100:
            raise ValueError('Original Python parity requires exactly 100 training epochs.')
    return {**settings, 'requested_analysis_mode': requested,
            'execution_contract_version': EXECUTION_CONTRACT}


def reference_sample_id(name):
    import re
    stem = Path(str(name)).stem
    match = re.match(r'^(V39|V28|V38|V44|V27)(?:$|[_\-.])', stem, re.IGNORECASE)
    return match.group(1).upper() if match else None


def validate_parity_order(names, analysis_mode):
    if analysis_mode != 'original_python_parity':
        return 'user_explicit_order'
    identities = [reference_sample_id(name) for name in names]
    if any(identities):
        if tuple(identities) != REFERENCE_ORDER:
            raise ValueError('The five-sample parity reference requires V39, V28, V38, V44, V27 in that exact order; no automatic reordering or partial reference is allowed.')
        return 'reference_five_sample_order'
    return 'user_explicit_order_generic_parity'


def input_settings(parameters):
    mode = str(parameters.get('analysis_mode') or 'general')
    if mode not in ('general', 'original_python_parity'):
        raise ValueError('Choose general or original_python_parity mode.')
    scale = str(parameters.get('input_scale') or '')
    if scale not in SCALES:
        raise ValueError('Declare the input .X scale: raw_counts, normalized_counts or log1p. River does not guess the expression scale.')
    if mode == 'original_python_parity' and scale != 'raw_counts':
        raise ValueError('original_python_parity requires raw-count .X and the original normalize_total -> log1p sequence.')
    column = str(parameters.get('annotation_column') or '').strip()
    source = str(parameters.get('annotation_source') or ('h5ad' if column else 'none'))
    value = str(parameters.get('annotation_value') or '').strip()
    if source not in ('none', 'h5ad', 'csv') or (source == 'none' and (column or value)) or (source != 'none' and not column):
        raise ValueError('Choose no annotation, or explicitly select an existing H5AD/CSV annotation column.')
    return {'analysis_mode': mode, 'input_scale': scale, 'annotation_source': source,
            'annotation_column': column, 'annotation_value': value,
            'allow_missing_annotation': parameters.get('allow_missing_annotation') is True,
            'platform_version': PLATFORM_VERSION, 'strict_samples': True}


def validated_zip_members(bundle):
    """Validate ALL members and total declared resources before writing any byte."""
    infos = bundle.infolist()
    if len(infos) > MAX_ARCHIVE_MEMBERS:
        raise ValueError(f'River ZIP has too many entries; limit {MAX_ARCHIVE_MEMBERS}.')
    total = 0
    names, stems = set(), set()
    files = []
    for info in infos:
        raw = str(info.filename).replace('\\', '/')
        member = PurePosixPath(raw)
        if '\x00' in raw or member.is_absolute() or '..' in member.parts or any(':' in part for part in member.parts):
            raise ValueError(f'Unsafe River ZIP path: {info.filename}')
        mode = (int(info.external_attr) >> 16) & 0o170000
        if mode and mode not in (stat.S_IFREG, stat.S_IFDIR):
            raise ValueError(f'Non-regular River ZIP member: {info.filename}')
        if int(info.flag_bits) & 1:
            raise ValueError(f'Encrypted River ZIP entry: {info.filename}')
        if info.is_dir():
            continue
        size, compressed = int(info.file_size), int(info.compress_size)
        if size < 0 or size > MAX_SINGLE_H5AD_BYTES:
            raise ValueError(f'Oversized River ZIP member: {info.filename}')
        if size and (compressed <= 0 or size / compressed > MAX_ARCHIVE_RATIO):
            raise ValueError(f'Unsafe compression ratio: {info.filename}')
        total += size
        if total > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
            raise ValueError('Total uncompressed ZIP size exceeds the River limit (including non-H5AD entries).')
        suffix = member.suffix.lower()
        if suffix not in ('.h5ad', '.csv'):
            continue
        if not size or (suffix == '.csv' and size > MAX_SINGLE_CSV_BYTES):
            raise ValueError(f'Empty or oversized River data/annotation entry: {info.filename}')
        key = member.name.casefold()
        if key in names:
            raise ValueError(f'Duplicate River ZIP filename: {member.name}')
        names.add(key)
        if suffix == '.h5ad':
            stem = member.stem.casefold()
            if stem in stems:
                raise ValueError(f'Duplicate River sample stem: {member.stem}')
            stems.add(stem)
        files.append(info)
    if not 2 <= len(stems) <= MAX_ARCHIVE_H5AD_FILES:
        raise ValueError(f'River ZIP must contain 2–{MAX_ARCHIVE_H5AD_FILES} H5AD samples.')
    return files


def extract_checked_member(bundle, info, destination):
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError('Refusing to overwrite an existing extracted input.')
    if shutil.disk_usage(destination.parent).free < int(info.file_size) + 256 * 1024**2:
        raise ValueError('Insufficient temporary disk space to inspect the River package.')
    written = 0
    try:
        with bundle.open(info) as source, destination.open('xb') as target:
            while True:
                chunk = source.read(1024**2)
                if not chunk:
                    break
                written += len(chunk)
                if written > info.file_size:
                    raise ValueError('ZIP expanded beyond its declared member size.')
                target.write(chunk)
        if written != info.file_size:
            raise ValueError('ZIP extraction size mismatch.')
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def validate_spatial(adata, *, sample='sample', allow_obs_coordinates=True):
    import numpy as np
    source = "obsm['spatial']"
    if 'spatial' not in adata.obsm:
        if not allow_obs_coordinates:
            raise ValueError(f'{sample}: missing real obsm[spatial]; synthetic coordinates are forbidden.')
        for x, y in (('x','y'), ('X','Y'), ('coord1','coord2'), ('Coord1','Coord2'),
                     ('pxl_col_in_fullres','pxl_row_in_fullres'), ('imagecol','imagerow'), ('array_col','array_row')):
            if x in adata.obs and y in adata.obs:
                adata.obsm['spatial'] = adata.obs[[x,y]].to_numpy(dtype=float)
                source = f'obs[{x},{y}]'
                break
        else:
            raise ValueError(f'{sample}: missing real spatial XY. Supply obsm[spatial] or documented coordinate columns; no artificial [i,i] fallback is allowed.')
    try:
        xy = np.asarray(adata.obsm['spatial'], dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{sample}: spatial XY must be numeric.') from exc
    if xy.shape != (adata.n_obs, 2) or not np.isfinite(xy).all():
        raise ValueError(f'{sample}: spatial must have finite shape n_obs × 2.')
    if adata.n_obs < MIN_SAMPLE_SPOTS:
        raise ValueError(f'{sample}: {adata.n_obs} spots cannot satisfy the unchanged KNN/FAISS neighborhood size {MIN_SAMPLE_SPOTS}.')
    spans = np.ptp(xy, axis=0)
    if (spans <= 0).any() or np.linalg.matrix_rank(xy - xy.mean(axis=0)) < 2:
        raise ValueError(f'{sample}: spatial coordinates are duplicated/collinear or have a degenerate axis; real two-dimensional tissue coordinates are required.')
    unique = len(np.unique(xy, axis=0))
    adata.obsm['spatial'] = xy.copy()
    return {'source': source, 'shape': list(xy.shape), 'finite': True,
            'axis_spans': spans.tolist(), 'duplicate_coordinate_rows': int(adata.n_obs-unique),
            'sha256': hashlib.sha256(xy.tobytes()).hexdigest()}


def validate_expression(adata, *, sample='sample'):
    import numpy as np
    from scipy import sparse
    matrix = adata.X
    if not adata.obs_names.is_unique:
        raise ValueError(f'{sample}: duplicate spot barcodes are ambiguous; provide unique obs_names.')
    if matrix is None or adata.n_vars < 3:
        raise ValueError(f'{sample}: expression .X is missing or has fewer than three genes.')
    values = matrix.data if sparse.issparse(matrix) else np.asarray(matrix)
    if not np.issubdtype(values.dtype, np.number) or not np.isfinite(values).all():
        raise ValueError(f'{sample}: expression .X must be numeric and finite (no NaN/Inf).')
    if values.size and np.min(values) < 0:
        raise ValueError(f'{sample}: negative expression is not supported; provide unscaled counts or log1p values, not z-scores.')
    if not np.count_nonzero(values):
        raise ValueError(f'{sample}: expression .X is entirely zero.')
    return {'shape': list(adata.shape), 'dtype': str(matrix.dtype),
            'storage': 'sparse' if sparse.issparse(matrix) else 'dense',
            'nonzero_values': int(np.count_nonzero(values))}


def annotation_frame(path):
    import pandas as pd
    frame = pd.read_csv(path)
    candidates = ('Barcode','barcode','BarcodeSpot','spot_name','Spot','cell','Cell','index','Index')
    index_col = next((c for c in candidates if c in frame.columns), None)
    if index_col is None:
        if frame.shape[1] < 2:
            raise ValueError('Annotation CSV needs a barcode column plus an explicit annotation column.')
        index_col = frame.columns[0]
    if frame[index_col].isna().any():
        raise ValueError('Annotation CSV contains missing barcodes.')
    frame[index_col] = frame[index_col].astype(str)
    if frame[index_col].duplicated().any():
        raise ValueError('Annotation CSV contains duplicate barcodes; the mapping is ambiguous.')
    return frame.set_index(index_col)


def apply_plot_annotation(adata, settings, *, csv_path=None, sample='sample'):
    import pandas as pd
    source, column = settings['annotation_source'], settings['annotation_column']
    if source == 'none':
        # Neutral drawing label, not an inferred biological annotation.
        adata.obs['river_plot_group'] = 'Unannotated'
        return {'source':'none', 'required':False, 'matched':int(adata.n_obs), 'missing':0}
    if source == 'csv':
        if not csv_path:
            raise ValueError(f'{sample}: the selected annotation CSV is missing.')
        frame = annotation_frame(csv_path)
        if column not in frame:
            raise ValueError(f'{sample}: selected annotation CSV column {column!r} does not exist.')
        series = frame[column].reindex(adata.obs_names.astype(str))
        series.index = adata.obs.index
    else:
        if column not in adata.obs:
            raise ValueError(f'{sample}: selected H5AD annotation column {column!r} does not exist.')
        series = adata.obs[column]
    missing = int(series.isna().sum())
    if missing and not settings['allow_missing_annotation']:
        raise ValueError(f'{sample}: annotation is missing for {missing}/{adata.n_obs} spots. Fix barcode/column mapping or explicitly allow Unknown labels.')
    adata.obs['river_plot_group'] = pd.Series(series, index=adata.obs.index).astype('string').fillna('Unknown').astype(str)
    value = settings['annotation_value']
    adata.uns['river_plot_annotation'] = {'source':source,'column':column,'highlight':value}
    return {'source':source,'column':column,'matched':int(adata.n_obs-missing),'missing':missing,
            'match_rate':float((adata.n_obs-missing)/max(1,adata.n_obs)), 'highlight':value}


def dense_feature_budget(adata_list):
    import numpy as np
    common = sorted(set.intersection(*(set(a.var_names) for a in adata_list)))
    if len(common) < 3:
        raise ValueError('River inputs must share at least three genes.')
    dtype = np.result_type(*(a.X.dtype for a in adata_list))
    estimate = sum(a.n_obs for a in adata_list) * len(common) * max(4,dtype.itemsize)
    # get_the_feature holds per-sample arrays and their concatenation; tensors add copies.
    if estimate * 3 > MAX_DENSE_MODEL_BYTES:
        raise MemoryError(f'River dense feature/tensor working set is estimated at {estimate*3/1024**3:.2f} GiB, above the {MAX_DENSE_MODEL_BYTES/1024**3:.0f} GiB input budget. Select fewer spots before running.')
    return {'common_gene_count':len(common),'estimated_feature_working_set_bytes':int(estimate*3)}


def adapt_feature_storage(adata):
    """Only storage adaptation for the unchanged core's .toarray() calls."""
    from scipy import sparse
    if not sparse.issparse(adata.X):
        adata.X = sparse.csr_matrix(adata.X)
    return adata
