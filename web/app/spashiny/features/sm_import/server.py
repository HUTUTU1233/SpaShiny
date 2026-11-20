# Extracted from /app/app/ST-SM.py. Feature: sm_import; ordered phases preserve original initialization.
from spashiny._shared import runtime_globals as _spashiny_globals


def _install_0(_spashiny_ctx):

    @_spashiny_ctx.output
    @_spashiny_ctx.render.ui
    def file_inputs():
        dtype = _spashiny_ctx.input.data_type()
        if dtype == "ImzML":
            return [
                _spashiny_ctx.ui.input_file(
                    "pos_files", "Upload Positive imzML / ibd Files", multiple=True
                ),
                _spashiny_ctx.ui.input_file(
                    "neg_files", "Upload Negative imzML / ibd Files", multiple=True
                ),
            ]
        else:
            return _spashiny_ctx.ui.input_file("csv_file", "Upload Spatial Metabolomics CSV File")

    _spashiny_ctx.file_inputs = file_inputs

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(
        _spashiny_ctx.input.pos_files, _spashiny_ctx.input.neg_files, _spashiny_ctx.input.csv_file
    )
    def save_uploaded_files():
        selected_files = (
            (_spashiny_ctx.input.pos_files() or [])
            + (_spashiny_ctx.input.neg_files() or [])
            + (_spashiny_ctx.input.csv_file() or [])
        )
        if not selected_files and _spashiny_ctx.sm_preprocess_source.get() == "EXAMPLE":
            return
        _spashiny_ctx.sm_preprocess_source.set("USER_UPLOAD" if selected_files else "")
        _spashiny_ctx.raw_pos_dir.set(None)
        _spashiny_ctx.raw_neg_dir.set(None)
        _spashiny_ctx.csv_file_path.set(None)
        _spashiny_ctx.adata_final.set(None)
        dtype = _spashiny_ctx.input.data_type()
        td = _spashiny_ctx.create_temp_dir()
        if dtype == "ImzML":
            pos_files = _spashiny_ctx.input.pos_files() or []
            neg_files = _spashiny_ctx.input.neg_files() or []
            if pos_files:
                pos_dir = _spashiny_ctx.Path(td) / "pos"
                pos_dir.mkdir(parents=True, exist_ok=True)
                for f in pos_files:
                    dst = pos_dir / f["name"]
                    with open(dst, "wb") as out_f:
                        out_f.write(_spashiny_ctx.Path(f["datapath"]).read_bytes())
                _spashiny_ctx.raw_pos_dir.set(str(pos_dir))
                _spashiny_ctx.log(f" Saved positive files to {pos_dir}")
            if neg_files:
                neg_dir = _spashiny_ctx.Path(td) / "neg"
                neg_dir.mkdir(parents=True, exist_ok=True)
                for f in neg_files:
                    dst = neg_dir / f["name"]
                    with open(dst, "wb") as out_f:
                        out_f.write(_spashiny_ctx.Path(f["datapath"]).read_bytes())
                _spashiny_ctx.raw_neg_dir.set(str(neg_dir))
                _spashiny_ctx.log(f" Saved negative files to {neg_dir}")
        else:
            csv_files = _spashiny_ctx.input.csv_file() or []
            if csv_files:
                csv_dst = _spashiny_ctx.Path(td) / csv_files[0]["name"]
                with open(csv_dst, "wb") as out_f:
                    out_f.write(_spashiny_ctx.Path(csv_files[0]["datapath"]).read_bytes())
                _spashiny_ctx.csv_file_path.set(str(csv_dst))
                _spashiny_ctx.log(f" CSV file saved: {csv_dst}")

    _spashiny_ctx.save_uploaded_files = save_uploaded_files

    def load_example_sm_data():
        if _spashiny_globals.SPASHINY_WEB_PLATFORM:
            try:
                from cloud.lab_example_inputs import resolve_bound_local_roles

                example_inputs = resolve_bound_local_roles(
                    session_id=_spashiny_ctx._require_cloud_session_id(),
                    analysis_session_id=str(_spashiny_ctx._cloud_analysis_session_id() or ""),
                    action_id="y7-sm-upload-imzml-example",
                    workflow_name="sm_quality_control",
                    required_roles=("sm_pos_imzml", "sm_pos_ibd", "sm_neg_imzml", "sm_neg_ibd"),
                )
                positive_imzml = example_inputs["sm_pos_imzml"]
                positive_ibd = example_inputs["sm_pos_ibd"]
                negative_imzml = example_inputs["sm_neg_imzml"]
                negative_ibd = example_inputs["sm_neg_ibd"]
                required_files = (positive_imzml, positive_ibd, negative_imzml, negative_ibd)
                missing = [str(item) for item in required_files if not item.is_file()]
                if missing:
                    raise FileNotFoundError(
                        "Missing Lab Y7_T SM example file(s): " + ", ".join(missing)
                    )
                if positive_imzml.with_suffix(".ibd") != positive_ibd:
                    raise RuntimeError("Positive Y7_T imzML/ibd pair does not match.")
                if negative_imzml.with_suffix(".ibd") != negative_ibd:
                    raise RuntimeError("Negative Y7_T imzML/ibd pair does not match.")
                _spashiny_ctx.raw_pos_dir.set(str(positive_imzml))
                _spashiny_ctx.raw_neg_dir.set(str(negative_imzml))
                _spashiny_ctx.sm_preprocess_source.set("EXAMPLE")
                _spashiny_ctx.csv_file_path.set(None)
                _spashiny_ctx.adata_final.set(None)
                try:
                    _spashiny_ctx.ui.update_radio_buttons("data_type", selected="ImzML")
                except Exception:
                    pass
                _spashiny_ctx.log("Lab Y7_T SM example selected for this Session.")
                _spashiny_ctx.log(f"  positive imzML: {positive_imzml.name}")
                _spashiny_ctx.log(f"  positive ibd  : {positive_ibd.name}")
                _spashiny_ctx.log(f"  negative imzML: {negative_imzml.name}")
                _spashiny_ctx.log(f"  negative ibd  : {negative_ibd.name}")
                _spashiny_ctx.log("Click Start Processing to run SM processing.")
                _spashiny_ctx.ui.notification_show(
                    "Y7_T SM example is ready. Click Start Processing.", type="message", duration=6
                )
            except Exception as exc:
                _spashiny_ctx.raw_pos_dir.set(None)
                _spashiny_ctx.raw_neg_dir.set(None)
                _spashiny_ctx.sm_preprocess_source.set("")
                _spashiny_ctx.log(f"Failed to load Lab Y7_T SM example: {exc}")
                _spashiny_ctx.ui.notification_show(
                    f"Failed to load Lab Y7_T SM example: {exc}", type="error", duration=10
                )
            return
        try:
            _spashiny_ctx.raw_pos_dir.set(None)
            _spashiny_ctx.raw_neg_dir.set(None)
            _spashiny_ctx.csv_file_path.set(None)
            _spashiny_ctx.adata_final.set(None)
            example_sm_dir = _spashiny_globals.get_example_sm_dir()
            example_sm_dir_display = _spashiny_globals.workspace_relative_path(example_sm_dir)
            if not example_sm_dir.exists():
                msg = f"Example SM folder was not found: {example_sm_dir_display}"
                _spashiny_ctx.log(f"{msg}")
                _spashiny_ctx.ui.notification_show(msg, type="error", duration=6)
                return
            pairs = _spashiny_globals.get_example_sm_imzml_pairs()
            _spashiny_ctx.raw_pos_dir.set(str(example_sm_dir))
            _spashiny_ctx.raw_neg_dir.set(str(example_sm_dir))
            try:
                _spashiny_ctx.ui.update_radio_buttons("data_type", selected="ImzML")
            except Exception:
                pass
            _spashiny_ctx.log(f"Example SM relative path: {example_sm_dir_display}")
            example_sm_dir = example_sm_dir_display
            _spashiny_ctx.log(f" Example SM loaded: {example_sm_dir}")
            _spashiny_ctx.log(f"   positive imzML: {pairs['positive_imzml'].name}")
            _spashiny_ctx.log(f"   positive ibd  : {pairs['positive_ibd'].name}")
            _spashiny_ctx.log(f"   negative imzML: {pairs['negative_imzml'].name}")
            _spashiny_ctx.log(f"   negative ibd  : {pairs['negative_ibd'].name}")
            _spashiny_ctx.log("Click 'Start Processing' to process the example SM data.")
            _spashiny_ctx.ui.notification_show(
                "Example SM data is ready. Click Start Processing.", type="message", duration=5
            )
        except Exception as e:
            _spashiny_ctx.log(f"Failed to load example SM data: {e}")
            _spashiny_ctx.log(_spashiny_ctx.traceback.format_exc())
            _spashiny_ctx.ui.notification_show(
                f"Failed to load example SM data: {e}", type="error", duration=8
            )

    _spashiny_ctx.load_example_sm_data = load_example_sm_data

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.load_example_sm)
    def _on_load_example_sm():
        _spashiny_ctx.load_example_sm_data()

    _spashiny_ctx._on_load_example_sm = _on_load_example_sm

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.process)
    async def process_data():
        from pyimzml.ImzMLParser import ImzMLParser

        _spashiny_ctx.ui.modal_show(
            _spashiny_ctx.ui.modal(
                _spashiny_ctx.ui.div(
                    _spashiny_ctx.ui.h4("Processing Data"),
                    _spashiny_ctx.ui.p("Parsing and merging SM data, please wait..."),
                ),
                easy_close=False,
                footer=None,
            )
        )
        try:
            _spashiny_ctx.adata_final.set(None)
            dtype = _spashiny_ctx.input.data_type()
            _spashiny_ctx.create_temp_dir()
            _spashiny_ctx.log("Starting SM data processing...")
            if (
                _spashiny_globals.SPASHINY_WEB_PLATFORM
                and _spashiny_ctx.sm_preprocess_source.get() == "EXAMPLE"
            ):
                from cloud.lab_example_inputs import resolve_bound_local_roles

                selected = resolve_bound_local_roles(
                    session_id=_spashiny_ctx._require_cloud_session_id(),
                    analysis_session_id=str(_spashiny_ctx._cloud_analysis_session_id() or ""),
                    action_id="y7-sm-upload-imzml-example",
                    workflow_name="sm_quality_control",
                    required_roles=("sm_pos_imzml", "sm_pos_ibd", "sm_neg_imzml", "sm_neg_ibd"),
                )
                _spashiny_ctx.raw_pos_dir.set(str(selected["sm_pos_imzml"]))
                _spashiny_ctx.raw_neg_dir.set(str(selected["sm_neg_imzml"]))

            def prepare_sm_for_h5ad(adata):
                changes = _spashiny_globals.sanitize_h5ad_keys(adata)
                if changes:
                    preview = ", ".join(changes[:5])
                    suffix = " ..." if len(changes) > 5 else ""
                    _spashiny_ctx.log(
                        f"Normalized h5ad metadata keys before saving: {preview}{suffix}"
                    )
                return adata

            if dtype == "CSV":
                csv_path = _spashiny_ctx.csv_file_path.get()
                if not csv_path:
                    _spashiny_ctx.log("No CSV file detected.")
                    return
                try:
                    adata_SM = await _spashiny_globals.asyncio.to_thread(
                        _spashiny_globals.smt.pp.read_sm_csv_as_anndata, csv_path
                    )
                    prepare_sm_for_h5ad(adata_SM)
                    _spashiny_ctx.adata_final.set(adata_SM)
                    _spashiny_ctx.log(f"CSV data loaded successfully, shape: {adata_SM.shape}")
                except Exception as e:
                    _spashiny_ctx.log(f"Failed to read CSV: {e}")
                return
            pos_dir = _spashiny_ctx.raw_pos_dir.get()
            neg_dir = _spashiny_ctx.raw_neg_dir.get()
            if (
                not pos_dir
                and (not neg_dir)
                and _spashiny_globals.SPASHINY_LAB_PROFILE
                and (_spashiny_ctx.sm_preprocess_source.get() == "EXAMPLE")
            ):
                action_id = _spashiny_ctx._latest_example_action_for("y7-sm-upload-imzml-example")
                if action_id:
                    try:
                        from cloud.lab_example_inputs import resolve_bound_local_roles

                        example_inputs = resolve_bound_local_roles(
                            session_id=_spashiny_ctx._require_cloud_session_id(),
                            analysis_session_id=str(
                                _spashiny_ctx._cloud_analysis_session_id() or ""
                            ),
                            action_id=action_id,
                            workflow_name="sm_quality_control",
                            required_roles=(
                                "sm_pos_imzml",
                                "sm_pos_ibd",
                                "sm_neg_imzml",
                                "sm_neg_ibd",
                            ),
                        )
                        if (
                            example_inputs["sm_pos_imzml"].with_suffix(".ibd")
                            != example_inputs["sm_pos_ibd"]
                        ):
                            raise RuntimeError("Positive imzML and ibd files do not match.")
                        if (
                            example_inputs["sm_neg_imzml"].with_suffix(".ibd")
                            != example_inputs["sm_neg_ibd"]
                        ):
                            raise RuntimeError("Negative imzML and ibd files do not match.")
                        pos_dir = str(example_inputs["sm_pos_imzml"])
                        neg_dir = str(example_inputs["sm_neg_imzml"])
                        _spashiny_ctx.log(
                            "Verified the four Y7_T SM example files bound to the current Session."
                        )
                    except Exception as exc:
                        _spashiny_ctx.log(f"Failed to resolve the bound Y7_T SM example: {exc}")
                        _spashiny_ctx.ui.notification_show(
                            f"Failed to resolve the bound Y7_T SM example: {exc}",
                            type="error",
                            duration=10,
                        )
                        return
            if not pos_dir and (not neg_dir):
                _spashiny_ctx.log(
                    "No uploaded positive/negative ion files or active Y7_T SM example binding were detected."
                )
                return
            adata_pos_obj, adata_neg_obj = (None, None)
            sample_name = "sample"

            def _resolve_imzml_pair(source_dir, polarity):
                source = _spashiny_ctx.Path(source_dir)
                explicit_name = "Y7_T_pos.imzML" if polarity == "positive" else "Y7_T_neg.imzML"
                if source.is_file():
                    imzml_file = source
                else:
                    explicit = source / explicit_name
                    if explicit.exists():
                        imzml_file = explicit
                    else:
                        candidates = sorted(source.glob("*.imzML"))
                        if not candidates:
                            raise FileNotFoundError(f"No {polarity} .imzML file found in {source}")
                        if len(candidates) > 1:
                            raise ValueError(
                                f"Multiple .imzML files found in {source}; please provide a single {polarity} pair."
                            )
                        imzml_file = candidates[0]
                if imzml_file.suffix.lower() != ".imzml":
                    raise ValueError(f"{polarity} input is not an .imzML file: {imzml_file}")
                ibd_file = imzml_file.with_suffix(".ibd")
                if not ibd_file.exists():
                    raise FileNotFoundError(
                        f"Missing {polarity} .ibd companion for {imzml_file.name}"
                    )
                return (imzml_file, ibd_file)

            def _sample_name_from_imzml(imzml_file):
                stem = _spashiny_ctx.Path(imzml_file).stem
                for suffix in ("_pos", "_neg", "-pos", "-neg"):
                    if stem.lower().endswith(suffix):
                        stem = stem[: -len(suffix)]
                        break
                return stem.split("-")[0] or "sample"

            if pos_dir:
                try:
                    imzml_file, ibd_file = _resolve_imzml_pair(pos_dir, "positive")
                    sample_name = _sample_name_from_imzml(imzml_file)
                    _spashiny_ctx.log(f"Positive imzML: {imzml_file.name}")
                    _spashiny_ctx.log(f"Positive ibd: {ibd_file.name}")
                    p = await _spashiny_globals.asyncio.to_thread(ImzMLParser, str(imzml_file))
                    mz_reference = await _spashiny_globals.asyncio.to_thread(
                        _spashiny_globals.smt.pp.get_mz_reference, p, ppm_tolerance=5
                    )
                    adata_SM_pos = await _spashiny_globals.asyncio.to_thread(
                        _spashiny_globals.smt.pp.read_sm_imzml_as_anndata, p, mz_reference
                    )
                    adata_pos_obj = adata_SM_pos
                    _spashiny_ctx.log(
                        f"Positive AnnData generated successfully, shape: {adata_SM_pos.shape}"
                    )
                except Exception as e:
                    _spashiny_ctx.log(f"Error processing positive ion data: {e}")
                    sample_name = "sample"
            if neg_dir:
                try:
                    imzml_file, ibd_file = _resolve_imzml_pair(neg_dir, "negative")
                    _spashiny_ctx.log(f"Negative imzML: {imzml_file.name}")
                    _spashiny_ctx.log(f"Negative ibd: {ibd_file.name}")
                    p = await _spashiny_globals.asyncio.to_thread(ImzMLParser, str(imzml_file))
                    mz_reference = await _spashiny_globals.asyncio.to_thread(
                        _spashiny_globals.smt.pp.get_mz_reference, p, ppm_tolerance=5
                    )
                    adata_SM_neg = await _spashiny_globals.asyncio.to_thread(
                        _spashiny_globals.smt.pp.read_sm_imzml_as_anndata, p, mz_reference
                    )
                    adata_neg_obj = adata_SM_neg
                    _spashiny_ctx.log(
                        f"Negative AnnData generated successfully, shape: {adata_SM_neg.shape}"
                    )
                except Exception as e:
                    _spashiny_ctx.log(f"Error processing negative ion data: {e}")
            if pos_dir and adata_pos_obj is None:
                raise RuntimeError(
                    "The selected POS input failed to load; no partial single-mode result was accepted."
                )
            if neg_dir and adata_neg_obj is None:
                raise RuntimeError(
                    "The selected NEG input failed to load; no partial single-mode result was accepted."
                )
            if adata_pos_obj is not None and adata_neg_obj is not None:
                try:
                    from cloud.portable_inputs import align_sm_pos_neg_inputs

                    matched_pos, matched_neg = await _spashiny_globals.asyncio.to_thread(
                        align_sm_pos_neg_inputs, adata_pos_obj, adata_neg_obj
                    )
                    _spashiny_ctx.log(
                        f"Exact POS/NEG matching: {matched_pos.n_obs} shared pixels; POS {adata_pos_obj.n_obs}, NEG {adata_neg_obj.n_obs} before matching. No interpolation or coordinate rounding."
                    )
                    adata_SM = await _spashiny_globals.asyncio.to_thread(
                        _spashiny_globals.smt.pp.merge_sm_pos_neg, matched_pos, matched_neg
                    )
                    adata_SM.var_names_make_unique()
                    prepare_sm_for_h5ad(adata_SM)
                    _spashiny_ctx.adata_final.set(adata_SM)
                    out_file = _spashiny_ctx._preprocessing_export_path(
                        f"{sample_name}_adata_SM_raw.h5ad"
                    )
                    await _spashiny_globals.asyncio.to_thread(adata_SM.write_h5ad, out_file)
                    _spashiny_ctx.log(
                        f"Positive and negative ion data merged successfully and saved as {out_file}"
                    )
                except Exception as e:
                    _spashiny_ctx.log(f"Error during merge or saving h5ad: {e}")
            elif adata_pos_obj is not None or adata_neg_obj is not None:
                try:
                    adata_SM = adata_pos_obj if adata_pos_obj is not None else adata_neg_obj
                    prepare_sm_for_h5ad(adata_SM)
                    _spashiny_ctx.adata_final.set(adata_SM)
                    out_file = _spashiny_ctx._preprocessing_export_path(
                        f"{sample_name}_adata_SM_raw.h5ad"
                    )
                    await _spashiny_globals.asyncio.to_thread(adata_SM.write_h5ad, out_file)
                    _spashiny_ctx.log(
                        f"Single imzML data processed successfully and saved as {out_file}"
                    )
                except Exception as e:
                    _spashiny_ctx.log(f"Error while saving single imzML AnnData: {e}")
            else:
                _spashiny_ctx.log(
                    "Data processing completed, but no mergeable AnnData object was generated."
                )
        except Exception as e:
            _spashiny_ctx.log(f"SM processing failed: {e}")
            _spashiny_ctx.log(_spashiny_ctx.traceback.format_exc())
            _spashiny_ctx.ui.notification_show(
                f"SM processing failed: {e}", type="error", duration=8
            )
        finally:
            _spashiny_ctx.ui.modal_remove()
            _spashiny_globals.release_unused_memory()

    _spashiny_ctx.process_data = process_data


_STEPS = (_install_0,)


def server(_spashiny_ctx, step=0):
    return _STEPS[step](_spashiny_ctx)
