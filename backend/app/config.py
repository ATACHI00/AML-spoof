"""AML Monitor — Configuration.

Pydantic Settings loading from environment variables.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # App
    app_name: str = "AML Monitor"
    app_version: str = "0.1.0"
    debug: bool = True
    log_level: str = "DEBUG"

    # Database (default: SQLite for standalone, PostgreSQL for Docker)
    database_url: str = "sqlite+aiosqlite:///./aml_monitor.db"
    database_url_sync: str = "sqlite:///./aml_monitor.db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Celery
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"

    # API Security
    api_keys: str = "dev-api-key-1,dev-api-key-2"

    @property
    def api_keys_list(self) -> list[str]:
        """Return API keys as a list."""
        return [k.strip() for k in self.api_keys.split(",") if k.strip()]


settings = Settings()