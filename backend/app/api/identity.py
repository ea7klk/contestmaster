"""Privileged sign-in and administrator account provisioning endpoints."""

from __future__ import annotations

import hashlib
import secrets
import smtplib
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.auth import (
    AuthenticatedUser,
    GlobalAdministrator,
    authenticate_password,
    clear_session_cookies,
    hash_password,
    issue_session,
    normalize_email,
    set_session_cookies,
    verify_password,
)
from backend.app.api.errors import API_ERROR_RESPONSES
from backend.app.audit import record_audit_event
from backend.app.config import get_settings
from backend.app.db import get_session
from backend.app.email_delivery import send_email
from backend.app.models import (
    Participant,
    ParticipantCallsign,
    ParticipantEmail,
    ParticipantSession,
    SystemPasswordReset,
    SystemRole,
    SystemSession,
    SystemUser,
)
from backend.app.rate_limit import enforce_rate_limit, request_identity

router = APIRouter(tags=["identity"])


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class PasswordResetConsume(BaseModel):
    token: str = Field(min_length=32, max_length=200)
    password: str = Field(min_length=12, max_length=1024)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=12, max_length=1024)


class UserCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    username: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=12, max_length=1024)
    role: str = Field(
        default="contest_admin", pattern="^(contest_admin|contest_manager|global_administrator)$"
    )
    must_change_password: bool = False
    audit_reason: str | None = Field(default=None, max_length=2000)


class UserUpdateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    username: str | None = Field(default=None, min_length=1, max_length=80)
    email: str | None = Field(default=None, min_length=3, max_length=320)
    display_name: str | None = Field(default=None, min_length=1, max_length=160)
    role: str | None = Field(
        default=None, pattern="^(contest_admin|contest_manager|global_administrator)$"
    )
    is_active: bool | None = None
    audit_reason: str | None = Field(default=None, max_length=2000)


class ParticipantAdminUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    display_name: str | None = Field(default=None, max_length=160)
    is_active: bool | None = None


def _user_response(user: SystemUser) -> dict[str, object]:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email_normalized,
        "display_name": user.display_name,
        "role": "global_administrator"
        if user.role is SystemRole.GLOBAL_ADMINISTRATOR
        else "contest_admin",
        "is_active": user.is_active,
        "must_change_password": user.must_change_password,
    }


@router.post("/login", responses=API_ERROR_RESPONSES)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    peer = request_identity(request)
    email_fingerprint = hashlib.sha256(payload.email.strip().casefold().encode()).hexdigest()
    enforce_rate_limit(
        request,
        "privileged-login-ip",
        limit=60,
        window_seconds=60,
        message="Too many sign-in attempts. Retry later.",
    )
    enforce_rate_limit(
        request,
        "privileged-login-account",
        identity=f"{peer}:{email_fingerprint}",
        limit=10,
        window_seconds=900,
        message="Too many sign-in attempts. Retry later.",
    )
    try:
        user = authenticate_password(session, payload.email, payload.password)
    except ValueError:
        user = None
    if user is None:
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    session_token, csrf_token, _record = issue_session(session, user)
    session.commit()
    set_session_cookies(response, session_token, csrf_token)
    return {"user": _user_response(user), "csrf_token": csrf_token}


