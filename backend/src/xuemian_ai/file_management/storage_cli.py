import asyncio

from xuemian_ai.core.config import get_settings
from xuemian_ai.core.logging import configure_logging, get_logger
from xuemian_ai.file_management.storage import ObjectStorage

_logger = get_logger(__name__)


async def initialize_storage() -> None:
    settings = get_settings()
    configure_logging(settings)
    storage = ObjectStorage(settings)
    for bucket in settings.rustfs_buckets:
        await storage.create_bucket(bucket)
        allowed_methods = (
            ["PUT", "HEAD"] if bucket == settings.rustfs_quarantine_bucket else ["GET", "HEAD"]
        )
        await storage.configure_bucket(bucket, settings.allowed_origins, allowed_methods)
        if bucket in {
            settings.rustfs_quarantine_bucket,
            settings.rustfs_temporary_bucket,
        }:
            await storage.configure_temporary_lifecycle(
                bucket, settings.file_temporary_retention_days
            )
    _logger.info("storage_initialized", bucket_count=len(settings.rustfs_buckets))


def run() -> None:
    asyncio.run(initialize_storage())
