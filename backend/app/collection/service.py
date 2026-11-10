"""Short database transactions around a synchronous, single-process collector."""

import logging
import math
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from threading import Lock
from time import monotonic
from uuid import UUID

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.collection.download import FeedDownloader, FeedError
from app.collection.gate import database_gate
from app.collection.parsing import parse_feed, url_key
from app.config import Settings
from app.db import utc_now
from app.models import AppUser, Article, CollectionRun, Source, Subscription

logger = logging.getLogger(__name__)
MANUAL_INTERVAL_SECONDS = 900
MANUAL_MAX_SOURCES = 10
MANUAL_MAX_SECONDS = 45


@dataclass
class RefreshSummary:
    checked: int = 0
    added: int = 0
    failed: int = 0
    skipped: int = 0
    deferred: int = 0
    retry_after: int | None = None


class RefreshRejected(Exception):
    def __init__(self, status_code: int, detail: str, retry_after: int | None = None) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.retry_after = retry_after


class Collector:
    def __init__(self, engine: Engine, settings: Settings) -> None:
        self.engine = engine
        self.settings = settings
        self.downloader = FeedDownloader(settings)
        self._lock = Lock()

    @contextmanager
    def exclusive(self) -> Iterator[None]:
        # Source writes and every collection path share this non-queued gate.
        if not self._lock.acquire(blocking=False):
            raise RefreshRejected(409, "A collection or source change is already in progress")
        try:
            with database_gate(self.engine) as acquired:
                if not acquired:
                    raise RefreshRejected(
                        409, "A collection or source change is already in progress"
                    )
                yield
        finally:
            self._lock.release()

    @staticmethod
    def authorize(session: Session, user_id: UUID, source_id: int | None = None) -> AppUser:
        user = session.get(AppUser, user_id)
        if user is None or not user.active:
            raise RefreshRejected(403, "User is not authorized")
        if source_id is not None and user.role != "admin":
            if session.get(Subscription, (user_id, source_id)) is None:
                raise RefreshRejected(403, "Follow this source before refreshing it")
        return user

    def refresh(self, source_id: int, *, user_id: UUID | None = None) -> CollectionRun:
        with self.exclusive():
            return self._refresh(source_id, user_id=user_id)

    def refresh_if_due(self, source_id: int) -> CollectionRun | None:
        """Recheck source settings under the same gate as manual refresh."""
        with self.exclusive():
            with Session(self.engine) as session:
                source = session.get(Source, source_id)
                if source is None or not source.enabled or self.remaining(source, scheduled=True):
                    return None
            return self._refresh(source_id)

    @staticmethod
    def _cooldown(source: Source) -> int:
        return max(
            MANUAL_INTERVAL_SECONDS, min(3600, 30 * 2 ** min(source.consecutive_failures, 7))
        )

    def remaining(self, source: Source, *, scheduled: bool = False) -> int:
        dates = [date for date in (source.last_attempt_at, source.last_checked_at) if date]
        if not dates:
            return 0
        delay = self._cooldown(source)
        if scheduled:
            delay = max(delay, source.refresh_interval_minutes * 60)
        return max(0, math.ceil(delay - (utc_now() - max(dates)).total_seconds()))

    def refresh_news(self, user_id: UUID) -> RefreshSummary:
        """Collect authorized sources once, sequentially, without an in-memory job queue."""
        result = RefreshSummary()
        deadline = monotonic() + MANUAL_MAX_SECONDS
        with self.exclusive():
            with Session(self.engine) as session:
                user = self.authorize(session, user_id)
                statement = select(Source).order_by(
                    Source.last_attempt_at.asc().nullsfirst(),
                    Source.last_checked_at.asc().nullsfirst(),
                    Source.id,
                )
                if user.role != "admin":
                    statement = statement.join(Subscription).where(Subscription.user_id == user_id)
                candidates = []
                for source in session.scalars(statement):
                    remaining = self.remaining(source)
                    if not source.enabled or remaining:
                        result.skipped += 1
                        if source.enabled and remaining:
                            result.retry_after = min(result.retry_after or remaining, remaining)
                    else:
                        candidates.append(source.id)
            for index, source_id in enumerate(candidates):
                if result.checked >= MANUAL_MAX_SOURCES or monotonic() >= deadline:
                    result.deferred = len(candidates) - index
                    break
                try:
                    run = self._refresh(source_id, user_id=user_id, deadline=deadline)
                except RefreshRejected as exc:
                    if exc.status_code == 403:
                        raise
                    result.skipped += 1
                    continue
                result.checked += 1
                result.added += run.articles_added
                result.failed += int(run.status == "error")
            if result.deferred:
                result.retry_after = None
        return result

    def _refresh(
        self, source_id: int, *, user_id: UUID | None = None, deadline: float | None = None
    ) -> CollectionRun:
        now = utc_now()
        with Session(self.engine) as session:
            if user_id is not None:
                self.authorize(session, user_id, source_id)
            source = session.get(Source, source_id)
            if source is None:
                raise RefreshRejected(404, "Source not found")
            if not source.enabled:
                raise RefreshRejected(409, "Enable the source before refreshing it")
            remaining = self.remaining(source)
            if remaining:
                raise RefreshRejected(429, "Source refresh is temporarily rate limited", remaining)
            # Recover runs interrupted by a previous process, only when this source is refreshed.
            for previous in session.scalars(
                select(CollectionRun).where(
                    CollectionRun.source_id == source_id, CollectionRun.status == "running"
                )
            ):
                previous.status = "error"
                previous.finished_at = max(now, previous.started_at)
                previous.error_message = "Collection interrupted before completion"
            # Reserve before network I/O. An interrupted attempt remains counted after restart.
            source.last_attempt_at = now
            source.consecutive_failures += 1
            run = CollectionRun(source_id=source_id, started_at=now)
            session.add(run)
            session.flush()
            run_id = run.id
            url, etag, modified = source.feed_url, source.etag, source.last_modified
            session.commit()
        try:
            download = (
                self.downloader.fetch(url, etag, modified)
                if deadline is None
                else self.downloader.fetch(url, etag, modified, deadline=deadline)
            )
            parsed = (
                None
                if download.not_modified
                else parse_feed(download.body, download.url, self.settings.feed_max_entries)
            )
            if deadline is not None and monotonic() >= deadline:
                raise FeedError("Feed download exceeded its time budget")
            with Session(self.engine, expire_on_commit=False) as session:
                source = session.get(Source, source_id)
                run = session.get(CollectionRun, run_id)
                if parsed is not None:
                    existing = session.scalars(
                        select(Article).where(Article.source_id == source_id)
                    ).all()
                    by_url = {url_key(article.url): article for article in existing}
                    guids, urls = set(), set()
                    for article in existing:
                        guid, stored_url = article.guid, article.url
                        if guid:
                            guids.add(guid)
                        urls.add(url_key(stored_url))
                    run.articles_seen = parsed.seen
                    for entry in parsed.entries:
                        key = url_key(entry.url)
                        if (entry.guid and entry.guid in guids) or key in urls:
                            stored = by_url.get(key)
                            if stored is not None and entry.discussion_url:
                                stored.discussion_url = entry.discussion_url
                                if stored.description == "Comments":
                                    stored.description = None
                            continue
                        session.add(Article(source_id=source_id, **asdict(entry)))
                        if entry.guid:
                            guids.add(entry.guid)
                        urls.add(key)
                        run.articles_added += 1
                run.status = "not_modified" if download.not_modified else "success"
                run.finished_at = max(utc_now(), run.started_at)
                source.last_checked_at = source.last_success_at = run.finished_at
                source.last_error = None
                source.consecutive_failures = 0
                source.etag, source.last_modified = download.etag, download.last_modified
                session.commit()
                logger.info(
                    "Collection source=%s run=%s status=%s seen=%s added=%s",
                    source_id,
                    run_id,
                    run.status,
                    run.articles_seen,
                    run.articles_added,
                )
                return run
        except Exception as exc:
            # Persist diagnostics after rollback, without exposing URLs or raw exceptions.
            message = str(exc) if isinstance(exc, FeedError) else "Unexpected collection failure"
            if not isinstance(exc, FeedError):
                logger.error(
                    "Collection source=%s run=%s failed (%s)", source_id, run_id, type(exc).__name__
                )
            with Session(self.engine, expire_on_commit=False) as session:
                source = session.get(Source, source_id)
                run = session.get(CollectionRun, run_id)
                run.status = "error"
                run.finished_at = max(utc_now(), run.started_at)
                run.error_message = message
                source.last_checked_at = run.finished_at
                source.last_error = message
                session.commit()
                logger.warning(
                    "Collection source=%s run=%s status=error reason=%s", source_id, run_id, message
                )
                return run
