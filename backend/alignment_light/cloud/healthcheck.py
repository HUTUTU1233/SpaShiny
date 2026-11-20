from __future__ import annotations

from typing import Any

from .compute_providers import ComputeProviderRegistry
from .config import SpaShinyCloudConfig, load_cloud_config
from .database import CloudDatabase
from .job_queue_repository import JobQueueRepository
from .lab_resource_monitor import LabResourceMonitor
from .models import ACTIVE_JOB_STATUSES, GPU_ACTIVE_STATUSES, JobStatus
from .runpod_api import RunPodAPIClient
from .storage_quota import StorageQuotaManager


class HealthChecker:
    def __init__(
        self,
        config: SpaShinyCloudConfig | None = None,
        database: CloudDatabase | None = None,
        runpod_api: RunPodAPIClient | None = None,
    ) -> None:
        self.config = config or load_cloud_config()
        self.database = database or CloudDatabase(config=self.config)
        self.runpod_api = runpod_api or RunPodAPIClient(self.config)

    def resource_status(self, *, include_admin: bool = False) -> dict[str, Any]:
        if self.config.is_lab_profile:
            return LabResourceMonitor(database=self.database, config=self.config).cached_snapshot()
        active = self.database.list_jobs(statuses=list(GPU_ACTIVE_STATUSES), limit=10000)
        active_all = self.database.list_jobs(statuses=list(ACTIVE_JOB_STATUSES), limit=10000)
        waiting = self.database.list_jobs(
            statuses=[JobStatus.QUEUED.value, JobStatus.QUEUED_CPU.value, JobStatus.QUEUED_GPU.value, JobStatus.WAITING_FOR_GPU.value],
            limit=10000,
        )
        failed = self.database.list_jobs(statuses=[JobStatus.FAILED.value, JobStatus.TIMED_OUT.value], limit=5)
        queue_status = JobQueueRepository(self.database, self.config).queue_status()
        workers = self._worker_summary()
        compute_providers = ComputeProviderRegistry(self.config).provider_status()
        r2_configured = bool(
            self.config.r2_account_id
            and self.config.r2_access_key_id
            and self.config.r2_secret_access_key
            and self.config.r2_endpoint_url
            and (self.config.r2_runtime_bucket or self.config.r2_bucket_name)
        )
        status: dict[str, Any] = {
            "gpu_state": "GPU Busy" if active else ("GPU Ready" if any(item.get("status") == "READY" for item in compute_providers.values()) else "GPU Offline"),
            "waiting_jobs": len(waiting),
            "active_jobs": len(active),
            "current_gpu_type": "Modal T4 / SaladCloud RTX 3090",
            "control_plane": {"status": "OK"},
            "local_cpu_worker": {
                "status": "READY" if workers["cpu_active"] else "NOT_RUNNING",
                "active_workers": workers["cpu_active"],
                "max_concurrency": int(self.config.max_cpu_concurrency),
            },
            "leaseweb_cpu": {
                "status": "READY" if workers["cpu_active"] else "NOT_RUNNING",
                "provider_mode": "local",
                "max_concurrency": int(self.config.max_cpu_concurrency),
            },
            "compute_providers": compute_providers,
            "modal_t4": compute_providers.get("modal_t4", {}),
            "salad_rtx3090": compute_providers.get("salad_rtx3090", {}),
            "tensordock_reserved": compute_providers.get("tensordock_reserved", {}),
            "job_queue": {
                "queued_jobs": int(queue_status["cpu_queue_length"]) + int(queue_status["gpu_queue_length"]),
                "running_jobs": len(active_all),
                "cpu_queue_length": int(queue_status["cpu_queue_length"]),
                "gpu_queue_length": int(queue_status["gpu_queue_length"]),
                "cpu_slots_used": int(queue_status["cpu_slots_used"]),
                "gpu_slots_used": int(queue_status["gpu_slots_used"]),
            },
            "r2_storage": {
                "status": "CONFIGURED" if r2_configured else "NOT_CONFIGURED",
                "backend": self.config.storage_backend,
            },
            "recent_errors": [
                {
                    "job_id": job.job_id,
                    "workflow": job.workflow_name or job.workflow,
                    "status": job.status,
                    "error_code": job.error_code,
                    "message": self._sanitize_error(job.error_message),
                }
                for job in failed
            ],
        }
        try:
            quota_status = StorageQuotaManager(database=self.database, config=self.config).status()
            status["object_storage"] = quota_status
            status["r2_storage"] = {**status["r2_storage"], **quota_status}
        except Exception as exc:
            status["object_storage_error"] = str(exc)
        if include_admin and self.config.runpod_pod_id and self.config.runpod_api_key:
            try:
                pod = self.runpod_api.get_pod(self.config.runpod_pod_id)
                status["pod"] = {
                    "id": pod.get("id"),
                    "desired_status": pod.get("desiredStatus"),
                    "gpu_count": pod.get("gpuCount"),
                    "cost_per_hr": pod.get("costPerHr"),
                    "runtime": pod.get("runtime"),
                }
            except Exception as exc:
                status["pod_error"] = str(exc)
        return status

    def _worker_summary(self) -> dict[str, int]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT worker_type, status, COUNT(*) AS count
                FROM worker_instances
                GROUP BY worker_type, status
                """
            ).fetchall()
        cpu_active = 0
        dispatcher_active = 0
        for row in rows:
            worker_type = str(row["worker_type"] or "")
            worker_status = str(row["status"] or "")
            count = int(row["count"] or 0)
            if worker_status != "ACTIVE":
                continue
            if worker_type == "cpu":
                cpu_active += count
            if worker_type == "dispatcher":
                dispatcher_active += count
        return {
            "cpu_active": cpu_active,
            "dispatcher_active": dispatcher_active,
        }

    @staticmethod
    def _sanitize_error(message: str | None) -> str:
        text = str(message or "").strip()
        if not text:
            return ""
        for marker in ("RUNPOD_API_KEY", "R2_SECRET_ACCESS_KEY", "CLOUDFLARE_TUNNEL_TOKEN"):
            text = text.replace(marker, "[redacted]")
        return text[:240]
