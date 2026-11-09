"""Exercise the deployment SQL only on an isolated local PostgreSQL database."""

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.api.proposals import approve_proposal, create_proposal
from app.collection.service import Collector
from app.config import Settings
from app.db import create_database_engine
from app.invitations import claim_invitation
from app.models import LOCAL_OWNER_ID, AppUser, ReaderInvitation
from app.schemas import ProposalApprove, ProposalCreate

SQL_ROOT = Path(__file__).resolve().parents[1] / "sql"


def test_runtime_role_can_claim_readers_but_cannot_elevate_reactivate_or_migrate(database):
    if database.dialect.name != "postgresql":
        pytest.skip("Run with --postgres to validate role setup on a disposable server")
    created = False
    runtime = None
    try:
        with database.connect() as connection:
            raw = connection.connection.driver_connection
            raw.autocommit = True
            # The SQL itself refuses pre-existing roles; never overwrite a role from another task.
            raw.execute((SQL_ROOT / "create_app_role.sql").read_text())
            created = True
            raw.execute((SQL_ROOT / "enable_source_proposals.sql").read_text())
            raw.execute((SQL_ROOT / "check_app_role.sql").read_text())
            raw.execute("ALTER ROLE tnr_app PASSWORD 'tnr-role-test-only'")
        runtime = create_database_engine(
            database.url.set(username="tnr_app", password="tnr-role-test-only")
        )
        with runtime.begin() as connection:
            assert (
                connection.exec_driver_sql("SELECT count(*) FROM tnr.app_users").scalar_one() == 1
            )
            source_id = connection.exec_driver_sql(
                "INSERT INTO tnr.sources (name, feed_url, created_at) "
                "VALUES ('Role check', 'https://example.org/feed', now()) RETURNING id"
            ).scalar_one()
            connection.exec_driver_sql("UPDATE tnr.sources SET name = 'Updated'")
            assert source_id > 0
            connection.exec_driver_sql("DELETE FROM tnr.sources")
        subject = uuid4()
        with Session(runtime) as session, session.begin():
            session.add(
                ReaderInvitation(
                    email="friend@example.org",
                    display_name="Friend",
                    invited_by=LOCAL_OWNER_ID,
                )
            )

        class VerifiedGoogleIdentity:
            def matches(self, *args):
                return True

        with Session(runtime) as session:
            user_id = claim_invitation(
                session,
                subject,
                "friend@example.org",
                "test-token",
                VerifiedGoogleIdentity(),
            )
            assert session.get(AppUser, user_id).role == "reader"
        # Approval must work without UPDATE on app_users or DELETE on proposals.
        with Session(runtime) as session:
            proposal = create_proposal(
                ProposalCreate(name="Proposed", follow_on_approval=True),
                session.get(AppUser, user_id),
                session,
            )
            proposal_id = proposal.id
            from app.models import Source

            source = Source(name="Existing", feed_url="https://example.org/existing")
            session.add(source)
            session.commit()
            source_id = source.id
            approved = approve_proposal(
                proposal_id,
                ProposalApprove(source_id=source_id),
                session.get(AppUser, LOCAL_OWNER_ID),
                session,
                Collector(runtime, Settings(_env_file=None)),
            )
            assert approved.status == "approved" and approved.source_id == source_id
        for role, candidate in (("admin", uuid4()), ("reader", uuid4())):
            with pytest.raises(DBAPIError), Session(runtime) as session, session.begin():
                session.add(
                    AppUser(
                        supabase_subject=candidate, display_name="Forbidden", role=role, active=True
                    )
                )
                session.flush()
        # Even a consumed invitation must never authorize an administrator insert.
        admin_subject = uuid4()
        with Session(runtime) as session, session.begin():
            from app.db import utc_now

            session.add(
                ReaderInvitation(
                    email="admin@example.org",
                    display_name="Not admin",
                    invited_by=LOCAL_OWNER_ID,
                    accepted_subject=admin_subject,
                    accepted_at=utc_now(),
                )
            )
        with pytest.raises(DBAPIError), Session(runtime) as session, session.begin():
            session.add(
                AppUser(
                    supabase_subject=admin_subject,
                    display_name="Forbidden",
                    role="admin",
                    active=True,
                )
            )
            session.flush()
        for sql in (
            "UPDATE tnr.app_users SET active = true",
            "DELETE FROM tnr.app_users",
            "SELECT * FROM tnr.alembic_version",
            "CREATE TABLE tnr.forbidden (id integer)",
            "TRUNCATE tnr.sources CASCADE",
            "SET ROLE postgres",
            "DELETE FROM tnr.source_proposals",
            "TRUNCATE tnr.source_proposals",
        ):
            with pytest.raises(DBAPIError):
                with runtime.begin() as connection:
                    connection.exec_driver_sql(sql)
        with database.connect() as connection:
            assert (
                connection.exec_driver_sql(
                    "SELECT count(*) FROM pg_auth_members "
                    "WHERE member = (SELECT oid FROM pg_roles WHERE rolname = 'tnr_app')"
                ).scalar_one()
                == 0
            )
            assert (
                connection.exec_driver_sql(
                    "SELECT count(*) FROM pg_roles WHERE rolname = 'tnr_app' "
                    "AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication "
                    "OR rolbypassrls OR rolinherit)"
                ).scalar_one()
                == 0
            )
            for role in ("anon", "authenticated", "service_role"):
                assert (
                    connection.exec_driver_sql(
                        "SELECT has_schema_privilege(%s, 'tnr', 'USAGE')", (role,)
                    ).scalar_one()
                    is False
                )
    finally:
        if runtime is not None:
            runtime.dispose()
        if created:
            with database.begin() as connection:
                connection.exec_driver_sql("DROP OWNED BY tnr_app")
                connection.exec_driver_sql("DROP ROLE tnr_app")
