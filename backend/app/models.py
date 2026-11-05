"""Persistence models. Feed validation and collection belong to later service modules."""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy import false as sql_false
from sqlalchemy import true as sql_true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, UTCDateTime, utc_now


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    sort_order: Mapped[int] = mapped_column(default=0, server_default="0")

    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint("length(trim(slug)) > 0", name="slug_not_blank"),
    )


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    feed_url: Mapped[str] = mapped_column(String(2048), unique=True)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=sql_true())
    refresh_interval_minutes: Mapped[int] = mapped_column(default=60, server_default="60")
    etag: Mapped[str | None] = mapped_column(Text)
    last_modified: Mapped[str | None] = mapped_column(Text)
    last_checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)

    category: Mapped[Category | None] = relationship()

    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint("length(trim(feed_url)) > 0", name="feed_url_not_blank"),
        CheckConstraint("refresh_interval_minutes > 0", name="positive_refresh_interval"),
        CheckConstraint("consecutive_failures >= 0", name="nonnegative_failures"),
    )


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    guid: Mapped[str | None] = mapped_column(String(1024))
    url: Mapped[str] = mapped_column(String(2048))
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sql_false())

    source: Mapped[Source] = relationship()

    __table_args__ = (
        UniqueConstraint("source_id", "guid", name="uq_articles_source_guid"),
        UniqueConstraint("source_id", "url", name="uq_articles_source_url"),
        CheckConstraint("guid IS NULL OR length(trim(guid)) > 0", name="guid_not_blank"),
        CheckConstraint("length(trim(url)) > 0", name="url_not_blank"),
        CheckConstraint("length(trim(title)) > 0", name="title_not_blank"),
        Index("ix_articles_published_at", "published_at", "id"),
        Index("ix_articles_source_published_at", "source_id", "published_at", "id"),
    )


class CollectionRun(Base):
    __tablename__ = "collection_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(String(20), default="running", server_default="running")
    articles_seen: Mapped[int] = mapped_column(default=0, server_default="0")
    articles_added: Mapped[int] = mapped_column(default=0, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text)

    source: Mapped[Source] = relationship()

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'success', 'not_modified', 'error')", name="valid_status"
        ),
        CheckConstraint("articles_seen >= 0", name="nonnegative_seen"),
        CheckConstraint(
            "articles_added >= 0 AND articles_added <= articles_seen", name="valid_added"
        ),
        CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at", name="valid_finish_time"
        ),
        CheckConstraint(
            "(status = 'running' AND finished_at IS NULL) OR "
            "(status <> 'running' AND finished_at IS NOT NULL)",
            name="status_matches_finish",
        ),
        Index("ix_collection_runs_source_started_at", "source_id", "started_at", "id"),
    )
