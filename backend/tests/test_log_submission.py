import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import logs
from backend.app.db import Base, get_session
from backend.app.main import app
from backend.app.models import (
    AuditEvent,
    Contest,
    Entry,
    EntryAccessGrant,
    EntryRevision,
    EntryStatus,
    GuestEntryEmail,
    GuestEntryEmailVerification,
    LogSubmissionRequest,
    ParticipantEmail,
    Qso,
    RulesetVersion,
    Station,
    SystemRole,
    SystemUser,
)
from backend.app.rate_limit import limiter

LOG = """START-OF-LOG
CONTEST: guest-sprint
CALLSIGN: EA7KLK
EMAIL: operator@example.test
NAME: Radio Operator
X-EXTRA: kept for audit
QSO: 14025 CW 2026-10-15 1234 EA7KLK 599 001 F4ABC 599 002
END-OF-LOG
"""

ADIF_LOG = (
    "<ADIF_VER:5>3.1.8<PROGRAMID:6>WSJT-X<STATION_CALLSIGN:6>EA7KLK<EOH>\n"
    "<QSO_DATE:8>20261015<TIME_ON:4>1234<BAND:2>2m<FREQ:7>144.174"
    "<MODE:4>MFSK<SUBMODE:3>FT8<CALL:5>F4ABC<GRIDSQUARE:4>JN18"
    "<MY_GRIDSQUARE:4>IM87<RST_SENT:3>-10<RST_RCVD:3>-12<EOR>\n"
)


@pytest.fixture
def log_database():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(UTC)
    with factory.begin() as session:
        manager = SystemUser(
            username="manager",
            email_normalized="manager@example.test",
            display_name="Manager",
            role=SystemRole.CONTEST_MANAGER,
            password_hash="test-hash",
        )
        session.add(manager)
        session.flush()
        session.add(
            Contest(
                owner_user_id=manager.id,
                name="Guest Sprint",
                slug="guest-sprint",
                starts_at=now - timedelta(hours=1),
                ends_at=now + timedelta(hours=1),
                log_submission_cutoff_at=now + timedelta(days=1),
                status="open",
            )
        )
    enable_digital_ruleset(
        factory,
        formats=("cabrillo",),
        ruleset_key="fixture-cabrillo",
        version="1",
    )

    def override_session():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    limiter.clear()
    try:
        yield factory
    finally:
        app.dependency_overrides.clear()
        limiter.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def submit(
    client: TestClient,
    content: str = LOG,
    *,
    key: str = "request-key-0001",
    filename: str = "entry.log",
):
    return client.post(
        "/api/v1/public/contests/guest-sprint/logs",
        headers={"Idempotency-Key": key},
        files={"file": (filename, content.encode(), "text/plain")},
    )


def enable_digital_ruleset(
    factory,
    *,
    formats=("adif",),
    ruleset_key="test-upload-formats",
    version="1",
):
    configuration = json.loads(
        (
            Path(__file__).parents[2] / "documentation/ruleset-drafts/vhf-uhf-ft8-activity.json"
        ).read_text()
    )
    mappings = [
        {
            "id": f"format-mapping-{format_name}",
            "rule": {
                "kind": "format_mapping",
                "format": format_name,
                "preserve_unknown_fields": True,
            },
        }
        for format_name in formats
    ]
    configuration["rules"] = [
        item for item in configuration["rules"] if item["rule"]["kind"] != "format_mapping"
    ] + mappings
    configuration["ruleset_key"] = ruleset_key
    configuration["version"] = version
    with factory.begin() as session:
        contest = session.scalar(select(Contest).where(Contest.slug == "guest-sprint"))
        ruleset = RulesetVersion(
            ruleset_key=configuration["ruleset_key"],
            version=configuration["version"],
            source_url=configuration.get("source_url"),
            source_edition=configuration.get("source_edition"),
            rule_type_keys=sorted({item["rule"]["kind"] for item in configuration["rules"]}),
            configuration=configuration,
        )
        session.add(ruleset)
        session.flush()
        contest.ruleset_version_id = ruleset.id
        from backend.app.logs.api import _contest_upload_formats

        expected = sorted(set(formats) & {"adif", "cabrillo"})
        assert _contest_upload_formats(session, contest) == expected


