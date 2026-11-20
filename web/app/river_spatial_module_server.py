import json
import gc
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
import functools
from pathlib import Path

import numpy as np
import pandas as pd
import scanpy as sc
#import squidpy as sq
import matplotlib
matplotlib.rcParams["pdf.fonttype"] = 42
matplotlib.rcParams["ps.fonttype"] = 42
matplotlib.rcParams["svg.fonttype"] = "none"
import matplotlib.pyplot as plt

from cloud.figure_export import EditablePdfPages as PdfPages
from matplotlib.colors import ListedColormap, LinearSegmentedColormap
from shiny import reactive, render, ui

from plot_color_tools import (
    COLOR_PRESETS,
    FIXED_COLORS,
    apply_color_settings_to_figure,
    clone_figure,
    extract_color_spec_from_figure,
    expand_color_list,
    figure_looks_empty,
    normalize_color,
    preset_colormap,
    preset_colors_for_count,
    settings_from_color_spec,
)
from ssh_module import (
    REQUIRED_RIVER_PACKAGES,
    ssh_check_python_packages,
    ssh_connection_ready,
    ssh_download_file,
    ssh_exec_command,
    ssh_mkdir_p,
    ssh_open_client,
    ssh_prepare_job_dir,
    ssh_quote,
    ssh_upload_directory,
    ssh_upload_file,
)

try:
    from memory_tools import current_process_memory
except Exception:
    current_process_memory = None

try:
    from palettable.cmocean.diverging import Balance_20, Delta_20
except Exception:
    Balance_20 = None
    Delta_20 = None


