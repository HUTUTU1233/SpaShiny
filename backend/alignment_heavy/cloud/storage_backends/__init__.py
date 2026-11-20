from __future__ import annotations

from pathlib import Path

from .base import ObjectHead, StorageBackendError, TemporaryObjectStorage
from .local_temp import LocalTempStorage
from .r2 import R2Storage
from ..config import SpaShinyCloudConfig, load_cloud_config


def get_temporary_object_storage(config: SpaShinyCloudConfig | None = None) -> TemporaryObjectStorage:
    cfg = config or load_cloud_config(require_storage=False)
    if cfg.storage_backend == "local":
        root = Path(cfg.local_object_root if cfg.is_lab_profile else (Path(cfg.workspace) / "temporary_objects"))
        return LocalTempStorage(root)
    if cfg.storage_backend == "r2":
        return R2Storage(cfg)
    raise StorageBackendError("Unsupported temporary storage backend.")


__all__ = [
    "LocalTempStorage",
    "ObjectHead",
    "R2Storage",
    "StorageBackendError",
    "TemporaryObjectStorage",
    "get_temporary_object_storage",
]
