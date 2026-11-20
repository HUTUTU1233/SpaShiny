from __future__ import annotations

from dataclasses import asdict, dataclass

from .gpu_runtime_profiles import runtime_profile_for_workflow
from .model_registry import get_model_spec_for_workflow


FILE_VALIDATION = "file_validation"
MANIFEST_GENERATION = "manifest_generation"
SMALL_PREVIEW = "small_preview"
METADATA_STATISTICS = "metadata_statistics"
LIGHTWEIGHT_PLOTTING = "lightweight_plotting"

ST_QUALITY_CONTROL = "st_quality_control"
SM_QUALITY_CONTROL = "sm_quality_control"
SM_TIC_PREVIEW = "sm_tic_preview"
SM_ROI_EXPORT = "sm_roi_export"
SM_POS_NEG_MERGE = "sm_pos_neg_merge"
NORMALIZATION = "normalization"
FEATURE_SELECTION = "feature_selection"
MARKER_FEATURE_ANALYSIS = "marker_feature_analysis"
MARKER_ANALYSIS = "marker_analysis"
DIFFERENTIAL_ANALYSIS = "differential_analysis"
ENRICHMENT_ANALYSIS = "enrichment_analysis"
GENE_ENRICHMENT = "gene_enrichment"
METABOLITE_ENRICHMENT = "metabolite_enrichment"
METABOLITE_ANNOTATION = "metabolite_annotation"
RIVER_SPATIAL_TRANSCRIPTOMICS = "river_spatial_transcriptomics"
RESULT_VALIDATION = "result_validation"
RESULT_PACKAGING = "result_packaging"
CLUSTERING = "clustering"
SPATIAL_STATISTICS = "spatial_statistics"
LARGE_MATRIX_PROCESSING = "large_matrix_processing"

ALIGNMENT_VAE_TRAINING = "alignment_vae_training"
ALIGNMENT_PREPROCESSING = "alignment_preprocessing"
ALIGNMENT_RASTERIZATION = "alignment_rasterization"
ALIGNMENT_FITTING = "alignment_fitting"
ALIGNMENT_APPLY_TRANSFORM = "alignment_apply_transform"
ST_SM_CONDITIONAL_VAE = "st_sm_conditional_vae"
VIT_SINGLE_SAMPLE_INTEGRATION = "vit_single_sample_integration"
HIT_SM_MULTI_SAMPLE_INTEGRATION = "hit_sm_multi_sample_integration"
VHIT_MULTI_SAMPLE_INTEGRATION = "vhit_multi_sample_integration"
SM_MULTI_SAMPLE_VAE = "sm_multi_sample_vae"
INTEGRATION_POSTPROCESSING = "integration_postprocessing"
MODEL_INFERENCE = "model_inference"
DEEP_MULTIMODAL_INTEGRATION = "deep_multimodal_integration"
GRAPH_NEURAL_NETWORK = "graph_neural_network"
IMAGE_FEATURE_EXTRACTION = "image_feature_extraction"
DEEP_MODEL_TRAINING = "deep_model_training"

WORKFLOW_UNDER_DEVELOPMENT = "WORKFLOW_UNDER_DEVELOPMENT"
WORKFLOW_HANDLER_NOT_IMPLEMENTED = "WORKFLOW_HANDLER_NOT_IMPLEMENTED"
WORKFLOW_NOT_IMPLEMENTED = "WORKFLOW_NOT_IMPLEMENTED"


