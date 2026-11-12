"""Release checks use mocked hosting APIs and disposable migration databases."""

import importlib.util
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import URL, make_url

from app.db import create_database_engine
from app.release_migrate import migrate, operator_url

spec = importlib.util.spec_from_file_location(
    "release_render", Path(__file__).resolve().parents[2] / "scripts/release_render.py"
)
render = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render)


def test_operator_url_pins_supabase_project_and_verified_tls(tmp_path, monkeypatch):
    project_ref = "a" * 20
    ca = tmp_path / "supabase-ca.crt"
    ca.write_text("test certificate", encoding="utf-8")
    value = URL.create(
        "postgresql+psycopg",
        username=f"postgres.{project_ref}",
        password="private-test-password",
        host="aws-0-eu-west-2.pooler.supabase.com",
        port=5432,
        database="postgres",
        query={"sslmode": "verify-full", "sslrootcert": str(ca)},
    )
    assert operator_url(value.render_as_string(hide_password=False), project_ref).host == value.host
    with pytest.raises(ValueError, match="named Supabase project"):
        operator_url(
            value.set(username="postgres.other").render_as_string(hide_password=False),
            project_ref,
        )
    monkeypatch.setenv("PGOPTIONS", "-c search_path=public")
    with pytest.raises(ValueError, match="libpq"):
        operator_url(value.render_as_string(hide_password=False), project_ref)


@pytest.mark.parametrize(
    "outcome", ["live", "build_failed", "wrong_commit", "auto_deploy", "wrong_url", "post_timeout"]
)
def test_render_waits_for_exact_commit(monkeypatch, outcome):
    sha = "a" * 40
    for key, value in {
        "GITHUB_SHA": sha,
        "RENDER_SERVICE_ID": "srv-test",
        "RENDER_API_KEY": "test-only",
        "TNR_BACKEND_URL": "https://test.onrender.com",
    }.items():
        monkeypatch.setenv(key, value)
    calls = []

    def request(url, token=None, payload=None):
        calls.append((url, payload))
        if url.endswith("srv-test"):
            return {
                "autoDeploy": "yes" if outcome == "auto_deploy" else "no",
                "branch": "main",
                "serviceDetails": {
                    "url": "https://wrong.onrender.com"
                    if outcome == "wrong_url"
                    else "https://test.onrender.com"
                },
            }
        if payload:
            assert payload == {"commitId": sha}
            if outcome == "post_timeout":
                raise TimeoutError("Simulated uncertain acceptance")
            return {"id": "dep-test"}
        if url.endswith("health"):
            return {"status": "ok"}
        return {
            "status": "live" if outcome != "build_failed" else outcome,
            "commit": {"id": "b" * 40 if outcome == "wrong_commit" else sha},
        }

    monkeypatch.setattr(render, "request", request)
    if outcome == "live":
        render.release()
        assert calls[-1][0].endswith("/api/health")
    else:
        with pytest.raises((RuntimeError, ValueError, TimeoutError)):
            render.release()
        assert not any(url.endswith("health") for url, _ in calls)
        assert sum(payload is not None for _, payload in calls) == (
            0 if outcome in {"auto_deploy", "wrong_url"} else 1
        )


def test_migration_supplied_connection_rolls_back(migration_config):
    """Alembic must not commit a transaction owned by the release caller."""
    engine = create_database_engine(migration_config.get_main_option("sqlalchemy.url"))
    try:
        command.upgrade(migration_config, "0010")
        with engine.connect() as connection:
            transaction = connection.begin()
            migration_config.attributes["connection"] = connection
            command.upgrade(migration_config, "head")
            transaction.rollback()
            assert (
                connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
                == "0010"
            )
    finally:
        engine.dispose()


def test_release_migration_and_grant_are_repeatable(migration_config):
    url = make_url(migration_config.get_main_option("sqlalchemy.url"))
    command.upgrade(migration_config, "0010")
    engine = create_database_engine(url)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE ROLE tnr_app")
    try:
        migrate(url)
        migrate(url)
        with engine.connect() as connection:
            assert (
                connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
                == "0013"
            )
            assert connection.exec_driver_sql(
                "SELECT has_column_privilege('tnr_app', 'tnr.app_users', 'last_seen_at', 'UPDATE')"
            ).scalar()
            assert connection.exec_driver_sql(
                "SELECT has_table_privilege('tnr_app', 'tnr.ai_brief_usage', "
                "'SELECT,INSERT,UPDATE')"
            ).scalar()
            assert not connection.exec_driver_sql(
                "SELECT has_table_privilege('tnr_app', 'tnr.ai_brief_usage', 'DELETE')"
            ).scalar()
            assert not connection.exec_driver_sql(
                "SELECT has_column_privilege('tnr_app', 'tnr.app_users', 'role', 'UPDATE')"
            ).scalar()
    finally:
        with engine.begin() as connection:
            connection.exec_driver_sql("DROP OWNED BY tnr_app")
            connection.exec_driver_sql("DROP ROLE tnr_app")
        engine.dispose()
