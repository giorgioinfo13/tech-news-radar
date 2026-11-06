"""Environment configuration shared by application entry points."""

from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TNR_",
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Tech News Radar"
    docs_enabled: bool = True
    database_url: str = Field(default="sqlite:///data/news.db", repr=False)
    migration_database_url: str | None = Field(default=None, repr=False)
    # Local development only. No request header/query/body may choose an identity.
    local_user_id: UUID | None = None
    supabase_url: str | None = None
    scheduler_enabled: bool = True
    scheduler_poll_seconds: int = Field(default=30, ge=1, le=300)
    feed_timeout_seconds: float = Field(default=10, gt=0, le=60)
    feed_max_bytes: int = Field(default=2_000_000, ge=1024, le=10_000_000)
    feed_max_entries: int = Field(default=5000, ge=1, le=10000)

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
