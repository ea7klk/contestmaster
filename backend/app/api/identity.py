"""Privileged sign-in and administrator account provisioning endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
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
)
from backend.app.api.errors import API_ERROR_RESPONSES
from backend.app.audit import record_audit_event
from backend.app.db import get_session
from backend.app.models import SystemRole, SystemUser

router = APIRouter(tags=["identity"])


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class UserCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    username: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=12, max_length=1024)
    audit_reason: str | None = Field(default=None, max_length=2000)


def _user_response(user: SystemUser) -> dict[str, object]:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email_normalized,
        "display_name": user.display_name,
        "role": user.role.value,
        "is_active": user.is_active,
    }


@router.post("/login", responses=API_ERROR_RESPONSES)
def login(
    payload: LoginRequest,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
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
        "role": actor.role.value,
    }


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
        role=SystemRole.CONTEST_MANAGER,
        password_hash=password_hash,
    )
    session.add(user)
    try:
        session.flush()
        record_audit_event(
            session,
            actor_user_id=actor.user_id,
            action="system_user.contest_manager_created",
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
