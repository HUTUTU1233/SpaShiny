from __future__ import annotations

import html
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict, Optional

import pandas as pd

from shiny import module, reactive, render, req, ui


# ============================================================
# Helpers
# ============================================================

def _uploaded_path(file_input: Any) -> Optional[str]:
    if file_input is None:
        return None
    if isinstance(file_input, list) and len(file_input) > 0:
        return file_input[0].get("datapath")
    return None


def _safe_read_csv(path: Path, nrows: Optional[int] = None) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame({"Message": [f"File not found: {path}"]})
    try:
        return pd.read_csv(path, nrows=nrows)
    except Exception as exc:
        return pd.DataFrame({"Message": [f"Failed to read result table: {exc}"]})


def _copy_uploaded_file(uploaded_path: str, outdir: Path, filename: str) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    suffix = Path(uploaded_path).suffix
    target = outdir / f"{filename}{suffix}"
    shutil.copyfile(uploaded_path, target)
    return target


def _run_rscript(
    rscript_bin: str,
    script_path: Path,
    mode: str,
    input_path: Path,
    outdir: Path,
    extra_args: Dict[str, Any],
    timeout: int = 1800,
) -> subprocess.CompletedProcess:
    if shutil.which(rscript_bin) is None and not Path(rscript_bin).exists():
        raise FileNotFoundError(
            f"Rscript not found: {rscript_bin}. Please make sure Rscript is available in PATH."
        )

    if not script_path.exists():
        raise FileNotFoundError(f"R backend script not found: {script_path}")

    cmd = [
        rscript_bin,
        str(script_path),
        "--mode",
        mode,
        "--input",
        str(input_path),
        "--outdir",
        str(outdir),
    ]

    for key, value in extra_args.items():
        cmd.extend([f"--{key}", str(value)])

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        stdout = proc.stdout.strip()
        detail = stderr if stderr else stdout
        raise RuntimeError(detail if detail else "Rscript failed without an error message.")

    return proc


def _make_output_dir(base_dir: Path, prefix: str) -> Path:
    result_root = base_dir / "results" / "enrichment"
    result_root.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=prefix, dir=result_root))


def _resolve_workspace_root(base_dir: Path) -> Path:
    return base_dir.parent


def _resolve_river_python(workspace_root: Path) -> str:
    explicit = os.environ.get("SPASHINY_RIVER_PYTHON")
    candidates = [
        explicit,
        workspace_root / "runtime" / "env_river" / "python.exe",
        workspace_root / "runtime" / "env_river" / "Scripts" / "python.exe",
        workspace_root / "runtime" / "env_app" / "python.exe",
        workspace_root / "runtime" / "env_app" / "Scripts" / "python.exe",
        sys.executable,
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists():
            return str(path)
    return sys.executable


def _bool_text(value: Any) -> str:
    return "true" if bool(value) else "false"


def _optional_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"success": False, "message": f"Failed to read summary JSON: {exc}"}


def _status_html(lines: list[str]) -> ui.Tag:
    escaped = "<br>".join(html.escape(str(line)) for line in lines)
    return ui.HTML(escaped)


# ============================================================
# Shiny module server
# ============================================================

