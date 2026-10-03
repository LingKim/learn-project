"""Exercise the real HTTP/worker path using a caller-supplied private access token.

Creates only a synthetic private practice; does not delete existing business data.
The API and practice worker must already be running. Never prints token or answers.
"""

import argparse
import asyncio
import json
import time
from pathlib import Path
from uuid import uuid4

import httpx


async def run() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    token = args.token_file.read_text().strip()
    async with httpx.AsyncClient(
        base_url=args.base_url.rstrip("/") + "/api/v1/learning/practice",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
        trust_env=False,
    ) as client:

        async def request(method, path, body=None):
            response = await client.request(method, path, json=body)
            response.raise_for_status()
            envelope = response.json()
            assert envelope["code"] == response.status_code
            return envelope["data"]

        async def terminal(run):
            deadline = time.monotonic() + 200
            while time.monotonic() < deadline:
                current = await request("GET", f"/runs/{run['id']}")
                if current["status"] == "succeeded":
                    return current
                if current["status"] in ("failed", "cancelled"):
                    raise RuntimeError(f"run {current['status']}: {current['error_key']}")
                await asyncio.sleep(1)
            raise TimeoutError("practice run did not reach a terminal status")

        obj = await request(
            "POST",
            "/sets",
            {
                "title": "合成HTTP验收练习",
                "request_key": str(uuid4()),
                "config": {
                    "topic": "数据库事务原子性",
                    "question_count": 1,
                    "question_types": {"single_choice": 1},
                },
            },
        )
        planned = await terminal(
            await request(
                "POST",
                f"/sets/{obj['id']}/plan",
                {"request_key": str(uuid4()), "expected_version": obj["version"]},
            )
        )
        plan = await request("GET", f"/sets/{obj['id']}/plans/{planned['result_ref']['version']}")
        generated = await terminal(
            await request(
                "POST",
                f"/sets/{obj['id']}/generate",
                {
                    "request_key": str(uuid4()),
                    "expected_version": obj["version"],
                    "plan_version": plan["version"],
                    "candidate": "original",
                    "confirmed_config_digest": plan["original"]["config_digest"],
                },
            )
        )
        detail = await request("GET", f"/sets/{obj['id']}")
        q = detail["revision"]["questions"][0]
        attempt = await request(
            "POST",
            f"/sets/{obj['id']}/attempts",
            {
                "request_key": str(uuid4()),
                "expected_version": detail["version"],
                "revision_id": generated["result_ref"]["id"],
            },
        )
        saved = await request(
            "PATCH",
            f"/attempts/{attempt['id']}/answers/{q['question_id']}",
            {
                "expected_version": attempt["version"],
                "answer": {"type": "single_choice", "option_id": q["answer"]},
            },
        )
        submission = await request(
            "POST",
            f"/attempts/{attempt['id']}/questions/{q['question_id']}/submit",
            {
                "request_key": str(uuid4()),
                "expected_version": saved["version"],
                "answer_version": saved["answers"][0]["version"],
            },
        )
        refreshed = await request("GET", f"/attempts/{attempt['id']}")
        assert refreshed["submissions"][0]["submission_id"] == submission["submission_id"]
        report = await request("GET", f"/attempts/{attempt['id']}/report")
        assert report["submitted_count"] == report["graded_count"] == 1
        await request(
            "POST",
            f"/attempts/{attempt['id']}/complete",
            {"expected_version": refreshed["version"]},
        )
        evidence = {
            "set_id": obj["id"],
            "attempt_id": attempt["id"],
            "plan_run_id": planned["id"],
            "generate_run_id": generated["id"],
            "status": "completed",
            "submitted_count": report["submitted_count"],
            "graded_count": report["graded_count"],
            "grade_level": submission["grades"][0]["level"],
            "synthetic_only": True,
        }
        args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
        print("Real HTTP/worker synthetic practice passed; evidence saved without token or body.")


if __name__ == "__main__":
    asyncio.run(run())
