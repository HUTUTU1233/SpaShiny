"""Minimal TEST-only process entrypoint for the existing SessionWatchdog."""

from __future__ import annotations

import logging
import os
import signal
import threading
from pathlib import Path

from .config import load_cloud_config
from .database import CloudDatabase
from .session_manager import SessionManager
from .session_watchdog import SessionWatchdog


LOG = logging.getLogger(__name__)
STOP = threading.Event()


def _stop(signum: int, _frame: object) -> None:
    LOG.info("session_watchdog_runner_stop_signal signal=%s", signum)
    STOP.set()


def main() -> int:
    logging.basicConfig(
        level=os.getenv("SPASHINY_WATCHDOG_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    config = load_cloud_config()
    database = CloudDatabase(config=config)
    sessions = SessionManager(database=database, config=config)
    watchdog = SessionWatchdog(session_manager=sessions, database=database)
    database_path = Path(database.path).resolve()
    identity = database_path.stat()
    interval = max(1, int(config.session_watchdog_interval_seconds))

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    LOG.info(
        "session_watchdog_runner_started pid=%s db_realpath=%s db_device_inode=%s:%s interval_seconds=%s",
        os.getpid(),
        database_path,
        identity.st_dev,
        identity.st_ino,
        interval,
    )
    while not STOP.is_set():
        cancelled = watchdog.run_once()
        LOG.info("session_watchdog_scan ended_analysis_count=%s", len(cancelled))
        STOP.wait(interval)
    LOG.info("session_watchdog_runner_stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