def test_guest_upload_persists_original_log_and_scoped_receipt(log_database):
    client = TestClient(app)
    response = submit(client)
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["summary"]["accepted_qsos"] == 1
    assert result["receipt_token"]
    with log_database() as session:
        entry = session.get(Entry, result["entry_id"])
        assert entry is not None and entry.submitter_user_id is None
        assert session.scalar(select(ParticipantEmail)).verified_at is None
        assert session.scalar(select(EntryRevision)).original_content == LOG
        assert session.scalar(select(Station)).callsign_submitted == "EA7KLK"
        assert session.scalar(select(Qso)).callsign_submitted == "F4ABC"
        assert session.scalar(select(EntryAccessGrant)).token_hash != result["receipt_token"]

    entry_id = result["entry_id"]
    headers = {"X-Entry-Receipt": result["receipt_token"]}
    entry_details = client.get(f"/api/v1/public/entries/{entry_id}", headers=headers)
    assert entry_details.status_code == 200
    assert entry_details.json()["accepted_formats"] == ["cabrillo"]
    assert client.get(f"/api/v1/public/entries/{entry_id}").status_code == 404


def test_valid_cabrillo_email_is_verified_and_grants_only_its_entry(log_database, monkeypatch):
    delivered: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "backend.app.logs.api.send_guest_entry_verification",
        lambda email, link: delivered.append((email, link)),
    )
    with TestClient(app) as client:
        uploaded = submit(client).json()
        assert uploaded["guest_email_prompt_required"] is False
        assert uploaded["guest_email_verification_sent"] is True
        assert delivered[0][0] == "operator@example.test"
        token = delivered[0][1].split("token=", 1)[1]
        with log_database() as session:
            contact = session.scalar(
                select(GuestEntryEmail).where(GuestEntryEmail.entry_id == uploaded["entry_id"])
            )
            assert contact is not None
            assert contact.access_opt_in is True
            assert contact.results_opt_in is False
            verification = session.scalar(
                select(GuestEntryEmailVerification).where(
                    GuestEntryEmailVerification.guest_email_id == contact.id
                )
            )
            assert verification is not None
            assert verification.token_hash != token
            assert token not in verification.token_hash
        verified = client.post("/api/v1/public/guest-email/verify", json={"token": token})
        assert verified.status_code == 200
        access_token = verified.json()["entry_access_token"]
        assert access_token
        details = client.get(
            f"/api/v1/public/entries/{uploaded['entry_id']}",
            headers={"X-Entry-Receipt": access_token},
        )
        assert details.status_code == 200
        amended = client.put(
            f"/api/v1/public/entries/{uploaded['entry_id']}/log",
            headers={
                "X-Entry-Receipt": access_token,
                "Idempotency-Key": "verified-email-amend-001",
            },
            files={"file": ("amended.log", LOG.replace("F4ABC", "F5XYZ").encode(), "text/plain")},
        )
        assert amended.status_code == 200, amended.text
        assert amended.json()["revision_number"] == 2
        withdrawn = client.post(
            f"/api/v1/public/entries/{uploaded['entry_id']}/withdraw",
            headers={"X-Entry-Receipt": access_token},
        )
        assert withdrawn.status_code == 200
        with log_database() as session:
            updated_entry = session.get(Entry, uploaded["entry_id"])
            assert updated_entry is not None and updated_entry.status is EntryStatus.WITHDRAWN
            assert (
                session.scalar(
                    select(func.count(AuditEvent.id)).where(AuditEvent.action == "entry.withdrawn")
                )
                == 1
            )
        second_upload = submit(
            client,
            LOG.replace("EA7KLK", "EA7KLM"),
            key="separate-entry-access-002",
        ).json()
        assert (
            client.get(
                f"/api/v1/public/entries/{second_upload['entry_id']}",
                headers={"X-Entry-Receipt": access_token},
            ).status_code
            == 404
        )
        revoked = client.post(
            f"/api/v1/public/entries/{uploaded['entry_id']}/guest-email",
            headers={"X-Entry-Receipt": uploaded["receipt_token"]},
            json={
                "email": "operator@example.test",
                "entry_access": False,
                "result_notifications": False,
            },
        )
        assert revoked.status_code == 200
        assert revoked.json()["status"] == "revoked"
        assert (
            client.get(
                f"/api/v1/public/entries/{uploaded['entry_id']}",
                headers={"X-Entry-Receipt": access_token},
            ).status_code
            == 404
        )
        assert (
            client.post("/api/v1/public/guest-email/verify", json={"token": token}).status_code
            == 400
        )


