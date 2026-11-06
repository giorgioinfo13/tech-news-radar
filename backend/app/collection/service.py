"""Short database transactions around a synchronous, single-process collector."""

import logging
import math
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from threading import Lock

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.collection.download import FeedDownloader, FeedError
from app.collection.parsing import parse_feed, url_key
from app.config import Settings
from app.db import utc_now
from app.models import Article, CollectionRun, Source

logger = logging.getLogger(__name__)


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
        # Source PATCH/DELETE use the same gate. No DB lock is held during HTTP I/O.
        if not self._lock.acquire(blocking=False):
            raise RefreshRejected(409, "A collection or source change is already in progress")
        try:
            yield
        finally:
            self._lock.release()

    def refresh(self, source_id: int) -> CollectionRun:
        with self.exclusive():
            return self._refresh(source_id)

    def refresh_if_due(self, source_id: int) -> CollectionRun | None:
        """Recheck current source settings under the same gate as manual refresh."""
        with self.exclusive():
            with Session(self.engine) as session:
                source = session.get(Source, source_id)
                if source is None or not source.enabled:
                    return None
                delay = max(source.refresh_interval_minutes * 60, self._cooldown(source))
                if (
                    source.last_checked_at
                    and (utc_now() - source.last_checked_at).total_seconds() < delay
                ):
                    return None
            return self._refresh(source_id)

    @staticmethod
    def _cooldown(source: Source) -> int:
        return min(3600, 30 * 2 ** min(source.consecutive_failures, 7))

    def _refresh(self, source_id: int) -> CollectionRun:
        now = utc_now()
        with Session(self.engine) as session:
            source = session.get(Source, source_id)
            if source is None:
                raise RefreshRejected(404, "Source not found")
            if not source.enabled:
                raise RefreshRejected(409, "Enable the source before refreshing it")
            cooldown = self._cooldown(source)
            if source.last_checked_at:
                remaining = cooldown - (now - source.last_checked_at).total_seconds()
                if remaining > 0:
                    raise RefreshRejected(
                        429, "Source refresh is temporarily rate limited", math.ceil(remaining)
                    )
            # Recover runs interrupted by a previous process, only when this source is refreshed.
            for previous in session.scalars(
                select(CollectionRun).where(
                    CollectionRun.source_id == source_id, CollectionRun.status == "running"
                )
            ):
                previous.status = "error"
                previous.finished_at = max(now, previous.started_at)
                previous.error_message = "Collection interrupted before completion"
            run = CollectionRun(source_id=source_id, started_at=now)
            session.add(run)
            session.flush()
            run_id = run.id
            url, etag, modified = source.feed_url, source.etag, source.last_modified
            session.commit()
        try:
            download = self.downloader.fetch(url, etag, modified)
            parsed = (
                None
                if download.not_modified
                else parse_feed(download.body, download.url, self.settings.feed_max_entries)
            )
            with Session(self.engine, expire_on_commit=False) as session:
                source = session.get(Source, source_id)
                run = session.get(CollectionRun, run_id)
                if parsed is not None:
                    existing = session.execute(
                        select(Article.guid, Article.url).where(Article.source_id == source_id)
                    )
                    guids, urls = set(), set()
                    for guid, stored_url in existing:
                        if guid:
                            guids.add(guid)
                        urls.add(url_key(stored_url))
                    run.articles_seen = parsed.seen
                    for entry in parsed.entries:
                        key = url_key(entry.url)
                        if (entry.guid and entry.guid in guids) or key in urls:
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
                source.consecutive_failures += 1
                session.commit()
                logger.warning(
                    "Collection source=%s run=%s status=error reason=%s", source_id, run_id, message
                )
                return run
