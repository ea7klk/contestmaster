"""Single-process timer for nightly master-data checks."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from backend.app.master_data.jobs import sync_cty
from backend.app.metrics import record_master_data_sync
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


REQUIRED_DATASET_KEYS = ("cty",)


def has_all_required_versions(session_factory: sessionmaker) -> bool:
    with session_factory() as session:
        active_keys = set(
            session.scalars(
                select(MasterDataVersion.dataset_key).where(
                    MasterDataVersion.dataset_key.in_(REQUIRED_DATASET_KEYS),
                    MasterDataVersion.status == MasterDataVersionStatus.ACTIVE,
                )
            )
        )
        return active_keys == set(REQUIRED_DATASET_KEYS)


async def run_master_data_sync(
    session_factory: sessionmaker, lock: asyncio.Lock, *, trigger: str = "nightly"
) -> None:
    if lock.locked():
        logger.warning(
            "master_data_sync_skipped",
            extra={"dataset_key": "cty", "trigger": trigger, "reason": "already_running"},
        )
        return
    async with lock:
        for dataset_key, importer in (("cty", sync_cty),):
            logger.info(
                "master_data_sync_attempt_started",
                extra={"dataset_key": dataset_key, "trigger": trigger},
            )
            try:
                result = await asyncio.to_thread(importer, session_factory)
                record_master_data_sync(
                    dataset_key,
                    "changed" if result.get("changed") else "unchanged",
                )
                logger.info(
                    "master_data_sync_observed",
                    extra={"dataset_key": dataset_key, "trigger": trigger, **result},
                )
            except Exception:
                record_master_data_sync(dataset_key, "failed")
                logger.exception(
                    "master_data_sync_error",
                    extra={"dataset_key": dataset_key, "trigger": trigger},
                )


async def nightly_master_data_timer(
    session_factory: sessionmaker,
    lock: asyncio.Lock,
    hour_utc: int,
) -> None:
    while True:
        delay = seconds_until_nightly_run(datetime.now(UTC), hour_utc)
        await asyncio.sleep(delay)
        await run_master_data_sync(session_factory, lock)
