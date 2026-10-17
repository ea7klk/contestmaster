"""Privileged contest management endpoints with server-side owner scoping."""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.auth import (
    AuthenticatedUser,
    Principal,
    can_manage_ruleset,
    require_contest_access,
)
from backend.app.api.errors import API_ERROR_RESPONSES, error_response
from backend.app.api.pagination import Page, page_meta, pagination_parameters, validate_sort
from backend.app.audit import record_audit_event
from backend.app.contest_deletion import DeletionConflictError, delete_contest_records
from backend.app.contest_series import create_series_for_contest
from backend.app.database_maintenance import vacuum_sqlite_after_commit
from backend.app.db import get_session
from backend.app.models import (
    Contest,
    ContestAdministrator,
    ContestSeries,
    ContestSeriesException,
    ContestStatus,
    Entry,
    EntryAccessGrant,
    EntryRevision,
    EntryStatus,
    Qso,
    Ruleset,
    RulesetVersion,
    Station,
    SystemRole,
    SystemUser,
)
from backend.app.rulesets.catalog_validation import catalog_reference_errors
from backend.app.rulesets.persistence import (
    RulesetConflictError,
    RulesetPersistenceError,
    activate_ruleset,
    load_ruleset_version,
    save_ruleset_version,
)
from backend.app.rulesets.schema import RulesetDefinition
from backend.app.rulesets.validation import RulesetValidationError, validate_ruleset
from backend.app.scheduling import (
    Recurrence,
    ResolvedSchedule,
    ScheduleResolutionError,
    recurrence_dates,
    resolve_contest_schedule,
    resolve_next_contest_schedules,
)

router = APIRouter(tags=["contests"])
public_router = APIRouter(tags=["public contests"])
logger = logging.getLogger("contestmaster.contests")


def _integrity_failure_kind(exc: IntegrityError) -> str:
    """Return a safe database-constraint category without exposing SQL parameters."""
    driver_name = getattr(exc.orig, "sqlite_errorname", None)
    if isinstance(driver_name, str) and driver_name.startswith("SQLITE_CONSTRAINT_"):
        constraint_kind = driver_name.removeprefix("SQLITE_CONSTRAINT_").casefold()
        return {
            "foreignkey": "foreign_key",
            "notnull": "not_null",
            "primarykey": "primary_key",
        }.get(constraint_kind, constraint_kind)

    error_text = str(exc.orig).casefold()
    if "foreign key" in error_text:
        return "foreign_key"
    if "unique constraint" in error_text:
        return "unique"
    if "check constraint" in error_text:
        return "check"
    if "not null constraint" in error_text:
        return "not_null"
    return "integrity_constraint"


@router.post("/schedule-preview")
def preview_contest_schedule(payload: ContestSchedulePreviewPayload) -> dict[str, object]:
    try:
        resolved = resolve_contest_schedule(
            payload.periodicity,
            payload.year or payload.starts_at.astimezone(UTC).year,
            payload.starts_at,
            payload.ends_at,
        )
        upcoming = resolve_next_contest_schedules(
            payload.periodicity,
            payload.starts_at,
            payload.ends_at,
            count=min(20, 5 + len(payload.exceptions)),
        )
    except ScheduleResolutionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    exception_by_date = {item.occurrence_date: item for item in payload.exceptions}
    preview_occurrences: list[ResolvedSchedule] = []
    for occurrence in upcoming:
        exception = exception_by_date.get(occurrence.starts_at.date())
        if exception is not None and exception.action == "skip":
            continue
        occurrence_date = (
            exception.moved_to_date
            if exception is not None and exception.action == "move"
            else occurrence.starts_at.date()
        )
        start = datetime.combine(occurrence_date, occurrence.starts_at.time(), tzinfo=UTC)
        preview_occurrences.append(
            ResolvedSchedule(
                starts_at=start,
                ends_at=start + (occurrence.ends_at - occurrence.starts_at),
            )
        )
        if len(preview_occurrences) == 5:
            break
    return {
        "starts_at": resolved.starts_at.isoformat().replace("+00:00", "Z"),
        "ends_at": resolved.ends_at.isoformat().replace("+00:00", "Z"),
        "occurrences": [
            {
                "starts_at": occurrence.starts_at.isoformat().replace("+00:00", "Z"),
                "ends_at": occurrence.ends_at.isoformat().replace("+00:00", "Z"),
            }
            for occurrence in preview_occurrences
        ],
    }


class ContestWrite(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]*$")
    description: str | None = Field(default=None, max_length=10000)
    starts_at: datetime
    ends_at: datetime
    periodicity: Recurrence | None = None
    log_submission_cutoff_at: datetime
    cutoff_offset_seconds: int | None = Field(default=None, ge=0, le=31_536_000)
    cutoff_is_override: bool = False
    automatic_window_days: int | None = Field(default=None, ge=1, le=730)
    auto_recalculate_on_upload: bool = False
    audit_reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_instants(self) -> ContestWrite:
        fields = (self.starts_at, self.ends_at, self.log_submission_cutoff_at)
        if any(value.tzinfo is None or value.utcoffset() is None for value in fields):
            raise ValueError("Contest times must include an explicit timezone offset")
        if self.starts_at >= self.ends_at:
            raise ValueError("Contest start must precede contest end")
        if self.cutoff_offset_seconds is not None and self.cutoff_offset_seconds % 3600:
            raise ValueError("Recurring cutoff offsets must use whole hours or whole days")
        if self.periodicity is not None:
            starts_at_utc = self.starts_at.astimezone(UTC)
            if starts_at_utc.date() not in recurrence_dates(self.periodicity, starts_at_utc.year):
                raise ValueError("Contest start date must match its configured UTC periodicity")
        elif self.cutoff_offset_seconds is not None or self.automatic_window_days is not None:
            raise ValueError("Recurring-series settings require contest periodicity")
        return self


class ContestImportPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contest: ContestWrite
    ruleset: RulesetDefinition | None = None


class ContestSchedulePreviewPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    periodicity: Recurrence
    year: int | None = Field(default=None, ge=1900, le=2200)
    starts_at: datetime
    ends_at: datetime
    exceptions: list[SeriesExceptionWrite] = Field(default_factory=list, max_length=15)

    @model_validator(mode="after")
    def validate_instants(self) -> ContestSchedulePreviewPayload:
        if any(
            value.tzinfo is None or value.utcoffset() is None
            for value in (self.starts_at, self.ends_at)
        ):
            raise ValueError("Contest schedule preview times must be timezone-aware")
        if self.starts_at >= self.ends_at:
            raise ValueError("Contest end must follow its start")
        return self


class SeriesExceptionWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    occurrence_date: date
    action: Literal["skip", "move"]
    moved_to_date: date | None = None

    @model_validator(mode="after")
    def validate_exception(self) -> SeriesExceptionWrite:
        if self.action == "move" and self.moved_to_date is None:
            raise ValueError("A moved occurrence requires a new UTC date")
        if self.action == "skip" and self.moved_to_date is not None:
            raise ValueError("A skipped occurrence cannot have a moved date")
        return self


def _series_for_user(session: Session, series_id: int, principal: Principal) -> ContestSeries:
    series = session.get(ContestSeries, series_id)
    has_assigned_edition = bool(
        series is not None
        and session.scalar(
            select(Contest.id)
            .join(ContestAdministrator, ContestAdministrator.contest_id == Contest.id)
            .where(
                Contest.series_id == series_id,
                ContestAdministrator.user_id == principal.user_id,
            )
            .limit(1)
        )
    )
    if series is None or (
        principal.role is not SystemRole.GLOBAL_ADMINISTRATOR
        and series.owner_user_id != principal.user_id
        and not has_assigned_edition
    ):
        raise HTTPException(status_code=404, detail="Contest series not found.")
    return series


def series_exception_output(item: ContestSeriesException) -> dict[str, object]:
    return {
        "occurrence_date": item.occurrence_date.isoformat(),
        "action": item.action,
        "moved_to_date": item.moved_to_date.isoformat() if item.moved_to_date else None,
    }


class RulesetSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ruleset_version_id: int = Field(strict=True, ge=1)
    audit_reason: str | None = Field(default=None, max_length=2000)


class ContestStatusChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ContestStatus
    audit_reason: str | None = Field(default=None, max_length=2000)


class AdministratorAssignment(BaseModel):
    user_id: int = Field(strict=True, ge=1)


class ContestDeleteConfirmation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    confirm_slug: str = Field(min_length=1, max_length=120)


class SeriesDeleteConfirmation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    confirm_name: str = Field(min_length=1, max_length=200)


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
    series = contest.series
    return {
        "id": contest.id,
        "owner_user_id": contest.owner_user_id,
        "name": contest.name,
        "slug": contest.slug,
        "description": contest.description,
        "starts_at": contest.starts_at,
        "ends_at": contest.ends_at,
        "periodicity": contest.periodicity,
        "log_submission_cutoff_at": contest.log_submission_cutoff_at,
        "cutoff_is_override": contest.cutoff_is_override,
        "series_id": contest.series_id,
        "series_name": series.name if series is not None else None,
        "series_occurrence_date": (
            contest.series_occurrence_date.isoformat()
            if contest.series_occurrence_date is not None
            else None
        ),
        "is_series_anchor": contest.is_series_anchor,
        "series_cutoff_offset_seconds": (
            series.cutoff_offset_seconds if series is not None else None
        ),
        "series_automatic_window_days": (
            series.automatic_window_days if series is not None else None
        ),
        "series_edition_count": len(series.editions) if series is not None else None,
        "status": contest.status.value,
        "auto_recalculate_on_upload": contest.auto_recalculate_on_upload,
        "ruleset_version_id": contest.ruleset_version_id,
        "created_at": contest.created_at,
        "updated_at": contest.updated_at,
    }


def _accessible_contests(principal: Principal):
    statement = select(Contest)
    if principal.role is not SystemRole.GLOBAL_ADMINISTRATOR:
        statement = statement.where(
            or_(
                Contest.owner_user_id == principal.user_id,
                Contest.id.in_(
                    select(ContestAdministrator.contest_id).where(
                        ContestAdministrator.user_id == principal.user_id
                    )
                ),
            )
        )
    return statement


def _cutoff_settings(payload: ContestWrite) -> tuple[datetime, int | None, bool]:
    """Return the resolved cutoff, series offset, and override state."""
    if payload.periodicity is None:
        return payload.log_submission_cutoff_at, None, True
    if payload.cutoff_offset_seconds is None:
        offset = max(
            0,
            int((payload.log_submission_cutoff_at - payload.ends_at).total_seconds()),
        )
        return payload.log_submission_cutoff_at, offset, True
    if payload.cutoff_is_override:
        return payload.log_submission_cutoff_at, payload.cutoff_offset_seconds, True
    return (
        payload.ends_at + timedelta(seconds=payload.cutoff_offset_seconds),
        payload.cutoff_offset_seconds,
        False,
    )


