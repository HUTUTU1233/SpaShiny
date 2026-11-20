# Extracted from /app/app/ST-SM.py. Feature: console; ordered phases preserve original initialization.
from spashiny._shared import runtime_globals as _spashiny_globals


def _install_0(_spashiny_ctx):

    @_spashiny_ctx.output
    @_spashiny_ctx.render.text
    def console_output():
        return _spashiny_ctx.log_text.get()

    _spashiny_ctx.console_output = console_output

    @_spashiny_ctx.output
    @_spashiny_ctx.render.text
    def process_status():
        txt = _spashiny_ctx.log_text.get()
        return txt.splitlines()[-1] if txt else "OK"

    _spashiny_ctx.process_status = process_status

    @_spashiny_ctx.output
    @_spashiny_ctx.render.text
    def process_status_st():
        txt = _spashiny_ctx.log_text.get()
        return txt.splitlines()[-1] if txt else "OK"

    _spashiny_ctx.process_status_st = process_status_st
    _spashiny_ctx.temp_dir_holder = {"path": None}

    def create_temp_dir():
        td = _spashiny_ctx.temp_dir.get()
        if td is None:
            td_path = _spashiny_ctx.Path(_spashiny_ctx.tempfile.mkdtemp())
            _spashiny_ctx.temp_dir.set(td_path)
            _spashiny_ctx.temp_dir_holder["path"] = td_path
            _spashiny_ctx.log(f"Created temp directory: {td_path}")
            return td_path
        _spashiny_ctx.temp_dir_holder["path"] = td
        return td

    _spashiny_ctx.create_temp_dir = create_temp_dir

    @_spashiny_ctx.session.on_ended
    def cleanup():
        try:
            td = _spashiny_ctx.temp_dir_holder["path"]
            if td and _spashiny_ctx.Path(td).exists():
                _spashiny_ctx.shutil.rmtree(td, ignore_errors=True)
                _spashiny_globals.safe_console_print("Temporary directory cleaned up.", flush=True)
        except Exception as exc:
            _spashiny_globals.safe_console_print(
                f"Temporary directory cleanup failed: {type(exc).__name__}: {exc}", flush=True
            )
        try:
            _spashiny_globals.gc.collect()
        except Exception as exc:
            _spashiny_globals.safe_console_print(
                f"Python garbage collection cleanup failed: {type(exc).__name__}: {exc}", flush=True
            )

    _spashiny_ctx.cleanup = cleanup


_STEPS = (_install_0,)


def server(_spashiny_ctx, step=0):
    return _STEPS[step](_spashiny_ctx)
