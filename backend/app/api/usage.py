"""Coarse usage summaries, available only to administrators."""

from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from app.ai_gemini import MONTHLY_NANO_USD
from app.ai_usage import TOKEN_FIELDS
from app.api.dependencies import PaginationDep, SessionDep, require_admin
from app.db import utc_now
from app.models import AIBriefBudget, AIBriefUsage, AppUser, ArticleReadState, Subscription
from app.schemas import AIUsageRead, Page, ReaderUsageRead

router = APIRouter(prefix="/usage", tags=["usage"], dependencies=[Depends(require_admin)])


def usage_summary(attempts: list[dict]) -> dict:
    measured = [a for a in attempts if a["usage_state"] == "measured"]
    unverified = sum(a["usage_state"] == "unverified" for a in attempts)
    return {
        "attempts": len(attempts),
        "successes": sum(a["status"] == "success" for a in attempts),
        "measured_attempts": len(measured),
        "unverified_attempts": unverified,
        "unavailable_attempts": len(attempts) - len(measured) - unverified,
        **{
            field: sum(a[field] for a in measured) if measured or not attempts else None
            for field in (*TOKEN_FIELDS[1:], "estimated_nano_usd")
        },
        "reserved_nano_usd": sum(a["reserved_nano_usd"] for a in attempts),
    }


@router.get("/gemini", response_model=AIUsageRead)
def gemini_usage(
    session: SessionDep,
    pagination: PaginationDep,
    month: Annotated[date | None, Query()] = None,
):
    now = utc_now()
    month = month or now.date().replace(day=1)
    if month.day != 1 or not 2000 <= month.year <= 9998:
        raise HTTPException(422, "Month must be the first day of a month between 2000 and 9998")
    start = datetime(month.year, month.month, 1, tzinfo=UTC)
    end = datetime(month.year + month.month // 12, month.month % 12 + 1, 1, tzinfo=UTC)
    # At most 24 admitted attempts per UTC day. One bounded month supplies both
    # aggregates and pagination from the same snapshot, without reading brief content.
    rows = session.scalars(
        select(AIBriefUsage)
        .where(AIBriefUsage.started_at >= start, AIBriefUsage.started_at < end)
        .order_by(AIBriefUsage.started_at.desc(), AIBriefUsage.id.desc())
    ).all()
    attempts, days = [], defaultdict(list)
    for row in rows:
        expired = row.status == "running" and row.lease_until <= now
        state = (
            "measured"
            if row.usage_validated
            else (
                "unverified"
                if any(getattr(row, key) is not None for key in TOKEN_FIELDS[1:])
                else "unavailable"
            )
        )
        attempt = {
            **{
                key: getattr(row, key)
                for key in (
                    "id",
                    "started_at",
                    "edition_at",
                    "dispatched_at",
                    "model",
                    "estimated_nano_usd",
                    "reserved_nano_usd",
                    *TOKEN_FIELDS,
                )
            },
            "finished_at": row.lease_until if expired else row.finished_at,
            "status": "interrupted" if expired else row.status,
            "error_code": "uncertain" if expired else row.error_code,
            "usage_state": state,
        }
        attempts.append(attempt)
        days[row.started_at.date()].append(attempt)
    budget = session.get(AIBriefBudget, month)
    return {
        "month": month,
        "summary": usage_summary(attempts),
        "days": [{"day": day, **usage_summary(items)} for day, items in days.items()],
        "attempts": {
            "items": attempts[pagination.offset : pagination.offset + pagination.limit],
            "total": len(attempts),
            "limit": pagination.limit,
            "offset": pagination.offset,
        },
        "budget_reserved_nano_usd": budget.reserved_nano_usd if budget else 0,
        "budget_limit_nano_usd": MONTHLY_NANO_USD,
    }


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
