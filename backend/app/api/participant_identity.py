"""Public email verification and participant-only magic-link sessions."""

from __future__ import annotations

import hmac
import re
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

from backend.app.api.auth import (
    CSRF_HEADER,
    _hash_token,
    hash_password,
    normalize_email,
    verify_password,
)
from backend.app.config import get_settings
from backend.app.db import get_session
from backend.app.email_delivery import send_email, send_participant_magic_link
from backend.app.models import (
    Contest,
    Entry,
    Participant,
    ParticipantCallsign,
    ParticipantEmail,
    ParticipantEmailChange,
    ParticipantMagicLink,
    ParticipantPasswordReset,
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


class ParticipantRegistration(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    callsign: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=12, max_length=1024)
    display_name: str | None = Field(default=None, max_length=160)


class ParticipantPasswordLogin(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class TokenRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class PasswordResetRequest(BaseModel):
    token: str = Field(min_length=32, max_length=200)
    password: str = Field(min_length=12, max_length=1024)


class CallsignRequest(BaseModel):
    callsign: str = Field(min_length=3, max_length=32)


class EmailChangeRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class ParticipantProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=160)


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


def _account_link(path: str, token: str) -> str:
    settings = get_settings()
    return f"{settings.frontend_base_url.rstrip('/')}{path}?{urlencode({'token': token})}"


def _new_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, _hash_token(token)


def _validate_callsign(value: str) -> tuple[str, str]:
    submitted = value.strip().upper()
    if (
        not re.fullmatch(r"[A-Z0-9/]{3,32}", submitted)
        or not any(c.isalpha() for c in submitted)
        or not any(c.isdigit() for c in submitted)
    ):
        raise ValueError("Enter a valid amateur radio callsign.")
    return value.strip(), submitted


def _start_participant_session(
    session: Session, email: ParticipantEmail, response: Response
) -> str:
    now = datetime.now(UTC)
    raw_session = secrets.token_urlsafe(32)
    raw_csrf = secrets.token_urlsafe(32)
    record = ParticipantSession(
        participant_email_id=email.id,
        token_hash=_hash_token(raw_session),
        csrf_token_hash=_hash_token(raw_csrf),
        created_at=now,
        expires_at=now + PARTICIPANT_SESSION_LIFETIME,
    )
    session.add(record)
    session.flush()
    _set_participant_cookies(response, raw_session, raw_csrf)
    return raw_csrf


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


@router.post("/register", status_code=202)
def register_participant(
    payload: ParticipantRegistration,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, str]:
    enforce_rate_limit(
        request,
        "participant-register-ip",
        limit=10,
        window_seconds=3600,
        message="Too many registration attempts.",
    )
    try:
        address = normalize_email(payload.email)
        submitted_call, call = _validate_callsign(payload.callsign)
        password = hash_password(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    email = session.scalar(
        select(ParticipantEmail).where(ParticipantEmail.email_normalized == address)
    )
    if email is not None:
        participant = session.get(Participant, email.participant_id)
        if participant is None or participant.password_hash is not None:
            raise HTTPException(status_code=409, detail="This email is already registered.")
    else:
        participant = Participant(display_name=payload.display_name)
        session.add(participant)
        session.flush()
        email = ParticipantEmail(
            participant_id=participant.id,
            email_normalized=address,
            is_primary=True,
        )
        session.add(email)
        session.flush()
    existing_call = session.scalar(
        select(ParticipantCallsign).where(ParticipantCallsign.callsign_normalized == call)
    )
    if existing_call is not None and existing_call.participant_id != participant.id:
        raise HTTPException(
            status_code=409, detail="This callsign is already attached to an account."
        )
    participant.password_hash = password
    participant.display_name = payload.display_name or participant.display_name
    participant.callsign_submitted = submitted_call
    participant.callsign_normalized = call
    if existing_call is None:
        session.add(
            ParticipantCallsign(
                participant_id=participant.id,
                callsign_submitted=submitted_call,
                callsign_normalized=call,
                is_primary=True,
                created_at=datetime.now(UTC),
            )
        )
    email.is_primary = True
    email.is_active = True
    raw_token, token_hash = _new_token()
    now = datetime.now(UTC)
    link = ParticipantMagicLink(
        participant_email_id=email.id,
        token_hash=token_hash,
        created_at=now,
        expires_at=now + MAGIC_LINK_LIFETIME,
    )
    session.add(link)
    try:
        session.flush()
        send_participant_magic_link(address, _magic_link_url(raw_token))
        session.commit()
    except (OSError, RuntimeError, ValueError, smtplib.SMTPException) as exc:
        session.rollback()
        raise HTTPException(
            status_code=503, detail="Email delivery is temporarily unavailable."
        ) from exc
    return {"status": "verification_sent"}


@router.post("/login")
def login_participant(
    payload: ParticipantPasswordLogin,
    response: Response,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    try:
        address = normalize_email(payload.email)
    except ValueError:
        address = ""
    enforce_rate_limit(
        request,
        "participant-login-ip",
        limit=60,
        window_seconds=60,
        message="Too many sign-in attempts.",
    )
    peer = request_identity(request)
    enforce_rate_limit(
        request,
        "participant-login-account",
        identity=f"{peer}:{_hash_token(address)}",
        limit=10,
        window_seconds=900,
        message="Too many sign-in attempts.",
    )
    email = (
        session.scalar(
            select(ParticipantEmail).where(
                ParticipantEmail.email_normalized == address,
                ParticipantEmail.is_active.is_(True),
                ParticipantEmail.is_primary.is_(True),
            )
        )
        if address
        else None
    )
    participant = session.get(Participant, email.participant_id) if email else None
    if (
        participant is None
        or not participant.is_active
        or participant.password_hash is None
        or email is None
        or email.verified_at is None
        or not verify_password(payload.password, participant.password_hash)
    ):
        raise HTTPException(
            status_code=401, detail="Email or password is incorrect, or the email is not verified."
        )
    csrf = _start_participant_session(session, email, response)
    session.commit()
    return {
        "participant": {
            "id": participant.id,
            "email": email.email_normalized,
            "display_name": participant.display_name,
            "callsign": participant.callsign_submitted,
        },
        "csrf_token": csrf,
    }


@router.post("/forgot-password", status_code=202)
def forgot_participant_password(
    payload: TokenRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, str]:
    try:
        address = normalize_email(payload.email)
    except ValueError:
        address = ""
    enforce_rate_limit(
        request,
        "participant-reset-ip",
        limit=10,
        window_seconds=3600,
        message="Too many reset requests.",
    )
    email = (
        session.scalar(
            select(ParticipantEmail).where(
                ParticipantEmail.email_normalized == address,
                ParticipantEmail.is_active.is_(True),
                ParticipantEmail.verified_at.is_not(None),
            )
        )
        if address
        else None
    )
    participant = session.get(Participant, email.participant_id) if email else None
    if participant and participant.is_active:
        token, token_hash = _new_token()
        now = datetime.now(UTC)
        record = ParticipantPasswordReset(
            participant_id=participant.id,
            participant_email_id=email.id,
            token_hash=token_hash,
            created_at=now,
            expires_at=now + timedelta(minutes=30),
        )
        session.add(record)
        try:
            session.flush()
            send_email(
                address,
                "Reset your Contestmaster password",
                "Use this one-time link to reset your password. It expires in 30 minutes.",
                _account_link("/participant/reset-password", token),
            )
            session.commit()
        except (OSError, RuntimeError, ValueError, smtplib.SMTPException) as exc:
            session.rollback()
            raise HTTPException(
                status_code=503, detail="Email delivery is temporarily unavailable."
            ) from exc
    return {
        "status": "accepted",
        "message": "If the account is eligible, a password reset link was sent.",
    }


@router.post("/reset-password")
def reset_participant_password(
    payload: PasswordResetRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, str]:
    enforce_rate_limit(
        request,
        "participant-reset-consume-ip",
        limit=20,
        window_seconds=60,
        message="Too many password reset attempts.",
    )
    now = datetime.now(UTC)
    record = session.scalar(
        select(ParticipantPasswordReset).where(
            ParticipantPasswordReset.token_hash == _hash_token(payload.token),
            ParticipantPasswordReset.consumed_at.is_(None),
            ParticipantPasswordReset.expires_at > now,
        )
    )
    if record is None:
        raise HTTPException(
            status_code=400, detail="The password reset link is invalid or expired."
        )
    participant = session.get(Participant, record.participant_id)
    if participant is None or not participant.is_active:
        raise HTTPException(
            status_code=400, detail="The password reset link is invalid or expired."
        )
    participant.password_hash = hash_password(payload.password)
    record.consumed_at = now
    for other in session.scalars(
        select(ParticipantPasswordReset).where(
            ParticipantPasswordReset.participant_id == participant.id,
            ParticipantPasswordReset.consumed_at.is_(None),
        )
    ):
        other.consumed_at = now
    participant_email_ids = select(ParticipantEmail.id).where(
        ParticipantEmail.participant_id == participant.id
    )
    for browser_session in session.scalars(
        select(ParticipantSession).where(
            ParticipantSession.participant_email_id.in_(participant_email_ids),
            ParticipantSession.revoked_at.is_(None),
        )
    ):
        browser_session.revoked_at = now
    session.commit()
    return {"status": "password_updated"}


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
    participant = session.get(Participant, email.participant_id) if email else None
    if (
        email is None
        or email.verified_at is None
        or not email.is_active
        or participant is None
        or not participant.is_active
    ):
        raise unauthorized
    return ParticipantPrincipal(email.participant_id, email.id, email.email_normalized, record.id)


@router.get("/me")
def participant_me(
    actor: Annotated[ParticipantPrincipal, Depends(require_participant)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    participant = session.get(Participant, actor.participant_id)
    callsigns = list(
        session.scalars(
            select(ParticipantCallsign)
            .where(ParticipantCallsign.participant_id == actor.participant_id)
            .order_by(ParticipantCallsign.is_primary.desc(), ParticipantCallsign.id)
        )
    )
    emails = list(
        session.scalars(
            select(ParticipantEmail)
            .where(
                ParticipantEmail.participant_id == actor.participant_id,
                ParticipantEmail.is_active.is_(True),
            )
            .order_by(ParticipantEmail.is_primary.desc(), ParticipantEmail.id)
        )
    )
    return {
        "id": actor.participant_id,
        "email": actor.email,
        "display_name": participant.display_name if participant else None,
        "callsigns": [
            {"id": item.id, "callsign": item.callsign_submitted, "is_primary": item.is_primary}
            for item in callsigns
        ],
        "emails": [
            {
                "email": item.email_normalized,
                "is_primary": item.is_primary,
                "verified": item.verified_at is not None,
            }
            for item in emails
        ],
    }


@router.patch("/me")
def update_participant_profile(
    payload: ParticipantProfileUpdate,
    actor: Annotated[ParticipantPrincipal, Depends(require_participant)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    participant = session.get(Participant, actor.participant_id)
    if participant is None:
        raise HTTPException(status_code=404, detail="Participant account not found.")
    if "display_name" in payload.model_fields_set:
        participant.display_name = payload.display_name.strip() if payload.display_name else None
    session.commit()
    return {"id": participant.id, "display_name": participant.display_name}


@router.post("/callsigns", status_code=201)
def add_participant_callsign(
    payload: CallsignRequest,
    actor: Annotated[ParticipantPrincipal, Depends(require_participant)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    try:
        submitted, normalized = _validate_callsign(payload.callsign)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if session.scalar(
        select(ParticipantCallsign.id).where(ParticipantCallsign.callsign_normalized == normalized)
    ):
        raise HTTPException(
            status_code=409, detail="This callsign is already attached to an account."
        )
    item = ParticipantCallsign(
        participant_id=actor.participant_id,
        callsign_submitted=submitted,
        callsign_normalized=normalized,
        created_at=datetime.now(UTC),
    )
    session.add(item)
    session.commit()
    return {"id": item.id, "callsign": item.callsign_submitted, "is_primary": False}


@router.delete("/callsigns/{callsign_id}", status_code=204)
def remove_participant_callsign(
    callsign_id: int,
    actor: Annotated[ParticipantPrincipal, Depends(require_participant)],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    item = session.scalar(
        select(ParticipantCallsign).where(
            ParticipantCallsign.participant_id == actor.participant_id,
            ParticipantCallsign.id == callsign_id,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Callsign not found.")
    if item.is_primary:
        raise HTTPException(status_code=409, detail="The primary callsign cannot be removed.")
    session.delete(item)
    session.commit()
    return Response(status_code=204)


@router.post("/email-change", status_code=202)
def begin_participant_email_change(
    payload: EmailChangeRequest,
    actor: Annotated[ParticipantPrincipal, Depends(require_participant)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, str]:
    try:
        target = normalize_email(payload.email)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if target == actor.email or session.scalar(
        select(ParticipantEmail.id).where(ParticipantEmail.email_normalized == target)
    ):
        raise HTTPException(status_code=409, detail="This email is already in use.")
    old_raw, old_hash = _new_token()
    new_raw, new_hash = _new_token()
    now = datetime.now(UTC)
    change = ParticipantEmailChange(
        participant_id=actor.participant_id,
        old_email_id=actor.participant_email_id,
        new_email_normalized=target,
        old_token_hash=old_hash,
        new_token_hash=new_hash,
        created_at=now,
        expires_at=now + timedelta(hours=24),
    )
    session.add(change)
    try:
        session.flush()
        send_email(
            actor.email,
            "Confirm your Contestmaster email change",
            "Confirm this email change from your current address. It expires in 24 hours.",
            _account_link("/participant/confirm-email-change", old_raw),
        )
        send_email(
            target,
            "Confirm your new Contestmaster email",
            "Confirm this address to complete the email change. It expires in 24 hours.",
            _account_link("/participant/confirm-email-change", new_raw),
        )
        session.commit()
    except (OSError, RuntimeError, ValueError, smtplib.SMTPException) as exc:
        session.rollback()
        raise HTTPException(
            status_code=503, detail="Email delivery is temporarily unavailable."
        ) from exc
    return {"status": "confirmation_sent"}


@router.post("/confirm-email-change")
def confirm_participant_email_change(
    payload: MagicLinkConsume,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, str]:
    now = datetime.now(UTC)
    token_hash = _hash_token(payload.token)
    change = session.scalar(
        select(ParticipantEmailChange).where(
            (
                (ParticipantEmailChange.old_token_hash == token_hash)
                & ParticipantEmailChange.old_confirmed_at.is_(None)
            )
            | (
                (ParticipantEmailChange.new_token_hash == token_hash)
                & ParticipantEmailChange.new_confirmed_at.is_(None)
            ),
            ParticipantEmailChange.completed_at.is_(None),
            ParticipantEmailChange.expires_at > now,
        )
    )
    if change is None:
        raise HTTPException(
            status_code=400, detail="The email confirmation link is invalid or expired."
        )
    if hmac.compare_digest(change.old_token_hash, token_hash):
        change.old_confirmed_at = now
    else:
        change.new_confirmed_at = now
    if change.old_confirmed_at is not None and change.new_confirmed_at is not None:
        old_email = session.get(ParticipantEmail, change.old_email_id)
        if old_email is None:
            raise HTTPException(
                status_code=400, detail="The email confirmation link is invalid or expired."
            )
        old_email.is_primary = False
        old_email.is_active = False
        new_email = ParticipantEmail(
            participant_id=change.participant_id,
            email_normalized=change.new_email_normalized,
            verified_at=now,
            is_primary=True,
            is_active=True,
        )
        session.add(new_email)
        change.completed_at = now
        participant_email_ids = select(ParticipantEmail.id).where(
            ParticipantEmail.participant_id == change.participant_id
        )
        for old_session in session.scalars(
            select(ParticipantSession).where(
                ParticipantSession.participant_email_id.in_(participant_email_ids),
                ParticipantSession.revoked_at.is_(None),
            )
        ):
            old_session.revoked_at = now
    session.commit()
    return {"status": "confirmed", "complete": str(change.completed_at is not None).lower()}


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
        email = ParticipantEmail(
            participant_id=participant.id, email_normalized=email_address, is_primary=True
        )
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
    participant = session.get(Participant, email.participant_id) if email else None
    if email is None or not email.is_active or participant is None or not participant.is_active:
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
    return {
        "participant": {
            "id": email.participant_id,
            "email": email.email_normalized,
            "display_name": participant.display_name if participant else None,
            "callsign": participant.callsign_submitted if participant else None,
        },
        "csrf_token": raw_csrf,
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
