"""Opposite bulk choices from two tabs must finish in one transaction order."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.personal import subscribe_all, unsubscribe_all
from app.models import LOCAL_OWNER_ID, AppUser, Source, Subscription


@pytest.mark.parametrize("first", ["follow", "unfollow"])
def test_opposite_bulk_choices_are_serialized(database, monkeypatch, first):
    with Session(database) as session, session.begin():
        sources = [
            Source(name=f"Source {i}", feed_url=f"https://example.org/{i}") for i in range(2)
        ]
        session.add_all(sources)
        session.flush()
        session.add(Subscription(user_id=LOCAL_OWNER_ID, source_id=sources[0].id))

    first_ready, second_started, release = Event(), Event(), Event()
    pids = {}
    original_commit = Session.commit

    def commit(session):
        if session.info.get("operation") == first:
            first_ready.set()
            assert release.wait(10), "First transaction was not released"
        original_commit(session)

    monkeypatch.setattr(Session, "commit", commit)

    def run(operation):
        with database.connect() as connection, Session(connection) as session:
            pids[operation] = connection.connection.driver_connection.info.backend_pid
            session.info["operation"] = operation
            if operation != first:
                second_started.set()
            action = subscribe_all if operation == "follow" else unsubscribe_all
            return action(session.get(AppUser, LOCAL_OWNER_ID), session)

    second = "unfollow" if first == "follow" else "follow"
    with ThreadPoolExecutor(max_workers=2) as executor:
        before = executor.submit(run, first)
        try:
            assert first_ready.wait(10)
            after = executor.submit(run, second)
            assert second_started.wait(10)
            deadline = monotonic() + 5
            while monotonic() < deadline:
                with database.connect() as observer:
                    waiting = observer.scalar(
                        text(
                            "SELECT wait_event = 'advisory' FROM pg_stat_activity WHERE pid = :pid"
                        ),
                        {"pid": pids[second]},
                    )
                if waiting:
                    break
                sleep(0.01)
            else:
                pytest.fail("Second bulk choice did not wait for the first transaction")
        finally:
            release.set()
        assert before.result(timeout=10) == {"changed": 1}
        assert after.result(timeout=10) == {"changed": 2}
    with Session(database) as session:
        total = session.scalar(select(func.count()).select_from(Subscription))
        assert total == (0 if second == "unfollow" else 2)
