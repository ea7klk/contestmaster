import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from backend.app.api.auth import hash_password, issue_session
from backend.app.db import Base, get_session
from backend.app.main import app
from backend.app.models import (
    AuditEvent,
    BandCatalogItem,
    CallsignPrefix,
    Contest,
    ContestEntity,
    ContestMasterDataVersion,
    ContestStatus,
    CQZone,
    EmailOutbox,
    EntityType,
    Entry,
    EntryRevision,
    EntryStatus,
    GuestEntryEmail,
    MasterDataSource,
    MasterDataSyncRun,
    MasterDataVersion,
    ModeCatalogItem,
    Participant,
    PrefixCQZoneAssignment,
    PrefixEntityAssignment,
    Qso,
    QsoScore,
    ResultPublication,
    ResultPublicationEntry,
    ScoreRun,
    Station,
    SystemRole,
    SystemUser,
)
from backend.app.models.enums import (
    MasterDataAuthorityRole,
    MasterDataRunStatus,
    MasterDataVersionStatus,
)
from backend.app.results.service import publication_policy
from backend.app.rulesets.persistence import save_ruleset_version
from backend.app.rulesets.validation import validate_ruleset
from backend.tests.test_rulesets import valid_payload


@pytest.fixture
def result_db(monkeypatch, tmp_path):
    database_path = tmp_path / "results.sqlite3"
    database_url = f"sqlite:///{database_path}"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=project_root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(
        "backend.app.api.auth.get_settings", lambda: SimpleNamespace(secure_cookies=False)
    )
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with factory.begin() as session:
        manager = SystemUser(
            username="results-manager",
            email_normalized="results@example.test",
            display_name="Results Manager",
            role=SystemRole.CONTEST_MANAGER,
            password_hash=hash_password("Correct horse battery staple"),
        )
        outsider = SystemUser(
            username="other-results-manager",
            email_normalized="other-results@example.test",
            display_name="Other Manager",
            role=SystemRole.CONTEST_MANAGER,
            password_hash=hash_password("Correct horse battery staple"),
        )
        participant = Participant(callsign_submitted="EA7AAA", callsign_normalized="EA7AAA")
        late_participant = Participant(callsign_submitted="EA7LATE", callsign_normalized="EA7LATE")
        withdrawn_participant = Participant(
            callsign_submitted="EA7WITH", callsign_normalized="EA7WITH"
        )
        session.add_all([manager, outsider, participant, late_participant, withdrawn_participant])
        session.flush()
        payload = valid_payload()
        payload["rules"] = [rule for rule in payload["rules"] if rule["id"] != "entity-multiplier"]
        exchange = next(rule for rule in payload["rules"] if rule["id"] == "exchange")
        for field in exchange["rule"]["fields"]:
            field["required"] = False
        version = save_ruleset_version(
            session, validate_ruleset(payload), created_by_user_id=manager.id
        ).version
        contest = Contest(
            owner_user_id=manager.id,
            ruleset_version_id=version.id,
            name="Results Sprint",
            slug="results-sprint",
            description="Public summary only.",
            starts_at=now,
            ends_at=now + timedelta(hours=2),
            log_submission_cutoff_at=now + timedelta(days=1),
            status=ContestStatus.CLOSED,
        )
        session.add(contest)
        session.flush()
        entry_specs = [
            (participant, "EA7AAA", EntryStatus.ACCEPTED, False),
            (late_participant, "EA7LATE", EntryStatus.CHECKLOG, True),
            (withdrawn_participant, "EA7WITH", EntryStatus.WITHDRAWN, False),
        ]
        for index, (person, callsign, status, is_late) in enumerate(entry_specs, start=1):
            entry = Entry(
                contest_id=contest.id,
                participant_id=person.id,
                entry_key=f"entry-{index}",
                category_values={"operator": "single"},
                status=status,
                is_late=is_late,
            )
            session.add(entry)
            session.flush()
            revision = EntryRevision(
                entry_id=entry.id,
                revision_number=1,
                input_format="cabrillo",
                storage_key=f"database://results/{index}",
                original_content=(
                    "START-OF-LOG\nCALLSIGN: "
                    + callsign
                    + "\nQSO: hidden private contact data\nEND-OF-LOG"
                ),
                import_metadata={"headers": {}},
                content_sha256=str(index) * 64,
                byte_size=32,
                submitted_at=now,
            )
            session.add(revision)
            session.flush()
            station = Station(
                entry_revision_id=revision.id,
                callsign_submitted=callsign,
                callsign_normalized=callsign,
                operator_name_submitted="Private Operator Name",
            )
            session.add(station)
            session.flush()
            session.add(
                Qso(
                    entry_revision_id=revision.id,
                    station_id=station.id,
                    source_line_number=1,
                    occurred_at=now + timedelta(minutes=1),
                    callsign_submitted=f"F{index}ABC",
                    callsign_normalized=f"F{index}ABC",
                    band="20M",
                    mode="CW",
                    exchange_sent_submitted={"raw": "001"},
                    exchange_received_submitted={"raw": "001"},
                )
            )
        session.flush()
        manager_id = manager.id
        outsider_id = outsider.id
        contest_id = contest.id

    def override_session():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        yield factory, contest_id, manager_id, outsider_id
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def manager_client(factory, user_id: int) -> TestClient:
    with factory.begin() as session:
        user = session.get(SystemUser, user_id)
        assert user is not None
        token, csrf, _record = issue_session(session, user)
    client = TestClient(app)
    client.cookies.set("contestmaster_session", token)
    client.cookies.set("contestmaster_csrf", csrf)
    return client


def test_late_entries_are_included_only_when_ruleset_publication_policy_enables_them(
    result_db,
):
    factory, contest_id, manager_id, _outsider_id = result_db
    with factory.begin() as session:
        contest = session.get(Contest, contest_id)
        assert contest is not None
        defaults = publication_policy(session, contest)
        assert defaults["include_late"] is False

        payload = valid_payload()
        payload["ruleset_key"] = "late-publication-policy-test"
        payload["version"] = "late-publication-policy-test-1"
        payload["rules"].append(
            {
                "id": "publication-policy",
                "rule": {
                    "kind": "workflow_hook",
                    "stage": "publication",
                    "key": "synthetic-test-results",
                    "execution": "automatic",
                    "parameters": {"include_late": True},
                },
            }
        )
        version = save_ruleset_version(
            session, validate_ruleset(payload), created_by_user_id=manager_id
        ).version
        contest.ruleset_version_id = version.id
        assert publication_policy(session, contest)["include_late"] is True


