import asyncio
import socket
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from xuemian_ai.core.config import Settings, get_settings
from xuemian_ai.core.logging import configure_logging, get_logger
from xuemian_ai.file_management.models import (
    FileAsset,
    FileAuditEvent,
    FileCleanupTask,
    FileDeletionTombstone,
    FileOrphanCandidate,
    StoredObject,
    UploadSession,
)
from xuemian_ai.file_management.service import verify_upload_task
from xuemian_ai.file_management.storage import ObjectStorage
from xuemian_ai.infrastructure.database import create_database_engine, create_session_factory

_logger = get_logger(__name__)


class FileTaskWorker:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._engine = create_database_engine(settings.database_url.get_secret_value())
        self._sessions = create_session_factory(self._engine)
        self._storage = ObjectStorage(settings)
        self._worker_id = f"{socket.gethostname()}:{id(self)}"

    async def close(self) -> None:
        await self._engine.dispose()

    async def run_forever(self) -> None:
        while True:
            worked = await self.run_once()
            if not worked:
                await asyncio.sleep(self._settings.file_worker_poll_seconds)

    async def run_once(self) -> bool:
        task_id = await self._claim_task()
        if task_id is None:
            return False
        try:
            async with self._sessions() as session, session.begin():
                task = await session.get(FileCleanupTask, task_id)
                if task is None:
                    return True
                await self._execute(session, task)
                task.status = "succeeded"
                task.locked_by = None
                task.locked_until = None
                task.last_error_code = None
        except Exception as exc:
            await self._record_failure(task_id, type(exc).__name__)
            _logger.warning(
                "file_task_failed",
                task_id=str(task_id),
                exception_type=type(exc).__name__,
            )
        return True

    async def _claim_task(self) -> UUID | None:
        now = datetime.now(UTC)
        async with self._sessions() as session, session.begin():
            task = cast(
                FileCleanupTask | None,
                await session.scalar(
                    select(FileCleanupTask)
                    .where(
                        FileCleanupTask.next_attempt_at <= now,
                        or_(
                            FileCleanupTask.status == "pending",
                            (
                                (FileCleanupTask.status == "processing")
                                & (FileCleanupTask.locked_until < now)
                            ),
                        ),
                    )
                    .order_by(FileCleanupTask.priority.asc(), FileCleanupTask.next_attempt_at.asc())
                    .with_for_update(skip_locked=True)
                    .limit(1)
                ),
            )
            if task is None:
                return None
            task.status = "processing"
            task.attempt_count += 1
            task.locked_by = self._worker_id
            task.locked_until = now + timedelta(seconds=self._settings.file_worker_lease_seconds)
            return task.id

    async def _execute(self, session: AsyncSession, task: FileCleanupTask) -> None:
        if task.task_type == "verify_upload":
            upload_id = UUID(str(task.payload["upload_session_id"]))
            await verify_upload_task(session, self._storage, self._settings, upload_id)
            return
        if task.task_type == "delete_temporary_object":
            bucket = str(task.payload["bucket"])
            key = str(task.payload["object_key"])
            multipart_upload_id = task.payload.get("multipart_upload_id")
            if multipart_upload_id:
                await self._storage.abort_multipart(bucket, key, str(multipart_upload_id))
            await self._storage.delete_object(bucket, key)
            return
        if task.task_type == "delete_stored_object":
            await self._delete_stored_object(session, UUID(str(task.payload["stored_object_id"])))
            return
        if task.task_type == "repair_reference_count":
            await self._repair_reference_count(session, UUID(str(task.payload["stored_object_id"])))
            return
        if task.task_type == "delete_orphan_object":
            await self._storage.delete_object(
                str(task.payload["bucket"]), str(task.payload["object_key"])
            )
            session.add(
                FileAuditEvent(
                    actor_user_id=None,
                    action="physical_delete_orphan",
                    target_type="orphan_object",
                    target_id=task.target_id,
                    outcome="success",
                    occurred_at=datetime.now(UTC),
                )
            )
            return
        raise ValueError("FILE_TASK_TYPE_UNKNOWN")

    async def _delete_stored_object(self, session: AsyncSession, stored_id: UUID) -> None:
        stored = cast(
            StoredObject | None,
            await session.scalar(
                select(StoredObject).where(StoredObject.id == stored_id).with_for_update()
            ),
        )
        if stored is None or stored.status == "deleted":
            return
        active_refs = int(
            await session.scalar(
                select(func.count()).where(
                    FileAsset.stored_object_id == stored.id,
                    FileAsset.deleted_at.is_(None),
                )
            )
            or 0
        )
        if stored.reference_count != active_refs:
            stored.status = "available"
            await self._insert_task_if_missing(
                session,
                task_type="repair_reference_count",
                target_type="stored_object",
                target_id=stored.id,
                payload={"stored_object_id": str(stored.id)},
                idempotency_key=(
                    f"repair-reference-count:{stored.id}:{stored.generation}:{active_refs}"
                ),
                max_attempts=3,
                priority=1,
            )
            return
        if active_refs > 0:
            stored.status = "available"
            return
        await self._storage.delete_object(stored.bucket, stored.object_key)
        stored.status = "deleted"
        stored.cleared_at = datetime.now(UTC)
        await self._insert_tombstone_if_missing(session, stored)
        session.add(
            FileAuditEvent(
                actor_user_id=None,
                action="physical_delete",
                target_type="stored_object",
                target_id=stored.id,
                outcome="success",
                occurred_at=stored.cleared_at,
            )
        )

    async def _repair_reference_count(self, session: AsyncSession, stored_id: UUID) -> None:
        stored = cast(
            StoredObject | None,
            await session.scalar(
                select(StoredObject).where(StoredObject.id == stored_id).with_for_update()
            ),
        )
        if stored is None or stored.status == "deleted":
            return
        active_refs = int(
            await session.scalar(
                select(func.count()).where(
                    FileAsset.stored_object_id == stored.id,
                    FileAsset.deleted_at.is_(None),
                )
            )
            or 0
        )
        stored.reference_count = active_refs
        if active_refs > 0:
            stored.status = "available"
            return
        stored.status = "deleting"
        await self._insert_task_if_missing(
            session,
            task_type="delete_stored_object",
            target_type="stored_object",
            target_id=stored.id,
            payload={"stored_object_id": str(stored.id)},
            idempotency_key=(f"delete-stored-object-after-repair:{stored.id}:{stored.generation}"),
            max_attempts=8,
            priority=5,
        )

    async def _insert_tombstone_if_missing(
        self, session: AsyncSession, stored: StoredObject
    ) -> None:
        tombstone = cast(
            FileDeletionTombstone | None,
            await session.scalar(
                select(FileDeletionTombstone).where(
                    FileDeletionTombstone.stored_object_id == stored.id
                )
            ),
        )
        deleted_at = stored.cleared_at or datetime.now(UTC)
        if tombstone is None:
            session.add(
                FileDeletionTombstone(
                    stored_object_id=stored.id,
                    storage_domain=stored.storage_domain,
                    bucket=stored.bucket,
                    object_key=stored.object_key,
                    reason="last_reference_deleted",
                    deleted_at=deleted_at,
                )
            )
            return
        tombstone.storage_domain = stored.storage_domain
        tombstone.bucket = stored.bucket
        tombstone.object_key = stored.object_key
        tombstone.reason = "last_reference_deleted"
        tombstone.deleted_at = deleted_at

    async def _insert_task_if_missing(
        self,
        session: AsyncSession,
        *,
        task_type: str,
        target_type: str,
        target_id: UUID,
        payload: dict[str, object],
        idempotency_key: str,
        max_attempts: int,
        priority: int,
    ) -> None:
        exists = await session.scalar(
            select(FileCleanupTask.id).where(FileCleanupTask.idempotency_key == idempotency_key)
        )
        if exists is None:
            session.add(
                FileCleanupTask(
                    task_type=task_type,
                    target_type=target_type,
                    target_id=target_id,
                    payload=payload,
                    priority=priority,
                    status="pending",
                    attempt_count=0,
                    max_attempts=max_attempts,
                    next_attempt_at=datetime.now(UTC),
                    idempotency_key=idempotency_key,
                )
            )

    async def _record_failure(self, task_id: UUID, error_code: str) -> None:
        async with self._sessions() as session, session.begin():
            task = await session.get(FileCleanupTask, task_id)
            if task is None:
                return
            task.last_error_code = error_code[:64]
            task.locked_by = None
            task.locked_until = None
            if task.attempt_count >= task.max_attempts:
                task.status = "failed"
                return
            delays = [60, 300, 900, 3600, 10_800, 21_600, 43_200, 86_400]
            delay = delays[min(task.attempt_count - 1, len(delays) - 1)]
            task.status = "pending"
            task.next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay)


