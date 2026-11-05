"""Request-scoped sessions and small shared database operations."""

from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Path, Query, Request
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import Base


def get_session(request: Request) -> Iterator[Session]:
    # Closing the session also rolls back any uncommitted transaction.
    with Session(request.app.state.database_engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
ResourceId = Annotated[int, Path(gt=0, le=9223372036854775807)]
FilterId = Annotated[int | None, Query(gt=0, le=9223372036854775807)]


class Pagination:
    def __init__(
        self,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0, le=9223372036854775807)] = 0,
    ) -> None:
        self.limit = limit
        self.offset = offset


PaginationDep = Annotated[Pagination, Depends()]


def paginate(session: Session, statement: Select, pagination: Pagination) -> dict[str, Any]:
    total = session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    items = session.scalars(statement.limit(pagination.limit).offset(pagination.offset)).all()
    return {"items": items, "total": total, "limit": pagination.limit, "offset": pagination.offset}


def get_or_404[T: Base](session: Session, model: type[T], resource_id: int) -> T:
    entity = session.get(model, resource_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"{model.__name__} not found")
    return entity


def commit_or_conflict(session: Session, detail: str) -> None:
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=detail) from exc
