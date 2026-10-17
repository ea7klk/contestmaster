import hashlib
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api import participant_identity
from backend.app.db import Base, get_session
from backend.app.main import app
from backend.app.models import (
    AuditEvent,
    Contest,
    Entry,
    EntryAccessGrant,
    EntryRevision,
    EntryStatus,
    Participant,
    ParticipantCallsign,
    ParticipantEmail,
    ParticipantEmailChange,
    ParticipantMagicLink,
    ParticipantPasswordReset,
    ParticipantSession,
    Station,
    SystemRole,
    SystemUser,
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

    consumed = client.post("/api/v1/participants/auth/consume-link", json={"token": raw_token})
    assert consumed.status_code == 200
    assert consumed.json()["participant"]["id"] == participant_id
    assert (
        "httponly"
        in next(
            cookie
            for cookie in consumed.headers.get_list("set-cookie")
            if cookie.startswith("contestmaster_participant_session=")
        ).lower()
    )
    assert client.get("/api/v1/participants/auth/me").json()["email"] == "pilot@example.test"
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/contests").status_code == 401
    entries = client.get("/api/v1/participants/auth/entries")
    assert [entry["entry_key"] for entry in entries.json()["items"]] == ["pilot"]
    entry_id = entries.json()["items"][0]["id"]
    withdrawn = client.post(
        f"/api/v1/public/entries/{entry_id}/withdraw",
        headers={"X-CSRF-Token": client.cookies.get("contestmaster_participant_csrf")},
    )
    assert withdrawn.status_code == 200
    assert (
        client.get("/api/v1/participants/auth/entries").json()["items"][0]["status"] == "withdrawn"
    )
    assert "global_administrator" not in consumed.text
    assert "contest_manager" not in consumed.text
    with participant_database() as session:
        assert session.query(ParticipantEmail).one().verified_at is not None
        assert session.query(ParticipantSession).count() == 1
        withdrawal = session.query(AuditEvent).filter_by(action="entry.withdrawn").one()
        assert withdrawal.event_metadata["access_channel"] == "participant_session"
        assert withdrawal.event_metadata["participant_id"] == participant_id

    reused = client.post("/api/v1/participants/auth/consume-link", json={"token": raw_token})
    assert reused.status_code == 401
    no_csrf = client.post("/api/v1/participants/auth/logout")
    assert no_csrf.status_code == 403
    csrf = client.cookies.get("contestmaster_participant_csrf")
    assert (
        client.post("/api/v1/participants/auth/logout", headers={"X-CSRF-Token": csrf}).status_code
        == 200
    )
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
        client.post("/api/v1/participants/auth/consume-link", json={"token": raw_token}).status_code
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
        assert (
            session.query(ParticipantEmail)
            .filter_by(email_normalized="rollback@example.test")
            .count()
            == 0
        )


def test_participant_registration_requires_email_verification_and_supports_password_login(
    participant_database, monkeypatch
):
    delivered: list[tuple[str, str]] = []
    monkeypatch.setattr(
        participant_identity,
        "send_participant_magic_link",
        lambda email, link: delivered.append((email, link)),
    )
    client = TestClient(app)
    registered = client.post(
        "/api/v1/participants/auth/register",
        json={
            "email": "radio@example.test",
            "callsign": "EA7ABC",
            "display_name": "Radio Operator",
            "password": "correct horse battery staple",
        },
    )
    assert registered.status_code == 202
    assert (
        client.post(
            "/api/v1/participants/auth/login",
            json={"email": "radio@example.test", "password": "correct horse battery staple"},
        ).status_code
        == 401
    )
    raw_token = parse_qs(urlparse(delivered[0][1]).query)["token"][0]
    assert (
        client.post("/api/v1/participants/auth/consume-link", json={"token": raw_token}).status_code
        == 200
    )
    primary = client.get("/api/v1/participants/auth/me").json()["callsigns"]
    assert len(primary) == 1
    assert primary[0]["callsign"] == "EA7ABC"
    assert primary[0]["is_primary"] is True
    csrf = client.cookies.get("contestmaster_participant_csrf")
    added = client.post(
        "/api/v1/participants/auth/callsigns",
        json={"callsign": "K1XYZ"},
        headers={"X-CSRF-Token": csrf},
    )
    assert added.status_code == 201
    assert (
        client.patch(
            "/api/v1/participants/auth/me",
            json={"display_name": "Updated Operator"},
            headers={"X-CSRF-Token": csrf},
        ).json()["display_name"]
        == "Updated Operator"
    )
    assert (
        client.delete(
            f"/api/v1/participants/auth/callsigns/{added.json()['id']}",
            headers={"X-CSRF-Token": csrf},
        ).status_code
        == 204
    )
    assert (
        client.delete(
            "/api/v1/participants/auth/callsigns/1", headers={"X-CSRF-Token": csrf}
        ).status_code
        == 409
    )
    assert (
        client.post("/api/v1/participants/auth/logout", headers={"X-CSRF-Token": csrf}).status_code
        == 200
    )
    signed_in = client.post(
        "/api/v1/participants/auth/login",
        json={"email": "radio@example.test", "password": "correct horse battery staple"},
    )
    assert signed_in.status_code == 200
    assert [
        item["callsign"] for item in client.get("/api/v1/participants/auth/me").json()["callsigns"]
    ] == ["EA7ABC"]


def test_participant_password_reset_is_single_use_and_revokes_sessions(
    participant_database, monkeypatch
):
    delivered: list[tuple[str, str]] = []
    monkeypatch.setattr(
        participant_identity,
        "send_participant_magic_link",
        lambda _email, link: delivered.append(("verification", link)),
    )
    monkeypatch.setattr(
        participant_identity,
        "send_email",
        lambda email, _subject, _body, link: delivered.append((email, link)),
    )
    client = TestClient(app)
    assert (
        client.post(
            "/api/v1/participants/auth/register",
            json={
                "email": "reset@example.test",
                "callsign": "K2RST",
                "password": "original password for test",
            },
        ).status_code
        == 202
    )
    verify_token = parse_qs(urlparse(delivered[0][1]).query)["token"][0]
    assert (
        client.post(
            "/api/v1/participants/auth/consume-link", json={"token": verify_token}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/participants/auth/logout",
            headers={"X-CSRF-Token": client.cookies.get("contestmaster_participant_csrf")},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/participants/auth/login",
            json={"email": "reset@example.test", "password": "original password for test"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/participants/auth/forgot-password", json={"email": "reset@example.test"}
        ).status_code
        == 202
    )
    reset_token = parse_qs(urlparse(delivered[-1][1]).query)["token"][0]
    assert (
        client.post(
            "/api/v1/participants/auth/reset-password",
            json={"token": reset_token, "password": "replacement password for test"},
        ).status_code
        == 200
    )
    assert client.get("/api/v1/participants/auth/me").status_code == 401
    assert (
        client.post(
            "/api/v1/participants/auth/reset-password",
            json={"token": reset_token, "password": "another replacement password"},
        ).status_code
        == 400
    )
    with participant_database() as session:
        record = session.query(ParticipantPasswordReset).one()
        assert record.token_hash != reset_token
        assert (
            session.query(ParticipantSession)
            .filter(ParticipantSession.revoked_at.is_not(None))
            .count()
            >= 1
        )
    assert (
        client.post(
            "/api/v1/participants/auth/login",
            json={"email": "reset@example.test", "password": "replacement password for test"},
        ).status_code
        == 200
    )


def test_email_change_requires_both_addresses_and_revokes_sessions(
    participant_database, monkeypatch
):
    delivered: list[tuple[str, str]] = []
    monkeypatch.setattr(
        participant_identity,
        "send_participant_magic_link",
        lambda _email, link: delivered.append(("verification", link)),
    )
    monkeypatch.setattr(
        participant_identity,
        "send_email",
        lambda email, _subject, _body, link: delivered.append((email, link)),
    )
    client = TestClient(app)
    assert (
        client.post(
            "/api/v1/participants/auth/register",
            json={
                "email": "old-address@example.test",
                "callsign": "K3MAIL",
                "password": "account password for test",
            },
        ).status_code
        == 202
    )
    verify_token = parse_qs(urlparse(delivered[0][1]).query)["token"][0]
    assert (
        client.post(
            "/api/v1/participants/auth/consume-link", json={"token": verify_token}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/participants/auth/email-change",
            json={"email": "new-address@example.test"},
            headers={"X-CSRF-Token": client.cookies.get("contestmaster_participant_csrf")},
        ).status_code
        == 202
    )
    assert [address for address, _link in delivered[1:]] == [
        "old-address@example.test",
        "new-address@example.test",
    ]
    new_token = parse_qs(urlparse(delivered[2][1]).query)["token"][0]
    old_token = parse_qs(urlparse(delivered[1][1]).query)["token"][0]

    first_confirmation = client.post(
        "/api/v1/participants/auth/confirm-email-change", json={"token": new_token}
    )
    assert first_confirmation.status_code == 200
    assert first_confirmation.json()["complete"] == "false"
    assert client.get("/api/v1/participants/auth/me").json()["email"] == "old-address@example.test"

    completed = client.post(
        "/api/v1/participants/auth/confirm-email-change", json={"token": old_token}
    )
    assert completed.status_code == 200
    assert completed.json()["complete"] == "true"
    assert client.get("/api/v1/participants/auth/me").status_code == 401
    assert (
        client.post(
            "/api/v1/participants/auth/confirm-email-change", json={"token": old_token}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/v1/participants/auth/login",
            json={"email": "new-address@example.test", "password": "account password for test"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/participants/auth/email-change",
            json={"email": "expired-address@example.test"},
            headers={"X-CSRF-Token": client.cookies.get("contestmaster_participant_csrf")},
        ).status_code
        == 202
    )
    expired_token = parse_qs(urlparse(delivered[-1][1]).query)["token"][0]
    with participant_database.begin() as session:
        pending = session.query(ParticipantEmailChange).filter_by(completed_at=None).one()
        pending.created_at = datetime.now(UTC) - timedelta(hours=25)
        pending.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert (
        client.post(
            "/api/v1/participants/auth/confirm-email-change", json={"token": expired_token}
        ).status_code
        == 400
    )
    with participant_database() as session:
        emails = {
            item.email_normalized: (item.is_primary, item.is_active, item.verified_at is not None)
            for item in session.query(ParticipantEmail).all()
        }
    assert emails == {
        "old-address@example.test": (False, False, True),
        "new-address@example.test": (True, True, True),
    }


def test_magic_link_request_invalidates_an_older_unconsumed_link(participant_database, monkeypatch):
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
    assert (
        client.post(
            "/api/v1/participants/auth/consume-link", json={"token": first_token}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/participants/auth/consume-link", json={"token": second_token}
        ).status_code
        == 200
    )


def test_magic_link_requests_are_rate_limited_per_email(participant_database, monkeypatch):
    monkeypatch.setattr(
        participant_identity,
        "send_participant_magic_link",
        lambda *_args: None,
    )
    client = TestClient(app)
    payload = {"email": "limited@example.test"}

    for _ in range(5):
        assert (
            client.post("/api/v1/participants/auth/request-link", json=payload).status_code == 202
        )

    rejected = client.post("/api/v1/participants/auth/request-link", json=payload)
    assert rejected.status_code == 429
    assert rejected.headers["Retry-After"]
    assert "limited@example.test" not in rejected.text


def test_participant_password_login_is_rate_limited_per_account(participant_database):
    from backend.app.api.auth import hash_password

    with participant_database.begin() as session:
        participant = Participant(password_hash=hash_password("valid participant password"))
        session.add(participant)
        session.flush()
        session.add(
            ParticipantEmail(
                participant_id=participant.id,
                email_normalized="password-limit@example.test",
                verified_at=datetime.now(UTC),
                is_primary=True,
            )
        )
    client = TestClient(app)
    payload = {"email": "password-limit@example.test", "password": "incorrect password"}
    for _ in range(10):
        assert client.post("/api/v1/participants/auth/login", json=payload).status_code == 401
    rejected = client.post("/api/v1/participants/auth/login", json=payload)
    assert rejected.status_code == 429
    assert rejected.headers["Retry-After"]


def test_registered_participant_can_claim_open_guest_entries_for_receipted_callsign(
    participant_database, monkeypatch
):
    delivered: list[tuple[str, str]] = []
    monkeypatch.setattr(
        participant_identity,
        "send_participant_magic_link",
        lambda email, link: delivered.append((email, link)),
    )
    monkeypatch.setattr(participant_identity, "enforce_rate_limit", lambda *_args, **_kwargs: None)
    now = datetime.now(UTC)
    receipt_tokens = {
        "first": "receipt-token-for-first-guest-entry",
        "second": "receipt-token-for-second-guest-entry",
        "other_call": "receipt-token-for-other-callsign-entry",
        "expired": "receipt-token-for-expired-entry",
        "revoked": "receipt-token-for-revoked-entry",
        "registered": "receipt-token-for-registered-entry",
    }
    with participant_database.begin() as session:
        owner = SystemUser(
            username="claim-owner",
            email_normalized="claim-owner@example.test",
            display_name="Contest owner",
            role=SystemRole.CONTEST_MANAGER,
            password_hash="unused-test-hash",
        )
        session.add(owner)
        session.flush()
        contest = Contest(
            owner_user_id=owner.id,
            name="Claim Contest",
            slug="claim-contest",
            starts_at=now - timedelta(days=2),
            ends_at=now - timedelta(days=1),
            log_submission_cutoff_at=now + timedelta(days=1),
        )
        session.add(contest)
        session.flush()
        guest_owners = {
            name: Participant(
                display_name=f"Guest {name}",
                callsign_submitted="EA7ABC" if name != "other_call" else "K1XYZ",
                callsign_normalized="EA7ABC" if name != "other_call" else "K1XYZ",
            )
            for name in ("first", "second", "other_call", "expired", "revoked")
        }
        registered_owner = Participant(
            display_name="Different registered owner",
            password_hash="already-registered-password-hash",
        )
        session.add_all([*guest_owners.values(), registered_owner])
        session.flush()
        for name, token in receipt_tokens.items():
            owner_participant = (
                registered_owner if name == "registered" else guest_owners[name]
            )
            call = "K1XYZ" if name == "other_call" else "EA7ABC"
            entry = Entry(
                contest_id=contest.id,
                participant_id=owner_participant.id,
                entry_key=f"entry-{name}",
                status=EntryStatus.ACCEPTED,
            )
            session.add(entry)
            session.flush()
            content = f"fixture log {name}"
            revision = EntryRevision(
                entry_id=entry.id,
                revision_number=1,
                input_format="cabrillo",
                storage_key=f"database://entry-revisions/{entry.id}/1",
                original_content=content,
                content_sha256=hashlib.sha256(content.encode()).hexdigest(),
                byte_size=len(content.encode()),
                submitted_at=now,
            )
            session.add(revision)
            session.flush()
            session.add(
                Station(
                    entry_revision_id=revision.id,
                    callsign_submitted=call,
                    callsign_normalized=call,
                )
            )
            created_at = now - timedelta(days=2) if name in {"expired", "revoked"} else now
            session.add(
                EntryAccessGrant(
                    entry_id=entry.id,
                    token_hash=hashlib.sha256(token.encode()).hexdigest(),
                    created_at=created_at,
                    expires_at=now - timedelta(days=1) if name == "expired" else None,
                    revoked_at=now - timedelta(days=1) if name == "revoked" else None,
                )
            )
        entry_ids = {
            name: session.scalar(
                select(Entry.id).where(Entry.entry_key == f"entry-{name}")
            )
            for name in receipt_tokens
        }

    client = TestClient(app)
    registration = client.post(
        "/api/v1/participants/auth/register",
        json={
            "email": "new-operator@example.test",
            "callsign": "EA7ABC",
            "password": "a long participant account password",
            "display_name": "New operator",
        },
    )
    assert registration.status_code == 202
    verification_token = parse_qs(urlparse(delivered[0][1]).query)["token"][0]
    assert (
        client.post(
            "/api/v1/participants/auth/consume-link", json={"token": verification_token}
        ).status_code
        == 200
    )

    claimed = client.post(
        "/api/v1/participants/auth/claim-entries",
        json={"receipt_token": receipt_tokens["first"]},
        headers={
            "X-CSRF-Token": client.cookies.get("contestmaster_participant_csrf"),
        },
    )
    assert claimed.status_code == 200
    assert claimed.json() == {
        "status": "claimed",
        "callsign": "EA7ABC",
        "claimed_entries": 2,
    }
    listed_entries = client.get("/api/v1/participants/auth/entries")
    assert listed_entries.status_code == 200
    assert {item["id"] for item in listed_entries.json()["items"]} == {
        entry_ids["first"],
        entry_ids["second"],
    }

    repeated = client.post(
        "/api/v1/participants/auth/claim-entries",
        json={"receipt_token": receipt_tokens["first"]},
        headers={
            "X-CSRF-Token": client.cookies.get("contestmaster_participant_csrf"),
        },
    )
    assert repeated.status_code == 200
    assert repeated.json()["claimed_entries"] == 0

    for token in (
        "not-a-valid-receipt-token-value",
        receipt_tokens["other_call"],
        receipt_tokens["expired"],
        receipt_tokens["revoked"],
        receipt_tokens["registered"],
    ):
        rejected = client.post(
            "/api/v1/participants/auth/claim-entries",
            json={"receipt_token": token},
            headers={
                "X-CSRF-Token": client.cookies.get("contestmaster_participant_csrf"),
            },
        )
        assert rejected.status_code == 404
        assert (
            rejected.json()["error"]["message"]
            == "Entry not found or access is no longer valid."
        )

    with participant_database() as session:
        claimant = session.scalar(
            select(Participant).where(Participant.display_name == "New operator")
        )
        assert claimant is not None
        assert session.get(Entry, entry_ids["first"]).participant_id == claimant.id
        assert session.get(Entry, entry_ids["second"]).participant_id == claimant.id
        assert session.get(Entry, entry_ids["other_call"]).participant_id != claimant.id
        assert session.get(Entry, entry_ids["expired"]).participant_id != claimant.id
        assert session.get(Entry, entry_ids["revoked"]).participant_id != claimant.id
        assert session.get(Entry, entry_ids["registered"]).participant_id != claimant.id
        claimed_call = session.scalar(
            select(ParticipantCallsign).where(
                ParticipantCallsign.participant_id == claimant.id
            )
        )
        assert claimed_call is not None
        assert claimed_call.verified_at is not None
        claim_audit = session.scalar(
            select(AuditEvent).where(AuditEvent.action == "participant.guest_entries_claimed")
        )
        assert claim_audit is not None
        assert claim_audit.event_metadata == {
            "participant_id": claimant.id,
            "callsign": "EA7ABC",
            "claimed_entry_count": 2,
            "access_channel": "participant_session",
        }
        assert receipt_tokens["first"] not in str(claim_audit.event_metadata)
