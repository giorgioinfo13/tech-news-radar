"""Durable, atomic admission; bounded network work happens outside transactions."""

import hashlib
import json
from asyncio import to_thread
from datetime import UTC, datetime, time, timedelta
from difflib import SequenceMatcher
from itertools import zip_longest
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.ai_content import DAILY_MESSAGE, AIUnavailable
from app.ai_gemini import (
    BUDGET_MESSAGE,
    MONTHLY_NANO_USD,
    Gemini,
    messages_for,
)
from app.collection.parsing import article_url, plain_text
from app.config import Settings
from app.db import UTCDateTime, lock_access_decisions
from app.models import AIBriefBudget, AIBriefControl, AIBriefJob, AppUser, Article, Category, Source

LEASE_SECONDS = 120
RESERVED_TOKENS = 4000


def database_now(session: Session) -> datetime:
    # PostgreSQL CURRENT_TIMESTAMP is frozen at transaction start, before a lock
    # wait. Admission/cooldowns need the wall clock after acquiring the gate.
    clock = (
        func.clock_timestamp(type_=UTCDateTime())
        if session.bind.dialect.name == "postgresql"
        else func.current_timestamp(type_=UTCDateTime())
    )
    return session.scalar(select(clock))


def reset_at(now: datetime) -> datetime:
    return datetime.combine(now.date() + timedelta(days=1), time(), UTC)


def normalized_url(url: str) -> str:
    parts = urlsplit(url)
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query)
        if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}
    ]
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/"),
            urlencode(sorted(query)),
            "",
        )
    )


def select_material(session: Session, category_id: int | None, now: datetime) -> list[dict]:
    if category_id is None:
        return select_digest_material(session, now)
    timestamp = func.coalesce(Article.published_at, Article.fetched_at)
    rows = session.execute(
        select(Article, Source.name)
        .join(Source)
        .where(
            Source.category_id == category_id,
            Source.enabled.is_(True),
            timestamp >= now - timedelta(hours=24),
            timestamp <= now,
        )
        .order_by(timestamp.desc(), Article.id.desc())
        .limit(200)
    )
    selected, urls, titles, domains = [], set(), [], {}
    for article, source_name in rows:
        url = article_url(article.url, "")
        if not url:
            continue
        title = plain_text(article.title[:4000], 160)
        title_key = " ".join(title.casefold().split())
        key, domain = normalized_url(url), urlsplit(url).hostname
        if not title or key in urls or domains.get(domain, 0) >= 3:
            continue
        if any(SequenceMatcher(None, title_key, old).ratio() >= 0.92 for old in titles):
            continue
        description = plain_text((article.description or "")[:6000], 450)
        candidate = {
            "id": article.id,
            "title": title,
            "url": url,
            "source": plain_text(source_name, 200),
            "description": description,
            "date": (article.published_at or article.fetched_at).isoformat(),
            "date_is_fetched": article.published_at is None,
        }
        selected.append(candidate)
        urls.add(key)
        titles.append(title_key)
        domains[domain] = domains.get(domain, 0) + 1
        if len(selected) == 12:
            break
    return selected


def select_digest_material(session: Session, now: datetime) -> list[dict]:
    categories = session.scalars(
        select(Category).order_by(Category.sort_order, Category.id).limit(64)
    ).all()
    groups = []
    for category in categories:
        group = select_material(session, category.id, now)
        groups.append(
            [
                {**a, "category_name": category.name}
                for a in group
                if len(a["description"]) >= 80 and len(a["description"].split()) >= 12
            ]
        )
    selected, urls, titles, domains = [], set(), [], {}
    for row in zip_longest(*groups):
        for candidate in row:
            if candidate is None:
                continue
            url = normalized_url(candidate["url"])
            title = " ".join(candidate["title"].casefold().split())
            domain = urlsplit(url).hostname
            if url in urls or domains.get(domain, 0) >= 3:
                continue
            if any(SequenceMatcher(None, title, previous).ratio() >= 0.92 for previous in titles):
                continue
            selected.append(candidate)
            urls.add(url)
            titles.append(title)
            domains[domain] = domains.get(domain, 0) + 1
            if len(selected) == 12:
                return selected
    return selected


def material_hash(material: list[dict]) -> str:
    values = sorted((a["id"], a["title"], a["description"]) for a in material)
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()


def edition_start(now: datetime) -> datetime:
    return now.replace(minute=0, second=0, microsecond=0)


