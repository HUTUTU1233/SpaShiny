from __future__ import annotations

import logging
from typing import Any, Callable

from .gpu_scheduler import GPUScheduler
from .job_manager import JobManager

LOGGER = logging.getLogger(__name__)


class TaskQueue:
    def __init__(self, jobs: JobManager | None = None, scheduler: GPUScheduler | None = None) -> None:
        self.jobs = jobs or JobManager()
        self.scheduler = scheduler or GPUScheduler()

    def submit_gpu_job(self, job_id: str, *, run_inline: bool = False) -> None:
        self.jobs.queue_job(job_id)
        if run_inline:
            self.run_gpu_job(job_id)
            return
        try:
            import redis
            from rq import Queue

            from .config import load_cloud_config

            cfg = load_cloud_config()
            if not cfg.redis_url:
                raise RuntimeError("SPASHINY_REDIS_URL is not configured.")
            connection = redis.from_url(cfg.redis_url)
            queue = Queue("gpu", connection=connection)
            queue.enqueue("cloud.task_queue.run_gpu_job_entrypoint", job_id)
        except Exception:
            LOGGER.info("RQ is unavailable; job %s remains queued for local SpaShiny workers.", job_id)

    def run_gpu_job(self, job_id: str) -> None:
        self.scheduler.submit_gpu_job(job_id)


def run_gpu_job_entrypoint(job_id: str) -> None:
    TaskQueue().run_gpu_job(job_id)
