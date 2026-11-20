from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from . import clustering, differential, enrichment, integration_postprocessing, marker, metabolite_annotation, river_st, sm_qc, st_qc
from .common import CPUWorkflowContext, CPUWorkflowError, validate_result_contract, write_csv, write_json


WORKFLOW_NOT_IMPLEMENTED = "WORKFLOW_NOT_IMPLEMENTED"
MARKER_ANALYSIS = "marker_analysis"
MARKER_FEATURE_ANALYSIS = "marker_feature_analysis"
GENE_ENRICHMENT = "gene_enrichment"
METABOLITE_ENRICHMENT = "metabolite_enrichment"
RESULT_VALIDATION = "result_validation"
RESULT_PACKAGING = "result_packaging"
INTEGRATION_POSTPROCESSING = "integration_postprocessing"
CLUSTERING = "clustering"
RIVER_SPATIAL_TRANSCRIPTOMICS = "river_spatial_transcriptomics"


@dataclass(frozen=True)
class CPUWorkflowSpec:
    workflow_name: str
    enabled: bool
    input_contract: dict
    parameter_schema: dict
    handler: Callable[[CPUWorkflowContext], dict] | None
    required_outputs: tuple[str, ...]
    optional_outputs: tuple[str, ...]
    timeout_seconds: int
    result_validator: Callable[[object, tuple[str, ...]], tuple[bool, str, str]]
    supported_input_types: tuple[str, ...]
    example_compatibility: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "workflow_name": self.workflow_name,
            "enabled": self.enabled,
            "input_contract": self.input_contract,
            "parameter_schema": self.parameter_schema,
            "handler": getattr(self.handler, "__name__", "") if self.handler else "",
            "required_outputs": list(self.required_outputs),
            "optional_outputs": list(self.optional_outputs),
            "timeout_seconds": self.timeout_seconds,
            "result_validator": getattr(self.result_validator, "__name__", "validate_result_contract"),
            "supported_input_types": list(self.supported_input_types),
            "example_compatibility": list(self.example_compatibility),
        }


COMMON_REQUIRED = ("summary.json", "manifest.json", "session_info.txt", "logs/stdout.log", "logs/stderr.log")
QC_REQUIRED = (*COMMON_REQUIRED, "qc_summary.json", "observation_qc.csv", "feature_qc.csv", "filtered_result.h5ad")
KNN_REQUIRED = (*COMMON_REQUIRED, "knn_summary.json", "knn_observation_summary.csv", "knn_sm_reassigned.h5ad", "knn_st_reassigned.h5ad")
CLUSTERING_REQUIRED = (*COMMON_REQUIRED, "clustering_summary.json", "cluster_counts.csv", "observation_clusters.csv", "clustered_result.h5ad")
ENRICHMENT_REQUIRED = (*COMMON_REQUIRED, "mapping_results.csv", "enrichment_results.csv", "enrichment_summary.json", "dotplot.png", "barplot.png")


def _file_validation(ctx: CPUWorkflowContext) -> dict:
    rows = []
    for item in ctx.downloaded_assets:
        rows.append(
            {
                "filename": item.get("filename", ""),
                "path": item.get("path", ""),
                "size_bytes": item.get("size_bytes", 0),
                "sha256": item.get("sha256", ""),
                "exists": bool(item.get("path") and __import__("pathlib").Path(str(item["path"])).is_file()),
            }
        )
    if not rows:
        raise CPUWorkflowError("INPUT_REQUIRED", "File validation requires at least one materialized input file.")
    if not all(row["exists"] for row in rows):
        raise CPUWorkflowError("INPUT_FILE_MISSING", "One or more materialized input files are missing.")
    write_csv(ctx.workspace / "validation_report.csv", rows)
    metrics = {"input_files": len(rows)}
    write_json(ctx.workspace / "validation_summary.json", {"status": "succeeded", **metrics})
    return {"metrics": metrics, "outputs": ["validation_report.csv", "validation_summary.json"]}