def prompt_material(candidates: list[dict]) -> list[dict]:
    selected = []
    for candidate in candidates:
        # Short descriptions are useful links, but insufficient evidence for generation.
        if len(candidate["description"]) < 80 or len(candidate["description"].split()) < 12:
            continue
        try:
            messages_for([*selected, candidate])
        except AIUnavailable:
            continue
        selected.append(candidate)
    if len(selected) < 2 or sum(len(a["description"]) for a in selected) < 250:
        return []
    return selected


def public_article(article: dict, existing_ids: set[int]) -> dict:
    return {
        **{k: v for k, v in article.items() if k != "description"},
        "removed": article["id"] not in existing_ids,
    }


class BriefService:
    def __init__(self, engine, settings: Settings, provider: Gemini | None = None):
        self.engine = engine
        self.settings = settings
        self.provider = provider or Gemini(settings)

    def _open(self, session: Session, user_id: UUID | None):
        # Shared with operator revocation. Never retain this gate during HTTP.
        lock_access_decisions(session)
        if user_id is not None:
            user = session.get(AppUser, user_id, populate_existing=True)
            if user is None or not user.active:
                raise HTTPException(403, "User is not authorized")
        elif not self.settings.ai_digest_enabled:
            raise HTTPException(403, "Scheduled digest is not enabled")
        control = session.get(AIBriefControl, 1, with_for_update=True)
        now = database_now(session)
        if control is None:
            raise HTTPException(503, "AI brief migration is required")
        if control.lease_until and control.lease_until <= now:
            job = session.get(AIBriefJob, control.lease_id)
            if job and job.status == "running":
                job.status, job.error_code = "interrupted", "uncertain"
                job.finished_at = control.lease_until
            control.lease_id = control.lease_until = None
        if control.quota_day != now.date():
            control.quota_day = now.date()
            control.attempts = control.reserved_tokens = 0
            # A lease or cooldown can span midnight. Never clear it as a quota reset.
        if control.blocked_until and control.blocked_until <= now:
            control.blocked_code = control.blocked_until = None
        session.execute(delete(AIBriefJob).where(AIBriefJob.started_at < now - timedelta(days=7)))
        session.flush()
        return control, now

    def _state(self, session: Session, category_id: int | None, control, now) -> dict:
        digest = category_id is None
        category = session.get(Category, category_id) if not digest else None
        if not digest and category is None:
            raise HTTPException(404, "Category not found")
        jobs = session.scalars(
            select(AIBriefJob)
            .where(
                AIBriefJob.edition_at.is_not(None)
                if digest
                else AIBriefJob.category_id == category_id
            )
            .order_by(AIBriefJob.started_at.desc())
        ).all()
        today = [j for j in jobs if j.quota_day == now.date()]
        slot = edition_start(now)
        current = next((j for j in jobs if j.edition_at == slot), None) if digest else None
        success = (
            (current if current and current.status == "success" else None)
            if digest
            else next((j for j in today if j.status == "success"), None)
        )
        candidates = select_material(session, category_id, now)
        material = prompt_material(candidates)
        month = now.date().replace(day=1)
        budget = session.get(AIBriefBudget, month)
        reserved_money = budget.reserved_nano_usd if budget else 0
        next_month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
        money_reset = datetime.combine(next_month, time(), UTC)
        code, retry = "available", None
        if control.blocked_code == "safety_stop":
            code = "safety_stop"
        elif reserved_money + self.provider.reservation_nano_usd > MONTHLY_NANO_USD:
            code, retry = "monthly_budget", money_reset
        elif (
            control.attempts >= self.settings.ai_daily_attempts
            or control.reserved_tokens + RESERVED_TOKENS > self.settings.ai_daily_tokens
        ):
            code, retry = "daily_limit", reset_at(now)
        elif control.blocked_until and control.blocked_until > now:
            code, retry = control.blocked_code, control.blocked_until
        elif digest and not self.settings.ai_digest_enabled:
            code = "disabled"
        elif not digest:
            code = "scheduled_only"
        elif current and current.status == "running":
            code, retry = "busy", current.lease_until
        elif current:
            code, retry = ("cached" if success else "edition_attempted"), slot + timedelta(hours=1)
        elif success:
            code, retry = "cached", reset_at(now)
        elif self.settings.ai_briefs_enabled and self.provider.activation_blocked:
            code = "activation_required"
        elif not self.provider.enabled:
            code = "disabled"
        elif control.lease_id:
            code, retry = "busy", control.lease_until
        elif control.next_allowed_at and control.next_allowed_at > now:
            code, retry = "temporary_limit", control.next_allowed_at
        elif now + timedelta(seconds=60) >= reset_at(now):
            # Do not dispatch across the local UTC-day boundary.
            code, retry = "temporary_limit", reset_at(now)
        elif (
            jobs
            and jobs[0].status in {"error", "interrupted"}
            and (jobs[0].finished_at + timedelta(hours=1) > now)
        ):
            code, retry = "category_cooldown", jobs[0].finished_at + timedelta(hours=1)
        elif not material:
            code = "insufficient_material" if candidates else "empty"
        elif digest and any(j.material_hash == material_hash(material) for j in jobs):
            code = "unchanged"
        article_ids = {a["id"] for j in jobs for a in j.articles} | {a["id"] for a in candidates}
        existing = set(session.scalars(select(Article.id).where(Article.id.in_(article_ids))))
        briefs = [
            {
                "id": str(j.id),
                "category_name": j.category_name,
                "generated_at": j.finished_at.isoformat(),
                "window_start": j.window_start.isoformat(),
                "window_end": j.window_end.isoformat(),
                "summary": j.summary,
                "articles": [public_article(a, existing) for a in j.articles],
            }
            for j in jobs
            if j.status == "success"
        ]
        return {
            "category_id": category_id,
            "category_name": category.name if category else "Rassegna delle ultime 24 ore",
            "next_edition_at": (slot + timedelta(hours=1)).isoformat() if digest else None,
            "last_error_code": jobs[0].error_code if jobs else None,
            "code": code,
            "can_generate": code == "available",
            "retry_at": retry.isoformat() if retry else None,
            "quota_reset_at": reset_at(now).isoformat(),
            "budget_currency": "USD",
            "budget_limit_nano_usd": MONTHLY_NANO_USD,
            "budget_reserved_nano_usd": reserved_money,
            "budget_reset_at": money_reset.isoformat(),
            "attempts_remaining": max(
                0,
                min(
                    self.settings.ai_daily_attempts - control.attempts,
                    (self.settings.ai_daily_tokens - control.reserved_tokens) // RESERVED_TOKENS,
                ),
            ),
            "briefs": briefs,
            "articles": [public_article(a, existing) for a in candidates],
            "last_job_status": jobs[0].status if jobs else None,
        }

    def read(self, category_id: int | None, user_id: UUID | None) -> dict:
        with Session(self.engine) as session, session.begin():
            control, now = self._open(session, user_id)
            return self._state(session, category_id, control, now)

    def reserve(self, category_id: int | None, user_id: UUID | None) -> tuple[UUID | None, dict]:
        with Session(self.engine) as session, session.begin():
            control, now = self._open(session, user_id)
            state = self._state(session, category_id, control, now)
            # Compatibility routes can read old category briefs, never acquire new work.
            if category_id is not None:
                return None, {**state, "can_generate": False}
            if not state["can_generate"]:
                # Commit expired-lease recovery before reporting the stable state.
                return None, state
            material = prompt_material(select_material(session, category_id, now))
            month = now.date().replace(day=1)
            budget = session.get(AIBriefBudget, month, with_for_update=True)
            if budget is None:
                budget = AIBriefBudget(month=month, reserved_nano_usd=0)
                session.add(budget)
            budget.reserved_nano_usd += self.provider.reservation_nano_usd
            job_id = uuid4()
            until = now + timedelta(seconds=LEASE_SECONDS)
            session.add(
                AIBriefJob(
                    id=job_id,
                    category_id=category_id,
                    category_name=state["category_name"],
                    edition_at=edition_start(now),
                    material_hash=material_hash(material),
                    quota_day=now.date(),
                    started_at=now,
                    window_start=now - timedelta(hours=24),
                    window_end=now,
                    lease_until=until,
                    status="running",
                    articles=material,
                    model=self.provider.model,
                    budget_month=month,
                    reserved_nano_usd=self.provider.reservation_nano_usd,
                )
            )
            control.attempts += 1
            control.reserved_tokens += RESERVED_TOKENS
            control.lease_id, control.lease_until = job_id, until
            control.next_allowed_at = now + timedelta(seconds=60)
            return job_id, state

    def dispatch_material(
        self, job_id: UUID, user_id: UUID | None, *, claim: bool = False
    ) -> list[dict]:
        with Session(self.engine) as session, session.begin():
            control, now = self._open(session, user_id)
            job = session.get(AIBriefJob, job_id)
            if control.blocked_code == "safety_stop":
                raise AIUnavailable("safety_stop")
            if (
                control.lease_id != job_id
                or job is None
                or job.status != "running"
                or job.quota_day != now.date()
                or now + timedelta(seconds=30) >= reset_at(now)
            ):
                raise AIUnavailable("uncertain", 3600)
            if job.edition_at != edition_start(now):
                raise AIUnavailable("uncertain", 3600)
            if claim:
                if job.dispatched_at is not None:
                    raise AIUnavailable("uncertain", 3600)
                job.dispatched_at = now
            # No automatic replacement with different articles after acquisition.
            ids = [a["id"] for a in job.articles]
            remaining = set(
                session.scalars(
                    select(Article.id)
                    .join(Source)
                    .where(
                        Article.id.in_(ids),
                        Source.enabled.is_(True),
                    )
                )
            )
            if remaining != set(ids):
                raise AIUnavailable("insufficient_material", 3600)
            return job.articles

    def finish(self, job_id: UUID, result: dict | None, failure: AIUnavailable | None):
        with Session(self.engine) as session, session.begin():
            lock_access_decisions(session)
            control = session.get(AIBriefControl, 1, with_for_update=True)
            job = session.get(AIBriefJob, job_id)
            now = database_now(session)
            # A late response can reveal an accounting violation after lease expiry.
            # Stop future work without overwriting a different job's ownership/status.
            if job and failure and failure.code == "safety_stop":
                control.blocked_code, control.blocked_until = "safety_stop", None
            if (
                not job
                or job.status != "running"
                or control.lease_id != job_id
                or job.lease_until <= now
            ):
                return
            job.finished_at = now
            if failure:
                job.status, job.error_code = "error", failure.code
                # Only locally defined labels/numbers, never provider payloads or secrets.
                job.diagnostics = {
                    key: value
                    for key, value in failure.diagnostics.items()
                    if key
                    in {
                        "http_status",
                        "retry_after_seconds",
                        "input_tokens",
                        "output_tokens",
                        "thought_tokens",
                        "total_tokens",
                        "counted_tokens",
                        "model_matches",
                        "thoughts_missing",
                    }
                    and type(value) is int
                    and 0 <= value <= 10_000_000
                }
                for key, allowed in {
                    "contract_issue": {
                        "usage_or_model_mismatch",  # Retain compatibility with older jobs.
                        "model_mismatch",
                        "invalid_usage",
                        "input_count_mismatch",
                        "output_limit",
                        "total_mismatch",
                        "unexpected_cache_or_tools",
                        "unexpected_modality",
                        "reservation_exceeded",
                        "oversized_response",
                        "invalid_envelope",
                        "invalid_token_count",
                    },
                    "output_issue": {
                        "incomplete_response",
                        "response_shape",
                        "invalid_json",
                        "invalid_schema",
                        "duplicate_citations",
                        "unknown_citations",
                        "summary_word_count",
                        "unsafe_summary",
                    },
                }.items():
                    if (
                        isinstance(failure.diagnostics.get(key), str)
                        and failure.diagnostics[key] in allowed
                    ):
                        job.diagnostics[key] = failure.diagnostics[key]
                if (
                    failure.code not in {"insufficient_material", "disabled"}
                    and control.blocked_code != "safety_stop"
                ):
                    control.blocked_code = failure.code
                    control.blocked_until = (
                        reset_at(now)
                        if failure.code == "daily_limit"
                        else now + timedelta(seconds=failure.delay)
                    )
                # Outcome could be uncertain. Preserve the reservation and full lease.
            else:
                job.status, job.summary, job.articles = (
                    "success",
                    result["summary"],
                    result["articles"],
                )
                control.lease_id = control.lease_until = None

    async def generate(self, category_id: int | None, user_id: UUID | None) -> dict:
        job_id, state = await to_thread(self.reserve, category_id, user_id)
        if job_id is None:
            if state["code"] in {"daily_limit", "monthly_budget"}:
                raise HTTPException(
                    429,
                    {
                        "code": state["code"],
                        "message": BUDGET_MESSAGE
                        if state["code"] == "monthly_budget"
                        else DAILY_MESSAGE,
                        "retry_at": state["retry_at"],
                    },
                )
            return state
        try:
            await self.provider.preflight()
            material = await to_thread(self.dispatch_material, job_id, user_id)

            async def guard():
                return await to_thread(self.dispatch_material, job_id, user_id, claim=True)

            result = await self.provider.generate(material, before_generate=guard)
        except AIUnavailable as exc:
            await to_thread(self.finish, job_id, None, exc)
        except HTTPException:
            await to_thread(self.finish, job_id, None, AIUnavailable("disabled", 3600))
            raise
        else:
            await to_thread(self.finish, job_id, result, None)
        state = await to_thread(self.read, category_id, user_id)
        if state["code"] in {"daily_limit", "monthly_budget"}:
            raise HTTPException(
                429,
                {
                    "code": state["code"],
                    "message": BUDGET_MESSAGE
                    if state["code"] == "monthly_budget"
                    else DAILY_MESSAGE,
                    "retry_at": state["retry_at"],
                },
            )
        return state
