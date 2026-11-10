"""Apply release migrations with a pinned Supabase target and bounded database locks."""

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import make_url

from app.db import BACKEND_ROOT, create_database_engine
from app.transfer_supabase import target_details


def migrate(url) -> None:
    """Migrate and grant the reviewed usage permission in one transaction."""
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option(
        "sqlalchemy.url", url.render_as_string(hide_password=False).replace("%", "%%")
    )
    scripts = ScriptDirectory.from_config(config)
    head = scripts.get_current_head()
    engine = create_database_engine(url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("SET LOCAL lock_timeout = '10s'")
            connection.exec_driver_sql("SET LOCAL statement_timeout = '120s'")
            if not connection.exec_driver_sql(
                "SELECT pg_try_advisory_xact_lock(746674, 99)"
            ).scalar():
                raise RuntimeError("Another database release is running")
            revisions = (
                connection.exec_driver_sql("SELECT version_num FROM tnr.alembic_version")
                .scalars()
                .all()
            )
            allowed = {
                revision.revision for revision in scripts.walk_revisions(base="0010", head=head)
            }
            if len(revisions) != 1 or revisions[0] not in allowed:
                raise RuntimeError(
                    "Release requires an existing database at revision 0010 or later"
                )
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            connection.exec_driver_sql("GRANT UPDATE (last_seen_at) ON tnr.app_users TO tnr_app")
            if (
                connection.exec_driver_sql("SELECT version_num FROM tnr.alembic_version").scalar()
                != head
            ):
                raise RuntimeError("Database revision verification failed")
    finally:
        engine.dispose()


def main() -> int:
    try:
        with TemporaryDirectory(prefix="tnr-release-") as directory:
            ca = Path(directory) / "supabase-ca.crt"
            ca.write_text(os.environ["TNR_SUPABASE_CA_CERT"], encoding="utf-8")
            ca.chmod(0o600)
            url = make_url(os.environ["TNR_MIGRATION_DATABASE_URL"]).update_query_dict(
                {"sslrootcert": str(ca)}
            )
            url, _ = target_details(url, os.environ["TNR_SUPABASE_PROJECT_REF"])
            migrate(url)
    except Exception:
        # Database exceptions can include URLs, SQL parameters or private schema data.
        print(
            "Database release failed. Inspect revision and permissions before retrying.",
            file=sys.stderr,
        )
        return 1
    print("Database migration and reader usage permission verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
