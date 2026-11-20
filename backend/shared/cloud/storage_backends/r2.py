from __future__ import annotations

from .base import ObjectHead, StorageBackendError
from ..config import SpaShinyCloudConfig
from ..r2_client import create_r2_client


class R2Storage:
    """Cloudflare R2 storage using boto3's S3-compatible API."""

    def __init__(self, config: SpaShinyCloudConfig) -> None:
        bucket = config.require_r2_runtime_config()
        try:
            self.client = create_r2_client(config)
        except Exception as exc:  # pragma: no cover - exercised only in R2 deployments
            raise StorageBackendError("boto3 and botocore are required when STORAGE_BACKEND=r2.") from exc
        self.config = config
        self.bucket = bucket

    def create_multipart_upload(
        self,
        *,
        object_key: str,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> str:
        response = self.client.create_multipart_upload(
            Bucket=self.bucket,
            Key=object_key,
            ContentType=content_type or "application/octet-stream",
            Metadata=metadata or {},
        )
        upload_id = response.get("UploadId")
        if not upload_id:
            raise StorageBackendError("R2 did not return a multipart upload id.")
        return str(upload_id)

    def create_presigned_part_url(
        self,
        *,
        object_key: str,
        multipart_upload_id: str,
        part_number: int,
        expires_seconds: int,
    ) -> str:
        return self.client.generate_presigned_url(
            "upload_part",
            Params={
                "Bucket": self.bucket,
                "Key": object_key,
                "UploadId": multipart_upload_id,
                "PartNumber": int(part_number),
            },
            ExpiresIn=int(expires_seconds),
        )

    def complete_multipart_upload(
        self,
        *,
        object_key: str,
        multipart_upload_id: str,
        parts: list[dict[str, object]],
    ) -> ObjectHead:
        self.client.complete_multipart_upload(
            Bucket=self.bucket,
            Key=object_key,
            UploadId=multipart_upload_id,
            MultipartUpload={
                "Parts": [
                    {"PartNumber": int(part["part_number"]), "ETag": str(part["etag"])}
                    for part in sorted(parts, key=lambda item: int(item["part_number"]))
                ]
            },
        )
        return self.head_object(object_key)

    def abort_multipart_upload(self, *, object_key: str, multipart_upload_id: str) -> None:
        try:
            self.client.abort_multipart_upload(Bucket=self.bucket, Key=object_key, UploadId=multipart_upload_id)
        except Exception:
            # Aborting an already-completed or already-aborted upload is treated as idempotent.
            return None

    def head_object(self, object_key: str) -> ObjectHead:
        response = self.client.head_object(Bucket=self.bucket, Key=object_key)
        metadata = {str(k): str(v) for k, v in (response.get("Metadata") or {}).items()}
        return ObjectHead(
            object_key=object_key,
            size_bytes=int(response.get("ContentLength") or 0),
            etag=str(response.get("ETag") or "").strip('"'),
            sha256=metadata.get("sha256"),
            metadata=metadata,
        )

    def create_presigned_download_url(
        self,
        *,
        object_key: str,
        expires_seconds: int,
        filename: str | None = None,
    ) -> str:
        params = {"Bucket": self.bucket, "Key": object_key}
        if filename:
            params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'
        return self.client.generate_presigned_url("get_object", Params=params, ExpiresIn=int(expires_seconds))

    def create_presigned_put_url(
        self,
        *,
        object_key: str,
        expires_seconds: int,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> str:
        params = {
            "Bucket": self.bucket,
            "Key": object_key,
            "ContentType": content_type or "application/octet-stream",
        }
        if metadata:
            params["Metadata"] = {str(key): str(value) for key, value in metadata.items()}
        return self.client.generate_presigned_url("put_object", Params=params, ExpiresIn=int(expires_seconds))

    def delete_object(self, object_key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=object_key)

    def delete_prefix(self, prefix: str) -> None:
        for object_key in self.list_prefix(prefix):
            try:
                self.delete_object(object_key)
            except Exception:
                continue

    def list_prefix(self, prefix: str) -> list[str]:
        keys: list[str] = []
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for item in page.get("Contents", []) or []:
                key = item.get("Key")
                if key:
                    keys.append(str(key))
        return keys

    def managed_usage_bytes(self, buckets: tuple[str, ...] = ()) -> int:
        bucket_names = tuple(item for item in buckets if str(item).strip()) or (self.bucket,)
        total = 0
        paginator = self.client.get_paginator("list_objects_v2")
        for bucket in bucket_names:
            for page in paginator.paginate(Bucket=str(bucket)):
                for item in page.get("Contents", []) or []:
                    total += max(0, int(item.get("Size") or 0))
        return total

    def object_exists(self, object_key: str) -> bool:
        try:
            self.head_object(object_key)
            return True
        except Exception:
            return False
