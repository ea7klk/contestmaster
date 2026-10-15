import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
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
    Contest,
    ContestStatus,
    Entry,
    EntryRevision,
    EntryStatus,
    Participant,
    Qso,
    ResultPublication,
    ResultPublicationEntry,
    ScoreRun,
    Station,
    SystemRole,
    SystemUser,
)
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


def test_manager_generates_reviews_publishes_snapshot_and_exports_consistently(result_db):
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
