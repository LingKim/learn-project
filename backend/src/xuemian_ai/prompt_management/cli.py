"""显式初始化真实注册定义的草稿；不运行模型，也不发布任何版本。"""

import argparse
import asyncio
from uuid import UUID

from xuemian_ai.core.config import get_settings
from xuemian_ai.infrastructure.database import create_database_engine, create_session_factory
from xuemian_ai.prompt_management.service import PromptService


async def bootstrap(actor: UUID) -> None:
    settings = get_settings()
    engine = create_database_engine(settings.database_url.get_secret_value())
    try:
        definitions = await PromptService(
            create_session_factory(engine), actor, settings
        ).bootstrap()
        print(f"已注册 {len(definitions)} 个真实定义；新模板仅为待评测草稿。")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin-user-id", type=UUID, required=True)
    args = parser.parse_args()
    asyncio.run(bootstrap(args.admin_user_id))


if __name__ == "__main__":
    main()
