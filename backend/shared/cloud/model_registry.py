from __future__ import annotations

from dataclasses import asdict, dataclass


MODEL_REGISTRY_VERSION = "production-candidate-v1"


@dataclass(frozen=True)
class ModelSpec:
    model_name: str
    label: str
    workflow_name: str
    analysis_page: str
    input_resolver: str
    provider_chain: tuple[str, ...]
    preferred_gpu_profile: str
    checkpoint_filename: str
    supports_precomputed_examples: bool = True

    def to_dict(self) -> dict:
        data = asdict(self)
        data["provider_chain"] = list(self.provider_chain)
        data["model_registry_version"] = MODEL_REGISTRY_VERSION
        return data


MODEL_REGISTRY: dict[str, ModelSpec] = {
    "st_sm_conditional_vae": ModelSpec(
        model_name="spatialmeta_conditional_vae",
        label="SpatialMETA Conditional VAE",
        workflow_name="st_sm_conditional_vae",
        analysis_page="Integration / Conditional VAE",
        input_resolver="session_input_binding_v1",
        provider_chain=("modal_t4", "salad_rtx3090", "tensordock_reserved"),
        preferred_gpu_profile="modal_t4_then_salad_rtx3090",
        checkpoint_filename="spatialmeta_conditional_vae_latest.pt",
    ),
    "vit_single_sample_integration": ModelSpec(
        model_name="spatialmeta_vit_single_sample",
        label="SpatialMETA VIT Single-sample ST-SM Integration",
        workflow_name="vit_single_sample_integration",
        analysis_page="Integration / VIT Single-sample ST-SM",
        input_resolver="session_input_binding_v1",
        provider_chain=("modal_t4", "salad_rtx3090", "tensordock_reserved"),
        preferred_gpu_profile="modal_t4_then_salad_rtx3090",
        checkpoint_filename="spatialmeta_vit_latest.pt",
    ),
    "hit_sm_multi_sample_integration": ModelSpec(
        model_name="spatialmeta_hit_sm_multi_sample",
        label="SpatialMETA HIT_SM Multi-sample SM Integration",
        workflow_name="hit_sm_multi_sample_integration",
        analysis_page="Integration / HIT_SM",
        input_resolver="session_input_binding_v1",
        provider_chain=("modal_t4", "salad_rtx3090", "tensordock_reserved"),
        preferred_gpu_profile="modal_t4_smoke_then_salad_rtx3090",
        checkpoint_filename="spatialmeta_hit_sm_latest.pt",
    ),
    "vhit_multi_sample_integration": ModelSpec(
        model_name="spatialmeta_vhit_multi_sample",
        label="SpatialMETA VHIT Multi-sample ST-SM Integration",
        workflow_name="vhit_multi_sample_integration",
        analysis_page="Integration / VHIT",
        input_resolver="session_input_binding_v1",
        provider_chain=("modal_t4", "salad_rtx3090", "tensordock_reserved"),
        preferred_gpu_profile="modal_t4_smoke_then_salad_rtx3090",
        checkpoint_filename="spatialmeta_vhit_latest.pt",
    ),
    "integration_postprocessing": ModelSpec(
        model_name="spashiny_integration_postprocess",
        label="Integration Post-processing",
        workflow_name="integration_postprocessing",
        analysis_page="Integration / Post-processing",
        input_resolver="session_input_binding_v1",
        provider_chain=("leaseweb_local_cpu",),
        preferred_gpu_profile="none",
        checkpoint_filename="",
    ),
}


def get_model_spec_for_workflow(workflow_name: str) -> ModelSpec:
    workflow = str(workflow_name or "")
    return MODEL_REGISTRY.get(
        workflow,
        ModelSpec(
            model_name=f"{workflow or 'unknown'}_model",
            label=workflow.replace("_", " ").title() if workflow else "Unknown Model",
            workflow_name=workflow,
            analysis_page=_analysis_page_for_workflow(workflow),
            input_resolver="session_input_binding_v1",
            provider_chain=("leaseweb_local_cpu",),
            preferred_gpu_profile="none",
            checkpoint_filename="",
            supports_precomputed_examples=False,
        ),
    )


def model_specs() -> list[dict]:
    return [spec.to_dict() for spec in MODEL_REGISTRY.values()]


def _analysis_page_for_workflow(workflow: str) -> str:
    value = str(workflow or "")
    if "quality" in value or "normalization" in value or "feature" in value:
        return "Data Processing / QC"
    if "enrichment" in value or "annotation" in value:
        return "Annotation / Enrichment"
    if "vae" in value or "integration" in value or "multimodal" in value:
        return "Integration"
    if "marker" in value or "differential" in value or "spatial" in value:
        return "Downstream Analysis"
    return "Cloud Job Center"
