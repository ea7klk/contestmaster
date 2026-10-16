from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.auth import hash_password
from backend.app.db import Base, get_session
from backend.app.main import app
from backend.app.models import (
    AdminNote,
    AuditEvent,
    Contest,
    ContestStatus,
    Entry,
    EntryAccessGrant,
    EntryRevision,
    EntryStatus,
    LogSubmissionRequest,
    Participant,
    Qso,
    QsoDecision,
    QsoScore,
    ResultPublication,
    ResultPublicationEntry,
    RulesetActivation,
    RulesetVersion,
    ScoreRun,
    Station,
    SystemRole,
    SystemUser,
)


@pytest.fixture
def deletion_database(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(
        "backend.app.api.auth.get_settings",
        lambda: type("Settings", (), {"secure_cookies": False})(),
    )

    def override_session():
        yield from _session_generator(factory)

    app.dependency_overrides[get_session] = override_session
    try:
        yield factory
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _session_generator(factory):
    with factory() as session:
        yield session


@pytest.fixture
def deletion_fixture(deletion_database):
    now = datetime.now(UTC)
    with deletion_database.begin() as session:
        manager = SystemUser(
            username="manager",
            email_normalized="manager@example.test",
            display_name="Contest Manager",
            role=SystemRole.CONTEST_MANAGER,
            password_hash=hash_password("Correct horse battery staple"),
        )
        outsider = SystemUser(
            username="outsider",
            email_normalized="outsider@example.test",
            display_name="Other Manager",
            role=SystemRole.CONTEST_MANAGER,
            password_hash=hash_password("Correct horse battery staple"),
        )
        session.add_all([manager, outsider])
        session.flush()
        ruleset = RulesetVersion(
            ruleset_key="delete-test",
            version="1",
            rule_type_keys=[],
            configuration={
                "schema_version": 2,
                "ruleset_key": "delete-test",
                "version": "1",
                "rules": [],
            },
            created_by_user_id=manager.id,
        )
        session.add(ruleset)
        session.flush()
        contest = Contest(
            owner_user_id=manager.id,
            ruleset_version_id=ruleset.id,
            name="Delete Test Contest",
            slug="delete-test-contest",
            starts_at=now,
            ends_at=now + timedelta(hours=2),
            log_submission_cutoff_at=now + timedelta(days=1),
            status=ContestStatus.CLOSED,
        )
        other_contest = Contest(
            owner_user_id=manager.id,
            name="Keep Test Contest",
            slug="keep-test-contest",
            starts_at=now,
            ends_at=now + timedelta(hours=2),
            log_submission_cutoff_at=now + timedelta(days=1),
            status=ContestStatus.DRAFT,
        )
        participant = Participant(callsign_submitted="N0TEST", callsign_normalized="N0TEST")
        session.add_all([contest, other_contest, participant])
        session.flush()
        entry = Entry(
            contest_id=contest.id,
            participant_id=participant.id,
            entry_key="N0TEST",
            status=EntryStatus.ACCEPTED,
        )
        other_entry = Entry(
            contest_id=other_contest.id,
            participant_id=participant.id,
            entry_key="N0TEST",
        )
        session.add_all([entry, other_entry])
        session.flush()
        revision = EntryRevision(
            entry_id=entry.id,
            revision_number=1,
            input_format="cabrillo",
            storage_key="database://test/entry",
            original_content="START-OF-LOG\nEND-OF-LOG",
            import_metadata={},
            content_sha256=sha256(b"test-log").hexdigest(),
            byte_size=23,
            submitted_at=now,
        )
        session.add(revision)
        session.flush()
        station = Station(entry_revision_id=revision.id, callsign_submitted="N0TEST")
        session.add(station)
        session.flush()
        qso = Qso(
            entry_revision_id=revision.id,
            station_id=station.id,
            occurred_at=now + timedelta(minutes=1),
            callsign_submitted="K1TEST",
            exchange_sent_submitted={},
            exchange_received_submitted={},
        )
        session.add(qso)
        session.flush()
        decision = QsoDecision(
            qso_id=qso.id,
            status="credited",
            source="automated",
            reason_code="valid",
            reason="Valid contact",
        )
        session.add(decision)
        session.add(
            EntryAccessGrant(
                entry_id=entry.id,
                token_hash="a" * 64,
            )
        )
        session.add(
            LogSubmissionRequest(
                contest_id=contest.id,
                key_sha256="b" * 64,
                content_sha256="c" * 64,
                entry_id=entry.id,
            )
        )
        session.add(AdminNote(contest_id=contest.id, entry_id=entry.id, body="Private review note"))
        activation = RulesetActivation(
            contest_id=contest.id,
            ruleset_version_id=ruleset.id,
            configuration_sha256="d" * 64,
        )
        session.add(activation)
        session.flush()
        score_run = ScoreRun(
            entry_id=entry.id,
            entry_revision_id=revision.id,
            ruleset_version_id=ruleset.id,
            run_number=1,
            input_digest="e" * 64,
        )
        session.add(score_run)
        session.flush()
        session.add(
            QsoScore(
                score_run_id=score_run.id,
                qso_id=qso.id,
                entry_revision_id=revision.id,
                credited=True,
                explanation="Contact credited",
            )
        )
        publication = ResultPublication(
            contest_id=contest.id,
            publication_number=1,
            source_digest="f" * 64,
            entry_count=1,
            withheld_count=0,
        )
        session.add(publication)
        session.flush()
        session.add(
            ResultPublicationEntry(
                publication_id=publication.id,
                entry_id=entry.id,
                score_run_id=score_run.id,
                callsign="N0TEST",
                status="accepted",
                score=1,
                points=1,
                multiplier_count=0,
                bonus_points=0,
                penalty_points=0,
                qso_count=1,
                credited_qso_count=1,
            )
        )
        return {
            "manager_id": manager.id,
            "outsider_id": outsider.id,
            "contest_id": contest.id,
            "contest_slug": contest.slug,
            "keep_contest_id": other_contest.id,
            "participant_id": participant.id,
            "ruleset_id": ruleset.id,
        }


def login(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Correct horse battery staple"},
    )
    assert response.status_code == 200


def test_contest_delete_removes_dependent_logs_results_and_keeps_shared_participant(
    deletion_database, deletion_fixture
):
    client = TestClient(app)
    login(client, "manager@example.test")
    csrf = client.cookies.get("contestmaster_csrf")
    path = f"/api/v1/contests/{deletion_fixture['contest_id']}"

    mismatch = client.request(
        "DELETE", path, json={"confirm_slug": "wrong"}, headers={"X-CSRF-Token": csrf}
    )
    assert mismatch.status_code == 422
    response = client.request(
        "DELETE",
        path,
        json={"confirm_slug": deletion_fixture["contest_slug"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 204

    with deletion_database() as session:
        assert session.get(Contest, deletion_fixture["contest_id"]) is None
        assert session.get(Contest, deletion_fixture["keep_contest_id"]) is not None
        assert session.get(Participant, deletion_fixture["participant_id"]) is not None
        assert session.scalar(select(func.count()).select_from(Entry)) == 1
        assert (
            session.scalar(
                select(Entry).where(Entry.contest_id == deletion_fixture["keep_contest_id"])
            )
            is not None
        )
        for model in (
            EntryRevision,
            EntryAccessGrant,
            LogSubmissionRequest,
            Station,
            Qso,
            QsoDecision,
            QsoScore,
            ScoreRun,
            ResultPublication,
            ResultPublicationEntry,
            AdminNote,
            RulesetActivation,
        ):
            assert session.scalar(select(func.count()).select_from(model)) == 0
        event = session.scalar(
            select(AuditEvent).where(
                AuditEvent.action == "contest.deleted",
                AuditEvent.target_id == str(deletion_fixture["contest_id"]),
            )
        )
        assert event is not None
        assert event.event_metadata["entries"] == 1
        # Ruleset assignment history and score runs are gone, so the version is now deletable.
        assert session.get(RulesetVersion, deletion_fixture["ruleset_id"]) is not None

    delete_ruleset = client.request(
        "DELETE",
        f"/api/v1/rulesets/versions/{deletion_fixture['ruleset_id']}",
        json={"confirm_identity": "delete-test@1"},
        headers={"X-CSRF-Token": csrf},
    )
    assert delete_ruleset.status_code == 204


def test_contest_delete_is_owner_scoped_and_ruleset_in_use_is_protected(
    deletion_database, deletion_fixture
):
    client = TestClient(app)
    login(client, "outsider@example.test")
    csrf = client.cookies.get("contestmaster_csrf")
    path = f"/api/v1/contests/{deletion_fixture['contest_id']}"
    denied = client.request(
        "DELETE",
        path,
        json={"confirm_slug": deletion_fixture["contest_slug"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert denied.status_code == 404

    client = TestClient(app)
    login(client, "manager@example.test")
    csrf = client.cookies.get("contestmaster_csrf")
    protected = client.request(
        "DELETE",
        f"/api/v1/rulesets/versions/{deletion_fixture['ruleset_id']}",
        json={"confirm_identity": "delete-test@1"},
        headers={"X-CSRF-Token": csrf},
    )
    assert protected.status_code == 409
    assert "referenced" in protected.json()["error"]["message"]


def test_contest_delete_conflict_rolls_back_all_changes(deletion_database, deletion_fixture):
    now = datetime.now(UTC)
    with deletion_database.begin() as session:
        kept_entry = session.scalar(
            select(Entry).where(Entry.contest_id == deletion_fixture["keep_contest_id"])
        )
        original_decision = session.scalar(select(QsoDecision))
        revision = EntryRevision(
            entry_id=kept_entry.id,
            revision_number=1,
            input_format="cabrillo",
            storage_key="database://test/other-entry",
            original_content="START-OF-LOG\nEND-OF-LOG",
            import_metadata={},
            content_sha256=sha256(b"other-log").hexdigest(),
            byte_size=23,
            submitted_at=now,
        )
        session.add(revision)
        session.flush()
        station = Station(entry_revision_id=revision.id, callsign_submitted="N0TEST")
        session.add(station)
        session.flush()
        qso = Qso(
            entry_revision_id=revision.id,
            station_id=station.id,
            occurred_at=now + timedelta(minutes=1),
            callsign_submitted="K2TEST",
            exchange_sent_submitted={},
            exchange_received_submitted={},
        )
        session.add(qso)
        session.flush()
        session.add(
            QsoDecision(
                qso_id=qso.id,
                status="needs_review",
                source="automated",
                reason_code="related",
                reason="This unrelated QSO incorrectly references another contest's decision.",
                supersedes_decision_id=original_decision.id,
            )
        )

    client = TestClient(app)
    login(client, "manager@example.test")
    response = client.request(
        "DELETE",
        f"/api/v1/contests/{deletion_fixture['contest_id']}",
        json={"confirm_slug": deletion_fixture["contest_slug"]},
        headers={"X-CSRF-Token": client.cookies.get("contestmaster_csrf")},
    )

    assert response.status_code == 409
    with deletion_database() as session:
        assert session.get(Contest, deletion_fixture["contest_id"]) is not None
        assert session.scalar(select(func.count()).select_from(Entry)) == 2
        assert (
            session.scalar(select(func.count()).where(AuditEvent.action == "contest.deleted")) == 0
        )