def test_adif_upload_prompts_for_email_after_acceptance(log_database):
    enable_digital_ruleset(log_database, formats=("adif",), ruleset_key="guest-adif-email-prompt")
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/public/contests/guest-sprint/logs",
            headers={"Idempotency-Key": "adif-email-prompt-001"},
            files={"file": ("entry.adi", ADIF_LOG.encode(), "text/plain")},
        )
        assert response.status_code == 201, response.text
        assert response.json()["guest_email_prompt_required"] is True
        assert response.json()["guest_email_verification_sent"] is None
        with log_database() as session:
            assert session.query(GuestEntryEmail).count() == 0


def test_invalid_cabrillo_email_does_not_reject_log_and_prompts_for_address(log_database):
    invalid_log = LOG.replace("EMAIL: operator@example.test", "EMAIL: not-an-address")
    with TestClient(app) as client:
        response = submit(client, invalid_log, key="invalid-email-prompt-001")
        assert response.status_code == 201, response.text
        assert response.json()["guest_email_prompt_required"] is True
        assert any(item["code"] == "invalid_email" for item in response.json()["warnings"])


def test_guest_email_result_notice_requires_separate_opt_in_and_verification(
    log_database, monkeypatch
):
    delivered: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "backend.app.logs.api.send_guest_entry_verification",
        lambda email, link: delivered.append((email, link)),
    )
    with TestClient(app) as client:
        uploaded = submit(client).json()
        receipt = uploaded["receipt_token"]
        response = client.post(
            f"/api/v1/public/entries/{uploaded['entry_id']}/guest-email",
            headers={"X-Entry-Receipt": receipt},
            json={
                "email": "results@example.test",
                "entry_access": False,
                "result_notifications": True,
            },
        )
        assert response.status_code == 200, response.text
        new_token = delivered[-1][1].split("token=", 1)[1]
        verified = client.post("/api/v1/public/guest-email/verify", json={"token": new_token})
        assert verified.status_code == 200
        assert verified.json()["entry_access_token"] is None
        assert verified.json()["results_notifications_enabled"] is True


def test_expired_guest_email_verification_is_rejected(log_database, monkeypatch):
    delivered: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "backend.app.logs.api.send_guest_entry_verification",
        lambda email, link: delivered.append((email, link)),
    )
    with TestClient(app) as client:
        uploaded = submit(client).json()
        token = delivered[0][1].split("token=", 1)[1]
        with log_database.begin() as session:
            verification = session.scalar(select(GuestEntryEmailVerification))
            assert verification is not None
            expired_at = datetime.now(UTC) - timedelta(seconds=1)
            verification.created_at = expired_at - timedelta(hours=1)
            verification.expires_at = expired_at
        response = client.post("/api/v1/public/guest-email/verify", json={"token": token})
        assert response.status_code == 400
        assert (
            client.get(
                f"/api/v1/public/entries/{uploaded['entry_id']}",
                headers={"X-Entry-Receipt": "invalid-token"},
            ).status_code
            == 404
        )


def test_failed_guest_verification_delivery_keeps_upload_and_allows_resend(
    log_database, monkeypatch
):
    send_attempts = 0

    def flaky_delivery(_email, _link):
        nonlocal send_attempts
        send_attempts += 1
        if send_attempts == 1:
            raise TimeoutError("mail transport unavailable")

    monkeypatch.setattr("backend.app.logs.api.send_guest_entry_verification", flaky_delivery)
    with TestClient(app) as client:
        uploaded_response = submit(client)
        assert uploaded_response.status_code == 201
        uploaded = uploaded_response.json()
        assert uploaded["guest_email_verification_sent"] is False
        retried = client.post(
            f"/api/v1/public/entries/{uploaded['entry_id']}/guest-email/resend",
            headers={"X-Entry-Receipt": uploaded["receipt_token"]},
        )
        assert retried.status_code == 200
        assert retried.json()["verification_email_sent"] is True
        assert send_attempts == 2


@pytest.mark.parametrize("version", ["2.0", "3.0"])
def test_guest_upload_accepts_versioned_cabrillo_v2_and_v3(log_database, version):
    versioned_log = LOG.replace("START-OF-LOG", f"START-OF-LOG: {version}").replace(
        "END-OF-LOG", "END-OF-LOG:"
    )

    response = submit(
        TestClient(app),
        versioned_log,
        key=f"cabrillo-v{version.replace('.', '')}-upload",
    )

    assert response.status_code == 201, response.text
    assert response.json()["summary"]["accepted_qsos"] == 1
    with log_database() as session:
        revision = session.scalar(select(EntryRevision))
        assert revision is not None
        assert revision.original_content == versioned_log