@dataclass(frozen=True)
class WorkflowSpec:
    name: str
    label: str
    input_key: str
    default_result: str
    compute_class: str
    preferred_backend: str
    minimum_cpu: int
    minimum_memory_gb: int
    minimum_vram_gb: int
    timeout_seconds: int
    maximum_retries: int
    worker_image: str
    expected_outputs: tuple[str, ...]
    implemented: bool = False
    notes: str = ""
    required_input_types: tuple[str, ...] = (".h5ad",)
    executor_name: str = "mock_gpu"
    estimated_cost_usd: float = 0.0
    gpu_required: bool = False
    provider_chain: tuple[str, ...] = ()
    model_name: str = ""
    analysis_page: str = ""
    runtime_profile: str = ""
    dispatch_enabled: bool = False
    disabled_error_code: str = WORKFLOW_HANDLER_NOT_IMPLEMENTED

    def to_dict(self) -> dict:
        data = asdict(self)
        data["workflow_name"] = self.name
        data["enabled"] = self.implemented
        data["dispatch_enabled"] = self.dispatch_enabled
        data["resource_type"] = self.resource_type
        data["automatic_resource_label"] = self.automatic_resource_label
        model = get_model_spec_for_workflow(self.name)
        data["provider_chain"] = list(self.provider_chain or model.provider_chain)
        data["model_name"] = self.model_name or model.model_name
        data["analysis_page"] = self.analysis_page or model.analysis_page
        data["runtime_profile"] = self.runtime_profile or (runtime_profile_for_workflow(self.name) if self.resource_type == "gpu" else "")
        return data

    @property
    def workflow_name(self) -> str:
        return self.name

    @property
    def enabled(self) -> bool:
        return self.implemented

    @property
    def resource_type(self) -> str:
        return "gpu" if self.compute_class == "gpu" else "cpu"

    @property
    def max_runtime_seconds(self) -> int:
        return int(self.timeout_seconds)

    @property
    def automatic_resource_label(self) -> str:
        if self.compute_class == "local_cpu":
            return "Automatic - Lab local CPU"
        if self.compute_class == "cpu":
            return "Automatic - Lab CPU worker"
        return "Automatic - Lab GPU 1/GPU 2"

    def estimate_cost(self, parameters: dict | None = None) -> float:
        return float(self.estimated_cost_usd or 0.0)


def _local_cpu(
    name: str,
    label: str,
    *,
    implemented: bool = True,
    expected_outputs: tuple[str, ...] = ("summary.json", "manifest.json", "session_info.txt", "logs/stdout.log", "logs/stderr.log"),
    disabled_error_code: str = WORKFLOW_NOT_IMPLEMENTED,
) -> WorkflowSpec:
    return WorkflowSpec(
        name=name,
        label=label,
        input_key="input_files",
        default_result=expected_outputs[0],
        compute_class="local_cpu",
        preferred_backend="leaseweb_local_cpu",
        minimum_cpu=1,
        minimum_memory_gb=1,
        minimum_vram_gb=0,
        timeout_seconds=900,
        maximum_retries=1,
        worker_image="spashiny-worker-cpu:production",
        expected_outputs=expected_outputs,
        implemented=implemented,
        required_input_types=(".h5ad", ".csv", ".tsv", ".txt", ".json", ".imzml", ".ibd"),
        executor_name="local_cpu",
        gpu_required=False,
        dispatch_enabled=implemented,
        disabled_error_code=disabled_error_code,
        notes="Small control-plane-safe CPU task.",
    )


def _runpod_cpu(
    name: str,
    label: str,
    *,
    implemented: bool = False,
    expected_outputs: tuple[str, ...] = ("summary.json", "manifest.json", "session_info.txt", "logs/stdout.log", "logs/stderr.log"),
    required_input_types: tuple[str, ...] = (".h5ad", ".csv", ".tsv", ".imzml", ".ibd"),
    disabled_error_code: str = WORKFLOW_NOT_IMPLEMENTED,
) -> WorkflowSpec:
    return WorkflowSpec(
        name=name,
        label=label,
        input_key="analysis_inputs",
        default_result="output/result_manifest.json",
        compute_class="cpu",
        preferred_backend="leaseweb_local_cpu",
        minimum_cpu=4,
        minimum_memory_gb=16,
        minimum_vram_gb=0,
        timeout_seconds=7200,
        maximum_retries=1,
        worker_image="spashiny-worker-cpu:production",
        expected_outputs=expected_outputs,
        implemented=implemented,
        required_input_types=required_input_types,
        executor_name="local_cpu",
        gpu_required=False,
        provider_chain=("leaseweb_local_cpu",),
        dispatch_enabled=implemented,
        disabled_error_code=disabled_error_code,
        notes="CPU workflow scheduled on the Lab local CPU worker, outside the Shiny process.",
    )


