"""Automatic, narrow102843 CUDA compatibility at the proved lifecycle point.

No seed calls, no model restoration, no CPU/Python/NumPy state setters. General
and legacy jobs never call this entry. Nonreference data never reads the pickle.
"""
import hashlib
import importlib.metadata as md
import inspect
import json
from pathlib import Path
import pickle
from cloud.river_paths import load_server_paths

from river_102843_fingerprints import REFERENCE
from river_passive_trace import array_fingerprint,model_fingerprints

RNG_PATH=load_server_paths()['history_rng']
RNG_SHA256='99bac53c8183a68a7477f56cd995ba272deae39c68cd49e08614d5a655e55244'
EXPECTED_INPUTS={
 'gene_expression':'ca59514e3493f3108382de5f28c1bbd1f2f451b7c3e04a8529f563c50a05fcd2',
 'spatial':'1be2de29b94aed30a8a1a5f286e2b88ee8b7a400cd55209d6502a609fc406046',
 'y':'3788c9468947664f990276529f00b3da4c580732cca08b3ee4ee3935292b3b1d'}
MATCHES=['e318425b4eff9d65ffff4879efb5fbdf559a469c508288f05e77a8c4b839bf53',
 '7aa1ee191f18753d3e44ecb654ffb1696b3a8f3141e8df136da0fac45c90f13a',
 '2eb9f5df29956c78a651f8d6a3963756dc33b342ed4c4ac28c8218d78fb6e9cf',
 'b0680d52a24eeeb9d57a8178c0f03c814c3e463426fc78728d49dc765dfa87af']
VERSIONS={'numpy':'1.24.4','scipy':'1.10.1','pandas':'1.5.3','scanpy':'1.9.8','anndata':'0.9.2',
 'torch':'2.3.1+cu121','captum':'0.7.0','scSLAT':'0.3.0'}
CORE={'river.py':'047563e08b276fa3e43fae09a0c9847a9586c854ee6c9c279d306ff647e77a9c',
 'model.py':'3364f2574d19513b185d97ac7cbcbac6e871d2af8b433bdddfa735a6bf06ca41',
 'preprocess.py':'47b4096de69ac62b0f0d7ab30568b488945d217f3999bc51855216e540942662'}


def eligibility(facts):
    checks={
      'five_original_file_hashes_and_order':facts.get('file_order')==REFERENCE['file_order'],
      'source_spot_counts':facts.get('source_spots')==REFERENCE['source_spots'],
      'source_gene_counts':facts.get('source_genes')==[32140]*5,
      'sampled_spot_counts':facts.get('sampled_spots')==[1052]*5,
      'gene_expression_spatial_y':facts.get('model_inputs')==EXPECTED_INPUTS,
      'four_fresh_slat_matches':facts.get('matching')==MATCHES,
      'initial_model_all14':facts.get('initial_model')==REFERENCE['initial_model'],
      'historical_core_sources':facts.get('core_sources')==CORE,
      'historical_dependency_versions':facts.get('versions')==VERSIONS and facts.get('python')=='3.8.20',
      'unchanged_slat_sources':facts.get('slat_sources_verified') is True,
      'non_cuda_states_already_equal':facts.get('cpu_rng')==REFERENCE['cpu_rng'],
      'actual_river_device_logical0':facts.get('device')=='cuda:0',
    }
    return {'eligible':all(checks.values()),'checks':checks,'reasons':[name for name,ok in checks.items() if not ok],
        'phase':'POST_CONSTRUCTOR_POST_DATALOADERS_PRE_FIRST_TRAIN_ITERATOR',
        'policy_version':'102843-content-and-state-gated-cuda0-v1'}


def _state_fingerprints():
    import random,numpy as np,torch
    return {'python_sha256':hashlib.sha256(pickle.dumps(random.getstate(),protocol=4)).hexdigest(),
      'numpy_sha256':hashlib.sha256(pickle.dumps(np.random.get_state(),protocol=4)).hexdigest(),
      'torch_cpu_sha256':array_fingerprint(torch.get_rng_state())['sha256']}


def maybe_restore_history_cuda0(config,trace,model):
    file_order=[row.get('original_h5ad',{}).get('sha256') for row in config.get('samples',[])]
    if file_order!=REFERENCE['file_order']:
        return {'status':'NOT_APPLIED','reasons':['nonreference_file_content_or_sample_order'],
            'policy_version':'102843-content-and-state-gated-cuda0-v1','restore_count':0}
    from river.river import River
    import platform
    import torch
    from cloud.river_execution_profiles import SC_SLAT
    import scSLAT.model.loaddata as loader
    import scSLAT.model.preprocess as slat_preprocess
    import scSLAT.model.utils as slat_utils
    base=Path(inspect.getfile(River)).resolve().parent
    core={name:hashlib.sha256((base/name).read_bytes()).hexdigest() for name in CORE}
    slat={name:hashlib.sha256(Path(inspect.getfile(module)).read_bytes()).hexdigest()
        for name,module in [('loaddata.py',loader),('preprocess.py',slat_preprocess),('utils.py',slat_utils)]}
    facts={'file_order':file_order,'source_spots':[r.get('spots_before_sampling') for r in trace['sample_checks']],
        'source_genes':[r.get('source_shape',[None,None])[1] for r in trace['sample_checks']],
        'sampled_spots':[r.get('spots_after_sampling') for r in trace['sample_checks']],
        'model_inputs':{k:v['sha256'] for k,v in trace['canonical_model_inputs'].items()},
        'matching':[r['sha256'] for r in trace.get('canonical_matching_fingerprints',[])],
        'initial_model':model_fingerprints(model.model),'core_sources':core,'python':platform.python_version(),
        'versions':{name:md.version(name) for name in VERSIONS},'slat_sources_verified':slat==SC_SLAT,
        'cpu_rng':_state_fingerprints(),'device':str(next(model.model.parameters()).device)}
    decision=eligibility(facts)
    if not decision['eligible']:return {**decision,'status':'NOT_APPLIED','restore_count':0}
    # Server-owned fixed evidence only. Unpickle only after content, numerical,
    # source/version and lifecycle checks AND the immutable file hash pass.
    payload=RNG_PATH.read_bytes() if RNG_PATH.is_file() else b''
    if not payload or hashlib.sha256(payload).hexdigest()!=RNG_SHA256:
        raise RuntimeError('Historical RNG evidence is missing/changed. No forced restore or fallback is allowed.')
    before=_state_fingerprints();cuda_before=array_fingerprint(torch.cuda.get_rng_state(0))['sha256']
    state=pickle.loads(payload)  # Deserialize the SAME bytes whose fixed hash passed.
    historical=state.get('torch_cuda',[])
    if len(historical)!=2 or array_fingerprint(historical[0])['sha256']!=REFERENCE['cuda0_rng']:
        raise RuntimeError('Historical CUDA snapshot identity/phase contract failed.')
    torch.cuda.set_rng_state(historical[0].cpu(),device=next(model.model.parameters()).device)
    after=_state_fingerprints();cuda_after=array_fingerprint(torch.cuda.get_rng_state(0))['sha256']
    if before!=after or cuda_after!=REFERENCE['cuda0_rng']:raise RuntimeError('CUDA-only restoration validation failed.')
    return {**decision,'status':'APPLIED','restore_count':1,'historical_logical_device':0,
        'target_device':str(next(model.model.parameters()).device),'cuda_before_sha256':cuda_before,
        'cuda_after_sha256':cuda_after,'non_cuda_states_unchanged':True,
        'historical_physical_mapping':'UNKNOWN_NOT_INVENTED','rng_evidence_sha256':RNG_SHA256}
