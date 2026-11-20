import argparse
import gc
import hashlib
import inspect
import json
import logging
import os
import random
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path


# SPATIALMETA_PARITY F04: presets are NOT model defaults. Historical payloads
# remain readable, but cannot override the installed package's hyperparameters.
# These options affect input/output or hardware selection, not model training.
from cloud.spatialmeta_tutorial_policy import (
    POLICY, URLS, IO_OPTIONS, profile_key, model_kwargs, fit_kwargs,
    tutorial_model_defaults, tutorial_training_defaults, postprocess_kwargs,
)


def resolve_runtime_config(mode="tutorial", user_params=None):
    supplied = dict(user_params or {})
    kind, scope = supplied.get("model_type", "stsm"), supplied.get("sample_policy", "single")
    key = profile_key(kind, scope)
    cfg = {k:v for k,v in supplied.items() if k in IO_OPTIONS and v is not None}
    cfg.update(model_kwargs(kind, scope))
    cfg.update(fit_kwargs(kind, scope))
    cfg.update(model_type=kind, sample_policy=scope, parameter_policy=POLICY,
               tutorial_profile=key, tutorial_url=URLS[key], save_model_state=True,
               ignored_legacy_parameter_names=sorted(set(supplied)-IO_OPTIONS-{"model_type","sample_policy","tutorial_profile"}))
    return cfg


def signature_defaults(method):
    return {name: value.default for name, value in inspect.signature(method).parameters.items()
            if value.default is not inspect.Parameter.empty}


def parse_custom_params(raw):
    if raw is None or str(raw).strip() == "":
        return {}

    raw = str(raw)
    stripped = raw.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return json.loads(stripped)

    possible_path = Path(raw)
    try:
        if possible_path.exists():
            return json.loads(possible_path.read_text(encoding="utf-8"))
    except OSError:
        pass

    return json.loads(raw)


# F04/F14: removed non-native preset/feature/seed implementation.


def json_default(value):
    try:
        import numpy as np

        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
    except Exception:
        pass
    if hasattr(value, "tolist"):
        return value.tolist()
    return str(value)


