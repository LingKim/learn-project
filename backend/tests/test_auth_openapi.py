from xuemian_ai.main import create_app


def test_openapi_exposes_only_current_authentication_endpoints() -> None:
    schema = create_app().openapi()
    paths = schema["paths"]

    assert "/api/v1/auth/register" in paths
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/auth/refresh" in paths
    assert "/api/v1/auth/me" in paths
    assert "/api/v1/auth/logout" in paths
    assert all("first-login" not in path and "reset-password" not in path for path in paths)


def test_authentication_openapi_contains_cookie_and_bearer_contracts() -> None:
    schema = create_app().openapi()
    refresh_operation = schema["paths"]["/api/v1/auth/refresh"]["post"]
    me_operation = schema["paths"]["/api/v1/auth/me"]["get"]

    assert any(
        parameter["in"] == "cookie" and parameter["name"] == "xuemian_refresh_token"
        for parameter in refresh_operation["parameters"]
    )
    assert me_operation["security"] == [{"HTTPBearer": []}]
