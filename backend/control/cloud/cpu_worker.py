from __future__ import annotations

import argparse
import os
import sys

from .job_dispatcher import JobDispatcher
from .models import ResourceType


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the SpaShiny local CPU worker.")
    parser.add_argument("--once", action="store_true", help="Process one dispatcher tick and exit.")
    parser.add_argument("--healthcheck", action="store_true", help="Validate worker imports and exit.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.healthcheck:
        return 0

    worker_id = os.environ.get("SPASHINY_WORKER_ID", "leaseweb-local-cpu-1").strip() or "leaseweb-local-cpu-1"
    dispatcher = JobDispatcher(
        worker_id=worker_id,
        worker_type="cpu",
        enabled_resources=(ResourceType.CPU.value,),
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
