"""One sequential worker, owned by the application's lifespan, with no job queue."""

import logging
from dataclasses import dataclass
from threading import Event, Thread
from time import monotonic

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collection.service import Collector, RefreshRejected
from app.models import Source

logger = logging.getLogger(__name__)


@dataclass
class ScanResult:
    collected: int = 0
    failed: int = 0
    skipped: int = 0
    deferred: bool = False


class CollectionScheduler:
    def __init__(self, collector: Collector, poll_seconds: int) -> None:
        self.collector = collector
        self.poll_seconds = poll_seconds
        self._stop = Event()
        self._thread = Thread(target=self._run, name="feed-scheduler")

    def start(self) -> None:
        self._thread.start()
        logger.info("Collection scheduler started poll_seconds=%s", self.poll_seconds)

    def stop(self) -> None:
        """Wake an idle worker; let an active feed finish before returning."""
        self._stop.set()
        if self._thread.ident is not None:
            self._thread.join()
        logger.info("Collection scheduler stopped")

    def _run(self) -> None:
        # Delay the first scan as well: startup never waits for DB or network I/O.
        # A slow pass cannot overlap another pass or create missed-job backlogs.
        while not self._stop.wait(self.poll_seconds):
            try:
                self.run_once()
            except Exception as exc:
                # Keep the worker alive after storage failures. Do not log DB URLs.
                logger.error("Scheduled collection scan failed (%s)", type(exc).__name__)

    def run_once(
        self, *, max_sources: int | None = None, max_seconds: float | None = None
    ) -> ScanResult:
        result = ScanResult()
        started = monotonic()
        with Session(self.collector.engine) as session:
            source_ids = session.scalars(
                select(Source.id)
                .where(Source.enabled.is_(True))
                .order_by(Source.last_checked_at.asc().nullsfirst(), Source.id)
            ).all()
        # No session or transaction is held while another source downloads.
        for source_id in source_ids:
            if (
                self._stop.is_set()
                or (max_sources is not None and result.collected + result.failed >= max_sources)
                or (max_seconds is not None and monotonic() - started >= max_seconds)
            ):
                result.deferred = True
                break
            try:
                run = self.collector.refresh_if_due(source_id)
                if run is None:
                    result.skipped += 1
                elif run.status == "error":
                    result.failed += 1
                else:
                    result.collected += 1
            except RefreshRejected as exc:
                if exc.status_code == 409:
                    # Manual refresh or source changes have the gate; retry next scan.
                    logger.debug("Scheduled collection deferred: collector busy")
                    result.deferred = True
                    break
                result.skipped += 1
            except Exception as exc:
                result.failed += 1
                logger.error(
                    "Scheduled collection source=%s failed (%s)", source_id, type(exc).__name__
                )
        return result
