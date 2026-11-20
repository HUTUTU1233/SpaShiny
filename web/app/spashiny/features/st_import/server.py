# Extracted from /app/app/ST-SM.py. Feature: st_import; ordered phases preserve original initialization.
from spashiny._shared import runtime_globals as _spashiny_globals


def _install_0(_spashiny_ctx):

    def load_example_st_data():
        if _spashiny_globals.SPASHINY_WEB_PLATFORM:
            try:
                from cloud.input_resolver import InputResolver

                resolved = InputResolver().resolve_interactive_local_input(
                    session_id=_spashiny_ctx._require_cloud_session_id(),
                    analysis_session_id=str(_spashiny_ctx._cloud_analysis_session_id() or ""),
                    action_id="y7-st-upload-example",
                    input_role="st_raw_zip",
                    workflow_name="st_quality_control",
                )
                example_path = _spashiny_ctx.Path(resolved["local_path"])
                _spashiny_ctx.st_example_dir_path.set(str(example_path))
                _spashiny_ctx.st_preprocess_source.set("EXAMPLE")
                _spashiny_ctx.adata_st.set(None)
                _spashiny_ctx.log("Lab Y7_T ST example selected for this Session.")
                _spashiny_ctx.log(f"  ST h5ad: {example_path}")
                _spashiny_ctx.log("Click Start Processing to load the ST example.")
                _spashiny_ctx.ui.notification_show(
                    "Y7_T ST example is ready. Click Start Processing.", type="message", duration=6
                )
            except Exception as exc:
                _spashiny_ctx.st_example_dir_path.set(None)
                _spashiny_ctx.st_preprocess_source.set("")
                _spashiny_ctx.log(f"Failed to load Lab Y7_T ST example: {exc}")
                _spashiny_ctx.ui.notification_show(
                    f"Failed to load Lab Y7_T ST example: {exc}", type="error", duration=10
                )
            return
        _spashiny_ctx.log(" Loading example ST data ...")
        try:
            adata_ST, source_path, source_kind = _spashiny_globals.read_example_st_anndata()
            adata_ST.var_names_make_unique()
            _spashiny_ctx.adata_st.set(adata_ST)
            _spashiny_ctx.st_example_dir_path.set(str(source_path))
            _spashiny_ctx.log(
                f"Example ST loaded from {source_kind}: {_spashiny_globals.workspace_relative_path(source_path)}"
            )
            _spashiny_ctx.log(f"ST example data loaded successfully, shape: {adata_ST.shape}")
            _spashiny_ctx.ui.notification_show(
                "Example ST data loaded successfully.", type="message", duration=5
            )
            return
            example_st_dir = _spashiny_globals.get_example_st_dir()
            if not example_st_dir.exists():
                msg = f"Example ST folder was not found: {example_st_dir}"
                _spashiny_ctx.log(f"{msg}")
                _spashiny_ctx.ui.notification_show(msg, type="error", duration=6)
                return
            visium_dir = _spashiny_globals.find_visium_dir(example_st_dir)
            if visium_dir is None:
                msg = (
                    f"Example ST folder is not a complete Visium output directory: {example_st_dir}"
                )
                _spashiny_ctx.log(f"Error: {msg}")
                _spashiny_ctx.ui.notification_show(msg, type="error", duration=6)
                return
            adata_ST = _spashiny_globals.read_visium_anndata(visium_dir)
            adata_ST.var_names_make_unique()
            _spashiny_ctx.adata_st.set(adata_ST)
            _spashiny_ctx.st_example_dir_path.set(str(visium_dir))
            _spashiny_ctx.log(f" Example ST loaded from: {example_st_dir}")
            _spashiny_ctx.log(f"ST example data loaded successfully, shape: {adata_ST.shape}")
            _spashiny_ctx.ui.notification_show(
                "Example ST data loaded successfully.", type="message", duration=5
            )
        except Exception as e:
            _spashiny_ctx.log(f"Error while loading example ST data: {e}")
            _spashiny_ctx.log(_spashiny_ctx.traceback.format_exc())
            _spashiny_ctx.ui.notification_show(
                f"Error while loading example ST data: {e}", type="error", duration=8
            )

    _spashiny_ctx.load_example_st_data = load_example_st_data

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.load_example_st)
    def _on_load_example_st():
        _spashiny_ctx.load_example_st_data()

    _spashiny_ctx._on_load_example_st = _on_load_example_st

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.st_files, ignore_none=True)
    def _select_st_preprocessing_upload():
        if _spashiny_ctx.input.st_files():
            _spashiny_ctx.st_preprocess_source.set("USER_UPLOAD")
            _spashiny_ctx.st_example_dir_path.set(None)
            _spashiny_ctx.adata_st.set(None)

    _spashiny_ctx._select_st_preprocessing_upload = _select_st_preprocessing_upload

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(
        _spashiny_ctx.input.cloud_example_action_activated, ignore_none=True
    )
    def _select_preprocessing_example_from_cloud_action():
        if not _spashiny_globals.SPASHINY_WEB_PLATFORM:
            return
        payload = _spashiny_ctx.input.cloud_example_action_activated() or {}
        if not isinstance(payload, dict) or not payload.get("ready"):
            return
        if str(payload.get("analysis_session_id") or "") != str(
            _spashiny_ctx._cloud_analysis_session_id() or ""
        ):
            return
        action_id = str(payload.get("action_id") or "")
        if action_id == "y7-st-upload-example":
            _spashiny_ctx.load_example_st_data()
        elif action_id == "y7-sm-upload-imzml-example":
            _spashiny_ctx.load_example_sm_data()

    _spashiny_ctx._select_preprocessing_example_from_cloud_action = (
        _select_preprocessing_example_from_cloud_action
    )

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.process_st)
    def process_st_data():
        _spashiny_ctx.log(" Starting ST data loading ...")
        try:
            st_files = _spashiny_ctx.input.st_files() or []
            if (
                _spashiny_globals.SPASHINY_WEB_PLATFORM
                and _spashiny_ctx.st_preprocess_source.get() == "EXAMPLE"
            ):
                from cloud.input_resolver import InputResolver

                selected = InputResolver().resolve_interactive_local_input(
                    session_id=_spashiny_ctx._require_cloud_session_id(),
                    analysis_session_id=str(_spashiny_ctx._cloud_analysis_session_id() or ""),
                    action_id="y7-st-upload-example",
                    input_role="st_raw_zip",
                    workflow_name="st_quality_control",
                )
                _spashiny_ctx.st_example_dir_path.set(str(selected["local_path"]))
                st_files = []
            if not st_files:
                existing_st = _spashiny_ctx.adata_st.get()
                if existing_st is not None:
                    _spashiny_ctx.log(
                        f"ST data is already loaded, shape: {existing_st.shape}. No upload is needed."
                    )
                    _spashiny_ctx.ui.notification_show(
                        "ST data is already loaded. You can continue with downstream analysis.",
                        type="message",
                        duration=5,
                    )
                    return
                example_path = _spashiny_ctx.st_example_dir_path.get()
                if example_path and _spashiny_ctx.Path(example_path).exists():
                    example_path = _spashiny_ctx.Path(example_path)
                    if example_path.suffix.lower() == ".h5ad":
                        adata_ST = _spashiny_globals.compact_adata_X(
                            _spashiny_globals.smt.read_h5ad_st(str(example_path))
                        )
                    else:
                        if example_path.suffix.lower() == ".zip":
                            example_path = _spashiny_globals.resolve_visium_upload_path(
                                example_path,
                                _spashiny_ctx.Path(_spashiny_ctx.create_temp_dir())
                                / "st_example_visium",
                            )
                        adata_ST = _spashiny_globals.read_visium_anndata(example_path)
                    adata_ST.var_names_make_unique()
                    _spashiny_ctx.adata_st.set(adata_ST)
                    _spashiny_ctx.log(
                        f"ST example data loaded successfully, shape: {adata_ST.shape}"
                    )
                    _spashiny_ctx.ui.notification_show(
                        "ST example data loaded successfully.", type="message", duration=5
                    )
                    return
                _spashiny_ctx.log(
                    "Please upload an ST .zip/.h5ad file or click Load Example ST first."
                )
                _spashiny_ctx.ui.notification_show(
                    "Please upload an ST .zip/.h5ad file or click Load Example ST first.",
                    type="error",
                    duration=6,
                )
                return
            td = _spashiny_ctx.create_temp_dir()
            dst_path = _spashiny_ctx.Path(td) / st_files[0]["name"]
            with open(dst_path, "wb") as f:
                f.write(_spashiny_ctx.Path(st_files[0]["datapath"]).read_bytes())
            _spashiny_ctx.st_example_dir_path.set(None)
            _spashiny_ctx.log(f" ST file has been saved to {dst_path}")
            if dst_path.suffix.lower() == ".h5ad":
                _spashiny_ctx.log(f"Reading raw ST h5ad file: {dst_path}")
                adata_ST = _spashiny_globals.compact_adata_X(
                    _spashiny_globals.smt.read_h5ad_st(str(dst_path))
                )
            else:
                visium_dir = _spashiny_globals.resolve_visium_upload_path(
                    dst_path, _spashiny_ctx.Path(td) / "st_uploads"
                )
                _spashiny_ctx.log(f"Reading Visium directory: {visium_dir}")
                adata_ST = _spashiny_globals.read_visium_anndata(visium_dir)
            adata_ST.var_names_make_unique()
            _spashiny_ctx.adata_st.set(adata_ST)
            _spashiny_ctx.log(f"ST data loaded successfully, shape: {adata_ST.shape}")
            _spashiny_ctx.ui.notification_show(
                "ST data loaded successfully.", type="message", duration=5
            )
        except Exception as e:
            _spashiny_ctx.log(f"Error while processing ST data: {e}")
            _spashiny_ctx.log(_spashiny_ctx.traceback.format_exc())
            _spashiny_ctx.ui.notification_show(
                f"Error while processing ST data: {e}", type="error", duration=8
            )

    _spashiny_ctx.process_st_data = process_st_data

    def _preprocessing_export_path(filename):
        filename = str(filename)
        if not filename or _spashiny_ctx.Path(filename).name != filename or "\\" in filename:
            raise ValueError("Export filename must be a file name, not a path.")
        root = (
            _spashiny_ctx._alignment_session_result_root() / "preprocessing" / "exports"
            if _spashiny_globals.SPASHINY_WEB_PLATFORM
            else _spashiny_ctx.Path(_spashiny_ctx.create_temp_dir()) / "exports"
        )
        destination = root / _spashiny_globals.uuid.uuid4().hex
        destination.mkdir(parents=True, exist_ok=False)
        return destination / filename

    _spashiny_ctx._preprocessing_export_path = _preprocessing_export_path

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.save_h5ad)
    def save_h5ad_file():
        adata = _spashiny_ctx.adata_final.get()
        if adata is None:
            _spashiny_ctx.log(" No SM data available to save.")
            return
        changes = _spashiny_globals.sanitize_h5ad_keys(adata)
        if changes:
            preview = ", ".join(changes[:5])
            suffix = " ..." if len(changes) > 5 else ""
            _spashiny_ctx.log(f"Normalized h5ad metadata keys before saving: {preview}{suffix}")
        out_file = _spashiny_ctx._preprocessing_export_path(
            f"manual_save_{int(_spashiny_ctx.time.time())}.h5ad"
        )
        adata.write_h5ad(out_file)
        _spashiny_ctx.log(f" Manual save completed: {out_file}")

    _spashiny_ctx.save_h5ad_file = save_h5ad_file

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.save_st)
    def save_st_file():
        adata = _spashiny_ctx.adata_st.get()
        if adata is None:
            _spashiny_ctx.log(" No ST data available to save.")
            return
        out_file = _spashiny_ctx._preprocessing_export_path(
            f"ST_save_{int(_spashiny_ctx.time.time())}.h5ad"
        )
        adata.write_h5ad(out_file)
        _spashiny_ctx.log(f" ST data saved successfully: {out_file}")

    _spashiny_ctx.save_st_file = save_st_file

    @_spashiny_ctx.render.download(
        filename=lambda: f"{int(_spashiny_ctx.time.time())}_adata_SM_raw.h5ad"
    )
    def download_h5ad():
        adata = _spashiny_ctx.adata_final.get()
        if adata is None:
            raise RuntimeError(
                "Load/process the selected SM input before downloading its H5AD result."
            )
        _spashiny_globals.sanitize_h5ad_keys(adata)
        try:
            with _spashiny_ctx.tempfile.TemporaryDirectory(prefix="sm-raw-export-") as directory:
                path = _spashiny_ctx.Path(directory) / "adata_SM_raw.h5ad"
                adata.write_h5ad(path)
                yield from _spashiny_ctx.stream_file(path)
        finally:
            _spashiny_globals.release_unused_memory()

    _spashiny_ctx.download_h5ad = download_h5ad

    @_spashiny_ctx.render.download(
        filename=lambda: f"{int(_spashiny_ctx.time.time())}_adata_ST_raw.h5ad"
    )
    def download_st():
        adata = _spashiny_ctx.adata_st.get()
        if adata is None:
            raise RuntimeError(
                "Load/process the selected ST input before downloading its H5AD result."
            )
        try:
            with _spashiny_ctx.tempfile.TemporaryDirectory(prefix="st-raw-export-") as directory:
                path = _spashiny_ctx.Path(directory) / "adata_ST_raw.h5ad"
                adata.write_h5ad(path)
                yield from _spashiny_ctx.stream_file(path)
        finally:
            _spashiny_globals.release_unused_memory()

    _spashiny_ctx.download_st = download_st
    import seaborn as sns

    _spashiny_ctx.sns = sns
    import matplotlib.pyplot as plt

    _spashiny_globals.plt = plt
    import scanpy as sc

    _spashiny_globals.sc = sc
    import spatialmeta as smt

    _spashiny_globals.smt = smt
    from matplotlib.colors import LinearSegmentedColormap

    _spashiny_ctx.LinearSegmentedColormap = LinearSegmentedColormap
    from pathlib import Path

    _spashiny_ctx.Path = Path

    def make_colormap(colors):
        return _spashiny_ctx.LinearSegmentedColormap.from_list("custom_cmap", colors)

    _spashiny_ctx.make_colormap = make_colormap
    _spashiny_ctx.qc_log = _spashiny_ctx.reactive.Value("")
    _spashiny_ctx.adata_SM = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.adata_SM_qc_base = _spashiny_ctx.reactive.Value(None)
    _spashiny_ctx.sm_qc_input_reference = _spashiny_ctx.reactive.Value(None)

    def _select_qc_input(kind, reference):
        current, result, base = (
            (
                _spashiny_ctx.st_qc_input_reference,
                _spashiny_ctx.adata_ST,
                _spashiny_ctx.adata_ST_qc_base,
            )
            if kind == "ST"
            else (
                _spashiny_ctx.sm_qc_input_reference,
                _spashiny_ctx.adata_SM,
                _spashiny_ctx.adata_SM_qc_base,
            )
        )
        if reference is None or current.get() != reference:
            result.set(None)
            base.set(None)
        current.set(reference)

    _spashiny_ctx._select_qc_input = _select_qc_input


_STEPS = (_install_0,)


def server(_spashiny_ctx, step=0):
    return _STEPS[step](_spashiny_ctx)