@router.get("", responses=API_ERROR_RESPONSES)
def list_contests(
    principal: AuthenticatedUser,
    session: Annotated[Session, Depends(get_session)],
    page: Annotated[Page, Depends(pagination_parameters)],
    status: Annotated[ContestStatus | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=120)] = None,
) -> dict[str, object]:
    count_statement = select(func.count()).select_from(Contest)
    statement = _accessible_contests(principal)
    if principal.role is not SystemRole.GLOBAL_ADMINISTRATOR:
        count_statement = count_statement.where(
            or_(
                Contest.owner_user_id == principal.user_id,
                Contest.id.in_(
                    select(ContestAdministrator.contest_id).where(
                        ContestAdministrator.user_id == principal.user_id
                    )
                ),
            )
        )
    if status is not None:
        count_statement = count_statement.where(Contest.status == status)
        statement = statement.where(Contest.status == status)
    search = (q or "").strip()
    if search:
        pattern = f"%{search}%"
        search_clauses = [Contest.name.ilike(pattern), Contest.slug.ilike(pattern)]
        matched_status = next(
            (
                contest_status
                for contest_status in ContestStatus
                if contest_status.value.casefold() == search.casefold()
            ),
            None,
        )
        if matched_status is not None:
            search_clauses.append(Contest.status == matched_status)
        search_filter = or_(*search_clauses)
        count_statement = count_statement.where(search_filter)
        statement = statement.where(search_filter)
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
    cutoff_at, cutoff_offset, cutoff_override = _cutoff_settings(payload)
    contest = Contest(
        owner_user_id=principal.user_id,
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        periodicity=(
            payload.periodicity.model_dump(mode="json", exclude_none=True)
            if payload.periodicity is not None
            else None
        ),
        log_submission_cutoff_at=cutoff_at,
        cutoff_is_override=cutoff_override,
        status=ContestStatus.DRAFT,
        auto_recalculate_on_upload=payload.auto_recalculate_on_upload,
    )
    session.add(contest)
    try:
        session.flush()
        if payload.periodicity is not None and cutoff_offset is not None:
            create_series_for_contest(
                session,
                contest,
                recurrence=payload.periodicity,
                cutoff_offset_seconds=cutoff_offset,
                automatic_window_days=payload.automatic_window_days,
                cutoff_is_override=cutoff_override,
            )
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


@router.post("/import", status_code=201, responses=API_ERROR_RESPONSES, response_model=None)
def import_contest(
    payload: ContestImportPayload,
    principal: AuthenticatedUser,
    session: Annotated[Session, Depends(get_session)],
    request: Request,
) -> dict[str, object] | JSONResponse:
    """Import contest metadata and an optional immutable ruleset atomically."""
    definition = None
    if payload.ruleset is not None:
        try:
            definition = validate_ruleset(payload.ruleset.model_dump(mode="json"))
            catalog_errors = catalog_reference_errors(session, definition)
            if catalog_errors:
                raise RulesetValidationError(catalog_errors)
        except RulesetValidationError as exc:
            details = [
                {
                    "location": [part for part in str(issue["path"]).split(".") if part],
                    "message": str(issue["message"]),
                    "type": "ruleset_configuration_error",
                }
                for issue in exc.errors
            ]
            return error_response(
                request,
                422,
                "invalid_ruleset",
                "Imported ruleset configuration is invalid.",
                details,
            )
        existing_ruleset = session.scalar(
            select(Ruleset).where(Ruleset.ruleset_key == definition.ruleset_key)
        )
        if existing_ruleset is not None and not can_manage_ruleset(
            session, existing_ruleset, principal
        ):
            raise HTTPException(status_code=404, detail="Ruleset not found.")

    contest_payload = payload.contest
    cutoff_at, cutoff_offset, cutoff_override = _cutoff_settings(contest_payload)
    contest = Contest(
        owner_user_id=principal.user_id,
        name=contest_payload.name,
        slug=contest_payload.slug,
        description=contest_payload.description,
        starts_at=contest_payload.starts_at,
        ends_at=contest_payload.ends_at,
        periodicity=(
            contest_payload.periodicity.model_dump(mode="json", exclude_none=True)
            if contest_payload.periodicity is not None
            else None
        ),
        log_submission_cutoff_at=cutoff_at,
        cutoff_is_override=cutoff_override,
        status=ContestStatus.DRAFT,
        auto_recalculate_on_upload=contest_payload.auto_recalculate_on_upload,
    )
    try:
        saved_ruleset = (
            save_ruleset_version(session, definition, created_by_user_id=principal.user_id)
            if definition is not None
            else None
        )
        session.add(contest)
        session.flush()
        if contest_payload.periodicity is not None and cutoff_offset is not None:
            create_series_for_contest(
                session,
                contest,
                recurrence=contest_payload.periodicity,
                cutoff_offset_seconds=cutoff_offset,
                automatic_window_days=contest_payload.automatic_window_days,
                cutoff_is_override=cutoff_override,
            )
        activation = (
            activate_ruleset(
                session,
                contest_id=contest.id,
                ruleset_version_id=saved_ruleset.version.id,
                activated_by_user_id=principal.user_id,
            )
            if saved_ruleset is not None
            else None
        )
        record_audit_event(
            session,
            actor_user_id=principal.user_id,
            action="contest.imported",
            target_type="contest",
            target_id=contest.id,
            reason=contest_payload.audit_reason,
            metadata={
                "slug": contest.slug,
                "ruleset_version_id": (
                    saved_ruleset.version.id if saved_ruleset is not None else None
                ),
            },
            request_id=getattr(request.state, "request_id", None),
        )
        if saved_ruleset is not None and saved_ruleset.created:
            record_audit_event(
                session,
                actor_user_id=principal.user_id,
                action="ruleset_version.created",
                target_type="ruleset_version",
                target_id=saved_ruleset.version.id,
                metadata={
                    "ruleset_key": saved_ruleset.version.ruleset_key,
                    "version": saved_ruleset.version.version,
                    "imported_with_contest": contest.id,
                },
                request_id=getattr(request.state, "request_id", None),
            )
        if activation is not None:
            record_audit_event(
                session,
                actor_user_id=principal.user_id,
                action="contest.ruleset_activated",
                target_type="contest",
                target_id=contest.id,
                metadata={"ruleset_version_id": saved_ruleset.version.id},
                request_id=getattr(request.state, "request_id", None),
            )
        session.commit()
    except RulesetConflictError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (IntegrityError, RulesetPersistenceError) as exc:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="The contest or ruleset conflicts with an existing record.",
        ) from exc
    session.refresh(contest)
    return {
        "contest": contest_output(contest),
        "ruleset_version_id": (saved_ruleset.version.id if saved_ruleset is not None else None),
    }


