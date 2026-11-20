from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .config import SpaShinyCloudConfig, load_cloud_config
from .database import CloudDatabase
from .example_assets import ExampleAssetService
from .lab_runtime import safe_session_child
from .models import JobRecord, UploadStatus
from .object_keys import ObjectKeyBuilder
from .storage_backends import TemporaryObjectStorage, get_temporary_object_storage
from .workflow_registry import get_workflow_spec


INPUT_RESOLVER_VERSION = "session_input_binding_v1"


# Internal handoffs deliberately use a small, fixed contract rather than a
# caller-provided server path.  The browser can name a parent workflow/job and
# a role only; this resolver reconstructs the safe path after verifying the
# same owner + tab analysis scope on every submit and worker-start.
WORKFLOW_ARTIFACT_CONTRACTS: dict[str, dict[str, str]] = {
    # SPATIALMETA_PARITY M03: training consumes the exact completed QC output,
    # not raw examples again. Only IDs/roles, never browser-provided paths.
    "vhit_multi_sample_integration": {
        "parent_type": "job", "parent_workflow": "vhit_multi_sample_integration",
        "parent_stage": "qc", "role": "vhit_prepared_h5ad", "modality": "joint",
    },
    "hit_sm_multi_sample_integration": {
        "parent_type": "job", "parent_workflow": "hit_sm_multi_sample_integration",
        "parent_stage": "qc", "role": "hit_sm_prepared_h5ad", "modality": "sm",
    },
    "integration_postprocessing": {
        "parent_type": "alignment_workflow",
        "role": "aligned_sm_h5ad",
    },
    "vit_single_sample_integration": {
        "parent_type": "job",
        "parent_workflow": "integration_postprocessing",
        "role": "knn_joint_h5ad",
    },
}


class InputResolverError(RuntimeError):
    pass


