"""Join full SM expression to verified fitted coordinates, never to selected X."""

EXPRESSION_KEY = "spashiny_knn_expression"
EXPRESSION_SOURCE = "original_full_sm.X"


def full_expression_with_alignment(raw, aligned, *, require_original_pixels=False):
    import numpy as np
    from scipy import sparse

    if not (raw.obs_names.is_unique and aligned.obs_names.is_unique
            and raw.var_names.is_unique and aligned.var_names.is_unique):
        raise ValueError("Raw and aligned SM require unique spot and feature identifiers.")
    positions = aligned.obs_names.get_indexer(raw.obs_names)
    if len(positions) != aligned.n_obs or (positions < 0).any() or not raw.n_obs:
        raise ValueError("Raw and aligned SM spot identifiers differ. Coordinates cannot be joined by row position.")
    for column in ("x_coord_original", "y_coord_original"):
        if column in raw.obs and column in aligned.obs:
            if not np.array_equal(raw.obs[column].to_numpy(), aligned.obs[column].to_numpy()[positions]):
                raise ValueError("Raw and aligned SM original pixel coordinates disagree by spot identifier.")
        elif require_original_pixels:
            raise ValueError("The official Raw/Aligned SM pair must retain original pixel identifiers.")
    if not set(aligned.var_names).issubset(raw.var_names):
        raise ValueError("Aligned features are not a subset of the supplied complete SM expression.")
    if "spatial_transformed" not in aligned.obsm:
        raise ValueError("Aligned SM lacks spatial_transformed. Original coordinates cannot substitute for the fit.")
    fitted = np.asarray(aligned.obsm["spatial_transformed"])
    if (fitted.shape != (aligned.n_obs, 2) or fitted.dtype.kind not in "iuf"
            or not np.isfinite(fitted).all()):
        raise ValueError("Aligned SM must have exactly one finite fitted XY pair per spot.")
    values = raw.X.data if sparse.issparse(raw.X) else np.asarray(raw.X)
    if values.dtype.kind not in "iuf" or not np.isfinite(values).all() or not np.count_nonzero(values):
        raise ValueError("Original SM expression must have non-zero finite signal.")
    if require_original_pixels and ((values < 0).any() or "log1p" in raw.uns):
        raise ValueError("The official example requires raw, non-negative SM intensities.")
    working = raw.copy()
    # A previous fitted frame embedded in the source is not evidence for this
    # new fit. This changes only the derived copy; raw X and IDs stay intact.
    working.obsm.pop("spatial_transformed_scaled", None)
    working.uns.pop("spashiny_knn_coordinate_contract", None)
    working.uns.pop("spashiny_alignment_coordinate_contract", None)
    working.obsm["spatial_transformed"] = fitted[positions].copy()
    return working


def expression_record(raw_sha256, shape):
    return {"schema": "spashiny.knn.expression.v1", "source": EXPRESSION_SOURCE,
            "original_sm_sha256": raw_sha256, "shape": [int(n) for n in shape],
            "coordinates_only_from_alignment": True}


def is_full_source_export(adata, expected_sha256=None):
    from collections.abc import Mapping
    import numpy as np
    import re

    record = adata.uns.get(EXPRESSION_KEY)
    if not isinstance(record, Mapping):
        return False
    schema, source = record.get("schema"), record.get("source")
    flag, sha = record.get("coordinates_only_from_alignment"), record.get("original_sm_sha256")
    shape = np.asarray(record.get("shape"))
    return bool(isinstance(schema, str) and schema == "spashiny.knn.expression.v1"
                and isinstance(source, str) and source == EXPRESSION_SOURCE
                and isinstance(flag, (bool, np.bool_)) and flag
                and shape.shape == (2,) and shape.dtype.kind in "iu"
                and tuple(shape) == tuple(adata.shape)
                and isinstance(sha, str) and re.fullmatch(r"[a-f0-9]{64}", sha)
                and (expected_sha256 is None or sha == expected_sha256))
