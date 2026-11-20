"""Server-owned RIVER path policy; never accepts request/runtime overrides.

Missing configuration is permitted only for offline inspection. Every actual
scientific interpreter selection verifies the shared file with required=True.
"""
import hashlib
import os
from pathlib import Path
import stat

PROJECT=Path('/srv/spashiny')
RUNTIME_NAME='river-original-python-strict-20261101-r1'
DIRECTORIES={
    'RIVER_RELEASE_RUNTIMES':'river-release-runtimes',
    'RIVER_UNIFIED_INPUT_CANDIDATE':'river-unified-input-candidate',
    'RIVER_CUDA_RNG_DIAGNOSTICS':'river-cuda-rng-diagnostics',
    'RIVER_UI_BACKEND_CANDIDATE':'river-ui-backend-candidate',
    'RIVER_PARITY_REPAIR':'river-parity-repair',
    'RIVER_AUDIT_ENV_AUDIT':'river-audit-env-audit',
    'RIVER_AUDIT_CHECKPOINTS':'river-audit-checkpoints',
}

def load_server_paths(required=False):
    expected={'RIVER_PROJECT_ROOT':PROJECT.as_posix(),**{k:(PROJECT/v).as_posix() for k,v in DIRECTORIES.items()}}
    config=PROJECT/'river-paths.env'
    if config.is_file():
        if os.name!='nt':
            mode=config.stat()
            if mode.st_uid not in (0,os.getuid()) or stat.S_IMODE(mode.st_mode)&0o022:
                raise ValueError('RIVER path configuration must be server-owned and not group/world writable.')
        raw=config.read_bytes();actual={}
        for line in raw.decode('utf-8').splitlines():
            line=line.strip()
            if not line or line.startswith('#'):continue
            key,separator,value=line.partition('=')
            if not separator or key in actual or key not in expected:
                raise ValueError('Unknown/duplicate server path configuration key.')
            actual[key]=value
        if actual!=expected:
            raise ValueError('RIVER server path configuration does not match the approved project roots.')
        config_sha256=hashlib.sha256(raw).hexdigest()
    elif required:
        raise ValueError('The shared server-owned river-paths.env is missing; no path fallback is allowed.')
    else:config_sha256=None
    return {**{key:Path(value) for key,value in expected.items()},
        'runtime':PROJECT/'river-release-runtimes'/RUNTIME_NAME,
        'history_rng':PROJECT/'river-audit-checkpoints/historical-102843/rng_before_training.pkl',
        'config_file':config,'config_sha256':config_sha256}
