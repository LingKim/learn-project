"""Explicit isolated synthetic four-format evaluation; never opens user source files."""

import argparse
import asyncio
import io
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

from docx import Document
from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy import delete, text

# Reuse the isolated storage fixture, not the application's business object storage.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from pydantic import TypeAdapter  # noqa: E402
from test_document_integration import seed  # noqa: E402

from xuemian_ai.accounts.models import User  # noqa: E402
from xuemian_ai.core.config import Settings, get_settings  # noqa: E402
from xuemian_ai.document_processing.models import BackgroundTask, VectorOperation  # noqa: E402
from xuemian_ai.document_processing.retrieval import RetrievalService  # noqa: E402
from xuemian_ai.document_processing.schemas import RetrievalRequest  # noqa: E402
from xuemian_ai.document_processing.vector_store import VectorStore  # noqa: E402
from xuemian_ai.file_management.models import FileAsset, StoredObject  # noqa: E402
from xuemian_ai.infrastructure.database import (  # noqa: E402
    create_database_engine,
    create_session_factory,
)
from xuemian_ai.practice.generation import QwenPracticeProvider, validate_questions
from xuemian_ai.practice.grading import validate_subjective_grade
from xuemian_ai.practice.schemas import (
    GradePayload,  # noqa: E402
    QuestionSnapshot,  # noqa: E402
)

FACTS = [
    "A transaction is a group of database operations.",
    "Atomicity means all operations succeed or all operations roll back.",
    "BEGIN starts a transaction. COMMIT commits it. ROLLBACK aborts it.",
    "Isolation separates concurrent transactions. Durability persists committed data.",
]


def native_pdf():
    writer = PdfWriter()
    page = writer.add_blank_page(width=650, height=400)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    stream = DecodedStreamObject()
    commands = "BT /F1 11 Tf 20 360 Td "
    commands += " 0 -25 Td ".join(f"({line}) Tj" for line in FACTS) + " ET"
    stream.set_data(commands.encode())
    page[NameObject("/Contents")] = writer._add_object(stream)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def scanned_pdf():
    image = Image.new("RGB", (1300, 450), "white")
    draw = ImageDraw.Draw(image)
    for i, line in enumerate(FACTS):
        draw.text((30, 40 + i * 65), line, fill="black", font_size=26)
    out = io.BytesIO()
    image.save(out, format="PDF")
    return out.getvalue()


def corpus():
    document = Document()
    for line in FACTS:
        document.add_paragraph(line)
    out = io.BytesIO()
    document.save(out)
    mixed = PdfWriter()
    for data in (native_pdf(), scanned_pdf()):
        mixed.add_page(PdfReader(io.BytesIO(data)).pages[0])
    mix = io.BytesIO()
    mixed.write(mix)
    return [
        ("synthetic.txt", "\n".join(FACTS).encode()),
        ("synthetic.md", ("# Transactions\n\n" + "\n\n".join(FACTS)).encode()),
        ("synthetic.docx", out.getvalue()),
        ("synthetic-native.pdf", native_pdf()),
        ("synthetic-scan.pdf", scanned_pdf()),
        ("synthetic-mixed.pdf", mix.getvalue()),
    ]