def _runpod_gpu(
    name: str,
    label: str,
    *,
    implemented: bool = False,
    expected_outputs: tuple[str, ...] = ("result_manifest.json", "results.zip"),
    notes: str = "Deep model workflow scheduled to RunPod GPU.",
    runtime_profile: str = "spatialmeta",
    input_key: str = "joint_h5ad",
    minimum_vram_gb: int = 16,
    timeout_seconds: int = 7200,
    estimated_cost_usd: float | None = None,
    dispatch_enabled: bool | None = None,
    disabled_error_code: str = WORKFLOW_UNDER_DEVELOPMENT,
) -> WorkflowSpec:
    return WorkflowSpec(
        name=name,
        label=label,
        input_key=input_key,
        default_result=expected_outputs[0],
        compute_class="gpu",
        preferred_backend="modal_t4",
        minimum_cpu=8,
        minimum_memory_gb=32,
        minimum_vram_gb=minimum_vram_gb,
        timeout_seconds=timeout_seconds,
        maximum_retries=0,
        worker_image="spashiny-gpu-worker-spatialmeta:production",
        expected_outputs=expected_outputs,
        implemented=implemented,
        required_input_types=(".h5ad",),
        executor_name="mock_gpu",
        estimated_cost_usd=(1.0 if implemented else 0.0) if estimated_cost_usd is None else float(estimated_cost_usd),
        gpu_required=True,
        provider_chain=("modal_t4", "salad_rtx3090", "tensordock_reserved"),
        runtime_profile=runtime_profile,
        dispatch_enabled=implemented if dispatch_enabled is None else bool(dispatch_enabled),
        disabled_error_code=disabled_error_code,
        notes=notes,
    )


