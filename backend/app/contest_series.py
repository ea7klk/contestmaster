"""Creation and maintenance of recurring contest editions."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models import Contest, ContestSeries, ContestSeriesException, ContestStatus
from backend.app.scheduling import Recurrence, ScheduleResolutionError, recurrence_date


def seconds_since_midnight(value: datetime) -> int:
    utc_value = value.astimezone(UTC)
    return utc_value.hour * 3600 + utc_value.minute * 60 + utc_value.second


def create_series_for_contest(
    session: Session,
    contest: Contest,
    *,
    recurrence: Recurrence,
    cutoff_offset_seconds: int,
    automatic_window_days: int | None,
    cutoff_is_override: bool = False,
) -> ContestSeries:
    duration = int((contest.ends_at - contest.starts_at).total_seconds())
    series = ContestSeries(
        owner_user_id=contest.owner_user_id,
        name=contest.name,
        base_slug=contest.slug,
        description=contest.description,
        periodicity=recurrence.model_dump(mode="json", exclude_none=True),
        start_time_seconds=seconds_since_midnight(contest.starts_at),
        duration_seconds=duration,
        cutoff_offset_seconds=cutoff_offset_seconds,
        automatic_window_days=automatic_window_days,
        auto_recalculate_on_upload=contest.auto_recalculate_on_upload,
        ruleset_version_id=contest.ruleset_version_id,
    )
    session.add(series)
    session.flush()
    contest.series_id = series.id
    contest.series_occurrence_date = contest.starts_at.astimezone(UTC).date()
    contest.is_series_anchor = True
    contest.periodicity = recurrence.model_dump(mode="json", exclude_none=True)
    contest.cutoff_is_override = cutoff_is_override
    return series


def _edition_start(series: ContestSeries, event_date: date) -> datetime:
    start_time_seconds = series.start_time_seconds
    start_time_utc = time(
        hour=start_time_seconds // 3600,
        minute=(start_time_seconds % 3600) // 60,
        second=start_time_seconds % 60,
    )
    return datetime.combine(event_date, start_time_utc, tzinfo=UTC)


def generate_due_editions(
    session_factory: sessionmaker,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    """Materialize missing future editions through each series' configured rolling window."""
    current = (now or datetime.now(UTC)).astimezone(UTC)
    generated = 0
    skipped = 0
    with session_factory() as session:
        series_rows = list(
            session.scalars(
                select(ContestSeries).where(ContestSeries.automatic_window_days.is_not(None))
            )
        )
        for series in series_rows:
            horizon = current + timedelta(days=series.automatic_window_days or 0)
            recurrence = Recurrence.model_validate(series.periodicity)
            existing_dates = set(
                session.scalars(
                    select(Contest.series_occurrence_date).where(
                        Contest.series_id == series.id,
                        Contest.series_occurrence_date.is_not(None),
                    )
                )
            )
            exceptions = {
                item.occurrence_date: item
                for item in session.scalars(
                    select(ContestSeriesException).where(
                        ContestSeriesException.series_id == series.id
                    )
                )
            }
            for year in range(current.year, horizon.year + 2):
                try:
                    occurrence_date = recurrence_date(recurrence, year)
                except ScheduleResolutionError:
                    # Invalid annual dates (for example February 29) do not occur every year.
                    continue
                if occurrence_date in existing_dates:
                    continue
                exception = exceptions.get(occurrence_date)
                if exception is not None and exception.action == "skip":
                    skipped += 1
                    continue
                actual_date = (
                    exception.moved_to_date
                    if exception is not None and exception.action == "move"
                    else occurrence_date
                )
                starts_at = _edition_start(series, actual_date)
                ends_at = starts_at + timedelta(seconds=series.duration_seconds)
                if starts_at < current or starts_at > horizon:
                    continue
                slug = f"{series.base_slug[:95].rstrip('-')}-{series.id}-{actual_date:%Y%m%d}"
                session.add(
                    Contest(
                        owner_user_id=series.owner_user_id,
                        ruleset_version_id=series.ruleset_version_id,
                        name=f"{series.name[:180]} — {actual_date.isoformat()}",
                        slug=slug,
                        description=series.description,
                        starts_at=starts_at,
                        ends_at=ends_at,
                        periodicity=series.periodicity,
                        series_id=series.id,
                        series_occurrence_date=occurrence_date,
                        is_series_anchor=False,
                        log_submission_cutoff_at=ends_at
                        + timedelta(seconds=series.cutoff_offset_seconds),
                        cutoff_is_override=False,
                        status=ContestStatus.DRAFT,
                        auto_recalculate_on_upload=series.auto_recalculate_on_upload,
                    )
                )
                existing_dates.add(occurrence_date)
                generated += 1
        session.commit()
    return {"generated": generated, "skipped": skipped}
