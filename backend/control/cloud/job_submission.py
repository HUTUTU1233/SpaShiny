from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .action_rate_limiter import ActionRateLimitExceeded, ActionRateLimiter, OwnerActionRateLimitExceeded
from .config import SpaShinyCloudConfig, load_cloud_config
from .database import CloudDatabase, utc_now
from .example_asset_references import ExampleAssetReferenceError, ExampleAssetReferenceService
from .example_assets import ExampleAssetAccessError, ExampleAssetError, ExampleAssetService
from .gpu_budget import GpuBudgetManager
from .lab_runtime import LabGpuScheduler, LabRuntimeError, normalize_lab_gpu_choice, safe_session_child
from .local_workspace_manager import LocalWorkspaceManager
from .models import ACTIVE_JOB_STATUSES, ExecutionBackend, JobRecord, JobStatus, QUEUED_RESOURCE_JOB_STATUSES, ResourceType, UploadStatus
from .model_registry import get_model_spec_for_workflow
from .object_keys import ObjectKeyBuilder
from .session_manager import SessionRecord
from .storage import WorkspaceStorage, safe_name
from .workflow_registry import WorkflowSpec, get_workflow_spec


class JobSubmissionError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = int(status_code)
        self.retry_after = retry_after


@dataclass
class JobSubmissionService:
    database: CloudDatabase | None = None
    config: SpaShinyCloudConfig | None = None
    storage: WorkspaceStorage | None = None
    workspace_manager: LocalWorkspaceManager | None = None
    budget: GpuBudgetManager | None = None
    example_assets: ExampleAssetService | None = None
    example_references: ExampleAssetReferenceService | None = None
    action_rate_limiter: ActionRateLimiter | None = None

    def __post_init__(self) -> None:
        if self.config is None:
            self.config = load_cloud_config()
        if self.database is None:
            self.database = CloudDatabase(config=self.config)
        if self.storage is None:
            self.storage = WorkspaceStorage(self.config)
        if self.workspace_manager is None:
            self.workspace_manager = LocalWorkspaceManager(self.config)
        if self.budget is None:
            self.budget = GpuBudgetManager(self.database, self.config)
        if self.example_assets is None:
            self.example_assets = ExampleAssetService(config=self.config)
        if self.example_references is None:
            self.example_references = ExampleAssetReferenceService(database=self.database, config=self.config, example_assets=self.example_assets)
        if self.action_rate_limiter is None:
            self.action_rate_limiter = ActionRateLimiter(database=self.database, config=self.config)

    def submit(
        self,
        *,
        session: SessionRecord,
        workflow_name: str,
        input_upload_ids: list[str],
        workflow_artifacts: list[dict[str, Any]] | None = None,
        parameters: dict[str, Any] | None = None,
        requested_resource: str | None = None,
        analysis_session_id: str | None = None,
    ) -> JobRecord:
        self._require_active_session(session)
        self._require_compute_available()
        spec = get_workflow_spec(workflow_name)
        parameters = self._with_analysis_session(session, parameters, analysis_session_id, workflow_name=spec.name, data_source_mode='USER_UPLOAD')
        artifact_binding = self._workflow_artifact_job_binding(
            session=session,
            analysis_session_id=str(parameters.get("__spashiny_analysis_session_id") or ""),
            workflow_name=spec.name,
            workflow_artifacts=workflow_artifacts or [],
        )
        if not spec.enabled:
            return self._create_job(
                session=session,
                spec=spec,
                input_upload_ids=input_upload_ids,
                parameters=parameters,
                status=JobStatus.NOT_ENABLED.value,
                error_code=spec.disabled_error_code,
                error_message=f"{spec.disabled_error_code}: {workflow_name}",
                asset_binding=artifact_binding,
            )
        self._check_action_rate_limit(
            session=session,
            analysis_session_id=str(parameters.get("__spashiny_analysis_session_id") or ""),
            workflow_name=spec.name,
            action_name="submit_job",
        )
        self._validate_owner_resource_job_limits(session.session_id, spec.resource_type)
        uploads = (
            self._validate_inputs(
                session.session_id,
                str(parameters.get("__spashiny_analysis_session_id") or ""),
                input_upload_ids,
                spec,
            )
            if input_upload_ids
            else []
        )
        if not uploads and not artifact_binding:
            raise JobSubmissionError("MISSING_INPUT", "At least one completed upload or registered parent artifact is required.")
        estimated_cost = 0.0 if self.config.is_lab_profile else spec.estimate_cost(parameters)
        queue_status = JobStatus.QUEUED_GPU.value if spec.resource_type == ResourceType.GPU.value else JobStatus.QUEUED_CPU.value
        queue_name = spec.preferred_backend or spec.resource_type
        queue_name, requested_resource, assigned_gpu = self._route_resource(spec, queue_name, requested_resource)
        if self._queue_length(queue_status) >= self._queue_limit(spec.resource_type):
            return self._create_job(
                session=session,
                spec=spec,
                input_upload_ids=input_upload_ids,
                parameters=parameters,
                status=JobStatus.QUEUE_FULL.value,
                error_code="QUEUE_FULL",
                estimated_gpu_cost_usd=estimated_cost,
                asset_binding=artifact_binding,
            )
        if spec.resource_type == ResourceType.GPU.value and not self.config.is_lab_profile and not self.budget.can_start_gpu_job(estimated_cost):
            return self._create_job(
                session=session,
                spec=spec,
                input_upload_ids=input_upload_ids,
                parameters=parameters,
                status=JobStatus.BUDGET_LIMIT.value,
                error_code="BUDGET_LIMIT",
                estimated_gpu_cost_usd=estimated_cost,
                asset_binding=artifact_binding,
            )
        return self._create_job(
            session=session,
            spec=spec,
            input_upload_ids=[upload.upload_id for upload in uploads],
            parameters=parameters,
            status=queue_status,
            queue_name=queue_name,
            requested_resource=requested_resource,
            assigned_gpu=assigned_gpu,
            estimated_gpu_cost_usd=estimated_cost,
            asset_binding=artifact_binding,
        )

    # M03: registered parent artifacts retain exact owner/analysis authorization.
    def _workflow_artifact_job_binding(
        self,
        *,
        session: SessionRecord,
        analysis_session_id: str,
        workflow_name: str,
        workflow_artifacts: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Validate internal handoffs now; InputResolver revalidates at run time."""
        if not workflow_artifacts:
            return None
        try:
            from .input_resolver import InputResolver, InputResolverError

            resolved = InputResolver(database=self.database, config=self.config).validate_workflow_artifacts(
                session_id=session.session_id,
                analysis_session_id=analysis_session_id,
                workflow_name=workflow_name,
                workflow_artifacts=workflow_artifacts,
            )
        except InputResolverError as exc:
            raise JobSubmissionError("WORKFLOW_ARTIFACT_NOT_AVAILABLE", str(exc), status_code=409) from exc
        canonical: list[dict[str, str]] = []
        for reference in workflow_artifacts:
            if not isinstance(reference, dict):
                continue
            parent_type = str(reference.get("parent_type") or "")
            item = {"parent_type": parent_type, "role": str(reference.get("role") or "")}
            if parent_type == "alignment_workflow":
                item["parent_workflow_id"] = str(reference.get("parent_workflow_id") or "")
            elif parent_type == "job":
                item["parent_job_id"] = str(reference.get("parent_job_id") or "")
            canonical.append(item)
        if len(canonical) != len(resolved):
            raise JobSubmissionError("WORKFLOW_ARTIFACT_NOT_AVAILABLE", "Workflow artifact request is malformed.", status_code=422)
        return {
            "input_source": "workflow_artifact",
            # This is intentionally limited to IDs and roles.  No local path,
            # object key, or browser-controlled file name is persisted here.
            "workflow_artifacts": canonical,
            "workflow_artifact_lineage": InputResolver._workflow_artifact_lineage(resolved),
        }

    def submit_with_assets(
        self,
        *,
        session: SessionRecord,
        workflow_name: str,
        asset_object_keys: list[str],
        parameters: dict[str, Any] | None = None,
        requested_resource: str | None = None,
        analysis_session_id: str | None = None,
    ) -> JobRecord:
        self._require_active_session(session)
        self._require_compute_available()
        spec = get_workflow_spec(workflow_name)
        parameters = self._with_analysis_session(session, parameters, analysis_session_id, workflow_name=spec.name, data_source_mode='EXAMPLE')
        assert self.example_assets is not None
        try:
            asset_binding = self.example_assets.build_job_asset_binding(asset_object_keys, workflow_name=workflow_name)
        except ExampleAssetAccessError as exc:
            raise JobSubmissionError("ASSET_NOT_ALLOWED", str(exc), status_code=403) from exc
        except ExampleAssetError as exc:
            raise JobSubmissionError("ASSET_MANIFEST_UNAVAILABLE", str(exc), status_code=503) from exc
        if not spec.enabled:
            return self._create_job(
                session=session,
                spec=spec,
                input_upload_ids=[],
                parameters=parameters,
                status=JobStatus.NOT_ENABLED.value,
                error_code=spec.disabled_error_code,
                error_message=f"{spec.disabled_error_code}: {workflow_name}",
                asset_binding=asset_binding,
            )
        self._check_action_rate_limit(
            session=session,
            analysis_session_id=str(parameters.get("__spashiny_analysis_session_id") or ""),
            workflow_name=spec.name,
            action_name="submit_job",
        )
        self._validate_owner_resource_job_limits(session.session_id, spec.resource_type)
        estimated_cost = 0.0 if self.config.is_lab_profile else spec.estimate_cost(parameters)
        queue_status = JobStatus.QUEUED_GPU.value if spec.resource_type == ResourceType.GPU.value else JobStatus.QUEUED_CPU.value
        queue_name = spec.preferred_backend or spec.resource_type
        queue_name, requested_resource, assigned_gpu = self._route_resource(spec, queue_name, requested_resource)
        if self._queue_length(queue_status) >= self._queue_limit(spec.resource_type):
            return self._create_job(
                session=session,
                spec=spec,
                input_upload_ids=[],
                parameters=parameters,
                status=JobStatus.QUEUE_FULL.value,
                error_code="QUEUE_FULL",
                estimated_gpu_cost_usd=estimated_cost,
                asset_binding=asset_binding,
            )
        if spec.resource_type == ResourceType.GPU.value and not self.config.is_lab_profile and not self.budget.can_start_gpu_job(estimated_cost):
            return self._create_job(
                session=session,
                spec=spec,
                input_upload_ids=[],
                parameters=parameters,
                status=JobStatus.BUDGET_LIMIT.value,
                error_code="BUDGET_LIMIT",
                estimated_gpu_cost_usd=estimated_cost,
                asset_binding=asset_binding,
            )
        return self._create_job(
            session=session,
            spec=spec,
            input_upload_ids=[],
            parameters=parameters,
            status=queue_status,
            queue_name=queue_name,
            requested_resource=requested_resource,
            assigned_gpu=assigned_gpu,
            estimated_gpu_cost_usd=estimated_cost,
            asset_binding=asset_binding,
        )

    def submit_with_asset_references(
        self,
        *,
        session: SessionRecord,
        workflow_name: str,
        asset_reference_ids: list[str],
        parameters: dict[str, Any] | None = None,
        requested_resource: str | None = None,
        analysis_session_id: str | None = None,
    ) -> JobRecord:
        self._require_active_session(session)
        self._require_compute_available()
        if not asset_reference_ids:
            raise JobSubmissionError("INVALID_ASSET_REFERENCE", "At least one example asset reference is required.", status_code=422)
        spec = get_workflow_spec(workflow_name)
        parameters = self._with_analysis_session(session, parameters, analysis_session_id, workflow_name=spec.name, data_source_mode='EXAMPLE')
        assert self.example_references is not None
        assert self.example_assets is not None
        records = []
        try:
            for reference_id in asset_reference_ids:
                records.append(
                    self.example_references.get_for_job_submission(
                        session_id=session.session_id,
                        analysis_session_id=str(parameters.get("__spashiny_analysis_session_id") or ""),
                        reference_id=str(reference_id),
                        workflow_name=workflow_name,
                    )
                )
        except ExampleAssetReferenceError as exc:
            raise JobSubmissionError(exc.code, str(exc), status_code=exc.status_code) from exc
        asset_keys = self.example_references.object_keys_for_references(records)
        try:
            asset_binding = self.example_assets.build_job_asset_binding(asset_keys, workflow_name=workflow_name)
        except ExampleAssetAccessError as exc:
            raise JobSubmissionError("ASSET_NOT_ALLOWLISTED", str(exc), status_code=403) from exc
        except ExampleAssetError as exc:
            raise JobSubmissionError("ASSET_MANIFEST_UNAVAILABLE", str(exc), status_code=503) from exc
        asset_binding["asset_reference_ids"] = [str(item) for item in asset_reference_ids]
        asset_binding["asset_ids"] = [str(record["asset_id"]) for record in records]
        if not spec.enabled:
            return self._create_job(
                session=session,
                spec=spec,
                input_upload_ids=[],
                parameters=parameters,
                status=JobStatus.NOT_ENABLED.value,
                error_code=spec.disabled_error_code,
                error_message=f"{spec.disabled_error_code}: {workflow_name}",
                asset_binding=asset_binding,
            )
        self._check_action_rate_limit(
            session=session,
            analysis_session_id=str(parameters.get("__spashiny_analysis_session_id") or ""),
            workflow_name=spec.name,
            action_name="submit_job",
        )
        self._validate_owner_resource_job_limits(session.session_id, spec.resource_type)
        estimated_cost = 0.0 if self.config.is_lab_profile else spec.estimate_cost(parameters)
        queue_status = JobStatus.QUEUED_GPU.value if spec.resource_type == ResourceType.GPU.value else JobStatus.QUEUED_CPU.value
        queue_name = spec.preferred_backend or spec.resource_type
        queue_name, requested_resource, assigned_gpu = self._route_resource(spec, queue_name, requested_resource)
        if self._queue_length(queue_status) >= self._queue_limit(spec.resource_type):
            return self._create_job(
                session=session,
                spec=spec,
                input_upload_ids=[],
                parameters=parameters,
                status=JobStatus.QUEUE_FULL.value,
                error_code="QUEUE_FULL",
                estimated_gpu_cost_usd=estimated_cost,
                asset_binding=asset_binding,
            )
        if spec.resource_type == ResourceType.GPU.value and not self.config.is_lab_profile and not self.budget.can_start_gpu_job(estimated_cost):
            return self._create_job(
                session=session,
                spec=spec,
                input_upload_ids=[],
                parameters=parameters,
                status=JobStatus.BUDGET_LIMIT.value,
                error_code="BUDGET_LIMIT",
                estimated_gpu_cost_usd=estimated_cost,
                asset_binding=asset_binding,
            )
        for record in records:
            self.database.mark_example_asset_reference_used(
                str(record["reference_id"]), session_id=session.session_id,
                analysis_session_id=str(parameters.get("__spashiny_analysis_session_id") or ""),
            )
        return self._create_job(
            session=session,
            spec=spec,
            input_upload_ids=[],
            parameters=parameters,
            status=queue_status,
            queue_name=queue_name,
            requested_resource=requested_resource,
            assigned_gpu=assigned_gpu,
            estimated_gpu_cost_usd=estimated_cost,
            asset_binding=asset_binding,
        )

    def submit_with_example_action(
        self,
        *,
        session: SessionRecord,
        workflow_name: str,
        example_action_id: str,
        parameters: dict[str, Any] | None = None,
        requested_resource: str | None = None,
        analysis_session_id: str | None = None,
    ) -> JobRecord:
        self._require_active_session(session)
        self._require_compute_available()
        if not str(example_action_id or "").strip():
            raise JobSubmissionError("MISSING_EXAMPLE_ACTION", "An example action binding is required.", status_code=422)
        spec = get_workflow_spec(workflow_name)
        parameters = self._with_analysis_session(session, parameters, analysis_session_id, workflow_name=spec.name, data_source_mode='EXAMPLE')
        asset_binding = self._example_action_job_binding(
            session_id=session.session_id,
            analysis_session_id=str(parameters.get("__spashiny_analysis_session_id") or ""),
            action_id=str(example_action_id),
            workflow_name=workflow_name,
        )
        if not spec.enabled:
            return self._create_job(
                session=session,
                spec=spec,
                input_upload_ids=[],
                parameters=parameters,
                status=JobStatus.NOT_ENABLED.value,
                error_code=spec.disabled_error_code,
                error_message=f"{spec.disabled_error_code}: {workflow_name}",
                asset_binding=asset_binding,
            )
        self._check_action_rate_limit(
            session=session,
            analysis_session_id=str(parameters.get("__spashiny_analysis_session_id") or ""),
            workflow_name=spec.name,
            action_name="submit_job",
        )
        self._validate_owner_resource_job_limits(session.session_id, spec.resource_type)
        estimated_cost = 0.0 if self.config.is_lab_profile else spec.estimate_cost(parameters)
        queue_status = JobStatus.QUEUED_GPU.value if spec.resource_type == ResourceType.GPU.value else JobStatus.QUEUED_CPU.value
        queue_name = spec.preferred_backend or spec.resource_type
        queue_name, requested_resource, assigned_gpu = self._route_resource(spec, queue_name, requested_resource)
        if self._queue_length(queue_status) >= self._queue_limit(spec.resource_type):
            return self._create_job(
                session=session,
                spec=spec,
                input_upload_ids=[],
                parameters=parameters,
                status=JobStatus.QUEUE_FULL.value,
                error_code="QUEUE_FULL",
                estimated_gpu_cost_usd=estimated_cost,
                asset_binding=asset_binding,
            )
        if spec.resource_type == ResourceType.GPU.value and not self.config.is_lab_profile and not self.budget.can_start_gpu_job(estimated_cost):
            return self._create_job(
                session=session,
                spec=spec,
                input_upload_ids=[],
                parameters=parameters,
                status=JobStatus.BUDGET_LIMIT.value,
                error_code="BUDGET_LIMIT",
                estimated_gpu_cost_usd=estimated_cost,
                asset_binding=asset_binding,
            )
        return self._create_job(
            session=session,
            spec=spec,
            input_upload_ids=[],
            parameters=parameters,
            status=queue_status,
            queue_name=queue_name,
            requested_resource=requested_resource,
            assigned_gpu=assigned_gpu,
            estimated_gpu_cost_usd=estimated_cost,
            asset_binding=asset_binding,
        )

    def _create_job(
        self,
        *,
        session: SessionRecord,
        spec: WorkflowSpec,
        input_upload_ids: list[str],
        parameters: dict[str, Any],
        status: str,
        queue_name: str | None = None,
        requested_resource: str | None = None,
        assigned_gpu: str = "",
        error_code: str = "",
        error_message: str = "",
        estimated_gpu_cost_usd: float = 0.0,
        asset_binding: dict[str, Any] | None = None,
    ) -> JobRecord:
        assert self.storage is not None
        assert self.workspace_manager is not None
        assert self.database is not None
        assert self.config is not None
        parameters = dict(parameters or {})
        analysis_session_id = str(parameters.pop("__spashiny_analysis_session_id", "") or "").strip()
        preparation_stage = str(parameters.get("stage") or "").strip().lower()
        expected_outputs = list(spec.expected_outputs)
        # Merge and QC are intentionally independent, persisted preparation
        # jobs. They must not be validated as if they had trained a VAE.
        # Their worker contract is the real merged H5AD plus its small summary
        # and manifest; ResultPublisher adds results.zip afterwards.
        if (
            spec.name in {"vhit_multi_sample_integration", "hit_sm_multi_sample_integration"}
            and preparation_stage in {"merge", "qc"}
        ):
            expected_outputs = ["integrated_result.h5ad", "merge_summary.json", "result_manifest.json"]
        self._enforce_action_rate_limit(
            session=session,
            analysis_session_id=analysis_session_id,
            workflow_name=spec.name,
            action_name="submit_job",
        )
        job_id = safe_name("job_" + uuid.uuid4().hex, "job")
        local_workspace = self._job_workspace_for_session(session.session_id, analysis_session_id, job_id)
        queue_name = queue_name or spec.preferred_backend or spec.resource_type
        queued_at = utc_now() if status in {JobStatus.QUEUED_CPU.value, JobStatus.QUEUED_GPU.value} else ""
        metadata = {
            "executor_name": spec.executor_name,
            "workflow_name": spec.workflow_name,
            "compute_class": spec.compute_class,
            "preferred_backend": spec.preferred_backend,
            "provider_chain": list(spec.provider_chain),
            "runtime_profile": spec.runtime_profile,
            "worker_image": spec.worker_image,
            "dispatch_enabled": bool(spec.dispatch_enabled),
            "expected_outputs": expected_outputs,
            "preparation_stage": preparation_stage,
            "minimum_cpu": int(spec.minimum_cpu),
            "minimum_memory_gb": int(spec.minimum_memory_gb),
            "minimum_vram_gb": int(spec.minimum_vram_gb),
            "timeout_seconds": int(spec.timeout_seconds),
            "maximum_retries": int(spec.maximum_retries),
            "automatic_resource_label": spec.automatic_resource_label,
            "requested_resource": str(requested_resource or ""),
            "assigned_gpu": str(assigned_gpu or ""),
            "analysis_session_id": analysis_session_id,
            "random_seed": int(parameters.get("random_seed", 42) or 42),
        }
        if asset_binding:
            metadata.update(asset_binding)
        model = get_model_spec_for_workflow(spec.workflow_name)
        if not metadata.get("provider_chain"):
            metadata["provider_chain"] = list(model.provider_chain)
        metadata["model"] = model.to_dict()
        metadata["model_name"] = model.model_name
        metadata["analysis_page"] = model.analysis_page
        metadata["model_registry_version"] = self.config.model_registry_version
        metadata["input_resolver"] = model.input_resolver
        metadata["session_input_binding"] = self._session_input_binding(
            session=session,
            analysis_session_id=analysis_session_id,
            job_id=job_id,
            spec=spec,
            input_upload_ids=input_upload_ids,
            asset_binding=asset_binding,
            model_name=model.model_name,
        )
        record = JobRecord(
            job_id=job_id,
            user_id=session.session_id,
            workflow=spec.name,
            workflow_name=spec.name,
            session_id=session.session_id,
            owner_session_id=session.session_id,
            analysis_session_id=analysis_session_id,
            anonymous_workspace_id=session.anonymous_workspace_id,
            resource_type=spec.resource_type,
            execution_backend=(
                ExecutionBackend.CPU.value
                if spec.resource_type == ResourceType.CPU.value
                else ExecutionBackend.GPU_LAB_LOCAL.value
                if self.config.is_lab_profile
                else ExecutionBackend.GPU_RUNPOD.value
            ),
            status=status,
            queue_name=queue_name,
            requested_resource=str(requested_resource or ""),
            assigned_gpu=str(assigned_gpu or ""),
            parameters_json=json.dumps(parameters, ensure_ascii=False, sort_keys=True),
            local_workspace=str(local_workspace),
            created_at=utc_now(),
            queued_at=queued_at,
            max_attempts=int(spec.maximum_retries),
            estimated_gpu_cost_usd=float(estimated_gpu_cost_usd or 0.0),
            input_upload_ids_json=json.dumps(input_upload_ids, ensure_ascii=False),
            input_manifest=json.dumps(metadata.get("session_input_binding") or {}, ensure_ascii=False, sort_keys=True),
            output_manifest=json.dumps({"expected_outputs": expected_outputs}, ensure_ascii=False, sort_keys=True),
            output_prefix=ObjectKeyBuilder.result_prefix(session.session_id, job_id),
            error_code=error_code,
            error_message=error_message,
            metadata_json=json.dumps(metadata, ensure_ascii=False, sort_keys=True),
        )
        return self.database.create_job(record)

    def _enforce_action_rate_limit(
        self,
        *,
        session: SessionRecord,
        analysis_session_id: str,
        workflow_name: str,
        action_name: str,
    ) -> None:
        assert self.action_rate_limiter is not None
        try:
            self.action_rate_limiter.check_and_record(
                owner_session_id=session.session_id,
                analysis_session_id=analysis_session_id,
                workflow_name=workflow_name,
                action_name=action_name,
            )
        except (ActionRateLimitExceeded, OwnerActionRateLimitExceeded) as exc:
            raise JobSubmissionError(
                exc.code,
                str(exc),
                status_code=429,
                retry_after=exc.retry_after,
            ) from exc

    def _check_action_rate_limit(
        self,
        *,
        session: SessionRecord,
        analysis_session_id: str,
        workflow_name: str,
        action_name: str,
    ) -> None:
        assert self.action_rate_limiter is not None
        try:
            self.action_rate_limiter.check(
                owner_session_id=session.session_id,
                analysis_session_id=analysis_session_id,
                workflow_name=workflow_name,
                action_name=action_name,
            )
        except ActionRateLimitExceeded as exc:
            raise JobSubmissionError(
                exc.code,
                str(exc),
                status_code=429,
                retry_after=exc.retry_after,
            ) from exc

    def _route_resource(
        self,
        spec: WorkflowSpec,
        queue_name: str,
        requested_resource: str | None,
    ) -> tuple[str, str, str]:
        if spec.resource_type != ResourceType.GPU.value:
            if self.config.is_lab_profile:
                try:
                    requested = normalize_lab_gpu_choice(requested_resource or "cpu")
                except LabRuntimeError as exc:
                    raise JobSubmissionError(str(exc), "Invalid Lab compute resource.", status_code=422) from exc
                if requested in {"gpu-0", "gpu-1"}:
                    raise JobSubmissionError(
                        "GPU_RESOURCE_NOT_SUPPORTED_FOR_CPU_WORKFLOW",
                        "GPU resources are not supported for this CPU workflow.",
                        status_code=422,
                    )
                return queue_name, "cpu" if requested == "cpu" else "", ""
            return queue_name, "", ""
        try:
            requested = normalize_lab_gpu_choice(requested_resource or "auto")
        except LabRuntimeError as exc:
            raise JobSubmissionError(str(exc), "Invalid Lab compute resource.", status_code=422) from exc
        if requested == "cpu":
            raise JobSubmissionError("CPU_RESOURCE_NOT_SUPPORTED_FOR_GPU_WORKFLOW", "CPU is not supported for this GPU workflow.", status_code=422)
        if not self.config.is_lab_profile:
            return queue_name, requested if requested_resource is not None else "", ""
        try:
            lab_queue, assigned_gpu = LabGpuScheduler(
                self.database,
                self.config,
                minimum_vram_gb=int(spec.minimum_vram_gb or 0),
            ).queue_for_request(requested)
        except LabRuntimeError as exc:
            raise JobSubmissionError(str(exc), "Invalid Lab compute resource.", status_code=422) from exc
        return lab_queue, requested, assigned_gpu

    def _session_input_binding(
        self,
        *,
        session: SessionRecord,
        analysis_session_id: str,
        job_id: str,
        spec: WorkflowSpec,
        input_upload_ids: list[str],
        asset_binding: dict[str, Any] | None,
        model_name: str,
    ) -> dict[str, Any]:
        binding_source = str((asset_binding or {}).get("input_source") or ("example_asset" if asset_binding else "upload"))
        materialized_input_dir = ""
        result_dir = ""
        if self.config.is_lab_profile:
            # This is the established writable bind-mounted worker root.  The
            # immutable job row and the artifact endpoint bind it to the
            # analysis workspace; job IDs are unique, so no cross-analysis
            # path can be selected through the browser.
            materialized_input_dir = str(
                safe_session_child(
                    Path(self.config.lab_data_root) / "sessions",
                    session.session_id,
                    "inputs",
                    job_id,
                )
            )
            result_dir = str(
                safe_session_child(
                    Path(self.config.lab_result_root) / "sessions",
                    session.session_id,
                    job_id,
                )
            )
        payload = {
            "binding_version": "session_input_binding_v1",
            "session_id": session.session_id,
            "analysis_session_id": analysis_session_id,
            "job_id": job_id,
            "workflow_name": spec.workflow_name,
            "model_name": model_name,
            "source": binding_source,
            "workflow_artifacts": list((asset_binding or {}).get("workflow_artifact_lineage") or []),
            "input_upload_ids": [str(item) for item in input_upload_ids],
            "asset_reference_ids": list((asset_binding or {}).get("asset_reference_ids") or []),
            "example_bundle_id": str((asset_binding or {}).get("example_bundle_id") or ""),
            "example_action_id": str((asset_binding or {}).get("example_action_id") or ""),
            "materialized_input_dir": materialized_input_dir,
            "result_dir": result_dir,
        }
        digest = uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(payload, sort_keys=True, ensure_ascii=True)).hex[:24]
        return {**payload, "binding_id": "sib_" + digest}

    def _job_workspace_for_session(self, session_id: str, analysis_session_id: str, job_id: str) -> Path:
        assert self.workspace_manager is not None
        if self.config.is_lab_profile:
            path = safe_session_child(Path(self.config.lab_result_root) / "sessions", session_id, job_id)
            for dirname in ("input", "working", "output", "figures", "logs", "checkpoints"):
                (path / dirname).mkdir(parents=True, exist_ok=True)
            return path
        return self.workspace_manager.job_workspace(job_id)

    def _with_analysis_session(
        self,
        session: SessionRecord,
        parameters: dict[str, Any] | None,
        analysis_session_id: str | None,
        *, workflow_name: str = '', data_source_mode: str | None = None,
    ) -> dict[str, Any]:
        """Validate and carry an analysis scope without retaining service state."""
        payload = dict(parameters or {})
        if workflow_name == 'river_spatial_transcriptomics':
            from .river_execution_contract import validate_submission, RiverContractError
            try:
                payload = validate_submission(payload, expected_source=data_source_mode)
            except (RiverContractError, ValueError) as exc:
                raise JobSubmissionError('RIVER_EXECUTION_CONTRACT_INVALID', str(exc), status_code=422) from exc
        payload["random_seed"] = 42 if workflow_name=='river_spatial_transcriptomics' and payload.get('execution_contract_version') in ('river-execution-v2','river-unified-v3') else self._fixed_random_seed()
        candidate = str(analysis_session_id or "").strip()
        if not self.config.is_lab_profile:
            payload["__spashiny_analysis_session_id"] = candidate
            return payload
        if not candidate:
            raise JobSubmissionError(
                "ANALYSIS_SESSION_REQUIRED",
                "Start or restore an analysis session before submitting a Lab job.",
                status_code=409,
            )
        assert self.database is not None
        try:
            self.database.get_analysis_session(candidate, owner_session_id=session.session_id)
        except KeyError as exc:
            raise JobSubmissionError(
                "ANALYSIS_SESSION_NOT_FOUND",
                "The current analysis session is unavailable or belongs to another workspace.",
                status_code=403,
            ) from exc
        payload["__spashiny_analysis_session_id"] = candidate
        return payload

    @staticmethod
    def _fixed_random_seed() -> int:
        """Return the deployment-wide reproducibility seed for every submitted job."""
        raw = str(os.environ.get("SPASHINY_RANDOM_SEED", "42") or "42").strip()
        try:
            seed = int(raw)
        except (TypeError, ValueError):
            return 42
        return seed if 0 <= seed <= 2_147_483_647 else 42

    def _example_action_job_binding(self, *, session_id: str, analysis_session_id: str, action_id: str, workflow_name: str) -> dict[str, Any]:
        assert self.database is not None
        try:
            record = self.database.get_example_action_binding(session_id=session_id, analysis_session_id=analysis_session_id, action_id=action_id)
        except KeyError as exc:
            raise JobSubmissionError("EXAMPLE_ACTION_BINDING_NOT_FOUND", "Example action binding was not found.", status_code=404) from exc
        if not bool(record.get("ready")):
            raise JobSubmissionError("EXAMPLE_ACTION_NOT_READY", "Example action binding is not ready.", status_code=409)
        available = self._json_list(record.get("available_workflows_json"))
        if available and workflow_name not in available:
            raise JobSubmissionError("EXAMPLE_ACTION_WORKFLOW_NOT_ALLOWED", "Example action binding is not compatible with this workflow.", status_code=403)
        try:
            metadata = json.loads(str(record.get("metadata_json") or "{}"))
        except Exception as exc:
            raise JobSubmissionError("EXAMPLE_ACTION_BINDING_INVALID", "Example action binding metadata is invalid.", status_code=409) from exc
        components = metadata.get("components") if isinstance(metadata, dict) else []
        object_keys = [
            str(item.get("object_key"))
            for item in components
            if isinstance(item, dict) and item.get("ready") and str(item.get("object_key") or "").strip()
        ]
        return {
            "input_source": "example_action",
            "example_action_id": str(action_id),
            "example_action_binding_id": str(record.get("binding_id") or ""),
            "example_bundle_id": str(record.get("bundle_id") or ""),
            "example_bundle": {
                "bundle_id": str(record.get("bundle_id") or ""),
                "action_id": str(action_id),
                "workflow_name": str(workflow_name or ""),
                "sample_ids": self._json_list(record.get("sample_ids_json")),
                "bound_roles": self._json_list(record.get("bound_roles_json")),
                "object_keys": object_keys,
                "read_only": True,
            },
            "asset_version": str(record.get("asset_version") or ""),
            "manifest_version": str(record.get("manifest_version") or ""),
            "asset_object_keys": object_keys,
        }

    @staticmethod
    def _json_list(value: Any) -> list[str]:
        try:
            data = json.loads(str(value or "[]"))
        except Exception:
            return []
        if not isinstance(data, list):
            return []
        return [str(item) for item in data if str(item).strip()]

    def _require_active_session(self, session: SessionRecord) -> None:
        if session.status != "ACTIVE":
            raise JobSubmissionError("SESSION_NOT_ACTIVE", "Session is not active.", status_code=410)

    def _require_compute_available(self) -> None:
        assert self.config is not None
        if bool(self.config.maintenance_mode):
            raise JobSubmissionError(
                "MAINTENANCE_MODE",
                "System maintenance is in progress. New analysis jobs are temporarily unavailable.",
                status_code=503,
            )

    def _validate_owner_resource_job_limits(self, owner_session_id: str, resource_type: str) -> None:
        assert self.database is not None
        assert self.config is not None
        resource = str(resource_type or "").strip()
        owner_jobs = self.database.list_jobs(
            session_id=owner_session_id,
            statuses=sorted(ACTIVE_JOB_STATUSES),
            limit=10000,
        )
        matching = [job for job in owner_jobs if str(job.resource_type or "") == resource]
        queued = [job for job in matching if str(job.status or "") in QUEUED_RESOURCE_JOB_STATUSES]
        active = [job for job in matching if str(job.status or "") not in QUEUED_RESOURCE_JOB_STATUSES]
        if resource == ResourceType.GPU.value:
            active_limit = int(self.config.max_active_gpu_jobs_per_owner)
            queued_limit = int(self.config.max_queued_gpu_jobs_per_owner)
            label = "GPU"
        else:
            active_limit = int(self.config.max_active_cpu_jobs_per_owner)
            queued_limit = int(self.config.max_queued_cpu_jobs_per_owner)
            label = "CPU"
        if active_limit >= 0 and len(active) >= active_limit:
            raise JobSubmissionError(
                "OWNER_ACTIVE_RESOURCE_LIMIT",
                f"You already have {len(active)} {label} job(s) running or finalizing. Please wait for an existing job to finish.",
                status_code=429,
            )
        if queued_limit >= 0 and len(queued) >= queued_limit:
            raise JobSubmissionError(
                "OWNER_QUEUED_RESOURCE_LIMIT",
                f"You already have {len(active)} {label} job(s) running and {len(queued)} {label} job(s) queued. Please wait for an existing job to finish.",
                status_code=429,
            )

    def _validate_inputs(
        self, session_id: str, analysis_session_id: str, input_upload_ids: list[str], spec: WorkflowSpec
    ):
        assert self.database is not None
        if not input_upload_ids:
            raise JobSubmissionError("MISSING_INPUT", "At least one completed upload is required.")
        records = []
        allowed_suffixes = {suffix.lower() for suffix in spec.required_input_types}
        for upload_id in input_upload_ids:
            upload = self.database.get_upload(str(upload_id), session_id=session_id, analysis_session_id=analysis_session_id)
            if upload.status != UploadStatus.COMPLETED.value:
                raise JobSubmissionError("INPUT_NOT_COMPLETED", "Input upload is not completed.")
            suffixes = [suffix.lower() for suffix in Path(upload.safe_filename).suffixes]
            if not suffixes or not any(suffix in allowed_suffixes for suffix in suffixes):
                raise JobSubmissionError("INPUT_TYPE_MISMATCH", "Input upload type is not accepted by this workflow.")
            records.append(upload)
        return records

    def _queue_length(self, queue_status: str) -> int:
        assert self.database is not None
        return len(self.database.list_jobs(statuses=[queue_status], limit=10000))

    def _queue_limit(self, resource_type: str) -> int:
        assert self.config is not None
        if resource_type == ResourceType.GPU.value:
            return int(self.config.max_gpu_queue_length)
        return int(self.config.max_cpu_queue_length)
