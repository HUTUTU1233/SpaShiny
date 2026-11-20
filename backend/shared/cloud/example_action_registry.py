from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_EXAMPLE_ACTION_MANIFEST = Path(__file__).with_name("example_bundle_manifest.json")


class ExampleActionRegistryError(ValueError):
    pass


class ExampleActionRegistry:
    """Loads the explicit page-level example action manifest.

    This registry is intentionally static and manifest-backed. Page buttons bind
    to action IDs from this file; the web app never discovers example objects by
    scanning R2 or local directories.
    """

    def __init__(self, manifest_path: Path | None = None, manifest: dict[str, Any] | None = None) -> None:
        self.manifest_path = Path(manifest_path) if manifest_path is not None else DEFAULT_EXAMPLE_ACTION_MANIFEST
        self._provided_manifest = manifest
        self._cache: dict[str, Any] | None = None

    def load_manifest(self, *, force: bool = False) -> dict[str, Any]:
        if self._cache is not None and not force:
            return self._cache
        if self._provided_manifest is not None:
            manifest = json.loads(json.dumps(self._provided_manifest, ensure_ascii=False))
        else:
            manifest = json.loads(self.manifest_path.read_text(encoding="utf-8-sig"))
        self._validate_manifest(manifest)
        self._cache = manifest
        return manifest

    def action_map(self) -> dict[str, dict[str, Any]]:
        return {str(item["action_id"]): item for item in self.load_manifest().get("actions", [])}

    def bundle_map(self) -> dict[str, dict[str, Any]]:
        return {str(item["bundle_id"]): item for item in self.load_manifest().get("bundles", [])}

    def get_action(self, action_id: str) -> dict[str, Any]:
        key = str(action_id or "").strip()
        try:
            return dict(self.action_map()[key])
        except KeyError as exc:
            raise ExampleActionRegistryError(f"Unknown example action: {key}") from exc

    def get_bundle(self, bundle_id: str) -> dict[str, Any]:
        key = str(bundle_id or "").strip()
        try:
            return dict(self.bundle_map()[key])
        except KeyError as exc:
            raise ExampleActionRegistryError(f"Unknown example bundle: {key}") from exc

    def _validate_manifest(self, manifest: dict[str, Any]) -> None:
        if not isinstance(manifest, dict):
            raise ExampleActionRegistryError("Example action manifest must be a JSON object.")
        if not manifest.get("manifest_version"):
            raise ExampleActionRegistryError("Example action manifest is missing manifest_version.")
        actions = manifest.get("actions")
        bundles = manifest.get("bundles")
        if not isinstance(actions, list) or not actions:
            raise ExampleActionRegistryError("Example action manifest must contain actions.")
        if not isinstance(bundles, list) or not bundles:
            raise ExampleActionRegistryError("Example action manifest must contain bundles.")

        bundle_ids: set[str] = set()
        for bundle in bundles:
            if not isinstance(bundle, dict):
                raise ExampleActionRegistryError("Example bundles must be objects.")
            bundle_id = str(bundle.get("bundle_id") or "").strip()
            if not bundle_id:
                raise ExampleActionRegistryError("Example bundle is missing bundle_id.")
            if bundle_id in bundle_ids:
                raise ExampleActionRegistryError(f"Duplicate example bundle_id: {bundle_id}")
            bundle_ids.add(bundle_id)
            components = bundle.get("components")
            if not isinstance(components, list) or not components:
                raise ExampleActionRegistryError(f"Example bundle {bundle_id} has no components.")
            component_ids: set[str] = set()
            for component in components:
                if not isinstance(component, dict):
                    raise ExampleActionRegistryError(f"Example bundle {bundle_id} components must be objects.")
                component_id = str(component.get("component_id") or "").strip()
                role = str(component.get("role") or "").strip()
                if not component_id or not role:
                    raise ExampleActionRegistryError(f"Example bundle {bundle_id} has an invalid component.")
                if component_id in component_ids:
                    raise ExampleActionRegistryError(f"Duplicate component_id in {bundle_id}: {component_id}")
                component_ids.add(component_id)
                if not str(component.get("object_key") or "").strip() and not str(component.get("static_path") or "").strip():
                    raise ExampleActionRegistryError(f"Component {component_id} needs object_key or static_path.")

        action_ids: set[str] = set()
        for action in actions:
            if not isinstance(action, dict):
                raise ExampleActionRegistryError("Example actions must be objects.")
            action_id = str(action.get("action_id") or "").strip()
            bundle_id = str(action.get("bundle_id") or "").strip()
            if not action_id or not bundle_id:
                raise ExampleActionRegistryError("Example action is missing action_id or bundle_id.")
            if action_id in action_ids:
                raise ExampleActionRegistryError(f"Duplicate example action_id: {action_id}")
            if bundle_id not in bundle_ids:
                raise ExampleActionRegistryError(f"Example action {action_id} references unknown bundle {bundle_id}.")
            action_ids.add(action_id)
            required_roles = action.get("required_roles")
            if not isinstance(required_roles, list) or not required_roles:
                raise ExampleActionRegistryError(f"Example action {action_id} has no required_roles.")
