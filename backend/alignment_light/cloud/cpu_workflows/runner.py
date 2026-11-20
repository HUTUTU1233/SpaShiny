from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

from .common import CPUWorkflowContext, CPUWorkflowError, peak_ram_mb, validate_result_contract, write_failure_artifacts, write_json, write_manifest, write_session_info, write_success_summary
from .registry import WORKFLOW_NOT_IMPLEMENTED, get_cpu_workflow


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if not argv:
        print("Usage: python -m cloud.cpu_workflows.runner <job_spec.json>", file=sys.stderr)
        return 2
    payload = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    ctx = CPUWorkflowContext.from_job_spec(payload)
    ctx.ensure_dirs()
    (ctx.logs_dir / "stdout.log").touch(exist_ok=True)
    (ctx.logs_dir / "stderr.log").touch(exist_ok=True)
    error_log = ctx.logs_dir / "error.log"
    if error_log.exists():
        error_log.unlink()
    start = time.monotonic()
    try:
        sleep_seconds = int(ctx.parameters.get("sleep_seconds") or 0)
        if sleep_seconds > 0:
            time.sleep(min(3600, sleep_seconds))
        spec = get_cpu_workflow(ctx.workflow_name)
        if not spec.enabled or spec.handler is None:
            raise CPUWorkflowError(WORKFLOW_NOT_IMPLEMENTED, f"CPU workflow is not implemented: {ctx.workflow_name}")
        result = spec.handler(ctx) or {}
        wall = time.monotonic() - start
        ram = peak_ram_mb()
        write_session_info(ctx)
        outputs = [str(item) for item in result.get("outputs") or []]
        metrics = dict(result.get("metrics") or {})
        write_success_summary(ctx, metrics=metrics, outputs=outputs, wall_time_seconds=wall, peak_ram_mb=ram)
        write_manifest(ctx, status="succeeded", wall_time_seconds=wall, peak_ram_mb=ram)
        ok, code, message = validate_result_contract(ctx.workspace, spec.required_outputs)
        if not ok:
            raise CPUWorkflowError(code or "RESULT_VALIDATION_FAILED", message)
        write_json(ctx.workspace / "cpu_workflow_status.json", {"status": "succeeded", "message": message, "error_code": ""})
        return 0
    except CPUWorkflowError as exc:
        wall = time.monotonic() - start
        write_failure_artifacts(ctx, code=exc.code, message=str(exc), wall_time_seconds=wall, peak_ram_mb=peak_ram_mb())
        write_json(ctx.workspace / "cpu_workflow_status.json", {"status": "failed", "message": str(exc), "error_code": exc.code})
        return 3
    except Exception as exc:
        wall = time.monotonic() - start
        message = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        write_failure_artifacts(ctx, code="CPU_WORKFLOW_EXCEPTION", message=message, wall_time_seconds=wall, peak_ram_mb=peak_ram_mb())
        write_json(ctx.workspace / "cpu_workflow_status.json", {"status": "failed", "message": str(exc), "error_code": "CPU_WORKFLOW_EXCEPTION"})
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