@module.server
def enrichment_module_server(
    input,
    output,
    session,
    base_dir: str | Path = ".",
    rscript_bin: str = "Rscript",
):
    base_dir = Path(base_dir).resolve()
    workspace_root = _resolve_workspace_root(base_dir)
    script_path = base_dir / "scripts" / "run_clusterprofiler_enrichment.R"
    annotator_script_path = workspace_root / "app" / "river" / "run_metabolite_annotation.py"

    gene_status_value = reactive.Value("Ready. Upload a differential gene table and run enrichment.")
    metab_status_value = reactive.Value("Ready. Upload a differential metabolite table and run enrichment.")
    annotation_status_value = reactive.Value("Ready. Upload h5ad and annotation table to run putative metabolite annotation.")

    gene_result = reactive.Value(None)
    metab_result = reactive.Value(None)
    annotation_result = reactive.Value(None)

    gene_outdir = reactive.Value(None)
    metab_outdir = reactive.Value(None)
    annotation_outdir = reactive.Value(None)
    annotation_paths = reactive.Value({})
    annotation_job = {
        "proc": None,
        "log_handle": None,
        "finalized": True,
    }

    def _annotation_is_running() -> bool:
        proc = annotation_job.get("proc")
        return proc is not None and proc.poll() is None

    def _close_annotation_log_handle() -> None:
        handle = annotation_job.get("log_handle")
        if handle is not None:
            try:
                handle.flush()
                handle.close()
            except Exception:
                pass
            annotation_job["log_handle"] = None

    def _finalize_annotation_if_done() -> None:
        proc = annotation_job.get("proc")
        if proc is None or annotation_job.get("finalized"):
            return
        returncode = proc.poll()
        if returncode is None:
            return

        _close_annotation_log_handle()
        paths = annotation_paths() or {}
        summary_path = Path(paths.get("summary_json", ""))
        summary = _read_json(summary_path)
        annotation_result.set(summary)
        annotation_job["finalized"] = True

        outdir = annotation_outdir()
        if returncode == 0 and summary.get("success", False):
            annotation_status_value.set(
                "\n".join(
                    [
                        "Done. Putative metabolite annotation completed.",
                        f"Annotated features: {summary.get('successfully_annotated_features', 0)} / {summary.get('participating_features', 0)}",
                        f"Candidate rows: {summary.get('candidate_rows', 0)}",
                        f"Output: {outdir}",
                    ]
                )
            )
        else:
            annotation_status_value.set(
                "\n".join(
                    [
                        f"Failed. Backend return code: {returncode}",
                        str(summary.get("message", "No summary message was written.")),
                        f"Output: {outdir}",
                    ]
                )
            )

    @reactive.Effect
    @reactive.event(input.run_gene_enrichment)
    def _run_gene_enrichment():
        try:
            uploaded = _uploaded_path(input.gene_file())
            if uploaded is None:
                raise ValueError("Please upload a differential gene table.")

            outdir = _make_output_dir(base_dir, "gene_")
            input_copy = _copy_uploaded_file(uploaded, outdir, "gene_input")

            gene_status_value.set("Running gene enrichment analysis...")

            _run_rscript(
                rscript_bin=rscript_bin,
                script_path=script_path,
                mode="gene",
                input_path=input_copy,
                outdir=outdir,
                extra_args={
                    "species": input.gene_species(),
                    "id_type": input.gene_id_type(),
                    "analysis": input.gene_analysis(),
                    "feature_mode": input.gene_feature_mode(),
                    "top_n": int(input.gene_top_n()),
                    "gene_col": input.gene_col(),
                    "p_col": input.gene_p_col(),
                    "logfc_col": input.gene_logfc_col(),
                    "state_col": input.gene_state_col(),
                    "pvalue_cutoff": float(input.gene_pvalue_cutoff()),
                    "qvalue_cutoff": float(input.gene_qvalue_cutoff()),
                    "show_category": int(input.gene_show_category()),
                },
            )

            result_df = _safe_read_csv(outdir / "enrichment_result.csv")
            gene_result.set(result_df)
            gene_outdir.set(outdir)
            gene_status_value.set(f"Done. Gene enrichment returned {len(result_df)} rows.\nOutput: {outdir}")

        except Exception as exc:
            gene_result.set(pd.DataFrame({"Error": [str(exc)]}))
            gene_status_value.set(f"Failed: {type(exc).__name__}: {exc}")

    @reactive.Effect
    @reactive.event(input.run_metab_enrichment)
    def _run_metab_enrichment():
        try:
            uploaded = _uploaded_path(input.metab_file())
            if uploaded is None:
                raise ValueError("Please upload a differential metabolite table.")

            outdir = _make_output_dir(base_dir, "metabolite_")
            input_copy = _copy_uploaded_file(uploaded, outdir, "metabolite_input")

            metab_status_value.set("Running metabolite KEGG enrichment analysis...")

            _run_rscript(
                rscript_bin=rscript_bin,
                script_path=script_path,
                mode="metabolite",
                input_path=input_copy,
                outdir=outdir,
                extra_args={
                    "kegg_col": input.metab_kegg_col(),
                    "feature_mode": input.metab_feature_mode(),
                    "top_n": int(input.metab_top_n()),
                    "p_col": input.metab_p_col(),
                    "logfc_col": input.metab_logfc_col(),
                    "state_col": input.metab_state_col(),
                    "pvalue_cutoff": float(input.metab_pvalue_cutoff()),
                    "qvalue_cutoff": float(input.metab_qvalue_cutoff()),
                    "show_category": int(input.metab_show_category()),
                },
            )

            result_df = _safe_read_csv(outdir / "enrichment_result.csv")
            metab_result.set(result_df)
            metab_outdir.set(outdir)
            metab_status_value.set(f"Done. Metabolite enrichment returned {len(result_df)} rows.\nOutput: {outdir}")

        except Exception as exc:
            metab_result.set(pd.DataFrame({"Error": [str(exc)]}))
            metab_status_value.set(f"Failed: {type(exc).__name__}: {exc}")

    @reactive.Effect
    @reactive.event(input.run_metabolite_annotation)
    def _run_metabolite_annotation():
        try:
            if _annotation_is_running():
                annotation_status_value.set("A putative metabolite annotation job is already running.")
                return

            uploaded_h5ad = _uploaded_path(input.annot_h5ad())
            uploaded_anno = _uploaded_path(input.annot_table())
            if uploaded_h5ad is None:
                raise ValueError("Please upload a spatial metabolomics or joint omics h5ad file.")
            if uploaded_anno is None:
                raise ValueError("Please upload a metabolite annotation table.")
            if not annotator_script_path.exists():
                raise FileNotFoundError(f"Annotation backend script not found: {annotator_script_path}")

            _close_annotation_log_handle()
            annotation_job["proc"] = None
            annotation_job["finalized"] = True
            annotation_result.set(None)

            outdir = _make_output_dir(base_dir, "metabolite_annotation_")
            annotation_outdir.set(outdir)
            input_h5ad = _copy_uploaded_file(uploaded_h5ad, outdir, "input")
            anno_table = _copy_uploaded_file(uploaded_anno, outdir, "annotation_table")

            annotated_h5ad = outdir / "annotated.h5ad"
            summary_json = outdir / "annotation_summary.json"
            candidates_csv = outdir / "all_candidate_annotations.csv"
            log_path = outdir / "metabolite_annotation.log"
            paths = {
                "input_h5ad": str(input_h5ad),
                "annotation_table": str(anno_table),
                "annotated_h5ad": str(annotated_h5ad),
                "summary_json": str(summary_json),
                "all_candidates_csv": str(candidates_csv),
                "log_path": str(log_path),
            }
            annotation_paths.set(paths)

            river_python = _resolve_river_python(workspace_root)
            cmd = [
                river_python,
                str(annotator_script_path),
                "--h5ad",
                str(input_h5ad),
                "--anno",
                str(anno_table),
                "--out",
                str(annotated_h5ad),
                "--mode",
                str(input.annot_mode()),
                "--tolerance_ppm",
                str(float(input.annot_tolerance_ppm())),
                "--top_n",
                str(int(input.annot_top_n())),
                "--summary_json",
                str(summary_json),
                "--all_candidates_csv",
                str(candidates_csv),
                "--only_sm_features",
                _bool_text(input.annot_only_sm()),
            ]

            for option_name, input_getter in (
                ("--var_mz_col", input.annot_var_mz_col),
                ("--anno_mz_col", input.annot_anno_mz_col),
                ("--polarity_col", input.annot_polarity_col),
            ):
                value = _optional_text(input_getter())
                if value:
                    cmd.extend([option_name, value])

            log_handle = open(log_path, "w", encoding="utf-8", errors="ignore")
            log_handle.write("Command: " + " ".join(cmd) + "\n\n")
            log_handle.flush()

            proc = subprocess.Popen(
                cmd,
                cwd=str(workspace_root),
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
            )
            annotation_job["proc"] = proc
            annotation_job["log_handle"] = log_handle
            annotation_job["finalized"] = False
            annotation_status_value.set(
                "\n".join(
                    [
                        "Running putative metabolite annotation in runtime/env_river backend process...",
                        f"Backend Python: {river_python}",
                        f"Output: {outdir}",
                    ]
                )
            )

        except Exception as exc:
            _close_annotation_log_handle()
            annotation_job["proc"] = None
            annotation_job["finalized"] = True
            annotation_result.set({"success": False, "message": str(exc)})
            annotation_status_value.set(f"Failed to start annotation: {type(exc).__name__}: {exc}")

    @output
    @render.ui
    def gene_status():
        return ui.HTML(gene_status_value())

    @output
    @render.ui
    def metab_status():
        return ui.HTML(metab_status_value())

    @output
    @render.ui
    def annotation_status():
        if _annotation_is_running():
            reactive.invalidate_later(1)
        _finalize_annotation_if_done()
        paths = annotation_paths() or {}
        lines = [annotation_status_value()]
        if paths:
            lines.extend(
                [
                    "",
                    f"Annotated h5ad: {paths.get('annotated_h5ad', '')}",
                    f"Summary JSON: {paths.get('summary_json', '')}",
                    f"Candidate CSV: {paths.get('all_candidates_csv', '')}",
                    f"Run log: {paths.get('log_path', '')}",
                ]
            )
        return _status_html(lines)

    @output
    @render.table
    def gene_result_table():
        df = gene_result()
        if df is None:
            return pd.DataFrame()
        return df.head(100)

    @output
    @render.table
    def metab_result_table():
        df = metab_result()
        if df is None:
            return pd.DataFrame()
        return df.head(100)

    @output
    @render.table
    def annotation_candidate_table():
        if _annotation_is_running():
            reactive.invalidate_later(1)
            return pd.DataFrame({"Status": ["Annotation job is running..."]})
        _finalize_annotation_if_done()
        paths = annotation_paths() or {}
        candidate_raw = paths.get("all_candidates_csv")
        if not candidate_raw:
            return pd.DataFrame()
        candidate_path = Path(candidate_raw)
        if not candidate_path.exists():
            return pd.DataFrame()
        return _safe_read_csv(candidate_path, nrows=100)

    @output
    @render.image
    def gene_dotplot():
        outdir = gene_outdir()
        if outdir is None:
            return None
        image_path = Path(outdir) / "dotplot.png"
        if not image_path.exists():
            return None
        return {
            "src": str(image_path),
            "alt": "Gene enrichment DotPlot",
            "width": "100%",
        }

    @output
    @render.image
    def metab_dotplot():
        outdir = metab_outdir()
        if outdir is None:
            return None
        image_path = Path(outdir) / "dotplot.png"
        if not image_path.exists():
            return None
        return {
            "src": str(image_path),
            "alt": "Metabolite enrichment DotPlot",
            "width": "100%",
        }

    @output
    @render.download(filename="gene_diff_example.csv")
    def download_gene_example_csv():
        example_path = base_dir / "examples" / "gene_diff_example.csv"
        req(example_path.exists())
        with open(example_path, "rb") as f:
            yield f.read()

    @output
    @render.download(filename="metabolite_diff_example.csv")
    def download_metab_example_csv():
        example_path = base_dir / "examples" / "metabolite_diff_example.csv"
        req(example_path.exists())
        with open(example_path, "rb") as f:
            yield f.read()

    @output
    @render.download(filename="gene_enrichment_result.csv")
    def download_gene_result():
        outdir = gene_outdir()
        req(outdir is not None)
        result_path = Path(outdir) / "enrichment_result.csv"
        req(result_path.exists())
        with open(result_path, "rb") as f:
            yield f.read()

    @output
    @render.download(filename="gene_enrichment_dotplot.pdf")
    def download_gene_dotplot():
        outdir = gene_outdir()
        req(outdir is not None)
        image_path = Path(outdir) / "dotplot.pdf"
        req(image_path.exists())
        with open(image_path, "rb") as f:
            yield f.read()

    @output
    @render.download(filename="metabolite_enrichment_result.csv")
    def download_metab_result():
        outdir = metab_outdir()
        req(outdir is not None)
        result_path = Path(outdir) / "enrichment_result.csv"
        req(result_path.exists())
        with open(result_path, "rb") as f:
            yield f.read()

    @output
    @render.download(filename="metabolite_enrichment_dotplot.pdf")
    def download_metab_dotplot():
        outdir = metab_outdir()
        req(outdir is not None)
        image_path = Path(outdir) / "dotplot.pdf"
        req(image_path.exists())
        with open(image_path, "rb") as f:
            yield f.read()

    @output
    @render.download(filename="annotated.h5ad")
    def download_annotated_h5ad():
        _finalize_annotation_if_done()
        paths = annotation_paths() or {}
        raw_path = paths.get("annotated_h5ad")
        req(raw_path)
        result_path = Path(raw_path)
        req(result_path.exists())
        with open(result_path, "rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk

    @output
    @render.download(filename="annotation_summary.json")
    def download_annotation_summary():
        _finalize_annotation_if_done()
        paths = annotation_paths() or {}
        raw_path = paths.get("summary_json")
        req(raw_path)
        result_path = Path(raw_path)
        req(result_path.exists())
        with open(result_path, "rb") as f:
            yield f.read()

    @output
    @render.download(filename="all_candidate_annotations.csv")
    def download_annotation_candidates():
        _finalize_annotation_if_done()
        paths = annotation_paths() or {}
        raw_path = paths.get("all_candidates_csv")
        req(raw_path)
        result_path = Path(raw_path)
        req(result_path.exists())
        with open(result_path, "rb") as f:
            yield f.read()

    @output
    @render.download(filename="metabolite_annotation.log")
    def download_annotation_log():
        _finalize_annotation_if_done()
        paths = annotation_paths() or {}
        raw_path = paths.get("log_path")
        req(raw_path)
        result_path = Path(raw_path)
        req(result_path.exists())
        with open(result_path, "rb") as f:
            yield f.read()
