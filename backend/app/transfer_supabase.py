"""Prepare offline, check read-only, or explicitly execute a pinned Supabase transfer."""

import argparse
import hashlib
import json
import os
import re
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import Uuid, bindparam, text
from sqlalchemy.exc import SQLAlchemyError

from app import transfer
from app.db import create_database_engine, resolve_database_url
from app.models import LOCAL_OWNER_ID
from app.transfer import TransferError


def target_details(value: str, project_ref: str) -> tuple:
    """Validate and pin the operator endpoint without opening a connection."""
    url = resolve_database_url(value)
    if (
        not re.fullmatch(r"[a-z0-9]{20}", project_ref)
        or url.get_backend_name() != "postgresql"
        or not re.fullmatch(r"aws-[0-9]+-[a-z0-9-]+\.pooler\.supabase\.com", url.host or "")
        or url.port != 5432
        or url.database != "postgres"
        or url.username != f"postgres.{project_ref}"
        or not url.password
        or url.query.get("sslmode") != "verify-full"
    ):
        raise TransferError(
            "Use the named Supabase project's operator session pooler with verified TLS."
        )
    if any(
        os.environ.get(key) for key in ("PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE", "PGOPTIONS")
    ):
        raise TransferError("Remove libpq routing/session overrides before transfer operations.")
    ca = Path(url.query.get("sslrootcert", ""))
    if not ca.is_absolute() or not ca.is_file():
        raise TransferError("An existing absolute CA certificate path is required.")
    return url, {
        "project_ref": project_ref,
        "host": url.host,
        "port": url.port,
        "database": url.database,
        "username": url.username,
        "sslmode": "verify-full",
        "ca_path": str(ca),
        "ca_sha256": transfer.snapshot_hash(ca),
    }


def table_manifest(rows: dict) -> dict:
    return {
        name: {"count": len(items), "sha256": transfer.row_digest(items)}
        for name, items in rows.items()
    }


def prepare(snapshot: Path, digest: str, operator_url: str, project_ref: str) -> dict:
    _, target = target_details(operator_url, project_ref)
    rows = transfer.read_snapshot(snapshot, digest)
    owner = next(row for row in rows["app_users"] if row["id"] == LOCAL_OWNER_ID)
    if not owner["active"] or any(
        user["active"] and user["supabase_subject"] is None for user in rows["app_users"]
    ):
        raise TransferError(
            "The owner must be active and every active profile must have an Auth subject."
        )
    return {
        "format": 1,
        "revision": transfer.REVISION,
        "target": target,
        "snapshot": str(snapshot.resolve()),
        "snapshot_sha256": digest,
        "tables": table_manifest(rows),
    }


def pinned_json(path: Path, digest: str) -> dict:
    raw = path.read_bytes()
    if not re.fullmatch(r"[a-f0-9]{64}", digest) or hashlib.sha256(raw).hexdigest() != digest:
        raise TransferError("The reviewed file's SHA-256 does not match.")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise TransferError("Expected a transfer plan or report object.")
    return value


def load_plan(path: Path, digest: str, operator_url: str) -> tuple:
    plan = pinned_json(path, digest)
    expected = prepare(
        Path(plan["snapshot"]), plan["snapshot_sha256"], operator_url, plan["target"]["project_ref"]
    )
    if plan != expected:
        raise TransferError(
            "Plan, snapshot, certificate or destination changed; prepare a new plan."
        )
    url, _ = target_details(operator_url, plan["target"]["project_ref"])
    return plan, url, transfer.read_snapshot(Path(plan["snapshot"]), plan["snapshot_sha256"])


def check_transport(connection) -> None:
    row = connection.execute(text("SELECT current_database(), current_user")).one()
    if tuple(row) != ("postgres", "postgres"):
        raise TransferError("The connected database or operator role does not match the plan.")
    if not connection.connection.driver_connection.pgconn.ssl_in_use:
        raise TransferError("The operator-to-pooler connection is not encrypted.")
    if (
        connection.execute(
            text("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()")
        ).scalar_one()
        is not True
    ):
        raise TransferError("The pooler-to-database connection is not encrypted.")


