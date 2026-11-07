"""Rehearse a SQLite snapshot transfer to a disposable, local PostgreSQL database."""

import argparse
import hashlib
import json
import os
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import Connection, Table, create_engine, inspect, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

from app.db import create_database_engine, resolve_database_url
from app.models import (
    LOCAL_OWNER_ID,
    AppUser,
    Article,
    ArticleReadState,
    Category,
    CollectionRun,
    ReaderInvitation,
    Source,
    Subscription,
)

REVISION = "0005"
TABLES = tuple(
    model.__table__
    for model in (
        AppUser,
        Category,
        Source,
        Article,
        CollectionRun,
        Subscription,
        ArticleReadState,
        ReaderInvitation,
    )
)
SEQUENCED_TABLES = ("categories", "sources", "articles", "collection_runs")
# Frozen migration seed contract, not the application's editable category catalog.
SEED_CATEGORIES = [
    {"id": position + 1, "name": name, "slug": slug, "sort_order": position}
    for position, (name, slug) in enumerate(
        [
            ("Artificial intelligence and LLMs", "artificial-intelligence"),
            ("AI agents and agentic development", "ai-agents"),
            ("Software engineering", "software-engineering"),
            ("Open-weight and open-source models", "open-models"),
            ("Technology companies", "technology-companies"),
            ("Research and scientific publications", "research"),
            ("Economics and financial markets", "economics-finance"),
            ("International technology news", "international-tech"),
        ]
    )
]


class TransferError(ValueError):
    """An operator-safe error with no credentials or record contents."""


def local_target_url(value: str):
    """Never inherit application/migration URLs or permit a remote destination."""
    try:
        url = resolve_database_url(value)
        valid = (
            url.get_backend_name() == "postgresql"
            and url.host in {"127.0.0.1", "::1"}
            and url.port is not None
            and re.fullmatch(r"tnr_(?:transfer|test)_[a-z0-9]{8,32}", url.database or "")
        )
    except (ValueError, SQLAlchemyError):
        valid = False
    if not valid:
        raise TransferError(
            "Target must be a disposable local PostgreSQL database with an explicit port."
        )
    if any(
        os.environ.get(key) for key in ("PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE", "PGOPTIONS")
    ):
        raise TransferError("Remove libpq routing/session overrides before this local rehearsal.")
    return url


def snapshot_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def check_layout(connection: Connection) -> None:
    schema = "tnr" if connection.dialect.name == "postgresql" else None
    inspector = inspect(connection)
    if set(inspector.get_table_names(schema=schema)) != {
        "alembic_version",
        *(table.name for table in TABLES),
    }:
        raise TransferError("Unexpected database tables; no transfer performed.")
    if connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all() != [
        REVISION
    ]:
        raise TransferError("Both databases must use migration revision 0005.")
    for table in TABLES:
        if {column["name"] for column in inspector.get_columns(table.name, schema=schema)} != set(
            table.c.keys()
        ):
            raise TransferError("Unexpected database columns; no transfer performed.")


def read_rows(connection: Connection, table: Table) -> list[dict]:
    return [
        dict(row)
        for row in connection.execute(select(table).order_by(*table.primary_key)).mappings()
    ]


