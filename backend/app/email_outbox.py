"""Retryable, de-duplicated result email delivery."""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from backend.app.config import get_settings
from backend.app.email_delivery import send_guest_result_notice
from backend.app.models import (
    Contest,
    EmailOutbox,
    GuestEntryEmail,
    ResultPublication,
    ResultPublicationEntry,
)

logger = logging.getLogger("contestmaster.email_outbox")
_dispatch_lock = threading.Lock()
MAX_ATTEMPTS = 6
BATCH_SIZE = 50


def queue_publication_notices(session, publication: ResultPublication) -> int:
    """Queue one uniquely keyed notice for each verified, opted-in published entry."""
    contact_ids = list(
        session.scalars(
            select(GuestEntryEmail.id)
            .join(
                ResultPublicationEntry,
                ResultPublicationEntry.entry_id == GuestEntryEmail.entry_id,
            )
            .where(
                ResultPublicationEntry.publication_id == publication.id,
                GuestEntryEmail.verified_at.is_not(None),
                GuestEntryEmail.revoked_at.is_(None),
                GuestEntryEmail.results_opt_in.is_(True),
            )
        )
    )
    existing = set(
        session.scalars(
            select(EmailOutbox.guest_email_id).where(
                EmailOutbox.publication_id == publication.id,
                EmailOutbox.guest_email_id.in_(contact_ids or [-1]),
            )
        )
    )
    added = 0
    for contact_id in contact_ids:
        if contact_id in existing:
            continue
        session.add(
            EmailOutbox(
                event_key=f"published:{publication.id}:guest-email:{contact_id}",
                guest_email_id=contact_id,
                publication_id=publication.id,
                state="pending",
                attempt_count=0,
                available_at=datetime.now(UTC),
                created_at=datetime.now(UTC),
            )
        )
        added += 1
    session.flush()
    return added


def dispatch_pending_emails(
    session_factory: sessionmaker, *, limit: int = BATCH_SIZE
) -> dict[str, int]:
    """Send due events once per process, persisting bounded retries without sensitive payloads."""
    counts = {"sent": 0, "cancelled": 0, "failed": 0, "pending": 0}
    settings = get_settings()
    if not settings.email_smtp_host or not settings.email_from_address:
        with session_factory() as session:
            counts["pending"] = (
                session.scalar(
                    select(func.count(EmailOutbox.id)).where(EmailOutbox.state == "pending")
                )
                or 0
            )
        if counts["pending"]:
            logger.warning(
                "email_outbox_delivery_not_configured",
                extra={"pending_count": counts["pending"]},
            )
        return counts
    if not _dispatch_lock.acquire(blocking=False):
        return counts
    try:
        with session_factory() as session:
            due_ids = list(
                session.scalars(
                    select(EmailOutbox.id)
                    .where(
                        EmailOutbox.state == "pending",
                        EmailOutbox.available_at <= datetime.now(UTC),
                    )
                    .order_by(EmailOutbox.id)
                    .limit(limit)
                )
            )
        for event_id in due_ids:
            with session_factory() as session:
                event = session.get(EmailOutbox, event_id)
                if event is None or event.state != "pending":
                    continue
                contact = session.get(GuestEntryEmail, event.guest_email_id)
                publication = session.get(ResultPublication, event.publication_id)
                contest = session.get(Contest, publication.contest_id) if publication else None
                if (
                    contact is None
                    or contact.revoked_at is not None
                    or contact.verified_at is None
                    or not contact.results_opt_in
                    or publication is None
                    or contest is None
                ):
                    event.state = "cancelled"
                    session.commit()
                    counts["cancelled"] += 1
                    continue
                email = contact.email_normalized
                contest_name = contest.name
                contest_slug = contest.slug
                publication_number = publication.publication_number
                event_key = event.event_key
                event.attempt_count += 1
                session.commit()
            link = f"{settings.frontend_base_url.rstrip('/')}/contests/{contest_slug}"
            try:
                send_guest_result_notice(email, contest_name, publication_number, link)
            except Exception as exc:  # SMTP exception text may contain private addresses or data.
                with session_factory.begin() as session:
                    event = session.scalar(
                        select(EmailOutbox).where(EmailOutbox.event_key == event_key)
                    )
                    if event is not None and event.state == "pending":
                        event.last_error = type(exc).__name__[:80]
                        if event.attempt_count >= MAX_ATTEMPTS:
                            event.state = "dead"
                        else:
                            delay = min(60 * 2 ** max(event.attempt_count - 1, 0), 86_400)
                            event.available_at = datetime.now(UTC) + timedelta(seconds=delay)
                logger.warning(
                    "result_notice_delivery_failed",
                    extra={"outbox_event_id": event_id, "error_type": type(exc).__name__},
                )
                counts["failed"] += 1
            else:
                with session_factory.begin() as session:
                    event = session.scalar(
                        select(EmailOutbox).where(EmailOutbox.event_key == event_key)
                    )
                    if event is not None and event.state == "pending":
                        event.state = "sent"
                        event.sent_at = datetime.now(UTC)
                        event.last_error = None
                counts["sent"] += 1
        return counts
    finally:
        _dispatch_lock.release()


async def email_outbox_timer(session_factory: sessionmaker, interval_seconds: int = 60) -> None:
    while True:
        await asyncio.to_thread(dispatch_pending_emails, session_factory)
        await asyncio.sleep(interval_seconds)
