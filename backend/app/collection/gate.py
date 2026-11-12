"""Non-queued, crash-released collection gate shared by collector instances."""

from contextlib import contextmanager

from sqlalchemy import text


@contextmanager
def database_gate(engine):
    # Session advisory locks require the existing direct/session-pooler connection.
    # AUTOCOMMIT avoids keeping a database transaction open across feed HTTP.
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
