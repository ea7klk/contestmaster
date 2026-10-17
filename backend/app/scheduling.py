"""UTC recurrence rules owned by contest configuration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Recurrence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    frequency: Literal[
        "annual_date",
        "nth_weekday",
        "first_full_weekend",
        "last_full_weekend",
        "nth_full_weekend",
    ]
    month: Annotated[int, Field(ge=1, le=12)] | list[Annotated[int, Field(ge=1, le=12)]]
    day: Annotated[int, Field(ge=1, le=31)] | None = None
    weekday: Annotated[int, Field(ge=0, le=6)] | list[Annotated[int, Field(ge=0, le=6)]] | None = (
        None
    )
    occurrence: Annotated[int, Field(ge=-1, le=5)] | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> Recurrence:
        months = self.month if isinstance(self.month, list) else [self.month]
        weekdays = self.weekday if isinstance(self.weekday, list) else [self.weekday]
        if not months or len(set(months)) != len(months):
            raise ValueError("month selections must be non-empty and unique")
        if self.frequency not in {"nth_weekday", "nth_full_weekend"} and len(months) != 1:
            raise ValueError("multiple months are only supported for nth recurrence patterns")
        if self.frequency == "annual_date" and (
            self.day is None
            or self.weekday is not None
            or self.occurrence is not None
            or isinstance(self.month, list)
        ):
            raise ValueError("annual_date requires day and does not accept weekday or occurrence")
        if self.frequency == "nth_weekday" and (
            self.weekday is None
            or self.occurrence is None
            or self.day is not None
            or not weekdays
            or len(set(weekdays)) != len(weekdays)
        ):
            raise ValueError(
                "nth_weekday requires unique month/weekday selections and occurrence, and not day"
            )
        if self.frequency == "nth_weekday" and self.occurrence == 0:
            raise ValueError("occurrence must be 1 through 5 or -1 for the last weekday")
        if self.frequency == "nth_full_weekend" and (
            self.occurrence is None
            or self.occurrence not in {1, 2, 3, 4, 5}
            or self.day is not None
            or self.weekday is not None
        ):
            raise ValueError("nth_full_weekend requires an occurrence from 1 through 5")
        if self.frequency == "last_full_weekend" and any(
            value is not None for value in (self.day, self.weekday, self.occurrence)
        ):
            raise ValueError("last_full_weekend derives its calendar date")
        if self.frequency == "first_full_weekend" and any(
            value is not None for value in (self.day, self.weekday, self.occurrence)
        ):
            raise ValueError("first_full_weekend derives its calendar date")
        return self


class ScheduleResolutionError(ValueError):
    pass


@dataclass(frozen=True)
class ResolvedSchedule:
    starts_at: datetime
    ends_at: datetime


def recurrence_date(recurrence: Recurrence, year: int) -> date:
    """Resolve the first matching date for compatibility with single-date callers."""
    dates = recurrence_dates(recurrence, year)
    if not dates:
        raise ScheduleResolutionError("No occurrence exists for the selected pattern this year")
    return dates[0]


def recurrence_dates(recurrence: Recurrence, year: int) -> list[date]:
    """Resolve all matching event dates in a year, in calendar order."""
    months = recurrence.month if isinstance(recurrence.month, list) else [recurrence.month]
    if recurrence.frequency == "annual_date":
        if recurrence.day is None:
            raise ScheduleResolutionError("Annual date recurrence has no day")
        try:
            return [date(year, months[0], recurrence.day)]
        except ValueError as exc:
            raise ScheduleResolutionError(
                "Annual recurrence date is invalid for this year"
            ) from exc
    if recurrence.frequency == "nth_weekday":
        if recurrence.weekday is None or recurrence.occurrence is None:
            raise ScheduleResolutionError("Nth-weekday recurrence is incomplete")
        weekdays = (
            recurrence.weekday if isinstance(recurrence.weekday, list) else [recurrence.weekday]
        )
        output: list[date] = []
        for month in months:
            for weekday in weekdays:
                if recurrence.occurrence == -1:
                    next_month = date(year, month + 1, 1) if month < 12 else date(year + 1, 1, 1)
                    last_day = next_month - timedelta(days=1)
                    result = last_day - timedelta(days=(last_day.weekday() - weekday) % 7)
                else:
                    first = date(year, month, 1)
                    offset = (weekday - first.weekday()) % 7
                    result = first + timedelta(days=offset + 7 * (recurrence.occurrence - 1))
                if result.month == month:
                    output.append(result)
        if not output:
            raise ScheduleResolutionError(
                "Requested weekday occurrence does not exist in selected months"
            )
        return sorted(set(output))

    output = []
    for month in months:
        first_day = date(year, month, 1)
        first_saturday = first_day + timedelta(days=(5 - first_day.weekday()) % 7)
        weekends = [
            first_saturday + timedelta(days=7 * index)
            for index in range(5)
            if (first_saturday + timedelta(days=7 * index) + timedelta(days=1)).month == month
        ]
        if recurrence.frequency == "first_full_weekend":
            output.append(weekends[0])
        elif recurrence.frequency == "last_full_weekend":
            output.append(weekends[-1])
        elif recurrence.frequency == "nth_full_weekend":
            occurrence = recurrence.occurrence or 1
            if occurrence <= len(weekends):
                output.append(weekends[occurrence - 1])
    if not output:
        raise ScheduleResolutionError(
            "Requested full-weekend occurrence does not exist in selected months"
        )
    return sorted(set(output))


def resolve_contest_schedule(
    recurrence: Recurrence, year: int, starts_at: datetime, ends_at: datetime
) -> ResolvedSchedule:
    if starts_at.tzinfo is None or ends_at.tzinfo is None:
        raise ScheduleResolutionError("Contest start and end must be timezone-aware")
    utc_start = starts_at.astimezone(UTC)
    utc_end = ends_at.astimezone(UTC)
    duration = utc_end - utc_start
    if duration <= timedelta(0):
        raise ScheduleResolutionError("Contest end must follow its start")
    dates = recurrence_dates(recurrence, year)
    requested_date = starts_at.astimezone(UTC).date()
    event_date = requested_date if requested_date in dates else dates[0]
    start = datetime.combine(event_date, utc_start.time(), tzinfo=UTC)
    return ResolvedSchedule(starts_at=start, ends_at=start + duration)


def resolve_next_contest_schedules(
    recurrence: Recurrence,
    starts_at: datetime,
    ends_at: datetime,
    *,
    count: int = 5,
) -> list[ResolvedSchedule]:
    """Resolve the next recurring occurrences from the configured edition onward."""
    if starts_at.tzinfo is None or ends_at.tzinfo is None:
        raise ScheduleResolutionError("Contest start and end must be timezone-aware")
    if count < 1 or count > 20:
        raise ScheduleResolutionError("Occurrence preview count must be between 1 and 20")
    start_utc = starts_at.astimezone(UTC)
    end_utc = ends_at.astimezone(UTC)
    duration = end_utc - start_utc
    if duration <= timedelta(0):
        raise ScheduleResolutionError("Contest end must follow its start")
    output: list[ResolvedSchedule] = []
    year = start_utc.year
    while len(output) < count and year <= start_utc.year + count + 4:
        try:
            event_dates = recurrence_dates(recurrence, year)
        except ScheduleResolutionError:
            # A recurrence such as February 29 may be absent in some years.
            year += 1
            continue
        for event_date in event_dates:
            start = datetime.combine(event_date, start_utc.time(), tzinfo=UTC)
            if start >= start_utc:
                output.append(ResolvedSchedule(starts_at=start, ends_at=start + duration))
        output.sort(key=lambda item: item.starts_at)
        if len(output) >= count:
            return output[:count]
        year += 1
    if len(output) < count:
        raise ScheduleResolutionError("Could not resolve the requested upcoming occurrences")
    return output