def read_snapshot(path: Path, expected_hash: str) -> dict[str, list[dict]]:
    path = path.resolve(strict=True)
    if not re.fullmatch(r"[a-f0-9]{64}", expected_hash) or snapshot_hash(path) != expected_hash:
        raise TransferError("Snapshot SHA-256 does not match the approved copy.")
    # The pinned hash must cover all data. Use backup_sqlite.py to include live WAL contents.
    sidecars = [Path(f"{path}{suffix}") for suffix in ("-wal", "-shm", "-journal")]
    if any(sidecar.exists() for sidecar in sidecars):
        raise TransferError("Use a closed SQLite backup without journal or WAL sidecars.")
    engine = create_engine(
        "sqlite+pysqlite://",
        creator=lambda: sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, autocommit=False),
        poolclass=NullPool,
        hide_parameters=True,
    )
    try:
        with engine.connect() as connection:
            if connection.exec_driver_sql("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise TransferError("SQLite integrity check failed.")
            if connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall():
                raise TransferError("SQLite foreign key check failed.")
            check_layout(connection)
            rows = {table.name: read_rows(connection, table) for table in TABLES}
    finally:
        engine.dispose()
    if snapshot_hash(path) != expected_hash or any(sidecar.exists() for sidecar in sidecars):
        raise TransferError("Snapshot changed while it was read.")
    owner = next((row for row in rows["app_users"] if row["id"] == LOCAL_OWNER_ID), None)
    if owner is None or owner["role"] != "admin":
        raise TransferError("Snapshot must retain the reserved owner as administrator.")
    if any(row["status"] == "running" for row in rows["collection_runs"]):
        raise TransferError(
            "Snapshot contains an unfinished collection; resolve it before transfer."
        )
    return rows


def check_seed(connection: Connection) -> None:
    rows = {table.name: read_rows(connection, table) for table in TABLES}
    users = rows.pop("app_users")
    categories = rows.pop("categories")
    owner = (
        {key: value for key, value in users[0].items() if key != "created_at"}
        if len(users) == 1
        else None
    )
    if (
        owner
        != {
            "id": LOCAL_OWNER_ID,
            "supabase_subject": None,
            "display_name": "Local owner",
            "role": "admin",
            "active": True,
        }
        or categories != SEED_CATEGORIES
        or any(rows.values())
    ):
        raise TransferError("Target contains data beyond the unchanged migration seeds.")


def canonical_value(value):
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat(timespec="microseconds")
    if isinstance(value, UUID):
        return str(value)
    raise TypeError("Unsupported value in transfer report")


def row_digest(rows: list[dict]) -> str:
    content = json.dumps(
        rows, default=canonical_value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def verify_rows(connection: Connection, rows: dict[str, list[dict]]) -> dict:
    report = {}
    for table in TABLES:
        actual = read_rows(connection, table)
        expected = rows[table.name]
        if actual != expected:
            raise TransferError(
                f"Row verification failed for {table.name}; transaction rolled back."
            )
        report[table.name] = {"count": len(expected), "sha256": row_digest(expected)}
    return report


def lock_target(connection: Connection) -> None:
    """Lock application tables in the caller's transaction before checking or copying."""
    connection.exec_driver_sql("SET LOCAL lock_timeout = '5s'")
    connection.exec_driver_sql("SET LOCAL statement_timeout = '60s'")
    names = ", ".join(f"tnr.{table.name}" for table in TABLES)
    connection.exec_driver_sql(f"LOCK TABLE {names}, tnr.alembic_version IN EXCLUSIVE MODE")


def copy_rows(connection: Connection, rows: dict[str, list[dict]]) -> dict:
    """Copy and verify in an existing transaction after lock_target; never commit here."""
    check_layout(connection)
    check_seed(connection)
    # Keep the reserved owner row/UUID. Replace only the verified, unused category seeds.
    owner = next(row for row in rows["app_users"] if row["id"] == LOCAL_OWNER_ID)
    connection.execute(
        AppUser.__table__.update()
        .where(AppUser.id == LOCAL_OWNER_ID)
        .values(**{key: value for key, value in owner.items() if key != "id"})
    )
    connection.execute(Category.__table__.delete())
    for table in TABLES:
        batch_rows = rows[table.name]
        if table.name == "app_users":
            batch_rows = [row for row in batch_rows if row["id"] != LOCAL_OWNER_ID]
        for offset in range(0, len(batch_rows), 500):
            connection.execute(table.insert(), batch_rows[offset : offset + 500])
    for name in SEQUENCED_TABLES:
        next_id = max(1, max((row["id"] for row in rows[name]), default=0) + 1)
        # RESTART is transactional; setval is not. No nextval is consumed by verification.
        connection.exec_driver_sql(f"ALTER SEQUENCE tnr.{name}_id_seq RESTART WITH {next_id}")
    return verify_rows(connection, rows)


def rehearse(snapshot: Path, expected_hash: str, target_url: str) -> dict:
    url = local_target_url(target_url)
    rows = read_snapshot(snapshot, expected_hash)
    engine = create_database_engine(url)
    try:
        with engine.begin() as connection:
            lock_target(connection)
            report = copy_rows(connection, rows)
        return {"revision": REVISION, "snapshot_sha256": expected_hash, "tables": report}
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    try:
        url = os.environ.get("TNR_TRANSFER_DATABASE_URL", "")
        report = rehearse(args.snapshot, args.sha256, url)
    except TransferError as error:
        parser.exit(1, f"Transfer refused: {error}\n")
    except (OSError, ValueError, SQLAlchemyError):
        # Database exception details can include credentials, subjects, or article contents.
        parser.exit(1, "Transfer failed. Inspect the disposable local target before retrying.\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
