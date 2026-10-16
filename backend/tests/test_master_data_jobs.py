from __future__ import annotations

import asyncio
import io
import zipfile
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db import Base, build_engine
from backend.app.master_data.cty import _read_url, parse_archive, parse_cty_dat
from backend.app.master_data.jobs import (
    MissingContestMasterData,
    activate_candidate,
    pin_contest_versions,
    sync_cty,
)
from backend.app.master_data.scheduler import (
    has_all_required_versions,
    run_master_data_sync,
    seconds_until_nightly_run,
)
from backend.app.models import (
    CallsignPrefix,
    Contest,
    ContestEntity,
    MasterDataAuthorityRole,
    MasterDataRunStatus,
    MasterDataSource,
    MasterDataSyncRun,
    MasterDataVersion,
    MasterDataVersionStatus,
    SystemRole,
    SystemUser,
)


def test_api_startup_schedules_immediate_sync_without_waiting(monkeypatch) -> None:
    import backend.app.main as main

    sync_started = asyncio.Event()
    finish_sync = asyncio.Event()

    async def blocked_sync(*_args, **_kwargs) -> None:
        sync_started.set()
        await finish_sync.wait()

    startup_sync = AsyncMock(side_effect=blocked_sync)
    startup_migration = Mock()

    async def wait_forever(*_args):
        await asyncio.Future()

    monkeypatch.setattr(
        main,
        "settings",
        SimpleNamespace(
            master_data_scheduler_enabled=True,
            master_data_nightly_hour_utc=2,
            contest_scheduler_enabled=False,
            contest_scheduler_interval_seconds=3600,
        ),
    )
    monkeypatch.setattr(main, "has_all_required_versions", lambda _factory: False)
    monkeypatch.setattr(main, "run_master_data_sync", startup_sync)
    monkeypatch.setattr(main, "nightly_master_data_timer", wait_forever)
    monkeypatch.setattr(main, "upgrade_database", startup_migration)
    monkeypatch.setattr(main.engine, "dispose", lambda: None)

    async def exercise_lifespan() -> None:
        async with main.lifespan(main.app):
            try:
                startup_migration.assert_called_once_with()
                await asyncio.wait_for(sync_started.wait(), timeout=2)
                startup_sync.assert_awaited_once()
                assert startup_sync.await_args.args[0] is main.SessionFactory
                assert isinstance(startup_sync.await_args.args[1], asyncio.Lock)
                assert startup_sync.await_args.kwargs == {"trigger": "startup"}
                assert not finish_sync.is_set()
            finally:
                finish_sync.set()

    asyncio.run(asyncio.wait_for(exercise_lifespan(), timeout=4))


def test_api_startup_skips_master_data_scheduler_when_disabled(monkeypatch) -> None:
    import backend.app.main as main

    startup_sync = AsyncMock()
    startup_migration = Mock()

    monkeypatch.setattr(
        main,
        "settings",
        SimpleNamespace(
            master_data_scheduler_enabled=False,
            master_data_nightly_hour_utc=2,
            contest_scheduler_enabled=False,
            contest_scheduler_interval_seconds=3600,
        ),
    )
    monkeypatch.setattr(main, "run_master_data_sync", startup_sync)
    monkeypatch.setattr(main, "upgrade_database", startup_migration)
    monkeypatch.setattr(main.engine, "dispose", lambda: None)

    async def exercise_lifespan() -> None:
        async with main.lifespan(main.app):
            startup_migration.assert_called_once_with()
            startup_sync.assert_not_awaited()

    asyncio.run(exercise_lifespan())


