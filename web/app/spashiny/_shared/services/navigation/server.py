# Extracted from /app/app/ST-SM.py. Feature: navigation; ordered phases preserve original initialization.
from spashiny._shared import runtime_globals as _spashiny_globals
from spashiny.features.alignment_auto import ui as _ui_alignment_auto
from spashiny.features.alignment_manual import ui as _ui_alignment_manual
from spashiny.features.connection import ui as _ui_connection
from spashiny.features.downstream import ui as _ui_downstream
from spashiny.features.enrichment import ui as _ui_enrichment
from spashiny.features.help import ui as _ui_help
from spashiny.features.home import ui as _ui_home
from spashiny.features.integration_multi_sm import ui as _ui_integration_multi_sm
from spashiny.features.integration_multi_st_sm import ui as _ui_integration_multi_st_sm
from spashiny.features.integration_single import ui as _ui_integration_single
from spashiny.features.jobs import ui as _ui_jobs
from spashiny.features.knn import ui as _ui_knn
from spashiny.features.metabolite_annotation import ui as _ui_metabolite_annotation
from spashiny.features.one_stop import ui as _ui_one_stop
from spashiny.features.r_enrichment import ui as _ui_r_enrichment
from spashiny.features.resources import ui as _ui_resources
from spashiny.features.results import ui as _ui_results
from spashiny.features.river import ui as _ui_river
from spashiny.features.sm_import import ui as _ui_sm_import
from spashiny.features.sm_qc import ui as _ui_sm_qc
from spashiny.features.sm_tic_roi import ui as _ui_sm_tic_roi
from spashiny.features.spatialmeta_dash import ui as _ui_spatialmeta_dash
from spashiny.features.st_import import ui as _ui_st_import
from spashiny.features.st_qc import ui as _ui_st_qc
from spashiny.features.uploads import ui as _ui_uploads


