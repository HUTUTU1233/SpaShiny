"""Fixed KNN input-inspection contract; ordinary KNN validation is unchanged."""
KNN_INPUT_OPERATIONS = frozenset({"input_qc", "input_preview"})
KNN_INPUT_REQUIRED = (
    "summary.json", "manifest.json", "session_info.txt", "logs/stdout.log", "logs/stderr.log",
    "knn_input_inspection.json", "knn_initial_qc.csv", "knn_st_prepared.h5ad", "knn_sm_prepared.h5ad",
    "figures/knn_input_overlay.png", "figures/knn_input_overlay.pdf",
)
KNN_RESULT_ADDITIONAL_REQUIRED = (
    "knn_quality.json", "knn_joint_plots.pdf", "knn_full_report.pdf",
    "figures/knn_reassignment_spatial.png", "figures/knn_reassignment_spatial.pdf",
    "figures/knn_intensity_histograms.png", "figures/knn_intensity_histograms.pdf",
    "figures/knn_joint_intensity.png", "figures/knn_joint_intensity.pdf",
    "figures/knn_joint_counts.png", "figures/knn_joint_counts.pdf",
)


def knn_required_outputs(workflow, parameters, default):
    if workflow == "integration_postprocessing" and (parameters or {}).get("operation") in KNN_INPUT_OPERATIONS:
        result = KNN_INPUT_REQUIRED
        if parameters.get("operation") == "input_preview":
            result += ("figures/knn_scaled_preview.png", "figures/knn_scaled_preview.pdf")
        return result
    if workflow == "integration_postprocessing" and (parameters or {}).get("knn_result_contract") == "r19":
        return tuple(dict.fromkeys((*default, *KNN_RESULT_ADDITIONAL_REQUIRED)))
    return default
