import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import PurePath
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from xuemian_ai.accounts.models import User
from xuemian_ai.core.config import Settings
from xuemian_ai.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from xuemian_ai.file_management.models import (
    FileAsset,
    FileAuditEvent,
    FileCleanupTask,
    StoredObject,
    UploadSession,
)
from xuemian_ai.file_management.policy import FilePolicyService
from xuemian_ai.file_management.storage import ObjectStorage
from xuemian_ai.profiles.image_processing import process_avatar_image
from xuemian_ai.profiles.models import UserProfile
from xuemian_ai.profiles.schemas import (
    AvatarUploadCompleteView,
    AvatarUploadCreate,
    AvatarUploadPlan,
    PreferredLanguage,
    TargetLevel,
    UserProfilePatch,
    UserProfileView,
)

_PROFILE_FIELDS = {
    "target_job",
    "experience_months",
    "target_level",
    "target_skills",
    "focus_topics",
    "learning_goal",
    "preferred_language",
}


def experience_display(months: int | None) -> str | None:
    if months is None:
        return None
    if months == 0:
        return "暂无工作经验"
    years, remaining = divmod(months, 12)
    if years == 0:
        return f"{remaining} 个月"
    if remaining == 0:
        return f"{years} 年"
    return f"{years} 年 {remaining} 个月"