def _install_0(_spashiny_ctx):

    @_spashiny_ctx.output
    @_spashiny_ctx.render.ui
    def cloud_job_center():
        try:
            from cloud.job_manager import JobManager
            from cloud.job_queue_repository import JobQueueRepository
            from cloud.models import QUEUED_RESOURCE_JOB_STATUSES
            from cloud.workflow_registry import workflow_specs

            session_id = _spashiny_ctx._cloud_session_id()
            analysis_session_id = _spashiny_ctx._cloud_analysis_session_id()
            if not session_id or not analysis_session_id:
                return _spashiny_ctx.ui.tags.div(
                    _spashiny_ctx.ui.tags.p(
                        "Anonymous cloud session is initializing. Jobs are hidden until the session is ready.",
                        class_="cloud-muted",
                    )
                )
            jobs = JobManager().list_jobs_for_session(
                session_id, analysis_session_id=analysis_session_id, limit=20
            )
            queue_repository = JobQueueRepository()
            queue_status = queue_repository.queue_status(session_id)
            try:
                _spashiny_ctx.reactive.invalidate_later(
                    max(3, min(5, int(queue_repository.config.queue_status_refresh_seconds)))
                )
            except Exception:
                pass
            workflow_rows = []
            for spec in workflow_specs():
                workflow_rows.append(
                    _spashiny_ctx.ui.tags.div(
                        _spashiny_ctx.ui.tags.strong(spec["label"]),
                        _spashiny_ctx.ui.tags.div(
                            f"{spec['workflow_name']} | Page: {spec.get('analysis_page') or 'Auto'} | {spec.get('compute_class') or spec['resource_type']} | {', '.join(spec.get('provider_chain') or [spec.get('preferred_backend') or 'auto'])} | "
                            + ("Enabled" if spec["enabled"] else "Not yet enabled"),
                            class_="cloud-muted",
                        ),
                        class_="cloud-row",
                    )
                )
            queue_summary = _spashiny_ctx.ui.tags.div(
                _spashiny_ctx.ui.tags.div(
                    _spashiny_ctx.ui.tags.div("CPU", class_="cloud-metric-title"),
                    _spashiny_ctx.ui.tags.div(
                        f"{queue_status['cpu_slots_used']} / {queue_status['cpu_concurrency']} active | {queue_status['cpu_queue_length']} queued",
                        class_="cloud-metric-value",
                    ),
                    class_="cloud-metric",
                ),
                _spashiny_ctx.ui.tags.div(
                    _spashiny_ctx.ui.tags.div("GPU", class_="cloud-metric-title"),
                    _spashiny_ctx.ui.tags.div(
                        f"{queue_status['gpu_slots_used']} / {queue_status['gpu_concurrency']} active | {queue_status['gpu_queue_length']} queued",
                        class_="cloud-metric-value",
                    ),
                    class_="cloud-metric",
                ),
                _spashiny_ctx.ui.tags.div(
                    _spashiny_ctx.ui.tags.div("System", class_="cloud-metric-title"),
                    _spashiny_ctx.ui.tags.div(
                        str(queue_status.get("system_state") or "NORMAL"),
                        class_="cloud-metric-value",
                    ),
                    class_="cloud-metric",
                ),
                class_="cloud-grid",
            )
            if not jobs:
                return _spashiny_ctx.ui.tags.div(
                    queue_summary,
                    _spashiny_ctx.ui.tags.h4("Workflows"),
                    _spashiny_ctx.ui.tags.div(*workflow_rows, class_="cloud-list"),
                    _spashiny_ctx.ui.tags.p("No cloud jobs yet.", class_="cloud-muted"),
                )
            rows = []
            for job in jobs:
                position = None
                if job.status in QUEUED_RESOURCE_JOB_STATUSES:
                    position = queue_repository.get_job_queue_position(
                        job_id=job.job_id,
                        owner_session_id=session_id,
                        analysis_session_id=analysis_session_id,
                    )
                queue_text = f"Queue: {job.queue_name} | Progress: {job.progress:.1f}% | Step: {job.current_step or 'Waiting'}"
                if position is not None:
                    queue_text = f"Waiting for {('GPU' if position['resource_type'] == 'gpu' else 'CPU')} | Queue position: {position['queue_position']} | Jobs ahead: {position['jobs_ahead']}"
                rows.append(
                    _spashiny_ctx.ui.tags.div(
                        _spashiny_ctx.ui.tags.strong(f"{job.workflow} | {job.status}"),
                        _spashiny_ctx.ui.tags.div(queue_text, class_="cloud-muted"),
                        _spashiny_ctx.ui.tags.div(
                            "Compute Resource: Automatic Selection", class_="cloud-muted"
                        ),
                        _spashiny_ctx.ui.tags.div(f"Job ID: {job.job_id}", class_="cloud-muted"),
                        (
                            _spashiny_globals._job_error_ui(job, title="Job failed")
                            if str(job.status or "").lower()
                            in {"failed", "cancelled", "timed_out", "not_enabled", "queue_full"}
                            else _spashiny_ctx.ui.div()
                        ),
                        _spashiny_ctx.ui.tags.button(
                            "Cancel",
                            type="button",
                            class_="cloud-cancel-job",
                            **{"data-job-id": job.job_id},
                        ),
                        class_="cloud-row",
                    )
                )
            return _spashiny_ctx.ui.tags.div(
                queue_summary,
                _spashiny_ctx.ui.tags.h4("Workflows"),
                _spashiny_ctx.ui.tags.div(*workflow_rows, class_="cloud-list"),
                _spashiny_ctx.ui.tags.h4("Jobs"),
                _spashiny_ctx.ui.tags.div(*rows, class_="cloud-list"),
            )
        except Exception as e:
            return _spashiny_ctx.ui.tags.div(
                _spashiny_ctx.ui.tags.p(
                    f"Job Center is not initialized yet: {e}", class_="cloud-muted"
                )
            )

    _spashiny_ctx.cloud_job_center = cloud_job_center

    @_spashiny_ctx.output
    @_spashiny_ctx.render.ui
    def cloud_my_results():
        try:
            from cloud.job_manager import JobManager
            from cloud.models import JobStatus

            session_id = _spashiny_ctx._cloud_session_id()
            analysis_session_id = _spashiny_ctx._cloud_analysis_session_id()
            if not session_id or not analysis_session_id:
                return _spashiny_ctx.ui.tags.div(
                    _spashiny_ctx.ui.tags.p(
                        "Anonymous cloud session is initializing. Results are hidden until the session is ready.",
                        class_="cloud-muted",
                    )
                )
            jobs = JobManager().list_results_for_session(
                session_id, analysis_session_id=analysis_session_id, limit=20
            )
            if not jobs:
                return _spashiny_ctx.ui.tags.div(
                    _spashiny_ctx.ui.tags.p("No synchronized results yet.", class_="cloud-muted")
                )
            rows = []
            for job in jobs:
                download_links = _spashiny_ctx._cloud_result_download_links(session_id, job)
                rows.append(
                    _spashiny_ctx.ui.tags.div(
                        _spashiny_ctx.ui.tags.strong(job.workflow),
                        _spashiny_ctx.ui.tags.div(f"Job ID: {job.job_id}", class_="cloud-muted"),
                        _spashiny_ctx.ui.tags.div(
                            (
                                "Results synchronized and ready for controlled download."
                                if job.result_synced
                                else "Result sync pending."
                            ),
                            class_="cloud-muted",
                        ),
                        (
                            _spashiny_ctx.ui.tags.div(
                                *download_links, class_="cloud-result-downloads"
                            )
                            if download_links
                            else _spashiny_ctx.ui.tags.div(
                                "No downloadable artifacts were found in result_manifest.json.",
                                class_="cloud-muted",
                            )
                        ),
                        class_="cloud-row",
                    )
                )
            return _spashiny_ctx.ui.tags.div(*rows, class_="cloud-list")
        except Exception as e:
            return _spashiny_ctx.ui.tags.div(
                _spashiny_ctx.ui.tags.p(
                    f"Results are not initialized yet: {e}", class_="cloud-muted"
                )
            )

    _spashiny_ctx.cloud_my_results = cloud_my_results

    @_spashiny_ctx.output
    @_spashiny_ctx.render.ui
    def cloud_resource_status():
        try:
            from cloud.healthcheck import HealthChecker

            status = HealthChecker().resource_status(include_admin=False)
            try:
                _spashiny_ctx.reactive.invalidate_later(5)
            except Exception:
                pass
            if status.get("profile") == "lab":
                cpu = status.get("cpu") or {}
                memory = status.get("memory") or {}
                jobs = status.get("jobs") or {}
                gpus = status.get("gpus") or {}
                load_values = cpu.get("load_average") or [
                    cpu.get("load_average_1m"),
                    cpu.get("load_average_5m"),
                    cpu.get("load_average_15m"),
                ]
                load_text = " / ".join(
                    ("UNKNOWN" if item is None else str(item) for item in load_values[:3])
                )
                gpu_cards = []
                for gpu_key in ("gpu-0", "gpu-1"):
                    gpu = gpus.get(gpu_key) or {}
                    vram_used = gpu.get("vram_used_mb")
                    vram_total = gpu.get("vram_total_mb")
                    vram_text = "UNKNOWN"
                    if vram_used is not None and vram_total is not None:
                        vram_text = f"{vram_used} / {vram_total} MB"
                    power = gpu.get("power_watts")
                    power_text = "UNKNOWN" if power is None else f"{power} W"
                    temp = gpu.get("temperature_c")
                    temp_text = "UNKNOWN" if temp is None else f"{temp} C"
                    gpu_cards.append(
                        _spashiny_ctx.ui.tags.div(
                            _spashiny_ctx.ui.tags.h4(gpu.get("label") or gpu_key),
                            _spashiny_ctx.ui.tags.div(
                                _spashiny_ctx.ui.tags.div(
                                    _spashiny_ctx.ui.tags.div(
                                        "Health", class_="cloud-metric-title"
                                    ),
                                    _spashiny_ctx.ui.tags.div(
                                        str(gpu.get("health", "UNKNOWN")),
                                        class_="cloud-metric-value",
                                    ),
                                    class_="cloud-metric",
                                ),
                                _spashiny_ctx.ui.tags.div(
                                    _spashiny_ctx.ui.tags.div(
                                        "VRAM Used / Total", class_="cloud-metric-title"
                                    ),
                                    _spashiny_ctx.ui.tags.div(
                                        vram_text, class_="cloud-metric-value"
                                    ),
                                    class_="cloud-metric",
                                ),
                                _spashiny_ctx.ui.tags.div(
                                    _spashiny_ctx.ui.tags.div(
                                        "GPU Utilization", class_="cloud-metric-title"
                                    ),
                                    _spashiny_ctx.ui.tags.div(
                                        str(gpu.get("utilization_percent", "UNKNOWN")),
                                        class_="cloud-metric-value",
                                    ),
                                    class_="cloud-metric",
                                ),
                                _spashiny_ctx.ui.tags.div(
                                    _spashiny_ctx.ui.tags.div(
                                        "Temperature", class_="cloud-metric-title"
                                    ),
                                    _spashiny_ctx.ui.tags.div(
                                        temp_text, class_="cloud-metric-value"
                                    ),
                                    class_="cloud-metric",
                                ),
                                _spashiny_ctx.ui.tags.div(
                                    _spashiny_ctx.ui.tags.div("Power", class_="cloud-metric-title"),
                                    _spashiny_ctx.ui.tags.div(
                                        power_text, class_="cloud-metric-value"
                                    ),
                                    class_="cloud-metric",
                                ),
                                _spashiny_ctx.ui.tags.div(
                                    _spashiny_ctx.ui.tags.div("Queue", class_="cloud-metric-title"),
                                    _spashiny_ctx.ui.tags.div(
                                        str(
                                            gpu.get("queue_length")
                                            if gpu.get("queue_length") is not None
                                            else "UNKNOWN"
                                        ),
                                        class_="cloud-metric-value",
                                    ),
                                    class_="cloud-metric",
                                ),
                                _spashiny_ctx.ui.tags.div(
                                    _spashiny_ctx.ui.tags.div("Lease", class_="cloud-metric-title"),
                                    _spashiny_ctx.ui.tags.div(
                                        str(gpu.get("lease_status", "IDLE")),
                                        class_="cloud-metric-value",
                                    ),
                                    class_="cloud-metric",
                                ),
                                class_="cloud-grid",
                            ),
                            _spashiny_ctx.ui.tags.p(
                                str(gpu.get("name") or "UNKNOWN"), class_="cloud-muted"
                            ),
                            class_="cloud-row",
                        )
                    )
                return _spashiny_ctx.ui.tags.div(
                    _spashiny_ctx.ui.tags.h3("Lab Resources"),
                    _spashiny_ctx.ui.tags.div(
                        _spashiny_ctx.ui.tags.div(
                            _spashiny_ctx.ui.tags.div("CPU Model", class_="cloud-metric-title"),
                            _spashiny_ctx.ui.tags.div(
                                str(cpu.get("model", "UNKNOWN")), class_="cloud-metric-value"
                            ),
                            class_="cloud-metric",
                        ),
                        _spashiny_ctx.ui.tags.div(
                            _spashiny_ctx.ui.tags.div("Logical Cores", class_="cloud-metric-title"),
                            _spashiny_ctx.ui.tags.div(
                                str(cpu.get("logical_cores", "UNKNOWN")),
                                class_="cloud-metric-value",
                            ),
                            class_="cloud-metric",
                        ),
                        _spashiny_ctx.ui.tags.div(
                            _spashiny_ctx.ui.tags.div("CPU Usage", class_="cloud-metric-title"),
                            _spashiny_ctx.ui.tags.div(
                                str(cpu.get("total_usage_percent", "UNKNOWN")),
                                class_="cloud-metric-value",
                            ),
                            class_="cloud-metric",
                        ),
                        _spashiny_ctx.ui.tags.div(
                            _spashiny_ctx.ui.tags.div(
                                "Load Avg 1/5/15", class_="cloud-metric-title"
                            ),
                            _spashiny_ctx.ui.tags.div(load_text, class_="cloud-metric-value"),
                            class_="cloud-metric",
                        ),
                        _spashiny_ctx.ui.tags.div(
                            _spashiny_ctx.ui.tags.div("RAM Total GB", class_="cloud-metric-title"),
                            _spashiny_ctx.ui.tags.div(
                                str(memory.get("total_gb", "UNKNOWN")), class_="cloud-metric-value"
                            ),
                            class_="cloud-metric",
                        ),
                        _spashiny_ctx.ui.tags.div(
                            _spashiny_ctx.ui.tags.div("RAM Used GB", class_="cloud-metric-title"),
                            _spashiny_ctx.ui.tags.div(
                                str(memory.get("used_gb", "UNKNOWN")), class_="cloud-metric-value"
                            ),
                            class_="cloud-metric",
                        ),
                        _spashiny_ctx.ui.tags.div(
                            _spashiny_ctx.ui.tags.div(
                                "RAM Available GB", class_="cloud-metric-title"
                            ),
                            _spashiny_ctx.ui.tags.div(
                                str(memory.get("available_gb", "UNKNOWN")),
                                class_="cloud-metric-value",
                            ),
                            class_="cloud-metric",
                        ),
                        _spashiny_ctx.ui.tags.div(
                            _spashiny_ctx.ui.tags.div(
                                "Running CPU Jobs", class_="cloud-metric-title"
                            ),
                            _spashiny_ctx.ui.tags.div(
                                str(jobs.get("running_cpu_jobs", jobs.get("cpu_active_jobs", 0))),
                                class_="cloud-metric-value",
                            ),
                            class_="cloud-metric",
                        ),
                        _spashiny_ctx.ui.tags.div(
                            _spashiny_ctx.ui.tags.div(
                                "Queued CPU Jobs", class_="cloud-metric-title"
                            ),
                            _spashiny_ctx.ui.tags.div(
                                str(
                                    jobs.get("queued_cpu_jobs", jobs.get("cpu_queue_length"))
                                    if jobs.get("queued_cpu_jobs", jobs.get("cpu_queue_length"))
                                    is not None
                                    else "UNKNOWN"
                                ),
                                class_="cloud-metric-value",
                            ),
                            class_="cloud-metric",
                        ),
                        class_="cloud-grid",
                    ),
                    _spashiny_ctx.ui.tags.h4("GPU 1 / GPU 2"),
                    _spashiny_ctx.ui.tags.div(*gpu_cards, class_="cloud-list"),
                    _spashiny_ctx.ui.tags.p(
                        "Anonymous laboratory session only. Other sessions are redacted.",
                        class_="cloud-muted",
                    ),
                )
            storage = status.get("r2_storage") or status.get("object_storage") or {}
            storage_status = storage.get("status", "Unknown")
            control_plane = status.get("control_plane") or {}
            local_cpu = status.get("local_cpu_worker") or {}
            modal_t4 = status.get("modal_t4") or {}
            salad_rtx3090 = status.get("salad_rtx3090") or {}
            tensordock_reserved = status.get("tensordock_reserved") or {}
            job_queue = status.get("job_queue") or {}
            recent_errors = status.get("recent_errors") or []
            storage_card = _spashiny_ctx.ui.tags.div(
                _spashiny_ctx.ui.tags.h4("R2 Storage"),
                _spashiny_ctx.ui.tags.div(
                    _spashiny_ctx.ui.tags.div(
                        _spashiny_ctx.ui.tags.div("Status", class_="cloud-metric-title"),
                        _spashiny_ctx.ui.tags.div(str(storage_status), class_="cloud-metric-value"),
                        class_="cloud-metric",
                    ),
                    _spashiny_ctx.ui.tags.div(
                        _spashiny_ctx.ui.tags.div("Used", class_="cloud-metric-title"),
                        _spashiny_ctx.ui.tags.div(
                            _spashiny_ctx._format_bytes(storage.get("physical_usage_bytes", 0)),
                            class_="cloud-metric-value",
                        ),
                        class_="cloud-metric",
                    ),
                    _spashiny_ctx.ui.tags.div(
                        _spashiny_ctx.ui.tags.div("Reserved", class_="cloud-metric-title"),
                        _spashiny_ctx.ui.tags.div(
                            _spashiny_ctx._format_bytes(storage.get("reserved_bytes", 0)),
                            class_="cloud-metric-value",
                        ),
                        class_="cloud-metric",
                    ),
                    _spashiny_ctx.ui.tags.div(
                        _spashiny_ctx.ui.tags.div("Safety Reserve", class_="cloud-metric-title"),
                        _spashiny_ctx.ui.tags.div(
                            _spashiny_ctx._format_bytes(storage.get("safety_reserve_bytes", 0)),
                            class_="cloud-metric-value",
                        ),
                        class_="cloud-metric",
                    ),
                    _spashiny_ctx.ui.tags.div(
                        _spashiny_ctx.ui.tags.div("User Available", class_="cloud-metric-title"),
                        _spashiny_ctx.ui.tags.div(
                            _spashiny_ctx._format_bytes(storage.get("available_bytes", 0)),
                            class_="cloud-metric-value",
                        ),
                        class_="cloud-metric",
                    ),
                    _spashiny_ctx.ui.tags.div(
                        _spashiny_ctx.ui.tags.div("Global Limit", class_="cloud-metric-title"),
                        _spashiny_ctx.ui.tags.div(
                            _spashiny_ctx._format_bytes(storage.get("global_limit_bytes", 0)),
                            class_="cloud-metric-value",
                        ),
                        class_="cloud-metric",
                    ),
                    class_="cloud-grid",
                ),
                _spashiny_ctx.ui.tags.p(
                    f"Usage: {storage.get('usage_percent', 0)}%. Status text is provided for accessibility and does not rely on color alone.",
                    class_="cloud-muted",
                ),
            )
            error_rows = []
            for item in recent_errors[:5]:
                error_info = _spashiny_globals._analysis_error_info(
                    item.get("error_code") or "ERROR",
                    item.get("message") or item.get("error_message") or "No details available.",
                    item.get("error_type") or "",
                    item.get("traceback") or "",
                    job_id=item.get("job_id") or "",
                    workflow=item.get("workflow") or "",
                    current_step=item.get("current_step") or "",
                )
                error_rows.append(
                    _spashiny_ctx.ui.tags.div(
                        _spashiny_ctx.ui.tags.strong(
                            f"{item.get('workflow') or item.get('job_id') or 'Job'} | {item.get('status') or 'ERROR'}"
                        ),
                        _spashiny_ctx.ui.tags.div(
                            f"{error_info['label']}: {error_info['message']} ({error_info['code'] or 'ERROR'})",
                            class_="cloud-muted",
                        ),
                        class_="cloud-row",
                    )
                )
            return _spashiny_ctx.ui.tags.div(
                _spashiny_ctx.ui.tags.div(
                    _spashiny_ctx.ui.tags.div(
                        _spashiny_ctx.ui.tags.div(
                            "Leaseweb Control Plane", class_="cloud-metric-title"
                        ),
                        _spashiny_ctx.ui.tags.div(
                            str(control_plane.get("status", "UNKNOWN")), class_="cloud-metric-value"
                        ),
                        class_="cloud-metric",
                    ),
                    _spashiny_ctx.ui.tags.div(
                        _spashiny_ctx.ui.tags.div("Local CPU Worker", class_="cloud-metric-title"),
                        _spashiny_ctx.ui.tags.div(
                            str(local_cpu.get("status", "UNKNOWN")), class_="cloud-metric-value"
                        ),
                        class_="cloud-metric",
                    ),
                    _spashiny_ctx.ui.tags.div(
                        _spashiny_ctx.ui.tags.div("Modal T4", class_="cloud-metric-title"),
                        _spashiny_ctx.ui.tags.div(
                            str(modal_t4.get("status", "UNKNOWN")), class_="cloud-metric-value"
                        ),
                        class_="cloud-metric",
                    ),
                    _spashiny_ctx.ui.tags.div(
                        _spashiny_ctx.ui.tags.div(
                            "SaladCloud RTX 3090", class_="cloud-metric-title"
                        ),
                        _spashiny_ctx.ui.tags.div(
                            str(salad_rtx3090.get("status", "UNKNOWN")), class_="cloud-metric-value"
                        ),
                        class_="cloud-metric",
                    ),
                    _spashiny_ctx.ui.tags.div(
                        _spashiny_ctx.ui.tags.div(
                            "TensorDock Interface", class_="cloud-metric-title"
                        ),
                        _spashiny_ctx.ui.tags.div(
                            str(tensordock_reserved.get("status", "UNKNOWN")),
                            class_="cloud-metric-value",
                        ),
                        class_="cloud-metric",
                    ),
                    _spashiny_ctx.ui.tags.div(
                        _spashiny_ctx.ui.tags.div(
                            "Current Running Jobs", class_="cloud-metric-title"
                        ),
                        _spashiny_ctx.ui.tags.div(
                            str(job_queue.get("running_jobs", status.get("active_jobs", 0))),
                            class_="cloud-metric-value",
                        ),
                        class_="cloud-metric",
                    ),
                    _spashiny_ctx.ui.tags.div(
                        _spashiny_ctx.ui.tags.div("Queue Length", class_="cloud-metric-title"),
                        _spashiny_ctx.ui.tags.div(
                            str(job_queue.get("queued_jobs", status.get("waiting_jobs", 0))),
                            class_="cloud-metric-value",
                        ),
                        class_="cloud-metric",
                    ),
                    class_="cloud-grid",
                ),
                storage_card,
                _spashiny_ctx.ui.tags.h4("Recent Errors"),
                (
                    _spashiny_ctx.ui.tags.div(*error_rows, class_="cloud-list")
                    if error_rows
                    else _spashiny_ctx.ui.tags.p("No recent errors.", class_="cloud-muted")
                ),
                _spashiny_ctx.ui.tags.p(
                    "Connection details and secrets are hidden from ordinary users.",
                    class_="cloud-muted",
                ),
            )
        except Exception as e:
            return _spashiny_ctx.ui.tags.div(
                _spashiny_ctx.ui.tags.p(
                    f"Resource status is not initialized yet: {e}", class_="cloud-muted"
                )
            )

    _spashiny_ctx.cloud_resource_status = cloud_resource_status

    def log(msg: str):
        msg = _spashiny_globals.sanitize_log_message(msg)
        now = _spashiny_ctx.time.strftime("[%H:%M:%S] ")
        new = _spashiny_ctx.log_text.get() + now + str(msg) + "\n"
        _spashiny_ctx.log_text.set(new)
        _spashiny_globals.safe_console_print(now + str(msg), flush=True)

    _spashiny_ctx.log = log

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.show_home)
    def _on_show_home():
        _spashiny_ctx.current_module.set("home")

    _spashiny_ctx._on_show_home = _on_show_home

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.show_ssh_module_menu)
    def _on_show_ssh_module_menu():
        if _spashiny_globals.SPASHINY_WEB_PLATFORM:
            _spashiny_ctx.current_module.set("Cloud Resources")
            return
        _spashiny_ctx.current_module.set("SSH Module")

    _spashiny_ctx._on_show_ssh_module_menu = _on_show_ssh_module_menu

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.show_cloud_files)
    def _on_show_cloud_files():
        _spashiny_ctx.current_module.set("Cloud Files")

    _spashiny_ctx._on_show_cloud_files = _on_show_cloud_files

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.show_cloud_jobs)
    def _on_show_cloud_jobs():
        _spashiny_ctx.current_module.set("Cloud Jobs")

    _spashiny_ctx._on_show_cloud_jobs = _on_show_cloud_jobs

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.show_cloud_results)
    def _on_show_cloud_results():
        _spashiny_ctx.current_module.set("Cloud Results")

    _spashiny_ctx._on_show_cloud_results = _on_show_cloud_results

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.show_cloud_resources)
    def _on_show_cloud_resources():
        _spashiny_ctx.current_module.set("Cloud Resources")

    _spashiny_ctx._on_show_cloud_resources = _on_show_cloud_resources

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.show_sm_prep)
    def _on_show_sm():
        _spashiny_ctx.current_module.set("SM")

    _spashiny_ctx._on_show_sm = _on_show_sm

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.show_st_prep)
    def _on_show_st():
        _spashiny_ctx.current_module.set("ST")

    _spashiny_ctx._on_show_st = _on_show_st

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.show_sm_QC)
    def _on_show_sm_qc():
        _spashiny_ctx.current_module.set("SM_QC")

    _spashiny_ctx._on_show_sm_qc = _on_show_sm_qc

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.show_st_QC)
    def _on_show_st_qc():
        _spashiny_ctx.current_module.set("ST_QC")

    _spashiny_ctx._on_show_st_qc = _on_show_st_qc

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.show_stsm_alignment)
    def _on_show_stsm_alignment():
        _spashiny_ctx.current_module.set("ST-SM Alignment")

    _spashiny_ctx._on_show_stsm_alignment = _on_show_stsm_alignment

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.show_single_sample_pipeline)
    def _on_show_single_sample_pipeline():
        _spashiny_ctx.current_module.set("ONE_STOP")

    _spashiny_ctx._on_show_single_sample_pipeline = _on_show_single_sample_pipeline

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.show_stsm_model)
    def _on_show_stsm_model():
        if _spashiny_ctx._prepare_confirmed_alignment_coordinates():
            _spashiny_ctx.current_module.set("ST-SM model")

    _spashiny_ctx._on_show_stsm_model = _on_show_stsm_model

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.show_stsm_reassignment)
    def _on_show_stsm_reassignment():
        _spashiny_ctx.current_module.set("ST-SM Reassignment")

    _spashiny_ctx._on_show_stsm_reassignment = _on_show_stsm_reassignment

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.VIT_SM_ST)
    def _on_show_vit_sm_st():
        _spashiny_ctx.current_module.set("VIT_SM_ST")

    _spashiny_ctx._on_show_vit_sm_st = _on_show_vit_sm_st

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.VHIT_SM_ST)
    def _on_show_vhit_sm_st():
        _spashiny_ctx.current_module.set("VHIT_SM_ST")

    _spashiny_ctx._on_show_vhit_sm_st = _on_show_vhit_sm_st

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.VHIT_SM_ST_MERGE)
    def _on_show_vhit_sm_st_merge():
        _spashiny_ctx.current_module.set("VHIT_SM_ST")

    _spashiny_ctx._on_show_vhit_sm_st_merge = _on_show_vhit_sm_st_merge

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.HIT_SM)
    def _on_show_hit_sm():
        _spashiny_ctx.current_module.set("HIT_SM")

    _spashiny_ctx._on_show_hit_sm = _on_show_hit_sm

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.AT_SM_ST1)
    def _on_show_at_sm_st1():
        _spashiny_ctx.current_module.set("AT_SM_ST1")

    _spashiny_ctx._on_show_at_sm_st1 = _on_show_at_sm_st1

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.show_downstream_marker)
    def _on_show_downstream_marker():
        _spashiny_ctx.current_module.set("AT_SM_ST1")

    _spashiny_ctx._on_show_downstream_marker = _on_show_downstream_marker

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.show_river_module)
    def _on_show_river_module():
        _spashiny_ctx.current_module.set("Spatial Transcriptomics River")

    _spashiny_ctx._on_show_river_module = _on_show_river_module

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.show_sm_tic_roi)
    def _on_show_sm_tic_roi():
        _spashiny_ctx.current_module.set("SM TIC ROI")

    _spashiny_ctx._on_show_sm_tic_roi = _on_show_sm_tic_roi

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.show_enrichment_module)
    def _on_show_enrichment_module():
        _spashiny_ctx.current_module.set(
            "Enrichment Module"
            if _spashiny_globals.SPASHINY_R_FEATURES_ENABLED
            else (
                "CPU Enrichment Module"
                if _spashiny_globals.SPASHINY_CPU_ENRICHMENT_ENABLED
                else "Enrichment Module Disabled"
            )
        )

    _spashiny_ctx._on_show_enrichment_module = _on_show_enrichment_module


