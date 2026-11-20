"""Isolated v2 process entry; archived scientific code is imported unchanged.

The current platform Runner remains an input/output adapter. Its historical
preparation branch was compared against the original Python calls with fresh
real-data PCA/SLAT. Neither the archived fixed_pipeline nor any core is edited.
"""
import argparse
import importlib.metadata as md
import inspect
import json
from pathlib import Path
import sys
import time

GPU_ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(GPU_ROOT))
from cloud.river_execution_contract import normalize_v2
from cloud.river_execution_profiles import profile,verify_profile
from cloud.river_unified_contract import V3, normalize_unified
from cloud.river_paths import load_server_paths


def runtime(parameters):
    p=normalize_unified(parameters) if parameters.get('execution_contract_version')==V3 else normalize_v2(parameters)
    selected=profile(p['execution_mode'],GPU_ROOT)
    hashes=verify_profile(selected)
    if Path(sys.executable).absolute()!=selected['python'].absolute():
        raise RuntimeError('Unexpected interpreter path; refusing a silent mode change.')
    required={'python':'3.8.20','numpy':'1.24.4','scipy':'1.10.1','pandas':'1.5.3','scanpy':'1.9.8','anndata':'0.9.2','torch':'2.3.1+cu121','captum':'0.7.0','scSLAT':'0.3.0'} if p['execution_mode']=='original_python_parity' else {
        'python':'3.10.14','scanpy':'1.11.5','anndata':'0.11.4','torch':'2.2.2','captum':'0.8.0'}
    import platform
    actual={'python':platform.python_version()}
    for package in required:
        if package!='python':actual[package]=md.version(package)
    for package,expected in required.items():
        # Production Torch has a CUDA local-version suffix on some builds.
        ok=actual[package]==expected or (p['execution_mode']=='corrected_training' and package=='torch' and actual[package].split('+')[0]==expected)
        if not ok:raise RuntimeError('Runtime dependency mismatch: '+package+'='+actual[package])
    if p['execution_mode']=='original_python_parity':
        sys.path.insert(0,str(selected['bundle']))
        from execution_modes import load_core
        River,contract,sources=load_core('original_python_parity',selected['bundle'])
    else:
        from river.river import River
        sources={name:{'path':str(selected['core']/name),'sha256':digest} for name,digest in hashes.items()}
    if Path(inspect.getfile(River)).resolve()!=selected['core']/'river.py':
        raise RuntimeError('The actual imported River core differs from the selected server profile.')
    return p,selected,{'execution_mode':p['execution_mode'],'input_profile':p.get('input_profile','unified_h5ad'),
        'execution_contract_version':p['execution_contract_version'],'runtime_versions':actual,
        'method_version':selected['method_version'],'core_sources':sources,'interpreter':sys.executable,
        'runtime_root':str(selected['runtime_root']) if selected.get('runtime_root') else None,
        'runtime_lock_sha256':selected.get('runtime_lock_sha256'),
        'server_paths_config_sha256':load_server_paths(required=True)['config_sha256'],
        'input_profile_verification':p.get('input_profile_verification','WORKER_REVALIDATED_V3')}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);parser.add_argument('--output')
    parser.add_argument('--probe',action='store_true');args=parser.parse_args()
    cfg=json.loads(Path(args.config).read_text(encoding='utf-8'))
    p,selected,record=runtime(cfg['platform_execution'])
    from cloud.river_trusted_inputs import recognize_hashes
    verification=recognize_hashes(item.get('original_h5ad',{}).get('sha256') for item in cfg.get('samples',[]))
    record['input_profile_verification']=verification['status']
    record['trusted_input_manifest']=verification
    if args.probe:
        print(json.dumps(record));return 0
    if not args.output:raise ValueError('A new job output directory is required.')
    out=Path(args.output).resolve()
    if (out/'river_summary.json').exists():raise RuntimeError('Refusing to overwrite a prior River result.')
    # Scientific calls stay in the existing tested adapter; v2 chooses the
    # actual imported core BEFORE the adapter imports River.
    import river_runner
    started=time.monotonic()
    sys.argv=[str(GPU_ROOT/'app/river_runner.py'),'--config',args.config,'--output',args.output]
    river_runner.main()
    record['wall_time_seconds']=time.monotonic()-started
    record['job_id']=str(cfg.get('job_id') or '')
    for filename in ('river_execution_trace.json','river_summary.json'):
        path=out/filename
        value=json.loads(path.read_text(encoding='utf-8'))
        value.update(record)
        if filename=='river_execution_trace.json':
            value['runner_extra_pca_call_count']=sum(item.get('runner_extra_pca_call_count',0) for item in value.get('sample_checks',[]))
        path.write_text(json.dumps(value,indent=2),encoding='utf-8')
    summary=json.loads((out/'river_summary.json').read_text(encoding='utf-8'))
    return 0 if summary.get('river_success') else 1


if __name__=='__main__':raise SystemExit(main())
