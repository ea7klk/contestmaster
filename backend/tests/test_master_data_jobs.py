from __future__ import annotations

import asyncio
import io
import zipfile
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db import Base, build_engine
from backend.app.master_data.cty import parse_archive, parse_cty_dat
from backend.app.master_data.jobs import (
    MissingContestMasterData,
    activate_candidate,
    pin_contest_versions,
    sync_cty,
    sync_m49_country_areas,
    sync_ungegn_countries,
)
from backend.app.master_data.m49 import parse_country_areas
from backend.app.master_data.scheduler import (
    has_all_required_versions,
    run_master_data_sync,
    seconds_until_nightly_run,
)
from backend.app.master_data.ungegn import parse_country_response
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


def test_api_startup_runs_immediate_sync_when_no_active_version(monkeypatch) -> None:
    import backend.app.main as main

    startup_sync = AsyncMock()

    async def wait_forever(*_args):
        await asyncio.Future()

    monkeypatch.setattr(
        main,
        "settings",
        SimpleNamespace(master_data_scheduler_enabled=True, master_data_nightly_hour_utc=2),
    )
    monkeypatch.setattr(main, "has_all_required_versions", lambda _factory: False)
    monkeypatch.setattr(main, "run_master_data_sync", startup_sync)
    monkeypatch.setattr(main, "nightly_master_data_timer", wait_forever)
    monkeypatch.setattr(main.engine, "dispose", lambda: None)

    async def exercise_lifespan() -> None:
        async with main.lifespan(main.app):
            startup_sync.assert_awaited_once()
            assert startup_sync.await_args.args[0] is main.SessionFactory
            assert isinstance(startup_sync.await_args.args[1], asyncio.Lock)

    asyncio.run(exercise_lifespan())


def test_master_data_sync_attempts_each_source_when_one_fails(monkeypatch) -> None:
    import backend.app.master_data.scheduler as scheduler

    calls: list[str] = []

    def broken_cty(_factory):
        calls.append("cty")
        raise ValueError("bad CTY response")

    def successful_ungegn(_factory):
        calls.append("ungegn")
        return {"changed": False}

    def successful_m49(_factory):
        calls.append("m49")
        return {"changed": False}

    monkeypatch.setattr(scheduler, "sync_cty", broken_cty)
    monkeypatch.setattr(scheduler, "sync_ungegn_countries", successful_ungegn)
    monkeypatch.setattr(scheduler, "sync_m49_country_areas", successful_m49)
    asyncio.run(run_master_data_sync(object(), asyncio.Lock()))
    assert calls == ["cty", "ungegn", "m49"]


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


def ungegn_payload(name_suffix: str = "") -> bytes:
    import json

    def alpha_code(index: int, width: int) -> str:
        chars = []
        for _ in range(width):
            chars.append(chr(65 + index % 26))
            index //= 26
        return "".join(reversed(chars))

    return json.dumps(
        [
            {
                "crM49": index,
                "countryName": f"Country {index}{name_suffix}",
                "crIso3": alpha_code(index, 3),
                "crIso2": alpha_code(index, 2),
            }
            for index in range(1, 194)
        ]
    ).encode()


def ungegn_fetcher(name_suffix: str = "", retrieved_at=None):
    payload = ungegn_payload(name_suffix)
    return lambda: parse_country_response(
        payload, retrieved_at or datetime(2026, 9, 15, tzinfo=UTC)
    )


def m49_html(name_suffix: str = "", count: int = 248) -> bytes:
    rows = [
        "<table id='downloadTableEN'><thead>"
        "<tr><th>Country or Area</th><th>M49 Code</th></tr></thead><tbody>"
    ]
    for index in range(count):
        name = "Åland & Islands" if index == 0 else f"Area {index}{name_suffix}"
        rows.append(f"<tr><td>{name}</td><td>{index + 1:03d}</td></tr>")
    rows.append("</tbody></table>")
    return "".join(rows).encode("utf-8")


