"""Privileged contest management endpoints with server-side owner scoping."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.auth import AuthenticatedUser, Principal, require_contest_access
from backend.app.api.errors import API_ERROR_RESPONSES
from backend.app.api.pagination import Page, page_meta, pagination_parameters
from backend.app.db import get_session
from backend.app.models import Contest, ContestStatus, SystemRole

router = APIRouter(tags=["contests"])


class ContestWrite(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]*$")
    description: str | None = Field(default=None, max_length=10000)
    starts_at: datetime
    ends_at: datetime
    log_submission_cutoff_at: datetime
    auto_recalculate_on_upload: bool = False

    @model_validator(mode="after")
    def validate_instants(self) -> ContestWrite:
        fields = (self.starts_at, self.ends_at, self.log_submission_cutoff_at)
        if any(value.tzinfo is None or value.utcoffset() is None for value in fields):
            raise ValueError("Contest times must include an explicit timezone offset")
        if self.starts_at >= self.ends_at:
            raise ValueError("Contest start must precede contest end")
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
) -> dict[str, object]:
    count_statement = select(func.count()).select_from(Contest)
    statement = _accessible_contests(principal)
    if principal.role is not SystemRole.GLOBAL_ADMINISTRATOR:
        count_statement = count_statement.where(Contest.owner_user_id == principal.user_id)
    total = session.scalar(count_statement) or 0
    rows = list(
        session.scalars(
            statement.order_by(Contest.created_at.desc(), Contest.id.asc())
            .offset((page.page - 1) * page.page_size)
            .limit(page.page_size)
        )
    )
    return {"items": [contest_output(contest) for contest in rows], "page": page_meta(page, total)}


@router.post("", status_code=201, responses=API_ERROR_RESPONSES)
def create_contest(
    payload: ContestWrite,
    principal: AuthenticatedUser,
    session: Annotated[Session, Depends(get_session)],
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
) -> dict[str, object]:
    if contest.status is ContestStatus.PUBLISHED:
        raise HTTPException(status_code=409, detail="Published contests cannot be edited.")
    for field_name in (
        "name",
        "slug",
        "description",
        "starts_at",
        "ends_at",
        "log_submission_cutoff_at",
        "auto_recalculate_on_upload",
    ):
        setattr(contest, field_name, getattr(payload, field_name))
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="A contest with this slug already exists."
        ) from exc
    session.refresh(contest)
    return contest_output(contest)
