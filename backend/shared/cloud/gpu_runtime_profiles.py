from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


RUNTIME_MAP_PATH = Path(__file__).resolve().parents[1] / "deploy" / "gpu-workflow-runtime-map.json"
DEFAULT_RUNTIME_PROFILE = "spatialmeta"


class GpuRuntimeProfileError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def load_gpu_runtime_map() -> dict[str, Any]:
    data = json.loads(RUNTIME_MAP_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise GpuRuntimeProfileError("GPU runtime map must be a JSON object.")
    return data


def runtime_profile_for_workflow(workflow_name: str) -> str:
    data = load_gpu_runtime_map()
    workflows = data.get("workflow_runtime_map")
    if not isinstance(workflows, dict):
        raise GpuRuntimeProfileError("GPU runtime map is missing workflow_runtime_map.")
    item = workflows.get(str(workflow_name or ""))
    if not isinstance(item, dict):
        return str(data.get("default_runtime_profile") or DEFAULT_RUNTIME_PROFILE)
    profile = item.get("runtime_profile")
    if profile:
        return str(profile)
    return str(data.get("default_runtime_profile") or DEFAULT_RUNTIME_PROFILE)


def validate_runtime_profile(runtime_profile: str) -> str:
    profile = str(runtime_profile or DEFAULT_RUNTIME_PROFILE).strip() or DEFAULT_RUNTIME_PROFILE
    profiles = load_gpu_runtime_map().get("runtime_profiles")
    if not isinstance(profiles, dict) or profile not in profiles:
        raise GpuRuntimeProfileError(f"Unsupported GPU runtime profile: {profile}")
    return profile
