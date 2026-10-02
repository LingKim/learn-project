import json
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
from qdrant_client import AsyncQdrantClient

from xuemian_ai.core.config import get_settings
from xuemian_ai.document_processing.parsers import ProcessingError
from xuemian_ai.document_processing.providers import (
    DeterministicProvider,
    QwenOcrProvider,
    validate_vectors,
)
from xuemian_ai.document_processing.retrieval import fuse_candidates
from xuemian_ai.document_processing.vector_store import VectorStore


async def test_qwen_ocr_contract_base64_no_system_prompt_no_confidence() -> None:
    settings = get_settings().model_copy(update={"environment": "test"})
    from pydantic import SecretStr

    settings.dashscope_api_key = SecretStr("synthetic-test-key")

    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "qwen3.5-ocr"
        assert [m["role"] for m in body["messages"]] == ["user"]
        assert body["messages"][0]["content"][0]["image_url"]["url"].startswith(
            "data:image/png;base64,"
        )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": "PostgreSQL transaction isolation"},
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handle)
    factory = httpx.AsyncClient
    with patch(
        "xuemian_ai.document_processing.providers.httpx.AsyncClient",
        side_effect=lambda **kwargs: factory(transport=transport),
    ):
        result = await QwenOcrProvider(settings).recognize(b"fake-png-fixture")
    assert result.confidence is None
    assert result.text == "PostgreSQL transaction isolation"


@pytest.mark.parametrize(
    ("status", "finish", "expected", "retryable"),
    [
        (200, "length", "DOCUMENT_OCR_OUTPUT_INCOMPLETE", False),
        (401, "stop", "DOCUMENT_OCR_AUTH_FAILED", False),
        (429, "stop", "DOCUMENT_OCR_UNAVAILABLE", True),
    ],
)
async def test_qwen_ocr_failure_classification(
    status: int, finish: str, expected: str, retryable: bool
) -> None:
    from pydantic import SecretStr

    settings = get_settings().model_copy(
        update={"environment": "test", "dashscope_api_key": SecretStr("synthetic")}
    )
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            status, json={"choices": [{"finish_reason": finish, "message": {"content": "fixture"}}]}
        )
    )
    factory = httpx.AsyncClient
    with patch(
        "xuemian_ai.document_processing.providers.httpx.AsyncClient",
        side_effect=lambda **kwargs: factory(transport=transport),
    ):
        with pytest.raises(ProcessingError) as exc:
            await QwenOcrProvider(settings).recognize(b"fixture")
    assert exc.value.code == expected and exc.value.retryable == retryable


async def test_local_qdrant_filters_user_and_draft_versions_and_deletes_precisely() -> None:
    settings = get_settings().model_copy(
        update={"environment": "test", "qdrant_collection": "isolated-test"}
    )
    client = AsyncQdrantClient(":memory:")
    store = VectorStore(settings, client)
    await store.initialize()
    provider = DeterministicProvider()
    vector = (await provider.embed(["transaction"]))[0]
    user, other, asset, version, draft, chunk, other_chunk, draft_chunk = [
        uuid4() for _ in range(8)
    ]
    await store.upsert(user, asset, version, [(chunk, vector)])
    await store.upsert(other, asset, version, [(other_chunk, vector)])
    await store.upsert(user, asset, draft, [(draft_chunk, vector)])
    hits = await store.search(user, [version], vector, 10)
    assert [item[0] for item in hits] == [chunk]
    await store.delete_version(user, asset, version)
    assert await store.count(user, asset, version) == 0
    assert await store.count(other, asset, version) == 1
    assert await store.count(user, asset, draft) == 1
    await store.close()


def test_rrf_deduplicates_same_id_but_retains_distinct_file_evidence() -> None:
    first, second, third = uuid4(), uuid4(), uuid4()
    result = fuse_candidates([(first, 0.9), (second, 0.8)], [(first, 0.7), (third, 0.6)], 10)
    assert result[0][0] == first
    assert {item[0] for item in result} == {first, second, third}


@pytest.mark.parametrize("vectors", [[[0.0] * 1024], [[1.0] * 1023], [[float("nan")] * 1024]])
def test_invalid_embeddings_are_rejected(vectors: list[list[float]]) -> None:
    with pytest.raises(ProcessingError, match="DOCUMENT_EMBEDDING_INVALID"):
        validate_vectors(vectors, 1)


async def test_embedding_sdk_disables_proxy_for_both_clients(monkeypatch) -> None:
    from pydantic import SecretStr

    from xuemian_ai.document_processing.providers import QwenEmbeddingProvider

    monkeypatch.setenv("ALL_PROXY", "socks5://127.0.0.1:1")
    settings = get_settings().model_copy(
        update={"environment": "test", "dashscope_api_key": SecretStr("synthetic")}
    )
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200,
            json={
                "object": "list",
                "model": settings.document_embedding_model,
                "data": [{"object": "embedding", "index": 0, "embedding": [1.0] * 1024}],
                "usage": {"prompt_tokens": 1, "total_tokens": 1},
            },
        )
    )
    sync_factory, async_factory = httpx.Client, httpx.AsyncClient

    class SyncClient(sync_factory):
        def __init__(self, **kwargs):
            assert kwargs["trust_env"] is False
            super().__init__(transport=transport, **kwargs)

    class AsyncClient(async_factory):
        def __init__(self, **kwargs):
            assert kwargs["trust_env"] is False
            super().__init__(transport=transport, **kwargs)

    with (
        patch("xuemian_ai.document_processing.providers.httpx.Client", new=SyncClient),
        patch("xuemian_ai.document_processing.providers.httpx.AsyncClient", new=AsyncClient),
    ):
        result = await QwenEmbeddingProvider(settings).embed(["synthetic fixture"])
    assert len(result) == 1 and len(result[0]) == 1024


async def test_embedding_constructor_failure_is_sanitized() -> None:
    from pydantic import SecretStr

    from xuemian_ai.document_processing.providers import QwenEmbeddingProvider

    settings = get_settings().model_copy(update={"dashscope_api_key": SecretStr("synthetic")})
    with patch(
        "xuemian_ai.document_processing.providers.OpenAIEmbeddings",
        side_effect=ValueError("sensitive upstream details"),
    ):
        with pytest.raises(ProcessingError, match="DOCUMENT_EMBEDDING_RESPONSE_INVALID") as error:
            await QwenEmbeddingProvider(settings).embed(["fixture"])
    assert "sensitive" not in str(error.value)


def test_sdk_connection_error_remains_retryable_and_sanitized() -> None:
    from openai import APIConnectionError

    from xuemian_ai.document_processing.providers import classify_upstream

    error = classify_upstream(
        APIConnectionError(request=httpx.Request("POST", "https://synthetic.invalid")),
        "DOCUMENT_EMBEDDING",
    )
    assert error.code == "DOCUMENT_EMBEDDING_UNAVAILABLE" and error.retryable