class FileScheduler:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._engine = create_database_engine(settings.database_url.get_secret_value())
        self._sessions = create_session_factory(self._engine)
        self._storage = ObjectStorage(settings)

    async def close(self) -> None:
        await self._engine.dispose()

    async def run_forever(self) -> None:
        await self.run_daily()
        local_now = datetime.now(UTC) + timedelta(hours=8)
        if local_now.weekday() == 6 and (local_now.hour, local_now.minute) >= (3, 30):
            await self.run_reconciliation()
        while True:
            now = datetime.now(UTC)
            local = now + timedelta(hours=8)
            target = local.replace(hour=2, minute=30, second=0, microsecond=0)
            if target <= local:
                target += timedelta(days=1)
            await asyncio.sleep((target - local).total_seconds())
            await self.run_daily()
            if target.weekday() == 6:
                await asyncio.sleep(3600)
                await self.run_reconciliation()

    async def run_daily(self) -> None:
        async with self._sessions() as session, session.begin():
            locked = await session.scalar(text("SELECT pg_try_advisory_xact_lock(867530901)"))
            if not locked:
                return
            now = datetime.now(UTC)
            uploads = list(
                (
                    await session.scalars(
                        select(UploadSession).where(
                            UploadSession.expires_at <= now,
                            UploadSession.status.in_(
                                ("created", "uploading", "uploaded", "verifying")
                            ),
                        )
                    )
                ).all()
            )
            for upload in uploads:
                upload.status = "expired"
                if not upload.temporary_object_key:
                    continue
                await self._insert_task_if_missing(
                    session,
                    task_type="delete_temporary_object",
                    target_type="upload_session",
                    target_id=upload.id,
                    payload={
                        "bucket": self._settings.rustfs_quarantine_bucket,
                        "object_key": upload.temporary_object_key,
                        "multipart_upload_id": upload.multipart_upload_id,
                    },
                    idempotency_key=f"delete-temp:{upload.id}",
                    max_attempts=8,
                    priority=100,
                )
            await self._purge_expired_metadata(session, now)

    async def run_reconciliation(self) -> None:
        async with self._sessions() as session, session.begin():
            locked = await session.scalar(text("SELECT pg_try_advisory_xact_lock(867530902)"))
            if not locked:
                return
            for bucket in self._settings.rustfs_buckets:
                token = None
                scanned = 0
                while scanned < self._settings.file_cleanup_batch_size:
                    keys, token = await self._storage.list_objects(
                        bucket,
                        token,
                        min(1000, self._settings.file_cleanup_batch_size - scanned),
                    )
                    for key in keys:
                        scanned += 1
                        known = await session.scalar(
                            select(StoredObject.id).where(
                                StoredObject.bucket == bucket,
                                StoredObject.object_key == key,
                                StoredObject.status != "deleted",
                            )
                        )
                        if known is None and not key.startswith("uploads/"):
                            await self._record_orphan(session, bucket, key)
                    if token is None:
                        break
                stored_objects = list(
                    (
                        await session.scalars(
                            select(StoredObject)
                            .where(
                                StoredObject.bucket == bucket,
                                StoredObject.status.in_(("available", "deleting")),
                            )
                            .limit(self._settings.file_cleanup_batch_size)
                        )
                    ).all()
                )
                for stored in stored_objects:
                    if not await self._storage.object_exists(bucket, stored.object_key):
                        stored.status = "missing"

    async def _purge_expired_metadata(self, session: AsyncSession, now: datetime) -> None:
        ninety_days_ago = now - timedelta(days=90)
        one_eighty_days_ago = now - timedelta(days=180)
        await session.execute(
            delete(UploadSession).where(
                UploadSession.status.in_(("completed", "cancelled", "expired", "failed")),
                UploadSession.updated_at < ninety_days_ago,
            )
        )
        await session.execute(
            delete(FileCleanupTask).where(
                FileCleanupTask.status == "succeeded",
                FileCleanupTask.updated_at < ninety_days_ago,
            )
        )
        await session.execute(
            delete(FileCleanupTask).where(
                FileCleanupTask.status.in_(("failed", "cancelled")),
                FileCleanupTask.updated_at < one_eighty_days_ago,
            )
        )
        await session.execute(
            delete(FileAuditEvent).where(FileAuditEvent.occurred_at < one_eighty_days_ago)
        )

    async def _record_orphan(self, session: AsyncSession, bucket: str, key: str) -> None:
        now = datetime.now(UTC)
        candidate = cast(
            FileOrphanCandidate | None,
            await session.scalar(
                select(FileOrphanCandidate).where(
                    FileOrphanCandidate.bucket == bucket,
                    FileOrphanCandidate.object_key == key,
                )
            ),
        )
        if candidate is None:
            session.add(
                FileOrphanCandidate(
                    bucket=bucket,
                    object_key=key,
                    first_seen_at=now,
                    last_seen_at=now,
                    confirmation_count=1,
                    delete_enqueued=False,
                )
            )
            return
        candidate.last_seen_at = now
        candidate.confirmation_count += 1
        if (
            candidate.confirmation_count >= 2
            and candidate.first_seen_at <= now - timedelta(days=7)
            and not candidate.delete_enqueued
        ):
            await self._insert_task_if_missing(
                session,
                task_type="delete_orphan_object",
                target_type="orphan_object",
                target_id=candidate.id,
                payload={"bucket": bucket, "object_key": key},
                idempotency_key=f"delete-orphan:{candidate.id}",
                max_attempts=8,
                priority=200,
            )
            candidate.delete_enqueued = True

    async def _insert_task_if_missing(
        self,
        session: AsyncSession,
        *,
        task_type: str,
        target_type: str,
        target_id: UUID,
        payload: dict[str, object],
        idempotency_key: str,
        max_attempts: int,
        priority: int,
    ) -> None:
        exists = await session.scalar(
            select(FileCleanupTask.id).where(FileCleanupTask.idempotency_key == idempotency_key)
        )
        if exists is None:
            session.add(
                FileCleanupTask(
                    task_type=task_type,
                    target_type=target_type,
                    target_id=target_id,
                    payload=payload,
                    priority=priority,
                    status="pending",
                    attempt_count=0,
                    max_attempts=max_attempts,
                    next_attempt_at=datetime.now(UTC),
                    idempotency_key=idempotency_key,
                )
            )


async def _run_worker() -> None:
    settings = get_settings()
    configure_logging(settings)
    worker = FileTaskWorker(settings)
    try:
        await worker.run_forever()
    finally:
        await worker.close()


async def _run_scheduler() -> None:
    settings = get_settings()
    configure_logging(settings)
    scheduler = FileScheduler(settings)
    try:
        await scheduler.run_forever()
    finally:
        await scheduler.close()


def run_worker() -> None:
    try:
        asyncio.run(_run_worker())
    except KeyboardInterrupt:
        return


def run_scheduler() -> None:
    try:
        asyncio.run(_run_scheduler())
    except KeyboardInterrupt:
        return
