"""Provision one disposable practice database; never change external service lifecycle."""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

from dotenv import dotenv_values
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]


def run() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--keep", action="store_true", help="retain isolated DB for synthetic sibling checks"
    )
    parser.add_argument("--cleanup", type=Path)
    args = parser.parse_args()
    values = {k: v for k, v in dotenv_values(ROOT / ".env").items() if v is not None}
    container, admin, owner = (
        values["POSTGRES_CONTAINER_NAME"],
        values["POSTGRES_ADMIN_USER"],
        values["APP_DB_USER"],
    )
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

    if args.cleanup:
        env = json.loads(args.cleanup.read_text())
        name = env["PRACTICE_INTEGRATION_DB"]
        if not re.fullmatch(r"xuemian_practice_[a-f0-9]{12}_e2e", name):
            raise RuntimeError("refuse non-practice database cleanup")
        sql(f'DROP DATABASE "{name}" WITH (FORCE);')
        args.cleanup.unlink()
        return
    name = "xuemian_practice_" + uuid4().hex[:12] + "_e2e"
    url = make_url(values["DATABASE_URL"]).set(database=name)
    env = {
        **os.environ,
        **values,
        "DATABASE_URL": url.render_as_string(hide_password=False),
        "ENVIRONMENT": "test",
        "DOCUMENT_PROVIDER": "deterministic",
        "PRACTICE_INTEGRATION_DB": name,
        "DOCUMENT_INTEGRATION_DB": name,
        "QDRANT_URL": "http://127.0.0.1:6333",
        "QDRANT_COLLECTION": "xuemian-practice-e2e-" + uuid4().hex,
    }
    env_path = None
    created = False
    try:
        sql(f'CREATE DATABASE "{name}" OWNER "{owner}";')
        created = True
        for command in (
            ["alembic", "upgrade", "head"],
            ["alembic", "downgrade", "20261003_02"],
            ["alembic", "upgrade", "head"],
        ):
            subprocess.run(
                [str(ROOT / "backend/.venv/bin" / command[0]), *command[1:]],
                cwd=ROOT / "backend",
                env=env,
                check=True,
            )
        descriptor, filename = tempfile.mkstemp(prefix="xuemian-practice-env-", suffix=".json")
        env_path = Path(filename)
        with os.fdopen(descriptor, "w") as stream:
            json.dump(env, stream)
        print(f"Isolated database: {name}\nProtected environment file: {env_path}", flush=True)
        result = subprocess.run(
            [
                str(ROOT / "backend/.venv/bin/pytest"),
                "tests/test_practice_domain_integration.py",
                "tests/test_practice_http_integration.py",
                "-q",
            ],
            cwd=ROOT / "backend",
            env=env,
        )
        sys.exit(result.returncode)
    finally:
        if created and not args.keep:
            sql(f'DROP DATABASE "{name}" WITH (FORCE);')
            if env_path:
                env_path.unlink(missing_ok=True)


if __name__ == "__main__":
    run()
