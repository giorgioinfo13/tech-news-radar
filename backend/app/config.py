"""Environment configuration shared by application entry points."""

import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.exc import ArgumentError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TNR_",
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    app_name: str = "Tech News Radar"
    environment: Literal["development", "production"] = "development"
    docs_enabled: bool = True
    database_url: str = Field(default="", repr=False)
    migration_database_url: str | None = Field(default=None, repr=False)
    # Local development only. No request header/query/body may choose an identity.
    local_user_id: UUID | None = None
    supabase_url: str | None = None
    supabase_publishable_key: str | None = Field(default=None, repr=False)
    scheduler_enabled: bool = True
    scheduler_poll_seconds: int = Field(default=30, ge=1, le=300)
    collection_trigger_secret: SecretStr | None = None
    feed_timeout_seconds: float = Field(default=10, gt=0, le=60)
    feed_max_bytes: int = Field(default=2_000_000, ge=1024, le=10_000_000)
    feed_max_entries: int = Field(default=5000, ge=1, le=10000)
    # Independent opt-in: installing this release never sends RSS to an AI provider.
    ai_briefs_enabled: bool = False
    # Reject stale provider selections instead of silently changing their destination.
    ai_transport: Literal["gemini"] = "gemini"
    gemini_api_key: SecretStr | None = None
    ai_privacy_reviewed: bool = False
    # Explicit deployment opt-in: reservations are estimates, not a provider invoice cap.
    ai_budget_risk_accepted: bool = False
    ai_digest_enabled: bool = False
    ai_digest_trigger_secret: SecretStr | None = None
    ai_daily_attempts: int = Field(default=24, ge=1, le=24)
    ai_daily_tokens: int = Field(default=96000, ge=4000, le=96000)

    @field_validator("supabase_publishable_key")
    @classmethod
    def validate_publishable_key(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"sb_publishable_[A-Za-z0-9_-]{1,200}", value):
            raise ValueError("Use a Supabase publishable key, never a privileged key")
        return value

    @field_validator("collection_trigger_secret", "ai_digest_trigger_secret")
    @classmethod
    def validate_trigger_secret(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not re.fullmatch(
            r"[A-Za-z0-9_-]{32,128}", value.get_secret_value()
        ):
            raise ValueError("Trigger secret must contain 32-128 URL-safe characters")
        return value

    @model_validator(mode="after")
    def separate_collection_modes(self):
        if self.collection_trigger_secret is not None and self.scheduler_enabled:
            raise ValueError("Disable the internal scheduler before enabling the external trigger")
        return self

    @field_validator("supabase_url")
    @classmethod
    def validate_supabase_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        url = urlsplit(value)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or url.port not in (None, 443)
            or url.path not in ("", "/")
            or url.query
            or url.fragment
            or any(char.isspace() for char in value)
        ):
            raise ValueError("Supabase URL must be an HTTPS origin without credentials")
        return value.rstrip("/")

    @model_validator(mode="after")
    def separate_identity_modes(self):
        if self.local_user_id is not None and self.supabase_url is not None:
            raise ValueError("Local identity and Supabase authentication are mutually exclusive")
        return self

    @model_validator(mode="after")
    def validate_production(self):
        if self.environment != "production":
            return self
        if self.local_user_id is not None or not self.supabase_url:
            raise ValueError("Production requires Supabase authentication without a local identity")
        if self.docs_enabled:
            raise ValueError("Disable API documentation in production")
        # Parse without connecting, creating directories, or disclosing credentials.
        from app.db import resolve_database_url

        try:
            url = resolve_database_url(self.database_url)
            valid = (
                url.get_backend_name() == "postgresql"
                and url.query.get("sslmode") == "verify-full"
                and bool(url.query.get("sslrootcert"))
                and bool(re.fullmatch(r"tnr_app(?:\.[a-z0-9]+)?", url.username or ""))
            )
        except (ArgumentError, ValueError, TypeError):
            valid = False
        if not valid:
            raise ValueError(
                "Production requires PostgreSQL with verified TLS and the tnr_app role"
            )
        return self