def setup_logging(outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    log_path = outdir / "spatialmeta_train.log"

    logger = logging.getLogger("spatialmeta_train")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger, log_path


def set_cpu_thread_env(cpu_threads):
    cpu_threads = max(1, int(cpu_threads or 1))
    for name in (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        os.environ[name] = str(cpu_threads)
    return cpu_threads


# F04/F14: removed non-native preset/feature/seed implementation.


def configure_torch_runtime(torch, cpu_threads, logger, requested_device="auto"):
    requested_device = str(requested_device or "auto")
    gpu_required = str(os.environ.get("SPASHINY_GPU_REQUIRED", "")).strip().lower() in {"1", "true", "yes", "on"}
    allow_cpu_fallback = str(os.environ.get("SPASHINY_ALLOW_CPU_FALLBACK", "1")).strip().lower() not in {"0", "false", "no", "off"}
    cuda_available = torch.cuda.is_available()
    if gpu_required and not cuda_available:
        raise RuntimeError("CUDA is required for this SpaShiny Lab GPU job.")
    auto_device = "cuda" if torch.cuda.is_available() else "cpu"
    if requested_device == "cpu":
        device = "cpu"
    elif requested_device.startswith("cuda") and cuda_available:
        device = requested_device
    else:
        if requested_device.startswith("cuda") and not allow_cpu_fallback:
            raise RuntimeError(f"Requested CUDA device is unavailable: {requested_device}")
        device = auto_device
    if gpu_required and not str(device).startswith("cuda"):
        raise RuntimeError("SpaShiny Lab GPU jobs cannot fall back to CPU.")
    is_cuda = str(device).startswith("cuda")

    if not is_cuda:
        torch.set_num_threads(cpu_threads)
        try:
            torch.set_num_interop_threads(1)
        except RuntimeError:
            pass
        logger.info("CPU mode: torch threads=%s, interop_threads=1", cpu_threads)
    else:
        # F14: leave precision, AMP and cuDNN/determinism at upstream defaults.
        logger.info("CUDA mode enabled; no platform precision overrides")

    return device


def normalize_path(path):
    return str(Path(path).expanduser().resolve())


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# F04/F14: removed non-native preset/feature/seed implementation.


# F04/F14: removed non-native preset/feature/seed implementation.

def clean_loss_dict(loss_record):
    clean = {}
    for key, values in (loss_record or {}).items():
        try:
            import numpy as np
            import torch

            if torch.is_tensor(values):
                clean[key] = [float(x) for x in values.detach().cpu().numpy().reshape(-1)]
            elif isinstance(values, np.ndarray):
                clean[key] = [float(x) for x in values.reshape(-1)]
            elif isinstance(values, (list, tuple)):
                clean[key] = [float(x) for x in values]
            else:
                clean[key] = [float(values)]
        except Exception:
            clean[key] = values
    return clean


def save_reconstruction_diagnostics(model, adata, cfg, n_per_batch, outdir, logger):
    import numpy as np
    import pandas as pd

    max_elements = int(cfg.get("max_reconstruction_diagnostics_elements", 20000000) or 0)
    sample_points = int(cfg.get("reconstruction_sample_points", 5000) or 5000)
    matrix_elements = int(adata.n_obs) * int(adata.n_vars)

    diag = {
        "status": "not_run",
        "matrix_elements": matrix_elements,
        "max_elements": max_elements,
    }
    if max_elements <= 0:
        diag.update({"status": "skipped", "message": "Reconstruction diagnostics are disabled."})
        return diag
    if matrix_elements > max_elements:
        message = (
            f"Reconstruction diagnostics skipped because matrix has {matrix_elements:,} elements "
            f"above the configured limit {max_elements:,}."
        )
        logger.info(message)
        (outdir / "reconstruction_diagnostics_skipped.txt").write_text(message + "\n", encoding="utf-8")
        diag.update({"status": "skipped", "message": message})
        return diag

    reconstruction = None
    X0 = None
    try:
        reconstruction = model.get_normalized_expression(n_per_batch=n_per_batch, show_progress=False)
        reconstruction = np.asarray(reconstruction, dtype=np.float32)
        source = adata.layers["normalized_for_cvae"] if "normalized_for_cvae" in adata.layers else adata.X
        X0 = source.toarray() if hasattr(source, "toarray") else np.asarray(source)
        X0 = np.asarray(X0, dtype=np.float32)

        n_rows = min(X0.shape[0], reconstruction.shape[0])
        n_cols = min(X0.shape[1], reconstruction.shape[1])
        if n_rows <= 0 or n_cols <= 0:
            raise ValueError("Empty reconstruction/original matrix.")
        X0 = X0[:n_rows, :n_cols]
        reconstruction = reconstruction[:n_rows, :n_cols]

        flat_n = int(n_rows * n_cols)
        rng = np.random.default_rng(int(cfg.get("seed", 42) or 42))
        sample_n = min(sample_points, flat_n)
        flat_idx = rng.choice(flat_n, size=sample_n, replace=False)
        scatter_csv = outdir / "reconstruction_scatter_sample.csv"
        pd.DataFrame(
            {
                "original": X0.reshape(-1)[flat_idx],
                "reconstructed": reconstruction.reshape(-1)[flat_idx],
            }
        ).to_csv(scatter_csv, index=False)

        mse = np.mean((X0 - reconstruction) ** 2, axis=1)
        mse_csv = outdir / "reconstruction_mse_by_obs.csv"
        pd.DataFrame(
            {
                "obs_name": adata.obs_names[:n_rows].astype(str),
                "mse": mse.astype(np.float32),
            }
        ).to_csv(mse_csv, index=False)

        diag.update(
            {
                "status": "ok",
                "message": "Reconstruction diagnostics saved.",
                "scatter_csv": str(scatter_csv),
                "mse_csv": str(mse_csv),
                "sample_points": sample_n,
                "shape": [n_rows, n_cols],
            }
        )
        logger.info("Reconstruction diagnostics saved: %s, %s", scatter_csv, mse_csv)
        return diag
    except Exception as exc:
        logger.exception("Reconstruction diagnostics failed")
        diag.update({"status": "failed", "message": str(exc)})
        return diag
    finally:
        try:
            del reconstruction
        except Exception:
            pass
        try:
            del X0
        except Exception:
            pass
        gc.collect()


def maybe_call_normalize(smt, sc, adata, cfg, logger):
    input_layer = cfg.get("input_layer")
    if input_layer:
        if input_layer not in adata.layers:
            raise ValueError(f"Requested input layer is missing: {input_layer}")
        adata.X = adata.layers[input_layer].copy()
        logger.info("Using adata.layers[%r] as model input", input_layer)
    elif "counts" in adata.layers and bool(cfg.get("use_counts_layer", True)):
        adata.X = adata.layers["counts"]
        logger.info("Using adata.layers['counts'] as model input")

    if bool(cfg.get("normalize_input", True)):
        try:
            import pandas as pd

            if not hasattr(pd.Series, "nonzero"):
                pd.Series.nonzero = lambda self: self.to_numpy().nonzero()
                logger.info("Applied pandas Series.nonzero compatibility shim for SpatialMETA normalization")
        except Exception as exc:
            logger.warning("Could not apply pandas Series.nonzero compatibility shim: %s", exc)

        if cfg["model_type"] == "stsm":
            # Both STSM tutorial training stages restore counts, normalize only
            # SM to 1e3 and leave the integer ST counts for the ZINB likelihood.
            logger.info("Tutorial training normalization: SM=1000; ST counts unchanged")
            smt.pp.normalize_total_joint_adata_sm_st(adata, target_sum_SM=1e3, target_sum_ST=None)
        else:
            logger.info("Tutorial SM normalization: target_sum=10000; no log1p")
            sc.pp.normalize_total(adata, target_sum=1e4)

    return adata


# F04/F14: removed non-native preset/feature/seed implementation.


def instantiate_model(smt, torch, adata, cfg, device, logger):
    model_type, sample_policy = cfg["model_type"], cfg["sample_policy"]
    if sample_policy == "multi" and ("sample" not in adata.obs or adata.obs["sample"].isna().any() or adata.obs["sample"].nunique() < 2):
        raise ValueError("The multi-sample tutorial requires the actual sample column with at least two samples")
    cls = smt.model.ConditionalVAESM if model_type == "sm" else smt.model.ConditionalVAESTSM
    kwargs = model_kwargs(model_type, sample_policy)
    logger.info("Tutorial constructor kwargs: %s", kwargs)
    model = cls(adata=adata, device=device, **kwargs)
    # Record inherited installed defaults as well as explicit notebook arguments.
    resolved_model = tutorial_model_defaults(smt, model_type, sample_policy)
    resolved_fit = tutorial_training_defaults(smt, model_type, sample_policy)
    cfg["resolved_model_defaults"] = json.loads(json.dumps(resolved_model, default=str))
    cfg["resolved_fit_defaults"] = json.loads(json.dumps(resolved_fit, default=str))
    cfg["n_per_batch"] = int(resolved_fit.get("n_per_batch", 128))
    return model


def fit_model(model, cfg, device, use_amp, logger):
    kwargs = fit_kwargs(cfg["model_type"], cfg["sample_policy"])
    logger.info("Tutorial fit kwargs: %s", json.dumps(kwargs))
    # No retry with altered kwargs after a partially executed training operation.
    return model.fit(**kwargs)


def run_training(args):
    outdir = Path(args.outdir).resolve()
    logger, log_path = setup_logging(outdir)
    start_time = datetime.now()

    user_params = parse_custom_params(args.custom_params_json)
    cfg = resolve_runtime_config(args.mode or "tutorial", user_params)
    cpu_threads = set_cpu_thread_env(cfg.get("cpu_threads", 2))

    summary = {
        "success": False,
        "input_h5ad": normalize_path(args.input_h5ad),
        "input_sha256": sha256_file(args.input_h5ad),
        "outdir": str(outdir),
        "mode": "tutorial",
        "resolved_config": cfg,
        "log_file": str(log_path),
        "start_time": start_time.isoformat(timespec="seconds"),
    }

    logger.info("=== SpatialMETA training started ===")
    logger.info("Input: %s", summary["input_h5ad"])
    logger.info("Output: %s", outdir)
    logger.info("Mode: %s", summary["mode"])
    logger.info("Resolved config: %s", json.dumps(cfg, ensure_ascii=False, indent=2, default=json_default))
    logger.info("Python: %s", sys.executable)

    model = None
    adata = None
    loss_record = None
    latent = None

    try:
        import numpy as np
        import pandas as pd
        import scanpy as sc
        import torch
        import spatialmeta as smt

        device = configure_torch_runtime(torch, cpu_threads, logger, cfg.get("requested_device", "auto"))
        # F14: the fit method owns its random_seed default. Do not force seed42
        # or deterministic/AMP modes before the native constructor.
        use_amp = False

        summary.update(
            {
                "device": device,
                "cpu_threads": cpu_threads,
                "cuda_available": bool(torch.cuda.is_available()),
                "use_amp": bool(use_amp),
                "torch_version": getattr(torch, "__version__", "unknown"),
                "spatialmeta_path": getattr(smt, "__file__", "unknown"),
            }
        )

        logger.info("Device: %s", device)
        logger.info("CUDA available: %s", torch.cuda.is_available())
        logger.info("AMP enabled: %s", use_amp)

        adata = sc.read_h5ad(summary["input_h5ad"])
        logger.info("Loaded AnnData shape=%s", adata.shape)

        adata.var_names_make_unique()
        adata.obs_names_make_unique()
        # F04: first-N selection was not spatial-variable selection. Preserve
        # every supplied feature and observation, or fail on invalid input.
        if not adata.n_obs or not adata.n_vars:
            raise ValueError("SpatialMETA input has no observations or features.")
        values = adata.X.data if hasattr(adata.X, "tocsr") else np.asarray(adata.X)
        if not np.isfinite(values).all():
            raise ValueError("SpatialMETA input contains NaN or infinite intensities.")
        filter_provenance = {
            "input_observations": int(adata.n_obs),
            "final_model_observations": int(adata.n_obs),
            "input_features": int(adata.n_vars),
            "feature_cap_applied": False,
            "platform_observation_filter_applied": False,
        }
        adata.uns["spashiny_joint_input_filter"] = filter_provenance
        summary["filter_provenance"] = filter_provenance
        logger.info("Preserved complete model input shape=%s", adata.shape)

        adata = maybe_call_normalize(smt, sc, adata, cfg, logger)
        if cfg["model_type"] == "stsm":
            if "type" not in adata.var or not {"ST", "SM"}.issubset(set(adata.var["type"].astype(str))):
                raise ValueError("Joint integration requires exact ST/SM feature type metadata.")
            st = adata.X[:, adata.var["type"].astype(str).eq("ST").to_numpy()]
            st_values = st.data if hasattr(st, "tocsr") else np.asarray(st)
            if (st_values < 0).any() or not np.equal(st_values, np.floor(st_values)).all():
                raise ValueError("Native SpatialMETA ZINB requires non-negative ST raw counts, not log/normalized expression. Supply the original counts layer; no values were rounded or replaced.")
            st_totals = np.asarray(st.sum(axis=1)).reshape(-1)
            if (st_totals <= 0).any():
                raise ValueError("Native joint integration cannot use observations with zero ST counts. Review QC/matching first; observations were not silently deleted.")
        # Feature Explorer follows the original SpatialMETA contract and renders
        # from layers["normalized"], never from a silent fallback to adata.X.
        if "normalized" not in adata.layers:
            normalized = adata.X.copy() if hasattr(adata.X, "copy") else np.array(adata.X, copy=True)
            adata.layers["normalized"] = normalized
            logger.info("Persisted normalized layer for SpatialMETA Feature Explorer")

        model = instantiate_model(smt, torch, adata, cfg, device, logger)
        cfg["native_constructor_defaults"] = next(
            (signature_defaults(base.__init__) for base in type(model).__mro__
             if "adata" in inspect.signature(base.__init__).parameters), {})
        cfg["native_fit_defaults"] = signature_defaults(model.fit)
        if hasattr(model, "fit_core"):
            cfg["native_fit_core_defaults"] = signature_defaults(model.fit_core)
        cfg["effective_workflow_mode"] = cfg["sample_policy"] if cfg["model_type"] == "stsm" else "sm"
        # Observed metadata for existing views, NEVER forwarded to fit().
        cfg.update(n_latent=int(model.n_latent), hidden_stacks=list(model.hidden_stacks),
                   batch_keys=model.batch_keys,
                   batch_embedding=cfg.get("resolved_model_defaults",{}).get("batch_embedding"),
                   max_epoch=fit_kwargs(cfg["model_type"], cfg["sample_policy"])["max_epoch"],
                   n_per_batch=cfg["native_fit_defaults"]["n_per_batch"],
                   lr=fit_kwargs(cfg["model_type"], cfg["sample_policy"])["lr"])
        # Serialize callables/types in defaults once; AnnData uns must be HDF5-safe.
        cfg = json.loads(json.dumps(cfg, default=json_default))
        logger.info("Model initialized")

        loss_record = fit_model(model, cfg, device, use_amp, logger)
        loss_record = clean_loss_dict(loss_record)
        # ConditionalVAESM may return one high-dimensional gate-logit vector per
        # epoch even when callers explicitly opted out of storing it.  Keep it
        # only on explicit request so routine worker results remain portable.
        if not bool(cfg.get("save_gate_logits", False)):
            removed_gate_logits = loss_record.pop("epoch_sm_gate_logits_list", None)
            if removed_gate_logits is not None:
                logger.info("Skipped epoch_sm_gate_logits_list because save_gate_logits=false")
        loss_path = outdir / "loss_record.json"
        loss_path.write_text(
            json.dumps(loss_record, ensure_ascii=False, indent=2, default=json_default),
            encoding="utf-8",
        )
        logger.info("Loss record saved: %s", loss_path)

        n_per_batch = int(signature_defaults(model.get_latent_embedding)["n_per_batch"])
        latent_raw = model.get_latent_embedding()
        # SpatialMETA 0.0.3.0 returns one array per batch for ConditionalVAESM,
        # unlike its joint model.  Flatten batches before attaching to AnnData.
        if isinstance(latent_raw, (list, tuple)):
            latent = np.concatenate([np.asarray(item, dtype=np.float32) for item in latent_raw], axis=0)
        else:
            latent = np.asarray(latent_raw, dtype=np.float32)
            if latent.ndim == 3:
                latent = latent.reshape((-1, latent.shape[-1]))
        if latent.ndim != 2 or latent.shape[0] != adata.n_obs:
            raise ValueError(
                f"SpatialMETA latent embedding shape {tuple(latent.shape)} does not match "
                f"AnnData observations {adata.n_obs}."
            )
        latent_path = outdir / "latent.npy"
        np.save(latent_path, latent)
        adata.obsm["X_emb"] = latent
        logger.info("Latent embedding saved: %s shape=%s", latent_path, latent.shape)

        contribution_csv = None
        if hasattr(model, "get_modality_contribution") and bool(cfg.get("save_modality_contribution", True)):
            contribution = model.get_modality_contribution()
            contribution = contribution.detach().cpu().numpy() if torch.is_tensor(contribution) else np.asarray(contribution)
            contribution = np.asarray(contribution, dtype=np.float32).reshape(-1)
            if contribution.shape[0] != adata.n_obs or not np.isfinite(contribution).all():
                raise ValueError("Native modality contribution is invalid; no substitute values were generated.")
            if contribution.shape[0] == adata.n_obs:
                adata.obs["contribution_st"] = contribution
                adata.obs["contribution_sm"] = np.asarray(1.0 - contribution, dtype=np.float32)
                contribution_csv = outdir / "modality_contribution.csv"
                pd.DataFrame(
                    {
                        "obs_name": adata.obs_names.astype(str),
                        "contribution_st": contribution,
                        "contribution_sm": np.asarray(1.0 - contribution, dtype=np.float32),
                    }
                ).to_csv(contribution_csv, index=False)
                logger.info("Modality contribution saved: %s", contribution_csv)

        reconstruction_path = None
        if bool(cfg.get("save_reconstruction", False)):
            reconstruction = model.get_normalized_expression(n_per_batch=n_per_batch, show_progress=False)
            reconstruction = np.asarray(reconstruction, dtype=np.float32)
            reconstruction_path = outdir / "normalized_expression.npy"
            np.save(reconstruction_path, reconstruction)
            if bool(cfg.get("store_reconstruction_layer", False)):
                adata.layers["reconstruction"] = reconstruction
            logger.info("Normalized expression saved: %s", reconstruction_path)

        reconstruction_diagnostics = None
        if bool(cfg.get("save_reconstruction_diagnostics", False)):
            reconstruction_diagnostics = save_reconstruction_diagnostics(
                model,
                adata,
                cfg,
                n_per_batch,
                outdir,
                logger,
            )

        if bool(cfg.get("run_postprocess", True)):
            # F11/F12: Scanpy's real defaults; failures must fail this job rather
            # than invent a single cluster and report successful integration.
            logger.info("SPASHINY_PROGRESS: POSTPROCESS_NEIGHBORS")
            sc.pp.neighbors(adata, use_rep="X_emb", **postprocess_kwargs(cfg["model_type"], cfg["sample_policy"])["neighbors"])
            logger.info("SPASHINY_PROGRESS: POSTPROCESS_UMAP")
            sc.tl.umap(adata, **postprocess_kwargs(cfg["model_type"], cfg["sample_policy"])["umap"])
            cluster_key = f"VAE_clusters_latent{latent.shape[1]}"
            logger.info("SPASHINY_PROGRESS: POSTPROCESS_LEIDEN")
            sc.tl.leiden(adata, key_added=cluster_key, **postprocess_kwargs(cfg["model_type"], cfg["sample_policy"])["leiden"])
            adata.obs["VAE_clusters"] = adata.obs[cluster_key].astype(str)
            summary["cluster_key"] = cluster_key
            logger.info("Postprocess finished: %s", cluster_key)

        result_h5ad = outdir / "spatialmeta_result.h5ad"
        logger.info("SPASHINY_PROGRESS: SAVING_RESULT")
        adata.uns["spatialmeta_train_config"] = cfg
        adata.uns["spashiny_reproducibility"] = {
            "parameter_policy": cfg["parameter_policy"],
            "native_fit_random_seed": int(cfg.get("native_fit_core_defaults", cfg["native_fit_defaults"]).get("random_seed", 12)),
            **filter_provenance,
        }
        adata.uns["spatialmeta_train_summary"] = {
            "mode": summary["mode"],
            "device": summary.get("device"),
            "use_amp": summary.get("use_amp"),
            "start_time": summary["start_time"],
        }
        adata.write_h5ad(result_h5ad)
        logger.info("Result AnnData saved: %s", result_h5ad)

        model_state_path = None
        if bool(cfg.get("save_model_state", cfg.get("save_model_copy", False))):
            model_state_path = outdir / "model_state_dict.pt"
            torch.save(model.state_dict(), model_state_path)
            logger.info("Model state_dict saved: %s", model_state_path)

        done_path = outdir / "done.txt"
        done_path.write_text("OK\n", encoding="utf-8")

        summary.update(
            {
                "success": True,
                "message": "OK",
                "result_h5ad": str(result_h5ad),
                "loss_json": str(loss_path),
                "latent_npy": str(latent_path),
                "model_state_dict": str(model_state_path) if model_state_path else None,
                "reconstruction_npy": str(reconstruction_path) if reconstruction_path else None,
                "reconstruction_diagnostics": reconstruction_diagnostics,
                "modality_contribution_csv": str(contribution_csv) if contribution_csv else None,
                "done_txt": str(done_path),
                "shape": list(adata.shape),
            }
        )
        return 0, summary

    except Exception as exc:
        tb = traceback.format_exc()
        logger.error("SpatialMETA training failed: %s", exc)
        logger.error(tb)

        error_path = outdir / "error.txt"
        error_path.write_text(f"{type(exc).__name__}: {exc}\n\n{tb}", encoding="utf-8")
        summary.update(
            {
                "success": False,
                "message": f"{type(exc).__name__}: {exc}",
                "traceback": tb,
                "error_txt": str(error_path),
            }
        )
        return 1, summary

    finally:
        try:
            del model
        except Exception:
            pass
        try:
            del adata
        except Exception:
            pass
        try:
            del loss_record
        except Exception:
            pass
        if "latent" in locals():
            try:
                del latent
            except Exception:
                pass
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        summary["end_time"] = datetime.now().isoformat(timespec="seconds")
        summary["elapsed_seconds"] = round(time.time() - start_time.timestamp(), 3)
        (outdir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=json_default),
            encoding="utf-8",
        )
        logger.info("Summary saved: %s", outdir / "summary.json")
        logger.info("=== SpatialMETA training ended ===")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_h5ad", required=True)
    parser.add_argument("--outdir", required=True)
    # Accept old queued payload labels for compatibility, never their presets.
    parser.add_argument("--mode", default="tutorial")
    parser.add_argument("--custom_params_json", default="{}")
    args = parser.parse_args()

    rc, _summary = run_training(args)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
