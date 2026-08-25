from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, SecretStr
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
    dependency_timeout_seconds: float = 2.0

    model_config = SettingsConfigDict(
        env_file=(REPOSITORY_ENV_FILE, ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
