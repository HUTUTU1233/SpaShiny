"""One new-job path regardless of example/upload. No training-method branch."""
import json
import os
from pathlib import Path
import subprocess
import zipfile
from .common import CPUWorkflowError,write_json,asset_paths
from ..river_unified_contract import normalize_unified,runner_settings
from ..river_scale_evidence import inspect_h5ad_contract,package_manifest
from ..river_execution_profiles import profile,verify_profile,child_environment


def run_unified(ctx):
    from .river_st import _input_sets,_match_csv,_river_compatible_copy,_create_archive,RIVER_PUBLIC_OUTPUTS
    p=normalize_unified(ctx.parameters)
    gpu_root=Path(__file__).resolve().parents[2]
    selected=profile('original_python_parity',gpu_root)
    try:hashes=verify_profile(selected);env=child_environment(selected,os.environ)
    except (ValueError,OSError) as exc:raise CPUWorkflowError('RIVER_PROFILE_UNAVAILABLE',str(exc)) from exc
    paths,csvs=_input_sets(ctx)
    if [path.name for path in paths]!=p['sample_order']:raise CPUWorkflowError('RIVER_INPUT_ORDER_CHANGED','Ordered authorized inputs differ from inspected files.')
    declarations={}
    for path in asset_paths(ctx):
        if Path(path).suffix.lower()=='.zip':
            with zipfile.ZipFile(path) as bundle:declarations=package_manifest(bundle)
    if set(declarations)-{path.name.casefold() for path in paths}:
        raise CPUWorkflowError('RIVER_MANIFEST_SAMPLE_MISSING','The input manifest refers to samples missing from the package.')
    settings=runner_settings({'platform_execution':p});samples=[]
    for source,label,evidence in zip(paths,p['time_labels'],p['sample_evidence']):
        confirmation=None
        if evidence['evidence_source']=='USER_CONFIRMED':
            confirmation={'file_sha256':evidence['file_sha256'],'x_sha256':evidence['x_binding']['sha256'],
                'scale':evidence['scale'],'acknowledged':evidence['confirmation_acknowledged']}
        actual=inspect_h5ad_contract(source,source.name,package_declaration=declarations.get(source.name.casefold()),confirmation=confirmation)
        for key in ('file_sha256','n_obs','n_vars','scale','evidence_source'):
            if actual.get(key)!=evidence.get(key):raise CPUWorkflowError('RIVER_INSPECTION_STALE',source.name+': '+key+' changed; inspect again.')
        if actual['x_binding']['sha256']!=evidence['x_binding']['sha256']:
            raise CPUWorkflowError('RIVER_EXPRESSION_CHANGED',source.name+': current .X differs from the confirmed matrix.')
        private=ctx.working_dir/'river_unified_inputs'/source.name
        sample_settings={**settings,'input_scale':actual['scale']}
        before=source.stat()
        _river_compatible_copy(source,private,sample_settings)
        after=source.stat()
        if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):
            raise CPUWorkflowError('RIVER_INPUT_CHANGED','An authorized input changed while copying.')
        annotation=_match_csv(source,csvs)
        samples.append({'sample_id':source.stem,'condition':label,'data_path':str(private),
            'csv_path':str(annotation) if annotation else '',
            'original_h5ad':{'path':str(source.resolve()),'sha256':actual['file_sha256'],'size_bytes':source.stat().st_size},
            'resolved_input_scale':actual['scale'],'validated_evidence':actual})
    config={**settings,'mode':'ST','samples':samples,'sample_order':p['sample_order'],'subsample_mode':'custom',
        'job_id':ctx.job_id,'representative_gene':p.get('representative_gene',''),'platform_execution':p}
    path=ctx.working_dir/'river_unified_config.json';write_json(path,config)
    with (ctx.logs_dir/'river_runner.log').open('wb') as stream:
        done=subprocess.run([str(selected['python']),'-B',str(selected['entry']),'--config',str(path),'--output',str(ctx.workspace)],
            cwd=str(gpu_root/'app'),env=env,stdout=stream,stderr=subprocess.STDOUT,check=False)
    if done.returncode:raise CPUWorkflowError('RIVER_UNIFIED_FAILED','Unified historical-core execution failed. No General fallback. Inspect the job trace/log.')
    summary=json.loads((ctx.workspace/'river_summary.json').read_text(encoding='utf-8'))
    if not summary.get('river_success') or summary.get('execution_mode')!='original_python_parity':
        raise CPUWorkflowError('RIVER_RESULT_CONTRACT','The result did not confirm the unified execution core.')
    _create_archive(ctx.workspace,ctx.workspace/'results.zip')
    return {'metrics':{'execution_contract_version':p['execution_contract_version'],'execution_mode':'original_python_parity',
        'input_profile':'unified_h5ad','runtime_versions':summary['runtime_versions'],'core_sha256':hashes,
        'method_version':summary.get('method_version'),'scientific_interpreter':summary.get('interpreter'),
        'runtime_root':summary.get('runtime_root'),'runtime_lock_sha256':summary.get('runtime_lock_sha256'),
        'sample_expression_states':summary.get('sample_expression_states',[]),
        'sample_order':p['sample_order'],'sample_count':len(samples),'subsample_size':1052,'river_epochs':100,'random_seed':42,
        'historical_rng':summary.get('historical_rng',{}),'execution_device':'cuda'},
        'outputs':[name for name in (*RIVER_PUBLIC_OUTPUTS,'results.zip') if (ctx.workspace/name).is_file()]}