def test_guest_upload_accepts_ruleset_enabled_adif_and_preserves_format(log_database):
    enable_digital_ruleset(log_database, formats=("adif", "cabrillo"))
    client = TestClient(app)

    listed = client.get("/api/v1/public/submittable-contests").json()["items"][0]
    assert listed["accepted_formats"] == ["adif", "cabrillo"]
    response = submit(client, ADIF_LOG, key="adif-entry-key-1", filename="ea7klk.adi")

    assert response.status_code == 201, response.text
    assert response.json()["summary"]["accepted_qsos"] == 1
    entry_details = client.get(
        f"/api/v1/public/entries/{response.json()['entry_id']}",
        headers={"X-Entry-Receipt": response.json()["receipt_token"]},
    )
    assert entry_details.json()["accepted_formats"] == ["adif", "cabrillo"]
    with log_database() as session:
        revision = session.scalar(select(EntryRevision))
        qso = session.scalar(select(Qso))
        assert revision is not None and revision.input_format == "adif"
        assert revision.original_content == ADIF_LOG
        assert qso is not None and qso.mode == "FT8" and qso.band == "2m"
        assert qso.exchange_received_submitted["values"]["grid"] == "JN18"


def test_guest_upload_rejects_format_not_enabled_by_contest_ruleset(log_database):
    enable_digital_ruleset(log_database, formats=("adif",))

    response = submit(TestClient(app), LOG, key="disabled-format-test", filename="entry.log")

    assert response.status_code == 415
    with log_database() as session:
        assert session.query(Entry).count() == 0


def test_guest_upload_rejects_contest_without_ruleset_format(log_database):
    with log_database.begin() as session:
        contest = session.scalar(select(Contest).where(Contest.slug == "guest-sprint"))
        contest.ruleset_version_id = None

    client = TestClient(app)
    assert client.get("/api/v1/public/submittable-contests").json()["items"] == []
    response = submit(client, LOG, key="no-ruleset-format", filename="entry.log")
    assert response.status_code == 415
    with log_database() as session:
        assert session.query(Entry).count() == 0


def test_guest_upload_rejects_ruleset_with_only_unsupported_format(log_database):
    enable_digital_ruleset(log_database, formats=("csv",))

    client = TestClient(app)
    assert client.get("/api/v1/public/submittable-contests").json()["items"] == []
    response = submit(client, LOG, key="csv-only-format", filename="entry.log")
    assert response.status_code == 415
    with log_database() as session:
        assert session.query(Entry).count() == 0


def test_entry_log_resubmission_accepts_adif_for_enabled_format(log_database):
    enable_digital_ruleset(log_database, formats=("adif",))
    client = TestClient(app)
    created = submit(client, ADIF_LOG, key="adif-entry-key-2", filename="ea7klk.adif")
    assert created.status_code == 201, created.text
    corrected = ADIF_LOG.replace("F4ABC", "F5ABC")

    response = client.put(
        f"/api/v1/public/entries/{created.json()['entry_id']}/log",
        headers={
            "Idempotency-Key": "adif-resubmit-key-1",
            "X-Entry-Receipt": created.json()["receipt_token"],
        },
        files={"file": ("corrected.adif", corrected.encode(), "text/plain")},
    )

    assert response.status_code == 200, response.text
    with log_database() as session:
        revisions = list(
            session.scalars(select(EntryRevision).order_by(EntryRevision.revision_number))
        )
        assert [revision.input_format for revision in revisions] == ["adif", "adif"]


def test_entry_log_resubmission_rejects_format_not_enabled_by_ruleset(log_database):
    enable_digital_ruleset(log_database, formats=("adif",))
    client = TestClient(app)
    created = submit(client, ADIF_LOG, key="adif-resubmit-base", filename="base.adif")
    assert created.status_code == 201

    response = client.put(
        f"/api/v1/public/entries/{created.json()['entry_id']}/log",
        headers={
            "Idempotency-Key": "disabled-revision-format",
            "X-Entry-Receipt": created.json()["receipt_token"],
        },
        files={"file": ("wrong-format.log", LOG.encode(), "text/plain")},
    )

    assert response.status_code == 415
    with log_database() as session:
        assert session.query(EntryRevision).count() == 1


