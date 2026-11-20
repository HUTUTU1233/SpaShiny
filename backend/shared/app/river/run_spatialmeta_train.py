import argparse
import gc
import hashlib
import json
import logging
import os
import random
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path


RESOURCE_PRESETS = {
    "low_memory": {
        "max_epoch": 8,
        "n_per_batch": 8,
        "hidden_stacks": [64],
        "n_latent": 6,
        "cpu_threads": 2,
        "n_top_genes": 800,
        "n_top_metabolites": 200,
        "save_gate_logits": False,
        "save_model_copy": False,
        "use_amp": False,
    },
    "balanced": {
        "max_epoch": 20,
        "n_per_batch": 16,
        "hidden_stacks": [128],
        "n_latent": 8,
        "cpu_threads": 4,
        "n_top_genes": 1500,
        "n_top_metabolites": 400,
        "save_gate_logits": False,
        "save_model_copy": False,
        "use_amp": True,
    },
    "performance": {
        "max_epoch": 35,
        "n_per_batch": 32,
        "hidden_stacks": [128, 64],
        "n_latent": 10,
        "cpu_threads": 6,
        "n_top_genes": 2000,
        "n_top_metabolites": 800,
        "save_gate_logits": False,
        "save_model_copy": False,
        "use_amp": True,
    },
    "original_compatible": {
        "max_epoch": 35,
        "n_per_batch": 128,
        "hidden_stacks": [128],
        "n_latent": 10,
        "cpu_threads": 4,
        "n_top_genes": None,
        "n_top_metabolites": None,
        "save_gate_logits": False,
        "save_model_copy": False,
        "use_amp": True,
        "batch_keys": "sample",
        "batch_embedding": "embedding",
        "reconstruction_method_sm": "g",
        "reconstruction_method_st": "zinb",
    },
}


def resolve_runtime_config(mode="low_memory", user_params=None):
    if user_params is None:
        user_params = {}

    preset = RESOURCE_PRESETS.get(mode, RESOURCE_PRESETS["low_memory"]).copy()
    preset.setdefault("seed", 42)

    for key, value in user_params.items():
        if value is not None and value != "":
            preset[key] = value

    return preset


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


def parse_hidden_stacks(value):
    if value is None or value == "":
        return None
    if isinstance(value, (list, tuple)):
        return [int(x) for x in value if str(x).strip() != ""]
    if isinstance(value, str):
        return [int(x.strip()) for x in value.split(",") if x.strip()]
    return [int(value)]


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


def set_reproducible_seed(torch, seed, logger):
    """Seed the actual independent SpatialMETA worker process."""
    import numpy as np

    seed = int(seed if seed is not None else 42)
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True
    try:
        torch.use_deterministic_algorithms(True, warn_only=True)
    except Exception:
        pass
    logger.info("Reproducibility seed=%s; deterministic CUDA mode requested", seed)
    return seed


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
        torch.backends.cudnn.benchmark = True
        try:
            torch.set_float32_matmul_precision("high")
        except Exception:
            pass
        logger.info("CUDA mode enabled")

    return device


def normalize_path(path):
    return str(Path(path).expanduser().resolve())


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def select_features_by_type(adata, n_top_genes=None, n_top_metabolites=None, logger=None):
    n_top_genes = int(n_top_genes or 0)
    n_top_metabolites = int(n_top_metabolites or 0)
    if n_top_genes <= 0 and n_top_metabolites <= 0:
        return adata

    var = adata.var
    if "type" not in var.columns:
        limit = n_top_genes + n_top_metabolites
        if limit > 0 and adata.n_vars > limit:
            if logger:
                logger.info("No var['type']; keeping first %s/%s variables", limit, adata.n_vars)
            return adata[:, :limit].copy()
        return adata

    type_values = var["type"].astype(str).str.upper()
    gene_mask = type_values.isin(["ST", "RNA", "GENE", "GENES", "TRANSCRIPTOME"])
    metabolite_mask = type_values.isin(["SM", "METABOLITE", "METABOLITES"])

    if not bool(gene_mask.any()) and not bool(metabolite_mask.any()):
        limit = n_top_genes + n_top_metabolites
        if limit > 0 and adata.n_vars > limit:
            return adata[:, :limit].copy()
        return adata

    selected = []
    if n_top_genes > 0:
        genes = list(var.index[gene_mask])
        selected.extend(genes[:n_top_genes])
    else:
        selected.extend(list(var.index[gene_mask]))

    if n_top_metabolites > 0:
        metabolites = list(var.index[metabolite_mask])
        selected.extend(metabolites[:n_top_metabolites])
    else:
        selected.extend(list(var.index[metabolite_mask]))

    selected = [x for x in selected if x in adata.var_names]
    if selected and len(selected) < adata.n_vars:
        if logger:
            logger.info("Feature cap: keeping %s/%s variables", len(selected), adata.n_vars)
        return adata[:, selected].copy()
    return adata


