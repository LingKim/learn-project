import asyncio
import hashlib
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import quote

import boto3  # type: ignore[import-untyped]
from botocore.client import BaseClient  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from xuemian_ai.core.config import Settings


@dataclass(frozen=True, slots=True)
class StoredPayload:
    content: bytes
    sha256: str
    byte_size: int


class ObjectStorage:
    def __init__(self, settings: Settings) -> None:
        credentials = {
            "aws_access_key_id": settings.rustfs_access_key.get_secret_value(),
            "aws_secret_access_key": settings.rustfs_secret_key.get_secret_value(),
            "region_name": settings.rustfs_region,
            "config": Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        }
        self._internal: BaseClient = boto3.client(
            "s3", endpoint_url=str(settings.rustfs_internal_endpoint).rstrip("/"), **credentials
        )
        self._public: BaseClient = boto3.client(
            "s3", endpoint_url=str(settings.rustfs_public_endpoint).rstrip("/"), **credentials
        )
        self._upload_seconds = settings.file_upload_url_seconds
        self._download_seconds = settings.file_download_url_seconds

    async def create_bucket(self, bucket: str) -> None:
        try:
            await asyncio.to_thread(self._internal.head_bucket, Bucket=bucket)
        except ClientError as exc:
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status not in {403, 404}:
                raise
            await asyncio.to_thread(self._internal.create_bucket, Bucket=bucket)

    async def configure_bucket(
        self, bucket: str, allowed_origins: list[str], allowed_methods: list[str]
    ) -> None:
        cors = {
            "CORSRules": [
                {
                    "AllowedHeaders": ["*"],
                    "AllowedMethods": allowed_methods,
                    "AllowedOrigins": allowed_origins,
                    "ExposeHeaders": ["ETag", "x-amz-request-id"],
                    "MaxAgeSeconds": 900,
                }
            ]
        }
        await asyncio.to_thread(
            self._internal.put_bucket_cors, Bucket=bucket, CORSConfiguration=cors
        )

    async def configure_temporary_lifecycle(self, bucket: str, retention_days: int) -> None:
        lifecycle = {
            "Rules": [
                {
                    "ID": "expire-temporary-files",
                    "Status": "Enabled",
                    "Filter": {"Prefix": ""},
                    "Expiration": {"Days": retention_days},
                    "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": retention_days},
                }
            ]
        }
        await asyncio.to_thread(
            self._internal.put_bucket_lifecycle_configuration,
            Bucket=bucket,
            LifecycleConfiguration=lifecycle,
        )

    async def check_buckets(self, buckets: tuple[str, ...]) -> None:
        for bucket in buckets:
            await asyncio.to_thread(self._internal.head_bucket, Bucket=bucket)

    async def presign_put(self, bucket: str, key: str, content_type: str | None) -> str:
        params: dict[str, Any] = {"Bucket": bucket, "Key": key}
        if content_type:
            params["ContentType"] = content_type
        return await asyncio.to_thread(
            self._public.generate_presigned_url,
            "put_object",
            Params=params,
            ExpiresIn=self._upload_seconds,
        )

    async def create_multipart(self, bucket: str, key: str, content_type: str | None) -> str:
        params: dict[str, Any] = {"Bucket": bucket, "Key": key}
        if content_type:
            params["ContentType"] = content_type
        response = await asyncio.to_thread(self._internal.create_multipart_upload, **params)
        return cast(str, response["UploadId"])

    async def presign_part(self, bucket: str, key: str, upload_id: str, part_number: int) -> str:
        return await asyncio.to_thread(
            self._public.generate_presigned_url,
            "upload_part",
            Params={
                "Bucket": bucket,
                "Key": key,
                "UploadId": upload_id,
                "PartNumber": part_number,
            },
            ExpiresIn=self._upload_seconds,
        )

    async def complete_multipart(
        self,
        bucket: str,
        key: str,
        upload_id: str,
        parts: list[dict[str, int | str]],
    ) -> None:
        await asyncio.to_thread(
            self._internal.complete_multipart_upload,
            Bucket=bucket,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
        )

    async def abort_multipart(self, bucket: str, key: str, upload_id: str) -> None:
        try:
            await asyncio.to_thread(
                self._internal.abort_multipart_upload,
                Bucket=bucket,
                Key=key,
                UploadId=upload_id,
            )
        except ClientError as exc:
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status != 404:
                raise

    async def read_and_hash(self, bucket: str, key: str, max_bytes: int) -> StoredPayload:
        return await asyncio.to_thread(self._read_and_hash_sync, bucket, key, max_bytes)

    def _read_and_hash_sync(self, bucket: str, key: str, max_bytes: int) -> StoredPayload:
        response = self._internal.get_object(Bucket=bucket, Key=key)
        body = response["Body"]
        digest = hashlib.sha256()
        chunks: list[bytes] = []
        total = 0
        try:
            while chunk := body.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError("FILE_TOO_LARGE")
                digest.update(chunk)
                chunks.append(chunk)
        finally:
            body.close()
        return StoredPayload(content=b"".join(chunks), sha256=digest.hexdigest(), byte_size=total)

    async def copy_object(
        self, source_bucket: str, source_key: str, target_bucket: str, target_key: str
    ) -> None:
        await asyncio.to_thread(
            self._internal.copy_object,
            Bucket=target_bucket,
            Key=target_key,
            CopySource={"Bucket": source_bucket, "Key": source_key},
        )

    async def delete_object(self, bucket: str, key: str) -> None:
        await asyncio.to_thread(self._internal.delete_object, Bucket=bucket, Key=key)

    async def object_exists(self, bucket: str, key: str) -> bool:
        try:
            await asyncio.to_thread(self._internal.head_object, Bucket=bucket, Key=key)
            return True
        except ClientError as exc:
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status == 404:
                return False
            raise

    async def presign_download(self, bucket: str, key: str, filename: str) -> str:
        disposition = f"attachment; filename*=UTF-8''{quote(filename)}"
        return await asyncio.to_thread(
            self._public.generate_presigned_url,
            "get_object",
            Params={
                "Bucket": bucket,
                "Key": key,
                "ResponseContentDisposition": disposition,
            },
            ExpiresIn=self._download_seconds,
        )

    async def list_objects(
        self, bucket: str, continuation_token: str | None = None, max_keys: int = 1000
    ) -> tuple[list[str], str | None]:
        params: dict[str, Any] = {"Bucket": bucket, "MaxKeys": max_keys}
        if continuation_token:
            params["ContinuationToken"] = continuation_token
        response = await asyncio.to_thread(self._internal.list_objects_v2, **params)
        keys = [item["Key"] for item in response.get("Contents", [])]
        return keys, response.get("NextContinuationToken")
