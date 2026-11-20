"""Versioned SM coordinate state; no expression preprocessing or registration."""
import copy
import datetime
import hashlib
import json
import numpy as np
from .coordinate_guards import finite_xy, normalized_xy

VERSION = 'sm_coordinate_policy_v1'
RAW = 'RAW_MSI_GRID'
TRANSFORMED = 'TRANSFORMED_SCALED'
MANUAL = 'MANUAL_PREALIGNED'
UNKNOWN = 'UNKNOWN'


def xy_hash(xy):
    a = np.ascontiguousarray(finite_xy(xy), dtype=np.float64)
    return hashlib.sha256(str(a.shape).encode() + a.tobytes()).hexdigest()


def _coordinates(values):
    xy = finite_xy(values)
    if np.any(np.ptp(xy, axis=0) <= 0) or np.linalg.matrix_rank(xy - xy.mean(0)) < 2:
        raise ValueError('SM coordinates must span two non-degenerate axes.')
    return xy


def detect_input_state(adata):
    current = _coordinates(adata.obsm['spatial'])
    last = adata.uns.get('spashiny_sm_coordinate_last_transform') or {}
    if last.get('version') == VERSION and last.get('output_coordinates_sha256') == xy_hash(current):
        return {'state': MANUAL, 'evidence': 'verified_current_transform_record'}
    grid = None
    if {'x_coord_original', 'y_coord_original'}.issubset(adata.obs.columns):
        grid = _coordinates(adata.obs[['x_coord_original', 'y_coord_original']].to_numpy())
    transformed = adata.obsm.get('spatial_transformed_scaled')
    raw_equal = grid is not None and np.array_equal(current, grid)
    transformed_equal = transformed is not None and np.array_equal(current, _coordinates(transformed))
    if transformed_equal:
        # Even an identity transform marker must not trigger automatic rotation.
        return {'state': TRANSFORMED, 'evidence': 'exact_spatial_transformed_scaled_match',
                'also_matches_original_grid': bool(raw_equal)}
    if raw_equal:
        return {'state': RAW, 'evidence': 'exact_original_MSI_grid_match'}
    return {'state': UNKNOWN, 'evidence': 'no_verified_coordinate_state'}


def initialize_sm_coordinates(adata):
    """Preserve imported coordinates, defer authoritative normalized metadata."""
    _coordinates(adata.obsm['spatial'])
    if 'spatial_input_original' not in adata.obsm:
        adata.obsm['spatial_input_original'] = np.asarray(adata.obsm['spatial']).copy()
    if {'x_coord_original', 'y_coord_original'}.issubset(adata.obs.columns):
        grid = adata.obs[['x_coord_original', 'y_coord_original']].to_numpy()
        _coordinates(grid)
        if 'spatial_msi_original' in adata.obsm and not np.array_equal(adata.obsm['spatial_msi_original'], grid):
            raise ValueError('Stored original MSI coordinates conflict with original observation columns.')
        adata.obsm['spatial_msi_original'] = grid.copy()
    if 'spatial_normalized' in adata.obsm:
        if 'spatial_normalized_imported' not in adata.obsm:
            adata.obsm['spatial_normalized_imported'] = np.asarray(adata.obsm['spatial_normalized']).copy()
        del adata.obsm['spatial_normalized']
    state = detect_input_state(adata)
    adata.uns['spashiny_sm_coordinate_input'] = {
        'version': VERSION, **state, 'input_coordinates_sha256': xy_hash(adata.obsm['spatial']),
        'original_import_coordinates_sha256': xy_hash(adata.obsm['spatial_input_original']),
        'normalized_status': 'PENDING_FINAL_MANUAL_TRANSFORM', 'automatic_rotation_applied': False,
        'model_input_key': 'spatial', 'original_files_modified': False}
    return dict(adata.uns['spashiny_sm_coordinate_input'])


def capture_sm_coordinate_state(adata):
    """AnnDataSM feature slicing may drop obsm fields: preserve them explicitly."""
    return {'obs_names': tuple(map(str, adata.obs_names)),
            'obsm': {k: np.asarray(v).copy() for k,v in adata.obsm.items() if k.startswith('spatial')},
            'input_record': copy.deepcopy(adata.uns.get('spashiny_sm_coordinate_input') or {})}


def restore_sm_coordinate_state(adata, snapshot):
    if tuple(map(str, adata.obs_names)) != snapshot['obs_names']:
        raise ValueError('SM observation identity/order changed during feature preprocessing.')
    for k,v in snapshot['obsm'].items():
        adata.obsm[k] = v.copy()
    adata.uns['spashiny_sm_coordinate_input'] = copy.deepcopy(snapshot['input_record'])


def copy_with_coordinate_state(adata):
    """Preserve spatial fields discarded by the installed AnnDataSM.copy()."""
    snapshot = capture_sm_coordinate_state(adata)
    result = adata.copy()
    restore_sm_coordinate_state(result, snapshot)
    for key,value in adata.uns.items():
        if key.startswith('spashiny_sm_coordinate'):
            result.uns[key] = copy.deepcopy(value)
    return result


