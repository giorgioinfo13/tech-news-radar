"""Persistence models. Feed validation and collection belong to later service modules."""

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy import false as sql_false
from sqlalchemy import true as sql_true
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, UTCDateTime, utc_now

LOCAL_OWNER_ID = UUID("00000000-0000-0000-0000-000000000001")


def text_type(length: int | None = None):
    # PostgreSQL C collation preserves SQLite's byte ordering and ASCII case folding.
    base = String(length) if length is not None else Text()
    postgres = String(length, collation="C") if length is not None else Text(collation="C")
    return base.with_variant(postgres, "postgresql")


def exact_key(name: str, *columns: str):
    """Exact uniqueness, including long UTF-8 keys that exceed PostgreSQL B-tree limits."""
    # Composite callers use an integer source_id first, making ':' unambiguous.
    expression = " || ':' || ".join(f"{column}::text" for column in columns)
    return (
        UniqueConstraint(*columns, name=name).ddl_if(dialect="sqlite"),
        # Hash exclusion rechecks original values, so hash collisions are not duplicates.
        ExcludeConstraint((text(f"({expression})"), "="), name=name, using="hash").ddl_if(
            dialect="postgresql"
        ),
    )


class AIBriefControl(Base):
    """One persistent project-wide gate, including across UTC day boundaries."""

    __tablename__ = "ai_brief_control"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    quota_day: Mapped[date | None] = mapped_column(Date)
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    reserved_tokens: Mapped[int] = mapped_column(default=0, server_default="0")
    next_allowed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    blocked_until: Mapped[datetime | None] = mapped_column(UTCDateTime())
    blocked_code: Mapped[str | None] = mapped_column(String(40))
    lease_id: Mapped[UUID | None] = mapped_column(Uuid)
    lease_until: Mapped[datetime | None] = mapped_column(UTCDateTime())
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton"),
        CheckConstraint("attempts BETWEEN 0 AND 24", name="attempt_budget"),
        CheckConstraint("reserved_tokens = attempts * 4000", name="token_budget"),
        CheckConstraint("(lease_id IS NULL) = (lease_until IS NULL)", name="lease_pair"),
    )


class AIBriefBudget(Base):
    """Monthly UTC reservations, independent of seven-day job retention."""

    __tablename__ = "ai_brief_budget"
    month: Mapped[date] = mapped_column(Date, primary_key=True)
    reserved_nano_usd: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    __table_args__ = (
        CheckConstraint("reserved_nano_usd BETWEEN 0 AND 2000000000", name="monthly_budget"),
    )


class AIBriefJob(Base):
    """An immutable reservation and its bounded, shared result; no reader identity."""

    __tablename__ = "ai_brief_jobs"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), index=True
    )
    category_name: Mapped[str] = mapped_column(String(120))
    edition_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    material_hash: Mapped[str | None] = mapped_column(String(64))
    budget_month: Mapped[date | None] = mapped_column(Date)
    reserved_nano_usd: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    dispatched_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    diagnostics: Mapped[dict | None] = mapped_column(JSON)
    quota_day: Mapped[date] = mapped_column(Date)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    window_start: Mapped[datetime] = mapped_column(UTCDateTime())
    window_end: Mapped[datetime] = mapped_column(UTCDateTime())
    lease_until: Mapped[datetime] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(String(20))
    error_code: Mapped[str | None] = mapped_column(String(40))
    summary: Mapped[str | None] = mapped_column(Text)
    # Backend snapshots preserve citations after article retention/deletion.
    articles: Mapped[list] = mapped_column(JSON)
    model: Mapped[str] = mapped_column(String(120))
    __table_args__ = (
        CheckConstraint("status IN ('running', 'success', 'error', 'interrupted')", name="status"),
        CheckConstraint("window_start < window_end", name="window"),
        CheckConstraint("(status = 'running') = (finished_at IS NULL)", name="finish"),
        Index("uq_ai_brief_jobs_edition", "edition_at", unique=True),
        Index("ix_ai_brief_jobs_started_at", "started_at"),
        Index("ix_ai_brief_jobs_category_day", "category_id", "quota_day"),
        Index(
            "uq_ai_brief_jobs_daily_success",
            "category_id",
            "quota_day",
            unique=True,
            sqlite_where=text("status = 'success'"),
            postgresql_where=text("status = 'success'"),
        ),
    )


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(text_type(120), unique=True)
    slug: Mapped[str] = mapped_column(text_type(120), unique=True)
    sort_order: Mapped[int] = mapped_column(default=0, server_default="0")

    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint("length(trim(slug)) > 0", name="slug_not_blank"),
    )


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(text_type(200))
    feed_url: Mapped[str] = mapped_column(text_type(2048))
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=sql_true())
    refresh_interval_minutes: Mapped[int] = mapped_column(default=60, server_default="60")
    etag: Mapped[str | None] = mapped_column(Text)
    last_modified: Mapped[str | None] = mapped_column(Text)
    last_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)

    category: Mapped[Category | None] = relationship()

    __table_args__ = (
        *exact_key("uq_sources_feed_url", "feed_url"),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint("length(trim(feed_url)) > 0", name="feed_url_not_blank"),
        CheckConstraint("refresh_interval_minutes > 0", name="positive_refresh_interval"),
        CheckConstraint("consecutive_failures >= 0", name="nonnegative_failures"),
    )


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    guid: Mapped[str | None] = mapped_column(text_type(1024))
    url: Mapped[str] = mapped_column(text_type(2048))
    title: Mapped[str] = mapped_column(text_type())
    description: Mapped[str | None] = mapped_column(text_type())
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)

    source: Mapped[Source] = relationship()

    __table_args__ = (
        *exact_key("uq_articles_source_guid", "source_id", "guid"),
        *exact_key("uq_articles_source_url", "source_id", "url"),
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


class AppUser(Base):
    __tablename__ = "app_users"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    supabase_subject: Mapped[UUID | None] = mapped_column(Uuid, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20), default="reader", server_default="reader")
    active: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sql_false())
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, server_default=func.current_timestamp()
    )

    __table_args__ = (
        CheckConstraint("role IN ('admin', 'reader')", name="valid_role"),
        CheckConstraint("length(trim(display_name)) > 0", name="display_name_not_blank"),
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("app_users.id", ondelete="CASCADE"), primary_key=True
    )
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, server_default=func.current_timestamp()
    )
    source: Mapped[Source] = relationship()


