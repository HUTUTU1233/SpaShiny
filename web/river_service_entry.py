"""Release boundary: validate the shared path policy before starting a service.

This wrapper does not change scientific parameters, imports or random state.
Web/Control stay in their image environment; GPU orchestration retains its
existing interpreter and selects the frozen scientific child per job contract.
"""
import argparse
import os
from pathlib import Path
import sys


def validate(role, source_root):
    source_root = Path(source_root).resolve()
    sys.path.insert(0, str(source_root))
    from cloud.river_paths import load_server_paths
    paths = load_server_paths(required=True)
    required = ("SPASHINY_DATABASE_URL", "SPASHINY_LOCAL_DATA_ROOT",
                "SPASHINY_LOCAL_RESULT_ROOT", "SPASHINY_LOCAL_JOBS_ROOT",
                "SPASHINY_LOCAL_LOGS_ROOT", "SPASHINY_LOCAL_SQLITE_ROOT",
                "SPASHINY_SESSION_HMAC_SECRET")
    missing = [key for key in required if not str(os.environ.get(key) or '').strip()]
    if missing:
        raise RuntimeError('Missing explicit release configuration: ' + ', '.join(missing))
    if role == 'gpu':
        for key in ('SPASHINY_LAB_ROOT', 'SPASHINY_HOTFIX_RUNTIME_ROOT', 'SPASHINY_HOST_GPU_ENV'):
            if not str(os.environ.get(key) or '').strip():
                raise RuntimeError('GPU host mapping must be explicit: ' + key)
        if Path(os.environ['SPASHINY_LAB_ROOT']).resolve() != paths['RIVER_PROJECT_ROOT']:
            raise RuntimeError('GPU project root does not match the approved release policy.')
    if role == 'web' and not str(os.environ.get('SPASHINY_CONTROL_API_BASE_URL') or '').strip():
        raise RuntimeError('Web must have an explicit Control upstream.')
    return paths


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--role', required=True, choices=('web', 'control', 'gpu'))
    parser.add_argument('--source-root', required=True)
    parser.add_argument('--gpu-index', choices=('0', '1'))
    args = parser.parse_args()
    paths = validate(args.role, args.source_root)
    print('RIVER_RELEASE_PATH_POLICY=' + paths['config_sha256'], flush=True)
    os.chdir(args.source_root)
    if args.role == 'gpu':
        if args.gpu_index is None:
            raise RuntimeError('A physical GPU must be explicitly assigned.')
        command = [sys.executable, '-B', str(Path(args.source_root) / 'host_gpu_worker.py'),
                   '--gpu-index', args.gpu_index]
    else:
        module, port = ('cloud.web_proxy_app:app', '8001') if args.role == 'web' else ('cloud.api:app', '8000')
        command = [sys.executable, '-B', '-m', 'uvicorn', module, '--host', '0.0.0.0', '--port', port]
    os.execvpe(command[0], command, os.environ)


if __name__ == '__main__':
    main()
