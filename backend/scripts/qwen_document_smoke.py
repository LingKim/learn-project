"""真实模型验证仅发送脚本内生成的合成文字图片；输出不含正文或 Key。"""

import argparse
import asyncio
import io
from time import monotonic

from PIL import Image, ImageDraw

from xuemian_ai.core.config import get_settings
from xuemian_ai.document_processing.parsers import ProcessingError
from xuemian_ai.document_processing.providers import (
    QwenEmbeddingProvider,
    QwenOcrProvider,
    QwenRerankProvider,
)


async def smoke() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-ocr", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    image = Image.new("RGB", (1000, 300), "white")
    ImageDraw.Draw(image).text(
        (40, 80), "PostgreSQL transactions prevent dirty reads.", fill="black", font_size=40
    )
    output = io.BytesIO()
    image.save(output, format="PNG")
    start = monotonic()
    try:
        if not args.skip_ocr:
            ocr = await QwenOcrProvider(settings).recognize(output.getvalue())
            assert "postgresql" in ocr.text.lower(), "OCR_SYNTHETIC_EXPECTATION_FAILED"
            print(
                {
                    "stage": "ocr",
                    "model": settings.document_ocr_model,
                    "status": "passed",
                    "elapsed_ms": round((monotonic() - start) * 1000),
                    "confidence_available": ocr.confidence is not None,
                }
            )
        vectors = await QwenEmbeddingProvider(settings).embed(
            ["PostgreSQL transactions prevent dirty reads.", "Bread is baked in an oven."]
        )
        print(
            {
                "stage": "embedding",
                "model": settings.document_embedding_model,
                "status": "passed",
                "vectors": len(vectors),
                "dimensions": len(vectors[0]),
            }
        )
        ranked = await QwenRerankProvider(settings).rerank(
            "How do transactions prevent dirty reads?",
            ["PostgreSQL transactions prevent dirty reads.", "Bread is baked in an oven."],
        )
        assert ranked[0][0] == 0, "RERANK_SYNTHETIC_EXPECTATION_FAILED"
        print(
            {
                "stage": "rerank",
                "model": settings.document_rerank_model,
                "status": "passed",
                "items": len(ranked),
            }
        )
    except ProcessingError as exc:
        print({"status": "failed", "error_key": exc.code, "retryable": exc.retryable})
        raise SystemExit(1) from None


if __name__ == "__main__":
    asyncio.run(smoke())
