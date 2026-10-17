"""Entry-scoped guest email consent and verification flows."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.app.api.auth import normalize_email
from backend.app.models import (
    EmailOutbox,
    Entry,
    EntryAccessGrant,
    GuestEntryEmail,
    GuestEntryEmailVerification,
)

GUEST_EMAIL_VERIFICATION_TTL = timedelta(hours=24)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def prepare_guest_email(
    session: Session,
    *,
    entry: Entry,
    email: str,
    source: str,
    access_opt_in: bool,
    results_opt_in: bool,
    locale: str = "en",
) -> tuple[GuestEntryEmail, str | None]:
    """Persist separate consent flags and return a raw one-time token only when needed."""
    normalized = normalize_email(email)
    if locale not in {"en", "de", "fr", "es", "it"}:
        locale = "en"
    if not (access_opt_in or results_opt_in):
        current = session.scalar(
            select(GuestEntryEmail).where(GuestEntryEmail.entry_id == entry.id)
        )
        if current is not None:
            now = datetime.now(UTC)
            current.access_opt_in = False
            current.results_opt_in = False
            current.revoked_at = now
            current.updated_at = now
            current.email_normalized = f"revoked-{current.id}@deleted.invalid"
            session.execute(
                update(EntryAccessGrant)
                .where(EntryAccessGrant.guest_email_id == current.id)
                .values(revoked_at=now)
            )
            session.execute(
                update(GuestEntryEmailVerification)
                .where(
                    GuestEntryEmailVerification.guest_email_id == current.id,
                    GuestEntryEmailVerification.consumed_at.is_(None),
                )
                .values(consumed_at=now)
            )
            session.execute(
                update(EmailOutbox)
                .where(
                    EmailOutbox.guest_email_id == current.id,
                    EmailOutbox.state == "pending",
                )
                .values(state="cancelled")
            )
            session.flush()
            return current, None
        raise ValueError("Select at least one optional email use or leave email blank.")

    now = datetime.now(UTC)
    contact = session.scalar(select(GuestEntryEmail).where(GuestEntryEmail.entry_id == entry.id))
    address_changed = contact is None or contact.email_normalized != normalized
    if contact is None:
        contact = GuestEntryEmail(
            entry_id=entry.id,
            email_normalized=normalized,
            source=source,
            locale=locale,
            access_opt_in=access_opt_in,
            results_opt_in=results_opt_in,
            created_at=now,
            updated_at=now,
        )
        session.add(contact)
        session.flush()
    else:
        contact.email_normalized = normalized
        contact.source = source
        contact.locale = locale
        contact.access_opt_in = access_opt_in
        contact.results_opt_in = results_opt_in
        contact.revoked_at = None
        contact.updated_at = now
        if address_changed:
            contact.verified_at = None
            session.execute(
                update(EntryAccessGrant)
                .where(EntryAccessGrant.guest_email_id == contact.id)
                .values(revoked_at=now)
            )
            session.execute(
                update(EmailOutbox)
                .where(
                    EmailOutbox.guest_email_id == contact.id,
                    EmailOutbox.state == "pending",
                )
                .values(state="cancelled")
            )
        session.flush()

    if contact.verified_at is not None and not address_changed:
        return contact, None

    session.execute(
        update(GuestEntryEmailVerification)
        .where(
            GuestEntryEmailVerification.guest_email_id == contact.id,
            GuestEntryEmailVerification.consumed_at.is_(None),
        )
        .values(consumed_at=now)
    )
    token = secrets.token_urlsafe(32)
    session.add(
        GuestEntryEmailVerification(
            guest_email_id=contact.id,
            token_hash=_token_hash(token),
            created_at=now,
            expires_at=now + GUEST_EMAIL_VERIFICATION_TTL,
        )
    )
    session.flush()
    return contact, token


def verify_guest_email(session: Session, token: str) -> tuple[GuestEntryEmail, str | None]:
    """Consume one verification token and optionally issue an entry-scoped access grant."""
    now = datetime.now(UTC)
    verification = session.scalar(
        select(GuestEntryEmailVerification).where(
            GuestEntryEmailVerification.token_hash == _token_hash(token),
            GuestEntryEmailVerification.consumed_at.is_(None),
            GuestEntryEmailVerification.expires_at > now,
        )
    )
    if verification is None:
        raise ValueError("This verification link is invalid, expired, or already used.")
    contact = session.get(GuestEntryEmail, verification.guest_email_id)
    if contact is None or contact.revoked_at is not None:
        raise ValueError("This verification link is no longer valid.")
    verification.consumed_at = now
    contact.verified_at = now
    contact.updated_at = now
    access_token = None
    if contact.access_opt_in:
        access_token = secrets.token_urlsafe(32)
        session.add(
            EntryAccessGrant(
                entry_id=contact.entry_id,
                guest_email_id=contact.id,
                token_hash=_token_hash(access_token),
                created_at=now,
            )
        )
    session.flush()
    return contact, access_token
