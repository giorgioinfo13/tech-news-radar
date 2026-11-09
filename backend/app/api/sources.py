from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.api.dependencies import (
    CollectorDep,
    FilterId,
    PaginationDep,
    ResourceId,
    SessionDep,
    UserDep,
    commit_or_conflict,
    get_or_404,
    paginate,
    reject_refresh,
    require_admin,
    source_write_guard,
)
from app.collection.service import RefreshRejected, RefreshSummary
from app.models import Category, CollectionRun, Source, Subscription
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


@router.post("", response_model=SourceRead, status_code=201, dependencies=[Depends(require_admin)])
def create_source(data: SourceCreate, session: SessionDep):
    """Store a source configuration. This does not fetch or verify the feed."""
    if data.category_id is not None:
        get_or_404(session, Category, data.category_id)
    source = Source(**data.model_dump())
    session.add(source)
    commit_or_conflict(session, CONFLICT)
    return source


@router.patch(
    "/{source_id}",
    response_model=SourceRead,
    dependencies=[Depends(require_admin), Depends(source_write_guard)],
)
def update_source(source_id: ResourceId, data: SourceUpdate, session: SessionDep):
    source = get_or_404(session, Source, source_id)
    if data.category_id is not None:
        get_or_404(session, Category, data.category_id)
    changes = data.model_dump(exclude_unset=True)
    if "feed_url" in changes and changes["feed_url"] != source.feed_url:
        # Validators and diagnostics describe the old URL, not the replacement.
        source.etag = None
        source.last_modified = None
        # URL edits clear diagnostics, but must not bypass shared attempt limits/backoff.
        dates = [date for date in (source.last_attempt_at, source.last_checked_at) if date]
        source.last_attempt_at = max(dates) if dates else None
        source.last_checked_at = None
        source.last_success_at = None
        source.last_error = None
    for field, value in changes.items():
        setattr(source, field, value)
    commit_or_conflict(session, CONFLICT)
    return source


@router.delete(
    "/{source_id}",
    status_code=204,
    dependencies=[Depends(require_admin), Depends(source_write_guard)],
)
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


@router.post("/refresh", response_model=RefreshSummary)
def refresh_news(collector: CollectorDep, user: UserDep, session: SessionDep):
    """Authenticated RSS-only collection. No operator secret or AI dispatch."""
    user_id = user.id
    session.rollback()
    try:
        return collector.refresh_news(user_id)
    except RefreshRejected as exc:
        raise reject_refresh(exc) from exc


@router.post(
    "/{source_id}/refresh",
    response_model=CollectionRunRead,
    responses={
        404: {"description": "Source not found"},
        409: {"description": "Source disabled or collection/source change in progress"},
        429: {"description": "Refresh cooldown; see Retry-After"},
        502: {
            "model": CollectionRunRead,
            "description": "Collection failed; result stored in history",
        },
    },
)
def refresh_source(
    source_id: ResourceId,
    collector: CollectorDep,
    response: Response,
    user: UserDep,
    session: SessionDep,
):
    """Refresh one enabled source and wait for its result. No background task is queued."""
    if user.role != "admin" and session.get(Subscription, (user.id, source_id)) is None:
        raise HTTPException(status_code=403, detail="Follow this source before refreshing it")
    # Authorization must not keep a transaction open during the guarded download.
    user_id = user.id
    session.rollback()
    try:
        run = collector.refresh(source_id, user_id=user_id)
    except RefreshRejected as exc:
        raise reject_refresh(exc) from exc
    if run.status == "error":
        response.status_code = 502
    return run