def m49_fetcher(name_suffix: str = "", retrieved_at=None):
    payload = m49_html(name_suffix)
    return lambda: parse_country_areas(
        payload, retrieved_at or datetime(2026, 9, 15, tzinfo=UTC)
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


def test_ungegn_parser_normalizes_m49_and_rejects_incomplete_or_duplicate_data() -> None:
    data = parse_country_response(ungegn_payload(), datetime(2026, 9, 15, tzinfo=UTC))
    assert len(data.countries) == 193
    assert data.countries[0].m49_code == "001"
    assert data.countries[0].name == "Country 1"
    assert data.normalized_checksum
    import json

    with pytest.raises(ValueError, match="incomplete"):
        parse_country_response(json.dumps([]).encode(), datetime(2026, 9, 15, tzinfo=UTC))
    duplicate = json.loads(ungegn_payload())
    duplicate[-1]["crM49"] = duplicate[0]["crM49"]
    with pytest.raises(ValueError, match="duplicate"):
        parse_country_response(json.dumps(duplicate).encode(), datetime(2026, 9, 15, tzinfo=UTC))


def test_ungegn_sync_is_idempotent_and_stages_country_name_changes(session_factory) -> None:
    first = sync_ungegn_countries(session_factory, ungegn_fetcher())
    no_change = sync_ungegn_countries(session_factory, ungegn_fetcher())
    changed = sync_ungegn_countries(session_factory, ungegn_fetcher(" updated"))

    with session_factory() as session:
        versions = list(
            session.scalars(
                select(MasterDataVersion)
                .where(MasterDataVersion.dataset_key == "countries-ungegn-wgn")
                .order_by(MasterDataVersion.id)
            )
        )
        runs = list(
            session.scalars(
                select(MasterDataSyncRun)
                .where(MasterDataSyncRun.dataset_key == "countries-ungegn-wgn")
                .order_by(MasterDataSyncRun.id)
            )
        )
        entities = list(
            session.scalars(
                select(ContestEntity).where(ContestEntity.version_id == versions[0].id)
            )
        )
        assert len(versions) == 2
        assert versions[0].status == MasterDataVersionStatus.ACTIVE
        assert versions[1].status == MasterDataVersionStatus.CANDIDATE
        assert len(entities) == 193
        assert entities[0].namespace == "UN-M49"
        assert entities[0].authority_code == "001"
        assert runs[1].change_detected is False
        assert len(runs[1].record_counts) == 1
    assert first["changed"] is True
    assert no_change["changed"] is False
    assert no_change["version_id"] == first["version_id"]
    assert changed["changed"] is True


def test_ungegn_failed_import_preserves_active_version(session_factory) -> None:
    first = sync_ungegn_countries(session_factory, ungegn_fetcher())

    def broken_feed():
        raise ValueError("source unavailable")

    with pytest.raises(ValueError, match="source unavailable"):
        sync_ungegn_countries(session_factory, broken_feed)
    with session_factory() as session:
        active = session.scalar(
            select(MasterDataVersion).where(
                MasterDataVersion.dataset_key == "countries-ungegn-wgn",
                MasterDataVersion.status == MasterDataVersionStatus.ACTIVE,
            )
        )
        failed = session.scalar(
            select(MasterDataSyncRun)
            .where(MasterDataSyncRun.dataset_key == "countries-ungegn-wgn")
            .order_by(MasterDataSyncRun.id.desc())
        )
        assert active is not None and active.id == first["version_id"]
        assert failed is not None and failed.status == MasterDataRunStatus.FAILED


def test_startup_required_versions_include_the_full_m49_dataset(session_factory) -> None:
    assert has_all_required_versions(session_factory) is False
    sync_cty(session_factory, fetcher(cty_text()))
    sync_ungegn_countries(session_factory, ungegn_fetcher())
    assert has_all_required_versions(session_factory) is False
    sync_m49_country_areas(session_factory, m49_fetcher())
    assert has_all_required_versions(session_factory) is True


def test_m49_parser_preserves_published_country_area_names_and_codes() -> None:
    data = parse_country_areas(
        m49_html(),
        datetime(2026, 9, 15, tzinfo=UTC),
    )
    assert len(data.country_areas) == 248
    assert data.country_areas[0].m49_code == "001"
    assert data.country_areas[0].name == "Åland & Islands"
    assert data.normalized_checksum
    assert data.response_sha256


def test_m49_parser_rejects_partial_duplicate_and_malformed_tables() -> None:
    moment = datetime(2026, 9, 15, tzinfo=UTC)
    with pytest.raises(ValueError, match="incomplete"):
        parse_country_areas(m49_html(count=239), moment)

    duplicate = m49_html().replace(b"<td>002</td>", b"<td>001</td>", 1)
    with pytest.raises(ValueError, match="duplicate"):
        parse_country_areas(duplicate, moment)

    malformed = m49_html().replace(b"<td>001</td>", b"<td>1A1</td>", 1)
    with pytest.raises(ValueError, match="invalid name or code"):
        parse_country_areas(malformed, moment)


def test_m49_sync_is_idempotent_and_stages_published_name_changes(session_factory) -> None:
    first = sync_m49_country_areas(session_factory, m49_fetcher())
    no_change = sync_m49_country_areas(session_factory, m49_fetcher())
    changed = sync_m49_country_areas(session_factory, m49_fetcher(" revised"))

    with session_factory() as session:
        versions = list(
            session.scalars(
                select(MasterDataVersion)
                .where(MasterDataVersion.dataset_key == "countries-unsd-m49")
                .order_by(MasterDataVersion.id)
            )
        )
        runs = list(
            session.scalars(
                select(MasterDataSyncRun)
                .where(MasterDataSyncRun.dataset_key == "countries-unsd-m49")
                .order_by(MasterDataSyncRun.id)
            )
        )
        entities = list(
            session.scalars(
                select(ContestEntity).where(ContestEntity.version_id == versions[0].id)
            )
        )
        assert len(versions) == 2
        assert versions[0].status == MasterDataVersionStatus.ACTIVE
        assert versions[1].status == MasterDataVersionStatus.CANDIDATE
        assert len(entities) == 248
        assert entities[0].namespace == "UN-M49"
        assert entities[0].authority_code == "001"
        assert entities[0].name == "Åland & Islands"
        assert runs[1].change_detected is False
        assert runs[1].record_counts == {"country_areas": 248}
        source = session.scalar(
            select(MasterDataSource).where(
                MasterDataSource.source_key == "unsd-m49-country-areas"
            )
        )
        assert source is not None
        assert source.enabled is True
        assert source.use_terms_url == "https://www.un.org/en/about-us/terms-of-use"
    assert first["changed"] is True
    assert no_change["changed"] is False
    assert no_change["version_id"] == first["version_id"]
    assert changed["changed"] is True


def test_m49_failed_import_preserves_active_version(session_factory) -> None:
    first = sync_m49_country_areas(session_factory, m49_fetcher())

    def broken_feed():
        raise ValueError("source unavailable")

    with pytest.raises(ValueError, match="source unavailable"):
        sync_m49_country_areas(session_factory, broken_feed)
    with session_factory() as session:
        active = session.scalar(
            select(MasterDataVersion).where(
                MasterDataVersion.dataset_key == "countries-unsd-m49",
                MasterDataVersion.status == MasterDataVersionStatus.ACTIVE,
            )
        )
        failed = session.scalar(
            select(MasterDataSyncRun)
            .where(MasterDataSyncRun.dataset_key == "countries-unsd-m49")
            .order_by(MasterDataSyncRun.id.desc())
        )
        assert active is not None and active.id == first["version_id"]
        assert failed is not None and failed.status == MasterDataRunStatus.FAILED


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
    assert has_all_required_versions(session_factory) is False
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