class ArticleReadState(Base):
    """A row means read; absence means unread, independently of subscriptions."""

    __tablename__ = "article_read_states"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("app_users.id", ondelete="CASCADE"), primary_key=True
    )
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    read_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, server_default=func.current_timestamp()
    )


class ReaderInvitation(Base):
    __tablename__ = "reader_invitations"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(text_type(254), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    invited_by: Mapped[UUID] = mapped_column(ForeignKey("app_users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # No FK that could reset acceptance when a profile is removed outside the operator command.
    accepted_subject: Mapped[UUID | None] = mapped_column(Uuid, unique=True)

    __table_args__ = (
        CheckConstraint(
            "length(email) BETWEEN 3 AND 254 AND email = lower(trim(email))",
            name="normalized_email",
        ),
        CheckConstraint("length(trim(display_name)) BETWEEN 1 AND 120", name="invitation_name"),
        CheckConstraint(
            "(accepted_at IS NULL) = (accepted_subject IS NULL)", name="invitation_claim"
        ),
    )


class SourceProposal(Base):
    __tablename__ = "source_proposals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("app_users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    name_key: Mapped[str] = mapped_column(String(64))
    url: Mapped[str | None] = mapped_column(String(2048))
    note: Mapped[str | None] = mapped_column(String(500))
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), index=True
    )
    follow_on_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    decided_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("app_users.id", ondelete="SET NULL"), index=True
    )
    reason: Mapped[str | None] = mapped_column(String(500))
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), index=True
    )
    approved_name: Mapped[str | None] = mapped_column(String(200))
    approved_feed_url: Mapped[str | None] = mapped_column(String(2048))
    user: Mapped[AppUser] = relationship(foreign_keys=[user_id])

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'cancelled')", name="valid_status"
        ),
        CheckConstraint("length(trim(name)) BETWEEN 1 AND 200", name="proposal_name"),
        CheckConstraint("url IS NULL OR length(url) BETWEEN 1 AND 2048", name="proposal_url"),
        CheckConstraint("note IS NULL OR length(note) <= 500", name="proposal_note"),
        CheckConstraint(
            "reason IS NULL OR length(reason) BETWEEN 1 AND 500", name="proposal_reason"
        ),
        CheckConstraint("(status = 'pending') = (decided_at IS NULL)", name="proposal_decision"),
        CheckConstraint("status <> 'rejected' OR reason IS NOT NULL", name="rejection_reason"),
        Index("ix_source_proposals_status_created", "status", "created_at", "id"),
        Index(
            "uq_source_proposals_pending_name",
            "user_id",
            "name_key",
            unique=True,
            sqlite_where=text("status = 'pending'"),
            postgresql_where=text("status = 'pending'"),
        ),
    )
