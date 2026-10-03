import pytest
from pydantic import ValidationError

from xuemian_ai.profiles.schemas import UserProfilePatch
from xuemian_ai.profiles.service import experience_display


@pytest.mark.parametrize(
    ("months", "expected"),
    [
        (None, None),
        (0, "暂无工作经验"),
        (6, "6 个月"),
        (12, "1 年"),
        (30, "2 年 6 个月"),
    ],
)
def test_experience_display_uses_months_as_single_source(
    months: int | None, expected: str | None
) -> None:
    assert experience_display(months) == expected


def test_profile_patch_normalizes_and_deduplicates_tags() -> None:
    request = UserProfilePatch.model_validate(
        {
            "version": 3,
            "target_job": "  后端工程师  ",
            "target_skills": [" Python ", "python", "FastAPI", ""],
            "focus_topics": [" SQLAlchemy ", "sqlalchemy"],
        }
    )

    assert request.target_job == "后端工程师"
    assert request.target_skills == ["Python", "FastAPI"]
    assert request.focus_topics == ["SQLAlchemy"]


def test_profile_patch_distinguishes_omitted_and_explicit_null() -> None:
    omitted = UserProfilePatch.model_validate({"version": 0})
    cleared = UserProfilePatch.model_validate({"version": 1, "target_job": None})

    assert omitted.model_fields_set == {"version"}
    assert cleared.model_fields_set == {"version", "target_job"}


def test_profile_patch_rejects_read_only_username_and_null_nickname() -> None:
    with pytest.raises(ValidationError):
        UserProfilePatch.model_validate({"version": 0, "username": "other"})
    with pytest.raises(ValidationError):
        UserProfilePatch.model_validate({"version": 0, "nickname": None})


@pytest.mark.parametrize(
    "payload",
    [
        {"version": 0, "experience_months": 721},
        {"version": 0, "target_level": "lead"},
        {"version": 0, "preferred_language": "ja-JP"},
        {"version": 0, "navigation_position": "right"},
        {"version": 0, "navigation_position": None},
        {"version": 0, "target_skills": [str(index) for index in range(31)]},
    ],
)
def test_profile_patch_rejects_out_of_policy_values(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        UserProfilePatch.model_validate(payload)


@pytest.mark.parametrize("position", ["left", "top"])
def test_navigation_preference_accepts_supported_positions(position: str) -> None:
    request = UserProfilePatch.model_validate({"version": 1, "navigation_position": position})

    assert request.navigation_position == position
    assert "navigation_position" in request.model_fields_set


def test_omitted_navigation_preference_is_not_part_of_patch() -> None:
    request = UserProfilePatch.model_validate({"version": 1, "nickname": "新昵称"})

    assert "navigation_position" not in request.model_dump(exclude_unset=True)
