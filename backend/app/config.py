"""Environment configuration shared by application entry points."""

from pathlib import Path

from pydantic import Field
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
    database_url: str = "sqlite:///data/news.db"
    feed_timeout_seconds: float = Field(default=10, gt=0, le=60)
    feed_max_bytes: int = Field(default=2_000_000, ge=1024, le=10_000_000)
    feed_max_entries: int = Field(default=5000, ge=1, le=10000)
