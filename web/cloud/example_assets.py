from __future__ import annotations

import json
import os
import re
import time
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from .config import SpaShinyCloudConfig, load_cloud_config
from .models import JobRecord
from .r2_client import create_r2_client


DEFAULT_ASSET_VERSION = "v1.0.0"
DEFAULT_ASSET_BUCKET = "spashiny-assets"
DEFAULT_ASSET_PREFIX = "examples/v1.0.0/"
DEFAULT_MANIFEST_KEY = "examples/v1.0.0/manifest.json"
DEFAULT_GET_TTL_SECONDS = 900

FORBIDDEN_MANIFEST_PATTERNS = (
    re.compile(r"([A-Za-z]:\\|/Users/|/home/|/mnt/|/Volumes/)"),
    re.compile(r"(?i)(R2_SECRET|R2_ACCESS|AWS_SECRET|AWS_ACCESS|secret_access_key|access_key_id|X-Amz-Signature|X-Amz-Credential)"),
    re.compile(r"\.DS_Store"),
    re.compile(r"user_data[/\\]output"),
)


class ExampleAssetError(ValueError):
    pass


class ExampleAssetAccessError(ExampleAssetError):
    pass


@dataclass(frozen=True)
class ExampleAsset:
    asset_id: str
    object_key: str
    display_name: str
    description: str
    species: str
    original_sample_id: str
    modality: str
    file_format: str
    applicable_workflows: tuple[str, ...]
    thumbnail_url: str
    preview_url: str
    data_role: str
    processing_stage: str
    size_bytes: int
    sha256: str
    content_type: str
    source_database: str
    source_record_doi: str
    publication_doi: str
    license: str
    citation_required: bool
    raw: dict[str, Any]
    local_path: str = ""
    read_only: bool = False

    def ui_row(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "name": self.display_name,
            "display_name": self.display_name,
            "description": self.description,
            "species": self.species,
            "original_sample_id": self.original_sample_id,
            "modality": self.modality,
            "data_modality": self.modality,
            "file_format": self.file_format,
            "applicable_workflows": list(self.applicable_workflows),
            "thumbnail_url": self.thumbnail_url,
            "preview_url": self.preview_url,
            "data_role": self.data_role,
            "processing_stage": self.processing_stage,
            "size_bytes": self.size_bytes,
            "file_size": self.size_bytes,
            "source_database": self.source_database,
            "source_record_doi": self.source_record_doi,
            "publication_doi": self.publication_doi,
            "license": self.license,
            "citation_required": self.citation_required,
            "object_key": self.object_key,
            "content_type": self.content_type,
            "read_only": bool(self.read_only),
        }


