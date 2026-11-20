"""Fixed, exact-analysis access to published KNN artifacts; no path fallback."""
import hashlib
import json
from pathlib import Path

WORKFLOW = "integration_postprocessing"
RESULT_FILES = frozenset({
    "knn_input_inspection.json", "knn_summary.json", "knn_handoff_manifest.json", "knn_spot_mapping.json",
    "knn_joint_ready.h5ad", "knn_st_reassigned.h5ad", "knn_sm_reassigned.h5ad",
    "figures/knn_input_overlay.png", "figures/knn_input_overlay.pdf",
    "figures/knn_scaled_preview.png", "figures/knn_scaled_preview.pdf",
    "figures/knn_reassignment_spatial.png", "figures/knn_reassignment_spatial.pdf",
    "figures/knn_sm_total_intensity.png", "figures/knn_sm_total_intensity.pdf",
    "figures/knn_st_total_counts.png", "figures/knn_st_total_counts.pdf",
    "figures/knn_intensity_histograms.png", "figures/knn_intensity_histograms.pdf",
    "figures/knn_joint_intensity.png", "figures/knn_joint_intensity.pdf",
    "figures/knn_joint_counts.png", "figures/knn_joint_counts.pdf",
    "knn_joint_plots.pdf", "knn_full_report.pdf",
})


def scoped_job(owner, analysis, job_id, key, *, database=None):
    from .database import CloudDatabase
    from .job_manager import JobManager

    if not all(isinstance(v, str) and v.strip() for v in (owner, analysis, job_id, key)):
        raise ValueError("A current owner, analysis, KNN job and input fingerprint are required.")
    database = database if database is not None else CloudDatabase(read_only=True)
    record = database.get_analysis_session(analysis, owner_session_id=owner)
    if record.get("status") != "ACTIVE":
        raise ValueError("This analysis has ended; old results cannot be inherited by a new analysis.")
    job = JobManager(database=database).get_job_for_session(owner, job_id, analysis_session_id=analysis)
    params = json.loads(job.parameters_json or "{}")
    if (job.session_id != owner or job.analysis_session_id != analysis or job.workflow != WORKFLOW
            or params.get("knn_input_key") != key or str(job.status).upper() != "SUCCEEDED"):
        raise ValueError("The completed KNN job does not match this exact owner, analysis and input source.")
    return job


def read_scoped_result(*, owner, analysis, job_id, key, relative, database=None, config=None):
    from .config import load_cloud_config

    if relative not in RESULT_FILES:
        raise ValueError("This KNN artifact name is not allowed.")
    job = scoped_job(owner, analysis, job_id, key, database=database)
    config = config if config is not None else load_cloud_config(require_storage=False)
    root = Path(job.local_workspace).resolve()
    managed = Path(config.lab_result_root).resolve()
    if managed not in root.parents:
        raise ValueError("KNN output is outside the managed results root.")
    manifest_path = root / "result_manifest.json"
    if not manifest_path.is_file() or manifest_path.stat().st_size > 1024 * 1024:
        raise ValueError("The KNN result manifest is missing or too large.")
    manifest = json.loads(manifest_path.read_text())
    if (manifest.get("job_id") != job_id or manifest.get("session_id") != owner
            or not isinstance(manifest.get("files"), list)
            or ("analysis_session_id" in manifest and manifest["analysis_session_id"] != analysis)):
        raise ValueError("The KNN result manifest identity is invalid.")
    entries = []
    for item in manifest["files"]:
        if not isinstance(item, dict):
            raise ValueError("Invalid KNN manifest entry.")
        aliases = [item[k] for k in ("path", "relative_path") if k in item]
        if len(aliases) == 2 and aliases[0] != aliases[1]:
            raise ValueError("Conflicting KNN artifact paths.")
        if aliases and aliases[0] == relative:
            entries.append(item)
    target = (root / relative).resolve()
    if len(entries) != 1 or root not in target.parents or not target.is_file():
        raise ValueError("The exact KNN artifact is not uniquely registered.")
    sizes = [entries[0][k] for k in ("size", "size_bytes") if k in entries[0]]
    if not sizes or any(type(v) is not int or v <= 0 or v != target.stat().st_size for v in sizes):
        raise ValueError("KNN artifact size validation failed.")
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != str(entries[0].get("sha256") or "").lower():
        raise ValueError("KNN artifact SHA256 validation failed.")
    return target
