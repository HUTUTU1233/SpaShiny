from __future__ import annotations

from .common import CPUWorkflowContext, CPUWorkflowError, ensure_dependency, save_figure_bundle, select_asset, write_csv, write_json


def _write_umap_plot(ctx: CPUWorkflowContext, adata, *, cluster_key: str) -> list[str]:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import scanpy as sc
    except Exception:
        return []

    if "X_umap" not in adata.obsm:
        return []
    fig, ax = plt.subplots(figsize=(7, 6))
    try:
        sc.pl.umap(adata, color=[cluster_key], ax=ax, show=False)
    except Exception:
        xy = adata.obsm["X_umap"]
        ax.scatter(xy[:, 0], xy[:, 1], s=8, alpha=0.8)
        ax.set_title(f"UMAP colored by {cluster_key}")
        ax.set_xlabel("UMAP1")
        ax.set_ylabel("UMAP2")
    fig.tight_layout()
    path, pdf_path = save_figure_bundle(fig, ctx.figures_dir / "clustering_umap.png", dpi=150)
    plt.close(fig)
    return [path.relative_to(ctx.workspace).as_posix(), pdf_path.relative_to(ctx.workspace).as_posix()]


def run(ctx: CPUWorkflowContext) -> dict:
    ensure_dependency("scanpy")
    ensure_dependency("numpy")
    import numpy as np
    import scanpy as sc

    input_path = select_asset(
        ctx,
        suffixes=(".h5ad",),
        roles=("joint_downstream_reference_h5ad", "processed_h5ad", "joint_raw", "primary"),
        label="clustering h5ad",
    )
    if input_path is None:
        raise CPUWorkflowError("INPUT_REQUIRED", "Clustering requires a processed h5ad input.")

    adata = sc.read_h5ad(str(input_path))
    use_rep = str(ctx.parameters.get("use_rep") or "X_emb")
    if use_rep not in adata.obsm:
        if "X_pca" in adata.obsm:
            use_rep = "X_pca"
        else:
            raise CPUWorkflowError("INPUT_CONTRACT_INVALID", f"Input h5ad is missing obsm['{use_rep}'].")

    n_neighbors = int(ctx.parameters.get("clustering_neighbors") or ctx.parameters.get("n_neighbors") or 15)
    resolution = float(ctx.parameters.get("clustering_resolution") or ctx.parameters.get("resolution") or 1.0)
    umap_min_dist = float(ctx.parameters.get("umap_min_dist") or 1.0)
    umap_spread = float(ctx.parameters.get("umap_spread") or 1.0)
    latent_dim = int(ctx.parameters.get("latent_dim") or ctx.parameters.get("vae_n_latent") or 10)
    cluster_key = str(ctx.parameters.get("cluster_key") or f"VAE_clusters_latent{latent_dim}")

    if n_neighbors <= 0:
        raise CPUWorkflowError("PARAMETER_INVALID", "n_neighbors must be positive.")
    if resolution <= 0:
        raise CPUWorkflowError("PARAMETER_INVALID", "resolution must be positive.")

    adata.obsm[use_rep] = np.asarray(adata.obsm[use_rep], dtype=np.float32)
    sc.pp.neighbors(adata, use_rep=use_rep, n_neighbors=n_neighbors)
    sc.tl.umap(adata, min_dist=umap_min_dist, spread=umap_spread)
    sc.tl.leiden(adata, resolution=resolution, key_added=cluster_key)
    adata.obs["VAE_clusters"] = adata.obs[cluster_key].astype(str)
    adata.write_h5ad(ctx.workspace / "clustered_result.h5ad")

    cluster_counts = adata.obs[cluster_key].astype(str).value_counts().sort_index()
    rows = [{"cluster": str(cluster), "count": int(count)} for cluster, count in cluster_counts.items()]
    write_csv(ctx.workspace / "cluster_counts.csv", rows, fieldnames=["cluster", "count"])
    write_csv(
        ctx.workspace / "observation_clusters.csv",
        [{"observation_id": str(idx), "cluster": str(value)} for idx, value in adata.obs[cluster_key].astype(str).items()],
        fieldnames=["observation_id", "cluster"],
    )
    figures = _write_umap_plot(ctx, adata, cluster_key=cluster_key)
    metrics = {
        "input_file": input_path.name,
        "input_shape": [int(adata.n_obs), int(adata.n_vars)],
        "use_rep": use_rep,
        "n_neighbors": int(n_neighbors),
        "resolution": float(resolution),
        "umap_min_dist": float(umap_min_dist),
        "umap_spread": float(umap_spread),
        "cluster_key": cluster_key,
        "clusters": int(len(cluster_counts)),
    }
    write_json(ctx.workspace / "clustering_summary.json", {"status": "succeeded", **metrics, "cluster_counts": rows})
    return {
        "metrics": metrics,
        "outputs": [
            "clustering_summary.json",
            "cluster_counts.csv",
            "observation_clusters.csv",
            "clustered_result.h5ad",
            *figures,
        ],
    }
