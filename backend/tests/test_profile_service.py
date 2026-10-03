from typing import cast
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from xuemian_ai.accounts.models import User
from xuemian_ai.core.config import Settings
from xuemian_ai.core.errors import ConflictError
from xuemian_ai.file_management.storage import ObjectStorage
from xuemian_ai.profiles.models import UserProfile
from xuemian_ai.profiles.schemas import UserProfilePatch
from xuemian_ai.profiles.service import UserProfileService


def make_service(
    profile: UserProfile | None,
) -> tuple[UserProfileService, MagicMock, User]:
    user = User(id=uuid4(), username="test-user", nickname="测试用户", role="user", status="active")
    session = MagicMock(spec=AsyncSession)
    session.scalar.side_effect = [user, profile]
    service = UserProfileService(
        cast(AsyncSession, session),
        cast(ObjectStorage, MagicMock()),
        Settings.model_construct(),
        user,
        None,
    )
    return service, session, user


async def test_missing_profile_defaults_to_left_without_creating_profile() -> None:
    service, session, _ = make_service(None)
    session.scalar.side_effect = [None]

    result = await service.get_profile()

    assert result.navigation_position == "left" and result.version == 0
    assert not any(isinstance(call.args[0], UserProfile) for call in session.add.call_args_list)


async def test_first_navigation_update_creates_account_profile() -> None:
    service, session, user = make_service(None)

    result = await service.update_profile(UserProfilePatch(version=0, navigation_position="top"))

    profile = next(
        call.args[0] for call in session.add.call_args_list if isinstance(call.args[0], UserProfile)
    )
    assert profile.user_id == user.id
    assert profile.navigation_position == result.navigation_position == "top"
    assert result.version == 1
    session.flush.assert_awaited_once()


async def test_navigation_update_preserves_other_profile_fields_and_is_readable_again() -> None:
    profile = UserProfile(
        id=uuid4(), navigation_position="left", version=4, target_job="后端工程师"
    )
    service, session, _ = make_service(profile)

    updated = await service.update_profile(UserProfilePatch(version=4, navigation_position="top"))
    session.scalar.side_effect = [profile]
    refreshed = await service.get_profile()

    assert updated.navigation_position == refreshed.navigation_position == "top"
    assert refreshed.target_job == "后端工程师"
    assert refreshed.version == 5


async def test_unrelated_patch_keeps_saved_navigation_position() -> None:
    profile = UserProfile(id=uuid4(), navigation_position="top", version=4)
    service, _, _ = make_service(profile)

    result = await service.update_profile(UserProfilePatch(version=4, nickname="新昵称"))

    assert result.navigation_position == "top"
    assert result.nickname == "新昵称"
    assert result.version == 5


async def test_stale_navigation_update_does_not_change_saved_preference() -> None:
    profile = UserProfile(id=uuid4(), navigation_position="left", version=4)
    service, session, _ = make_service(profile)

    with pytest.raises(ConflictError) as error:
        await service.update_profile(UserProfilePatch(version=3, navigation_position="top"))

    assert error.value.error_key == "PROFILE_VERSION_CONFLICT"
    assert profile.navigation_position == "left" and profile.version == 4
    session.flush.assert_not_awaited()