@pytest.mark.parametrize("format_state", ["no_ruleset", "unsupported_only"])
def test_entry_revision_rejects_contest_without_supported_format(log_database, format_state):
    client = TestClient(app)
    created = submit(client, key="revision-format-base")
    assert created.status_code == 201
    if format_state == "no_ruleset":
        with log_database.begin() as session:
            contest = session.scalar(select(Contest).where(Contest.slug == "guest-sprint"))
            contest.ruleset_version_id = None
    else:
        enable_digital_ruleset(log_database, formats=("csv",))

    response = client.put(
        f"/api/v1/public/entries/{created.json()['entry_id']}/log",
        headers={
            "Idempotency-Key": f"revision-{format_state}-format",
            "X-Entry-Receipt": created.json()["receipt_token"],
        },
        files={"file": ("corrected.log", LOG.encode(), "text/plain")},
    )

    assert response.status_code == 415
    with log_database() as session:
        assert session.query(EntryRevision).count() == 1


def test_idempotent_retry_reuses_entry_and_conflicting_body_is_rejected(log_database):
    client = TestClient(app)
    first = submit(client)
    repeated = submit(client)
    assert first.status_code == repeated.status_code == 201
    assert repeated.json()["replayed"] is True
    assert repeated.json()["entry_id"] == first.json()["entry_id"]
    assert repeated.json()["receipt_token"] == first.json()["receipt_token"]
    changed = submit(client, LOG.replace("F4ABC", "F5XYZ"))
    assert changed.status_code == 409
    with log_database() as session:
        assert session.query(Entry).count() == 1
        assert session.query(EntryRevision).count() == 1
        assert session.query(LogSubmissionRequest).count() == 1


def test_malformed_and_unsupported_uploads_do_not_create_entries(log_database):
    client = TestClient(app)
    malformed = submit(client, LOG.replace("599 002", ""))
    assert malformed.status_code == 422
    assert malformed.json()["status"] == "rejected"
    assert malformed.json()["errors"][0]["line"] > 0
    unsupported = submit(client, filename="../../entry.exe", key="request-key-0002")
    assert unsupported.status_code == 415
    with log_database() as session:
        assert session.query(Entry).count() == 0


def test_size_deadline_and_expiring_receipt_are_enforced(log_database):
    client = TestClient(app)
    oversized = submit(client, "x" * (logs.api.MAX_UPLOAD_BYTES + 1))
    assert oversized.status_code == 413
    created = submit(client, key="request-key-0002").json()
    with log_database.begin() as session:
        contest = session.scalar(select(Contest).where(Contest.slug == "guest-sprint"))
        contest.log_submission_cutoff_at = datetime.now(UTC) - timedelta(seconds=1)
        grant = session.scalar(select(EntryAccessGrant))
        grant.created_at = datetime.now(UTC) - timedelta(days=1)
        grant.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert submit(client, key="request-key-late").status_code == 409
    denied = client.get(
        f"/api/v1/public/entries/{created['entry_id']}",
        headers={"X-Entry-Receipt": created["receipt_token"]},
    )
    assert denied.status_code == 404