def safe_console_print(*args, sep=" ", end="\n", flush=False):
    text = sep.join(str(arg) for arg in args) + end
    stream = sys.stdout
    try:
        stream.write(text)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "utf-8"
        safe_text = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
        stream.write(safe_text)
    if flush:
        stream.flush()


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def river_module_server(input, output, session, ssh_state=None):
    river_log_text = reactive.Value("")
    river_status_text = reactive.Value("Waiting for .h5ad / .h5 files and CSV annotations...")
    river_preview_text = reactive.Value("No files previewed yet.")

    river_output_dir = reactive.Value(None)
    river_plot_png = reactive.Value(None)
    river_plot_pdf = reactive.Value(None)
    river_rank_npy = reactive.Value(None)
    river_rank_csv = reactive.Value(None)
    river_summary_json = reactive.Value(None)
    river_workspace = reactive.Value(None)
    river_prepared_cfg = reactive.Value(None)

    river_plot_adata_path = reactive.Value(None)
    river_plot_adata = reactive.Value(None)  # lightweight metadata, not a full AnnData object
    river_rank_features = reactive.Value([])
    river_selected_feature = reactive.Value(None)
    river_color_settings = reactive.Value({})
    river_color_revision = reactive.Value(0)
    river_generated_color_plots = set()
    river_color_specs = {}

    def _river_color_picker_tag(picker_id, text_id, value):
        ns_picker = session.ns(picker_id)
        ns_text = session.ns(text_id)
        value = normalize_color(value, "#157B9B")
        return ui.tags.input(
            id=ns_picker,
            type="color",
            value=value,
            style="width:100%; height:38px; padding:2px; border:1px solid #d0d7de; border-radius:8px;",
            oninput=(
                f"const target=document.getElementById('{ns_text}');"
                "if(target){target.value=this.value;target.dispatchEvent(new Event('input',{bubbles:true}));"
                "target.dispatchEvent(new Event('change',{bubbles:true}));}"
                f"if(window.Shiny){{Shiny.setInputValue('{ns_text}', this.value, {{priority:'event'}});}}"
            ),
        )

    def _river_palette_row(prefix, index, label, current):
        text_id = f"{prefix}_{index}"
        fixed_id = f"{text_id}_fixed"
        return ui.div(
            ui.input_text(session.ns(text_id), label, value=normalize_color(current, "#157B9B")),
            _river_color_picker_tag(f"{text_id}_picker", text_id, current),
            ui.input_select(session.ns(fixed_id), "Fixed colors", choices=FIXED_COLORS, selected=""),
            style="display:grid; grid-template-columns: minmax(150px,1fr) 74px minmax(150px,1fr); gap:10px; align-items:end; margin-bottom:10px;",
        )

    def _river_current_modal_colors(spec):
        settings = (river_color_settings.get() or {}).get("river_feature_plot") or {}
        base_colors = [item.get("color") for item in spec.get("colors", [])]
        colors = settings.get("colors") if settings else None
        current_colors = expand_color_list(colors or base_colors, len(base_colors), base_colors)
        current_cmap = settings.get("colormap") or spec.get("colormap") or []
        current_cmap = expand_color_list(current_cmap, len(current_cmap), current_cmap) if current_cmap else []
        return current_colors, current_cmap

    def _show_river_color_modal():
        if "river_feature_plot" not in river_generated_color_plots:
            ui.modal_show(
                ui.modal(
                    ui.h4("Adjust Colors"),
                    ui.p("Please generate the plot first."),
                    footer=ui.modal_button("Close"),
                    easy_close=True,
                )
            )
            return

        spec = river_color_specs.get("river_feature_plot") or {"colors": [], "colormap": None}
        current_colors, current_cmap = _river_current_modal_colors(spec)
        preset_choices = {
            "custom": "Manual colors",
            "original": "Original plot colors",
        }
        preset_choices.update({name: preset["label"] for name, preset in COLOR_PRESETS.items()})
        color_rows = [
            _river_palette_row("river_color_item", idx, f"{idx + 1}. {item.get('label') or 'Color'}", current_colors[idx])
            for idx, item in enumerate(spec.get("colors", []))
        ]
        cmap_labels = ["Colormap low", "Colormap middle", "Colormap high"]
        cmap_rows = [
            _river_palette_row("river_cmap_item", idx, cmap_labels[idx] if idx < len(cmap_labels) else f"Colormap {idx + 1}", color)
            for idx, color in enumerate(current_cmap)
        ]
        body_rows = []
        if color_rows:
            body_rows.extend([ui.h5("Discrete / category colors"), *color_rows])
        if cmap_rows:
            body_rows.extend([ui.hr(), ui.h5("Continuous colormap"), *cmap_rows])
        if not body_rows:
            body_rows.append(ui.p("No adjustable colors were detected for this plot."))
        ui.modal_show(
            ui.modal(
                ui.h4("Adjust Colors - River Feature Plot"),
                ui.input_select(session.ns("river_color_preset"), "Preset palette", choices=preset_choices, selected="custom"),
                ui.div(
                    *body_rows,
                    style="max-height:58vh; overflow-y:auto; padding-right:8px;",
                ),
                footer=ui.div(
                    ui.input_action_button(session.ns("apply_river_plot_color_palette"), "Apply Colors", class_="btn btn-primary"),
                    ui.input_action_button(session.ns("reset_river_plot_color_palette"), "Reset Default", class_="btn btn-outline-secondary"),
                    ui.modal_button("Close"),
                    style="display:flex; gap:10px; justify-content:flex-end;",
                ),
                size="l",
                easy_close=True,
            )
        )

    def _read_river_modal_color(prefix, index, fallback):
        try:
            fixed = getattr(input, f"{prefix}_{index}_fixed")()
        except Exception:
            fixed = ""
        try:
            text = getattr(input, f"{prefix}_{index}")()
        except Exception:
            text = ""
        return normalize_color(fixed or text, fallback)

    def _river_modal_settings_from_inputs():
        spec = river_color_specs.get("river_feature_plot") or {"colors": [], "colormap": None}
        base_colors = [item.get("color") for item in spec.get("colors", [])]
        base_cmap = spec.get("colormap") or []
        preset = input.river_color_preset() or "custom"
        if preset == "original":
            colors = base_colors
            cmap = base_cmap
        elif preset in COLOR_PRESETS:
            colors = preset_colors_for_count(preset, len(base_colors))
            cmap = preset_colormap(preset) if base_cmap else []
        else:
            colors = [
                _read_river_modal_color("river_color_item", idx, fallback)
                for idx, fallback in enumerate(base_colors)
            ]
            cmap = [
                _read_river_modal_color("river_cmap_item", idx, fallback)
                for idx, fallback in enumerate(base_cmap)
            ]
        return settings_from_color_spec(spec, colors=colors, colormap=cmap)

    def river_colorize_plot(plot_id, fig):
        river_color_revision.get()
        settings_map = river_color_settings.get() or {}
        if fig is not None and not figure_looks_empty(fig):
            river_generated_color_plots.add(plot_id)
            river_color_specs[plot_id] = extract_color_spec_from_figure(fig)
        settings = settings_map.get(plot_id)
        if not settings:
            return fig
        return apply_color_settings_to_figure(clone_figure(fig), settings, river_color_specs.get(plot_id))

    def river_plot_colorized(plot_id):
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                return river_colorize_plot(plot_id, func(*args, **kwargs))
            return wrapper
        return decorator

    # =========================================================
    # Logging
    # =========================================================
    def river_log(msg: str):
        now = time.strftime("[%H:%M:%S] ")
        new = river_log_text.get() + now + str(msg) + "\n"
        river_log_text.set(new)
        safe_console_print(now + str(msg), flush=True)

    def format_exception(e: Exception) -> str:
        err_name = type(e).__name__
        err_msg = str(e).strip()
        if err_msg:
            return f"{err_name}: {err_msg}"
        return repr(e)

    # =========================================================
    # Workspace
    # =========================================================
    def get_workspace() -> Path:
        ws = river_workspace.get()
        if ws is None:
            ws = Path(tempfile.mkdtemp(prefix="river_upload_workspace_"))
            river_workspace.set(ws)
        return ws

    def create_job_output_dir(prefix="river") -> Path:
        root = Path(__file__).resolve().parents[1] / "user_data" / "output"
        root.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        out_dir = root / f"job_{prefix}_{stamp}_{uuid.uuid4().hex[:8]}"
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir

    def reset_dir(path: Path) -> Path:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @session.on_ended
    def _cleanup_workspace():
        with reactive.isolate():
            ws = river_workspace.get()
            out_dir = river_output_dir.get()

        if ws and Path(ws).exists():
            shutil.rmtree(ws, ignore_errors=True)

        # Keep completed job outputs under user_data/output/job_xxx for reuse,
        # downloads, and post-run inspection.

    # =========================================================
    # File helpers
    # =========================================================
    def normalize_sample_key(name: str) -> str:
        stem = Path(name).stem.strip()

        suffix_patterns = [
            r"_adata_st_raw$",
            r"_adata_sm_raw$",
            r"_adata_raw$",
            r"_adata$",
            r"_raw$",
            r"_processed$",
            r"_region$",
            r"_regions$",
            r"_annotation$",
            r"_annotations$",
            r"_anno$",
            r"_csv$",
        ]
        for pat in suffix_patterns:
            stem = re.sub(pat, "", stem, flags=re.IGNORECASE)

        stem = re.sub(r"\s+", "_", stem)
        return stem

    def copy_uploaded_files(
        fileinfo,
        target_dir: Path,
        label: str,
        allowed_suffixes=(".h5ad",),
        required: bool = True,
    ) -> list[str]:
        if not fileinfo:
            if required:
                raise RuntimeError(f"Please upload {label}.")
            return []

        reset_dir(target_dir)
        saved_paths = []

        for f in fileinfo:
            src = Path(f["datapath"])
            original_name = Path(f["name"]).name
            suffix = Path(original_name).suffix.lower()

            if suffix not in allowed_suffixes:
                raise RuntimeError(
                    f"{label} only supports: {', '.join(allowed_suffixes)} ; got {original_name}"
                )

            dst = target_dir / original_name
            if dst.exists():
                base = dst.stem
                ext = dst.suffix
                i = 1
                while True:
                    candidate = target_dir / f"{base}__{i}{ext}"
                    if not candidate.exists():
                        dst = candidate
                        break
                    i += 1

            shutil.copy2(src, dst)
            saved_paths.append(str(dst.resolve()))

        return saved_paths

    def build_sample_records(
        data_paths: list[str],
        csv_paths: list[str],
        sample_names_text: str,
    ) -> tuple[list[dict], str]:
        data_map = {normalize_sample_key(Path(p).name): p for p in data_paths}
        csv_map = {normalize_sample_key(Path(p).name): p for p in csv_paths}

        ordered_keys = list(data_map.keys())
        user_conditions = [x.strip() for x in (sample_names_text or "").split(",") if x.strip()]

        samples = []
        preview_lines = []
        preview_lines.append(f"Total .h5ad/.h5 files: {len(data_paths)}")
        preview_lines.append(f"Total CSV files: {len(csv_paths)}")
        preview_lines.append("=" * 60)

        for i, key in enumerate(ordered_keys):
            condition = user_conditions[i] if i < len(user_conditions) else key
            data_path = data_map[key]
            csv_path = csv_map.get(key)

            samples.append(
                {
                    "sample_id": key,
                    "condition": condition,
                    "h5ad_path": data_path,
                    "csv_path": csv_path,
                }
            )

            preview_lines.append(f"[Sample {i + 1}]")
            preview_lines.append(f"sample_id : {key}")
            preview_lines.append(f"condition : {condition}")
            preview_lines.append(f"data file : {Path(data_path).name}")
            preview_lines.append(f"csv       : {Path(csv_path).name if csv_path else 'None'}")
            preview_lines.append("")

        extra_csv_keys = sorted(set(csv_map.keys()) - set(data_map.keys()))
        if extra_csv_keys:
            preview_lines.append("[CSV files without matched .h5ad/.h5]")
            for k in extra_csv_keys:
                preview_lines.append(f"{k} -> {Path(csv_map[k]).name}")
            preview_lines.append("")

        if user_conditions and len(user_conditions) != len(ordered_keys):
            preview_lines.append(
                f"[WARN] Number of provided sample_names ({len(user_conditions)}) "
                f"does not match number of uploaded files ({len(ordered_keys)}). "
                "Unmatched conditions were ignored or auto-filled by sample_id."
            )

        if not samples:
            preview_lines.append("[WARN] No valid .h5ad / .h5 samples detected.")

        return samples, "\n".join(preview_lines)

    def prepare_uploads() -> tuple[dict, str]:
        ws = get_workspace()
        upload_root = reset_dir(ws / "uploaded_files")

        data_paths = copy_uploaded_files(
            input.river_h5ad_files(),
            upload_root / "h5ad_files",
            "River .h5ad / .h5 files",
            allowed_suffixes=(".h5ad", ".h5"),
            required=True,
        )

        csv_paths = copy_uploaded_files(
            input.river_csv_files(),
            upload_root / "csv_annotations",
            "River annotation CSV files",
            allowed_suffixes=(".csv",),
            required=False,
        )

        samples, preview = build_sample_records(
            data_paths=data_paths,
            csv_paths=csv_paths,
            sample_names_text=input.river_sample_names() or "",
        )

        cfg = {
            "mode": input.river_mode(),
            "river_epochs": int(input.river_epochs() or 100),
            "subsample_size": int(input.river_subsample() or 6000),
            "samples": samples,
            "h5ad_files": data_paths,
            "csv_files": csv_paths,
        }

        river_prepared_cfg.set(cfg)
        return cfg, preview

    def resolve_artifact_path(p, base_dir: Path):
        if not p:
            return None
        pp = Path(p)
        if not pp.is_absolute():
            pp = base_dir / pp
        return str(pp.resolve())

    def remote_enabled() -> bool:
        return bool(ssh_state is not None and ssh_connection_ready(ssh_state.get()))

    def remote_safe_name(path, fallback="file"):
        name = Path(path).name if path else fallback
        name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
        return name or fallback

    def build_remote_cfg_and_uploads(client, cfg, remote_input_dir):
        import copy

        remote_cfg = copy.deepcopy(cfg)
        data_paths = {}
        csv_paths = {}

        samples = remote_cfg.get("samples", [])
        for idx, sample in enumerate(samples):
            local_data = sample.get("h5ad_path") or sample.get("h5_path") or sample.get("data_path")
            if local_data:
                remote_name = f"sample_{idx + 1}_{remote_safe_name(local_data)}"
                remote_path = posixpath.join(remote_input_dir, remote_name)
                river_log(f"[UPLOAD] Uploading River data: {Path(local_data).name}")
                ssh_upload_file(client, local_data, remote_path)
                sample["h5ad_path"] = remote_path
                sample["data_path"] = remote_path
                data_paths[local_data] = remote_path

            local_csv = sample.get("csv_path")
            if local_csv:
                remote_name = f"sample_{idx + 1}_{remote_safe_name(local_csv)}"
                remote_path = posixpath.join(remote_input_dir, remote_name)
                river_log(f"[UPLOAD] Uploading River CSV: {Path(local_csv).name}")
                ssh_upload_file(client, local_csv, remote_path)
                sample["csv_path"] = remote_path
                csv_paths[local_csv] = remote_path

        remote_cfg["h5ad_files"] = [data_paths.get(p, p) for p in remote_cfg.get("h5ad_files", [])]
        remote_cfg["csv_files"] = [csv_paths.get(p, p) for p in remote_cfg.get("csv_files", [])]
        return remote_cfg

    def download_remote_river_outputs(client, remote_output_dir, local_out_dir: Path):
        summary_path = local_out_dir / "river_summary.json"
        ssh_download_file(client, posixpath.join(remote_output_dir, "river_summary.json"), summary_path)

        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        artifact_keys = [
            "plot_png",
            "plot_pdf",
            "rank_file",
            "rank_csv",
            "ig_file",
            "dl_file",
            "sl_file",
            "plot_adata",
            "plot_feature_csv",
        ]

        for key in artifact_keys:
            remote_path = summary.get(key)
            if not remote_path:
                continue
            remote_name = posixpath.basename(str(remote_path))
            local_path = local_out_dir / remote_name
            try:
                ssh_download_file(client, remote_path, local_path)
                summary[key] = str(local_path.resolve())
                river_log(f"[DOWNLOAD] Downloaded River artifact: {remote_name}")
            except Exception as e:
                river_log(f"[WARN] Failed to download remote artifact {key}: {e}")
                summary[key] = None

        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return summary_path

    def run_river_remote(cfg, out_dir: Path):
        state = ssh_state.get()
        client = ssh_open_client(state)

        try:
            river_python = (state.get("river_python_cmd") or state.get("python_cmd") or "python").strip()
            river_log("[CHECK] Checking remote River Python environment dependencies...")
            ssh_check_python_packages(
                client,
                river_python,
                REQUIRED_RIVER_PACKAGES,
                label="River",
            )

            remote_dir = ssh_prepare_job_dir(client, state, "river")
            remote_input_dir = posixpath.join(remote_dir, "inputs")
            remote_output_dir = posixpath.join(remote_dir, "output")
            remote_app_dir = posixpath.join(remote_dir, "app")

            ssh_mkdir_p(client, remote_input_dir)
            ssh_mkdir_p(client, remote_output_dir)
            ssh_mkdir_p(client, remote_app_dir)

            if "__file__" in globals():
                base_dir = Path(__file__).resolve().parent
            else:
                base_dir = Path.cwd()

            runner_path = base_dir / "river_runner.py"
            river_pkg_dir = base_dir / "river"
            if not runner_path.exists():
                raise RuntimeError(f"River runner script not found: {runner_path}")
            if not river_pkg_dir.exists():
                raise RuntimeError(f"River package directory not found: {river_pkg_dir}")

            river_log(f"[REMOTE] SSH remote River job directory: {remote_dir}")
            river_log("[UPLOAD] Uploading River runner and package...")
            ssh_upload_file(client, runner_path, posixpath.join(remote_app_dir, "river_runner.py"))
            ssh_upload_directory(client, river_pkg_dir, posixpath.join(remote_app_dir, "river"))

            remote_cfg = build_remote_cfg_and_uploads(client, cfg, remote_input_dir)
            local_remote_cfg = out_dir / "river_remote_config.json"
            local_remote_cfg.write_text(
                json.dumps(remote_cfg, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            ssh_upload_file(client, local_remote_cfg, posixpath.join(remote_dir, "river_config.json"))

            command = (
                f"cd {ssh_quote(remote_app_dir)} && "
                f"{river_python} river_runner.py "
                f"--config {ssh_quote(posixpath.join(remote_dir, 'river_config.json'))} "
                f"--output {ssh_quote(remote_output_dir)}"
            )

            river_log(f"[RUN] Running remote River with: {river_python}")
            result = ssh_exec_command(client, command, timeout=None)
            river_log(f"Remote process return code: {result['exit_status']}")

            if result.get("stdout"):
                river_log("[remote stdout]")
                river_log(result["stdout"])
            if result.get("stderr"):
                river_log("[remote stderr]")
                river_log(result["stderr"])

            if result["exit_status"] != 0:
                raise RuntimeError(f"Remote River runner exited with non-zero status: {result['exit_status']}")

            return download_remote_river_outputs(client, remote_output_dir, out_dir)
        finally:
            client.close()

    def safe_filename(x: str) -> str:
        x = str(x or "river_feature").strip()
        x = re.sub(r"[^\w\-.]+", "_", x)
        return x or "river_feature"

    def to_1d_array(x):
        if hasattr(x, "toarray"):
            x = x.toarray()
        return np.asarray(x).reshape(-1)

    def close_backed_adata(adata):
        try:
            if getattr(adata, "isbacked", False) and getattr(adata, "file", None) is not None:
                adata.file.close()
        except Exception:
            pass

    def load_plot_adata_metadata(plot_adata_path, feature_csv=None):
        features = []
        if feature_csv and os.path.exists(feature_csv):
            try:
                df = pd.read_csv(feature_csv)
                if "feature" in df.columns:
                    features = df["feature"].astype(str).tolist()
                elif df.shape[1] > 0:
                    features = df.iloc[:, 0].astype(str).tolist()
            except Exception:
                features = []

        backed = sc.read_h5ad(plot_adata_path, backed="r")
        try:
            var_names = [str(x) for x in backed.var_names.tolist()]
            var_set = set(var_names)
            features = [f for f in features if f in var_set] if features else var_names

            coords = None
            if "spatial" in backed.obsm:
                coords = np.asarray(backed.obsm["spatial"], dtype=np.float32)
                if coords.ndim == 2 and coords.shape[1] >= 2:
                    coords = coords[:, :2]
                else:
                    coords = None

            return {
                "path": str(Path(plot_adata_path).resolve()),
                "features": features,
                "coords": coords,
                "shape": tuple(backed.shape),
            }
        finally:
            close_backed_adata(backed)

    def read_plot_feature_values(plot_meta, feature):
        path = plot_meta.get("path") if isinstance(plot_meta, dict) else None
        if not path or not os.path.exists(path):
            raise RuntimeError("river_plot_adata.h5ad is missing.")

        backed = sc.read_h5ad(path, backed="r")
        try:
            feature = str(feature)
            if feature not in backed.var_names:
                raise RuntimeError(f"Feature not found: {feature}")
            return to_1d_array(backed[:, [feature]].X)
        finally:
            close_backed_adata(backed)

    def get_river_cmap(name: str):
        name = str(name or "Balance_20")

        if name == "Balance_20":
            if Balance_20 is not None:
                return ListedColormap(Balance_20.mpl_colors)
            return plt.get_cmap("viridis")

        if name == "Delta_20":
            if Delta_20 is not None:
                return ListedColormap(Delta_20.mpl_colors)
            return plt.get_cmap("plasma")

        if name == "Viridis":
            return plt.get_cmap("viridis")

        if name == "Magma":
            return plt.get_cmap("magma")

        if name == "BlueWhiteRed":
            return LinearSegmentedColormap.from_list(
                "blue_white_red",
                ["#313695", "#FFFFFF", "#A50026"]
            )

        return plt.get_cmap("viridis")

    def empty_river_fig(msg="Please run River first."):
        fig, ax = plt.subplots(figsize=(10, 3))
        ax.axis("off")
        ax.text(0.5, 0.5, msg, ha="center", va="center", fontsize=12)
        return fig

    def build_river_feature_figure(feature: str, cmap_name: str):
        plot_meta = river_plot_adata.get()
        if not plot_meta:
            return empty_river_fig("No river_plot_adata.h5ad found.")

        feature = str(feature)
        feature_choices = plot_meta.get("features", []) if isinstance(plot_meta, dict) else []
        if feature_choices and feature not in feature_choices:
            return empty_river_fig(f"Feature not found: {feature}")

        coords = plot_meta.get("coords") if isinstance(plot_meta, dict) else None
        if coords is None:
            return empty_river_fig("No spatial coordinates found in adata.obsm['spatial'].")

        try:
            vals = read_plot_feature_values(plot_meta, feature)
        except Exception as e:
            return empty_river_fig(format_exception(e))

        if vals.size == 0:
            return empty_river_fig(f"No values found for feature: {feature}")

        coords = np.asarray(coords, dtype=float)
        if coords.ndim != 2 or coords.shape[1] < 2:
            return empty_river_fig("Invalid spatial coordinates.")
        if coords.shape[0] != vals.shape[0]:
            return empty_river_fig("Feature values and spatial coordinates do not have the same length.")

        x = coords[:, 0]
        y = coords[:, 1]

        vmin = float(np.nanmin(vals))
        vmax = float(np.nanmax(vals))

        if not np.isfinite(vmin) or not np.isfinite(vmax):
            vmin, vmax = 0.0, 1.0
        if vmin == vmax:
            vmax = vmin + 1e-9

        norm = plt.Normalize(vmin=vmin, vmax=vmax)
        cmap = get_river_cmap(cmap_name)

        plt.close("all")
        fig, ax = plt.subplots(figsize=(20, 4))

        sca = ax.scatter(
            x,
            y,
            c=vals,
            cmap=cmap,
            norm=norm,
            s=18,
            linewidths=0,
            alpha=0.95
        )

        ax.set_title(f"River feature: {feature}", fontsize=14)
        ax.set_xlabel("")
        ax.set_ylabel("")
        ax.set_xticks([])
        ax.set_yticks([])
        ax.invert_yaxis()

        for spine in ax.spines.values():
            spine.set_visible(False)

        cbar = fig.colorbar(sca, ax=ax, fraction=0.025, pad=0.01)
        cbar.ax.set_title("Expr", fontsize=9)

        fig.tight_layout()
        return fig

    # =========================================================
    # Outputs
    # =========================================================
    @output
    @render.text
    def river_console_output():
        return river_log_text.get()

    @output
    @render.text
    def river_status():
        return river_status_text.get()

    @output
    @render.text
    def river_folder_preview():
        return river_preview_text.get()

    # =========================================================
    # Feature selector UI
    # =========================================================
    @output
    @render.ui
    def river_feature_name_ui():
        plot_meta = river_plot_adata.get()
        choices = river_rank_features.get()
        if not choices and isinstance(plot_meta, dict):
            choices = [str(x) for x in plot_meta.get("features", [])]

        selected = river_selected_feature.get()
        if selected not in choices:
            selected = None

        return ui.input_selectize(
            "river_feature_name",
            "Feature name",
            choices=choices,
            selected=selected,
            multiple=False,
            options={"placeholder": "Search feature name..."}
        )

    # =========================================================
    # Preview
    # =========================================================
    @reactive.Effect
    @reactive.event(input.river_preview_btn)
    def _preview_river_inputs():
        try:
            cfg, preview = prepare_uploads()
            river_preview_text.set(preview)
            river_status_text.set(
                f"Validation passed. {len(cfg['samples'])} sample(s) detected."
            )
            river_log("[OK] Preview completed successfully.")

        except Exception as e:
            err = format_exception(e)
            tb = traceback.format_exc()

            msg = f"Preview failed: {err}"
            river_preview_text.set(msg)
            river_status_text.set(msg)
            river_log(f"[ERROR] {msg}")
            river_log(tb)

    # =========================================================
    # Run River
    # =========================================================
    @reactive.Effect
    @reactive.event(input.river_run_btn)
    def _run_river():
        river_log_text.set("")
        river_status_text.set("Running analysis...")
        river_plot_png.set(None)
        river_plot_pdf.set(None)
        river_rank_npy.set(None)
        river_rank_csv.set(None)
        river_summary_json.set(None)
        river_plot_adata_path.set(None)
        river_plot_adata.set(None)
        river_rank_features.set([])
        river_selected_feature.set(None)

        ui.modal_show(
            ui.modal(
                ui.p("Reading uploaded .h5ad / .h5 / CSV files and calling River environment..."),
                title="River is running",
                easy_close=False,
                footer=None,
            )
        )

        try:
            river_log("=== River run started ===")

            cfg, preview = prepare_uploads()
            river_preview_text.set(preview)
            river_log(preview)

            if not cfg["samples"]:
                raise RuntimeError("No valid samples were prepared from uploaded .h5ad / .h5 files.")

            old_out = river_output_dir.get()
            if old_out and Path(old_out).exists():
                shutil.rmtree(old_out, ignore_errors=True)

            out_dir = create_job_output_dir("river")
            river_output_dir.set(str(out_dir))
            river_log(f"Output directory: {out_dir}")

            if remote_enabled():
                river_log("[REMOTE] SSH connected: running River on the selected remote environment.")
                summary_path = run_river_remote(cfg, out_dir)
                river_log(f"Remote summary downloaded to: {summary_path}")
            else:
                river_python = (input.river_python() or "").strip()
                if not river_python:
                    river_python = os.environ.get("SPASHINY_RIVER_PYTHON", sys.executable)
                    river_log(f"No river_python provided. Using SPASHINY_RIVER_PYTHON/current interpreter: {river_python}")

                river_log(f"Using local Python: {river_python}")

                if not Path(river_python).exists():
                    raise RuntimeError(f"River Python path does not exist: {river_python}")

                config_path = out_dir / "river_config.json"
                config_path.write_text(
                    json.dumps(cfg, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
                river_log(f"Config written to: {config_path}")

                if "__file__" in globals():
                    runner_path = Path(__file__).resolve().with_name("river_runner.py")
                else:
                    runner_path = Path.cwd() / "river_runner.py"

                river_log(f"Runner path resolved to: {runner_path}")

                if not runner_path.exists():
                    raise RuntimeError(f"Runner script not found: {runner_path}")

                cmd = [
                    river_python,
                    str(runner_path),
                    "--config",
                    str(config_path),
                    "--output",
                    str(out_dir),
                ]

                river_log("Command to execute:")
                river_log(" ".join(cmd))

                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="ignore",
                )

                river_log(f"Process return code: {proc.returncode}")

                if proc.stdout:
                    river_log("[stdout]")
                    river_log(proc.stdout)

                if proc.stderr:
                    river_log("[stderr]")
                    river_log(proc.stderr)

                if proc.returncode != 0:
                    raise RuntimeError(f"River runner exited with non-zero status: {proc.returncode}")

                summary_path = out_dir / "river_summary.json"
                river_log(f"Looking for summary: {summary_path}")

                if not summary_path.exists():
                    raise RuntimeError(
                        "The runner did not generate river_summary.json. "
                        "Please check the River environment and dependencies."
                    )

            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            base_dir = summary_path.parent

            river_summary_json.set(str(summary_path.resolve()))
            river_plot_png.set(resolve_artifact_path(summary.get("plot_png"), base_dir))
            river_plot_pdf.set(resolve_artifact_path(summary.get("plot_pdf"), base_dir))
            river_rank_npy.set(resolve_artifact_path(summary.get("rank_file"), base_dir))
            river_rank_csv.set(resolve_artifact_path(summary.get("rank_csv"), base_dir))
            river_plot_adata_path.set(resolve_artifact_path(summary.get("plot_adata"), base_dir))

            if not summary.get("river_success", False):
                raise RuntimeError(summary.get("message", "River runner reported failure."))

            plot_adata_path = river_plot_adata_path.get()
            if plot_adata_path and os.path.exists(plot_adata_path):
                plot_meta = load_plot_adata_metadata(
                    plot_adata_path,
                    resolve_artifact_path(summary.get("plot_feature_csv"), base_dir),
                )
                river_plot_adata.set(plot_meta)
                river_log(f"Loaded plot metadata: {plot_adata_path}")
                river_log(
                    f"Plot metadata shape={plot_meta.get('shape')}, "
                    f"cached features={len(plot_meta.get('features', []))}"
                )
            else:
                river_plot_adata.set(None)
                river_log("[WARN] plot_adata was not found in summary.")

            rank_feats = []
            rank_npy = river_rank_npy.get()
            rank_csv = river_rank_csv.get()

            if rank_npy and os.path.exists(rank_npy):
                arr = np.load(rank_npy, allow_pickle=True)
                rank_feats = [str(x) for x in arr.tolist()]
            elif rank_csv and os.path.exists(rank_csv):
                df = pd.read_csv(rank_csv)
                if "feature" in df.columns:
                    rank_feats = df["feature"].astype(str).tolist()
                elif df.shape[1] > 0:
                    rank_feats = df.iloc[:, 0].astype(str).tolist()

            river_rank_features.set(rank_feats)
            if rank_feats:
                river_selected_feature.set(rank_feats[0])
                river_log(f"Loaded ranked features: {len(rank_feats)}")
                river_log(f"Default feature set to: {rank_feats[0]}")
            else:
                river_log("[WARN] No ranked features found.")

            status_lines = [
                f"Mode: {summary.get('mode')}",
                f"Number of valid samples: {summary.get('n_valid', 0)}",
                f"Valid samples: {', '.join(summary.get('valid_samples', [])) or 'None'}",
                f"Invalid samples: {', '.join(summary.get('invalid_samples', [])) or 'None'}",
                f"River success: {summary.get('river_success')}",
            ]
            if summary.get("message"):
                status_lines.append(f"Message: {summary['message']}")

            river_status_text.set("\n".join(status_lines))
            river_log("[OK] River module finished successfully.")

        except Exception as e:
            err = format_exception(e)
            tb = traceback.format_exc()

            river_status_text.set(f"Run failed: {err}")
            river_log(f"[ERROR] {err}")
            river_log(tb)

        finally:
            ui.modal_remove()
            gc.collect()
            if current_process_memory is not None:
                try:
                    mem = current_process_memory()
                    river_log(f"Shiny process memory RSS: {mem['rss_text']}")
                except Exception:
                    pass

    # =========================================================
    # Generate feature plot
    # =========================================================
    @reactive.Effect
    @reactive.event(input.river_generate_feature_btn)
    def _generate_river_feature():
        try:
            mode = input.river_feature_mode() or "top"

            if mode == "top":
                rank_feats = river_rank_features.get()
                if not rank_feats:
                    raise RuntimeError("No ranked features found. Please run River first.")
                top_idx = int(input.river_top_index() or 1)
                if top_idx < 1 or top_idx > len(rank_feats):
                    raise RuntimeError(f"TOP index must be between 1 and {len(rank_feats)}.")
                feature = rank_feats[top_idx - 1]
            else:
                feature = str(input.river_feature_name() or "").strip()
                if not feature:
                    raise RuntimeError("Please choose a feature name.")

            river_selected_feature.set(feature)
            river_log(f" Selected feature: {feature}")
            river_log(f" Colormap: {input.river_feature_cmap() or 'Balance_20'}")

        except Exception as e:
            river_log(f"[ERROR] {format_exception(e)}")

    @reactive.Effect
    @reactive.event(input.palette_river_feature_plot)
    def _open_river_feature_palette():
        _show_river_color_modal()

    @reactive.Effect
    @reactive.event(input.apply_river_plot_color_palette)
    def _apply_river_plot_color_palette():
        settings_map = dict(river_color_settings.get() or {})
        settings_map["river_feature_plot"] = _river_modal_settings_from_inputs()
        river_color_settings.set(settings_map)
        river_color_revision.set(river_color_revision.get() + 1)
        ui.modal_remove()
        ui.notification_show("River feature plot colors updated.", type="message")

    @reactive.Effect
    @reactive.event(input.reset_river_plot_color_palette)
    def _reset_river_plot_color_palette():
        settings_map = dict(river_color_settings.get() or {})
        settings_map.pop("river_feature_plot", None)
        river_color_settings.set(settings_map)
        river_color_revision.set(river_color_revision.get() + 1)
        ui.modal_remove()
        ui.notification_show("River feature plot colors reset to defaults.", type="message")

    # =========================================================
    # Result image
    # =========================================================
    @output
    @render.image
    def river_result_image():
        png = river_plot_png.get()
        if not png or not os.path.exists(png):
            return None

        return {
            "src": png,
            "content_type": "image/png",
            "width": "100%",
            "alt": "River result plot"
        }

    # =========================================================
    # Feature plot
    # =========================================================
    @output
    @render.plot
    @river_plot_colorized("river_feature_plot")
    def river_feature_plot():
        feature = river_selected_feature.get()
        if not feature:
            return empty_river_fig("Please choose TOP index or feature name, then click Generate Feature Plot.")

        cmap_name = input.river_feature_cmap() or "Balance_20"
        return build_river_feature_figure(feature, cmap_name)

    # =========================================================
    # Downloads
    # =========================================================
    @render.download(filename=lambda: "river_result.pdf")
    def river_download_pdf():
        pdf = river_plot_pdf.get()
        if pdf and os.path.exists(pdf):
            with open(pdf, "rb") as f:
                yield f.read()
        else:
            yield b""

    @render.download(filename=lambda: "river_rank_temporal.npy")
    def river_download_rank():
        npy = river_rank_npy.get()
        if npy and os.path.exists(npy):
            with open(npy, "rb") as f:
                yield f.read()
        else:
            yield b""

    @render.download(filename=lambda: "river_summary.json")
    def river_download_summary():
        js = river_summary_json.get()
        if js and os.path.exists(js):
            with open(js, "rb") as f:
                yield f.read()
        else:
            yield b""

    @render.download(filename=lambda: f"river_feature_{safe_filename(river_selected_feature.get())}.pdf")
    def river_download_feature_pdf():
        feature = river_selected_feature.get()
        if not feature:
            yield b""
            return

        fig = build_river_feature_figure(
            feature=feature,
            cmap_name=input.river_feature_cmap() or "Balance_20"
        )
        fig = river_colorize_plot("river_feature_plot", fig)

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        tmp.close()

        try:
            with PdfPages(tmp.name) as pdf:
                pdf.savefig(fig, dpi=300, bbox_inches="tight")
            plt.close(fig)

            with open(tmp.name, "rb") as f:
                yield f.read()

            river_log(f" Exported feature PDF: {feature}")

        finally:
            if os.path.exists(tmp.name):
                os.remove(tmp.name)
