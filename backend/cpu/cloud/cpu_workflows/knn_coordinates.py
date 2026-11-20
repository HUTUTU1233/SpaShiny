"""Resolve KNN units from verifiable H5AD/catalog metadata, never geometry guesses."""
from collections.abc import Mapping
import math
from pathlib import Path
import json

from .common import CPUWorkflowError
from ..knn_tutorial import ACTION, SAMPLE


def _required(message):
    return CPUWorkflowError("COORDINATE_CONTRACT_REQUIRED", message)


def _invalid(message):
    return CPUWorkflowError("COORDINATE_CONTRACT_INVALID", message)


def _xy(adata, key):
    import numpy as np

    if key not in adata.obsm:
        raise _required(f"Aligned data lack the declared obsm[{key!r}]; no raw-coordinate fallback was used.")
    try:
        xy = np.asarray(adata.obsm[key])
        if (xy.shape != (adata.n_obs, 2) or not adata.n_obs
                or xy.dtype.kind not in "iuf" or not np.isfinite(xy).all()):
            raise ValueError("invalid XY")
    except (ValueError, TypeError) as exc:
        raise _invalid(f"obsm[{key!r}] must contain one finite XY pair per observation.") from exc
    return xy


def _library(adata_st, declared, *, image_units):
    libraries = adata_st.uns.get("spatial", {})
    if not isinstance(libraries, Mapping):
        raise _invalid("ST uns['spatial'] is not valid spatial library metadata.")
    if declared and declared not in libraries:
        raise _invalid(f"The declared ST library {declared!r} is absent from the paired ST metadata.")
    if not declared and len(libraries) > 1:
        raise _required("The ST file contains multiple spatial libraries. Supply a single-library ST file or record its st_library_id in the SM coordinate metadata.")
    sample = declared or (str(next(iter(libraries))) if libraries else "")
    if not image_units:
        return sample, None
    if not sample:
        raise _required("ST hires-pixel coordinates require the paired ST spatial library and tissue_hires_scalef.")
    try:
        scale = float(libraries[sample]["scalefactors"]["tissue_hires_scalef"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise _required("The paired ST library has no valid tissue_hires_scalef.") from exc
    if not math.isfinite(scale) or scale <= 0:
        raise _invalid("ST tissue_hires_scalef must be finite and positive.")
    return sample, scale


def _descriptor(record, *, alignment):
    if not isinstance(record, Mapping):
        raise _invalid("SM coordinate metadata must be an object, not a free-text unit guess.")
    schema = "spashiny.alignment.coordinate_contract" if alignment else "spashiny.knn.coordinate_contract"
    if record.get("schema") != schema or record.get("version") != 1:
        raise _invalid("The declared SM coordinate contract schema or version is unsupported.")
    key = "spatial_transformed" if alignment else record.get("source_coordinate_key")
    space = record.get("fit_output_space") if alignment else record.get("input_space")
    if alignment and record.get("st_input_space") != "visium_full_resolution":
        raise _invalid("The Alignment export does not identify the ST full-resolution reference frame.")
    if (key not in ("spatial_transformed", "spatial_transformed_scaled", "spatial")
            or space not in ("st_full_resolution", "st_image_pixels")):
        raise _invalid("The declared SM coordinate key or units are unsupported.")
    names = {str(record[k]) for k in ("st_library_id", "sample_name") if record.get(k)}
    if len(names) > 1:
        raise _invalid("The SM metadata names two different ST libraries.")
    return key, space, next(iter(names), ""), record.get("to_st_full_resolution_scale")


def coordinate_contract(ctx, adata_st, adata_sm, lineage):
    import numpy as np

    mode = str(lineage["source_mode"])
    records = []
    if mode == "EXAMPLE":
        if lineage.get("example_action_id") != ACTION:
            raise _invalid("Unknown official example coordinate contract.")
        records.append(("spatial_transformed", "st_image_pixels", SAMPLE, None))
        evidence = "sha256_verified_y7_catalog_hires_coordinates"
    elif mode == "USER_UPLOAD":
        root = (ctx.workspace.parent.parent / "owners" / ctx.owner_session_id / "analysis_sessions"
                / lineage["analysis_session_id"] / "workflows" / lineage["parent_workflow_id"])
        try:
            manifest = json.loads((root / "alignment_handoff_manifest.json").read_text())
        except (OSError, ValueError) as exc:
            raise _required("The exact Alignment Step6 coordinate contract is missing. Re-save Step6 in this analysis.") from exc
        records.append(_descriptor(manifest.get("coordinate_contract"), alignment=True))
        evidence = "exact_alignment_step6_manifest"
    elif mode == "USER_UPLOAD_ALIGNED_PAIR":
        for name, alignment in (("spashiny_alignment_coordinate_contract", True),
                                ("spashiny_knn_coordinate_contract", False)):
            if name in adata_sm.uns:
                records.append(_descriptor(adata_sm.uns[name], alignment=alignment))
        evidence = "embedded_h5ad_coordinate_metadata"
        if not records:
            # Recognize the notebook's two explicitly named coordinate arrays
            # only when the recorded ST image scale verifies their relation.
            # A coordinate name by itself (or a similar bounding box) proves nothing.
            if not {"spatial_transformed", "spatial_transformed_scaled"}.issubset(adata_sm.obsm):
                raise _required("Cannot confirm the aligned SM coordinate units from H5AD metadata. Upload an Alignment Step6 export or provide a valid spashiny_knn_coordinate_contract in SM.uns. No units were guessed.")
            records.append(("spatial_transformed", "st_image_pixels", "", None))
            evidence = "verified_notebook_hires_full_resolution_pair"
    else:
        raise _invalid("Unknown KNN input source.")

    key, space, library, _ = records[0]
    names = {record[2] for record in records if record[2]}
    if len(names) > 1 or any(record[:2] != (key, space) for record in records):
        raise _invalid("The SM coordinate metadata declarations disagree.")
    sample, scale = _library(adata_st, next(iter(names), library), image_units=space == "st_image_pixels")
    factor = 1.0 / scale if scale is not None else 1.0
    for _, _, _, claimed in records:
        if claimed is None:
            continue
        try:
            agrees = math.isclose(float(claimed), factor, rel_tol=1e-6, abs_tol=0)
        except (ValueError, TypeError, OverflowError) as exc:
            raise _invalid("The recorded coordinate scale is not numeric.") from exc
        if not agrees:
            raise _invalid("The recorded SM coordinate scale conflicts with the paired ST metadata.")
    xy = _xy(adata_sm, key)
    if (mode == "USER_UPLOAD_ALIGNED_PAIR" and space == "st_image_pixels"
            and key == "spatial_transformed" and "spatial_transformed_scaled" in adata_sm.obsm):
        if not np.allclose(_xy(adata_sm, "spatial_transformed_scaled"), xy / scale, rtol=1e-6, atol=1e-5):
            raise _invalid("SM hires and full-resolution coordinate arrays disagree with ST tissue_hires_scalef.")
    return {"schema": "spashiny.knn.coordinate_contract", "version": 1,
            "source_coordinate_key": key, "input_space": space, "to_st_full_resolution_scale": factor,
            "st_tissue_hires_scalef": scale, "evidence": evidence, "sample_name": sample}


def prepare_coordinates(ctx, adata_st, adata_sm, lineage):
    import numpy as np

    contract = coordinate_contract(ctx, adata_st, adata_sm, lineage)
    transformed = _xy(adata_sm, contract["source_coordinate_key"])
    original = _xy(adata_sm, "spatial") if "spatial" in adata_sm.obsm else transformed
    _xy(adata_st, "spatial")
    working = adata_sm.copy()
    working.obsm["spatial_input_original"] = original.copy()
    scale = contract.pop("st_tissue_hires_scalef")
    xy = transformed / scale if scale is not None else transformed.copy()
    if not np.isfinite(xy).all():
        raise _invalid("SM coordinates became nonfinite after unit conversion.")
    working.obsm["spatial"] = xy
    if scale is not None:
        working.obsm["spatial_transformed_scaled"] = xy.copy()
        contract["st_tissue_hires_scalef"] = scale
    contract = {**contract, "target_space": "visium_full_resolution", "canonical_coordinate_key": "spatial",
        "source_file_unchanged": True, "input_bounds": [transformed.min(axis=0).tolist(), transformed.max(axis=0).tolist()],
        "output_bounds": [working.obsm["spatial"].min(axis=0).tolist(), working.obsm["spatial"].max(axis=0).tolist()]}
    working.uns["spashiny_knn_coordinate_contract"] = dict(contract)
    return working, contract


def coverage(adata_st, adata_sm, distance_limit):
    import numpy as np
    from scipy.spatial import cKDTree

    st = np.asarray(adata_st.obsm["spatial"], dtype=float)
    sm = np.asarray(adata_sm.obsm["spatial"], dtype=float)
    distances, _ = cKDTree(sm).query(st, k=1)
    matched = distances <= float(distance_limit)
    record = {"st_observations": len(st), "sm_observations": len(sm),
        "distance_limit": float(distance_limit), "st_with_sm_neighbor": int(matched.sum()),
        "st_without_sm_neighbor": int((~matched).sum()), "coverage_fraction": float(matched.mean()),
        "nearest_sm_distance_median": float(np.median(distances)), "nearest_sm_distance_max": float(distances.max())}
    if not matched.any():
        raise CPUWorkflowError("KNN_NO_SPATIAL_OVERLAP", "No ST position has an aligned SM neighbor within the KNN distance limit. Check coordinate units and alignment; a zero-filled result is not accepted.")
    return record


def matrix_quality(adata_st, adata_sm):
    import numpy as np
    from scipy import sparse

    out = {}
    for name, data in (("st", adata_st), ("sm", adata_sm)):
        values = data.X.data if sparse.issparse(data.X) else np.asarray(data.X).ravel()
        sums = np.asarray(data.X.sum(axis=1)).ravel()
        if not values.size or not np.isfinite(values).all() or not np.count_nonzero(values):
            raise CPUWorkflowError("KNN_ZERO_OR_INVALID_MODALITY", f"KNN {name.upper()} output has no non-zero finite signal. This is not a valid completed scientific result.")
        out[name] = {"shape": list(data.shape), "nonzero_values": int(np.count_nonzero(values)),
            "nonzero_rows": int(np.count_nonzero(sums)), "zero_rows": int(np.count_nonzero(sums == 0)),
            "sum": float(sums.sum())}
    st_xy = np.asarray(adata_st.obsm["spatial"])
    sm_xy = np.asarray(adata_sm.obsm["spatial"])
    if (adata_st.n_obs != adata_sm.n_obs or not np.array_equal(st_xy, sm_xy)
            or list(adata_st.obs["spot_name"]) != list(adata_sm.obs["spot_name"])):
        raise CPUWorkflowError("KNN_PAIR_MISMATCH", "Reassigned ST/SM positions or spot identifiers do not match exactly.")
    return {"status": "PASS", "same_spatial_coordinates": True, "same_spot_order": True, **out}
