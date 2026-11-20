# Extracted from /app/app/ST-SM.py. Feature: workbench_bridge; ordered phases preserve original initialization.
from spashiny._shared import runtime_globals as _spashiny_globals


def _install_0(_spashiny_ctx):
    _spashiny_globals.register_workbench(
        _spashiny_ctx.input,
        _spashiny_ctx.output,
        _spashiny_ctx.session,
        _spashiny_globals.create_adapter({**vars(_spashiny_globals), **vars(_spashiny_ctx)}),
    )


_STEPS = (_install_0,)


def server(_spashiny_ctx, step=0):
    return _STEPS[step](_spashiny_ctx)
