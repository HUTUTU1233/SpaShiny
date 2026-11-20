"""Runner-only PCA policy. The original scSLAT PCA is never replaced here.

This adapter intentionally does not import Scanpy or rewrite any scientific
function. Both the legacy input contract and the v2 orchestrator must select a
known preparation policy explicitly. General preserves its existing call.
"""


def apply_runner_pca(adata, *, preparation_policy, ensure_pca, trace=None):
    if preparation_policy == 'original_python_parity':
        if trace is not None:
            trace['runner_extra_pca_call_count'] = 0
            trace['pca_source'] = 'scSLAT.load_anndatas(feature=pca)'
            trace['pca_policy'] = '102843-original-slat-only-v1'
        return adata
    if preparation_policy == 'general':
        if trace is not None:
            trace['runner_extra_pca_call_count'] = 1
            trace['pca_source'] = 'runner.ensure_pca + unchanged scSLAT internal preprocessing'
            trace['pca_policy'] = 'existing-general-preserved-v1'
        return ensure_pca(adata, force=True)
    raise ValueError('Unknown River input preparation policy; no PCA fallback is allowed.')
