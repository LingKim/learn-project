import asyncio
from uuid import uuid4

from sqlalchemy import select

from xuemian_ai.accounts.models import User
from xuemian_ai.auth.schemas import normalize_username, validate_password_rules
from xuemian_ai.auth.security import PasswordService
from xuemian_ai.core.config import Settings, get_settings
from xuemian_ai.infrastructure.database import create_database_engine, create_session_factory
from xuemian_ai.knowledge_bases.models import KnowledgeBase


async def initialize_administrator(settings: Settings) -> str:
    if not settings.admin_username or settings.admin_password is None:
        raise ValueError("ADMIN_USERNAME and ADMIN_PASSWORD must be configured")
    username = normalize_username(settings.admin_username)
    password = validate_password_rules(settings.admin_password.get_secret_value())
    engine = create_database_engine(settings.database_url.get_secret_value())
    sessions = create_session_factory(engine)
    try:
        async with sessions() as session, session.begin():
            existing = await session.scalar(select(User).where(User.username == username))
            if existing is not None:
                if existing.role != "admin":
                    raise ValueError("configured administrator username belongs to a regular user")
                return "administrator already exists; no changes applied"

            user_id = uuid4()
            session.add(
                User(
                    id=user_id,
                    username=username,
                    nickname="系统管理员",
                    password_hash=PasswordService().hash(password),
                    role="admin",
                    status="active",
                    created_by=user_id,
                    updated_by=user_id,
                )
            )
            await session.flush()
            session.add(
                KnowledgeBase(
                    owner_user_id=user_id,
                    name="默认知识库",
                    is_default=True,
                    created_by=user_id,
                    updated_by=user_id,
                )
            )
        return "administrator created"
    finally:
        await engine.dispose()


def run() -> None:
    try:
        message = asyncio.run(initialize_administrator(get_settings()))
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    print(message)