def initial_sm_display_coordinates(adata):
    """Select verified original grid AFTER frozen expression/Moran preprocessing.

    This is a coordinate-source reset, never a rotation/flip/scale operation.
    Imported coordinates remain in spatial_input_original.
    """
    if 'spatial_input_original' not in adata.obsm:
        initialize_sm_coordinates(adata)
    source = 'current_spatial'
    if 'spatial_msi_original' in adata.obsm:
        adata.obsm['spatial'] = np.asarray(adata.obsm['spatial_msi_original']).copy()
        source = 'original_msi_grid'
    rec = initialize_sm_coordinates(adata)
    rec.update(initial_display_source=source, initial_rotation=0.0, initial_flip=False,
               initial_scale_multiplier=1.0, initial_translation=[0.0,0.0],
               feature_selection_coordinate_basis='imported spatial before initial-display source reset')
    adata.uns['spashiny_sm_coordinate_input'] = rec
    return dict(rec)


def source_coordinates(adata, coordinate_source='current_spatial', declared_state='auto'):
    if coordinate_source == 'original_msi_grid':
        if 'spatial_msi_original' not in adata.obsm:
            raise ValueError('Original MSI grid is unavailable; no synthetic grid or range-based inference is allowed.')
        return np.asarray(adata.obsm['spatial_msi_original']).copy(), {'state': RAW, 'evidence': 'explicit_original_MSI_grid_selection'}
    if coordinate_source == 'imported_file_spatial':
        if 'spatial_input_original' not in adata.obsm:
            raise ValueError('Imported coordinate snapshot is unavailable.')
        from types import SimpleNamespace
        imported = np.asarray(adata.obsm['spatial_input_original']).copy()
        probe = SimpleNamespace(obsm={**dict(adata.obsm), 'spatial': imported},uns=adata.uns,obs=adata.obs)
        detected = detect_input_state(probe)
        current = imported
    elif coordinate_source == 'current_spatial':
        detected = detect_input_state(adata)
        current = np.asarray(adata.obsm['spatial']).copy()
    else:
        raise ValueError('Choose current_spatial, imported_file_spatial or original_msi_grid explicitly.')
    declarations = {'auto': None, 'raw_msi_grid': RAW, 'transformed_scaled': TRANSFORMED}
    if declared_state not in declarations:
        raise ValueError('Unknown SM coordinate-state declaration.')
    declared = declarations[declared_state]
    if declared and detected['state'] not in {UNKNOWN, declared}:
        raise ValueError('Declared SM state conflicts with verified coordinates; use the original MSI source selector instead.')
    if declared and detected['state'] == UNKNOWN:
        detected = {'state': declared, 'evidence': 'explicit_user_declaration_not_independently_verified'}
    return current, detected


def resolved_transform(adata, request):
    request = dict(request or {})
    source = request.get('coordinate_source', 'current_spatial')
    xy, state = source_coordinates(adata, source, request.get('declared_state', 'auto'))
    profile = request.get('profile', 'manual')
    if profile != 'manual':
        raise ValueError('Automatic tutorial rotation is disabled. Use the explicit manual rotation control.')
    params = {k: float(request.get(k, default)) for k, default in {
        'rotation': 0, 'scale_width': 1, 'scale_height': 1, 'translation_x': 0, 'translation_y': 0}.items()}
    params.update(horizontal_flip=bool(request.get('horizontal_flip', False)),
                  vertical_flip=bool(request.get('vertical_flip', False)))
    reason = 'explicit_user_manual_controls_no_automatic_rotation'
    if not np.isfinite([params[k] for k in ['rotation','scale_width','scale_height','translation_x','translation_y']]).all():
        raise ValueError('Coordinate transform parameters must be finite.')
    if params['scale_width'] <= 0 or params['scale_height'] <= 0:
        raise ValueError('Scale is a positive multiplier: 1 means unchanged, not 100 or 190 percent.')
    if not np.isclose(params['scale_width'], params['scale_height'], rtol=1e-12, atol=0):
        raise ValueError('Non-isotropic width/height scaling is prohibited. Use equal multipliers to preserve tissue aspect ratio.')
    return xy, state, params, {'profile': profile, 'coordinate_source': source, 'reason': reason}


def finalize_sm_coordinates(adata):
    """One authoritative snapshot, only after the final manual transform."""
    last = adata.uns.get('spashiny_sm_coordinate_last_transform') or {}
    if last.get('version') != VERSION or last.get('output_coordinates_sha256') != xy_hash(adata.obsm['spatial']):
        raise ValueError('Final normalized coordinates require a matching current manual transform record.')
    normalized, definition = normalized_xy(adata.obsm['spatial'])
    adata.obsm['spatial_normalized'] = normalized
    adata.uns['spashiny_sm_coordinate_normalization'] = {
        **definition, 'definition_version': definition['version'], 'version': VERSION,
        'stage': 'AFTER_FINAL_MANUAL_TRANSFORM',
        'coordinates_sha256': xy_hash(adata.obsm['spatial']),
        'normalized_coordinates_sha256': xy_hash(normalized), 'model_input_key': 'spatial',
        'KNN_input_key': 'spatial_transformed_with_explicit_image_scale', 'normalized_is_physical_coordinates': False}
    return dict(adata.uns['spashiny_sm_coordinate_normalization'])


