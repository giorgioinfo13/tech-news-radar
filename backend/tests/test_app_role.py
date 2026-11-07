"""Exercise the deployment SQL only on an isolated local PostgreSQL database."""

from pathlib import Path

import pytest
from sqlalchemy.exc import DBAPIError

from app.db import create_database_engine

SQL_ROOT = Path(__file__).resolve().parents[1] / "sql"


def test_runtime_role_can_use_app_data_but_cannot_provision_or_migrate(database):
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
        for sql in (
            "UPDATE tnr.app_users SET active = true",
            "DELETE FROM tnr.app_users",
            "SELECT * FROM tnr.alembic_version",
            "CREATE TABLE tnr.forbidden (id integer)",
            "TRUNCATE tnr.sources CASCADE",
            "SET ROLE postgres",
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
