from __future__ import annotations

from .config import SpaShinyCloudConfig


def create_r2_client(config: SpaShinyCloudConfig, *, connect_timeout: int = 10, read_timeout: int = 30):
    try:
        import boto3
        from botocore.config import Config
    except Exception as exc:  # pragma: no cover - exercised only when R2 dependencies are absent
        raise RuntimeError("boto3 and botocore are required for R2 operations.") from exc
    return boto3.client(
        "s3",
        endpoint_url=config.r2_endpoint_url,
        aws_access_key_id=config.r2_access_key_id,
        aws_secret_access_key=config.r2_secret_access_key,
        region_name="auto",
        config=Config(
            signature_version="s3v4",
            connect_timeout=int(connect_timeout),
            read_timeout=int(read_timeout),
            retries={"max_attempts": 2, "mode": "standard"},
        ),
    )
