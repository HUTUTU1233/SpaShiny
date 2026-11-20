from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import SpaShinyCloudConfig, load_cloud_config
from .database import CloudDatabase
from .example_assets import ExampleAssetService
from .lab_runtime import safe_session_child
from .models import JobRecord, UploadStatus
from .object_keys import ObjectKeyBuilder
from .storage_backends import TemporaryObjectStorage, get_temporary_object_storage
from .workflow_registry import get_workflow_spec


INPUT_RESOLVER_VERSION = "session_input_binding_v1"


class InputResolverError(RuntimeError):
    pass


@dataclass
class InputResolver:
    database: CloudDatabase | None = None
    config: SpaShinyCloudConfig | None = None
    storage: TemporaryObjectStorage | None = None
    example_assets: ExampleAssetService | None = None

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
            "assets": assets,
            "precomputed_results": precomputed,
            "checkpoint": checkpoint,
            "result_uploads": result_uploads,
            "callback": callback,
            "expires_in": ttl,
        }

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

    def resolve_input(
        self,
        *,
        session_id: str,
        input_role: str,
        workflow_name: str = "",
        action_id: str,
    ) -> list[dict[str, Any]]:
        plan = self.resolve_example_action_binding(
            session_id=session_id,
            analysis_session_id=str(job.analysis_session_id or ""),
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
