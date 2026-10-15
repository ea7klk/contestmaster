"""Privileged account authentication and role/ownership dependencies."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.db import get_session
from backend.app.models import Contest, SystemRole, SystemSession, SystemUser

SESSION_COOKIE = "contestmaster_session"
CSRF_COOKIE = "contestmaster_csrf"
SESSION_LIFETIME = timedelta(hours=12)
CSRF_HEADER = "X-CSRF-Token"


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: int
    username: str
    email: str
    display_name: str
    role: SystemRole


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    """Hash a password with the Python standard library's memory-hard scrypt."""
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=2**15, r=8, p=1, maxmem=64 * 1024 * 1024
    )
    return f"scrypt$32768$8$1${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_hex, digest_hex = encoded.split("$")
        if algorithm != "scrypt":
            return False
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
            maxmem=64 * 1024 * 1024,
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def normalize_email(email: str) -> str:
    normalized = email.strip().casefold()
    if not normalized or "@" not in normalized or len(normalized) > 320:
        raise ValueError("A valid email address is required")
    return normalized


def authenticate_password(session: Session, email: str, password: str) -> SystemUser | None:
    normalized = normalize_email(email)
    user = session.scalar(select(SystemUser).where(SystemUser.email_normalized == normalized))
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        return None
    return user


def issue_session(session: Session, user: SystemUser) -> tuple[str, str, SystemSession]:
    now = datetime.now(UTC)
    session_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    record = SystemSession(
        user_id=user.id,
        token_hash=_hash_token(session_token),
        csrf_token_hash=_hash_token(csrf_token),
        created_at=now,
        expires_at=now + SESSION_LIFETIME,
    )
    session.add(record)
    session.flush()
    return session_token, csrf_token, record


def set_session_cookies(response: Response, session_token: str, csrf_token: str) -> None:
    secure = get_settings().secure_cookies
    response.set_cookie(
        SESSION_COOKIE,
        session_token,
        httponly=True,
        secure=secure,
        samesite="strict",
        path="/api/v1",
        max_age=int(SESSION_LIFETIME.total_seconds()),
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        httponly=False,
        secure=secure,
        samesite="strict",
        # The Vue application runs at `/`; the readable anti-CSRF cookie must be
        # visible there so the shared client can copy it into the request header.
        path="/",
        max_age=int(SESSION_LIFETIME.total_seconds()),
    )


def clear_session_cookies(response: Response) -> None:
    secure = get_settings().secure_cookies
    for name, httponly, path in (
        (SESSION_COOKIE, True, "/api/v1"),
        (CSRF_COOKIE, False, "/"),
    ):
        response.delete_cookie(name, path=path, httponly=httponly, secure=secure, samesite="strict")


def require_authenticated_user(
    request: Request, session: Annotated[Session, Depends(get_session)]
) -> Principal:
    raw_token = request.cookies.get(SESSION_COOKIE)
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication is required.",
        headers={"WWW-Authenticate": "Session"},
    )
    if not raw_token:
        raise unauthorized
    session_record = session.scalar(
        select(SystemSession).where(SystemSession.token_hash == _hash_token(raw_token))
    )
    now = datetime.now(UTC)
    if (
        session_record is None
        or session_record.revoked_at is not None
        or session_record.expires_at <= now
    ):
        raise unauthorized
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        cookie_csrf = request.cookies.get(CSRF_COOKIE, "")
        header_csrf = request.headers.get(CSRF_HEADER, "")
        if (
            not cookie_csrf
            or not header_csrf
            or not hmac.compare_digest(cookie_csrf, header_csrf)
            or not hmac.compare_digest(_hash_token(header_csrf), session_record.csrf_token_hash)
        ):
            raise HTTPException(status_code=403, detail="CSRF validation failed.")
    user = session.get(SystemUser, session_record.user_id)
    if user is None or not user.is_active:
        raise unauthorized
    return Principal(user.id, user.username, user.email_normalized, user.display_name, user.role)


def require_global_administrator(
    principal: Annotated[Principal, Depends(require_authenticated_user)],
) -> Principal:
    if principal.role is not SystemRole.GLOBAL_ADMINISTRATOR:
        raise HTTPException(status_code=403, detail="Global administrator access is required.")
    return principal


def require_contest_access(
    contest_id: int,
    principal: Annotated[Principal, Depends(require_authenticated_user)],
    session: Annotated[Session, Depends(get_session)],
) -> Contest:
    contest = session.get(Contest, contest_id)
    if contest is None:
        raise HTTPException(status_code=404, detail="Contest not found.")
    if (
        principal.role is not SystemRole.GLOBAL_ADMINISTRATOR
        and contest.owner_user_id != principal.user_id
    ):
        # Do not reveal the existence of contests owned by another manager.
        raise HTTPException(status_code=404, detail="Contest not found.")
    return contest


AuthenticatedUser = Annotated[Principal, Depends(require_authenticated_user)]
GlobalAdministrator = Annotated[Principal, Depends(require_global_administrator)]
