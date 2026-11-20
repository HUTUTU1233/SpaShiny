# Feature toi: original callable implementation extracted from toi_feature_module.py.
from spashiny._shared.feature_support import toi_feature_module as _feature_shared


def register_toi_feature_server(
    input,
    output,
    session,
    *,
    adata_rv,
    dash_state,
    get_input,
    get_owner,
    get_analysis,
    click_guard,
    show_modal,
    colorize_plot,
):
    """All operations resolve the current viewer; no owner-only/old-result fallback."""
    results = {
        name: _feature_shared.reactive.Value(None)
        for name in ("arrow", "gene_heatmap", "mz_heatmap", "gene_curve", "mz_curve")
    }
    selection_revision = _feature_shared.reactive.Value(0)
    last_scope = _feature_shared.reactive.Value(None)
    last_key = _feature_shared.reactive.Value(None)

    def value(name, default=None):
        try:
            result = getattr(input, name)()
            return default if result is None else result
        except Exception:
            return default

    def clear():
        import matplotlib.pyplot as plt

        with _feature_shared.reactive.isolate(), _feature_shared.PLOT_LOCK:
            for state in results.values():
                stored = state.get()
                if stored:
                    plt.close(stored["figure"])
                state.set(None)

    session.on_ended(clear)

    def context(require_key=True):
        from cloud.native_dash_runtime import get_viewer
        from cloud.database import CloudDatabase

        state = dash_state.get() or {}
        owner = str(get_owner() or "")
        analysis = str(get_analysis() or "")
        adata = adata_rv.get()
        viewer = get_viewer(state.get("viewer_id"))
        if (
            state.get("status") != "native"
            or not owner
            or (not analysis)
            or (adata is None)
            or (viewer is None)
            or (viewer.owner_id != owner)
            or (viewer.analysis_id != analysis)
            or (state.get("analysis_id") != analysis)
            or (state.get("data_id") != id(get_input()))
            or (viewer.wrapper.adata is not adata)
        ):
            raise ValueError(
                "Open SpatialMETA Dash for the current analysis input, draw a TOI, then refresh the TOI list. A previous input's TOI cannot be reused."
            )
        record = CloudDatabase(read_only=True).get_analysis_session(
            analysis, owner_session_id=owner
        )
        if record.get("status") != "ACTIVE":
            raise ValueError(
                "This analysis is no longer active. Start a new analysis and load its input."
            )
        scope = (owner, analysis, viewer.viewer_id, state["data_id"], id(adata))
        if not require_key:
            return (adata, str(value("traj_selected_key", "") or ""), scope)
        key = str(value("traj_selected_key", "") or "")
        if key not in _feature_shared.list_trajectory_keys(adata):
            raise ValueError("Select an existing TOI after refreshing the TOI list.")
        fingerprint = _feature_shared.trajectory_fingerprint(adata, key)
        return (adata, key, (*scope, key, fingerprint))

    def parameters(kind):
        if kind in {"gene_curve", "mz_curve"}:
            field = "traj_features" if kind == "gene_curve" else "toi_mz_features"
            selected = value(field, []) or []
            if isinstance(selected, str):
                selected = [selected]
            return {
                "features": list(selected),
                "bins": int(value("traj_bins", 100)),
                "scale": bool(value("traj_scale", True)),
            }
        if kind in {"gene_heatmap", "mz_heatmap"}:
            gene = kind == "gene_heatmap"
            prefix = "native_gene_clustermap_" if gene else "native_mz_clustermap_"
            return {
                "feature_top": int(value(prefix + "top", 10 if gene else 20)),
                "window_size": int(value(prefix + "window", 1000 if gene else 300)),
            }
        return {}

    def current_result(kind, required=False):
        stored = results[kind].get()
        if not stored:
            if required:
                raise ValueError("Generate this figure for the current TOI before downloading it.")
            return None
        try:
            _, _, signature = context()
            valid = stored["signature"] == signature and stored["parameters"] == parameters(kind)
        except Exception:
            valid = False
        if not valid:
            if required:
                raise ValueError(
                    "The TOI, input, or plotting settings changed. Generate this figure again; a previous result will not be exported."
                )
            return None
        return stored

    def refresh_choices(notify=False):
        try:
            adata, selected, _ = context(require_key=False)
            keys = _feature_shared.list_trajectory_keys(adata)
            selected = selected if selected in keys else keys[0] if keys else None
            _feature_shared.ui.update_selectize(
                "traj_selected_key", choices=keys, selected=selected, session=session
            )
            for field, modality in (("traj_features", "ST"), ("toi_mz_features", "SM")):
                choices = _feature_shared.list_feature_choices(adata, modality)
                existing = value(field, []) or []
                if isinstance(existing, str):
                    existing = [existing]
                _feature_shared.ui.update_selectize(
                    field,
                    choices=choices,
                    selected=[name for name in existing if name in choices],
                    session=session,
                )
            if notify and (not keys):
                _feature_shared.ui.notification_show(
                    "No TOI was found. Draw an open path in SpatialMETA Dash and wait for its success message first.",
                    type="warning",
                )
        except Exception as exc:
            _feature_shared.ui.update_selectize(
                "traj_selected_key", choices=[], selected=None, session=session
            )
            for field in ("traj_features", "toi_mz_features"):
                _feature_shared.ui.update_selectize(field, choices=[], selected=[], session=session)
            if notify:
                _feature_shared.ui.notification_show(str(exc), type="error", duration=10)

    @_feature_shared.reactive.effect
    def _sync_viewer_scope():
        try:
            _, _, scope = context(require_key=False)
        except Exception:
            scope = None
        with _feature_shared.reactive.isolate():
            old = last_scope.get()
        if scope != old:
            clear()
            last_scope.set(scope)
            last_key.set(None)
            refresh_choices()
        if scope is None and adata_rv.get() is not None:
            adata_rv.set(None)

    @_feature_shared.reactive.effect
    @_feature_shared.reactive.event(input.btn_refresh_toi)
    def _refresh_toi():
        if not click_guard("btn_refresh_toi", "Refresh TOI list", window_seconds=1):
            return
        refresh_choices(notify=True)
        selection_revision.set(selection_revision.get() + 1)

    @_feature_shared.reactive.effect
    def _selection_changed():
        selection_revision.get()
        try:
            _, _, signature = context()
        except Exception:
            signature = None
        with _feature_shared.reactive.isolate():
            old = last_key.get()
        if signature != old:
            clear()
            last_key.set(signature)

    @output
    @_feature_shared.render.ui
    def toi_current_selection():
        selection_revision.get()
        try:
            adata, key, _ = context()
            count = len(adata.uns["trajectory"][key]["indices"])
            return _feature_shared.ui.p(
                f"Selected TOI: {key} | {count:,} spots. Spatial arrows and feature curves use this path. Native clustermaps preserve the current input row order.",
                class_="apple-muted",
            )
        except Exception:
            return _feature_shared.ui.p(
                "Draw a TOI in Dash, refresh the list, and select it. Existing TOIs are not recomputed.",
                class_="apple-muted",
            )

    def run(kind, button, title):
        if not click_guard(button, title):
            return
        results[kind].set(None)
        show_modal(
            title,
            "Rendering the selected TOI from the existing normalized data. No model, trajectory, or differential ranking is recomputed.",
        )
        figure = None
        try:
            import numpy as np
            import matplotlib.pyplot as plt
            import spatialmeta as smt
            import seaborn as sns

            adata, key, signature = context()
            params = parameters(kind)
            if kind == "arrow":
                entry = adata.uns["trajectory"][key]
                with _feature_shared.PLOT_LOCK:
                    adata.obs[key] = -1.0
                    adata.obs.iloc[
                        np.asarray(entry["indices"], dtype=int), adata.obs.columns.get_loc(key)
                    ] = np.asarray(entry["locations"], dtype=float)
                    figure, ax = plt.subplots(figsize=(8, 6))
                    smt.pl.plot_trajectory_with_arrows(
                        adata,
                        path_key=key,
                        color=key,
                        fig=figure,
                        ax=ax,
                        color_map=sns.light_palette("#157B9B", as_cmap=True),
                    )
            elif kind in {"gene_curve", "mz_curve"}:
                figure = _feature_shared.build_feature_trajectory_figure(
                    adata, key, modality="ST" if kind == "gene_curve" else "SM", **params
                )
            elif kind in {"gene_heatmap", "mz_heatmap"}:
                figure = _feature_shared.build_native_clustermap_figure(
                    adata, "ST" if kind == "gene_heatmap" else "SM", **params
                )
            with _feature_shared.PLOT_LOCK:
                plt.close(figure)
            if context()[2] != signature:
                raise ValueError(
                    "The selected TOI changed while rendering. Generate the figure again."
                )
            results[kind].set({"figure": figure, "signature": signature, "parameters": params})
            _feature_shared.ui.notification_show(f"{title} completed for {key}.", type="message")
        except Exception as exc:
            if figure is not None:
                import matplotlib.pyplot as plt

                plt.close(figure)
            results[kind].set(None)
            _feature_shared.ui.notification_show(
                f"{title} failed: {type(exc).__name__}: {exc}", type="error", duration=14
            )
            _feature_shared.traceback.print_exc()
        finally:
            _feature_shared.ui.modal_remove()

    def bind_button(kind, button, title):

        @_feature_shared.reactive.effect
        @_feature_shared.reactive.event(getattr(input, button))
        def generate():
            run(kind, button, title)

        return generate

    bound = [
        bind_button(*args)
        for args in (
            ("arrow", "btn_run_traj_register", "TOI Spatial Arrow Plot"),
            ("gene_heatmap", "btn_toi_gene_heatmap", "Native Gene Clustermap"),
            ("mz_heatmap", "btn_toi_mz_heatmap", "Native m/z Clustermap"),
            ("gene_curve", "btn_run_feature_traj", "Gene Feature Trajectory"),
            ("mz_curve", "btn_toi_mz_feature", "m/z Feature Trajectory"),
        )
    ]

    def bind_plot(kind, output_id):

        @output(id=output_id)
        @_feature_shared.render.plot
        def show():
            selection_revision.get()
            stored = current_result(kind)
            if stored:
                return _feature_shared.build_preview_image(
                    colorize_plot(output_id, stored["figure"])
                )
            import matplotlib.pyplot as plt

            with _feature_shared.PLOT_LOCK:
                figure, ax = plt.subplots(figsize=(8, 4))
                ax.text(
                    0.5,
                    0.5,
                    "Select a TOI and generate this figure.\nChanged inputs or settings invalidate previous results.",
                    ha="center",
                    va="center",
                    transform=ax.transAxes,
                )
                ax.axis("off")
            image = _feature_shared.build_preview_image(figure)
            plt.close(figure)
            return image

        return show

    bound.extend(
        (
            bind_plot(*args)
            for args in (
                ("arrow", "traj_arrow_plot"),
                ("gene_heatmap", "toi_gene_heatmap"),
                ("mz_heatmap", "toi_mz_heatmap"),
                ("gene_curve", "traj_feature_plot"),
                ("mz_curve", "toi_mz_feature_plot"),
            )
        )
    )

    def bind_download(kind, download_id, extension, output_id):

        def download():
            from cloud.figure_export import figure_bytes

            stored = current_result(kind, required=True)
            with _feature_shared.PLOT_LOCK:
                payload = figure_bytes(colorize_plot(output_id, stored["figure"]), format=extension)
            yield payload

        download.__name__ = download_id
        return _feature_shared.render.download(
            filename=lambda: f"{str(value('traj_selected_key', 'TOI'))}_{kind}.{extension}"
        )(download)

    for kind, stem, output_id in (
        ("gene_heatmap", "gene_heatmap", "toi_gene_heatmap"),
        ("mz_heatmap", "mz_heatmap", "toi_mz_heatmap"),
        ("gene_curve", "gene_feature", "traj_feature_plot"),
        ("mz_curve", "mz_feature", "toi_mz_feature_plot"),
    ):
        for extension in ("pdf", "svg"):
            bound.append(
                bind_download(kind, "download_toi_" + stem + "_" + extension, extension, output_id)
            )

    def bind_download_controls(kind, stem, label):

        @output(id="toi_downloads_" + kind)
        @_feature_shared.render.ui
        def controls():
            if not current_result(kind):
                return _feature_shared.ui.p(
                    "Generate this figure for the current TOI to enable downloads.",
                    class_="apple-muted",
                )
            return _feature_shared.ui.TagList(
                *(
                    _feature_shared.ui.download_button(
                        "download_toi_" + stem + "_" + ext, label + " " + ext.upper()
                    )
                    for ext in ("pdf", "svg")
                )
            )

        return controls

    bound.extend(
        (
            bind_download_controls(*args)
            for args in (
                ("gene_heatmap", "gene_heatmap", "Gene Heatmap"),
                ("mz_heatmap", "mz_heatmap", "m/z Heatmap"),
                ("gene_curve", "gene_feature", "Gene Curves"),
                ("mz_curve", "mz_feature", "m/z Curves"),
            )
        )
    )

    @output
    @_feature_shared.render.ui
    def toi_combined_download():
        if not any(
            (
                current_result(kind)
                for kind in ("arrow", "gene_heatmap", "mz_heatmap", "gene_curve", "mz_curve")
            )
        ):
            return _feature_shared.ui.p(
                "Generate a figure for the current TOI to enable the combined PDF.",
                class_="apple-muted",
            )
        return _feature_shared.ui.download_button(
            "download_traj_pdf", "Download Trajectory PDF", class_="btn btn-secondary w-100 mt-3"
        )

    @output
    @_feature_shared.render.download(
        filename=lambda: _feature_shared.re.sub(
            "[^A-Za-z0-9_.-]", "_", str(value("export_prefix", "trajectory_analysis"))
        )[:100]
        + ".pdf"
    )
    def download_traj_pdf():
        from cloud.figure_export import EditablePdfPages

        buffer = _feature_shared.io.BytesIO()
        figures = []
        for kind, output_id in (
            ("arrow", "traj_arrow_plot"),
            ("gene_heatmap", "toi_gene_heatmap"),
            ("mz_heatmap", "toi_mz_heatmap"),
            ("gene_curve", "traj_feature_plot"),
            ("mz_curve", "toi_mz_feature_plot"),
        ):
            stored = current_result(kind)
            if stored:
                figures.append(colorize_plot(output_id, stored["figure"]))
        if not figures:
            raise ValueError(
                "Generate at least one figure for the current TOI before exporting the PDF."
            )
        with _feature_shared.PLOT_LOCK, EditablePdfPages(buffer) as pdf:
            for figure in figures:
                pdf.savefig(figure, bbox_inches="tight")
        yield buffer.getvalue()

    return {"results": results, "handlers": bound, "clear": clear}


server = register_toi_feature_server
