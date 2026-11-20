"""Explicit isolated entry points; never replace the production General interpreter.

Historical compatibility is an experiment contract, not a recommended training method.
The archived River/model/preprocess files are loaded unchanged in separate processes.
"""
import hashlib
import importlib
from pathlib import Path
import sys

CONTRACTS = {
    "original_python_parity": {
        "river_sha256": "047563e08b276fa3e43fae09a0c9847a9586c854ee6c9c279d306ff647e77a9c",
        "eval_shuffle": True, "restore_training_after_evaluation": False,
        "scientific_method_version": "river-102843-historical-behavior-v1",
        "intended_runtime": "river-original-python-strict",
    },
    "corrected_training": {
        "river_sha256": "66c3da2b21160f350b1be27a3786eef49f2c7fff8b2638f7e017555e1c01349d",
        "eval_shuffle": False, "restore_training_after_evaluation": True,
        "scientific_method_version": "existing-production-training-unchanged",
        "intended_runtime": "existing-general-environment-unchanged",
    },
}
SHARED_HASHES = {
    "model.py": "3364f2574d19513b185d97ac7cbcbac6e871d2af8b433bdddfa735a6bf06ca41",
    "preprocess.py": "47b4096de69ac62b0f0d7ab30568b488945d217f3999bc51855216e540942662",
}


def mode_contract(mode):
    if mode == "general":
        mode = "corrected_training"
    if mode not in CONTRACTS:
        raise ValueError("An explicit supported execution mode is required; no fallback is permitted")
    return mode, dict(CONTRACTS[mode])


def load_core(mode, candidate_root):
    mode, contract = mode_contract(mode)
    folder = Path(candidate_root).resolve() / mode
    expected = dict(SHARED_HASHES, **{"river.py": contract["river_sha256"]})
    manifest = {}
    for filename, digest in expected.items():
        path = folder / "river" / filename
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != digest:
            raise RuntimeError("Archived algorithm source changed: " + filename)
        manifest[filename] = {"path": str(path), "sha256": actual}
    if any(name == "river" or name.startswith("river.") for name in sys.modules):
        raise RuntimeError("Modes must run in separate processes; a River module is already imported")
    sys.path.insert(0, str(folder))
    cls = importlib.import_module("river.river").River
    if Path(sys.modules[cls.__module__].__file__).resolve() != folder / "river/river.py":
        raise RuntimeError("Unexpected River import")
    return cls, contract, manifest
