# Feature connection: original callable implementation extracted from ssh_module.py.
from spashiny._shared.feature_support import ssh_module as _feature_shared


def ssh_module_server(input, output, session):
    ssh_state = _feature_shared.reactive.Value(
        {
            "status": "local",
            "host": "",
            "port": 22,
            "username": "",
            "password": "",
            "key_text": "",
            "remote_workspace": _feature_shared.DEFAULT_REMOTE_WORKDIR,
            "python_cmd": _feature_shared.DEFAULT_REMOTE_PYTHON,
            "stsm_python_cmd": _feature_shared.DEFAULT_STSM_PYTHON,
            "river_python_cmd": _feature_shared.DEFAULT_RIVER_PYTHON,
            "env_choices": [
                {"label": "python (PATH)", "command": "python"},
                {"label": "python3 (PATH)", "command": "python3"},
            ],
            "env_check": {},
            "wheelhouse_path": _feature_shared.DEFAULT_LOCAL_WHEELHOUSE,
            "remote_package_dir": _feature_shared.DEFAULT_REMOTE_PACKAGE_DIR,
            "install_summary": {},
            "message": "Local mode is active.",
        }
    )
    ssh_log_value = _feature_shared.reactive.Value(
        "[INFO] Local mode is active. SSH is not connected.\n"
    )

    def append_log(msg):
        import time

        old = ssh_log_value.get() or ""
        ssh_log_value.set(old + time.strftime("[%H:%M:%S] ") + str(msg) + "\n")

    def set_state(
        status,
        host="",
        port=22,
        username="",
        password="",
        key_text="",
        remote_workspace=_feature_shared.DEFAULT_REMOTE_WORKDIR,
        python_cmd=_feature_shared.DEFAULT_STSM_PYTHON,
        stsm_python_cmd=_feature_shared.DEFAULT_STSM_PYTHON,
        river_python_cmd=_feature_shared.DEFAULT_RIVER_PYTHON,
        env_choices=None,
        env_check=None,
        wheelhouse_path=None,
        remote_package_dir=None,
        install_summary=None,
        message="",
    ):
        current = ssh_state.get()
        stsm_python_cmd = stsm_python_cmd or python_cmd or _feature_shared.DEFAULT_STSM_PYTHON
        ssh_state.set(
            {
                "status": status,
                "host": host or "",
                "port": int(port or 22),
                "username": username or "",
                "password": password or "",
                "key_text": key_text or "",
                "remote_workspace": remote_workspace or _feature_shared.DEFAULT_REMOTE_WORKDIR,
                "python_cmd": stsm_python_cmd,
                "stsm_python_cmd": stsm_python_cmd,
                "river_python_cmd": river_python_cmd or _feature_shared.DEFAULT_RIVER_PYTHON,
                "env_choices": env_choices
                or [
                    {"label": "python (PATH)", "command": "python"},
                    {"label": "python3 (PATH)", "command": "python3"},
                ],
                "env_check": env_check or {},
                "wheelhouse_path": (
                    wheelhouse_path
                    if wheelhouse_path is not None
                    else current.get("wheelhouse_path", _feature_shared.DEFAULT_LOCAL_WHEELHOUSE)
                ),
                "remote_package_dir": (
                    remote_package_dir
                    if remote_package_dir is not None
                    else current.get(
                        "remote_package_dir", _feature_shared.DEFAULT_REMOTE_PACKAGE_DIR
                    )
                ),
                "install_summary": (
                    install_summary
                    if install_summary is not None
                    else current.get("install_summary", {})
                ),
                "message": message or "",
            }
        )

    def validate_envs_with_client(
        client, stsm_python_cmd, river_python_cmd, raise_on_missing=False
    ):
        checks = {}
        errors = []
        for label, cmd, packages, key in [
            ("ST-SM", stsm_python_cmd, _feature_shared.REQUIRED_STSM_PACKAGES, "stsm"),
            ("River", river_python_cmd, _feature_shared.REQUIRED_RIVER_PACKAGES, "river"),
        ]:
            try:
                meta = _feature_shared.ssh_probe_python_packages(client, cmd, packages)
                if meta.get("exit_status") != 0:
                    error = f"{label} environment dependency probe failed.\nSTDOUT:\n{meta.get('stdout', '')}\nSTDERR:\n{meta.get('stderr', '')}"
                    checks[key] = {
                        "ok": False,
                        "cmd": cmd,
                        "command_ok": False,
                        "error": error,
                        **meta,
                    }
                    errors.append(error)
                    append_log(f"[ERROR] {label} dependency probe failed: {cmd}")
                    continue
                missing = meta.get("missing") or []
                if missing:
                    error = (
                        f"{label} environment is missing required package(s): {', '.join(missing)}"
                    )
                    checks[key] = {
                        "ok": False,
                        "cmd": cmd,
                        "command_ok": True,
                        "error": error,
                        **meta,
                    }
                    errors.append(error)
                    append_log(f"[WARN] {error}")
                    continue
                checks[key] = {"ok": True, "cmd": cmd, "command_ok": True, **meta}
                append_log(
                    f"[OK] {label} environment dependencies are complete: {cmd} (Python {meta.get('version', '')}, executable={meta.get('python', '')})"
                )
            except Exception as e:
                checks[key] = {"ok": False, "cmd": cmd, "command_ok": False, "error": str(e)}
                errors.append(str(e))
                append_log(f"[ERROR] {e}")
        if errors and raise_on_missing:
            raise RuntimeError("; ".join(errors))
        return (checks, errors)

    @output
    @_feature_shared.render.ui
    def ssh_env_selectors():
        st = ssh_state.get()
        if st.get("status") == "connected":
            choices = _feature_shared.ssh_env_choices_dict(
                st.get("env_choices", []),
                st.get("stsm_python_cmd", _feature_shared.DEFAULT_STSM_PYTHON),
                st.get("river_python_cmd", _feature_shared.DEFAULT_RIVER_PYTHON),
            )
            return _feature_shared.ui.tags.div(
                _feature_shared.ui.input_select(
                    "ssh_stsm_env_choice",
                    "ST-SM remote environment",
                    choices=choices,
                    selected=st.get("stsm_python_cmd", _feature_shared.DEFAULT_STSM_PYTHON),
                ),
                _feature_shared.ui.input_select(
                    "ssh_river_env_choice",
                    "River remote environment",
                    choices=choices,
                    selected=st.get("river_python_cmd", _feature_shared.DEFAULT_RIVER_PYTHON),
                ),
                _feature_shared.ui.tags.div(
                    "Available Python/conda environments were discovered on the SSH server. Select one, then click Validate Selected Environments.",
                    class_="ssh-muted",
                ),
            )
        return _feature_shared.ui.tags.div(
            _feature_shared.ui.input_text(
                "ssh_python_cmd",
                "ST-SM remote Python command",
                value=_feature_shared.DEFAULT_STSM_PYTHON,
                placeholder="e.g. python, python3, conda run -n spatialmeta python",
            ),
            _feature_shared.ui.input_text(
                "ssh_river_python_cmd",
                "River remote Python command",
                value=_feature_shared.DEFAULT_RIVER_PYTHON,
                placeholder="e.g. python, python3, conda run -n river python",
            ),
            _feature_shared.ui.tags.div(
                "Before connecting, you can enter commands manually. After a successful connection, conda/mamba environments on the SSH server will be discovered automatically.",
                class_="ssh-muted",
            ),
        )

    @_feature_shared.reactive.Effect
    @_feature_shared.reactive.event(input.ssh_stsm_env_choice, input.ssh_river_env_choice)
    def _apply_selected_envs():
        st = ssh_state.get()
        if st.get("status") != "connected":
            return
        try:
            stsm_cmd = input.ssh_stsm_env_choice()
            river_cmd = input.ssh_river_env_choice()
        except Exception:
            return
        if not stsm_cmd or not river_cmd:
            return
        if stsm_cmd == st.get("stsm_python_cmd") and river_cmd == st.get("river_python_cmd"):
            return
        set_state(
            "connected",
            host=st.get("host", ""),
            port=st.get("port", 22),
            username=st.get("username", ""),
            password=st.get("password", ""),
            key_text=st.get("key_text", ""),
            remote_workspace=st.get("remote_workspace", _feature_shared.DEFAULT_REMOTE_WORKDIR),
            stsm_python_cmd=stsm_cmd,
            river_python_cmd=river_cmd,
            env_choices=st.get("env_choices", []),
            env_check={},
            message=f"Selected remote environments: ST-SM={stsm_cmd}; River={river_cmd}. Please validate dependencies.",
        )

    @_feature_shared.reactive.Effect
    @_feature_shared.reactive.event(input.ssh_test)
    def _test_ssh_connection():
        host = (input.ssh_host() or "").strip()
        port = int(input.ssh_port() or 22)
        username = (input.ssh_username() or "").strip()
        password = input.ssh_password() or ""
        key_text = input.ssh_key_text() or ""
        remote_workspace = (
            input.ssh_remote_workspace() or _feature_shared.DEFAULT_REMOTE_WORKDIR
        ).strip()
        current = ssh_state.get()
        try:
            stsm_python_cmd = (
                input.ssh_python_cmd()
                or current.get("stsm_python_cmd")
                or _feature_shared.DEFAULT_STSM_PYTHON
            ).strip()
        except Exception:
            stsm_python_cmd = (
                current.get("stsm_python_cmd") or _feature_shared.DEFAULT_STSM_PYTHON
            ).strip()
        try:
            river_python_cmd = (
                input.ssh_river_python_cmd()
                or current.get("river_python_cmd")
                or _feature_shared.DEFAULT_RIVER_PYTHON
            ).strip()
        except Exception:
            river_python_cmd = (
                current.get("river_python_cmd") or _feature_shared.DEFAULT_RIVER_PYTHON
            ).strip()
        if not host:
            set_state("error", message="Please enter Host / IP.")
            append_log("[ERROR] Host / IP is empty.")
            return
        if not username:
            set_state("error", host=host, port=port, message="Please enter a username.")
            append_log("[ERROR] Username is empty.")
            return
        if not stsm_python_cmd:
            set_state(
                "error",
                host=host,
                port=port,
                username=username,
                message="Please enter the ST-SM remote Python command.",
            )
            append_log("[ERROR] ST-SM remote Python command is empty.")
            return
        if not river_python_cmd:
            set_state(
                "error",
                host=host,
                port=port,
                username=username,
                message="Please enter the River remote Python command.",
            )
            append_log("[ERROR] River remote Python command is empty.")
            return
        append_log(f"[INFO] Testing SSH connection: {username}@{host}:{port}")
        try:
            with _feature_shared.socket.create_connection((host, port), timeout=6):
                append_log("[OK] TCP port is reachable.")
        except Exception as e:
            msg = f"TCP connection failed: {e}"
            set_state("error", host=host, port=port, username=username, message=msg)
            append_log("[ERROR] " + msg)
            return
        try:
            import paramiko
        except Exception:
            msg = "paramiko is not installed. Please install it in the current Python environment: pip install paramiko"
            set_state("error", host=host, port=port, username=username, message=msg)
            append_log("[ERROR] " + msg)
            return
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            pkey = (
                _feature_shared._load_private_key(key_text, password) if key_text.strip() else None
            )
            client.connect(
                hostname=host,
                port=port,
                username=username,
                password=password if password else None,
                pkey=pkey,
                timeout=8,
                banner_timeout=8,
                auth_timeout=8,
                look_for_keys=True,
                allow_agent=True,
            )
            test_cmd = f"echo SSH_OK && hostname && mkdir -p {_feature_shared.ssh_quote(remote_workspace)} && cd {_feature_shared.ssh_quote(remote_workspace)} && pwd"
            result = _feature_shared.ssh_exec_command(client, test_cmd, timeout=20)
            out = result["stdout"].strip()
            err = result["stderr"].strip()
            exit_status = result["exit_status"]
            if exit_status != 0:
                raise RuntimeError(f"Remote workspace test failed: {err or out}")
            append_log("[INFO] Discovering Python/conda environments on the SSH server...")
            env_choices = _feature_shared.ssh_discover_python_envs(client)
            append_log(
                f"[OK] Discovered {len(env_choices)} selectable Python command(s) / environment(s)."
            )
            selected_stsm_python_cmd = _feature_shared.ssh_pick_working_python_command(
                client, stsm_python_cmd, env_choices
            )
            selected_river_python_cmd = _feature_shared.ssh_pick_working_python_command(
                client, river_python_cmd, env_choices
            )
            if selected_stsm_python_cmd != stsm_python_cmd:
                append_log(
                    f"[INFO] ST-SM Python default changed to discovered command: {selected_stsm_python_cmd}"
                )
            if selected_river_python_cmd != river_python_cmd:
                append_log(
                    f"[INFO] River Python default changed to discovered command: {selected_river_python_cmd}"
                )
            stsm_python_cmd = selected_stsm_python_cmd
            river_python_cmd = selected_river_python_cmd
            append_log(
                "[INFO] Checking dependencies for the selected ST-SM / River environments..."
            )
            env_check, env_errors = validate_envs_with_client(
                client, stsm_python_cmd, river_python_cmd, raise_on_missing=False
            )
            msg = "SSH login succeeded." + (f" Remote output: {out}" if out else "")
            if env_errors:
                msg += " Remote environment dependency checks did not pass: " + "; ".join(
                    env_errors
                )
            set_state(
                "connected",
                host=host,
                port=port,
                username=username,
                password=password,
                key_text=key_text,
                remote_workspace=remote_workspace,
                python_cmd=stsm_python_cmd,
                stsm_python_cmd=stsm_python_cmd,
                river_python_cmd=river_python_cmd,
                env_choices=env_choices,
                env_check=env_check,
                message=msg,
            )
            append_log("[OK] " + msg)
            if err:
                append_log("[REMOTE STDERR] " + err)
            client.close()
        except Exception as e:
            try:
                client.close()
            except Exception:
                pass
            msg = f"SSH login failed: {e}"
            set_state("error", host=host, port=port, username=username, message=msg)
            append_log("[ERROR] " + msg)
            append_log(_feature_shared.traceback.format_exc())

    @_feature_shared.reactive.Effect
    @_feature_shared.reactive.event(input.ssh_validate_envs)
    def _validate_selected_envs():
        st = ssh_state.get()
        if st.get("status") != "connected":
            append_log(
                "[WARN] Please test and connect SSH before validating remote environment dependencies."
            )
            return
        try:
            stsm_cmd = input.ssh_stsm_env_choice() or st.get(
                "stsm_python_cmd", _feature_shared.DEFAULT_STSM_PYTHON
            )
            river_cmd = input.ssh_river_env_choice() or st.get(
                "river_python_cmd", _feature_shared.DEFAULT_RIVER_PYTHON
            )
        except Exception:
            stsm_cmd = st.get("stsm_python_cmd", _feature_shared.DEFAULT_STSM_PYTHON)
            river_cmd = st.get("river_python_cmd", _feature_shared.DEFAULT_RIVER_PYTHON)
        client = None
        try:
            client = _feature_shared.ssh_open_client(st)
            append_log("[INFO] Validating selected remote environment dependencies...")
            env_check, env_errors = validate_envs_with_client(
                client, stsm_cmd, river_cmd, raise_on_missing=False
            )
            message = f"Selected remote environments: ST-SM={stsm_cmd}; River={river_cmd}"
            if env_errors:
                message += ". Missing dependencies: " + "; ".join(env_errors)
            else:
                message += ". Dependency checks passed."
            set_state(
                "connected",
                host=st.get("host", ""),
                port=st.get("port", 22),
                username=st.get("username", ""),
                password=st.get("password", ""),
                key_text=st.get("key_text", ""),
                remote_workspace=st.get("remote_workspace", _feature_shared.DEFAULT_REMOTE_WORKDIR),
                stsm_python_cmd=stsm_cmd,
                river_python_cmd=river_cmd,
                env_choices=st.get("env_choices", []),
                env_check=env_check,
                message=message,
            )
        except Exception as e:
            append_log(f"[ERROR] Remote environment validation failed: {e}")
            append_log(_feature_shared.traceback.format_exc())
        finally:
            if client is not None:
                client.close()

    @_feature_shared.reactive.Effect
    @_feature_shared.reactive.event(input.ssh_install_missing)
    def _install_missing_remote_packages():
        st = ssh_state.get()
        if st.get("status") != "connected":
            append_log("[WARN] Please test and connect SSH before installing remote packages.")
            return
        try:
            stsm_cmd = input.ssh_stsm_env_choice() or st.get(
                "stsm_python_cmd", _feature_shared.DEFAULT_STSM_PYTHON
            )
            river_cmd = input.ssh_river_env_choice() or st.get(
                "river_python_cmd", _feature_shared.DEFAULT_RIVER_PYTHON
            )
        except Exception:
            stsm_cmd = st.get("stsm_python_cmd", _feature_shared.DEFAULT_STSM_PYTHON)
            river_cmd = st.get("river_python_cmd", _feature_shared.DEFAULT_RIVER_PYTHON)
        try:
            wheelhouse_text = (
                input.ssh_local_wheelhouse()
                or st.get("wheelhouse_path")
                or _feature_shared.DEFAULT_LOCAL_WHEELHOUSE
            ).strip()
        except Exception:
            wheelhouse_text = st.get("wheelhouse_path") or _feature_shared.DEFAULT_LOCAL_WHEELHOUSE
        try:
            remote_package_dir = (
                input.ssh_remote_package_dir()
                or st.get("remote_package_dir")
                or _feature_shared.DEFAULT_REMOTE_PACKAGE_DIR
            ).strip()
        except Exception:
            remote_package_dir = (
                st.get("remote_package_dir") or _feature_shared.DEFAULT_REMOTE_PACKAGE_DIR
            )
        client = None
        try:
            client = _feature_shared.ssh_open_client(st)
            append_log("[INFO] Checking missing remote packages before offline installation...")
            initial_check, _ = validate_envs_with_client(
                client, stsm_cmd, river_cmd, raise_on_missing=False
            )
            fatal = [
                f"{label}: {initial_check.get(key, {}).get('error', 'command failed')}"
                for key, label in [("stsm", "ST-SM"), ("river", "River")]
                if initial_check.get(key, {}).get("command_ok") is False
            ]
            if fatal:
                message = (
                    "Cannot install packages until the selected Python command runs successfully. "
                    + "; ".join(fatal)
                )
                append_log("[ERROR] " + message)
                set_state(
                    "connected",
                    host=st.get("host", ""),
                    port=st.get("port", 22),
                    username=st.get("username", ""),
                    password=st.get("password", ""),
                    key_text=st.get("key_text", ""),
                    remote_workspace=st.get(
                        "remote_workspace", _feature_shared.DEFAULT_REMOTE_WORKDIR
                    ),
                    stsm_python_cmd=stsm_cmd,
                    river_python_cmd=river_cmd,
                    env_choices=st.get("env_choices", []),
                    env_check=initial_check,
                    wheelhouse_path=wheelhouse_text,
                    remote_package_dir=remote_package_dir,
                    message=message,
                )
                return
            missing_jobs = []
            for key, label, cmd, packages in [
                ("stsm", "ST-SM", stsm_cmd, _feature_shared.REQUIRED_STSM_PACKAGES),
                ("river", "River", river_cmd, _feature_shared.REQUIRED_RIVER_PACKAGES),
            ]:
                missing = initial_check.get(key, {}).get("missing") or []
                if missing:
                    missing_jobs.append((key, label, cmd, packages))
            if not missing_jobs:
                append_log("[OK] No missing packages were detected. Nothing to install.")
                set_state(
                    "connected",
                    host=st.get("host", ""),
                    port=st.get("port", 22),
                    username=st.get("username", ""),
                    password=st.get("password", ""),
                    key_text=st.get("key_text", ""),
                    remote_workspace=st.get(
                        "remote_workspace", _feature_shared.DEFAULT_REMOTE_WORKDIR
                    ),
                    stsm_python_cmd=stsm_cmd,
                    river_python_cmd=river_cmd,
                    env_choices=st.get("env_choices", []),
                    env_check=initial_check,
                    wheelhouse_path=wheelhouse_text,
                    remote_package_dir=remote_package_dir,
                    message="Selected remote environments already have all required packages.",
                )
                return
            local_wheelhouse = _feature_shared.ssh_resolve_local_wheelhouse(wheelhouse_text)
            extract_python_cmd = missing_jobs[0][2]
            remote_wheelhouse = _feature_shared.ssh_upload_local_wheelhouse(
                client,
                local_wheelhouse,
                st.get("remote_workspace", _feature_shared.DEFAULT_REMOTE_WORKDIR),
                extract_python_cmd,
                remote_package_dir,
                append_log,
            )
            install_summary = {}
            for key, label, cmd, packages in missing_jobs:
                install_summary[key] = _feature_shared.ssh_install_missing_packages_from_wheelhouse(
                    client, cmd, packages, remote_wheelhouse, label=label, log=append_log
                )
            append_log("[INFO] Re-validating remote environments after installation...")
            env_check, env_errors = validate_envs_with_client(
                client, stsm_cmd, river_cmd, raise_on_missing=False
            )
            message = "Offline package installation completed."
            if env_errors:
                message += " Some dependency checks still failed: " + "; ".join(env_errors)
            else:
                message += " Dependency checks passed."
            set_state(
                "connected",
                host=st.get("host", ""),
                port=st.get("port", 22),
                username=st.get("username", ""),
                password=st.get("password", ""),
                key_text=st.get("key_text", ""),
                remote_workspace=st.get("remote_workspace", _feature_shared.DEFAULT_REMOTE_WORKDIR),
                stsm_python_cmd=stsm_cmd,
                river_python_cmd=river_cmd,
                env_choices=st.get("env_choices", []),
                env_check=env_check,
                wheelhouse_path=wheelhouse_text,
                remote_package_dir=remote_package_dir,
                install_summary=install_summary,
                message=message,
            )
            append_log("[OK] " + message)
        except Exception as e:
            append_log(f"[ERROR] Remote offline package installation failed: {e}")
            append_log(_feature_shared.traceback.format_exc())
        finally:
            if client is not None:
                client.close()

    @_feature_shared.reactive.Effect
    @_feature_shared.reactive.event(input.ssh_disconnect)
    def _disconnect_ssh():
        set_state("local", message="Returned to local mode.")
        append_log("[INFO] SSH has been disconnected. Switched back to local mode.")

    @output
    @_feature_shared.render.ui
    def ssh_status_card():
        st = ssh_state.get()
        status = st.get("status", "local")
        host = st.get("host", "")
        port = st.get("port", 22)
        username = st.get("username", "")
        message = st.get("message", "")
        if status == "connected":
            pill_cls = "ssh-pill connected"
            pill_text = "Remote mode"
            title = "SSH Connected"
            desc = f"Current connection: {username}@{host}:{port}. {message}"
        elif status == "error":
            pill_cls = "ssh-pill error"
            pill_text = "Connection failed"
            title = "SSH Connection Error"
            desc = (
                message
                or "Connection failed. Please check the host, port, username, password, key, or network."
            )
        else:
            pill_cls = "ssh-pill local"
            pill_text = "Local mode"
            title = "SSH Not Connected"
            desc = message or "Analysis runs locally by default."
        return _feature_shared.ui.tags.div(
            _feature_shared.ui.tags.div(
                _feature_shared.ui.tags.div(title, class_="ssh-status-title"),
                _feature_shared.ui.tags.div(desc, class_="ssh-status-desc"),
            ),
            _feature_shared.ui.tags.div(
                _feature_shared.ui.tags.span(class_="ssh-dot"),
                _feature_shared.ui.tags.span(pill_text),
                class_=pill_cls,
            ),
            class_="ssh-status-card",
        )

    @output
    @_feature_shared.render.ui
    def ssh_env_check_card():
        st = ssh_state.get()
        checks = st.get("env_check") or {}
        if not checks:
            return _feature_shared.ui.tags.div(
                _feature_shared.ui.tags.h4("Environment Check"),
                _feature_shared.ui.tags.div(
                    "Connect SSH to scan environments and validate required packages.",
                    class_="ssh-muted",
                ),
            )

        def build_item(key, label):
            check = checks.get(key) or {}
            ok = bool(check.get("ok"))
            missing = check.get("missing") or []
            command_ok = check.get("command_ok")
            badge_text = (
                "Ready" if ok else "Command error" if command_ok is False else "Needs packages"
            )
            badge_cls = "ssh-check-badge ok" if ok else "ssh-check-badge warn"
            meta_parts = []
            cmd = check.get("cmd") or ""
            if cmd:
                meta_parts.append(f"Command: {cmd}")
            if check.get("python") or check.get("version"):
                meta_parts.append(
                    f"Python: {check.get('python', '')} {check.get('version', '')}".strip()
                )
            if command_ok is False and check.get("error"):
                meta_parts.append("Error: " + str(check.get("error")))
            elif missing:
                meta_parts.append("Missing: " + ", ".join(missing))
            elif check.get("error") and (not ok):
                meta_parts.append("Error: " + str(check.get("error")))
            else:
                meta_parts.append("Required packages are available.")
            return _feature_shared.ui.tags.div(
                _feature_shared.ui.tags.div(
                    _feature_shared.ui.tags.span(label),
                    _feature_shared.ui.tags.span(badge_text, class_=badge_cls),
                    class_="ssh-check-head",
                ),
                _feature_shared.ui.tags.div(" | ".join(meta_parts), class_="ssh-check-meta"),
                class_="ssh-check-card",
            )

        return _feature_shared.ui.tags.div(
            _feature_shared.ui.tags.h4("Environment Check"),
            _feature_shared.ui.tags.div(
                build_item("stsm", "ST-SM"), build_item("river", "River"), class_="ssh-check-grid"
            ),
        )

    @output
    @_feature_shared.render.text
    def ssh_log():
        return ssh_log_value.get()

    return ssh_state


server = ssh_module_server
