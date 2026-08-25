from dataclasses import dataclass

import httpx
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from xuemian_ai.core.config import Settings
from xuemian_ai.infrastructure.database import create_database_engine, create_session_factory


@dataclass(slots=True)
class Infrastructure:
    database: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    redis: Redis
    http: httpx.AsyncClient

    @classmethod
    def create(cls, settings: Settings) -> "Infrastructure":
        database = create_database_engine(settings.database_url.get_secret_value())
        return cls(
            database=database,
            sessions=create_session_factory(database),
            redis=Redis.from_url(settings.redis_url.get_secret_value(), decode_responses=True),
            http=httpx.AsyncClient(
                timeout=settings.dependency_timeout_seconds,
                trust_env=False,
            ),
        )

    async def close(self) -> None:
        await self.http.aclose()
        await self.redis.aclose()
        await self.database.dispose()

    async def check_database(self) -> None:
        async with self.database.connect() as connection:
            await connection.execute(text("SELECT 1"))

    async def check_redis(self) -> None:
        await self.redis.ping()

    async def check_rustfs(self, health_url: str) -> None:
        response = await self.http.get(health_url)
        response.raise_for_status()
