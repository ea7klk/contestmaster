from sqlalchemy import event, text

from backend.app import database_maintenance
from backend.app.database_maintenance import vacuum_sqlite_after_commit
from backend.app.db import build_engine


def test_sqlite_vacuum_reclaims_free_pages_after_committed_deletion(tmp_path, monkeypatch):
    database = build_engine(f"sqlite:///{tmp_path / 'maintenance.sqlite3'}")
    original_create_engine = database_maintenance.create_engine
    maintenance_statements = []

    def observe_maintenance_engine(*args, **kwargs):
        maintenance_engine = original_create_engine(*args, **kwargs)
        event.listen(
            maintenance_engine,
            "before_cursor_execute",
            lambda _connection, _cursor, statement, _parameters, _context, _many: (
                maintenance_statements.append(statement.strip().upper())
            ),
        )
        return maintenance_engine

    monkeypatch.setattr(database_maintenance, "create_engine", observe_maintenance_engine)
    try:
        with database.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE vacuum_fixture (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)"
            )
            connection.execute(
                text("INSERT INTO vacuum_fixture (payload) VALUES (:payload)"),
                [{"payload": "x" * 1000} for _ in range(6000)],
            )
            connection.exec_driver_sql("DELETE FROM vacuum_fixture")

        with database.connect() as connection:
            free_pages_before = connection.exec_driver_sql("PRAGMA freelist_count").scalar_one()
            pages_before = connection.exec_driver_sql("PRAGMA page_count").scalar_one()

        assert free_pages_before > 0
        assert vacuum_sqlite_after_commit(database, resource_kind="contest", resource_id=12)

        with database.connect() as connection:
            free_pages_after = connection.exec_driver_sql("PRAGMA freelist_count").scalar_one()
            pages_after = connection.exec_driver_sql("PRAGMA page_count").scalar_one()

        assert free_pages_after == 0
        assert pages_after < pages_before
        assert maintenance_statements == ["VACUUM"]
    finally:
        database.dispose()


def test_sqlite_vacuum_skips_in_memory_database():
    database = build_engine("sqlite:///:memory:")
    try:
        assert not vacuum_sqlite_after_commit(database, resource_kind="contest", resource_id=12)
    finally:
        database.dispose()


def test_sqlite_vacuum_failure_is_logged_without_raising(tmp_path, monkeypatch, caplog):
    database = build_engine(f"sqlite:///{tmp_path / 'maintenance.sqlite3'}")

    def fail_to_create_maintenance_engine(*_args, **_kwargs):
        raise RuntimeError("maintenance connection unavailable")

    monkeypatch.setattr(database_maintenance, "create_engine", fail_to_create_maintenance_engine)
    try:
        assert not vacuum_sqlite_after_commit(database, resource_kind="contest", resource_id=12)
        assert "sqlite_vacuum_failed" in caplog.text
    finally:
        database.dispose()
