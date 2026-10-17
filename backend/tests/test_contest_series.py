import asyncio
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.contest_series import create_series_for_contest, generate_due_editions
from backend.app.db import Base, build_engine
from backend.app.models import (
    Contest,
    ContestSeriesException,
    ContestStatus,
    SystemRole,
    SystemUser,
)
from backend.app.scheduling import Recurrence


@pytest.fixture
def session_factory():
    engine = build_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    yield factory
    engine.dispose()


def create_series(session: Session, *, window: int | None = 730):
    manager = SystemUser(
        username="series-manager",
        email_normalized="series-manager@example.test",
        display_name="Series Manager",
        role=SystemRole.CONTEST_MANAGER,
        password_hash="test-hash",
    )
    session.add(manager)
    session.flush()
    contest = Contest(
        owner_user_id=manager.id,
        name="Spring Sprint",
        slug="spring-sprint",
        starts_at=datetime(2025, 5, 1, 12, tzinfo=UTC),
        ends_at=datetime(2025, 5, 1, 18, tzinfo=UTC),
        periodicity={"frequency": "annual_date", "month": 5, "day": 1},
        log_submission_cutoff_at=datetime(2025, 5, 4, 18, tzinfo=UTC),
        status=ContestStatus.DRAFT,
    )
    session.add(contest)
    session.flush()
    series = create_series_for_contest(
        session,
        contest,
        recurrence=Recurrence(frequency="annual_date", month=5, day=1),
        cutoff_offset_seconds=3 * 86400,
        automatic_window_days=window,
    )
    session.commit()
    return contest, series


def test_rolling_window_materializes_utc_editions_once_and_derives_cutoff(session_factory):
    with session_factory() as session:
        _, series = create_series(session)
        series_id = series.id

    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert generate_due_editions(session_factory, now=now) == {"generated": 2, "skipped": 0}
    assert generate_due_editions(session_factory, now=now) == {"generated": 0, "skipped": 0}

    with session_factory() as session:
        editions = list(
            session.scalars(
                select(Contest)
                .where(Contest.series_id == series_id, Contest.is_series_anchor.is_(False))
                .order_by(Contest.starts_at)
            )
        )
        assert [item.starts_at for item in editions] == [
            datetime(2026, 5, 1, 12, tzinfo=UTC),
            datetime(2027, 5, 1, 12, tzinfo=UTC),
        ]
        assert all(item.ends_at.hour == 18 for item in editions)
        assert all(
            item.log_submission_cutoff_at == datetime(2026 + index, 5, 4, 18, tzinfo=UTC)
            for index, item in enumerate(editions)
        )
        assert len({item.slug for item in editions}) == 2


def test_generation_applies_skip_and_move_exceptions(session_factory):
    with session_factory() as session:
        _, series = create_series(session)
        series_id = series.id
        session.add_all(
            [
                ContestSeriesException(
                    series_id=series_id,
                    occurrence_date=date(2026, 5, 1),
                    action="skip",
                ),
                ContestSeriesException(
                    series_id=series_id,
                    occurrence_date=date(2027, 5, 1),
                    action="move",
                    moved_to_date=date(2027, 5, 8),
                ),
            ]
        )
        session.commit()

    result = generate_due_editions(session_factory, now=datetime(2026, 1, 1, tzinfo=UTC))
    assert result == {"generated": 1, "skipped": 1}
    with session_factory() as session:
        edition = session.scalar(
            select(Contest).where(
                Contest.series_id == series_id,
                Contest.series_occurrence_date == date(2027, 5, 1),
            )
        )
        assert edition is not None
        assert edition.starts_at == datetime(2027, 5, 8, 12, tzinfo=UTC)


def test_generation_materializes_each_selected_month_and_weekday(session_factory):
    with session_factory() as session:
        _, series = create_series(session, window=90)
        series.periodicity = {
            "frequency": "nth_weekday",
            "month": [1, 3],
            "weekday": [0, 4],
            "occurrence": 1,
        }
        session.commit()
        series_id = series.id

    result = generate_due_editions(session_factory, now=datetime(2026, 1, 1, tzinfo=UTC))
    assert result == {"generated": 4, "skipped": 0}
    with session_factory() as session:
        editions = list(
            session.scalars(
                select(Contest)
                .where(Contest.series_id == series_id, Contest.is_series_anchor.is_(False))
                .order_by(Contest.starts_at)
            )
        )
        assert [edition.starts_at for edition in editions] == [
            datetime(2026, 1, 2, 12, tzinfo=UTC),
            datetime(2026, 1, 5, 12, tzinfo=UTC),
            datetime(2026, 3, 2, 12, tzinfo=UTC),
            datetime(2026, 3, 6, 12, tzinfo=UTC),
        ]


def test_manual_series_does_not_generate_editions(session_factory):
    with session_factory() as session:
        _, series = create_series(session, window=None)
        assert series.automatic_window_days is None
    assert generate_due_editions(session_factory, now=datetime(2026, 1, 1, tzinfo=UTC)) == {
        "generated": 0,
        "skipped": 0,
    }


def test_api_startup_runs_series_materialization_and_starts_internal_timer(monkeypatch):
    import backend.app.main as main

    generation_started = asyncio.Event()
    finish_generation = asyncio.Event()

    async def blocked_generation(*_args, **_kwargs):
        generation_started.set()
        await finish_generation.wait()

    startup_generation = AsyncMock(side_effect=blocked_generation)
    startup_migration = Mock()

    async def wait_forever(*_args):
        await asyncio.Future()

    monkeypatch.setattr(
        main,
        "settings",
        SimpleNamespace(
            master_data_scheduler_enabled=False,
            contest_scheduler_enabled=True,
            contest_scheduler_interval_seconds=3600,
        ),
    )
    monkeypatch.setattr(main, "run_edition_generation", startup_generation)
    monkeypatch.setattr(main, "contest_edition_timer", wait_forever)
    monkeypatch.setattr(main, "upgrade_database", startup_migration)
    monkeypatch.setattr(main.engine, "dispose", lambda: None)

    async def exercise_lifespan():
        async with main.lifespan(main.app):
            await asyncio.wait_for(generation_started.wait(), timeout=2)
            startup_generation.assert_awaited_once()
            assert startup_generation.await_args.args[0] is main.SessionFactory
            assert startup_generation.await_args.kwargs == {"trigger": "startup"}
            assert startup_migration.call_count == 1
            finish_generation.set()

    asyncio.run(asyncio.wait_for(exercise_lifespan(), timeout=4))


def test_scheduler_reports_generation_failures_without_raising(monkeypatch, caplog):
    import backend.app.contest_series_scheduler as scheduler

    def fail_generation(*_args, **_kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(scheduler, "generate_due_editions", fail_generation)
    asyncio.run(scheduler.run_edition_generation(Mock(), asyncio.Lock(), trigger="test"))

    assert "contest_edition_generation_failed" in caplog.text