def test_manager_generates_reviews_publishes_snapshot_and_exports_consistently(
    result_db, monkeypatch
):
    factory, contest_id, manager_id, outsider_id = result_db
    client = manager_client(factory, manager_id)
    outsider = manager_client(factory, outsider_id)

    assert client.get(f"/api/v1/contests/{contest_id}/results/review").status_code == 200
    assert outsider.get(f"/api/v1/contests/{contest_id}/results/review").status_code == 404
    assert client.get("/api/v1/public/contests").json()["items"] == []
    assert client.get("/api/v1/public/contests/results-sprint/results").status_code == 404

    generated = client.post(
        f"/api/v1/contests/{contest_id}/results/generate",
        headers={
            "X-CSRF-Token": client.cookies.get("contestmaster_csrf"),
            "Idempotency-Key": "phase8-generate-01",
        },
        json={"reason": "Initial manager score run"},
    )
    assert generated.status_code == 202, generated.text
    assert len(generated.json()["score_runs"]) == 3
    assert generated.json()["unresolved_count"] >= 1
    assert (
        outsider.post(
            f"/api/v1/contests/{contest_id}/results/generate",
            headers={
                "X-CSRF-Token": outsider.cookies.get("contestmaster_csrf"),
                "Idempotency-Key": "other-generate-001",
            },
            json={},
        ).status_code
        == 404
    )

    review = client.get(f"/api/v1/contests/{contest_id}/results/review")
    assert review.status_code == 200
    selected = [
        item["score_run_id"]
        for item in review.json()["items"]
        if item["included_by_default"] and item["entry_status"] != "withdrawn"
    ]
    assert len(selected) == 1
    with factory.begin() as session:
        run = session.get(ScoreRun, selected[0])
        assert run is not None
        now = datetime.now(UTC)
        session.add(
            GuestEntryEmail(
                entry_id=run.entry_id,
                email_normalized="notified@example.test",
                source="upload_prompt",
                locale="fr",
                access_opt_in=False,
                results_opt_in=True,
                verified_at=now,
                created_at=now,
                updated_at=now,
            )
        )
    delivered: list[tuple[str, str, int, str]] = []
    monkeypatch.setattr(
        "backend.app.results.api.get_settings",
        lambda: SimpleNamespace(
            email_smtp_host="mail.example.test",
            email_from_address="contestmaster@example.test",
        ),
    )
    monkeypatch.setattr("backend.app.results.api.SessionFactory", factory)
    monkeypatch.setattr(
        "backend.app.email_outbox.get_settings",
        lambda: SimpleNamespace(
            email_smtp_host="mail.example.test",
            email_from_address="contestmaster@example.test",
            frontend_base_url="https://contestmaster.example.test",
        ),
    )
    monkeypatch.setattr(
        "backend.app.email_outbox.send_guest_result_notice",
        lambda email, contest_name, number, link, **kwargs: delivered.append(
            (email, contest_name, number, link, kwargs.get("locale"))
        ),
    )
    withheld_run = next(
        item["score_run_id"]
        for item in review.json()["items"]
        if item["result_status"] == "checklog"
    )
    blocked = client.post(
        f"/api/v1/contests/{contest_id}/results/publish",
        headers={"X-CSRF-Token": client.cookies.get("contestmaster_csrf")},
        json={"score_run_ids": selected + [withheld_run]},
    )
    assert blocked.status_code == 422

    published = client.post(
        f"/api/v1/contests/{contest_id}/results/publish",
        headers={"X-CSRF-Token": client.cookies.get("contestmaster_csrf")},
        json={"score_run_ids": selected, "reason": "Reviewed result list"},
    )
    assert published.status_code == 201, published.text
    assert published.json()["status"] == "published"
    assert published.json()["entry_count"] == 1
    assert published.json()["withheld_count"] == 1
    assert published.json()["queued_result_notices"] == 1
    assert delivered == [
        (
            "notified@example.test",
            "Results Sprint",
            published.json()["publication_number"],
            "https://contestmaster.example.test/contests/results-sprint",
            "fr",
        )
    ]
    from backend.app.email_outbox import dispatch_pending_emails

    assert dispatch_pending_emails(factory) == {
        "sent": 0,
        "cancelled": 0,
        "failed": 0,
        "pending": 0,
    }
    with factory() as session:
        event = session.scalar(select(EmailOutbox))
        assert event is not None and event.state == "sent"
        assert event.attempt_count == 1
    from backend.app.email_outbox import queue_publication_notices

    with factory.begin() as session:
        publication = session.scalar(select(ResultPublication))
        assert publication is not None
        assert queue_publication_notices(session, publication) == 0
    assert client.get(f"/api/v1/contests/{contest_id}/results/review").status_code == 200

    public_list = client.get("/api/v1/public/contests")
    assert [row["slug"] for row in public_list.json()["items"]] == ["results-sprint"]
    result_response = client.get("/api/v1/public/contests/results-sprint/results")
    assert result_response.status_code == 200
    data = result_response.json()
    assert data["meta"]["total"] == 1
    row = data["items"][0]
    assert row["callsign"] == "EA7AAA"
    assert row["score"] == row["explanation"]["score"]
    assert row["explanation"]["format_version"] == 3
    assert isinstance(row["explanation"]["multiplier_counts"], dict)
    assert isinstance(row["explanation"]["bonus_counts"], dict)
    assert row["status"] == "scored"
    assert "score_run_id" not in row and "entry_id" not in row
    assert "qso_scores" not in row
    assert data["contest"]["publication"]["withheld_count"] == 1
    assert (
        client.get(
            "/api/v1/public/contests/results-sprint/results?category=operator&value=single"
        ).json()["meta"]["total"]
        == 1
    )
    assert (
        client.get("/api/v1/public/contests/results-sprint/results?status=checklog").json()["meta"][
            "total"
        ]
        == 0
    )

    json_export = client.get("/api/v1/public/contests/results-sprint/results/export?format=json")
    assert json_export.status_code == 200
    assert json_export.headers["X-Contestmaster-Export-Version"] == "results-v1"
    assert json_export.json()["items"][0]["score"] == row["score"]
    csv_export = client.get("/api/v1/public/contests/results-sprint/results/export?format=csv")
    assert csv_export.status_code == 200
    assert 'filename="results-sprint-results-v1.csv"' in csv_export.headers["Content-Disposition"]
    assert "EA7AAA" in csv_export.text and str(row["score"]) in csv_export.text
    assert "Private Operator Name" not in json_export.text
    assert "hidden private contact data" not in json_export.text

    with factory() as session:
        publication = session.scalar(select(ResultPublication))
        entry = session.scalar(select(ResultPublicationEntry))
        assert publication and publication.is_sealed
        assert entry and type(entry.score) is int
        entry.score += 1
        with pytest.raises(DBAPIError, match="immutable"):
            session.commit()
        session.rollback()
        assert session.scalar(select(ScoreRun).where(ScoreRun.id == selected[0])) is not None
        events = {event.action for event in session.scalars(select(AuditEvent))}
        assert "contest.results_generated" in events
        assert "contest.results_published" in events


