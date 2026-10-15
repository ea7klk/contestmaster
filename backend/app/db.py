from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, MetaData, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.app.config import ensure_sqlite_parent, get_settings


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


def build_engine(database_url: str | None = None, busy_timeout_ms: int | None = None) -> Engine:
    settings = get_settings()
    url = database_url or settings.database_url
    timeout_ms = settings.sqlite_busy_timeout_ms if busy_timeout_ms is None else busy_timeout_ms
    if timeout_ms <= 0:
        raise ValueError("busy_timeout_ms must be positive")
    ensure_sqlite_parent(url)
    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": timeout_ms / 1000}
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def configure_sqlite(dbapi_connection: Any, _record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute(f"PRAGMA busy_timeout={int(timeout_ms)}")
            if url != "sqlite:///:memory:":
                cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


engine = build_engine()
SessionFactory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    with SessionFactory() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise


@contextmanager
def transaction(session: Session) -> Generator[Session, None, None]:
    """Explicit short transaction boundary for a unit of application work."""
    with session.begin():
        yield session
