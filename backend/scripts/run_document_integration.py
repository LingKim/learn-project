"""只创建和删除本次唯一隔离数据库；不操作 PostgreSQL/Redis 生命周期。"""

import os
import re
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from dotenv import dotenv_values
from sqlalchemy.engine import make_url

root = Path(__file__).resolve().parents[2]
values = {k: v for k, v in dotenv_values(root / ".env").items() if v is not None}
name = "xuemian_document_" + uuid4().hex[:12] + "_e2e"
container = values["POSTGRES_CONTAINER_NAME"]
admin = values["POSTGRES_ADMIN_USER"]
owner = values["APP_DB_USER"]
if not re.fullmatch(r"[A-Za-z0-9_]+", owner):
    raise RuntimeError("invalid app role")


def sql(statement: str) -> None:
    subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            container,
            "psql",
            "--username",
            admin,
            "--dbname",
            "postgres",
            "--set",
            "ON_ERROR_STOP=1",
        ],
        input=statement,
        text=True,
        check=True,
    )


url = make_url(values["DATABASE_URL"]).set(database=name)
env = {
    **os.environ,
    **values,
    "DATABASE_URL": url.render_as_string(hide_password=False),
    "ENVIRONMENT": "test",
    "DOCUMENT_PROVIDER": "deterministic",
    "DOCUMENT_INTEGRATION_DB": name,
    "QDRANT_URL": "http://127.0.0.1:6335",
    "QDRANT_COLLECTION": "xuemian-e2e-" + uuid4().hex,
}
created = False
try:
    sql(f'CREATE DATABASE "{name}" OWNER "{owner}";')
    created = True
    subprocess.run(
        [str(root / "backend/.venv/bin/alembic"), "upgrade", "head"],
        cwd=root / "backend",
        env=env,
        check=True,
    )
    subprocess.run(
        [str(root / "backend/.venv/bin/alembic"), "downgrade", "20260830_01"],
        cwd=root / "backend",
        env=env,
        check=True,
    )
    subprocess.run(
        [str(root / "backend/.venv/bin/alembic"), "upgrade", "head"],
        cwd=root / "backend",
        env=env,
        check=True,
    )
    result = subprocess.run(
        [str(root / "backend/.venv/bin/pytest"), "tests/test_document_integration.py", "-q"],
        cwd=root / "backend",
        env=env,
    )
    sys.exit(result.returncode)
finally:
    if created:
        sql(f'DROP DATABASE "{name}" WITH (FORCE);')
