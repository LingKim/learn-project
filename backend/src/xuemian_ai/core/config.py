from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPOSITORY_ENV_FILE = Path(__file__).resolve().parents[4] / ".env"


class Settings(BaseSettings):
    """仅从环境读取的运行配置；秘密值不会出现在 repr 中。"""

    app_name: str = "学面通AI API"
    app_version: str = "0.1.0"
    environment: Literal["development", "test", "production"] = "development"
    log_format: Literal["console", "json"] = "console"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    api_v1_prefix: str = "/api/v1"
    database_url: SecretStr = SecretStr(
        "postgresql+asyncpg://xuemian_ai_app:change-me@localhost:5432/xuemian_ai"
    )
    redis_url: SecretStr = SecretStr("redis://localhost:6379/0")
    rustfs_health_url: AnyHttpUrl = AnyHttpUrl("http://localhost:9000/health")
    rustfs_internal_endpoint: AnyHttpUrl = AnyHttpUrl("http://localhost:9000")
    rustfs_public_endpoint: AnyHttpUrl = AnyHttpUrl("http://localhost:9000")
    rustfs_access_key: SecretStr = SecretStr("replace-with-generated-local-access-key")
    rustfs_secret_key: SecretStr = SecretStr("replace-with-generated-local-secret-key")
    rustfs_region: str = "us-east-1"
    rustfs_quarantine_bucket: str = "xuemian-quarantine"
    rustfs_documents_bucket: str = "xuemian-documents"
    rustfs_recordings_bucket: str = "xuemian-recordings"
    rustfs_temporary_bucket: str = "xuemian-temporary"
    file_upload_url_seconds: int = 900
    file_download_url_seconds: int = 300
    file_upload_session_hours: int = 24
    file_confirmation_minutes: int = 5
    file_worker_poll_seconds: float = 1.0
    file_worker_lease_seconds: int = 300
    file_cleanup_batch_size: int = 100
    file_temporary_retention_days: int = 2
    dependency_timeout_seconds: float = 2.0
    auth_access_secret: SecretStr
    auth_refresh_secret: SecretStr
    auth_refresh_digest_secret: SecretStr
    auth_fingerprint_secret: SecretStr
    auth_issuer: str = "xuemian-ai"
    auth_audience: str = "xuemian-ai-web"
    auth_access_minutes: int = 15
    auth_refresh_days: int = 7
    auth_cookie_secure: bool = False
    auth_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    auth_redis_key_prefix: str = "xuemian:development:auth"
    admin_username: str | None = None
    admin_password: SecretStr | None = None

    model_config = SettingsConfigDict(
        env_file=(REPOSITORY_ENV_FILE, ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_authentication_secrets(self) -> "Settings":
        secrets = {
            self.auth_access_secret.get_secret_value(),
            self.auth_refresh_secret.get_secret_value(),
            self.auth_refresh_digest_secret.get_secret_value(),
            self.auth_fingerprint_secret.get_secret_value(),
        }
        if any(len(secret) < 32 for secret in secrets):
            raise ValueError("authentication secrets must be at least 32 characters")
        if len(secrets) != 4:
            raise ValueError("authentication secrets must be distinct")
        if self.auth_access_minutes <= 0 or self.auth_refresh_days <= 0:
            raise ValueError("authentication token lifetimes must be positive")
        if self.file_upload_url_seconds <= 0 or self.file_download_url_seconds <= 0:
            raise ValueError("file signed URL lifetimes must be positive")
        if self.file_upload_session_hours <= 0 or self.file_confirmation_minutes <= 0:
            raise ValueError("file session and confirmation lifetimes must be positive")
        if self.file_worker_poll_seconds <= 0 or self.file_worker_lease_seconds <= 0:
            raise ValueError("file worker timing must be positive")
        if self.file_cleanup_batch_size <= 0 or self.file_temporary_retention_days <= 0:
            raise ValueError("file cleanup settings must be positive")
        if self.environment == "production":
            if self.rustfs_public_endpoint.scheme != "https":
                raise ValueError("production RustFS public endpoint must use HTTPS")
            storage_secrets = {
                self.rustfs_access_key.get_secret_value(),
                self.rustfs_secret_key.get_secret_value(),
            }
            if any("replace-with" in secret for secret in storage_secrets):
                raise ValueError("production RustFS credentials must not use placeholders")
        return self

    @property
    def rustfs_buckets(self) -> tuple[str, str, str, str]:
        return (
            self.rustfs_quarantine_bucket,
            self.rustfs_documents_bucket,
            self.rustfs_recordings_bucket,
            self.rustfs_temporary_bucket,
        )

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.auth_allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
