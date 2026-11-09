import importlib.util
import sqlite3
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.models import AIBriefBudget, Source

spec = importlib.util.spec_from_file_location(
    "backup_sqlite", Path(__file__).resolve().parents[2] / "scripts" / "backup_sqlite.py"
)
backup_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup_module)


def test_backup_preserves_migrated_data_and_never_overwrites(database, tmp_path):
    if database.dialect.name != "sqlite":
        pytest.skip("SQLite backup check; PostgreSQL uses pg_dump")
    with Session(database) as session, session.begin():
        session.add(Source(name="Preserved", feed_url="https://example.org/feed"))
        session.add(AIBriefBudget(month=date(2026, 11, 1), reserved_nano_usd=1625000))
    source = Path(database.url.database)
    destination = tmp_path / "backup.db"
    backup_module.backup(source, destination)
    assert destination.stat().st_mode & 0o777 == 0o600
    with sqlite3.connect(destination) as copy:
        assert copy.execute("SELECT version_num FROM alembic_version").fetchall() == [("0009",)]
        assert copy.execute("SELECT name FROM sources").fetchall() == [("Preserved",)]
        assert copy.execute("SELECT count(*) FROM app_users").fetchone() == (1,)
        assert copy.execute("SELECT reserved_nano_usd FROM ai_brief_budget").fetchall() == [
            (1625000,)
        ]
    with pytest.raises(FileExistsError):
        backup_module.backup(source, destination)
    assert source.is_file()


def test_backup_refuses_missing_source_without_creating_files(tmp_path):
    with pytest.raises(ValueError):
        backup_module.backup(tmp_path / "missing.db", tmp_path / "backup.db")
    assert not list(tmp_path.iterdir())
