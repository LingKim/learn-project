import os
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from xuemian_ai.accounts.models import User
from xuemian_ai.api.practice import router
from xuemian_ai.auth.dependencies import current_user_model
from xuemian_ai.core.config import get_settings
from xuemian_ai.core.problem_details import register_problem_handlers
from xuemian_ai.practice.worker import PracticeWorker

pytest_plugins = ["test_practice_domain_integration"]
pytestmark = pytest.mark.skipif(
    not os.getenv("PRACTICE_INTEGRATION_DB"), reason="explicit isolated database required"
)


class SyntheticProvider:
    async def invoke(self, operation, payload):
        if operation == "plan":
            return {
                "recommended_config": payload["config"],
                "summary": "合成配置摘要",
                "recommendation_summary": "合成推荐摘要",
                "suggestions": [],
            }
        if operation in ("generate", "regenerate"):
            return {
                "status": "ready",
                "questions": [
                    {
                        "type": "single_choice",
                        "difficulty": "medium",
                        "topics": ["事务"],
                        "stem": "PostgreSQL事务原子性是什么？",
                        "answer_explanation": "全部成功或全部回滚",
                        "options": [
                            {"id": "A", "text": "全部成功或全部回滚"},
                            {"id": "B", "text": "允许部分写入"},
                        ],
                        "answer": "A",
                        "rubric": [{"id": "correct", "description": "选A正确", "max_score": 1}],
                        "citation_ids": [],
                    }
                ],
            }
        raise AssertionError("unexpected operation")


async def test_actual_http_worker_and_saved_attempt_refresh(domain):
    app = FastAPI()
    app.state.infrastructure = SimpleNamespace(sessions=domain.sessions)
    app.include_router(router, prefix="/api/v1")
    register_problem_handlers(app)
    app.dependency_overrides[current_user_model] = lambda: User(id=domain.owner)
    app.dependency_overrides[get_settings] = lambda: domain.settings
    worker = PracticeWorker(domain.sessions, domain.settings, provider=SyntheticProvider())
    base = "/api/v1/learning/practice"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://isolated"
    ) as client:
        create = await client.post(
            base + "/sets",
            json={
                "title": "合成HTTP练习",
                "request_key": str(uuid4()),
                "config": {
                    "topic": "事务",
                    "question_count": 1,
                    "question_types": {"single_choice": 1},
                },
            },
        )
        assert create.status_code == create.json()["code"] == 201
        assert create.headers["cache-control"] == "no-store"
        obj = create.json()["data"]
        plan = await client.post(
            f"{base}/sets/{obj['id']}/plan",
            json={"request_key": str(uuid4()), "expected_version": obj["version"]},
        )
        assert plan.status_code == plan.json()["code"] == 202
        assert await worker.run_once()
        completed = (await client.get(f"{base}/runs/{plan.json()['data']['id']}")).json()["data"]
        assert completed["status"] == "succeeded"
        proposal = (
            await client.get(f"{base}/sets/{obj['id']}/plans/{completed['result_ref']['version']}")
        ).json()["data"]
        generated = await client.post(
            f"{base}/sets/{obj['id']}/generate",
            json={
                "request_key": str(uuid4()),
                "expected_version": obj["version"],
                "plan_version": proposal["version"],
                "candidate": "original",
                "confirmed_config_digest": proposal["original"]["config_digest"],
            },
        )
        assert generated.status_code == generated.json()["code"] == 202
        await worker.run_once()
        result = (await client.get(f"{base}/runs/{generated.json()['data']['id']}")).json()["data"]
        assert result["status"] == "succeeded", result
        detail = (await client.get(f"{base}/sets/{obj['id']}")).json()["data"]
        question_id = detail["revision"]["questions"][0]["question_id"]
        started = await client.post(
            f"{base}/sets/{obj['id']}/attempts",
            json={
                "request_key": str(uuid4()),
                "expected_version": detail["version"],
                "revision_id": result["result_ref"]["id"],
            },
        )
        assert started.status_code == 201
        attempt = started.json()["data"]
        saved = (
            await client.patch(
                f"{base}/attempts/{attempt['id']}/answers/{question_id}",
                json={
                    "expected_version": attempt["version"],
                    "answer": {"type": "single_choice", "option_id": "A"},
                },
            )
        ).json()["data"]
        submit = await client.post(
            f"{base}/attempts/{attempt['id']}/questions/{question_id}/submit",
            json={
                "request_key": str(uuid4()),
                "expected_version": saved["version"],
                "answer_version": saved["answers"][0]["version"],
            },
        )
        assert submit.status_code == submit.json()["code"] == 200
        assert submit.json()["data"]["grades"][0]["level"] == "correct"
        refreshed = (await client.get(f"{base}/attempts/{attempt['id']}")).json()["data"]
        assert refreshed["answers"][0]["answer"]["option_id"] == "A"
        assert refreshed["submissions"][0]["grades"][0]["level"] == "correct"
        report = (await client.get(f"{base}/attempts/{attempt['id']}/report")).json()["data"]
        assert report["score"] == report["max_score"] == 1
        completed = await client.post(
            f"{base}/attempts/{attempt['id']}/complete",
            json={"expected_version": refreshed["version"]},
        )
        assert completed.json()["data"]["status"] == "completed"
        app.dependency_overrides[current_user_model] = lambda: User(id=uuid4(), role="admin")
        inaccessible = await client.get(f"{base}/sets/{obj['id']}")
        assert inaccessible.status_code == inaccessible.json()["code"] == 404


