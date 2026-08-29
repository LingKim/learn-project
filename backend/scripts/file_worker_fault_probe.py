import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from xuemian_ai.core.config import get_settings
from xuemian_ai.file_management.models import FileCleanupTask
from xuemian_ai.file_management.worker import FileTaskWorker
from xuemian_ai.infrastructure.database import create_database_engine, create_session_factory


async def run_probe() -> None:
    settings = get_settings()
    engine = create_database_engine(settings.database_url.get_secret_value())
    sessions = create_session_factory(engine)
    task_id = uuid4()
    try:
        async with sessions() as session, session.begin():
            session.add(
                FileCleanupTask(
                    id=task_id,
                    task_type="delete_temporary_object",
                    target_type="upload_session",
                    target_id=None,
                    payload={
                        "bucket": settings.rustfs_quarantine_bucket,
                        "object_key": f"fault-smoke/{uuid4()}",
                    },
                    priority=100,
                    status="pending",
                    attempt_count=0,
                    max_attempts=3,
                    next_attempt_at=datetime.now(UTC),
                    idempotency_key=f"fault-smoke:{task_id}",
                )
            )

        bad_settings = settings.model_copy(
            update={"rustfs_internal_endpoint": "http://127.0.0.1:1"}
        )
        failed_worker = FileTaskWorker(bad_settings)
        try:
            assert await failed_worker.run_once()
        finally:
            await failed_worker.close()

        async with sessions() as session, session.begin():
            task = await session.get(FileCleanupTask, task_id)
            assert task is not None
            assert task.status == "pending"
            assert task.attempt_count == 1
            assert task.last_error_code == "EndpointConnectionError"
            task.next_attempt_at = datetime.now(UTC)
            print("fault_result=pending|1|EndpointConnectionError")

        recovered_worker = FileTaskWorker(settings)
        try:
            assert await recovered_worker.run_once()
        finally:
            await recovered_worker.close()

        async with sessions() as session:
            task = await session.get(FileCleanupTask, task_id)
            assert task is not None
            assert task.status == "succeeded"
            assert task.attempt_count == 2
            assert task.last_error_code is None
            print("recovery_result=succeeded|2")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_probe())
