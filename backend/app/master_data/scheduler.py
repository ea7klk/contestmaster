"""Single-process timer for nightly master-data checks."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from backend.app.master_data.jobs import sync_cty
from backend.app.models import MasterDataVersion, MasterDataVersionStatus

logger = logging.getLogger("contestmaster.master_data.scheduler")


def seconds_until_nightly_run(now: datetime, hour_utc: int) -> float:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if not 0 <= hour_utc <= 23:
        raise ValueError("hour_utc must be between 0 and 23")
    current = now.astimezone(UTC)
    next_run = datetime.combine(current.date(), time(hour_utc), tzinfo=UTC)
    if next_run <= current:
        next_run += timedelta(days=1)
    return (next_run - current).total_seconds()


def has_active_cty_version(session_factory: sessionmaker) -> bool:
    with session_factory() as session:
        return (
            session.scalar(
                select(MasterDataVersion.id).where(
                    MasterDataVersion.dataset_key == "cty",
                    MasterDataVersion.status == MasterDataVersionStatus.ACTIVE,
                )
            )
            is not None
        )


async def run_cty_sync(session_factory: sessionmaker, lock: asyncio.Lock) -> None:
    if lock.locked():
        logger.warning("master_data_sync_skipped", extra={"reason": "already_running"})
        return
    async with lock:
        try:
            result = await asyncio.to_thread(sync_cty, session_factory)
            logger.info("master_data_sync_observed", extra=result)
        except Exception:
            # A bad feed must not prevent the API from serving its existing last-good version.
            logger.exception("master_data_sync_error")


async def nightly_master_data_timer(
    session_factory: sessionmaker,
    lock: asyncio.Lock,
    hour_utc: int,
) -> None:
    while True:
        delay = seconds_until_nightly_run(datetime.now(UTC), hour_utc)
        await asyncio.sleep(delay)
        await run_cty_sync(session_factory, lock)
