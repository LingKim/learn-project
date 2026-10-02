import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from pathlib import PurePath
from typing import Literal, cast
from uuid import UUID, uuid4

from redis.asyncio import Redis
from sqlalchemy import and_, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from xuemian_ai.accounts.models import User
from xuemian_ai.core.config import Settings
from xuemian_ai.core.errors import (
    ConflictError,
    NotFoundError,
    PayloadTooLargeError,
    TooManyRequestsError,
    UpstreamServiceError,
    ValidationAppError,
)
from xuemian_ai.core.status_codes import ApiStatusCode
from xuemian_ai.document_processing.service import enqueue_processing, revoke_processing
from xuemian_ai.file_management.models import (
    FileAsset,
    FileAuditEvent,
    FileCleanupTask,
    KnowledgeBaseFile,
    StoredObject,
    UploadSession,
)
from xuemian_ai.file_management.policy import FilePolicyService, knowledge_rules
from xuemian_ai.file_management.schemas import (
    DeleteResult,
    DeletionImpactView,
    DownloadUrlView,
    KnowledgeFileView,
    SignedPart,
    UploadPlan,
    UploadSessionCreate,
    UploadSessionView,
)
from xuemian_ai.file_management.storage import ObjectStorage
from xuemian_ai.file_management.validation import validate_content, validate_declared_file
from xuemian_ai.knowledge_bases.models import KnowledgeBase

_ACTIVE_UPLOAD_STATUSES = {"created", "uploading", "uploaded", "verifying"}
_PART_SIZE = 16 * 1024 * 1024
_MULTIPART_THRESHOLD = 20 * 1024 * 1024


