"""Public API contracts, separate from persistence models."""

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StrictBool,
    StringConstraints,
    model_validator,
)

from app.invitations import normalize_email

CategoryName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]
SourceName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Slug = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=120, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$"
    ),
]
PositiveId = Annotated[int, Field(strict=True, gt=0, le=9223372036854775807)]
RefreshInterval = Annotated[int, Field(strict=True, ge=1, le=10080)]
SortOrder = Annotated[int, Field(strict=True, ge=-2147483648, le=2147483647)]


def validate_feed_url(value: str) -> str:
    url = HttpUrl(value)
    if url.username is not None or url.password is not None:
        raise ValueError("Feed URLs must not contain credentials")
    if url.fragment is not None:
        raise ValueError("Feed URLs must not contain fragments")
    normalized = str(url)
    if len(normalized) > 2048:
        raise ValueError("Feed URLs must not exceed 2048 characters")
    return normalized


FeedUrl = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2048),
    AfterValidator(validate_feed_url),
]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PartialUpdate(InputModel):
    @model_validator(mode="after")
    def reject_null_required_fields(self) -> Self:
        # Only category_id is nullable. Omitted fields do not change stored values.
        for name in self.model_fields_set - {"category_id"}:
            if getattr(self, name) is None:
                raise ValueError(f"{name} must not be null")
        return self


class CategoryCreate(InputModel):
    name: CategoryName
    slug: Slug
    sort_order: SortOrder = 0


class CategoryUpdate(PartialUpdate):
    name: CategoryName | None = None
    slug: Slug | None = None
    sort_order: SortOrder | None = None


class OutputModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SubscriptionChange(OutputModel):
    changed: int = Field(ge=0)


class CategoryRead(OutputModel):
    id: int
    name: str
    slug: str
    sort_order: int


class SourceCreate(InputModel):
    name: SourceName
    feed_url: FeedUrl
    category_id: PositiveId | None = None
    enabled: StrictBool = True
    refresh_interval_minutes: RefreshInterval = 60


class SourceUpdate(PartialUpdate):
    name: SourceName | None = None
    feed_url: FeedUrl | None = None
    category_id: PositiveId | None = None
    enabled: StrictBool | None = None
    refresh_interval_minutes: RefreshInterval | None = None


class SourceSummary(OutputModel):
    id: int
    name: str
    category: CategoryRead | None


class SourceRead(SourceSummary):
    feed_url: str
    category_id: int | None
    enabled: bool
    refresh_interval_minutes: int
    last_checked_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None
    consecutive_failures: int
    created_at: datetime


class ArticleUpdate(InputModel):
    is_read: StrictBool


class ArticleRead(OutputModel):
    id: int
    source_id: int
    source: SourceSummary
    url: str
    title: str
    description: str | None
    discussion_url: str | None
    published_at: datetime | None
    fetched_at: datetime
    is_read: bool


class CollectionRunRead(OutputModel):
    id: int
    source_id: int
    started_at: datetime
    finished_at: datetime | None
    status: Literal["running", "success", "not_modified", "error"]
    articles_seen: int
    articles_added: int
    error_message: str | None


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int


class UserRead(OutputModel):
    id: UUID
    display_name: str
    role: Literal["admin", "reader"]


class ReaderUsageRead(OutputModel):
    id: UUID
    display_name: str
    created_at: datetime
    last_seen_at: datetime | None
    followed_sources: int
    read_articles: int
    last_read_at: datetime | None


class SubscriptionRead(OutputModel):
    source_id: int
    source: SourceRead
    created_at: datetime


class InvitationCreate(InputModel):
    email: Annotated[str, StringConstraints(max_length=254), AfterValidator(normalize_email)]
    display_name: CategoryName


class InvitationRead(OutputModel):
    id: UUID
    email: str
    display_name: str
    created_at: datetime
    accepted_at: datetime | None


ProposalNote = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]


class ProposalCreate(InputModel):
    name: SourceName
    url: FeedUrl | None = None
    note: ProposalNote | None = None
    category_id: PositiveId | None = None
    follow_on_approval: StrictBool = False


class ProposalApprove(InputModel):
    source_id: PositiveId | None = None
    name: SourceName | None = None
    feed_url: FeedUrl | None = None
    category_id: PositiveId | None = None

    @model_validator(mode="after")
    def approval_target(self) -> Self:
        if self.source_id is None and (self.name is None or self.feed_url is None):
            raise ValueError("A new source requires a name and RSS/Atom feed URL")
        if self.source_id is not None and self.model_fields_set - {"source_id"}:
            raise ValueError("Existing sources must be linked without editing their configuration")
        return self


class ProposalReject(InputModel):
    reason: ProposalNote


class ProposalRead(OutputModel):
    id: int
    name: str
    url: str | None
    note: str | None
    category_id: int | None
    follow_on_approval: bool
    status: Literal["pending", "approved", "rejected", "cancelled"]
    created_at: datetime
    decided_at: datetime | None
    reason: str | None
    source_id: int | None
    approved_name: str | None
    approved_feed_url: str | None
    user: UserRead