def check_privileges(connection) -> None:
    role = connection.execute(
        text("""
        SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication,
               rolbypassrls, rolinherit FROM pg_roles WHERE rolname='tnr_app'
    """)
    ).one_or_none()
    if role is None or tuple(role) != (True, False, False, False, False, False, False):
        raise TransferError("Application role flags do not match the restricted runtime role.")
    if connection.execute(
        text("""
        SELECT count(*) FROM pg_auth_members WHERE member='tnr_app'::regrole
    """)
    ).scalar_one():
        raise TransferError("The runtime role must have no role memberships.")
    schema = connection.execute(
        text("""
        SELECT has_schema_privilege('tnr_app','tnr','USAGE'),
               has_schema_privilege('tnr_app','tnr','CREATE'),
               pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='tnr'
    """)
    ).one()
    if schema[0] is not True or schema[1] is not False or schema[2] == "tnr_app":
        raise TransferError("Runtime schema privileges or ownership are unsafe.")
    for name in [*(table.name for table in transfer.TABLES), "alembic_version"]:
        allowed = {"SELECT"} if name == "app_users" else {"SELECT", "INSERT", "UPDATE", "DELETE"}
        if name == "alembic_version":
            allowed = set()
        for permission in (
            "SELECT",
            "INSERT",
            "UPDATE",
            "DELETE",
            "TRUNCATE",
            "REFERENCES",
            "TRIGGER",
        ):
            actual = connection.execute(
                text("SELECT has_table_privilege('tnr_app', :table, :permission)"),
                {"table": f"tnr.{name}", "permission": permission},
            ).scalar_one()
            if actual != (permission in allowed):
                raise TransferError("Runtime table privileges differ from the approved policy.")
    for name in transfer.SEQUENCED_TABLES:
        for permission in ("USAGE", "SELECT", "UPDATE"):
            actual = connection.execute(
                text("SELECT has_sequence_privilege('tnr_app', :sequence, :permission)"),
                {"sequence": f"tnr.{name}_id_seq", "permission": permission},
            ).scalar_one()
            if actual != (permission == "USAGE"):
                raise TransferError("Runtime sequence privileges differ from the approved policy.")
    if connection.execute(
        text("""
        SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='tnr' AND c.relowner='tnr_app'::regrole
    """)
    ).scalar_one():
        raise TransferError("The runtime must not own application objects.")
    # PUBLIC is not a pg_roles row. Inspect its ACL explicitly, including inherited defaults.
    if connection.execute(
        text("""
        SELECT EXISTS (
          SELECT 1 FROM pg_namespace n, LATERAL aclexplode(n.nspacl) a
          WHERE n.nspname='tnr' AND a.grantee=0
          UNION ALL
          SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace,
                        LATERAL aclexplode(c.relacl) a
          WHERE n.nspname='tnr' AND a.grantee=0
        )
    """)
    ).scalar_one():
        raise TransferError("PUBLIC must have no application schema/object privileges.")
    for role_name in ("anon", "authenticated", "service_role"):
        if connection.execute(
            text("SELECT has_schema_privilege(:role, 'tnr', 'USAGE,CREATE')"), {"role": role_name}
        ).scalar_one():
            raise TransferError("A Data API role can access the private application schema.")
        for table in transfer.TABLES:
            if connection.execute(
                text(
                    "SELECT has_table_privilege(:role, :table, "
                    "'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')"
                ),
                {"role": role_name, "table": f"tnr.{table.name}"},
            ).scalar_one():
                raise TransferError("A Data API role has application table privileges.")


def check_access(connection, rows: dict) -> dict:
    check_transport(connection)
    transfer.check_layout(connection)
    check_privileges(connection)
    subjects = {user["supabase_subject"] for user in rows["app_users"] if user["active"]}
    query = text("SELECT id FROM auth.users WHERE id IN :subjects").bindparams(
        bindparam("subjects", expanding=True, type_=Uuid())
    )
    if set(connection.execute(query, {"subjects": list(subjects)}).scalars()) != subjects:
        raise TransferError(
            "An active profile's subject is missing from this project's Auth users."
        )
    return {
        "active_auth_subjects_checked": len(subjects),
        "runtime_privileges_checked": True,
        "transport_checked": True,
    }


def check_state(connection, rows: dict) -> dict:
    state = check_access(connection, rows)
    transfer.check_seed(connection)
    state["seed_tables"] = table_manifest(
        {table.name: transfer.read_rows(connection, table) for table in transfer.TABLES}
    )
    return state


def verify_sequences(connection, rows: dict) -> None:
    for name in transfer.SEQUENCED_TABLES:
        expected = max(1, max((row["id"] for row in rows[name]), default=0) + 1)
        actual = connection.exec_driver_sql(
            f"SELECT last_value, is_called FROM tnr.{name}_id_seq"
        ).one()
        if tuple(actual) != (expected, False):
            raise TransferError("Sequence state differs from the completed transfer.")


