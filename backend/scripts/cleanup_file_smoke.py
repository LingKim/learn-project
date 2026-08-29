import argparse
import asyncio
from typing import Any, cast

from sqlalchemy import delete, select

from xuemian_ai.accounts.models import User
from xuemian_ai.core.config import get_settings
from xuemian_ai.file_management.service import FileManagementService
from xuemian_ai.infrastructure.database import create_database_engine, create_session_factory


async def cleanup(username: str) -> None:
    settings = get_settings()
    engine = create_database_engine(settings.database_url.get_secret_value())
    sessions = create_session_factory(engine)
    try:
        async with sessions() as session, session.begin():
            user = await session.scalar(select(User).where(User.username == username))
            if user is None:
                return
            service = FileManagementService(
                session=session,
                redis=cast(Any, None),
                storage=cast(Any, None),
                settings=settings,
                user=user,
            )
            await service.enqueue_user_file_cleanup(user.id)
        await asyncio.sleep(1)
        async with sessions() as session, session.begin():
            await session.execute(delete(User).where(User.username == username))
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("username")
    args = parser.parse_args()
    asyncio.run(cleanup(args.username))


if __name__ == "__main__":
    main()
