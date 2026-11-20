from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from .config import SpaShinyCloudConfig, load_cloud_config
from .database import CloudDatabase, ExampleReferenceScopeConflict, utc_now
from .example_assets import ExampleAsset, ExampleAssetAccessError, ExampleAssetError, ExampleAssetService
from .session_manager import SessionRecord


class ExampleAssetReferenceError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = int(status_code)


@dataclass
class ExampleAssetReferenceService:
    database: CloudDatabase | None = None
    config: SpaShinyCloudConfig | None = None
    example_assets: ExampleAssetService | None = None

    def __post_init__(self) -> None:
        if self.config is None:
            self.config = load_cloud_config()
        if self.database is None:
            self.database = CloudDatabase(config=self.config)
        if self.example_assets is None:
            self.example_assets = ExampleAssetService(config=self.config)

    def create(
        self,
        *,
        session: SessionRecord,
        analysis_session_id: str,
        asset_id: str | None = None,
        asset_object_key: str | None = None,
    ) -> dict[str, Any]:
        self._require_active_session(session)
        self._require_analysis(session.session_id, analysis_session_id)
        asset = self._resolve_asset(asset_id=asset_id, asset_object_key=asset_object_key)
        assert self.example_assets is not None
        manifest = self.example_assets.load_manifest()
        associated_keys = self.example_assets.associated_object_keys(asset.object_key)
        values = {
                "reference_id": "ear_" + uuid.uuid4().hex,
                "session_id": session.session_id,
                "analysis_session_id": analysis_session_id,
                "reference_type": "example_asset",
                "asset_id": asset.asset_id,
                "asset_version": self.example_assets.asset_version,
                "manifest_version": str(manifest.get("manifest_version") or ""),
                "object_key": asset.object_key,
                "asset_object_keys_json": json.dumps(associated_keys, ensure_ascii=False, sort_keys=True),
                "display_name": asset.display_name,
                "eligible_workflows_json": json.dumps(list(asset.applicable_workflows), ensure_ascii=False, sort_keys=True),
                "modality": asset.modality,
                "file_format": asset.file_format,
                "size_bytes": int(asset.size_bytes),
                "species": asset.species,
                "created_at": utc_now(),
                "metadata_json": json.dumps(self._metadata(asset), ensure_ascii=False, sort_keys=True),
            }
        try:
            record = self.database.create_or_get_example_asset_reference(values)
        except ExampleReferenceScopeConflict as exc:
            raise ExampleAssetReferenceError("EXAMPLE_REFERENCE_SCOPE_CONFLICT", str(exc), status_code=409) from exc
        return self.public_reference(record)

    def list_public(self, session_id: str, *, analysis_session_id: str) -> list[dict[str, Any]]:
        self._require_analysis(session_id, analysis_session_id)
        return [self.public_reference(record) for record in self.database.list_example_asset_references(session_id=session_id, analysis_session_id=analysis_session_id)]

    def get_for_job_submission(self, *, session_id: str, analysis_session_id: str, reference_id: str, workflow_name: str) -> dict[str, Any]:
        self._require_analysis(session_id, analysis_session_id)
        try:
            record = self.database.get_example_asset_reference(reference_id, session_id=session_id, analysis_session_id=analysis_session_id)
        except KeyError as exc:
            raise ExampleAssetReferenceError("ASSET_REFERENCE_NOT_FOUND", "Example asset reference was not found.", status_code=404) from exc
        if record["session_id"] != session_id:
            raise ExampleAssetReferenceError("ASSET_REFERENCE_FORBIDDEN", "Example asset reference belongs to another session.", status_code=403)
        if record["reference_type"] != "example_asset":
            raise ExampleAssetReferenceError("INVALID_ASSET_REFERENCE", "Asset reference type is not supported.", status_code=422)
        asset = self._resolve_asset(asset_id=str(record["asset_id"]), asset_object_key=None)
        if asset.object_key != record["object_key"]:
            raise ExampleAssetReferenceError("ASSET_NOT_ALLOWLISTED", "Example asset reference is no longer in the current manifest.", status_code=403)
        eligible = self._json_list(record.get("eligible_workflows_json"))
        if workflow_name not in eligible:
            raise ExampleAssetReferenceError("ASSET_WORKFLOW_NOT_ALLOWED", "Selected workflow is not allowed for this example asset.", status_code=409)
        return record

    def _require_analysis(self, session_id: str, analysis_session_id: str) -> None:
        if not str(session_id or "").strip() or not str(analysis_session_id or "").strip():
            raise ExampleAssetReferenceError("ANALYSIS_SESSION_REQUIRED", "Example references require an explicit current analysis.", status_code=400)
        try:
            record = self.database.get_analysis_session(analysis_session_id, owner_session_id=session_id)
        except KeyError as exc:
            raise ExampleAssetReferenceError("ANALYSIS_SESSION_FORBIDDEN", "The analysis does not belong to this owner.", status_code=403) from exc
        if str(record.get("status") or "") != "ACTIVE":
            raise ExampleAssetReferenceError("ANALYSIS_SESSION_ENDED", "The selected analysis has ended.", status_code=409)

    def object_keys_for_references(self, records: list[dict[str, Any]]) -> list[str]:
        keys: list[str] = []
        for record in records:
            for key in self._json_list(record.get("asset_object_keys_json")) or [str(record["object_key"])]:
                if key not in keys:
                    keys.append(key)
        return keys

    def public_reference(self, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "reference_id": record["reference_id"],
            "analysis_session_id": record["analysis_session_id"],
            "asset_id": record["asset_id"],
            "display_name": record["display_name"],
            "reference_type": "example_asset",
            "eligible_workflows": self._json_list(record.get("eligible_workflows_json")),
            "manifest_version": record.get("manifest_version") or "",
            "modality": record.get("modality") or "",
            "file_format": record.get("file_format") or "",
            "size_bytes": int(record.get("size_bytes") or 0),
            "species": record.get("species") or "",
            "created_at": record.get("created_at") or "",
        }

    def _resolve_asset(self, *, asset_id: str | None, asset_object_key: str | None) -> ExampleAsset:
        assert self.example_assets is not None
        try:
            if asset_id:
                return self.example_assets.get_asset_by_id(asset_id)
            if asset_object_key:
                return self.example_assets.get_asset(asset_object_key)
        except ExampleAssetAccessError as exc:
            raise ExampleAssetReferenceError("ASSET_NOT_ALLOWLISTED", str(exc), status_code=403) from exc
        except ExampleAssetError as exc:
            raise ExampleAssetReferenceError("ASSET_MANIFEST_UNAVAILABLE", str(exc), status_code=503) from exc
        raise ExampleAssetReferenceError("INVALID_REQUEST_PAYLOAD", "Request must include asset_id.", status_code=422)

    @staticmethod
    def _require_active_session(session: SessionRecord) -> None:
        if session.status != "ACTIVE":
            raise ExampleAssetReferenceError("SESSION_EXPIRED", "Session is not active.", status_code=410)

    @staticmethod
    def _json_list(value: Any) -> list[str]:
        try:
            data = json.loads(str(value or "[]"))
        except Exception:
            return []
        if not isinstance(data, list):
            return []
        return [str(item) for item in data if str(item)]

    @staticmethod
    def _metadata(asset: ExampleAsset) -> dict[str, Any]:
        return {
            "source_database": asset.source_database,
            "source_record_doi": asset.source_record_doi,
            "publication_doi": asset.publication_doi,
            "citation_required": asset.citation_required,
        }