def filter_zero_selected_st_library(adata, logger=None):
    """Apply and persist the selected-ST-library input contract dynamically."""
    import numpy as np
    input_observations = int(adata.n_obs)
    provenance = {
        "input_observations": input_observations,
        "zero_st_library_observations": 0,
        "filtered_zero_st_library_observations": 0,
        "final_model_observations": input_observations,
        "zero_library_filter_enabled": False,
        "zero_library_filter_rule": "selected ST library > 0 after feature selection",
    }
    if "type" not in adata.var.columns:
        provenance["zero_library_filter_rule"] = "not evaluated: missing feature type annotations"
        adata.uns["spashiny_joint_input_filter"] = provenance
        return adata
    feature_type = adata.var["type"].astype(str).str.upper().to_numpy()
    st_mask = feature_type == "ST"; sm_mask = feature_type == "SM"
    if not bool(st_mask.any()) or not bool(sm_mask.any()):
        provenance["zero_library_filter_rule"] = "not evaluated: selected joint ST/SM feature types unavailable"
        adata.uns["spashiny_joint_input_filter"] = provenance
        return adata
    st_library = adata.X[:, st_mask].sum(axis=1)
    st_library = st_library.A1 if hasattr(st_library, "A1") else np.asarray(st_library).reshape(-1)
    keep = np.isfinite(st_library) & (st_library > 0)
    zero_count = int((~keep).sum())
    provenance.update({
        "zero_st_library_observations": zero_count,
        "filtered_zero_st_library_observations": zero_count,
        "final_model_observations": int(keep.sum()),
        "zero_library_filter_enabled": True,
    })
    if zero_count:
        if not bool(keep.any()):
            raise ValueError("No observations have positive selected ST library for ConditionalVAESTSM.")
        if logger:
            logger.info("Filtering %s observations with zero selected ST library before ConditionalVAESTSM.", zero_count)
        adata = adata[keep].copy()
    adata.uns["spashiny_joint_input_filter"] = provenance
    return adata

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
    target_sum_sm = cfg.get("target_sum_sm", cfg.get("target_sum_SM", 1000))
    target_sum_st = cfg.get("target_sum_st", cfg.get("target_sum_ST", None))

    input_layer = cfg.get("input_layer")
    if input_layer and input_layer in adata.layers:
        adata.X = adata.layers[input_layer]
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

        if hasattr(smt.pp, "normalize_total_joint_adata_sm_st") and "type" in adata.var.columns:
            logger.info(
                "Normalizing joint AnnData with target_sum_SM=%s, target_sum_ST=%s",
                target_sum_sm,
                target_sum_st,
            )
            smt.pp.normalize_total_joint_adata_sm_st(
                adata,
                target_sum_SM=target_sum_sm,
                target_sum_ST=target_sum_st,
            )
        else:
            target_sum = target_sum_sm if target_sum_sm is not None else 1e4
            logger.info("Normalizing AnnData with scanpy target_sum=%s", target_sum)
            sc.pp.normalize_total(adata, target_sum=target_sum)
            sc.pp.log1p(adata)

    return adata


def parse_batch_keys(value, adata):
    if value is None:
        return None
    if isinstance(value, str):
        if value.strip() == "":
            return None
        keys = [x.strip() for x in value.split(",") if x.strip()]
    elif isinstance(value, (list, tuple)):
        keys = [str(x).strip() for x in value if str(x).strip()]
    else:
        keys = [str(value).strip()]
    keys = [key for key in keys if key in adata.obs.columns]
    return keys or None


