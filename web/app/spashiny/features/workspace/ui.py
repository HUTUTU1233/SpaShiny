# Actual feature UI extracted from production. Feature: workspace.
from spashiny._shared import runtime_globals as _spashiny_globals


def cloud_platform_ui(section="jobs"):
    title_map = {
        "files": ("My Files", "Private uploads for the current cloud user."),
        "jobs": (
            "Job Center",
            "Cloud tasks submitted with automatic CPU or GPU resource selection.",
        ),
        "results": (
            "My Results",
            "Completed result packages available after secure synchronization.",
        ),
        "resources": (
            "Resource Status",
            "Control plane, CPU/GPU pools, storage, and queue availability without exposing secrets.",
        ),
    }
    title, subtitle = title_map.get(section, title_map["jobs"])
    output_map = {
        "files": "cloud_my_files",
        "jobs": "cloud_job_center",
        "results": "cloud_my_results",
        "resources": "cloud_resource_status",
    }
    return _spashiny_globals.ui.page_fluid(
        _spashiny_globals.ui.tags.style(
            """
        .cloud-shell { max-width: 1280px; margin: 0 auto; padding: 28px 10px 46px; color: #1d1d1f; }
        .cloud-header { margin-bottom: 18px; }
        .cloud-title { font-size: 2rem; font-weight: 760; margin: 0 0 6px; }
        .cloud-subtitle { color: #6e6e73; line-height: 1.65; max-width: 860px; }
        .cloud-panel { background: rgba(255,255,255,0.96); border: 1px solid rgba(0,0,0,0.06); border-radius: 12px; padding: 20px 22px; box-shadow: 0 8px 22px rgba(0,0,0,0.045); }
        .cloud-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
        .cloud-metric { border: 1px solid #e5e7eb; border-radius: 8px; padding: 14px; background: #f8fafc; }
        .cloud-metric-title { color: #64748b; font-size: .86rem; margin-bottom: 5px; }
        .cloud-metric-value { font-weight: 740; font-size: 1.25rem; }
        .cloud-list { display: grid; gap: 10px; }
        .cloud-row { border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px 14px; background: #fff; }
        .cloud-example-row { display: grid; grid-template-columns: 110px minmax(0, 1fr) auto; gap: 14px; align-items: start; }
        .cloud-example-preview { width: 110px; min-height: 74px; border: 1px solid #dbeafe; border-radius: 8px; background: #eff6ff; color: #1d4ed8; display: grid; place-items: center; font-size: .86rem; overflow: hidden; }
        .cloud-example-preview img { width: 100%; height: 100%; object-fit: cover; display: block; }
        .cloud-example-meta { display: flex; flex-wrap: wrap; gap: 6px 10px; margin-top: 8px; }
        .cloud-example-meta span { border: 1px solid #e5e7eb; border-radius: 6px; padding: 3px 7px; background: #f8fafc; color: #475569; font-size: .84rem; }
        .cloud-use-example { border: 1px solid #0f766e; color: #0f766e; background: #fff; border-radius: 6px; padding: 8px 10px; white-space: nowrap; }
        .cloud-use-example:disabled { opacity: .62; cursor: progress; }
        .cloud-muted { color: #6e6e73; }
        .cloud-error { color: #b91c1c; }
        .cloud-session { display: flex; flex-wrap: wrap; gap: 10px 16px; align-items: center; border: 1px solid #dbeafe; background: #eff6ff; border-radius: 8px; padding: 10px 12px; margin-bottom: 12px; }
        .cloud-session strong { color: #1e3a8a; }
        .cloud-session button { border: 1px solid #bfdbfe; background: #fff; color: #1d4ed8; border-radius: 6px; padding: 6px 10px; }
        @media (max-width: 900px) { .cloud-grid { grid-template-columns: 1fr; } }
        """
        ),
        _spashiny_globals.ui.tags.div(
            _spashiny_globals.ui.tags.div(
                _spashiny_globals.ui.tags.h2(title, class_="cloud-title"),
                _spashiny_globals.ui.tags.div(subtitle, class_="cloud-subtitle"),
                class_="cloud-header",
            ),
            _spashiny_globals.ui.tags.div(
                _spashiny_globals.ui.tags.strong(
                    "Anonymous laboratory session"
                    if _spashiny_globals.SPASHINY_LAB_PROFILE
                    else "Anonymous temporary session"
                ),
                _spashiny_globals.ui.tags.span("Status: "),
                _spashiny_globals.ui.tags.span("INITIALIZING", id="spashiny-session-status"),
                _spashiny_globals.ui.tags.span(
                    "Workspace: " if _spashiny_globals.SPASHINY_LAB_PROFILE else "Session: "
                ),
                _spashiny_globals.ui.tags.span("not ready", id="spashiny-session-id"),
                _spashiny_globals.ui.tags.span("Idle remaining: "),
                _spashiny_globals.ui.tags.span("not ready", id="spashiny-session-idle"),
                _spashiny_globals.ui.tags.span(
                    "Local lab files are isolated to this anonymous workspace."
                    if _spashiny_globals.SPASHINY_LAB_PROFILE
                    else "Online analyses end after 12 hours without work or user activity. Running jobs and uploads are protected from inactivity expiry. Closing the tab uses the existing close-grace policy."
                ),
                _spashiny_globals.ui.tags.button(
                    "New Analysis", id="spashiny-new-analysis", type="button"
                ),
                _spashiny_globals.ui.tags.button(
                    "End session and delete data", id="spashiny-session-end", type="button"
                ),
                class_="cloud-session",
            ),
            _spashiny_globals.ui.tags.div(
                _spashiny_globals.ui.output_ui(output_map.get(section, "cloud_job_center")),
                class_="cloud-panel",
            ),
            class_="cloud-shell",
        ),
    )


def ui(_spashiny_ctx):
    return cloud_platform_ui()