@router.get("/{contest_id}", responses=API_ERROR_RESPONSES)
def get_contest(
    contest: Annotated[Contest, Depends(require_contest_access)],
) -> dict[str, object]:
    return contest_output(contest)


@router.get("/series/{series_id}/exceptions", responses=API_ERROR_RESPONSES)
def list_series_exceptions(
    series_id: int,
    principal: AuthenticatedUser,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    series = _series_for_user(session, series_id, principal)
    items = session.scalars(
        select(ContestSeriesException)
        .where(ContestSeriesException.series_id == series.id)
        .order_by(ContestSeriesException.occurrence_date)
    )
    return {"items": [series_exception_output(item) for item in items]}


@router.post("/series/{series_id}/exceptions", status_code=201, responses=API_ERROR_RESPONSES)
def set_series_exception(
    series_id: int,
    payload: SeriesExceptionWrite,
    principal: AuthenticatedUser,
    session: Annotated[Session, Depends(get_session)],
    request: Request,
) -> dict[str, object]:
    series = _series_for_user(session, series_id, principal)
    recurrence = Recurrence.model_validate(series.periodicity)
    try:
        scheduled_dates = recurrence_dates(recurrence, payload.occurrence_date.year)
    except ScheduleResolutionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if payload.occurrence_date not in scheduled_dates:
        raise HTTPException(
            status_code=422,
            detail="The exception date does not match a scheduled recurrence.",
        )
    if payload.action == "move" and payload.moved_to_date == payload.occurrence_date:
        raise HTTPException(
            status_code=422, detail="Choose a different date for a moved occurrence."
        )
    if payload.action == "move" and payload.moved_to_date is not None:
        try:
            destination_occurrences = recurrence_dates(recurrence, payload.moved_to_date.year)
        except ScheduleResolutionError:
            destination_occurrences = []
        if payload.moved_to_date in destination_occurrences:
            raise HTTPException(
                status_code=409,
                detail="The moved date is already reserved for another scheduled occurrence.",
            )
        destination_conflict = session.scalar(
            select(ContestSeriesException.id)
            .where(
                ContestSeriesException.series_id == series.id,
                ContestSeriesException.moved_to_date == payload.moved_to_date,
            )
            .limit(1)
        )
        if destination_conflict is not None:
            raise HTTPException(
                status_code=409,
                detail="Another occurrence is already moved to this date.",
            )
    existing_exception = session.scalar(
        select(ContestSeriesException).where(
            ContestSeriesException.series_id == series.id,
            ContestSeriesException.occurrence_date == payload.occurrence_date,
        )
    )
    if existing_exception is not None:
        raise HTTPException(status_code=409, detail="This occurrence already has an exception.")
    edition = session.scalar(
        select(Contest).where(
            Contest.series_id == series.id,
            Contest.series_occurrence_date == payload.occurrence_date,
        )
    )
    if payload.action == "skip" and edition is not None:
        has_entries = session.scalar(
            select(Entry.id).where(Entry.contest_id == edition.id).limit(1)
        )
        if has_entries is not None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "An edition with submitted logs cannot be skipped. Close or retain it instead."
                ),
            )
        try:
            delete_contest_records(session, edition)
        except DeletionConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    moved_to_date = payload.moved_to_date if payload.action == "move" else None
    if payload.action == "move":
        conflict = session.scalar(
            select(Contest.id)
            .where(
                Contest.series_id == series.id,
                Contest.starts_at >= datetime.combine(moved_to_date, time.min, tzinfo=UTC),
                Contest.starts_at
                < datetime.combine(moved_to_date + timedelta(days=1), time.min, tzinfo=UTC),
                Contest.id != (edition.id if edition is not None else -1),
            )
            .limit(1)
        )
        if conflict is not None:
            raise HTTPException(
                status_code=409, detail="Another edition already uses the moved date."
            )
        if edition is not None:
            start_seconds = series.start_time_seconds
            start = datetime.combine(
                moved_to_date,
                time(start_seconds // 3600, (start_seconds % 3600) // 60, start_seconds % 60),
                tzinfo=UTC,
            )
            edition.starts_at = start
            edition.ends_at = start + timedelta(seconds=series.duration_seconds)
            if not edition.cutoff_is_override:
                edition.log_submission_cutoff_at = edition.ends_at + timedelta(
                    seconds=series.cutoff_offset_seconds
                )
    exception = ContestSeriesException(
        series_id=series.id,
        occurrence_date=payload.occurrence_date,
        action=payload.action,
        moved_to_date=moved_to_date,
    )
    session.add(exception)
    try:
        session.flush()
        record_audit_event(
            session,
            actor_user_id=principal.user_id,
            action="contest_series.exception_set",
            target_type="contest_series",
            target_id=series.id,
            metadata={
                "occurrence_date": payload.occurrence_date.isoformat(),
                "action": payload.action,
                "moved_to_date": moved_to_date.isoformat() if moved_to_date else None,
            },
            request_id=getattr(request.state, "request_id", None),
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="A series exception already exists.") from exc
    return series_exception_output(exception)


@router.delete("/series/{series_id}/exceptions/{occurrence_date}", responses=API_ERROR_RESPONSES)
def remove_series_exception(
    series_id: int,
    occurrence_date: date,
    principal: AuthenticatedUser,
    session: Annotated[Session, Depends(get_session)],
    request: Request,
) -> Response:
    series = _series_for_user(session, series_id, principal)
    exception = session.scalar(
        select(ContestSeriesException).where(
            ContestSeriesException.series_id == series.id,
            ContestSeriesException.occurrence_date == occurrence_date,
        )
    )
    if exception is None:
        raise HTTPException(status_code=404, detail="Series exception not found.")
    edition = session.scalar(
        select(Contest).where(
            Contest.series_id == series.id,
            Contest.series_occurrence_date == occurrence_date,
        )
    )
    if edition is not None and exception.action == "move":
        start_seconds = series.start_time_seconds
        start = datetime.combine(
            occurrence_date,
            time(start_seconds // 3600, (start_seconds % 3600) // 60, start_seconds % 60),
            tzinfo=UTC,
        )
        edition.starts_at = start
        edition.ends_at = start + timedelta(seconds=series.duration_seconds)
        if not edition.cutoff_is_override:
            edition.log_submission_cutoff_at = edition.ends_at + timedelta(
                seconds=series.cutoff_offset_seconds
            )
    session.delete(exception)
    record_audit_event(
        session,
        actor_user_id=principal.user_id,
        action="contest_series.exception_removed",
        target_type="contest_series",
        target_id=series.id,
        metadata={"occurrence_date": occurrence_date.isoformat()},
        request_id=getattr(request.state, "request_id", None),
    )
    session.commit()
    return Response(status_code=204)


@router.delete("/series/{series_id}", status_code=204, responses=API_ERROR_RESPONSES)
def delete_series(
    series_id: int,
    payload: SeriesDeleteConfirmation,
    principal: AuthenticatedUser,
    session: Annotated[Session, Depends(get_session)],
    request: Request,
) -> Response:
    series = _series_for_user(session, series_id, principal)
    if payload.confirm_name != series.name:
        raise HTTPException(status_code=422, detail="Confirmation name does not match this series.")
    series_name = series.name
    database_engine = session.get_bind()
    editions = list(session.scalars(select(Contest).where(Contest.series_id == series.id)))
    try:
        counts = {"editions": len(editions), "entries": 0, "score_runs": 0, "publications": 0}
        for edition in editions:
            deleted = delete_contest_records(session, edition)
            for key in ("entries", "score_runs", "publications"):
                counts[key] += deleted[key]
        session.execute(
            delete(ContestSeriesException).where(ContestSeriesException.series_id == series_id)
        )
        session.delete(series)
        record_audit_event(
            session,
            actor_user_id=principal.user_id,
            action="contest_series.deleted",
            target_type="contest_series",
            target_id=series_id,
            metadata={"name": series_name, **counts},
            request_id=getattr(request.state, "request_id", None),
        )
        session.commit()
    except DeletionConflictError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="The series has retained references that prevent safe deletion.",
        ) from exc
    except Exception:
        session.rollback()
        logger.exception("contest_series_delete_failed", extra={"series_id": series_id})
        raise
    session.close()
    vacuum_sqlite_after_commit(
        database_engine, resource_kind="contest_series", resource_id=series_id
    )
    return Response(status_code=204)


@router.delete("/{contest_id}", status_code=204, responses=API_ERROR_RESPONSES)
def delete_contest(
    payload: ContestDeleteConfirmation,
    contest: Annotated[Contest, Depends(require_contest_access)],
    principal: AuthenticatedUser,
    session: Annotated[Session, Depends(get_session)],
    request: Request,
) -> Response:
    """Delete a contest and its associated logs, results, and contest-scoped history."""
    if contest.series_id is not None:
        raise HTTPException(
            status_code=409,
            detail="Recurring editions must be removed through the entire-series deletion action.",
        )
    if payload.confirm_slug != contest.slug:
        raise HTTPException(
            status_code=422, detail="Confirmation slug does not match this contest."
        )
    contest_id = contest.id
    contest_slug = contest.slug
    database_engine = session.get_bind()
    try:
        counts = delete_contest_records(session, contest)
        record_audit_event(
            session,
            actor_user_id=principal.user_id,
            action="contest.deleted",
            target_type="contest",
            target_id=contest_id,
            metadata={"slug": contest_slug, **counts},
            request_id=getattr(request.state, "request_id", None),
        )
        session.commit()
    except DeletionConflictError as exc:
        session.rollback()
        logger.warning(
            "contest_delete_blocked",
            extra={"contest_id": contest_id, "failure_kind": "retained_cross_contest_reference"},
        )
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        session.rollback()
        failure_kind = _integrity_failure_kind(exc)
        logger.warning(
            "contest_delete_blocked",
            extra={"contest_id": contest_id, "failure_kind": failure_kind},
        )
        raise HTTPException(
            status_code=409,
            detail="The contest has retained references that prevent safe deletion.",
        ) from exc
    session.close()
    vacuum_sqlite_after_commit(database_engine, resource_kind="contest", resource_id=contest_id)
    return Response(status_code=204)


def _latest_revision_id():
    return (
        select(EntryRevision.id)
        .where(EntryRevision.entry_id == Entry.id)
        .order_by(EntryRevision.revision_number.desc(), EntryRevision.id.desc())
        .limit(1)
        .correlate(Entry)
        .scalar_subquery()
    )


def _revision_callsign(revision_id):
    return (
        select(Station.callsign_submitted)
        .where(Station.entry_revision_id == revision_id)
        .order_by(Station.id)
        .limit(1)
        .correlate(Entry)
        .scalar_subquery()
    )


def _revision_qso_count(revision_id):
    return (
        select(func.count(Qso.id))
        .where(Qso.entry_revision_id == revision_id)
        .correlate(EntryRevision)
        .scalar_subquery()
    )


def _entry_summary(
    entry: Entry,
    revision: EntryRevision | None,
    callsign: str | None,
    qso_count: int,
) -> dict[str, object]:
    return {
        "entry_id": entry.id,
        "entry_key": entry.entry_key,
        "callsign": callsign or entry.entry_key,
        "status": entry.status.value,
        "is_late": entry.is_late,
        "category_values": entry.category_values,
        "submitted_at": entry.submitted_at,
        "revision_id": revision.id if revision else None,
        "revision_number": revision.revision_number if revision else None,
        "input_format": revision.input_format if revision else None,
        "original_filename": revision.original_filename if revision else None,
        "qso_count": qso_count,
    }


@router.get("/{contest_id}/entries", responses=API_ERROR_RESPONSES)
def list_contest_entries(
    contest: Annotated[Contest, Depends(require_contest_access)],
    session: Annotated[Session, Depends(get_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
    search: Annotated[str | None, Query(max_length=120)] = None,
) -> dict[str, object]:
    latest_id = _latest_revision_id()
    callsign = _revision_callsign(latest_id)
    statement = select(Entry).where(Entry.contest_id == contest.id)
    count_statement = select(func.count(Entry.id)).where(Entry.contest_id == contest.id)
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        search_condition = or_(Entry.entry_key.ilike(pattern), callsign.ilike(pattern))
        statement = statement.where(search_condition)
        count_statement = count_statement.where(search_condition)

    total = session.scalar(count_statement) or 0
    rows = session.execute(
        select(Entry, EntryRevision, callsign, _revision_qso_count(EntryRevision.id))
        .outerjoin(EntryRevision, EntryRevision.id == latest_id)
        .where(statement.whereclause)
        .order_by(Entry.submitted_at.desc(), Entry.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [
        _entry_summary(entry, revision, station_call, qso_count or 0)
        for entry, revision, station_call, qso_count in rows
    ]
    return {
        "items": items,
        "meta": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": (total + page_size - 1) // page_size,
        },
    }


@router.get("/{contest_id}/entries/{entry_id}", responses=API_ERROR_RESPONSES)
def get_contest_entry(
    contest_id: int,
    entry_id: int,
    contest: Annotated[Contest, Depends(require_contest_access)],
    session: Annotated[Session, Depends(get_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
    revision_id: Annotated[int | None, Query(ge=1)] = None,
) -> dict[str, object]:
    entry = session.scalar(
        select(Entry).where(Entry.id == entry_id, Entry.contest_id == contest.id)
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found.")
    if revision_id is None:
        revision = session.scalar(
            select(EntryRevision)
            .where(EntryRevision.entry_id == entry.id)
            .order_by(EntryRevision.revision_number.desc(), EntryRevision.id.desc())
            .limit(1)
        )
    else:
        revision = session.scalar(
            select(EntryRevision).where(
                EntryRevision.id == revision_id,
                EntryRevision.entry_id == entry.id,
            )
        )
        if revision is None:
            raise HTTPException(status_code=404, detail="Entry revision not found.")
    if revision is None:
        raise HTTPException(status_code=404, detail="Entry has no uploaded log revision.")

    station = session.scalar(
        select(Station)
        .where(Station.entry_revision_id == revision.id)
        .order_by(Station.id)
        .limit(1)
    )
    revisions = list(
        session.scalars(
            select(EntryRevision)
            .where(EntryRevision.entry_id == entry.id)
            .order_by(EntryRevision.revision_number.desc(), EntryRevision.id.desc())
        )
    )
    revision_qso_counts = (
        dict(
            session.execute(
                select(Qso.entry_revision_id, func.count(Qso.id))
                .where(Qso.entry_revision_id.in_([row.id for row in revisions]))
                .group_by(Qso.entry_revision_id)
            ).all()
        )
        if revisions
        else {}
    )
    total = (
        session.scalar(select(func.count(Qso.id)).where(Qso.entry_revision_id == revision.id)) or 0
    )
    contacts = session.scalars(
        select(Qso)
        .where(Qso.entry_revision_id == revision.id)
        .order_by(Qso.source_line_number, Qso.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "entry": {
            **_entry_summary(
                entry, revision, station.callsign_submitted if station else None, total
            ),
            "revision_count": len(revisions),
        },
        "revisions": [
            {
                "id": row.id,
                "revision_number": row.revision_number,
                "input_format": row.input_format,
                "original_filename": row.original_filename,
                "byte_size": row.byte_size,
                "submitted_at": row.submitted_at,
                "received_at": row.received_at,
                "qso_count": revision_qso_counts.get(row.id, 0),
            }
            for row in revisions
        ],
        "contacts": [
            {
                "id": qso.id,
                "source_line_number": qso.source_line_number,
                "occurred_at": qso.occurred_at,
                "callsign": qso.callsign_submitted,
                "band": qso.band,
                "mode": qso.mode,
                "exchange_sent": qso.exchange_sent_submitted,
                "exchange_received": qso.exchange_received_submitted,
            }
            for qso in contacts
        ],
        "meta": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": (total + page_size - 1) // page_size,
        },
    }


@router.get(
    "/{contest_id}/entries/{entry_id}/revisions/{revision_id}/download",
    responses=API_ERROR_RESPONSES,
)
def download_contest_entry_revision(
    contest_id: int,
    entry_id: int,
    revision_id: int,
    contest: Annotated[Contest, Depends(require_contest_access)],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    revision = session.scalar(
        select(EntryRevision)
        .join(Entry, Entry.id == EntryRevision.entry_id)
        .where(
            Entry.id == entry_id,
            Entry.contest_id == contest.id,
            EntryRevision.id == revision_id,
        )
    )
    if revision is None:
        raise HTTPException(status_code=404, detail="Entry revision not found.")
    suffix = ".adi" if revision.input_format == "adif" else ".log"
    return Response(
        revision.original_content,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="entry-{entry_id}-revision-'
                f'{revision.revision_number}{suffix}"'
            )
        },
    )


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
    remove_series = False
    if contest.series_id is not None and payload.periodicity is None:
        series = contest.series
        edition_ids = list(
            session.scalars(select(Contest.id).where(Contest.series_id == contest.series_id))
        )
        exception_exists = session.scalar(
            select(ContestSeriesException.id)
            .where(ContestSeriesException.series_id == contest.series_id)
            .limit(1)
        )
        if not contest.is_series_anchor or len(edition_ids) > 1 or exception_exists is not None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "A recurring series with other editions or exceptions cannot be made one-time."
                ),
            )
        remove_series = series is not None
    if (
        contest.series_id is not None
        and not contest.is_series_anchor
        and payload.periodicity is not None
        and payload.periodicity.model_dump(mode="json", exclude_none=True)
        != contest.series.periodicity
    ):
        raise HTTPException(
            status_code=409,
            detail="Edit recurrence settings on the series anchor, not an individual edition.",
        )
    if contest.series_id is not None and contest.is_series_anchor:
        series = contest.series
        assert series is not None
        existing_edition_count = (
            session.scalar(
                select(func.count()).select_from(Contest).where(Contest.series_id == series.id)
            )
            or 0
        )
        requested_recurrence = (
            payload.periodicity.model_dump(mode="json", exclude_none=True)
            if payload.periodicity is not None
            else None
        )
        requested_start_seconds = (
            payload.starts_at.astimezone(UTC).hour * 3600
            + payload.starts_at.astimezone(UTC).minute * 60
            + payload.starts_at.astimezone(UTC).second
        )
        requested_duration = int((payload.ends_at - payload.starts_at).total_seconds())
        if existing_edition_count > 1 and (
            requested_recurrence != series.periodicity
            or requested_start_seconds != series.start_time_seconds
            or requested_duration != series.duration_seconds
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Recurrence, start time, and duration cannot be changed after future editions "
                    "exist. Use a skip or move exception for an individual occurrence."
                ),
            )
    cutoff_at, cutoff_offset, cutoff_override = _cutoff_settings(payload)
    if contest.series_id is not None and payload.cutoff_offset_seconds is None:
        cutoff_offset = contest.series.cutoff_offset_seconds
    editable_fields = (
        "name",
        "slug",
        "description",
        "starts_at",
        "ends_at",
        "periodicity",
        "log_submission_cutoff_at",
        "cutoff_is_override",
        "auto_recalculate_on_upload",
    )
    values = payload.model_dump(exclude={"audit_reason"}, mode="python")
    values["periodicity"] = (
        payload.periodicity.model_dump(mode="json", exclude_none=True)
        if payload.periodicity is not None
        else None
    )
    values["log_submission_cutoff_at"] = cutoff_at
    values["cutoff_is_override"] = cutoff_override
    changed_fields = [
        field_name
        for field_name in editable_fields
        if getattr(contest, field_name) != values[field_name]
    ]
    for field_name in editable_fields:
        setattr(contest, field_name, values[field_name])
    try:
        if remove_series:
            series = contest.series
            contest.series_id = None
            contest.series_occurrence_date = None
            contest.is_series_anchor = False
            contest.cutoff_is_override = True
            if series is not None:
                session.delete(series)
        elif (
            payload.periodicity is not None
            and contest.series_id is None
            and cutoff_offset is not None
        ):
            session.flush()
            create_series_for_contest(
                session,
                contest,
                recurrence=payload.periodicity,
                cutoff_offset_seconds=cutoff_offset,
                automatic_window_days=payload.automatic_window_days,
                cutoff_is_override=cutoff_override,
            )
        elif contest.series_id is not None and contest.is_series_anchor:
            series = contest.series
            assert series is not None
            if cutoff_offset is None:
                cutoff_offset = max(0, int((cutoff_at - payload.ends_at).total_seconds()))
            series.name = payload.name
            series.base_slug = payload.slug
            series.description = payload.description
            series.periodicity = payload.periodicity.model_dump(mode="json", exclude_none=True)
            series.start_time_seconds = (
                payload.starts_at.astimezone(UTC).hour * 3600
                + payload.starts_at.astimezone(UTC).minute * 60
                + payload.starts_at.astimezone(UTC).second
            )
            series.duration_seconds = int((payload.ends_at - payload.starts_at).total_seconds())
            series.cutoff_offset_seconds = cutoff_offset
            series.automatic_window_days = payload.automatic_window_days
            series.auto_recalculate_on_upload = payload.auto_recalculate_on_upload
            for edition in series.editions:
                if not edition.cutoff_is_override:
                    edition.log_submission_cutoff_at = edition.ends_at + timedelta(
                        seconds=cutoff_offset
                    )
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
    version = session.get(RulesetVersion, payload.ruleset_version_id)
    if version is None or not can_manage_ruleset(
        session, session.get(Ruleset, version.ruleset_id) if version else None, principal
    ):
        raise HTTPException(status_code=404, detail="Ruleset version not found.")
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


def public_contest_detail_output(contest: Contest, session: Session) -> dict[str, object]:
    """Expose public contest metadata and its selected, validated ruleset."""
    output = public_contest_output(contest)
    ruleset = (
        session.get(RulesetVersion, contest.ruleset_version_id)
        if contest.ruleset_version_id is not None
        else None
    )
    if ruleset is not None:
        output["ruleset"] = load_ruleset_version(ruleset).model_dump(mode="json")
    else:
        output["ruleset"] = None
    return output


@router.get("/{contest_id}/administrators")
def list_contest_administrators(
    contest: Annotated[Contest, Depends(require_contest_access)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    rows = session.execute(
        select(ContestAdministrator, SystemUser)
        .join(SystemUser, SystemUser.id == ContestAdministrator.user_id)
        .where(ContestAdministrator.contest_id == contest.id)
        .order_by(SystemUser.display_name, SystemUser.id)
    )
    eligible = list(
        session.scalars(
            select(SystemUser)
            .where(
                SystemUser.is_active.is_(True),
                SystemUser.role == SystemRole.CONTEST_MANAGER,
                SystemUser.id != contest.owner_user_id,
                SystemUser.id.not_in(
                    select(ContestAdministrator.user_id).where(
                        ContestAdministrator.contest_id == contest.id
                    )
                ),
            )
            .order_by(SystemUser.display_name, SystemUser.id)
        )
    )
    return {
        "owner_user_id": contest.owner_user_id,
        "items": [
            {"user_id": user.id, "username": user.username, "display_name": user.display_name}
            for _link, user in rows
        ],
        "eligible": [
            {"user_id": user.id, "username": user.username, "display_name": user.display_name}
            for user in eligible
        ],
    }


@router.post("/{contest_id}/administrators", status_code=201)
def add_contest_administrator(
    contest_id: int,
    payload: AdministratorAssignment,
    actor: AuthenticatedUser,
    session: Annotated[Session, Depends(get_session)],
    request: Request,
) -> dict[str, object]:
    contest = session.get(Contest, contest_id)
    if contest is None or (
        actor.role is not SystemRole.GLOBAL_ADMINISTRATOR and contest.owner_user_id != actor.user_id
    ):
        raise HTTPException(status_code=404, detail="Contest not found.")
    user = session.get(SystemUser, payload.user_id)
    if user is None or not user.is_active or user.role is not SystemRole.CONTEST_MANAGER:
        raise HTTPException(
            status_code=422, detail="Select an active contest administrator account."
        )
    if user.id == contest.owner_user_id:
        raise HTTPException(
            status_code=409, detail="The contest owner is already an administrator."
        )
    link = ContestAdministrator(
        contest_id=contest.id, user_id=user.id, added_by_user_id=actor.user_id
    )
    session.add(link)
    try:
        session.flush()
        record_audit_event(
            session,
            actor_user_id=actor.user_id,
            action="contest.administrator_added",
            target_type="contest",
            target_id=contest.id,
            metadata={"administrator_user_id": user.id},
            request_id=getattr(request.state, "request_id", None),
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="This user already administers the contest."
        ) from exc
    return {"user_id": user.id, "username": user.username, "display_name": user.display_name}


@router.delete("/{contest_id}/administrators/{user_id}", status_code=204)
def remove_contest_administrator(
    contest_id: int,
    user_id: int,
    actor: AuthenticatedUser,
    session: Annotated[Session, Depends(get_session)],
    request: Request,
) -> Response:
    contest = session.get(Contest, contest_id)
    if contest is None or (
        actor.role is not SystemRole.GLOBAL_ADMINISTRATOR and contest.owner_user_id != actor.user_id
    ):
        raise HTTPException(status_code=404, detail="Contest not found.")
    link = session.get(ContestAdministrator, (contest_id, user_id))
    if link is None:
        raise HTTPException(status_code=404, detail="Contest administrator not found.")
    session.delete(link)
    record_audit_event(
        session,
        actor_user_id=actor.user_id,
        action="contest.administrator_removed",
        target_type="contest",
        target_id=contest.id,
        metadata={"administrator_user_id": user_id},
        request_id=getattr(request.state, "request_id", None),
    )
    session.commit()
    return Response(status_code=204)


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
    return public_contest_detail_output(contest, session)
