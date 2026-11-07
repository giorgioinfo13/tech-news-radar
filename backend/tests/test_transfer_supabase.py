import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from psycopg import ConnectionInfo
from psycopg.pq import PGconn
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from test_transfer import snapshot as snapshot
from test_transfer import target as target

from app import transfer
from app import transfer_supabase as remote

PROJECT = "abcdefghijklmnopqrst"
HOST = "aws-0-eu-west-2.pooler.supabase.com"


@pytest.fixture
def operator(tmp_path):
    ca = tmp_path / "test-ca.crt"
    ca.write_text("Test certificate contents; never used for a network connection")
    return f"postgresql+psycopg://postgres.{PROJECT}:dummy-password@{HOST}:5432/postgres?sslmode=verify-full&sslrootcert={ca}"


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2))
    path.chmod(0o600)
    return transfer.snapshot_hash(path)


@pytest.fixture
def plan(snapshot, operator, tmp_path):
    path = tmp_path / "plan.json"
    value = remote.prepare(snapshot, transfer.snapshot_hash(snapshot), operator, PROJECT)
    digest = write_json(path, value)
    return path, digest


def test_prepare_is_offline_and_contains_no_credentials(snapshot, operator, monkeypatch):
    monkeypatch.setattr(
        remote, "create_database_engine", lambda *args: pytest.fail("Preparation must not connect")
    )
    result = remote.prepare(snapshot, transfer.snapshot_hash(snapshot), operator, PROJECT)
    serialized = json.dumps(result)
    assert "dummy-password" not in serialized
    assert result["target"]["project_ref"] == PROJECT
    assert result["tables"]["app_users"]["count"] == 3
    assert "supabase_subject" not in serialized
    assert "display_name" not in serialized


@pytest.mark.parametrize(
    "change",
    [
        lambda url: url.replace(PROJECT, "z" * 20),
        lambda url: url.replace(HOST, "attacker.example"),
        lambda url: url.replace(":5432/", ":6543/"),
        lambda url: url.replace("/postgres?", "/other?"),
        lambda url: url.replace("postgres.", "tnr_app.", 1),
        lambda url: url.replace("verify-full", "require"),
        lambda url: url + "&host=attacker.example",
        lambda url: url.replace(":dummy-password@", "@"),
        lambda url: url.split("&sslrootcert=")[0],
    ],
)
def test_rejects_wrong_remote_destination(operator, change):
    with pytest.raises((ValueError, SQLAlchemyError)):
        remote.target_details(change(operator), PROJECT)


def test_rejects_libpq_route_override(operator, monkeypatch):
    monkeypatch.setenv("PGHOSTADDR", "192.0.2.1")
    with pytest.raises(transfer.TransferError, match="overrides"):
        remote.target_details(operator, PROJECT)


@pytest.mark.parametrize("change", ["plan", "certificate", "host", "snapshot"])
def test_plan_changes_are_rejected_before_connection(plan, operator, monkeypatch, change):
    path, digest = plan
    value = json.loads(path.read_text())
    monkeypatch.setattr(
        remote, "create_database_engine", lambda *args: pytest.fail("Must refuse before connection")
    )
    if change == "plan":
        path.write_text(path.read_text() + " ")
    elif change == "certificate":
        Path(value["target"]["ca_path"]).write_text("Different CA")
    elif change == "host":
        operator = operator.replace("aws-0-", "aws-1-")
    else:
        with Path(value["snapshot"]).open("ab") as stream:
            stream.write(b"changed")
    with pytest.raises(transfer.TransferError):
        remote.run_remote(path, digest, operator)


@pytest.mark.parametrize("failure", ["project", "missing", "old", "different_plan"])
def test_execution_requires_matching_recent_preflight(
    plan, operator, tmp_path, monkeypatch, failure
):
    path, digest = plan
    report = tmp_path / "preflight.json"
    data = {
        "operation": "check",
        "plan_sha256": digest,
        "checked_at": datetime.now(UTC).isoformat(),
        "state": {},
    }
    if failure == "old":
        data["checked_at"] = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    if failure == "different_plan":
        data["plan_sha256"] = "f" * 64
    report_hash = write_json(report, data)
    monkeypatch.setattr(
        remote, "create_database_engine", lambda *args: pytest.fail("Must refuse before connection")
    )
    with pytest.raises(transfer.TransferError):
        remote.run_remote(
            path,
            digest,
            operator,
            confirmation="wrong" if failure == "project" else PROJECT,
            preflight=None if failure == "missing" else report,
            preflight_hash=report_hash,
        )


