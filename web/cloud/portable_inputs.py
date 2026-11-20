"""Lossless input adapters: portable ZIP paths and explicit modality labels."""
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import stat
import zipfile


def extract_portable_zip(zip_path, extract_dir):
    """Read Windows/POSIX ZIP paths without changing the source archive.

    Validate the complete directory before extracting any file. Backslashes
    from Windows-created archives are separators, including in traversal
    attempts. Never follow symlinks or overwrite a normalized duplicate path.
    """
    root = Path(extract_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    entries = []
    files = set()
    directories = set()
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            name = member.filename.replace('\\', '/')
            relative = PurePosixPath(name)
            mode = member.external_attr >> 16
            if (relative.is_absolute() or PureWindowsPath(name).drive
                    or '..' in relative.parts or stat.S_ISLNK(mode)):
                raise ValueError(f'Unsafe path inside zip archive: {member.filename}')
            is_dir = member.is_dir() or name.endswith('/')
            if not relative.parts:
                if is_dir:
                    continue
                raise ValueError('ZIP file has an empty filename.')
            key = relative.as_posix()
            if (key in files or (not is_dir and key in directories)
                    or any(parent.as_posix() in files for parent in relative.parents)):
                raise ValueError(f'Conflicting path inside zip archive: {member.filename}')
            if is_dir:
                directories.add(key)
            else:
                files.add(key)
                directories.update(parent.as_posix() for parent in relative.parents if parent.parts)
            target = (root / Path(*relative.parts)).resolve()
            if root not in target.parents or target.exists():
                raise ValueError(f'Unsafe or existing ZIP destination: {member.filename}')
            entries.append((member, target, is_dir))
        required = sum(member.file_size for member, _, is_dir in entries if not is_dir)
        if required > shutil.disk_usage(root).free:
            raise OSError('Insufficient free disk space to extract the uploaded ZIP.')
        for member, target, is_dir in entries:
            if is_dir:
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open('xb') as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
    return root


def canonical_feature_types(labels):
    """Accept known explicit labels; never infer unknown features to be ST."""
    mapping = {
        **dict.fromkeys(('ST', 'GENE', 'GENES', 'RNA', 'TRANSCRIPT',
                         'TRANSCRIPTOMICS', 'SPATIAL_TRANSCRIPTOMICS'), 'ST'),
        **dict.fromkeys(('SM', 'SM_POS', 'SM_NEG', 'METABOLITE', 'METABOLITES', 'MZ', 'M/Z',
                         'MSI', 'MALDI', 'METABOLOMICS', 'SPATIAL_METABOLOMICS'), 'SM'),
    }
    canonical = labels.astype(str).str.strip().str.upper().map(mapping)
    if canonical.isna().any():
        invalid = labels[canonical.isna()].astype(str).unique().tolist()[:8]
        raise ValueError(f'Unrecognized ST/SM feature type(s): {invalid}. Supply explicit modality labels; no features were guessed or dropped.')
    return canonical


def align_sm_pos_neg_inputs(pos, neg):
    """Exact coordinate intersection/order for the native row-wise merge.

    No intensity changes, coordinate rounding, registration or zero filling.
    Both source objects remain unchanged.
    """
    import numpy as np
    import pandas as pd
    columns = ['x_coord_original', 'y_coord_original']
    keys = []
    for label, data in [('POS', pos), ('NEG', neg)]:
        if any(name not in data.obs for name in columns):
            raise ValueError(f'{label} is missing original XY coordinate columns.')
        xy = data.obs[columns].to_numpy(dtype=float)
        spatial = np.asarray(data.obsm.get('spatial'), dtype=float)
        if (xy.shape != (data.n_obs, 2) or not np.isfinite(xy).all()
                or spatial.shape != xy.shape or not np.array_equal(spatial, xy)):
            raise ValueError(f'{label} original XY and spatial coordinates are inconsistent.')
        key = pd.MultiIndex.from_frame(data.obs[columns])
        if not key.is_unique:
            raise ValueError(f'{label} has duplicate pixel coordinates; automatic deduplication is not allowed.')
        keys.append(key)
    pos_key, neg_key = keys
    common = pos_key[pos_key.isin(neg_key)]
    if not len(common):
        raise ValueError('POS and NEG have no exact shared coordinates. Register the datasets first; no coordinates were guessed or rounded.')
    pos = pos[pos_key.get_indexer(common), :].copy()
    neg = neg[neg_key.get_indexer(common), :].copy()
    if not np.array_equal(pos.obsm['spatial'], neg.obsm['spatial']):
        raise ValueError('POS/NEG coordinate ordering is inconsistent after exact matching.')
    return pos, neg


def prepare_downstream_expression(data, source='X'):
    """Select an explicit matrix, unchanged; never guess from uns['log1p']."""
    import numpy as np
    from scipy import sparse
    if source not in ('X', 'normalized'):
        raise ValueError('Choose X or the existing normalized layer for downstream analysis.')
    if source == 'normalized' and source not in data.layers:
        raise ValueError("This input has no layers['normalized']. Prepare it explicitly or select X; no fallback transformation was applied.")
    if 'type' not in data.var:
        raise ValueError("Joint downstream analysis requires an explicit ST/SM feature 'type' column.")
    types = canonical_feature_types(data.var['type'])
    if not {'ST', 'SM'}.issubset(set(types)):
        raise ValueError('Joint downstream analysis requires both ST and SM features.')
    result = data.copy()
    matrix = data.X if source == 'X' else data.layers[source]
    result.X = sparse.csr_matrix(matrix.copy())
    if not np.isfinite(result.X.data).all():
        raise ValueError('The selected analysis matrix contains NaN or infinity; no values were replaced.')
    result.var['type'] = types
    result.uns['spashiny_downstream_expression'] = {
        'source': 'X' if source == 'X' else "layers['normalized']",
        'transform': 'none', 'native_use_raw': False,
        'selection': 'Explicit user selection; uns[log1p] was not used to infer matrix state',
    }
    return result


def read_visium_mtx(visium_dir, count_dir):
    """Read the advertised MTX layout using native Scanpy matrix import.

    Scanpy read_visium accepts HDF5 count files, not a matrix directory.
    The spatial sidecar contract stays identical: full-resolution XY, original
    images and unmodified scale factors. No coordinate normalization occurs.
    """
    import json
    import numpy as np
    import pandas as pd
    import scanpy as sc
    from matplotlib.image import imread
    root = Path(visium_dir)
    data = sc.read_10x_mtx(str(count_dir), var_names='gene_symbols', make_unique=True, cache=False)
    spatial = root / 'spatial'
    positions_path = spatial / 'tissue_positions.csv'
    has_header = positions_path.is_file()
    if not has_header:
        positions_path = spatial / 'tissue_positions_list.csv'
    positions = pd.read_csv(positions_path, header=0 if has_header else None, index_col=0)
    if positions.shape[1] != 5 or not positions.index.is_unique:
        raise ValueError('Visium positions must contain one unique barcode and the five standard coordinate fields.')
    positions.index = positions.index.astype(str)
    positions.columns = ['in_tissue', 'array_row', 'array_col', 'pixel_row_fullres', 'pixel_col_fullres']
    if not data.obs_names.isin(positions.index).all():
        raise ValueError('Visium spatial positions are missing expression-matrix barcodes.')
    positions = positions.loc[data.obs_names]
    xy = positions[['pixel_col_fullres', 'pixel_row_fullres']].to_numpy()
    if not np.isfinite(np.asarray(xy, dtype=float)).all():
        raise ValueError('Visium full-resolution pixel coordinates must be finite.')
    data.obs = data.obs.join(positions[['in_tissue', 'array_row', 'array_col']], how='left')
    data.obsm['spatial'] = xy
    factors = json.loads((spatial / 'scalefactors_json.json').read_text(encoding='utf-8'))
    images = {kind: imread(str(spatial / f'tissue_{kind}_image.png')) for kind in ('hires', 'lowres')}
    for kind in images:
        factor = float(factors.get(f'tissue_{kind}_scalef', 0))
        if not np.isfinite(factor) or factor <= 0:
            raise ValueError(f'Visium {kind} image requires a positive tissue_{kind}_scalef.')
    data.uns['spatial'] = {root.name: {'images': images, 'scalefactors': factors, 'metadata': {}}}
    data.uns['spashiny_visium_input'] = {'matrix_format': '10x MTX',
        'matrix_reader': 'scanpy.read_10x_mtx', 'coordinate_units': 'full-resolution image pixels',
        'library_id_source': 'Visium input directory name; no HDF5 library identifier was supplied'}
    return data
