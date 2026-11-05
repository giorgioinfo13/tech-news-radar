from fastapi import APIRouter, Response
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.api.dependencies import (
    FilterId,
    PaginationDep,
    ResourceId,
    SessionDep,
    commit_or_conflict,
    get_or_404,
    paginate,
)
from app.models import Category, CollectionRun, Source
from app.schemas import CollectionRunRead, Page, SourceCreate, SourceRead, SourceUpdate

router = APIRouter(prefix="/sources", tags=["sources"])
CONFLICT = "The feed URL already exists or the category no longer exists"


@router.get("", response_model=Page[SourceRead])
def list_sources(
    session: SessionDep,
    pagination: PaginationDep,
    category_id: FilterId = None,
    enabled: bool | None = None,
):
    statement = select(Source).options(joinedload(Source.category)).order_by(Source.name, Source.id)
    if category_id is not None:
        statement = statement.where(Source.category_id == category_id)
    if enabled is not None:
        statement = statement.where(Source.enabled == enabled)
    return paginate(session, statement, pagination)


@router.post("", response_model=SourceRead, status_code=201)
def create_source(data: SourceCreate, session: SessionDep):
    """Store a source configuration. This does not fetch or verify the feed."""
    if data.category_id is not None:
        get_or_404(session, Category, data.category_id)
    source = Source(**data.model_dump())
    session.add(source)
    commit_or_conflict(session, CONFLICT)
    return source


@router.patch("/{source_id}", response_model=SourceRead)
def update_source(source_id: ResourceId, data: SourceUpdate, session: SessionDep):
    source = get_or_404(session, Source, source_id)
    if data.category_id is not None:
        get_or_404(session, Category, data.category_id)
    changes = data.model_dump(exclude_unset=True)
    if "feed_url" in changes and changes["feed_url"] != source.feed_url:
        # Validators and diagnostics describe the old URL, not the replacement.
        source.etag = None
        source.last_modified = None
        source.last_checked_at = None
        source.last_success_at = None
        source.last_error = None
        source.consecutive_failures = 0
    for field, value in changes.items():
        setattr(source, field, value)
    commit_or_conflict(session, CONFLICT)
    return source


@router.delete("/{source_id}", status_code=204)
def delete_source(source_id: ResourceId, session: SessionDep) -> Response:
    """Permanently delete the source, all its articles, and its collection history."""
    session.delete(get_or_404(session, Source, source_id))
    session.commit()
    return Response(status_code=204)


@router.get("/{source_id}/runs", response_model=Page[CollectionRunRead])
def list_collection_runs(source_id: ResourceId, session: SessionDep, pagination: PaginationDep):
    get_or_404(session, Source, source_id)
    statement = (
        select(CollectionRun)
        .where(CollectionRun.source_id == source_id)
        .order_by(CollectionRun.started_at.desc(), CollectionRun.id.desc())
    )
    return paginate(session, statement, pagination)
