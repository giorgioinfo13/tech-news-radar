"""Coarse usage summaries, available only to administrators."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.api.dependencies import PaginationDep, SessionDep, require_admin
from app.models import AppUser, ArticleReadState, Subscription
from app.schemas import Page, ReaderUsageRead

router = APIRouter(prefix="/usage", tags=["usage"], dependencies=[Depends(require_admin)])


@router.get("/readers", response_model=Page[ReaderUsageRead])
def reader_usage(session: SessionDep, pagination: PaginationDep):
    subscriptions = (
        select(Subscription.user_id, func.count().label("followed_sources"))
        .group_by(Subscription.user_id)
        .subquery()
    )
    reads = (
        select(
            ArticleReadState.user_id,
            func.count().label("read_articles"),
            func.max(ArticleReadState.read_at).label("last_read_at"),
        )
        .group_by(ArticleReadState.user_id)
        .subquery()
    )
    statement = (
        select(
            AppUser.id,
            AppUser.display_name,
            AppUser.created_at,
            AppUser.last_seen_at,
            func.coalesce(subscriptions.c.followed_sources, 0).label("followed_sources"),
            func.coalesce(reads.c.read_articles, 0).label("read_articles"),
            reads.c.last_read_at,
        )
        .outerjoin(subscriptions, subscriptions.c.user_id == AppUser.id)
        .outerjoin(reads, reads.c.user_id == AppUser.id)
        .where(AppUser.role == "reader", AppUser.active.is_(True))
        .order_by(AppUser.display_name, AppUser.id)
    )
    total = session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    items = session.execute(statement.limit(pagination.limit).offset(pagination.offset)).mappings()
    return {
        "items": list(items),
        "total": total,
        "limit": pagination.limit,
        "offset": pagination.offset,
    }