class UserProfileService:
    def __init__(
        self,
        session: AsyncSession,
        storage: ObjectStorage,
        settings: Settings,
        user: User,
        request_id: str | None,
    ) -> None:
        if user.role != "user":
            raise ForbiddenError("管理员不能访问用户画像", error_key="PROFILE_USER_ONLY")
        self._session = session
        self._storage = storage
        self._settings = settings
        self._user = user
        self._request_id = request_id

    async def get_profile(self) -> UserProfileView:
        profile = await self._profile()
        self._audit("read_profile", profile.id if profile is not None else self._user.id)
        return self._view(profile)

    async def update_profile(self, request: UserProfilePatch) -> UserProfileView:
        await self._lock_user()
        profile = await self._locked_profile()
        current_version = profile.version if profile is not None else 0
        if request.version != current_version:
            raise ConflictError(
                "个人资料已在其他位置更新，请刷新后重试",
                error_key="PROFILE_VERSION_CONFLICT",
            )
        fields = request.model_fields_set - {"version"}
        if "nickname" in fields:
            assert request.nickname is not None
            self._user.nickname = request.nickname
            self._user.updated_by = self._user.id

        profile_fields = fields & _PROFILE_FIELDS
        if profile is None and profile_fields:
            profile = UserProfile(
                user_id=self._user.id,
                version=1,
                created_by=self._user.id,
                updated_by=self._user.id,
            )
            self._session.add(profile)
        elif profile is not None and fields:
            profile.version += 1
            profile.updated_by = self._user.id

        if profile is not None:
            for field in profile_fields:
                setattr(profile, field, getattr(request, field))
        await self._session.flush()
        self._audit("update_profile", profile.id if profile is not None else self._user.id)
        return self._view(profile)

    async def create_avatar_upload(
        self, request: AvatarUploadCreate, idempotency_key: str
    ) -> AvatarUploadPlan:
        suffix = PurePath(request.filename).suffix.lower().lstrip(".")
        allowed_suffixes = {"jpg", "jpeg", "png", "webp"}
        if suffix not in allowed_suffixes:
            raise ValidationAppError("头像文件扩展名不支持", error_key="AVATAR_INVALID_IMAGE")
        profile = await self._profile()
        current_version = profile.version if profile is not None else 0
        if request.profile_version != current_version:
            raise ConflictError(
                "个人资料已在其他位置更新，请刷新后重试",
                error_key="PROFILE_VERSION_CONFLICT",
            )
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "filename": request.filename,
                    "size": request.size,
                    "declared_mime": request.declared_mime,
                    "profile_version": request.profile_version,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        existing = cast(
            UploadSession | None,
            await self._session.scalar(
                select(UploadSession).where(
                    UploadSession.owner_user_id == self._user.id,
                    UploadSession.idempotency_key == idempotency_key,
                )
            ),
        )
        if existing is not None:
            if existing.purpose != "avatar" or existing.request_fingerprint != fingerprint:
                raise ConflictError("幂等键已用于其他请求", error_key="FILE_IDEMPOTENCY_CONFLICT")
            return await self._avatar_plan(existing)

        policy = await FilePolicyService(self._session).ensure_default()
        rules = cast(dict[str, object], policy.rules.get("avatar"))
        if not rules:
            raise ConflictError("头像文件策略尚未发布", error_key="AVATAR_POLICY_NOT_FOUND")
        session_id = uuid4()
        key = f"avatars/{self._user.id}/{session_id}"
        expires_at = datetime.now(UTC) + timedelta(hours=self._settings.file_upload_session_hours)
        upload = UploadSession(
            id=session_id,
            owner_user_id=self._user.id,
            knowledge_base_id=None,
            purpose="avatar",
            policy_version_id=policy.id,
            policy_snapshot=rules,
            original_filename=request.filename,
            declared_mime=request.declared_mime,
            declared_size=request.size,
            upload_mode="single",
            storage_domain="avatars",
            temporary_object_key=key,
            status="uploading",
            request_fingerprint=fingerprint,
            idempotency_key=idempotency_key,
            requested_profile_version=request.profile_version,
            expires_at=expires_at,
        )
        self._session.add(upload)
        await self._session.flush()
        self._audit("create_avatar_upload", upload.id)
        return await self._avatar_plan(upload)

    async def complete_avatar_upload(self, upload_id: UUID) -> AvatarUploadCompleteView:
        upload = await self._avatar_upload(upload_id)
        if upload.status in {"verifying", "completed", "failed"}:
            return self._avatar_complete_view(upload)
        if upload.status != "uploading" or upload.expires_at <= datetime.now(UTC):
            raise ConflictError("头像上传状态不允许完成", error_key="AVATAR_UPLOAD_STATE_CONFLICT")
        upload.status = "verifying"
        upload.completed_at = datetime.now(UTC)
        await _enqueue_task(
            self._session,
            "process_avatar",
            "upload_session",
            upload.id,
            {"upload_session_id": str(upload.id)},
            f"process-avatar:{upload.id}",
            3,
            10,
        )
        self._audit("complete_avatar_upload", upload.id)
        return self._avatar_complete_view(upload)

    async def avatar_content(self) -> bytes:
        profile = await self._profile()
        if profile is None or profile.avatar_file_asset_id is None:
            raise NotFoundError("尚未设置头像", error_key="AVATAR_NOT_SET")
        row = (
            await self._session.execute(
                select(FileAsset, StoredObject)
                .join(StoredObject, StoredObject.id == FileAsset.stored_object_id)
                .where(
                    FileAsset.id == profile.avatar_file_asset_id,
                    FileAsset.owner_user_id == self._user.id,
                    FileAsset.purpose == "avatar",
                    FileAsset.validation_status == "available",
                    FileAsset.deleted_at.is_(None),
                    StoredObject.status == "available",
                )
            )
        ).one_or_none()
        if row is None:
            raise NotFoundError("尚未设置头像", error_key="AVATAR_NOT_SET")
        payload = await self._storage.read_and_hash(
            row[1].bucket, row[1].object_key, 2 * 1024 * 1024
        )
        self._audit("read_avatar", row[0].id)
        return payload.content

    async def delete_avatar(self, version: int) -> UserProfileView:
        await self._lock_user()
        profile = await self._locked_profile()
        current_version = profile.version if profile is not None else 0
        if version != current_version:
            raise ConflictError(
                "个人资料已在其他位置更新，请刷新后重试",
                error_key="PROFILE_VERSION_CONFLICT",
            )
        if profile is None or profile.avatar_file_asset_id is None:
            return self._view(profile)
        old_asset_id = profile.avatar_file_asset_id
        profile.avatar_file_asset_id = None
        profile.version += 1
        profile.updated_by = self._user.id
        await _retire_avatar_asset(self._session, old_asset_id, self._user.id)
        self._audit("delete_avatar", old_asset_id)
        await self._session.flush()
        return self._view(profile)

    async def _profile(self) -> UserProfile | None:
        return cast(
            UserProfile | None,
            await self._session.scalar(
                select(UserProfile).where(UserProfile.user_id == self._user.id)
            ),
        )

    async def _locked_profile(self) -> UserProfile | None:
        return cast(
            UserProfile | None,
            await self._session.scalar(
                select(UserProfile).where(UserProfile.user_id == self._user.id).with_for_update()
            ),
        )

    async def _lock_user(self) -> None:
        user = cast(
            User | None,
            await self._session.scalar(
                select(User).where(User.id == self._user.id).with_for_update()
            ),
        )
        if user is None or user.deleted_at is not None or user.status != "active":
            raise ForbiddenError("用户状态不允许访问个人资料", error_key="PROFILE_USER_INACTIVE")
        self._user = user

    async def _avatar_upload(self, upload_id: UUID) -> UploadSession:
        upload = cast(
            UploadSession | None,
            await self._session.scalar(
                select(UploadSession).where(
                    UploadSession.id == upload_id,
                    UploadSession.owner_user_id == self._user.id,
                    UploadSession.purpose == "avatar",
                )
            ),
        )
        if upload is None:
            raise NotFoundError("头像上传会话不存在", error_key="AVATAR_UPLOAD_NOT_FOUND")
        return upload

    async def _avatar_plan(self, upload: UploadSession) -> AvatarUploadPlan:
        if upload.status != "uploading" or upload.temporary_object_key is None:
            raise ConflictError("头像上传状态不允许续传", error_key="AVATAR_UPLOAD_STATE_CONFLICT")
        url = await self._storage.presign_put(
            self._settings.rustfs_quarantine_bucket,
            upload.temporary_object_key,
            upload.declared_mime,
        )
        return AvatarUploadPlan(
            id=upload.id,
            upload_url=url,
            expires_at=upload.expires_at.isoformat(),
            status=upload.status,
        )

    def _avatar_complete_view(self, upload: UploadSession) -> AvatarUploadCompleteView:
        profile_version = None
        if upload.status == "completed" and upload.requested_profile_version is not None:
            profile_version = upload.requested_profile_version + 1
        return AvatarUploadCompleteView(
            id=upload.id,
            status=upload.status,
            failure_code=upload.failure_code,
            profile_version=profile_version,
        )

    def _view(self, profile: UserProfile | None) -> UserProfileView:
        return UserProfileView(
            username=self._user.username,
            nickname=self._user.nickname,
            target_job=profile.target_job if profile else None,
            experience_months=profile.experience_months if profile else None,
            experience_display=experience_display(profile.experience_months) if profile else None,
            target_level=cast(TargetLevel | None, profile.target_level) if profile else None,
            target_skills=profile.target_skills if profile else None,
            focus_topics=profile.focus_topics if profile else None,
            learning_goal=profile.learning_goal if profile else None,
            preferred_language=(
                cast(PreferredLanguage | None, profile.preferred_language) if profile else None
            ),
            avatar_set=bool(profile and profile.avatar_file_asset_id),
            avatar_url=(
                "/api/v1/users/me/avatar" if profile and profile.avatar_file_asset_id else None
            ),
            version=profile.version if profile else 0,
            active_weaknesses=[],
        )

    def _audit(self, action: str, target_id: UUID) -> None:
        self._session.add(
            FileAuditEvent(
                actor_user_id=self._user.id,
                action=action,
                target_type="user_profile",
                target_id=target_id,
                outcome="success",
                request_id=self._request_id,
                occurred_at=datetime.now(UTC),
            )
        )


