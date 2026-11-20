"""Aggregate-only fingerprints. No RNG draw, optimizer operation or tensor edit."""
import hashlib
import pickle


def array_fingerprint(value):
    import numpy as np
    if hasattr(value,'detach'):value=value.detach().cpu().numpy()
    a=np.ascontiguousarray(value)
    digest=hashlib.sha256(str(a.dtype).encode()+np.asarray(a.shape,dtype=np.int64).tobytes())
    digest.update(a.view(np.uint8))
    return {'shape':list(a.shape),'dtype':str(a.dtype),'sha256':digest.hexdigest()}


def model_fingerprints(model):
    return {name:array_fingerprint(value) for name,value in model.state_dict().items()}


def rng_fingerprints():
    import random
    import numpy as np
    import torch
    return {'python':hashlib.sha256(pickle.dumps(random.getstate())).hexdigest(),
        'numpy':hashlib.sha256(pickle.dumps(np.random.get_state())).hexdigest(),
        'torch_cpu':array_fingerprint(torch.get_rng_state()),
        'torch_cuda':[array_fingerprint(state) for state in torch.cuda.get_rng_state_all()]}
