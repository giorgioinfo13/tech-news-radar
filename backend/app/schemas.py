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


class SubscriptionRead(OutputModel):
    source_id: int
    source: SourceRead
    created_at: datetime
