import base64
import hashlib
import math
import re
from typing import Protocol

import httpx
from langchain_openai import OpenAIEmbeddings
from openai import APIConnectionError, APITimeoutError
from pydantic import BaseModel, ConfigDict, Field

from xuemian_ai.core.config import Settings
from xuemian_ai.document_processing.parsers import OcrResult, ProcessingError


class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class RerankProvider(Protocol):
    async def rerank(self, query: str, texts: list[str]) -> list[tuple[int, float]]: ...


def validate_vectors(vectors: list[list[float]], expected: int) -> list[list[float]]:
    if len(vectors) != expected or any(
        len(v) != 1024 or not all(math.isfinite(x) for x in v) or not any(v) for v in vectors
    ):
        raise ProcessingError("DOCUMENT_EMBEDDING_INVALID")
    return vectors


def classify_upstream(exc: Exception, prefix: str) -> ProcessingError:
    status = getattr(exc, "status_code", None)
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
    if status in {401, 403}:
        return ProcessingError(f"{prefix}_AUTH_FAILED")
    if (
        status == 429
        or isinstance(status, int)
        and status >= 500
        or isinstance(
            exc,
            (
                TimeoutError,
                httpx.TimeoutException,
                httpx.NetworkError,
                APIConnectionError,
                APITimeoutError,
            ),
        )
    ):
        return ProcessingError(f"{prefix}_UNAVAILABLE", retryable=True)
    return ProcessingError(f"{prefix}_RESPONSE_INVALID")


class QwenEmbeddingProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.settings.dashscope_api_key.get_secret_value():
            raise ProcessingError("DOCUMENT_EMBEDDING_AUTH_FAILED")
        # 两种客户端均显式禁用环境代理；SDK 重试由持久化任务接管。
        try:
            with httpx.Client(
                timeout=self.settings.document_model_timeout_seconds, trust_env=False
            ) as sync_http:
                async with httpx.AsyncClient(
                    timeout=self.settings.document_model_timeout_seconds, trust_env=False
                ) as async_http:
                    model = OpenAIEmbeddings(
                        model=self.settings.document_embedding_model,
                        api_key=self.settings.dashscope_api_key,
                        base_url=str(self.settings.ai_base_url).rstrip("/"),
                        dimensions=1024,
                        chunk_size=20,
                        max_retries=0,
                        check_embedding_ctx_length=False,
                        http_client=sync_http,
                        http_async_client=async_http,
                    )
                    return validate_vectors(await model.aembed_documents(texts), len(texts))
        except ProcessingError:
            raise
        except Exception as exc:
            raise classify_upstream(exc, "DOCUMENT_EMBEDDING") from None


class QwenOcrProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def recognize(self, png: bytes) -> OcrResult:
        if not self.settings.dashscope_api_key.get_secret_value():
            raise ProcessingError("DOCUMENT_OCR_AUTH_FAILED")
        image = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
        if len(image) > 10_000_000:
            raise ProcessingError("DOCUMENT_OCR_LIMIT_EXCEEDED")
        body = {
            "model": self.settings.document_ocr_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": image},
                            "min_pixels": 3072,
                            "max_pixels": min(8388608, self.settings.document_ocr_max_pixels),
                        },
                        {"type": "text", "text": "请仅输出图像中的文本内容。"},
                    ],
                }
            ],
            "max_tokens": 16384,
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.document_model_timeout_seconds, trust_env=False
            ) as http:
                response = await http.post(
                    str(self.settings.ai_base_url).rstrip("/") + "/chat/completions",
                    json=body,
                    headers={
                        "Authorization": "Bearer "
                        + self.settings.dashscope_api_key.get_secret_value()
                    },
                )
                response.raise_for_status()
                data = OcrCompletion.model_validate(response.json())
            choice = data.choices[0]
            if choice.finish_reason != "stop":
                raise ProcessingError("DOCUMENT_OCR_OUTPUT_INCOMPLETE")
            return OcrResult(choice.message.content)
        except ProcessingError:
            raise
        except Exception as exc:
            raise classify_upstream(exc, "DOCUMENT_OCR") from None


class OcrMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    content: str = Field(max_length=100_000)


class OcrChoice(BaseModel):
    model_config = ConfigDict(extra="ignore")
    message: OcrMessage
    finish_reason: str


class OcrCompletion(BaseModel):
    model_config = ConfigDict(extra="ignore")
    choices: list[OcrChoice] = Field(min_length=1, max_length=1)


class RankedItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    index: int = Field(ge=0)
    relevance_score: float = Field(ge=0, le=1, allow_inf_nan=False)


class RerankOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    results: list[RankedItem]


class RerankResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    output: RerankOutput


class QwenRerankProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def rerank(self, query: str, texts: list[str]) -> list[tuple[int, float]]:
        if not texts:
            return []
        if not self.settings.dashscope_api_key.get_secret_value():
            raise ProcessingError("DOCUMENT_RERANK_AUTH_FAILED")
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.document_model_timeout_seconds, trust_env=False
            ) as http:
                response = await http.post(
                    str(self.settings.ai_rerank_url),
                    json={
                        "model": self.settings.document_rerank_model,
                        "input": {"query": query, "documents": texts},
                        "parameters": {"top_n": len(texts), "return_documents": False},
                    },
                    headers={
                        "Authorization": "Bearer "
                        + self.settings.dashscope_api_key.get_secret_value()
                    },
                )
                response.raise_for_status()
                data = RerankResponse.model_validate(response.json())
            results = [(item.index, item.relevance_score) for item in data.output.results]
            if len(results) != len(texts) or set(index for index, _ in results) != set(
                range(len(texts))
            ):
                raise ProcessingError("DOCUMENT_RERANK_RESPONSE_INVALID")
            return sorted(results, key=lambda item: (-item[1], item[0]))
        except ProcessingError:
            raise
        except Exception as exc:
            raise classify_upstream(exc, "DOCUMENT_RERANK") from None


class DeterministicProvider:
    """仅测试使用的词汇向量；不声称具备真实模型的同义词能力。"""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vector = [0.0] * 1024
            terms = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", text.lower())
            for term in terms or [text]:
                digest = hashlib.sha256(term.encode()).digest()
                vector[int.from_bytes(digest[:4], "big") % 1024] += 1
            norm = math.sqrt(sum(v * v for v in vector))
            vectors.append([v / norm for v in vector])
        return vectors

    async def rerank(self, query: str, texts: list[str]) -> list[tuple[int, float]]:
        query_vector = (await self.embed([query]))[0]
        vectors = await self.embed(texts)
        return sorted(
            [
                (i, sum(a * b for a, b in zip(query_vector, vector, strict=True)))
                for i, vector in enumerate(vectors)
            ],
            key=lambda item: (-item[1], item[0]),
        )


def model_providers(settings: Settings) -> tuple[EmbeddingProvider, RerankProvider]:
    if settings.document_provider == "deterministic":
        if settings.environment != "test":
            raise ProcessingError("DOCUMENT_PROVIDER_CONFIG_INVALID")
        provider = DeterministicProvider()
        return provider, provider
    return QwenEmbeddingProvider(settings), QwenRerankProvider(settings)
