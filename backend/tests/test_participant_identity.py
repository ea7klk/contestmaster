from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api import participant_identity
from backend.app.db import Base, get_session
from backend.app.main import app
from backend.app.models import (
    Contest,
    Entry,
    Participant,
    ParticipantEmail,
    ParticipantMagicLink,
    ParticipantSession,
)


@pytest.fixture
def participant_database(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    monkeypatch.setattr(
        "backend.app.api.participant_identity.get_settings",
        lambda: type(
            "Settings",
            (),
            {"secure_cookies": False, "frontend_base_url": "http://localhost:5173"},
        )(),
    )
    try:
        yield factory
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_magic_link_verifies_email_and_scopes_session_to_participant_entries(
    participant_database, monkeypatch
):
    delivered: list[tuple[str, str]] = []
    monkeypatch.setattr(
        participant_identity,
        "send_participant_magic_link",
        lambda email, link: delivered.append((email, link)),
    )
    with participant_database.begin() as session:
        participant = Participant(display_name="Radio Pilot", callsign_submitted="EA7KLK")
        other_participant = Participant(display_name="Other Pilot")
        session.add_all([participant, other_participant])
        session.flush()
        first_contest = Contest(
            owner_user_id=1,
            name="First",
            slug="first",
            starts_at=datetime(2026, 1, 1, tzinfo=UTC),
            ends_at=datetime(2026, 1, 1, 2, tzinfo=UTC),
            log_submission_cutoff_at=datetime(2026, 1, 2, tzinfo=UTC),
        )
        # Contest ownership is a system-account FK, so create the minimum owner.
        from backend.app.models import SystemRole, SystemUser

        owner = SystemUser(
            username="owner",
            email_normalized="owner@example.test",
            display_name="Owner",
            role=SystemRole.CONTEST_MANAGER,
            password_hash="unused-test-hash",
        )
        session.add(owner)
        session.flush()
        first_contest.owner_user_id = owner.id
        second_contest = Contest(
            owner_user_id=owner.id,
            name="Second",
            slug="second",
            starts_at=datetime(2026, 2, 1, tzinfo=UTC),
            ends_at=datetime(2026, 2, 1, 2, tzinfo=UTC),
            log_submission_cutoff_at=datetime(2026, 2, 2, tzinfo=UTC),
        )
        session.add_all([first_contest, second_contest])
        session.flush()
        email = ParticipantEmail(
            participant_id=participant.id, email_normalized="pilot@example.test"
        )
        session.add(email)
        session.add_all(
            [
                Entry(
                    contest_id=first_contest.id,
                    participant_id=participant.id,
                    entry_key="pilot",
                ),
                Entry(
                    contest_id=second_contest.id,
                    participant_id=other_participant.id,
                    entry_key="other",
                ),
            ]
        )
        session.flush()
        participant_id = participant.id

    client = TestClient(app)
    requested = client.post(
        "/api/v1/participants/auth/request-link", json={"email": "PILOT@example.test"}
    )
    assert requested.status_code == 202
    assert requested.json()["status"] == "accepted"
    assert delivered[0][0] == "pilot@example.test"
    raw_token = parse_qs(urlparse(delivered[0][1]).query)["token"][0]
    with participant_database() as session:
        link = session.query(ParticipantMagicLink).one()
        assert link.token_hash != raw_token
        assert session.get(ParticipantEmail, link.participant_email_id).verified_at is None

    consumed = client.post(
        "/api/v1/participants/auth/consume-link", json={"token": raw_token}
    )
    assert consumed.status_code == 200
    assert consumed.json()["participant"]["id"] == participant_id
    assert "httponly" in next(
        cookie
        for cookie in consumed.headers.get_list("set-cookie")
        if cookie.startswith("contestmaster_participant_session=")
    ).lower()
    assert client.get("/api/v1/participants/auth/me").json()["email"] == "pilot@example.test"
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/contests").status_code == 401
    entries = client.get("/api/v1/participants/auth/entries")
    assert [entry["entry_key"] for entry in entries.json()["items"]] == ["pilot"]
    assert "global_administrator" not in consumed.text
    assert "contest_manager" not in consumed.text
    with participant_database() as session:
        assert session.query(ParticipantEmail).one().verified_at is not None
        assert session.query(ParticipantSession).count() == 1

    reused = client.post(
        "/api/v1/participants/auth/consume-link", json={"token": raw_token}
    )
    assert reused.status_code == 401
    no_csrf = client.post("/api/v1/participants/auth/logout")
    assert no_csrf.status_code == 403
    csrf = client.cookies.get("contestmaster_participant_csrf")
    assert client.post(
        "/api/v1/participants/auth/logout", headers={"X-CSRF-Token": csrf}
    ).status_code == 200
    assert client.get("/api/v1/participants/auth/me").status_code == 401


def test_expired_magic_link_is_rejected_and_delivery_failure_rolls_back(
    participant_database, monkeypatch
):
    delivered: list[tuple[str, str]] = []
    monkeypatch.setattr(
        participant_identity,
        "send_participant_magic_link",
        lambda email, link: delivered.append((email, link)),
    )
    client = TestClient(app)
    assert (
        client.post(
            "/api/v1/participants/auth/request-link", json={"email": "expired@example.test"}
        ).status_code
        == 202
    )
    raw_token = parse_qs(urlparse(delivered[0][1]).query)["token"][0]
    with participant_database.begin() as session:
        link = session.query(ParticipantMagicLink).one()
        link.created_at = datetime.now(UTC) - timedelta(minutes=3)
        link.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    assert (
        client.post(
            "/api/v1/participants/auth/consume-link", json={"token": raw_token}
        ).status_code
        == 401
    )

    monkeypatch.setattr(
        participant_identity,
        "send_participant_magic_link",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("smtp unavailable")),
    )
    failed = client.post(
        "/api/v1/participants/auth/request-link", json={"email": "rollback@example.test"}
    )
    assert failed.status_code == 503
    with participant_database() as session:
        assert session.query(ParticipantEmail).filter_by(
            email_normalized="rollback@example.test"
        ).count() == 0


def test_magic_link_request_invalidates_an_older_unconsumed_link(
    participant_database, monkeypatch
):
    delivered: list[tuple[str, str]] = []
    monkeypatch.setattr(
        participant_identity,
        "send_participant_magic_link",
        lambda email, link: delivered.append((email, link)),
    )
    client = TestClient(app)
    for _ in range(2):
        assert (
            client.post(
                "/api/v1/participants/auth/request-link", json={"email": "rotate@example.test"}
            ).status_code
            == 202
        )
    first_token = parse_qs(urlparse(delivered[0][1]).query)["token"][0]
    second_token = parse_qs(urlparse(delivered[1][1]).query)["token"][0]
    assert client.post(
        "/api/v1/participants/auth/consume-link", json={"token": first_token}
    ).status_code == 401
    assert client.post(
        "/api/v1/participants/auth/consume-link", json={"token": second_token}
    ).status_code == 200
