from __future__ import annotations

import argparse
import os

from cloud.config import load_cloud_config
from cloud.database import CloudDatabase
from cloud.executors.local_cpu import LocalCPUExecutor
from cloud.job_dispatcher import JobDispatcher
from cloud.models import ResourceType


RIVER_ST_QUEUE = "host_river_cpu"


def build_dispatcher() -> JobDispatcher:
    config = load_cloud_config()
    database = CloudDatabase(config=config)
    executor = LocalCPUExecutor(config=config, database=database)
    return JobDispatcher(
        database=database,
        config=config,
        worker_id=os.environ.get("SPASHINY_WORKER_ID", "spashiny-host-river-st"),
        worker_type="river_st",
        enabled_resources=(ResourceType.CPU.value,),
        cpu_queue_names=(RIVER_ST_QUEUE,),
        executors={ResourceType.CPU.value: executor},
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SpaShiny host-native Spatial Transcriptomics River worker")
    parser.add_argument("--once", action="store_true", help="Process at most one scheduler iteration.")
    parser.add_argument("--healthcheck", action="store_true", help="Validate imports and configuration without claiming jobs.")
    args = parser.parse_args(argv)
    dispatcher = build_dispatcher()
    if args.healthcheck:
        dispatcher.stop()
        print("host_river_worker=ready", flush=True)
        return 0
    try:
        if args.once:
            print(dispatcher.run_once(), flush=True)
            return 0
        dispatcher.run_forever()
        return 0
    finally:
        dispatcher.stop()


if __name__ == "__main__":
    raise SystemExit(main())