async def test_http_config_patch_returns_timestamp_and_replans(domain):
    app = FastAPI()
    app.state.infrastructure = SimpleNamespace(sessions=domain.sessions)
    app.include_router(router, prefix="/api/v1")
    register_problem_handlers(app)
    app.dependency_overrides[current_user_model] = lambda: User(id=domain.owner)
    app.dependency_overrides[get_settings] = lambda: domain.settings
    worker = PracticeWorker(domain.sessions, domain.settings, provider=SyntheticProvider())
    base = "/api/v1/learning/practice"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://isolated"
    ) as client:
        response = await client.post(
            base + "/sets",
            json={
                "request_key": str(uuid4()),
                "config": {
                    "topic": "旧主题",
                    "question_count": 1,
                    "question_types": {"single_choice": 1},
                },
            },
        )
        original = response.json()["data"]
        patched = await client.patch(
            f"{base}/sets/{original['id']}",
            json={
                "expected_version": original["version"],
                "title": "修改后练习",
                "config": {
                    "topic": "新事务主题",
                    "question_count": 1,
                    "question_types": {"single_choice": 1},
                },
            },
        )
        assert patched.status_code == patched.json()["code"] == 200
        updated = patched.json()["data"]
        assert updated["version"] == original["version"] + 1
        assert updated["updated_at"] and updated["title"] == "修改后练习"
        planned = await client.post(
            f"{base}/sets/{original['id']}/plan",
            json={"request_key": str(uuid4()), "expected_version": updated["version"]},
        )
        assert planned.status_code == 202
        await worker.run_once()
        state = (await client.get(f"{base}/runs/{planned.json()['data']['id']}")).json()["data"]
        assert state["status"] == "succeeded"
        plan = (
            await client.get(f"{base}/sets/{original['id']}/plans/{state['result_ref']['version']}")
        ).json()["data"]
        assert plan["original"]["config"]["topic"] == "新事务主题"
        assert plan["base_set_version"] == updated["version"]


async def test_http_worker_omitted_recommendation_keeps_frozen_profile(domain):
    from xuemian_ai.profiles.models import UserProfile

    async with domain.sessions.begin() as session:
        session.add(UserProfile(user_id=domain.owner, target_job="ProfileJava"))
    app = FastAPI()
    app.state.infrastructure = SimpleNamespace(sessions=domain.sessions)
    app.include_router(router, prefix="/api/v1")
    register_problem_handlers(app)
    app.dependency_overrides[current_user_model] = lambda: User(id=domain.owner)
    app.dependency_overrides[get_settings] = lambda: domain.settings
    worker = PracticeWorker(domain.sessions, domain.settings, provider=SyntheticProvider())
    base = "/api/v1/learning/practice"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://isolated"
    ) as client:
        created = await client.post(
            base + "/sets",
            json={
                "request_key": str(uuid4()),
                "config": {
                    "topic": "事务",
                    "question_count": 1,
                    "question_types": {"single_choice": 1},
                },
            },
        )
        obj = created.json()["data"]
        assert obj["profile_override_fields"] == []
        planned = await client.post(
            f"{base}/sets/{obj['id']}/plan",
            json={"request_key": str(uuid4()), "expected_version": obj["version"]},
        )
        await worker.run_once()
        state = (await client.get(f"{base}/runs/{planned.json()['data']['id']}")).json()["data"]
        assert state["status"] == "succeeded"
        plan = (
            await client.get(f"{base}/sets/{obj['id']}/plans/{state['result_ref']['version']}")
        ).json()["data"]
        assert plan["original"]["effective_context"]["values"]["target_job"] == "ProfileJava"
        assert plan["recommended"]["effective_context"]["values"]["target_job"] == "ProfileJava"