@router.post("/change-password", responses=API_ERROR_RESPONSES)
def change_system_password(
    payload: PasswordChangeRequest,
    request: Request,
    response: Response,
    actor: AuthenticatedUser,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    user = session.get(SystemUser, actor.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Authentication is required.")
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="The current password is incorrect.")
    if verify_password(payload.new_password, user.password_hash):
        raise HTTPException(
            status_code=422, detail="The new password must differ from the current password."
        )
    try:
        user.password_hash = hash_password(payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    user.must_change_password = False
    now = datetime.now(UTC)
    for existing in session.scalars(
        select(SystemSession).where(
            SystemSession.user_id == user.id, SystemSession.revoked_at.is_(None)
        )
    ):
        existing.revoked_at = now
    session_token, csrf_token, _record = issue_session(session, user)
    record_audit_event(
        session,
        actor_user_id=user.id,
        action="system_user.password_changed",
        target_type="system_user",
        target_id=user.id,
        request_id=getattr(request.state, "request_id", None),
    )
    session.commit()
    set_session_cookies(response, session_token, csrf_token)
    return {
        "status": "password_updated",
        "user": _user_response(user),
        "csrf_token": csrf_token,
    }


@router.post("/logout", responses=API_ERROR_RESPONSES)
def logout(
    request: Request,
    response: Response,
    actor: AuthenticatedUser,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, str]:
    from datetime import UTC, datetime

    del actor
    raw_token = request.cookies.get("contestmaster_session", "")
    from hashlib import sha256

    token_hash = sha256(raw_token.encode("utf-8")).hexdigest()
    from backend.app.models import SystemSession

    record = session.scalar(select(SystemSession).where(SystemSession.token_hash == token_hash))
    if record is not None and record.revoked_at is None:
        record.revoked_at = datetime.now(UTC)
        session.commit()
    clear_session_cookies(response)
    return {"status": "signed_out"}


@router.get("/me", responses=API_ERROR_RESPONSES)
def current_user(actor: AuthenticatedUser) -> dict[str, object]:
    return {
        "id": actor.user_id,
        "username": actor.username,
        "email": actor.email,
        "display_name": actor.display_name,
        "role": "global_administrator"
        if actor.role is SystemRole.GLOBAL_ADMINISTRATOR
        else "contest_admin",
        "must_change_password": actor.must_change_password,
    }


@router.post("/forgot-password", status_code=202)
def forgot_system_password(
    payload: PasswordResetRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, str]:
    try:
        address = normalize_email(payload.email)
    except ValueError:
        address = ""
    enforce_rate_limit(
        request,
        "system-password-reset-ip",
        limit=10,
        window_seconds=3600,
        message="Too many password reset requests.",
    )
    user = (
        session.scalar(select(SystemUser).where(SystemUser.email_normalized == address))
        if address
        else None
    )
    if user is not None and user.is_active:
        raw = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw.encode()).hexdigest()
        now = datetime.now(UTC)
        session.add(
            SystemPasswordReset(
                user_id=user.id,
                token_hash=token_hash,
                created_at=now,
                expires_at=now + timedelta(minutes=30),
            )
        )
        query = urlencode({"token": raw})
        link = f"{get_settings().frontend_base_url.rstrip('/')}/reset-password?{query}"
        try:
            session.flush()
            send_email(
                address,
                "Reset your Contestmaster password",
                "Use this one-time link to reset your password. It expires in 30 minutes.",
                link,
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
def consume_system_password_reset(
    payload: PasswordResetConsume,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, str]:
    enforce_rate_limit(
        request,
        "system-password-reset-consume-ip",
        limit=20,
        window_seconds=60,
        message="Too many password reset attempts.",
    )
    now = datetime.now(UTC)
    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()
    record = session.scalar(
        select(SystemPasswordReset).where(
            SystemPasswordReset.token_hash == token_hash,
            SystemPasswordReset.consumed_at.is_(None),
            SystemPasswordReset.expires_at > now,
        )
    )
    if record is None:
        raise HTTPException(
            status_code=400, detail="The password reset link is invalid or expired."
        )
    user = session.get(SystemUser, record.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=400, detail="The password reset link is invalid or expired."
        )
    user.password_hash = hash_password(payload.password)
    user.must_change_password = False
    record.consumed_at = now
    for previous in session.scalars(
        select(SystemPasswordReset).where(
            SystemPasswordReset.user_id == user.id,
            SystemPasswordReset.consumed_at.is_(None),
        )
    ):
        previous.consumed_at = now
    for browser_session in session.scalars(
        select(SystemSession).where(
            SystemSession.user_id == user.id, SystemSession.revoked_at.is_(None)
        )
    ):
        browser_session.revoked_at = now
    session.commit()
    return {"status": "password_updated"}


@router.post("/admin/users", status_code=201, responses=API_ERROR_RESPONSES)
def create_contest_manager(
    payload: UserCreateRequest,
    actor: GlobalAdministrator,
    session: Annotated[Session, Depends(get_session)],
    request: Request,
) -> dict[str, object]:
    try:
        email = normalize_email(payload.email)
        password_hash = hash_password(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    user = SystemUser(
        username=payload.username,
        email_normalized=email,
        display_name=payload.display_name,
        role=(
            SystemRole.GLOBAL_ADMINISTRATOR
            if payload.role == "global_administrator"
            else SystemRole.CONTEST_MANAGER
        ),
        password_hash=password_hash,
        must_change_password=payload.must_change_password,
    )
    session.add(user)
    try:
        session.flush()
        record_audit_event(
            session,
            actor_user_id=actor.user_id,
            action="system_user.created",
            target_type="system_user",
            target_id=user.id,
            reason=payload.audit_reason,
            metadata={"role": user.role.value},
            request_id=getattr(request.state, "request_id", None),
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Username or email is already in use.") from exc
    session.refresh(user)
    return _user_response(user)


@router.get("/admin/users")
def list_system_users(
    _actor: GlobalAdministrator,
    session: Annotated[Session, Depends(get_session)],
    q: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, object]:
    if page < 1 or not 1 <= page_size <= 100:
        raise HTTPException(status_code=422, detail="Page must be positive and page_size 1–100.")
    statement = select(SystemUser)
    count_statement = select(func.count()).select_from(SystemUser)
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        from sqlalchemy import or_

        where = or_(
            SystemUser.username.ilike(pattern),
            SystemUser.email_normalized.ilike(pattern),
            SystemUser.display_name.ilike(pattern),
        )
        statement = statement.where(where)
        count_statement = count_statement.where(where)
    users = list(
        session.scalars(
            statement.order_by(SystemUser.id).offset((page - 1) * page_size).limit(page_size)
        )
    )
    return {
        "items": [_user_response(user) for user in users],
        "total": session.scalar(count_statement) or 0,
        "page": page,
        "page_size": page_size,
    }


@router.patch("/admin/users/{user_id}")
def update_system_user(
    user_id: int,
    payload: UserUpdateRequest,
    actor: GlobalAdministrator,
    session: Annotated[Session, Depends(get_session)],
    request: Request,
) -> dict[str, object]:
    from datetime import UTC, datetime

    from backend.app.models import SystemSession

    user = session.get(SystemUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    was_active_global = user.role is SystemRole.GLOBAL_ADMINISTRATOR and user.is_active
    changes = payload.model_dump(exclude_unset=True, exclude={"audit_reason"})
    role_value = changes.pop("role", None)
    if role_value:
        user.role = (
            SystemRole.GLOBAL_ADMINISTRATOR
            if role_value == "global_administrator"
            else SystemRole.CONTEST_MANAGER
        )
    if changes.get("email") is not None:
        try:
            user.email_normalized = normalize_email(changes.pop("email"))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    for key, value in changes.items():
        if value is not None:
            setattr(user, key, value)
    active_global_count = (
        session.scalar(
            select(func.count())
            .select_from(SystemUser)
            .where(
                SystemUser.role == SystemRole.GLOBAL_ADMINISTRATOR, SystemUser.is_active.is_(True)
            )
        )
        or 0
    )
    if (
        was_active_global
        and (user.role is not SystemRole.GLOBAL_ADMINISTRATOR or not user.is_active)
        and active_global_count < 1
    ):
        raise HTTPException(
            status_code=409, detail="At least one active global administrator must remain."
        )
    if not user.is_active or role_value not in (None, "global_administrator"):
        now = datetime.now(UTC)
        for browser_session in session.scalars(
            select(SystemSession).where(
                SystemSession.user_id == user.id, SystemSession.revoked_at.is_(None)
            )
        ):
            browser_session.revoked_at = now
    try:
        session.flush()
        record_audit_event(
            session,
            actor_user_id=actor.user_id,
            action="system_user.updated",
            target_type="system_user",
            target_id=user.id,
            reason=payload.audit_reason,
            metadata={"fields": sorted(changes)},
            request_id=getattr(request.state, "request_id", None),
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Username or email is already in use.") from exc
    return _user_response(user)


@router.get("/admin/participants")
def list_participant_accounts(
    _actor: GlobalAdministrator,
    session: Annotated[Session, Depends(get_session)],
    q: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, object]:
    if page < 1 or not 1 <= page_size <= 100:
        raise HTTPException(status_code=422, detail="Page must be positive and page_size 1–100.")
    statement = select(Participant)
    count_statement = select(func.count()).select_from(Participant)
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        participant_ids = (
            select(ParticipantEmail.participant_id)
            .where(ParticipantEmail.email_normalized.ilike(pattern))
            .union(
                select(ParticipantCallsign.participant_id).where(
                    ParticipantCallsign.callsign_normalized.ilike(pattern)
                )
            )
        )
        where = (Participant.id.in_(participant_ids)) | Participant.display_name.ilike(pattern)
        statement = statement.where(where)
        count_statement = count_statement.where(where)
    participants = list(
        session.scalars(
            statement.order_by(Participant.id).offset((page - 1) * page_size).limit(page_size)
        )
    )
    items = []
    for participant in participants:
        emails = list(
            session.scalars(
                select(ParticipantEmail)
                .where(ParticipantEmail.participant_id == participant.id)
                .order_by(ParticipantEmail.is_primary.desc(), ParticipantEmail.id)
            )
        )
        callsigns = list(
            session.scalars(
                select(ParticipantCallsign)
                .where(ParticipantCallsign.participant_id == participant.id)
                .order_by(ParticipantCallsign.is_primary.desc(), ParticipantCallsign.id)
            )
        )
        items.append(
            {
                "id": participant.id,
                "display_name": participant.display_name,
                "is_active": participant.is_active,
                "has_password": participant.password_hash is not None,
                "emails": [
                    {
                        "email": email.email_normalized,
                        "verified": email.verified_at is not None,
                        "active": email.is_active,
                    }
                    for email in emails
                ],
                "callsigns": [call.callsign_submitted for call in callsigns],
            }
        )
    return {
        "items": items,
        "total": session.scalar(count_statement) or 0,
        "page": page,
        "page_size": page_size,
    }


@router.patch("/admin/participants/{participant_id}")
def update_participant_account(
    participant_id: int,
    payload: ParticipantAdminUpdate,
    actor: GlobalAdministrator,
    session: Annotated[Session, Depends(get_session)],
    request: Request,
) -> dict[str, object]:
    participant = session.get(Participant, participant_id)
    if participant is None:
        raise HTTPException(status_code=404, detail="Participant account not found.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(participant, key, value)
    if payload.is_active is False:
        email_ids = select(ParticipantEmail.id).where(
            ParticipantEmail.participant_id == participant.id
        )
        now = datetime.now(UTC)
        for account_session in session.scalars(
            select(ParticipantSession).where(
                ParticipantSession.participant_email_id.in_(email_ids),
                ParticipantSession.revoked_at.is_(None),
            )
        ):
            account_session.revoked_at = now
    session.flush()
    record_audit_event(
        session,
        actor_user_id=actor.user_id,
        action="participant_account.updated",
        target_type="participant",
        target_id=participant.id,
        metadata={"fields": sorted(payload.model_fields_set)},
        request_id=getattr(request.state, "request_id", None),
    )
    session.commit()
    return {
        "id": participant.id,
        "display_name": participant.display_name,
        "is_active": participant.is_active,
    }