def instantiate_model(smt, torch, adata, cfg, device, logger):
    hidden_stacks = parse_hidden_stacks(cfg.get("hidden_stacks")) or [64]
    batch_keys = parse_batch_keys(cfg.get("batch_keys", "sample"), adata)
    model_type = str(cfg.get("model_type", "stsm")).lower()

    common_kwargs = {
        "adata": adata,
        "hidden_stacks": hidden_stacks,
        "batch_keys": batch_keys,
        "n_latent": int(cfg.get("n_latent", 6)),
        "bias": bool(cfg.get("bias", True)),
        "use_batch_norm": bool(cfg.get("use_batch_norm", True)),
        "use_layer_norm": bool(cfg.get("use_layer_norm", False)),
        "dropout_rate": float(cfg.get("dropout_rate", 0.1)),
        "device": device,
        "batch_embedding": cfg.get("batch_embedding", "onehot"),
        "encode_libsize": bool(cfg.get("encode_libsize", False)),
        "batch_hidden_dim": int(cfg.get("batch_hidden_dim", 8)),
    }

    logger.info("Model type=%s, hidden_stacks=%s, batch_keys=%s", model_type, hidden_stacks, batch_keys)

    if model_type in ("sm", "conditionalsm", "conditionalvaesm"):
        activation_map = {
            "ReLU": torch.nn.ReLU,
            "LeakyReLU": torch.nn.LeakyReLU,
            "Tanh": torch.nn.Tanh,
            "Sigmoid": torch.nn.Sigmoid,
            "ELU": torch.nn.ELU,
        }
        common_kwargs["activation_fn"] = activation_map.get(
            cfg.get("activation_fn", "ReLU"),
            torch.nn.ReLU,
        )
        common_kwargs["reconstruction_method"] = cfg.get("reconstruction_method", cfg.get("reconstruction_method_sm", "g"))
        return smt.model.ConditionalVAESM(**common_kwargs)

    common_kwargs["reconstruction_method_sm"] = cfg.get("reconstruction_method_sm", "g")
    common_kwargs["reconstruction_method_st"] = cfg.get("reconstruction_method_st", "zinb")
    return smt.model.ConditionalVAESTSM(**common_kwargs)


def fit_model(model, cfg, device, use_amp, logger):
    fit_kwargs = {
        "max_epoch": int(cfg.get("max_epoch", 8)),
        "n_per_batch": int(cfg.get("n_per_batch", 8)),
        "lr": float(cfg.get("lr", cfg.get("learning_rate", 0.001))),
        "kl_loss_reduction": cfg.get("kl_loss_reduction", "mean"),
        "kl_weight": float(cfg.get("kl_weight", 1.0)),
        "n_epochs_kl_warmup": int(cfg.get("n_epochs_kl_warmup", cfg.get("kl_warmup_epochs", 0)) or 0),
        "weight_decay": float(cfg.get("weight_decay", 1e-6)),
        "save_gate_logits": bool(cfg.get("save_gate_logits", False)),
        "save_model_copy": bool(cfg.get("save_model_copy", False)),
        "use_amp": bool(use_amp),
    }

    mode = cfg.get("mode", cfg.get("training_mode", None))
    if mode:
        fit_kwargs["mode"] = mode

    for key in (
        "reconstruction_st_weight",
        "reconstruction_sm_weight",
        "reconstruction_weight",
        "mmd_weight",
    ):
        if key in cfg and cfg[key] not in (None, ""):
            fit_kwargs[key] = float(cfg[key])

    logger.info("Fit kwargs: %s", json.dumps(fit_kwargs, ensure_ascii=False, default=json_default))

    try:
        return model.fit(**fit_kwargs)
    except TypeError as exc:
        message = str(exc)
        removable = ("save_gate_logits", "save_model_copy", "use_amp")
        if any(key in message for key in removable):
            logger.warning("SpatialMETA fit lacks new low-memory kwargs; retrying without them: %s", message)
            for key in removable:
                fit_kwargs.pop(key, None)
            return model.fit(**fit_kwargs)
        raise


