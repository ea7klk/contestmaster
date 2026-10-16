"""Privileged contest management endpoints with server-side owner scoping."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.auth import AuthenticatedUser, Principal, require_contest_access
from backend.app.api.errors import API_ERROR_RESPONSES
from backend.app.api.pagination import Page, page_meta, pagination_parameters, validate_sort
from backend.app.audit import record_audit_event
from backend.app.db import get_session
from backend.app.models import (
    Contest,
    ContestStatus,
    Entry,
    EntryAccessGrant,
    EntryStatus,
    RulesetVersion,
    SystemRole,
)
from backend.app.rulesets.persistence import (
    RulesetPersistenceError,
    activate_ruleset,
    load_ruleset_version,
)

router = APIRouter(tags=["contests"])
public_router = APIRouter(tags=["public contests"])


class ContestWrite(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]*$")
    description: str | None = Field(default=None, max_length=10000)
    starts_at: datetime
    ends_at: datetime
    log_submission_cutoff_at: datetime
    auto_recalculate_on_upload: bool = False
    audit_reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_instants(self) -> ContestWrite:
        fields = (self.starts_at, self.ends_at, self.log_submission_cutoff_at)
        if any(value.tzinfo is None or value.utcoffset() is None for value in fields):
            raise ValueError("Contest times must include an explicit timezone offset")
        if self.starts_at >= self.ends_at:
            raise ValueError("Contest start must precede contest end")
        return self


class RulesetSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ruleset_version_id: int = Field(strict=True, ge=1)
    audit_reason: str | None = Field(default=None, max_length=2000)


class ContestStatusChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ContestStatus
    audit_reason: str | None = Field(default=None, max_length=2000)


class EntryStatusChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["accepted", "checklog", "withdrawn", "disqualified"]
    audit_reason: str = Field(min_length=1, max_length=2000)


class EntryGrantChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["create", "set_expiry", "revoke", "rotate"]
    expires_at: datetime | None = None
    audit_reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_expiry(self) -> EntryGrantChange:
        if self.expires_at is not None and (
            self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None
        ):
            raise ValueError("Grant expiry must include an explicit timezone offset")
        if self.operation in {"create", "rotate"} and self.expires_at is not None:
            if self.expires_at <= datetime.now(self.expires_at.tzinfo):
                raise ValueError("Grant expiry must be in the future")
        return self


def contest_output(contest: Contest) -> dict[str, object]:
    return {
        "id": contest.id,
        "owner_user_id": contest.owner_user_id,
        "name": contest.name,
        "slug": contest.slug,
        "description": contest.description,
        "starts_at": contest.starts_at,
        "ends_at": contest.ends_at,
        "log_submission_cutoff_at": contest.log_submission_cutoff_at,
        "status": contest.status.value,
        "auto_recalculate_on_upload": contest.auto_recalculate_on_upload,
        "ruleset_version_id": contest.ruleset_version_id,
        "created_at": contest.created_at,
        "updated_at": contest.updated_at,
    }


def _accessible_contests(principal: Principal):
    statement = select(Contest)
    if principal.role is not SystemRole.GLOBAL_ADMINISTRATOR:
        statement = statement.where(Contest.owner_user_id == principal.user_id)
    return statement


@router.get("", responses=API_ERROR_RESPONSES)
def list_contests(
    principal: AuthenticatedUser,
    session: Annotated[Session, Depends(get_session)],
    page: Annotated[Page, Depends(pagination_parameters)],
    status: Annotated[ContestStatus | None, Query()] = None,
) -> dict[str, object]:
    count_statement = select(func.count()).select_from(Contest)
    statement = _accessible_contests(principal)
    if principal.role is not SystemRole.GLOBAL_ADMINISTRATOR:
        count_statement = count_statement.where(Contest.owner_user_id == principal.user_id)
    if status is not None:
        count_statement = count_statement.where(Contest.status == status)
        statement = statement.where(Contest.status == status)
    total = session.scalar(count_statement) or 0
    sort_fields = {
        "name": Contest.name,
        "slug": Contest.slug,
        "starts_at": Contest.starts_at,
        "ends_at": Contest.ends_at,
        "created_at": Contest.created_at,
        "id": Contest.id,
    }
    ordering = [
        sort_fields[field].asc() if direction == "asc" else sort_fields[field].desc()
        for field, direction in validate_sort(page, set(sort_fields), "id")
    ]
    rows = list(
        session.scalars(
            statement.order_by(*ordering)
            .offset((page.page - 1) * page.page_size)
            .limit(page.page_size)
        )
    )
    return {"items": [contest_output(contest) for contest in rows], "meta": page_meta(page, total)}


@router.post("", status_code=201, responses=API_ERROR_RESPONSES)
def create_contest(
    payload: ContestWrite,
    principal: AuthenticatedUser,
    session: Annotated[Session, Depends(get_session)],
    request: Request,
) -> dict[str, object]:
    contest = Contest(
        owner_user_id=principal.user_id,
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        log_submission_cutoff_at=payload.log_submission_cutoff_at,
        status=ContestStatus.DRAFT,
        auto_recalculate_on_upload=payload.auto_recalculate_on_upload,
    )
    session.add(contest)
    try:
        session.flush()
        record_audit_event(
            session,
            actor_user_id=principal.user_id,
            action="contest.created",
            target_type="contest",
            target_id=contest.id,
            reason=payload.audit_reason,
            metadata={"slug": contest.slug},
            request_id=getattr(request.state, "request_id", None),
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="A contest with this slug already exists."
        ) from exc
    session.refresh(contest)
    return contest_output(contest)


@router.get("/{contest_id}", responses=API_ERROR_RESPONSES)
def get_contest(
    contest: Annotated[Contest, Depends(require_contest_access)],
) -> dict[str, object]:
    return contest_output(contest)


@router.put("/{contest_id}", responses=API_ERROR_RESPONSES)
def update_contest(
    payload: ContestWrite,
    contest: Annotated[Contest, Depends(require_contest_access)],
    session: Annotated[Session, Depends(get_session)],
    principal: AuthenticatedUser,
    request: Request,
) -> dict[str, object]:
    if contest.status is ContestStatus.PUBLISHED:
        raise HTTPException(status_code=409, detail="Published contests cannot be edited.")
    editable_fields = (
        "name",
        "slug",
        "description",
        "starts_at",
        "ends_at",
        "log_submission_cutoff_at",
        "auto_recalculate_on_upload",
    )
    changed_fields = [
        field_name
        for field_name in editable_fields
        if getattr(contest, field_name) != getattr(payload, field_name)
    ]
    for field_name in editable_fields:
        setattr(contest, field_name, getattr(payload, field_name))
    try:
        if changed_fields:
            record_audit_event(
                session,
                actor_user_id=principal.user_id,
                action="contest.updated",
                target_type="contest",
                target_id=contest.id,
                reason=payload.audit_reason,
                metadata={"changed_fields": changed_fields},
                request_id=getattr(request.state, "request_id", None),
            )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="A contest with this slug already exists."
        ) from exc
    session.refresh(contest)
    return contest_output(contest)


@router.put("/{contest_id}/ruleset", responses=API_ERROR_RESPONSES)
def select_contest_ruleset(
    payload: RulesetSelection,
    contest: Annotated[Contest, Depends(require_contest_access)],
    principal: AuthenticatedUser,
    session: Annotated[Session, Depends(get_session)],
    request: Request,
) -> dict[str, object]:
    if contest.status is not ContestStatus.DRAFT:
        raise HTTPException(
            status_code=409,
            detail="A ruleset can be selected only while the contest is a draft.",
        )
    try:
        activation = activate_ruleset(
            session,
            contest_id=contest.id,
            ruleset_version_id=payload.ruleset_version_id,
            activated_by_user_id=principal.user_id,
        )
        if activation is not None:
            record_audit_event(
                session,
                actor_user_id=principal.user_id,
                action="contest.ruleset_activated",
                target_type="contest",
                target_id=contest.id,
                reason=payload.audit_reason,
                metadata={"ruleset_version_id": payload.ruleset_version_id},
                request_id=getattr(request.state, "request_id", None),
            )
        session.commit()
    except RulesetPersistenceError as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.refresh(contest)
    return contest_output(contest)


@router.put("/{contest_id}/status", responses=API_ERROR_RESPONSES)
def change_contest_status(
    payload: ContestStatusChange,
    contest: Annotated[Contest, Depends(require_contest_access)],
    principal: AuthenticatedUser,
    session: Annotated[Session, Depends(get_session)],
    request: Request,
) -> dict[str, object]:
    allowed = {
        ContestStatus.DRAFT: {ContestStatus.OPEN},
        ContestStatus.OPEN: {ContestStatus.CLOSED},
        ContestStatus.CLOSED: {ContestStatus.OPEN, ContestStatus.PUBLISHED},
        ContestStatus.PUBLISHED: {ContestStatus.CLOSED},
    }
    if payload.status is contest.status:
        return contest_output(contest)
    if payload.status not in allowed[contest.status]:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Contest cannot transition from {contest.status.value} to {payload.status.value}."
            ),
        )
    if payload.status is ContestStatus.PUBLISHED:
        raise HTTPException(
            status_code=409,
            detail="Publish a generated and reviewed result snapshot through the results endpoint.",
        )
    if payload.status in {ContestStatus.OPEN, ContestStatus.PUBLISHED}:
        if contest.ruleset_version_id is None:
            raise HTTPException(
                status_code=409,
                detail="A validated ruleset must be selected before the contest is made available.",
            )
        ruleset = session.get(RulesetVersion, contest.ruleset_version_id)
        if ruleset is None:
            raise HTTPException(status_code=409, detail="The selected ruleset version is missing.")
        try:
            load_ruleset_version(ruleset)
        except RulesetPersistenceError as exc:
            raise HTTPException(status_code=409, detail="The selected ruleset is invalid.") from exc
    previous = contest.status
    contest.status = payload.status
    record_audit_event(
        session,
        actor_user_id=principal.user_id,
        action="contest.status_changed",
        target_type="contest",
        target_id=contest.id,
        reason=payload.audit_reason,
        metadata={"from": previous.value, "to": payload.status.value},
        request_id=getattr(request.state, "request_id", None),
    )
    session.commit()
    session.refresh(contest)
    return contest_output(contest)


@router.put("/{contest_id}/entries/{entry_id}/status", responses=API_ERROR_RESPONSES)
def change_entry_status(
    contest_id: int,
    entry_id: int,
    payload: EntryStatusChange,
    contest: Annotated[Contest, Depends(require_contest_access)],
    principal: AuthenticatedUser,
    session: Annotated[Session, Depends(get_session)],
    request: Request,
) -> dict[str, object]:
    if contest.id != contest_id:
        raise HTTPException(status_code=404, detail="Contest not found.")
    entry = session.scalar(
        select(Entry).where(Entry.id == entry_id, Entry.contest_id == contest.id)
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found.")
    next_status = EntryStatus(payload.status)
    if entry.status is EntryStatus.WITHDRAWN and next_status is not EntryStatus.ACCEPTED:
        raise HTTPException(
            status_code=409, detail="Withdrawn entries can only be reinstated as accepted."
        )
    previous = entry.status
    previous_late = entry.is_late
    entry.status = next_status
    if next_status is EntryStatus.ACCEPTED:
        entry.is_late = False
    record_audit_event(
        session,
        actor_user_id=principal.user_id,
        action="contest.entry_status_changed",
        target_type="entry",
        target_id=entry.id,
        reason=payload.audit_reason,
        metadata={
            "contest_id": contest.id,
            "from": previous.value,
            "to": next_status.value,
            "was_late": previous_late,
            "late_after": entry.is_late,
        },
        request_id=getattr(request.state, "request_id", None),
    )
    session.commit()
    return {"entry_id": entry.id, "status": entry.status.value}


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _issue_entry_grant(
    session: Session,
    *,
    entry_id: int,
    actor_user_id: int,
    expires_at: datetime | None,
) -> tuple[EntryAccessGrant, str]:
    token = secrets.token_urlsafe(32)
    grant = EntryAccessGrant(
        entry_id=entry_id,
        token_hash=_token_digest(token),
        expires_at=expires_at,
        created_by_user_id=actor_user_id,
    )
    session.add(grant)
    session.flush()
    return grant, token


@router.put("/{contest_id}/entries/{entry_id}/access-grant", responses=API_ERROR_RESPONSES)
def manage_entry_access_grant(
    payload: EntryGrantChange,
    contest: Annotated[Contest, Depends(require_contest_access)],
    entry_id: int,
    principal: AuthenticatedUser,
    session: Annotated[Session, Depends(get_session)],
    request: Request,
) -> dict[str, object]:
    entry = session.scalar(
        select(Entry).where(Entry.id == entry_id, Entry.contest_id == contest.id)
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found.")
    now = datetime.now(UTC)
    grants = list(
        session.scalars(
            select(EntryAccessGrant)
            .where(EntryAccessGrant.entry_id == entry.id)
            .order_by(EntryAccessGrant.created_at.desc(), EntryAccessGrant.id.desc())
        )
    )
    live_grants = [
        grant
        for grant in grants
        if grant.revoked_at is None and (grant.expires_at is None or grant.expires_at > now)
    ]
    token: str | None = None
    grant: EntryAccessGrant | None = None
    if payload.operation == "create":
        if live_grants:
            raise HTTPException(status_code=409, detail="Entry already has active guest access.")
        grant, token = _issue_entry_grant(
            session,
            entry_id=entry.id,
            actor_user_id=principal.user_id,
            expires_at=payload.expires_at,
        )
    elif payload.operation == "rotate":
        for active in live_grants:
            active.revoked_at = now
            active.revoked_by_user_id = principal.user_id
        grant, token = _issue_entry_grant(
            session,
            entry_id=entry.id,
            actor_user_id=principal.user_id,
            expires_at=payload.expires_at,
        )
    elif payload.operation == "revoke":
        if not live_grants:
            raise HTTPException(
                status_code=409, detail="Entry has no active guest access to revoke."
            )
        for active in live_grants:
            active.revoked_at = now
            active.revoked_by_user_id = principal.user_id
        grant = live_grants[0]
    else:
        if payload.expires_at is not None and payload.expires_at <= now:
            raise HTTPException(status_code=422, detail="Grant expiry must be in the future.")
        if not live_grants:
            raise HTTPException(
                status_code=409, detail="Entry has no active guest access to update."
            )
        grant = live_grants[0]
        grant.expires_at = payload.expires_at

    record_audit_event(
        session,
        actor_user_id=principal.user_id,
        action=f"entry_access_grant.{payload.operation}",
        target_type="entry_access_grant",
        target_id=grant.id,
        reason=payload.audit_reason,
        metadata={"entry_id": entry.id, "contest_id": contest.id},
        request_id=getattr(request.state, "request_id", None),
    )
    session.commit()
    session.refresh(grant)
    return {
        "id": grant.id,
        "entry_id": grant.entry_id,
        "created_at": grant.created_at,
        "expires_at": grant.expires_at,
        "revoked_at": grant.revoked_at,
        "active": grant.revoked_at is None and (grant.expires_at is None or grant.expires_at > now),
        "receipt_token": token,
    }


def public_contest_output(contest: Contest) -> dict[str, object]:
    return {
        "id": contest.id,
        "name": contest.name,
        "slug": contest.slug,
        "description": contest.description,
        "starts_at": contest.starts_at,
        "ends_at": contest.ends_at,
        "log_submission_cutoff_at": contest.log_submission_cutoff_at,
        "status": contest.status.value,
    }


@public_router.get("", responses=API_ERROR_RESPONSES)
def list_published_contests(
    session: Annotated[Session, Depends(get_session)],
    page: Annotated[Page, Depends(pagination_parameters)],
) -> dict[str, object]:
    condition = Contest.status == ContestStatus.PUBLISHED
    total = session.scalar(select(func.count()).select_from(Contest).where(condition)) or 0
    contests = list(
        session.scalars(
            select(Contest)
            .where(condition)
            .order_by(Contest.starts_at.desc(), Contest.id.asc())
            .offset((page.page - 1) * page.page_size)
            .limit(page.page_size)
        )
    )
    return {
        "items": [public_contest_output(contest) for contest in contests],
        "meta": page_meta(page, total),
    }


@public_router.get("/upcoming", responses=API_ERROR_RESPONSES)
def list_open_contests(
    session: Annotated[Session, Depends(get_session)],
    page: Annotated[Page, Depends(pagination_parameters)],
) -> dict[str, object]:
    """List public open contests that have not yet reached their end instant."""
    as_of = datetime.now(UTC)
    condition = (Contest.status == ContestStatus.OPEN) & (Contest.ends_at > as_of)
    total = session.scalar(select(func.count()).select_from(Contest).where(condition)) or 0
    contests = list(
        session.scalars(
            select(Contest)
            .where(condition)
            .order_by(Contest.starts_at.asc(), Contest.id.asc())
            .offset((page.page - 1) * page.page_size)
            .limit(page.page_size)
        )
    )
    return {
        "items": [public_contest_output(contest) for contest in contests],
        "meta": page_meta(page, total),
        "as_of": as_of,
    }


@public_router.get("/{slug}", responses=API_ERROR_RESPONSES)
def get_public_contest(
    slug: str,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    contest = session.scalar(
        select(Contest).where(
            Contest.slug == slug,
            Contest.status.in_((ContestStatus.OPEN, ContestStatus.PUBLISHED)),
        )
    )
    if contest is None:
        raise HTTPException(status_code=404, detail="Contest not found.")
    return public_contest_output(contest)
