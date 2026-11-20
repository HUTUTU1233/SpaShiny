"""Input adapters only; the River/model/preprocess core remains byte-identical."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path


def scanpy_sample(adata, target_n=1052):
    import scanpy as sc
    if isinstance(target_n,bool) or target_n != 1052 or adata.n_obs < target_n:
        raise ValueError(f'original_python_parity needs {target_n} spots per sample; available {adata.n_obs}. No silent reduction is allowed.')
    if not adata.var_names.is_unique:
        raise ValueError('Original H5AD parity rejects duplicate var_names; it does not rename genes.')
    # Scanpy copy=True requires an in-memory AnnData. The worker compatibility
    # bridge bounds the full input before this materialization. This is the
    # actual data object, not a NumPy selector or an index-only carrier.
    source = adata.to_memory() if adata.isbacked else adata
    selected = sc.pp.subsample(source,n_obs=1052,random_state=0,copy=True)
    selected.uns['_river_sampling_audit'] = {
        'algorithm':'scanpy.pp.subsample','kwargs':{'n_obs':1052,'random_state':0,'copy':True},
        'spots_before':int(adata.n_obs),'spots_after':int(selected.n_obs),
        'scanpy_return_order_preserved':True,'general_selector_used':False,
        'obs_names_sha256':order_digest(selected.obs_names)}
    return selected


def preprocess_expression(adata, settings):
    import scanpy as sc
    from cloud.river_input_contract import validate_expression
    stats = validate_expression(adata)
    scale = settings['input_scale']
    if scale != 'log1p' and 'log1p' in adata.uns:
        raise ValueError('The H5AD contains a log1p preprocessing marker but .X was declared unlogged. Verify the .X scale; it will not be processed twice.')
    steps = []
    operations = []
    if scale == 'raw_counts':
        before = matrix_digest(adata.X)
        sc.pp.normalize_total(adata)
        steps.append('scanpy.pp.normalize_total(defaults)')
        operations.append({'function':'scanpy.pp.normalize_total','kwargs':{},'input':before,'output':matrix_digest(adata.X)})
    if scale in ('raw_counts','normalized_counts'):
        before = matrix_digest(adata.X)
        sc.pp.log1p(adata)
        steps.append('scanpy.pp.log1p(defaults)')
        operations.append({'function':'scanpy.pp.log1p','kwargs':{},'input':before,'output':matrix_digest(adata.X)})
    return {'declared_input_scale':scale,'source':'.X','steps':steps,'input':stats,
            'operations':operations,'raw_or_layers_substituted':False}


def order_digest(names):
    return hashlib.sha256('\0'.join(map(str,names)).encode()).hexdigest()


def versions():
    result = {'python':platform.python_version()}
    for name in ('numpy','scipy','scanpy','anndata','torch','captum','scSLAT','squidpy','matplotlib'):
        try: result[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: result[name] = 'not installed'
    return result


def file_digest(path):
    path = Path(path).resolve()
    before = path.stat()
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024**2),b''):digest.update(chunk)
    after = path.stat()
    if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):
        raise ValueError('Input file changed while computing its execution audit hash.')
    return {'path':str(path),'sha256':digest.hexdigest(),'size_bytes':after.st_size}


def matrix_digest(matrix):
    """SHA256 of dtype+shape+numerical row-major bytes; bounded sparse blocks.

    Dense/CSR representations with identical dtype/values have identical hashes.
    Byteorder and dtype are intentionally not coerced. Never mutates .X.
    """
    import numpy as np
    from scipy import sparse
    shape=tuple(matrix.shape);dtype=np.dtype(matrix.dtype)
    header={'schema':'ndarray-c-order-v1','shape':list(shape),'dtype':dtype.str}
    digest=hashlib.sha256(json.dumps(header,sort_keys=True,separators=(',',':')).encode()+b'\0')
    if len(shape)==0:
        digest.update(np.asarray(matrix).tobytes())
    elif shape[0]:
        row_bytes=max(1,int(np.prod(shape[1:]))*dtype.itemsize)
        block_rows=max(1,(8*1024**2)//row_bytes)
        for start in range(0,shape[0],block_rows):
            block=matrix[start:start+block_rows]
            if sparse.issparse(block):block=block.toarray(order='C')
            digest.update(np.ascontiguousarray(block).tobytes(order='C'))
    return {**header,'sha256':digest.hexdigest()}
