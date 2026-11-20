"""Content fingerprints of the verified 102843 input manifest, not filenames.

Provenance: native Scanpy1.9.8 preparation_report.json, 20261031 experiment.
This immutable allowlist is not a generic inference of expression scale.
"""
MANIFEST_VERSION='spa5-102843-content-v1'
FILES={
 'V39_Sham_spatialmeta_qc0.h5ad':'eaf39cdc830be91cd9886e273e689b19afef9fd3176de6da0fb56ef157a7b49e',
 'V28_D1_spatialmeta_qc0.h5ad':'175fe194e2afb0325ae5a2d06c0d0140dbad5d3b739032b4d89eb15ba327625f',
 'V38_D3_spatialmeta_qc0.h5ad':'fe19ff80e7badc364e3516ac1f4b201efa594cf686d11ee774a216dc52d378a9',
 'V44_D7_spatialmeta_qc0.h5ad':'78ae752b47414c3be277ac08f0f4e2cd35d0049fe364fe3f5a403bb73719b1c2',
 'V27_D28_spatialmeta_qc0.h5ad':'b0e0754ac6267d8c412fb70616b16eef017e575b4b301ae8ca39a1563f887811',
}


def recognize_hashes(hashes):
    hashes=list(hashes)
    if len(hashes)==len(FILES) and set(hashes)==set(FILES.values()):
        return {'status':'VERIFIED_CONTENT_MANIFEST','manifest_version':MANIFEST_VERSION,'input_scale':'raw_counts',
            'recommended_input_profile':'spa_data_export','recommended_execution_mode':'original_python_parity'}
    return {'status':'UNVERIFIED_USER_DECLARATION','input_scale':None}