class ExampleAssetService:
    """Manifest-backed access to published example assets.

    The service intentionally never lists the bucket to discover examples. The
    published manifest is the allow-list for UI display, presigning, and job
    binding.
    """

    def __init__(
        self,
        *,
        config: SpaShinyCloudConfig | None = None,
        client: Any | None = None,
        manifest: dict[str, Any] | None = None,
        asset_version: str = DEFAULT_ASSET_VERSION,
        manifest_key: str = DEFAULT_MANIFEST_KEY,
        cache_ttl_seconds: int = 300,
    ) -> None:
        self.config = config or load_cloud_config()
        self.client = client
        self._provided_manifest = manifest
        self.asset_version = str(asset_version)
        self.manifest_key = str(manifest_key)
        self.cache_ttl_seconds = max(0, int(cache_ttl_seconds or self.config.example_cache_ttl_seconds))
        self._cache: dict[str, Any] | None = None
        self._cache_loaded_at = 0.0

    @property
    def bucket(self) -> str:
        return self.config.r2_assets_bucket or DEFAULT_ASSET_BUCKET

    @property
    def prefix(self) -> str:
        return DEFAULT_ASSET_PREFIX

    @property
    def local_examples_root(self) -> Path:
        override = str(os.environ.get("SPASHINY_LOCAL_EXAMPLES_ROOT") or "").strip()
        return Path(override).resolve() if override else (Path(self.config.lab_data_root) / "examples").resolve()

    def load_manifest(self, *, force: bool = False) -> dict[str, Any]:
        now = time.monotonic()
        if (
            not force
            and self._cache is not None
            and (self.cache_ttl_seconds <= 0 or now - self._cache_loaded_at <= self.cache_ttl_seconds)
        ):
            return self._cache
        if self._provided_manifest is not None:
            manifest = json.loads(json.dumps(self._provided_manifest, ensure_ascii=False))
        elif self.config.is_lab_profile:
            manifest = self._load_local_manifest()
        else:
            manifest = self._download_manifest()
        self._validate_manifest(manifest)
        self._cache = manifest
        self._cache_loaded_at = now
        return manifest

    def assets(self, *, force: bool = False) -> list[ExampleAsset]:
        manifest = self.load_manifest(force=force)
        return [self._asset_from_item(item) for item in manifest["files"]]

    def asset_map(self, *, force: bool = False) -> dict[str, ExampleAsset]:
        return {asset.object_key: asset for asset in self.assets(force=force)}

    def asset_id_map(self, *, force: bool = False) -> dict[str, ExampleAsset]:
        return {asset.asset_id: asset for asset in self.assets(force=force)}

    def ui_rows(self, *, force: bool = False) -> list[dict[str, Any]]:
        manifest_version = self.load_manifest(force=force).get("manifest_version")
        rows = []
        for asset in self.assets(force=force):
            row = asset.ui_row()
            row["manifest_version"] = manifest_version
            row["asset_version"] = self.asset_version
            rows.append(row)
        return rows

    def group_by_modality(self, *, force: bool = False) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for asset in self.assets(force=force):
            grouped.setdefault(asset.modality, []).append(asset.ui_row())
        return grouped

    def group_by_sample(self, *, force: bool = False) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for asset in self.assets(force=force):
            grouped.setdefault(asset.original_sample_id or "unknown", []).append(asset.ui_row())
        return grouped

    def get_asset(self, object_key: str) -> ExampleAsset:
        key = self._normalize_object_key(object_key)
        try:
            return self.asset_map()[key]
        except KeyError as exc:
            raise ExampleAssetAccessError("Object key is not in the published example asset manifest.") from exc

    def get_asset_by_id(self, asset_id: str) -> ExampleAsset:
        key = str(asset_id or "").strip()
        if not key:
            raise ExampleAssetAccessError("Invalid example asset id.")
        try:
            return self.asset_id_map()[key]
        except KeyError as exc:
            raise ExampleAssetAccessError("Asset id is not in the published example asset manifest.") from exc

    def associated_object_keys(self, object_key: str) -> list[str]:
        asset = self.get_asset(object_key)
        by_lower = {key.lower(): key for key in self.asset_map()}
        keys = [asset.object_key]
        lower_key = asset.object_key.lower()
        if lower_key.endswith(".imzml"):
            companion = by_lower.get((asset.object_key[:-6] + ".ibd").lower())
            if companion:
                keys.append(companion)
        elif lower_key.endswith(".ibd"):
            companion = by_lower.get((asset.object_key[:-4] + ".imzML").lower())
            if companion:
                keys.insert(0, companion)
        for parent in asset.raw.get("parent_objects") or []:
            if isinstance(parent, str) and parent in self.asset_map() and parent not in keys:
                keys.append(parent)
        return keys

    def resolve_selection(self, object_keys: list[str]) -> list[ExampleAsset]:
        if not object_keys:
            raise ExampleAssetAccessError("At least one example asset object key is required.")
        resolved: list[str] = []
        for object_key in object_keys:
            for associated in self.associated_object_keys(object_key):
                if associated not in resolved:
                    resolved.append(associated)
        return [self.get_asset(key) for key in resolved]

    def build_job_asset_binding(self, object_keys: list[str], *, workflow_name: str = "") -> dict[str, Any]:
        assets = self.resolve_selection(object_keys)
        manifest = self.load_manifest()
        manifest_version = manifest.get("manifest_version")
        object_key_values = [asset.object_key for asset in assets]
        bundle_id = self._bundle_id(
            workflow_name=workflow_name,
            manifest_version=str(manifest_version or ""),
            object_keys=object_key_values,
        )
        return {
            "input_source": "example_asset",
            "legacy_input_source": "R2_ASSET",
            "example_bundle": {
                "bundle_id": bundle_id,
                "workflow_name": str(workflow_name or ""),
                "asset_ids": [asset.asset_id for asset in assets],
                "object_keys": object_key_values,
                "asset_version": self.asset_version,
                "manifest_version": manifest_version,
            },
            "example_bundle_id": bundle_id,
            "asset_version": self.asset_version,
            "manifest_version": manifest_version,
            "asset_bucket": self.bucket,
            "asset_manifest_key": self.manifest_key,
            "asset_object_key": assets[0].object_key,
            "asset_object_keys": object_key_values,
            "precomputed_result_candidates": self._precomputed_candidates(assets, workflow_name=workflow_name),
        }

    def job_asset_keys(self, job: JobRecord) -> list[str]:
        metadata = self._job_metadata(job)
        if metadata.get("input_source") not in {"example_asset", "R2_ASSET"}:
            return []
        if metadata.get("asset_bucket") != self.bucket:
            raise ExampleAssetAccessError("Job asset bucket does not match the configured assets bucket.")
        if metadata.get("asset_version") != self.asset_version:
            raise ExampleAssetAccessError("Job asset version does not match the service asset version.")
        keys = metadata.get("asset_object_keys")
        if not isinstance(keys, list):
            raise ExampleAssetAccessError("Job asset object keys are malformed.")
        return [self.get_asset(str(key)).object_key for key in keys]

    def create_worker_download_plan(self, job: JobRecord, *, expires_in: int | None = None) -> list[dict[str, Any]]:
        plan = []
        for key in self.job_asset_keys(job):
            asset = self.get_asset(key)
            plan.append(self.worker_plan_entry(asset, source="example_asset", expires_in=expires_in))
        return plan

    def worker_plan_entry(self, asset: ExampleAsset, *, source: str = "example_asset", expires_in: int | None = None) -> dict[str, Any]:
        entry = {
            "source": source,
            "object_key": asset.object_key,
            "filename": Path(asset.object_key).name,
            "size_bytes": asset.size_bytes,
            "sha256": asset.sha256,
            "content_type": asset.content_type,
            "read_only": bool(asset.read_only),
        }
        if asset.local_path:
            entry["local_path"] = asset.local_path
            entry["example_root"] = str(self.local_examples_root)
        else:
            entry["url"] = self.presign_get_url(asset.object_key, expires_in=expires_in)
        return entry

    def create_precomputed_download_plan(self, job: JobRecord, *, expires_in: int | None = None) -> list[dict[str, Any]]:
        metadata = self._job_metadata(job)
        if not self.config.example_precompute_enabled:
            return []
        candidates = metadata.get("precomputed_result_candidates")
        if not isinstance(candidates, list):
            return []
        plan = []
        for item in candidates:
            if not isinstance(item, dict):
                continue
            object_key = self._normalize_manifest_object_key(str(item.get("object_key") or ""))
            plan.append(
                {
                    "object_key": object_key,
                    "filename": Path(object_key).name,
                    "workflow_name": str(item.get("workflow_name") or metadata.get("workflow_name") or ""),
                    "model_name": str(item.get("model_name") or ""),
                    "size_bytes": int(item.get("size_bytes") or 0),
                    "sha256": str(item.get("sha256") or ""),
                    "content_type": str(item.get("content_type") or "application/octet-stream"),
                    "url": self.presign_declared_object_url(object_key, expires_in=expires_in),
                }
            )
        return plan

    def download_job_assets(self, job: JobRecord, target_dir: Path) -> list[Path]:
        target = Path(target_dir)
        target.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for item in self.create_worker_download_plan(job):
            local_path = target / str(item["filename"])
            with urlopen(str(item["url"])) as response, local_path.open("wb") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
            paths.append(local_path)
        return paths

    def presign_get_url(self, object_key: str, *, expires_in: int | None = None) -> str:
        if self.config.is_lab_profile:
            raise ExampleAssetError("Lab example assets are local read-only files and do not provide presigned URLs.")
        key = self.get_asset(object_key).object_key
        client = self._client()
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=int(expires_in or self.config.r2_presigned_url_ttl_seconds or DEFAULT_GET_TTL_SECONDS),
        )

    def presign_declared_object_url(self, object_key: str, *, expires_in: int | None = None) -> str:
        if self.config.is_lab_profile:
            raise ExampleAssetError("Lab example assets are local read-only files and do not provide presigned URLs.")
        key = self._normalize_manifest_object_key(object_key)
        client = self._client()
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=int(expires_in or self.config.r2_presigned_url_ttl_seconds or DEFAULT_GET_TTL_SECONDS),
        )

    def _download_manifest(self) -> dict[str, Any]:
        client = self._client()
        try:
            response = client.get_object(Bucket=self.bucket, Key=self.manifest_key)
            body = response.get("Body")
            if body is None or not hasattr(body, "read"):
                raise ExampleAssetError("R2 manifest response did not contain a readable body.")
            raw = body.read()
            if isinstance(raw, str):
                raw = raw.encode("utf-8")
            data = json.loads(bytes(raw).decode("utf-8"))
        except Exception as exc:
            cached = self._read_persistent_manifest_cache()
            if cached is not None:
                return cached
            raise ExampleAssetError("R2 example asset manifest is not valid JSON.") from exc
        if not isinstance(data, dict):
            raise ExampleAssetError("R2 example asset manifest must be a JSON object.")
        self._write_persistent_manifest_cache(data)
        return data

    def _load_local_manifest(self) -> dict[str, Any]:
        root = self.local_examples_root.resolve()
        candidates = [root / "manifest.json", root / "examples_manifest.json", root / "example_manifest.json"]
        manifest: dict[str, Any] | None = None
        for path in candidates:
            if path.is_file():
                manifest = json.loads(path.read_text(encoding="utf-8-sig"))
                break
        if manifest is None:
            per_example_files = sorted(root.glob("*/manifest.json")) if root.exists() else []
            if per_example_files:
                examples = []
                for path in per_example_files:
                    payload = json.loads(path.read_text(encoding="utf-8-sig"))
                    if isinstance(payload, dict):
                        payload.setdefault("_manifest_dir", str(path.parent))
                        examples.append(payload)
                manifest = {
                    "manifest_version": "lab-local-examples-v1",
                    "asset_version": self.asset_version,
                    "examples": examples,
                }
        if not isinstance(manifest, dict):
            raise ExampleAssetError(f"Local example manifest was not found under {root}.")
        return self._normalize_local_manifest(manifest, root=root)

    def _client(self):
        if self.client is None:
            self.client = create_r2_client(self.config)
        return self.client

    def _validate_manifest(self, manifest: dict[str, Any]) -> None:
        if self.config.is_lab_profile:
            self._validate_local_manifest(manifest)
            return
        if self.bucket != DEFAULT_ASSET_BUCKET:
            raise ExampleAssetError("Example assets must use spashiny-assets.")
        if self.manifest_key != DEFAULT_MANIFEST_KEY:
            raise ExampleAssetError("Example asset manifest key is fixed to examples/v1.0.0/manifest.json.")
        files = manifest.get("files")
        if not isinstance(files, list) or not files:
            raise ExampleAssetError("R2 example asset manifest does not contain a files array.")
        text = json.dumps(manifest, ensure_ascii=True, sort_keys=True)
        if any(pattern.search(text) for pattern in FORBIDDEN_MANIFEST_PATTERNS):
            raise ExampleAssetError("R2 example asset manifest contains a forbidden path or secret marker.")
        seen: set[str] = set()
        seen_asset_ids: set[str] = set()
        for item in files:
            if not isinstance(item, dict):
                raise ExampleAssetError("R2 example asset manifest file entries must be objects.")
            key = self._normalize_object_key(str(item.get("object_key") or ""))
            if key in seen:
                raise ExampleAssetError("R2 example asset manifest contains duplicate object keys.")
            seen.add(key)
            asset_id = self._asset_id_for_item(item, key)
            if asset_id in seen_asset_ids:
                raise ExampleAssetError("R2 example asset manifest contains duplicate asset ids.")
            seen_asset_ids.add(asset_id)
            if not key.startswith(self.prefix):
                raise ExampleAssetError("R2 example asset object key is outside the published prefix.")
            if str(item.get("asset_version") or "") != self.asset_version:
                raise ExampleAssetError("R2 example asset version mismatch.")
            if not item.get("sha256") or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256"))):
                raise ExampleAssetError("R2 example asset is missing a valid SHA256.")

    def _validate_local_manifest(self, manifest: dict[str, Any]) -> None:
        files = manifest.get("files")
        if not isinstance(files, list) or not files:
            raise ExampleAssetError("Local example manifest does not contain a files array.")
        root = self.local_examples_root.resolve()
        seen: set[str] = set()
        for item in files:
            if not isinstance(item, dict):
                raise ExampleAssetError("Local example manifest file entries must be objects.")
            key = self._normalize_object_key(str(item.get("object_key") or ""))
            if key in seen:
                raise ExampleAssetError("Local example manifest contains duplicate object keys.")
            seen.add(key)
            local_path = Path(str(item.get("local_path") or "")).resolve()
            if not str(item.get("local_path") or ""):
                raise ExampleAssetError(f"Local example asset is missing local_path: {key}")
            if local_path != root and root not in local_path.parents:
                raise ExampleAssetError(f"Local example asset path escapes the examples root: {key}")
            if not local_path.is_file():
                raise ExampleAssetError(f"Local example asset file is missing: {local_path}")
            expected_size = int(item.get("size_bytes") or 0)
            actual_size = local_path.stat().st_size
            if expected_size and actual_size != expected_size:
                raise ExampleAssetError(f"Local example asset size mismatch for {key}.")
            expected_sha = str(item.get("sha256") or "").strip().lower()
            if expected_sha and not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
                raise ExampleAssetError(f"Local example asset SHA256 is malformed for {key}.")
            if bool(item.get("read_only")) is not True:
                raise ExampleAssetError(f"Local example asset must declare read_only=true: {key}")

    def _asset_from_item(self, item: dict[str, Any]) -> ExampleAsset:
        key = self._normalize_object_key(str(item.get("object_key") or ""))
        return ExampleAsset(
            asset_id=self._asset_id_for_item(item, key),
            object_key=key,
            display_name=str(item.get("display_name") or Path(key).name),
            description=str(
                item.get("description")
                or item.get("publication_title")
                or item.get("source_record_doi")
                or "Published SpaShiny example dataset"
            ),
            species=str(item.get("species") or item.get("organism") or item.get("organism_name") or "unknown"),
            original_sample_id=str(item.get("original_sample_id") or ""),
            modality=self._modality_for_key(key),
            file_format=str(item.get("file_format") or self._file_format_for_key(key)),
            applicable_workflows=tuple(
                str(value)
                for value in (
                    item.get("applicable_workflows")
                    or item.get("workflows")
                    or self._default_workflows_for_key(key)
                )
                if str(value).strip()
            ),
            thumbnail_url=str(item.get("thumbnail_url") or item.get("thumbnail") or ""),
            preview_url=str(item.get("preview_url") or item.get("preview") or ""),
            data_role=str(item.get("data_role") or ""),
            processing_stage=str(item.get("processing_stage") or ""),
            size_bytes=int(item.get("size_bytes") or 0),
            sha256=str(item.get("sha256") or ""),
            content_type=str(item.get("content_type") or "application/octet-stream"),
            source_database=str(item.get("source_database") or ""),
            source_record_doi=str(item.get("source_record_doi") or ""),
            publication_doi=str(item.get("publication_doi") or ""),
            license=str(item.get("license") or ""),
            citation_required=bool(item.get("citation_required")),
            local_path=str(item.get("local_path") or ""),
            read_only=bool(item.get("read_only")),
            raw=dict(item),
        )

    def _normalize_local_manifest(self, manifest: dict[str, Any], *, root: Path) -> dict[str, Any]:
        files: list[dict[str, Any]] = []
        raw_files = manifest.get("files")
        if isinstance(raw_files, list):
            for item in raw_files:
                if isinstance(item, dict):
                    files.append(self._normalize_local_file_item(item, root=root, example={}))
        raw_examples = manifest.get("examples")
        if isinstance(raw_examples, list):
            for example in raw_examples:
                if not isinstance(example, dict):
                    continue
                example_root = Path(str(example.get("_manifest_dir") or root)).resolve()
                for item in example.get("files") or []:
                    if isinstance(item, dict):
                        files.append(self._normalize_local_file_item(item, root=root, example=example, example_root=example_root))
        normalized = dict(manifest)
        normalized["manifest_version"] = str(manifest.get("manifest_version") or "lab-local-examples-v1")
        normalized["asset_version"] = str(manifest.get("asset_version") or self.asset_version)
        normalized["files"] = files
        return normalized

    def _normalize_local_file_item(
        self,
        item: dict[str, Any],
        *,
        root: Path,
        example: dict[str, Any],
        example_root: Path | None = None,
    ) -> dict[str, Any]:
        data = dict(item)
        example_id = str(example.get("example_id") or data.get("example_id") or data.get("sample_name") or data.get("sample_id") or "").strip()
        sample_name = str(example.get("sample_name") or example.get("sample_id") or data.get("sample_name") or data.get("sample_id") or example_id).strip()
        relative_value = str(data.get("relative_path") or data.get("path") or "").strip()
        local_raw = str(data.get("local_path") or "").strip()
        object_key = str(data.get("object_key") or "").strip()
        if not object_key:
            base = example_id or sample_name or "local"
            name = Path(relative_value or local_raw or data.get("filename") or "asset.bin").name
            object_key = f"{self.prefix}local/{base}/{name}"
        object_key = self._normalize_object_key(object_key)
        local_path = self._resolve_local_asset_path(
            root=root,
            object_key=object_key,
            local_path=local_raw,
            relative_path=relative_value,
            example_root=example_root,
        )
        size_bytes = int(data.get("size_bytes") or 0)
        if not size_bytes and local_path.is_file():
            size_bytes = local_path.stat().st_size
        data.update(
            {
                "asset_version": str(data.get("asset_version") or example.get("asset_version") or self.asset_version),
                "object_key": object_key,
                "display_name": str(data.get("display_name") or example.get("display_name") or Path(object_key).name),
                "original_sample_id": str(data.get("original_sample_id") or sample_name),
                "sample_name": sample_name,
                "example_id": example_id,
                "applicable_workflows": data.get("applicable_workflows") or data.get("workflow_compatibility") or example.get("workflow_compatibility") or example.get("applicable_workflows") or [],
                "size_bytes": size_bytes,
                "sha256": str(data.get("sha256") or ""),
                "local_path": str(local_path),
                "read_only": True,
                "source": "local_example_asset",
            }
        )
        return data

    def _resolve_local_asset_path(
        self,
        *,
        root: Path,
        object_key: str,
        local_path: str,
        relative_path: str,
        example_root: Path | None,
    ) -> Path:
        candidates: list[Path] = []
        if local_path:
            path = Path(local_path)
            candidates.append(path if path.is_absolute() else root / path)
            if example_root is not None and not path.is_absolute():
                candidates.append(example_root / path)
        if relative_path:
            path = Path(relative_path)
            candidates.append(path if path.is_absolute() else root / path)
            if example_root is not None and not path.is_absolute():
                candidates.append(example_root / path)
        key_path = Path(object_key)
        candidates.append(root / key_path)
        if object_key.startswith(self.prefix):
            candidates.append(root / object_key[len(self.prefix):])
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved.is_file():
                return resolved
        return candidates[0].resolve() if candidates else (root / key_path).resolve()

    def _normalize_object_key(self, object_key: str) -> str:
        key = str(object_key or "").strip()
        if not key or key.startswith("/") or "\\" in key:
            raise ExampleAssetAccessError("Invalid example asset object key.")
        parts = [part for part in key.split("/") if part]
        if any(part in {".", ".."} for part in parts):
            raise ExampleAssetAccessError("Invalid example asset object key.")
        return key

    def _normalize_manifest_object_key(self, object_key: str) -> str:
        key = self._normalize_object_key(object_key)
        if not key.startswith(self.prefix):
            raise ExampleAssetAccessError("Manifest-declared object is outside the published prefix.")
        return key

    def _bundle_id(self, *, workflow_name: str, manifest_version: str, object_keys: list[str]) -> str:
        payload = json.dumps(
            {
                "asset_version": self.asset_version,
                "manifest_version": manifest_version,
                "workflow_name": str(workflow_name or ""),
                "object_keys": sorted(object_keys),
            },
            sort_keys=True,
        )
        return "bundle_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]

    def _precomputed_candidates(self, assets: list[ExampleAsset], *, workflow_name: str) -> list[dict[str, Any]]:
        if not self.config.example_precompute_enabled:
            return []
        workflow = str(workflow_name or "")
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for asset in assets:
            for item in asset.raw.get("precomputed_results") or []:
                if not isinstance(item, dict):
                    continue
                item_workflow = str(item.get("workflow_name") or item.get("workflow") or "")
                if item_workflow and workflow and item_workflow != workflow:
                    continue
                object_key = self._normalize_manifest_object_key(str(item.get("object_key") or ""))
                if object_key in seen:
                    continue
                seen.add(object_key)
                candidates.append(
                    {
                        "object_key": object_key,
                        "workflow_name": item_workflow or workflow,
                        "model_name": str(item.get("model_name") or ""),
                        "size_bytes": int(item.get("size_bytes") or 0),
                        "sha256": str(item.get("sha256") or ""),
                        "content_type": str(item.get("content_type") or "application/octet-stream"),
                    }
                )
        return candidates

    def _persistent_manifest_cache_path(self) -> Path:
        return Path(self.config.workspace) / "example_cache" / self.asset_version / "manifest.json"

    def _read_persistent_manifest_cache(self) -> dict[str, Any] | None:
        if not self.config.example_cache_enabled:
            return None
        path = self._persistent_manifest_cache_path()
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    def _write_persistent_manifest_cache(self, manifest: dict[str, Any]) -> None:
        if not self.config.example_cache_enabled:
            return
        try:
            path = self._persistent_manifest_cache_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_suffix(".json.tmp")
            tmp_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
            tmp_path.replace(path)
        except Exception:
            return None

    def _asset_id_for_item(self, item: dict[str, Any], object_key: str) -> str:
        explicit = str(item.get("asset_id") or item.get("id") or "").strip()
        value = explicit or ("asset_" + hashlib.sha256(object_key.encode("utf-8")).hexdigest()[:16])
        if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", value):
            raise ExampleAssetAccessError("Invalid example asset id.")
        return value

    def _modality_for_key(self, object_key: str) -> str:
        parts = object_key.split("/")
        for value in ("multimodal", "spatial_transcriptomics", "spatial_metabolomics", "single_cell"):
            if value in parts:
                return value
        return "unknown"

    def _file_format_for_key(self, object_key: str) -> str:
        suffixes = [suffix.lstrip(".") for suffix in Path(object_key).suffixes if suffix]
        return "+".join(suffixes) if suffixes else "unknown"

    def _default_workflows_for_key(self, object_key: str) -> tuple[str, ...]:
        parts = object_key.split("/")
        lower_key = object_key.lower()
        if "spatial_transcriptomics" in parts:
            return ("st_quality_control", "normalization", "feature_selection")
        if "spatial_metabolomics" in parts:
            if "/raw/" in f"/{lower_key}" and lower_key.endswith(".h5ad"):
                return ("hit_sm_multi_sample_integration", "sm_quality_control", "normalization", "spatial_statistics")
            return ("sm_quality_control", "normalization", "spatial_statistics")
        if "multimodal" in parts:
            if "/raw/" in f"/{lower_key}":
                return ("vit_single_sample_integration", "vhit_multi_sample_integration", "st_sm_conditional_vae", "integration_postprocessing")
            return ("st_sm_conditional_vae", "integration_postprocessing")
        if lower_key.endswith(".h5ad"):
            return ("st_sm_conditional_vae", "integration_postprocessing")
        return ("file_validation", "metadata_statistics")

    def _job_metadata(self, job: JobRecord) -> dict[str, Any]:
        try:
            data = json.loads(job.metadata_json or "{}")
        except Exception as exc:
            raise ExampleAssetAccessError("Job metadata is not valid JSON.") from exc
        if not isinstance(data, dict):
            raise ExampleAssetAccessError("Job metadata must be a JSON object.")
        return data
