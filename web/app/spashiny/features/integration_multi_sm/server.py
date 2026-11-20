# Extracted from /app/app/ST-SM.py. Feature: integration_multi_sm; ordered phases preserve original initialization.
from spashiny._shared import runtime_globals as _spashiny_globals


def _install_0(_spashiny_ctx):
    import os

    _spashiny_globals.os = os
    import re

    _spashiny_ctx.re = re
    import json

    _spashiny_ctx.json = json
    import pickle

    _spashiny_ctx.pickle = pickle
    import shutil

    _spashiny_ctx.shutil = shutil
    import zipfile

    _spashiny_ctx.zipfile = zipfile
    import tempfile

    _spashiny_ctx.tempfile = tempfile
    import traceback

    _spashiny_ctx.traceback = traceback
    from pathlib import Path

    _spashiny_ctx.Path = Path
    import numpy as np

    _spashiny_globals.np = np
    import pandas as pd

    _spashiny_ctx.pd = pd
    import scanpy as sc

    _spashiny_globals.sc = sc
    import seaborn as sns

    _spashiny_ctx.sns = sns
    import matplotlib.pyplot as plt

    _spashiny_globals.plt = plt
    import anndata as ad

    _spashiny_ctx.ad = ad
    import spatialmeta as smt

    _spashiny_globals.smt = smt
    import torch

    _spashiny_globals.torch = torch
    import torch.nn as nn

    _spashiny_ctx.nn = nn
    from shiny import reactive, render, ui

    _spashiny_ctx.reactive = reactive
    _spashiny_ctx.render = render
    _spashiny_ctx.ui = ui
    _spashiny_ctx.sm_sample_data = _spashiny_ctx.reactive.Value({})
    _spashiny_ctx.merged_sm_data = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.integrated_sm_data = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.sm_merge_log = _spashiny_ctx.reactive.Value([])
    _spashiny_ctx.sm_merge_status = _spashiny_ctx.reactive.Value("Waiting")
    _spashiny_ctx.vae_training_status = _spashiny_ctx.reactive.Value("Waiting")
    _spashiny_ctx.is_merging = _spashiny_ctx.reactive.Value(False)
    _spashiny_ctx.is_training = _spashiny_ctx.reactive.Value(False)
    _spashiny_ctx.vae_model = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.vae_loss_dict = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.vae_job_dir = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.integrated_sm_data_path = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.vae_summary = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.vae_model_state_path = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.hit_sm_example_merge_requested = _spashiny_ctx.reactive.Value(False)
    _spashiny_ctx.hit_sm_merge_summary = _spashiny_ctx.reactive.Value({})
    _spashiny_ctx.hit_sm_merge_metadata = _spashiny_ctx.reactive.Value({})
    _spashiny_ctx.hit_sm_merge_result_path = _spashiny_ctx.reactive.Value("")
    _spashiny_ctx.hit_sm_svm_summary = _spashiny_ctx.reactive.Value({})
    _spashiny_ctx.hit_sm_svm_metadata = _spashiny_ctx.reactive.Value({})
    _spashiny_ctx.hit_sm_svm_result_path = _spashiny_ctx.reactive.Value("")
    _spashiny_ctx.hit_sm_input_source_mode = _spashiny_ctx.reactive.Value("")

    def _cloud_authorized_worker_figure(summary, *, workflow_name, stage, rel_path):
        """Exact owner/analysis/job/manifest authorization for immutable worker figures."""
        import hashlib
        import json
        import re
        from pathlib import Path
        from cloud.database import CloudDatabase
        from cloud.job_manager import JobManager

        latent_pattern = rel_path == "glob:figures/vae_clusters_latent*.png"
        if (
            workflow_name
            not in {"hit_sm_multi_sample_integration", "vhit_multi_sample_integration"}
            or stage not in {"merge", "qc", "train"}
            or (
                not (
                    latent_pattern
                    or re.fullmatch("figures/[A-Za-z0-9_.-]+\\.(?:png|pdf)", str(rel_path))
                )
            )
        ):
            raise ValueError("Unknown worker figure.")
        job_id = str((summary or {}).get("cloud_job_id") or "").strip()
        owner = _spashiny_ctx._cloud_session_id()
        analysis = _spashiny_ctx._cloud_analysis_session_id()
        if not job_id or not owner or (not analysis):
            return None
        database = CloudDatabase(read_only=True)
        try:
            record = database.get_analysis_session(analysis, owner_session_id=owner)
            job = JobManager(database=database).get_job_for_session(
                owner, job_id, analysis_session_id=analysis
            )
        except KeyError:
            raise ValueError("The worker figure does not belong to this analysis.") from None
        if str(record.get("status") or "").upper() != "ACTIVE":
            raise ValueError("This analysis has ended; its figure cannot be downloaded here.")
        if (
            str(job.job_id) != job_id
            or str(job.session_id) != owner
            or str(job.analysis_session_id) != analysis
            or (str(job.workflow) != workflow_name)
            or ((_spashiny_ctx._cloud_job_stage(job) or "train") != stage)
        ):
            raise ValueError("The worker figure scope or workflow stage is invalid.")
        if str(job.status or "").upper() not in {"SUCCEEDED", "COMPLETED"}:
            return None
        if not str(job.local_workspace or "").strip():
            raise ValueError("The worker result workspace is unavailable.")
        root = Path(job.local_workspace).resolve()
        manifest_path = (root / "result_manifest.json").resolve()
        if (
            root not in manifest_path.parents
            or not manifest_path.is_file()
            or manifest_path.stat().st_size > 1024 * 1024
        ):
            raise ValueError("The worker figure manifest is unavailable.")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            not isinstance(manifest, dict)
            or manifest.get("job_id") != job_id
            or manifest.get("session_id") != owner
            or (not isinstance(manifest.get("files"), list))
            or (manifest.get("analysis_session_id") not in (None, "", analysis))
        ):
            raise ValueError("The worker figure manifest scope is invalid.")
        entries = []
        for item in manifest["files"]:
            if not isinstance(item, dict):
                raise ValueError("The worker figure manifest contains an invalid entry.")
            paths = [item[key] for key in ("relative_path", "path") if key in item]
            if len(paths) == 2 and paths[0] != paths[1]:
                raise ValueError("The worker figure manifest has conflicting paths.")
            if paths and (
                paths[0] == rel_path
                or (
                    latent_pattern
                    and isinstance(paths[0], str)
                    and re.fullmatch("figures/vae_clusters_latent[0-9]+\\.png", paths[0])
                )
            ):
                entries.append((item, paths[0]))
        if len(entries) != 1:
            raise ValueError("The worker figure must occur exactly once in its manifest.")
        entry, relative = entries[0]
        sizes = [entry[key] for key in ("size", "size_bytes") if key in entry]
        target = (root / relative).resolve()
        if (
            root not in target.parents
            or not target.is_file()
            or (not sizes)
            or any(
                (
                    type(value) is not int or value <= 0 or value != target.stat().st_size
                    for value in sizes
                )
            )
        ):
            raise ValueError("The worker figure path or size is invalid.")
        digest = hashlib.sha256()
        with target.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != str(entry.get("sha256") or "").lower():
            raise ValueError("The worker figure failed SHA256 validation.")
        return target

    _spashiny_ctx._cloud_authorized_worker_figure = _cloud_authorized_worker_figure

    def _hit_sm_prepared_artifact(kind, suffix):
        options = {
            "sample_size": (_spashiny_ctx.hit_sm_merge_summary, "merge", "sample_distribution"),
            "feature_distribution": (_spashiny_ctx.hit_sm_svm_summary, "qc", "qc_violin"),
            "svm": (_spashiny_ctx.hit_sm_svm_summary, "qc", "spatial_variable_features"),
        }
        if suffix not in {"png", "pdf"} or kind not in options:
            raise ValueError("Unknown worker figure.")
        summary_value, stage, stem = options[kind]
        return _spashiny_ctx._cloud_authorized_worker_figure(
            summary_value.get() or {},
            workflow_name="hit_sm_multi_sample_integration",
            stage=stage,
            rel_path=f"figures/{stem}.{suffix}",
        )

    _spashiny_ctx._hit_sm_prepared_artifact = _hit_sm_prepared_artifact

    def _hit_sm_prepared_figure(kind, *, downloads=False):
        options = {
            "sample_size": (
                _spashiny_ctx.hit_sm_merge_summary,
                "merge",
                "sample_distribution",
                "sm_sample_size_plot",
                "Sample size distribution",
            ),
            "feature_distribution": (
                _spashiny_ctx.hit_sm_svm_summary,
                "qc",
                "qc_violin",
                "sm_feature_distribution_plot",
                "Worker feature intensity distribution",
            ),
            "svm": (
                _spashiny_ctx.hit_sm_svm_summary,
                "qc",
                "spatial_variable_features",
                "svm_plot",
                "Worker spatially variable metabolites",
            ),
        }
        summary_value, stage, stem, fallback, alt = options[kind]
        if not _spashiny_globals.SPASHINY_LAB_PROFILE:
            return (
                _spashiny_ctx.ui.download_button(
                    "download_" + fallback, "Download Figure", class_="btn-secondary", width="100%"
                )
                if downloads
                else _spashiny_globals.plot_output_with_palette(
                    fallback, width="1300px", height="1300px"
                )
            )
        if not downloads:
            artifact = _spashiny_ctx._hit_sm_prepared_artifact(kind, "png")
            if artifact is None:
                return _spashiny_ctx.ui.span(
                    "The worker figure becomes available after completion.", class_="cloud-muted"
                )
            import base64

            encoded = base64.b64encode(artifact.read_bytes()).decode("ascii")
            return _spashiny_ctx.ui.tags.img(
                src="data:image/png;base64," + encoded,
                alt=alt,
                style="width:100%;height:auto;display:block;object-fit:contain;",
            )
        links = []
        for suffix in ("pdf", "png"):
            if _spashiny_ctx._hit_sm_prepared_artifact(kind, suffix) is not None:
                links.append(
                    _spashiny_ctx.ui.download_button(
                        f"hit_sm_{kind}_{suffix}",
                        "Download " + suffix.upper(),
                        class_="btn btn-outline-primary",
                        style="margin-right:8px;",
                    )
                )
        return (
            _spashiny_ctx.ui.div(*links)
            if links
            else _spashiny_ctx.ui.span(
                "Figure downloads become available when the worker completes.", class_="cloud-muted"
            )
        )

    _spashiny_ctx._hit_sm_prepared_figure = _hit_sm_prepared_figure

    def _hit_sm_stream_prepared_figure(kind, suffix):
        artifact = _spashiny_ctx._hit_sm_prepared_artifact(kind, suffix)
        if artifact is None:
            raise ValueError("The worker figure is not ready for download.")
        yield from _spashiny_ctx.stream_file(artifact)

    _spashiny_ctx._hit_sm_stream_prepared_figure = _hit_sm_stream_prepared_figure

    @_spashiny_ctx.render.download(
        filename="sm_sample_distribution.pdf", media_type="application/pdf"
    )
    def hit_sm_sample_size_pdf():
        yield from _spashiny_ctx._hit_sm_stream_prepared_figure("sample_size", "pdf")

    _spashiny_ctx.hit_sm_sample_size_pdf = hit_sm_sample_size_pdf

    @_spashiny_ctx.render.download(filename="sm_sample_distribution.png", media_type="image/png")
    def hit_sm_sample_size_png():
        yield from _spashiny_ctx._hit_sm_stream_prepared_figure("sample_size", "png")

    _spashiny_ctx.hit_sm_sample_size_png = hit_sm_sample_size_png

    @_spashiny_ctx.render.download(
        filename="sm_feature_distribution.pdf", media_type="application/pdf"
    )
    def hit_sm_feature_distribution_pdf():
        yield from _spashiny_ctx._hit_sm_stream_prepared_figure("feature_distribution", "pdf")

    _spashiny_ctx.hit_sm_feature_distribution_pdf = hit_sm_feature_distribution_pdf

    @_spashiny_ctx.render.download(filename="sm_feature_distribution.png", media_type="image/png")
    def hit_sm_feature_distribution_png():
        yield from _spashiny_ctx._hit_sm_stream_prepared_figure("feature_distribution", "png")

    _spashiny_ctx.hit_sm_feature_distribution_png = hit_sm_feature_distribution_png

    @_spashiny_ctx.render.download(
        filename="sm_spatial_variable_features.pdf", media_type="application/pdf"
    )
    def hit_sm_svm_pdf():
        yield from _spashiny_ctx._hit_sm_stream_prepared_figure("svm", "pdf")

    _spashiny_ctx.hit_sm_svm_pdf = hit_sm_svm_pdf

    @_spashiny_ctx.render.download(
        filename="sm_spatial_variable_features.png", media_type="image/png"
    )
    def hit_sm_svm_png():
        yield from _spashiny_ctx._hit_sm_stream_prepared_figure("svm", "png")

    _spashiny_ctx.hit_sm_svm_png = hit_sm_svm_png

    @_spashiny_ctx.render.ui
    def hit_sm_sample_size_worker_plot():
        return _spashiny_ctx._hit_sm_prepared_figure("sample_size")

    _spashiny_ctx.hit_sm_sample_size_worker_plot = hit_sm_sample_size_worker_plot

    @_spashiny_ctx.render.ui
    def hit_sm_feature_distribution_worker_plot():
        return _spashiny_ctx._hit_sm_prepared_figure("feature_distribution")

    _spashiny_ctx.hit_sm_feature_distribution_worker_plot = hit_sm_feature_distribution_worker_plot

    @_spashiny_ctx.render.ui
    def hit_sm_svm_worker_plot():
        return _spashiny_ctx._hit_sm_prepared_figure("svm")

    _spashiny_ctx.hit_sm_svm_worker_plot = hit_sm_svm_worker_plot

    @_spashiny_ctx.render.ui
    def hit_sm_sample_size_downloads():
        return _spashiny_ctx._hit_sm_prepared_figure("sample_size", downloads=True)

    _spashiny_ctx.hit_sm_sample_size_downloads = hit_sm_sample_size_downloads

    @_spashiny_ctx.render.ui
    def hit_sm_feature_distribution_downloads():
        return _spashiny_ctx._hit_sm_prepared_figure("feature_distribution", downloads=True)

    _spashiny_ctx.hit_sm_feature_distribution_downloads = hit_sm_feature_distribution_downloads

    @_spashiny_ctx.render.ui
    def hit_sm_svm_downloads():
        return _spashiny_ctx._hit_sm_prepared_figure("svm", downloads=True)

    _spashiny_ctx.hit_sm_svm_downloads = hit_sm_svm_downloads

    def hit_notify(message, type_="message", duration=4):
        """English-only Shiny notification with no icon."""
        try:
            _spashiny_ctx.ui.notification_show(message, type=type_, duration=duration)
        except Exception:
            pass

    _spashiny_ctx.hit_notify = hit_notify

    def hit_show_modal(title="Processing", message="Please wait..."):
        _spashiny_ctx.ui.modal_show(
            _spashiny_ctx.ui.modal(
                _spashiny_ctx.ui.p(message), title=title, easy_close=False, footer=None
            )
        )

    _spashiny_ctx.hit_show_modal = hit_show_modal

    def hit_close_modal():
        try:
            _spashiny_ctx.ui.modal_remove()
        except Exception:
            pass
        _spashiny_globals.release_unused_memory()

    _spashiny_ctx.hit_close_modal = hit_close_modal

    def add_sm_log(message):
        logs = _spashiny_ctx.sm_merge_log.get()
        timestamp = _spashiny_ctx.pd.Timestamp.now().strftime("%H:%M:%S")
        logs.append(f"{timestamp} - {message}")
        _spashiny_ctx.sm_merge_log.set(logs)
        print(message, flush=True)

    _spashiny_ctx.add_sm_log = add_sm_log

    def extract_sample_name(file_name):
        """Infer sample name from file name."""
        base_name = _spashiny_globals.os.path.splitext(file_name)[0]
        patterns = [
            "^adata_SM_(.*?)_raw$",
            "^adata_SM_(.*?)$",
            "^(.*?)_adata_SM_raw$",
            "^(.*?)_SM_raw$",
            "^(.*?)_adata$",
            "^(.*?)_raw$",
        ]
        for pattern in patterns:
            match = _spashiny_ctx.re.match(pattern, base_name, flags=_spashiny_ctx.re.IGNORECASE)
            if match and match.group(1):
                return match.group(1)
        return base_name

    _spashiny_ctx.extract_sample_name = extract_sample_name

    def create_info_plot(message="No data available", title="Information"):
        fig, ax = _spashiny_globals.plt.subplots(figsize=(8, 6))
        ax.text(0.5, 0.5, message, ha="center", va="center", transform=ax.transAxes, fontsize=14)
        ax.set_title(title)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")
        return fig

    _spashiny_ctx.create_info_plot = create_info_plot

    def get_active_sm_data():
        """Prefer integrated data; otherwise use merged data."""
        return (
            _spashiny_ctx.integrated_sm_data.get()
            if _spashiny_ctx.integrated_sm_data.get() is not None
            else _spashiny_ctx.merged_sm_data.get()
        )

    _spashiny_ctx.get_active_sm_data = get_active_sm_data

    def get_worker_sm_summary():
        """Only the current analysis' already-authorized compact summaries."""
        return (
            _spashiny_ctx.hit_sm_svm_metadata.get()
            or _spashiny_ctx.hit_sm_merge_metadata.get()
            or {}
        )

    _spashiny_ctx.get_worker_sm_summary = get_worker_sm_summary

    def get_prepared_sm_for_display():
        data = _spashiny_ctx.merged_sm_data.get()
        if data is not None:
            return (data, False)
        path = (
            _spashiny_ctx.hit_sm_svm_result_path.get()
            or _spashiny_ctx.hit_sm_merge_result_path.get()
        )
        return _spashiny_globals.read_h5ad_for_display(path) if path else (None, False)

    _spashiny_ctx.get_prepared_sm_for_display = get_prepared_sm_for_display

    def worker_sm_tables():
        """Rebuild display/CSV tables from saved counts, without loading X."""
        merged = _spashiny_ctx.hit_sm_merge_metadata.get() or {}
        svm = _spashiny_ctx.hit_sm_svm_metadata.get() or {}
        current = svm or merged
        counts = current.get("sample_counts") or {}
        files = {}
        if merged.get("sample_counts"):
            files["sample_stats.csv"] = _spashiny_ctx.pd.DataFrame(
                [
                    {
                        "Sample": name,
                        "Cells/Spots": int(count),
                        "Features": int(merged["n_vars"]),
                        "Status": "Worker prepared",
                    }
                    for name, count in merged["sample_counts"].items()
                ]
            )
        if counts:
            total = int(current.get("n_obs") or sum(counts.values()))
            files["merged_stats.csv"] = _spashiny_ctx.pd.DataFrame(
                [
                    {
                        "Sample": name,
                        "Cells/Spots": int(count),
                        "Percent": f"{int(count) / max(total, 1) * 100:.1f}%",
                    }
                    for name, count in counts.items()
                ]
            )
        if svm:
            before = merged.get("n_vars")
            after = int(svm["n_vars"])
            files["svm_results.csv"] = _spashiny_ctx.pd.DataFrame(
                {
                    "Metric": [
                        "Spatially variable metabolites",
                        "Features before SVM",
                        "Retained ratio",
                    ],
                    "Value": [
                        after,
                        int(before) if before is not None else "Not recorded",
                        (
                            f"{after / max(int(before), 1) * 100:.1f}%"
                            if before is not None
                            else "Not recorded"
                        ),
                    ],
                }
            )
        return files

    _spashiny_ctx.worker_sm_tables = worker_sm_tables

    def to_numpy(x):
        """Robust conversion to numpy."""
        if _spashiny_globals.torch.is_tensor(x):
            x = x.detach().cpu().numpy()
        elif isinstance(x, list):
            try:
                x = _spashiny_globals.np.asarray(x)
            except Exception:
                x = _spashiny_globals.np.array([_spashiny_globals.np.asarray(i) for i in x])
        if isinstance(x, _spashiny_globals.np.ndarray) and x.dtype == object:
            try:
                x = _spashiny_globals.np.stack(x)
            except Exception:
                x = _spashiny_globals.np.array([_spashiny_globals.np.asarray(i).ravel() for i in x])
        return _spashiny_globals.np.asarray(x)

    _spashiny_ctx.to_numpy = to_numpy

    def dense_row_sum(X):
        """Row sums for dense or sparse matrix."""
        try:
            vals = X.sum(axis=1)
            if hasattr(vals, "A1"):
                return vals.A1
            return _spashiny_globals.np.asarray(vals).ravel()
        except Exception:
            arr = _spashiny_globals.np.asarray(X)
            return arr.sum(axis=1).ravel()

    _spashiny_ctx.dense_row_sum = dense_row_sum

    def safe_density_and_mean(X):
        try:
            if hasattr(X, "nnz"):
                total = X.shape[0] * X.shape[1]
                density = X.nnz / total * 100 if total else 0.0
                mean_expr = X.mean()
                if hasattr(mean_expr, "A1"):
                    mean_expr = float(mean_expr.A1[0])
                else:
                    mean_expr = float(mean_expr)
                return (density, mean_expr)
            else:
                arr = _spashiny_globals.np.asarray(X)
                density = (
                    _spashiny_globals.np.count_nonzero(arr) / arr.size * 100 if arr.size else 0.0
                )
                mean_expr = float(_spashiny_globals.np.mean(arr)) if arr.size else 0.0
                return (density, mean_expr)
        except Exception:
            return (None, None)

    _spashiny_ctx.safe_density_and_mean = safe_density_and_mean

    def serializable_loss_dict(loss_dict):
        if loss_dict is None:
            return {}
        out = {}
        for k, v in loss_dict.items():
            try:
                if isinstance(v, (list, tuple)):
                    out[k] = [float(x) for x in v]
                elif _spashiny_globals.torch.is_tensor(v):
                    out[k] = [float(x) for x in v.detach().cpu().numpy().ravel().tolist()]
                elif isinstance(v, _spashiny_globals.np.ndarray):
                    out[k] = [float(x) for x in v.ravel().tolist()]
                else:
                    out[k] = v
            except Exception:
                out[k] = str(v)
        return out

    _spashiny_ctx.serializable_loss_dict = serializable_loss_dict

    def align_sm_var_metadata_to_merged(merged_adata, reference_adata, reference_name):
        ref_var = reference_adata.var.copy()
        if ref_var.index.has_duplicates:
            ref_var = ref_var[~ref_var.index.duplicated(keep="first")]
        aligned_var = ref_var.reindex(merged_adata.var_names)
        merged_adata.var = aligned_var.copy()
        missing_count = int(aligned_var.isna().all(axis=1).sum()) if aligned_var.shape[1] else 0
        if missing_count:
            _spashiny_ctx.add_sm_log(
                f"Variable metadata copied from '{reference_name}' with {missing_count} feature(s) missing metadata."
            )
        else:
            _spashiny_ctx.add_sm_log(
                f"Variable metadata was copied from reference sample '{reference_name}'."
            )

    _spashiny_ctx.align_sm_var_metadata_to_merged = align_sm_var_metadata_to_merged

    def save_fig_to_temp_png(fig, prefix="plot", dpi=300):
        tmp = _spashiny_ctx.tempfile.NamedTemporaryFile(prefix=prefix, suffix=".png", delete=False)
        tmp.close()
        fig.savefig(tmp.name, dpi=dpi, bbox_inches="tight", facecolor="white")
        return tmp.name

    _spashiny_ctx.save_fig_to_temp_png = save_fig_to_temp_png

    def stream_file(path):
        with open(path, "rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk

    _spashiny_ctx.stream_file = stream_file

    def get_integrated_sm_for_display(adata_obj=None):
        if adata_obj is not None:
            return (adata_obj, False)
        try:
            cached = _spashiny_ctx.integrated_sm_data.get()
            if cached is not None:
                return (cached, False)
        except Exception:
            pass
        try:
            result_path = _spashiny_ctx.integrated_sm_data_path.get()
        except Exception:
            result_path = None
        if not result_path:
            result_path, _status, _job = _spashiny_ctx._cloud_integration_result_state(
                _spashiny_ctx.vae_summary.get() or {},
                workflow_name="hit_sm_multi_sample_integration",
            )
        return _spashiny_globals.read_h5ad_for_display(result_path)

    _spashiny_ctx.get_integrated_sm_for_display = get_integrated_sm_for_display

    @_spashiny_ctx.render.ui
    def vae_resource_mode_details():
        return _spashiny_ctx.ui.div()

    _spashiny_ctx.vae_resource_mode_details = vae_resource_mode_details

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.vae_use_original_params)
    def vae_use_original_params():
        _spashiny_ctx.model_config.set(
            _spashiny_globals.tutorial_model_defaults(_spashiny_globals.smt)
        )
        _spashiny_ctx.training_config.set(
            _spashiny_globals.tutorial_training_defaults(_spashiny_globals.smt)
        )

    _spashiny_ctx.vae_use_original_params = vae_use_original_params

    def build_sm_sample_size_figure():
        sample_data = _spashiny_ctx.sm_sample_data.get()
        counts = _spashiny_ctx.get_worker_sm_summary().get("sample_counts") or {}
        if not sample_data and (not counts):
            return _spashiny_ctx.create_info_plot(
                "Please upload sample data first.", "Sample Size Distribution"
            )
        names = list(sample_data.keys()) if sample_data else list(counts)
        sizes = (
            [adata_obj.n_obs for adata_obj in sample_data.values()]
            if sample_data
            else list(counts.values())
        )
        fig, ax = _spashiny_globals.plt.subplots(figsize=(10, 6))
        bars = ax.bar(names, sizes, color="lightblue")
        ax.set_title("Sample Size Distribution")
        ax.set_ylabel("Cells/Spots")
        for bar in bars:
            height = bar.get_height()
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                height,
                f"{int(height):,}",
                ha="center",
                va="bottom",
            )
        _spashiny_globals.plt.xticks(rotation=45)
        _spashiny_globals.plt.tight_layout()
        return fig

    _spashiny_ctx.build_sm_sample_size_figure = build_sm_sample_size_figure

    def build_sm_feature_distribution_figure():
        sample_data = _spashiny_ctx.sm_sample_data.get()
        if not sample_data:
            data, should_close = _spashiny_ctx.get_prepared_sm_for_display()
            try:
                if data is not None and "sample" in data.obs and ("total_intensity" in data.obs):
                    fig, ax = _spashiny_globals.plt.subplots(figsize=(10, 6))
                    for name, frame in data.obs.groupby("sample", observed=True):
                        intensities = _spashiny_ctx.pd.to_numeric(
                            frame["total_intensity"], errors="coerce"
                        ).dropna()
                        if len(intensities) > 1 and intensities.nunique() > 1:
                            _spashiny_ctx.sns.kdeplot(
                                intensities, label=str(name), ax=ax, fill=True, alpha=0.35
                            )
                    ax.set(title="Feature Intensity Distribution", xlabel="Total Intensity")
                    if ax.get_legend_handles_labels()[0]:
                        ax.legend()
                    fig.tight_layout()
                    return fig
                if data is not None:
                    return _spashiny_ctx.create_info_plot(
                        "Per-spot total_intensity was not recorded in this worker result.",
                        "Feature Intensity Distribution",
                    )
            finally:
                _spashiny_globals.close_display_h5ad(data, should_close)
        if not sample_data:
            return _spashiny_ctx.create_info_plot(
                "Please upload sample data first.", "Feature Intensity Distribution"
            )
        fig, ax = _spashiny_globals.plt.subplots(figsize=(10, 6))
        for name, adata_obj in sample_data.items():
            try:
                if "total_intensity" in adata_obj.obs.columns:
                    intensities = (
                        _spashiny_ctx.pd.to_numeric(
                            adata_obj.obs["total_intensity"], errors="coerce"
                        )
                        .dropna()
                        .values
                    )
                else:
                    intensities = _spashiny_ctx.dense_row_sum(adata_obj.X)
                if len(intensities) > 0:
                    _spashiny_ctx.sns.kdeplot(intensities, label=name, ax=ax, fill=True, alpha=0.35)
            except Exception as e:
                _spashiny_ctx.add_sm_log(f"Could not draw density for sample '{name}': {str(e)}")
        ax.set_title("Feature Intensity Distribution")
        ax.set_xlabel("Total Intensity")
        ax.legend()
        _spashiny_globals.plt.tight_layout()
        return fig

    _spashiny_ctx.build_sm_feature_distribution_figure = build_sm_feature_distribution_figure

    def build_svm_figure():
        data = _spashiny_ctx.merged_sm_data.get()
        if data is None:
            preview, should_close = _spashiny_ctx.get_prepared_sm_for_display()
            try:
                if preview is None or not _spashiny_ctx.hit_sm_svm_metadata.get():
                    return _spashiny_ctx.create_info_plot(
                        "Please run SVM analysis first.", "SVM Summary"
                    )
                if "morans_i" in preview.var:
                    top = preview.var.sort_values("morans_i", ascending=False).head(20)
                    fig, ax = _spashiny_globals.plt.subplots(figsize=(8, 6))
                    ax.barh(
                        top.index.astype(str)[::-1], top["morans_i"].iloc[::-1], color="steelblue"
                    )
                    ax.set(
                        title="Top Spatially Variable Metabolites",
                        xlabel="Moran's I",
                        ylabel="Feature",
                    )
                else:
                    merged = _spashiny_ctx.hit_sm_merge_metadata.get() or {}
                    after = int(_spashiny_ctx.hit_sm_svm_metadata.get()["n_vars"])
                    before = merged.get("n_vars")
                    fig, ax = _spashiny_globals.plt.subplots(figsize=(8, 6))
                    labels, values = (["Retained"], [after])
                    if before is not None:
                        labels.append("Removed")
                        values.append(max(int(before) - after, 0))
                    ax.bar(labels, values, color=["tomato", "lightgray"][: len(labels)])
                    ax.set(title="SVM Filtering Summary", ylabel="Feature Count")
                fig.tight_layout()
                return fig
            finally:
                _spashiny_globals.close_display_h5ad(preview, should_close)
        if "morans_i" not in data.var.columns and "highly_variable_moranI" not in data.var.columns:
            return _spashiny_ctx.create_info_plot("Please run SVM analysis first.", "SVM Summary")
        fig, ax = _spashiny_globals.plt.subplots(figsize=(8, 6))
        if "morans_i" in data.var.columns:
            top_df = data.var.sort_values("morans_i", ascending=False).head(20).copy()
            top_df["feature"] = top_df.index.astype(str)
            ax.barh(top_df["feature"][::-1], top_df["morans_i"][::-1], color="steelblue")
            ax.set_title("Top Spatially Variable Metabolites")
            ax.set_xlabel("Moran's I")
            ax.set_ylabel("Feature")
        else:
            after_n = int(data.uns.get("n_features_after_svm", data.n_vars))
            before_n = int(data.uns.get("n_features_before_svm", data.n_vars))
            removed_n = max(before_n - after_n, 0)
            ax.bar(["Retained", "Removed"], [after_n, removed_n], color=["tomato", "lightgray"])
            ax.set_title("SVM Filtering Summary")
            ax.set_ylabel("Feature Count")
        _spashiny_globals.plt.tight_layout()
        return fig

    _spashiny_ctx.build_svm_figure = build_svm_figure

    def build_sm_debatch_umap_figure():
        data, should_close = _spashiny_ctx.get_integrated_sm_for_display()
        try:
            if data is None or "X_umap" not in data.obsm:
                return _spashiny_ctx.create_info_plot(
                    "UMAP will be shown after ConditionalVAE integration.", "Debatched UMAP"
                )
            fig, ax = _spashiny_globals.plt.subplots(figsize=(8, 6))
            if "sample" in data.obs.columns:
                _spashiny_globals.sc.pl.umap(
                    data,
                    color="sample",
                    ax=ax,
                    show=False,
                    title="Debatched UMAP by Sample",
                    size=6,
                )
            else:
                _spashiny_globals.sc.pl.umap(
                    data, ax=ax, show=False, title="Debatched UMAP", size=6
                )
            return fig
        finally:
            _spashiny_globals.close_display_h5ad(data, should_close)

    _spashiny_ctx.build_sm_debatch_umap_figure = build_sm_debatch_umap_figure

    def build_sm_batch_effect_evaluation_figure():
        data, should_close = _spashiny_ctx.get_integrated_sm_for_display()
        try:
            if data is None or "X_umap" not in data.obsm:
                return _spashiny_ctx.create_info_plot(
                    "UMAP will be shown after ConditionalVAE integration.",
                    "Batch Effect Evaluation",
                )
            fig, axes = _spashiny_globals.plt.subplots(1, 2, figsize=(12, 5))
            if "sample" in data.obs.columns:
                _spashiny_globals.sc.pl.umap(
                    data, color="sample", ax=axes[0], show=False, title="By Sample", size=6
                )
            else:
                axes[0].text(
                    0.5,
                    0.5,
                    "No sample column.",
                    ha="center",
                    va="center",
                    transform=axes[0].transAxes,
                )
                axes[0].set_title("By Sample")
            if "VAE_clusters" in data.obs.columns:
                _spashiny_globals.sc.pl.umap(
                    data, color="VAE_clusters", ax=axes[1], show=False, title="By Cluster", size=6
                )
            else:
                axes[1].text(
                    0.5,
                    0.5,
                    "VAE cluster column was not found.",
                    ha="center",
                    va="center",
                    transform=axes[1].transAxes,
                )
                axes[1].set_title("By Cluster")
            _spashiny_globals.plt.tight_layout()
            return fig
        finally:
            _spashiny_globals.close_display_h5ad(data, should_close)

    _spashiny_ctx.build_sm_batch_effect_evaluation_figure = build_sm_batch_effect_evaluation_figure

    def build_vae_training_loss_figure():
        loss_dict = _spashiny_ctx.vae_loss_dict.get()
        if loss_dict is None:
            data = _spashiny_ctx.integrated_sm_data.get()
            if data is not None and "vae_training_loss" in data.uns:
                loss_dict = data.uns["vae_training_loss"]
        if loss_dict is None:
            return _spashiny_ctx.create_info_plot(
                "Please run ConditionalVAE training first.", "Training Loss"
            )
        loss_dict = _spashiny_ctx.serializable_loss_dict(loss_dict)
        fig, ax = _spashiny_globals.plt.subplots(figsize=(10, 6))
        plotted = False
        if "total_loss" in loss_dict:
            ax.plot(loss_dict["total_loss"], label="Total Loss", linewidth=2)
            plotted = True
        if "reconst" in loss_dict:
            ax.plot(loss_dict["reconst"], label="Reconstruction", alpha=0.8)
            plotted = True
        if "kldiv" in loss_dict:
            ax.plot(loss_dict["kldiv"], label="KL Divergence", alpha=0.8)
            plotted = True
        if not plotted:
            for key, values in loss_dict.items():
                try:
                    arr = _spashiny_globals.np.asarray(values, dtype=float).reshape(-1)
                    if arr.size > 0:
                        ax.plot(arr, label=str(key), linewidth=1.6, alpha=0.85)
                        plotted = True
                except Exception:
                    pass
        if not plotted:
            _spashiny_globals.plt.close(fig)
            return _spashiny_ctx.create_info_plot(
                "Loss record exists but no numeric series could be plotted.", "Training Loss"
            )
        ax.set_xlabel("Epoch")
        ax.set_ylabel("Loss")
        ax.set_title("ConditionalVAE Training Loss")
        ax.legend()
        ax.grid(True, alpha=0.3)
        _spashiny_globals.plt.tight_layout()
        return fig

    _spashiny_ctx.build_vae_training_loss_figure = build_vae_training_loss_figure

    @_spashiny_ctx.reactive.Calc
    def parsed_sm_sample_list():
        txt = _spashiny_ctx.input.sm_sample_list()
        if not txt:
            return []
        return [s.strip() for s in txt.split(",") if s.strip()]

    _spashiny_ctx.parsed_sm_sample_list = parsed_sm_sample_list

    def _hydrate_hit_sm_worker_managed_example(payload=None, *, force=False):
        """Hydrate only lightweight UI state for a session-bound SM bundle."""
        if not _spashiny_globals.SPASHINY_LAB_PROFILE:
            return False
        if not force and _spashiny_ctx.hit_sm_input_source_mode.get() not in {"", "EXAMPLE"}:
            return False
        action_id = _spashiny_ctx._latest_example_action_for("sm-five-sample-batch-example")
        if not action_id:
            return False
        payload = payload if isinstance(payload, dict) else {}
        samples = [str(x).strip() for x in payload.get("sample_ids") or [] if str(x).strip()]
        if not samples:
            samples = _spashiny_ctx.parsed_sm_sample_list()
        if not samples:
            samples = ["R114_T", "S15_T", "X49_T", "Y27_T", "Y7_T"]
        _spashiny_ctx.sm_sample_data.set({})
        _spashiny_ctx.hit_sm_input_source_mode.set("EXAMPLE")
        _spashiny_ctx.merged_sm_data.set(None)
        _spashiny_ctx.integrated_sm_data.set(None)
        _spashiny_ctx.hit_sm_merge_summary.set({})
        _spashiny_ctx.hit_sm_merge_metadata.set({})
        _spashiny_ctx.hit_sm_merge_result_path.set("")
        _spashiny_ctx.hit_sm_svm_summary.set({})
        _spashiny_ctx.hit_sm_svm_metadata.set({})
        _spashiny_ctx.hit_sm_svm_result_path.set("")
        _spashiny_ctx.ui.update_text_area("sm_sample_list", value=", ".join(samples))
        _spashiny_ctx.sm_merge_status.set(
            f"{len(samples)} read-only SM example inputs are bound to this session. Click Run Merge to stage the GPU-worker merge."
        )
        _spashiny_ctx.add_sm_log(
            f"Bound {len(samples)} read-only SM example inputs to the GPU worker. No H5AD is loaded in the Shiny process."
        )
        return True

    _spashiny_ctx._hydrate_hit_sm_worker_managed_example = _hydrate_hit_sm_worker_managed_example

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(
        _spashiny_ctx.input.cloud_example_action_activated, ignore_none=True
    )
    def hydrate_hit_sm_worker_managed_example():
        try:
            payload = _spashiny_ctx.input.cloud_example_action_activated() or {}
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            return
        if str(payload.get("action_id") or "") != "sm-five-sample-batch-example" or not bool(
            payload.get("ready")
        ):
            return
        if str(payload.get("analysis_session_id") or "") != str(
            _spashiny_ctx._cloud_analysis_session_id() or ""
        ):
            return
        _spashiny_ctx.hit_sm_example_merge_requested.set(False)
        if _spashiny_ctx._hydrate_hit_sm_worker_managed_example(payload, force=True):
            _spashiny_ctx._show_multisample_feedback_modal(
                "Example Inputs Ready",
                "Five read-only SM H5AD inputs are bound to this session.",
                detail="No large H5AD file is loaded in the Web process. Continue with Run Merge.",
            )
            _spashiny_ctx.hit_notify(
                "Five example inputs are ready for worker-managed merging. Click Run Merge, then Run ConditionalVAE Integration.",
                type_="message",
                duration=8,
            )

    _spashiny_ctx.hydrate_hit_sm_worker_managed_example = hydrate_hit_sm_worker_managed_example

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.load_hit_sm_example)
    def load_hit_sm_example():
        example_dir = _spashiny_globals.EXAMPLE_SM_BATCH_DIR
        _spashiny_ctx.hit_sm_input_source_mode.set("EXAMPLE")
        if _spashiny_globals.SPASHINY_LAB_PROFILE:
            try:
                example_files = _spashiny_globals.get_allowlisted_example_files(
                    example_dir, _spashiny_globals.EXAMPLE_SM_BATCH_RAW_FILES
                )
            except FileNotFoundError as exc:
                _spashiny_ctx.add_sm_log(str(exc))
                _spashiny_ctx.sm_merge_status.set("Bundled SM examples are unavailable")
                _spashiny_ctx.hit_notify(
                    "One or more bundled raw SM examples are missing.", type_="warning"
                )
                return
            sample_names = [_spashiny_ctx.extract_sample_name(path.name) for path in example_files]
            _spashiny_ctx.sm_sample_data.set({})
            _spashiny_ctx.merged_sm_data.set(None)
            _spashiny_ctx.integrated_sm_data.set(None)
            _spashiny_ctx.vae_model.set(None)
            _spashiny_ctx.vae_loss_dict.set(None)
            _spashiny_ctx.vae_job_dir.set(None)
            _spashiny_ctx.integrated_sm_data_path.set(None)
            _spashiny_ctx.vae_summary.set(None)
            _spashiny_ctx.vae_model_state_path.set(None)
            _spashiny_ctx.vae_training_status.set("Ready for worker submission")
            _spashiny_ctx.hit_sm_example_merge_requested.set(False)
            _spashiny_ctx.hit_sm_merge_summary.set({})
            _spashiny_ctx.hit_sm_merge_metadata.set({})
            _spashiny_ctx.hit_sm_merge_result_path.set("")
            _spashiny_ctx.hit_sm_svm_summary.set({})
            _spashiny_ctx.hit_sm_svm_metadata.set({})
            _spashiny_ctx.hit_sm_svm_result_path.set("")
            _spashiny_ctx.ui.update_text_area("sm_sample_list", value=", ".join(sample_names))
            _spashiny_ctx.sm_merge_status.set(
                f"Bound {len(sample_names)} read-only SM example samples; worker merge and SVM are pending."
            )
            _spashiny_ctx.add_sm_log(
                "Bound five read-only SM example inputs. No H5AD was read in Shiny; click Run ConditionalVAE Integration to execute merge, SVM filtering, and training in the GPU worker."
            )
            _spashiny_ctx.hit_notify(
                f"Bound {len(sample_names)} SM example samples. Click Run ConditionalVAE Integration to continue.",
                type_="message",
                duration=8,
            )
            return
        if not example_dir.exists():
            _spashiny_ctx.add_sm_log(f"Example SM directory was not found: {example_dir}")
            _spashiny_ctx.hit_notify(
                "Example SM directory was not found.", type_="error", duration=8
            )
            return
        try:
            example_files = _spashiny_globals.get_allowlisted_example_files(
                example_dir, _spashiny_globals.EXAMPLE_SM_BATCH_RAW_FILES
            )
        except FileNotFoundError as exc:
            _spashiny_ctx.add_sm_log(str(exc))
            _spashiny_ctx.hit_notify(
                "One or more bundled raw SM examples are missing.", type_="warning"
            )
            return
        _spashiny_ctx.hit_show_modal("Loading Example SM Data", "Reading bundled SM .h5ad files...")
        try:
            loaded_data = {}
            loaded_samples = []
            for path in example_files:
                sample_name = _spashiny_ctx.extract_sample_name(path.name)
                unique_sample = sample_name
                counter = 2
                while unique_sample in loaded_data:
                    unique_sample = f"{sample_name}_{counter}"
                    counter += 1
                adata_obj = _spashiny_globals.compact_adata_X(
                    _spashiny_globals.sc.read_h5ad(str(path))
                )
                adata_obj.obs_names_make_unique()
                adata_obj.obs["sample"] = unique_sample
                loaded_data[unique_sample] = adata_obj
                loaded_samples.append(unique_sample)
                _spashiny_ctx.add_sm_log(
                    f"Loaded example SM sample '{unique_sample}' with shape {adata_obj.shape}."
                )
            _spashiny_ctx.sm_sample_data.set(loaded_data)
            _spashiny_ctx.merged_sm_data.set(None)
            _spashiny_ctx.integrated_sm_data.set(None)
            _spashiny_ctx.vae_model.set(None)
            _spashiny_ctx.vae_loss_dict.set(None)
            _spashiny_ctx.vae_job_dir.set(None)
            _spashiny_ctx.integrated_sm_data_path.set(None)
            _spashiny_ctx.vae_summary.set(None)
            _spashiny_ctx.vae_model_state_path.set(None)
            _spashiny_ctx.vae_training_status.set("Waiting")
            _spashiny_ctx.sm_merge_status.set(f"Loaded {len(loaded_samples)} example sample(s)")
            _spashiny_ctx.ui.update_text_area("sm_sample_list", value=", ".join(loaded_samples))
            _spashiny_ctx.add_sm_log(f"Loaded example SM directory: {example_dir}")
            _spashiny_ctx.hit_notify(
                f"Loaded {len(loaded_samples)} example SM sample(s). Click Run Merge to continue.",
                type_="message",
                duration=6,
            )
        except Exception as e:
            _spashiny_ctx.add_sm_log(f"Example SM loading failed: {str(e)}")
            _spashiny_ctx.sm_merge_status.set("Example loading failed")
            _spashiny_ctx.hit_notify(
                f"Example SM loading failed: {str(e)}", type_="error", duration=8
            )
            _spashiny_ctx.traceback.print_exc()
        finally:
            _spashiny_ctx.hit_close_modal()
            _spashiny_globals.release_unused_memory()

    _spashiny_ctx.load_hit_sm_example = load_hit_sm_example

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.auto_detect_samples)
    def auto_detect_samples():
        files = _spashiny_ctx.input.sm_upload()
        if not files:
            if _spashiny_ctx._hydrate_hit_sm_worker_managed_example():
                _spashiny_ctx.hit_notify(
                    "Detected five session-bound example samples.", type_="message"
                )
                return
            loaded_samples = list(_spashiny_ctx.sm_sample_data.get().keys())
            if loaded_samples:
                sample_text = ", ".join(loaded_samples)
                _spashiny_ctx.ui.update_text_area("sm_sample_list", value=sample_text)
                _spashiny_ctx.add_sm_log(f"Detected loaded samples: {sample_text}")
                _spashiny_ctx.hit_notify(
                    f"Detected {len(loaded_samples)} loaded sample(s).", type_="message"
                )
                return
            _spashiny_ctx.add_sm_log("No uploaded files were found.")
            _spashiny_ctx.hit_notify("Please upload .h5ad files first.", type_="warning")
            return
        detected_samples = []
        for file in files:
            detected_samples.append(_spashiny_ctx.extract_sample_name(file["name"]))
        sample_text = ", ".join(detected_samples)
        _spashiny_ctx.ui.update_text_area("sm_sample_list", value=sample_text)
        _spashiny_ctx.add_sm_log(f"Detected samples: {sample_text}")
        _spashiny_ctx.hit_notify(
            f"Detected {len(detected_samples)} sample name(s).", type_="message"
        )

    _spashiny_ctx.auto_detect_samples = auto_detect_samples

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.sm_upload)
    def handle_sm_upload():
        files = _spashiny_ctx.input.sm_upload()
        if not files:
            return
        previous_source_mode = _spashiny_ctx.hit_sm_input_source_mode.get()
        _spashiny_ctx.hit_sm_input_source_mode.set("USER_UPLOAD")
        _spashiny_ctx.merged_sm_data.set(None)
        _spashiny_ctx.integrated_sm_data.set(None)
        _spashiny_ctx.hit_sm_merge_summary.set({})
        _spashiny_ctx.hit_sm_merge_metadata.set({})
        _spashiny_ctx.hit_sm_merge_result_path.set("")
        _spashiny_ctx.hit_sm_svm_summary.set({})
        _spashiny_ctx.hit_sm_svm_metadata.set({})
        _spashiny_ctx.hit_sm_svm_result_path.set("")
        _spashiny_ctx.sm_sample_data.set({})
        _spashiny_ctx.integrated_sm_data_path.set("")
        _spashiny_ctx.vae_summary.set(None)
        _spashiny_ctx.vae_model.set(None)
        _spashiny_ctx.vae_training_status.set("Waiting for uploaded input processing.")
        _spashiny_ctx.hit_show_modal("Loading Files", "Reading uploaded .h5ad files...")
        try:
            samples = _spashiny_ctx.parsed_sm_sample_list()
            if not samples or previous_source_mode == "EXAMPLE":
                detected_samples = [
                    _spashiny_ctx.extract_sample_name(file["name"]) for file in files
                ]
                _spashiny_ctx.ui.update_text_area(
                    "sm_sample_list", value=", ".join(detected_samples)
                )
                samples = detected_samples
                _spashiny_ctx.add_sm_log(
                    "Sample list was filled from the selected upload filenames."
                )
            current_data = dict(_spashiny_ctx.sm_sample_data.get())
            files_processed = 0
            for file in files:
                file_name = file["name"]
                sample_name = _spashiny_ctx.extract_sample_name(file_name)
                if sample_name not in samples:
                    _spashiny_ctx.add_sm_log(
                        f"Skipped '{sample_name}' because it is not in the sample list."
                    )
                    continue
                try:
                    adata_obj = _spashiny_globals.compact_adata_X(
                        _spashiny_globals.sc.read_h5ad(file["datapath"])
                    )
                    adata_obj.obs_names_make_unique()
                    adata_obj.obs["sample"] = sample_name
                    current_data[sample_name] = adata_obj
                    files_processed += 1
                    _spashiny_ctx.add_sm_log(
                        f"Loaded sample '{sample_name}' with shape {adata_obj.shape}."
                    )
                except Exception as e:
                    _spashiny_ctx.add_sm_log(f"Failed to load '{sample_name}': {str(e)}")
            _spashiny_ctx.sm_sample_data.set(current_data)
            if files_processed > 0:
                _spashiny_ctx.sm_merge_status.set(f"Loaded {files_processed} sample(s)")
                _spashiny_ctx.hit_notify(f"Loaded {files_processed} sample(s).", type_="message")
            else:
                _spashiny_ctx.hit_notify(
                    "No sample was loaded successfully.", type_="error", duration=6
                )
        except Exception as e:
            _spashiny_ctx.add_sm_log(f"Upload handling failed: {str(e)}")
            _spashiny_ctx.hit_notify(f"Upload handling failed: {str(e)}", type_="error", duration=8)
            _spashiny_ctx.traceback.print_exc()
        finally:
            _spashiny_ctx.hit_close_modal()

    _spashiny_ctx.handle_sm_upload = handle_sm_upload

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.run_sm_merge)
    def run_sm_merge():
        sample_data = _spashiny_ctx.sm_sample_data.get()
        samples = _spashiny_ctx.parsed_sm_sample_list()
        hit_sm_example_action_id = (
            _spashiny_ctx._latest_example_action_for("sm-five-sample-batch-example")
            if _spashiny_globals.SPASHINY_LAB_PROFILE
            and _spashiny_ctx.hit_sm_input_source_mode.get() == "EXAMPLE"
            else ""
        )
        if _spashiny_globals.SPASHINY_LAB_PROFILE and hit_sm_example_action_id:
            _spashiny_ctx._hydrate_hit_sm_worker_managed_example()
            try:
                from cloud.workflow_registry import HIT_SM_MULTI_SAMPLE_INTEGRATION

                requested_resource = _spashiny_ctx.input.vae_compute_resource() or "auto"
                job = _spashiny_ctx._submit_cloud_example_action_job(
                    workflow_name=HIT_SM_MULTI_SAMPLE_INTEGRATION,
                    example_action_ids=("sm-five-sample-batch-example",),
                    parameters={"stage": "merge", "custom_params": {"run_spatial_variable": False}},
                    requested_resource=requested_resource,
                )
                _spashiny_ctx.hit_sm_example_merge_requested.set(True)
                _spashiny_ctx.hit_sm_merge_summary.set(
                    {"cloud_job_id": job.job_id, "status": "QUEUED", "stage": "merge"}
                )
                _spashiny_ctx.sm_merge_status.set(f"Merge job submitted: {job.job_id}")
                _spashiny_ctx.add_sm_log(
                    f"Five-sample SM merge submitted to the independent GPU worker: {job.job_id}"
                )
                _spashiny_ctx._show_multisample_prepare_modal(
                    job_id=job.job_id, title="Five-sample SM merge"
                )
                _spashiny_ctx.hit_notify(
                    "Merge job submitted. Wait for completion before running SVM analysis.",
                    type_="message",
                    duration=8,
                )
            except Exception as exc:
                _spashiny_ctx.sm_merge_status.set("Merge submission failed")
                _spashiny_ctx.add_sm_log(f"Worker SM merge submission failed: {exc}")
                _spashiny_ctx.hit_notify(
                    f"Could not submit SM merge: {exc}", type_="error", duration=8
                )
            return
        if not sample_data:
            _spashiny_ctx.add_sm_log("No sample data is available.")
            _spashiny_ctx.hit_notify("Please upload sample files first.", type_="warning")
            return
        if not samples:
            _spashiny_ctx.add_sm_log("Sample list is empty.")
            _spashiny_ctx.hit_notify("Please provide sample names first.", type_="warning")
            return
        _spashiny_ctx.hit_show_modal(
            "Merging SM Data", "Merging samples and preparing normalized layers..."
        )
        _spashiny_ctx.is_merging.set(True)
        try:
            _spashiny_ctx.add_sm_log("Started SM sample merge.")
            merge_dict = {}
            for sample in samples:
                if sample in sample_data:
                    merge_dict[sample] = sample_data[sample]
            if not merge_dict:
                _spashiny_ctx.add_sm_log("No matching sample was found for merging.")
                _spashiny_ctx.hit_notify("No matching sample was found for merging.", type_="error")
                return
            if _spashiny_ctx.input.sm_merge_method() == "intersect":
                common_features = set.intersection(
                    *[set(adata_obj.var_names) for adata_obj in merge_dict.values()]
                )
                if not common_features:
                    _spashiny_ctx.add_sm_log("No common features were found across samples.")
                    _spashiny_ctx.hit_notify(
                        "No common features were found across samples.", type_="error"
                    )
                    return
                common_features = list(common_features)
                for k in list(merge_dict.keys()):
                    merge_dict[k] = _spashiny_globals.compact_adata_X(
                        merge_dict[k][:, common_features].copy()
                    )
                _spashiny_ctx.add_sm_log(
                    f"Using feature intersection: {len(common_features)} common features retained."
                )
            merged = _spashiny_ctx.ad.concat(merge_dict, label="sample", join="inner")
            merged.obs_names_make_unique()
            first_sample = next(iter(merge_dict))
            _spashiny_ctx.align_sm_var_metadata_to_merged(
                merged, merge_dict[first_sample], first_sample
            )
            _spashiny_globals.set_compact_layer(merged, "counts")
            if _spashiny_ctx.input.sm_normalize():
                _spashiny_globals.sc.pp.normalize_total(merged, target_sum=10000.0)
                _spashiny_ctx.add_sm_log(
                    "Merged SM data normalized with target_sum=1e4 (SpatialMETA tutorial; no log1p)."
                )
            else:
                _spashiny_ctx.add_sm_log("Normalization was skipped by user setting.")
            _spashiny_globals.set_compact_layer(merged, "normalized")
            _spashiny_ctx.merged_sm_data.set(merged)
            _spashiny_ctx.integrated_sm_data.set(None)
            _spashiny_ctx.vae_model.set(None)
            _spashiny_ctx.vae_loss_dict.set(None)
            _spashiny_ctx.vae_job_dir.set(None)
            _spashiny_ctx.integrated_sm_data_path.set(None)
            _spashiny_ctx.vae_summary.set(None)
            _spashiny_ctx.vae_model_state_path.set(None)
            _spashiny_ctx.vae_training_status.set("Waiting")
            _spashiny_ctx.sm_merge_status.set("Merge completed")
            _spashiny_ctx.add_sm_log(f"Merged data shape: {merged.shape}")
            _spashiny_ctx.hit_notify(
                f"Merge completed: {merged.n_obs} cells/spots, {merged.n_vars} features.",
                type_="message",
            )
        except Exception as e:
            _spashiny_ctx.add_sm_log(f"Merge failed: {str(e)}")
            _spashiny_ctx.sm_merge_status.set("Merge failed")
            _spashiny_ctx.hit_notify(f"Merge failed: {str(e)}", type_="error", duration=8)
            _spashiny_ctx.traceback.print_exc()
        finally:
            _spashiny_ctx.is_merging.set(False)
            _spashiny_ctx.hit_close_modal()

    _spashiny_ctx.run_sm_merge = run_sm_merge

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.run_svm_analysis)
    def run_svm_analysis():
        data = _spashiny_ctx.merged_sm_data.get()
        hit_sm_example_action_id = (
            _spashiny_ctx._latest_example_action_for("sm-five-sample-batch-example")
            if _spashiny_globals.SPASHINY_LAB_PROFILE
            and _spashiny_ctx.hit_sm_input_source_mode.get() == "EXAMPLE"
            else ""
        )
        if _spashiny_globals.SPASHINY_LAB_PROFILE and hit_sm_example_action_id:
            if not _spashiny_ctx.hit_sm_merge_result_path.get():
                _spashiny_ctx.hit_notify(
                    "Click Run Merge and wait for its worker job to finish before SVM filtering.",
                    type_="warning",
                )
                return
            try:
                from cloud.workflow_registry import HIT_SM_MULTI_SAMPLE_INTEGRATION

                requested_resource = _spashiny_ctx.input.vae_compute_resource() or "auto"
                custom_params = {
                    "run_spatial_variable": True,
                    "n_top_variable": int(_spashiny_ctx.input.svm_top_genes() or 2000),
                    "spatial_variable_batch_key": "sample",
                    "spatial_variable_min_samples": 3,
                    "spatial_variable_min_frac": 0.9,
                    "spatial_variable_min_logfc": 3,
                }
                job = _spashiny_ctx._submit_cloud_example_action_job(
                    workflow_name=HIT_SM_MULTI_SAMPLE_INTEGRATION,
                    example_action_ids=("sm-five-sample-batch-example",),
                    parameters={"stage": "qc", "custom_params": custom_params},
                    requested_resource=requested_resource,
                )
                _spashiny_ctx.hit_sm_svm_summary.set(
                    {"cloud_job_id": job.job_id, "status": "QUEUED", "stage": "qc"}
                )
                _spashiny_ctx.sm_merge_status.set(f"SVM filtering job submitted: {job.job_id}")
                _spashiny_ctx.add_sm_log(
                    f"Spatial-variable metabolite filtering submitted to the GPU worker: {job.job_id}"
                )
                _spashiny_ctx._show_multisample_prepare_modal(
                    job_id=job.job_id, title="SM spatial-variable metabolite filtering"
                )
                _spashiny_ctx.hit_notify(
                    "SVM filtering job submitted.", type_="message", duration=8
                )
            except Exception as exc:
                _spashiny_ctx.add_sm_log(f"Worker SVM filtering submission failed: {exc}")
                _spashiny_ctx.hit_notify(
                    f"Could not submit SVM filtering: {exc}", type_="error", duration=8
                )
            return
        if data is None:
            _spashiny_ctx.add_sm_log("Merged data is not available.")
            _spashiny_ctx.hit_notify("Please complete SM merge first.", type_="warning")
            return
        _spashiny_ctx.hit_show_modal(
            "Running SVM Analysis",
            "Calculating spatially variable metabolites and removing batch-biased features...",
        )
        try:
            _spashiny_globals.preflight_memory(
                "HIT SVM analysis",
                adata=data,
                multiplier=1.8,
                min_available_gb=1.5,
                log_func=_spashiny_ctx.add_sm_log,
                notify_func=_spashiny_ctx.hit_notify,
            )
            working = _spashiny_globals.compact_adata_X(data)
            _spashiny_ctx.add_sm_log(
                "SVM analysis uses the existing AnnData object to avoid duplicating large matrices."
            )
            if "normalized" not in working.layers:
                _spashiny_globals.sc.pp.normalize_total(working, target_sum=10000.0)
                _spashiny_globals.set_compact_layer(working, "normalized")
            _spashiny_globals.set_X_from_layer(working, "normalized")
            n_top_variable = int(_spashiny_ctx.input.svm_top_genes())
            _spashiny_ctx.add_sm_log(
                f"Running spatial_variable with n_top_variable={n_top_variable}."
            )
            n_features_before_svm = int(working.n_vars)
            _spashiny_globals.smt.pp.spatial_variable(
                working,
                n_top_variable=n_top_variable,
                add_key="highly_variable_moranI",
                batch_key="sample",
                min_samples=3,
                min_frac=0.9,
                min_logfc=3,
            )
            if "highly_variable_moranI" not in working.var.columns:
                raise ValueError("The column 'highly_variable_moranI' was not created.")
            n_svm = int(
                _spashiny_globals.np.sum(working.var["highly_variable_moranI"].astype(bool))
            )
            if n_svm == 0:
                raise ValueError("No spatially variable metabolites were retained.")
            working = _spashiny_globals.compact_adata_X(
                working[:, working.var["highly_variable_moranI"].astype(bool)].copy()
            )
            if "normalized" in working.layers:
                _spashiny_globals.set_X_from_layer(working, "normalized")
            working.uns["n_features_before_svm"] = n_features_before_svm
            working.uns["n_features_after_svm"] = int(working.n_vars)
            _spashiny_ctx.merged_sm_data.set(working)
            _spashiny_ctx.integrated_sm_data.set(None)
            _spashiny_ctx.vae_model.set(None)
            _spashiny_ctx.vae_loss_dict.set(None)
            _spashiny_ctx.vae_job_dir.set(None)
            _spashiny_ctx.integrated_sm_data_path.set(None)
            _spashiny_ctx.vae_summary.set(None)
            _spashiny_ctx.vae_model_state_path.set(None)
            _spashiny_ctx.sm_merge_status.set("SVM filtering completed")
            _spashiny_ctx.add_sm_log(
                f"SVM analysis completed: retained {n_svm} spatially variable metabolites."
            )
            _spashiny_ctx.hit_notify(
                f"SVM analysis completed: retained {n_svm} features.", type_="message"
            )
        except Exception as e:
            error_msg = _spashiny_globals.user_facing_error("SVM analysis failed", e)
            _spashiny_ctx.add_sm_log(error_msg)
            _spashiny_ctx.hit_notify(
                error_msg,
                type_="error",
                duration=14 if _spashiny_globals.is_memory_related_exception(e) else 8,
            )
            _spashiny_ctx.traceback.print_exc()
        finally:
            _spashiny_ctx.hit_close_modal()

    _spashiny_ctx.run_svm_analysis = run_svm_analysis

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.run_vae_integration)
    async def run_vae_integration():
        data = _spashiny_ctx.merged_sm_data.get()
        hit_sm_example_action_id = (
            _spashiny_ctx._latest_example_action_for("sm-five-sample-batch-example")
            if _spashiny_globals.SPASHINY_LAB_PROFILE
            and _spashiny_ctx.hit_sm_input_source_mode.get() == "EXAMPLE"
            else ""
        )
        if data is None and (not hit_sm_example_action_id):
            _spashiny_ctx.add_sm_log("Merged data is not available for VAE integration.")
            _spashiny_ctx.vae_training_status.set("Failed: no data")
            _spashiny_ctx.hit_notify(
                "Please finish merge and SVM filtering first.", type_="warning"
            )
            return
        if hit_sm_example_action_id and (not _spashiny_ctx.hit_sm_merge_result_path.get()):
            _spashiny_ctx.add_sm_log(
                "Worker-managed example inputs are bound, but the persisted merge step has not completed."
            )
            _spashiny_ctx.vae_training_status.set("Waiting for Run Merge")
            _spashiny_ctx.hit_notify(
                "Click Run Merge and wait for its worker job to complete.", type_="warning"
            )
            return
        if hit_sm_example_action_id and (not _spashiny_ctx.hit_sm_svm_result_path.get()):
            _spashiny_ctx.add_sm_log(
                "The persisted merge is available, but SVM filtering has not completed."
            )
            _spashiny_ctx.vae_training_status.set("Waiting for SVM Filtering")
            _spashiny_ctx.hit_notify(
                "Run SVM Analysis and wait for its worker job to complete before ConditionalVAE integration.",
                type_="warning",
            )
            return
        _spashiny_ctx.hit_show_modal(
            "ConditionalVAE Integration", "Training ConditionalVAESM. This may take a while..."
        )
        _spashiny_ctx.is_training.set(True)
        _spashiny_ctx.vae_training_status.set("Preparing backend job")
        _spashiny_ctx.vae_model.set(None)
        _spashiny_ctx.vae_loss_dict.set(None)
        _spashiny_ctx.vae_job_dir.set(None)
        _spashiny_ctx.integrated_sm_data_path.set(None)
        _spashiny_ctx.vae_summary.set(None)
        _spashiny_ctx.vae_model_state_path.set(None)
        cloud_job_submitted = False
        try:
            if hit_sm_example_action_id:
                requested_resource = _spashiny_ctx.input.vae_compute_resource() or "auto"
                cloud_parameters = _spashiny_globals.tutorial_job_parameters(
                    "sm", "multi", input_layer="normalized", normalize_input=False
                )
                from cloud.workflow_registry import HIT_SM_MULTI_SAMPLE_INTEGRATION

                cloud_job = _spashiny_ctx._submit_prepared_multisample_training(
                    workflow_name=HIT_SM_MULTI_SAMPLE_INTEGRATION,
                    prepared_summary=_spashiny_ctx.hit_sm_svm_summary.get(),
                    parameters=cloud_parameters,
                    requested_resource=requested_resource,
                )
                _spashiny_ctx.vae_job_dir.set(cloud_job.local_workspace)
                _spashiny_ctx.vae_summary.set(
                    {
                        "cloud_job_id": cloud_job.job_id,
                        "status": "QUEUED",
                        "input_source": "example_action",
                    }
                )
                cloud_job_submitted = True
                _spashiny_ctx.vae_training_status.set(f"Cloud job submitted: {cloud_job.job_id}")
                _spashiny_ctx.add_sm_log(f"Lab example GPU job submitted: {cloud_job.job_id}")
                _spashiny_ctx.add_sm_log(f"Requested compute resource: {requested_resource}")
                _spashiny_ctx.add_sm_log("Open Job Center to monitor progress.")
                _spashiny_ctx.hit_notify(f"Cloud job created: {cloud_job.job_id}", type_="message")
                return
            from cloud.workflow_registry import HIT_SM_MULTI_SAMPLE_INTEGRATION

            parameters = _spashiny_globals.tutorial_job_parameters(
                "sm", "multi", input_layer="normalized", normalize_input=False
            )
            cloud_job = await _spashiny_ctx._submit_uploaded_multisample_training(
                workflow_name=HIT_SM_MULTI_SAMPLE_INTEGRATION,
                data=data,
                parameters=parameters,
                requested_resource=_spashiny_ctx.input.vae_compute_resource() or "auto",
                source_mode=_spashiny_ctx.hit_sm_input_source_mode.get(),
            )
            _spashiny_ctx.vae_job_dir.set(cloud_job.local_workspace)
            _spashiny_ctx.vae_summary.set(
                {
                    "cloud_job_id": cloud_job.job_id,
                    "status": cloud_job.status,
                    "input_source": "upload",
                }
            )
            cloud_job_submitted = True
            _spashiny_ctx.vae_training_status.set(f"Cloud job submitted: {cloud_job.job_id}")
            _spashiny_ctx.add_sm_log(
                f"Same-analysis processed upload submitted: {cloud_job.job_id}"
            )
        except Exception as e:
            error_msg = _spashiny_globals.user_facing_error("ConditionalVAE integration failed", e)
            _spashiny_ctx.vae_training_status.set("Training failed")
            _spashiny_ctx.add_sm_log(error_msg)
            _spashiny_ctx.hit_notify(
                error_msg,
                type_="error",
                duration=14 if _spashiny_globals.is_memory_related_exception(e) else 8,
            )
            __import__("traceback").print_exc()
        finally:
            _spashiny_ctx.is_training.set(False)
            if not cloud_job_submitted:
                _spashiny_ctx.hit_close_modal()

    _spashiny_ctx.run_vae_integration = run_vae_integration

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.run_clustering)
    def run_clustering():
        data = _spashiny_ctx.integrated_sm_data.get()
        result_path = _spashiny_ctx.integrated_sm_data_path.get()
        loaded_from_path = False
        if data is None and result_path and _spashiny_globals.os.path.exists(result_path):
            data = _spashiny_globals.sc.read_h5ad(result_path)
            loaded_from_path = True
        if data is None:
            _spashiny_ctx.add_sm_log("Integrated data is not available.")
            _spashiny_ctx.hit_notify(
                "Please run ConditionalVAE integration first.", type_="warning"
            )
            return
        if "X_emb" not in data.obsm:
            _spashiny_ctx.add_sm_log("Latent embedding 'X_emb' is missing.")
            _spashiny_ctx.hit_notify("Latent embedding 'X_emb' is missing.", type_="error")
            return
        _spashiny_ctx.hit_show_modal(
            "Clustering Analysis", "Computing neighbors, UMAP, and Leiden clusters..."
        )
        try:
            _spashiny_globals.preflight_memory(
                "HIT clustering",
                adata=data,
                multiplier=1.3,
                min_available_gb=1.2,
                log_func=_spashiny_ctx.add_sm_log,
                notify_func=_spashiny_ctx.hit_notify,
            )
            working = data
            working.obsm["X_emb"] = _spashiny_globals.np.asarray(
                working.obsm["X_emb"], dtype=_spashiny_globals.np.float32
            )
            _spashiny_globals.sc.pp.neighbors(
                working,
                use_rep="X_emb",
                n_neighbors=int(_spashiny_ctx.input.clustering_neighbors()),
            )
            _spashiny_globals.sc.tl.umap(
                working,
                min_dist=float(_spashiny_ctx.input.umap_min_dist()),
                spread=float(_spashiny_ctx.input.umap_spread()),
            )
            latent_dim = None
            summary = _spashiny_ctx.vae_summary.get()
            if isinstance(summary, dict):
                latent_dim = summary.get("resolved_config", {}).get("n_latent")
            if latent_dim is None:
                latent_dim = (
                    _spashiny_globals.tutorial_model_defaults(_spashiny_globals.smt, "sm")[
                        "n_latent"
                    ]
                    or 10
                )
            cluster_key = f"VAE_clusters_latent{int(latent_dim)}"
            _spashiny_globals.sc.tl.leiden(
                working,
                resolution=float(_spashiny_ctx.input.clustering_resolution()),
                key_added=cluster_key,
            )
            working.obs["VAE_clusters"] = working.obs[cluster_key].astype(str)
            if result_path:
                _spashiny_globals.sanitize_h5ad_keys(working)
                working.write_h5ad(result_path)
                _spashiny_ctx.integrated_sm_data.set(None)
                _spashiny_ctx.integrated_sm_data_path.set(result_path)
            else:
                _spashiny_ctx.integrated_sm_data.set(working)
            _spashiny_ctx.add_sm_log(f"Clustering completed with key '{cluster_key}'.")
            _spashiny_ctx.hit_notify("Clustering completed successfully.", type_="message")
        except Exception as e:
            error_msg = _spashiny_globals.user_facing_error("Clustering failed", e)
            _spashiny_ctx.add_sm_log(error_msg)
            _spashiny_ctx.hit_notify(
                error_msg,
                type_="error",
                duration=14 if _spashiny_globals.is_memory_related_exception(e) else 8,
            )
            _spashiny_ctx.traceback.print_exc()
        finally:
            if loaded_from_path:
                try:
                    del data
                except Exception:
                    pass
                _spashiny_globals.release_unused_memory()
            _spashiny_ctx.hit_close_modal()

    _spashiny_ctx.run_clustering = run_clustering

    @_spashiny_ctx.render.ui
    def sm_merge_status_display():
        status = _spashiny_ctx.sm_merge_status.get()
        logs = _spashiny_ctx.sm_merge_log.get()[-5:]
        return _spashiny_ctx.ui.div(
            _spashiny_ctx.ui.h5("Operation Status"),
            _spashiny_ctx.ui.p(status),
            _spashiny_ctx.ui.h5("Recent Log"),
            (
                _spashiny_ctx.ui.tags.ul(*[_spashiny_ctx.ui.tags.li(log) for log in logs])
                if logs
                else _spashiny_ctx.ui.p("No log yet.")
            ),
        )

    _spashiny_ctx.sm_merge_status_display = sm_merge_status_display

    @_spashiny_ctx.render.ui
    def sm_merge_result():
        data = _spashiny_ctx.merged_sm_data.get()
        merge_meta = _spashiny_ctx.hit_sm_merge_metadata.get() or {}
        svm_meta = _spashiny_ctx.hit_sm_svm_metadata.get() or {}
        if data is None:
            metadata = svm_meta or merge_meta
            if metadata:
                counts = metadata.get("sample_counts") or {}
                feature_note = "SVM-filtered features" if svm_meta else "Merged features"
                return _spashiny_ctx.ui.div(
                    _spashiny_ctx.ui.h4("Merge Summary"),
                    _spashiny_ctx.ui.p(f"Samples: {len(counts)}"),
                    _spashiny_ctx.ui.p(f"Total cells/spots: {int(metadata.get('n_obs', 0)):,}"),
                    _spashiny_ctx.ui.p(f"{feature_note}: {int(metadata.get('n_vars', 0)):,}"),
                )
            hit_sm_example_action_id = (
                _spashiny_ctx._latest_example_action_for("sm-five-sample-batch-example")
                if _spashiny_globals.SPASHINY_LAB_PROFILE
                and _spashiny_ctx.hit_sm_input_source_mode.get() == "EXAMPLE"
                else ""
            )
            if hit_sm_example_action_id:
                message = (
                    "Worker merge is running or waiting for the GPU worker."
                    if (_spashiny_ctx.hit_sm_merge_summary.get() or {}).get("cloud_job_id")
                    else "Five read-only example inputs are bound. Click Run Merge to submit the worker merge."
                )
                return _spashiny_ctx.ui.p(message, class_="text-muted")
            return _spashiny_ctx.ui.p("Please complete SM merge first.", class_="text-muted")
        return _spashiny_ctx.ui.div(
            _spashiny_ctx.ui.h4("Merge Summary"),
            _spashiny_ctx.ui.p(
                f"Samples: {len(data.obs['sample'].unique())}"
                if "sample" in data.obs
                else "Samples: N/A"
            ),
            _spashiny_ctx.ui.p(f"Total cells/spots: {data.n_obs:,}"),
            _spashiny_ctx.ui.p(f"Total features: {data.n_vars:,}"),
        )

    _spashiny_ctx.sm_merge_result = sm_merge_result

    @_spashiny_ctx.render.ui
    def vae_integration_status():
        merged_data = _spashiny_ctx.merged_sm_data.get()
        integrated_data = _spashiny_ctx.integrated_sm_data.get()
        result_path = _spashiny_ctx.integrated_sm_data_path.get()
        summary = _spashiny_ctx.vae_summary.get()
        cloud_progress = _spashiny_ctx._cloud_training_progress_card(
            summary, title="Multi-sample SM ConditionalVAE"
        )
        items = []
        if merged_data is not None:
            items.append(f"Merged shape: {merged_data.shape}")
            before_n = merged_data.uns.get("n_features_before_svm", None)
            after_n = merged_data.uns.get("n_features_after_svm", None)
            if before_n is not None and after_n is not None:
                items.append(f"SVM retained: {after_n}/{before_n} features")
            elif "highly_variable_moranI" in merged_data.var.columns:
                items.append(
                    f"SVM retained: {int(merged_data.var['highly_variable_moranI'].astype(bool).sum())} features"
                )
        if integrated_data is not None:
            items.append(f"Integrated shape: {integrated_data.shape}")
            if "X_emb" in integrated_data.obsm:
                items.append(f"Latent embedding: {integrated_data.obsm['X_emb'].shape}")
            if "X_umap" in integrated_data.obsm:
                items.append("UMAP: available")
            if "VAE_clusters" in integrated_data.obs:
                items.append(f"Clusters: {len(integrated_data.obs['VAE_clusters'].unique())}")
        if integrated_data is None and result_path:
            items.append(f"Backend result: {result_path}")
            if isinstance(summary, dict) and summary.get("shape"):
                items.append(f"Integrated shape: {tuple(summary.get('shape'))}")
            preview, should_close = (None, False)
            try:
                preview, should_close = _spashiny_globals.read_h5ad_for_display(result_path)
                if preview is not None:
                    if "X_emb" in preview.obsm:
                        items.append(f"Latent embedding: {preview.obsm['X_emb'].shape}")
                    if "X_umap" in preview.obsm:
                        items.append("UMAP: available")
                    cluster_key = _spashiny_globals.find_vae_cluster_key(preview)
                    if cluster_key:
                        items.append(f"Clusters: {cluster_key}")
            except Exception as exc:
                items.append(f"Result preview unavailable: {exc}")
            finally:
                _spashiny_globals.close_display_h5ad(preview, should_close)
        items.append(f"Training status: {_spashiny_ctx.vae_training_status.get()}")
        return _spashiny_ctx.ui.card(
            cloud_progress if cloud_progress is not None else _spashiny_ctx.ui.div(),
            _spashiny_ctx.ui.h5("Integration Status"),
            _spashiny_ctx.ui.tags.ul(*[_spashiny_ctx.ui.tags.li(x) for x in items]),
        )

    _spashiny_ctx.vae_integration_status = vae_integration_status

    @_spashiny_ctx.render.ui
    def hit_sm_cloud_training_progress():
        card = _spashiny_ctx._cloud_training_progress_card(
            _spashiny_ctx.vae_summary.get(), title="Multi-sample SM ConditionalVAE"
        )
        return card if card is not None else _spashiny_ctx.ui.div()

    _spashiny_ctx.hit_sm_cloud_training_progress = hit_sm_cloud_training_progress

    @_spashiny_ctx.reactive.Effect
    def _restore_hit_sm_prepare_results():
        message = ""
        for summary_value, meta_value, path_value, label, stage in (
            (
                _spashiny_ctx.hit_sm_merge_summary,
                _spashiny_ctx.hit_sm_merge_metadata,
                _spashiny_ctx.hit_sm_merge_result_path,
                "merge",
                "merge",
            ),
            (
                _spashiny_ctx.hit_sm_svm_summary,
                _spashiny_ctx.hit_sm_svm_metadata,
                _spashiny_ctx.hit_sm_svm_result_path,
                "SVM filtering",
                "qc",
            ),
        ):
            summary = summary_value.get() or {}
            if _spashiny_ctx.hit_sm_input_source_mode.get() == "USER_UPLOAD" and (
                not summary.get("cloud_job_id")
            ):
                continue
            metadata, result_path, status, _job = _spashiny_ctx._cloud_prepare_result_state(
                summary,
                workflow_name="hit_sm_multi_sample_integration",
                stage=stage,
                read_only_db=True,
            )
            if _job is not None and (
                not summary.get("cloud_job_id") or summary.get("status") != status
            ):
                summary = {"cloud_job_id": str(_job.job_id), "status": status, "stage": stage}
                summary_value.set(summary)
            if _spashiny_ctx._cloud_result_still_active(status):
                _spashiny_ctx.reactive.invalidate_later(2)
            if metadata and meta_value.get() != metadata:
                meta_value.set(metadata)
                path_value.set(result_path)
                _spashiny_ctx.add_sm_log(f"Worker {label} result restored from persistent storage.")
            elif result_path and path_value.get() != result_path:
                path_value.set(result_path)
            if _job is not None:
                progress = max(0.0, min(100.0, float(_job.progress or 0.0)))
                if status in {"SUCCEEDED", "COMPLETED"} and result_path and metadata:
                    message = f"Worker {label} completed: {_job.job_id}"
                elif _spashiny_ctx._cloud_result_still_active(status):
                    message = f"Worker {label}: {status} ({progress:.0f}%) — {_job.job_id}"
                else:
                    message = f"Worker {label}: {status} — {_job.job_id}"
            _spashiny_ctx._sync_multisample_prepare_modal(
                summary,
                title=f"SM {label}",
                workflow_name="hit_sm_multi_sample_integration",
                read_only_db=True,
            )
        if message and _spashiny_ctx.sm_merge_status.get() != message:
            _spashiny_ctx.sm_merge_status.set(message)

    _spashiny_ctx._restore_hit_sm_prepare_results = _restore_hit_sm_prepare_results

    @_spashiny_ctx.reactive.Effect
    def _restore_hit_sm_cloud_result():
        summary = _spashiny_ctx.vae_summary.get() or {}
        if _spashiny_ctx.hit_sm_input_source_mode.get() == "USER_UPLOAD" and (
            not summary.get("cloud_job_id")
        ):
            return
        result_path, status, _job = _spashiny_ctx._cloud_integration_result_state(
            summary,
            workflow_name="hit_sm_multi_sample_integration",
            stage="train",
            read_only_db=True,
        )
        if _job is not None:
            restored = dict(summary, cloud_job_id=str(_job.job_id), status=status, stage="train")
            if result_path:
                metadata, losses = _spashiny_globals.read_worker_training_metadata(result_path)
                restored.update(metadata)
                if losses and _spashiny_ctx.vae_loss_dict.get() != losses:
                    _spashiny_ctx.vae_loss_dict.set(losses)
                state_path = metadata.get("model_state_path")
                if state_path and _spashiny_ctx.vae_model_state_path.get() != state_path:
                    _spashiny_ctx.vae_model_state_path.set(state_path)
            if restored != summary:
                _spashiny_ctx.vae_summary.set(restored)
                summary = restored
        if _spashiny_ctx._cloud_result_still_active(status):
            _spashiny_ctx.reactive.invalidate_later(2)
        if result_path and _spashiny_ctx.integrated_sm_data_path.get() != result_path:
            _spashiny_ctx.integrated_sm_data_path.set(result_path)
            _spashiny_ctx.vae_training_status.set("Worker result restored from persistent storage.")
        _spashiny_ctx._sync_cloud_postprocess_modal(
            summary,
            title="Multi-sample SM ConditionalVAE post-processing",
            workflow_name="hit_sm_multi_sample_integration",
        )

    _spashiny_ctx._restore_hit_sm_cloud_result = _restore_hit_sm_cloud_result

    @_spashiny_ctx.render.ui
    def vae_model_info():
        model = _spashiny_ctx.vae_model.get()
        summary = _spashiny_ctx.vae_summary.get()
        if model is None and isinstance(summary, dict):
            cfg = summary.get("resolved_config", {})
            info_items = [
                f"Backend result: {summary.get('result_h5ad') or 'N/A'}",
                f"Latent dimension: {cfg.get('n_latent', 'N/A')}",
                f"Batch key(s): {cfg.get('batch_keys', 'sample')}",
                f"Batch embedding: {cfg.get('batch_embedding', 'N/A')}",
                f"Learning rate: {cfg.get('lr', 'N/A')}",
                f"Max epochs: {cfg.get('max_epoch', 'N/A')}",
                f"Device: {summary.get('device', 'N/A')}",
            ]
            return _spashiny_ctx.ui.tags.ul(
                *[_spashiny_ctx.ui.tags.li(item) for item in info_items]
            )
        if model is None:
            return _spashiny_ctx.ui.p("Model has not been trained yet.", class_="text-muted")
        info_items = [
            f"{key}: {getattr(model, key, 'not recorded')}"
            for key in ("n_latent", "hidden_stacks", "batch_keys", "batch_embedding", "device")
        ]
        return _spashiny_ctx.ui.tags.ul(*[_spashiny_ctx.ui.tags.li(item) for item in info_items])

    _spashiny_ctx.vae_model_info = vae_model_info

    @_spashiny_ctx.render.ui
    def vae_integration_debug_info():
        data = _spashiny_ctx.get_active_sm_data()
        if data is None:
            metadata = _spashiny_ctx.get_worker_sm_summary()
            if metadata:
                return _spashiny_ctx.ui.p(
                    f"Worker-managed {metadata.get('stage', 'prepared')} data: {int(metadata['n_obs']):,} observations × {int(metadata['n_vars']):,} features. Full matrices remain in the worker result; model metadata is shown above."
                )
            return _spashiny_ctx.ui.p("No data is currently available.", class_="text-muted")
        info_items = [
            f"Shape: {data.shape}",
            f"obs columns: {', '.join(list(data.obs.columns[:10]))}"
            + (" ..." if len(data.obs.columns) > 10 else ""),
            f"var columns: {', '.join(list(data.var.columns[:10]))}"
            + (" ..." if len(data.var.columns) > 10 else ""),
            f"obsm keys: {(', '.join(list(data.obsm.keys())) if len(data.obsm) > 0 else 'None')}",
            f"layers: {(', '.join(list(data.layers.keys())) if len(data.layers) > 0 else 'None')}",
        ]
        return _spashiny_ctx.ui.tags.ul(*[_spashiny_ctx.ui.tags.li(item) for item in info_items])

    _spashiny_ctx.vae_integration_debug_info = vae_integration_debug_info

    @_spashiny_ctx.render.text
    def sm_sample_count():
        data = _spashiny_ctx.merged_sm_data.get()
        if data is not None and "sample" in data.obs:
            return f"{len(data.obs['sample'].unique())}"
        counts = _spashiny_ctx.get_worker_sm_summary().get("sample_counts")
        if counts:
            return str(len(counts))
        samples = _spashiny_ctx.parsed_sm_sample_list()
        return f"{len(samples)}" if samples else "0"

    _spashiny_ctx.sm_sample_count = sm_sample_count

    @_spashiny_ctx.render.text
    def sm_total_cells():
        data = _spashiny_ctx.merged_sm_data.get()
        if data is not None:
            return f"{data.n_obs:,}"
        metadata = _spashiny_ctx.get_worker_sm_summary()
        if metadata:
            return f"{int(metadata['n_obs']):,}"
        sample_data = _spashiny_ctx.sm_sample_data.get()
        if not sample_data:
            return "0"
        total_cells = sum((adata_obj.n_obs for adata_obj in sample_data.values()))
        return f"{total_cells:,}"

    _spashiny_ctx.sm_total_cells = sm_total_cells

    @_spashiny_ctx.render.text
    def sm_total_features():
        data = _spashiny_ctx.merged_sm_data.get()
        if data is not None:
            return f"{data.n_vars:,}"
        metadata = _spashiny_ctx.get_worker_sm_summary()
        if metadata:
            return f"{int(metadata['n_vars']):,}"
        sample_data = _spashiny_ctx.sm_sample_data.get()
        if not sample_data:
            return "0"
        try:
            if _spashiny_ctx.input.sm_merge_method() == "intersect":
                common_features = set.intersection(
                    *[set(adata_obj.var_names) for adata_obj in sample_data.values()]
                )
                return f"{len(common_features):,}"
            else:
                union_features = set().union(
                    *[set(adata_obj.var_names) for adata_obj in sample_data.values()]
                )
                return f"{len(union_features):,}"
        except Exception:
            return "0"

    _spashiny_ctx.sm_total_features = sm_total_features

    @_spashiny_ctx.render.table
    def sm_sample_stats_table():
        sample_data = _spashiny_ctx.sm_sample_data.get()
        if not sample_data:
            saved = _spashiny_ctx.worker_sm_tables().get("sample_stats.csv")
            if saved is not None:
                return saved
            return _spashiny_ctx.pd.DataFrame(
                {
                    "Sample": ["No data"],
                    "Cells/Spots": ["0"],
                    "Features": ["0"],
                    "Status": ["Waiting"],
                }
            )
        stats = []
        for name, adata_obj in sample_data.items():
            stats.append(
                {
                    "Sample": name,
                    "Cells/Spots": f"{adata_obj.n_obs:,}",
                    "Features": f"{adata_obj.n_vars:,}",
                    "Status": "Loaded",
                }
            )
        return _spashiny_ctx.pd.DataFrame(stats)

    _spashiny_ctx.sm_sample_stats_table = sm_sample_stats_table

    @_spashiny_ctx.render.table
    def sm_merged_stats():
        data = _spashiny_ctx.merged_sm_data.get()
        if data is None or "sample" not in data.obs:
            return _spashiny_ctx.worker_sm_tables().get("merged_stats.csv")
        sample_counts = data.obs["sample"].value_counts()
        stats = []
        for sample, count in sample_counts.items():
            stats.append(
                {
                    "Sample": sample,
                    "Cells/Spots": f"{count:,}",
                    "Percent": f"{count / data.n_obs * 100:.1f}%",
                }
            )
        return _spashiny_ctx.pd.DataFrame(stats)

    _spashiny_ctx.sm_merged_stats = sm_merged_stats

    @_spashiny_ctx.render.table
    def svm_results_table():
        data = _spashiny_ctx.merged_sm_data.get()
        if data is None:
            saved = _spashiny_ctx.worker_sm_tables().get("svm_results.csv")
            if saved is not None:
                return saved
            return _spashiny_ctx.pd.DataFrame({"Status": ["Please run SVM analysis first."]})
        before_n = int(data.uns.get("n_features_before_svm", data.n_vars))
        after_n = int(data.uns.get("n_features_after_svm", data.n_vars))
        return _spashiny_ctx.pd.DataFrame(
            {
                "Metric": [
                    "Spatially variable metabolites",
                    "Features before SVM",
                    "Retained ratio",
                ],
                "Value": [
                    f"{after_n:,}",
                    f"{before_n:,}",
                    f"{after_n / max(before_n, 1) * 100:.1f}%",
                ],
            }
        )

    _spashiny_ctx.svm_results_table = svm_results_table

    @_spashiny_ctx.render.download(filename=lambda: "hit_sm_tables_csv.zip")
    def download_hit_tables_zip():
        import io

        files = _spashiny_ctx.worker_sm_tables()
        sample_data = _spashiny_ctx.sm_sample_data.get()
        if sample_data:
            files["sample_stats.csv"] = _spashiny_ctx.pd.DataFrame(
                [
                    {
                        "Sample": name,
                        "Cells/Spots": adata_obj.n_obs,
                        "Features": adata_obj.n_vars,
                        "Status": "Loaded",
                    }
                    for name, adata_obj in sample_data.items()
                ]
            )
        data = _spashiny_ctx.merged_sm_data.get()
        if data is not None and "sample" in data.obs:
            sample_counts = data.obs["sample"].value_counts()
            files["merged_stats.csv"] = _spashiny_ctx.pd.DataFrame(
                [
                    {
                        "Sample": sample,
                        "Cells/Spots": int(count),
                        "Percent": f"{count / data.n_obs * 100:.1f}%",
                    }
                    for sample, count in sample_counts.items()
                ]
            )
            before_n = int(data.uns.get("n_features_before_svm", data.n_vars))
            after_n = int(data.uns.get("n_features_after_svm", data.n_vars))
            files["svm_results.csv"] = _spashiny_ctx.pd.DataFrame(
                {
                    "Metric": [
                        "Spatially variable metabolites",
                        "Features before SVM",
                        "Retained ratio",
                    ],
                    "Value": [after_n, before_n, f"{after_n / max(before_n, 1) * 100:.1f}%"],
                }
            )
        if not files:
            files["README.csv"] = _spashiny_ctx.pd.DataFrame(
                {"Message": ["No HIT_SM table data is available yet."]}
            )
        buf = io.BytesIO()
        with _spashiny_ctx.zipfile.ZipFile(buf, "w", _spashiny_ctx.zipfile.ZIP_DEFLATED) as zf:
            for name, df in files.items():
                zf.writestr(name, df.to_csv(index=False))
        buf.seek(0)
        yield buf.read()

    _spashiny_ctx.download_hit_tables_zip = download_hit_tables_zip

    @_spashiny_ctx.render.download(filename=lambda: "merged_sm_tutorial.h5ad")
    def download_hit_merged_data():
        data = _spashiny_ctx.merged_sm_data.get()
        if data is None:
            path = (
                _spashiny_ctx.hit_sm_svm_result_path.get()
                or _spashiny_ctx.hit_sm_merge_result_path.get()
            )
            if path:
                yield from _spashiny_ctx.stream_file(path)
                return
            _spashiny_ctx.hit_notify(
                "No merged SM data is available for download.", type_="warning"
            )
            return
        tmp = _spashiny_ctx.tempfile.NamedTemporaryFile(suffix=".h5ad", delete=False)
        tmp.close()
        try:
            data.write_h5ad(tmp.name)
            with open(tmp.name, "rb") as f:
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    yield chunk
        finally:
            if _spashiny_globals.os.path.exists(tmp.name):
                _spashiny_globals.os.remove(tmp.name)

    _spashiny_ctx.download_hit_merged_data = download_hit_merged_data

    @_spashiny_ctx.render.download(filename=lambda: "integrated_sm_after_vae.h5ad")
    def download_integrated_sm():
        result_path = _spashiny_ctx.integrated_sm_data_path.get()
        if result_path and _spashiny_globals.os.path.exists(result_path):
            yield from _spashiny_ctx.stream_file(result_path)
            return
        data = _spashiny_ctx.integrated_sm_data.get()
        if data is None:
            _spashiny_ctx.hit_notify(
                "No integrated SM data is available. Run ConditionalVAE first.", type_="warning"
            )
            return
        tmp = _spashiny_ctx.tempfile.NamedTemporaryFile(suffix=".h5ad", delete=False)
        tmp.close()
        try:
            data.write_h5ad(tmp.name)
            with open(tmp.name, "rb") as f:
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    yield chunk
        finally:
            if _spashiny_globals.os.path.exists(tmp.name):
                _spashiny_globals.os.remove(tmp.name)

    _spashiny_ctx.download_integrated_sm = download_integrated_sm

    @_spashiny_ctx.render.download(filename=lambda: "conditionalvae_sm_model_bundle.zip")
    def download_vae_model():
        model = _spashiny_ctx.vae_model.get()
        data = _spashiny_ctx.integrated_sm_data.get()
        state_path = _spashiny_ctx.vae_model_state_path.get()
        if model is None and (not (state_path and _spashiny_globals.os.path.exists(state_path))):
            _spashiny_ctx.hit_notify("No trained model is available for download.", type_="warning")
            return
        tmp_dir = _spashiny_ctx.tempfile.mkdtemp(prefix="conditionalvae_sm_")
        zip_path = _spashiny_globals.os.path.join(tmp_dir, "conditionalvae_sm_model_bundle.zip")
        try:
            meta = dict((_spashiny_ctx.vae_summary.get() or {}).get("resolved_config") or {})
            if not meta and model is not None:
                meta = {
                    key: getattr(model, key, None)
                    for key in ("n_latent", "hidden_stacks", "batch_keys", "batch_embedding")
                }
            if not meta:
                raise RuntimeError(
                    "This model has no recorded configuration; refusing to label it with new defaults."
                )
            with open(
                _spashiny_globals.os.path.join(tmp_dir, "metadata.json"), "w", encoding="utf-8"
            ) as f:
                _spashiny_ctx.json.dump(meta, f, indent=2, ensure_ascii=False)
            with open(
                _spashiny_globals.os.path.join(tmp_dir, "training_loss.json"), "w", encoding="utf-8"
            ) as f:
                _spashiny_ctx.json.dump(
                    _spashiny_ctx.serializable_loss_dict(_spashiny_ctx.vae_loss_dict.get()),
                    f,
                    indent=2,
                    ensure_ascii=False,
                )
            summary = _spashiny_ctx.vae_summary.get()
            if summary:
                with open(
                    _spashiny_globals.os.path.join(tmp_dir, "backend_summary.json"),
                    "w",
                    encoding="utf-8",
                ) as f:
                    _spashiny_ctx.json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
            saved = False
            if state_path and _spashiny_globals.os.path.exists(state_path):
                try:
                    _spashiny_ctx.shutil.copy2(
                        state_path, _spashiny_globals.os.path.join(tmp_dir, "model_state_dict.pt")
                    )
                    saved = True
                except Exception:
                    saved = False
            if not saved and model is not None and hasattr(model, "state_dict"):
                try:
                    _spashiny_globals.torch.save(
                        model.state_dict(),
                        _spashiny_globals.os.path.join(tmp_dir, "model_state_dict.pt"),
                    )
                    saved = True
                except Exception:
                    saved = False
            if (
                not saved
                and model is not None
                and hasattr(model, "model")
                and hasattr(model.model, "state_dict")
            ):
                try:
                    _spashiny_globals.torch.save(
                        model.model.state_dict(),
                        _spashiny_globals.os.path.join(tmp_dir, "model_state_dict.pt"),
                    )
                    saved = True
                except Exception:
                    saved = False
            if not saved and model is not None:
                with open(_spashiny_globals.os.path.join(tmp_dir, "model.pkl"), "wb") as f:
                    _spashiny_ctx.pickle.dump(model, f)
            if data is not None:
                with open(
                    _spashiny_globals.os.path.join(tmp_dir, "integrated_data_summary.json"),
                    "w",
                    encoding="utf-8",
                ) as f:
                    _spashiny_ctx.json.dump(
                        {
                            "shape": list(data.shape),
                            "obs_columns": list(data.obs.columns),
                            "var_columns": list(data.var.columns),
                            "obsm_keys": list(data.obsm.keys()),
                            "layers": list(data.layers.keys()),
                        },
                        f,
                        indent=2,
                        ensure_ascii=False,
                    )
            with _spashiny_ctx.zipfile.ZipFile(
                zip_path, "w", _spashiny_ctx.zipfile.ZIP_DEFLATED
            ) as zf:
                for name in _spashiny_globals.os.listdir(tmp_dir):
                    if name.endswith(".zip"):
                        continue
                    zf.write(_spashiny_globals.os.path.join(tmp_dir, name), arcname=name)
            with open(zip_path, "rb") as f:
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    yield chunk
        finally:
            _spashiny_ctx.shutil.rmtree(tmp_dir, ignore_errors=True)

    _spashiny_ctx.download_vae_model = download_vae_model

    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("sm_sample_size_plot")
    def sm_sample_size_plot():
        return _spashiny_ctx.build_sm_sample_size_figure()

    _spashiny_ctx.sm_sample_size_plot = sm_sample_size_plot

    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("sm_feature_distribution_plot")
    def sm_feature_distribution_plot():
        return _spashiny_ctx.build_sm_feature_distribution_figure()

    _spashiny_ctx.sm_feature_distribution_plot = sm_feature_distribution_plot

    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("svm_plot")
    def svm_plot():
        return _spashiny_ctx.build_svm_figure()

    _spashiny_ctx.svm_plot = svm_plot

    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("sm_debatch_umap")
    def sm_debatch_umap():
        return _spashiny_ctx.build_sm_debatch_umap_figure()

    _spashiny_ctx.sm_debatch_umap = sm_debatch_umap

    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("sm_batch_effect_evaluation")
    def sm_batch_effect_evaluation():
        return _spashiny_ctx.build_sm_batch_effect_evaluation_figure()

    _spashiny_ctx.sm_batch_effect_evaluation = sm_batch_effect_evaluation

    @_spashiny_ctx.render.plot
    @_spashiny_ctx.plot_colorized("vae_training_loss_plot")
    def vae_training_loss_plot():
        return _spashiny_ctx.build_vae_training_loss_figure()

    _spashiny_ctx.vae_training_loss_plot = vae_training_loss_plot

    @_spashiny_ctx.render.ui
    def data_structure_info():
        data = _spashiny_ctx.get_active_sm_data()
        if data is None:
            metadata = _spashiny_ctx.get_worker_sm_summary()
            if metadata:
                return _spashiny_ctx.ui.tags.ul(
                    _spashiny_ctx.ui.tags.li(
                        f"Shape: ({int(metadata['n_obs'])}, {int(metadata['n_vars'])})"
                    ),
                    _spashiny_ctx.ui.tags.li(f"Worker stage: {metadata.get('stage', 'prepared')}"),
                    _spashiny_ctx.ui.tags.li(
                        "Matrix is stored in the current analysis' persistent H5AD; it is not loaded into Web memory."
                    ),
                )
            return _spashiny_ctx.ui.p("No data available.")
        info_items = [
            f"Shape: {data.shape}",
            f"Observations: {data.n_obs}",
            f"Variables: {data.n_vars}",
        ]
        if hasattr(data, "obs") and len(data.obs.columns) > 0:
            obs_cols = ", ".join(list(data.obs.columns[:8]))
            if len(data.obs.columns) > 8:
                obs_cols += " ..."
            info_items.append(f"obs columns: {obs_cols}")
        if hasattr(data, "var") and len(data.var.columns) > 0:
            var_cols = ", ".join(list(data.var.columns[:8]))
            if len(data.var.columns) > 8:
                var_cols += " ..."
            info_items.append(f"var columns: {var_cols}")
        if hasattr(data, "obsm") and len(data.obsm) > 0:
            info_items.append(f"obsm keys: {', '.join(data.obsm.keys())}")
        if hasattr(data, "layers") and len(data.layers) > 0:
            info_items.append(f"layers: {', '.join(data.layers.keys())}")
        return _spashiny_ctx.ui.tags.ul(*[_spashiny_ctx.ui.tags.li(item) for item in info_items])

    _spashiny_ctx.data_structure_info = data_structure_info

    @_spashiny_ctx.render.download(filename=lambda: "sm_sample_size_distribution.png")
    def download_sm_sample_size_plot():
        fig = _spashiny_ctx.build_sm_sample_size_figure()
        path = _spashiny_ctx.save_fig_to_temp_png(fig, prefix="sm_sample_size")
        try:
            yield from _spashiny_ctx.stream_file(path)
        finally:
            _spashiny_globals.plt.close(fig)
            if _spashiny_globals.os.path.exists(path):
                _spashiny_globals.os.remove(path)

    _spashiny_ctx.download_sm_sample_size_plot = download_sm_sample_size_plot

    @_spashiny_ctx.render.download(filename=lambda: "sm_feature_intensity_distribution.png")
    def download_sm_feature_distribution_plot():
        fig = _spashiny_ctx.build_sm_feature_distribution_figure()
        path = _spashiny_ctx.save_fig_to_temp_png(fig, prefix="sm_feature_distribution")
        try:
            yield from _spashiny_ctx.stream_file(path)
        finally:
            _spashiny_globals.plt.close(fig)
            if _spashiny_globals.os.path.exists(path):
                _spashiny_globals.os.remove(path)

    _spashiny_ctx.download_sm_feature_distribution_plot = download_sm_feature_distribution_plot

    @_spashiny_ctx.render.download(filename=lambda: "svm_visualization.png")
    def download_svm_plot():
        fig = _spashiny_ctx.build_svm_figure()
        path = _spashiny_ctx.save_fig_to_temp_png(fig, prefix="svm_plot")
        try:
            yield from _spashiny_ctx.stream_file(path)
        finally:
            _spashiny_globals.plt.close(fig)
            if _spashiny_globals.os.path.exists(path):
                _spashiny_globals.os.remove(path)

    _spashiny_ctx.download_svm_plot = download_svm_plot

    @_spashiny_ctx.render.download(filename=lambda: "sm_debatched_umap.png")
    def download_sm_debatch_umap_plot():
        fig = _spashiny_ctx.build_sm_debatch_umap_figure()
        path = _spashiny_ctx.save_fig_to_temp_png(fig, prefix="sm_debatch_umap")
        try:
            yield from _spashiny_ctx.stream_file(path)
        finally:
            _spashiny_globals.plt.close(fig)
            if _spashiny_globals.os.path.exists(path):
                _spashiny_globals.os.remove(path)

    _spashiny_ctx.download_sm_debatch_umap_plot = download_sm_debatch_umap_plot

    def _stream_sm_umap_pdf(builder):
        """Export the live native UMAP Figure; do not retrain or wrap a PNG."""
        import io

        fig = builder()
        try:
            has_points = any(
                (
                    hasattr(artist, "get_offsets") and len(artist.get_offsets()) > 0
                    for ax in fig.axes
                    for artist in ax.collections
                )
            )
            if not has_points:
                raise ValueError("Complete SM integration before downloading its UMAP PDF.")
            buffer = io.BytesIO()
            _spashiny_globals.save_native_figure(
                fig, buffer, format="pdf", bbox_inches="tight", facecolor="white"
            )
            payload = buffer.getvalue()
            if not payload.startswith(b"%PDF-"):
                raise RuntimeError("The editable UMAP PDF could not be generated.")
            yield payload
        finally:
            _spashiny_globals.plt.close(fig)

    _spashiny_ctx._stream_sm_umap_pdf = _stream_sm_umap_pdf

    @_spashiny_ctx.render.download(filename="sm_debatched_umap.pdf", media_type="application/pdf")
    def download_sm_debatch_umap_pdf():
        yield from _spashiny_ctx._stream_sm_umap_pdf(_spashiny_ctx.build_sm_debatch_umap_figure)

    _spashiny_ctx.download_sm_debatch_umap_pdf = download_sm_debatch_umap_pdf

    @_spashiny_ctx.render.download(
        filename="sm_batch_effect_evaluation.pdf", media_type="application/pdf"
    )
    def download_sm_batch_effect_evaluation_pdf():
        yield from _spashiny_ctx._stream_sm_umap_pdf(
            _spashiny_ctx.build_sm_batch_effect_evaluation_figure
        )

    _spashiny_ctx.download_sm_batch_effect_evaluation_pdf = download_sm_batch_effect_evaluation_pdf

    @_spashiny_ctx.render.download(filename=lambda: "sm_batch_effect_evaluation.png")
    def download_sm_batch_effect_evaluation_plot():
        fig = _spashiny_ctx.build_sm_batch_effect_evaluation_figure()
        path = _spashiny_ctx.save_fig_to_temp_png(fig, prefix="sm_batch_effect")
        try:
            yield from _spashiny_ctx.stream_file(path)
        finally:
            _spashiny_globals.plt.close(fig)
            if _spashiny_globals.os.path.exists(path):
                _spashiny_globals.os.remove(path)

    _spashiny_ctx.download_sm_batch_effect_evaluation_plot = (
        download_sm_batch_effect_evaluation_plot
    )

    @_spashiny_ctx.render.download(filename=lambda: "vae_training_loss_curve.png")
    def download_vae_training_loss_plot():
        fig = _spashiny_ctx.build_vae_training_loss_figure()
        path = _spashiny_ctx.save_fig_to_temp_png(fig, prefix="vae_training_loss")
        try:
            yield from _spashiny_ctx.stream_file(path)
        finally:
            _spashiny_globals.plt.close(fig)
            if _spashiny_globals.os.path.exists(path):
                _spashiny_globals.os.remove(path)

    _spashiny_ctx.download_vae_training_loss_plot = download_vae_training_loss_plot
    from shiny import App, render, reactive, ui

    _spashiny_ctx.App = App
    _spashiny_ctx.render = render
    _spashiny_ctx.reactive = reactive
    _spashiny_ctx.ui = ui
    import scanpy as sc

    _spashiny_globals.sc = sc
    import pandas as pd

    _spashiny_ctx.pd = pd
    import matplotlib.pyplot as plt

    _spashiny_globals.plt = plt
    import traceback

    _spashiny_ctx.traceback = traceback
    import spatialmeta as smt

    _spashiny_globals.smt = smt
    _spashiny_ctx.adata_obj = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.marker_res = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.merged_sm_data = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.log_msg = _spashiny_ctx.reactive.Value("")
    _spashiny_ctx.downstream_input_reference = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.downstream_action_clicks = _spashiny_ctx.reactive.Value({})

    def _downstream_click_guard(action_id, label, window_seconds=10):
        import time as _time

        action_id = str(action_id or "").strip()
        label = str(label or action_id or "this action").strip()
        if not action_id:
            return True
        now = _time.monotonic()
        state = dict(_spashiny_ctx.downstream_action_clicks.get() or {})
        last = float(state.get(action_id) or 0.0)
        if last and now - last < int(window_seconds):
            remaining = max(1, int(int(window_seconds) - (now - last) + 0.999))
            _spashiny_ctx.ui.notification_show(
                f"Clicked too quickly. Please wait {remaining} seconds before clicking {label} again.",
                type="warning",
                duration=5,
            )
            return False
        state[action_id] = now
        _spashiny_ctx.downstream_action_clicks.set(state)
        return True

    _spashiny_ctx._downstream_click_guard = _downstream_click_guard


_STEPS = (_install_0,)


def server(_spashiny_ctx, step=0):
    return _STEPS[step](_spashiny_ctx)
