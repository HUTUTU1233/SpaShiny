"""Single-sample orchestration, not a replacement scientific implementation.

No database initialization, authentication fallback, idle timer or model training
lives here. The Web adapter must re-authenticate the exact scope before actions.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class PipelineError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class Scope:
    owner: str
    analysis: str

    def __post_init__(self):
        for value in (self.owner, self.analysis):
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", str(value)):
                raise PipelineError("SCOPE_REQUIRED", "An authenticated owner and analysis are required.")


STEPS = (
    "preflight", "preprocess", "initial_preview", "manual_alignment",
    "normalize_coordinates", "create_alignment_model", "alignment_training",
    "alignment_raster", "alignment_fitting", "alignment_step6", "knn",
    "integration", "prepare_downstream", "report",
)
STARTS = {"raw_pair": 0, "manual": 3, "step6": 10, "knn": 11, "joint": 11}
SUCCESS = {"SUCCEEDED", "COMPLETED"}
FAILURE = {"FAILED", "CANCELLED", "CANCELED", "TIMED_OUT", "ABANDONED", "ENDED"}
TERMINAL = SUCCESS | FAILURE


@dataclass
class Run:
    scope: Scope
    run_id: str
    start: str
    index: int
    status: str = "READY"
    workflow_id: str = ""
    inputs: dict = field(default_factory=dict)
    jobs: dict = field(default_factory=dict)
    completed: dict = field(default_factory=dict)
    events: list = field(default_factory=list)
    parameters: dict = field(default_factory=dict)
    error: str = ""
    job_progress: float | None = None

    @classmethod
    def create(cls, scope, start, *, inputs=None, parameters=None):
        import uuid
        if start not in STARTS:
            raise PipelineError("START_INVALID", "Select a supported single-sample starting checkpoint.")
        run = cls(scope, "pipeline_" + uuid.uuid4().hex, start, STARTS[start],
                  inputs=dict(inputs or {}), parameters=dict(parameters or {}))
        run.event("CREATED", {"start": start, "not_run": list(STEPS[:run.index])})
        return run

    @property
    def step(self):
        return STEPS[self.index] if self.index < len(STEPS) else "ready_for_dash"

    @property
    def progress(self):
        # Stage-based progress, not a fabricated wall-clock ETA.
        total = len(STEPS) - STARTS[self.start]
        fraction = 0 if self.job_progress is None else min(0.99, max(0, self.job_progress / 100))
        return min(100, 100 * (self.index - STARTS[self.start] + fraction) / total)

    def event(self, kind, detail=None):
        self.events.append({"at": utcnow(), "event": kind, "step": self.step, "detail": detail or {}})

    def assert_scope(self, scope):
        if self.scope != scope:
            raise PipelineError("CROSS_ANALYSIS_DENIED", "This run belongs to another owner or analysis.")

    def begin(self):
        if self.status != "READY":
            return False
        if self.step == "manual_alignment":
            self.status = "WAITING_FOR_MANUAL"
            self.event("MANUAL_CONFIRMATION_REQUIRED")
            return False
        self.status = "DISPATCHING"
        self.event("ACTION_STARTED")
        return True

    def submitted(self, job_id):
        if self.status != "DISPATCHING" or not str(job_id).strip():
            raise PipelineError("SUBMISSION_INVALID", "A real job id is required after dispatch.")
        self.jobs[self.step] = str(job_id)
        self.status = "WAITING_FOR_JOB"
        self.event("JOB_SUBMITTED", {"job_id": str(job_id)})

    def succeed(self, evidence=None):
        self.completed[self.step] = {"at": utcnow(), "evidence": evidence or {}}
        self.event("STEP_SUCCEEDED", evidence)
        self.index += 1
        self.job_progress = None
        self.status = "SUCCEEDED" if self.index == len(STEPS) else "READY"

    def observe(self, *, scope, job_id, status, progress=None, error=""):
        self.assert_scope(scope)
        if self.status != "WAITING_FOR_JOB" or self.jobs.get(self.step) != str(job_id):
            raise PipelineError("JOB_LINEAGE_INVALID", "Job is not the current stage's submitted job.")
        status = str(status).upper()
        if progress is not None and math.isfinite(float(progress)):
            self.job_progress = max(0.0, min(100.0, float(progress)))
        if status in FAILURE:
            self.fail(error or f"Backend job ended with {status}.")
        elif status in SUCCESS:
            # The adapter still must validate artifacts before succeed().
            return True
        return False

    def confirm_manual(self):
        if self.status != "WAITING_FOR_MANUAL":
            raise PipelineError("MANUAL_STATE_INVALID", "No manual alignment confirmation is pending.")
        self.status = "DISPATCHING"
        self.event("MANUAL_CONFIRMED")

    def fail(self, error):
        self.status, self.error = "FAILED", str(error)[:4000]
        self.event("FAILED", {"error": self.error})

    def pause(self):
        if self.status == "DISPATCHING":
            raise PipelineError("ACTION_IN_FLIGHT", "Wait for the current submission to finish.")
        if self.status not in {"SUCCEEDED", "FAILED", "PAUSED"}:
            previous = self.status
            self.status = "PAUSED"
            self.event("PAUSED", {"previous_status": previous, "existing_jobs_continue": True})

    def resume(self):
        if self.status != "PAUSED":
            return
        previous = next(e["detail"]["previous_status"] for e in reversed(self.events) if e["event"] == "PAUSED")
        self.status = previous
        self.event("RESUMED")

    def to_dict(self):
        return {"schema": "spashiny.single_sample_pipeline.v1", **asdict(self)}


def atomic_json(path: Path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".state-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save_run(path, run):
    atomic_json(Path(path), run.to_dict())


def load_run(path, scope):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.pop("schema", None) != "spashiny.single_sample_pipeline.v1":
        raise PipelineError("STATE_VERSION_INVALID", "Unsupported pipeline state version.")
    payload["scope"] = Scope(**payload["scope"])
    run = Run(**payload)
    run.assert_scope(scope)
    if run.status == "DISPATCHING":
        # A crash at this point is ambiguous: never automatically double-submit.
        run.fail("SUBMISSION_RECEIPT_UNKNOWN: inspect existing jobs before starting a new run.")
    return run


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_h5ad(path, *, role, require_image=False, check_values=True, single_sample=True):
    """Read-only, bounded chunk scan; no filtering, normalization or label edits."""
    import anndata as ad
    import numpy as np
    from scipy import sparse

    path = Path(path)
    if path.suffix.lower() != ".h5ad" or not path.is_file():
        raise PipelineError("H5AD_REQUIRED", "A completed, authorized H5AD upload is required.")
    data = ad.read_h5ad(path, backed="r")
    try:
        if min(data.shape) < 1 or data.n_obs < 3:
            raise PipelineError("INPUT_EMPTY", "At least three spatial observations and one feature are required.")
        if not data.obs_names.is_unique or not data.var_names.is_unique:
            raise PipelineError("DUPLICATE_IDENTIFIERS", "Observation and feature identifiers must be unique.")
        xy = np.asarray(data.obsm.get("spatial"))
        if xy.ndim != 2 or xy.shape != (data.n_obs, 2) or not np.isfinite(xy).all():
            raise PipelineError("SPATIAL_INVALID", 'obsm["spatial"] must contain finite N x 2 coordinates.')
        if (np.ptp(xy, axis=0) <= 0).any():
            raise PipelineError("SPATIAL_DEGENERATE", "Both spatial axes must have nonzero extent.")
        samples = {}
        for key in ("sample", "sample_id", "batch"):
            if key in data.obs:
                samples[key] = int(data.obs[key].nunique(dropna=True))
                if single_sample and samples[key] > 1:
                    raise PipelineError("MULTISAMPLE_NOT_SUPPORTED", f"{key} contains multiple samples; use the multi-sample workflow.")
        if role == "joint":
            if "type" not in data.var or not {"ST", "SM"}.issubset(set(data.var["type"].astype(str))):
                raise PipelineError("MODALITY_TYPES_MISSING", "A joint input needs var['type'] containing ST and SM.")
        if require_image:
            images = data.uns.get("spatial", {})
            valid = []
            for key, record in images.items():
                scale = (record.get("scalefactors") or {}).get("tissue_hires_scalef")
                image = (record.get("images") or {}).get("hires")
                if image is not None and scale is not None and np.isfinite(float(scale)) and float(scale) > 0:
                    valid.append(str(key))
            if len(valid) != 1:
                raise PipelineError("ST_IMAGE_INVALID", "Automatic alignment requires exactly one ST hires image and a positive tissue_hires_scalef.")
        if check_values:
            # Bound dense chunks by element count as well as observations.
            chunk_rows = max(1, min(128, 2_000_000 // max(1, data.n_vars)))
            for start in range(0, data.n_obs, chunk_rows):
                block = data.X[start:start + chunk_rows]
                values = block.data if sparse.issparse(block) else np.asarray(block)
                if not np.isfinite(values).all():
                    raise PipelineError("MATRIX_NONFINITE", "Expression/intensity values contain NaN or infinity.")
                if role in {"st", "sm"} and np.any(values < 0):
                    raise PipelineError("MATRIX_NEGATIVE", "The raw ST/SM start expects nonnegative expression/intensity values.")
        return {"filename": path.name, "sha256": sha256_file(path), "shape": list(data.shape),
                "role": role, "sample_counts": samples, "spatial_shape": list(xy.shape),
                "annotation_present": "celltype_ST_SM" in data.obs,
                "value_scan": "PASS" if check_values else "NOT_RUN"}
    finally:
        data.file.close()


async def bounded_child(arguments, *, timeout=300):
    """Only our own child is terminated on timeout; never a scientific worker."""
    process = await asyncio.create_subprocess_exec(*map(str, arguments),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "MPLBACKEND": "Agg", "OMP_NUM_THREADS": "1",
             "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"})
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout)
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.communicate()
        raise
    if process.returncode:
        detail = stderr.decode("utf-8", "replace")[-12000:]
        raise PipelineError("CHILD_FAILED", detail or stdout.decode("utf-8", "replace")[-4000:])
    return stdout.decode("utf-8", "replace")

