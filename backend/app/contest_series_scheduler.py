"""Single-process internal timer for recurring contest edition creation."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.orm import sessionmaker

from backend.app.contest_series import generate_due_editions

logger = logging.getLogger("contestmaster.contests.scheduler")


async def run_edition_generation(
    session_factory: sessionmaker,
    lock: asyncio.Lock,
    *,
    trigger: str,
) -> None:
    if lock.locked():
        logger.warning(
            "contest_edition_generation_skipped",
            extra={"trigger": trigger, "reason": "already_running"},
        )
        return
    async with lock:
        logger.info("contest_edition_generation_started", extra={"trigger": trigger})
        try:
            result = await asyncio.to_thread(generate_due_editions, session_factory)
            logger.info(
                "contest_edition_generation_completed", extra={"trigger": trigger, **result}
            )
        except Exception:
            logger.exception("contest_edition_generation_failed", extra={"trigger": trigger})


async def contest_edition_timer(
    session_factory: sessionmaker,
    lock: asyncio.Lock,
    interval_seconds: int,
) -> None:
    if interval_seconds < 60:
        raise ValueError("Contest edition timer interval must be at least 60 seconds")
    while True:
        await asyncio.sleep(interval_seconds)
        await run_edition_generation(session_factory, lock, trigger="timer")
