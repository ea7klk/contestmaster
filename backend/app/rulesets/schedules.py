"""Deterministic contest schedule and submission-cutoff resolution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from backend.app.rulesets.schema import Recurrence, ScheduleRule, SubmissionRule


class ScheduleResolutionError(ValueError):
    pass


@dataclass(frozen=True)
class ResolvedSchedule:
    starts_at: datetime
    ends_at: datetime
    timezone: str
    local_start: datetime


@dataclass(frozen=True)
class ResolvedSubmission:
    cutoff_at: datetime
    late_policy: str
    manager_extension_allowed: bool


def _recurrence_date(recurrence: Recurrence, year: int) -> date:
    if recurrence.frequency == "annual_date":
        if recurrence.day is None:
            raise ScheduleResolutionError("Annual date recurrence has no day")
        try:
            return date(year, recurrence.month, recurrence.day)
        except ValueError as exc:
            raise ScheduleResolutionError(
                "Annual recurrence date is invalid for this year"
            ) from exc
    if recurrence.frequency == "nth_weekday":
        if recurrence.weekday is None or recurrence.occurrence is None:
            raise ScheduleResolutionError("Nth-weekday recurrence is incomplete")
        if recurrence.occurrence == -1:
            last_day = (
                date(year, recurrence.month + 1, 1) - timedelta(days=1)
                if recurrence.month < 12
                else date(year + 1, 1, 1) - timedelta(days=1)
            )
            return last_day - timedelta(days=(last_day.weekday() - recurrence.weekday) % 7)
        if recurrence.occurrence == 0:
            raise ScheduleResolutionError("Occurrence must be 1 through 5 or -1 for last")
        first = date(year, recurrence.month, 1)
        offset = (recurrence.weekday - first.weekday()) % 7
        result = first + timedelta(days=offset + 7 * (recurrence.occurrence - 1))
        if result.month != recurrence.month:
            raise ScheduleResolutionError("Requested weekday occurrence does not exist")
        return result
    first_day = date(year, recurrence.month, 1)
    first_saturday = first_day + timedelta(days=(5 - first_day.weekday()) % 7)
    sunday = first_saturday + timedelta(days=1)
    if sunday.month != recurrence.month:
        raise ScheduleResolutionError("Month has no complete Saturday-Sunday weekend")
    return first_saturday


def _resolve_local(naive: datetime, zone: ZoneInfo, fold: int | None) -> datetime:
    candidate = naive.replace(tzinfo=zone, fold=fold or 0)
    round_trip = candidate.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
    if round_trip != naive:
        raise ScheduleResolutionError(
            "Local schedule time does not exist because of a DST transition"
        )
    first = naive.replace(tzinfo=zone, fold=0).utcoffset()
    second = naive.replace(tzinfo=zone, fold=1).utcoffset()
    if first != second and fold is None:
        raise ScheduleResolutionError("Ambiguous local time requires an explicit fold policy")
    return candidate.astimezone(UTC)


def resolve_schedule(rule: ScheduleRule, year: int | None = None) -> ResolvedSchedule:
    """Resolve a fixed instant or recurrence and return the UTC instants to persist."""
    try:
        zone = ZoneInfo(rule.timezone)
    except Exception as exc:
        raise ScheduleResolutionError(f"Unknown timezone: {rule.timezone}") from exc
    if rule.fixed_start_utc is not None:
        starts_at = rule.fixed_start_utc.astimezone(UTC)
        local_start = starts_at.astimezone(zone)
    else:
        if rule.recurrence is None or year is None:
            raise ScheduleResolutionError("Recurring schedule requires an edition year")
        local_date = _recurrence_date(rule.recurrence, year)
        naive = datetime.combine(local_date, rule.start_local_time)
        starts_at = _resolve_local(naive, zone, rule.ambiguous_time_fold)
        local_start = naive.replace(tzinfo=zone, fold=rule.ambiguous_time_fold or 0)
    return ResolvedSchedule(
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=rule.duration_minutes),
        timezone=rule.timezone,
        local_start=local_start,
    )


def resolve_submission(rule: SubmissionRule, schedule: ResolvedSchedule) -> ResolvedSubmission:
    """Resolve a separately configured cutoff; contest end is never assumed as cutoff."""
    if rule.cutoff_mode == "at_utc":
        if rule.cutoff_utc is None or rule.cutoff_utc.tzinfo is None:
            raise ScheduleResolutionError("Fixed cutoff must be timezone-aware")
        cutoff = rule.cutoff_utc.astimezone(UTC)
    else:
        if rule.minutes_after_contest is None:
            raise ScheduleResolutionError("Relative cutoff is missing minutes_after_contest")
        cutoff = schedule.ends_at + timedelta(minutes=rule.minutes_after_contest)
    return ResolvedSubmission(cutoff, rule.late_policy, rule.manager_extension_allowed)


def classify_submission(
    submitted_at: datetime,
    cutoff_at: datetime,
    late_policy: str,
    *,
    manager_extension_until: datetime | None = None,
    manager_extension_allowed: bool = False,
) -> str:
    """Return on_time, late, checklog, or rejected for a submission instant."""
    if submitted_at.tzinfo is None or submitted_at.utcoffset() is None:
        raise ValueError("submitted_at must be timezone-aware")
    if cutoff_at.tzinfo is None or cutoff_at.utcoffset() is None:
        raise ValueError("cutoff_at must be timezone-aware")
    if manager_extension_until is not None:
        if manager_extension_until.tzinfo is None or manager_extension_until.utcoffset() is None:
            raise ValueError("manager_extension_until must be timezone-aware")
        if manager_extension_until > cutoff_at and not manager_extension_allowed:
            raise ValueError("This ruleset does not allow manager cutoff extensions")
    cutoff = max(cutoff_at, manager_extension_until) if manager_extension_until else cutoff_at
    if submitted_at.astimezone(UTC) <= cutoff.astimezone(UTC):
        return "on_time"
    if late_policy == "accept_late":
        return "late"
    if late_policy == "checklog":
        return "checklog"
    return "rejected"
