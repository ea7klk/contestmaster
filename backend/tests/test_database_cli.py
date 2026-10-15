from pathlib import Path

import pytest
from sqlalchemy import String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from backend.app.database_cli import backup_database, restore_database


class BackupBase(DeclarativeBase):
    pass


class BackupRecord(BackupBase):
    __tablename__ = "backup_record"

    id: Mapped[int] = mapped_column(primary_key=True)
    value: Mapped[str] = mapped_column(String(80))


def _database(path: Path, value: str) -> str:
    engine = create_engine(f"sqlite:///{path}")
    BackupBase.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        session.add(BackupRecord(value=value))
    engine.dispose()
    return f"sqlite:///{path}"


def _values(path: Path) -> list[str]:
    engine = create_engine(f"sqlite:///{path}")
    with Session(engine) as session:
        values = list(session.scalars(select(BackupRecord.value).order_by(BackupRecord.id)))
    engine.dispose()
    return values


def test_backup_is_validated_and_restore_replaces_database_with_safety_copy(tmp_path: Path):
    database = tmp_path / "app.db"
    _database(database, "before-backup")
    backup = tmp_path / "backups" / "app.db.bak"

    assert backup_database(f"sqlite:///{database}", backup) == backup
    assert _values(backup) == ["before-backup"]

    _database(database, "after-backup")
    assert restore_database(f"sqlite:///{database}", backup) == database
    assert _values(database) == ["before-backup"]
    assert len(list(tmp_path.glob("app.db.pre-restore-*.bak"))) == 1


def test_backup_refuses_to_overwrite_existing_destination(tmp_path: Path):
    database = tmp_path / "app.db"
    _database(database, "safe")
    backup = tmp_path / "backup.db"
    backup.write_text("preserve", encoding="utf-8")

    with pytest.raises(FileExistsError):
        backup_database(f"sqlite:///{database}", backup)
    assert backup.read_text(encoding="utf-8") == "preserve"


def test_restore_rejects_corrupt_source_without_changing_live_database(tmp_path: Path):
    database = tmp_path / "app.db"
    _database(database, "safe")
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_bytes(b"not sqlite")

    with pytest.raises(ValueError, match="integrity check"):
        restore_database(f"sqlite:///{database}", corrupt)
    assert _values(database) == ["safe"]
