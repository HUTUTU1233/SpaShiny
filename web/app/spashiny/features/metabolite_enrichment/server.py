# Extracted from /app/app/ST-SM.py. Feature: metabolite_enrichment; ordered phases preserve original initialization.
from spashiny._shared import runtime_globals as _spashiny_globals


def _install_0(_spashiny_ctx):

    @_spashiny_ctx.output
    @_spashiny_ctx.render.ui
    def metabolite_enrichment_kegg_column_selector():
        columns = _spashiny_ctx._enrichment_uploaded_columns(
            _spashiny_ctx.input.metabolite_enrichment_csv()
        )
        return _spashiny_ctx._enrichment_column_select_ui(
            "metabolite_enrichment_kegg_column",
            "KEGG Compound ID column",
            columns,
            ["KEGG.ID", "KEGG_ID", "kegg_id", "kegg", "compound_id", "kegg_compound_id"],
            "KEGG.ID",
            "Offline metabolite enrichment uses explicit KEGG Compound IDs; names alone are not guessed.",
        )

    _spashiny_ctx.metabolite_enrichment_kegg_column_selector = (
        metabolite_enrichment_kegg_column_selector
    )

    @_spashiny_ctx.output
    @_spashiny_ctx.render.ui
    def metabolite_enrichment_name_column_selector():
        columns = _spashiny_ctx._enrichment_uploaded_columns(
            _spashiny_ctx.input.metabolite_enrichment_csv()
        )
        return _spashiny_ctx._enrichment_column_select_ui(
            "metabolite_enrichment_name_column",
            "Metabolite name column",
            columns,
            ["metabolite", "Metabolite", "name", "compound_name", "input_metabolite"],
            "metabolite",
            "This column is preserved in mapping output; KEGG.ID is still required for enrichment.",
        )

    _spashiny_ctx.metabolite_enrichment_name_column_selector = (
        metabolite_enrichment_name_column_selector
    )


def _install_1(_spashiny_ctx):

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.run_metabolite_enrichment_csv)
    def _run_metabolite_enrichment_csv():
        try:
            files = _spashiny_ctx.input.metabolite_enrichment_csv() or []
            if not files:
                raise RuntimeError("Please upload a Metabolite CSV first.")
            job = _spashiny_ctx._submit_enrichment_job_from_file(
                workflow_name="metabolite_enrichment",
                file_entry=files[0],
                parameters={
                    "kegg_column": str(
                        _spashiny_ctx.input.metabolite_enrichment_kegg_column() or "KEGG.ID"
                    ),
                    "metabolite_column": str(
                        _spashiny_ctx.input.metabolite_enrichment_name_column() or "metabolite"
                    ),
                    "fdr_cutoff": _spashiny_ctx._enrichment_parse_fdr(
                        _spashiny_ctx.input.metabolite_enrichment_fdr_cutoff()
                    ),
                },
                status_value=_spashiny_ctx.metabolite_enrichment_status_msg,
            )
            _spashiny_ctx.metabolite_enrichment_job_id.set(job.job_id)
            _spashiny_ctx.ui.notification_show(
                f"Metabolite enrichment submitted: {job.job_id}", type="message", duration=6
            )
        except Exception as exc:
            error_msg = _spashiny_globals.user_facing_error(
                "Metabolite enrichment submit failed", exc
            )
            _spashiny_ctx.metabolite_enrichment_status_msg.set(error_msg)
            _spashiny_ctx.ui.notification_show(error_msg, type="error", duration=10)

    _spashiny_ctx._run_metabolite_enrichment_csv = _run_metabolite_enrichment_csv

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.run_metabolite_enrichment_marker)
    def _run_metabolite_enrichment_marker():
        try:
            table = _spashiny_ctx._marker_feature_table("metabolite")
            if "KEGG.ID" not in table.columns:
                raise RuntimeError(
                    "Current Marker Analysis met_df does not include KEGG.ID. Offline metabolite enrichment will not guess names; upload a CSV with KEGG.ID values."
                )
            job = _spashiny_ctx._submit_enrichment_job_from_dataframe(
                workflow_name="metabolite_enrichment",
                table=table,
                filename="marker_met_df_for_enrichment.csv",
                parameters={
                    "kegg_column": "KEGG.ID",
                    "metabolite_column": "metabolite",
                    "fdr_cutoff": _spashiny_ctx._enrichment_parse_fdr(
                        _spashiny_ctx.input.metabolite_enrichment_fdr_cutoff()
                    ),
                    "input_origin": "marker_res.met_df",
                },
                status_value=_spashiny_ctx.metabolite_enrichment_status_msg,
            )
            _spashiny_ctx.metabolite_enrichment_job_id.set(job.job_id)
            _spashiny_ctx.ui.notification_show(
                f"Marker metabolite enrichment submitted: {job.job_id}", type="message", duration=6
            )
        except Exception as exc:
            error_msg = _spashiny_globals.user_facing_error(
                "Marker metabolite enrichment submit failed", exc
            )
            _spashiny_ctx.metabolite_enrichment_status_msg.set(error_msg)
            _spashiny_ctx.ui.notification_show(error_msg, type="error", duration=10)

    _spashiny_ctx._run_metabolite_enrichment_marker = _run_metabolite_enrichment_marker


def _install_2(_spashiny_ctx):

    @_spashiny_ctx.output
    @_spashiny_ctx.render.text
    def metabolite_enrichment_status():
        return _spashiny_ctx.metabolite_enrichment_status_msg.get()

    _spashiny_ctx.metabolite_enrichment_status = metabolite_enrichment_status


def _install_3(_spashiny_ctx):

    @_spashiny_ctx.output
    @_spashiny_ctx.render.ui
    def metabolite_enrichment_job_results():
        return _spashiny_ctx._enrichment_job_result_ui(
            _spashiny_ctx.metabolite_enrichment_job_id.get(),
            empty_message="No Metabolite Enrichment job submitted in this page yet.",
        )

    _spashiny_ctx.metabolite_enrichment_job_results = metabolite_enrichment_job_results


_STEPS = (_install_0, _install_1, _install_2, _install_3)


def server(_spashiny_ctx, step=0):
    return _STEPS[step](_spashiny_ctx)
