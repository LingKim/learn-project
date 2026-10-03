from xuemian_ai.main import create_app


def test_openapi_exposes_current_user_profile_and_private_avatar_endpoints() -> None:
    paths = create_app().openapi()["paths"]

    assert {"get", "patch"} <= set(paths["/api/v1/users/me/profile"])
    assert "post" in paths["/api/v1/users/me/avatar-upload-sessions"]
    assert "post" in paths["/api/v1/users/me/avatar-upload-sessions/{upload_id}/complete"]
    assert {"get", "delete"} <= set(paths["/api/v1/users/me/avatar"])


def test_profile_contract_does_not_expose_storage_or_owner_internals() -> None:
    schemas = create_app().openapi()["components"]["schemas"]
    forbidden = {
        "user_id",
        "owner_user_id",
        "avatar_file_asset_id",
        "bucket",
        "object_key",
        "stored_object_id",
    }

    for name in ("UserProfileView", "AvatarUploadPlan", "AvatarUploadCompleteView"):
        assert forbidden.isdisjoint(schemas[name].get("properties", {}))


def test_navigation_contract_has_required_response_and_optional_non_null_patch() -> None:
    schemas = create_app().openapi()["components"]["schemas"]
    view = schemas["UserProfileView"]
    patch = schemas["UserProfilePatch"]

    assert "navigation_position" in view["required"]
    assert "navigation_position" not in patch["required"]
    for schema in (view, patch):
        preference = schema["properties"]["navigation_position"]
        assert preference["type"] == "string"
        assert preference["enum"] == ["left", "top"]
