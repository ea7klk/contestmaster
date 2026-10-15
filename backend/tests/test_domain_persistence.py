from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db import Base, build_engine
from backend.app.models import (
    Contest,
    Entry,
    EntryRevision,
    MasterDataAuthorityRole,
    MasterDataSource,
    MasterDataSyncRun,
    MasterDataVersion,
    MasterDataVersionStatus,
    Participant,
    Qso,
    QsoScore,
    RulesetVersion,
    ScoreRun,
    Station,
    SystemRole,
    SystemUser,
    UTCDateTime,
)
from backend.app.repositories.contests import ContestRepository, EntryRepository


@pytest.fixture
def session():
    engine = build_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db_session:
        yield db_session
    engine.dispose()


def create_guest_entry(session: Session) -> tuple[Contest, Entry, EntryRevision, RulesetVersion]:
    manager = SystemUser(
        username="manager",
        email_normalized="manager@example.test",
        display_name="Contest Manager",
        role=SystemRole.CONTEST_MANAGER,
        password_hash="argon2id-hash",
    )
    ruleset = RulesetVersion(ruleset_key="test-contest", version="1", configuration={"points": 1})
    session.add_all([manager, ruleset])
    session.flush()
    contest = Contest(
        owner_user_id=manager.id,
        ruleset_version_id=ruleset.id,
        name="Test Sprint",
        slug="test-sprint",
        starts_at=datetime(2026, 1, 1, tzinfo=UTC),
        ends_at=datetime(2026, 1, 2, tzinfo=UTC),
        log_submission_cutoff_at=datetime(2026, 1, 3, tzinfo=UTC),
    )
    participant = Participant(display_name="Guest", callsign_submitted="ea7klk/p")
    session.add_all([contest, participant])
    session.flush()
    entry = Entry(
        contest_id=contest.id,
        participant_id=participant.id,
        submitter_user_id=None,
        entry_key="single-op",
    )
    session.add(entry)
    session.flush()
    revision = EntryRevision(
        entry_id=entry.id,
        revision_number=1,
        input_format="cabrillo",
        original_filename="submitted.log",
        storage_key="private/entry-1/rev-1",
        content_sha256="a" * 64,
        byte_size=42,
        submitted_at=datetime(2026, 1, 2, 12, tzinfo=UTC),
    )
    session.add(revision)
    session.flush()
    return contest, entry, revision, ruleset


def test_repositories_persist_guest_entry_and_keep_submitted_values(session: Session) -> None:
    contest, entry, revision, _ = create_guest_entry(session)
    station = Station(
        entry_revision_id=revision.id,
        callsign_submitted="EA7KLK/P",
        callsign_normalized="EA7KLK",
    )
    session.add(station)
    session.flush()
    qso = Qso(
        entry_revision_id=revision.id,
        station_id=station.id,
        occurred_at=datetime(2026, 1, 1, 13, 4, 5, 123456, tzinfo=UTC),
        callsign_submitted="F/ON4XYZ/P",
        callsign_normalized="ON4XYZ",
        exchange_sent_submitted={"serial": "001"},
        exchange_sent_normalized={"serial": 1},
        exchange_received_submitted={"serial": " 007 "},
        exchange_received_normalized={"serial": 7},
    )
    session.add(qso)
    session.commit()

    contests = ContestRepository(session)
    entries = EntryRepository(session)
    assert contests.get(contest.id).slug == "test-sprint"
    assert contests.get_by_slug("TEST-SPRINT").id == contest.id
    assert entries.get(entry.id).submitter_user_id is None
    revisions = entries.list_revisions(entry.id)
    assert [item.revision_number for item in revisions] == [1]
    persisted = session.scalar(select(Qso).where(Qso.id == qso.id))
    assert persisted.callsign_submitted == "F/ON4XYZ/P"
    assert persisted.callsign_normalized == "ON4XYZ"
    assert persisted.exchange_received_submitted == {"serial": " 007 "}
    assert persisted.exchange_received_normalized == {"serial": 7}


