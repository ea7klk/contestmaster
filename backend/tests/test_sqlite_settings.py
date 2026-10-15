import pytest
from sqlalchemy import Column, Integer, MetaData, Table, insert, select, text
from sqlalchemy.orm import Session

from backend.app.db import build_engine, transaction


def test_file_sqlite_connections_enable_foreign_keys_busy_timeout_and_wal(tmp_path):
    engine = build_engine(f"sqlite:///{tmp_path / 'test.db'}", busy_timeout_ms=1234)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
            assert connection.execute(text("PRAGMA busy_timeout")).scalar_one() == 1234
            assert connection.execute(text("PRAGMA journal_mode")).scalar_one().lower() == "wal"
    finally:
        engine.dispose()


def test_sqlite_memory_database_skips_wal():
    engine = build_engine("sqlite:///:memory:")
    try:
        with engine.connect() as connection:
            assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
            assert connection.execute(text("PRAGMA journal_mode")).scalar_one().lower() == "memory"
    finally:
        engine.dispose()


def test_orm_transaction_commits_success_and_rolls_back_failure():
    engine = build_engine("sqlite:///:memory:")
    table = Table("transaction_probe", MetaData(), Column("value", Integer, primary_key=True))
    table.create(engine)
    try:
        with Session(engine) as session:
            with transaction(session):
                session.execute(insert(table).values(value=1))

            with pytest.raises(RuntimeError):
                with transaction(session):
                    session.execute(insert(table).values(value=2))
                    raise RuntimeError("abort this unit of work")

            assert session.execute(
                select(table.c.value).order_by(table.c.value)
            ).scalars().all() == [1]
    finally:
        engine.dispose()
