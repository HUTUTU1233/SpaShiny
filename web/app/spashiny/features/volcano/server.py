# Extracted from /app/app/ST-SM.py. Feature: volcano; ordered phases preserve original initialization.
from spashiny._shared import runtime_globals as _spashiny_globals


def _install_0(_spashiny_ctx):
    _spashiny_ctx.volcano_res = _spashiny_ctx.reactive.Value(None)

    @_spashiny_ctx.reactive.Effect
    def _invalidate_volcano_on_input_change():
        _spashiny_ctx.downstream_input_reference.get()
        _spashiny_ctx.adata_obj.get()
        _spashiny_ctx.marker_res.get()
        with _spashiny_ctx.reactive.isolate():
            previous = _spashiny_ctx.volcano_res.get()
            if isinstance(previous, dict):
                for key in ("gene_volcano", "metabolite_volcano"):
                    if previous.get(key) is not None:
                        _spashiny_globals.plt.close(previous[key])
            _spashiny_ctx.volcano_res.set(None)

    _spashiny_ctx._invalidate_volcano_on_input_change = _invalidate_volcano_on_input_change

    def _downstream_volcano_artifact_dir():
        """Return a session-scoped, non-public artifact directory for volcano PNGs."""
        try:
            owner = _spashiny_ctx._cloud_analysis_session_id() or _spashiny_ctx._cloud_session_id()
        except Exception:
            owner = ""
        owner = (
            _spashiny_ctx.re.sub("[^A-Za-z0-9_.-]+", "_", str(owner or "desktop"))[:128]
            or "desktop"
        )
        root = (
            _spashiny_ctx.Path(
                _spashiny_globals.os.environ.get("SPASHINY_TMP_DIR")
                or _spashiny_ctx.tempfile.gettempdir()
            )
            / "downstream_volcano"
            / owner
        )
        root.mkdir(parents=True, exist_ok=True)
        return root

    _spashiny_ctx._downstream_volcano_artifact_dir = _downstream_volcano_artifact_dir

    def _persist_downstream_volcano_png(plot_obj, name):
        """Save once at generation time; downloads must never re-render a Figure."""
        fig = _spashiny_ctx._as_matplotlib_figure(plot_obj)
        target = _spashiny_ctx._downstream_volcano_artifact_dir() / f"{name}.png"
        temporary = target.with_suffix(".png.tmp")
        fig.savefig(temporary, format="png", dpi=300, bbox_inches="tight", facecolor="white")
        if not temporary.is_file() or temporary.stat().st_size <= 0:
            raise RuntimeError(f"Volcano PNG was not written: {target.name}")
        _spashiny_globals.os.replace(temporary, target)
        return str(target)

    _spashiny_ctx._persist_downstream_volcano_png = _persist_downstream_volcano_png

    def _persist_downstream_volcano_pdf(plot_obj, name):
        """Write an Illustrator-editable PDF from the original live Figure."""
        fig = _spashiny_ctx._as_matplotlib_figure(plot_obj)
        target = _spashiny_ctx._downstream_volcano_artifact_dir() / f"{name}.pdf"
        temporary = target.with_suffix(".pdf.tmp")
        _spashiny_globals.save_editable_figure(fig, temporary, format="pdf")
        _spashiny_globals.save_editable_figure(fig, target.with_suffix(".svg"))
        if not temporary.is_file() or temporary.stat().st_size <= 0:
            raise RuntimeError(f"Volcano editable PDF was not written: {target.name}")
        _spashiny_globals.os.replace(temporary, target)
        return str(target)

    _spashiny_ctx._persist_downstream_volcano_pdf = _persist_downstream_volcano_pdf

    def make_spatialmeta_corr_plot_compatible_copy(adata):
        out = adata.copy()
        if "type" in out.var.columns:
            type_s = out.var["type"].astype(str).str.lower()
            sm_mask = type_s.str.contains("sm|metabolite|mz|msi|maldi", regex=True, na=False)
        else:
            name_s = _spashiny_ctx.pd.Series(
                [str(x) for x in out.var_names], index=out.var.index
            ).str.lower()
            sm_mask = name_s.str.contains("sm|metabolite|mz|m/z|msi|maldi", regex=True, na=False)
        out.var["type"] = _spashiny_globals.np.where(sm_mask.to_numpy(), "SM", "ST")
        return out

    _spashiny_ctx.make_spatialmeta_corr_plot_compatible_copy = (
        make_spatialmeta_corr_plot_compatible_copy
    )

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.btn_run_volcano)
    def run_volcano_plot():
        if not _spashiny_ctx._downstream_click_guard("btn_run_volcano", "Generate Volcano Plot"):
            return
        adata = _spashiny_ctx.corr_res()
        if adata is None:
            _spashiny_ctx.ui.notification_show(
                "Please complete the ST-SM correlation analysis first.", type="error"
            )
            return
        if "celltype_ST_SM" not in adata.obs.columns:
            _spashiny_ctx.ui.notification_show(
                "'celltype_ST_SM' was not found in adata.obs.", type="error"
            )
            return
        cluster = _spashiny_ctx.input.volcano_cluster()
        if not cluster:
            _spashiny_ctx.ui.notification_show("Please select a target cluster.", type="error")
            return
        if cluster not in [str(x) for x in adata.obs["celltype_ST_SM"].unique()]:
            _spashiny_ctx.ui.notification_show(f"Cluster not found: {cluster}", type="error")
            return
        gene_name = str(_spashiny_ctx.input.volcano_gene() or "").strip()
        metabolite_mass = str(_spashiny_ctx.input.volcano_metabolite() or "").strip()
        threshold_value = _spashiny_ctx.input.volcano_threshold()
        threshold = float(0.3 if threshold_value is None else threshold_value)
        if not gene_name:
            _spashiny_ctx.ui.notification_show("Please select a gene.", type="error")
            return
        if not metabolite_mass:
            _spashiny_ctx.ui.notification_show("Please select a metabolite m/z.", type="error")
            return
        _spashiny_ctx.ui.modal_show(
            _spashiny_ctx.ui.modal(
                _spashiny_ctx.ui.div(
                    _spashiny_ctx.ui.h4("Generating Volcano Plots...", class_="mb-3"),
                    _spashiny_ctx.ui.p("Please wait while the volcano plots are being generated."),
                    _spashiny_ctx.ui.p(
                        "Both Gene -> Metabolite and Metabolite -> Gene views will be prepared automatically.",
                        class_="text-muted",
                    ),
                ),
                title="Analysis in Progress",
                easy_close=False,
                footer=None,
            )
        )
        try:
            joint_adata_cluster = _spashiny_globals.prepare_volcano_input(
                adata, cluster, gene_name, metabolite_mass
            )
            gene_volcano_fig = _spashiny_globals.native_matplotlib_figure(
                _spashiny_globals.smt.pl.plot_volcano_corrcoef_metabolite,
                joint_adata_cluster,
                gene=gene_name,
                use_raw=False,
                threshold=threshold,
                color_threshold=threshold,
                show=False,
            )
            metabolite_volcano_fig = _spashiny_globals.native_matplotlib_figure(
                _spashiny_globals.smt.pl.plot_volcano_corrcoef_gene,
                joint_adata_cluster,
                metabolite=metabolite_mass,
                use_raw=False,
                threshold=threshold,
                color_threshold=threshold,
                show=False,
            )
            gene_png = _spashiny_ctx._persist_downstream_volcano_png(
                gene_volcano_fig, "gene_to_metabolite_volcano"
            )
            metabolite_png = _spashiny_ctx._persist_downstream_volcano_png(
                metabolite_volcano_fig, "metabolite_to_gene_volcano"
            )
            gene_pdf = _spashiny_ctx._persist_downstream_volcano_pdf(
                gene_volcano_fig, "gene_to_metabolite_volcano"
            )
            metabolite_pdf = _spashiny_ctx._persist_downstream_volcano_pdf(
                metabolite_volcano_fig, "metabolite_to_gene_volcano"
            )
            _spashiny_ctx.volcano_res.set(
                {
                    "gene_volcano": gene_volcano_fig,
                    "metabolite_volcano": metabolite_volcano_fig,
                    "gene_png": gene_png,
                    "metabolite_png": metabolite_png,
                    "gene_pdf": gene_pdf,
                    "metabolite_pdf": metabolite_pdf,
                }
            )
            _spashiny_ctx.ui.notification_show(
                "Volcano plots generated successfully.", type="message"
            )
        except Exception as e:
            _spashiny_ctx.volcano_res.set(None)
            _spashiny_ctx.ui.notification_show(
                f"Failed to generate volcano plots: {e}", type="error"
            )
            _spashiny_ctx.traceback.print_exc()
        finally:
            _spashiny_ctx.ui.modal_remove()

    _spashiny_ctx.run_volcano_plot = run_volcano_plot

    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("plt_gene_volcano")
    def plt_gene_volcano():
        figs = _spashiny_ctx.volcano_res()
        if figs is None:
            return None
        return figs["gene_volcano"]

    _spashiny_ctx.plt_gene_volcano = plt_gene_volcano

    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("plt_metabolite_volcano")
    def plt_metabolite_volcano():
        figs = _spashiny_ctx.volcano_res()
        if figs is None:
            return None
        return figs["metabolite_volcano"]

    _spashiny_ctx.plt_metabolite_volcano = plt_metabolite_volcano

    @_spashiny_ctx.render.download(filename=lambda: "gene_to_metabolite_volcano.png")
    def download_gene_volcano_png():
        figs = _spashiny_ctx.volcano_res()
        path = _spashiny_ctx.Path(str((figs or {}).get("gene_png") or ""))
        if not path.is_file() or path.stat().st_size <= 0:
            raise RuntimeError(
                "The generated gene-to-metabolite volcano PNG is unavailable. Generate the plot again."
            )
        yield from _spashiny_ctx.stream_file(path)

    _spashiny_ctx.download_gene_volcano_png = download_gene_volcano_png

    @_spashiny_ctx.render.download(filename=lambda: "metabolite_to_gene_volcano.png")
    def download_metabolite_volcano_png():
        figs = _spashiny_ctx.volcano_res()
        path = _spashiny_ctx.Path(str((figs or {}).get("metabolite_png") or ""))
        if not path.is_file() or path.stat().st_size <= 0:
            raise RuntimeError(
                "The generated metabolite-to-gene volcano PNG is unavailable. Generate the plot again."
            )
        yield from _spashiny_ctx.stream_file(path)

    _spashiny_ctx.download_metabolite_volcano_png = download_metabolite_volcano_png

    @_spashiny_ctx.render.download(filename=lambda: "gene_to_metabolite_volcano.pdf")
    def download_gene_volcano_pdf():
        figs = _spashiny_ctx.volcano_res()
        path = _spashiny_ctx.Path(str((figs or {}).get("gene_pdf") or ""))
        if not path.is_file() or path.stat().st_size <= 0:
            raise RuntimeError(
                "The generated gene-to-metabolite vector PDF is unavailable. Generate the plot again."
            )
        yield from _spashiny_ctx.stream_file(path)

    _spashiny_ctx.download_gene_volcano_pdf = download_gene_volcano_pdf

    @_spashiny_ctx.render.download(filename=lambda: "metabolite_to_gene_volcano.pdf")
    def download_metabolite_volcano_pdf():
        figs = _spashiny_ctx.volcano_res()
        path = _spashiny_ctx.Path(str((figs or {}).get("metabolite_pdf") or ""))
        if not path.is_file() or path.stat().st_size <= 0:
            raise RuntimeError(
                "The generated metabolite-to-gene vector PDF is unavailable. Generate the plot again."
            )
        yield from _spashiny_ctx.stream_file(path)

    _spashiny_ctx.download_metabolite_volcano_pdf = download_metabolite_volcano_pdf

    @_spashiny_ctx.render.download(filename=lambda: "gene_to_metabolite_volcano.svg")
    def download_gene_volcano_svg():
        figs = _spashiny_ctx.volcano_res()
        raw = str((figs or {}).get("gene_pdf") or "")
        if not raw:
            raise RuntimeError(
                "Generate the current gene-to-metabolite volcano before downloading its SVG."
            )
        path = _spashiny_ctx.Path(raw).with_suffix(".svg")
        if not path.is_file() or path.stat().st_size <= 0:
            raise RuntimeError(
                "Generate the current gene-to-metabolite volcano before downloading its SVG."
            )
        yield from _spashiny_ctx.stream_file(path)

    _spashiny_ctx.download_gene_volcano_svg = download_gene_volcano_svg

    @_spashiny_ctx.render.download(filename=lambda: "metabolite_to_gene_volcano.svg")
    def download_metabolite_volcano_svg():
        figs = _spashiny_ctx.volcano_res()
        raw = str((figs or {}).get("metabolite_pdf") or "")
        if not raw:
            raise RuntimeError(
                "Generate the current metabolite-to-gene volcano before downloading its SVG."
            )
        path = _spashiny_ctx.Path(raw).with_suffix(".svg")
        if not path.is_file() or path.stat().st_size <= 0:
            raise RuntimeError(
                "Generate the current metabolite-to-gene volcano before downloading its SVG."
            )
        yield from _spashiny_ctx.stream_file(path)

    _spashiny_ctx.download_metabolite_volcano_svg = download_metabolite_volcano_svg


_STEPS = (_install_0,)


def server(_spashiny_ctx, step=0):
    return _STEPS[step](_spashiny_ctx)
