"""Provenance and coordinate contracts; never change expression or identities."""
import hashlib
import json
import numpy as np


def mark_independent_reference(adata, source_sha256=''):
    """Metadata only: a precomputed reference is never this analysis's result."""
    record={'data_role':'INDEPENDENT_REFERENCE',
        'source_sha256':str(source_sha256 or 'UNKNOWN'),
        'parent_run_status':'UNKNOWN','current_pipeline_result':False}
    adata.uns['spashiny_reference_provenance']=record
    return record


def reference_species(adata, selected):
    values=set()
    if 'genome' in adata.var:
        values={str(x) for x in adata.var['genome'].dropna().unique() if str(x)}
    human={'GRCh38','GRCh37','hg38','hg19'}
    mouse={'GRCm38','GRCm39','mm10','mm39'}
    inferred='Human' if values and values.issubset(human) else 'Mouse' if values and values.issubset(mouse) else None
    if selected is None:
        selected=inferred
    if inferred and selected!=inferred:
        raise ValueError(f'Selected species {selected} conflicts with the input reference genome {sorted(values)} ({inferred}). Select the matching species; no data were modified.')
    if selected not in {'Human','Mouse'}:
        raise ValueError('Select Human or Mouse explicitly for mitochondrial QC.')
    return {'species':selected,'reference_genomes':sorted(values),'evidence':'var.genome' if inferred else 'user_selection','metrics_stage':'input_before_gene_removal'}


def calculate_st_input_qc(adata, selected):
    import scanpy as sc
    record=reference_species(adata,selected)
    prefix='MT-' if record['species']=='Human' else 'mt-'
    adata.var['mt']=adata.var_names.str.startswith(prefix)
    sc.pp.calculate_qc_metrics(adata,qc_vars=['mt'],percent_top=[n for n in (50,100,200,500) if n<=adata.n_vars],inplace=True)
    record.update(mitochondrial_prefix=prefix,mitochondrial_features=int(adata.var['mt'].sum()),
        input_shape=list(adata.shape),matrix_source='input.X; no normalization performed',
        observation_order_sha256=hashlib.sha256(json.dumps(list(adata.obs_names)).encode()).hexdigest())
    adata.uns['spashiny_st_qc_metadata']=record
    return record


def record_post_filter_qc(adata):
    """Keep pre-removal QC fields; label current-matrix statistics separately."""
    adata.obs['post_filter_total_counts']=np.asarray(adata.X.sum(axis=1)).reshape(-1)
    adata.obs['post_filter_n_genes_by_counts']=np.asarray((adata.X>0).sum(axis=1)).reshape(-1)
    record=dict(adata.uns.get('spashiny_st_qc_metadata',{}))
    record.update(output_shape=list(adata.shape),qc_fields_stage='input_before_gene_removal',
        current_matrix_fields=['post_filter_total_counts','post_filter_n_genes_by_counts'])
    adata.uns['spashiny_st_qc_metadata']=record


def validate_xy(adata,key='spatial'):
    if key not in adata.obsm:
        raise ValueError(f'Missing real spatial coordinates: obsm[{key!r}].')
    xy=np.asarray(adata.obsm[key])
    if xy.shape!=(adata.n_obs,2) or not np.isfinite(xy).all():
        raise ValueError('Spatial coordinates must be a finite n_obs x 2 array; no synthetic coordinates or truncation allowed.')
    if np.any(np.ptp(xy,axis=0)<=0):
        raise ValueError('Spatial coordinates have a degenerate axis; inspect the original coordinate source.')
    return xy


def normalize_alignment_coordinates(adata, *, modality, source_sha256=''):
    """Use the exact tutorial's x-span isotropic formula, not axis-wise warping.

    `spatial` remains unchanged. `spatial_normalized` is a separate model-space
    coordinate set. Already-transformed imported coordinates are explicitly
    labelled, never silently treated as raw MSI pixel indices.
    """
    xy=validate_xy(adata)
    from cloud.coordinate_guards import normalized_xy
    if modality == 'SM' and 'spashiny_sm_coordinate_input' in adata.uns:
        from cloud.sm_coordinate_policy import finalize_sm_coordinates
        finalize_sm_coordinates(adata)
    normalized, definition = normalized_xy(xy)
    xmin=definition['offset_scalar'];span=100.0/definition['scale_factor']
    if not np.isfinite(normalized).all():raise ValueError('Non-finite normalized coordinates.')
    adata.obsm['spatial_normalized']=normalized
    space='UNKNOWN_IMPORTED'
    if modality=='ST' and 'spatial' in adata.uns:
        space='VISIUM_FULL_RES_IMAGE_PIXELS'
    if modality=='SM' and 'spatial_transformed_scaled' in adata.obsm and np.array_equal(xy,np.asarray(adata.obsm['spatial_transformed_scaled'])):
        space='IMPORTED_TRANSFORMED_SCALED; NOT_ORIGINAL_MSI_GRID'
    if modality=='SM' and 'spashiny_sm_coordinate_last_transform' in adata.uns:
        space='MANUAL_PREALIGNED; verified coordinate ledger; NOT_ORIGINAL_MSI_GRID'
    if modality=='SM' and {'x_coord_original','y_coord_original'}.issubset(adata.obs.columns):
        original=adata.obs[['x_coord_original','y_coord_original']].to_numpy()
        if original.shape!=xy.shape or not np.isfinite(original).all():raise ValueError('Invalid original MSI coordinates.')
        adata.obsm['spatial_msi_original']=original.copy()
    record={'schema':'spashiny.spatial_coordinate_contract.v1','modality':modality,
        'source_sha256':str(source_sha256),'input_key':'spatial','input_space':space,
        'normalized_key':'spatial_normalized','normalized_units':'x-span=100; common scalar for both axes',
        'formula':'(spatial - xmin) / (xmax - xmin) * 100','offset_scalar':xmin,'scale_factor':100/span,
        'input_spatial_unchanged':True,'automatic_rotation_or_mirror':False,
        'x_y_order':'columns preserved, no swap','spatial_transformed_usage':'not normalized or reused as an original grid',
        'normalized_range_min':normalized.min(axis=0).tolist(),'normalized_range_max':normalized.max(axis=0).tolist(),
        'normalization_version':definition['version'],'definition':definition}
    adata.uns['spashiny_spatial_coordinate_contract']=record
    return record