def test_result_notice_outbox_retries_failures_and_deduplicates(result_db, monkeypatch):
    factory, contest_id, _manager_id, _outsider_id = result_db
    with factory.begin() as session:
        entry = session.scalar(select(Entry).where(Entry.contest_id == contest_id))
        assert entry is not None
        now = datetime.now(UTC)
        contact = GuestEntryEmail(
            entry_id=entry.id,
            email_normalized="retry@example.test",
            source="upload_prompt",
            access_opt_in=False,
            results_opt_in=True,
            verified_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(contact)
        publication = ResultPublication(
            contest_id=contest_id,
            publication_number=1,
            source_digest="b" * 64,
            entry_count=1,
            withheld_count=0,
            published_at=now,
            is_sealed=True,
        )
        session.add(publication)
        session.flush()
        event = EmailOutbox(
            event_key=f"published:{publication.id}:guest-email:{contact.id}",
            guest_email_id=contact.id,
            publication_id=publication.id,
            state="pending",
            attempt_count=0,
            available_at=now,
            created_at=now,
        )
        session.add(event)
    monkeypatch.setattr(
        "backend.app.email_outbox.get_settings",
        lambda: SimpleNamespace(
            email_smtp_host="mail.example.test",
            email_from_address="contestmaster@example.test",
            frontend_base_url="https://contestmaster.example.test",
        ),
    )
    attempts = 0

    def flaky_sender(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise TimeoutError("mail transport timeout")

    monkeypatch.setattr("backend.app.email_outbox.send_guest_result_notice", flaky_sender)
    from backend.app.email_outbox import dispatch_pending_emails

    assert dispatch_pending_emails(factory) == {
        "sent": 0,
        "cancelled": 0,
        "failed": 1,
        "pending": 0,
    }
    with factory.begin() as session:
        persisted = session.scalar(select(EmailOutbox))
        assert persisted is not None
        assert persisted.state == "pending"
        assert persisted.attempt_count == 1
        assert persisted.last_error == "TimeoutError"
        persisted.available_at = datetime.now(UTC) - timedelta(seconds=1)
    assert dispatch_pending_emails(factory) == {
        "sent": 1,
        "cancelled": 0,
        "failed": 0,
        "pending": 0,
    }
    assert dispatch_pending_emails(factory) == {
        "sent": 0,
        "cancelled": 0,
        "failed": 0,
        "pending": 0,
    }
    assert attempts == 2
    with factory() as session:
        persisted = session.scalar(select(EmailOutbox))
        assert persisted is not None and persisted.state == "sent"
        assert persisted.attempt_count == 2


def test_staging_guest_upload_scoring_publication_and_privacy_workflow(result_db):
    factory, contest_id, manager_id, _outsider_id = result_db
    manager = manager_client(factory, manager_id)
    csrf = manager.cookies.get("contestmaster_csrf")
    now = datetime.now(UTC)
    starts_at = now - timedelta(minutes=20)
    ends_at = now + timedelta(minutes=20)
    with factory.begin() as session:
        contest = session.get(Contest, contest_id)
        assert contest is not None
        payload = valid_payload()
        payload["ruleset_key"] = "phase9-staging"
        payload["version"] = "2026-live-staging"
        submission = next(rule["rule"] for rule in payload["rules"] if rule["id"] == "submission")
        submission["late_policy"] = "accept_late"
        payload["rules"] = [rule for rule in payload["rules"] if rule["id"] != "entity-multiplier"]
        format_rule = next(rule["rule"] for rule in payload["rules"] if rule["id"] == "format")
        format_rule["qso_columns"] = [
            "frequency",
            "mode",
            "date",
            "time",
            "callsign_sent",
            "rst_sent",
            "exchange_sent",
            "callsign_received",
            "rst_received",
            "exchange_received",
        ]
        format_rule["category_mappings"] = [
            {"external_value": "SINGLE-OP", "category_values": {"operator": "single"}}
        ]
        exchange = next(rule["rule"] for rule in payload["rules"] if rule["id"] == "exchange")
        for field in exchange["fields"]:
            field["required"] = False
        ruleset = save_ruleset_version(
            session,
            validate_ruleset(payload),
            created_by_user_id=manager_id,
        ).version
        contest.ruleset_version_id = ruleset.id
        contest.starts_at = starts_at
        contest.ends_at = ends_at
        contest.log_submission_cutoff_at = now + timedelta(days=2)
        contest.auto_recalculate_on_upload = True

    opened = manager.put(
        f"/api/v1/contests/{contest_id}/status",
        headers={"X-CSRF-Token": csrf},
        json={"status": "open"},
    )
    assert opened.status_code == 200, opened.text

    qso_time = (now - timedelta(minutes=10)).strftime("%H%M")
    log = (
        "START-OF-LOG\nCONTEST: Results Sprint\nCALLSIGN: EA7FLOW\n"
        "CATEGORY-OPERATOR: SINGLE-OP\n"
        f"QSO: 14025 CW {now:%Y-%m-%d} {qso_time} EA7FLOW 599 101 F4XYZ 599 202\n"
        "END-OF-LOG\n"
    )
    guest = TestClient(app)
    uploaded = guest.post(
        "/api/v1/public/contests/results-sprint/logs",
        headers={"Idempotency-Key": "phase9-stage-upload-01"},
        files={"file": ("workflow.log", log.encode(), "text/plain")},
    )
    assert uploaded.status_code == 201, uploaded.text
    receipt = uploaded.json()["receipt_token"]
    entry_id = uploaded.json()["entry_id"]
    assert uploaded.json()["summary"]["accepted_qsos"] == 1
    guest_score_run = next(
        run for run in uploaded.json()["score_runs"] if run["entry_id"] == entry_id
    )
    assert guest_score_run["status"] == "completed"
    assert (
        guest.get(
            f"/api/v1/public/entries/{entry_id}", headers={"X-Entry-Receipt": receipt}
        ).status_code
        == 200
    )

    closed = manager.put(
        f"/api/v1/contests/{contest_id}/status",
        headers={"X-CSRF-Token": csrf},
        json={"status": "closed"},
    )
    assert closed.status_code == 200, closed.text
    generated = manager.post(
        f"/api/v1/contests/{contest_id}/results/generate",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "phase9-stage-generate-01"},
        json={"reason": "Staging acceptance workflow"},
    )
    assert generated.status_code == 202, generated.text
    review = manager.get(f"/api/v1/contests/{contest_id}/results/review").json()
    guest_result = next(item for item in review["items"] if item["callsign"] == "EA7FLOW")
    assert guest_result["included_by_default"] is True
    selected = [item["score_run_id"] for item in review["items"] if item["included_by_default"]]
    publication = manager.post(
        f"/api/v1/contests/{contest_id}/results/publish",
        headers={"X-CSRF-Token": csrf},
        json={"score_run_ids": selected, "reason": "Staging acceptance workflow"},
    )
    assert publication.status_code == 201, publication.text

    public = TestClient(app)
    standings = public.get("/api/v1/public/contests/results-sprint/results")
    assert standings.status_code == 200
    assert "EA7FLOW" in {row["callsign"] for row in standings.json()["items"]}
    assert "F4XYZ" not in standings.text
    assert "operator@example.test" not in standings.text
    assert "exchange_received" not in standings.text
    assert public.get(f"/api/v1/public/entries/{entry_id}").status_code == 404


def test_azqp_2026_sponsor_fixture_scores_and_publishes_safe_explanation(result_db):
    fixture_path = (
        Path(__file__).parents[2]
        / "documentation/ruleset-parity/fixtures/arizona-qso-party-2026-cabrillo.json"
    )
    fixture = json.loads(fixture_path.read_text())
    expected = fixture["expected"]
    ruleset_payload = fixture["ruleset"]
    assert fixture["accepted_format"] == "cabrillo"
    assert ruleset_payload["source_url"] == fixture["rules_url"]
    assert ruleset_payload["version"] == fixture["ruleset_version"]

    factory, _existing_contest_id, manager_id, _outsider_id = result_db
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    contest_slug = "azqp-2026-parity"
    with factory.begin() as session:
        manager = session.get(SystemUser, manager_id)
        assert manager is not None
        # PH is the WWROF Cabrillo token for Phone, distinct from the SSB catalog
        # key. The baseline modes are globally editable; this test models the
        # active catalog supplied by migration 0029.
        catalog_items = (
            (
                BandCatalogItem,
                "40m",
                {
                    "label": "40 m",
                    "description": "40 m HF band",
                    "frequency_range": "7 MHz",
                    "sort_order": 1,
                    "contest_free": False,
                },
            ),
            (ModeCatalogItem, "CW", {"label": "CW", "description": "Morse code"}),
            (
                ModeCatalogItem,
                "PH",
                {
                    "label": "Phone (Cabrillo PH)",
                    "description": "Cabrillo log mode token for phone contacts",
                },
            ),
        )
        for model, key, values in catalog_items:
            item = session.scalar(select(model).where(model.key == key))
            if item is None:
                session.add(model(key=key, is_active=True, **values))
            else:
                item.is_active = True
        session.flush()
    manager = manager_client(factory, manager_id)
    headers = {"X-CSRF-Token": manager.cookies.get("contestmaster_csrf")}
    validation_client = TestClient(app)
    validation = validation_client.post("/api/v1/rulesets/validate", json=ruleset_payload)
    assert validation.status_code == 200, validation.text

    with factory.begin() as session:
        ruleset = save_ruleset_version(
            session,
            validate_ruleset(ruleset_payload),
            created_by_user_id=manager_id,
        ).version
        session.add(
            Contest(
                owner_user_id=manager_id,
                ruleset_version_id=ruleset.id,
                name="Arizona QSO Party 2026 fixture",
                slug=contest_slug,
                starts_at=now - timedelta(minutes=5),
                ends_at=now + timedelta(minutes=30),
                log_submission_cutoff_at=now + timedelta(days=10),
                status=ContestStatus.OPEN,
            )
        )
        session.flush()
        contest_id = session.scalar(select(Contest.id).where(Contest.slug == contest_slug))
        assert contest_id is not None

    with TestClient(app) as client:
        uploaded_at = datetime.now(UTC).replace(second=0, microsecond=0)
        lines = [
            "START-OF-LOG: 3.0",
            f"CONTEST: {contest_slug}",
            f"CALLSIGN: {fixture['entrant']['callsign']}",
            "EMAIL: k1out@nomail.invalid",
            "NAME: Private Synthetic Operator",
            f"CATEGORY-OPERATOR: {fixture['entrant']['category_operator']}",
        ]
        for index, contact in enumerate(fixture["contacts"], start=1):
            timestamp = uploaded_at + timedelta(minutes=index)
            lines.append(
                f"QSO: 7048 {contact['mode']} {timestamp:%Y-%m-%d} {timestamp:%H%M} "
                f"{fixture['entrant']['callsign']} 599 {fixture['entrant']['state']} "
                f"{contact['worked_callsign']} 599 {contact['county']}"
            )
        lines.append("END-OF-LOG:")
        log_content = "\n".join(lines) + "\n"
        uploaded = client.post(
            f"/api/v1/public/contests/{contest_slug}/logs",
            headers={"Idempotency-Key": "azqp-fixture-upload-2026"},
            files={"file": ("azqp-2026.log", log_content.encode(), "text/plain")},
        )
        assert uploaded.status_code == 201, uploaded.text
        assert uploaded.json()["summary"]["accepted_qsos"] == expected["credited_qsos"]

        closed = manager.put(
            f"/api/v1/contests/{contest_id}/status",
            headers=headers,
            json={"status": "closed"},
        )
        assert closed.status_code == 200, closed.text
        generated = manager.post(
            f"/api/v1/contests/{contest_id}/results/generate",
            headers={**headers, "Idempotency-Key": "azqp-fixture-generate-2026"},
            json={"reason": "Sponsor-linked 2026 AZQP conformance fixture"},
        )
        assert generated.status_code == 202, generated.text
        review = manager.get(f"/api/v1/contests/{contest_id}/results/review")
        assert review.status_code == 200, review.text
        candidate = next(
            item
            for item in review.json()["items"]
            if item["callsign"] == fixture["entrant"]["callsign"]
        )
        assert candidate["included_by_default"] is True
        assert candidate["score"] == expected["final_score"], candidate
        score_explanation = candidate["explanation"]
        assert score_explanation["multiplier_counts"] == expected["multiplier_counts"]
        assert score_explanation["bonus_counts"] == expected["bonus_counts"]

        with factory() as session:
            run = session.get(ScoreRun, candidate["score_run_id"])
            assert run is not None
            assert run.points == expected["qso_points"]
            assert run.multiplier_count == sum(expected["multiplier_counts"].values())
            assert run.bonus_points == expected["bonus_points"]
            assert run.penalty_points == expected["penalty_points"]
            assert run.final_score == expected["final_score"]
            qso_scores = list(
                session.scalars(
                    select(QsoScore)
                    .where(QsoScore.score_run_id == run.id)
                    .order_by(QsoScore.qso_id)
                )
            )
            assert len(qso_scores) == expected["credited_qsos"]
            assert sum(row.points for row in qso_scores) == expected["qso_points"]
            assert sum(row.bonus_points for row in qso_scores) == expected["bonus_points"]

        published = manager.post(
            f"/api/v1/contests/{contest_id}/results/publish",
            headers=headers,
            json={
                "score_run_ids": [candidate["score_run_id"]],
                "reason": "Sponsor-linked 2026 AZQP conformance fixture",
            },
        )
        assert published.status_code == 201, published.text

        public = TestClient(app)
        standings = public.get(f"/api/v1/public/contests/{contest_slug}/results")
        assert standings.status_code == 200, standings.text
        assert len(standings.json()["items"]) == 1
        public_entry = standings.json()["items"][0]
        assert public_entry["callsign"] == fixture["entrant"]["callsign"]
        explanation = public_entry["explanation"]
        assert explanation["points"] == expected["qso_points"]
        assert explanation["multiplier_counts"] == expected["multiplier_counts"]
        assert explanation["bonus_counts"] == expected["bonus_counts"]
        assert explanation["bonus_points"] == expected["bonus_points"]
        assert explanation["penalty_points"] == expected["penalty_points"]
        assert explanation["score"] == expected["final_score"]
        for private_value in (
            "K7A",
            "K7B",
            "K7C",
            "K7D",
            "APH",
            "NY",
            "k1out@nomail.invalid",
            "Private Synthetic Operator",
            "exchange_received",
        ):
            assert private_value not in standings.text


def test_cqww_2026_sponsor_fixture_uses_contest_pinned_geography_and_separate_counts(result_db):
    fixture_path = (
        Path(__file__).parents[2]
        / "documentation/ruleset-parity/fixtures/cq-ww-dx-2026-cw-cabrillo.json"
    )
    fixture = json.loads(fixture_path.read_text())
    expected = fixture["expected"]
    ruleset_payload = fixture["ruleset"]
    factory, _existing_contest_id, manager_id, _outsider_id = result_db
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    contest_slug = "cqww-2026-parity"

    with factory.begin() as session:
        for model, key, values in (
            (
                BandCatalogItem,
                "20m",
                {
                    "label": "20 m",
                    "description": "20 m HF band",
                    "frequency_range": "14 MHz",
                    "sort_order": 2,
                    "contest_free": False,
                },
            ),
            (ModeCatalogItem, "CW", {"label": "CW", "description": "Morse code"}),
        ):
            item = session.scalar(select(model).where(model.key == key))
            if item is None:
                session.add(model(key=key, is_active=True, **values))
            else:
                item.is_active = True
        session.flush()

    manager = manager_client(factory, manager_id)
    headers = {"X-CSRF-Token": manager.cookies.get("contestmaster_csrf")}
    validation = TestClient(app).post("/api/v1/rulesets/validate", json=ruleset_payload)
    assert validation.status_code == 200, validation.text

    with factory.begin() as session:
        source = MasterDataSource(
            source_key="fixture-cty",
            name="Synthetic CTY fixture",
            canonical_url="https://www.country-files.com/",
            authority_role=MasterDataAuthorityRole.PRIMARY_OPERATIONAL,
        )
        session.add(source)
        session.flush()
        sync = MasterDataSyncRun(
            source_id=source.id,
            dataset_key="cty",
            status=MasterDataRunStatus.SUCCEEDED,
            finished_at=now,
            retrieved_at=now,
            source_url=fixture["rules_url"],
        )
        session.add(sync)
        session.flush()
        version = MasterDataVersion(
            sync_run_id=sync.id,
            dataset_key="cty",
            retrieved_at=now,
            checksum="a" * 64,
            valid_from=now - timedelta(days=1),
            status=MasterDataVersionStatus.RETIRED,
        )
        session.add(version)
        session.flush()
        entity_rows = {}
        for code, continent in (("K", "NA"), ("EA", "EU"), ("VE", "NA")):
            entity = ContestEntity(
                version_id=version.id,
                namespace="cty",
                authority_code=code,
                name=f"Fixture entity {code}",
                continent=continent,
                entity_type=EntityType.CONTEST_ENTITY,
            )
            session.add(entity)
            entity_rows[code] = entity
        zone_rows = {}
        for code in ("04", "05", "14"):
            zone = CQZone(version_id=version.id, code=code, name=f"Fixture zone {code}")
            session.add(zone)
            zone_rows[code] = zone
        session.flush()
        for prefix_text, entity_code, zone_code in (
            ("K", "K", "05"),
            ("W", "K", "05"),
            ("EA", "EA", "14"),
            ("VE", "VE", "04"),
        ):
            prefix = CallsignPrefix(
                version_id=version.id,
                prefix_pattern=prefix_text,
                allocation_type="prefix",
            )
            session.add(prefix)
            session.flush()
            session.add_all(
                [
                    PrefixEntityAssignment(
                        version_id=version.id,
                        prefix_id=prefix.id,
                        entity_id=entity_rows[entity_code].id,
                        source_note="Synthetic fixture mapping",
                    ),
                    PrefixCQZoneAssignment(
                        version_id=version.id,
                        prefix_id=prefix.id,
                        cq_zone_id=zone_rows[zone_code].id,
                    ),
                ]
            )
        ruleset = save_ruleset_version(
            session,
            validate_ruleset(ruleset_payload),
            created_by_user_id=manager_id,
        ).version
        contest = Contest(
            owner_user_id=manager_id,
            ruleset_version_id=ruleset.id,
            name="CQ WW DX 2026 CW fixture",
            slug=contest_slug,
            starts_at=now - timedelta(minutes=5),
            ends_at=now + timedelta(minutes=30),
            log_submission_cutoff_at=now + timedelta(days=10),
            status=ContestStatus.OPEN,
        )
        session.add(contest)
        session.flush()
        session.add(
            ContestMasterDataVersion(
                contest_id=contest.id,
                dataset_key="cty",
                master_data_version_id=version.id,
                pinned_at=now,
            )
        )
        contest_id = contest.id
        version_id = version.id

    with TestClient(app) as client:
        uploaded_at = datetime.now(UTC).replace(second=0, microsecond=0)
        lines = [
            "START-OF-LOG: 3.0",
            f"CONTEST: {contest_slug}",
            f"CALLSIGN: {fixture['entrant']['callsign']}",
            "EMAIL: k1out@nomail.invalid",
            "NAME: Private CQ WW Fixture Operator",
            f"CATEGORY-OPERATOR: {fixture['entrant']['category_operator']}",
        ]
        for index, contact in enumerate(fixture["contacts"], start=1):
            timestamp = uploaded_at + timedelta(minutes=index)
            lines.append(
                f"QSO: 14025 CW {timestamp:%Y-%m-%d} {timestamp:%H%M} "
                f"{fixture['entrant']['callsign']} 599 {fixture['entrant']['cq_zone']} "
                f"{contact['worked_callsign']} 599 {contact['cq_zone']}"
            )
        lines.append("END-OF-LOG:")
        uploaded = client.post(
            f"/api/v1/public/contests/{contest_slug}/logs",
            headers={"Idempotency-Key": "cqww-fixture-upload-2026"},
            files={"file": ("cqww-2026.log", ("\n".join(lines) + "\n").encode(), "text/plain")},
        )
        assert uploaded.status_code == 201, uploaded.text
        assert uploaded.json()["summary"]["accepted_qsos"] == expected["credited_qsos"]

        with factory() as session:
            resolved_version_ids = set(
                session.scalars(
                    select(Qso.resolved_master_data_version_id).where(
                        Qso.entry_revision_id
                        == session.scalar(
                            select(EntryRevision.id).order_by(EntryRevision.id.desc())
                        )
                    )
                )
            )
            assert resolved_version_ids <= {None, version_id}

        closed = manager.put(
            f"/api/v1/contests/{contest_id}/status", headers=headers, json={"status": "closed"}
        )
        assert closed.status_code == 200, closed.text
        generated = manager.post(
            f"/api/v1/contests/{contest_id}/results/generate",
            headers={**headers, "Idempotency-Key": "cqww-fixture-generate-2026"},
            json={"reason": "Sponsor-linked CQ WW DX 2026 fixture"},
        )
        assert generated.status_code == 202, generated.text
        review = manager.get(f"/api/v1/contests/{contest_id}/results/review").json()
        candidate = next(item for item in review["items"] if item["callsign"] == "K1OUT")
        assert candidate["included_by_default"] is True, {
            key: candidate.get(key) for key in ("result_status", "score", "explanation")
        }
        assert candidate["score"] == expected["final_score"]
        assert candidate["explanation"]["multiplier_counts"] == expected["multiplier_counts"]
        assert candidate["explanation"]["bonus_counts"] == expected["bonus_counts"]
        with factory() as session:
            run = session.get(ScoreRun, candidate["score_run_id"])
            assert run is not None
            assert run.master_data_snapshot == {"cty": version_id}
            assert run.points == expected["qso_points"]
            assert run.multiplier_count == sum(expected["multiplier_counts"].values())
            assert run.bonus_points == expected["bonus_points"]
            assert run.penalty_points == expected["penalty_points"]
            assert run.final_score == expected["final_score"]

        published = manager.post(
            f"/api/v1/contests/{contest_id}/results/publish",
            headers=headers,
            json={"score_run_ids": [candidate["score_run_id"]]},
        )
        assert published.status_code == 201, published.text
        standings = TestClient(app).get(f"/api/v1/public/contests/{contest_slug}/results")
        assert standings.status_code == 200, standings.text
        assert len(standings.json()["items"]) == 1
        public_entry = standings.json()["items"][0]
        assert public_entry["score"] == expected["final_score"]
        explanation = public_entry["explanation"]
        assert explanation["points"] == expected["qso_points"]
        assert explanation["multiplier_counts"] == expected["multiplier_counts"]
        assert explanation["bonus_counts"] == expected["bonus_counts"]
        assert explanation["penalty_points"] == expected["penalty_points"]
        assert explanation["score"] == expected["final_score"]
        for private_value in (
            "EA7AAA",
            "W1AW",
            "VE3ABC",
            "k1out@nomail.invalid",
            "Private CQ WW Fixture Operator",
        ):
            assert private_value not in standings.text


def test_rsgb_2026_sponsor_fixture_scores_distance_and_session_resets_end_to_end(result_db):
    fixture_path = (
        Path(__file__).parents[2]
        / "documentation/ruleset-parity/fixtures/rsgb-vhf-2026-distance-sessions-cabrillo.json"
    )
    fixture = json.loads(fixture_path.read_text())
    expected = fixture["expected"]
    ruleset_payload = fixture["ruleset"]
    factory, _existing_contest_id, manager_id, _outsider_id = result_db
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    contest_slug = "rsgb-vhf-2026-parity"
    contest_start = now - timedelta(minutes=80)

    with factory.begin() as session:
        for model, key, values in (
            (
                BandCatalogItem,
                "2m",
                {
                    "label": "2 m",
                    "description": "2 m VHF band",
                    "frequency_range": "144 MHz",
                    "sort_order": 20,
                    "contest_free": False,
                },
            ),
            (ModeCatalogItem, "CW", {"label": "CW", "description": "Morse code"}),
        ):
            item = session.scalar(select(model).where(model.key == key))
            if item is None:
                session.add(model(key=key, is_active=True, **values))
            else:
                item.is_active = True
        session.flush()

    manager = manager_client(factory, manager_id)
    headers = {"X-CSRF-Token": manager.cookies.get("contestmaster_csrf")}
    validation = TestClient(app).post("/api/v1/rulesets/validate", json=ruleset_payload)
    assert validation.status_code == 200, validation.text

    with factory.begin() as session:
        ruleset = save_ruleset_version(
            session,
            validate_ruleset(ruleset_payload),
            created_by_user_id=manager_id,
        ).version
        contest = Contest(
            owner_user_id=manager_id,
            ruleset_version_id=ruleset.id,
            name="RSGB VHF distance and sessions 2026 fixture",
            slug=contest_slug,
            starts_at=contest_start,
            ends_at=now + timedelta(minutes=30),
            log_submission_cutoff_at=now + timedelta(days=10),
            status=ContestStatus.OPEN,
        )
        session.add(contest)
        session.flush()
        contest_id = contest.id

    with TestClient(app) as client:
        lines = [
            "START-OF-LOG: 3.0",
            f"CONTEST: {contest_slug}",
            f"CALLSIGN: {fixture['entrant']['callsign']}",
            "EMAIL: g0out@nomail.invalid",
            "NAME: Private Synthetic Operator",
            f"GRID-LOCATOR: {fixture['entrant']['grid']}",
            f"CATEGORY-OPERATOR: {fixture['entrant']['category_operator']}",
        ]
        for contact, offset_minutes in zip(fixture["contacts"], (10, 70), strict=True):
            timestamp = contest_start + timedelta(minutes=offset_minutes)
            lines.append(
                f"QSO: 144050 CW {timestamp:%Y-%m-%d} {timestamp:%H%M} "
                f"{fixture['entrant']['callsign']} 599 {contact['sent_serial']:03} "
                f"{contact['worked_callsign']} 599 {contact['received_grid']}"
            )
        lines.append("END-OF-LOG:")
        uploaded = client.post(
            f"/api/v1/public/contests/{contest_slug}/logs",
            headers={"Idempotency-Key": "rsgb-distance-session-fixture-2026"},
            files={
                "file": (
                    "rsgb-vhf-2026.log",
                    ("\n".join(lines) + "\n").encode(),
                    "text/plain",
                )
            },
        )
        assert uploaded.status_code == 201, uploaded.text
        assert uploaded.json()["summary"]["accepted_qsos"] == expected["credited_qsos"]

        closed = manager.put(
            f"/api/v1/contests/{contest_id}/status",
            headers=headers,
            json={"status": "closed"},
        )
        assert closed.status_code == 200, closed.text
        generated = manager.post(
            f"/api/v1/contests/{contest_id}/results/generate",
            headers={**headers, "Idempotency-Key": "rsgb-fixture-generate-2026"},
            json={"reason": "Sponsor-linked RSGB distance and session fixture"},
        )
        assert generated.status_code == 202, generated.text
        review = manager.get(f"/api/v1/contests/{contest_id}/results/review")
        assert review.status_code == 200, review.text
        candidate = next(
            item
            for item in review.json()["items"]
            if item["callsign"] == fixture["entrant"]["callsign"]
        )
        assert candidate["included_by_default"] is True
        assert candidate["score"] == expected["final_score"], candidate

        with factory() as session:
            run = session.get(ScoreRun, candidate["score_run_id"])
            assert run is not None
            assert run.points == expected["qso_points"]
            assert run.final_score == expected["final_score"]
            qso_scores = list(
                session.scalars(
                    select(QsoScore)
                    .where(QsoScore.score_run_id == run.id)
                    .order_by(QsoScore.qso_id)
                )
            )
            assert [row.points for row in qso_scores] == [
                contact["expected_points"] for contact in fixture["contacts"]
            ]
            assert [row.session_number for row in qso_scores] == [
                contact["expected_session"] for contact in fixture["contacts"]
            ]
            assert all(row.status == "credited" for row in qso_scores)

        published = manager.post(
            f"/api/v1/contests/{contest_id}/results/publish",
            headers=headers,
            json={
                "score_run_ids": [candidate["score_run_id"]],
                "reason": "Sponsor-linked RSGB distance and session fixture",
            },
        )
        assert published.status_code == 201, published.text
        public = TestClient(app)
        standings = public.get(f"/api/v1/public/contests/{contest_slug}/results")
        assert standings.status_code == 200, standings.text
        public_entry = standings.json()["items"][0]
        assert public_entry["explanation"]["points"] == expected["qso_points"]
        assert public_entry["explanation"]["score"] == expected["final_score"]
        assert "G1GRID" not in standings.text
        assert "g0out@nomail.invalid" not in standings.text
        assert "Private Synthetic Operator" not in standings.text


def test_sarl_zs2_2026_sponsor_fixture_scores_adif_exchange_end_to_end(result_db):
    fixture_path = (
        Path(__file__).parents[2]
        / "documentation/ruleset-parity/fixtures/sarl-zs2-qso-party-2026-adif.json"
    )
    fixture = json.loads(fixture_path.read_text())
    expected = fixture["expected"]
    ruleset_payload = fixture["ruleset"]
    factory, _existing_contest_id, manager_id, _outsider_id = result_db
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    contest_slug = "sarl-zs2-2026-adif-parity"

    with factory.begin() as session:
        for model, key, values in (
            (
                BandCatalogItem,
                "40m",
                {
                    "label": "40 m",
                    "description": "40 m HF band",
                    "frequency_range": "7 MHz",
                    "sort_order": 1,
                    "contest_free": False,
                },
            ),
            (ModeCatalogItem, "CW", {"label": "CW", "description": "Morse code"}),
        ):
            item = session.scalar(select(model).where(model.key == key))
            if item is None:
                session.add(model(key=key, is_active=True, **values))
            else:
                item.is_active = True
        session.flush()

    manager = manager_client(factory, manager_id)
    headers = {"X-CSRF-Token": manager.cookies.get("contestmaster_csrf")}
    validation = TestClient(app).post("/api/v1/rulesets/validate", json=ruleset_payload)
    assert validation.status_code == 200, validation.text

    with factory.begin() as session:
        ruleset = save_ruleset_version(
            session,
            validate_ruleset(ruleset_payload),
            created_by_user_id=manager_id,
        ).version
        contest = Contest(
            owner_user_id=manager_id,
            ruleset_version_id=ruleset.id,
            name="SARL ZS2 QSO Party 2026 ADIF fixture",
            slug=contest_slug,
            starts_at=now - timedelta(minutes=10),
            ends_at=now + timedelta(minutes=30),
            log_submission_cutoff_at=now + timedelta(days=10),
            status=ContestStatus.OPEN,
        )
        session.add(contest)
        session.flush()
        contest_id = contest.id

    with TestClient(app) as client:
        log_lines = [
            "<ADIF_VER:5>3.1.4",
            f"<STATION_CALLSIGN:{len(fixture['entrant']['callsign'])}>{fixture['entrant']['callsign']}",
            f"<CATEGORY-OPERATOR:{len(fixture['entrant']['category_operator'])}>{fixture['entrant']['category_operator']}",
            "<EOH>",
        ]
        for index, contact in enumerate(fixture["contacts"], start=1):
            timestamp = now + timedelta(minutes=index)
            qso_fields = (
                ("QSO_DATE", timestamp.strftime("%Y%m%d")),
                ("TIME_ON", timestamp.strftime("%H%M%S")),
                ("CALL", contact["worked_callsign"]),
                ("BAND", "40M"),
                ("MODE", "CW"),
                ("RST_SENT", "599"),
                ("RST_RCVD", "599"),
                ("STX_STRING", contact["sent_area"]),
                ("SRX_STRING", contact["received_area"]),
            )
            log_lines.append(
                "".join(f"<{name}:{len(value)}>{value}" for name, value in qso_fields) + "<EOR>"
            )
        log_content = "\n".join(log_lines) + "\n"
        uploaded = client.post(
            f"/api/v1/public/contests/{contest_slug}/logs",
            headers={"Idempotency-Key": "sarl-zs2-adif-fixture-2026"},
            files={
                "file": (
                    "K1OUT-SARL-ZS2-QSO-Party.adi",
                    log_content.encode(),
                    "text/plain",
                )
            },
        )
        assert uploaded.status_code == 201, uploaded.text
        assert uploaded.json()["summary"]["accepted_qsos"] == expected["credited_qsos"]

        closed = manager.put(
            f"/api/v1/contests/{contest_id}/status",
            headers=headers,
            json={"status": "closed"},
        )
        assert closed.status_code == 200, closed.text
        generated = manager.post(
            f"/api/v1/contests/{contest_id}/results/generate",
            headers={**headers, "Idempotency-Key": "sarl-adif-fixture-generate-2026"},
            json={"reason": "Sponsor-linked SARL ADIF scoring fixture"},
        )
        assert generated.status_code == 202, generated.text
        review = manager.get(f"/api/v1/contests/{contest_id}/results/review")
        assert review.status_code == 200, review.text
        candidate = next(
            item
            for item in review.json()["items"]
            if item["callsign"] == fixture["entrant"]["callsign"]
        )
        assert candidate["included_by_default"] is True
        assert candidate["score"] == expected["final_score"]

        with factory() as session:
            run = session.get(ScoreRun, candidate["score_run_id"])
            assert run is not None
            assert run.points == expected["qso_points"]
            assert run.multiplier_count == 0
            assert run.bonus_points == expected["bonus_points"]
            assert run.penalty_points == expected["penalty_points"]
            qso_scores = list(
                session.scalars(
                    select(QsoScore)
                    .where(QsoScore.score_run_id == run.id)
                    .order_by(QsoScore.qso_id)
                )
            )
            assert [row.points for row in qso_scores] == [
                contact["qso_points"] for contact in fixture["contacts"]
            ]

        published = manager.post(
            f"/api/v1/contests/{contest_id}/results/publish",
            headers=headers,
            json={
                "score_run_ids": [candidate["score_run_id"]],
                "reason": "Sponsor-linked SARL ADIF scoring fixture",
            },
        )
        assert published.status_code == 201, published.text
        standings = TestClient(app).get(f"/api/v1/public/contests/{contest_slug}/results")
        assert standings.status_code == 200, standings.text
        assert standings.json()["items"][0]["explanation"]["score"] == expected["final_score"]
        assert "ZS2PE" not in standings.text


def test_unpublishing_hides_snapshot_without_deleting_it_and_foreign_result_id_is_private(
    result_db,
):
    factory, contest_id, manager_id, _outsider_id = result_db
    client = manager_client(factory, manager_id)
    headers = {"X-CSRF-Token": client.cookies.get("contestmaster_csrf")}
    generated = client.post(
        f"/api/v1/contests/{contest_id}/results/generate",
        headers={**headers, "Idempotency-Key": "phase8-generate-02"},
        json={},
    )
    review = client.get(f"/api/v1/contests/{contest_id}/results/review").json()
    selected = [item["score_run_id"] for item in review["items"] if item["included_by_default"]]
    publication = client.post(
        f"/api/v1/contests/{contest_id}/results/publish",
        headers=headers,
        json={"score_run_ids": selected},
    )
    assert generated.status_code == 202
    assert publication.status_code == 201
    published_id = client.get("/api/v1/public/contests/results-sprint/results").json()["items"][0][
        "id"
    ]
    assert (
        client.get(
            f"/api/v1/public/contests/results-sprint/results/entries/{published_id}"
        ).status_code
        == 200
    )

    closed = client.put(
        f"/api/v1/contests/{contest_id}/status",
        headers=headers,
        json={"status": "closed", "audit_reason": "Temporarily withdraw publication"},
    )
    assert closed.status_code == 200
    assert client.get("/api/v1/public/contests/results-sprint/results").status_code == 404
    assert (
        client.get("/api/v1/public/contests/results-sprint/results/entries/999999").status_code
        == 404
    )
    with factory() as session:
        assert session.query(ResultPublication).count() == 1