async def process_avatar_upload_task(
    session: AsyncSession,
    storage: ObjectStorage,
    settings: Settings,
    upload_id: UUID,
) -> None:
    upload = cast(
        UploadSession | None,
        await session.scalar(
            select(UploadSession).where(UploadSession.id == upload_id).with_for_update()
        ),
    )
    if upload is None or upload.purpose != "avatar" or upload.status in {"completed", "failed"}:
        return
    if upload.status != "verifying" or upload.temporary_object_key is None:
        raise ValueError("AVATAR_UPLOAD_STATE_CONFLICT")
    try:
        max_bytes = upload.policy_snapshot.get("max_bytes")
        if not isinstance(max_bytes, int):
            raise ValueError("AVATAR_POLICY_INVALID")
        payload = await storage.read_and_hash(
            settings.rustfs_quarantine_bucket,
            upload.temporary_object_key,
            max_bytes,
        )
        if payload.byte_size != upload.declared_size:
            raise ValidationAppError("头像大小与声明不一致", error_key="AVATAR_SIZE_MISMATCH")
        processed = await asyncio.wait_for(
            asyncio.to_thread(process_avatar_image, payload.content),
            timeout=settings.avatar_processing_timeout_seconds,
        )
        expected_mime_by_suffix = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
        }
        suffix = PurePath(upload.original_filename).suffix.lower().lstrip(".")
        if (
            processed.source_mime != upload.declared_mime
            or expected_mime_by_suffix.get(suffix) != processed.source_mime
        ):
            raise ValidationAppError("头像图片类型与声明不一致", error_key="AVATAR_INVALID_IMAGE")
    except ValidationAppError as exc:
        upload.status = "failed"
        upload.failure_code = exc.error_key
        await _enqueue_temp_cleanup(session, settings, upload)
        return
    except TimeoutError:
        upload.status = "failed"
        upload.failure_code = "AVATAR_PROCESSING_TIMEOUT"
        await _enqueue_temp_cleanup(session, settings, upload)
        return
    except ValueError:
        upload.status = "failed"
        upload.failure_code = "AVATAR_TOO_LARGE"
        await _enqueue_temp_cleanup(session, settings, upload)
        return

    owner = cast(
        User | None,
        await session.scalar(select(User).where(User.id == upload.owner_user_id).with_for_update()),
    )
    if (
        owner is None
        or owner.deleted_at is not None
        or owner.status != "active"
        or owner.role != "user"
    ):
        upload.status = "failed"
        upload.failure_code = "PROFILE_USER_INACTIVE"
        await _enqueue_temp_cleanup(session, settings, upload)
        return
    profile = cast(
        UserProfile | None,
        await session.scalar(
            select(UserProfile).where(UserProfile.user_id == upload.owner_user_id).with_for_update()
        ),
    )
    current_version = profile.version if profile is not None else 0
    if upload.requested_profile_version != current_version:
        upload.status = "failed"
        upload.failure_code = "PROFILE_VERSION_CONFLICT"
        await _enqueue_temp_cleanup(session, settings, upload)
        return

    digest = hashlib.sha256(processed.content).hexdigest()
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:value, 0))"),
        {"value": f"avatars:{digest}:{len(processed.content)}"},
    )
    target_key = f"avatars/sha256/{digest[:2]}/{digest}.webp"
    stored = cast(
        StoredObject | None,
        await session.scalar(
            select(StoredObject).where(
                StoredObject.storage_domain == "avatars",
                StoredObject.sha256 == digest,
                StoredObject.byte_size == len(processed.content),
            )
        ),
    )
    if stored is None:
        await storage.put_bytes(
            settings.rustfs_documents_bucket,
            target_key,
            processed.content,
            "image/webp",
        )
        stored = StoredObject(
            storage_domain="avatars",
            sha256=digest,
            byte_size=len(processed.content),
            detected_mime="image/webp",
            bucket=settings.rustfs_documents_bucket,
            object_key=target_key,
            status="available",
            reference_count=0,
        )
        session.add(stored)
        await session.flush()
    elif stored.status != "available":
        await storage.put_bytes(stored.bucket, stored.object_key, processed.content, "image/webp")
        stored.status = "available"
        stored.generation += 1
        stored.cleared_at = None

    asset = FileAsset(
        owner_user_id=upload.owner_user_id,
        stored_object_id=stored.id,
        purpose="avatar",
        original_filename=upload.original_filename,
        detected_mime="image/webp",
        byte_size=len(processed.content),
        validation_status="available",
        policy_version_id=upload.policy_version_id,
        created_from_upload_session_id=upload.id,
        created_by=upload.owner_user_id,
        updated_by=upload.owner_user_id,
    )
    session.add(asset)
    await session.flush()
    old_asset_id = profile.avatar_file_asset_id if profile is not None else None
    if profile is None:
        profile = UserProfile(
            user_id=upload.owner_user_id,
            avatar_file_asset_id=asset.id,
            version=1,
            created_by=upload.owner_user_id,
            updated_by=upload.owner_user_id,
        )
        session.add(profile)
    else:
        profile.avatar_file_asset_id = asset.id
        profile.version += 1
        profile.updated_by = upload.owner_user_id
    stored.reference_count += 1
    if old_asset_id is not None:
        await _retire_avatar_asset(session, old_asset_id, upload.owner_user_id)
    upload.status = "completed"
    upload.result_file_asset_id = asset.id
    await _enqueue_temp_cleanup(session, settings, upload)


