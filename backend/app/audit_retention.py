"""Prune expired audit history with ORM-managed transactions."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import sessionmaker

from backend.app.models import AuditEvent

logger = logging.getLogger("contestmaster.audit_retention")
RETENTION = timedelta(days=90)
PRUNE_INTERVAL_SECONDS = 24 * 60 * 60


def prune_expired_audit_events(
    session_factory: sessionmaker, *, now: datetime | None = None
) -> int:
    """Delete audit rows strictly older than 90 days; return the number removed."""
    current = now or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("Audit retention requires an aware UTC instant")
    cutoff = current.astimezone(UTC) - RETENTION
    with session_factory() as session:
        result = session.execute(
            delete(AuditEvent)
            .where(AuditEvent.occurred_at < cutoff)
            .execution_options(synchronize_session=False)
        )
        session.commit()
        return result.rowcount or 0


async def audit_retention_timer(session_factory: sessionmaker) -> None:
    """Run daily cleanup; startup cleanup is called separately by the API lifespan."""
    while True:
        await asyncio.sleep(PRUNE_INTERVAL_SECONDS)
        try:
            removed = await asyncio.to_thread(prune_expired_audit_events, session_factory)
            logger.info("audit_retention_completed", extra={"deleted_count": removed})
        except Exception:
            logger.exception("audit_retention_failed")
