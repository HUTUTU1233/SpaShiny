# Extracted from /app/app/ST-SM.py. Feature: spatialmeta_dash; ordered phases preserve original initialization.
from spashiny._shared import runtime_globals as _spashiny_globals


def _install_0(_spashiny_ctx):
    import socket

    _spashiny_ctx.socket = socket
    _spashiny_ctx.DASH_PORT = 8050
    _spashiny_ctx.dash_runtime = {"app": None, "port": None, "feature": None, "adata_id": None}
    _spashiny_ctx.session_plotly_result = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.trajectory_adata_rv = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.trajectory_analysis_results_rv = _spashiny_ctx.reactive.Value({})

    def find_available_port(start_port=8050, max_tries=200):
        for port in range(start_port, start_port + max_tries):
            try:
                with _spashiny_ctx.socket.socket(
                    _spashiny_ctx.socket.AF_INET, _spashiny_ctx.socket.SOCK_STREAM
                ) as s:
                    s.bind((_spashiny_globals.DASH_BIND_HOST, port))
                    return port
            except OSError:
                continue
        raise RuntimeError("No available local port was found for Dash.")

    _spashiny_ctx.find_available_port = find_available_port

    def _dash_proxy_prefix(port):
        return f"{_spashiny_globals.DASH_PROXY_BASE_PATH}/{int(port)}/"

    _spashiny_ctx._dash_proxy_prefix = _dash_proxy_prefix

    def _build_dash_app_with_proxy_prefix(wrapper, selected_feature, port):
        """Create SpatialMETA's Dash app with the same-origin proxy prefix.

        SpatialMETA 0.0.3.0 hardcodes ``dash.Dash(...)`` inside
        ``Wrapper.to_plotly`` and Dash 3.x makes pathname prefixes read-only
        after construction.  This narrow test-only shim injects the prefix at
        construction time without changing SpatialMETA or the plotting logic.
        """
        import dash as _dash_module

        proxy_prefix = _spashiny_ctx._dash_proxy_prefix(port)
        original_dash_cls = _dash_module.Dash

        class _SpaShinyPrefixedDash(original_dash_cls):

            def __init__(self, *args, **kwargs):
                kwargs.setdefault("requests_pathname_prefix", proxy_prefix)
                kwargs.setdefault("routes_pathname_prefix", proxy_prefix)
                super().__init__(*args, **kwargs)

        with _spashiny_globals.DASH_APP_CONSTRUCTOR_LOCK:
            _dash_module.Dash = _SpaShinyPrefixedDash
            try:
                app_obj = wrapper.to_plotly(init_feature=selected_feature)
            finally:
                _dash_module.Dash = original_dash_cls
        return (app_obj, proxy_prefix)

    _spashiny_ctx._build_dash_app_with_proxy_prefix = _build_dash_app_with_proxy_prefix

    def _native_dash_input():
        result = _spashiny_ctx.marker_res.get()
        if isinstance(result, dict) and result.get("adata") is not None:
            return result["adata"]
        return _spashiny_ctx.adata_obj.get()

    _spashiny_ctx._native_dash_input = _native_dash_input
    _spashiny_ctx.native_dash_scope = _spashiny_globals.uuid.uuid4().hex
    _spashiny_ctx.native_dash_closed = _spashiny_globals.threading.Event()

    @_spashiny_ctx.reactive.extended_task
    async def start_native_dash_task(adata, feature, owner_id, analysis_id):
        from cloud.native_dash_runtime import start_viewer

        return await _spashiny_globals.asyncio.to_thread(
            start_viewer,
            adata,
            feature,
            owner_id,
            analysis_id,
            _spashiny_ctx.native_dash_scope,
            _spashiny_ctx.native_dash_closed,
        )

    _spashiny_ctx.start_native_dash_task = start_native_dash_task

    @_spashiny_ctx.session.on_ended
    async def _close_native_dash():
        from cloud.native_dash_runtime import close_scope

        _spashiny_ctx.native_dash_closed.set()
        _spashiny_ctx.start_native_dash_task.cancel()
        await _spashiny_globals.asyncio.to_thread(close_scope, _spashiny_ctx.native_dash_scope)

    _spashiny_ctx._close_native_dash = _close_native_dash

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.btn_native_spatialmeta)
    def _open_native_spatialmeta():
        if not _spashiny_ctx._downstream_click_guard(
            "btn_native_spatialmeta", "Open SpatialMETA Dash"
        ):
            return
        if _spashiny_ctx.start_native_dash_task.status() == "running":
            return
        try:
            owner_id = _spashiny_ctx._require_cloud_session_id()
            analysis_id = _spashiny_ctx._cloud_analysis_session_id()
            from cloud.database import CloudDatabase

            if (
                not analysis_id
                or CloudDatabase(read_only=True)
                .get_analysis_session(analysis_id, owner_session_id=owner_id)
                .get("status")
                != "ACTIVE"
            ):
                raise ValueError(
                    "This analysis is no longer ACTIVE. Open a new analysis rather than restoring an ended one."
                )
            adata = _spashiny_ctx._native_dash_input()
            if adata is None:
                raise ValueError(
                    "Load the current analysis input first. Correlation is not required."
                )
            feature = str(_spashiny_ctx.input.wrapper_feature() or "")
            if feature not in adata.var_names:
                feature = str(adata.var_names[0])
            _spashiny_ctx.dash_embed_state.set(
                {
                    "status": "starting",
                    "message": "Starting native SpatialMETA Dash in the background; no analysis is rerun.",
                }
            )
            _spashiny_ctx.current_module.set("Dash Plotly")
            _spashiny_ctx.start_native_dash_task(adata, feature, owner_id, analysis_id)
        except Exception as exc:
            _spashiny_ctx.dash_embed_state.set(
                {"status": "error", "message": f"SpatialMETA Dash: {type(exc).__name__}: {exc}"}
            )
            _spashiny_ctx.ui.notification_show(str(exc), type="error", duration=12)

    _spashiny_ctx._open_native_spatialmeta = _open_native_spatialmeta

    @_spashiny_ctx.reactive.Effect
    def _native_dash_ready():
        status = _spashiny_ctx.start_native_dash_task.status()
        if status not in {"success", "error"}:
            return
        try:
            state = _spashiny_ctx.start_native_dash_task.result()
            if state["analysis_id"] != _spashiny_ctx._cloud_analysis_session_id() or state[
                "data_id"
            ] != id(_spashiny_ctx._native_dash_input()):
                raise ValueError(
                    "The current input changed while Dash was starting. Open Dash again for the new input."
                )
            from cloud.native_dash_runtime import get_viewer

            viewer = get_viewer(state["viewer_id"])
            if viewer is None:
                raise RuntimeError("The native Dash instance has ended; open it again.")
            _spashiny_ctx.trajectory_adata_rv.set(viewer.wrapper.adata)
            _spashiny_ctx.dash_embed_state.set(
                {
                    **state,
                    "status": "native",
                    "message": "SpatialMETA native Dash: expression, grouping, ROI annotation and trajectory controls.",
                }
            )
        except Exception as exc:
            if status == "success":
                from cloud.native_dash_runtime import close_viewer

                stale = _spashiny_ctx.start_native_dash_task.result()
                _spashiny_globals.threading.Thread(
                    target=close_viewer, args=(stale["viewer_id"],), daemon=True
                ).start()
            _spashiny_ctx.dash_embed_state.set(
                {"status": "error", "message": f"SpatialMETA Dash: {type(exc).__name__}: {exc}"}
            )
            _spashiny_ctx.ui.notification_show(str(exc), type="error", duration=12)

    _spashiny_ctx._native_dash_ready = _native_dash_ready

    @_spashiny_ctx.reactive.Effect
    def _native_dash_input_changed():
        data_id = id(_spashiny_ctx._native_dash_input())
        with _spashiny_ctx.reactive.isolate():
            state = _spashiny_ctx.dash_embed_state.get()
        if state.get("data_id") and state["data_id"] != data_id:
            from cloud.native_dash_runtime import close_viewer

            _spashiny_globals.threading.Thread(
                target=close_viewer, args=(state["viewer_id"],), daemon=True
            ).start()
            _spashiny_ctx.dash_embed_state.set(
                {
                    "status": "idle",
                    "message": "The current input changed. Open SpatialMETA Dash for the new input.",
                }
            )

    _spashiny_ctx._native_dash_input_changed = _native_dash_input_changed

    @_spashiny_ctx.output
    @_spashiny_ctx.render.ui
    def dash_plotly_panel():
        state = _spashiny_ctx.dash_embed_state.get()
        adata = _spashiny_ctx._native_dash_input()
        features = [str(x) for x in adata.var_names] if adata is not None else []
        selected = state.get("feature")
        if selected not in features:
            selected = features[0] if features else None
        controls = _spashiny_ctx.ui.layout_columns(
            _spashiny_ctx.ui.input_selectize(
                "wrapper_feature",
                "Initial feature",
                choices=features,
                selected=selected,
                options={"placeholder": "Search feature...", "maxOptions": 200},
            ),
            _spashiny_ctx.ui.input_action_button(
                "btn_native_spatialmeta",
                "Open SpatialMETA Dash Spatial Map",
                class_="btn btn-primary",
            ),
            col_widths=(8, 4),
        )
        body = _spashiny_ctx.ui.p(
            "Load the current analysis input or finish Marker analysis first. Correlation is not required."
        )
        if state.get("status") == "native" and state.get("data_id") == id(adata):
            body = _spashiny_ctx.ui.tags.iframe(
                srcdoc=state["html"],
                sandbox="allow-scripts allow-same-origin allow-downloads",
                title="SpatialMETA native Dash",
                class_="dash-plotly-frame",
                style="height:1100px;width:100%;border:0;",
            )
        elif state.get("status") == "starting":
            body = _spashiny_ctx.ui.p(
                "Initializing the original SpatialMETA interface. This page remains connected while it starts."
            )
        return _spashiny_ctx.ui.div(
            {"class": "dash-plotly-panel"},
            _spashiny_ctx.ui.div(state.get("message", ""), class_="dash-plotly-status"),
            controls,
            body,
        )

    _spashiny_ctx.dash_plotly_panel = dash_plotly_panel

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.dash_go_downstream)
    def _dash_go_downstream():
        _spashiny_ctx.current_module.set("AT_SM_ST1")

    _spashiny_ctx._dash_go_downstream = _dash_go_downstream

    @_spashiny_ctx.reactive.Effect
    def update_wrapper_feature_choices():
        adata = _spashiny_ctx._native_dash_input()
        if adata is None:
            return
        features = [str(x) for x in adata.var_names.tolist()]
        if not features:
            return
        with _spashiny_ctx.reactive.isolate():
            current_feature = _spashiny_ctx.input.wrapper_feature()
        selected_feature = current_feature if current_feature in features else features[0]
        _spashiny_ctx.ui.update_selectize(
            "wrapper_feature",
            choices=features,
            selected=selected_feature,
            session=_spashiny_ctx.session,
        )

    _spashiny_ctx.update_wrapper_feature_choices = update_wrapper_feature_choices

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.btn_session_plotly)
    def run_session_feature_plot():
        if not _spashiny_ctx._downstream_click_guard(
            "btn_session_plotly", "Plot current-analysis spatial feature"
        ):
            return
        _spashiny_ctx._show_downstream_action_modal(
            "Preparing interactive spatial map...",
            "Reading one existing feature; no training, correlation or other analysis is rerun.",
        )
        fig = None
        try:
            adata = _spashiny_ctx.corr_res()
            if adata is None:
                raise ValueError("Load the current analysis and complete correlation first.")
            feature = str(_spashiny_ctx.input.wrapper_feature() or "").strip()
            chart, fig, metadata = _spashiny_globals.build_session_feature_plot(
                adata, feature, _spashiny_globals.smt.pl.Wrapper
            )
            token = _spashiny_globals.uuid.uuid4().hex
            root = _spashiny_ctx._downstream_volcano_artifact_dir()
            pdf = _spashiny_globals.save_editable_figure(fig, root / f"spatial_feature_{token}.pdf")
            svg = _spashiny_globals.save_editable_figure(fig, root / f"spatial_feature_{token}.svg")
            _spashiny_ctx.session_plotly_result.set(
                {"pdf": str(pdf), "svg": str(svg), "metadata": metadata}
            )
            _spashiny_ctx.dash_embed_state.set(
                {
                    "status": "session_plotly",
                    "url": "",
                    "html": _spashiny_globals.session_plotly_html(chart),
                    "feature": feature,
                    "message": "Session-safe Plotly spatial viewer is ready. Original Dash tools are separate.",
                }
            )
            _spashiny_ctx.current_module.set("Dash Plotly")
        except Exception as exc:
            _spashiny_ctx.session_plotly_result.set(None)
            _spashiny_ctx.dash_embed_state.set(
                {
                    "status": "error",
                    "url": "",
                    "html": "",
                    "message": f"Spatial viewer failed: {type(exc).__name__}: {exc}",
                }
            )
            _spashiny_ctx.ui.notification_show(
                f"Spatial viewer failed: {type(exc).__name__}: {exc}", type="error", duration=10
            )
            _spashiny_ctx.traceback.print_exc()
        finally:
            if fig is not None:
                _spashiny_globals.plt.close(fig)
            _spashiny_ctx.ui.modal_remove()

    _spashiny_ctx.run_session_feature_plot = run_session_feature_plot

    @_spashiny_ctx.render.download(filename=lambda: "spatial_feature.pdf")
    def download_session_plotly_pdf():
        result = _spashiny_ctx.session_plotly_result.get() or {}
        path = _spashiny_ctx.Path(str(result.get("pdf") or ""))
        if not path.is_file() or path.stat().st_size <= 0:
            raise RuntimeError(
                "Generate the current analysis spatial map before downloading its editable PDF."
            )
        yield from _spashiny_ctx.stream_file(path)

    _spashiny_ctx.download_session_plotly_pdf = download_session_plotly_pdf

    @_spashiny_ctx.render.download(filename=lambda: "spatial_feature.svg")
    def download_session_plotly_svg():
        result = _spashiny_ctx.session_plotly_result.get() or {}
        path = _spashiny_ctx.Path(str(result.get("svg") or ""))
        if not path.is_file() or path.stat().st_size <= 0:
            raise RuntimeError(
                "Generate the current analysis spatial map before downloading its editable SVG."
            )
        yield from _spashiny_ctx.stream_file(path)

    _spashiny_ctx.download_session_plotly_svg = download_session_plotly_svg

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.btn_run_wrapper)
    def run_wrapper_plot():
        if not _spashiny_ctx._downstream_click_guard(
            "btn_run_wrapper", "Initialize Embedded Plotly / Dash"
        ):
            return
        _spashiny_ctx._show_downstream_action_modal(
            "Initializing Embedded Plotly / Dash...",
            "Preparing the embedded interactive Dash/Plotly view for this analysis session.",
        )
        owner_analysis_port_binding_implemented = False
        if (
            not _spashiny_globals.SPASHINY_ENABLE_EMBEDDED_DASH
            or not owner_analysis_port_binding_implemented
        ):
            previous = dict(_spashiny_ctx.dash_embed_state.get() or {})
            previous.update(
                {
                    "status": "disabled",
                    "url": "",
                    "message": "Original Dash annotation/ROI/trajectory tools are disabled: the separate proxy listener has no exact owner + analysis port binding. Use the session-safe Plotly spatial viewer above; no authorization is relaxed.",
                }
            )
            _spashiny_ctx.dash_embed_state.set(previous)
            _spashiny_ctx.ui.notification_show(
                "Original Dash tools require owner + analysis scoped proxy authorization; the session-safe spatial viewer is available without opening that listener.",
                type="warning",
                duration=8,
            )
            _spashiny_ctx.ui.modal_remove()
            return
        adata = _spashiny_ctx.corr_res()
        if adata is None:
            _spashiny_ctx.dash_embed_state.set(
                {
                    "status": "idle",
                    "url": "",
                    "message": "Please complete downstream marker and ST–SM correlation analysis first, then open Downstream Analysis → Dash Plotly.",
                }
            )
            _spashiny_ctx.ui.notification_show(
                "Please complete downstream marker and ST–SM correlation analysis first, then open Downstream Analysis → Dash Plotly.",
                type="error",
                duration=8,
            )
            _spashiny_ctx.ui.modal_remove()
            return
        features = [str(x) for x in adata.var_names.tolist()]
        if not features:
            _spashiny_ctx.ui.notification_show(
                "No valid features were found in AnnData.", type="error"
            )
            _spashiny_ctx.ui.modal_remove()
            return
        try:
            selected_feature = _spashiny_ctx.input.wrapper_feature()
        except Exception:
            selected_feature = None
        if not selected_feature or selected_feature not in features:
            selected_feature = features[0]
            try:
                _spashiny_ctx.ui.update_selectize(
                    "wrapper_feature",
                    choices=features,
                    selected=selected_feature,
                    session=_spashiny_ctx.session,
                )
            except Exception:
                pass
        try:
            needs_new_app = _spashiny_ctx.dash_runtime.get(
                "app"
            ) is None or _spashiny_ctx.dash_runtime.get("adata_id") != id(adata)
            if needs_new_app:
                _spashiny_ctx.ui.notification_show(
                    "Initializing embedded Plotly / Dash. The first launch may take a little longer.",
                    type="message",
                    duration=6,
                )
                port = _spashiny_ctx.find_available_port(_spashiny_ctx.DASH_PORT)
                wrapper = _spashiny_globals.smt.pl.Wrapper(adata)
                new_dash_app, dash_proxy_prefix = _spashiny_ctx._build_dash_app_with_proxy_prefix(
                    wrapper, selected_feature, port
                )

                def run_dash(app_obj=new_dash_app, dash_port=port):
                    try:
                        app_obj.run(
                            host=_spashiny_globals.DASH_BIND_HOST,
                            port=dash_port,
                            debug=False,
                            use_reloader=False,
                        )
                    except Exception:
                        _spashiny_ctx.traceback.print_exc()

                _spashiny_globals.threading.Thread(target=run_dash, daemon=True).start()
                _spashiny_ctx.time.sleep(1.5)
                _spashiny_ctx.dash_runtime.update(
                    {
                        "app": new_dash_app,
                        "port": port,
                        "proxy_prefix": dash_proxy_prefix,
                        "feature": selected_feature,
                        "adata_id": id(adata),
                    }
                )
                _spashiny_ctx.trajectory_adata_rv.set(adata)
            else:
                _spashiny_ctx.dash_runtime["feature"] = selected_feature
                _spashiny_ctx.trajectory_adata_rv.set(adata)
            port = _spashiny_ctx.dash_runtime.get("port") or _spashiny_ctx.DASH_PORT
            dash_url = _spashiny_ctx.dash_runtime.get(
                "proxy_prefix"
            ) or _spashiny_ctx._dash_proxy_prefix(port)
            _spashiny_ctx.dash_embed_state.set(
                {
                    "status": "running",
                    "url": dash_url,
                    "message": "Embedded Dash Plotly viewer is running. Open Downstream Analysis → Dash Plotly to open it.",
                }
            )
            _spashiny_ctx.ui.notification_show(
                "Embedded Dash Plotly viewer is ready. Please open Downstream Analysis → Dash Plotly to open it.",
                type="message",
                duration=10,
            )
        except Exception as e:
            _spashiny_ctx.dash_embed_state.set(
                {"status": "error", "url": "", "message": f"Failed to start Plotly / Dash: {e}"}
            )
            _spashiny_ctx.ui.notification_show(f"Failed to start Plotly / Dash: {e}", type="error")
            _spashiny_ctx.traceback.print_exc()
        finally:
            _spashiny_ctx.ui.modal_remove()

    _spashiny_ctx.run_wrapper_plot = run_wrapper_plot
    from toi_feature_module import register_toi_feature_server

    _spashiny_ctx.register_toi_feature_server = register_toi_feature_server
    _spashiny_ctx.toi_feature_controller = _spashiny_ctx.register_toi_feature_server(
        _spashiny_ctx.input,
        _spashiny_ctx.output,
        _spashiny_ctx.session,
        adata_rv=_spashiny_ctx.trajectory_adata_rv,
        dash_state=_spashiny_ctx.dash_embed_state,
        get_input=_spashiny_ctx._native_dash_input,
        get_owner=_spashiny_ctx._require_cloud_session_id,
        get_analysis=_spashiny_ctx._cloud_analysis_session_id,
        click_guard=_spashiny_ctx._downstream_click_guard,
        show_modal=_spashiny_ctx._show_downstream_action_modal,
        colorize_plot=_spashiny_ctx.colorize_plot,
    )


_STEPS = (_install_0,)


def server(_spashiny_ctx, step=0):
    return _STEPS[step](_spashiny_ctx)