async def _retire_avatar_asset(session: AsyncSession, asset_id: UUID, actor_id: UUID) -> None:
    asset = cast(
        FileAsset | None,
        await session.scalar(select(FileAsset).where(FileAsset.id == asset_id).with_for_update()),
    )
    if asset is None or asset.deleted_at is not None:
        return
    stored = cast(
        StoredObject | None,
        await session.scalar(
            select(StoredObject).where(StoredObject.id == asset.stored_object_id).with_for_update()
        ),
    )
    asset.deleted_at = datetime.now(UTC)
    asset.deleted_by = actor_id
    if stored is None:
        return
    stored.reference_count = max(0, stored.reference_count - 1)
    if stored.reference_count == 0:
        stored.status = "deleting"
        await _enqueue_task(
            session,
            "delete_stored_object",
            "stored_object",
            stored.id,
            {"stored_object_id": str(stored.id)},
            f"delete-avatar-stored:{stored.id}:{stored.generation}",
            8,
            5,
        )


async def _enqueue_temp_cleanup(
    session: AsyncSession, settings: Settings, upload: UploadSession
) -> None:
    assert upload.temporary_object_key is not None
    await _enqueue_task(
        session,
        "delete_temporary_object",
        "upload_session",
        upload.id,
        {
            "bucket": settings.rustfs_quarantine_bucket,
            "object_key": upload.temporary_object_key,
        },
        f"delete-avatar-temp:{upload.id}",
        8,
        100,
    )


async def _enqueue_task(
    session: AsyncSession,
    task_type: str,
    target_type: str,
    target_id: UUID,
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
