# Extracted from /app/app/ST-SM.py. Feature: plot_appearance; ordered phases preserve original initialization.
from spashiny._shared import runtime_globals as _spashiny_globals


def _install_0(_spashiny_ctx):

    def _is_alignment_worker_color_plot(plot_id):
        return str(plot_id or "") in _spashiny_ctx.ALIGNMENT_WORKER_COLOR_PLOTS

    _spashiny_ctx._is_alignment_worker_color_plot = _is_alignment_worker_color_plot

    def _alignment_color_title(plot_id):
        cfg = _spashiny_ctx.ALIGNMENT_WORKER_COLOR_PLOTS.get(str(plot_id or "")) or {}
        return str(cfg.get("title") or _spashiny_globals.humanize_plot_id(plot_id))

    _spashiny_ctx._alignment_color_title = _alignment_color_title

    def _alignment_fallback_color_spec(plot_id):
        cfg = _spashiny_ctx.ALIGNMENT_WORKER_COLOR_PLOTS.get(str(plot_id or "")) or {}
        spec = cfg.get("fallback_spec") or {"colors": [], "colormap": None}
        return _spashiny_ctx.json.loads(_spashiny_ctx.json.dumps(spec, ensure_ascii=True))

    _spashiny_ctx._alignment_fallback_color_spec = _alignment_fallback_color_spec

    def _register_alignment_worker_color_spec(plot_id, spec=None):
        plot_id = str(plot_id or "")
        if not _spashiny_ctx._is_alignment_worker_color_plot(plot_id):
            return
        _spashiny_ctx.generated_color_plots.add(plot_id)
        if not spec:
            spec = _spashiny_ctx.plot_color_specs.get(
                plot_id
            ) or _spashiny_ctx._alignment_fallback_color_spec(plot_id)
        if isinstance(spec, dict):
            _spashiny_ctx.plot_color_specs[plot_id] = spec

    _spashiny_ctx._register_alignment_worker_color_spec = _register_alignment_worker_color_spec

    def _refresh_alignment_worker_color_spec(plot_id):
        if not _spashiny_ctx._is_alignment_worker_color_plot(plot_id):
            return
        try:
            spec = _spashiny_ctx._alignment_worker_color_spec_from_current_result(plot_id)
        except Exception:
            spec = None
        _spashiny_ctx._register_alignment_worker_color_spec(plot_id, spec)

    _spashiny_ctx._refresh_alignment_worker_color_spec = _refresh_alignment_worker_color_spec

    def _color_picker_tag(picker_id, text_id, value):
        value = _spashiny_globals.normalize_color(value, "#157B9B")
        return _spashiny_ctx.ui.tags.input(
            id=picker_id,
            type="color",
            value=value,
            style="width:100%; height:38px; padding:2px; border:1px solid #d0d7de; border-radius:8px;",
            oninput=f"const target=document.getElementById('{text_id}');if(target){{target.value=this.value;target.dispatchEvent(new Event('input',{{bubbles:true}}));target.dispatchEvent(new Event('change',{{bubbles:true}}));}}if(window.Shiny){{Shiny.setInputValue('{text_id}', this.value, {{priority:'event'}});}}",
        )

    _spashiny_ctx._color_picker_tag = _color_picker_tag

    def _palette_input_row(prefix, index, label, current):
        text_id = f"{prefix}_{index}"
        picker_id = f"{text_id}_picker"
        fixed_id = f"{text_id}_fixed"
        return _spashiny_ctx.ui.div(
            _spashiny_ctx.ui.input_text(
                text_id, label, value=_spashiny_globals.normalize_color(current, "#157B9B")
            ),
            _spashiny_ctx._color_picker_tag(picker_id, text_id, current),
            _spashiny_ctx.ui.input_select(
                fixed_id, "Fixed colors", choices=_spashiny_globals.FIXED_COLORS, selected=""
            ),
            style="display:grid; grid-template-columns: minmax(150px,1fr) 74px minmax(150px,1fr); gap:10px; align-items:end; margin-bottom:10px;",
        )

    _spashiny_ctx._palette_input_row = _palette_input_row

    def _current_modal_colors(plot_id, spec):
        settings_map = _spashiny_ctx.plot_color_settings.get() or {}
        settings = settings_map.get(plot_id) or settings_map.get("__global__") or {}
        base_colors = [item.get("color") for item in spec.get("colors", [])]
        colors = settings.get("colors") if settings else None
        current_colors = _spashiny_globals.expand_color_list(
            colors or base_colors, len(base_colors), base_colors
        )
        current_cmap = settings.get("colormap") or spec.get("colormap") or []
        current_cmap = (
            _spashiny_globals.expand_color_list(current_cmap, len(current_cmap), current_cmap)
            if current_cmap
            else []
        )
        return (current_colors, current_cmap)

    _spashiny_ctx._current_modal_colors = _current_modal_colors

    def _show_color_modal(plot_id):
        if _spashiny_ctx._alignment_modal_is_blocking():
            _spashiny_ctx.log(
                "Adjust Colors is temporarily unavailable while an Alignment workflow step is running or awaiting acknowledgement."
            )
            _spashiny_ctx.ui.notification_show(
                "Close the current Alignment workflow modal before adjusting colors.",
                type="warning",
                duration=6,
            )
            return
        _spashiny_ctx.active_color_plot.set(plot_id)
        if _spashiny_ctx._is_alignment_worker_color_plot(plot_id):
            _spashiny_ctx._refresh_alignment_worker_color_spec(plot_id)
        if plot_id not in _spashiny_ctx.generated_color_plots:
            _spashiny_ctx.ui.modal_show(
                _spashiny_ctx.ui.modal(
                    _spashiny_ctx.ui.h4(
                        f"Adjust Colors - {_spashiny_ctx._alignment_color_title(plot_id)}"
                        if _spashiny_ctx._is_alignment_worker_color_plot(plot_id)
                        else "Adjust Colors"
                    ),
                    _spashiny_ctx.ui.p("Please generate the plot first."),
                    footer=_spashiny_ctx.ui.modal_button("Close"),
                    easy_close=True,
                )
            )
            return
        spec = _spashiny_ctx.plot_color_specs.get(plot_id) or {"colors": [], "colormap": None}
        current_colors, current_cmap = _spashiny_ctx._current_modal_colors(plot_id, spec)
        preset_choices = {"custom": "Manual colors", "original": "Original plot colors"}
        preset_choices.update(
            {name: preset["label"] for name, preset in _spashiny_globals.COLOR_PRESETS.items()}
        )
        color_rows = [
            _spashiny_ctx._palette_input_row(
                "plot_color_item",
                idx,
                f"{idx + 1}. {item.get('label') or 'Color'}",
                current_colors[idx],
            )
            for idx, item in enumerate(spec.get("colors", []))
        ]
        cmap_labels = ["Colormap low", "Colormap middle", "Colormap high"]
        cmap_rows = [
            _spashiny_ctx._palette_input_row(
                "plot_cmap_item",
                idx,
                cmap_labels[idx] if idx < len(cmap_labels) else f"Colormap {idx + 1}",
                color,
            )
            for idx, color in enumerate(current_cmap)
        ]
        body_rows = []
        if color_rows:
            body_rows.extend([_spashiny_ctx.ui.h5("Discrete / category colors"), *color_rows])
        if cmap_rows:
            body_rows.extend(
                [_spashiny_ctx.ui.hr(), _spashiny_ctx.ui.h5("Continuous colormap"), *cmap_rows]
            )
        if not body_rows:
            body_rows.append(
                _spashiny_ctx.ui.p("No adjustable colors were detected for this plot.")
            )
        _spashiny_ctx.ui.modal_show(
            _spashiny_ctx.ui.modal(
                _spashiny_ctx.ui.h4(
                    f"Adjust Colors - {(_spashiny_ctx._alignment_color_title(plot_id) if _spashiny_ctx._is_alignment_worker_color_plot(plot_id) else _spashiny_globals.humanize_plot_id(plot_id))}"
                ),
                _spashiny_ctx.ui.input_select(
                    "plot_color_preset", "Preset palette", choices=preset_choices, selected="custom"
                ),
                _spashiny_ctx.ui.div(
                    *body_rows, style="max-height:58vh; overflow-y:auto; padding-right:8px;"
                ),
                _spashiny_ctx.ui.input_checkbox(
                    "plot_color_apply_all", "Apply to all generated plots", value=False
                ),
                footer=_spashiny_ctx.ui.div(
                    _spashiny_ctx.ui.input_action_button(
                        "apply_plot_color_palette", "Apply Colors", class_="btn btn-primary"
                    ),
                    _spashiny_ctx.ui.input_action_button(
                        "reset_plot_color_palette",
                        "Reset Default",
                        class_="btn btn-outline-secondary",
                    ),
                    _spashiny_ctx.ui.modal_button("Close"),
                    style="display:flex; gap:10px; justify-content:flex-end;",
                ),
                size="l",
                easy_close=True,
            )
        )

    _spashiny_ctx._show_color_modal = _show_color_modal

    def _read_modal_color(prefix, index, fallback):
        try:
            fixed = getattr(_spashiny_ctx.input, f"{prefix}_{index}_fixed")()
        except Exception:
            fixed = ""
        try:
            text = getattr(_spashiny_ctx.input, f"{prefix}_{index}")()
        except Exception:
            text = ""
        return _spashiny_globals.normalize_color(fixed or text, fallback)

    _spashiny_ctx._read_modal_color = _read_modal_color

    def _modal_settings_from_inputs(global_scope=False):
        plot_id = _spashiny_ctx.active_color_plot.get()
        spec = _spashiny_ctx.plot_color_specs.get(plot_id) or {"colors": [], "colormap": None}
        base_colors = [item.get("color") for item in spec.get("colors", [])]
        base_cmap = spec.get("colormap") or []
        preset = _spashiny_ctx.input.plot_color_preset() or "custom"
        if preset == "original":
            colors = base_colors
            cmap = base_cmap
        elif preset in _spashiny_globals.COLOR_PRESETS:
            colors = _spashiny_globals.preset_colors_for_count(preset, len(base_colors))
            cmap = _spashiny_globals.preset_colormap(preset) if base_cmap else []
        else:
            colors = [
                _spashiny_ctx._read_modal_color("plot_color_item", idx, fallback)
                for idx, fallback in enumerate(base_colors)
            ]
            cmap = [
                _spashiny_ctx._read_modal_color("plot_cmap_item", idx, fallback)
                for idx, fallback in enumerate(base_cmap)
            ]
        return _spashiny_globals.settings_from_color_spec(
            spec, colors=colors, colormap=cmap, global_scope=global_scope
        )

    _spashiny_ctx._modal_settings_from_inputs = _modal_settings_from_inputs

    def colorize_plot(plot_id, fig):
        _spashiny_ctx.plot_color_revision.get()
        settings_map = _spashiny_ctx.plot_color_settings.get() or {}
        if _spashiny_ctx._is_alignment_worker_color_plot(plot_id):
            if fig is not None and (not _spashiny_globals.figure_looks_empty(fig)):
                _spashiny_ctx._refresh_alignment_worker_color_spec(plot_id)
            return fig
        if fig is not None and (not _spashiny_globals.figure_looks_empty(fig)):
            _spashiny_ctx.generated_color_plots.add(plot_id)
            _spashiny_ctx.plot_color_specs[plot_id] = (
                _spashiny_globals.extract_color_spec_from_figure(fig)
            )
        settings = settings_map.get(plot_id) or settings_map.get("__global__")
        if not settings:
            return fig
        return _spashiny_globals.apply_color_settings_to_figure(
            _spashiny_globals.clone_figure(fig),
            settings,
            _spashiny_ctx.plot_color_specs.get(plot_id),
        )

    _spashiny_ctx.colorize_plot = colorize_plot

    def plot_colorized(plot_id):

        def decorator(func):

            @_spashiny_globals.functools.wraps(func)
            def wrapper(*args, **kwargs):
                return _spashiny_ctx.colorize_plot(plot_id, func(*args, **kwargs))

            return wrapper

        return decorator

    _spashiny_ctx.plot_colorized = plot_colorized

    def _register_palette_button(plot_id):

        @_spashiny_ctx.reactive.Effect
        @_spashiny_ctx.reactive.event(getattr(_spashiny_ctx.input, f"palette_{plot_id}"))
        def _open_palette_modal():
            _spashiny_ctx._show_color_modal(plot_id)

    _spashiny_ctx._register_palette_button = _register_palette_button
    for _spashiny_ctx._plot_id in _spashiny_globals.PLOT_COLOR_IDS:
        _spashiny_ctx._register_palette_button(_spashiny_ctx._plot_id)

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.alignment_palette_request)
    def _open_alignment_palette_request():
        try:
            payload = _spashiny_ctx.input.alignment_palette_request()
        except Exception:
            payload = None
        if isinstance(payload, dict):
            plot_id = str(payload.get("plot_id") or "")
        else:
            plot_id = str(payload or "")
        if not _spashiny_ctx._is_alignment_worker_color_plot(plot_id):
            return
        _spashiny_ctx._show_color_modal(plot_id)

    _spashiny_ctx._open_alignment_palette_request = _open_alignment_palette_request

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.apply_plot_color_palette)
    def _apply_plot_color_palette():
        plot_id = _spashiny_ctx.active_color_plot.get()
        if not plot_id:
            return
        settings_map = dict(_spashiny_ctx.plot_color_settings.get() or {})
        try:
            apply_all = bool(_spashiny_ctx.input.plot_color_apply_all())
        except Exception:
            apply_all = False
        new_settings = _spashiny_ctx._modal_settings_from_inputs(global_scope=apply_all)
        if _spashiny_ctx._is_alignment_worker_color_plot(plot_id):
            try:
                _spashiny_ctx._submit_alignment_worker_color_rerender(plot_id, new_settings)
            except Exception as exc:
                _spashiny_ctx.log(f"Alignment color re-render submit failed for {plot_id}: {exc}")
                _spashiny_ctx.ui.notification_show(
                    _spashiny_globals.user_facing_error(
                        "Failed to submit Alignment color render", exc
                    ),
                    type="error",
                    duration=10,
                )
            finally:
                _spashiny_ctx.ui.modal_remove()
            return
        if apply_all:
            settings_map["__global__"] = new_settings
        else:
            settings_map[plot_id] = new_settings
        _spashiny_ctx.plot_color_settings.set(settings_map)
        _spashiny_ctx.plot_color_revision.set(_spashiny_ctx.plot_color_revision.get() + 1)
        _spashiny_ctx.ui.modal_remove()
        _spashiny_ctx.ui.notification_show("Plot colors updated.", type="message")

    _spashiny_ctx._apply_plot_color_palette = _apply_plot_color_palette

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.reset_plot_color_palette)
    def _reset_plot_color_palette():
        plot_id = _spashiny_ctx.active_color_plot.get()
        settings_map = dict(_spashiny_ctx.plot_color_settings.get() or {})
        try:
            apply_all = bool(_spashiny_ctx.input.plot_color_apply_all())
        except Exception:
            apply_all = False
        if apply_all:
            settings_map.pop("__global__", None)
        elif plot_id:
            settings_map.pop(plot_id, None)
        if _spashiny_ctx._is_alignment_worker_color_plot(plot_id):
            try:
                _spashiny_ctx._submit_alignment_worker_color_rerender(plot_id, {})
            except Exception as exc:
                _spashiny_ctx.log(f"Alignment color reset submit failed for {plot_id}: {exc}")
                _spashiny_ctx.ui.notification_show(
                    _spashiny_globals.user_facing_error(
                        "Failed to submit Alignment color reset", exc
                    ),
                    type="error",
                    duration=10,
                )
            finally:
                _spashiny_ctx.ui.modal_remove()
            return
        _spashiny_ctx.plot_color_settings.set(settings_map)
        _spashiny_ctx.plot_color_revision.set(_spashiny_ctx.plot_color_revision.get() + 1)
        _spashiny_ctx.ui.modal_remove()
        _spashiny_ctx.ui.notification_show("Plot colors reset to defaults.", type="message")

    _spashiny_ctx._reset_plot_color_palette = _reset_plot_color_palette

    @_spashiny_ctx.output
    @_spashiny_ctx.render.ui
    def ssh_top_status():
        if _spashiny_globals.SPASHINY_WEB_PLATFORM:
            return _spashiny_ctx.ui.tags.div(
                _spashiny_ctx.ui.tags.span("Control Plane", class_="cloud-status-pill ok"),
                _spashiny_ctx.ui.tags.span("CPU Pool", class_="cloud-status-pill"),
                _spashiny_ctx.ui.tags.span("GPU Pool", class_="cloud-status-pill"),
                _spashiny_ctx.ui.tags.span(
                    "Local Storage" if _spashiny_globals.SPASHINY_LAB_PROFILE else "R2 Storage",
                    class_="cloud-status-pill",
                ),
                _spashiny_ctx.ui.tags.span("Job Queue", class_="cloud-status-pill"),
                class_="cloud-top-status",
            )
        st = _spashiny_ctx.ssh_state.get()
        return _spashiny_globals.ssh_status_indicator_ui(
            st.get("status", "local"), st.get("host", ""), st.get("username", "")
        )

    _spashiny_ctx.ssh_top_status = ssh_top_status


_STEPS = (_install_0,)


def server(_spashiny_ctx, step=0):
    return _STEPS[step](_spashiny_ctx)
