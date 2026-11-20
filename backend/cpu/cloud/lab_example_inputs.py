from __future__ import annotations

import json
import os
import hashlib
from pathlib import Path
from typing import Iterable

from .input_resolver import InputResolver, InputResolverError


class LabExampleInputError(RuntimeError):
    pass


ROLE_ALIASES = {
    "alignment_st_h5ad": "st_raw_h5ad",
    "alignment_sm_h5ad": "sm_raw_h5ad",
    "knn_st_h5ad": "st_qc_h5ad",
    "knn_sm_h5ad": "sm_aligned_h5ad",
    "downstream_joint_h5ad": "joint_downstream_reference_h5ad",
    "positive_imzml": "sm_pos_imzml",
    "positive_ibd": "sm_pos_ibd",
    "negative_imzml": "sm_neg_imzml",
    "negative_ibd": "sm_neg_ibd",
}

WORKFLOW_ALIASES = {
    "sm_upload": {"file_validation", "sm_quality_control"},
    "sm upload": {"file_validation", "sm_quality_control"},
    "st_upload": {"st_quality_control"},
    "st upload": {"st_quality_control"},
    "sm_qc": {"sm_quality_control"},
    "sm qc": {"sm_quality_control"},
    "st_qc": {"st_quality_control"},
    "st qc": {"st_quality_control"},
    "automatic_alignment": {"alignment_fitting", "alignment_rasterization"},
    "automatic alignment": {"alignment_fitting", "alignment_rasterization"},
    "alignment": {"alignment_fitting", "alignment_rasterization"},
    "knn": {"integration_postprocessing"},
    "joint": {"st_sm_conditional_vae"},
    "downstream": {"marker_feature_analysis", "differential_analysis", "clustering"},
}


def _examples_root(examples_root: str | Path | None = None) -> Path:
    if examples_root:
        return Path(examples_root).resolve()
    direct_root = os.environ.get("SPASHINY_EXAMPLES_ROOT") or os.environ.get("SPASHINY_LAB_EXAMPLES_ROOT")
    if direct_root:
        return Path(direct_root).resolve()
    data_root = Path(os.environ.get("SPASHINY_LOCAL_DATA_ROOT") or "/workspace/data")
    return (data_root / "examples").resolve()


def _load_manifest(root: Path, manifest_path: str | Path | None = None) -> dict:
    path = Path(manifest_path).resolve() if manifest_path else root / "manifest.json"
    if not path.is_file():
        raise LabExampleInputError(f"Example manifest was not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise LabExampleInputError(f"Example manifest is not valid JSON: {path}") from exc


def _workflow_allowed(item: dict, workflow: str, page_name: str) -> bool:
    requested = set()
    for value in (workflow, page_name):
        text = str(value or "").strip()
        if not text:
            continue
        requested.add(text)
        requested.add(text.lower())
        requested.update(WORKFLOW_ALIASES.get(text.lower(), set()))
    allowed = {str(value) for value in item.get("workflow_compatibility") or item.get("applicable_workflows") or []}
    allowed_lower = {value.lower() for value in allowed}
    if requested and allowed and (requested & allowed or {value.lower() for value in requested} & allowed_lower):
        return True
    # UI-only pages such as knn/downstream reuse prepared Y7_T assets but are
    # not always listed in the core manifest workflow compatibility table.
    return not allowed


def _verify_manifest_file(root: Path, item: dict, *, verify_sha256: bool = False) -> Path:
    rel = str(item.get("relative_path") or "").strip()
    if not rel:
        raise LabExampleInputError("Example manifest entry is missing relative_path.")
    candidate = (root / rel).resolve(strict=True)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise LabExampleInputError("Example input resolved outside the examples root.") from exc
    if not candidate.is_file():
        raise LabExampleInputError(f"Example input is not a regular file: {candidate}")
    expected_size = int(item.get("size_bytes") or 0)
    if expected_size and candidate.stat().st_size != expected_size:
        raise LabExampleInputError(f"Example input failed size validation: {candidate.name}")
    if verify_sha256:
        expected_sha = str(item.get("sha256") or "").strip().lower()
        if expected_sha:
            digest = hashlib.sha256()
            with candidate.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != expected_sha:
                raise LabExampleInputError(f"Example input failed SHA256 validation: {candidate.name}")
    return candidate


def resolve_example_input(
    workflow: str,
    page_name: str,
    role: str,
    example_id: str = "Y7_T",
    *,
    examples_root: str | Path | None = None,
    manifest_path: str | Path | None = None,
    verify_sha256: bool = False,
) -> Path:
    """Resolve one read-only Lab example input role from the local manifest."""

    role = ROLE_ALIASES.get(str(role or "").strip(), str(role or "").strip())
    example_id = str(example_id or "Y7_T").strip()
    if not role:
        raise LabExampleInputError("The example input role is missing.")
    root = _examples_root(examples_root)
    manifest = _load_manifest(root, manifest_path)
    for item in manifest.get("files") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("example_id") or "").strip() != example_id:
            continue
        if str(item.get("data_role") or "").strip() != role:
            continue
        if not bool(item.get("read_only", manifest.get("read_only", False))):
            raise LabExampleInputError(f"Example input role is not marked read-only: {role}")
        if not _workflow_allowed(item, workflow, page_name):
            raise LabExampleInputError(f"Example input role {role} is not compatible with workflow {workflow or page_name}.")
        return _verify_manifest_file(root, item, verify_sha256=verify_sha256)
    raise LabExampleInputError(f"Example input role was not found: example_id={example_id}, role={role}")


