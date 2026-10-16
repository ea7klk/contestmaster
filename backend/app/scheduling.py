"""UTC recurrence rules owned by contest configuration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Recurrence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    frequency: Literal["annual_date", "nth_weekday", "first_full_weekend"]
    month: Annotated[int, Field(ge=1, le=12)]
    day: Annotated[int, Field(ge=1, le=31)] | None = None
    weekday: Annotated[int, Field(ge=0, le=6)] | None = None
    occurrence: Annotated[int, Field(ge=-1, le=5)] | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> Recurrence:
        if self.frequency == "annual_date" and (
            self.day is None or self.weekday is not None or self.occurrence is not None
        ):
            raise ValueError("annual_date requires day and does not accept weekday or occurrence")
        if self.frequency == "nth_weekday" and (
            self.weekday is None or self.occurrence is None or self.day is not None
        ):
            raise ValueError("nth_weekday requires weekday and occurrence, and not day")
        if self.frequency == "nth_weekday" and self.occurrence == 0:
            raise ValueError("occurrence must be 1 through 5 or -1 for the last weekday")
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
            next_month = (
                date(year, recurrence.month + 1, 1)
                if recurrence.month < 12
                else date(year + 1, 1, 1)
            )
            last_day = next_month - timedelta(days=1)
            return last_day - timedelta(days=(last_day.weekday() - recurrence.weekday) % 7)
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
    event_date = recurrence_date(recurrence, year)
    start = datetime.combine(event_date, utc_start.time(), tzinfo=UTC)
    return ResolvedSchedule(starts_at=start, ends_at=start + duration)
