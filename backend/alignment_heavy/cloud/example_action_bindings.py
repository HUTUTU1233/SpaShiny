from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT, SpaShinyCloudConfig, load_cloud_config
from .database import CloudDatabase
from .example_action_registry import ExampleActionRegistry, ExampleActionRegistryError
from .example_assets import ExampleAssetAccessError, ExampleAssetError, ExampleAssetService
from .session_manager import SessionRecord


class ExampleActionError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = int(status_code)


@dataclass
class ExampleActionBindingService:
    database: CloudDatabase | None = None
    config: SpaShinyCloudConfig | None = None
    example_assets: ExampleAssetService | None = None
    registry: ExampleActionRegistry | None = None

    def __post_init__(self) -> None:
        if self.config is None:
            self.config = load_cloud_config()
        if self.database is None:
            self.database = CloudDatabase(config=self.config)
        if self.example_assets is None:
            self.example_assets = ExampleAssetService(config=self.config)
        if self.registry is None:
            self.registry = ExampleActionRegistry()

    def activate(self, *, session: SessionRecord, action_id: str, page_name: str = "") -> dict[str, Any]:
        if session.status != "ACTIVE":
            raise ExampleActionError("SESSION_EXPIRED", "Session is not active.", status_code=410)
        try:
            action = self.registry.get_action(action_id)
            bundle = self.registry.get_bundle(str(action.get("bundle_id") or ""))
        except ExampleActionRegistryError as exc:
            raise ExampleActionError("EXAMPLE_ACTION_NOT_FOUND", str(exc), status_code=404) from exc

        requested_page = str(page_name or "").strip()
        action_page = str(action.get("page_name") or "").strip()
        eligible_pages = [str(item) for item in (bundle.get("eligible_pages") or []) if str(item).strip()]
        if requested_page and requested_page not in {action_page, *eligible_pages}:
            raise ExampleActionError(
                "EXAMPLE_ACTION_PAGE_MISMATCH",
                "Example action is not available on this page.",
                status_code=409,
            )
        page = requested_page or action_page

        manifest = self.registry.load_manifest()
        required_roles = [str(item) for item in (action.get("required_roles") or []) if str(item).strip()]
        optional_roles = [str(item) for item in (action.get("optional_roles") or []) if str(item).strip()]
        components = [dict(item) for item in (bundle.get("components") or []) if isinstance(item, dict)]

        validated_components: list[dict[str, Any]] = []
        ready_roles: set[str] = set()
        missing_roles: set[str] = set()
        object_keys: list[str] = []
        static_paths: list[str] = []
        for component in components:
            role = str(component.get("role") or "").strip()
            status = self._validate_component(component)
            internal = self._component_internal_record(component, status=status)
            validated_components.append(internal)
            if status["ready"]:
                ready_roles.add(role)
                if internal.get("object_key"):
                    object_keys.append(str(internal["object_key"]))
                if internal.get("static_path"):
                    static_paths.append(str(internal["static_path"]))
            elif role:
                missing_roles.add(role)

        for role in required_roles:
            if role not in ready_roles:
                missing_roles.add(role)

        ready = not missing_roles and str(bundle.get("completeness_status") or "").lower() == "complete"
        sample_ids = self._unique_ordered(str(item) for item in (bundle.get("sample_ids") or []))
        if not sample_ids:
            sample_ids = self._unique_ordered(str(item.get("sample_id") or "") for item in components)
        bound_roles = self._unique_ordered(role for role in [*required_roles, *optional_roles] if role in ready_roles)
        if not bound_roles:
            bound_roles = self._unique_ordered(role for role in ready_roles)
        available_workflows = self._unique_ordered(
            str(item) for item in (action.get("available_workflows") or bundle.get("eligible_workflows") or [])
        )
        message = str(action.get("user_message") or action.get("display_name") or action_id)
        if not ready:
            message = "Example inputs are not ready because required roles are unavailable."

        metadata = {
            "binding_version": "example_action_binding_v1",
            "action_id": str(action.get("action_id") or action_id),
            "bundle_id": str(bundle.get("bundle_id") or ""),
            "display_name": str(action.get("display_name") or bundle.get("display_name") or action_id),
            "page_name": page,
            "required_roles": required_roles,
            "optional_roles": optional_roles,
            "components": validated_components,
            "object_keys": object_keys,
            "static_paths": static_paths,
            "asset_bucket": manifest.get("asset_bucket") or self.example_assets.bucket,
            "asset_manifest_key": manifest.get("asset_manifest_key") or self.example_assets.manifest_key,
        }
        values = {
            "session_id": session.session_id,
            "action_id": str(action.get("action_id") or action_id),
            "page_name": page,
            "bundle_id": str(bundle.get("bundle_id") or ""),
            "manifest_version": str(manifest.get("manifest_version") or ""),
            "asset_version": str(manifest.get("asset_version") or ""),
            "ready": int(bool(ready)),
            "bound_roles_json": json.dumps(bound_roles, ensure_ascii=False),
            "missing_roles_json": json.dumps(sorted(missing_roles), ensure_ascii=False),
            "sample_ids_json": json.dumps(sample_ids, ensure_ascii=False),
            "available_workflows_json": json.dumps(available_workflows, ensure_ascii=False),
            "metadata_json": json.dumps(metadata, ensure_ascii=False, sort_keys=True),
        }
        self.database.create_or_update_example_action_binding(values)

        return {
            "action_id": str(action.get("action_id") or action_id),
            "page_name": page,
            "ready": bool(ready),
            "sample_ids": sample_ids,
            "bound_roles": bound_roles,
            "missing_roles": sorted(missing_roles),
            "message": message,
            "user_message": message,
            "available_workflows": available_workflows,
        }

    def binding_for_session(self, *, session_id: str, action_id: str) -> dict[str, Any]:
        try:
            return self.database.get_example_action_binding(session_id=session_id, action_id=action_id)
        except KeyError as exc:
            raise ExampleActionError("EXAMPLE_ACTION_BINDING_NOT_FOUND", "Example action binding was not found.", status_code=404) from exc

    def _validate_component(self, component: dict[str, Any]) -> dict[str, Any]:
        object_key = str(component.get("object_key") or "").strip()
        if object_key:
            return self._validate_r2_component(component, object_key=object_key)
        return self._validate_static_component(component)

    def _validate_r2_component(self, component: dict[str, Any], *, object_key: str) -> dict[str, Any]:
        try:
            asset = self.example_assets.get_asset(object_key)
        except ExampleAssetAccessError:
            return {"ready": False, "source": self._asset_source_label(), "code": "ASSET_NOT_ALLOWLISTED"}
        except ExampleAssetError:
            return {"ready": False, "source": self._asset_source_label(), "code": "ASSET_MANIFEST_UNAVAILABLE"}
        expected_size = int(component.get("size_bytes") or 0)
        expected_sha = str(component.get("sha256") or "").strip().lower()
        if expected_size and int(asset.size_bytes or 0) != expected_size:
            return {"ready": False, "source": self._asset_source_label(), "code": "ASSET_SIZE_MISMATCH"}
        if expected_sha and str(asset.sha256 or "").lower() != expected_sha:
            return {"ready": False, "source": self._asset_source_label(), "code": "ASSET_SHA256_MISMATCH"}
        return {
            "ready": True,
            "source": self._asset_source_label(),
            "asset_id": asset.asset_id,
            "size_bytes": int(asset.size_bytes or expected_size or 0),
            "sha256": asset.sha256,
            "content_type": asset.content_type,
            "local_path": asset.local_path,
            "read_only": bool(asset.read_only),
        }

    def _validate_static_component(self, component: dict[str, Any]) -> dict[str, Any]:
        relative = str(component.get("static_path") or "").strip()
        if not relative:
            return {"ready": False, "source": "static_file", "code": "STATIC_PATH_MISSING"}
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            return {"ready": False, "source": "static_file", "code": "STATIC_PATH_FORBIDDEN"}
        path = PROJECT_ROOT / relative
        if not path.is_file():
            return {"ready": False, "source": "static_file", "code": "STATIC_FILE_MISSING"}
        expected_size = int(component.get("size_bytes") or 0)
        expected_sha = str(component.get("sha256") or "").strip().lower()
        actual_size = path.stat().st_size
        if expected_size and actual_size != expected_size:
            return {"ready": False, "source": "static_file", "code": "STATIC_SIZE_MISMATCH"}
        if expected_sha:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest.lower() != expected_sha:
                return {"ready": False, "source": "static_file", "code": "STATIC_SHA256_MISMATCH"}
        return {
            "ready": True,
            "source": "static_file",
            "size_bytes": actual_size,
            "sha256": expected_sha,
            "content_type": "text/csv" if path.suffix.lower() == ".csv" else "application/octet-stream",
        }

    @staticmethod
    def _component_internal_record(component: dict[str, Any], *, status: dict[str, Any]) -> dict[str, Any]:
        keys = [
            "component_id",
            "role",
            "sample_id",
            "object_key",
            "static_path",
            "format",
            "size_bytes",
            "sha256",
            "modality",
            "polarity",
            "paired_component_id",
            "content_version",
        ]
        data = {key: component.get(key) for key in keys if component.get(key) not in (None, "")}
        data["ready"] = bool(status.get("ready"))
        data["source"] = str(status.get("source") or "")
        if status.get("asset_id"):
            data["asset_id"] = str(status["asset_id"])
        if status.get("code"):
            data["code"] = str(status["code"])
        if status.get("local_path"):
            data["local_path"] = str(status["local_path"])
        if status.get("read_only"):
            data["read_only"] = bool(status["read_only"])
        return data

    def _asset_source_label(self) -> str:
        return "local_example_asset" if self.config and self.config.is_lab_profile else "r2_asset"

    @staticmethod
    def _unique_ordered(items) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            value = str(item or "").strip()
            if value and value not in seen:
                seen.add(value)
                result.append(value)
        return result