def test_utc_datetime_stores_fixed_precision_utc_and_rejects_naive() -> None:
    timestamp = datetime(2026, 5, 1, 14, 30, 1, 123456, tzinfo=timezone(timedelta(hours=2)))
    encoded = UTCDateTime().process_bind_param(timestamp, None)
    assert encoded == "2026-05-01T12:30:01.123456Z"
    assert UTCDateTime().process_result_value(encoded, None) == datetime(
        2026, 5, 1, 12, 30, 1, 123456, tzinfo=UTC
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        UTCDateTime().process_bind_param(datetime(2026, 5, 1), None)


def test_database_rejects_fractional_scores(session: Session) -> None:
    _, entry, revision, ruleset = create_guest_entry(session)
    station = Station(entry_revision_id=revision.id, callsign_submitted="EA7KLK")
    session.add(station)
    session.flush()
    qso = Qso(
        entry_revision_id=revision.id,
        station_id=station.id,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        callsign_submitted="F4ABC",
    )
    source = MasterDataSource(
        source_key="test-source",
        name="Test Source",
        canonical_url="https://example.test/data",
        authority_role=MasterDataAuthorityRole.PRIMARY_OPERATIONAL,
    )
    session.add(source)
    session.flush()
    sync_run = MasterDataSyncRun(source_id=source.id, dataset_key="cty")
    session.add(sync_run)
    session.flush()
    master_data_version = MasterDataVersion(
        sync_run_id=sync_run.id,
        dataset_key="cty",
        retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
        checksum="c" * 64,
        status=MasterDataVersionStatus.ACTIVE,
    )
    session.add(master_data_version)
    session.flush()
    run = ScoreRun(
        entry_id=entry.id,
        entry_revision_id=revision.id,
        ruleset_version_id=ruleset.id,
        master_data_version_id=master_data_version.id,
        run_number=1,
        input_digest="b" * 64,
        ruleset_snapshot={"version": "1"},
        master_data_snapshot={"checksum": "c" * 64},
    )
    session.add_all([qso, run])
    session.flush()
    score = QsoScore(
        score_run_id=run.id,
        qso_id=qso.id,
        entry_revision_id=revision.id,
        credited=True,
        points=1.5,
        explanation="must remain an integer",
    )
    session.add(score)
    with pytest.raises(IntegrityError):
        session.flush()


def test_score_breakdown_must_reference_qso_from_scored_revision(session: Session) -> None:
    _, entry, revision, ruleset = create_guest_entry(session)
    station = Station(entry_revision_id=revision.id, callsign_submitted="EA7KLK")
    session.add(station)
    session.flush()
    qso = Qso(
        entry_revision_id=revision.id,
        station_id=station.id,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        callsign_submitted="F4ABC",
    )
    run = ScoreRun(
        entry_id=entry.id,
        entry_revision_id=revision.id,
        ruleset_version_id=ruleset.id,
        run_number=1,
        input_digest="b" * 64,
        ruleset_snapshot={"version": "1"},
    )
    session.add_all([qso, run])
    session.flush()
    other_revision = EntryRevision(
        entry_id=entry.id,
        revision_number=2,
        input_format="cabrillo",
        storage_key="private/entry-1/rev-2",
        content_sha256="d" * 64,
        byte_size=42,
        submitted_at=datetime(2026, 1, 2, 12, tzinfo=UTC),
    )
    session.add(other_revision)
    session.flush()
    session.add(
        QsoScore(
            score_run_id=run.id,
            qso_id=qso.id,
            entry_revision_id=other_revision.id,
            credited=True,
            points=1,
            explanation="wrong input revision",
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_core_models_have_database_foreign_key_and_integer_score_guards() -> None:
    engine = build_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    assert "entry_revisions" in inspector.get_table_names()
    assert "master_data_versions" in inspector.get_table_names()
    assert inspector.get_foreign_keys("score_runs")
    checks = {item["name"] for item in inspector.get_check_constraints("score_runs")}
    assert "ck_score_runs_score_values_integer_storage" in checks
    engine.dispose()
