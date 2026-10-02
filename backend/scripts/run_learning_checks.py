"""在唯一临时 DB/collection 验证学习与检索；不迁移业务库，不启停基础设施。"""

import argparse
import os
import re
import subprocess
from pathlib import Path
from uuid import uuid4

from dotenv import dotenv_values
from sqlalchemy.engine import make_url

root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument("--real-models", action="store_true", help="仅发送合成问题与资料给千问")
parser.add_argument("--quality", action="store_true", help="运行真实千问合成检索评测")
args = parser.parse_args()
values = {k: v for k, v in dotenv_values(root / ".env").items() if v is not None}
name = "xuemian_learning_" + uuid4().hex[:12] + "_test"
owner = values["APP_DB_USER"]
if not re.fullmatch(r"[A-Za-z0-9_]+", owner):
    raise RuntimeError("invalid app role")
collection = "xuemian-learning-test-" + uuid4().hex
url = make_url(values["DATABASE_URL"]).set(database=name)
env = {
    **os.environ,
    **values,
    "DATABASE_URL": url.render_as_string(hide_password=False),
    "ENVIRONMENT": "test",
    "DOCUMENT_PROVIDER": "deterministic",
    "DOCUMENT_INTEGRATION_DB": name,
    "QDRANT_COLLECTION": collection,
    "LEARNING_ANSWER_MODEL": "qwen3.8-flash",
}
if args.real_models:
    env["LEARNING_REAL_MODELS"] = "1"
if args.quality:
    env["RETRIEVAL_REAL_QUALITY"] = "1"


def sql(statement: str) -> None:
    subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            values["POSTGRES_CONTAINER_NAME"],
            "psql",
            "--username",
            values["POSTGRES_ADMIN_USER"],
            "--dbname",
            "postgres",
            "--set",
            "ON_ERROR_STOP=1",
        ],
        input=statement,
        text=True,
        check=True,
    )


created = False
try:
    sql(f'CREATE DATABASE "{name}" OWNER "{owner}";')
    created = True
    for command in ("upgrade head", "downgrade 20261002_01", "upgrade head"):
        subprocess.run(
            [str(root / "backend/.venv/bin/alembic"), *command.split()],
            cwd=root / "backend",
            env=env,
            check=True,
        )
    targets = ["tests/test_learning_integration.py", "tests/test_document_integration.py"]
    if args.quality:
        targets.append("tests/test_retrieval_quality.py")
    subprocess.run(
        [str(root / "backend/.venv/bin/pytest"), *targets, "-q"],
        cwd=root / "backend",
        env=env,
        check=True,
    )
finally:
    # 测试 fixture 清 collection；失败/中断后仍只清本次精确 collection。
    cleanup = """import asyncio
from xuemian_ai.core.config import get_settings
from xuemian_ai.document_processing.vector_store import VectorStore
async def run():
    store=VectorStore(get_settings())
    try:
        if await store.client.collection_exists(store.collection):
            await store.client.delete_collection(store.collection)
    finally:
        await store.close()
asyncio.run(run())
"""
    try:
        subprocess.run(
            [str(root / "backend/.venv/bin/python"), "-c", cleanup],
            cwd=root / "backend",
            env=env,
            check=True,
        )
    finally:
        if created:
            sql(f'DROP DATABASE "{name}" WITH (FORCE);')
