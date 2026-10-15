"""Offline SQLite backup, validation, and restore helpers using SQLAlchemy."""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from backend.app.config import ensure_sqlite_parent, get_settings

logger = logging.getLogger("contestmaster.database")


def _sqlite_path(database_url: str) -> Path:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix) or database_url == "sqlite:///:memory:":
        raise ValueError("Database maintenance commands require a file-backed SQLite database")
    raw_path = database_url[len(prefix) :].split("?", maxsplit=1)[0]
    path = Path(raw_path)
    return path if path.is_absolute() else Path.cwd() / path


def _verify_database(engine: Engine) -> None:
    try:
        with engine.connect() as connection:
            result = connection.execute(text("PRAGMA integrity_check")).scalar_one()
            if result != "ok":
                raise ValueError("SQLite integrity check failed")
    except SQLAlchemyError as exc:
        raise ValueError("Database cannot be opened or failed its SQLite integrity check") from exc


def _open_engine(path: Path) -> Engine:
    ensure_sqlite_parent(f"sqlite:///{path}")
    return create_engine(f"sqlite:///{path}", pool_pre_ping=True)


def backup_database(database_url: str, destination: Path) -> Path:
    """Create and validate an offline copy; stop the API before calling this."""
    source = _sqlite_path(database_url).resolve()
    target = destination.resolve()
    if source == target:
        raise ValueError("Backup destination must differ from the configured database")
    if not source.is_file():
        raise FileNotFoundError("Configured database file does not exist")
    if target.exists():
        raise FileExistsError("Backup destination already exists")
    target.parent.mkdir(parents=True, exist_ok=True)

    source_engine = _open_engine(source)
    try:
        with source_engine.connect() as connection:
            connection.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
        source_engine.dispose()
        temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        try:
            shutil.copy2(source, temporary)
            check_engine = _open_engine(temporary)
            try:
                _verify_database(check_engine)
            finally:
                check_engine.dispose()
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    finally:
        source_engine.dispose()
    return target


def restore_database(database_url: str, backup: Path) -> Path:
    """Validate then atomically install a backup; stop the API before calling this."""
    target = _sqlite_path(database_url).resolve()
    source = backup.resolve()
    if source == target:
        raise ValueError("Restore source must differ from the configured database")
    if not source.is_file():
        raise FileNotFoundError("Restore source does not exist")
    target.parent.mkdir(parents=True, exist_ok=True)

    check_engine = _open_engine(source)
    try:
        _verify_database(check_engine)
    finally:
        check_engine.dispose()

    temporary = target.with_name(f".{target.name}.{os.getpid()}.restore")
    safety_copy = target.with_name(
        f"{target.name}.pre-restore-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.bak"
    )
    try:
        shutil.copy2(source, temporary)
        candidate_engine = _open_engine(temporary)
        try:
            _verify_database(candidate_engine)
        finally:
            candidate_engine.dispose()
        if target.exists():
            shutil.copy2(target, safety_copy)
        for suffix in ("-wal", "-shm"):
            Path(f"{target}{suffix}").unlink(missing_ok=True)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="contestmaster-db")
    subparsers = parser.add_subparsers(dest="command", required=True)
    backup_parser = subparsers.add_parser(
        "backup", help="Create an offline validated SQLite backup"
    )
    backup_parser.add_argument("destination", type=Path)
    restore_parser = subparsers.add_parser(
        "restore", help="Restore a validated offline SQLite backup"
    )
    restore_parser.add_argument("source", type=Path)
    subparsers.add_parser("verify", help="Check configured SQLite database integrity")
    args = parser.parse_args(argv)
    try:
        url = get_settings().database_url
        if args.command == "backup":
            result = backup_database(url, args.destination)
        elif args.command == "restore":
            result = restore_database(url, args.source)
        else:
            engine = _open_engine(_sqlite_path(url))
            try:
                _verify_database(engine)
            finally:
                engine.dispose()
            result = _sqlite_path(url)
        print(f"Database {args.command} completed: {result}")
        return 0
    except Exception as exc:
        logger.error(
            "database_maintenance_failed",
            extra={"operation": args.command, "error_type": type(exc).__name__},
        )
        print(f"Database {args.command} failed: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
