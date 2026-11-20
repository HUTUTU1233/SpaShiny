"""Server-owned interpreter whitelist. No browser-controlled executable paths.

Candidate configuration only: this module is not installed in Production.
The historical runtime below was rebuilt from exact archives at the explicitly
approved persistent release path, then import/source/metadata/CUDA verified.
"""
from pathlib import Path
import hashlib
import json
import os
from .river_paths import load_server_paths

HISTORICAL_ROOT=load_server_paths()['runtime']
HISTORICAL_EXTRA=HISTORICAL_ROOT/'graph_extension'
FROZEN_RUNTIME_LOCK_SHA256='ff238a274cccfdb4376f2f4604e45d14a88fe850c57c1c29e5ebd44663b1865f'
EXPECTED_CORE={
    'model.py':'3364f2574d19513b185d97ac7cbcbac6e871d2af8b433bdddfa735a6bf06ca41',
    'preprocess.py':'47b4096de69ac62b0f0d7ab30568b488945d217f3999bc51855216e540942662',
}
HISTORICAL_RIVER='047563e08b276fa3e43fae09a0c9847a9586c854ee6c9c279d306ff647e77a9c'
CORRECTED_RIVER='66c3da2b21160f350b1be27a3786eef49f2c7fff8b2638f7e017555e1c01349d'
SC_SLAT={
    'loaddata.py':'62862dd489476522aee72cdcddb6c2b6488cfef57bcb98496837523e43843863',
    'preprocess.py':'22683379fc4b3619b244d399d2554f45cb40892b59a575939a6ed59bdf11885a',
    'utils.py':'53a07eba7147a8cca28c048e5279b48c5a71f7bcd0c020c177e8ee7f27711f19',
}


def profile(mode, gpu_root):
    gpu_root=Path(gpu_root).resolve()
    bundle=HISTORICAL_ROOT/'river_source'
    if mode=='original_python_parity':
        return {'mode':mode,'python':HISTORICAL_ROOT/'env/bin/python',
            'entry':gpu_root/'app/river_execution_entry.py','bundle':bundle,
            'core':bundle/'original_python_parity/river','river_sha256':HISTORICAL_RIVER,
            'python_paths':[HISTORICAL_EXTRA,bundle,bundle/'vendor',gpu_root/'app',gpu_root],
            'method_version':'river-102843-historical-behavior-v1',
            'runtime_root':HISTORICAL_ROOT,'runtime_lock_sha256':FROZEN_RUNTIME_LOCK_SHA256}
    if mode=='corrected_training':
        return {'mode':mode,'python':Path('/srv/spashiny/runtime/gpu-env-hotfix11/bin/python'),
            'entry':gpu_root/'app/river_execution_entry.py','bundle':None,
            'core':gpu_root/'app/river','river_sha256':CORRECTED_RIVER,
            'python_paths':[gpu_root/'app',gpu_root,Path('/srv/spashiny/releases/river-gpu-candidate-20260925/deps')],
            'method_version':'existing-production-training-unchanged'}
    raise ValueError('Unknown execution_mode: no environment fallback is permitted.')


def verify_profile(value):
    for name in ('python','entry'):
        if not value[name].is_file():raise ValueError('Required server execution file is absent: '+name)
    if not os.access(value['python'],os.X_OK):raise ValueError('The selected interpreter is not executable.')
    hashes={}
    for filename,expected in dict(EXPECTED_CORE,**{'river.py':value['river_sha256']}).items():
        path=value['core']/filename
        if not path.is_file():raise ValueError('Missing immutable River source: '+filename)
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if digest!=expected:raise ValueError('River core hash mismatch: '+filename)
        hashes[filename]=digest
    if value['mode']=='original_python_parity':
        load_server_paths(required=True)
        from .river_bundle_hashes import BUNDLE_SHA256
        for relative,expected in BUNDLE_SHA256.items():
            archived=value['bundle']/relative
            if not archived.is_file() or hashlib.sha256(archived.read_bytes()).hexdigest()!=expected:
                raise ValueError('Historical bundle file hash mismatch: '+relative)
        for filename,expected in SC_SLAT.items():
            path=value['bundle']/'vendor/scSLAT/model'/filename
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
                raise ValueError('Historical scSLAT source hash mismatch: '+filename)
        for name,expected in {
            'fixed_pipeline.py':'06df26e5ff0f4bdddf19263f8dcf0275b13379e0d8d74178a1d347fb35ced2f3',
            'execution_modes.py':'21d2a2cf6c793b8f9745b1525dcf4dac0f9c30b728f840fd2af8f5968e141cb5',
            'requirements-history-core.txt':'400e671f6a569161596ba9b5d10ab3bf0bf23e55e0b96f634b9fbffcd85d459c',
        }.items():
            if hashlib.sha256((value['bundle']/name).read_bytes()).hexdigest()!=expected:
                raise ValueError('Historical execution bundle changed: '+name)
        if not (value['python_paths'][0]/'torch_scatter').is_dir():
            raise ValueError('The isolated compatible graph extension is absent; no global installation/fallback.')
        raw=(HISTORICAL_ROOT/'manifests/RUNTIME_LOCK.final-path.json').read_bytes()
        if hashlib.sha256(raw).hexdigest()!=FROZEN_RUNTIME_LOCK_SHA256:
            raise ValueError('The approved frozen runtime lock changed; no environment fallback.')
        lock=json.loads(raw)
        if lock.get('schema')!='river-frozen-runtime-v1' or lock.get('status')!='VERIFIED' or lock.get('python')!=str(value['python']):
            raise ValueError('Frozen runtime identity/verification is invalid.')
        for relative,digest in lock['critical_files'].items():
            path=(HISTORICAL_ROOT/relative).resolve()
            if HISTORICAL_ROOT not in path.parents or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
                raise ValueError('Frozen runtime critical file changed: '+relative)
    return hashes


def child_environment(value, inherited):
    env=dict(inherited)
    if not str(env.get('CUDA_VISIBLE_DEVICES') or '').strip():
        raise ValueError('A worker-assigned CUDA device is required, never silently use CPU.')
    # The scheduler's CUDA value is propagated unchanged. Historical imports
    # never inherit the corrected environment's scSLAT / binary dependencies.
    paths=[str(p) for p in value['python_paths']]
    if value['mode']=='corrected_training' and env.get('PYTHONPATH'):paths.append(env['PYTHONPATH'])
    env['PYTHONPATH']=os.pathsep.join(paths)
    env['PYTHONDONTWRITEBYTECODE']='1'
    env.pop('SPASHINY_RIVER_PYTHON',None)  # v2 selection is per-job, not global.
    return env
