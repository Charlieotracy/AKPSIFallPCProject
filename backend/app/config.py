"""Application settings, read from environment variables and an optional `.env` file.

Fail-closed rules (design doc, "Identity and settings"):
- A missing APP_ENV means "prod".
- The dev identity may only be enabled when APP_ENV is "local" or "test".
- "prod" has no default database; DATABASE_URL must be set.
"""

from __future__ import annotations

from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOCAL_SQLITE_URL = "sqlite+aiosqlite:///./jev_uw_local.db"


class Settings(BaseSettings):
    # `.env` is resolved from the working directory (backend/ for every documented command).
    # extra="ignore" lets .env hold keys meant for other components.
    # hide_input_in_errors: a validation error must never echo DATABASE_URL (it holds a password).
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", hide_input_in_errors=True
    )

    app_env: Literal["local", "test", "prod"] = "prod"
    dev_identity_enabled: bool = False
    database_url: str | None = None

    @field_validator("database_url")
    @classmethod
    def _empty_url_is_unset(cls, value: str | None) -> str | None:
        return value or None

    @model_validator(mode="after")
    def _dev_identity_only_outside_prod(self) -> Settings:
        if self.dev_identity_enabled and self.app_env == "prod":
            raise ValueError("DEV_IDENTITY_ENABLED is only allowed when APP_ENV is local or test")
        return self

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        if self.app_env in ("local", "test"):
            return LOCAL_SQLITE_URL
        raise ValueError("DATABASE_URL is required when APP_ENV is prod")
