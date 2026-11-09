"""Real PostgreSQL ordering between operator revocation and proposal approval."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.access import set_access
from app.api.proposals import approve_proposal, create_proposal
from app.collection.download import Download, FeedDownloader
from app.collection.service import Collector
from app.config import Settings
from app.models import LOCAL_OWNER_ID, AppUser, Source, SourceProposal, Subscription
from app.schemas import ProposalApprove, ProposalCreate


@pytest.mark.parametrize("first", ["approval", "revocation"])
def test_revocation_and_approval_have_one_transaction_order(database, monkeypatch, first):
    if database.dialect.name != "postgresql":
        pytest.skip("Run with --postgres to check cross-connection advisory lock ordering")

    subject, reader_id = uuid4(), uuid4()
    with Session(database) as session:
        reader = AppUser(id=reader_id, supabase_subject=subject, display_name="Reader", active=True)
        session.add(reader)
        session.commit()
        proposal_id = create_proposal(
            ProposalCreate(name="News", follow_on_approval=True), reader, session
        ).id

    monkeypatch.setattr(
        FeedDownloader,
        "fetch",
        lambda self, url: Download(
            b'<rss version="2.0"><channel><title>News</title></channel></rss>', url
        ),
    )
    first_holds, release = Event(), Event()
    started = {operation: Event() for operation in ("approval", "revocation")}
    pids = {}
    normal_get = Session.get

    def pause_after_proposer_check(session, model, identity, **kwargs):
        result = normal_get(session, model, identity, **kwargs)
        if (
            first == "approval"
            and model is AppUser
            and identity == reader_id
            and kwargs.get("populate_existing")
        ):
            first_holds.set()
            assert release.wait(10), "Approval was not released"
        return result

    monkeypatch.setattr(Session, "get", pause_after_proposer_check)

    def approve():
        # Pin the connection across the API's preflight rollbacks so its PID is stable.
        with database.connect() as connection, Session(connection) as session:
            pids["approval"] = connection.connection.driver_connection.info.backend_pid
            started["approval"].set()
            try:
                result = approve_proposal(
                    proposal_id,
                    ProposalApprove(name="News", feed_url="https://example.org/feed"),
                    session.get(AppUser, LOCAL_OWNER_ID),
                    session,
                    Collector(database, Settings(_env_file=None)),
                )
                return result.status
            except HTTPException as exc:
                return exc.status_code

    def revoke():
        with database.connect() as connection, Session(connection) as session:
            pids["revocation"] = connection.connection.driver_connection.info.backend_pid
            started["revocation"].set()
            set_access(session, subject, active=False)
            session.flush()
            observed_status = session.get(SourceProposal, proposal_id).status
            if first == "revocation":
                first_holds.set()
                assert release.wait(10), "Revocation was not released"
            session.commit()
            return observed_status

    operations = {"approval": approve, "revocation": revoke}
    second = "revocation" if first == "approval" else "approval"
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {first: pool.submit(operations[first])}
        try:
            assert first_holds.wait(5)
            futures[second] = pool.submit(operations[second])
            assert started[second].wait(5)
            # Observe the database waiter, not just a sleep or thread start signal.
            deadline = monotonic() + 5
            blocked = False
            while monotonic() < deadline and not futures[second].done():
                with database.connect() as connection:
                    blocked = connection.scalar(
                        text(
                            "SELECT EXISTS (SELECT 1 FROM pg_locks "
                            "WHERE pid = :pid AND locktype = 'advisory' AND NOT granted)"
                        ),
                        {"pid": pids[second]},
                    )
                if blocked:
                    break
                sleep(0.01)
            assert blocked, f"{second} did not wait for the first transaction"
        finally:
            release.set()
        results = {operation: future.result(timeout=5) for operation, future in futures.items()}

    with Session(database) as session:
        assert session.get(AppUser, reader_id).active is False
        proposal = session.get(SourceProposal, proposal_id)
        if first == "approval":
            assert results == {"approval": "approved", "revocation": "approved"}
            assert proposal.status == "approved"
            assert session.scalar(select(func.count()).select_from(Source)) == 1
            assert session.scalar(select(func.count()).select_from(Subscription)) == 1
        else:
            assert results == {"revocation": "pending", "approval": 409}
            assert proposal.status == "pending"
            assert proposal.decided_at is None
            assert session.scalar(select(func.count()).select_from(Source)) == 0
            assert session.scalar(select(func.count()).select_from(Subscription)) == 0
