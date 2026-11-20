"""Pinned inputs and parameters for the published Y7_T Reassignment example."""

ACTION = "y7-knn-reassignment-example"
POLICY = "spatialmeta-y7-reassignment-raw-v1"
SAMPLE = "Y7_T"
THRESHOLD = 2_000_000.0
K = 5
DIST_FOLD = 1.5
INPUTS = {
    "st": ((1914, 36404), "878e4373a550e2069ae93ec6856b3c7b0884db01b26387b0c2ef667a069a6b76"),
    "sm": ((10649, 500), "42b7c816241cce91037d4e63f0d03ad4931e97a7fce425946f9ce98a1dec1a0c"),
    "sm_raw": ((10649, 1299), "43103c4645e888df074ffaf420119c522c814d08133236477ef0df4873603ee5"),
}


def example_parameters():
    return {
        "n_neighbors": K, "dist_fold": DIST_FOLD,
        "initial_min_total_intensity": THRESHOLD,
        "post_min_total_intensity": THRESHOLD,
        "preview_sample_name": SAMPLE,
        "tutorial_policy": POLICY,
    }
