from __future__ import annotations

import argparse
import os
import sys

from .config import load_cloud_config
from .executors.local_gpu import LocalGPUExecutor
from .job_dispatcher import JobDispatcher
from .lab_runtime import LAB_GPU_QUEUE_NAMES, LAB_GPU_UI_LABELS, validate_lab_gpu_worker_environment
from .models import ResourceType


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a pinned SpaShiny Lab GPU worker.")
    parser.add_argument("--gpu-index", required=True, choices=("0", "1"), help="Physical GPU index pinned by Docker.")
    parser.add_argument("--once", action="store_true", help="Process one dispatcher tick and exit.")
    parser.add_argument("--healthcheck", action="store_true", help="Validate CUDA visibility and exit.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    gpu_choice = f"gpu-{args.gpu_index}"
    os.environ["SPASHINY_ASSIGNED_GPU"] = gpu_choice
    config = load_cloud_config()
    manifest = validate_lab_gpu_worker_environment(config)
    if args.healthcheck:
        return 0
    worker_id = os.environ.get("SPASHINY_WORKER_ID", f"spashiny-lab-gpu-worker-{args.gpu_index}").strip()
    executor = LocalGPUExecutor(
        physical_gpu_index=int(args.gpu_index),
        ui_gpu_label=LAB_GPU_UI_LABELS[gpu_choice],
        gpu_name=str(manifest.get("gpu_name") or ""),
        gpu_uuid=str(manifest.get("gpu_uuid") or ""),
        termination_grace_seconds=int(config.local_process_termination_grace_seconds),
    )
    dispatcher = JobDispatcher(
        config=config,
        worker_id=worker_id,
        worker_type="gpu",
        enabled_resources=(ResourceType.GPU.value,),
        gpu_queue_names=(LAB_GPU_QUEUE_NAMES[gpu_choice],),
        executors={ResourceType.GPU.value: executor},
    )
    try:
        if args.once or os.environ.get("SPASHINY_WORKER_ONCE", "").strip().lower() in {"1", "true", "yes", "on"}:
            dispatcher.run_once()
        else:
            dispatcher.run_forever()
    finally:
        dispatcher.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
