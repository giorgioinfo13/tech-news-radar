"""Personal endpoints always scope writes to the server-resolved user."""

import logging
from datetime import timedelta

from fastapi import APIRouter, Response
from sqlalchemy import Uuid, delete, func, literal, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from app.api.dependencies import (
    PaginationDep,
    ResourceId,
    SessionDep,
    UserDep,
    get_or_404,
    paginate,
)
from app.db import insert_once, utc_now
from app.models import AppUser, Source, Subscription
from app.schemas import Page, SubscriptionChange, SubscriptionRead, UserRead

router = APIRouter(tags=["personal"])
logger = logging.getLogger(__name__)


@router.get("/me", response_model=UserRead)
def current_user(user: UserDep, session: SessionDep):
    result = UserRead.model_validate(user)
    user_id = user.id
    now = utc_now()
    cutoff = now - timedelta(minutes=15)
    if user.last_seen_at is None or user.last_seen_at <= cutoff:
        # Release the authentication read snapshot before this independent write.
        session.rollback()
        try:
            session.execute(
                update(AppUser)
                .where(
                    AppUser.id == user_id,
                    AppUser.active.is_(True),
                    or_(AppUser.last_seen_at.is_(None), AppUser.last_seen_at <= cutoff),
                )
                .values(last_seen_at=now)
                .execution_options(synchronize_session=False)
            )
            session.commit()
        except SQLAlchemyError:
            # Optional telemetry must not prevent an already authorized app opening.
            session.rollback()
            logger.warning("Reader usage timestamp could not be saved")
    return result


@router.get("/subscriptions", response_model=Page[SubscriptionRead])
def list_subscriptions(user: UserDep, session: SessionDep, pagination: PaginationDep):
    statement = (
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .options(joinedload(Subscription.source).joinedload(Source.category))
        .order_by(Subscription.source_id)
    )
    return paginate(session, statement, pagination)


def lock_subscriptions(session, user_id):
    # Order this user's choices across tabs, including bulk add/remove races.
    # A separate advisory namespace avoids the collection/access decision locks.
    session.execute(select(func.pg_advisory_xact_lock(746675, func.hashtext(str(user_id)))))


@router.put("/subscriptions", response_model=SubscriptionChange)
def subscribe_all(user: UserDep, session: SessionDep):
    user_id = user.id
    session.rollback()
    lock_subscriptions(session, user_id)
    # One database snapshot covers the full catalog, including paused sources.
    # Server defaults supply timestamps; existing subscriptions retain theirs.
    inserted = (
        insert(Subscription.__table__)
        .from_select(
            ["user_id", "source_id"],
            select(literal(user_id, type_=Uuid()), Source.id).order_by(Source.id),
            include_defaults=False,
        )
        .on_conflict_do_nothing(index_elements=["user_id", "source_id"])
        .returning(Subscription.source_id)
        .cte("inserted_subscriptions")
    )
    changed = session.scalar(select(func.count()).select_from(inserted))
    session.commit()
    return {"changed": changed}


@router.delete("/subscriptions", response_model=SubscriptionChange)
def unsubscribe_all(user: UserDep, session: SessionDep):
    user_id = user.id
    session.rollback()
    lock_subscriptions(session, user_id)
    result = session.execute(delete(Subscription).where(Subscription.user_id == user_id))
    changed = result.rowcount
    session.commit()
    return {"changed": changed}


@router.put("/subscriptions/{source_id}", status_code=204)
def subscribe(source_id: ResourceId, user: UserDep, session: SessionDep) -> Response:
    user_id = user.id
    get_or_404(session, Source, source_id)
    # End the preflight read transaction before the atomic write.
    session.rollback()
    lock_subscriptions(session, user_id)
    insert_once(session, Subscription, {"user_id": user_id, "source_id": source_id})
    session.commit()
    return Response(status_code=204)


@router.delete("/subscriptions/{source_id}", status_code=204)
def unsubscribe(source_id: ResourceId, user: UserDep, session: SessionDep) -> Response:
    user_id = user.id
    session.rollback()
    lock_subscriptions(session, user_id)
    session.execute(
        delete(Subscription).where(
            Subscription.user_id == user_id, Subscription.source_id == source_id
        )
    )
    session.commit()
    return Response(status_code=204)
