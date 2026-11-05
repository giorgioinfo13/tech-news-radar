from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload

from app.api.dependencies import (
    FilterId,
    PaginationDep,
    ResourceId,
    SessionDep,
    get_or_404,
    paginate,
)
from app.models import Article, Source
from app.schemas import ArticleRead, ArticleUpdate, Page

router = APIRouter(prefix="/articles", tags=["articles"])


@router.get("", response_model=Page[ArticleRead])
def list_articles(
    session: SessionDep,
    pagination: PaginationDep,
    source_id: FilterId = None,
    category_id: FilterId = None,
    is_read: bool | None = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
):
    """Newest first, using acquisition time only when publication time is unknown."""
    statement = (
        select(Article)
        .options(joinedload(Article.source).joinedload(Source.category))
        .order_by(func.coalesce(Article.published_at, Article.fetched_at).desc(), Article.id.desc())
    )
    if source_id is not None:
        statement = statement.where(Article.source_id == source_id)
    if category_id is not None:
        statement = statement.join(Article.source).where(Source.category_id == category_id)
    if is_read is not None:
        statement = statement.where(Article.is_read == is_read)
    if q is not None and (term := q.strip()):
        statement = statement.where(
            or_(
                Article.title.icontains(term, autoescape=True),
                Article.description.icontains(term, autoescape=True),
            )
        )
    return paginate(session, statement, pagination)


@router.patch("/{article_id}", response_model=ArticleRead)
def update_article(article_id: ResourceId, data: ArticleUpdate, session: SessionDep):
    article = get_or_404(session, Article, article_id)
    article.is_read = data.is_read
    session.commit()
    return article