def test_cty_source_download_logs_start_completion_and_failure(monkeypatch, caplog) -> None:
    import backend.app.master_data.cty as cty

    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.return_value = b"feed"
    monkeypatch.setattr(cty.urllib.request, "urlopen", Mock(return_value=response))

    with caplog.at_level("INFO", logger="contestmaster.master_data.cty"):
        assert _read_url("https://example.test/feed") == b"feed"

    records = [
        record for record in caplog.records if record.name == "contestmaster.master_data.cty"
    ]
    assert [record.getMessage() for record in records] == [
        "master_data_source_request_started",
        "master_data_source_request_finished",
    ]
    assert records[0].source_url == "https://example.test/feed"
    assert records[1].response_bytes == 4
    assert records[1].duration_ms >= 0

    caplog.clear()
    monkeypatch.setattr(cty.urllib.request, "urlopen", Mock(side_effect=TimeoutError))
    with caplog.at_level("INFO", logger="contestmaster.master_data.cty"):
        with pytest.raises(TimeoutError):
            _read_url("https://example.test/feed")
    assert [record.getMessage() for record in caplog.records] == [
        "master_data_source_request_started",
        "master_data_source_request_failed",
    ]


def test_master_data_sync_attempts_only_cty(monkeypatch) -> None:
    import backend.app.master_data.scheduler as scheduler

    calls: list[str] = []

    def successful_cty(_factory):
        calls.append("cty")
        return {"changed": False}

    monkeypatch.setattr(scheduler, "sync_cty", successful_cty)
    asyncio.run(run_master_data_sync(object(), asyncio.Lock()))
    assert calls == ["cty"]


@pytest.fixture
def session_factory():
    engine = build_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    yield factory
    engine.dispose()


def cty_text(*, changed_first_zone: int | None = None, spaced: bool = False) -> str:
    rows = []
    for index in range(101):
        prefix = f"A{index:02d}"
        zone = changed_first_zone if index == 0 and changed_first_zone else 1
        sep = " : " if spaced else ": "
        rows.extend(
            [
                f"Test Entity {index}{sep}{zone}{sep}1{sep}EU{sep}0{sep}0{sep}0{sep}{prefix}:",
                f"  {prefix},={prefix}ABC;",
            ]
        )
    return "\n".join(rows)


