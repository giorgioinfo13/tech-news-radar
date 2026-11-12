"""Bounded external scans using the application's existing collector."""

import math
from threading import Event, Lock
from time import monotonic

from app.collection.scheduler import CollectionScheduler, ScanResult
from app.collection.service import Collector, RefreshRejected


class CollectionTrigger:
    def __init__(self, collector: Collector) -> None:
        # Reuse the due-source scan, but never start its timer thread.
        self.scheduler = CollectionScheduler(collector, 30)
        self._lock = Lock()
        self._stopped = Event()
        self._next_allowed = 0.0

    def run(self) -> ScanResult:
        if not self._lock.acquire(blocking=False):
            raise RefreshRejected(409, "A collection scan is already in progress", 300)
        try:
            if self._stopped.is_set():
                raise RefreshRejected(503, "Collection is stopping", 300)
            remaining = self._next_allowed - monotonic()
            if remaining > 0:
                raise RefreshRejected(
                    429, "Collection scan is temporarily rate limited", math.ceil(remaining)
                )
            try:
                # The time budget is checked between feeds. An active download must finish.
                return self.scheduler.run_once(max_sources=100, max_seconds=240)
            finally:
                # Also throttle empty and failed scans; never keep a DB transaction open here.
                self._next_allowed = monotonic() + 300
        finally:
            self._lock.release()

    def stop(self) -> None:
        self._stopped.set()
        self.scheduler.stop()
        # Finish the active feed before the application disposes its engine.
        with self._lock:
            pass
