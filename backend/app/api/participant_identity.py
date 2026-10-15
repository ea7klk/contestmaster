"""Public email verification and participant-only magic-link sessions."""

from __future__ import annotations

import hmac
import secrets
import smtplib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.app.api.auth import CSRF_HEADER, _hash_token, normalize_email
from backend.app.config import get_settings
from backend.app.db import get_session
from backend.app.email_delivery import send_participant_magic_link
from backend.app.models import (
    Contest,
    Entry,
    Participant,
    ParticipantEmail,
    ParticipantMagicLink,
    ParticipantSession,
)
from backend.app.rate_limit import enforce_rate_limit, request_identity

router = APIRouter(tags=["participant identity"])
MAGIC_LINK_LIFETIME = timedelta(minutes=15)
PARTICIPANT_SESSION_LIFETIME = timedelta(hours=12)
SESSION_COOKIE = "contestmaster_participant_session"
PARTICIPANT_CSRF_COOKIE = "contestmaster_participant_csrf"


class MagicLinkRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class MagicLinkConsume(BaseModel):
    token: str = Field(min_length=32, max_length=200)


@dataclass(frozen=True, slots=True)
class ParticipantPrincipal:
    participant_id: int
    participant_email_id: int
    email: str
    session_id: int


def _magic_link_url(token: str) -> str:
    settings = get_settings()
    base_url = settings.frontend_base_url.rstrip("/")
    query = urlencode({"token": token})
    return f"{base_url}/participant/verify?{query}"


def _set_participant_cookies(response: Response, token: str, csrf: str) -> None:
    settings = get_settings()
    secure = settings.secure_cookies
    lifetime = int(PARTICIPANT_SESSION_LIFETIME.total_seconds())
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=secure,
        samesite="strict",
        path="/api/v1",
        max_age=lifetime,
    )
    response.set_cookie(
        PARTICIPANT_CSRF_COOKIE,
        csrf,
        httponly=False,
        secure=secure,
        samesite="strict",
        path="/",
        max_age=lifetime,
    )


def _clear_participant_cookies(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        SESSION_COOKIE, path="/api/v1", httponly=True, secure=settings.secure_cookies
    )
    response.delete_cookie(
        PARTICIPANT_CSRF_COOKIE, path="/", httponly=False, secure=settings.secure_cookies
    )


def require_participant(
    request: Request, session: Annotated[Session, Depends(get_session)]
) -> ParticipantPrincipal:
    raw_token = request.cookies.get(SESSION_COOKIE)
    unauthorized = HTTPException(status_code=401, detail="Participant sign-in is required.")
    if not raw_token:
        raise unauthorized
    record = session.scalar(
        select(ParticipantSession).where(ParticipantSession.token_hash == _hash_token(raw_token))
    )
    now = datetime.now(UTC)
    if record is None or record.revoked_at is not None or record.expires_at <= now:
        raise unauthorized
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        cookie_csrf = request.cookies.get(PARTICIPANT_CSRF_COOKIE, "")
        header_csrf = request.headers.get(CSRF_HEADER, "")
        if (
            not cookie_csrf
            or not header_csrf
            or not hmac.compare_digest(cookie_csrf, header_csrf)
            or not hmac.compare_digest(_hash_token(header_csrf), record.csrf_token_hash)
        ):
            raise HTTPException(status_code=403, detail="CSRF validation failed.")
    email = session.get(ParticipantEmail, record.participant_email_id)
    if email is None or email.verified_at is None:
        raise unauthorized
    return ParticipantPrincipal(email.participant_id, email.id, email.email_normalized, record.id)