def restore_manual_coordinates(base, coordinates, record):
    """Restore an already computed artifact: never apply rotation a second time."""
    if record.get('version') != VERSION:
        raise ValueError('Current coordinate-policy record is required; re-run this Stage manual preview.')
    result = copy_with_coordinate_state(base)
    if 'spatial_input_original' not in result.obsm:
        initialize_sm_coordinates(result)
    source, _ = source_coordinates(result, record['coordinate_source'], record.get('declared_state', 'auto'))
    if xy_hash(source) != record['input_coordinates_sha256'] or xy_hash(coordinates) != record['output_coordinates_sha256']:
        raise ValueError('Manual artifact source/output coordinate fingerprint does not match this input.')
    result.obsm['spatial'] = np.asarray(coordinates).copy()
    history = copy.deepcopy(result.uns.get('spashiny_sm_coordinate_history') or {})
    history[record['transform_id']] = copy.deepcopy(record)
    result.uns['spashiny_sm_coordinate_history'] = history
    result.uns['spashiny_sm_coordinate_last_transform'] = copy.deepcopy(record)
    finalize_sm_coordinates(result)
    return result


def transform_sm_coordinates(base, request, native_transform):
    """Call the installed SpatialMETA transform, preserving the original basis."""
    prepared = copy_with_coordinate_state(base)
    if 'spatial_input_original' not in prepared.obsm:
        initialize_sm_coordinates(prepared)
    source, state, params, policy = resolved_transform(prepared, request)
    result = copy_with_coordinate_state(prepared);result.obsm['spatial'] = source.copy()
    no_op = (params['rotation'] == 0 and not params['horizontal_flip'] and not params['vertical_flip']
             and params['scale_width'] == 1 and params['scale_height'] == 1
             and params['translation_x'] == 0 and params['translation_y'] == 0)
    if not no_op:
        native_transform(adata=result, **params, spatial_key_SM='spatial', new_spatial_key_SM='spatial')
    output = np.asarray(result.obsm['spatial'], dtype=np.float32)
    _coordinates(output)
    theta = np.deg2rad(params['rotation']);c,s = np.cos(theta),np.sin(theta)
    flips = np.diag([-1 if params['horizontal_flip'] else 1, -1 if params['vertical_flip'] else 1])
    linear = params['scale_width'] * np.array([[c,-s],[s,c]]) @ flips
    shift = np.median(output.astype(float) - source.astype(float) @ linear.T, axis=0)
    reconstructed = source.astype(float) @ linear.T + shift
    error = float(np.max(np.linalg.norm(reconstructed-output,axis=1)))
    tolerance = 16*np.finfo(np.float32).eps*max(1.,float(np.abs(output).max()))
    if error > tolerance:
        raise ValueError('Native transform cannot be reconciled with the recorded affine map.')
    matrix = np.eye(3);matrix[:2,:2]=linear;matrix[:2,2]=shift
    record = {'version': VERSION, **policy, 'input_state': state['state'], 'state_evidence': state['evidence'],
        'declared_state': (request or {}).get('declared_state','auto'), 'output_state': MANUAL,
        'input_coordinates_sha256': xy_hash(source), 'output_coordinates_sha256': xy_hash(output),
        'original_import_coordinates_sha256': xy_hash(prepared.obsm['spatial_input_original']),
        'parameters': params, 'scale_unit': 'multiplier; 1=unchanged', 'isotropic_scale': True,
        'automatic_rotation_applied': False,
        'input_dtype': str(source.dtype), 'persisted_output_dtype': str(output.dtype),
        'affine_matrix_3x3': matrix.tolist(), 'affine_max_error': error, 'affine_numeric_tolerance': tolerance,
        'native_positive_shift_included': True, 'row_and_axis_order_preserved': True}
    record['transform_id'] = 't_'+hashlib.sha256(json.dumps(record,sort_keys=True).encode()).hexdigest()[:24]
    record['created_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return restore_manual_coordinates(prepared, output, record), record


def assert_final_coordinates(adata):
    m = adata.uns.get('spashiny_sm_coordinate_normalization') or {}
    if m.get('stage') != 'AFTER_FINAL_MANUAL_TRANSFORM' or m.get('coordinates_sha256') != xy_hash(adata.obsm['spatial']):
        raise ValueError('SM spatial changed after final normalization; re-apply the current manual transform.')
    expected,_=normalized_xy(adata.obsm['spatial'])
    if 'spatial_normalized' not in adata.obsm or not np.array_equal(expected,adata.obsm['spatial_normalized']):
        raise ValueError('SM normalized metadata is stale or uses a different coordinate definition.')
