import asyncio

from xuemian_ai.core.config import get_settings
from xuemian_ai.document_processing.vector_store import VectorStore


async def initialize() -> None:
    store = VectorStore(get_settings())
    try:
        await store.initialize()
        print("Qdrant collection 与 payload schema 已校验")
    finally:
        await store.close()


def run() -> None:
    asyncio.run(initialize())
