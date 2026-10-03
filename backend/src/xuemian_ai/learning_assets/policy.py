"""Versioned deterministic evidence policy; confidence is never a mastery probability."""

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

POLICY_VERSION = "practice_weakness_v1"


def concept_key(title: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", title).casefold().split())


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":")
        ).encode()
    ).hexdigest()


def scope_key(config: dict[str, Any]) -> str:
    return fingerprint(
        {
            "mode": config.get("source_mode", "general"),
            "kb": str(config.get("knowledge_base_id") or ""),
            "files": sorted({str(item) for item in config.get("file_ids", [])}) or "all",
        }
    )


@dataclass(frozen=True)
class Observation:
    question_id: UUID
    attempt_id: UUID
    submitted_at: datetime
    level: str
    difficulty: str
    single_topic: bool
    low_confidence: bool
    available: bool = True
    ignored: bool = False


def automatic_confirmation(observations: list[Observation], now: datetime) -> bool:
    # Each immutable question contributes once, ordered by answer time, never regrade time.
    latest: dict[UUID, Observation] = {}
    for item in observations:
        previous = latest.get(item.question_id)
        if previous is None or item.submitted_at > previous.submitted_at:
            latest[item.question_id] = item
    valid = sorted(
        (
            item
            for item in latest.values()
            if item.available
            and not item.ignored
            and item.single_topic
            and not item.low_confidence
            and now - timedelta(days=30) <= item.submitted_at <= now
        ),
        key=lambda item: (item.submitted_at, str(item.question_id)),
    )
    wrong = [
        item
        for item in valid
        if item.level in {"incorrect", "partial"} and item.difficulty in {"medium", "hard"}
    ]
    return (
        len(wrong) >= 3
        and len({item.attempt_id for item in wrong}) >= 2
        and len(valid) >= 2
        and all(item.level in {"incorrect", "partial"} for item in valid[-2:])
    )


def review_conclusion(
    total: int,
    submitted: int,
    graded: int,
    correct: int,
    low: int,
    completed: bool,
    available: bool,
) -> tuple[bool, str]:
    if not available:
        return False, "source_unavailable"
    if not completed:
        return False, "in_progress"
    if total < 3:
        return False, "insufficient_sample"
    if submitted != total or graded != total:
        return False, "incomplete_evidence"
    if low:
        return False, "low_confidence"
    if correct == total:
        return True, "validation_passed"
    return False, "needs_learning"
