"""Versioned platform contract only. No scientific algorithms or DB access.

v1 analysis_mode remains an INPUT-preparation switch, never reinterpreted as
the v2 execution_mode. Historical training requires an explicit v2 request.
"""
from pathlib import PurePosixPath

V2='river-execution-v2'
V1='river-parity-execution-v1'
WORKFLOW='river_spatial_transcriptomics'
PROFILES=('spa_data_export','general_h5ad')
MODES=('original_python_parity','corrected_training')
REFERENCE_ORDER=('V39','V28','V38','V44','V27')
FORBIDDEN_RUNTIME_OVERRIDES=frozenset({'python','python_path','python_executable','runner_python','runner_path','bundle',
    'bundle_path','execution_profile','runtime_profile','SPASHINY_RIVER_PYTHON','checkpoint_path','model_path'})


class RiverContractError(ValueError):
    pass


def _integer(value,name,minimum,maximum):
    if isinstance(value,bool) or not isinstance(value,int) or not minimum<=value<=maximum:
        raise RiverContractError('%s must be an integer between %s and %s.'%(name,minimum,maximum))
    return value


def normalize_v2(parameters):
    p=dict(parameters or {})
    if p.get('execution_contract_version')!=V2:
        raise RiverContractError('This entry requires the explicit river-execution-v2 contract.')
    if any(k in p for k in ('analysis_mode','requested_analysis_mode')):
        raise RiverContractError('v2 cannot contain legacy analysis_mode fields; do not reinterpret an old job.')
    if FORBIDDEN_RUNTIME_OVERRIDES.intersection(p):
        raise RiverContractError('Browser requests cannot choose interpreters, bundles, runners or model checkpoints.')
    profile=p.get('input_profile');mode=p.get('execution_mode');scale=p.get('input_scale')
    if profile not in PROFILES:raise RiverContractError('Choose an explicit supported Input data profile.')
    if mode not in MODES:raise RiverContractError('Choose original_python_parity or corrected_training explicitly.')
    if scale not in ('raw_counts','normalized_counts','log1p'):
        raise RiverContractError('Declare .X scale explicitly; file/sample names are not evidence of raw counts.')
    if profile=='spa_data_export' and scale!='raw_counts':
        raise RiverContractError('The spa_data_export profile declares unnormalized .X. Use general_h5ad for processed .X.')
    if p.get('data_source_mode') not in ('USER_UPLOAD','EXAMPLE'):
        raise RiverContractError('data_source_mode must name the actual upload or example source.')
    order=p.get('sample_order');labels=p.get('time_labels')
    if not isinstance(order,list) or not 2<=len(order)<=64:
        raise RiverContractError('Provide 2-64 unique ordered H5AD filenames.')
    if any(not isinstance(x,str) or not x or ':' in x or not x.lower().endswith('.h5ad') or PurePosixPath(x.replace('\\','/')).name!=x for x in order):
        raise RiverContractError('sample_order must contain filenames, not paths.')
    if len({name.casefold() for name in order})!=len(order):
        raise RiverContractError('Sample filenames must be unique, including case-insensitive archive names.')
    if not isinstance(labels,list) or len(labels)!=len(order) or any(not isinstance(x,str) or not x.strip() for x in labels):
        raise RiverContractError('One nonempty time label is required for each ordered sample.')
    _integer(p.get('random_seed'),'random_seed',42,42)
    _integer(p.get('river_epochs'),'river_epochs',10,1000)
    size=_integer(p.get('subsample_size'),'subsample_size',20,2**31-1)
    if p.get('subsample_mode') not in ('minimum','custom'):raise RiverContractError('Choose minimum or custom spot sampling.')
    if mode=='original_python_parity':
        if scale!='raw_counts' or size!=1052 or p['river_epochs']!=100:
            raise RiverContractError('Historical parity locks raw_counts, 1052 spots, Scanpy random_state0, seed42 and100 epochs.')
        import re
        ids=[re.match(r'^(V39|V28|V38|V44|V27)(?:$|[_\-.])',PurePosixPath(x).stem,re.I) for x in order]
        if any(ids) and tuple(m.group(1).upper() if m else None for m in ids)!=REFERENCE_ORDER:
            raise RiverContractError('The102843 reference order is V39,V28,V38,V44,V27; partial or reordered references are rejected.')
    source=p.get('annotation_source') or ('h5ad' if p.get('annotation_column') else 'none')
    column=str(p.get('annotation_column') or '').strip();value=str(p.get('annotation_value') or '').strip()
    if source not in ('none','h5ad','csv') or (source=='none' and (column or value)) or (source!='none' and not column):
        raise RiverContractError('Annotation is optional; selected annotations require an explicit source and column.')
    p.update(annotation_source=source,annotation_column=column,annotation_value=value,
        allow_missing_annotation=p.get('allow_missing_annotation') is True,
        input_profile_verification='UNVERIFIED_USER_DECLARATION',sampling_random_state=0,
        preparation_policy='102843-original-v1' if mode=='original_python_parity' else 'existing-general-v1')
    return p


def validate_submission(parameters,*,workflow_name=WORKFLOW,expected_source=None):
    p=dict(parameters or {})
    if workflow_name!=WORKFLOW:return p
    # Only creation of NEW jobs is unified. Worker parsers for existing v1/v2
    # jobs remain below their original contracts and are never reinterpreted.
    from .river_unified_contract import normalize_unified
    return normalize_unified(p,expected_source=expected_source)