def archive_bytes(data: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("cty.dat", data)
        archive.writestr(
            "copyright.txt",
            "Permission is hereby granted to use, copy, modify, publish, and distribute this data.",
        )
    return buffer.getvalue()


def fetcher(data: str):
    return lambda: (
        archive_bytes(data),
        "2026-09-15",
        "https://www.country-files.com/bigcty/download/2026/bigcty-20260915.zip",
        datetime(2026, 9, 15, tzinfo=UTC),
    )


def test_cty_parser_handles_prefix_overrides_exact_calls_and_continuations() -> None:
    parsed = parse_cty_dat("Example: 5: 8: EU: 40: -3: -1: EA:\n EA,EA2(6)[9],=EA7ABC;\n")
    assert parsed[0].name == "Example"
    assert parsed[0].primary_prefix == "EA"
    assert [(p.pattern, p.exact_callsign, p.cq_zone, p.itu_zone) for p in parsed[0].prefixes] == [
        ("EA", False, 5, 8),
        ("EA2", False, 6, 9),
        ("EA7ABC", True, 5, 8),
    ]


def test_cty_parser_preserves_exact_call_override_and_first_duplicate_assignment() -> None:
    parsed = parse_cty_dat(
        "First: 5: 8: EU: 40: -3: -1: EA:\n EA;\nSecond: 6: 9: EU: 41: -4: -1: EB:\n EA,=EA,EB;\n"
    )
    assert [(p.pattern, p.exact_callsign) for p in parsed[0].prefixes] == [("EA", False)]
    assert [(p.pattern, p.exact_callsign) for p in parsed[1].prefixes] == [
        ("EA", True),
        ("EB", False),
    ]


def test_cty_parser_rejects_incomplete_record_and_invalid_zone() -> None:
    with pytest.raises(ValueError, match="terminator"):
        parse_cty_dat("Example: 5: 8: EU: 40: -3: -1: EA:\n EA")
    with pytest.raises(ValueError, match="header"):
        parse_cty_dat("Example: 41: 8: EU: 40: -3: -1: EA:\n EA;")


def test_archive_requires_copyright_notice_and_known_minimum_completeness() -> None:
    payload = archive_bytes("One: 5: 8: EU: 40: -3: -1: EA:\n EA;\n")
    with pytest.raises(ValueError, match="incomplete"):
        parse_archive(
            payload,
            "2026-09-15",
            "https://example.test/file.zip",
            datetime(2026, 9, 15, tzinfo=UTC),
        )


def test_cty_is_the_only_required_master_data_dataset(session_factory) -> None:
    assert has_all_required_versions(session_factory) is False
    result = sync_cty(session_factory, fetcher(cty_text()))
    assert result["changed"] is True
    assert has_all_required_versions(session_factory) is True

    with session_factory() as session:
        versions = list(session.scalars(select(MasterDataVersion)))
        sources = list(session.scalars(select(MasterDataSource)))
        assert [version.dataset_key for version in versions] == ["cty"]
        assert [source.source_key for source in sources] == ["big-cty"]


def test_nightly_timer_calculates_next_utc_run_and_requires_aware_time() -> None:
    before = datetime(2026, 9, 15, 1, 30, tzinfo=UTC)
    after = datetime(2026, 9, 15, 2, 30, tzinfo=UTC)
    assert seconds_until_nightly_run(before, 2) == 1800
    assert seconds_until_nightly_run(after, 2) == 23 * 3600 + 30 * 60
    with pytest.raises(ValueError, match="timezone-aware"):
        seconds_until_nightly_run(datetime(2026, 9, 15, 1, 30), 2)


def test_sync_is_idempotent_for_identical_normalized_content(session_factory) -> None:
    assert has_all_required_versions(session_factory) is False
    first = sync_cty(session_factory, fetcher(cty_text()))
    assert has_all_required_versions(session_factory) is True
    second = sync_cty(session_factory, fetcher(cty_text(spaced=True)))

    with session_factory() as session:
        assert session.scalar(select(func.count(MasterDataVersion.id))) == 1
        assert session.scalar(select(func.count(MasterDataSyncRun.id))) == 2
        run = session.scalar(select(MasterDataSyncRun).order_by(MasterDataSyncRun.id.desc()))
        assert run is not None
        assert run.status == MasterDataRunStatus.SUCCEEDED
        assert run.change_detected is False
        assert (
            run.source_url
            == "https://www.country-files.com/bigcty/download/2026/bigcty-20260915.zip"
        )
    assert first["changed"] is True
    assert second["changed"] is False
    assert second["version_id"] == first["version_id"]


def test_zone_boundary_change_is_staged_without_replacing_active(session_factory) -> None:
    first = sync_cty(session_factory, fetcher(cty_text()))
    changed = sync_cty(session_factory, fetcher(cty_text(changed_first_zone=2)))
    retry = sync_cty(session_factory, fetcher(cty_text(changed_first_zone=2)))

    with session_factory() as session:
        versions = list(session.scalars(select(MasterDataVersion).order_by(MasterDataVersion.id)))
        assert len(versions) == 2
        assert versions[0].id == first["version_id"]
        assert versions[0].status == MasterDataVersionStatus.ACTIVE
        assert versions[1].id == changed["version_id"]
        assert versions[1].status == MasterDataVersionStatus.CANDIDATE
        assert versions[0].valid_to is None
        assert session.scalar(select(func.count(ContestEntity.id))) == 202
        assert session.scalar(select(func.count(CallsignPrefix.id))) == 404
        assert retry["changed"] is False
        assert retry["version_id"] == changed["version_id"]
        activation = datetime(2026, 9, 16, tzinfo=UTC)
        promoted = activate_candidate(session, versions[1].id, activation)
        session.flush()
        assert promoted.status == MasterDataVersionStatus.ACTIVE
        assert promoted.valid_from == activation
        assert versions[0].valid_to == activation


def test_safe_content_change_closes_old_interval_and_activates_new_version(session_factory) -> None:
    original = cty_text()
    extended = original.replace("A00,=A00ABC;", "A00,=A00ABC,ZZZ;")
    first = sync_cty(session_factory, fetcher(original))
    retrieved = datetime(2026, 9, 16, tzinfo=UTC)
    changed = sync_cty(
        session_factory,
        lambda: (
            archive_bytes(extended),
            "2026-09-16",
            "https://www.country-files.com/bigcty/download/2026/bigcty-20260916.zip",
            retrieved,
        ),
    )

    with session_factory() as session:
        versions = list(session.scalars(select(MasterDataVersion).order_by(MasterDataVersion.id)))
        assert len(versions) == 2
        assert versions[0].id == first["version_id"]
        assert versions[0].status == MasterDataVersionStatus.RETIRED
        assert versions[0].valid_to == retrieved
        assert versions[1].id == changed["version_id"]
        assert versions[1].status == MasterDataVersionStatus.ACTIVE
        assert versions[1].valid_from == retrieved


def test_failed_import_keeps_last_good_version_and_records_failure(session_factory) -> None:
    good = sync_cty(session_factory, fetcher(cty_text()))
    with pytest.raises(ValueError, match="valid ZIP"):
        sync_cty(
            session_factory, lambda: (b"bad zip", "2026-09-16", "https://x", datetime.now(UTC))
        )

    with session_factory() as session:
        current = session.scalar(
            select(MasterDataVersion).where(
                MasterDataVersion.status == MasterDataVersionStatus.ACTIVE
            )
        )
        failed = session.scalar(select(MasterDataSyncRun).order_by(MasterDataSyncRun.id.desc()))
        assert current is not None and current.id == good["version_id"]
        assert failed is not None and failed.status == MasterDataRunStatus.FAILED


def test_contest_pins_the_single_version_valid_at_start_and_blocks_missing() -> None:
    engine = build_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        admin = SystemUser(
            username="admin",
            email_normalized="admin@example.test",
            display_name="Admin",
            role=SystemRole.GLOBAL_ADMINISTRATOR,
            password_hash="hash",
        )
        source = MasterDataSource(
            source_key="seed",
            name="Seed",
            canonical_url="https://example.test",
            authority_role=MasterDataAuthorityRole.GAP_FILLING,
        )
        session.add_all([admin, source])
        session.flush()
        run = MasterDataSyncRun(source_id=source.id, dataset_key="cty")
        session.add(run)
        session.flush()
        run.status = MasterDataRunStatus.SUCCEEDED
        starts = datetime(2026, 9, 15, tzinfo=UTC)
        earlier_run = MasterDataSyncRun(source_id=source.id, dataset_key="cty")
        session.add(earlier_run)
        session.flush()
        session.add(
            MasterDataVersion(
                sync_run_id=earlier_run.id,
                dataset_key="cty",
                checksum="b" * 64,
                retrieved_at=starts - timedelta(days=3),
                valid_from=starts - timedelta(days=2),
                valid_to=starts,
                status=MasterDataVersionStatus.RETIRED,
            )
        )
        version = MasterDataVersion(
            sync_run_id=run.id,
            dataset_key="cty",
            checksum="a" * 64,
            retrieved_at=starts,
            valid_from=starts,
            status=MasterDataVersionStatus.ACTIVE,
        )
        session.add(version)
        session.flush()
        contest = Contest(
            owner_user_id=admin.id,
            name="Test",
            slug="test",
            starts_at=starts,
            ends_at=starts + timedelta(hours=1),
            log_submission_cutoff_at=starts + timedelta(days=2),
        )
        session.add(contest)
        session.flush()

        with pytest.raises(MissingContestMasterData, match="other-dataset"):
            pin_contest_versions(session, contest.id, ["other-dataset"], now=starts)
        pins = pin_contest_versions(session, contest.id, ["cty"], now=starts)
        assert len(pins) == 1
        assert pins[0].master_data_version_id == version.id
        assert pins[0].dataset_key == "cty"
        assert pin_contest_versions(session, contest.id, ["cty"], now=starts) == pins
    engine.dispose()