def _result_validation(ctx: CPUWorkflowContext) -> dict:
    target = str(ctx.parameters.get("result_dir") or ctx.parameters.get("target_result_dir") or ctx.workspace)
    ok, code, message = validate_result_contract(target, tuple(ctx.parameters.get("required_outputs") or ()))
    if not ok:
        raise CPUWorkflowError(code or "RESULT_VALIDATION_FAILED", message)
    write_json(ctx.workspace / "validation_summary.json", {"status": "succeeded", "target_result_dir": target, "message": message})
    return {"metrics": {"target_result_dir": target}, "outputs": ["validation_summary.json"]}


def _result_packaging(ctx: CPUWorkflowContext) -> dict:
    import zipfile
    from pathlib import Path

    target = Path(str(ctx.parameters.get("result_dir") or ctx.parameters.get("target_result_dir") or ctx.workspace)).resolve()
    if not target.exists():
        raise CPUWorkflowError("RESULT_DIR_MISSING", "Result packaging target directory does not exist.")
    zip_path = ctx.workspace / "packaged_results.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        for path in sorted(target.rglob("*")):
            if path.is_file() and path.resolve() != zip_path.resolve():
                archive.write(path, path.relative_to(target).as_posix())
    write_json(ctx.workspace / "packaging_summary.json", {"status": "succeeded", "target_result_dir": str(target), "archive": "packaged_results.zip"})
    return {"metrics": {"target_result_dir": str(target)}, "outputs": ["packaged_results.zip", "packaging_summary.json"]}


