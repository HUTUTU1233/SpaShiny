"""Frozen official-notebook training profiles; no platform resource presets.

Only arguments explicitly used in the tutorials are passed to SpatialMETA.
Unspecified arguments retain the installed package's defaults. Existing trained
checkpoints are loaded with their recorded architecture, never rewritten.
"""
import copy
import inspect

POLICY = "spatialmeta_official_tutorials_20261021_v1"
NOTICE = ("SpatialMETA tutorial parameters: Alignment VAE 128 epochs; "
          "ST-SM/SM integration 64 epochs, learning rate 0.001, latent dimension 10; "
          "alignment optimization 500 iterations. No Low memory/Balanced/Performance overrides.")
URLS = {
    "alignment": "https://spatialmeta.readthedocs.io/en/latest/notebooks/Alignment.html",
    "stsm_single": "https://spatialmeta.readthedocs.io/en/latest/notebooks/Vertical_Integration_for_SM_ST.html",
    "stsm_multi": "https://spatialmeta.readthedocs.io/en/latest/notebooks/Vertical_and_Horizontal_Integration_for_ST_SM.html",
    "sm_multi": "https://spatialmeta.readthedocs.io/en/latest/notebooks/Horizontal_Integration_for_SM.html",
}
_MODEL = {
    "alignment": {"n_latent": 10},
    "stsm_single": {"n_latent": 10, "reconstruction_method_sm": "g", "reconstruction_method_st": "zinb"},
    "stsm_multi": {"n_latent": 10, "batch_keys": ["sample"], "batch_embedding": "embedding",
                   "reconstruction_method_sm": "g", "reconstruction_method_st": "zinb"},
    "sm_multi": {"n_latent": 10, "batch_keys": "sample", "batch_embedding": "embedding"},
}
_FIT = {
    "alignment": {"max_epoch": 128},
    "stsm_single": {"max_epoch": 64, "lr": 1e-3, "mode": "single"},
    "stsm_multi": {"max_epoch": 64, "lr": 1e-3, "mode": "multi", "kl_loss_reduction": "mean"},
    "sm_multi": {"max_epoch": 64, "lr": 1e-3, "kl_loss_reduction": "mean", "kl_weight": 15,
                 "n_epochs_kl_warmup": 0},
}
IO_OPTIONS = {"input_layer", "normalize_input", "requested_device", "cpu_threads",
              "run_postprocess", "save_model_state", "save_modality_contribution",
              "save_reconstruction", "store_reconstruction_layer", "save_reconstruction_diagnostics",
              "max_reconstruction_diagnostics_elements", "reconstruction_sample_points",
              "run_spatial_variable", "n_top_variable", "spatial_variable_batch_key",
              "spatial_variable_min_samples", "spatial_variable_min_frac", "spatial_variable_min_logfc"}


def profile_key(model_type="stsm", sample_policy="single"):
    key = "alignment" if model_type == "alignment" else f"{model_type}_{sample_policy}"
    if key not in _MODEL:
        raise ValueError(f"No approved SpatialMETA tutorial profile: {key}")
    return key


def model_kwargs(model_type="stsm", sample_policy="single"):
    return copy.deepcopy(_MODEL[profile_key(model_type, sample_policy)])


def fit_kwargs(model_type="stsm", sample_policy="single"):
    return copy.deepcopy(_FIT[profile_key(model_type, sample_policy)])


def signature_defaults(method):
    return {k: v.default for k, v in inspect.signature(method).parameters.items()
            if v.default is not inspect.Parameter.empty}


def tutorial_model_defaults(smt, model_type="stsm", sample_policy="single"):
    cls = smt.model.ConditionalVAESM if model_type == "sm" else smt.model.ConditionalVAESTSM
    values = {}
    for base in cls.__mro__:
        if "adata" in inspect.signature(base.__init__).parameters:
            values = signature_defaults(base.__init__)
            break
    values.update(model_kwargs(model_type, "multi" if model_type == "sm" else sample_policy))
    return values


def tutorial_training_defaults(smt, model_type="stsm", sample_policy="single"):
    cls = smt.model.ConditionalVAESM if model_type == "sm" else smt.model.ConditionalVAESTSM
    values = signature_defaults(cls.fit_core) if hasattr(cls, "fit_core") else {}
    values.update(signature_defaults(cls.fit))
    values.update(fit_kwargs(model_type, "multi" if model_type == "sm" else sample_policy))
    # The installed STSM fit wrapper resolves these internally by workflow mode.
    # Record that effective behavior, not the different fit_core signature values.
    if model_type == "stsm":
        values.update(kl_weight=2.0 if sample_policy == "single" else 15.0,
                      n_epochs_kl_warmup=35 if sample_policy == "single" else 0)
    return values


def postprocess_kwargs(model_type="stsm", sample_policy="single"):
    profile_key(model_type, sample_policy)
    return {"neighbors": {"n_neighbors": 20 if (model_type, sample_policy) == ("stsm", "multi") else 15},
            "umap": {"min_dist": 1, "spread": 1}, "leiden": {"resolution": 1}}


def tutorial_job_parameters(model_type="stsm", sample_policy="single", **io_options):
    key = profile_key(model_type, sample_policy)
    unexpected = set(io_options) - IO_OPTIONS
    if unexpected:
        raise ValueError("Training overrides are not permitted: " + ", ".join(sorted(unexpected)))
    return {"mode": "tutorial", "parameter_policy": POLICY, "custom_params": {
        "model_type": model_type, "sample_policy": sample_policy, "tutorial_profile": key,
        "run_postprocess": True, "save_model_state": True,
        "save_modality_contribution": model_type == "stsm", "save_reconstruction": model_type == "stsm",
        "store_reconstruction_layer": model_type == "stsm", "save_reconstruction_diagnostics": model_type == "stsm",
        **io_options}}


def alignment_epochs():
    return 128


def alignment_iterations():
    return 500


def alignment_fit_kwargs(method):
    """Map the tutorial's historical align_st_feature=False to installed API."""
    params = inspect.signature(method).parameters
    result = {"niter": alignment_iterations()}
    for key in ("align_st_feature", "align_st_feature_map"):
        if key in params:
            result[key] = False
    # The installed version renamed this flag; do not invent an unsupported kwarg.
    return result