def run_training(args):
    outdir = Path(args.outdir).resolve()
    logger, log_path = setup_logging(outdir)
    start_time = datetime.now()

    user_params = parse_custom_params(args.custom_params_json)
    cfg = resolve_runtime_config(args.mode or "low_memory", user_params)
    cpu_threads = set_cpu_thread_env(cfg.get("cpu_threads", 2))

    summary = {
        "success": False,
        "input_h5ad": normalize_path(args.input_h5ad),
        "input_sha256": sha256_file(args.input_h5ad),
        "outdir": str(outdir),
        "mode": args.mode or "low_memory",
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
        seed = set_reproducible_seed(torch, cfg.get("seed", 42), logger)
        cfg["seed"] = seed
        use_amp = bool(cfg.get("use_amp", False)) and device == "cuda"

        summary.update(
            {
                "device": device,
                "cpu_threads": cpu_threads,
                "cuda_available": bool(torch.cuda.is_available()),
                "use_amp": bool(use_amp),
                "torch_version": getattr(torch, "__version__", "unknown"),
                "seed": seed,
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
        adata = select_features_by_type(
            adata,
            n_top_genes=cfg.get("n_top_genes"),
            n_top_metabolites=cfg.get("n_top_metabolites"),
            logger=logger,
        )
        logger.info("Training AnnData shape after feature cap=%s", adata.shape)
        adata = filter_zero_selected_st_library(adata, logger)
        filter_provenance = dict(adata.uns.get("spashiny_joint_input_filter") or {})
        filter_provenance.update({
            "random_seed": int(seed),
            "n_top_genes": int(cfg.get("n_top_genes") or 0),
            "n_top_metabolites": int(cfg.get("n_top_metabolites") or 0),
        })
        adata.uns["spashiny_joint_input_filter"] = filter_provenance
        summary["filter_provenance"] = filter_provenance
        logger.info("Training AnnData shape after joint input filter=%s", adata.shape)

        adata = maybe_call_normalize(smt, sc, adata, cfg, logger)
        # Feature Explorer follows the original SpatialMETA contract and renders
        # from layers["normalized"], never from a silent fallback to adata.X.
        if "normalized" not in adata.layers:
            normalized = adata.X.copy() if hasattr(adata.X, "copy") else np.array(adata.X, copy=True)
            adata.layers["normalized"] = normalized
            logger.info("Persisted normalized layer for SpatialMETA Feature Explorer")

        model = instantiate_model(smt, torch, adata, cfg, device, logger)
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

        n_per_batch = int(cfg.get("n_per_batch", 8))
        latent_raw = model.get_latent_embedding(n_per_batch=n_per_batch, show_progress=False)
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
            try:
                neighbors = int(cfg.get("n_neighbors", 15))
                logger.info("SPASHINY_PROGRESS: POSTPROCESS_NEIGHBORS")
                sc.pp.neighbors(adata, use_rep="X_emb", n_neighbors=neighbors, random_state=seed)
                logger.info("SPASHINY_PROGRESS: POSTPROCESS_UMAP")
                sc.tl.umap(adata, min_dist=float(cfg.get("umap_min_dist", 1.0)), spread=float(cfg.get("umap_spread", 1.0)), random_state=seed)
                cluster_key = f"VAE_clusters_latent{int(cfg.get('n_latent', 6))}"
                logger.info("SPASHINY_PROGRESS: POSTPROCESS_LEIDEN")
                sc.tl.leiden(adata, resolution=float(cfg.get("leiden_resolution", 1.0)), key_added=cluster_key, random_state=seed)
                adata.obs["VAE_clusters"] = adata.obs[cluster_key].astype(str)
                summary["cluster_key"] = cluster_key
                logger.info("Postprocess finished: %s", cluster_key)
            except Exception:
                logger.exception("Postprocess failed; keeping trained outputs")

        result_h5ad = outdir / "spatialmeta_result.h5ad"
        logger.info("SPASHINY_PROGRESS: SAVING_RESULT")
        adata.uns["spatialmeta_train_config"] = cfg
        adata.uns["spashiny_reproducibility"] = {
            "random_seed": int(seed),
            "n_top_genes": int(cfg.get("n_top_genes") or 0),
            "n_top_metabolites": int(cfg.get("n_top_metabolites") or 0),
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
    parser.add_argument("--mode", default="low_memory", choices=sorted(RESOURCE_PRESETS.keys()))
    parser.add_argument("--custom_params_json", default="{}")
    args = parser.parse_args()

    rc, _summary = run_training(args)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