def test_receipt_allows_append_only_contact_edit_and_remove(log_database):
    client = TestClient(app)
    created = submit(client).json()
    entry_id = created["entry_id"]
    headers = {"X-Entry-Receipt": created["receipt_token"]}
    initial = client.get(f"/api/v1/public/entries/{entry_id}", headers=headers).json()
    contact_id = initial["contacts"][0]["id"]
    payload = {
        "occurred_at": "2026-10-15T12:35:00Z",
        "callsign": "F5XYZ",
        "frequency": "14025",
        "mode": "CW",
        "exchange_sent": {"raw": "001", "rst": "599"},
        "exchange_received": {"raw": "003", "rst": "599"},
    }
    edited = client.put(
        f"/api/v1/public/entries/{entry_id}/contacts/{contact_id}",
        headers=headers,
        json=payload,
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["revision_number"] == 2
    assert edited.json()["contacts"][0]["callsign"] == "F5XYZ"
    new_contact_id = edited.json()["contacts"][0]["id"]
    removed = client.delete(
        f"/api/v1/public/entries/{entry_id}/contacts/{new_contact_id}", headers=headers
    )
    assert removed.status_code == 200
    assert removed.json()["revision_number"] == 3
    assert removed.json()["contacts"] == []
    with log_database() as session:
        revisions = session.scalars(
            select(EntryRevision).order_by(EntryRevision.revision_number)
        ).all()
        assert [revision.revision_number for revision in revisions] == [1, 2, 3]
        assert revisions[0].original_content == LOG


def test_full_log_resubmission_creates_new_revision_and_recovers_receipt_on_retry(log_database):
    client = TestClient(app)
    created = submit(client).json()
    content = LOG.replace("F4ABC", "F5XYZ")
    request_args = {
        "headers": {
            "X-Entry-Receipt": created["receipt_token"],
            "Idempotency-Key": "resubmit-key-0001",
        },
        "files": {"file": ("new.log", content.encode(), "text/plain")},
    }
    first = client.put(f"/api/v1/public/entries/{created['entry_id']}/log", **request_args)
    replay = client.put(f"/api/v1/public/entries/{created['entry_id']}/log", **request_args)

    assert first.status_code == replay.status_code == 200
    assert first.json()["revision_number"] == 2
    assert replay.json()["replayed"] is True
    with log_database() as session:
        assert session.query(EntryRevision).count() == 2


def test_cabrillo_source_download_requires_entry_access_and_is_versioned(log_database):
    client = TestClient(app)
    submitted = submit(client).json()
    entry_id = submitted["entry_id"]
    revision = client.get(
        f"/api/v1/public/entries/{entry_id}",
        headers={"X-Entry-Receipt": submitted["receipt_token"]},
    ).json()
    url = f"/api/v1/public/entries/{entry_id}/revisions/{revision['revision_id']}/download"

    assert client.get(url).status_code == 404
    download = client.get(url, headers={"X-Entry-Receipt": submitted["receipt_token"]})
    assert download.status_code == 200
    assert download.headers["X-Contestmaster-Log-Format"] == "cabrillo-source-v1"
    assert download.headers["Content-Disposition"].endswith('filename="entry.log"')
    assert "CALLSIGN: EA7KLK" in download.text
    assert "X-EXTRA: kept for audit" in download.text


def test_verified_participant_identity_is_associated_and_can_use_its_session(log_database):
    from hashlib import sha256

    from backend.app.models import Participant, ParticipantEmail, ParticipantSession

    with log_database.begin() as session:
        participant = Participant(display_name="Registered", callsign_submitted="EA7KLK")
        session.add(participant)
        session.flush()
        email = ParticipantEmail(
            participant_id=participant.id,
            email_normalized="operator@example.test",
            verified_at=datetime.now(UTC),
        )
        session.add(email)
        session.flush()
        raw_session, csrf = "participant-session-token", "participant-csrf-token"
        session.add(
            ParticipantSession(
                participant_email_id=email.id,
                token_hash=sha256(raw_session.encode()).hexdigest(),
                csrf_token_hash=sha256(csrf.encode()).hexdigest(),
                created_at=datetime.now(UTC),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        participant_id = participant.id
        email_id = email.id

    client = TestClient(app)
    uploaded = submit(client).json()
    with log_database() as session:
        entry = session.get(Entry, uploaded["entry_id"])
        assert entry.participant_id == participant_id
    client.cookies.set("contestmaster_participant_session", raw_session)
    client.cookies.set("contestmaster_participant_csrf", csrf)
    response = client.get(f"/api/v1/public/entries/{uploaded['entry_id']}")
    assert response.status_code == 200
    contact_id = response.json()["contacts"][0]["id"]
    updated = client.delete(
        f"/api/v1/public/entries/{uploaded['entry_id']}/contacts/{contact_id}",
        headers={"X-CSRF-Token": csrf},
    )
    assert updated.status_code == 200
    assert updated.json()["contacts"] == []
    with log_database() as session:
        revision = session.scalar(select(EntryRevision).where(EntryRevision.revision_number == 2))
        assert revision.received_by_participant_email_id == email_id
        assert revision.received_via == "participant_session"


def test_anonymous_log_upload_has_no_per_ip_rate_limit(log_database):
    client = TestClient(app)
    accepted = [submit(client, key=f"request-key-{index:04d}").status_code for index in range(65)]

    assert all(status in {200, 201} for status in accepted)


def test_log_resubmission_has_no_per_ip_rate_limit(log_database):
    client = TestClient(app)
    created = submit(client, key="resubmit-create-0001")
    assert created.status_code in {200, 201}
    entry_id = created.json()["entry_id"]
    receipt = created.json()["receipt_token"]
    results = [
        client.put(
            f"/api/v1/public/entries/{entry_id}/log",
            files={"file": ("entry.log", LOG.encode(), "text/plain")},
            headers={
                "Idempotency-Key": f"resubmit-key-{index:04d}",
                "X-Entry-Receipt": receipt,
            },
        ).status_code
        for index in range(125)
    ]

    assert all(status in {200, 201} for status in results)