def resolve_example_inputs(
    workflow: str,
    page_name: str,
    roles: Iterable[str],
    example_id: str = "Y7_T",
    *,
    verify_sha256: bool = False,
) -> dict[str, Path]:
    return {
        str(role): resolve_example_input(workflow, page_name, str(role), example_id, verify_sha256=verify_sha256)
        for role in roles
    }


def resolve_bound_local_roles(
    *,
    session_id: str,
    analysis_session_id: str,
    action_id: str,
    workflow_name: str,
    required_roles: Iterable[str],
) -> dict[str, Path]:
    """Resolve a session-scoped example binding to verified local files."""

    session_id = str(session_id or "").strip()
    analysis_session_id = str(analysis_session_id or "").strip()
    action_id = str(action_id or "").strip()
    workflow_name = str(workflow_name or "").strip()
    roles = tuple(str(role).strip() for role in required_roles if str(role).strip())

    if not session_id:
        raise LabExampleInputError("The Lab Session ID is missing.")
    if not analysis_session_id:
        raise LabExampleInputError("The tab analysis session ID is missing.")
    if not action_id:
        raise LabExampleInputError("The example action ID is missing.")
    if not workflow_name:
        raise LabExampleInputError("The workflow name is missing.")
    if not roles:
        raise LabExampleInputError("No required input roles were specified.")

    resolver = InputResolver()

    try:
        plan = resolver.resolve_example_action_binding(
            session_id=session_id,
            analysis_session_id=analysis_session_id,
            action_id=action_id,
            workflow_name=workflow_name,
        )
    except InputResolverError as exc:
        raise LabExampleInputError(str(exc)) from exc

    available = {str(item) for item in plan.get("available_workflows") or []}
    if available and workflow_name not in available:
        raise LabExampleInputError(
            "The example binding is not compatible with this workflow."
        )

    role_assets: dict[str, dict] = {}
    for item in plan.get("assets") or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        if role in roles and role not in role_assets:
            role_assets[role] = item

    missing = [role for role in roles if role not in role_assets]
    if missing:
        raise LabExampleInputError(
            "The example binding is missing role(s): " + ", ".join(missing)
        )

    if resolver.example_assets is None:
        raise LabExampleInputError("The example asset service is unavailable.")

    example_root = resolver.example_assets.local_examples_root.resolve(strict=True)
    resolved: dict[str, Path] = {}

    for role in roles:
        item = role_assets[role]
        local_path = str(item.get("local_path") or "").strip()

        if not local_path:
            raise LabExampleInputError(
                f"The example role {role} has no Lab-local path."
            )

        candidate = Path(local_path).resolve(strict=True)

        try:
            candidate.relative_to(example_root)
        except ValueError as exc:
            raise LabExampleInputError(
                f"The example role {role} resolved outside the example root."
            ) from exc

        if not candidate.is_file():
            raise LabExampleInputError(
                f"The example role {role} is not a regular file."
            )

        expected_size = int(item.get("size_bytes") or 0)
        if expected_size and candidate.stat().st_size != expected_size:
            raise LabExampleInputError(
                f"The example role {role} failed size validation."
            )

        expected_sha = str(item.get("sha256") or "").strip().lower()
        if expected_sha:
            digest = hashlib.sha256()
            with candidate.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != expected_sha:
                raise LabExampleInputError(
                    f"The example role {role} failed SHA256 validation."
                )

        resolved[role] = candidate

    return resolved