def _install_1(_spashiny_ctx):

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.show_dash_plotly)
    def _on_show_dash_plotly():
        _spashiny_ctx.current_module.set("Dash Plotly")

    _spashiny_ctx._on_show_dash_plotly = _on_show_dash_plotly

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.show_help_tutorial)
    def _on_show_help_tutorial():
        _spashiny_ctx.current_module.set("Help & Tutorial")

    _spashiny_ctx._on_show_help_tutorial = _on_show_help_tutorial

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.help_open_alignment)
    def _on_help_open_alignment():
        _spashiny_ctx.current_module.set("ST-SM Alignment")

    _spashiny_ctx._on_help_open_alignment = _on_help_open_alignment

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.help_open_st_qc)
    def _on_help_open_st_qc():
        _spashiny_ctx.current_module.set("ST_QC")

    _spashiny_ctx._on_help_open_st_qc = _on_help_open_st_qc

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.help_open_sm_qc)
    def _on_help_open_sm_qc():
        _spashiny_ctx.current_module.set("SM_QC")

    _spashiny_ctx._on_help_open_sm_qc = _on_help_open_sm_qc

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.help_open_integration)
    def _on_help_open_integration():
        _spashiny_ctx.current_module.set("VIT_SM_ST")

    _spashiny_ctx._on_help_open_integration = _on_help_open_integration

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.show_ssh_module)
    def _on_show_ssh_module():
        if _spashiny_globals.SPASHINY_WEB_PLATFORM:
            _spashiny_ctx.current_module.set("Cloud Resources")
            return
        _spashiny_ctx.current_module.set("SSH Module")

    _spashiny_ctx._on_show_ssh_module = _on_show_ssh_module

    @_spashiny_ctx.output
    @_spashiny_ctx.render.ui
    def main_content():
        module = _spashiny_ctx.current_module.get()
        if module == "ONE_STOP":
            return _ui_one_stop.ui(_spashiny_ctx, module)
        if module == "SSH Module":
            return _ui_connection.ui(_spashiny_ctx, module)
        if module == "Cloud Files":
            return _ui_uploads.ui(_spashiny_ctx, module)
        if module == "Cloud Jobs":
            return _ui_jobs.ui(_spashiny_ctx, module)
        if module == "Cloud Results":
            return _ui_results.ui(_spashiny_ctx, module)
        if module == "Cloud Resources":
            return _ui_resources.ui(_spashiny_ctx, module)
        if module == "Help & Tutorial":
            return _ui_help.ui(_spashiny_ctx, module)
        if module == "home":
            return _ui_home.ui(_spashiny_ctx, module)
        if module == "SM":
            return _ui_sm_import.ui(_spashiny_ctx, module)
        _spashiny_ctx.st_apple_style = """
        <style>
            /* ppp */
            .st-header {
                font-weight: 600;
                color: #1d1d1f;
                margin-bottom: 28px;
                letter-spacing: -0.022em;
                font-size: 24px;
            }

            /* ppp */
            .accordion {
                border: none !important;
            }
            .accordion-item {
                border: 1px solid #d2d2d7 !important;
                border-radius: 14px !important;
                margin-bottom: 16px;
                overflow: hidden;
                background: #ffffff;
            }
            .accordion-button {
                background-color: #ffffff !important;
                font-weight: 500;
                color: #1d1d1f;
                box-shadow: none !important;
                padding: 18px 24px;
            }
            .accordion-button:not(.collapsed) {
                color: #007aff;
                background-color: #fafafa !important;
            }

            /* ppp */
            .control-panel {
                background: #ffffff;
                padding: 24px;
                border-radius: 16px;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
                height: 100%;
                border: 1px solid #f0f0f2;
            }

            /* ppp */
            .btn-apple {
                border-radius: 10px;
                padding: 10px 16px;
                font-weight: 500;
                font-size: 14px;
                transition: all 0.2s cubic-bezier(0.25, 0.1, 0.25, 1);
                border: none;
                margin-bottom: 10px;
                width: 100%;
            }
            /* ppp */
            .btn-apple-primary {
                background: #007aff;
                color: white;
            }
            .btn-apple-primary:hover {
                background: #0063cc;
                transform: scale(1.01);
            }

            /* ppp */
            .btn-apple-secondary {
                background: #f5f5f7;
                color: #1d1d1f;
                border: 1px solid rgba(0,0,0,0.05);
            }
            .btn-apple-secondary:hover {
                background: #e8e8ed;
            }

            /* ppp  */
            .console-window {
                background: #fbfbfd; /* ppp */
                color: #424245;
                padding: 20px;
                border-radius: 12px;
                font-family: "SF Mono", "SFMono-Regular", Consolas, Menlo, monospace;
                font-size: 13px;
                line-height: 1.6;
                height: 450px;
                overflow-y: auto;
                border: 1px solid #d2d2d7;
                box-shadow: inset 0 1px 4px rgba(0,0,0,0.03);
                white-space: pre-wrap;
            }

            /* ppp  */
            .console-window::-webkit-scrollbar {
                width: 6px;
            }
            .console-window::-webkit-scrollbar-track {
                background: transparent;
            }
            .console-window::-webkit-scrollbar-thumb {
                background: #d2d2d7;
                border-radius: 10px;
            }
            .console-window::-webkit-scrollbar-thumb:hover {
                background: #86868b;
            }

            /* ppp  */
            .control-label {
                font-size: 12px;
                font-weight: 600;
                color: #86868b;
                margin-bottom: 10px;
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }
        </style>
        """
        if module == "ST":
            return _ui_st_import.ui(_spashiny_ctx, module)
        _spashiny_ctx.qc_apple_style = """
        <style>
            .qc-header {
                font-weight: 600;
                color: #1d1d1f;
                margin-bottom: 28px;
                letter-spacing: -0.022em;
                font-size: 24px;
            }


            .control-panel {
                background: #ffffff;
                padding: 24px;
                border-radius: 16px;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
                border: 1px solid #f0f0f2;
                height: 100%;
            }


            .control-label {
                font-size: 12px;
                font-weight: 600;
                color: #86868b;
                margin-bottom: 10px;
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }

            .qc-param-grid {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 8px 10px;
                margin: 8px 0 12px 0;
            }

            .qc-param-grid .shiny-input-container,
            .qc-param-grid .form-group {
                margin-bottom: 0 !important;
                width: 100%;
            }

            .qc-param-grid .shiny-input-container:only-child,
            .qc-param-grid .form-group:only-child {
                grid-column: 1 / -1;
            }

            .qc-param-grid label {
                margin-bottom: 4px !important;
                font-size: 12px !important;
                color: #424245;
            }

            .qc-param-grid input {
                min-height: 38px !important;
                padding: 7px 10px !important;
                border-radius: 8px !important;
            }


            .btn-apple {
                border-radius: 10px;
                padding: 10px 16px;
                font-weight: 500;
                font-size: 14px;
                transition: all 0.2s ease;
                border: none;
                margin-bottom: 10px;
                width: 100%;
            }
            .btn-apple-primary { background: #007aff; color: white; }
            .btn-apple-primary:hover { background: #0063cc; }

            .btn-apple-secondary { background: #f5f5f7; color: #1d1d1f; border: 1px solid rgba(0,0,0,0.05); }
            .btn-apple-secondary:hover { background: #e8e8ed; }


            .console-window {
                background: #fbfbfd;
                color: #424245;
                padding: 20px;
                border-radius: 12px;
                font-family: "SF Mono", "SFMono-Regular", Consolas, monospace;
                font-size: 13px;
                line-height: 1.6;
                height: 380px;
                overflow-y: auto;
                border: 1px solid #d2d2d7;
                box-shadow: inset 0 1px 4px rgba(0,0,0,0.02);
            }


            .plot-card {
                background: #ffffff;
                padding: 20px;
                border-radius: 16px;
                border: 1px solid #f0f0f2;
                margin-bottom: 20px;
            }

            .plot-title {
                font-size: 14px;
                font-weight: 600;
                color: #1d1d1f;
                margin-bottom: 15px;
                text-align: center;
            }
        </style>
        """
        if module == "SM_QC":
            return _ui_sm_qc.ui(_spashiny_ctx, module)
        if module == "ST_QC":
            return _ui_st_qc.ui(_spashiny_ctx, module)
        if module == "ST-SM Alignment":
            return _ui_alignment_manual.ui(_spashiny_ctx, module)
        if module == "ST-SM model":
            return _ui_alignment_auto.ui(_spashiny_ctx, module)
        if module == "ST-SM Reassignment":
            return _ui_knn.ui(_spashiny_ctx, module)
        if module == "VIT_SM_ST":
            return _ui_integration_single.ui(_spashiny_ctx, module)
        if module == "VHIT_SM_ST":
            return _ui_integration_multi_st_sm.ui(_spashiny_ctx, module)
        if module == "HIT_SM":
            return _ui_integration_multi_sm.ui(_spashiny_ctx, module)
        _spashiny_ctx.at_sm_st1_apple_css = """
        <style>
        :root {
            --apple-bg: #f5f5f7;
            --apple-card: rgba(255, 255, 255, 0.86);
            --apple-border: rgba(0, 0, 0, 0.06);
            --apple-shadow: 0 10px 30px rgba(0, 0, 0, 0.06);
            --apple-shadow-hover: 0 16px 40px rgba(0, 0, 0, 0.10);
            --apple-text: #1d1d1f;
            --apple-subtext: #6e6e73;
            --apple-blue: #0071e3;
            --apple-green: #34c759;
            --apple-red: #ff3b30;
            --apple-orange: #ff9f0a;
            --apple-gray: #8e8e93;
            --apple-radius-xl: 28px;
            --apple-radius-lg: 22px;
            --apple-radius-md: 18px;
        }

        body {
            background: linear-gradient(180deg, #f8f9fb 0%, #f2f4f8 100%);
            color: var(--apple-text);
            font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display",
                        "SF Pro Text", "Helvetica Neue", Helvetica, Arial, sans-serif;
            margin-top: 0 !important;
            padding-top: 1 !important;
        }

        .at-page-shell {
            max-width: 1580px;
            margin: 0 auto;
            padding: 0px 20px 48px 20px;
        }

        /* =========================
        Hero
        ========================= */
        .at-hero {
            background: linear-gradient(135deg, rgba(255,255,255,0.94), rgba(248,250,255,0.90));
            border: 1px solid rgba(255,255,255,0.6);
            backdrop-filter: blur(18px);
            -webkit-backdrop-filter: blur(18px);
            border-radius: 34px;
            box-shadow: var(--apple-shadow);
            padding: 32px 36px;
            margin-bottom: 24px;
            position: relative;
            overflow: hidden;
        }

        .at-hero::before {
            content: "";
            position: absolute;
            top: -80px;
            right: -80px;
            width: 220px;
            height: 220px;
            background: radial-gradient(circle, rgba(0,113,227,0.12) 0%, rgba(0,113,227,0.02) 65%, transparent 100%);
            border-radius: 50%;
        }

        .at-title {
            font-size: 2.15rem;
            font-weight: 700;
            letter-spacing: -0.03em;
            margin: 0 0 8px 0;
        }

        .at-subtitle {
            font-size: 1.00rem;
            color: var(--apple-subtext);
            margin: 0;
            max-width: 1000px;
            line-height: 1.7;
        }

        /* =========================
        Main stack
        ========================= */
        .at-stack {
            display: flex;
            flex-direction: column;
            gap: 22px;
        }

        /* =========================
        Apple panel
        ========================= */
        .apple-panel {
            background: var(--apple-card);
            border: 1px solid rgba(255,255,255,0.55);
            backdrop-filter: blur(18px);
            -webkit-backdrop-filter: blur(18px);
            border-radius: var(--apple-radius-xl);
            box-shadow: var(--apple-shadow);
            padding: 26px;
            transition: all 0.28s ease;
        }

        .apple-panel:hover {
            transform: translateY(-2px);
            box-shadow: var(--apple-shadow-hover);
        }

        .apple-section-title {
            font-size: 1.22rem;
            font-weight: 700;
            letter-spacing: -0.02em;
            margin-bottom: 18px;
        }

        .apple-subsection-title {
            font-size: 1rem;
            font-weight: 600;
            color: var(--apple-text);
            margin: 18px 0 12px 0;
        }

        .apple-muted {
            color: var(--apple-subtext);
            font-size: 0.95rem;
            line-height: 1.7;
        }

        .metric-note {
            background: rgba(0,113,227,0.06);
            border: 1px solid rgba(0,113,227,0.08);
            border-radius: 20px;
            padding: 14px 16px;
            color: #1d3f72;
            font-size: 0.95rem;
            line-height: 1.65;
        }

        .manual-annotation-panel {
            padding: 16px 18px;
            border-radius: 12px;
        }

        .manual-annotation-panel .apple-section-title {
            margin-bottom: 4px;
            font-size: 1.05rem;
        }

        .manual-annotation-note {
            color: var(--apple-subtext);
            font-size: 0.84rem;
            line-height: 1.35;
            margin-bottom: 10px;
        }

        .manual-annotation-grid {
            display: grid;
            grid-template-columns: minmax(180px, 1fr) minmax(230px, 1.5fr) minmax(160px, auto);
            gap: 8px 10px;
            align-items: end;
        }

        .manual-annotation-grid .shiny-input-container,
        .manual-annotation-grid .form-group {
            margin-bottom: 0 !important;
            width: 100%;
        }

        .manual-annotation-actions {
            display: grid;
            grid-template-columns: 1fr auto;
            gap: 10px;
            align-items: stretch;
            margin-top: 10px;
        }

        .manual-annotation-preview {
            max-height: 120px;
            overflow: auto;
            border: 1px solid #d9dee6;
            border-radius: 8px;
            background: #f9fafb;
            padding: 8px 10px;
        }

        .manual-annotation-preview pre {
            margin: 0 !important;
            white-space: pre-wrap;
            font-size: 0.78rem;
            line-height: 1.35;
            background: transparent !important;
            border: 0 !important;
            padding: 0 !important;
        }

        .manual-annotation-panel .btn {
            min-height: 40px;
            padding: 9px 13px !important;
            white-space: nowrap;
        }

        @media (max-width: 991px) {
            .manual-annotation-grid,
            .manual-annotation-actions {
                grid-template-columns: 1fr;
            }
        }

        /* =========================
        Gray upload shell
        ========================= */
        .at-upload-shell {
            background: linear-gradient(135deg, rgba(233,236,240,0.86), rgba(220,224,230,0.76));
            border: 1px solid rgba(255,255,255,0.55);
            backdrop-filter: blur(18px);
            -webkit-backdrop-filter: blur(18px);
            border-radius: 24px;
            padding: 20px 22px;
        }

        .at-upload-actions {
            display: flex;
            gap: 12px;
            align-items: end;
            height: 100%;
        }

        /* =========================
        Buttons
        ========================= */
        .btn, .btn-default, .btn-primary, .btn-success, .btn-danger, .btn-info, .btn-secondary, .btn-warning {
            border-radius: 999px !important;
            padding: 12px 18px !important;
            font-weight: 600 !important;
            border: none !important;
            box-shadow: 0 8px 18px rgba(0,0,0,0.08);
            transition: all 0.22s ease !important;
        }

        .btn:hover {
            transform: translateY(-1px);
            box-shadow: 0 12px 24px rgba(0,0,0,0.12);
        }

        .btn-primary { background: linear-gradient(135deg, #0a84ff, #0071e3) !important; }
        .btn-success { background: linear-gradient(135deg, #34c759, #30b958) !important; }
        .btn-danger  { background: linear-gradient(135deg, #ff5e57, #ff3b30) !important; }
        .btn-info    { background: linear-gradient(135deg, #5ac8fa, #0a84ff) !important; }
        .btn-warning { background: linear-gradient(135deg, #ffb340, #ff9500) !important; color: white !important; }
        .btn-secondary { background: linear-gradient(135deg, #8e8e93, #6e6e73) !important; }

        /* =========================
        Inputs
        ========================= */
        .form-control, .form-select, .shiny-input-number input, input, select, textarea {
            border-radius: 18px !important;
            border: 1px solid rgba(0,0,0,0.08) !important;
            background: rgba(255,255,255,0.94) !important;
            box-shadow: none !important;
            padding: 12px 14px !important;
            min-height: 48px;
        }

        .control-label, label {
            font-weight: 600 !important;
            color: var(--apple-text) !important;
            margin-bottom: 8px !important;
        }

        /* =========================
        Compact controls
        ========================= */
        .at-compact-controls .shiny-input-container,
        .at-compact-controls .form-group,
        .at-compact-controls .mb-3,
        .at-compact-controls .mb-2 {
            margin-bottom: 5px !important;
        }

        .at-compact-controls label {
            font-size: 0.88rem !important;
            margin-bottom: 3px !important;
        }

        .at-compact-controls .form-control,
        .at-compact-controls .form-select,
        .at-compact-controls textarea,
        .at-compact-controls input {
            min-height: 42px !important;
            padding: 10px 12px !important;
            font-size: 0.90rem !important;
        }

        .at-compact-controls textarea.form-control {
            min-height: 90px !important;
        }
        /* 1. Highlight effect for custom action buttons */
        .btn-apple-action {
            background: var(--apple-blue);
            color: white;
            border-radius: 12px;
            padding: 12px;
            border: none;
            transition: all 0.3s ease;
            box-shadow: 0 4px 12px rgba(0, 113, 227, 0.2);
            font-weight: 600;
        }

        /* Feedback during click and active states */
        .btn-apple-action:active, .btn-apple-action:focus {
            background: #0077ed;
            box-shadow: 0 0 15px var(--apple-blue); /* Breathing light effect */
            transform: scale(0.98);
        }

        /* 2. Make active switches more vivid (Apple Green) */
        .form-check-input:checked {
            background-color: var(--apple-green) !important;
            border-color: var(--apple-green) !important;
            filter: drop-shadow(0 0 5px rgba(52, 199, 89, 0.5)); /* Green glow effect */
        }

        /* 3. Highlight border for selected cards */
        .at-hero:active-within {
            border: 1px solid var(--apple-blue) !important;
            box-shadow: var(--apple-shadow-hover);
        }

        /* =========================
        Plot shells
        ========================= */
        .wide-plot {
            width: 100%;
            min-height: 520px;
            border-radius: 26px;
            overflow: hidden;
            background: rgba(255,255,255,0.68);
            border: 1px solid rgba(0,0,0,0.04);
            padding: 14px;
        }

        .correlation-plot-shell {
            width: 100%;
            flex: 1 1 auto;
            min-height: 0;
            overflow: auto;
            padding: 8px 2px 2px 2px;
        }

        .correlation-plot-shell .shiny-plot-output {
            min-height: 520px;
        }

        .correlation-workspace {
            align-items: stretch;
        }

        .correlation-square-card,
        #correlation-control-card {
            aspect-ratio: 1 / 1;
            min-height: 620px;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            padding: 16px;
            border: 1px solid #d9dee6;
            border-radius: 6px;
            background: #ffffff;
            box-shadow: none;
            backdrop-filter: none;
            -webkit-backdrop-filter: none;
        }

        #correlation-control-card {
            aspect-ratio: auto;
            height: 100%;
            min-height: 0;
            overflow: visible;
            padding: 14px 16px;
            border-radius: 8px;
            background: #fbfcfe;
        }

        #correlation-control-card .at-hero {
            margin: 0 0 10px 0 !important;
            padding: 0 !important;
            min-height: 0 !important;
            background: transparent !important;
            border: 0 !important;
            box-shadow: none !important;
            backdrop-filter: none !important;
            -webkit-backdrop-filter: none !important;
        }

        #correlation-control-card .apple-section-title,
        .apple-panel:has(#correlation-heatmap-card) .apple-section-title {
            margin-bottom: 8px;
            font-size: 1.02rem;
            letter-spacing: 0;
        }

        #correlation-control-card .shiny-input-container,
        #correlation-control-card .form-group,
        #correlation-control-card .mb-3,
        #correlation-control-card .mb-2 {
            margin-bottom: 0 !important;
            width: 100%;
        }

        #correlation-control-card label {
            margin-bottom: 2px !important;
            font-size: 0.80rem !important;
            color: #4b5563;
        }

        #correlation-control-card .form-control,
        #correlation-control-card .form-select,
        #correlation-control-card input[type="text"],
        #correlation-control-card input[type="number"] {
            min-height: 34px !important;
            padding: 6px 9px !important;
            font-size: 0.84rem !important;
            border-color: #cfd6df;
            border-radius: 4px;
        }

        #correlation-control-card textarea.form-control {
            min-height: 58px !important;
            height: 58px !important;
            padding: 6px 9px !important;
            resize: none;
        }

        #correlation-control-card .form-check {
            min-height: 26px;
            padding-top: 0;
            padding-left: 0;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        #correlation-control-card .form-check-input {
            width: 2em !important;
            height: 1em !important;
            min-height: 0 !important;
            padding: 0 !important;
            margin-top: 0.2em;
            margin-left: 0 !important;
            flex: 0 0 auto;
            filter: none !important;
        }

        #correlation-control-card .form-check-label {
            margin-bottom: 0 !important;
            line-height: 1.2;
            white-space: normal;
        }

        #correlation-control-card .bslib-grid {
            gap: 10px 14px !important;
        }

        #correlation-control-card .correlation-form-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 6px 10px;
            align-items: end;
        }

        #correlation-control-card .correlation-form-wide {
            grid-column: 1 / -1;
        }

        #correlation-control-card .correlation-form-small,
        #correlation-control-card .correlation-form-switch {
            grid-column: span 1;
            min-width: 0;
        }

        #correlation-control-card .correlation-form-switch {
            align-self: center;
        }

        #correlation-control-card .correlation-form-actions {
            grid-column: 1 / -1;
        }

        #correlation-control-card .btn-apple-action {
            width: 100%;
            min-height: 38px;
            margin-top: 2px;
            padding: 8px 12px;
            border-radius: 4px;
            box-shadow: none;
            font-size: 0.86rem;
            transition: none;
            background: #2563eb !important;
            background-image: none !important;
        }

        #correlation-control-card .btn-apple-action:active,
        #correlation-control-card .btn-apple-action:focus {
            box-shadow: none;
            transform: none;
        }

        .apple-panel:has(#correlation-heatmap-card) {
            aspect-ratio: 1 / 1;
            min-height: 620px;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            padding: 16px;
            border: 1px solid #d9dee6;
            border-radius: 6px;
            background: #ffffff;
            box-shadow: none;
            backdrop-filter: none;
            -webkit-backdrop-filter: none;
        }

        .correlation-control-body {
            flex: 1 1 auto;
            overflow: auto;
            padding-right: 4px;
        }

        @media (max-width: 991px) {
            .correlation-square-card,
            #correlation-control-card,
            .apple-panel:has(#correlation-heatmap-card) {
                aspect-ratio: auto;
                min-height: 540px;
            }

            #correlation-control-card {
                min-height: 0;
            }

            #correlation-control-card .correlation-form-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }

            #correlation-control-card .correlation-form-wide,
            #correlation-control-card .correlation-form-actions {
                grid-column: 1 / -1;
            }

            #correlation-control-card .correlation-form-small,
            #correlation-control-card .correlation-form-switch {
                grid-column: span 1;
            }
        }

        .square-plot {
            aspect-ratio: 1 / 1;
            width: 100%;
            min-height: 440px;
            border-radius: 24px;
            overflow: hidden;
            background: rgba(255,255,255,0.68);
            border: 1px solid rgba(0,0,0,0.04);
            padding: 12px;
        }

        .rect-plot {
            min-height: 500px;
            width: 100%;
            border-radius: 24px;
            overflow: hidden;
            background: rgba(255,255,255,0.68);
            border: 1px solid rgba(0,0,0,0.04);
            padding: 12px;
        }

        .marker-table-shell {
            min-height: 240px;
            max-height: 240px;
            overflow: auto;
            border-radius: 22px;
            background: rgba(255,255,255,0.70);
            border: 1px solid rgba(0,0,0,0.04);
            padding: 12px 14px;
        }

        .plot-title {
            font-size: 1.02rem;
            font-weight: 700;
            margin-bottom: 12px;
            letter-spacing: -0.01em;
        }

        .plot-title-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            margin-bottom: 12px;
        }

        .plot-title-row .plot-title {
            margin-bottom: 0;
        }

        .plot-download-button {
            border-radius: 6px !important;
            padding: 6px 10px !important;
            min-height: 0 !important;
            font-size: 0.78rem !important;
            line-height: 1.2 !important;
            background: #ffffff !important;
            background-image: none !important;
            color: #374151 !important;
            border: 1px solid #d1d5db !important;
            box-shadow: none !important;
            transform: none !important;
            white-space: nowrap;
        }

        .plot-download-button:hover,
        .plot-download-button:focus,
        .plot-download-button:active {
            background: #f9fafb !important;
            background-image: none !important;
            color: #111827 !important;
            box-shadow: none !important;
            transform: none !important;
        }

        /* =========================
        Tables / summary
        ========================= */
        .table-shell {
            background: rgba(255,255,255,0.78);
            border-radius: 24px;
            padding: 18px;
            border: 1px solid rgba(0,0,0,0.04);
            overflow: hidden;
        }

        .config-summary-box {
            background: rgba(255,255,255,0.76);
            border: 1px solid rgba(0,0,0,0.04);
            border-radius: 20px;
            padding: 14px 18px;
            min-height: 56px;
            display: flex;
            align-items: center;
        }

        /* =========================
        Modal
        ========================= */
        .modal-content {
            border-radius: 30px !important;
            border: 1px solid rgba(255,255,255,0.55) !important;
            background: rgba(255,255,255,0.90) !important;
            backdrop-filter: blur(18px);
            -webkit-backdrop-filter: blur(18px);
            box-shadow: 0 20px 50px rgba(0,0,0,0.14) !important;
            padding: 8px;
        }

        .modal-header, .modal-footer {
            border: none !important;
            background: transparent !important;
        }

        .modal-body {
            padding: 24px 26px !important;
        }

        /* =========================
        Misc
        ========================= */
        pre, .shiny-text-output, .shiny-html-output {
            white-space: pre-wrap !important;
            word-break: break-word !important;
        }

        /* =========================
        Responsive
        ========================= */
        @media (max-width: 992px) {
            .wide-plot, .rect-plot {
                min-height: 380px;
            }

            .square-plot {
                min-height: 340px;
                aspect-ratio: auto;
            }

            .marker-table-shell {
                min-height: 220px;
                max-height: none;
            }

            .at-upload-actions {
                flex-direction: column;
                align-items: stretch;
            }
        }
        </style>

        <script>
        document.addEventListener("DOMContentLoaded", function () {
            const cards = document.querySelectorAll(".apple-panel");
            cards.forEach((card, i) => {
                card.style.opacity = "0";
                card.style.transform = "translateY(18px)";
                setTimeout(() => {
                    card.style.transition = "all 0.5s ease";
                    card.style.opacity = "1";
                    card.style.transform = "translateY(0)";
                }, 60 * i);
            });
        });
        </script>
        """
        if module == "Dash Plotly":
            return _ui_spatialmeta_dash.ui(_spashiny_ctx, module)
        if module == "AT_SM_ST1":
            return _ui_downstream.ui(_spashiny_ctx, module)
        if module == "Enrichment Module":
            return _ui_r_enrichment.ui(_spashiny_ctx, module)
        if module == "CPU Enrichment Module":
            return _ui_enrichment.ui(_spashiny_ctx, module)
        if module == "SpatialMETA Metabolite Annotation":
            return _ui_metabolite_annotation.ui(_spashiny_ctx, module)
        if module == "Enrichment Module Disabled":
            return _ui_enrichment.ui(_spashiny_ctx, module)
        if module == "Spatial Transcriptomics River":
            return _ui_river.ui(_spashiny_ctx, module)
        if module == "SM TIC ROI":
            return _ui_sm_tic_roi.ui(_spashiny_ctx, module)
        return _spashiny_ctx.ui.div(_spashiny_ctx.ui.p("NOT 404"))

    _spashiny_ctx.main_content = main_content


_STEPS = (_install_0, _install_1)


def server(_spashiny_ctx, step=0):
    return _STEPS[step](_spashiny_ctx)
