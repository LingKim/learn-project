from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, model_validator
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
    # 应用层加密密钥环 JSON：key_id -> Fernet key；空配置明确拒绝创建/读取正文快照。
    diagnostic_snapshot_keys: SecretStr = SecretStr("{}")
    diagnostic_snapshot_active_key_id: str = Field(default="v1", pattern=r"^[A-Za-z0-9_-]{1,32}$")
    ai_quality_confirmation_days: int = Field(default=7, ge=1, le=30)
    ai_quality_case_hourly_limit: int = Field(default=20, ge=1, le=1000)
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
    avatar_processing_timeout_seconds: float = 5.0
    dependency_timeout_seconds: float = 2.0
    dashscope_api_key: SecretStr = SecretStr("")
    ai_base_url: AnyHttpUrl = AnyHttpUrl("https://maas.qianwenaiapi.com/compatible-mode/v1")
    ai_rerank_url: AnyHttpUrl = AnyHttpUrl(
        "https://maas.qianwenaiapi.com/api/v1/services/rerank/text-rerank/text-rerank"
    )
    learning_vision_model: str = "qwen3-vl-flash"
    learning_answer_model: str = "qwen3.8-flash"
    learning_model_timeout_seconds: float = Field(default=60, gt=0, le=120)
    learning_request_timeout_seconds: float = Field(default=120, gt=0, le=180)
    learning_consent_version: str = "qwen-learning-v2"
    practice_worker_poll_seconds: float = Field(default=1.0, gt=0)
    practice_worker_lease_seconds: int = Field(default=30, ge=15)
    practice_worker_concurrency: int = Field(default=2, ge=1, le=16)
    practice_run_timeout_seconds: float = Field(default=180, ge=120, le=600)
    knowledge_worker_poll_seconds: float = Field(default=1.0, gt=0)
    knowledge_worker_lease_seconds: int = Field(default=30, ge=15)
    knowledge_worker_concurrency: int = Field(default=2, ge=1, le=16)
    knowledge_run_timeout_seconds: float = Field(default=180, ge=120, le=600)
    document_provider: Literal["qwen", "deterministic"] = "qwen"
    document_embedding_model: str = "qwen3.7-text-embedding"
    document_rerank_model: str = "qwen3-rerank"
    document_ocr_model: str = "qwen3.5-ocr"
    document_model_timeout_seconds: float = Field(default=60, gt=0)
    document_parse_timeout_seconds: float = Field(default=600, gt=0)
    document_chunk_size: int = Field(default=1200, ge=100, le=8000)
    document_chunk_overlap: int = Field(default=120, ge=0)
    document_max_characters: int = Field(default=2_000_000, gt=0)
    document_max_chunks: int = Field(default=10_000, gt=0)
    document_ocr_max_pages: int = Field(default=100, gt=0, le=500)
    document_ocr_max_pixels: int = Field(default=12_000_000, gt=0)
    document_ocr_dpi: int = Field(default=144, ge=72, le=300)
    document_worker_lease_seconds: int = Field(default=120, ge=15)
    document_worker_poll_seconds: float = Field(default=1, gt=0)
    document_retrieval_min_score: float = Field(default=0.2, ge=0, le=1)
    document_retrieval_candidates: int = Field(default=40, ge=5, le=100)
    ai_processing_terms_version: str = "qwen-document-v1"
    qdrant_url: AnyHttpUrl = AnyHttpUrl("http://localhost:6333")
    qdrant_api_key: SecretStr = SecretStr("")
    qdrant_collection: str = Field(
        default="xuemian_qwen_text_1024_v1", pattern=r"^[A-Za-z0-9_-]{1,128}$"
    )
    qdrant_timeout_seconds: float = Field(default=10, gt=0)
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
        if self.avatar_processing_timeout_seconds <= 0:
            raise ValueError("avatar processing timeout must be positive")
        if self.document_chunk_overlap >= self.document_chunk_size:
            raise ValueError("document overlap must be smaller than chunk size")
        if self.document_provider == "deterministic" and self.environment != "test":
            raise ValueError("deterministic document provider is only available in test")
        if self.environment == "production":
            if self.qdrant_url.scheme != "https" or self.ai_base_url.scheme != "https":
                raise ValueError("production AI and Qdrant endpoints must use HTTPS")
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
