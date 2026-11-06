"""Personal endpoints always scope writes to the server-resolved user."""

from fastapi import APIRouter, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import joinedload

from app.api.dependencies import (
    PaginationDep,
    ResourceId,
    SessionDep,
    UserDep,
    get_or_404,
    paginate,
)
from app.db import insert_once
from app.models import Source, Subscription
from app.schemas import Page, SubscriptionRead, UserRead

router = APIRouter(tags=["personal"])


@router.get("/me", response_model=UserRead)
def current_user(user: UserDep):
    return user


@router.get("/subscriptions", response_model=Page[SubscriptionRead])
def list_subscriptions(user: UserDep, session: SessionDep, pagination: PaginationDep):
    statement = (
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .options(joinedload(Subscription.source).joinedload(Source.category))
        .order_by(Subscription.source_id)
    )
    return paginate(session, statement, pagination)


@router.put("/subscriptions/{source_id}", status_code=204)
def subscribe(source_id: ResourceId, user: UserDep, session: SessionDep) -> Response:
    user_id = user.id
    get_or_404(session, Source, source_id)
    # Release preflight read locks before the atomic write (SQLite lock upgrades).
    session.rollback()
    insert_once(session, Subscription, {"user_id": user_id, "source_id": source_id})
    session.commit()
    return Response(status_code=204)


@router.delete("/subscriptions/{source_id}", status_code=204)
def unsubscribe(source_id: ResourceId, user: UserDep, session: SessionDep) -> Response:
    user_id = user.id
    session.rollback()
    session.execute(
        delete(Subscription).where(
            Subscription.user_id == user_id, Subscription.source_id == source_id
        )
    )
    session.commit()
    return Response(status_code=204)