async def evaluate(env_file, output, qdrant_url=None):
    environment = json.loads(env_file.read_text())
    settings_keys = {field.upper() for field in Settings.model_fields}
    os.environ.update({key: value for key, value in environment.items() if key in settings_keys})
    get_settings.cache_clear()
    settings = get_settings().model_copy(update={"document_provider": "qwen"})
    if qdrant_url:
        settings = settings.model_copy(update={"qdrant_url": qdrant_url})
    expected_db = environment.get("PRACTICE_INTEGRATION_DB")
    if not expected_db or not expected_db.startswith("xuemian_practice_"):
        raise RuntimeError("explicit isolated practice database required")
    if not settings.qdrant_collection.startswith("xuemian-practice-e2e-"):
        raise RuntimeError("explicit unique synthetic collection required")
    engine = create_database_engine(settings.database_url.get_secret_value())
    sessions = create_session_factory(engine)
    async with engine.connect() as connection:
        if await connection.scalar(text("SELECT current_database()")) != expected_db:
            raise RuntimeError("isolated target mismatch")
    store = VectorStore(settings)
    try:
        await store.initialize()
    except Exception as exc:
        blocked = {
            "blocked": "vector_store_unavailable",
            "error_type": type(exc).__name__,
            "denominators": {"positive_files": 0, "negative_topics": 0},
        }
        output.write_text(json.dumps(blocked, ensure_ascii=False, indent=2))
        print(json.dumps(blocked))
        await store.close()
        await engine.dispose()
        return
    context = settings, sessions, store
    report = {"model": settings.learning_answer_model, "samples": [], "negative_samples": []}
    created_users = []
    created_objects = []
    last = None
    provider = QwenPracticeProvider(settings)
    try:
        for filename, content in corpus():
            sample = {
                "file": filename,
                "processing": False,
                "recall_at_5": None,
                "source_complete": False,
                "structure": False,
                "citations_locatable": False,
            }
            report["samples"].append(sample)
            try:
                (user, kb, binding, asset, task), worker = await seed(context, content)
                created_users.append(user.id)
                async with sessions.begin() as session:
                    file = await session.get(FileAsset, asset)
                    file.original_filename = filename
                    created_objects.append(file.stored_object_id)
                await worker.run_once()
                async with sessions() as session:
                    job = await session.get(BackgroundTask, task)
                    sample["processing"] = job.status == "succeeded"
                    if not sample["processing"]:
                        sample["error_key"] = job.last_error_code
                        continue
                result = await RetrievalService(
                    sessions, settings, user.id, str(uuid4()), store
                ).search(
                    kb,
                    RetrievalRequest(
                        query="What does transaction atomicity mean?", file_ids=[binding], top_n=5
                    ),
                )
                sample["recall_at_5"] = float(any(e.file_id == binding for e in result.evidence))
                sample["source_complete"] = bool(result.evidence) and all(
                    e.file_id == binding
                    and e.processing_version_id
                    and e.chunk_id
                    and (e.page_start is not None or e.paragraph_start is not None)
                    for e in result.evidence
                )
                config = dict(
                    source_mode="materials",
                    question_count=5,
                    question_types={
                        kind: 1
                        for kind in [
                            "single_choice",
                            "multiple_choice",
                            "true_false",
                            "short_answer",
                            "code_text",
                        ]
                    },
                    difficulty="medium",
                )
                raw = await provider.invoke(
                    "generate",
                    {
                        "config": config,
                        "effective_context": {},
                        "evidence": [
                            {"number": i + 1, "content": e.content}
                            for i, e in enumerate(result.evidence)
                        ],
                        "question_schema": TypeAdapter(QuestionSnapshot).json_schema(),
                    },
                )
                sample["synthetic_raw"] = raw
                last = result.evidence, config
                questions = validate_questions(
                    raw, config, result.evidence, {str(binding): str(asset)}
                )
                sample["structure"] = True
                sample["citations_locatable"] = all(q["source_refs"] for q in questions)
                sample["synthetic_questions"] = questions
                sample["retrieved_source_kinds"] = sorted({e.source_kind for e in result.evidence})
                subjective = next((q for q in questions if q["type"] == "short_answer"), None)
                if subjective and "grading" not in report:
                    answer = {"type": "short_answer", "text": "\n".join(subjective["answer"])}
                    try:
                        raw_grade = await provider.invoke(
                            "grade",
                            {
                                "question": subjective,
                                "answer": answer,
                                "grade_schema": GradePayload.model_json_schema(),
                            },
                        )
                        report["synthetic_grade"] = {
                            "question": subjective,
                            "answer": answer,
                            "raw": raw_grade,
                        }
                        graded = validate_subjective_grade(
                            raw_grade.get("grade", raw_grade), subjective, answer
                        )
                        report["grading"] = {
                            "passed": True,
                            "dimensions": len(graded.dimensions),
                            "confidence": graded.confidence,
                        }
                    except Exception as exc:
                        report["grading"] = {
                            "passed": False,
                            "error_key": getattr(exc, "error_key", None) or type(exc).__name__,
                        }
            except Exception as exc:
                sample["error_key"] = (
                    getattr(exc, "error_key", None)
                    or getattr(exc, "code", None)
                    or type(exc).__name__
                )
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        if last:
            evidence, config = last
            for topic in ["法国葡萄酒酿造参数", "海王星距离", "某公司2030年利润"]:
                sample = {"topic": topic, "correct_refusal": False}
                report["negative_samples"].append(sample)
                try:
                    raw = await provider.invoke(
                        "generate",
                        {
                            "config": dict(config, topic=topic),
                            "effective_context": {},
                            "evidence": [
                                {"number": i + 1, "content": e.content}
                                for i, e in enumerate(evidence)
                            ],
                            "question_schema": TypeAdapter(QuestionSnapshot).json_schema(),
                        },
                    )
                    sample["correct_refusal"] = (
                        raw.get("status") == "evidence_insufficient" and raw.get("questions") == []
                    )
                except Exception as exc:
                    sample["error_key"] = getattr(exc, "error_key", None) or type(exc).__name__
        report["denominators"] = {
            "positive_files": len(report["samples"]),
            "negative_topics": len(report["negative_samples"]),
        }
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(
            json.dumps(
                {
                    "denominators": report["denominators"],
                    "processing_pass": sum(s["processing"] for s in report["samples"]),
                    "structure_pass": sum(s["structure"] for s in report["samples"]),
                    "source_complete_pass": sum(s["source_complete"] for s in report["samples"]),
                    "refusal_pass": sum(s["correct_refusal"] for s in report["negative_samples"]),
                },
                ensure_ascii=False,
            )
        )
    finally:
        async with sessions.begin() as session:
            await session.execute(
                delete(VectorOperation).where(VectorOperation.user_id.in_(created_users))
            )
            await session.execute(delete(User).where(User.id.in_(created_users)))
            await session.execute(delete(StoredObject).where(StoredObject.id.in_(created_objects)))
        await store.client.delete_collection(store.collection)
        await store.close()
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--qdrant-url")
    args = parser.parse_args()
    try:
        asyncio.run(evaluate(args.env_file, args.output, args.qdrant_url))
    except Exception as exc:
        print(json.dumps({"runner_failed": type(exc).__name__}))
        raise SystemExit(1) from None
