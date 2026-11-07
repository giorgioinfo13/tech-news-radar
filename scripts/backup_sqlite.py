"""Create a consistent private SQLite backup without altering the source."""

import argparse
import os
import sqlite3
from contextlib import closing
from pathlib import Path


def backup(source: Path, destination: Path) -> None:
    # mode=ro prevents silently creating a missing source. The backup API includes WAL data.
    if not source.is_file():
        raise ValueError("Source must be an existing SQLite database")
    with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as origin:
        fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        try:
            with closing(sqlite3.connect(destination)) as target:
                origin.backup(target)
                if target.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                    raise ValueError("Backup integrity check failed")
                if target.execute("PRAGMA foreign_key_check").fetchall():
                    raise ValueError("Backup foreign key check failed")
        except (OSError, ValueError, sqlite3.Error):
            # Retain the artifact for diagnosis; never remove or overwrite another file.
            raise ValueError("Backup failed: do not use the incomplete destination") from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    try:
        backup(args.source, args.destination)
    except (OSError, ValueError, sqlite3.Error):
        print("Backup failed. Check source, permissions, and that the destination does not exist.")
        return 1
    print("Backup completed; integrity and foreign keys verified. Store it privately.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
