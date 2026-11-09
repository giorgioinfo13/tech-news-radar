"""Non-queued, crash-released collection gate shared by collector instances."""

import fcntl
import os
from contextlib import contextmanager

from sqlalchemy import text


@contextmanager
def database_gate(engine):
    # Session advisory locks require the existing direct/session-pooler connection.
    # AUTOCOMMIT avoids keeping a database transaction open across feed HTTP.
    if engine.dialect.name == "postgresql":
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            acquired = connection.scalar(text("SELECT pg_try_advisory_lock(746674, 10)"))
            try:
                yield acquired
            finally:
                if acquired:
                    try:
                        connection.execute(text("SELECT pg_advisory_unlock(746674, 10)"))
                    except Exception:
                        connection.invalidate()
                        raise
    else:
        # File-backed SQLite only; the application already requires one local database.
        # OS locks survive suspension and are released on exit, without stale lease rows.
        path = engine.url.database
        if not path or path == ":memory:":
            raise RuntimeError("Collection requires a file-backed database")
        descriptor = os.open(f"{path}.collection.lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
            else:
                try:
                    yield True
                finally:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)
