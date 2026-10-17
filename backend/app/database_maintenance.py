"""Post-transaction database maintenance operations."""

from __future__ import annotations

import logging

from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import NullPool

logger = logging.getLogger("contestmaster.database_maintenance")


def vacuum_sqlite_after_commit(
    engine: Engine,
    *,
    resource_kind: str,
    resource_id: int,
) -> bool:
    """Reclaim SQLite free pages after the caller has committed a deletion."""
    if engine.dialect.name != "sqlite":
        return False
    if engine.url.database in {None, "", ":memory:"}:
        logger.debug(
            "sqlite_vacuum_skipped_in_memory",
            extra={"resource_kind": resource_kind, "resource_id": resource_id},
        )
        return False

    logger.info(
        "sqlite_vacuum_started",
        extra={"resource_kind": resource_kind, "resource_id": resource_id},
    )
    # Use a fresh, non-pinging connection so VACUUM is the first SQL statement after
    # deletion. The request session must already be committed and closed by the caller.
    maintenance_engine: Engine | None = None
    try:
        connect_args = engine.dialect.create_connect_args(engine.url)[1]
        maintenance_engine = create_engine(
            engine.url,
            poolclass=NullPool,
            pool_pre_ping=False,
            connect_args=connect_args,
        )
        with maintenance_engine.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as connection:
            connection.exec_driver_sql("VACUUM")
    except Exception:
        logger.exception(
            "sqlite_vacuum_failed",
            extra={"resource_kind": resource_kind, "resource_id": resource_id},
        )
        return False
    finally:
        if maintenance_engine is not None:
            maintenance_engine.dispose()

    logger.info(
        "sqlite_vacuum_completed",
        extra={"resource_kind": resource_kind, "resource_id": resource_id},
    )
    return True
