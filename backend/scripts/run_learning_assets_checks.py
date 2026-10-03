"""Validate learning assets in one disposable project DB without managing dependencies."""

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
    parser.add_argument("--keep", action="store_true", help="keep only this synthetic test DB")
    parser.add_argument("--cleanup", type=Path)
    parser.add_argument("--real-models", action="store_true", help="send synthetic samples only")
    args = parser.parse_args()
    values = {k: v for k, v in dotenv_values(ROOT / ".env").items() if v is not None}
    owner = values["APP_DB_USER"]
    if not re.fullmatch(r"[A-Za-z0-9_]+", owner):
        raise RuntimeError("invalid project app role")

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

    if args.cleanup:
        saved = json.loads(args.cleanup.read_text())
        name = saved["LEARNING_ASSETS_INTEGRATION_DB"]
        if not re.fullmatch(r"xuemian_assets_[a-f0-9]{12}_test", name):
            raise RuntimeError("refuse cleanup outside this test database namespace")
        sql(f'DROP DATABASE "{name}" WITH (FORCE);')
        args.cleanup.unlink()
        return

    name = "xuemian_assets_" + uuid4().hex[:12] + "_test"
    url = make_url(values["DATABASE_URL"]).set(database=name)
    env = {
        **os.environ,
        **values,
        "DATABASE_URL": url.render_as_string(hide_password=False),
        "ENVIRONMENT": "test",
        "DOCUMENT_PROVIDER": "deterministic",
        "LEARNING_ASSETS_INTEGRATION_DB": name,
        "PRACTICE_INTEGRATION_DB": name,
        "DOCUMENT_INTEGRATION_DB": name,
        "QDRANT_URL": "http://127.0.0.1:6333",
        "QDRANT_COLLECTION": "xuemian-assets-test-" + uuid4().hex,
    }
    if args.real_models:
        env["LEARNING_REAL_MODELS"] = "1"
        env["KNOWLEDGE_FORMAT_EVAL"] = "1"
    env_path: Path | None = None
    created = False
    try:
        sql(f'CREATE DATABASE "{name}" OWNER "{owner}";')
        created = True
        descriptor, filename = tempfile.mkstemp(prefix="xuemian-assets-env-", suffix=".json")
        env_path = Path(filename)
        with os.fdopen(descriptor, "w") as stream:
            json.dump(env, stream)
        print({"isolated_database": name, "protected_environment": str(env_path)}, flush=True)
        for command in (["upgrade", "head"], ["downgrade", "20261003_03"], ["upgrade", "head"]):
            subprocess.run(
                [str(ROOT / "backend/.venv/bin/alembic"), *command],
                cwd=ROOT / "backend",
                env=env,
                check=True,
            )
        targets = sorted(
            str(p.relative_to(ROOT / "backend"))
            for pattern in ("test_learning_assets*.py", "test_learning_knowledge*.py")
            for p in (ROOT / "backend/tests").glob(pattern)
        )
        if not targets:
            raise RuntimeError("learning assets tests missing")
        targets += [
            "tests/test_practice_domain_integration.py",
            "tests/test_practice_http_integration.py",
        ]
        result = subprocess.run(
            [str(ROOT / "backend/.venv/bin/pytest"), *targets, "-q"],
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
