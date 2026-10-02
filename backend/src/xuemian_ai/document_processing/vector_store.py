"""Qdrant SDK 只在基础设施适配器内部使用。"""

from collections.abc import Sequence
from uuid import UUID

from qdrant_client import AsyncQdrantClient, models

from xuemian_ai.core.config import Settings
from xuemian_ai.document_processing.parsers import ProcessingError


class VectorStore:
    def __init__(self, settings: Settings, client: AsyncQdrantClient | None = None) -> None:
        self._test_local = client is not None and settings.environment == "test"
        self.collection = settings.qdrant_collection
        self.client = client or AsyncQdrantClient(
            url=str(settings.qdrant_url),
            api_key=settings.qdrant_api_key.get_secret_value() or None,
            timeout=max(1, int(settings.qdrant_timeout_seconds)),
            check_compatibility=False,
            trust_env=False,
        )

    async def close(self) -> None:
        await self.client.close()

    async def initialize(self) -> None:
        # 仅显式 CLI 或隔离测试调用；已存在的不兼容 collection 绝不自动覆盖。
        if not await self.client.collection_exists(self.collection):
            await self.client.create_collection(
                self.collection,
                vectors_config={
                    "dense": models.VectorParams(size=1024, distance=models.Distance.COSINE)
                },
            )
            await self.client.create_payload_index(
                self.collection,
                "user_id",
                field_schema=models.KeywordIndexParams(
                    type=models.KeywordIndexType.KEYWORD, is_tenant=True
                ),
                wait=True,
            )
            for key in ("file_asset_id", "processing_version_id"):
                await self.client.create_payload_index(
                    self.collection, key, field_schema=models.PayloadSchemaType.UUID, wait=True
                )
        await self.check_schema()

    async def check_schema(self) -> None:
        try:
            info = await self.client.get_collection(self.collection)
            vectors = info.config.params.vectors
            if (
                not isinstance(vectors, dict)
                or "dense" not in vectors
                or vectors["dense"].size != 1024
                or vectors["dense"].distance != models.Distance.COSINE
            ):
                raise ProcessingError("DOCUMENT_VECTOR_SCHEMA_INCOMPATIBLE")
            # Local Qdrant 测试实现不维护 payload 索引，不用于服务 schema 验收。
            if not self._test_local:
                expected = {
                    "user_id": models.PayloadSchemaType.KEYWORD,
                    "file_asset_id": models.PayloadSchemaType.UUID,
                    "processing_version_id": models.PayloadSchemaType.UUID,
                }
                if any(
                    key not in info.payload_schema or info.payload_schema[key].data_type != kind
                    for key, kind in expected.items()
                ):
                    raise ProcessingError("DOCUMENT_VECTOR_SCHEMA_INCOMPATIBLE")
        except ProcessingError:
            raise
        except Exception:
            raise ProcessingError("DOCUMENT_VECTOR_UNAVAILABLE", retryable=True) from None

    @staticmethod
    def scope(
        user_id: UUID, version_ids: Sequence[UUID], file_asset_id: UUID | None = None
    ) -> models.Filter:
        must: list[
            models.FieldCondition
            | models.IsEmptyCondition
            | models.IsNullCondition
            | models.HasIdCondition
            | models.HasVectorCondition
            | models.NestedCondition
            | models.Filter
        ] = [
            models.FieldCondition(key="user_id", match=models.MatchValue(value=str(user_id))),
            models.FieldCondition(
                key="processing_version_id",
                match=models.MatchAny(any=[str(value) for value in version_ids]),
            ),
        ]
        if file_asset_id is not None:
            must.append(
                models.FieldCondition(
                    key="file_asset_id", match=models.MatchValue(value=str(file_asset_id))
                )
            )
        return models.Filter(must=must)

    async def upsert(
        self,
        user_id: UUID,
        file_asset_id: UUID,
        version_id: UUID,
        points: list[tuple[UUID, list[float]]],
    ) -> None:
        try:
            await self.client.upsert(
                self.collection,
                points=[
                    models.PointStruct(
                        id=str(chunk_id),
                        vector={"dense": vector},
                        payload={
                            "user_id": str(user_id),
                            "file_asset_id": str(file_asset_id),
                            "processing_version_id": str(version_id),
                            "chunk_id": str(chunk_id),
                            "schema_version": "v1",
                        },
                    )
                    for chunk_id, vector in points
                ],
                wait=True,
            )
        except Exception:
            raise ProcessingError("DOCUMENT_VECTOR_UNAVAILABLE", retryable=True) from None

    async def count(self, user_id: UUID, file_asset_id: UUID, version_id: UUID) -> int:
        try:
            return (
                await self.client.count(
                    self.collection,
                    count_filter=self.scope(user_id, [version_id], file_asset_id),
                    exact=True,
                )
            ).count
        except Exception:
            raise ProcessingError("DOCUMENT_VECTOR_UNAVAILABLE", retryable=True) from None

    async def search(
        self, user_id: UUID, versions: Sequence[UUID], vector: list[float], limit: int
    ) -> list[tuple[UUID, float]]:
        if not versions:
            return []
        try:
            response = await self.client.query_points(
                self.collection,
                query=vector,
                using="dense",
                query_filter=self.scope(user_id, versions),
                limit=limit,
                with_payload=False,
                with_vectors=False,
            )
            return [(UUID(str(point.id)), point.score) for point in response.points]
        except Exception:
            raise ProcessingError("DOCUMENT_VECTOR_UNAVAILABLE", retryable=True) from None

    async def delete_version(self, user_id: UUID, file_asset_id: UUID, version_id: UUID) -> None:
        try:
            await self.client.delete(
                self.collection,
                points_selector=models.FilterSelector(
                    filter=self.scope(user_id, [version_id], file_asset_id)
                ),
                wait=True,
            )
        except Exception:
            raise ProcessingError("DOCUMENT_VECTOR_UNAVAILABLE", retryable=True) from None

    async def version_point_ids(
        self, user_id: UUID, asset_id: UUID, version_id: UUID, maximum: int
    ) -> set[UUID]:
        """有界枚举版本点，只取 ID，不读正文或向量。"""
        ids: set[UUID] = set()
        offset = None
        try:
            while True:
                points, offset = await self.client.scroll(
                    self.collection,
                    scroll_filter=self.scope(user_id, [version_id], asset_id),
                    limit=256,
                    offset=offset,
                    with_payload=False,
                    with_vectors=False,
                )
                ids.update(UUID(str(point.id)) for point in points)
                if len(ids) > maximum:
                    raise ProcessingError("DOCUMENT_VECTOR_COUNT_INVALID")
                if offset is None:
                    return ids
        except ProcessingError:
            raise
        except Exception:
            raise ProcessingError("DOCUMENT_VECTOR_UNAVAILABLE", retryable=True) from None

    async def delete_points(
        self, user_id: UUID, asset_id: UUID, version_id: UUID, ids: set[UUID]
    ) -> None:
        if not ids:
            return
        scope = self.scope(user_id, [version_id], asset_id)
        assert isinstance(scope.must, list)
        scope.must.append(models.HasIdCondition(has_id=[str(point) for point in ids]))
        try:
            await self.client.delete(
                self.collection, points_selector=models.FilterSelector(filter=scope), wait=True
            )
        except Exception:
            raise ProcessingError("DOCUMENT_VECTOR_UNAVAILABLE", retryable=True) from None
