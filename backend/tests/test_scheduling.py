from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from backend.app.scheduling import (
    Recurrence,
    ScheduleResolutionError,
    recurrence_date,
    resolve_next_contest_schedules,
)


@pytest.mark.parametrize(
    ("frequency", "occurrence", "expected"),
    [
        ("first_full_weekend", None, date(2026, 2, 7)),
        ("nth_full_weekend", 2, date(2026, 2, 14)),
        ("last_full_weekend", None, date(2026, 2, 21)),
    ],
)
def test_full_weekend_recurrence_patterns(frequency, occurrence, expected):
    recurrence = Recurrence.model_validate(
        {
            "frequency": frequency,
            "month": 2,
            **({"occurrence": occurrence} if occurrence is not None else {}),
        }
    )
    assert recurrence_date(recurrence, 2026) == expected


def test_nth_full_weekend_rejects_a_weekend_that_does_not_exist():
    recurrence = Recurrence(frequency="nth_full_weekend", month=2, occurrence=5)
    with pytest.raises(ScheduleResolutionError, match="does not exist"):
        recurrence_date(recurrence, 2026)


def test_five_occurrence_preview_keeps_start_time_and_event_duration_in_utc():
    recurrence = Recurrence(frequency="first_full_weekend", month=1)
    resolved = resolve_next_contest_schedules(
        recurrence,
        datetime(2026, 1, 3, 8, tzinfo=UTC),
        datetime(2026, 1, 3, 11, 30, tzinfo=UTC),
    )
    assert [item.starts_at for item in resolved] == [
        datetime(2026, 1, 3, 8, tzinfo=UTC),
        datetime(2027, 1, 2, 8, tzinfo=UTC),
        datetime(2028, 1, 1, 8, tzinfo=UTC),
        datetime(2029, 1, 6, 8, tzinfo=UTC),
        datetime(2030, 1, 5, 8, tzinfo=UTC),
    ]
    assert all((item.ends_at - item.starts_at).total_seconds() == 12600 for item in resolved)


def test_full_weekend_occurrence_is_required_for_nth_pattern():
    with pytest.raises(ValidationError, match="requires an occurrence"):
        Recurrence(frequency="nth_full_weekend", month=2)
