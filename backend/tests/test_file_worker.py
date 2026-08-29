from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from xuemian_ai.file_management.models import FileCleanupTask, FileDeletionTombstone, StoredObject
from xuemian_ai.file_management.worker import FileScheduler, FileTaskWorker


def _stored_object(*, reference_count: int, status: str = "deleting") -> StoredObject:
    return StoredObject(
        id=uuid4(),
        storage_domain="documents",
        sha256="a" * 64,
        byte_size=10,
        detected_mime="text/plain",
        bucket="documents",
        object_key=f"sha256/aa/{uuid4()}",
        status=status,
        reference_count=reference_count,
    )


async def test_reference_count_drift_stops_delete_and_enqueues_repair() -> None:
    worker = object.__new__(FileTaskWorker)
    worker._storage = AsyncMock()  # type: ignore[attr-defined]
    stored = _stored_object(reference_count=2)
    session = AsyncMock()
    session.add = MagicMock()
    session.scalar.side_effect = [stored, 0, None]

    await worker._delete_stored_object(session, stored.id)

    worker._storage.delete_object.assert_not_awaited()  # type: ignore[attr-defined]
    assert stored.status == "available"
    task = session.add.call_args.args[0]
    assert isinstance(task, FileCleanupTask)
    assert task.task_type == "repair_reference_count"


async def test_reference_repair_reschedules_safe_physical_delete() -> None:
    worker = object.__new__(FileTaskWorker)
    worker._storage = AsyncMock()  # type: ignore[attr-defined]
    stored = _stored_object(reference_count=9, status="available")
    session = AsyncMock()
    session.add = MagicMock()
    session.scalar.side_effect = [stored, 0, None]

    await worker._repair_reference_count(session, stored.id)

    assert stored.reference_count == 0
    assert stored.status == "deleting"
    task = session.add.call_args.args[0]
    assert isinstance(task, FileCleanupTask)
    assert task.task_type == "delete_stored_object"


async def test_last_reference_delete_writes_tombstone() -> None:
    worker = object.__new__(FileTaskWorker)
    worker._storage = AsyncMock()  # type: ignore[attr-defined]
    stored = _stored_object(reference_count=0)
    session = AsyncMock()
    session.add = MagicMock()
    session.scalar.side_effect = [stored, 0, None]

    await worker._delete_stored_object(session, stored.id)

    worker._storage.delete_object.assert_awaited_once_with(  # type: ignore[attr-defined]
        stored.bucket, stored.object_key
    )
    assert stored.status == "deleted"
    assert stored.cleared_at is not None
    tombstone = next(
        call.args[0]
        for call in session.add.call_args_list
        if isinstance(call.args[0], FileDeletionTombstone)
    )
    assert isinstance(tombstone, FileDeletionTombstone)
    assert tombstone.stored_object_id == stored.id


async def test_daily_retention_issues_only_technical_metadata_deletes() -> None:
    scheduler = object.__new__(FileScheduler)
    session = AsyncMock()

    await scheduler._purge_expired_metadata(session, datetime.now(UTC))

    assert session.execute.await_count == 4
