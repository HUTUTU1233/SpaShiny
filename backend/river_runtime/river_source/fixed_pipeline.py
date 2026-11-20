"""Complete standalone candidate: real H5AD -> original SLAT -> River -> original Captum/Borda.

NOT deployed. The checkpoint-replay experiments are separate from this fresh-SLAT entry.
Requires --mode explicitly; General/corrected source remains a separate unchanged copy.
"""
import argparse
import hashlib
import importlib.metadata as md
import inspect
import json
import os
from pathlib import Path
import sys

from execution_modes import load_core, mode_contract


def file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b""):
            digest.update(block)
    return digest.hexdigest()


def array_hash(value):
    import numpy as np
    a = np.ascontiguousarray(value)
    h = hashlib.sha256(str(a.dtype).encode() + np.asarray(a.shape, dtype=np.int64).tobytes())
    h.update(a.view(np.uint8))
    return {"shape": list(a.shape), "dtype": str(a.dtype), "sha256": h.hexdigest()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=("original_python_parity", "corrected_training"))
    parser.add_argument("--manifest", required=True, help="JSON samples map; V39,V28,V38,V44,V27 paths and declared raw_counts")
    parser.add_argument("--output", required=True, help="New independent directory, never an existing historical result")
    args = parser.parse_args()
    mode, contract = mode_contract(args.mode)
    if mode == "original_python_parity":
        assert sys.version_info[:3] == (3, 8, 20)
        for name, required in {"numpy": "1.24.4", "scipy": "1.10.1", "pandas": "1.5.3", "scanpy": "1.9.8",
                               "anndata": "0.9.2", "torch": "2.3.1+cu121", "captum": "0.7.0", "scSLAT": "0.3.0"}.items():
            assert md.version(name) == required, (name, md.version(name), required)
    manifest = json.loads(Path(args.manifest).read_text())
    assert manifest["input_scale"] == "raw_counts", "No silent second normalization of declared processed data"
    order = ["V39", "V28", "V38", "V44", "V27"]
    assert set(manifest["samples"]) == set(order)
    out = Path(args.output).resolve()
    assert not out.exists(), "No overwrite of existing results"
    os.umask(0o077)
    out.mkdir(parents=True, mode=0o700)
    os.chdir(out)
    sys.dont_write_bytecode = True
    for key, folder in (("MPLCONFIGDIR", "matplotlib"), ("NUMBA_CACHE_DIR", "numba"), ("XDG_CACHE_HOME", "xdg"),
                        ("TORCH_HOME", "torch"), ("TORCH_EXTENSIONS_DIR", "extensions"), ("CUDA_CACHE_PATH", "cuda"), ("TMPDIR", "tmp")):
        path = out / "cache" / folder
        path.mkdir(parents=True)
        os.environ[key] = str(path)

    def audit(event, values):
        if event in ("sqlite3.connect", "socket.connect"):
            raise RuntimeError("Standalone candidate cannot access a database or network")
        if event == "open":
            path, how, flags = values
            writing = isinstance(how, str) and any(c in how for c in "wax+") or isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)
            if writing and not isinstance(path, int) and path != "/dev/null":
                resolved = Path(os.fsdecode(path)).resolve()
                assert resolved == out or out in resolved.parents, "Write outside candidate output refused"
    sys.addaudithook(audit)
    import numpy as np
    import scanpy as sc
    import torch
    from scipy import sparse
    River, contract, sources = load_core(mode, Path(__file__).resolve().parent)
    from river.preprocess import do_slat_pair, get_the_feature, seed_everything
    assert torch.cuda.is_available(), "Historical River core requires CUDA; no CPU fallback"
    trace = {"analysis_mode": mode, "method_version": contract["scientific_method_version"], "core_sources": sources,
             "sample_order": order, "groups": ["Sham", "D1", "D3", "D7", "D28"],
             "target_meaning": "H5AD sample IDs 0..4, not disease-group or time-regression target",
             "seed": 42, "epochs": 100, "n_obs": 1052, "random_state": 0,
             "sampling_algorithm": "scanpy.pp.subsample", "runner_extra_pca_call_count": 0,
             "annotation_required": False, "input_files": [], "SLAT_pairs": [], "status": "RUNNING"}
    seed_everything(42)
    adatas = []
    for sample in order:
        path = Path(manifest["samples"][sample]).resolve()
        a = sc.read_h5ad(path)
        assert a.n_obs >= 1052 and a.var_names.is_unique
        assert "spatial" in a.obsm
        p = np.asarray(a.obsm["spatial"])
        assert p.shape == (a.n_obs, 2) and np.isfinite(p).all()
        values = a.X.data if sparse.issparse(a.X) else np.asarray(a.X)
        assert np.isfinite(values).all() and not (values < 0).any()
        n_before = a.n_obs
        a = sc.pp.subsample(a, n_obs=1052, random_state=0, copy=True)
        sc.pp.normalize_total(a)
        sc.pp.log1p(a)
        a.obsm["spatial"] = np.asarray(a.obsm["spatial"], dtype=float)
        if not sparse.issparse(a.X):
            a.X = sparse.csr_matrix(a.X)
        trace["input_files"].append({"sample": sample, "path": str(path), "sha256": file_sha(path), "spots_before": n_before,
                                     "spots_after": a.n_obs, "spot_order_sha256": hashlib.sha256(b"".join(str(v).encode() + b"\0" for v in a.obs_names)).hexdigest()})
        adatas.append(a)
    # Preserve original two-layer preprocessing and original SLAT defaults.
    seed_everything(42)
    matches = []
    for index, a in enumerate(adatas[1:], 1):
        _, best = do_slat_pair(adatas[0], a, feature="pca")
        match = np.asarray(best[0])
        matches.append(match)
        np.save(out / ("matching_" + str(index) + ".npy"), match, allow_pickle=False)
        trace["SLAT_pairs"].append({"reference": order[0], "query": order[index], "matching": array_hash(match)})
    x, p, y, overlap = get_the_feature(adatas, matches)
    trace["model_inputs"] = {key: array_hash(value) for key, value in (("gene_expression", x), ("spatial", p), ("y", y))}
    trace["overlap_gene_count"] = len(overlap)
    trace["overlap_order_sha256"] = hashlib.sha256(b"".join(str(g).encode() + b"\0" for g in overlap)).hexdigest()
    (out / "river_execution_trace.json").write_text(json.dumps(trace, indent=2))
    model = River(gene_expression=x, spatial=p, label=y, device="cuda:0")
    torch.save(model.model.state_dict(), out / "initial_model.pt")
    model.train(epoch=100)
    torch.save(model.model.state_dict(), out / "final_model.pt")
    returned = model.attribution()
    for name, values in zip(("ig", "dl", "sl"), returned):
        torch.save(values, out / (name + "_abs_attribution.pt"))
    model.summary_attribution(*returned, overlap)
    model.final_rank.to_csv(out / "rank_borda_full.csv", index_label="gene", header=["borda_score"])
    for name, normalized in (("ig", model.scores_ig), ("dl", model.scores_dl), ("sl", model.scores_sl)):
        np.save(out / (name + "_normalized.npy"), normalized.cpu().numpy(), allow_pickle=False)
        np.save(out / (name + "_gene_total_scores.npy"), normalized.sum(0).cpu().numpy(), allow_pickle=False)
    trace.update(status="TECHNICALLY_COMPLETED", Top200=list(map(str, model.return_top_k_gene(200))),
                 attributed_spots=5248, retained_original_drop_last=True,
                 scientific_validity_note="Original attribution and ranking behavior preserved, including historical limitations; technical success is not proof of biological validity")
    (out / "river_execution_trace.json").write_text(json.dumps(trace, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
