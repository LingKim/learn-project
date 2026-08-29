import asyncio

import boto3  # type: ignore[import-untyped]
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import ClientError
from sqlalchemy import text

from xuemian_ai.core.config import get_settings
from xuemian_ai.infrastructure.database import create_database_engine


def cleanup_bucket(client: BaseClient, bucket: str) -> None:
    if not bucket.startswith("xuemian-e2e-"):
        raise RuntimeError("refusing to clean a non-E2E bucket")
    try:
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket):
            objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
            if objects:
                client.delete_objects(Bucket=bucket, Delete={"Objects": objects, "Quiet": True})
        uploads = client.list_multipart_uploads(Bucket=bucket).get("Uploads", [])
        for upload in uploads:
            client.abort_multipart_upload(
                Bucket=bucket,
                Key=upload["Key"],
                UploadId=upload["UploadId"],
            )
        client.delete_bucket(Bucket=bucket)
    except ClientError as exc:
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if status != 404:
            raise


async def cleanup() -> None:
    settings = get_settings()
    if settings.environment != "test" or ":e2e:" not in settings.auth_redis_key_prefix:
        raise RuntimeError("refusing to clean outside the isolated E2E environment")

    engine = create_database_engine(settings.database_url.get_secret_value())
    try:
        async with engine.begin() as connection:
            database_name = await connection.scalar(text("SELECT current_database()"))
            if not isinstance(database_name, str) or not database_name.endswith("_e2e"):
                raise RuntimeError("refusing to clean a non-E2E database")
            await connection.execute(
                text(
                    "TRUNCATE TABLE file_deletion_tombstones, file_orphan_candidates, "
                    "file_cleanup_tasks, file_audit_events, knowledge_base_files, file_assets, "
                    "stored_objects, file_upload_sessions, file_policy_versions CASCADE"
                )
            )

        credentials = {
            "aws_access_key_id": settings.rustfs_access_key.get_secret_value(),
            "aws_secret_access_key": settings.rustfs_secret_key.get_secret_value(),
            "region_name": settings.rustfs_region,
            "config": Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        }
        client = boto3.client(
            "s3",
            endpoint_url=str(settings.rustfs_internal_endpoint).rstrip("/"),
            **credentials,
        )
        for bucket in settings.rustfs_buckets:
            await asyncio.to_thread(cleanup_bucket, client, bucket)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(cleanup())