@pytest.mark.parametrize(
    "database,user,client_ssl,server_ssl",
    [
        ("other", "postgres", True, True),
        ("postgres", "tnr_app", True, True),
        ("postgres", "postgres", False, True),
        ("postgres", "postgres", True, False),
        ("postgres", "postgres", True, True),
    ],
)
def test_transport_checks_both_tls_hops_and_database_identity(
    database, user, client_ssl, server_ssl
):
    connection = Mock()
    connection.execute.return_value.one.return_value = (database, user)
    connection.execute.return_value.scalar_one.return_value = server_ssl
    driver = SimpleNamespace(info=Mock(spec_set=ConnectionInfo), pgconn=Mock(spec_set=PGconn))
    driver.pgconn.ssl_in_use = client_ssl
    connection.connection.driver_connection = driver
    if (database, user, client_ssl, server_ssl) == ("postgres", "postgres", True, True):
        remote.check_transport(connection)
    else:
        with pytest.raises(transfer.TransferError):
            remote.check_transport(connection)


@pytest.fixture
def ready(target, snapshot, monkeypatch):
    # Only external Auth/TLS are simulated; application schema uses real Alembic migrations.
    created = False
    try:
        with target.connect() as connection:
            raw = connection.connection.driver_connection
            raw.autocommit = True
            raw.execute(
                (Path(__file__).resolve().parents[1] / "sql/create_app_role.sql").read_text()
            )
            created = True
            raw.autocommit = False
        rows = transfer.read_snapshot(snapshot, transfer.snapshot_hash(snapshot))
        with target.begin() as connection:
            connection.exec_driver_sql("CREATE SCHEMA auth")
            connection.exec_driver_sql("CREATE TABLE auth.users (id uuid PRIMARY KEY)")
            for user in rows["app_users"]:
                connection.execute(
                    text("INSERT INTO auth.users (id) VALUES (:id)"),
                    {"id": user["supabase_subject"]},
                )
        monkeypatch.setattr(remote, "create_database_engine", lambda url: target)
        monkeypatch.setattr(remote, "check_transport", lambda connection: None)
        yield target
    finally:
        if created:
            with target.begin() as connection:
                connection.exec_driver_sql("DROP OWNED BY tnr_app")
                connection.exec_driver_sql("DROP ROLE tnr_app")


def test_check_is_enforced_read_only_and_preserves_every_target_row(
    plan, operator, ready, monkeypatch
):
    path, digest = plan
    with ready.connect() as connection:
        before = {table.name: transfer.read_rows(connection, table) for table in transfer.TABLES}
    original = remote.check_state

    def guarded_check(connection, rows):
        assert connection.exec_driver_sql("SHOW transaction_read_only").scalar_one() == "on"
        with pytest.raises(SQLAlchemyError) as error, connection.begin_nested():
            connection.exec_driver_sql("DELETE FROM tnr.categories")
        assert error.value.orig.sqlstate == "25006"
        return original(connection, rows)

    monkeypatch.setattr(remote, "check_state", guarded_check)
    report = remote.run_remote(path, digest, operator)
    assert report["operation"] == "check"
    assert report["state"]["active_auth_subjects_checked"] == 2
    with ready.connect() as connection:
        assert {
            table.name: transfer.read_rows(connection, table) for table in transfer.TABLES
        } == before


@pytest.mark.parametrize(
    "change",
    [
        "GRANT UPDATE ON tnr.app_users TO tnr_app",
        "ALTER TABLE tnr.app_users DISABLE ROW LEVEL SECURITY",
        "DROP POLICY app_users_insert_reader ON tnr.app_users",
        "CREATE POLICY unsafe_insert ON tnr.app_users FOR INSERT WITH CHECK (true)",
        "GRANT SELECT ON tnr.alembic_version TO tnr_app",
        "GRANT UPDATE ON SEQUENCE tnr.sources_id_seq TO tnr_app",
        "ALTER ROLE tnr_app BYPASSRLS",
        "GRANT service_role TO tnr_app",
        "GRANT USAGE ON SCHEMA tnr TO PUBLIC",
        "GRANT SELECT ON tnr.sources TO anon",
        "DELETE FROM auth.users",
        "UPDATE tnr.categories SET name='Changed' WHERE id=1",
    ],
)
def test_preflight_refuses_unsafe_grants_missing_identity_or_target_data(
    plan, operator, ready, change
):
    with ready.begin() as connection:
        connection.exec_driver_sql(change)
    with pytest.raises(transfer.TransferError):
        remote.run_remote(*plan, operator)


