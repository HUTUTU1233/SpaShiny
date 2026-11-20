"""Content-bound scale evidence, never a max-value/count-like heuristic.

Known server content is trusted. User producer metadata/manifests are explicit
declarations bound to actual bytes/X, not cryptographic producer authentication.
Unknown inputs require a scoped, content-bound acknowledgement.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath
from .river_trusted_inputs import FILES
from .river_input_contract import validate_spatial
from .river_unified_contract import SCALES

METADATA_SCHEMA='river-h5ad-input-v1'
MANIFEST_SCHEMA='river-input-manifest-v1'
MANIFEST_NAME='river_input_manifest.json'
MAX_MANIFEST_BYTES=256*1024


def file_sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024**2),b''):h.update(block)
    return h.hexdigest()


def name_sha(names):return hashlib.sha256('\0'.join(map(str,names)).encode()).hexdigest()


def matrix_evidence(matrix):
    import numpy as np
    from scipy import sparse
    if matrix is None or len(matrix.shape)!=2:raise ValueError('Missing a2-dimensional expression matrix in .X.')
    dtype=np.dtype(matrix.dtype)
    if not np.issubdtype(dtype,np.number) or np.issubdtype(dtype,np.complexfloating):raise ValueError('.X must contain real numeric values.')
    header={'schema':'ndarray-c-order-v1','shape':[int(n) for n in matrix.shape],'dtype':dtype.str}
    h=hashlib.sha256(json.dumps(header,sort_keys=True,separators=(',',':')).encode()+b'\0')
    rows=max(1,(4*1024**2)//max(1,int(matrix.shape[1])*dtype.itemsize));nonzero=0
    for start in range(0,matrix.shape[0],rows):
        block=matrix[start:start+rows]
        values=block.data if sparse.issparse(block) else np.asarray(block)
        if not np.isfinite(values).all():raise ValueError('.X contains NaN/Inf; correct the file before submitting.')
        if (values<0).any():raise ValueError('.X contains negative/scaled values; supply counts or nonnegative log1p values.')
        nonzero+=int(np.count_nonzero(values))
        dense=block.toarray(order='C') if sparse.issparse(block) else np.ascontiguousarray(block)
        h.update(np.ascontiguousarray(dense).tobytes(order='C'))
    if not nonzero:raise ValueError('.X is entirely zero.')
    return {**header,'sha256':h.hexdigest(),'nonzero_values':nonzero}


def _declared_scale(declaration,*,file_hash,x_binding,obs_hash,var_hash,source):
    if not isinstance(declaration,dict):raise ValueError('Expression declaration must be an object.')
    schema=METADATA_SCHEMA if source=='BOUND_H5AD_METADATA' else MANIFEST_SCHEMA
    if declaration.get('schema')!=schema:raise ValueError('Unknown expression declaration schema.')
    if declaration.get('matrix_slot')!='X' or declaration.get('scale') not in SCALES:
        raise ValueError('A declaration must explicitly describe the current .X scale, not raw/layers.')
    if source=='BOUND_H5AD_METADATA':
        binding=declaration.get('x_binding')
        if not isinstance(binding,dict) or binding.get('sha256')!=x_binding['sha256'] or list(binding.get('shape',[]))!=x_binding['shape']:
            raise ValueError('H5AD expression metadata is stale: current .X fingerprint differs.')
        if declaration.get('obs_names_sha256')!=obs_hash or declaration.get('var_names_sha256')!=var_hash:
            raise ValueError('Expression metadata is not bound to the current spot/gene ordering.')
    elif declaration.get('file_sha256')!=file_hash:
        raise ValueError('Package expression manifest does not match the H5AD content hash.')
    expected={'raw_counts':(False,False),'normalized_counts':(True,False),'log1p':(True,True)}
    normalize,logged=expected[declaration['scale']]
    steps=declaration.get('processed_steps')
    valid_flag=lambda value,expected:type(value).__name__ in ('bool','bool_') and bool(value)==expected
    if not isinstance(steps,dict) or not valid_flag(steps.get('normalize_total'),normalize) or not valid_flag(steps.get('log1p'),logged):
        raise ValueError('Declared scale conflicts with its explicit processing-state metadata.')
    return declaration['scale']


def resolve_scale(*,file_hash,x_binding,obs_hash,var_hash,metadata=None,package_declaration=None,log1p_marker=False,confirmation=None):
    candidates=[]
    if file_hash in set(FILES.values()):candidates.append(('SERVER_CONTENT_MANIFEST','raw_counts'))
    for source,declaration in [('BOUND_H5AD_METADATA',metadata),('BOUND_PACKAGE_MANIFEST',package_declaration)]:
        if declaration is not None:
            candidates.append((source,_declared_scale(declaration,file_hash=file_hash,x_binding=x_binding,
                obs_hash=obs_hash,var_hash=var_hash,source=source)))
    if len({scale for _,scale in candidates})>1:raise ValueError('Conflicting expression-scale evidence; no normalization will run.')
    if candidates:
        source,scale=candidates[0]
        if log1p_marker and scale!='log1p':raise ValueError('A log1p marker conflicts with an unlogged declaration; refusing repeated log1p.')
        return {'status':'RESOLVED','scale':scale,'evidence_source':source,'confirmation_acknowledged':False}
    if confirmation is not None:
        if not isinstance(confirmation,dict) or confirmation.get('file_sha256')!=file_hash or confirmation.get('x_sha256')!=x_binding['sha256']:
            raise ValueError('Expression confirmation belongs to different file content.')
        if confirmation.get('acknowledged') is not True or confirmation.get('scale') not in SCALES:
            raise ValueError('Explicitly confirm the current .X processing state.')
        scale=confirmation['scale']
        if log1p_marker and scale!='log1p':raise ValueError('A log1p marker conflicts with the confirmation; fix contradictory producer metadata first.')
        return {'status':'RESOLVED','scale':scale,'evidence_source':'USER_CONFIRMED','confirmation_acknowledged':True}
    return {'status':'NEEDS_CONFIRMATION','scale':None,'evidence_source':None,
        'reason':'No content-bound explicit .X processing declaration. Filenames, integer-like values and maxima are not scale proof.',
        'log1p_marker':bool(log1p_marker)}


def inspect_h5ad_contract(path,filename=None,package_declaration=None,confirmation=None):
    import anndata as ad
    path=Path(path);filename=filename or path.name;before=path.stat();file_hash=file_sha(path)
    data=ad.read_h5ad(path,backed='r')
    try:
        if data.n_obs<1052 or data.n_vars<3:raise ValueError(filename+': require at least1052 spots and3 genes.')
        for kind,names in [('Spot',data.obs_names),('Gene',data.var_names)]:
            if not names.is_unique or names.hasnans or any(not str(v).strip() for v in names):raise ValueError(filename+': '+kind+' IDs must be unique and nonempty.')
        spatial=validate_spatial(data,sample=filename,allow_obs_coordinates=False)
        x=matrix_evidence(data.X);obs_hash=name_sha(data.obs_names);var_hash=name_sha(data.var_names)
        metadata=data.uns.get('river_input_contract')
        resolution=resolve_scale(file_hash=file_hash,x_binding=x,obs_hash=obs_hash,var_hash=var_hash,
            metadata=metadata,package_declaration=package_declaration,log1p_marker='log1p' in data.uns,confirmation=confirmation)
        return {'file_name':filename,'file_sha256':file_hash,'n_obs':int(data.n_obs),'n_vars':int(data.n_vars),
            'x_binding':x,'obs_names_sha256':obs_hash,'var_names_sha256':var_hash,
            'spatial':spatial,'log1p_marker':'log1p' in data.uns,**resolution}
    finally:
        data.file.close();after=path.stat()
        if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):
            raise ValueError('The input changed during contract inspection; inspect again.')


def package_manifest(bundle):
    entries=[i for i in bundle.infolist() if Path(i.filename.replace('\\','/')).name==MANIFEST_NAME and not i.is_dir()]
    if not entries:return {}
    if len(entries)!=1 or entries[0].filename!=MANIFEST_NAME:raise ValueError('Supply at most one root-level '+MANIFEST_NAME)
    info=entries[0]
    if info.file_size>MAX_MANIFEST_BYTES or info.flag_bits&1:raise ValueError('Input manifest is oversized/encrypted.')
    raw=bundle.read(info)
    value=json.loads(raw.decode('utf-8'))
    if not isinstance(value,dict) or value.get('schema')!=MANIFEST_SCHEMA or not isinstance(value.get('samples'),list):raise ValueError('Invalid River input manifest.')
    result={}
    for row in value['samples']:
        name=row.get('file_name') if isinstance(row,dict) else None
        if not isinstance(name,str) or not name.lower().endswith('.h5ad') or ':' in name or PurePosixPath(name.replace('\\','/')).name!=name or name.casefold() in result:raise ValueError('Invalid/duplicate manifest sample filename.')
        result[name.casefold()]={**row,'schema':MANIFEST_SCHEMA}
    return result


def confirmation_for(row,scale):
    if row.get('status')!='NEEDS_CONFIRMATION':return row
    result=resolve_scale(file_hash=row['file_sha256'],x_binding=row['x_binding'],obs_hash=row['obs_names_sha256'],
        var_hash=row['var_names_sha256'],log1p_marker=row.get('log1p_marker',False),
        confirmation={'file_sha256':row['file_sha256'],'x_sha256':row['x_binding']['sha256'],'scale':scale,'acknowledged':True})
    return {**row,**result}
