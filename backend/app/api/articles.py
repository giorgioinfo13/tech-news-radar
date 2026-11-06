from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import joinedload

from app.api.dependencies import (
    FilterId,
    PaginationDep,
    ResourceId,
    SessionDep,
    UserDep,
    get_or_404,
)
from app.db import insert_once
from app.models import Article, ArticleReadState, Source, Subscription
from app.schemas import ArticleRead, ArticleUpdate, Page

router = APIRouter(prefix="/articles", tags=["articles"])


@router.get("", response_model=Page[ArticleRead])
def list_articles(
    session: SessionDep,
    pagination: PaginationDep,
    user: UserDep,
    source_id: FilterId = None,
    category_id: FilterId = None,
    is_read: bool | None = None,
    subscribed_only: bool = True,
    q: Annotated[str | None, Query(max_length=200)] = None,
):
    """Newest first, using acquisition time only when publication time is unknown."""
    read = (
        select(ArticleReadState.article_id)
        .where(ArticleReadState.article_id == Article.id, ArticleReadState.user_id == user.id)
        .exists()
    )
    statement = (
        select(Article, read.label("is_read"))
        .options(joinedload(Article.source).joinedload(Source.category))
        .order_by(func.coalesce(Article.published_at, Article.fetched_at).desc(), Article.id.desc())
    )
    if subscribed_only:
        statement = statement.where(
            select(Subscription.source_id)
            .where(Subscription.source_id == Article.source_id, Subscription.user_id == user.id)
            .exists()
        )
    if source_id is not None:
        statement = statement.where(Article.source_id == source_id)
    if category_id is not None:
        statement = statement.join(Article.source).where(Source.category_id == category_id)
    if is_read is not None:
        statement = statement.where(read == is_read)
    if q is not None and (term := q.strip()):
        statement = statement.where(
            or_(
                Article.title.icontains(term, autoescape=True),
                Article.description.icontains(term, autoescape=True),
            )
        )
    total = session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    rows = session.execute(statement.limit(pagination.limit).offset(pagination.offset)).all()
    return {
        "items": [article_response(article, flag) for article, flag in rows],
        "total": total,
        "limit": pagination.limit,
        "offset": pagination.offset,
    }


def article_response(article: Article, is_read: bool) -> dict:
    return {
        name: getattr(article, name) for name in ArticleRead.model_fields if name != "is_read"
    } | {"is_read": is_read}


@router.patch("/{article_id}", response_model=ArticleRead)
def update_article(article_id: ResourceId, data: ArticleUpdate, session: SessionDep, user: UserDep):
    user_id = user.id
    article = get_or_404(session, Article, article_id)
    # Do not upgrade a SQLite read snapshot while concurrent requests also write.
    session.rollback()
    if data.is_read:
        insert_once(session, ArticleReadState, {"user_id": user_id, "article_id": article_id})
    else:
        session.execute(
            delete(ArticleReadState).where(
                ArticleReadState.user_id == user_id, ArticleReadState.article_id == article_id
            )
        )
    session.commit()
    return article_response(article, data.is_read)