@pytest.mark.parametrize("change", [None, "seed", "permission", "verification"])
def test_execute_rechecks_and_copies_atomically(
    plan, operator, ready, snapshot, tmp_path, monkeypatch, change
):
    path, digest = plan
    preflight = tmp_path / "preflight.json"
    report_hash = write_json(preflight, remote.run_remote(path, digest, operator))
    with ready.connect() as connection:
        before = {table.name: transfer.read_rows(connection, table) for table in transfer.TABLES}
        sequence = connection.exec_driver_sql(
            "SELECT last_value, is_called FROM tnr.sources_id_seq"
        ).one()
        auth_before = connection.exec_driver_sql("SELECT id FROM auth.users ORDER BY id").all()
    if change == "seed":
        with ready.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE tnr.app_users SET created_at=created_at + interval '1 second'"
            )
    if change == "permission":
        with ready.begin() as connection:
            connection.exec_driver_sql("GRANT UPDATE ON tnr.app_users TO tnr_app")
    if change == "verification":
        original = transfer.verify_rows

        def corrupt(connection, rows):
            connection.exec_driver_sql("UPDATE tnr.articles SET title='Incorrect' WHERE id=101")
            return original(connection, rows)

        monkeypatch.setattr(transfer, "verify_rows", corrupt)

    def execute():
        return remote.run_remote(
            path,
            digest,
            operator,
            confirmation=PROJECT,
            preflight=preflight,
            preflight_hash=report_hash,
        )

    if change:
        with pytest.raises(transfer.TransferError):
            execute()
    else:
        result = execute()
        assert result["operation"] == "execute"
        assert result["tables"]["articles"]["count"] == 2
        verified = remote.run_remote(path, digest, operator, verify=True)
        assert verified["operation"] == "verify"
        assert verified["tables"] == result["tables"]
        with pytest.raises(transfer.TransferError, match="beyond"):
            execute()
    with ready.connect() as connection:
        assert (
            connection.exec_driver_sql("SELECT id FROM auth.users ORDER BY id").all() == auth_before
        )
        if change in {"verification", "permission"}:
            assert {
                table.name: transfer.read_rows(connection, table) for table in transfer.TABLES
            } == before
            assert (
                connection.exec_driver_sql(
                    "SELECT last_value, is_called FROM tnr.sources_id_seq"
                ).one()
                == sequence
            )
        if change is None:
            expected = transfer.read_snapshot(snapshot, transfer.snapshot_hash(snapshot))
            assert {
                table.name: transfer.read_rows(connection, table) for table in transfer.TABLES
            } == expected


def test_cli_prepare_private_output_and_no_overwrite(
    snapshot, operator, tmp_path, monkeypatch, capsys
):
    config = tmp_path / "operator.json"
    write_json(config, {"TNR_MIGRATION_DATABASE_URL": operator})
    output = tmp_path / "result.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "transfer_supabase",
            "prepare",
            "--operator-config",
            str(config),
            "--snapshot",
            str(snapshot),
            "--sha256",
            transfer.snapshot_hash(snapshot),
            "--project-ref",
            PROJECT,
            "--output",
            str(output),
        ],
    )
    monkeypatch.setattr(remote, "create_database_engine", lambda *args: pytest.fail("Offline only"))
    assert remote.main() == 0
    assert output.stat().st_mode & 0o777 == 0o600
    original = output.read_bytes()
    with pytest.raises(SystemExit):
        remote.main()
    assert output.read_bytes() == original
    captured = capsys.readouterr()
    assert "dummy-password" not in captured.out + captured.err
    config.chmod(0o644)
    with pytest.raises(transfer.TransferError, match="private"):
        remote.operator_url(config)


def test_accidental_autocommit_is_rejected_before_sql(plan, operator, ready):
    with ready.connect() as connection:
        connection.connection.driver_connection.autocommit = True
    with pytest.raises(transfer.TransferError, match="transactions"):
        remote.run_remote(*plan, operator)


@pytest.mark.parametrize("change", ["rows", "sequence"])
def test_post_transfer_verification_detects_changes_without_writing(
    plan, operator, ready, tmp_path, change
):
    path, digest = plan
    preflight = tmp_path / "preflight.json"
    report_hash = write_json(preflight, remote.run_remote(path, digest, operator))
    remote.run_remote(
        path,
        digest,
        operator,
        confirmation=PROJECT,
        preflight=preflight,
        preflight_hash=report_hash,
    )
    with ready.begin() as connection:
        if change == "rows":
            connection.exec_driver_sql(
                "UPDATE tnr.articles SET title='Changed after commit' WHERE id=101"
            )
        else:
            connection.exec_driver_sql("SELECT nextval('tnr.sources_id_seq')")
        before = {table.name: transfer.read_rows(connection, table) for table in transfer.TABLES}
    with pytest.raises(transfer.TransferError):
        remote.run_remote(path, digest, operator, verify=True)
    with ready.connect() as connection:
        assert {
            table.name: transfer.read_rows(connection, table) for table in transfer.TABLES
        } == before
