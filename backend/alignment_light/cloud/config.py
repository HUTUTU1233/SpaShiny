from __future__ import annotations

import os
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_R2_ENV_FILE = ".env.r2.local"
_LEGACY_R2_BUCKET_NAME_WARNED = False
SPATIALMETA_GPU_WORKER_IMAGE = "spashiny-gpu-worker-spatialmeta:production"
SPATIALMETA_GPU_WORKER_REPOSITORY = "spashiny-gpu-worker-spatialmeta"


class CloudConfigError(RuntimeError):
    """Raised when required cloud deployment configuration is missing."""


def load_local_r2_env(env_path: Path | None = None) -> bool:
    path = env_path or (PROJECT_ROOT / LOCAL_R2_ENV_FILE)
    if not path.exists():
        return False
    try:
        from dotenv import load_dotenv
    except ImportError as exc:
        raise CloudConfigError("python-dotenv is required to load .env.r2.local.") from exc
    load_dotenv(dotenv_path=path, override=False)
    return True


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise CloudConfigError(f"{name} must be an integer, got {raw!r}.") from exc


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise CloudConfigError(f"{name} must be a number, got {raw!r}.") from exc


def _env_csv(name: str, default: str = "") -> tuple[str, ...]:
    raw = os.environ.get(name, default)
    return tuple(item.strip() for item in str(raw or "").split(",") if item.strip())


def _normalize_url_origin(value: str | None) -> str | None:
    raw = str(value or "").strip().rstrip("/")
    if not raw:
        return None
    parsed = urlsplit(raw)
    if not parsed.scheme or not parsed.netloc:
        raise CloudConfigError(f"Expected an absolute URL origin, got {raw!r}.")
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _origin_host(origin: str | None) -> str | None:
    if not origin:
        return None
    parsed = urlsplit(origin)
    return parsed.hostname.lower() if parsed.hostname else None


