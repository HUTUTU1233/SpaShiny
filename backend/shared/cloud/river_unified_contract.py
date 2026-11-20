"""One contract for ALL newly submitted River jobs; legacy execution is separate."""
import re
from pathlib import PurePosixPath

V3='river-unified-v3'
MODE='original_python_parity'
SCALES=('raw_counts','normalized_counts','log1p')
RUNTIME_KEYS=frozenset({'python','python_path','python_executable','runner_python','runner_path','bundle','bundle_path',
    'execution_profile','runtime_profile','SPASHINY_RIVER_PYTHON','checkpoint_path','model_path','rng_path',
    'rng_state','cuda_rng','force_historical_rng','historical_rng_path'})


def digest(value):return isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value) is not None


def normalize_unified(parameters,expected_source=None):
    p=dict(parameters or {})
    if p.get('execution_contract_version')!=V3:raise ValueError('New River jobs require river-unified-v3. Inspect inputs with the current page.')
    if p.get('execution_mode')!=MODE:raise ValueError('All new River jobs use Original Python Parity; no mode fallback is allowed.')
    if RUNTIME_KEYS.intersection(p):raise ValueError('Requests cannot select executable paths, RNG files or model checkpoints.')
    if any(k in p for k in ('analysis_mode','requested_analysis_mode','input_profile','input_scale')):
        raise ValueError('User-selected preparation/scale modes are not part of the unified contract.')
    source=p.get('data_source_mode')
    if source not in ('EXAMPLE','USER_UPLOAD') or expected_source is not None and source!=expected_source:
        raise ValueError('Choose the actual built-in example or upload source; they cannot be mixed.')
    for key,fixed in (('random_seed',42),('sampling_random_state',0),('subsample_size',1052),('river_epochs',100)):
        if type(p.get(key)) is not int or p.get(key)!=fixed:raise ValueError('%s is fixed at %s by the original workflow.'%(key,fixed))
    order=p.get('sample_order');labels=p.get('time_labels');evidence=p.get('sample_evidence')
    if not isinstance(order,list) or not 2<=len(order)<=64:raise ValueError('Provide2-64 ordered H5AD samples.')
    if any(not isinstance(n,str) or not n or ':' in n or PurePosixPath(n.replace('\\','/')).name!=n or not n.lower().endswith('.h5ad') for n in order):
        raise ValueError('sample_order must contain H5AD basenames, not paths.')
    if len({n.casefold() for n in order})!=len(order):raise ValueError('Sample filenames must be unique.')
    if not isinstance(labels,list) or len(labels)!=len(order) or any(not isinstance(n,str) or not n.strip() for n in labels):
        raise ValueError('Every ordered sample requires a nonempty time label.')
    if not isinstance(evidence,list) or len(evidence)!=len(order):raise ValueError('Inspect every H5AD and resolve unknown expression states before submitting.')
    for filename,row in zip(order,evidence):
        if not isinstance(row,dict) or row.get('file_name')!=filename or not digest(row.get('file_sha256')):
            raise ValueError('Input evidence does not match the ordered files.')
        if row.get('status')!='RESOLVED':raise ValueError(filename+': expression state is unresolved; confirm before submitting.')
        if not isinstance(row.get('n_obs'),int) or isinstance(row.get('n_obs'),bool) or row['n_obs']<1052:
            raise ValueError(filename+': at least1052 spots are required; no silent reduction.')
        if type(row.get('n_vars')) is not int or row['n_vars']<3:raise ValueError(filename+': at least3 genes are required.')
        if row.get('scale') not in SCALES:raise ValueError(filename+': expression state is unknown; confirm before submitting.')
        if row.get('evidence_source') not in ('SERVER_CONTENT_MANIFEST','BOUND_H5AD_METADATA','BOUND_PACKAGE_MANIFEST','USER_CONFIRMED'):
            raise ValueError(filename+': no auditable expression-state evidence.')
        if row.get('evidence_source')=='USER_CONFIRMED' and row.get('confirmation_acknowledged') is not True:
            raise ValueError(filename+': explicitly acknowledge the unknown expression state.')
        binding=row.get('x_binding')
        if not isinstance(binding,dict) or not digest(binding.get('sha256')) or binding.get('shape')!=[row['n_obs'],row['n_vars']]:
            raise ValueError(filename+': missing current .X fingerprint binding.')
    column=str(p.get('annotation_column') or '').strip();value=str(p.get('annotation_value') or '').strip()
    annotation=p.get('annotation_source') or ('h5ad' if column else 'none')
    if annotation not in ('none','h5ad','csv') or annotation=='none' and (column or value) or annotation!='none' and not column:
        raise ValueError('Optional plot annotations require an explicit existing column.')
    p.update(annotation_source=annotation,annotation_column=column,annotation_value=value,
        allow_missing_annotation=p.get('allow_missing_annotation') is True)
    return p


def runner_settings(config):
    p=normalize_unified(config['platform_execution'])
    return {'analysis_mode':MODE,'requested_analysis_mode':MODE,'execution_contract_version':V3,
        'input_scale':p['sample_evidence'][0]['scale'],'random_seed':42,'subsample_size':1052,'river_epochs':100,
        'annotation_source':p['annotation_source'],'annotation_column':p['annotation_column'],
        'annotation_value':p['annotation_value'],'allow_missing_annotation':p['allow_missing_annotation'],
        'strict_samples':True,'platform_version':'river-unified-input-v3'}


def resolve_runner_settings(config,legacy_validator):
    if config.get('execution_contract_version')==V3:return runner_settings(config)
    return legacy_validator(config)