class FileManagementService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        redis: Redis,
        storage: ObjectStorage,
        settings: Settings,
        user: User,
        request_id: str | None = None,
        ip_address: str | None = None,
    ) -> None:
        self._session = session
        self._redis = redis
        self._storage = storage
        self._settings = settings
        self._user = user
        self._request_id = request_id
        self._ip_hash = self._fingerprint(ip_address)

    async def list_knowledge_bases(
        self, page: int, page_size: int
    ) -> tuple[list[KnowledgeBase], int]:
        predicate = and_(
            KnowledgeBase.owner_user_id == self._user.id,
            KnowledgeBase.deleted_at.is_(None),
        )
        total = int(await self._session.scalar(select(func.count()).where(predicate)) or 0)
        items = list(
            (
                await self._session.scalars(
                    select(KnowledgeBase)
                    .where(predicate)
                    .order_by(KnowledgeBase.created_at.asc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
        )
        return items, total

    async def create_knowledge_base(self, name: str) -> KnowledgeBase:
        existing = await self._session.scalar(
            select(KnowledgeBase.id).where(
                KnowledgeBase.owner_user_id == self._user.id,
                KnowledgeBase.name == name,
                KnowledgeBase.deleted_at.is_(None),
            )
        )
        if existing is not None:
            raise ConflictError("知识库名称已存在", error_key="KNOWLEDGE_BASE_NAME_EXISTS")
        knowledge_base = KnowledgeBase(
            owner_user_id=self._user.id,
            name=name,
            is_default=False,
            created_by=self._user.id,
            updated_by=self._user.id,
        )
        self._session.add(knowledge_base)
        await self._session.flush()
        return knowledge_base

    async def rename_knowledge_base(self, knowledge_base_id: UUID, name: str) -> KnowledgeBase:
        knowledge_base = await self._knowledge_base(knowledge_base_id)
        existing = await self._session.scalar(
            select(KnowledgeBase.id).where(
                KnowledgeBase.owner_user_id == self._user.id,
                KnowledgeBase.name == name,
                KnowledgeBase.id != knowledge_base.id,
                KnowledgeBase.deleted_at.is_(None),
            )
        )
        if existing is not None:
            raise ConflictError("知识库名称已存在", error_key="KNOWLEDGE_BASE_NAME_EXISTS")
        knowledge_base.name = name
        knowledge_base.updated_by = self._user.id
        await self._session.flush()
        await self._session.refresh(knowledge_base)
        return knowledge_base

    async def create_upload_session(
        self,
        knowledge_base_id: UUID,
        request: UploadSessionCreate,
        idempotency_key: str,
    ) -> UploadPlan:
        await self._knowledge_base(knowledge_base_id)
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:value, 0))"),
            {"value": f"file-upload-idempotency:{self._user.id}:{idempotency_key}"},
        )
        policy = await FilePolicyService(self._session).ensure_default()
        rules = knowledge_rules(policy)
        filename = validate_declared_file(request.filename, request.size, rules)
        fingerprint = self._request_fingerprint(knowledge_base_id, request)
        existing_session = cast(
            UploadSession | None,
            await self._session.scalar(
                select(UploadSession).where(
                    UploadSession.owner_user_id == self._user.id,
                    UploadSession.idempotency_key == idempotency_key,
                )
            ),
        )
        if existing_session is not None:
            if existing_session.request_fingerprint != fingerprint:
                raise ConflictError("幂等键已用于不同请求", error_key="IDEMPOTENCY_KEY_REUSED")
            return await self._upload_plan(existing_session)

        await self._enforce_upload_limits(request.size, policy.rules)
        limits = cast(dict[str, object], policy.rules["limits"])
        await self._record_rate_limit(cast(int, limits["sessions_per_hour"]))

        if request.client_sha256:
            duplicate = await self._find_owned_asset_by_digest(request.client_sha256, request.size)
            if duplicate is not None:
                same_target = await self._active_binding(knowledge_base_id, duplicate.id)
                if same_target is not None:
                    raise ConflictError("该知识库已存在相同文件", error_key="FILE_ALREADY_ATTACHED")
                session = UploadSession(
                    id=uuid4(),
                    owner_user_id=self._user.id,
                    knowledge_base_id=knowledge_base_id,
                    policy_version_id=policy.id,
                    policy_snapshot=rules,
                    original_filename=filename,
                    declared_mime=request.declared_mime,
                    declared_size=request.size,
                    client_sha256=request.client_sha256,
                    client_md5=request.client_md5,
                    upload_mode="reuse",
                    storage_domain="documents",
                    status="duplicate_action_required",
                    request_fingerprint=fingerprint,
                    idempotency_key=idempotency_key,
                    duplicate_file_asset_id=duplicate.id,
                    expires_at=datetime.now(UTC)
                    + timedelta(hours=self._settings.file_upload_session_hours),
                )
                self._session.add(session)
                await self._session.flush()
                self._audit("create_upload", "upload_session", session.id)
                return await self._upload_plan(session)

        session_id = uuid4()
        key = f"uploads/{session_id}"
        mode = "single" if request.size <= _MULTIPART_THRESHOLD else "multipart"
        upload_id = None
        if mode == "multipart":
            try:
                upload_id = await self._storage.create_multipart(
                    self._settings.rustfs_quarantine_bucket,
                    key,
                    request.declared_mime,
                )
            except Exception as exc:
                raise UpstreamServiceError(
                    "对象存储暂时不可用",
                    status_code=ApiStatusCode.SERVICE_UNAVAILABLE,
                    error_key="OBJECT_STORAGE_UNAVAILABLE",
                ) from exc
        session = UploadSession(
            id=session_id,
            owner_user_id=self._user.id,
            knowledge_base_id=knowledge_base_id,
            policy_version_id=policy.id,
            policy_snapshot=rules,
            original_filename=filename,
            declared_mime=request.declared_mime,
            declared_size=request.size,
            client_sha256=request.client_sha256,
            client_md5=request.client_md5,
            upload_mode=mode,
            storage_domain="documents",
            temporary_object_key=key,
            multipart_upload_id=upload_id,
            status="uploading",
            request_fingerprint=fingerprint,
            idempotency_key=idempotency_key,
            expires_at=datetime.now(UTC)
            + timedelta(hours=self._settings.file_upload_session_hours),
        )
        self._session.add(session)
        await self._session.flush()
        self._audit("create_upload", "upload_session", session.id)
        return await self._upload_plan(session)

    async def sign_parts(self, session_id: UUID, part_numbers: list[int]) -> list[SignedPart]:
        upload = await self._upload_session(session_id)
        self._ensure_upload_active(upload)
        if upload.upload_mode != "multipart" or not upload.multipart_upload_id:
            raise ConflictError("该会话不是分片上传", error_key="FILE_UPLOAD_STATE_CONFLICT")
        assert upload.temporary_object_key is not None
        return [
            SignedPart(
                part_number=number,
                upload_url=await self._storage.presign_part(
                    self._settings.rustfs_quarantine_bucket,
                    upload.temporary_object_key,
                    upload.multipart_upload_id,
                    number,
                ),
            )
            for number in part_numbers
        ]

    async def renew_upload_url(self, session_id: UUID) -> UploadPlan:
        upload = await self._upload_session(session_id)
        self._ensure_upload_active(upload)
        return await self._upload_plan(upload)

    async def complete_upload(
        self, session_id: UUID, parts: list[dict[str, int | str]]
    ) -> UploadSessionView:
        upload = await self._upload_session(session_id)
        if upload.status in {"verifying", "completed", "duplicate_action_required"}:
            return self._session_view(upload)
        self._ensure_upload_active(upload)
        if upload.upload_mode == "multipart":
            if not upload.multipart_upload_id or not upload.temporary_object_key or not parts:
                raise ConflictError("分片信息不完整", error_key="FILE_UPLOAD_STATE_CONFLICT")
            ordered = sorted(parts, key=lambda item: int(item["PartNumber"]))
            if len({int(item["PartNumber"]) for item in ordered}) != len(ordered):
                raise ValidationAppError("分片编号重复", error_key="FILE_PARTS_INVALID")
            try:
                await self._storage.complete_multipart(
                    self._settings.rustfs_quarantine_bucket,
                    upload.temporary_object_key,
                    upload.multipart_upload_id,
                    ordered,
                )
            except Exception as exc:
                raise UpstreamServiceError(
                    "完成分片上传失败",
                    status_code=ApiStatusCode.SERVICE_UNAVAILABLE,
                    error_key="OBJECT_STORAGE_UNAVAILABLE",
                ) from exc
        elif upload.upload_mode != "single":
            raise ConflictError("上传状态不允许完成", error_key="FILE_UPLOAD_STATE_CONFLICT")
        upload.status = "verifying"
        upload.completed_at = datetime.now(UTC)
        await self._enqueue_task(
            "verify_upload",
            "upload_session",
            upload.id,
            {"upload_session_id": str(upload.id)},
            f"verify-upload:{upload.id}",
            max_attempts=3,
            priority=10,
        )
        await self._session.flush()
        self._audit("complete_upload", "upload_session", upload.id)
        return self._session_view(upload)

    async def get_upload_session(self, session_id: UUID) -> UploadSessionView:
        return self._session_view(await self._upload_session(session_id))

    async def cancel_upload(self, session_id: UUID) -> UploadSessionView:
        upload = await self._upload_session(session_id)
        if upload.status in {"cancelled", "expired", "failed"}:
            return self._session_view(upload)
        if upload.status == "completed":
            raise ConflictError("已完成会话不能取消", error_key="FILE_UPLOAD_STATE_CONFLICT")
        upload.status = "cancelled"
        if upload.temporary_object_key:
            await self._enqueue_temp_cleanup(upload)
        await self._session.flush()
        self._audit("cancel_upload", "upload_session", upload.id)
        return self._session_view(upload)

    async def resolve_duplicate(self, session_id: UUID, action: str) -> UploadSessionView:
        upload = await self._upload_session(session_id)
        if upload.status == "completed":
            return self._session_view(upload)
        if upload.status != "duplicate_action_required" or upload.duplicate_file_asset_id is None:
            raise ConflictError("没有待处理的重复文件", error_key="FILE_UPLOAD_STATE_CONFLICT")
        if action == "CANCEL":
            upload.status = "cancelled"
            if upload.temporary_object_key:
                await self._enqueue_temp_cleanup(upload)
            await self._session.flush()
            return self._session_view(upload)
        asset = cast(
            FileAsset | None,
            await self._session.scalar(
                select(FileAsset).where(
                    FileAsset.id == upload.duplicate_file_asset_id,
                    FileAsset.owner_user_id == self._user.id,
                    FileAsset.deleted_at.is_(None),
                )
            ),
        )
        if asset is None:
            raise ConflictError("重复候选已失效", error_key="FILE_UPLOAD_STATE_CONFLICT")
        if upload.knowledge_base_id is None:
            raise ConflictError("上传用途不匹配", error_key="FILE_UPLOAD_STATE_CONFLICT")
        existing_target = await self._active_binding(upload.knowledge_base_id, asset.id)
        if existing_target is not None:
            raise ConflictError("该知识库已存在相同文件", error_key="FILE_ALREADY_ATTACHED")
        if action == "MOVE":
            source = cast(
                KnowledgeBaseFile | None,
                await self._session.scalar(
                    select(KnowledgeBaseFile)
                    .join(KnowledgeBase, KnowledgeBase.id == KnowledgeBaseFile.knowledge_base_id)
                    .where(
                        KnowledgeBaseFile.file_asset_id == asset.id,
                        KnowledgeBaseFile.deleted_at.is_(None),
                        KnowledgeBase.owner_user_id == self._user.id,
                    )
                    .order_by(KnowledgeBaseFile.created_at.asc())
                ),
            )
            if source is None:
                raise ConflictError("重复候选关联已失效", error_key="FILE_UPLOAD_STATE_CONFLICT")
            source.deleted_at = datetime.now(UTC)
            source.deleted_by = self._user.id
        binding = KnowledgeBaseFile(
            knowledge_base_id=upload.knowledge_base_id,
            file_asset_id=asset.id,
            display_name=upload.original_filename,
            processing_status="pending_processing",
            created_by=self._user.id,
            updated_by=self._user.id,
        )
        self._session.add(binding)
        await self._session.flush()
        upload.result_knowledge_file_id = binding.id
        upload.status = "completed"
        if upload.temporary_object_key:
            await self._enqueue_temp_cleanup(upload)
        self._audit(action.lower(), "knowledge_base_file", binding.id)
        return self._session_view(upload)

    async def list_files(
        self,
        knowledge_base_id: UUID,
        page: int,
        page_size: int,
        search: str | None,
        status: str | None,
    ) -> tuple[list[KnowledgeFileView], int]:
        await self._knowledge_base(knowledge_base_id)
        predicate = [
            KnowledgeBaseFile.knowledge_base_id == knowledge_base_id,
            KnowledgeBaseFile.deleted_at.is_(None),
            FileAsset.deleted_at.is_(None),
        ]
        if search:
            predicate.append(KnowledgeBaseFile.display_name.ilike(f"%{search.strip()}%"))
        if status:
            predicate.append(KnowledgeBaseFile.processing_status == status)
        query = select(KnowledgeBaseFile, FileAsset).join(
            FileAsset, FileAsset.id == KnowledgeBaseFile.file_asset_id
        )
        total = int(
            await self._session.scalar(
                select(func.count())
                .select_from(KnowledgeBaseFile)
                .join(FileAsset, FileAsset.id == KnowledgeBaseFile.file_asset_id)
                .where(*predicate)
            )
            or 0
        )
        rows = (
            await self._session.execute(
                query.where(*predicate)
                .order_by(KnowledgeBaseFile.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return [self._file_view(binding, asset) for binding, asset in rows], total

    async def rename_file(
        self, knowledge_base_id: UUID, knowledge_file_id: UUID, display_name: str
    ) -> KnowledgeFileView:
        binding, asset = await self._knowledge_file(knowledge_base_id, knowledge_file_id)
        old_ext = PurePath(binding.display_name).suffix.lower()
        new_ext = PurePath(display_name).suffix.lower()
        if old_ext != new_ext:
            raise ValidationAppError(
                "重命名不能修改文件扩展名", error_key="FILE_EXTENSION_IMMUTABLE"
            )
        binding.display_name = display_name
        binding.updated_by = self._user.id
        binding.resource_version += 1
        await self._session.flush()
        await self._session.refresh(binding)
        self._audit("rename", "knowledge_base_file", binding.id)
        return self._file_view(binding, asset)

    async def move_file(
        self, knowledge_base_id: UUID, knowledge_file_id: UUID, target_id: UUID
    ) -> KnowledgeFileView:
        binding, asset = await self._knowledge_file(knowledge_base_id, knowledge_file_id)
        await self._knowledge_base(target_id)
        if target_id == knowledge_base_id:
            return self._file_view(binding, asset)
        if await self._active_binding(target_id, asset.id) is not None:
            raise ConflictError("目标知识库已存在该文件", error_key="FILE_ALREADY_ATTACHED")
        binding.knowledge_base_id = target_id
        binding.updated_by = self._user.id
        binding.resource_version += 1
        await self._session.flush()
        await self._session.refresh(binding)
        self._audit("move", "knowledge_base_file", binding.id)
        return self._file_view(binding, asset)

    async def download_url(
        self, knowledge_base_id: UUID, knowledge_file_id: UUID
    ) -> DownloadUrlView:
        binding, asset = await self._knowledge_file(knowledge_base_id, knowledge_file_id)
        stored = await self._session.get(StoredObject, asset.stored_object_id)
        if stored is None or stored.status != "available":
            raise NotFoundError(error_key="FILE_NOT_AVAILABLE")
        url = await self._storage.presign_download(
            stored.bucket, stored.object_key, binding.display_name
        )
        self._audit("download_authorize", "knowledge_base_file", binding.id)
        return DownloadUrlView(url=url, expires_in=self._settings.file_download_url_seconds)

    async def deletion_impact(
        self, target_type: str, target_id: UUID, mode: str = "SOURCE_ONLY"
    ) -> DeletionImpactView:
        version = await self._target_version(target_type, target_id)
        expires_at = datetime.now(UTC) + timedelta(minutes=self._settings.file_confirmation_minutes)
        token = self._confirmation_token(target_type, target_id, mode, version, expires_at)
        return DeletionImpactView(
            target_id=target_id,
            confirmation_token=token,
            expires_at=expires_at,
        )

    async def file_deletion_impact(
        self,
        knowledge_base_id: UUID,
        knowledge_file_id: UUID,
        mode: str = "SOURCE_ONLY",
    ) -> DeletionImpactView:
        await self._knowledge_file(knowledge_base_id, knowledge_file_id)
        return await self.deletion_impact("knowledge_base_file", knowledge_file_id, mode)

    async def delete_file(
        self,
        knowledge_base_id: UUID,
        knowledge_file_id: UUID,
        token: str,
        mode: str,
    ) -> DeleteResult:
        binding, asset = await self._knowledge_file(knowledge_base_id, knowledge_file_id)
        self._verify_confirmation_token(
            token, "knowledge_base_file", binding.id, mode, binding.resource_version
        )
        await self._delete_binding(binding, asset)
        self._audit("delete", "knowledge_base_file", binding.id)
        return DeleteResult(target_id=binding.id)

    async def delete_knowledge_base(
        self, knowledge_base_id: UUID, token: str, mode: str
    ) -> DeleteResult:
        knowledge_base = await self._knowledge_base(knowledge_base_id)
        count = int(
            await self._session.scalar(
                select(func.count()).where(
                    KnowledgeBase.owner_user_id == self._user.id,
                    KnowledgeBase.deleted_at.is_(None),
                )
            )
            or 0
        )
        if count <= 1:
            raise ConflictError(
                "必须至少保留一个有效知识库", error_key="KNOWLEDGE_BASE_LAST_ACTIVE"
            )
        version = int(knowledge_base.updated_at.timestamp())
        self._verify_confirmation_token(token, "knowledge_base", knowledge_base.id, mode, version)
        rows = (
            await self._session.execute(
                select(KnowledgeBaseFile, FileAsset)
                .join(FileAsset, FileAsset.id == KnowledgeBaseFile.file_asset_id)
                .where(
                    KnowledgeBaseFile.knowledge_base_id == knowledge_base.id,
                    KnowledgeBaseFile.deleted_at.is_(None),
                    FileAsset.deleted_at.is_(None),
                )
            )
        ).all()
        for binding, asset in rows:
            await self._delete_binding(binding, asset)
        now = datetime.now(UTC)
        knowledge_base.deleted_at = now
        knowledge_base.deleted_by = self._user.id
        self._audit("delete", "knowledge_base", knowledge_base.id)
        return DeleteResult(target_id=knowledge_base.id)

    async def enqueue_user_file_cleanup(self, user_id: UUID) -> None:
        bindings = list(
            (
                await self._session.scalars(
                    select(KnowledgeBaseFile)
                    .join(KnowledgeBase, KnowledgeBase.id == KnowledgeBaseFile.knowledge_base_id)
                    .where(
                        KnowledgeBase.owner_user_id == user_id,
                        KnowledgeBaseFile.deleted_at.is_(None),
                    )
                )
            ).all()
        )
        now = datetime.now(UTC)
        for binding in bindings:
            asset = await self._session.get(FileAsset, binding.file_asset_id)
            if asset is not None and asset.deleted_at is None:
                await self._delete_binding(binding, asset, actor_id=user_id)
        uploads = list(
            (
                await self._session.scalars(
                    select(UploadSession).where(
                        UploadSession.owner_user_id == user_id,
                        UploadSession.status.in_(tuple(_ACTIVE_UPLOAD_STATUSES)),
                    )
                )
            ).all()
        )
        for upload in uploads:
            upload.status = "cancelled"
            upload.completed_at = now
            if upload.temporary_object_key:
                await self._enqueue_temp_cleanup(upload, priority=5)

    async def _delete_binding(
        self, binding: KnowledgeBaseFile, asset: FileAsset, actor_id: UUID | None = None
    ) -> None:
        actor = actor_id or self._user.id
        now = datetime.now(UTC)
        if binding.deleted_at is None:
            binding.deleted_at = now
            binding.deleted_by = actor
            binding.processing_status = "cancelled"
            binding.resource_version += 1
        other_count = int(
            await self._session.scalar(
                select(func.count()).where(
                    KnowledgeBaseFile.file_asset_id == asset.id,
                    KnowledgeBaseFile.deleted_at.is_(None),
                    KnowledgeBaseFile.id != binding.id,
                )
            )
            or 0
        )
        if other_count > 0 or asset.deleted_at is not None:
            return
        asset.deleted_at = now
        asset.deleted_by = actor
        await revoke_processing(self._session, asset)
        stored = cast(
            StoredObject | None,
            await self._session.scalar(
                select(StoredObject)
                .where(StoredObject.id == asset.stored_object_id)
                .with_for_update()
            ),
        )
        if stored is None:
            return
        active_refs = int(
            await self._session.scalar(
                select(func.count()).where(
                    FileAsset.stored_object_id == stored.id,
                    FileAsset.deleted_at.is_(None),
                    FileAsset.id != asset.id,
                )
            )
            or 0
        )
        stored.reference_count = active_refs
        if active_refs == 0 and stored.status not in {"deleting", "deleted"}:
            stored.status = "deleting"
            await self._enqueue_task(
                "delete_stored_object",
                "stored_object",
                stored.id,
                {"stored_object_id": str(stored.id)},
                f"delete-stored-object:{stored.id}:{stored.generation}",
                max_attempts=8,
                priority=5,
            )

    async def _target_version(self, target_type: str, target_id: UUID) -> int:
        if target_type == "knowledge_base_file":
            binding, _ = await self._knowledge_file_by_id(target_id)
            return binding.resource_version
        if target_type == "knowledge_base":
            knowledge_base = await self._knowledge_base(target_id)
            return int(knowledge_base.updated_at.timestamp())
        raise ValidationAppError(error_key="DELETE_TARGET_INVALID")

    async def _knowledge_base(self, knowledge_base_id: UUID) -> KnowledgeBase:
        knowledge_base = cast(
            KnowledgeBase | None,
            await self._session.scalar(
                select(KnowledgeBase).where(
                    KnowledgeBase.id == knowledge_base_id,
                    KnowledgeBase.owner_user_id == self._user.id,
                    KnowledgeBase.deleted_at.is_(None),
                )
            ),
        )
        if knowledge_base is None:
            raise NotFoundError("知识库不存在", error_key="KNOWLEDGE_BASE_NOT_FOUND")
        return knowledge_base

    async def _upload_session(self, session_id: UUID) -> UploadSession:
        upload = cast(
            UploadSession | None,
            await self._session.scalar(
                select(UploadSession).where(
                    UploadSession.id == session_id,
                    UploadSession.owner_user_id == self._user.id,
                )
            ),
        )
        if upload is None:
            raise NotFoundError("上传会话不存在", error_key="FILE_UPLOAD_SESSION_NOT_FOUND")
        if upload.expires_at <= datetime.now(UTC) and upload.status in _ACTIVE_UPLOAD_STATUSES:
            upload.status = "expired"
            if upload.temporary_object_key:
                await self._enqueue_temp_cleanup(upload)
            await self._session.flush()
        return upload

    async def _knowledge_file(
        self, knowledge_base_id: UUID, knowledge_file_id: UUID
    ) -> tuple[KnowledgeBaseFile, FileAsset]:
        await self._knowledge_base(knowledge_base_id)
        row = (
            await self._session.execute(
                select(KnowledgeBaseFile, FileAsset)
                .join(FileAsset, FileAsset.id == KnowledgeBaseFile.file_asset_id)
                .where(
                    KnowledgeBaseFile.id == knowledge_file_id,
                    KnowledgeBaseFile.knowledge_base_id == knowledge_base_id,
                    KnowledgeBaseFile.deleted_at.is_(None),
                    FileAsset.owner_user_id == self._user.id,
                    FileAsset.deleted_at.is_(None),
                )
            )
        ).one_or_none()
        if row is None:
            raise NotFoundError("文件不存在", error_key="FILE_NOT_FOUND")
        return row[0], row[1]

    async def _knowledge_file_by_id(
        self, knowledge_file_id: UUID
    ) -> tuple[KnowledgeBaseFile, FileAsset]:
        row = (
            await self._session.execute(
                select(KnowledgeBaseFile, FileAsset)
                .join(FileAsset, FileAsset.id == KnowledgeBaseFile.file_asset_id)
                .join(KnowledgeBase, KnowledgeBase.id == KnowledgeBaseFile.knowledge_base_id)
                .where(
                    KnowledgeBaseFile.id == knowledge_file_id,
                    KnowledgeBaseFile.deleted_at.is_(None),
                    FileAsset.deleted_at.is_(None),
                    KnowledgeBase.owner_user_id == self._user.id,
                    KnowledgeBase.deleted_at.is_(None),
                )
            )
        ).one_or_none()
        if row is None:
            raise NotFoundError("文件不存在", error_key="FILE_NOT_FOUND")
        return row[0], row[1]

    async def _active_binding(
        self, knowledge_base_id: UUID, asset_id: UUID
    ) -> KnowledgeBaseFile | None:
        return cast(
            KnowledgeBaseFile | None,
            await self._session.scalar(
                select(KnowledgeBaseFile).where(
                    KnowledgeBaseFile.knowledge_base_id == knowledge_base_id,
                    KnowledgeBaseFile.file_asset_id == asset_id,
                    KnowledgeBaseFile.deleted_at.is_(None),
                )
            ),
        )

    async def _find_owned_asset_by_digest(self, sha256: str, size: int) -> FileAsset | None:
        return cast(
            FileAsset | None,
            await self._session.scalar(
                select(FileAsset)
                .join(StoredObject, StoredObject.id == FileAsset.stored_object_id)
                .where(
                    FileAsset.owner_user_id == self._user.id,
                    FileAsset.deleted_at.is_(None),
                    FileAsset.validation_status == "available",
                    StoredObject.storage_domain == "documents",
                    StoredObject.sha256 == sha256,
                    StoredObject.byte_size == size,
                    StoredObject.status == "available",
                )
                .order_by(FileAsset.created_at.asc())
            ),
        )

    async def _enforce_upload_limits(
        self, requested_size: int, all_rules: dict[str, object]
    ) -> None:
        limits = cast(dict[str, object], all_rules["limits"])
        active_count = int(
            await self._session.scalar(
                select(func.count()).where(
                    UploadSession.owner_user_id == self._user.id,
                    UploadSession.status.in_(tuple(_ACTIVE_UPLOAD_STATUSES)),
                    UploadSession.expires_at > datetime.now(UTC),
                )
            )
            or 0
        )
        if active_count >= cast(int, limits["concurrent_sessions"]):
            raise TooManyRequestsError(
                "同时上传的文件过多",
                retry_after=60,
                error_key="FILE_CONCURRENT_LIMIT",
            )
        pending_bytes = int(
            await self._session.scalar(
                select(func.coalesce(func.sum(UploadSession.declared_size), 0)).where(
                    UploadSession.owner_user_id == self._user.id,
                    UploadSession.status.in_(tuple(_ACTIVE_UPLOAD_STATUSES)),
                    UploadSession.expires_at > datetime.now(UTC),
                )
            )
            or 0
        )
        if pending_bytes + requested_size > cast(int, limits["pending_bytes"]):
            raise PayloadTooLargeError(
                "未完成上传占用量超过限制", error_key="FILE_CAPACITY_EXCEEDED"
            )
        long_lived = int(
            await self._session.scalar(
                select(func.coalesce(func.sum(FileAsset.byte_size), 0)).where(
                    FileAsset.owner_user_id == self._user.id,
                    FileAsset.deleted_at.is_(None),
                    FileAsset.purpose == "knowledge_document",
                )
            )
            or 0
        )
        if long_lived + requested_size > cast(int, limits["long_lived_bytes"]):
            raise PayloadTooLargeError("长期文件容量超过限制", error_key="FILE_CAPACITY_EXCEEDED")

    async def _record_rate_limit(self, sessions_per_hour: int) -> None:
        bucket = datetime.now(UTC).strftime("%Y%m%d%H")
        key = f"{self._settings.auth_redis_key_prefix}:file-upload:{self._user.id}:{bucket}"
        try:
            count = await self._redis.incr(key)
            if count == 1:
                await self._redis.expire(key, 3700)
        except Exception as exc:
            raise UpstreamServiceError(
                "上传频率保护暂时不可用",
                status_code=ApiStatusCode.SERVICE_UNAVAILABLE,
                error_key="FILE_RATE_LIMIT_UNAVAILABLE",
            ) from exc
        if count > sessions_per_hour:
            raise TooManyRequestsError(
                "上传会话创建过于频繁", retry_after=3600, error_key="FILE_RATE_LIMITED"
            )

    async def _upload_plan(self, upload: UploadSession) -> UploadPlan:
        url = None
        parts: list[SignedPart] = []
        if upload.status in _ACTIVE_UPLOAD_STATUSES and upload.upload_mode == "single":
            assert upload.temporary_object_key is not None
            url = await self._storage.presign_put(
                self._settings.rustfs_quarantine_bucket,
                upload.temporary_object_key,
                upload.declared_mime,
            )
        elif upload.status in _ACTIVE_UPLOAD_STATUSES and upload.upload_mode == "multipart":
            parts = await self.sign_parts(upload.id, [1])
        upload_mode = cast(Literal["single", "multipart", "reuse"], upload.upload_mode)
        return UploadPlan(
            session_id=upload.id,
            status=upload.status,
            upload_mode=upload_mode,
            expires_at=upload.expires_at,
            upload_url=url,
            part_size=_PART_SIZE if upload.upload_mode == "multipart" else None,
            parts=parts,
            duplicate_file_asset_id=upload.duplicate_file_asset_id,
        )

    def _session_view(self, upload: UploadSession) -> UploadSessionView:
        return UploadSessionView(
            session_id=upload.id,
            status=upload.status,
            upload_mode=upload.upload_mode,
            filename=upload.original_filename,
            size=upload.declared_size,
            expires_at=upload.expires_at,
            failure_code=upload.failure_code,
            knowledge_file_id=upload.result_knowledge_file_id,
            duplicate_file_asset_id=upload.duplicate_file_asset_id,
        )

    def _ensure_upload_active(self, upload: UploadSession) -> None:
        if upload.expires_at <= datetime.now(UTC):
            raise ConflictError("上传会话已过期", error_key="FILE_UPLOAD_SESSION_EXPIRED")
        if upload.status not in _ACTIVE_UPLOAD_STATUSES:
            raise ConflictError("上传状态不允许该操作", error_key="FILE_UPLOAD_STATE_CONFLICT")

    async def _enqueue_temp_cleanup(self, upload: UploadSession, priority: int = 100) -> None:
        if not upload.temporary_object_key:
            return
        await self._enqueue_task(
            "delete_temporary_object",
            "upload_session",
            upload.id,
            {
                "bucket": self._settings.rustfs_quarantine_bucket,
                "object_key": upload.temporary_object_key,
                "multipart_upload_id": upload.multipart_upload_id,
            },
            f"delete-temp:{upload.id}",
            max_attempts=8,
            priority=priority,
        )

    async def _enqueue_task(
        self,
        task_type: str,
        target_type: str,
        target_id: UUID | None,
        payload: dict[str, object],
        idempotency_key: str,
        *,
        max_attempts: int,
        priority: int,
    ) -> None:
        await _add_cleanup_task(
            self._session,
            task_type,
            target_type,
            target_id,
            payload,
            idempotency_key,
            max_attempts,
            priority,
        )

    def _audit(self, action: str, target_type: str, target_id: UUID | None) -> None:
        self._session.add(
            FileAuditEvent(
                actor_user_id=self._user.id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                outcome="success",
                request_id=self._request_id,
                ip_hash=self._ip_hash,
                occurred_at=datetime.now(UTC),
            )
        )

    def _file_view(self, binding: KnowledgeBaseFile, asset: FileAsset) -> KnowledgeFileView:
        return KnowledgeFileView(
            id=binding.id,
            display_name=binding.display_name,
            detected_mime=asset.detected_mime,
            byte_size=asset.byte_size,
            processing_status=binding.processing_status,
            validation_status=asset.validation_status,
            created_at=binding.created_at,
            updated_at=binding.updated_at,
        )

    def _request_fingerprint(self, knowledge_base_id: UUID, request: UploadSessionCreate) -> str:
        payload = {
            "knowledge_base_id": str(knowledge_base_id),
            "filename": request.filename,
            "size": request.size,
            "declared_mime": request.declared_mime,
            "client_sha256": request.client_sha256,
            "client_md5": request.client_md5,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def _confirmation_token(
        self, target_type: str, target_id: UUID, mode: str, version: int, expires_at: datetime
    ) -> str:
        payload = {
            "user_id": str(self._user.id),
            "target_type": target_type,
            "target_id": str(target_id),
            "mode": mode,
            "version": version,
            "expires_at": int(expires_at.timestamp()),
        }
        encoded = base64.urlsafe_b64encode(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).rstrip(b"=")
        signature = hmac.new(
            self._settings.auth_fingerprint_secret.get_secret_value().encode(),
            encoded,
            hashlib.sha256,
        ).digest()
        return f"{encoded.decode()}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"

    def _verify_confirmation_token(
        self, token: str, target_type: str, target_id: UUID, mode: str, version: int
    ) -> None:
        try:
            encoded_text, signature_text = token.split(".", 1)
            encoded = encoded_text.encode()
            expected = hmac.new(
                self._settings.auth_fingerprint_secret.get_secret_value().encode(),
                encoded,
                hashlib.sha256,
            ).digest()
            supplied = base64.urlsafe_b64decode(signature_text + "=" * (-len(signature_text) % 4))
            if not hmac.compare_digest(expected, supplied):
                raise ValueError
            payload = json.loads(
                base64.urlsafe_b64decode(encoded + b"=" * (-len(encoded) % 4)).decode()
            )
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            raise ConflictError("删除确认已失效", error_key="DELETE_PREVIEW_STALE") from exc
        valid = (
            payload.get("user_id") == str(self._user.id)
            and payload.get("target_type") == target_type
            and payload.get("target_id") == str(target_id)
            and payload.get("mode") == mode
            and payload.get("version") == version
            and int(payload.get("expires_at", 0)) >= int(datetime.now(UTC).timestamp())
        )
        if not valid:
            raise ConflictError("删除影响已变化，请重新确认", error_key="DELETE_PREVIEW_STALE")

    def _fingerprint(self, value: str | None) -> str | None:
        if value is None:
            return None
        return hmac.new(
            self._settings.auth_fingerprint_secret.get_secret_value().encode(),
            value.encode(),
            hashlib.sha256,
        ).hexdigest()


async def verify_upload_task(
    session: AsyncSession,
    storage: ObjectStorage,
    settings: Settings,
    upload_session_id: UUID,
) -> None:
    upload = cast(
        UploadSession | None,
        await session.scalar(
            select(UploadSession).where(UploadSession.id == upload_session_id).with_for_update()
        ),
    )
    if upload is None or upload.status in {"completed", "cancelled", "expired", "failed"}:
        return
    if upload.status != "verifying" or not upload.temporary_object_key:
        raise ValueError("FILE_UPLOAD_STATE_CONFLICT")
    if upload.purpose != "knowledge_document" or upload.knowledge_base_id is None:
        raise ValueError("FILE_UPLOAD_PURPOSE_CONFLICT")
    rules = upload.policy_snapshot
    try:
        payload = await storage.read_and_hash(
            settings.rustfs_quarantine_bucket,
            upload.temporary_object_key,
            cast(int, rules["max_bytes"]),
        )
        if payload.byte_size != upload.declared_size:
            raise ValidationAppError("实际文件大小与声明不一致", error_key="FILE_SIZE_MISMATCH")
        result = validate_content(upload.original_filename, payload.content, rules)
    except (ValidationAppError, PayloadTooLargeError) as exc:
        upload.status = "failed"
        upload.failure_code = exc.error_key
        await _add_cleanup_task(
            session,
            "delete_temporary_object",
            "upload_session",
            upload.id,
            {
                "bucket": settings.rustfs_quarantine_bucket,
                "object_key": upload.temporary_object_key,
            },
            f"delete-temp:{upload.id}",
            8,
            100,
        )
        return

    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:value, 0))"),
        {"value": f"documents:{payload.sha256}:{payload.byte_size}"},
    )
    stored = cast(
        StoredObject | None,
        await session.scalar(
            select(StoredObject).where(
                StoredObject.storage_domain == "documents",
                StoredObject.sha256 == payload.sha256,
                StoredObject.byte_size == payload.byte_size,
            )
        ),
    )
    owned_asset = None
    if stored is not None:
        owned_asset = cast(
            FileAsset | None,
            await session.scalar(
                select(FileAsset).where(
                    FileAsset.owner_user_id == upload.owner_user_id,
                    FileAsset.stored_object_id == stored.id,
                    FileAsset.purpose == "knowledge_document",
                    FileAsset.deleted_at.is_(None),
                )
            ),
        )
    if owned_asset is not None:
        same_target = await session.scalar(
            select(KnowledgeBaseFile.id).where(
                KnowledgeBaseFile.knowledge_base_id == upload.knowledge_base_id,
                KnowledgeBaseFile.file_asset_id == owned_asset.id,
                KnowledgeBaseFile.deleted_at.is_(None),
            )
        )
        upload.duplicate_file_asset_id = owned_asset.id
        upload.status = "failed" if same_target is not None else "duplicate_action_required"
        upload.failure_code = "FILE_ALREADY_ATTACHED" if same_target is not None else None
        await _add_cleanup_task(
            session,
            "delete_temporary_object",
            "upload_session",
            upload.id,
            {
                "bucket": settings.rustfs_quarantine_bucket,
                "object_key": upload.temporary_object_key,
            },
            f"delete-temp:{upload.id}",
            8,
            100,
        )
        return

    if stored is None:
        target_key = f"sha256/{payload.sha256[:2]}/{payload.sha256}"
        await storage.copy_object(
            settings.rustfs_quarantine_bucket,
            upload.temporary_object_key,
            settings.rustfs_documents_bucket,
            target_key,
        )
        stored = StoredObject(
            storage_domain="documents",
            sha256=payload.sha256,
            byte_size=payload.byte_size,
            detected_mime=result.detected_mime,
            bucket=settings.rustfs_documents_bucket,
            object_key=target_key,
            status="available",
            reference_count=0,
        )
        session.add(stored)
        await session.flush()
    elif stored.status != "available":
        await storage.copy_object(
            settings.rustfs_quarantine_bucket,
            upload.temporary_object_key,
            stored.bucket,
            stored.object_key,
        )
        stored.detected_mime = result.detected_mime
        stored.status = "available"
        stored.generation += 1
        stored.reference_count = 0
        stored.cleared_at = None
    asset = FileAsset(
        owner_user_id=upload.owner_user_id,
        stored_object_id=stored.id,
        purpose="knowledge_document",
        original_filename=upload.original_filename,
        detected_mime=result.detected_mime,
        byte_size=payload.byte_size,
        validation_status="available",
        policy_version_id=upload.policy_version_id,
        created_from_upload_session_id=upload.id,
        created_by=upload.owner_user_id,
        updated_by=upload.owner_user_id,
    )
    session.add(asset)
    await session.flush()
    binding = KnowledgeBaseFile(
        knowledge_base_id=upload.knowledge_base_id,
        file_asset_id=asset.id,
        display_name=upload.original_filename,
        processing_status="pending_processing",
        created_by=upload.owner_user_id,
        updated_by=upload.owner_user_id,
    )
    session.add(binding)
    await session.flush()
    await enqueue_processing(session, asset)
    stored.reference_count += 1
    upload.status = "completed"
    upload.result_knowledge_file_id = binding.id
    await _add_cleanup_task(
        session,
        "delete_temporary_object",
        "upload_session",
        upload.id,
        {"bucket": settings.rustfs_quarantine_bucket, "object_key": upload.temporary_object_key},
        f"delete-temp:{upload.id}",
        8,
        100,
    )


async def _add_cleanup_task(
    session: AsyncSession,
    task_type: str,
    target_type: str,
    target_id: UUID | None,
    payload: dict[str, object],
    idempotency_key: str,
    max_attempts: int,
    priority: int,
) -> None:
    await session.execute(
        pg_insert(FileCleanupTask)
        .values(
            id=uuid4(),
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
        .on_conflict_do_nothing(index_elements=[FileCleanupTask.idempotency_key])
    )