CPU_WORKFLOW_REGISTRY: dict[str, CPUWorkflowSpec] = {
    INTEGRATION_POSTPROCESSING: CPUWorkflowSpec(
        workflow_name=INTEGRATION_POSTPROCESSING,
        enabled=True,
        input_contract={"st": "ST QC h5ad", "sm": "aligned SM h5ad", "parameters": ["n_neighbors", "dist_fold"]},
        parameter_schema={
            "n_neighbors": {"type": "integer", "minimum": 1, "default": 5},
            "dist_fold": {"type": "number", "minimum": 0, "default": 2.0},
        },
        handler=integration_postprocessing.run,
        required_outputs=KNN_REQUIRED,
        optional_outputs=("figures/knn_reassignment_spatial.png",),
        timeout_seconds=7200,
        result_validator=validate_result_contract,
        supported_input_types=(".h5ad",),
        example_compatibility=("st_qc_h5ad", "sm_aligned_h5ad"),
    ),
    "file_validation": CPUWorkflowSpec(
        workflow_name="file_validation",
        enabled=True,
        input_contract={"assets": "one_or_more_files"},
        parameter_schema={"sleep_seconds": {"type": "integer", "minimum": 0, "maximum": 3600}},
        handler=_file_validation,
        required_outputs=(*COMMON_REQUIRED, "validation_report.csv", "validation_summary.json"),
        optional_outputs=(),
        timeout_seconds=900,
        result_validator=validate_result_contract,
        supported_input_types=(".h5ad", ".csv", ".tsv", ".txt", ".json", ".imzml", ".ibd"),
        example_compatibility=("file_validation",),
    ),
    "st_quality_control": CPUWorkflowSpec(
        workflow_name="st_quality_control",
        enabled=True,
        input_contract={"primary": "ST h5ad, 10x h5, or mtx directory"},
        parameter_schema={"min_counts": {"type": "number"}, "min_features": {"type": "number"}, "min_cells": {"type": "number"}},
        handler=st_qc.run,
        required_outputs=QC_REQUIRED,
        optional_outputs=("figures/st_qc_total_counts.png", "figures/st_qc_n_features_by_counts.png"),
        timeout_seconds=7200,
        result_validator=validate_result_contract,
        supported_input_types=(".h5ad", ".h5", ".hdf5", ".mtx"),
        example_compatibility=("st_raw_h5ad", "joint_raw"),
    ),
    "sm_quality_control": CPUWorkflowSpec(
        workflow_name="sm_quality_control",
        enabled=True,
        input_contract={"primary": "SM h5ad or imzML/ibd pair"},
        parameter_schema={"min_counts": {"type": "number"}, "min_features": {"type": "number"}, "min_cells": {"type": "number"}},
        handler=sm_qc.run,
        required_outputs=QC_REQUIRED,
        optional_outputs=("figures/sm_qc_total_counts.png", "figures/sm_qc_n_features_by_counts.png"),
        timeout_seconds=7200,
        result_validator=validate_result_contract,
        supported_input_types=(".h5ad", ".h5", ".hdf5", ".imzml", ".ibd"),
        example_compatibility=("sm_raw_h5ad", "sm_batch_raw", "sm_pos_imzml", "sm_neg_imzml", "joint_raw"),
    ),
    MARKER_ANALYSIS: CPUWorkflowSpec(
        workflow_name=MARKER_ANALYSIS,
        enabled=True,
        input_contract={"primary": "processed h5ad", "parameters": ["group_column"]},
        parameter_schema={"group_column": {"type": "string"}},
        handler=marker.run,
        required_outputs=(*COMMON_REQUIRED, "marker_results.csv", "marker_summary.json"),
        optional_outputs=(),
        timeout_seconds=7200,
        result_validator=validate_result_contract,
        supported_input_types=(".h5ad",),
        example_compatibility=("processed_h5ad", "joint_raw", "st_raw_h5ad", "sm_raw_h5ad"),
    ),
    MARKER_FEATURE_ANALYSIS: CPUWorkflowSpec(
        workflow_name=MARKER_FEATURE_ANALYSIS,
        enabled=True,
        input_contract={"primary": "processed h5ad", "parameters": ["group_column"]},
        parameter_schema={"group_column": {"type": "string"}},
        handler=marker.run,
        required_outputs=(*COMMON_REQUIRED, "marker_results.csv", "marker_summary.json"),
        optional_outputs=(),
        timeout_seconds=7200,
        result_validator=validate_result_contract,
        supported_input_types=(".h5ad",),
        example_compatibility=("processed_h5ad", "joint_raw", "st_raw_h5ad", "sm_raw_h5ad"),
    ),
    "differential_analysis": CPUWorkflowSpec(
        workflow_name="differential_analysis",
        enabled=True,
        input_contract={"primary": "processed h5ad", "parameters": ["group_column", "target_group", "control_group"]},
        parameter_schema={"group_column": {"type": "string"}, "target_group": {"type": "string"}, "control_group": {"type": "string"}},
        handler=differential.run,
        required_outputs=(*COMMON_REQUIRED, "differential_results.csv", "differential_summary.json"),
        optional_outputs=(),
        timeout_seconds=7200,
        result_validator=validate_result_contract,
        supported_input_types=(".h5ad",),
        example_compatibility=("processed_h5ad", "joint_raw", "st_raw_h5ad", "sm_raw_h5ad"),
    ),
    "enrichment_analysis": CPUWorkflowSpec(
        workflow_name="enrichment_analysis",
        enabled=True,
        input_contract={"primary": "gene table/list or h5ad var names", "database": "local CSV/JSON only"},
        parameter_schema={"database_path": {"type": "string"}, "genes": {"type": "array"}},
        handler=enrichment.run,
        required_outputs=(*COMMON_REQUIRED, "enrichment_results.csv", "enrichment_summary.json"),
        optional_outputs=(),
        timeout_seconds=7200,
        result_validator=validate_result_contract,
        supported_input_types=(".csv", ".tsv", ".txt", ".h5ad"),
        example_compatibility=("marker_table", "gene_list", "processed_h5ad"),
    ),
    GENE_ENRICHMENT: CPUWorkflowSpec(
        workflow_name=GENE_ENRICHMENT,
        enabled=True,
        input_contract={"primary": "gene CSV/table or marker gene_df artifact", "database": "local GMT/SQLite only"},
        parameter_schema={
            "species": {"type": "string", "default": "mouse"},
            "gene_column": {"type": "string", "default": "gene"},
            "database_ids": {"type": "array", "default": ["hallmark", "reactome", "go_bp", "go_cc", "go_mf"]},
            "gene_resource_root": {"type": "string", "default": "/workspace/data/enrichment/gene"},
            "fdr_cutoff": {"type": "number", "default": 0.05},
        },
        handler=enrichment.run_gene,
        required_outputs=ENRICHMENT_REQUIRED,
        optional_outputs=(),
        timeout_seconds=1200,
        result_validator=validate_result_contract,
        supported_input_types=(".csv", ".tsv", ".txt", ".h5ad"),
        example_compatibility=("marker_table", "gene_list", "processed_h5ad", "gene_enrichment_csv"),
    ),
    METABOLITE_ENRICHMENT: CPUWorkflowSpec(
        workflow_name=METABOLITE_ENRICHMENT,
        enabled=True,
        input_contract={"primary": "metabolite CSV/table with KEGG.ID", "database": "local KEGG compound-pathway TSV only"},
        parameter_schema={
            "kegg_column": {"type": "string", "default": "KEGG.ID"},
            "metabolite_column": {"type": "string", "default": "metabolite"},
            "compound_pathway_db": {"type": "string", "default": "/workspace/data/enrichment/metabolite/kegg/compound_pathway_membership.tsv"},
            "fdr_cutoff": {"type": "number", "default": 0.05},
        },
        handler=enrichment.run_metabolite,
        required_outputs=ENRICHMENT_REQUIRED,
        optional_outputs=(),
        timeout_seconds=1200,
        result_validator=validate_result_contract,
        supported_input_types=(".csv", ".tsv", ".txt"),
        example_compatibility=("metabolite_table", "metabolite_enrichment_csv"),
    ),
    "metabolite_annotation": CPUWorkflowSpec(
        workflow_name="metabolite_annotation",
        enabled=True,
        input_contract={"primary": "mz table, SM h5ad, imzML, or Y7_T example", "database": "local RaMP SQLite / offline resources only"},
        parameter_schema={
            "annotation_methods": {"type": "array", "default": ["ms1_ramp_exact_mass"]},
            "database_path": {"type": "string", "default": "/workspace/data/enrichment/metabolite/ramp/RaMP_SQLite_v3.0.7.sqlite"},
            "ramp_sqlite_path": {"type": "string", "default": "/workspace/data/enrichment/metabolite/ramp/RaMP_SQLite_v3.0.7.sqlite"},
            "tolerance_ppm": {"type": "number", "default": 10.0},
            "ion_mode": {"type": "string", "default": "positive"},
            "mz_column": {"type": "string", "default": "mz"},
            "max_query_mz": {"type": "integer", "default": 1000},
            "example_id": {"type": "string"},
        },
        handler=metabolite_annotation.run,
        required_outputs=(*COMMON_REQUIRED, "metabolite_annotations.csv", "annotation_summary.json"),
        optional_outputs=(
            "metabolite_annotation_candidates.csv",
            "mapped_metabolites.csv",
            "unmapped_metabolites.csv",
            "ambiguous_metabolites.csv",
            "annotation_requirements.csv",
            "annotation_methods.json",
            "result_manifest.json",
            "results.zip",
        ),
        timeout_seconds=7200,
        result_validator=validate_result_contract,
        supported_input_types=(".csv", ".tsv", ".txt", ".h5ad", ".imzml"),
        example_compatibility=("mz_table", "feature_table", "sm_raw_h5ad", "sm_pos_imzml", "sm_neg_imzml"),
    ),
    RIVER_SPATIAL_TRANSCRIPTOMICS: CPUWorkflowSpec(
        workflow_name=RIVER_SPATIAL_TRANSCRIPTOMICS,
        enabled=True,
        input_contract={"samples": "two_or_more_spatial_transcriptomics_h5ad_or_h5", "annotations": "optional CSV matched by filename"},
        parameter_schema={
            "sample_labels": {"type": "string", "default": ""},
            "subsample_size": {"type": "integer", "minimum": 500, "maximum": 50000, "default": 6000},
            "river_epochs": {"type": "integer", "minimum": 10, "maximum": 1000, "default": 100},
            "random_seed": {"type": "integer", "default": 42},
        },
        handler=river_st.run,
        required_outputs=(*COMMON_REQUIRED, *river_st.RIVER_REQUIRED_OUTPUTS),
        optional_outputs=("river_plot_adata_features.csv", "river_final_rank_temporal.npy", "river_ig_temporal.npy", "river_dl_temporal.npy", "river_sl_temporal.npy"),
        timeout_seconds=21600,
        result_validator=validate_result_contract,
        supported_input_types=(".h5ad", ".h5", ".csv"),
        example_compatibility=(),
    ),
    RESULT_VALIDATION: CPUWorkflowSpec(
        workflow_name=RESULT_VALIDATION,
        enabled=True,
        input_contract={"parameters": ["result_dir"]},
        parameter_schema={"result_dir": {"type": "string"}, "required_outputs": {"type": "array"}},
        handler=_result_validation,
        required_outputs=(*COMMON_REQUIRED, "validation_summary.json"),
        optional_outputs=(),
        timeout_seconds=900,
        result_validator=validate_result_contract,
        supported_input_types=(),
        example_compatibility=(),
    ),
    CLUSTERING: CPUWorkflowSpec(
        workflow_name=CLUSTERING,
        enabled=True,
        input_contract={"primary": "processed h5ad with latent embedding", "parameters": ["n_neighbors", "resolution"]},
        parameter_schema={
            "use_rep": {"type": "string", "default": "X_emb"},
            "n_neighbors": {"type": "integer", "minimum": 1, "default": 15},
            "resolution": {"type": "number", "minimum": 0, "default": 1.0},
            "umap_min_dist": {"type": "number", "default": 1.0},
            "umap_spread": {"type": "number", "default": 1.0},
        },
        handler=clustering.run,
        required_outputs=CLUSTERING_REQUIRED,
        optional_outputs=("figures/clustering_umap.png",),
        timeout_seconds=7200,
        result_validator=validate_result_contract,
        supported_input_types=(".h5ad",),
        example_compatibility=("joint_downstream_reference_h5ad", "processed_h5ad", "joint_raw"),
    ),
    RESULT_PACKAGING: CPUWorkflowSpec(
        workflow_name=RESULT_PACKAGING,
        enabled=True,
        input_contract={"parameters": ["result_dir"]},
        parameter_schema={"result_dir": {"type": "string"}},
        handler=_result_packaging,
        required_outputs=(*COMMON_REQUIRED, "packaged_results.zip", "packaging_summary.json"),
        optional_outputs=(),
        timeout_seconds=900,
        result_validator=validate_result_contract,
        supported_input_types=(),
        example_compatibility=(),
    ),
}


def get_cpu_workflow(workflow_name: str) -> CPUWorkflowSpec:
    workflow = str(workflow_name or "")
    spec = CPU_WORKFLOW_REGISTRY.get(workflow)
    if spec is None:
        return CPUWorkflowSpec(
            workflow_name=workflow,
            enabled=False,
            input_contract={},
            parameter_schema={},
            handler=None,
            required_outputs=COMMON_REQUIRED,
            optional_outputs=(),
            timeout_seconds=0,
            result_validator=validate_result_contract,
            supported_input_types=(),
            example_compatibility=(),
        )
    return spec


def list_cpu_workflows() -> list[dict]:
    return [spec.to_dict() for spec in CPU_WORKFLOW_REGISTRY.values()]
