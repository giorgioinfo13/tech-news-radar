"""One sequential worker, owned by the application's lifespan, with no job queue."""

import logging
from threading import Event, Thread

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collection.service import Collector, RefreshRejected
from app.models import Source

logger = logging.getLogger(__name__)


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

    def run_once(self) -> None:
        with Session(self.collector.engine) as session:
            source_ids = session.scalars(
                select(Source.id)
                .where(Source.enabled.is_(True))
                .order_by(Source.last_checked_at.asc().nullsfirst(), Source.id)
            ).all()
        # No session or transaction is held while another source downloads.
        for source_id in source_ids:
            if self._stop.is_set():
                break
            try:
                self.collector.refresh_if_due(source_id)
            except RefreshRejected as exc:
                if exc.status_code == 409:
                    # Manual refresh or source changes have the gate; retry next scan.
                    logger.debug("Scheduled collection deferred: collector busy")
                    break
            except Exception as exc:
                logger.error(
                    "Scheduled collection source=%s failed (%s)", source_id, type(exc).__name__
                )
