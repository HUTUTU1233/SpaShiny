# Feature connection: original callable implementation extracted from ssh_module.py.
from spashiny._shared.feature_support import ssh_module as _feature_shared
from spashiny._shared import runtime_globals as _spashiny_globals


def _view_1(_spashiny_ctx, module):
    if _spashiny_globals.SPASHINY_WEB_PLATFORM:
        return _spashiny_globals.cloud_platform_ui("resources")
    return _spashiny_globals.ssh_module_ui()


def ui(_spashiny_ctx, module):
    if module == "SSH Module":
        return _view_1(_spashiny_ctx, module)
    raise ValueError("Unknown feature page: connection")


def ssh_module_ui():
    return _feature_shared.ui.page_fluid(
        _feature_shared.ui.tags.style(
            """
        .ssh-page {
            max-width: 1280px;
            margin: 0 auto;
            padding: 28px 8px 42px 8px;
        }
        .ssh-hero {
            background: linear-gradient(135deg, rgba(255,255,255,0.98), rgba(245,249,255,0.94));
            border: 1px solid rgba(0,0,0,0.06);
            border-radius: 28px;
            box-shadow: 0 12px 30px rgba(0,0,0,0.05);
            padding: 30px 34px;
            margin-bottom: 22px;
        }
        .ssh-title {
            font-size: 2.0rem;
            font-weight: 760;
            color: #1d1d1f;
            letter-spacing: -0.03em;
            margin-bottom: 8px;
        }
        .ssh-subtitle {
            color: #6e6e73;
            line-height: 1.75;
            max-width: 980px;
        }
        .ssh-layout {
            display: grid;
            grid-template-columns: minmax(320px, 420px) minmax(0, 1fr);
            gap: 20px;
            align-items: start;
        }
        .ssh-card {
            background: rgba(255,255,255,0.96);
            border: 1px solid rgba(0,0,0,0.06);
            border-radius: 24px;
            box-shadow: 0 10px 26px rgba(0,0,0,0.045);
            padding: 22px 24px;
        }
        .ssh-card h4 {
            font-weight: 740;
            color: #1d1d1f;
            margin-top: 0;
            margin-bottom: 14px;
        }
        .ssh-muted {
            color: #6e6e73;
            font-size: 0.94rem;
            line-height: 1.7;
        }
        .ssh-btn-row {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin-top: 14px;
        }
        .ssh-status-card {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 18px;
            padding: 18px 20px;
            border-radius: 20px;
            background: #f8fafc;
            border: 1px solid #e5e7eb;
            margin-bottom: 16px;
        }
        .ssh-status-title {
            font-size: 1.06rem;
            font-weight: 730;
            color: #1d1d1f;
            margin-bottom: 4px;
        }
        .ssh-status-desc {
            color: #6e6e73;
            line-height: 1.6;
            font-size: 0.93rem;
        }
        .ssh-pill {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 9px 13px;
            border-radius: 999px;
            font-size: 0.92rem;
            font-weight: 720;
            white-space: nowrap;
        }
        .ssh-pill.local {
            background: #f1f5f9;
            color: #475569;
            border: 1px solid #cbd5e1;
        }
        .ssh-pill.connected {
            background: #ecfdf5;
            color: #047857;
            border: 1px solid #a7f3d0;
        }
        .ssh-pill.error {
            background: #fef2f2;
            color: #b91c1c;
            border: 1px solid #fecaca;
        }
        .ssh-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            display: inline-block;
            background: #94a3b8;
            box-shadow: 0 0 0 4px rgba(148,163,184,0.14);
        }
        .ssh-pill.connected .ssh-dot {
            background: #10b981;
            box-shadow: 0 0 0 4px rgba(16,185,129,0.16);
        }
        .ssh-pill.error .ssh-dot {
            background: #ef4444;
            box-shadow: 0 0 0 4px rgba(239,68,68,0.14);
        }
        .ssh-log-box pre {
            min-height: 260px;
            max-height: 420px;
            overflow: auto;
            background: #0f172a;
            color: #dbeafe;
            border-radius: 18px;
            border: 1px solid #1e293b;
            padding: 16px 18px;
            font-size: 0.9rem;
            line-height: 1.55;
        }
        .ssh-wheelhouse-panel {
            margin-top: 14px;
            padding: 14px 15px;
            border-radius: 16px;
            background: #f8fafc;
            border: 1px solid #e5e7eb;
        }
        .ssh-wheelhouse-panel .form-group {
            margin-bottom: 8px;
        }
        .ssh-check-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 12px;
            margin-bottom: 16px;
        }
        .ssh-check-card {
            border: 1px solid #e5e7eb;
            border-radius: 16px;
            padding: 13px 14px;
            background: #ffffff;
        }
        .ssh-check-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
            margin-bottom: 8px;
            font-weight: 740;
            color: #1d1d1f;
        }
        .ssh-check-badge {
            border-radius: 999px;
            padding: 4px 9px;
            font-size: 0.78rem;
            font-weight: 760;
            white-space: nowrap;
        }
        .ssh-check-badge.ok {
            background: #ecfdf5;
            color: #047857;
            border: 1px solid #a7f3d0;
        }
        .ssh-check-badge.warn {
            background: #fff7ed;
            color: #c2410c;
            border: 1px solid #fed7aa;
        }
        .ssh-check-meta {
            color: #64748b;
            font-size: 0.86rem;
            line-height: 1.55;
            word-break: break-word;
        }
        .ssh-top-status {
            display: inline-flex;
            align-items: center;
            gap: 7px;
            margin-left: 14px;
            padding: 7px 10px;
            border-radius: 999px;
            font-size: 13px;
            font-weight: 720;
            border: 1px solid #cbd5e1;
            color: #475569;
            background: #f8fafc;
        }
        .ssh-top-status.connected {
            border-color: #a7f3d0;
            color: #047857;
            background: #ecfdf5;
        }
        .ssh-top-status.error {
            border-color: #fecaca;
            color: #b91c1c;
            background: #fef2f2;
        }
        .ssh-top-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #94a3b8;
        }
        .ssh-top-status.connected .ssh-top-dot { background: #10b981; }
        .ssh-top-status.error .ssh-top-dot { background: #ef4444; }
        @media (max-width: 980px) {
            .ssh-layout { grid-template-columns: 1fr; }
            .ssh-check-grid { grid-template-columns: 1fr; }
        }
        """
        ),
        _feature_shared.ui.tags.div(
            _feature_shared.ui.tags.div(
                _feature_shared.ui.tags.div("SSH Connection", class_="ssh-title"),
                _feature_shared.ui.tags.div(
                    "Optionally connect to a remote server for downstream background analysis. When disconnected, jobs run locally; after a successful SSH test, ST-SM and River can use the selected remote environments.",
                    class_="ssh-subtitle",
                ),
                class_="ssh-hero",
            ),
            _feature_shared.ui.tags.div(
                _feature_shared.ui.tags.div(
                    _feature_shared.ui.tags.div(
                        _feature_shared.ui.tags.h4("Connection Parameters"),
                        _feature_shared.ui.input_text(
                            "ssh_host",
                            "Host / IP",
                            placeholder="e.g. 127.0.0.1 or server.example.com",
                        ),
                        _feature_shared.ui.input_numeric(
                            "ssh_port", "Port", value=22, min=1, max=65535, step=1
                        ),
                        _feature_shared.ui.input_text(
                            "ssh_username", "Username", placeholder="e.g. zhuozhong"
                        ),
                        _feature_shared.ui.input_password(
                            "ssh_password",
                            "Password",
                            placeholder="Optional; leave empty when using an unencrypted key",
                        ),
                        _feature_shared.ui.input_text_area(
                            "ssh_key_text",
                            "Private key text (optional)",
                            placeholder="Paste an OpenSSH private key here. If provided, it is preferred for login; the password field can also be used as the passphrase.",
                            rows=4,
                        ),
                        _feature_shared.ui.input_text(
                            "ssh_remote_workspace",
                            "Remote workspace",
                            value=_feature_shared.DEFAULT_REMOTE_WORKDIR,
                            placeholder="e.g. ~/SpaShiny_STSM_jobs",
                        ),
                        _feature_shared.ui.output_ui("ssh_env_selectors"),
                        _feature_shared.ui.tags.div(
                            _feature_shared.ui.input_text(
                                "ssh_local_wheelhouse",
                                "Local wheelhouse folder / zip",
                                value=_feature_shared.DEFAULT_LOCAL_WHEELHOUSE,
                                placeholder="e.g. runtime/wheelhouse or /opt/spashiny/packages/spashiny_wheels.zip",
                            ),
                            _feature_shared.ui.input_text(
                                "ssh_remote_package_dir",
                                "Remote package directory",
                                value=_feature_shared.DEFAULT_REMOTE_PACKAGE_DIR,
                                placeholder="e.g. data/packages, ~/spashiny_packages, or /data/user/spashiny_packages",
                            ),
                            _feature_shared.ui.tags.div(
                                "When packages are missing, SpaShiny uploads this compatible Python wheelhouse to the remote package directory and installs with pip --no-index.",
                                class_="ssh-muted",
                            ),
                            class_="ssh-wheelhouse-panel",
                        ),
                        _feature_shared.ui.tags.div(
                            _feature_shared.ui.input_action_button(
                                "ssh_test", "Test and Connect", class_="btn btn-primary"
                            ),
                            _feature_shared.ui.input_action_button(
                                "ssh_validate_envs",
                                "Validate Selected Environments",
                                class_="btn btn-info",
                            ),
                            _feature_shared.ui.input_action_button(
                                "ssh_install_missing",
                                "Upload Python Wheelhouse & Install Missing",
                                class_="btn btn-success",
                            ),
                            _feature_shared.ui.input_action_button(
                                "ssh_disconnect", "Disconnect / Use Local", class_="btn btn-default"
                            ),
                            class_="ssh-btn-row",
                        ),
                        _feature_shared.ui.tags.hr(),
                        _feature_shared.ui.tags.div(
                            "SSH manages the remote connection. ST-SM and River use the remote Python/conda environments configured here. Disconnecting switches analysis back to local mode.",
                            class_="ssh-muted",
                        ),
                        class_="ssh-card",
                    ),
                    _feature_shared.ui.tags.div(
                        _feature_shared.ui.tags.div(
                            _feature_shared.ui.output_ui("ssh_status_card"),
                            _feature_shared.ui.output_ui("ssh_env_check_card"),
                            _feature_shared.ui.tags.h4("Connection Log"),
                            _feature_shared.ui.tags.div(
                                _feature_shared.ui.output_text_verbatim("ssh_log"),
                                class_="ssh-log-box",
                            ),
                            class_="ssh-card",
                        )
                    ),
                    class_="ssh-layout",
                )
            ),
            class_="ssh-page",
        ),
    )


def ssh_status_indicator_ui(status, host="", username=""):
    if status == "connected":
        label = "SSH connected"
        extra = f" - {username}@{host}" if host and username else ""
        cls = "ssh-top-status connected"
    elif status == "error":
        label = "SSH error"
        extra = ""
        cls = "ssh-top-status error"
    else:
        label = "Local mode"
        extra = ""
        cls = "ssh-top-status"
    return _feature_shared.ui.tags.div(
        _feature_shared.ui.tags.span(class_="ssh-top-dot"),
        _feature_shared.ui.tags.span(label + extra),
        class_=cls,
        title=label + extra,
    )