WORKFLOW_REGISTRY: dict[str, WorkflowSpec] = {
    SM_POS_NEG_MERGE: _runpod_cpu(
        SM_POS_NEG_MERGE, "SpatialMETA POS/NEG CSV to H5AD", implemented=True,
        expected_outputs=("summary.json", "manifest.json", "session_info.txt", "logs/stdout.log", "logs/stderr.log", "sm_pos_neg_merged.h5ad", "pos_neg_merge_summary.json", "pos_neg_matched_coordinates.csv", "pos_neg_results.zip"),
        required_input_types=(".csv",),
    ),
    SM_TIC_PREVIEW: _runpod_cpu(
        SM_TIC_PREVIEW,
        "SM TIC / ROI Preview",
        implemented=True,
        expected_outputs=("summary.json", "manifest.json", "session_info.txt", "logs/stdout.log", "logs/stderr.log", "tic_preview.json", "tic_pixels.csv", "tic_roi_summary.json"),
        required_input_types=(".imzml", ".ibd"),
    ),
    SM_ROI_EXPORT: _runpod_cpu(
        SM_ROI_EXPORT,
        "SM ROI SpatialMETA CSV Export",
        implemented=True,
        expected_outputs=("summary.json", "manifest.json", "session_info.txt", "logs/stdout.log", "logs/stderr.log", "tic_roi_summary.json", "spatialmeta_csv.zip"),
        required_input_types=(".imzml", ".ibd"),
    ),
    FILE_VALIDATION: _local_cpu(
        FILE_VALIDATION,
        "File Validation",
        expected_outputs=("summary.json", "manifest.json", "session_info.txt", "logs/stdout.log", "logs/stderr.log", "validation_report.csv", "validation_summary.json"),
    ),
    MANIFEST_GENERATION: _local_cpu(MANIFEST_GENERATION, "Manifest", implemented=False),
    SMALL_PREVIEW: _local_cpu(SMALL_PREVIEW, "Small Preview", implemented=False, expected_outputs=("figures/preview.png", "result_manifest.json")),
    METADATA_STATISTICS: _local_cpu(METADATA_STATISTICS, "Metadata Statistics", implemented=False),
    LIGHTWEIGHT_PLOTTING: _local_cpu(LIGHTWEIGHT_PLOTTING, "Lightweight Plotting", implemented=False, expected_outputs=("figures/plot.pdf", "result_manifest.json")),
    INTEGRATION_POSTPROCESSING: WorkflowSpec(
        name=INTEGRATION_POSTPROCESSING,
        label="Integration Post-processing",
        input_key="result_h5ad",
        default_result="output/postprocessed_result.h5ad",
        compute_class="local_cpu",
        preferred_backend="leaseweb_local_cpu",
        minimum_cpu=1,
        minimum_memory_gb=2,
        minimum_vram_gb=0,
        timeout_seconds=1800,
        maximum_retries=1,
        worker_image="spashiny-worker-cpu:production",
        expected_outputs=(
            "summary.json",
            "manifest.json",
            "session_info.txt",
            "logs/stdout.log",
            "logs/stderr.log",
            "knn_summary.json",
            "knn_observation_summary.csv",
            "knn_sm_reassigned.h5ad",
            "knn_st_reassigned.h5ad",
            "figures/knn_reassignment_spatial.png",
        ),
        implemented=True,
        required_input_types=(".h5ad",),
        executor_name="local_cpu",
        provider_chain=("leaseweb_local_cpu",),
        dispatch_enabled=True,
        disabled_error_code=WORKFLOW_HANDLER_NOT_IMPLEMENTED,
        notes="KNN reassignment runs in the independent Lab CPU worker using the real SpatialMETA spot_align_byknn API.",
    ),
    ST_QUALITY_CONTROL: _runpod_cpu(
        ST_QUALITY_CONTROL,
        "Spatial Transcriptomics QC",
        implemented=True,
        expected_outputs=("summary.json", "manifest.json", "session_info.txt", "logs/stdout.log", "logs/stderr.log", "qc_summary.json", "observation_qc.csv", "feature_qc.csv", "filtered_result.h5ad"),
        required_input_types=(".h5ad", ".h5", ".hdf5", ".mtx"),
    ),
    SM_QUALITY_CONTROL: _runpod_cpu(
        SM_QUALITY_CONTROL,
        "Spatial Metabolomics QC",
        implemented=True,
        expected_outputs=("summary.json", "manifest.json", "session_info.txt", "logs/stdout.log", "logs/stderr.log", "qc_summary.json", "observation_qc.csv", "feature_qc.csv", "filtered_result.h5ad"),
        required_input_types=(".h5ad", ".h5", ".hdf5", ".imzml", ".ibd"),
    ),
    NORMALIZATION: _runpod_cpu(NORMALIZATION, "Normalization"),
    FEATURE_SELECTION: _runpod_cpu(FEATURE_SELECTION, "Feature Selection"),
    MARKER_FEATURE_ANALYSIS: _runpod_cpu(
        MARKER_FEATURE_ANALYSIS,
        "Marker Feature Analysis",
        implemented=True,
        expected_outputs=("summary.json", "manifest.json", "session_info.txt", "logs/stdout.log", "logs/stderr.log", "marker_results.csv", "marker_summary.json"),
        required_input_types=(".h5ad",),
    ),
    MARKER_ANALYSIS: _runpod_cpu(
        MARKER_ANALYSIS,
        "Marker Analysis",
        implemented=True,
        expected_outputs=("summary.json", "manifest.json", "session_info.txt", "logs/stdout.log", "logs/stderr.log", "marker_results.csv", "marker_summary.json"),
        required_input_types=(".h5ad",),
    ),
    DIFFERENTIAL_ANALYSIS: _runpod_cpu(
        DIFFERENTIAL_ANALYSIS,
        "Differential Analysis",
        implemented=True,
        expected_outputs=("summary.json", "manifest.json", "session_info.txt", "logs/stdout.log", "logs/stderr.log", "differential_results.csv", "differential_summary.json"),
        required_input_types=(".h5ad",),
    ),
    ENRICHMENT_ANALYSIS: _runpod_cpu(
        ENRICHMENT_ANALYSIS,
        "Enrichment Analysis",
        implemented=True,
        expected_outputs=("summary.json", "manifest.json", "session_info.txt", "logs/stdout.log", "logs/stderr.log", "enrichment_results.csv", "enrichment_summary.json"),
        required_input_types=(".csv", ".tsv", ".txt", ".h5ad"),
    ),
    GENE_ENRICHMENT: _runpod_cpu(
        GENE_ENRICHMENT,
        "Gene Enrichment",
        implemented=True,
        expected_outputs=(
            "summary.json",
            "manifest.json",
            "session_info.txt",
            "logs/stdout.log",
            "logs/stderr.log",
            "mapping_results.csv",
            "enrichment_results.csv",
            "enrichment_summary.json",
            "dotplot.png",
            "barplot.png",
        ),
        required_input_types=(".csv", ".tsv", ".txt", ".h5ad"),
    ),
    METABOLITE_ENRICHMENT: _runpod_cpu(
        METABOLITE_ENRICHMENT,
        "Metabolite Enrichment",
        implemented=True,
        expected_outputs=(
            "summary.json",
            "manifest.json",
            "session_info.txt",
            "logs/stdout.log",
            "logs/stderr.log",
            "mapping_results.csv",
            "enrichment_results.csv",
            "enrichment_summary.json",
            "dotplot.png",
            "barplot.png",
        ),
        required_input_types=(".csv", ".tsv", ".txt"),
    ),
    METABOLITE_ANNOTATION: _runpod_cpu(
        METABOLITE_ANNOTATION,
        "SpatialMETA Metabolite Annotation",
        implemented=True,
        expected_outputs=(
            "summary.json",
            "manifest.json",
            "session_info.txt",
            "logs/stdout.log",
            "logs/stderr.log",
            "metabolite_annotations.csv",
            "annotation_summary.json",
            "result_manifest.json",
            "results.zip",
        ),
        required_input_types=(".h5ad",),
    ),
    RIVER_SPATIAL_TRANSCRIPTOMICS: WorkflowSpec(
        name=RIVER_SPATIAL_TRANSCRIPTOMICS,
        label="Spatial Transcriptomics River",
        input_key="st_samples",
        default_result="river_summary.json",
        compute_class="local_cpu",
        preferred_backend="leaseweb_local_cpu",
        minimum_cpu=4,
        minimum_memory_gb=16,
        minimum_vram_gb=0,
        timeout_seconds=21600,
        maximum_retries=0,
        worker_image="spashiny-worker-cpu:production",
        expected_outputs=(
            "summary.json", "manifest.json", "session_info.txt", "logs/stdout.log", "logs/stderr.log",
            "river_summary.json", "river_combined_plot.png", "river_combined_plot.pdf",
            "river_final_rank_temporal.csv", "river_plot_adata.h5ad", "results.zip",
        ),
        implemented=True,
        required_input_types=(".h5ad", ".h5", ".csv"),
        executor_name="local_cpu",
        provider_chain=("leaseweb_local_cpu",),
        dispatch_enabled=True,
        disabled_error_code=WORKFLOW_HANDLER_NOT_IMPLEMENTED,
        notes="Spatial Transcriptomics River runs in the existing canonical CPU worker; its public input contract accepts ST samples only.",
    ),
    RESULT_VALIDATION: _runpod_cpu(
        RESULT_VALIDATION,
        "Result Validation",
        implemented=True,
        expected_outputs=("summary.json", "manifest.json", "session_info.txt", "logs/stdout.log", "logs/stderr.log", "validation_summary.json"),
        required_input_types=(".json", ".txt", ".csv", ".h5ad", ".zip"),
    ),
    RESULT_PACKAGING: _runpod_cpu(
        RESULT_PACKAGING,
        "Result Packaging",
        implemented=True,
        expected_outputs=("summary.json", "manifest.json", "session_info.txt", "logs/stdout.log", "logs/stderr.log", "packaged_results.zip", "packaging_summary.json"),
        required_input_types=(".json", ".txt", ".csv", ".h5ad", ".zip"),
    ),
    CLUSTERING: _runpod_cpu(
        CLUSTERING,
        "Clustering",
        implemented=True,
        expected_outputs=(
            "summary.json",
            "manifest.json",
            "session_info.txt",
            "logs/stdout.log",
            "logs/stderr.log",
            "clustering_summary.json",
            "cluster_counts.csv",
            "observation_clusters.csv",
            "clustered_result.h5ad",
            "figures/clustering_umap.png",
        ),
        required_input_types=(".h5ad",),
    ),
    SPATIAL_STATISTICS: _runpod_cpu(SPATIAL_STATISTICS, "Spatial Statistics"),
    LARGE_MATRIX_PROCESSING: _runpod_cpu(LARGE_MATRIX_PROCESSING, "Large Matrix Processing"),
    ST_SM_CONDITIONAL_VAE: _runpod_gpu(
        ST_SM_CONDITIONAL_VAE,
        "Conditional VAE",
        implemented=True,
        expected_outputs=(
            "integrated_result.h5ad",
            "model_state.pt",
            "latent.npy",
            "loss_record.json",
            "cluster_statistics.csv",
            "summary.json",
            "result_manifest.json",
            "results.zip",
        ),
        notes="Implemented GPU lifecycle path uses signed worker contracts, async callbacks, checkpoint restore, and automatic provider release.",
    ),
    ALIGNMENT_VAE_TRAINING: _runpod_gpu(
        ALIGNMENT_VAE_TRAINING,
        "AlignmentVAE",
        disabled_error_code=WORKFLOW_UNDER_DEVELOPMENT,
    ),
    ALIGNMENT_PREPROCESSING: _runpod_cpu(
        ALIGNMENT_PREPROCESSING,
        "Alignment Preprocessing",
        implemented=False,
    ),
    ALIGNMENT_RASTERIZATION: _runpod_cpu(
        ALIGNMENT_RASTERIZATION,
        "Alignment Rasterization",
        implemented=False,
    ),
    ALIGNMENT_FITTING: _runpod_gpu(
        ALIGNMENT_FITTING,
        "Alignment Fitting",
        disabled_error_code=WORKFLOW_UNDER_DEVELOPMENT,
    ),
    ALIGNMENT_APPLY_TRANSFORM: _runpod_cpu(
        ALIGNMENT_APPLY_TRANSFORM,
        "Alignment Apply Transform",
        implemented=False,
    ),
    VIT_SINGLE_SAMPLE_INTEGRATION: _runpod_gpu(
        VIT_SINGLE_SAMPLE_INTEGRATION,
        "VIT Single-sample ST-SM Integration",
        implemented=True,
        expected_outputs=(
            "integrated_result.h5ad",
            "model_state.pt",
            "latent.npy",
            "loss_record.json",
            "cluster_statistics.csv",
            "summary.json",
            "result_manifest.json",
            "results.zip",
        ),
        notes="Single-sample SpatialMETA ConditionalVAESTSM training extracted to the signed remote worker runner.",
    ),
    HIT_SM_MULTI_SAMPLE_INTEGRATION: _runpod_gpu(
        HIT_SM_MULTI_SAMPLE_INTEGRATION,
        "HIT_SM Multi-sample SM Integration",
        implemented=True,
        input_key="sm_batch_h5ad",
        minimum_vram_gb=16,
        timeout_seconds=10800,
        estimated_cost_usd=1.5,
        expected_outputs=(
            "integrated_result.h5ad",
            "model_state.pt",
            "latent.npy",
            "loss_record.json",
            "cluster_statistics.csv",
            "summary.json",
            "result_manifest.json",
            "results.zip",
        ),
        notes="Multi-sample SpatialMETA ConditionalVAESM training. CPU merge/materialization happens inside the worker workspace before GPU training.",
    ),
    VHIT_MULTI_SAMPLE_INTEGRATION: _runpod_gpu(
        VHIT_MULTI_SAMPLE_INTEGRATION,
        "VHIT Multi-sample ST-SM Integration",
        implemented=True,
        input_key="joint_batch_h5ad",
        minimum_vram_gb=24,
        timeout_seconds=14400,
        estimated_cost_usd=2.0,
        expected_outputs=(
            "integrated_result.h5ad",
            "model_state.pt",
            "latent.npy",
            "loss_record.json",
            "cluster_statistics.csv",
            "summary.json",
            "result_manifest.json",
            "results.zip",
        ),
        notes="Multi-sample SpatialMETA ConditionalVAESTSM training with sample-aware batch keys. It is not an alias for the single-sample Conditional VAE.",
    ),
    SM_MULTI_SAMPLE_VAE: _runpod_gpu(
        SM_MULTI_SAMPLE_VAE,
        "SM Multi-sample Conditional VAE",
        disabled_error_code=WORKFLOW_HANDLER_NOT_IMPLEMENTED,
    ),
    MODEL_INFERENCE: _runpod_gpu(
        MODEL_INFERENCE,
        "SpatialMETA Model Inference",
        disabled_error_code=WORKFLOW_UNDER_DEVELOPMENT,
    ),
    DEEP_MULTIMODAL_INTEGRATION: _runpod_gpu(DEEP_MULTIMODAL_INTEGRATION, "Deep Multimodal Integration"),
    GRAPH_NEURAL_NETWORK: _runpod_gpu(GRAPH_NEURAL_NETWORK, "Graph Neural Network"),
    IMAGE_FEATURE_EXTRACTION: _runpod_gpu(IMAGE_FEATURE_EXTRACTION, "Image Feature Extraction"),
    DEEP_MODEL_TRAINING: _runpod_gpu(DEEP_MODEL_TRAINING, "Deep Model Training"),
}

