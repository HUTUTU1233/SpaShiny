from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

from .security import sha256_file
from .sftp_manager import SFTPManager


class ResultSyncError(RuntimeError):
    """Raised when a result manifest cannot be downloaded or verified."""


class ResultSynchronizer:
    def __init__(self, sftp: SFTPManager) -> None:
        self.sftp = sftp

    def sync_from_manifest(self, remote_workspace: str, local_workspace: Path) -> dict[str, Any]:
        local_workspace = Path(local_workspace)
        local_workspace.mkdir(parents=True, exist_ok=True)
        manifest_local = local_workspace / "result_manifest.json"
        self.sftp.download_file(f"{remote_workspace}/result_manifest.json", manifest_local)
        manifest = json.loads(manifest_local.read_text(encoding="utf-8"))
        files = manifest.get("files") or []
        if not isinstance(files, list):
            raise ResultSyncError("result_manifest.json has invalid files list.")

        downloaded = []
        for entry in files:
            rel = str(entry.get("relative_path") or "").replace("\\", "/")
            expected_sha = str(entry.get("sha256") or "")
            if not rel or rel.startswith("../") or "/../" in rel:
                raise ResultSyncError(f"Unsafe manifest path: {rel}")
            remote_file = f"{remote_workspace.rstrip('/')}/{rel}"
            local_file = local_workspace / rel
            self.sftp.download_file(remote_file, local_file)
            actual_sha = sha256_file(local_file)
            if expected_sha and actual_sha != expected_sha:
                raise ResultSyncError(f"SHA256 mismatch for {rel}")
            downloaded.append({"relative_path": rel, "local_path": str(local_file), "sha256": actual_sha})
        (local_workspace / "manifest.json").write_text(
            json.dumps({"files": downloaded}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {"manifest": manifest, "downloaded": downloaded}


def package_results_zip(local_workspace: Path) -> Path:
    local_workspace = Path(local_workspace)
    zip_path = local_workspace / "results.zip"
    tmp_path = zip_path.with_suffix(".zip.tmp")
    allowed_roots = ("output", "figures", "logs")
    top_level = (
        "integrated_result.h5ad",
        "model_state.pt",
        "latent.npy",
        "loss_record.json",
        "cluster_statistics.csv",
        "summary.json",
        "manifest.json",
        "result_manifest.json",
        "session_info.txt",
    )
    with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        for root_name in allowed_roots:
            root = local_workspace / root_name
            if not root.exists():
                continue
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(local_workspace).as_posix())
        for name in top_level:
            path = local_workspace / name
            if path.exists() and path.is_file():
                archive.write(path, path.name)
    tmp_path.replace(zip_path)
    return zip_path


def result_artifact_size_bytes(local_workspace: Path) -> int:
    local_workspace = Path(local_workspace)
    paths: set[Path] = set()
    manifest_path = local_workspace / "result_manifest.json"
    if manifest_path.exists():
        paths.add(manifest_path)
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for entry in manifest.get("files") or []:
                rel = str(entry.get("relative_path") or "").replace("\\", "/")
                if rel and not rel.startswith("../") and "/../" not in rel:
                    paths.add(local_workspace / rel)
        except Exception:
            pass
    for rel in REQUIRED_CONDITIONAL_VAE_OUTPUTS:
        paths.add(local_workspace / rel)
    paths.add(local_workspace / "results.zip")
    total = 0
    for path in paths:
        try:
            if path.is_file():
                total += max(0, int(path.stat().st_size))
        except Exception:
            continue
    return total


def delete_result_artifacts(local_workspace: Path) -> None:
    local_workspace = Path(local_workspace)
    for name in ("output", "figures", "logs"):
        shutil.rmtree(local_workspace / name, ignore_errors=True)
    for rel in REQUIRED_CONDITIONAL_VAE_OUTPUTS | {"result_manifest.json", "results.zip"}:
        path = local_workspace / rel
        try:
            if path.is_file():
                path.unlink()
        except Exception:
            continue


REQUIRED_CONDITIONAL_VAE_OUTPUTS = {
    "integrated_result.h5ad",
    "model_state.pt",
    "latent.npy",
    "loss_record.json",
    "cluster_statistics.csv",
    "summary.json",
    "manifest.json",
    "session_info.txt",
    "figures/umap.pdf",
    "figures/spatial_cluster.pdf",
    "figures/modality_contribution.pdf",
    "figures/reconstruction_diagnostics.pdf",
    "logs/run.log",
    "logs/error.log",
}


def verify_conditional_vae_outputs(local_workspace: Path) -> dict[str, Any]:
    local_workspace = Path(local_workspace)
    missing = []
    for rel in sorted(REQUIRED_CONDITIONAL_VAE_OUTPUTS):
        if not (local_workspace / rel).exists():
            missing.append(rel)

    manifest_path = local_workspace / "result_manifest.json"
    if not manifest_path.exists():
        missing.append("result_manifest.json")

    errors = []
    manifest = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for entry in manifest.get("files") or []:
            rel = str(entry.get("relative_path") or "")
            expected = str(entry.get("sha256") or "")
            path = local_workspace / rel
            if not path.exists():
                errors.append(f"Manifest file missing: {rel}")
                continue
            actual = sha256_file(path)
            if expected and actual != expected:
                errors.append(f"SHA256 mismatch: {rel}")

    h5ad_ok = False
    h5ad_error = ""
    h5ad_path = local_workspace / "integrated_result.h5ad"
    if h5ad_path.exists():
        try:
            import scanpy as sc

            adata = sc.read_h5ad(h5ad_path)
            missing_fields = []
            if "X_latent" not in adata.obsm:
                missing_fields.append("obsm['X_latent']")
            if "X_umap" not in adata.obsm:
                missing_fields.append("obsm['X_umap']")
            if "leiden" not in adata.obs:
                missing_fields.append("obs['leiden']")
            if missing_fields:
                h5ad_error = "Missing " + ", ".join(missing_fields)
            else:
                h5ad_ok = True
        except Exception as exc:
            h5ad_error = str(exc)

    if h5ad_path.exists() and not h5ad_ok:
        errors.append(f"integrated_result.h5ad verification failed: {h5ad_error}")

    zip_ok = True
    zip_error = ""
    zip_path = local_workspace / "results.zip"
    if zip_path.exists():
        try:
            with zipfile.ZipFile(zip_path, "r") as archive:
                bad_member = archive.testzip()
                if bad_member:
                    zip_ok = False
                    zip_error = f"Corrupt ZIP member: {bad_member}"
        except Exception as exc:
            zip_ok = False
            zip_error = str(exc)
        if not zip_ok:
            errors.append(f"results.zip verification failed: {zip_error}")

    ok = not missing and not errors and h5ad_ok and zip_ok
    return {
        "ok": ok,
        "missing": missing,
        "errors": errors,
        "h5ad_ok": h5ad_ok,
        "zip_ok": zip_ok,
        "manifest_files": len(manifest.get("files") or []) if manifest else 0,
    }
