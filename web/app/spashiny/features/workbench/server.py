# Feature workbench: original callable implementation extracted from spatialmeta_workbench_ui.py.
from spashiny._shared.feature_support import spatialmeta_workbench_ui as _feature_shared


def register_workbench(input, output, session, api):
    """api is trusted server closures; no client-provided absolute paths."""
    run_value = _feature_shared.reactive.Value(None)
    run_revision = _feature_shared.reactive.Value(0)
    sources = _feature_shared.reactive.Value({})
    notice = _feature_shared.reactive.Value(
        "Ready. Upload data or select an existing same-analysis checkpoint."
    )
    network = _feature_shared.reactive.Value(None)
    report = _feature_shared.reactive.Value(None)
    network_notice = _feature_shared.reactive.Value(
        "Create or load celltype_ST_SM annotations to begin."
    )
    pending = {"pipeline": None, "network": None, "report": None}
    network_modal = {"open": False}

    def show_network_modal():
        _feature_shared.ui.modal_show(
            _feature_shared.ui.modal(
                _feature_shared.ui.h4("Generating SpatialMETA spatial proximity network"),
                _feature_shared.ui.p(
                    "Running the original plotting function. Please wait; no model training or trajectory analysis is started."
                ),
                _feature_shared.ui.tags.div(
                    class_="spinner-border text-primary",
                    role="status",
                    **{"aria-label": "Network generation in progress"},
                ),
                title="Spatial network in progress",
                footer=None,
                easy_close=False,
            )
        )
        network_modal["open"] = True

    def close_network_modal():
        if network_modal["open"]:
            _feature_shared.ui.modal_remove()
            network_modal["open"] = False

    def scope():
        return api["scope"]()

    def store(run):
        run.assert_scope(scope())
        _feature_shared.save_run(api["root"]() / "pipeline_state.json", run)
        run_value.set(run)
        run_revision.set(run_revision.get() + 1)
        api["set_active"](run.status not in {"SUCCEEDED", "FAILED", "PAUSED"})
        if run.status == "SUCCEEDED":
            notice.set(
                "Requested main stages completed; Dash/Plotly was not started. Check the report for native downstream SUCCEEDED versus NOT_RUN: missing annotations/layers are not invented."
            )
        elif run.status == "FAILED":
            notice.set(run.error)

    def current_run():
        run_revision.get()
        run = run_value.get()
        if run is not None:
            run.assert_scope(scope())
        return run

    @_feature_shared.reactive.extended_task
    async def pipeline_task(work):
        return await work

    @_feature_shared.reactive.extended_task
    async def network_task(work):
        return await work

    @_feature_shared.reactive.extended_task
    async def report_task(work):
        return await work

    def show_progress():
        _feature_shared.ui.modal_show(
            _feature_shared.ui.modal(
                _feature_shared.ui.output_ui("one_stop_modal_body"),
                title="Single-sample workflow",
                footer=_feature_shared.ui.div(
                    _feature_shared.ui.input_action_button(
                        "one_stop_pause", "Pause after current action"
                    ),
                    _feature_shared.ui.modal_button("Keep running in background"),
                ),
                easy_close=False,
                size="l",
            )
        )

    @output
    @_feature_shared.render.ui
    def one_stop_modal_body():
        run_revision.get()
        run = run_value.get()
        if run is None:
            return _feature_shared.ui.p(notice.get())
        manual = run.status == "WAITING_FOR_MANUAL"
        if manual:
            return _feature_shared.ui.div(
                _feature_shared.ui.h4("Manual alignment - human confirmation required"),
                _feature_shared.ui.p(
                    "Adjust angle, size, flips and translation. Preview first, then confirm. Nothing is automatically matched to an unrelated example."
                ),
                _feature_shared.ui.layout_columns(
                    _feature_shared.ui.input_numeric(
                        "one_stop_angle", "Rotation (degrees)", value=0
                    ),
                    _feature_shared.ui.input_numeric(
                        "one_stop_width", "Width", value=190, min=0.001
                    ),
                    _feature_shared.ui.input_numeric(
                        "one_stop_height", "Height", value=190, min=0.001
                    ),
                    _feature_shared.ui.input_numeric("one_stop_x", "Translate X", value=0),
                    _feature_shared.ui.input_numeric("one_stop_y", "Translate Y", value=0),
                ),
                _feature_shared.ui.input_checkbox("one_stop_flip_x", "Horizontal flip"),
                _feature_shared.ui.input_checkbox("one_stop_flip_y", "Vertical flip"),
                _feature_shared.ui.input_action_button(
                    "one_stop_preview_manual", "Preview transformation"
                ),
                _feature_shared.ui.output_image("one_stop_manual_preview", height="auto"),
                _feature_shared.ui.input_action_button(
                    "one_stop_confirm_manual",
                    "Confirm this transformation and continue",
                    class_="btn btn-primary",
                ),
            )
        return _feature_shared.ui.div(
            _feature_shared.ui.h4(run.step.replace("_", " ")),
            _feature_shared.ui.tags.progress(value=run.progress, max=100, style="width:100%"),
            _feature_shared.ui.p(f"{run.progress:.1f}% of requested stages - {run.status}"),
            (
                _feature_shared.ui.p(run.error, class_="text-danger")
                if run.error
                else _feature_shared.ui.p(notice.get())
            ),
            _feature_shared.ui.p(
                "No mouse activity is required. Jobs are polled from their real status. A genuine transport or expired-session error is not hidden."
            ),
            _feature_shared.ui.tags.pre(
                _feature_shared.json.dumps(run.jobs, ensure_ascii=False, indent=2)
            ),
        )

    @output
    @_feature_shared.render.ui
    def one_stop_status():
        run_revision.get()
        run = run_value.get()
        return _feature_shared.ui.div(
            notice.get(),
            _feature_shared.ui.p(f"{run.status}: {run.step}") if run else _feature_shared.ui.div(),
        )

    @output
    @_feature_shared.render.image
    def one_stop_manual_preview():
        scope()
        _feature_shared.reactive.invalidate_later(2)
        path = api["manual_preview"]()
        return (
            {"src": str(path), "width": "100%", "alt": "Current manual ST-SM alignment preview"}
            if path
            else None
        )

    @_feature_shared.reactive.effect
    @_feature_shared.reactive.event(input.one_stop_canonical_upload)
    def upload_finished():
        payload = input.one_stop_canonical_upload() or {}
        role = str(payload.get("role") or "")
        if role not in {"st", "sm", "joint"}:
            return
        run = current_run()
        if run and run.status not in {"SUCCEEDED", "FAILED", "PAUSED"}:
            notice.set(
                "A run is active; this new upload was not adopted. Pause/finish the run before selecting another source."
            )
            return
        refs = dict(sources.get())
        refs.pop(role, None)
        if payload.get("status") == "READY":
            resolved = api["resolve_upload"](str(payload.get("upload_id") or ""), role)
            refs[role] = {
                "source": "upload",
                "upload_id": str(payload["upload_id"]),
                "filename": resolved["filename"],
            }
        sources.set(refs)

    @_feature_shared.reactive.effect
    @_feature_shared.reactive.event(input.one_stop_begin)
    def begin_run():
        try:
            previous = current_run()
            if previous and previous.status not in {"SUCCEEDED", "FAILED"}:
                raise _feature_shared.PipelineError(
                    "RUN_ALREADY_EXISTS",
                    "Resume or finish the current run; no duplicate job was submitted.",
                )
            start = str(input.one_stop_start() or "raw_pair")
            refs = dict(sources.get())
            checkpoint = api["validate_start"](start, refs) or {}
            run = _feature_shared.Run.create(scope(), start, inputs=refs)
            run.workflow_id = checkpoint.get("workflow_id", "")
            run.jobs.update(checkpoint.get("jobs", {}))
            run.parameters = api["parameters"]()
            store(run)
            notice.set(
                "Input validation is starting. Progress reflects completed stages and actual backend jobs."
            )
            show_progress()
        except Exception as exc:
            notice.set(api["error"](exc))
            _feature_shared.ui.notification_show(notice.get(), type="error", duration=12)

    @_feature_shared.reactive.effect
    @_feature_shared.reactive.event(input.one_stop_show_progress)
    def show_run():
        scope()
        show_progress()

    @_feature_shared.reactive.effect
    @_feature_shared.reactive.event(input.one_stop_pause)
    def pause_run():
        try:
            run = current_run()
            if run:
                run.pause()
                store(run)
                notice.set(
                    "Orchestration paused. Already submitted jobs continue under the normal session lifecycle."
                )
        except Exception as exc:
            notice.set(api["error"](exc))

    @_feature_shared.reactive.effect
    @_feature_shared.reactive.event(input.one_stop_resume)
    def resume_run():
        try:
            run = current_run()
            if run is None:
                run = _feature_shared.load_run(api["root"]() / "pipeline_state.json", scope())
            api["validate_resume"](run)
            run.resume()
            store(run)
            show_progress()
        except Exception as exc:
            notice.set(api["error"](exc))

    def accept_receipt(run, result):
        if result.get("workflow_id"):
            run.workflow_id = result["workflow_id"]
        if result.get("job_id"):
            run.submitted(result["job_id"])
        else:
            run.succeed(result.get("evidence"))
        store(run)

    def dispatch(run, *, manual=None):
        result = api["dispatch"](run, manual=manual)
        if "background" in result:
            pending["pipeline"] = (run.run_id, run.step, result["commit"])
            pipeline_task.invoke(result["background"])
        else:
            accept_receipt(run, result)

    @_feature_shared.reactive.effect
    def pipeline_finished():
        try:
            value = pipeline_task.result()
        except _feature_shared.SilentException:
            raise
        except Exception as exc:
            with _feature_shared.reactive.isolate():
                run = current_run()
                if run:
                    run.fail(api["error"](exc))
                    store(run)
            return
        with _feature_shared.reactive.isolate():
            run = current_run()
            receipt = pending["pipeline"]
            if not run or not receipt or (run.run_id, run.step) != receipt[:2]:
                return
            try:
                accept_receipt(run, receipt[2](value))
            except Exception as exc:
                run.fail(api["error"](exc))
                store(run)
            finally:
                pending["pipeline"] = None

    @_feature_shared.reactive.effect
    def poll_run():
        _feature_shared.reactive.invalidate_later(2)
        with _feature_shared.reactive.isolate():
            try:
                run = current_run()
                if not run or run.status in {
                    "SUCCEEDED",
                    "FAILED",
                    "PAUSED",
                    "DISPATCHING",
                    "WAITING_FOR_MANUAL",
                }:
                    return
                if run.status == "WAITING_FOR_JOB":
                    observation = api["observe"](run)
                    ready = run.observe(scope=scope(), **observation)
                    if ready:
                        evidence = api["accept_artifacts"](run)
                        run.succeed(evidence)
                    store(run)
                elif run.begin():
                    store(run)
                    dispatch(run)
                else:
                    store(run)
                    show_progress()
            except Exception as exc:
                run = run_value.get()
                if run:
                    run.fail(api["error"](exc))
                    run_value.set(run)
                    api["set_active"](False)
                    run_revision.set(run_revision.get() + 1)

    def manual_values():
        return {
            "rotation": float(input.one_stop_angle() or 0),
            "scale_width": float(input.one_stop_width() or 190),
            "scale_height": float(input.one_stop_height() or 190),
            "translation_x": float(input.one_stop_x() or 0),
            "translation_y": float(input.one_stop_y() or 0),
            "horizontal_flip": bool(input.one_stop_flip_x()),
            "vertical_flip": bool(input.one_stop_flip_y()),
            "mode": "overlay",
        }

    @_feature_shared.reactive.effect
    @_feature_shared.reactive.event(input.one_stop_preview_manual)
    def preview_manual():
        try:
            run = current_run()
            if run and run.status == "WAITING_FOR_MANUAL":
                api["preview_manual"](manual_values())
        except Exception as exc:
            notice.set(api["error"](exc))
            _feature_shared.ui.notification_show(notice.get(), type="error", duration=10)

    @_feature_shared.reactive.effect
    @_feature_shared.reactive.event(input.one_stop_confirm_manual)
    def confirm_manual():
        run = current_run()
        try:
            if run is None:
                return
            params = manual_values()
            api["validate_manual"](params)
            api["manual_ready"](params)
            run.confirm_manual()
            store(run)
            dispatch(run, manual=params)
            show_progress()
        except Exception as exc:
            if run:
                if run.status == "WAITING_FOR_MANUAL":
                    notice.set(api["error"](exc))
                    _feature_shared.ui.notification_show(notice.get(), type="error", duration=10)
                else:
                    run.fail(api["error"](exc))
                    store(run)

    @_feature_shared.reactive.effect
    @_feature_shared.reactive.event(input.run_native_spatial_network)
    def run_network():
        started = False
        try:
            scope()
            if pending["network"]:
                raise _feature_shared.PipelineError(
                    "NETWORK_BUSY", "A network export is already running."
                )
            task = api["prepare_network"](
                {
                    "top_n_neighbors": int(input.native_network_neighbors() or 3),
                    "edge_weight_threshold": float(input.native_network_threshold()),
                    "node_use_scale": bool(input.native_network_node_scale()),
                    "edge_use_scale": bool(input.native_network_edge_scale()),
                    "split_by": None if input.native_network_split() == "none" else "auto",
                }
            )
            pending["network"] = (scope(), task["commit"])
            started = True
            network.set(None)
            network_notice.set(
                "Running the original spatialmeta.pl.plot_network in an isolated child; Shiny remains responsive."
            )
            show_network_modal()
            network_task.invoke(task["background"])
        except Exception as exc:
            network_notice.set(api["error"](exc))
            if started:
                pending["network"] = None
                close_network_modal()
            elif not pending["network"]:
                close_network_modal()

    @_feature_shared.reactive.effect
    def network_finished():
        try:
            value = network_task.result()
        except _feature_shared.SilentException:
            raise
        except Exception as exc:
            with _feature_shared.reactive.isolate():
                pending["network"] = None
                network_notice.set(api["error"](exc))
                close_network_modal()
            return
        with _feature_shared.reactive.isolate():
            task = pending["network"]
            pending["network"] = None
            try:
                if not task or task[0] != scope():
                    return
                network.set(task[1](value))
                network_notice.set(
                    "Complete: original SpatialMETA network. PDF/SVG contain editable paths and text."
                )
            except Exception as exc:
                network.set(None)
                network_notice.set(api["error"](exc))
            finally:
                close_network_modal()

    @output
    @_feature_shared.render.ui
    def native_network_status():
        return _feature_shared.ui.p(network_notice.get())

    @output
    @_feature_shared.render.image
    def native_network_preview():
        result = network.get()
        if result and api["network_current"](result):
            return {
                "src": str(result["root"] / "spatial_network.png"),
                "alt": "Native SpatialMETA spatial network",
                "width": 720,
            }
        return None

    def download_network(filename):
        scope()
        value = network.get()
        if not value or not api["network_current"](value):
            raise _feature_shared.PipelineError(
                "NETWORK_NOT_READY", "Generate a network for the current data/annotation first."
            )
        return (value["root"] / filename).read_bytes()

    @output
    @_feature_shared.render.download(filename="spatial_network.pdf")
    def download_native_network_pdf():
        yield download_network("spatial_network.pdf")

    @output
    @_feature_shared.render.download(filename="spatial_network.svg")
    def download_native_network_svg():
        yield download_network("spatial_network.svg")

    @output
    @_feature_shared.render.download(filename="network_edges.csv")
    def download_native_network_edges():
        yield download_network("network_edges.csv")

    @output
    @_feature_shared.render.download(filename="network_nodes.csv")
    def download_native_network_nodes():
        yield download_network("network_nodes.csv")

    @_feature_shared.reactive.effect
    @_feature_shared.reactive.event(input.create_ai_result_report)
    def create_report():
        try:
            if pending["report"]:
                raise _feature_shared.PipelineError(
                    "REPORT_BUSY", "A report is already being generated."
                )
            task = api["prepare_report"](current_run())
            pending["report"] = (scope(), task["commit"])
            report.set(None)
            report_task.invoke(task["background"])
        except Exception as exc:
            notice.set(api["error"](exc))

    @_feature_shared.reactive.effect
    def report_finished():
        try:
            value = report_task.result()
        except _feature_shared.SilentException:
            raise
        except Exception as exc:
            with _feature_shared.reactive.isolate():
                pending["report"] = None
                notice.set(api["error"](exc))
            return
        with _feature_shared.reactive.isolate():
            task = pending["report"]
            pending["report"] = None
            if task and task[0] == scope():
                report.set(task[1](value))
                notice.set(
                    "AI-readable report is ready for download. No external AI service was contacted."
                )

    @output
    @_feature_shared.render.text
    def ai_result_report_status():
        return (
            "Report ready."
            if report.get()
            else "Prepare a report after an analysis has produced results."
        )

    def report_bytes():
        scope()
        value = report.get() or api["existing_report"](current_run())
        if not value:
            raise _feature_shared.PipelineError(
                "REPORT_NOT_READY", "No report has been generated for this analysis."
            )
        return _feature_shared.Path(value).read_bytes()

    @output
    @_feature_shared.render.download(filename="analysis_report.zip")
    def download_one_stop_report():
        yield report_bytes()

    @output
    @_feature_shared.render.download(filename="analysis_report.zip")
    def download_ai_result_report():
        yield report_bytes()

    @session.on_ended
    def stop_owned_children():
        pipeline_task.cancel()
        network_task.cancel()
        report_task.cancel()


server = register_workbench
