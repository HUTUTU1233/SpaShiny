from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .runpod_lifecycle_manager import RunPodLifecycleManager


@dataclass
class RunPodReconciler:
    lifecycle: RunPodLifecycleManager

    def reconcile_instance(self, instance_id: str) -> dict[str, Any]:
        return self.lifecycle.reconcile_instance(instance_id)

    def reconcile_all_managed_instances(self) -> dict[str, Any]:
        return self.lifecycle.reconcile_all_managed_instances()
