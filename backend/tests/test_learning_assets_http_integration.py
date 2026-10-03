import os
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from xuemian_ai.accounts.models import User
from xuemian_ai.api.learning_assets import router
from xuemian_ai.auth.dependencies import current_user_model
from xuemian_ai.core.config import get_settings
from xuemian_ai.core.problem_details import register_problem_handlers

pytest_plugins = ["test_learning_assets_domain_integration"]

pytestmark = pytest.mark.skipif(
    not os.getenv("LEARNING_ASSETS_INTEGRATION_DB"), reason="explicit isolated database required"
)


def app_for(domain, owner=None, role="user"):
    app = FastAPI()
    app.state.infrastructure = SimpleNamespace(sessions=domain.sessions)
    app.include_router(router, prefix="/api/v1")
    register_problem_handlers(app)
    app.dependency_overrides[current_user_model] = lambda: User(id=owner or domain.owner, role=role)
    app.dependency_overrides[get_settings] = lambda: domain.settings
    return app


async def test_http_private_crud_run_recovery_failure_and_version(assets):
    domain, _ = assets
    app = app_for(domain)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://isolated"
    ) as client:
        key = str(uuid4())
        body = {"title": "事务", "request_key": key, "source_mode": "general"}
        response = await client.post("/api/v1/weaknesses", json=body)
        assert response.status_code == response.json()["code"] == 201
        assert response.headers["cache-control"] == "no-store"
        obj = response.json()["data"]
        repeated = await client.post("/api/v1/weaknesses", json=body)
        assert repeated.json()["data"]["id"] == obj["id"]
        detail = (await client.get("/api/v1/weaknesses/" + obj["id"])).json()["data"]
        assert detail["evidence"][0]["kind"] == "manual" and detail["run"]["status"] == "pending"
        lookup = await client.get(
            "/api/v1/learning/knowledge-runs", params={"request_key": detail["run"]["request_key"]}
        )
        assert lookup.status_code == 200 and lookup.json()["data"]["id"] == detail["run"]["id"]
        wrong_version = await client.patch(
            "/api/v1/weaknesses/" + obj["id"], json={"expected_version": 99, "title": "新版"}
        )
        assert wrong_version.status_code == wrong_version.json()["status"] == 409
        assert wrong_version.json()["error_key"] == "LEARNING_ASSET_VERSION_CONFLICT"
        cancelled = await client.post(
            "/api/v1/learning/knowledge-runs/" + detail["run"]["id"] + "/cancel"
        )
        assert cancelled.json()["data"]["status"] == "cancelled"
        create_key = str(uuid4())
        created = await client.post(
            "/api/v1/learning/explanations", json={"topic": "索引", "request_key": create_key}
        )
        assert created.status_code == created.json()["code"] == 202
        accepted = created.json()["data"]
        assert accepted["run"]["status"] == "pending"
        assert (
            await client.post(
                "/api/v1/learning/explanations", json={"topic": "索引", "request_key": create_key}
            )
        ).json()["data"]["explanation"]["id"] == accepted["explanation"]["id"]
        claim = await domain.claim_run("http-test")
        await domain.fail_run(claim.id, claim.lease_token, "KNOWLEDGE_PROVIDER_UNAVAILABLE", True)
        run = (await client.get("/api/v1/learning/knowledge-runs/" + str(claim.id))).json()["data"]
        assert run["status"] == "failed" and run["retryable"]
        retry = await client.post(
            "/api/v1/learning/knowledge-runs/" + str(claim.id) + "/retry",
            json={"request_key": run["request_key"], "input_digest": run["input_digest"]},
        )
        assert (
            retry.status_code == retry.json()["code"] == 202
            and retry.json()["data"]["status"] == "pending"
        )
        invalid = await client.post(
            "/api/v1/learning/explanations",
            json={"topic": "事务", "source_mode": "materials", "request_key": str(uuid4())},
        )
        assert invalid.status_code == 422
        app.dependency_overrides[current_user_model] = lambda: User(id=uuid4(), role="user")
        for path in [
            "/weaknesses/" + obj["id"],
            "/learning/explanations/" + obj["explanation_id"],
            "/learning/knowledge-runs/" + detail["run"]["id"],
        ]:
            denied = await client.get("/api/v1" + path)
            assert (
                denied.status_code == 404
                and denied.json()["error_key"] == "LEARNING_ASSET_NOT_FOUND"
            )
        app.dependency_overrides[current_user_model] = lambda: User(id=domain.owner, role="admin")
        assert (await client.get("/api/v1/weaknesses/" + obj["id"])).status_code == 404
        assert (
            await client.post(
                "/api/v1/weaknesses", json={"title": "管理员业务资料", "request_key": str(uuid4())}
            )
        ).status_code == 404
