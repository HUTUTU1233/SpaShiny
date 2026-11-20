"""v2 per-job dispatch. Owner/analysis/input authorization stays upstream."""
import json
import os
from pathlib import Path
import subprocess

from .common import CPUWorkflowError,write_json,sha256_file
from ..river_execution_contract import normalize_v2,V1
from ..river_execution_profiles import profile,verify_profile,child_environment


def run_v2(ctx):
    from .river_st import _input_sets,_sample_label_map,_match_csv,_river_compatible_copy,_create_archive,RIVER_PUBLIC_OUTPUTS
    p=normalize_v2(ctx.parameters)
    gpu_root=Path(__file__).resolve().parents[2]
    selected=profile(p['execution_mode'],gpu_root)
    try:
        hashes=verify_profile(selected)
        env=child_environment(selected,os.environ)
    except (ValueError,OSError) as exc:
        raise CPUWorkflowError('RIVER_EXECUTION_PROFILE_UNAVAILABLE',str(exc)) from exc
    paths,csvs=_input_sets(ctx);labels=_sample_label_map(p,paths)
    if [path.name for path in paths]!=p['sample_order']:
        raise CPUWorkflowError('RIVER_SAMPLE_ORDER_MISMATCH','Authorized inputs do not match the submitted order.')
    historical=p['execution_mode']=='original_python_parity'
    settings={'analysis_mode':'original_python_parity' if historical else 'general','requested_analysis_mode':'original_python_parity' if historical else 'general',
        'execution_contract_version':V1,'input_scale':p['input_scale'],'random_seed':42,
        'subsample_size':p['subsample_size'],'river_epochs':p['river_epochs'],
        'annotation_source':p['annotation_source'],'annotation_column':p['annotation_column'],
        'annotation_value':p['annotation_value'],'allow_missing_annotation':p['allow_missing_annotation']}
    samples=[]
    for source,label in zip(paths,labels):
        before=source.stat();original={'path':str(source.resolve()),'sha256':sha256_file(source),'size_bytes':before.st_size}
        destination=ctx.working_dir/'river_v2_compatible_inputs'/source.name
        _river_compatible_copy(source,destination,settings)
        after=source.stat()
        if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):
            raise CPUWorkflowError('RIVER_INPUT_CHANGED','An authorized input changed during preparation.')
        annotation=_match_csv(source,csvs)
        samples.append({'sample_id':source.stem,'condition':label,'data_path':str(destination),
            'csv_path':str(annotation) if annotation else '','original_h5ad':original})
    config={**settings,'mode':'ST','samples':samples,'subsample_mode':p['subsample_mode'],
        'sample_order':p['sample_order'],'representative_gene':p.get('representative_gene',''),
        'job_id':ctx.job_id,'platform_execution':p}
    config_path=ctx.working_dir/'river_v2_config.json';write_json(config_path,config)
    # No shell, no request-controlled interpreter, inherited scheduler CUDA.
    log=ctx.logs_dir/'river_runner.log'
    with log.open('wb') as stream:
        completed=subprocess.run([str(selected['python']),'-B',str(selected['entry']),'--config',str(config_path),'--output',str(ctx.workspace)],
            cwd=str(gpu_root/'app'),env=env,stdout=stream,stderr=subprocess.STDOUT,check=False)
    if completed.returncode:
        raise CPUWorkflowError('RIVER_RUNNER_FAILED','The selected v2 interpreter failed; no fallback. Inspect the authorized job log.')
    summary=json.loads((ctx.workspace/'river_summary.json').read_text(encoding='utf-8'))
    if not summary.get('river_success') or summary.get('execution_mode')!=p['execution_mode']:
        raise CPUWorkflowError('RIVER_MODE_RESULT_MISMATCH','The result did not confirm the requested execution mode.')
    _create_archive(ctx.workspace,ctx.workspace/'results.zip')
    return {'metrics':{'public_workflow':'spatial_transcriptomics_river','input_profile':p['input_profile'],
        'execution_mode':p['execution_mode'],'execution_contract_version':p['execution_contract_version'],
        'method_version':selected['method_version'],'runtime_versions':summary['runtime_versions'],
        'core_sha256':hashes,'sample_order':p['sample_order'],'sample_count':len(paths),
        'river_epochs':p['river_epochs'],'random_seed':42,'execution_device':'cuda'},
        'outputs':[name for name in (*RIVER_PUBLIC_OUTPUTS,'results.zip') if (ctx.workspace/name).is_file()]}