@router.post("/request-link", status_code=202)
def request_magic_link(
    payload: MagicLinkRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, str]:
    try:
        email_address = normalize_email(payload.email)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    peer = request_identity(request)
    email_fingerprint = _hash_token(email_address)
    enforce_rate_limit(
        request,
        "participant-link-ip",
        limit=30,
        window_seconds=60,
        message="Too many sign-in link requests. Retry later.",
    )
    enforce_rate_limit(
        request,
        "participant-link-email",
        identity=f"{peer}:{email_fingerprint}",
        limit=5,
        window_seconds=3600,
        message="Too many sign-in link requests. Retry later.",
    )

    email = session.scalar(
        select(ParticipantEmail).where(ParticipantEmail.email_normalized == email_address)
    )
    if email is None:
        participant = Participant()
        session.add(participant)
        session.flush()
        email = ParticipantEmail(participant_id=participant.id, email_normalized=email_address)
        session.add(email)
        session.flush()

    now = datetime.now(UTC)
    for prior in session.scalars(
        select(ParticipantMagicLink).where(
            ParticipantMagicLink.participant_email_id == email.id,
            ParticipantMagicLink.consumed_at.is_(None),
        )
    ):
        prior.consumed_at = now
    raw_token = secrets.token_urlsafe(32)
    link = ParticipantMagicLink(
        participant_email_id=email.id,
        token_hash=_hash_token(raw_token),
        created_at=now,
        expires_at=now + MAGIC_LINK_LIFETIME,
    )
    session.add(link)
    session.flush()
    try:
        send_participant_magic_link(email_address, _magic_link_url(raw_token))
        session.commit()
    except (OSError, RuntimeError, ValueError, smtplib.SMTPException) as exc:
        session.rollback()
        raise HTTPException(
            status_code=503,
            detail="Email delivery is temporarily unavailable.",
        ) from exc
    return {"status": "accepted", "message": "If the address can be used, a sign-in link was sent."}


@router.post("/consume-link")
def consume_magic_link(
    payload: MagicLinkConsume,
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    enforce_rate_limit(
        request,
        "participant-link-consume",
        limit=20,
        window_seconds=60,
        message="Too many sign-in link attempts. Retry later.",
    )
    now = datetime.now(UTC)
    link = session.scalar(
        select(ParticipantMagicLink).where(
            ParticipantMagicLink.token_hash == _hash_token(payload.token),
            ParticipantMagicLink.consumed_at.is_(None),
            ParticipantMagicLink.expires_at > now,
        )
    )
    if link is None:
        raise HTTPException(status_code=401, detail="The sign-in link is invalid or expired.")
    email = session.get(ParticipantEmail, link.participant_email_id)
    if email is None:
        raise HTTPException(status_code=401, detail="The sign-in link is invalid or expired.")

    consumed = session.execute(
        update(ParticipantMagicLink)
        .where(
            ParticipantMagicLink.id == link.id,
            ParticipantMagicLink.consumed_at.is_(None),
            ParticipantMagicLink.expires_at > now,
        )
        .values(consumed_at=now)
    )
    if consumed.rowcount != 1:
        raise HTTPException(status_code=401, detail="The sign-in link is invalid or expired.")
    link.consumed_at = now
    if email.verified_at is None:
        email.verified_at = now
    raw_session_token = secrets.token_urlsafe(32)
    raw_csrf = secrets.token_urlsafe(32)
    participant_session = ParticipantSession(
        participant_email_id=email.id,
        token_hash=_hash_token(raw_session_token),
        csrf_token_hash=_hash_token(raw_csrf),
        created_at=now,
        expires_at=now + PARTICIPANT_SESSION_LIFETIME,
    )
    session.add(participant_session)
    session.commit()
    _set_participant_cookies(response, raw_session_token, raw_csrf)
    participant = session.get(Participant, email.participant_id)
    return {
        "participant": {
            "id": email.participant_id,
            "email": email.email_normalized,
            "display_name": participant.display_name if participant else None,
            "callsign": participant.callsign_submitted if participant else None,
        },
        "csrf_token": raw_csrf,
    }


@router.get("/me")
def participant_me(
    principal: Annotated[ParticipantPrincipal, Depends(require_participant)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    participant = session.get(Participant, principal.participant_id)
    return {
        "id": principal.participant_id,
        "email": principal.email,
        "display_name": participant.display_name if participant else None,
        "callsign": participant.callsign_submitted if participant else None,
    }


@router.get("/entries")
def participant_entries(
    principal: Annotated[ParticipantPrincipal, Depends(require_participant)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    rows = session.execute(
        select(Entry, Contest)
        .join(Contest, Contest.id == Entry.contest_id)
        .where(Entry.participant_id == principal.participant_id)
        .order_by(Contest.starts_at.desc(), Entry.id.asc())
    )
    return {
        "items": [
            {
                "id": entry.id,
                "contest_id": contest.id,
                "contest_name": contest.name,
                "contest_slug": contest.slug,
                "entry_key": entry.entry_key,
                "status": entry.status.value,
                "submitted_at": entry.submitted_at,
            }
            for entry, contest in rows
        ]
    }


@router.post("/logout")
def participant_logout(
    response: Response,
    principal: Annotated[ParticipantPrincipal, Depends(require_participant)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, str]:
    record = session.get(ParticipantSession, principal.session_id)
    if record is not None:
        record.revoked_at = datetime.now(UTC)
        session.commit()
    _clear_participant_cookies(response)
    return {"status": "signed_out"}
