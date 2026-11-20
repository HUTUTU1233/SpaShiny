# Extracted from /app/app/ST-SM.py. Feature: gene_enrichment; ordered phases preserve original initialization.
from spashiny._shared import runtime_globals as _spashiny_globals


def _install_0(_spashiny_ctx):

    def _selected_gene_enrichment_databases():
        try:
            selected = _spashiny_ctx.input.gene_enrichment_database_ids()
        except Exception:
            selected = ["hallmark", "reactome", "go_bp", "go_cc", "go_mf"]
        parsed = _spashiny_ctx._enrichment_parse_database_selection(selected)
        return parsed or ["hallmark", "reactome", "go_bp", "go_cc", "go_mf"]

    _spashiny_ctx._selected_gene_enrichment_databases = _selected_gene_enrichment_databases


def _install_1(_spashiny_ctx):

    @_spashiny_ctx.output
    @_spashiny_ctx.render.ui
    def gene_enrichment_gene_column_selector():
        columns = _spashiny_ctx._enrichment_uploaded_columns(
            _spashiny_ctx.input.gene_enrichment_csv()
        )
        return _spashiny_ctx._enrichment_column_select_ui(
            "gene_enrichment_gene_column",
            "Gene column",
            columns,
            ["gene", "Gene", "symbol", "gene_symbol", "GeneSymbol", "input_gene"],
            "gene",
            "Upload a CSV/TSV to choose from its columns. Marker Analysis uses gene_df directly.",
        )

    _spashiny_ctx.gene_enrichment_gene_column_selector = gene_enrichment_gene_column_selector


def _install_2(_spashiny_ctx):

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.run_gene_enrichment_csv)
    def _run_gene_enrichment_csv():
        try:
            files = _spashiny_ctx.input.gene_enrichment_csv() or []
            if not files:
                raise RuntimeError("Please upload a Gene CSV first.")
            job = _spashiny_ctx._submit_enrichment_job_from_file(
                workflow_name="gene_enrichment",
                file_entry=files[0],
                parameters={
                    "gene_column": str(_spashiny_ctx.input.gene_enrichment_gene_column() or "gene"),
                    "database_ids": _spashiny_ctx._selected_gene_enrichment_databases(),
                    "species": "mouse",
                    "fdr_cutoff": _spashiny_ctx._enrichment_parse_fdr(
                        _spashiny_ctx.input.gene_enrichment_fdr_cutoff()
                    ),
                },
                status_value=_spashiny_ctx.gene_enrichment_status_msg,
            )
            _spashiny_ctx.gene_enrichment_job_id.set(job.job_id)
            _spashiny_ctx.ui.notification_show(
                f"Gene enrichment submitted: {job.job_id}", type="message", duration=6
            )
        except Exception as exc:
            error_msg = _spashiny_globals.user_facing_error("Gene enrichment submit failed", exc)
            _spashiny_ctx.gene_enrichment_status_msg.set(error_msg)
            _spashiny_ctx.ui.notification_show(error_msg, type="error", duration=10)

    _spashiny_ctx._run_gene_enrichment_csv = _run_gene_enrichment_csv

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.run_gene_enrichment_marker)
    def _run_gene_enrichment_marker():
        try:
            table = _spashiny_ctx._marker_feature_table("gene")
            job = _spashiny_ctx._submit_enrichment_job_from_dataframe(
                workflow_name="gene_enrichment",
                table=table,
                filename="marker_gene_df_for_enrichment.csv",
                parameters={
                    "gene_column": "gene",
                    "database_ids": _spashiny_ctx._selected_gene_enrichment_databases(),
                    "species": "mouse",
                    "fdr_cutoff": _spashiny_ctx._enrichment_parse_fdr(
                        _spashiny_ctx.input.gene_enrichment_fdr_cutoff()
                    ),
                    "input_origin": "marker_res.gene_df",
                },
                status_value=_spashiny_ctx.gene_enrichment_status_msg,
            )
            _spashiny_ctx.gene_enrichment_job_id.set(job.job_id)
            _spashiny_ctx.ui.notification_show(
                f"Marker gene enrichment submitted: {job.job_id}", type="message", duration=6
            )
        except Exception as exc:
            error_msg = _spashiny_globals.user_facing_error(
                "Marker gene enrichment submit failed", exc
            )
            _spashiny_ctx.gene_enrichment_status_msg.set(error_msg)
            _spashiny_ctx.ui.notification_show(error_msg, type="error", duration=10)

    _spashiny_ctx._run_gene_enrichment_marker = _run_gene_enrichment_marker


def _install_3(_spashiny_ctx):

    @_spashiny_ctx.output
    @_spashiny_ctx.render.text
    def gene_enrichment_status():
        return _spashiny_ctx.gene_enrichment_status_msg.get()

    _spashiny_ctx.gene_enrichment_status = gene_enrichment_status


def _install_4(_spashiny_ctx):

    @_spashiny_ctx.output
    @_spashiny_ctx.render.ui
    def gene_enrichment_job_results():
        return _spashiny_ctx._enrichment_job_result_ui(
            _spashiny_ctx.gene_enrichment_job_id.get(),
            empty_message="No Gene Enrichment job submitted in this page yet.",
        )

    _spashiny_ctx.gene_enrichment_job_results = gene_enrichment_job_results


_STEPS = (_install_0, _install_1, _install_2, _install_3, _install_4)


def server(_spashiny_ctx, step=0):
    return _STEPS[step](_spashiny_ctx)
