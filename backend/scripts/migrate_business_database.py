"""按 AGENTS 授权备份后迁移本项目业务库；不管理外部依赖生命周期。"""

import asyncio
import hashlib
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from dotenv import dotenv_values
from sqlalchemy import text
from sqlalchemy.engine import make_url

from xuemian_ai.infrastructure.database import create_database_engine

root = Path(__file__).resolve().parents[2]
values = {key: value for key, value in dotenv_values(root / ".env").items() if value is not None}
url = make_url(values["DATABASE_URL"])
if (
    url.database != "xuemian_ai"
    or url.database != values["APP_DB_NAME"]
    or url.username != values["APP_DB_USER"]
):
    raise RuntimeError("target must be the configured project business database and role")
if url.host not in {"localhost", "127.0.0.1"} or url.port not in {None, 5432}:
    raise RuntimeError("only the current local project database is authorized")
for key in ("POSTGRES_CONTAINER_NAME", "POSTGRES_ADMIN_USER"):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", values[key]):
        raise RuntimeError("invalid local database identity")


async def revision() -> str:
    engine = create_database_engine(values["DATABASE_URL"])
    try:
        async with engine.connect() as connection:
            if await connection.scalar(text("SELECT current_database()")) != "xuemian_ai":
                raise RuntimeError("database preflight mismatch")
            return str(await connection.scalar(text("SELECT version_num FROM alembic_version")))
    finally:
        await engine.dispose()


before = asyncio.run(revision())
config = Config(str(root / "backend/alembic.ini"))
config.set_main_option("script_location", str(root / "backend/migrations"))
head = ScriptDirectory.from_config(config).get_current_head()
if before == head:
    print({"database": "xuemian_ai", "revision": before, "migration": "already_current"})
else:
    backup_dir = root / ".runtime/backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / (
        "xuemian_ai-before-"
        + str(head)
        + "-"
        + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        + ".dump"
    )
    descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        subprocess.run(
            [
                "docker",
                "exec",
                values["POSTGRES_CONTAINER_NAME"],
                "pg_dump",
                "--username",
                values["POSTGRES_ADMIN_USER"],
                "--dbname",
                "xuemian_ai",
                "--format",
                "custom",
            ],
            stdout=output,
            check=True,
        )
    with backup.open("rb") as input_file:
        subprocess.run(
            ["docker", "exec", "-i", values["POSTGRES_CONTAINER_NAME"], "pg_restore", "--list"],
            stdin=input_file,
            stdout=subprocess.DEVNULL,
            check=True,
        )
    subprocess.run(
        [str(root / "backend/.venv/bin/alembic"), "upgrade", "head"],
        cwd=root / "backend",
        check=True,
    )
    after = asyncio.run(revision())
    if after != head:
        raise RuntimeError("migration revision verification failed; preserve backup")
    print(
        {
            "database": "xuemian_ai",
            "before": before,
            "after": after,
            "backup": str(backup),
            "backup_bytes": backup.stat().st_size,
            "backup_sha256": hashlib.sha256(backup.read_bytes()).hexdigest(),
        }
    )