# Backward-compatible alias retained for older tests/imports.
GPU_WORKFLOWS = WORKFLOW_REGISTRY


def workflow_specs() -> list[dict]:
    return [spec.to_dict() for spec in WORKFLOW_REGISTRY.values()]


def get_workflow_spec(workflow: str) -> WorkflowSpec:
    workflow = str(workflow)
    spec = WORKFLOW_REGISTRY.get(workflow)
    if spec is None:
        raise ValueError(f"Unsupported workflow: {workflow}")
    return spec


def validate_workflow_name(workflow: str, *, require_implemented: bool = False) -> str:
    workflow = str(workflow)
    spec = get_workflow_spec(workflow)
    if require_implemented and not spec.implemented:
        raise NotImplementedError(f"{spec.disabled_error_code}: Workflow is registered but not implemented yet: {workflow}")
    return workflow


def gpu_provider_workflow_allowlist() -> tuple[str, ...]:
    return tuple(
        name
        for name, spec in WORKFLOW_REGISTRY.items()
        if spec.resource_type == "gpu" and spec.dispatch_enabled
    )


def ensure_workflow_dispatch_enabled(workflow: str) -> WorkflowSpec:
    try:
        spec = get_workflow_spec(workflow)
    except ValueError as exc:
        raise NotImplementedError(f"{WORKFLOW_HANDLER_NOT_IMPLEMENTED}: Unsupported workflow: {workflow}") from exc
    if not spec.dispatch_enabled:
        raise NotImplementedError(f"{spec.disabled_error_code}: Workflow is not dispatch-enabled: {workflow}")
    return spec