@dataclass
class InputResolver:
    database: CloudDatabase | None = None
    config: SpaShinyCloudConfig | None = None
    storage: TemporaryObjectStorage | None = None
    example_assets: ExampleAssetService | None = None
    # Preserve the existing host-GPU container-to-host result mapper.
    workspace_path_mapper: Callable[[str], Path] | None = None

    def __post_init__(self) -> None:
        if self.config is None:
            self.config = load_cloud_config()
        if self.database is None:
            self.database = CloudDatabase(config=self.config)
        if self.storage is None:
            self.storage = get_temporary_object_storage(self.config)
        if self.example_assets is None:
            self.example_assets = ExampleAssetService(config=self.config)

    def resolve_for_worker(self, job: JobRecord, *, callback_expires_at: int | None = None) -> dict[str, Any]:
        metadata = self._metadata(job)
        ttl = self._url_ttl()
        assets = self._upload_assets(job, ttl=ttl)
        workflow_artifacts = self._workflow_artifact_assets(job)
        assets.extend(workflow_artifacts)
        input_source = str(metadata.get("input_source") or "").strip()
        if input_source == "example_action":
            example_assets = self._example_action_assets(job, ttl=ttl)
            precomputed = []
        else:
            example_assets = self.example_assets.create_worker_download_plan(job, expires_in=ttl)
            precomputed = self.example_assets.create_precomputed_download_plan(job, expires_in=ttl)
        assets.extend(example_assets)
        result_uploads = self._result_upload_targets(job, ttl=ttl)
        checkpoint = self._checkpoint_contract(job, ttl=ttl)
        callback = self._callback_contract(job, expires_at=callback_expires_at)
        runtime_profile = self._runtime_profile(job)
        materialized_input_dir = self._materialized_input_dir(job, metadata)
        return {
            "contract_version": "signed_url_callback_v1",
            "input_resolver_version": INPUT_RESOLVER_VERSION,
            "job_id": job.job_id,
            "session_id": job.session_id or "",
            "analysis_session_id": str(job.analysis_session_id or ""),
            "worker_id": job.worker_id or "",
            "workflow": job.workflow_name or job.workflow,
            "workflow_version": self.config.model_registry_version,
            "runtime_profile": runtime_profile,
            "input_source": metadata.get("input_source") or ("example_asset" if example_assets else "upload"),
            "materialized_input_dir": materialized_input_dir,
            "manifest_version": metadata.get("manifest_version"),
            "session_input_binding": metadata.get("session_input_binding") or {},
            "example_bundle": metadata.get("example_bundle") or {},
            "model": metadata.get("model") or {},
            "workflow_artifacts": self._workflow_artifact_lineage(workflow_artifacts),
            "assets": assets,
            "precomputed_results": precomputed,
            "checkpoint": checkpoint,
            "result_uploads": result_uploads,
            "callback": callback,
            "expires_in": ttl,
        }

    def validate_workflow_artifacts(
        self,
        *,
        session_id: str,
        analysis_session_id: str,
        workflow_name: str,
        workflow_artifacts: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Resolve only whitelisted, same-analysis internal artifacts.

        This method intentionally does not accept an absolute path, storage
        key, or a legacy/NULL analysis scope.  It is called once on submission
        and again immediately before a worker obtains its input plan.
        """
        owner = str(session_id or "").strip()
        analysis = str(analysis_session_id or "").strip()
        workflow = str(workflow_name or "").strip()
        contract = WORKFLOW_ARTIFACT_CONTRACTS.get(workflow)
        if not owner or not analysis or contract is None:
            raise InputResolverError("This workflow artifact handoff requires an active tab analysis session.")
        if not isinstance(workflow_artifacts, list) or len(workflow_artifacts) != 1:
            raise InputResolverError("This workflow requires exactly one registered parent artifact.")
        reference = workflow_artifacts[0]
        if not isinstance(reference, dict):
            raise InputResolverError("Workflow artifact reference is malformed.")
        if str(reference.get("parent_type") or "") != contract["parent_type"]:
            raise InputResolverError("Workflow artifact parent type is not allowed for this workflow.")
        if str(reference.get("role") or "") != contract["role"]:
            raise InputResolverError("Workflow artifact role is not allowed for this workflow.")
        if contract["parent_type"] == "alignment_workflow":
            return [self._alignment_workflow_artifact(owner, analysis, reference)]
        return [self._job_workflow_artifact(owner, analysis, contract, reference)]

    def _workflow_artifact_assets(self, job: JobRecord) -> list[dict[str, Any]]:
        metadata = self._metadata(job)
        raw = metadata.get("workflow_artifacts")
        if raw in (None, ""):
            return []
        return self.validate_workflow_artifacts(
            session_id=str(job.session_id or ""),
            analysis_session_id=str(job.analysis_session_id or ""),
            workflow_name=str(job.workflow_name or job.workflow or ""),
            workflow_artifacts=raw if isinstance(raw, list) else [],
        )

    def _alignment_workflow_artifact(self, owner: str, analysis: str, reference: dict[str, Any]) -> dict[str, Any]:
        workflow_id = str(reference.get("parent_workflow_id") or "").strip()
        if not workflow_id:
            raise InputResolverError("Alignment workflow artifact is missing its parent workflow ID.")
        try:
            root = safe_session_child(
                Path(self.config.lab_result_root) / "sessions" / "owners",
                owner,
                "analysis_sessions",
                analysis,
                "workflows",
                workflow_id,
            )
        except Exception as exc:
            raise InputResolverError("Alignment workflow artifact reference is unsafe.") from exc
        state = self._read_json_object(root / "alignment_workflow_state.json")
        if (
            state.get("workflow_id") != workflow_id
            or state.get("owner_id") != owner
            or state.get("analysis_session_id") != analysis
            or str(state.get("step6_status") or "").lower() != "completed"
        ):
            raise InputResolverError("Alignment artifact is not a completed artifact of the current tab analysis.")
        lineage = state.get("input_provenance") if isinstance(state.get("input_provenance"), dict) else {}
        if not self._is_user_upload_pair(lineage):
            raise InputResolverError("KNN handoff accepts only Alignment results derived from user-uploaded ST and SM inputs.")
        manifest = self._read_json_object(root / "alignment_handoff_manifest.json")
        artifact = manifest.get("artifact") if isinstance(manifest.get("artifact"), dict) else {}
        if (
            manifest.get("parent_workflow_id") != workflow_id
            or manifest.get("owner_session_id") != owner
            or manifest.get("analysis_session_id") != analysis
            or artifact.get("role") != "aligned_sm_h5ad"
        ):
            raise InputResolverError("Alignment handoff manifest does not match the current analysis scope.")
        path = self._artifact_path(root, artifact)
        return self._artifact_asset(
            path=path,
            role="sm_aligned_h5ad",
            parent_type="alignment_workflow",
            parent_id=workflow_id,
            expected_sha256=str(artifact.get("sha256") or ""),
            lineage={"source_mode": "USER_UPLOAD", "inputs": self._safe_input_lineage(lineage)},
        )

    def _job_workflow_artifact(
        self,
        owner: str,
        analysis: str,
        contract: dict[str, str],
        reference: dict[str, Any],
    ) -> dict[str, Any]:
        if contract.get("parent_stage"):
            return self._multisample_prepared_artifact(owner, analysis, contract, reference)
        parent_job_id = str(reference.get("parent_job_id") or "").strip()
        if not parent_job_id:
            raise InputResolverError("KNN artifact is missing its parent job ID.")
        try:
            parent = self.database.get_job(
                parent_job_id,
                session_id=owner,
                analysis_session_id=analysis,
            )
        except KeyError as exc:
            raise InputResolverError("Parent KNN job is not available in the current tab analysis.") from exc
        if str(parent.workflow_name or parent.workflow or "") != contract.get("parent_workflow"):
            raise InputResolverError("Parent job workflow is not allowed for this handoff.")
        if str(parent.status or "").upper() not in {"SUCCEEDED", "COMPLETED"}:
            raise InputResolverError("Parent KNN job has not completed successfully.")
        stored_workspace = str(parent.local_workspace or "")
        workspace = (Path(self.workspace_path_mapper(stored_workspace)).resolve()
                     if self.workspace_path_mapper else Path(stored_workspace).resolve())
        allowed_root = Path(self.config.lab_result_root).resolve()
        if not workspace.is_dir() or (workspace != allowed_root and allowed_root not in workspace.parents):
            raise InputResolverError("Parent KNN artifact workspace is unavailable.")
        manifest = self._read_json_object(workspace / "knn_handoff_manifest.json")
        artifact = manifest.get("artifact") if isinstance(manifest.get("artifact"), dict) else {}
        if (
            manifest.get("parent_job_id") != parent_job_id
            or manifest.get("owner_session_id") != owner
            or manifest.get("analysis_session_id") != analysis
            or artifact.get("role") != "knn_joint_h5ad"
        ):
            raise InputResolverError("KNN handoff manifest does not match the current analysis scope.")
        lineage = manifest.get("input_lineage") if isinstance(manifest.get("input_lineage"), dict) else {}
        if str(lineage.get("source_mode") or "") != "USER_UPLOAD":
            raise InputResolverError("Integration handoff is not derived from the required user-upload Alignment chain.")
        path = self._artifact_path(workspace, artifact)
        return self._artifact_asset(
            path=path,
            role="joint_h5ad",
            parent_type="job",
            parent_id=parent_job_id,
            expected_sha256=str(artifact.get("sha256") or ""),
            lineage=self._safe_lineage(lineage),
        )

    def _multisample_prepared_artifact(self, owner, analysis, contract, reference):
        """Exact owner/analysis + successful QC + managed path + manifest SHA."""
        parent_id = str(reference.get("parent_job_id") or "").strip()
        if not parent_id:
            raise InputResolverError("Prepared input is missing its parent job ID.")
        try:
            parent = self.database.get_job(parent_id, session_id=owner, analysis_session_id=analysis)
        except KeyError as exc:
            raise InputResolverError("Prepared input is not available in this owner/analysis.") from exc
        if (str(parent.session_id or "") != owner or str(parent.analysis_session_id or "") != analysis
                or str(parent.status or "").upper() != "SUCCEEDED"
                or str(parent.workflow_name or parent.workflow or "") != contract["parent_workflow"]):
            raise InputResolverError("Prepared input parent scope/status/workflow does not match.")
        try:
            parameters = json.loads(parent.parameters_json or "{}")
        except (ValueError, TypeError) as exc:
            raise InputResolverError("Prepared input parameters are invalid.") from exc
        if parameters.get("stage") != contract["parent_stage"]:
            raise InputResolverError("Training requires completed QC/SVM, not a raw merge or training result.")
        # M03: require the registered publisher location and its exact owner/job.
        # The host GPU publisher uses owner__hostgpu to avoid rootless-container
        # directory ownership. Never guess a different directory on lookup failure.
        root = Path(self.config.lab_result_root).resolve()
        stored_workspace = str(parent.local_workspace or "").strip()
        if not stored_workspace:
            raise InputResolverError("Prepared input has no registered result workspace.")
        try:
            workspace = (Path(self.workspace_path_mapper(stored_workspace)).resolve()
                         if self.workspace_path_mapper else Path(stored_workspace).resolve())
            allowed = {
                safe_session_child(root / "sessions", owner, parent_id).resolve(),
                safe_session_child(root / "sessions", owner + "__hostgpu", parent_id).resolve(),
            }
        except (ValueError, RuntimeError) as exc:
            raise InputResolverError("Prepared input workspace mapping is invalid.") from exc
        if workspace not in allowed or root not in workspace.parents or not workspace.is_dir():
            raise InputResolverError("Prepared input workspace is unavailable.")
        summary = self._read_json_object(workspace / "merge_summary.json")
        if (summary.get("stage") != "qc" or summary.get("workflow_name") != contract["parent_workflow"]
                or summary.get("modality") != contract["modality"]):
            raise InputResolverError("Prepared input summary does not match its registered stage/workflow.")
        manifest = self._read_json_object(workspace / "result_manifest.json")
        item = self._prepared_manifest_entry(manifest)
        path = self._artifact_path(workspace, item)
        if int(item.get("size", -1)) != path.stat().st_size:
            raise InputResolverError("Prepared input size does not match its manifest.")
        return self._artifact_asset(path=path, role="joint_h5ad" if contract["modality"] == "joint" else "sm_h5ad",
            parent_type="job", parent_id=parent_id, expected_sha256=str(item.get("sha256") or ""),
            lineage={"source_mode": "MULTISAMPLE_PREPARED", "parent_job_id": parent_id, "analysis_session_id": analysis})

    @staticmethod
    def _prepared_manifest_entry(manifest: dict[str, Any]) -> dict[str, Any]:
        """Accept the worker and published manifest dialects, never a guessed file.

        progress_writer emits relative_path/size; ResultPublisher emits
        path/size_bytes. Publication replaces the worker manifest, so training
        must understand both. Conflicting aliases and duplicate entries are
        rejected rather than choosing whichever field happens to pass.
        """
        files = manifest.get("files")
        if not isinstance(files, list):
            raise InputResolverError("Prepared result manifest has an invalid files list.")
        entries = []
        for raw in files:
            if not isinstance(raw, dict):
                raise InputResolverError("Prepared result manifest has an invalid file entry.")
            paths = [raw[key] for key in ("relative_path", "path") if key in raw]
            if any(not isinstance(value, str) or not value for value in paths):
                raise InputResolverError("Prepared result manifest has an invalid file path.")
            if len(paths) == 2 and paths[0] != paths[1]:
                raise InputResolverError("Prepared result manifest has conflicting file paths.")
            if not paths or paths[0] != "integrated_result.h5ad":
                continue
            sizes = [raw[key] for key in ("size", "size_bytes") if key in raw]
            if not sizes or any(type(value) is not int or value <= 0 for value in sizes):
                raise InputResolverError("Prepared result manifest has an invalid H5AD size.")
            if len(sizes) == 2 and sizes[0] != sizes[1]:
                raise InputResolverError("Prepared result manifest has conflicting H5AD sizes.")
            entries.append({**raw, "relative_path": paths[0], "size": sizes[0]})
        if len(entries) != 1:
            raise InputResolverError("Prepared H5AD must occur exactly once in its result manifest.")
        return entries[0]

    @staticmethod
    def _read_json_object(path: Path) -> dict[str, Any]:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as exc:
            raise InputResolverError("Required workflow handoff metadata is unavailable.") from exc
        if not isinstance(data, dict):
            raise InputResolverError("Required workflow handoff metadata is malformed.")
        return data

    @staticmethod
    def _artifact_path(root: Path, artifact: dict[str, Any]) -> Path:
        relative = str(artifact.get("relative_path") or "").strip()
        candidate = Path(relative)
        if not relative or candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
            raise InputResolverError("Workflow artifact path is unsafe.")
        resolved_root = Path(root).resolve()
        path = (resolved_root / candidate).resolve()
        if resolved_root not in path.parents or path.suffix.lower() != ".h5ad" or not path.is_file():
            raise InputResolverError("Registered workflow artifact is unavailable.")
        return path

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _artifact_asset(
        self,
        *,
        path: Path,
        role: str,
        parent_type: str,
        parent_id: str,
        expected_sha256: str,
        lineage: dict[str, Any],
    ) -> dict[str, Any]:
        actual_sha256 = self._sha256_file(path)
        if not expected_sha256 or actual_sha256.lower() != expected_sha256.lower():
            raise InputResolverError("Registered workflow artifact failed SHA256 validation.")
        return {
            "source": "workflow_artifact",
            "role": role,
            "filename": path.name,
            "size_bytes": int(path.stat().st_size),
            "sha256": actual_sha256,
            "content_type": "application/x-hdf5",
            "read_only": True,
            "local_path": str(path),
            "parent_type": parent_type,
            "parent_id": parent_id,
            "lineage": self._safe_lineage(lineage),
        }

    @staticmethod
    def _is_user_upload_pair(lineage: dict[str, Any]) -> bool:
        return all(
            isinstance(lineage.get(key), dict)
            and str(lineage[key].get("source_mode") or "").upper() == "USER_UPLOAD"
            for key in ("st", "sm")
        )

    @staticmethod
    def _safe_input_lineage(lineage: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key in ("st", "sm"):
            item = lineage.get(key) if isinstance(lineage.get(key), dict) else {}
            result[key] = {
                "source_mode": str(item.get("source_mode") or ""),
                "reference": str(item.get("reference") or ""),
                "filename": str(item.get("filename") or ""),
                "sha256": str(item.get("sha256") or ""),
                "size_bytes": int(item.get("size_bytes") or 0),
            }
        return result

    @staticmethod
    def _safe_lineage(lineage: dict[str, Any]) -> dict[str, Any]:
        # Never carry workspace paths into a user-visible provenance contract.
        safe: dict[str, Any] = {}
        for key in ("source_mode", "parent_workflow_id", "parent_job_id", "analysis_session_id", "inputs"):
            value = lineage.get(key)
            if key == "inputs" and isinstance(value, dict):
                safe[key] = InputResolver._safe_input_lineage(value)
            elif isinstance(value, (str, int, float, bool)):
                safe[key] = value
        return safe

    @staticmethod
    def _workflow_artifact_lineage(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "source": "workflow_artifact",
                "role": str(item.get("role") or ""),
                "parent_type": str(item.get("parent_type") or ""),
                "parent_id": str(item.get("parent_id") or ""),
                "filename": str(item.get("filename") or ""),
                "sha256": str(item.get("sha256") or ""),
                "size_bytes": int(item.get("size_bytes") or 0),
                "lineage": InputResolver._safe_lineage(item.get("lineage") if isinstance(item.get("lineage"), dict) else {}),
            }
            for item in assets
        ]

    def resolve_example_action_binding(self, *, session_id: str, analysis_session_id: str, action_id: str, workflow_name: str = "") -> dict[str, Any]:
        try:
            record = self.database.get_example_action_binding(session_id=session_id, analysis_session_id=analysis_session_id, action_id=action_id)
        except KeyError as exc:
            raise InputResolverError("Example action binding was not found.") from exc
        metadata = self._binding_metadata(record)
        if not bool(record.get("ready")):
            raise InputResolverError("Example action binding is not ready.")
        components = metadata.get("components")
        if not isinstance(components, list):
            raise InputResolverError("Example action binding components are malformed.")
        assets = []
        static_files = []
        for component in components:
            if not isinstance(component, dict) or not component.get("ready"):
                continue
            object_key = str(component.get("object_key") or "").strip()
            if object_key:
                asset = self.example_assets.get_asset(object_key)
                entry = {
                    "source": "example_action",
                    "action_id": str(record.get("action_id") or ""),
                    "bundle_id": str(record.get("bundle_id") or ""),
                    "component_id": str(component.get("component_id") or ""),
                    "role": str(component.get("role") or ""),
                    "sample_id": str(component.get("sample_id") or ""),
                    "object_key": asset.object_key,
                    "filename": Path(asset.object_key).name,
                    "size_bytes": int(asset.size_bytes or 0),
                    "sha256": asset.sha256,
                    "content_type": asset.content_type,
                    "read_only": bool(asset.read_only),
                }
                if asset.local_path:
                    entry["local_path"] = asset.local_path
                assets.append(entry)
            elif component.get("static_path"):
                static_files.append(
                    {
                        "source": "example_action_static",
                        "action_id": str(record.get("action_id") or ""),
                        "bundle_id": str(record.get("bundle_id") or ""),
                        "component_id": str(component.get("component_id") or ""),
                        "role": str(component.get("role") or ""),
                        "sample_id": str(component.get("sample_id") or ""),
                        "static_path": str(component.get("static_path") or ""),
                        "filename": Path(str(component.get("static_path") or "")).name,
                        "size_bytes": int(component.get("size_bytes") or 0),
                        "sha256": str(component.get("sha256") or ""),
                        "content_type": "text/csv" if str(component.get("format") or "").lower() == "csv" else "application/octet-stream",
                    }
                )
        return {
            "input_resolver_version": INPUT_RESOLVER_VERSION,
            "input_source": "example_action",
            "session_id": str(session_id or ""),
            "action_id": str(record.get("action_id") or ""),
            "bundle_id": str(record.get("bundle_id") or ""),
            "workflow_name": str(workflow_name or ""),
            "manifest_version": str(record.get("manifest_version") or ""),
            "asset_version": str(record.get("asset_version") or ""),
            "sample_ids": self._json_list(record.get("sample_ids_json")),
            "bound_roles": self._json_list(record.get("bound_roles_json")),
            "available_workflows": self._json_list(record.get("available_workflows_json")),
            "assets": assets,
            "static_files": static_files,
        }

    def resolve_interactive_local_input(
        self,
        *,
        session_id: str,
        analysis_session_id: str,
        upload_id: str = "",
        action_id: str = "",
        input_role: str = "",
        workflow_name: str = "",
    ) -> dict[str, Any]:
        """Resolve one exact, analysis-scoped interactive input to a local path.

        This bridge is intentionally limited to Lab/local-object-storage pages that
        run an existing interactive calculation in the web process.  It does not
        relax worker input authorization: an upload is looked up with both its
        owner and analysis session, while an example is read through its exact
        analysis-scoped action binding.
        """
        owner = str(session_id or "").strip()
        analysis = str(analysis_session_id or "").strip()
        if not owner or not analysis:
            raise InputResolverError("An authenticated tab analysis session is required.")
        upload_id = str(upload_id or "").strip()
        action_id = str(action_id or "").strip()
        if bool(upload_id) == bool(action_id):
            raise InputResolverError("Specify exactly one uploaded input or example action.")

        if upload_id:
            upload = self.database.get_upload(
                upload_id,
                session_id=owner,
                analysis_session_id=analysis,
            )
            if upload.status != UploadStatus.COMPLETED.value:
                raise InputResolverError("The selected upload is not complete.")
            return self._interactive_local_entry(
                source="upload",
                object_key=upload.object_key,
                filename=upload.safe_filename,
                upload_id=upload.upload_id,
                size_bytes=int(upload.actual_size_bytes or upload.declared_size_bytes or 0),
                sha256=str(upload.sha256 or ""),
            )

        plan = self.resolve_example_action_binding(
            session_id=owner,
            analysis_session_id=analysis,
            action_id=action_id,
            workflow_name=workflow_name,
        )
        role = str(input_role or "").strip()
        candidates = [
            item for item in [*plan.get("assets", []), *plan.get("static_files", [])]
            if not role or str(item.get("role") or "") == role
        ]
        if len(candidates) != 1:
            raise InputResolverError("The example action does not resolve to one usable input.")
        entry = candidates[0]
        local_path = str(entry.get("local_path") or entry.get("static_path") or "").strip()
        if not local_path:
            raise InputResolverError("This example input is not available to the local interactive runtime.")
        path = Path(local_path).resolve()
        if not path.is_file():
            raise InputResolverError("The resolved example input is unavailable.")
        return {
            "source": "example_action",
            "input_source_mode": "EXAMPLE",
            "action_id": action_id,
            "role": str(entry.get("role") or ""),
            "filename": str(entry.get("filename") or path.name),
            "local_path": str(path),
            "size_bytes": int(entry.get("size_bytes") or 0),
            "sha256": str(entry.get("sha256") or ""),
        }

    def _interactive_local_entry(
        self,
        *,
        source: str,
        object_key: str,
        filename: str,
        upload_id: str = "",
        size_bytes: int = 0,
        sha256: str = "",
    ) -> dict[str, Any]:
        path_factory = getattr(self.storage, "_object_path", None)
        if not callable(path_factory):
            raise InputResolverError("Interactive local input resolution is unavailable for this storage backend.")
        path = Path(path_factory(object_key)).resolve()
        if not path.is_file():
            raise InputResolverError("The resolved upload object is unavailable.")
        return {
            "source": source,
            "input_source_mode": "USER_UPLOAD",
            "upload_id": str(upload_id or ""),
            "object_key": str(object_key or ""),
            "filename": str(filename or path.name),
            "local_path": str(path),
            "size_bytes": int(size_bytes or 0),
            "sha256": str(sha256 or ""),
        }

    def resolve_input(
        self,
        *,
        session_id: str,
        analysis_session_id: str,
        input_role: str,
        workflow_name: str = "",
        action_id: str,
    ) -> list[dict[str, Any]]:
        plan = self.resolve_example_action_binding(
            session_id=session_id,
            analysis_session_id=str(analysis_session_id or ""),
            action_id=action_id,
            workflow_name=workflow_name,
        )
        role = str(input_role or "").strip()
        return [
            item
            for item in [*plan.get("assets", []), *plan.get("static_files", [])]
            if str(item.get("role") or "") == role
        ]

    def _upload_assets(self, job: JobRecord, *, ttl: int) -> list[dict[str, Any]]:
        assets: list[dict[str, Any]] = []
        metadata = self._metadata(job)
        raw_roles = metadata.get("input_asset_roles")
        upload_roles = raw_roles if isinstance(raw_roles, dict) else {}
        try:
            upload_ids = json.loads(job.input_upload_ids_json or "[]")
        except Exception:
            upload_ids = []
        if not isinstance(upload_ids, list):
            return assets
        for upload_id in upload_ids:
            upload = self.database.get_upload(str(upload_id), session_id=job.session_id, analysis_session_id=str(job.analysis_session_id or ""))
            if upload.status != UploadStatus.COMPLETED.value:
                raise InputResolverError("Worker input upload is not completed.")
            assets.append(
                {
                    "source": "upload",
                    "upload_id": upload.upload_id,
                    # Upload ownership remains immutable; this role is an
                    # exact workflow input contract recorded at submission.
                    "role": str(upload_roles.get(str(upload.upload_id)) or ""),
                    "object_key": upload.object_key,
                    "filename": upload.safe_filename,
                    "size_bytes": int(upload.actual_size_bytes or upload.declared_size_bytes or 0),
                    "sha256": upload.sha256 or "",
                    "content_type": upload.content_type,
                    "url": self.storage.create_presigned_download_url(
                        object_key=upload.object_key,
                        expires_seconds=ttl,
                        filename=upload.safe_filename,
                    ),
                }
            )
        return assets

    def _result_upload_targets(self, job: JobRecord, *, ttl: int) -> list[dict[str, Any]]:
        if self.config.is_lab_profile:
            return []
        metadata = self._metadata(job)
        expected = metadata.get("expected_outputs")
        expected_outputs = [str(item) for item in expected] if isinstance(expected, list) else []
        if "result_manifest.json" not in expected_outputs:
            expected_outputs.append("result_manifest.json")
        if "results.zip" not in expected_outputs:
            expected_outputs.append("results.zip")
        targets = []
        seen: set[str] = set()
        for relative_path in expected_outputs:
            filename = Path(relative_path).name
            if not filename or filename in seen:
                continue
            seen.add(filename)
            object_key = ObjectKeyBuilder.result_object(str(job.session_id or job.user_id), job.job_id, filename)
            targets.append(
                {
                    "relative_path": relative_path,
                    "filename": filename,
                    "object_key": object_key,
                    "method": "PUT",
                    "content_type": self._content_type(filename),
                    "url": self.storage.create_presigned_put_url(
                        object_key=object_key,
                        expires_seconds=ttl,
                        content_type=self._content_type(filename),
                        metadata={"job_id": job.job_id, "session_id": str(job.session_id or "")},
                    ),
                }
            )
        return targets

    def _checkpoint_contract(self, job: JobRecord, *, ttl: int) -> dict[str, Any]:
        if self.config.is_lab_profile:
            return {"restore": [], "upload": {}}
        metadata = self._metadata(job)
        model = metadata.get("model") if isinstance(metadata.get("model"), dict) else {}
        checkpoint_filename = str(model.get("checkpoint_filename") or "latest_checkpoint.pt")
        object_key = ObjectKeyBuilder.checkpoint_object(str(job.session_id or job.user_id), job.job_id, checkpoint_filename)
        restore = []
        for key in self.storage.list_prefix(ObjectKeyBuilder.checkpoint_prefix(str(job.session_id or job.user_id), job.job_id)):
            restore.append(
                {
                    "object_key": key,
                    "filename": Path(key).name,
                    "url": self.storage.create_presigned_download_url(object_key=key, expires_seconds=ttl, filename=Path(key).name),
                }
            )
        return {
            "restore": restore,
            "upload": {
                "object_key": object_key,
                "filename": checkpoint_filename,
                "method": "PUT",
                "url": self.storage.create_presigned_put_url(
                    object_key=object_key,
                    expires_seconds=min(ttl, int(self.config.worker_checkpoint_ttl_seconds)),
                    content_type="application/octet-stream",
                    metadata={"job_id": job.job_id, "kind": "checkpoint"},
                ),
            },
        }

    def _callback_contract(self, job: JobRecord, *, expires_at: int | None = None) -> dict[str, Any]:
        expires_at = int(expires_at or (int(time.time()) + int(self.config.worker_callback_token_ttl_seconds)))
        token = sign_worker_callback_token(job, expires_at=expires_at, config=self.config)
        base = (self.config.public_base_url or self.config.public_origin or "").rstrip("/")
        path = f"/api/jobs/{job.job_id}/worker-callback"
        return {
            "url": f"{base}{path}" if base else path,
            "token": token,
            "expires_at": expires_at,
            "header": "X-SpaShiny-Callback-Token",
        }

    def _url_ttl(self) -> int:
        values = [
            int(self.config.r2_presigned_url_ttl_seconds or 900),
            int(self.config.worker_signed_url_ttl_seconds or 600),
        ]
        return max(60, min(values))

    def _example_action_assets(self, job: JobRecord, *, ttl: int) -> list[dict[str, Any]]:
        metadata = self._metadata(job)
        binding = metadata.get("session_input_binding") if isinstance(metadata.get("session_input_binding"), dict) else {}
        action_id = str(binding.get("example_action_id") or metadata.get("example_action_id") or "").strip()
        if not action_id:
            raise InputResolverError("Job metadata is missing example_action_id.")
        plan = self.resolve_example_action_binding(
            session_id=str(job.session_id or ""),
            analysis_session_id=str(job.analysis_session_id or ""),
            action_id=action_id,
            workflow_name=job.workflow_name or job.workflow,
        )
        available = {str(item) for item in plan.get("available_workflows") or []}
        workflow = str(job.workflow_name or job.workflow or "")
        if available and workflow not in available:
            raise InputResolverError("Example action binding is not compatible with this workflow.")
        return [dict(item) for item in plan.get("assets") or []]

    def _materialized_input_dir(self, job: JobRecord, metadata: dict[str, Any]) -> str:
        binding = metadata.get("session_input_binding") if isinstance(metadata.get("session_input_binding"), dict) else {}
        explicit = str(binding.get("materialized_input_dir") or metadata.get("materialized_input_dir") or "").strip()
        if explicit:
            return explicit
        if self.config.is_lab_profile and job.session_id:
            return str(safe_session_child(Path(self.config.lab_data_root) / "sessions", str(job.session_id), "inputs", job.job_id))
        return ""

    def _metadata(self, job: JobRecord) -> dict[str, Any]:
        try:
            data = json.loads(job.metadata_json or "{}")
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _runtime_profile(self, job: JobRecord) -> str:
        workflow = job.workflow_name or job.workflow
        try:
            spec = get_workflow_spec(workflow)
        except ValueError as exc:
            raise InputResolverError(f"Unsupported workflow for worker input resolution: {workflow}") from exc
        if spec.resource_type != "gpu":
            return ""
        return str(spec.runtime_profile or "spatialmeta")

    def _binding_metadata(self, record: dict[str, Any]) -> dict[str, Any]:
        try:
            data = json.loads(str(record.get("metadata_json") or "{}"))
        except Exception as exc:
            raise InputResolverError("Example action binding metadata is not valid JSON.") from exc
        if not isinstance(data, dict):
            raise InputResolverError("Example action binding metadata must be an object.")
        return data

    @staticmethod
    def _json_list(value: Any) -> list[str]:
        try:
            data = json.loads(str(value or "[]"))
        except Exception:
            return []
        if not isinstance(data, list):
            return []
        return [str(item) for item in data if str(item).strip()]

    @staticmethod
    def _content_type(filename: str) -> str:
        suffix = Path(filename).suffix.lower()
        if suffix == ".json":
            return "application/json"
        if suffix == ".zip":
            return "application/zip"
        if suffix == ".csv":
            return "text/csv"
        if suffix == ".txt":
            return "text/plain"
        return "application/octet-stream"


def sign_worker_callback_token(job: JobRecord, *, expires_at: int, config: SpaShinyCloudConfig) -> str:
    payload = {
        "job_id": job.job_id,
        "worker_id": job.worker_id,
        "claim_token_sha256": hashlib.sha256(str(job.claim_token or "").encode("utf-8")).hexdigest(),
        "exp": int(expires_at),
        "purpose": "spashiny_worker_callback",
    }
    body = _b64(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(_callback_secret(config), body.encode("ascii"), hashlib.sha256).digest()
    return body + "." + _b64(sig)


def sign_worker_job_spec_token(job: JobRecord, *, expires_at: int, config: SpaShinyCloudConfig) -> str:
    payload = {
        "job_id": job.job_id,
        "worker_id": job.worker_id,
        "claim_token_sha256": hashlib.sha256(str(job.claim_token or "").encode("utf-8")).hexdigest(),
        "exp": int(expires_at),
        "purpose": "spashiny_worker_job_spec",
    }
    body = _b64(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(_callback_secret(config), body.encode("ascii"), hashlib.sha256).digest()
    return body + "." + _b64(sig)


def verify_worker_job_spec_token(token: str, job: JobRecord, *, config: SpaShinyCloudConfig) -> int:
    payload = _verify_signed_worker_token(token, job, config=config, purpose="spashiny_worker_job_spec")
    return int(payload["exp"])


def verify_worker_callback_token(token: str, job: JobRecord, *, config: SpaShinyCloudConfig) -> None:
    _verify_signed_worker_token(token, job, config=config, purpose="spashiny_worker_callback")


def _verify_signed_worker_token(token: str, job: JobRecord, *, config: SpaShinyCloudConfig, purpose: str) -> dict[str, Any]:
    try:
        body, signature = str(token or "").split(".", 1)
    except ValueError as exc:
        raise InputResolverError("Invalid worker token.") from exc
    expected = _b64(hmac.new(_callback_secret(config), body.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        raise InputResolverError("Invalid worker token signature.")
    try:
        payload = json.loads(base64.urlsafe_b64decode(_pad_b64(body)).decode("utf-8"))
    except Exception as exc:
        raise InputResolverError("Invalid worker token payload.") from exc
    if int(payload.get("exp") or 0) < int(time.time()):
        raise InputResolverError("Worker token has expired.")
    if payload.get("purpose") != purpose:
        raise InputResolverError("Worker token purpose is invalid.")
    if payload.get("job_id") != job.job_id or payload.get("worker_id") != job.worker_id:
        raise InputResolverError("Worker token does not match this job.")
    expected_claim = hashlib.sha256(str(job.claim_token or "").encode("utf-8")).hexdigest()
    if payload.get("claim_token_sha256") != expected_claim:
        raise InputResolverError("Worker token does not match this claim.")
    return payload


def _callback_secret(config: SpaShinyCloudConfig) -> bytes:
    secret = config.session_hmac_secret or "spashiny-local-dev-callback-secret"
    return str(secret).encode("utf-8")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _pad_b64(value: str) -> bytes:
    return (value + ("=" * (-len(value) % 4))).encode("ascii")
