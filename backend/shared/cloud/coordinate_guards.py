"""Coordinate contracts and diagnostics; never replace registration or training."""
import numpy as np

NORMALIZATION_VERSION = "spatialmeta_scalar_xmin_xspan_100_v1"


def finite_xy(values, *, name="spatial"):
    xy = np.asarray(values)
    if xy.ndim != 2 or xy.shape[1] != 2 or not len(xy) or not np.isfinite(xy).all():
        raise ValueError(f"{name} must be a nonempty finite n x 2 coordinate array.")
    return xy.astype(np.float64)


def normalized_xy(values):
    """Metadata basis: scalar xmin subtracted from BOTH axes, one x-span scale."""
    xy = finite_xy(values)
    span = np.ptp(xy, axis=0)
    if np.any(span <= 0):
        raise ValueError("Spatial coordinates have a degenerate axis.")
    xmin = float(xy[:, 0].min())
    scale = 100.0 / float(span[0])
    result = (xy - xmin) / float(span[0]) * 100
    return result, {"version": NORMALIZATION_VERSION,
        "formula": "(spatial - scalar_xmin) / x_span * 100",
        "origin": [xmin, xmin], "offset_scalar": xmin, "scale_factor": scale,
        "source_key": "spatial", "normalized_key": "spatial_normalized",
        "x_y_order": "preserved", "aspect_ratio_preserved": True}


def frame_roundtrip_check(source, transformed, *, origin, scale, output_dtype=np.float32):
    """Quantization error in SOURCE units, not a biological accuracy claim."""
    x = finite_xy(source, name="source")
    z = finite_xy(transformed, name="transformed")
    o = np.asarray(origin, dtype=np.float64)
    factor = float(scale)
    if x.shape != z.shape or o.shape != (2,) or not np.isfinite(o).all() or not np.isfinite(factor) or factor <= 0:
        raise ValueError("Invalid coordinate frame or row correspondence.")
    expected = (x - o) * factor
    recovered = z / factor + o
    err = np.linalg.norm(recovered - x, axis=1)
    eps_out = np.finfo(np.dtype(output_dtype)).eps
    eps64 = np.finfo(np.float64).eps
    allowance = 4 * eps_out * max(1.0, float(np.abs(expected).max())) / factor
    allowance += 32 * eps64 * max(1.0, float(np.abs(x).max()))
    max_error = float(err.max())
    record = {"schema": "spashiny.coordinate_roundtrip.v1", "n_points": len(x),
        "scale": factor, "orientation_determinant": factor * factor,
        "source_bounds": [x.min(axis=0).tolist(), x.max(axis=0).tolist()],
        "transformed_bounds": [z.min(axis=0).tolist(), z.max(axis=0).tolist()],
        "max_error_source_units": max_error,
        "rmse_source_units": float(np.sqrt(np.mean(err ** 2))),
        "p95_error_source_units": float(np.percentile(err, 95)),
        "numeric_tolerance_source_units": float(allowance),
        "tolerance_policy": "4 output-dtype ulps inverse-mapped + 32 float64 ulps at source magnitude",
        "passed": bool(max_error <= allowance), "biological_accuracy_test": False}
    if not record["passed"]:
        raise ValueError(f"Coordinate roundtrip exceeds its numeric tolerance: {max_error:g} > {allowance:g}.")
    return record


def registration_quality(initial_points, aligned_points, st_image_points, *, image_scale):
    """Same-frame geometric proxies; never invent independent landmark truth."""
    from scipy.spatial import cKDTree
    before = finite_xy(initial_points, name="initial fitted-frame points")
    after = finite_xy(aligned_points, name="aligned points")
    reference = finite_xy(st_image_points, name="ST image points")
    scale = float(image_scale)
    if before.shape != after.shape or not np.isfinite(scale) or scale <= 0:
        raise ValueError("Registration QA requires matching SM rows and positive image scale.")
    if np.any(np.ptp(after, axis=0) <= 0) or np.linalg.matrix_rank(after - after.mean(axis=0)) < 2:
        raise ValueError("Aligned coordinates collapsed to a point or line.")
    ref_tree = cKDTree(reference)
    d = ref_tree.query(reference, k=2)[0][:, 1] if len(reference) > 1 else np.array([])
    spacing = d[d > 0]
    if not spacing.size:
        raise ValueError("ST coordinates lack distinct reference positions.")
    limit = float(np.median(spacing)) * 1.5
    def stats(points):
        to_st = ref_tree.query(points, k=1)[0]
        from_st = cKDTree(points).query(reference, k=1)[0]
        return {"sm_to_st_rmse_image_pixels": float(np.sqrt(np.mean(to_st ** 2))),
            "sm_to_st_median_image_pixels": float(np.median(to_st)),
            "sm_to_st_p95_image_pixels": float(np.percentile(to_st, 95)),
            "symmetric_mean_nearest_distance_image_pixels": float((to_st.mean() + from_st.mean()) / 2),
            "st_coverage_fraction": float(np.mean(from_st <= limit)),
            "sm_within_st_distance_fraction": float(np.mean(to_st <= limit)),
            "sm_to_st_rmse_full_resolution_pixels": float(np.sqrt(np.mean(to_st ** 2)) / scale)}
    a, b = stats(before), stats(after)
    if b["st_coverage_fraction"] == 0:
        raise ValueError("Registration QA found no ST overlap within the spacing-derived distance limit.")
    improved = b["symmetric_mean_nearest_distance_image_pixels"] <= a["symmetric_mean_nearest_distance_image_pixels"]
    return {"schema": "spashiny.registration_quality.v1", "before": a, "after": b,
        "coordinate_space": "ST hires-image pixels", "image_scale": scale,
        "distance_limit_image_pixels": limit, "distance_policy": "1.5 * median positive nearest ST spacing",
        "nearest_distance_improved": bool(improved),
        "status": "GEOMETRIC_CHECKS_PASSED" if improved else "NEEDS_REVIEW",
        "independent_landmark_error": "UNVERIFIED_NO_LANDMARK_TRUTH",
        "interpretation": "Density/overlap proxies only; not landmark RMSE or proof of biological correspondence."}


def landmark_error(predicted, reference):
    """Optional independently paired truth, for synthetic/annotated tests only."""
    p, r = finite_xy(predicted), finite_xy(reference)
    if p.shape != r.shape:
        raise ValueError("Landmark row identities must correspond exactly.")
    e = np.linalg.norm(p - r, axis=1)
    return {"n_landmarks": len(e), "rmse": float(np.sqrt(np.mean(e ** 2))),
        "max_error": float(e.max()), "p95_error": float(np.percentile(e, 95))}
