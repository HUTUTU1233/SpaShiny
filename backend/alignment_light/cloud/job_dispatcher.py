from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from .config import SpaShinyCloudConfig, load_cloud_config
from .database import CloudDatabase, utc_now
from .executors.base import ExecutorResult, JobExecutor
from .executors.local_cpu import LocalCPUExecutor
from .executors.mock_gpu import MockGPUExecutor
from .executor_registry import ExecutorRegistry
from .job_queue_repository import ClaimedJob, JobQueueRepository
from .models import JobRecord, JobStatus, ResourceType
from .result_publisher import ResultPublisher
from .runpod_lifecycle_manager import ResultStorageReservationError, RunPodLifecycleManager
from .runpod_provider import RunPodCapacityUnavailable, RunPodCreateError, RunPodReadyTimeout, RunPodTerminateError
from .worker_heartbeat import WorkerHeartbeatRepository
from .workflow_registry import ensure_workflow_dispatch_enabled


class _LabNoopRunPodLifecycle:
    result_quota = None

    def provision_for_job(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("RunPod provisioning is disabled in lab_server mode.")

    def wait_ready(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("RunPod readiness is disabled in lab_server mode.")

    def mark_busy(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def poll_instance(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def terminate_instance(self, *_args: Any, **_kwargs: Any) -> None:
        return None


@dataclass
class JobDispatcher:
    database: CloudDatabase | None = None
    config: SpaShinyCloudConfig | None = None
    queue: JobQueueRepository | None = None
    worker_id: str = "dispatcher"
    executors: dict[str, JobExecutor] = field(default_factory=dict)
    registry: ExecutorRegistry | None = None
    heartbeat: WorkerHeartbeatRepository | None = None
    runpod_lifecycle: RunPodLifecycleManager | None = None
    result_publisher: ResultPublisher | None = None
    enabled_resources: tuple[str, ...] = (ResourceType.CPU.value, ResourceType.GPU.value)
    cpu_queue_names: tuple[str, ...] | None = None
    gpu_queue_names: tuple[str, ...] | None = None
    worker_type: str = "dispatcher"
    _stopped: bool = False

    def __post_init__(self) -> None:
        if self.config is None:
            self.config = load_cloud_config()
        if self.database is None:
            self.database = CloudDatabase(config=self.config)
        if self.queue is None:
            self.queue = JobQueueRepository(self.database, self.config)
        if self.registry is None:
            registry_executors: dict[str, JobExecutor] = {}
            if self.executors:
                if ResourceType.CPU.value in self.executors:
                    registry_executors["local_cpu"] = self.executors[ResourceType.CPU.value]
                if ResourceType.GPU.value in self.executors:
                    registry_executors["mock_gpu"] = self.executors[ResourceType.GPU.value]
                registry_executors.update({key: value for key, value in self.executors.items() if key not in {ResourceType.CPU.value, ResourceType.GPU.value}})
            self.registry = ExecutorRegistry(self.config, registry_executors)
        if not self.executors:
            self.executors = {
                ResourceType.CPU.value: LocalCPUExecutor(config=self.config, database=self.database),
                ResourceType.GPU.value: MockGPUExecutor(),
            }
        if self.heartbeat is None:
            self.heartbeat = WorkerHeartbeatRepository(self.database, self.config)
        self.heartbeat.register(self.worker_id, worker_type=self.worker_type)
        if self.runpod_lifecycle is None:
            if self.config.is_lab_profile:
                self.runpod_lifecycle = _LabNoopRunPodLifecycle()
            else:
                self.runpod_lifecycle = RunPodLifecycleManager(database=self.database, config=self.config, queue=self.queue)
        if self.result_publisher is None:
            self.result_publisher = ResultPublisher(config=self.config)

    def stop(self) -> None:
        self._stopped = True
        if self.heartbeat is not None:
            self.heartbeat.stop(self.worker_id)

    def run_forever(self) -> None:
        assert self.config is not None
        while not self._stopped:
            self.run_once()
            time.sleep(int(self.config.job_dispatcher_interval_seconds))

    def run_once(self) -> dict[str, Any]:
        assert self.queue is not None
        assert self.heartbeat is not None
        self.heartbeat.heartbeat(self.worker_id)
        timed_out = self.queue.mark_timed_out_jobs()
        for job_id in timed_out:
            self._release_result_reservation(job_id, "RELEASED", "job timed out")
        recovered = self.queue.recover_expired_leases()
        cancelled = self._process_cancel_requested()
        polled = self._poll_owned_running_jobs()
        claimed: list[str] = []
        if ResourceType.CPU.value in self.enabled_resources:
            cpu_queues = self.cpu_queue_names if self.cpu_queue_names is not None else ("leaseweb_local_cpu",) if self.worker_type == "cpu" else None
            cpu = self.queue.claim_next_cpu_job(self.worker_id, queue_names=cpu_queues)
            if cpu is not None:
                claimed.append(cpu.job.job_id)
                self._execute_claim(cpu)
        if ResourceType.GPU.value in self.enabled_resources:
            gpu = self.queue.claim_next_gpu_job(self.worker_id, queue_names=self.gpu_queue_names)
            if gpu is not None:
                claimed.append(gpu.job.job_id)
                self._execute_gpu_claim(gpu)
        return {"claimed": claimed, "polled": polled, "timed_out": timed_out, "recovered": recovered, "cancelled": cancelled}

    def _execute_gpu_claim(self, claimed: ClaimedJob) -> None:
        assert self.queue is not None
        assert self.runpod_lifecycle is not None
        assert self.config is not None
        if self.config.is_lab_profile:
            self._execute_claim(claimed)
            return
        try:
            ensure_workflow_dispatch_enabled(claimed.job.workflow_name or claimed.job.workflow)
        except NotImplementedError as exc:
            message = str(exc)
            error_code = message.split(":", 1)[0] if ":" in message else "WORKFLOW_HANDLER_NOT_IMPLEMENTED"
            self._finish_claim(claimed, ExecutorResult(JobStatus.FAILED.value, message, error_code))
            return
        try:
            job = self.queue.update_claimed_job(
                claimed.job.job_id,
                claimed.worker_id,
                claimed.claim_token,
                JobStatus.PROVISIONING.value,
                started_at=utc_now(),
                current_step="Provisioning GPU",
            )
            instance = self.runpod_lifecycle.provision_for_job(job.job_id)
            self.queue.update_claimed_job(
                job.job_id,
                claimed.worker_id,
                claimed.claim_token,
                JobStatus.STARTING.value,
                current_step="Starting Pod",
                metadata_json=self._merge_metadata(self.database.get_job(job.job_id).metadata_json, {"runpod_instance_id": instance["instance_id"]}),
            )
            ready = self.runpod_lifecycle.wait_ready(str(instance["instance_id"]))
            running = self.queue.update_claimed_job(
                job.job_id,
                claimed.worker_id,
                claimed.claim_token,
                JobStatus.RUNNING.value,
                current_step="Pod ready",
            )
            self.runpod_lifecycle.mark_busy(str(ready["instance_id"]))
            self.queue.update_claimed_job(
                running.job_id,
                claimed.worker_id,
                claimed.claim_token,
                JobStatus.RUNNING.value,
                current_step="GPU worker running",
                metadata_json=self._merge_metadata(
                    running.metadata_json,
                    {
                        "compute_instance": {
                            "instance_id": str(ready["instance_id"]),
                            "provider_name": str(ready.get("provider_name") or ""),
                            "provider_pod_id": str(ready.get("provider_pod_id") or ""),
                            "contract": "signed_url_callback_v1",
                            "ssh": False,
                        }
                    },
                ),
            )
        except RunPodCapacityUnavailable as exc:
            self._finish_claim(claimed, ExecutorResult(JobStatus.FAILED.value, "RunPod capacity unavailable.", "CAPACITY_UNAVAILABLE"))
        except RunPodReadyTimeout as exc:
            self._finish_claim(claimed, ExecutorResult(JobStatus.TIMED_OUT.value, "RunPod pod readiness timed out.", "READY_TIMEOUT"))
        except ResultStorageReservationError as exc:
            self._finish_claim(claimed, ExecutorResult(JobStatus.FAILED.value, str(exc), "INSUFFICIENT_RESULT_STORAGE"))
        except (RunPodCreateError, RunPodTerminateError, Exception) as exc:
            self._finish_claim(claimed, ExecutorResult(JobStatus.FAILED.value, str(exc), "RUNPOD_LIFECYCLE_FAILED"))

    def _execute_claim(self, claimed: ClaimedJob) -> None:
        assert self.queue is not None
        assert self.registry is not None
        executor = self.registry.get_executor(claimed.job)
        try:
            downloading = self.queue.update_claimed_job(
                claimed.job.job_id,
                claimed.worker_id,
                claimed.claim_token,
                JobStatus.DOWNLOADING.value,
                current_step="Preparing input data",
            )
            started = executor.start(downloading)
        except Exception as exc:
            self._finish_claim(
                claimed,
                ExecutorResult(
                    JobStatus.FAILED.value,
                    f"{type(exc).__name__}: {exc}",
                    "EXECUTOR_START_FAILED",
                ),
            )
            return
        metadata_json = downloading.metadata_json
        if started.metadata:
            metadata_json = self._merge_metadata(downloading.metadata_json, {"executor": started.metadata})
        job = self.queue.update_claimed_job(
            claimed.job.job_id,
            claimed.worker_id,
            claimed.claim_token,
            started.status,
            started_at=utc_now(),
            current_step=started.message,
            metadata_json=metadata_json,
        )
        if started.status in {JobStatus.FAILED.value, JobStatus.CANCELLED.value, JobStatus.TIMED_OUT.value}:
            self._finish_claim(claimed, started)
            return
        polled = executor.poll(job)
        if polled.status == JobStatus.RUNNING.value:
            self.queue.renew_lease(job.job_id, claimed.worker_id)
            return
        if polled.status == JobStatus.SUCCEEDED.value:
            self._complete_successful_claim(claimed, job)
            return
        self._finish_claim(claimed, polled)

    def _poll_owned_running_jobs(self) -> list[str]:
        assert self.database is not None
        assert self.queue is not None
        assert self.registry is not None
        polled_job_ids: list[str] = []
        jobs = [
            job
            for job in self.database.list_jobs(statuses=[JobStatus.RUNNING.value], limit=10000)
            if job.worker_id == self.worker_id and job.claim_token
        ]
        for job in jobs:
            if job.resource_type == ResourceType.GPU.value and not self.config.is_lab_profile:
                if self.runpod_lifecycle is not None:
                    instance = self.database.get_runpod_instance_by_job(job.job_id, active_only=True)
                    if instance is not None:
                        self.runpod_lifecycle.poll_instance(str(instance["instance_id"]))
                self.queue.renew_lease(job.job_id, job.worker_id)
                polled_job_ids.append(job.job_id)
                continue
            executor = self.registry.get_executor(job)
            result = executor.poll(job)
            polled_job_ids.append(job.job_id)
            claimed = ClaimedJob(job=job, worker_id=job.worker_id, claim_token=job.claim_token, lease_id="")
            if result.status == JobStatus.RUNNING.value:
                self.queue.renew_lease(job.job_id, job.worker_id)
            elif result.status == JobStatus.SUCCEEDED.value:
                self._complete_successful_claim(claimed, job)
            else:
                self._finish_claim(claimed, result)
        return polled_job_ids

    def _complete_successful_claim(self, claimed: ClaimedJob, job: JobRecord) -> None:
        assert self.queue is not None
        assert self.registry is not None
        post = self.queue.update_claimed_job(job.job_id, claimed.worker_id, claimed.claim_token, JobStatus.POSTPROCESSING.value, current_step="Postprocessing")
        executor = self.registry.get_executor(post)
        collected = executor.collect_result(post)
        if collected.status != JobStatus.SUCCEEDED.value:
            self._finish_claim(claimed, collected)
            return
        verified = self.queue.update_claimed_job(job.job_id, claimed.worker_id, claimed.claim_token, JobStatus.VERIFYING.value, current_step="Verifying")
        packaged = self.queue.update_claimed_job(verified.job_id, claimed.worker_id, claimed.claim_token, JobStatus.PACKAGING.value, current_step="Packaging results")
        assert self.result_publisher is not None
        published = self.result_publisher.publish(packaged)
        self.queue.update_claimed_job(
            packaged.job_id,
            claimed.worker_id,
            claimed.claim_token,
            JobStatus.SUCCEEDED.value,
            finished_at=utc_now(),
            progress=100.0,
            current_step="Completed",
            metadata_json=self._merge_metadata(packaged.metadata_json, {"result_publication": published}),
            result_synced=True,
        )
        self._finish_attempt(job.job_id, JobStatus.SUCCEEDED.value)
        self.queue.release_lease(job.job_id, claimed.worker_id)

    def _finish_claim(self, claimed: ClaimedJob, result: ExecutorResult) -> None:
        assert self.queue is not None
        self.queue.update_claimed_job(
            claimed.job.job_id,
            claimed.worker_id,
            claimed.claim_token,
            result.status,
            finished_at=utc_now(),
            error_code=result.error_code,
            error_message=result.message,
            current_step=result.message,
        )
        self._finish_attempt(claimed.job.job_id, result.status, result.error_code, result.message)
        if result.status != JobStatus.SUCCEEDED.value:
            self._release_result_reservation(claimed.job.job_id, "RELEASED", result.error_code or result.status)
        self.queue.release_lease(claimed.job.job_id, claimed.worker_id)

    def _process_cancel_requested(self) -> list[str]:
        assert self.database is not None
        cancelled: list[str] = []
        jobs = self.database.list_jobs(statuses=[JobStatus.CANCEL_REQUESTED.value], limit=10000)
        for job in jobs:
            assert self.registry is not None
            self.registry.request_cancel(job)
            self.registry.terminate(job)
            instance = self.database.get_runpod_instance_by_job(job.job_id, active_only=True)
            if instance is not None and self.runpod_lifecycle is not None:
                self.runpod_lifecycle.terminate_instance(str(instance["instance_id"]), reason="job_cancel")
            self.database.update_job(job.job_id, status=JobStatus.CANCELLED.value, finished_at=utc_now())
            self._release_result_reservation(job.job_id, "RELEASED", "job cancelled")
            if job.worker_id:
                assert self.queue is not None
                self.queue.release_lease(job.job_id, job.worker_id)
            self._finish_attempt(job.job_id, JobStatus.CANCELLED.value)
            cancelled.append(job.job_id)
        return cancelled

    def _finish_attempt(self, job_id: str, status: str, error_code: str = "", error_message: str = "") -> None:
        assert self.database is not None
        with self.database.connect() as conn:
            conn.execute(
                """
                UPDATE job_attempts
                SET status=?, finished_at=?, error_code=?, error_message=?
                WHERE job_id=?
                AND finished_at IS NULL
                """,
                (status, utc_now(), error_code, error_message, job_id),
            )

    def _merge_metadata(self, metadata_json: str, values: dict[str, Any]) -> str:
        try:
            data = json.loads(metadata_json or "{}")
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}
        data.update(values)
        return json.dumps(data, ensure_ascii=False, sort_keys=True)

    def _release_result_reservation(self, job_id: str, status: str, error_message: object = "") -> None:
        try:
            if self.runpod_lifecycle is not None and self.runpod_lifecycle.result_quota is not None:
                self.runpod_lifecycle.result_quota.release_result_reservation_for_job(job_id, status=status, error_message=error_message)
        except Exception:
            return
