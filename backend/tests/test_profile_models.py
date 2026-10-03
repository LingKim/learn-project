from xuemian_ai.file_management.models import UploadSession
from xuemian_ai.profiles.models import UserProfile


def test_user_profile_has_one_to_one_avatar_and_version_constraints() -> None:
    columns = set(UserProfile.__table__.columns.keys())
    constraints = {constraint.name for constraint in UserProfile.__table__.constraints}

    assert {
        "user_id",
        "target_job",
        "experience_months",
        "target_level",
        "target_skills",
        "focus_topics",
        "learning_goal",
        "preferred_language",
        "navigation_position",
        "avatar_file_asset_id",
        "version",
    } <= columns
    assert {
        "uq_user_profiles_user_id",
        "ck_user_profiles_experience_months",
        "ck_user_profiles_target_level",
        "ck_user_profiles_preferred_language",
        "ck_user_profiles_navigation_position",
        "ck_user_profiles_version",
    } <= constraints


def test_navigation_position_is_non_nullable_with_database_default() -> None:
    column = UserProfile.__table__.columns["navigation_position"]

    assert column.nullable is False
    assert column.default is not None and column.default.arg == "left"
    assert column.server_default is not None and str(column.server_default.arg) == "left"


def test_upload_session_supports_isolated_avatar_purpose() -> None:
    columns = UploadSession.__table__.columns
    constraints = {constraint.name for constraint in UploadSession.__table__.constraints}

    assert columns["knowledge_base_id"].nullable is True
    assert {"purpose", "result_file_asset_id", "requested_profile_version"} <= set(columns.keys())
    assert "ck_file_upload_purpose" in constraints
