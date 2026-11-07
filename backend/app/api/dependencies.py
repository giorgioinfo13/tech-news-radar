"""Request-scoped sessions and small shared database operations."""

from collections.abc import Iterator
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, HTTPException, Path, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import AuthenticationUnavailable, InvalidAccessToken
from app.collection.service import Collector, RefreshRejected
from app.db import Base
from app.invitations import claim_invitation
from app.models import AppUser


def get_session(request: Request) -> Iterator[Session]:
    # Closing the session also rolls back any uncommitted transaction.
    with Session(request.app.state.database_engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
BearerDep = Annotated[HTTPAuthorizationCredentials | None, Depends(HTTPBearer(auto_error=False))]


def get_identity(request: Request, session: SessionDep, credentials: BearerDep) -> UUID:
    """Resolve an explicitly approved identity, with no token-to-local fallback."""
    if request.app.state.settings.supabase_url is not None:
        authorization = request.headers.get("authorization", "")
        parts = authorization.split()
        if credentials is None or len(parts) != 2 or parts[0].lower() != "bearer":
            raise HTTPException(
                status_code=401,
                detail="Bearer token required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            claims = request.app.state.auth_verifier.verify_claims(parts[1])
            subject = UUID(claims["sub"])
        except InvalidAccessToken:
            raise HTTPException(
                status_code=401,
                detail="Invalid access token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from None
        except AuthenticationUnavailable:
            raise HTTPException(
                status_code=503,
                detail="Authentication temporarily unavailable",
                headers={"Retry-After": "10"},
            ) from None
        user_id = session.scalar(select(AppUser.id).where(AppUser.supabase_subject == subject))
        if user_id is None:
            try:
                user_id = claim_invitation(
                    session,
                    subject,
                    claims.get("email"),
                    parts[1],
                    request.app.state.google_identity_verifier,
                )
            except AuthenticationUnavailable:
                raise HTTPException(
                    status_code=503,
                    detail="Authentication temporarily unavailable",
                    headers={"Retry-After": "10"},
                ) from None
        if user_id is None:
            raise HTTPException(status_code=403, detail="User is not authorized")
        return user_id
    user_id = request.app.state.settings.local_user_id
    if user_id is None or request.headers.get("authorization"):
        raise HTTPException(status_code=401, detail="Authentication is not configured")
    if request.client is None or request.client.host not in {"127.0.0.1", "::1"}:
        raise HTTPException(status_code=403, detail="Local identity requires a loopback client")
    return user_id


def get_current_user(
    identity: Annotated[UUID, Depends(get_identity)], session: SessionDep
) -> AppUser:
    user = session.get(AppUser, identity)
    if user is None or not user.active:
        raise HTTPException(status_code=403, detail="User is not authorized")
    return user


UserDep = Annotated[AppUser, Depends(get_current_user)]


def require_admin(user: UserDep) -> AppUser:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    return user


AdminDep = Annotated[AppUser, Depends(require_admin)]


def get_collector(request: Request) -> Collector:
    return request.app.state.collector


CollectorDep = Annotated[Collector, Depends(get_collector)]


def reject_refresh(exc: RefreshRejected) -> HTTPException:
    headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after is not None else None
    return HTTPException(status_code=exc.status_code, detail=exc.detail, headers=headers)


def source_write_guard(collector: CollectorDep) -> Iterator[None]:
    try:
        with collector.exclusive():
            yield
    except RefreshRejected as exc:
        raise reject_refresh(exc) from exc


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
