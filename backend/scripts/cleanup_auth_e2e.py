import asyncio

from redis.asyncio import Redis
from sqlalchemy import text

from xuemian_ai.core.config import get_settings
from xuemian_ai.infrastructure.database import create_database_engine


async def cleanup() -> None:
    settings = get_settings()
    if settings.environment != "test" or ":e2e:" not in settings.auth_redis_key_prefix:
        raise RuntimeError("refusing to clean outside the isolated E2E environment")

    engine = create_database_engine(settings.database_url.get_secret_value())
    redis = Redis.from_url(settings.redis_url.get_secret_value(), decode_responses=True)
    try:
        async with engine.begin() as connection:
            database_name = await connection.scalar(text("SELECT current_database()"))
            if not isinstance(database_name, str) or not database_name.endswith("_e2e"):
                raise RuntimeError("refusing to clean a non-E2E database")
            await connection.execute(
                text(
                    "TRUNCATE TABLE auth_audit_events, auth_sessions, "
                    "knowledge_bases, users CASCADE"
                )
            )

        keys = [key async for key in redis.scan_iter(match=f"{settings.auth_redis_key_prefix}:*")]
        if keys:
            await redis.delete(*keys)
    finally:
        await redis.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(cleanup())