def validate_preflight(path: Path, digest: str, plan_hash: str) -> dict:
    report = pinned_json(path, digest)
    if report.get("operation") != "check" or report.get("plan_sha256") != plan_hash:
        raise TransferError("A successful preflight report for this exact plan is required.")
    age = datetime.now(UTC) - datetime.fromisoformat(report["checked_at"])
    if not timedelta(0) <= age <= timedelta(hours=24):
        raise TransferError("Preflight must be from the last 24 hours; check again.")
    return report["state"]


def run_remote(
    plan_path: Path,
    plan_hash: str,
    operator_url: str,
    *,
    confirmation: str | None = None,
    preflight: Path | None = None,
    preflight_hash: str | None = None,
    verify: bool = False,
) -> dict:
    plan, url, rows = load_plan(plan_path, plan_hash, operator_url)
    if verify and confirmation is not None:
        raise TransferError("Verification and execution are separate operations.")
    expected_state = None
    if confirmation is not None:
        if (
            confirmation != plan["target"]["project_ref"]
            or preflight is None
            or preflight_hash is None
        ):
            raise TransferError(
                "Execution requires the exact project reference and a pinned preflight report."
            )
        expected_state = validate_preflight(preflight, preflight_hash, plan_hash)
    engine = create_database_engine(url)
    try:
        with engine.begin() as connection:
            if connection.connection.driver_connection.autocommit:
                raise TransferError("Transfer operations require real database transactions.")
            if confirmation is None:
                connection.exec_driver_sql(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
                )
                connection.exec_driver_sql("SET LOCAL statement_timeout = '60s'")
            else:
                transfer.lock_target(connection)
            if verify:
                state = check_access(connection, rows)
                tables = transfer.verify_rows(connection, rows)
                verify_sequences(connection, rows)
            elif confirmation is not None:
                state = check_state(connection, rows)
                if state != expected_state:
                    raise TransferError("Remote state changed since preflight; no data copied.")
                tables = transfer.copy_rows(connection, rows)
                check_privileges(connection)
            else:
                state = check_state(connection, rows)
                tables = plan["tables"]
        return {
            "operation": "verify" if verify else "execute" if confirmation is not None else "check",
            "plan_sha256": plan_hash,
            "checked_at": datetime.now(UTC).isoformat(),
            "state": state,
            "tables": tables,
        }
    finally:
        engine.dispose()


def operator_url(path: Path) -> str:
    if not stat.S_ISREG(path.stat().st_mode) or path.stat().st_mode & 0o077:
        raise TransferError("Operator configuration must be a private regular file (mode 0600).")
    value = json.loads(path.read_text())["TNR_MIGRATION_DATABASE_URL"]
    if not isinstance(value, str):
        raise TransferError("Operator configuration must contain a migration URL.")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    for name in ("prepare", "check", "execute", "verify"):
        sub = subparsers.add_parser(name)
        sub.add_argument("--operator-config", type=Path, required=True)
        sub.add_argument("--output", type=Path, required=True)
        if name == "prepare":
            sub.add_argument("--snapshot", type=Path, required=True)
            sub.add_argument("--sha256", required=True)
            sub.add_argument("--project-ref", required=True)
        else:
            sub.add_argument("--plan", type=Path, required=True)
            sub.add_argument("--plan-sha256", required=True)
        if name == "execute":
            sub.add_argument("--confirm-project-ref", required=True)
            sub.add_argument("--preflight", type=Path, required=True)
            sub.add_argument("--preflight-sha256", required=True)
    args = parser.parse_args()
    try:
        url = operator_url(args.operator_config)
        # Reserve output before any connection/commit. Refuse overwrites and symlinks.
        with open(
            args.output, "x", opener=lambda path, flags: os.open(path, flags, 0o600)
        ) as output:
            if args.operation == "prepare":
                result = prepare(args.snapshot, args.sha256, url, args.project_ref)
            else:
                options = (
                    {"verify": args.operation == "verify"}
                    if args.operation != "execute"
                    else {
                        "confirmation": args.confirm_project_ref,
                        "preflight": args.preflight,
                        "preflight_hash": args.preflight_sha256,
                    }
                )
                result = run_remote(args.plan, args.plan_sha256, url, **options)
            json.dump(result, output, indent=2)
    except TransferError as error:
        parser.exit(1, f"Transfer refused: {error}\n")
    except (OSError, ValueError, KeyError, TypeError, SQLAlchemyError):
        parser.exit(
            1,
            "Operation failed. Details withheld to protect credentials and records. "
            "Do not retry execution without inspecting the target.\n",
        )
    print(
        f"{args.operation.capitalize()} completed. "
        f"Private output SHA-256: {transfer.snapshot_hash(args.output)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