def _unique_ordered(items: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        value = str(item or "").strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return tuple(result)


def _split_image_tag_or_digest(image: str) -> tuple[str, str, str]:
    image = str(image or "").strip()
    if "@" in image:
        repository, digest = image.split("@", 1)
        return repository, "", digest
    last_slash = image.rfind("/")
    last_colon = image.rfind(":")
    if last_colon > last_slash:
        return image[:last_colon], image[last_colon + 1 :], ""
    return image, "", ""


def _image_has_registry_domain(repository: str) -> bool:
    first = str(repository or "").split("/", 1)[0].strip().lower()
    return bool(first and (first == "localhost" or "." in first or ":" in first))


def _image_repository_basename(repository: str) -> str:
    return str(repository or "").split("/")[-1].strip()


def _require_remote_spatialmeta_worker_image(image: str, env_name: str) -> None:
    value = str(image or "").strip()
    repository, tag, digest = _split_image_tag_or_digest(value)
    if (
        not value
        or value.lower() == "latest"
        or not _image_has_registry_domain(repository)
        or _image_repository_basename(repository) != SPATIALMETA_GPU_WORKER_REPOSITORY
        or (not digest and (not tag or tag.lower() == "latest"))
        or (digest and not digest.lower().startswith("sha256:"))
    ):
        raise CloudConfigError(
            f"{env_name} must be a full remote registry reference for "
            f"{SPATIALMETA_GPU_WORKER_REPOSITORY} with an explicit non-latest tag or sha256 digest. "
            f"Example: ghcr.io/<namespace>/{SPATIALMETA_GPU_WORKER_REPOSITORY}:<immutable-version>."
        )


def _env_path(name: str, default: str) -> Path:
    raw = os.environ.get(name, default)
    return Path(raw).expanduser()


def _warn_legacy_r2_bucket_name() -> None:
    global _LEGACY_R2_BUCKET_NAME_WARNED
    if _LEGACY_R2_BUCKET_NAME_WARNED:
        return
    warnings.warn(
        "R2_BUCKET_NAME is deprecated; use R2_RUNTIME_BUCKET for runtime objects and R2_ASSETS_BUCKET for example assets.",
        RuntimeWarning,
        stacklevel=3,
    )
    _LEGACY_R2_BUCKET_NAME_WARNED = True


@dataclass(frozen=True)
class SpaShinyCloudConfig:
    workspace: Path
    database_url: str | None
    redis_url: str | None
    remote_job_root: str
    runpod_api_key: str | None = field(repr=False)
    runpod_pod_id: str | None
    runpod_template_id: str | None
    runpod_network_volume_id: str | None
    runpod_api_endpoint: str
    ssh_username: str
    ssh_private_key: Path
    ssh_known_hosts: Path
    ssh_trust_on_first_use: bool
    gpu_idle_minutes: int
    gpu_job_timeout_hours: int
    max_gpu_jobs: int
    ssh_connect_timeout: int
    ssh_command_timeout: int
    status_poll_seconds: int
    runpod_connect_timeout: int
    runpod_read_timeout: int
    session_hmac_secret: str | None = field(default=None, repr=False)
    session_idle_timeout_seconds: int = 300
    session_heartbeat_interval_seconds: int = 30
    session_watchdog_interval_seconds: int = 60
    deployment_profile: str = ""
    deployment_mode: str = "web"
    lab_profile: bool = False
    lab_session_cookie_name: str = "spashiny_lab_session"
    anonymous_session_ttl_hours: int = 24
    completed_job_retention_hours: int = 168
    failed_job_retention_hours: int = 168
    session_storage_limit_gb: int = 50
    lab_data_root: Path = Path("/workspace/data")
    lab_result_root: Path = Path("/workspace/results")
    lab_jobs_root: Path = Path("/workspace/jobs")
    lab_logs_root: Path = Path("/workspace/logs")
    lab_sqlite_root: Path = Path("/workspace/sqlite")
    local_object_root: Path = Path("/workspace/data/sessions")
    lab_gpu_concurrency_per_device: int = 1
    gpu_required: bool = False
    allow_cpu_fallback: bool = True
    lab_allowed_gpu_name_tokens: tuple[str, ...] = ("RTX 4090", "NVIDIA GeForce RTX 4090")
    storage_backend: str = "local"
    r2_enabled: bool = False
    remote_provider_enabled: bool = False
    r2_account_id: str | None = None
    r2_access_key_id: str | None = field(default=None, repr=False)
    r2_secret_access_key: str | None = field(default=None, repr=False)
    r2_bucket_name: str | None = None
    r2_assets_bucket: str | None = None
    r2_runtime_bucket: str | None = None
    r2_endpoint_url: str | None = None
    r2_region: str = "auto"
    r2_apply_infrastructure: bool = False
    r2_run_integration_tests: bool = False
    r2_presigned_url_ttl_seconds: int = 900
    r2_multipart_part_size_bytes: int = 67108864
    r2_multipart_max_parallel_parts: int = 4
    r2_global_storage_limit_bytes: int = 10_000_000_000
    r2_storage_safety_reserve_bytes: int = 500_000_000
    r2_absolute_limit_bytes: int = 10_000_000_000
    r2_safe_limit_bytes: int = 9_000_000_000
    r2_runtime_limit_bytes: int = 7_000_000_000
    r2_max_upload_bytes: int = 5_000_000_000
    r2_default_result_reserve_bytes: int = 1_000_000_000
    r2_managed_buckets: tuple[str, ...] = ()
    r2_upload_reservation_ttl_seconds: int = 3600
    r2_multipart_reservation_ttl_seconds: int = 7200
    r2_job_result_reservation_ttl_seconds: int = 7200
    r2_reconcile_interval_seconds: int = 3600
    r2_result_size_estimate_factor: float = 1.25
    r2_result_min_reservation_bytes: int = 1_073_741_824
    max_upload_file_bytes: int = 5368709120
    max_session_upload_bytes: int = 12884901888
    max_session_upload_files: int = 20
    max_concurrent_upload_sessions: int = 2
    max_cpu_concurrency: int = 2
    max_gpu_concurrency: int = 1
    max_gpu_queue_length: int = 10
    max_cpu_queue_length: int = 20
    max_active_jobs_per_session: int = 1
    max_gpu_job_seconds: int = 7200
    max_cpu_job_seconds: int = 7200
    cpu_job_memory_limit_gb: int = 16
    daily_gpu_budget_usd: float = 15.0
    max_gpu_retries: int = 0
    max_cpu_retries: int = 0
    job_dispatcher_interval_seconds: int = 2
    resource_lease_seconds: int = 120
    resource_lease_heartbeat_seconds: int = 30
    temp_root: Path | None = None
    local_process_termination_grace_seconds: int = 10
    cleanup_worker_interval_seconds: int = 60
    cleanup_max_retries: int = 5
    cleanup_retry_base_seconds: int = 30
    cancel_grace_seconds: int = 15
    worker_lost_timeout_seconds: int = 180
    orphan_workspace_min_age_seconds: int = 3600
    runpod_provider_mode: str = "fake"
    runpod_api_base_url: str | None = None
    runpod_image: str = "spashiny-gpu:fake"
    runpod_cpu_image: str | None = None
    runpod_gpu_image: str | None = None
    runpod_image_digest: str | None = None
    runpod_cpu_template_id: str | None = None
    runpod_gpu_template_id: str | None = None
    runpod_gpu_type_candidates: tuple[str, ...] = ()
    runpod_gpu_count: int = 1
    runpod_cloud_type: str = ""
    runpod_location_candidates: tuple[str, ...] = ()
    runpod_container_disk_gb: int = 30
    runpod_volume_disk_gb: int = 0
    runpod_pod_ready_timeout_seconds: int = 600
    runpod_pod_terminate_timeout_seconds: int = 180
    runpod_status_poll_seconds: int = 5
    runpod_max_pod_age_seconds: int = 7200
    runpod_api_max_retries: int = 3
    runpod_api_retry_base_seconds: int = 2
    runpod_gpu_hourly_cost_usd: float = 0.0
    runpod_name_prefix: str = "spashiny"
    run_real_runpod_tests: bool = False
    compute_provider_mode: str = "fake"
    gpu_provider_order: tuple[str, ...] = ("modal_t4", "salad_rtx3090", "tensordock_reserved")
    spashiny_gpu_worker_image: str = SPATIALMETA_GPU_WORKER_IMAGE
    spashiny_gpu_spatialmeta_image: str = SPATIALMETA_GPU_WORKER_IMAGE
    spashiny_gpu_scslat_image: str = ""
    worker_signed_url_ttl_seconds: int = 600
    worker_callback_token_ttl_seconds: int = 7200
    worker_checkpoint_ttl_seconds: int = 3600
    example_cache_enabled: bool = True
    example_cache_ttl_seconds: int = 86400
    example_precompute_enabled: bool = True
    show_example_asset_debug: bool = False
    model_registry_version: str = "production-candidate-v1"
    modal_enabled: bool = False
    modal_api_token: str | None = field(default=None, repr=False)
    modal_proxy_token_id: str | None = field(default=None, repr=False)
    modal_proxy_token_secret: str | None = field(default=None, repr=False)
    modal_t4_image: str = "modal.Image"
    modal_t4_template_id: str = ""
    modal_submit_url: str | None = None
    modal_health_url: str | None = None
    modal_cancel_url: str | None = None
    modal_logs_url: str | None = None
    modal_launch_url: str | None = None
    modal_status_url: str | None = None
    modal_terminate_url: str | None = None
    modal_hourly_cost_usd: float = 0.0
    salad_enabled: bool = False
    salad_api_key: str | None = field(default=None, repr=False)
    salad_api_base_url: str = "https://api.salad.com/api/public"
    salad_organization_name: str = ""
    salad_project_name: str = ""
    salad_priority: str = "batch"
    salad_container_group_prefix: str = "spashiny"
    salad_cpu: int = 4
    salad_memory_mb: int = 32768
    salad_storage_gb: int = 50
    salad_rtx3090_image: str = SPATIALMETA_GPU_WORKER_IMAGE
    salad_container_group: str = ""
    salad_logs_url: str | None = None
    salad_launch_url: str | None = None
    salad_status_url: str | None = None
    salad_terminate_url: str | None = None
    salad_hourly_cost_usd: float = 0.0
    tensordock_enabled: bool = False
    tensordock_api_token: str | None = field(default=None, repr=False)
    tensordock_image: str = SPATIALMETA_GPU_WORKER_IMAGE
    tensordock_launch_url: str | None = None
    tensordock_status_url: str | None = None
    tensordock_terminate_url: str | None = None
    tensordock_hourly_cost_usd: float = 0.0
    public_base_url: str | None = None
    public_origin: str | None = None
    cors_allowed_origins: tuple[str, ...] = ()
    trusted_hosts: tuple[str, ...] = ()
    cloudflare_tunnel_configured: bool = False
    cloudflare_tunnel_origin_service: str = "http://spashiny-control:8000"

    @property
    def is_lab_profile(self) -> bool:
        profile = str(self.deployment_profile or "").strip().lower()
        mode = str(self.deployment_mode or "").strip().lower()
        return bool(self.lab_profile or profile == "lab_server" or mode == "lab")

    def gpu_worker_image_for_profile(self, runtime_profile: str | None) -> str:
        profile = str(runtime_profile or "spatialmeta").strip().lower() or "spatialmeta"
        if profile == "spatialmeta":
            return self.spashiny_gpu_spatialmeta_image or self.spashiny_gpu_worker_image
        if profile == "scslat":
            if not self.spashiny_gpu_scslat_image:
                raise CloudConfigError("SPASHINY_GPU_SCSLAT_IMAGE is not configured for runtime_profile=scslat.")
            return self.spashiny_gpu_scslat_image
        raise CloudConfigError(f"Unsupported GPU runtime profile: {profile}")

    def require_runpod_api_key(self) -> str:
        if not self.runpod_api_key:
            raise CloudConfigError("RUNPOD_API_KEY is not configured.")
        return self.runpod_api_key

    def require_pod_id(self) -> str:
        if not self.runpod_pod_id:
            raise CloudConfigError("RUNPOD_POD_ID is not configured.")
        return self.runpod_pod_id

    def require_ssh_key(self) -> Path:
        if not self.ssh_private_key.exists():
            raise CloudConfigError(f"RUNPOD_SSH_PRIVATE_KEY does not exist: {self.ssh_private_key}")
        return self.ssh_private_key

    def require_session_hmac_secret(self) -> str:
        if not self.session_hmac_secret:
            raise CloudConfigError("SPASHINY_SESSION_HMAC_SECRET is not configured.")
        return self.session_hmac_secret

    def require_r2_config(self) -> None:
        self.require_r2_runtime_config()

    def runtime_bucket_name(self) -> str | None:
        return self.r2_runtime_bucket or self.r2_bucket_name

    def require_r2_runtime_config(self) -> str:
        missing = []
        for name, value in (
            ("R2_ACCESS_KEY_ID", self.r2_access_key_id),
            ("R2_SECRET_ACCESS_KEY", self.r2_secret_access_key),
            ("R2_RUNTIME_BUCKET", self.runtime_bucket_name()),
            ("R2_ENDPOINT_URL", self.r2_endpoint_url),
        ):
            if not value:
                missing.append(name)
        if missing:
            raise CloudConfigError("Missing required R2 configuration: " + ", ".join(missing))
        return str(self.runtime_bucket_name())

    def require_r2_assets_config(self) -> str:
        missing = []
        for name, value in (
            ("R2_ACCESS_KEY_ID", self.r2_access_key_id),
            ("R2_SECRET_ACCESS_KEY", self.r2_secret_access_key),
            ("R2_ASSETS_BUCKET", self.r2_assets_bucket),
            ("R2_ENDPOINT_URL", self.r2_endpoint_url),
        ):
            if not value:
                missing.append(name)
        if missing:
            raise CloudConfigError("Missing required R2 assets configuration: " + ", ".join(missing))
        return str(self.r2_assets_bucket)

    def require_runpod_provider_config(self) -> None:
        mode = (self.runpod_provider_mode or "fake").lower()
        if mode not in {"fake", "real", "lab", "local"}:
            raise CloudConfigError("RUNPOD_PROVIDER_MODE must be one of 'fake', 'real', 'lab', or 'local'.")
        if mode in {"fake", "lab", "local"}:
            return
        missing = []
        if not self.runpod_api_key:
            missing.append("RUNPOD_API_KEY")
        if not (self.runpod_template_id or self.runpod_cpu_template_id or self.runpod_gpu_template_id):
            missing.append("RUNPOD_TEMPLATE_ID or RUNPOD_CPU_TEMPLATE_ID/RUNPOD_GPU_TEMPLATE_ID")
        if not (self.runpod_image or self.runpod_cpu_image or self.runpod_gpu_image):
            missing.append("RUNPOD_IMAGE or RUNPOD_CPU_IMAGE/RUNPOD_GPU_IMAGE")
        if missing:
            raise CloudConfigError("Missing required RunPod provider configuration: " + ", ".join(missing))

    def require_compute_provider_config(self) -> None:
        if self.salad_enabled:
            _require_remote_spatialmeta_worker_image(self.salad_rtx3090_image, "SALAD_RTX3090_IMAGE")
        if self.tensordock_enabled:
            _require_remote_spatialmeta_worker_image(self.tensordock_image, "TENSORDOCK_IMAGE")
        mode = (self.compute_provider_mode or "fake").lower()
        if mode not in {"fake", "real", "lab", "local"}:
            raise CloudConfigError("SPASHINY_COMPUTE_PROVIDER_MODE must be one of 'fake', 'real', 'lab', or 'local'.")
        if mode in {"fake", "lab", "local"}:
            return
        providers = {item.strip() for item in self.gpu_provider_order if item.strip()}
        missing: list[str] = []
        if "modal_t4" in providers and self.modal_enabled and not (
            self.modal_submit_url
            and self.modal_status_url
            and self.modal_cancel_url
            and self.modal_proxy_token_id
            and self.modal_proxy_token_secret
        ):
            missing.append("MODAL_SUBMIT_URL/MODAL_STATUS_URL/MODAL_CANCEL_URL and MODAL_PROXY_TOKEN_ID/MODAL_PROXY_TOKEN_SECRET")
        if "salad_rtx3090" in providers and self.salad_enabled and not (
            self.salad_api_key
            and self.salad_organization_name
            and self.salad_project_name
            and self.salad_rtx3090_image
        ):
            missing.append("SALAD_API_KEY/SALAD_ORGANIZATION_NAME/SALAD_PROJECT_NAME and SALAD_RTX3090_IMAGE")
        if "tensordock_reserved" in providers and self.tensordock_enabled and not self.tensordock_launch_url:
            missing.append("TENSORDOCK_LAUNCH_URL")
        if not any(
            (
                "modal_t4" in providers and self.modal_enabled,
                "salad_rtx3090" in providers and self.salad_enabled,
                "tensordock_reserved" in providers and self.tensordock_enabled,
            )
        ):
            missing.append("NO_GPU_PROVIDER_AVAILABLE")
        if missing:
            raise CloudConfigError("Missing required compute provider configuration: " + ", ".join(missing))


def load_cloud_config(
    *,
    require_runpod: bool = False,
    require_ssh_key: bool = False,
    require_session_secret: bool = False,
    require_storage: bool = False,
) -> SpaShinyCloudConfig:
    deployment_profile = os.environ.get("SPASHINY_DEPLOYMENT_PROFILE", "").strip().lower()
    if deployment_profile != "lab_server":
        load_local_r2_env()
    workspace = _env_path("SPASHINY_WORKSPACE", "/opt/spashiny/workspace")
    deployment_mode_default = "lab" if deployment_profile == "lab_server" else "web"
    deployment_mode = os.environ.get("SPASHINY_DEPLOYMENT_MODE", deployment_mode_default).strip().lower() or deployment_mode_default
    lab_profile = deployment_profile == "lab_server" or deployment_mode == "lab" or _env_bool("SPASHINY_LAB_PROFILE", False)
    public_base_url = _normalize_url_origin(os.environ.get("PUBLIC_BASE_URL"))
    public_origin = _normalize_url_origin(os.environ.get("SPASHINY_PUBLIC_ORIGIN")) or public_base_url
    cors_allowed_origins = tuple(
        origin
        for origin in (_normalize_url_origin(item) for item in _env_csv("SPASHINY_CORS_ALLOWED_ORIGINS"))
        if origin
    )
    if not cors_allowed_origins and public_origin:
        cors_allowed_origins = (public_origin,)
    default_trusted_hosts = (_origin_host(public_origin),) if public_origin else ()
    trusted_hosts = _unique_ordered(
        tuple(host.lower() for host in _env_csv("SPASHINY_TRUSTED_HOSTS"))
        or tuple(host for host in default_trusted_hosts if host)
    )
    r2_account_id = os.environ.get("R2_ACCOUNT_ID")
    r2_endpoint_url = os.environ.get("R2_ENDPOINT_URL")
    if not r2_endpoint_url and r2_account_id:
        r2_endpoint_url = f"https://{r2_account_id}.r2.cloudflarestorage.com"
    r2_assets_bucket = os.environ.get("R2_ASSETS_BUCKET")
    r2_legacy_bucket_name = os.environ.get("R2_BUCKET_NAME")
    r2_runtime_bucket = os.environ.get("R2_RUNTIME_BUCKET")
    if r2_legacy_bucket_name and not r2_runtime_bucket:
        _warn_legacy_r2_bucket_name()
        r2_runtime_bucket = r2_legacy_bucket_name
    gpu_worker_image = (
        os.environ.get("SPASHINY_GPU_WORKER_IMAGE")
        or os.environ.get("RUNPOD_GPU_IMAGE")
        or SPATIALMETA_GPU_WORKER_IMAGE
    ).strip() or SPATIALMETA_GPU_WORKER_IMAGE
    gpu_spatialmeta_image = (
        os.environ.get("SPASHINY_GPU_SPATIALMETA_IMAGE")
        or gpu_worker_image
    ).strip() or gpu_worker_image
    storage_backend = (
        os.environ.get("SPASHINY_STORAGE_BACKEND")
        or os.environ.get("STORAGE_BACKEND")
        or ("local" if lab_profile else "local")
    ).strip().lower() or "local"
    lab_data_root = _env_path("SPASHINY_LOCAL_DATA_ROOT", "/workspace/data")
    local_object_root = _env_path("SPASHINY_LOCAL_OBJECT_ROOT", str(lab_data_root / "sessions"))
    r2_enabled = _env_bool("SPASHINY_R2_ENABLED", _env_bool("R2_ENABLED", storage_backend == "r2"))
    remote_provider_enabled = _env_bool(
        "SPASHINY_REMOTE_PROVIDER_ENABLED",
        _env_bool("REMOTE_PROVIDER_ENABLED", not lab_profile),
    )
    cfg = SpaShinyCloudConfig(
        workspace=workspace,
        database_url=os.environ.get("SPASHINY_DATABASE_URL"),
        redis_url=os.environ.get("SPASHINY_REDIS_URL"),
        remote_job_root=os.environ.get("SPASHINY_REMOTE_JOB_ROOT", "/workspace/spashiny/jobs").rstrip("/"),
        runpod_api_key=os.environ.get("RUNPOD_API_KEY"),
        runpod_pod_id=os.environ.get("RUNPOD_POD_ID"),
        runpod_template_id=os.environ.get("RUNPOD_TEMPLATE_ID"),
        runpod_network_volume_id=os.environ.get("RUNPOD_NETWORK_VOLUME_ID"),
        runpod_api_endpoint=os.environ.get("RUNPOD_API_ENDPOINT", "https://api.runpod.io/graphql"),
        ssh_username=os.environ.get("RUNPOD_SSH_USERNAME", "root"),
        ssh_private_key=_env_path("RUNPOD_SSH_PRIVATE_KEY", "/opt/spashiny/secrets/runpod_ed25519"),
        ssh_known_hosts=_env_path("RUNPOD_SSH_KNOWN_HOSTS", "/opt/spashiny/secrets/known_hosts"),
        ssh_trust_on_first_use=os.environ.get("SPASHINY_SSH_TRUST_ON_FIRST_USE", "0") == "1",
        gpu_idle_minutes=_env_int("SPASHINY_GPU_IDLE_MINUTES", 20),
        gpu_job_timeout_hours=_env_int("SPASHINY_GPU_JOB_TIMEOUT_HOURS", 12),
        max_gpu_jobs=_env_int("SPASHINY_MAX_GPU_JOBS", 1),
        ssh_connect_timeout=_env_int("SPASHINY_SSH_CONNECT_TIMEOUT", 30),
        ssh_command_timeout=_env_int("SPASHINY_SSH_COMMAND_TIMEOUT", 120),
        status_poll_seconds=_env_int("SPASHINY_STATUS_POLL_SECONDS", 3),
        runpod_connect_timeout=_env_int("RUNPOD_CONNECT_TIMEOUT", 10),
        runpod_read_timeout=_env_int("RUNPOD_READ_TIMEOUT", 60),
        session_hmac_secret=os.environ.get("SPASHINY_SESSION_HMAC_SECRET"),
        session_idle_timeout_seconds=_env_int("SESSION_IDLE_TIMEOUT_SECONDS", 300),
        session_heartbeat_interval_seconds=_env_int("SESSION_HEARTBEAT_INTERVAL_SECONDS", 30),
        session_watchdog_interval_seconds=_env_int("SESSION_WATCHDOG_INTERVAL_SECONDS", 60),
        deployment_profile=deployment_profile,
        deployment_mode=deployment_mode,
        lab_profile=lab_profile,
        lab_session_cookie_name=os.environ.get("SPASHINY_LAB_SESSION_COOKIE_NAME", "spashiny_lab_session").strip()
        or "spashiny_lab_session",
        anonymous_session_ttl_hours=_env_int("SPASHINY_ANONYMOUS_SESSION_TTL_HOURS", 24),
        completed_job_retention_hours=_env_int("SPASHINY_COMPLETED_JOB_RETENTION_HOURS", 168),
        failed_job_retention_hours=_env_int("SPASHINY_FAILED_JOB_RETENTION_HOURS", 168),
        session_storage_limit_gb=_env_int("SPASHINY_SESSION_STORAGE_LIMIT_GB", 50),
        lab_data_root=lab_data_root,
        lab_result_root=_env_path("SPASHINY_LOCAL_RESULT_ROOT", "/workspace/results"),
        lab_jobs_root=_env_path("SPASHINY_LOCAL_JOBS_ROOT", "/workspace/jobs"),
        lab_logs_root=_env_path("SPASHINY_LOCAL_LOGS_ROOT", "/workspace/logs"),
        lab_sqlite_root=_env_path("SPASHINY_LOCAL_SQLITE_ROOT", "/workspace/sqlite"),
        local_object_root=local_object_root,
        lab_gpu_concurrency_per_device=_env_int("SPASHINY_GPU_CONCURRENCY_PER_DEVICE", 1),
        gpu_required=_env_bool("SPASHINY_GPU_REQUIRED", False),
        allow_cpu_fallback=_env_bool("SPASHINY_ALLOW_CPU_FALLBACK", True),
        lab_allowed_gpu_name_tokens=_env_csv("SPASHINY_LAB_ALLOWED_GPU_NAME_TOKENS", "RTX 4090,NVIDIA GeForce RTX 4090"),
        storage_backend=storage_backend,
        r2_enabled=r2_enabled,
        remote_provider_enabled=remote_provider_enabled,
        r2_account_id=r2_account_id,
        r2_access_key_id=os.environ.get("R2_ACCESS_KEY_ID"),
        r2_secret_access_key=os.environ.get("R2_SECRET_ACCESS_KEY"),
        r2_bucket_name=r2_legacy_bucket_name,
        r2_assets_bucket=r2_assets_bucket,
        r2_runtime_bucket=r2_runtime_bucket,
        r2_endpoint_url=r2_endpoint_url,
        r2_region=os.environ.get("R2_REGION", "auto"),
        r2_apply_infrastructure=_env_bool("R2_APPLY_INFRASTRUCTURE", False),
        r2_run_integration_tests=_env_bool("R2_RUN_INTEGRATION_TESTS", False),
        r2_presigned_url_ttl_seconds=_env_int("R2_PRESIGNED_URL_TTL_SECONDS", 900),
        r2_multipart_part_size_bytes=_env_int("R2_MULTIPART_PART_SIZE_BYTES", 67108864),
        r2_multipart_max_parallel_parts=_env_int("R2_MULTIPART_MAX_PARALLEL_PARTS", 4),
        r2_global_storage_limit_bytes=_env_int("R2_GLOBAL_STORAGE_LIMIT_BYTES", 10_000_000_000),
        r2_storage_safety_reserve_bytes=_env_int("R2_STORAGE_SAFETY_RESERVE_BYTES", 500_000_000),
        r2_absolute_limit_bytes=_env_int("R2_ABSOLUTE_LIMIT_BYTES", 10_000_000_000),
        r2_safe_limit_bytes=_env_int("R2_SAFE_LIMIT_BYTES", 9_000_000_000),
        r2_runtime_limit_bytes=_env_int("R2_RUNTIME_LIMIT_BYTES", 7_000_000_000),
        r2_max_upload_bytes=_env_int("R2_MAX_UPLOAD_BYTES", 5_000_000_000),
        r2_default_result_reserve_bytes=_env_int("R2_DEFAULT_RESULT_RESERVE_BYTES", 1_000_000_000),
        r2_managed_buckets=_env_csv("R2_MANAGED_BUCKETS"),
        r2_upload_reservation_ttl_seconds=_env_int("R2_UPLOAD_RESERVATION_TTL_SECONDS", 3600),
        r2_multipart_reservation_ttl_seconds=_env_int("R2_MULTIPART_RESERVATION_TTL_SECONDS", 7200),
        r2_job_result_reservation_ttl_seconds=_env_int("R2_JOB_RESULT_RESERVATION_TTL_SECONDS", 7200),
        r2_reconcile_interval_seconds=_env_int("R2_RECONCILE_INTERVAL_SECONDS", 3600),
        r2_result_size_estimate_factor=_env_float("R2_RESULT_SIZE_ESTIMATE_FACTOR", 1.25),
        r2_result_min_reservation_bytes=_env_int("R2_RESULT_MIN_RESERVATION_BYTES", 1_073_741_824),
        max_upload_file_bytes=_env_int("MAX_UPLOAD_FILE_BYTES", 5368709120),
        max_session_upload_bytes=_env_int("MAX_SESSION_UPLOAD_BYTES", 12884901888),
        max_session_upload_files=_env_int("MAX_SESSION_UPLOAD_FILES", 20),
        max_concurrent_upload_sessions=_env_int("MAX_CONCURRENT_UPLOAD_SESSIONS", 2),
        max_cpu_concurrency=_env_int("SPASHINY_CPU_WORKER_CONCURRENCY", _env_int("MAX_CPU_CONCURRENCY", 2)),
        max_gpu_concurrency=_env_int("MAX_GPU_CONCURRENCY", 1),
        max_gpu_queue_length=_env_int("MAX_GPU_QUEUE_LENGTH", 10),
        max_cpu_queue_length=_env_int("MAX_CPU_QUEUE_LENGTH", 20),
        max_active_jobs_per_session=_env_int("MAX_ACTIVE_JOBS_PER_SESSION", 1),
        max_gpu_job_seconds=_env_int("MAX_GPU_JOB_SECONDS", 7200),
        max_cpu_job_seconds=_env_int("SPASHINY_CPU_JOB_TIMEOUT_SECONDS", _env_int("MAX_CPU_JOB_SECONDS", 7200)),
        cpu_job_memory_limit_gb=_env_int("SPASHINY_CPU_JOB_MEMORY_LIMIT_GB", 16),
        daily_gpu_budget_usd=float(os.environ.get("DAILY_GPU_BUDGET_USD", "15") or "15"),
        max_gpu_retries=_env_int("MAX_GPU_RETRIES", 0),
        max_cpu_retries=_env_int("MAX_CPU_RETRIES", 0),
        job_dispatcher_interval_seconds=_env_int("JOB_DISPATCHER_INTERVAL_SECONDS", 2),
        resource_lease_seconds=_env_int("RESOURCE_LEASE_SECONDS", 120),
        resource_lease_heartbeat_seconds=_env_int("RESOURCE_LEASE_HEARTBEAT_SECONDS", 30),
        temp_root=_env_path("SPASHINY_TEMP_ROOT", str(workspace / "temp")),
        local_process_termination_grace_seconds=_env_int("LOCAL_PROCESS_TERMINATION_GRACE_SECONDS", 10),
        cleanup_worker_interval_seconds=_env_int("CLEANUP_WORKER_INTERVAL_SECONDS", 60),
        cleanup_max_retries=_env_int("CLEANUP_MAX_RETRIES", 5),
        cleanup_retry_base_seconds=_env_int("CLEANUP_RETRY_BASE_SECONDS", 30),
        cancel_grace_seconds=_env_int("CANCEL_GRACE_SECONDS", 15),
        worker_lost_timeout_seconds=_env_int("WORKER_LOST_TIMEOUT_SECONDS", 180),
        orphan_workspace_min_age_seconds=_env_int("ORPHAN_WORKSPACE_MIN_AGE_SECONDS", 3600),
        runpod_provider_mode=os.environ.get("RUNPOD_PROVIDER_MODE", "lab" if lab_profile else "fake").strip().lower() or ("lab" if lab_profile else "fake"),
        runpod_api_base_url=os.environ.get("RUNPOD_API_BASE_URL"),
        runpod_image=os.environ.get("RUNPOD_IMAGE", "spashiny-gpu:fake").strip() or "spashiny-gpu:fake",
        runpod_cpu_image=os.environ.get("RUNPOD_CPU_IMAGE") or None,
        runpod_gpu_image=os.environ.get("RUNPOD_GPU_IMAGE") or None,
        runpod_image_digest=os.environ.get("RUNPOD_IMAGE_DIGEST") or None,
        runpod_cpu_template_id=os.environ.get("RUNPOD_CPU_TEMPLATE_ID") or None,
        runpod_gpu_template_id=os.environ.get("RUNPOD_GPU_TEMPLATE_ID") or None,
        runpod_gpu_type_candidates=_env_csv("RUNPOD_GPU_TYPE_CANDIDATES"),
        runpod_gpu_count=_env_int("RUNPOD_GPU_COUNT", 1),
        runpod_cloud_type=os.environ.get("RUNPOD_CLOUD_TYPE", "").strip(),
        runpod_location_candidates=_env_csv("RUNPOD_LOCATION_CANDIDATES"),
        runpod_container_disk_gb=_env_int("RUNPOD_CONTAINER_DISK_GB", 30),
        runpod_volume_disk_gb=_env_int("RUNPOD_VOLUME_DISK_GB", 0),
        runpod_pod_ready_timeout_seconds=_env_int("RUNPOD_POD_READY_TIMEOUT_SECONDS", 600),
        runpod_pod_terminate_timeout_seconds=_env_int("RUNPOD_POD_TERMINATE_TIMEOUT_SECONDS", 180),
        runpod_status_poll_seconds=_env_int("RUNPOD_STATUS_POLL_SECONDS", 5),
        runpod_max_pod_age_seconds=_env_int("RUNPOD_MAX_POD_AGE_SECONDS", 7200),
        runpod_api_max_retries=_env_int("RUNPOD_API_MAX_RETRIES", 3),
        runpod_api_retry_base_seconds=_env_int("RUNPOD_API_RETRY_BASE_SECONDS", 2),
        runpod_gpu_hourly_cost_usd=_env_float("RUNPOD_GPU_HOURLY_COST_USD", 0.0),
        runpod_name_prefix=os.environ.get("RUNPOD_NAME_PREFIX", "spashiny").strip() or "spashiny",
        run_real_runpod_tests=os.environ.get("RUN_REAL_RUNPOD_TESTS", "0") == "1",
        compute_provider_mode=os.environ.get(
            "SPASHINY_COMPUTE_PROVIDER_MODE",
            "lab" if lab_profile else os.environ.get("RUNPOD_PROVIDER_MODE", "fake"),
        ).strip().lower() or ("lab" if lab_profile else "fake"),
        gpu_provider_order=_env_csv("SPASHINY_GPU_PROVIDER_ORDER", "modal_t4,salad_rtx3090,tensordock_reserved"),
        spashiny_gpu_worker_image=gpu_worker_image,
        spashiny_gpu_spatialmeta_image=gpu_spatialmeta_image,
        spashiny_gpu_scslat_image=os.environ.get("SPASHINY_GPU_SCSLAT_IMAGE", "").strip(),
        worker_signed_url_ttl_seconds=_env_int("SPASHINY_WORKER_SIGNED_URL_TTL_SECONDS", 600),
        worker_callback_token_ttl_seconds=_env_int("SPASHINY_WORKER_CALLBACK_TOKEN_TTL_SECONDS", 7200),
        worker_checkpoint_ttl_seconds=_env_int("SPASHINY_WORKER_CHECKPOINT_TTL_SECONDS", 3600),
        example_cache_enabled=_env_bool("SPASHINY_EXAMPLE_CACHE_ENABLED", True),
        example_cache_ttl_seconds=_env_int("SPASHINY_EXAMPLE_CACHE_TTL_SECONDS", 86400),
        example_precompute_enabled=_env_bool("SPASHINY_EXAMPLE_PRECOMPUTE_ENABLED", True),
        show_example_asset_debug=_env_bool("SPASHINY_SHOW_EXAMPLE_ASSET_DEBUG", False),
        model_registry_version=os.environ.get("SPASHINY_MODEL_REGISTRY_VERSION", "production-candidate-v1").strip() or "production-candidate-v1",
        modal_enabled=_env_bool("MODAL_ENABLED", False),
        modal_api_token=os.environ.get("MODAL_API_TOKEN"),
        modal_proxy_token_id=os.environ.get("MODAL_PROXY_TOKEN_ID") or os.environ.get("MODAL_KEY"),
        modal_proxy_token_secret=os.environ.get("MODAL_PROXY_TOKEN_SECRET") or os.environ.get("MODAL_SECRET"),
        modal_t4_image=os.environ.get("MODAL_T4_IMAGE", "modal.Image").strip() or "modal.Image",
        modal_t4_template_id=os.environ.get("MODAL_T4_TEMPLATE_ID", "").strip(),
        modal_submit_url=os.environ.get("MODAL_SUBMIT_URL") or os.environ.get("MODAL_LAUNCH_URL") or None,
        modal_health_url=os.environ.get("MODAL_HEALTH_URL") or None,
        modal_cancel_url=os.environ.get("MODAL_CANCEL_URL") or os.environ.get("MODAL_TERMINATE_URL") or None,
        modal_logs_url=os.environ.get("MODAL_LOGS_URL") or None,
        modal_launch_url=os.environ.get("MODAL_LAUNCH_URL") or None,
        modal_status_url=os.environ.get("MODAL_STATUS_URL") or None,
        modal_terminate_url=os.environ.get("MODAL_TERMINATE_URL") or None,
        modal_hourly_cost_usd=_env_float("MODAL_T4_HOURLY_COST_USD", 0.0),
        salad_enabled=_env_bool("SALAD_ENABLED", False),
        salad_api_key=os.environ.get("SALAD_API_KEY"),
        salad_api_base_url=os.environ.get("SALAD_API_BASE_URL", "https://api.salad.com/api/public").strip().rstrip("/")
        or "https://api.salad.com/api/public",
        salad_organization_name=os.environ.get("SALAD_ORGANIZATION_NAME", "").strip(),
        salad_project_name=os.environ.get("SALAD_PROJECT_NAME", "").strip(),
        salad_priority=os.environ.get("SALAD_PRIORITY", "batch").strip().lower() or "batch",
        salad_container_group_prefix=os.environ.get("SALAD_CONTAINER_GROUP_PREFIX", "spashiny").strip() or "spashiny",
        salad_cpu=_env_int("SALAD_CPU", 4),
        salad_memory_mb=_env_int("SALAD_MEMORY_MB", 32768),
        salad_storage_gb=_env_int("SALAD_STORAGE_GB", 50),
        salad_rtx3090_image=os.environ.get("SALAD_RTX3090_IMAGE", gpu_spatialmeta_image).strip() or gpu_spatialmeta_image,
        salad_container_group=os.environ.get("SALAD_CONTAINER_GROUP", "").strip(),
        salad_logs_url=os.environ.get("SALAD_LOGS_URL") or None,
        salad_launch_url=os.environ.get("SALAD_LAUNCH_URL") or None,
        salad_status_url=os.environ.get("SALAD_STATUS_URL") or None,
        salad_terminate_url=os.environ.get("SALAD_TERMINATE_URL") or None,
        salad_hourly_cost_usd=_env_float("SALAD_RTX3090_HOURLY_COST_USD", 0.0),
        tensordock_enabled=_env_bool("TENSORDOCK_ENABLED", False),
        tensordock_api_token=os.environ.get("TENSORDOCK_API_TOKEN"),
        tensordock_image=os.environ.get("TENSORDOCK_IMAGE", gpu_spatialmeta_image).strip() or gpu_spatialmeta_image,
        tensordock_launch_url=os.environ.get("TENSORDOCK_LAUNCH_URL") or None,
        tensordock_status_url=os.environ.get("TENSORDOCK_STATUS_URL") or None,
        tensordock_terminate_url=os.environ.get("TENSORDOCK_TERMINATE_URL") or None,
        tensordock_hourly_cost_usd=_env_float("TENSORDOCK_HOURLY_COST_USD", 0.0),
        public_base_url=public_base_url,
        public_origin=public_origin,
        cors_allowed_origins=cors_allowed_origins,
        trusted_hosts=trusted_hosts,
        cloudflare_tunnel_configured=bool(os.environ.get("CLOUDFLARE_TUNNEL_TOKEN"))
        or _env_bool("CLOUDFLARE_TUNNEL_CONFIGURED", False),
        cloudflare_tunnel_origin_service=os.environ.get(
            "CLOUDFLARE_TUNNEL_ORIGIN_SERVICE",
            "http://spashiny-control:8000",
        ).strip() or "http://spashiny-control:8000",
    )
    if cfg.storage_backend not in {"local", "r2"}:
        raise CloudConfigError("STORAGE_BACKEND must be either 'local' or 'r2'.")
    if cfg.is_lab_profile:
        if cfg.storage_backend != "local":
            raise CloudConfigError("Lab deployment requires SPASHINY_STORAGE_BACKEND=local.")
        if cfg.r2_enabled:
            raise CloudConfigError("Lab deployment requires SPASHINY_R2_ENABLED=0.")
        if cfg.remote_provider_enabled:
            raise CloudConfigError("Lab deployment requires SPASHINY_REMOTE_PROVIDER_ENABLED=0.")
        if cfg.cloudflare_tunnel_configured:
            raise CloudConfigError("Lab deployment must not enable Cloudflare Tunnel.")
        if cfg.modal_enabled or cfg.salad_enabled or cfg.tensordock_enabled or cfg.compute_provider_mode not in {"lab", "local", "fake"}:
            raise CloudConfigError("Lab deployment must not enable public GPU providers.")
    if require_runpod:
        cfg.require_runpod_api_key()
        cfg.require_pod_id()
    if require_ssh_key:
        cfg.require_ssh_key()
    if require_session_secret:
        cfg.require_session_hmac_secret()
    if require_storage:
        cfg.require_r2_config()
    cfg.require_runpod_provider_config()
    cfg.require_compute_provider_config()
    return cfg
