from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.adjudication.scoring import (
    recalculate_contest,
    score_entry_revision,
)
from backend.app.api.auth import issue_session
from backend.app.db import Base, get_session
from backend.app.main import app
from backend.app.models import (
    AuditEvent,
    Contest,
    ContestMasterDataVersion,
    ContestStatus,
    Entry,
    EntryRevision,
    MasterDataSource,
    MasterDataSyncRun,
    MasterDataVersion,
    MasterDataVersionStatus,
    Participant,
    Qso,
    QsoDecision,
    QsoDecisionSource,
    QsoDecisionStatus,
    QsoScore,
    RulesetVersion,
    ScoreRun,
    ScoreRunStatus,
    Station,
    SystemRole,
    SystemUser,
)
from backend.app.models.enums import EntityType
from backend.app.models.master_data import (
    CallsignPrefix,
    ContestEntity,
    PrefixEntityAssignment,
)
from backend.app.rulesets.persistence import save_ruleset_version
from backend.app.rulesets.validation import validate_ruleset
from backend.tests.test_rulesets import valid_payload

START = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def scoring_db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory.begin() as session:
        manager = SystemUser(
            username="scoring-manager",
            email_normalized="score@example.test",
            display_name="Scoring Manager",
            role=SystemRole.CONTEST_MANAGER,
            password_hash="unused-test-hash",
        )
        participant = Participant(callsign_submitted="EA7KLK", callsign_normalized="EA7KLK")
        session.add_all([manager, participant])
        session.flush()
        payload = valid_payload()
        payload["rules"] = [item for item in payload["rules"] if item["id"] != "entity-multiplier"]
        exchange = next(item for item in payload["rules"] if item["id"] == "exchange")
        for field in exchange["rule"]["fields"]:
            field["required"] = False
        persisted = save_ruleset_version(
            session, validate_ruleset(payload), created_by_user_id=manager.id
        )
        contest = Contest(
            owner_user_id=manager.id,
            ruleset_version_id=persisted.version.id,
            name="Test Contest",
            slug="test-contest",
            starts_at=START,
            ends_at=START + timedelta(hours=2),
            log_submission_cutoff_at=START + timedelta(days=1),
            status=ContestStatus.CLOSED,
            auto_recalculate_on_upload=True,
        )
        session.add(contest)
        session.flush()
        entry = Entry(
            contest_id=contest.id,
            participant_id=participant.id,
            entry_key="entry-one",
            category_values={"operator": "single"},
        )
        session.add(entry)
        session.flush()
        revision = EntryRevision(
            entry_id=entry.id,
            revision_number=1,
            input_format="cabrillo",
            storage_key="database://test/1",
            original_content="START-OF-LOG\nEND-OF-LOG",
            import_metadata={"headers": {"CLAIMED-SCORE": ["41"]}},
            content_sha256="a" * 64,
            byte_size=22,
            submitted_at=START,
        )
        session.add(revision)
        session.flush()
        station = Station(
            entry_revision_id=revision.id,
            callsign_submitted="EA7KLK",
            callsign_normalized="EA7KLK",
        )
        session.add(station)
        session.flush()
        for index, instant in enumerate((START, START + timedelta(minutes=1)), start=1):
            session.add(
                Qso(
                    entry_revision_id=revision.id,
                    station_id=station.id,
                    source_line_number=index,
                    occurred_at=instant,
                    callsign_submitted="F4ABC",
                    callsign_normalized="F4ABC",
                    band="20M",
                    mode="CW",
                    exchange_sent_submitted={},
                    exchange_received_submitted={},
                )
            )
        session.flush()
    try:
        yield factory, contest.id, entry.id, revision.id
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_scoring_creates_integer_auditable_run_and_is_idempotent(scoring_db):
    factory, contest_id, entry_id, revision_id = scoring_db
    with factory.begin() as session:
        run = score_entry_revision(
            session,
            entry_id=entry_id,
            revision_id=revision_id,
            idempotency_key="manual-run-1",
        )
        assert run.status is ScoreRunStatus.COMPLETED
        assert run.points == 2
        assert run.bonus_points == 5
        assert run.final_score == 5
        assert run.adjudicated_score is None
        assert run.claimed_points == 41
        assert isinstance(run.final_score, int)
        scores = list(session.scalars(select(QsoScore).where(QsoScore.score_run_id == run.id)))
        assert [row.status for row in scores] == ["credited", "not_credited"]
        assert scores[0].points == 2 and scores[0].bonus_points == 0
        again = score_entry_revision(
            session,
            entry_id=entry_id,
            revision_id=revision_id,
            idempotency_key="manual-run-1",
        )
        assert again.id == run.id
        assert session.query(ScoreRun).count() == 1


def test_received_grid_exchange_is_exposed_to_multiplier_scoring(scoring_db):
    factory, _contest_id, entry_id, revision_id = scoring_db
    with factory.begin() as session:
        contest = session.get(Contest, _contest_id)
        current_ruleset = session.get(RulesetVersion, contest.ruleset_version_id)
        config = dict(current_ruleset.configuration)
        config["version"] = "grid-multiplier"
        exchange_rule = next(item for item in config["rules"] if item["id"] == "exchange")
        exchange_rule["rule"]["fields"].append(
            {
                "key": "grid",
                "label": "Grid",
                "value_type": "grid",
                "direction": "both",
                "required": True,
            }
        )
        config["rules"].append(
            {
                "id": "grid-multiplier",
                "rule": {
                    "kind": "multiplier",
                    "source_fact": "qso.grid",
                    "scope": "band",
                    "label": "Grid square",
                },
            }
        )
        persisted = save_ruleset_version(session, validate_ruleset(config), created_by_user_id=None)
        contest.ruleset_version_id = persisted.version.id
        qsos = list(
            session.scalars(
                select(Qso).where(Qso.entry_revision_id == revision_id).order_by(Qso.id)
            )
        )
        for index, (qso, callsign, grid) in enumerate(
            zip(qsos, ("F4ABC", "VE3XYZ"), ("JN18", "FN31"), strict=True), start=1
        ):
            qso.callsign_submitted = callsign
            qso.callsign_normalized = callsign
            qso.exchange_sent_submitted = {
                "raw": "599 1",
                "rst": "599",
                "values": {"serial": index, "grid": "FN20"},
            }
            qso.exchange_received_submitted = {
                "raw": "599 1",
                "rst": "599",
                "values": {"serial": index, "grid": grid},
            }
        run = score_entry_revision(
            session,
            entry_id=entry_id,
            revision_id=revision_id,
            idempotency_key="grid-multiplier-run",
        )

        assert run.status is ScoreRunStatus.COMPLETED
        assert run.multiplier_count == 2
        persisted_scores = list(
            session.scalars(
                select(QsoScore).where(QsoScore.score_run_id == run.id).order_by(QsoScore.qso_id)
            )
        )
        assert [score.multiplier_count for score in persisted_scores] == [1, 1]
        assert all(score.status == "credited" for score in persisted_scores)


def test_distance_scoring_uses_persisted_entrant_and_received_grid_values(scoring_db):
    factory, _contest_id, entry_id, revision_id = scoring_db
    with factory.begin() as session:
        contest = session.get(Contest, _contest_id)
        current_ruleset = session.get(RulesetVersion, contest.ruleset_version_id)
        config = dict(current_ruleset.configuration)
        config["version"] = "distance-scoring"
        exchange_rule = next(item for item in config["rules"] if item["id"] == "exchange")
        exchange_rule["rule"]["fields"].append(
            {
                "key": "grid",
                "label": "Grid",
                "value_type": "grid",
                "direction": "received",
                "required": False,
            }
        )
        config["rules"].append(
            {
                "id": "distance",
                "rule": {
                    "kind": "distance_points",
                    "grid_field": "grid",
                    "precision": 6,
                    "points_per_kilometer": 1,
                    "same_grid_points": 1,
                },
            }
        )
        persisted = save_ruleset_version(session, validate_ruleset(config), created_by_user_id=None)
        contest.ruleset_version_id = persisted.version.id
        revision = session.get(EntryRevision, revision_id)
        revision.import_metadata = {"headers": {"GRID-LOCATOR": ["IO91AA"]}}
        station = session.scalar(select(Station).where(Station.entry_revision_id == revision_id))
        station.grid_submitted = "IO91AA"
        qsos = list(
            session.scalars(
                select(Qso).where(Qso.entry_revision_id == revision_id).order_by(Qso.id)
            )
        )
        for index, (qso, callsign, grid) in enumerate(
            zip(qsos, ("F4ABC", "VE3XYZ"), ("IO91AA", "IO91AA"), strict=True)
        ):
            qso.callsign_submitted = callsign
            qso.callsign_normalized = callsign
            qso.exchange_received_submitted = {"raw": grid, "values": {"grid": grid}}
            if index == 0:
                qso.exchange_sent_submitted = {
                    "values": {"grid": "IO91AB"},
                }

        run = score_entry_revision(
            session,
            entry_id=entry_id,
            revision_id=revision_id,
            idempotency_key="distance-scoring-run",
        )

        assert run.status is ScoreRunStatus.COMPLETED
        scores = list(
            session.scalars(
                select(QsoScore).where(QsoScore.score_run_id == run.id).order_by(QsoScore.qso_id)
            )
        )
        assert run.points == 10
        assert [score.points for score in scores] == [7, 3]
        assert all(score.status == "credited" for score in scores)


def test_distance_scoring_does_not_reuse_legacy_location_as_grid(scoring_db):
    factory, _contest_id, entry_id, revision_id = scoring_db
    with factory.begin() as session:
        contest = session.get(Contest, _contest_id)
        current_ruleset = session.get(RulesetVersion, contest.ruleset_version_id)
        config = dict(current_ruleset.configuration)
        config["version"] = "distance-legacy-location"
        exchange_rule = next(item for item in config["rules"] if item["id"] == "exchange")
        exchange_rule["rule"]["fields"].append(
            {
                "key": "grid",
                "label": "Grid",
                "value_type": "grid",
                "direction": "received",
                "required": False,
            }
        )
        config["rules"].append(
            {
                "id": "distance",
                "rule": {
                    "kind": "distance_points",
                    "grid_field": "grid",
                    "precision": 6,
                    "points_per_kilometer": 1,
                    "same_grid_points": 1,
                },
            }
        )
        persisted = save_ruleset_version(session, validate_ruleset(config), created_by_user_id=None)
        contest.ruleset_version_id = persisted.version.id
        revision = session.get(EntryRevision, revision_id)
        revision.import_metadata = {"headers": {"LOCATION": ["IO91AA"]}}
        station = session.scalar(select(Station).where(Station.entry_revision_id == revision_id))
        station.grid_submitted = "IO91AA"
        for qso in session.scalars(select(Qso).where(Qso.entry_revision_id == revision_id)):
            qso.exchange_received_submitted = {
                "raw": "IO91AA",
                "values": {"grid": "IO91AA"},
            }

        run = score_entry_revision(
            session,
            entry_id=entry_id,
            revision_id=revision_id,
            idempotency_key="legacy-location-not-grid",
        )

        first_score = session.scalar(
            select(QsoScore).where(QsoScore.score_run_id == run.id).order_by(QsoScore.qso_id)
        )
        assert first_score.status == "needs_review"
        assert first_score.points == 0
        assert "distance_grid_missing_or_invalid:distance" in first_score.explanation


def test_manual_decision_is_append_only_and_supersedes_in_a_new_score_run(scoring_db):
    factory, _contest_id, entry_id, revision_id = scoring_db
    with factory.begin() as session:
        first = score_entry_revision(
            session, entry_id=entry_id, revision_id=revision_id, idempotency_key="before-review"
        )
        first_qso = session.scalar(
            select(Qso).where(Qso.entry_revision_id == revision_id).order_by(Qso.id)
        )
        automated = QsoDecision(
            qso_id=first_qso.id,
            status=QsoDecisionStatus.NEEDS_REVIEW,
            source=QsoDecisionSource.AUTOMATED,
            reason_code="needs_review",
            reason="Automated review required.",
        )
        session.add(automated)
        session.flush()
        manual = QsoDecision(
            qso_id=first_qso.id,
            status=QsoDecisionStatus.NOT_CREDITED,
            source=QsoDecisionSource.CONTEST_MANAGER,
            reason_code="incorrect_exchange",
            reason="The exchange was confirmed incorrect.",
            evidence={"note": "reviewed"},
            supersedes_decision_id=automated.id,
        )
        session.add(manual)
        session.flush()
        second = score_entry_revision(
            session,
            entry_id=entry_id,
            revision_id=revision_id,
            idempotency_key="after-review",
        )
        assert second.id != first.id
        assert (
            session.scalar(
                select(QsoScore).where(
                    QsoScore.score_run_id == second.id, QsoScore.qso_id == first_qso.id
                )
            ).status
            == "not_credited"
        )
        assert session.get(QsoDecision, manual.id).supersedes_decision_id == automated.id
        assert second.adjudicated_score == second.final_score


def test_master_data_rules_require_contest_start_pin_and_copy_exact_version(scoring_db):
    factory, contest_id, entry_id, revision_id = scoring_db
    with factory.begin() as session:
        contest = session.get(Contest, contest_id)
        ruleset = session.get(RulesetVersion, contest.ruleset_version_id)
        config = dict(ruleset.configuration)
        config["version"] = "2026.1"
        config["rules"] = [
            *config["rules"],
            {
                "id": "entity-multiplier",
                "rule": {
                    "kind": "multiplier",
                    "source_fact": "station.continent",
                    "scope": "contest",
                    "label": "Entrant continent",
                },
            },
        ]
        persisted = save_ruleset_version(
            session,
            validate_ruleset(config),
            created_by_user_id=None,
        )
        contest.ruleset_version_id = persisted.version.id
        failed = recalculate_contest(session, contest_id, trigger_key="pinned-data-retry")[0]
        assert failed.status is ScoreRunStatus.FAILED
        assert "cty" in failed.master_data_snapshot["error"]
        session.flush()
        failed_event = session.scalar(
            select(AuditEvent).where(
                AuditEvent.action == "score_run.calculation_failed",
                AuditEvent.target_id == str(failed.id),
            )
        )
        assert failed_event is not None
        assert failed_event.event_metadata["status"] == "failed"
        source = MasterDataSource(
            source_key="cty-test",
            name="cty test",
            canonical_url="https://example.test/cty",
            authority_role="primary_operational",
        )
        session.add(source)
        session.flush()
        sync = MasterDataSyncRun(source_id=source.id, dataset_key="cty")
        session.add(sync)
        session.flush()
        pinned_version = MasterDataVersion(
            sync_run_id=sync.id,
            dataset_key="cty",
            retrieved_at=START - timedelta(days=2),
            checksum="b" * 64,
            valid_from=START - timedelta(days=3),
            valid_to=START + timedelta(days=1),
            status=MasterDataVersionStatus.RETIRED,
        )
        session.add(pinned_version)
        session.flush()
        pinned_entity = ContestEntity(
            version_id=pinned_version.id,
            namespace="cty",
            authority_code="EA",
            name="Pinned entity",
            continent="EU",
            entity_type=EntityType.CONTEST_ENTITY,
        )
        pinned_prefix = CallsignPrefix(
            version_id=pinned_version.id, prefix_pattern="EA", allocation_type="prefix"
        )
        session.add_all([pinned_entity, pinned_prefix])
        session.flush()
        session.add(
            PrefixEntityAssignment(
                version_id=pinned_version.id,
                prefix_id=pinned_prefix.id,
                entity_id=pinned_entity.id,
                source_note="pinned test allocation",
            )
        )
        newer_sync = MasterDataSyncRun(
            source_id=source.id,
            dataset_key="cty",
            status="succeeded",
            finished_at=START + timedelta(days=2),
        )
        session.add(newer_sync)
        session.flush()
        active_version = MasterDataVersion(
            sync_run_id=newer_sync.id,
            dataset_key="cty",
            retrieved_at=START + timedelta(days=2),
            checksum="d" * 64,
            valid_from=START + timedelta(days=1),
            status=MasterDataVersionStatus.ACTIVE,
        )
        session.add(active_version)
        session.flush()
        active_entity = ContestEntity(
            version_id=active_version.id,
            namespace="cty",
            authority_code="EA",
            name="Current entity",
            continent="NA",
            entity_type=EntityType.CONTEST_ENTITY,
        )
        active_prefix = CallsignPrefix(
            version_id=active_version.id, prefix_pattern="EA", allocation_type="prefix"
        )
        session.add_all([active_entity, active_prefix])
        session.flush()
        session.add(
            PrefixEntityAssignment(
                version_id=active_version.id,
                prefix_id=active_prefix.id,
                entity_id=active_entity.id,
                source_note="later test allocation",
            )
        )
        session.add(
            ContestMasterDataVersion(
                contest_id=contest_id,
                dataset_key="cty",
                master_data_version_id=pinned_version.id,
                pinned_at=START,
            )
        )
        session.flush()
        run = recalculate_contest(session, contest_id, trigger_key="pinned-data-retry")[0]
        assert run.status is ScoreRunStatus.COMPLETED
        assert run.master_data_snapshot == {"cty": pinned_version.id}
        assert run.master_data_version_id == pinned_version.id
        first_qso_score = session.scalar(
            select(QsoScore).where(QsoScore.score_run_id == run.id).order_by(QsoScore.qso_id)
        )
        assert first_qso_score is not None
        assert any(key.endswith(":EU") for key in first_qso_score.multiplier_keys)
        assert run.explanation["multiplier_counts"] == {"entity-multiplier": 1}


def test_recalculation_after_upload_retries_the_same_trigger_once(scoring_db):
    factory, contest_id, _entry_id, _revision_id = scoring_db
    with factory.begin() as session:
        first = recalculate_contest(session, contest_id, trigger_key="accepted-upload:test")
        retry = recalculate_contest(session, contest_id, trigger_key="accepted-upload:test")
        assert len(first) == len(retry) == 1
        assert first[0].id == retry[0].id
        assert first[0].status is ScoreRunStatus.COMPLETED
        session.flush()
        audit_events = list(
            session.scalars(select(AuditEvent).where(AuditEvent.target_id == str(first[0].id)))
        )
        assert [event.action for event in audit_events] == [
            "score_run.calculated",
            "score_run.calculated",
        ]
        assert all(event.event_metadata["trigger"] == "system" for event in audit_events)


def test_configured_cross_log_hook_uses_reciprocal_logs_and_integer_tolerances(scoring_db):
    factory, contest_id, entry_id, revision_id = scoring_db
    with factory.begin() as session:
        contest = session.get(Contest, contest_id)
        current_ruleset = session.get(RulesetVersion, contest.ruleset_version_id)
        config = dict(current_ruleset.configuration)
        config["version"] = "2026-cross-log"
        config["rules"] = [
            *config["rules"],
            {
                "id": "cross-log-check",
                "rule": {
                    "kind": "workflow_hook",
                    "stage": "cross_log",
                    "key": "reciprocal-contact",
                    "execution": "automatic",
                    "parameters": {
                        "timestamp_tolerance_seconds": 60,
                        "numeric_exchange_tolerances": {"serial": 1},
                        "require_counterpart": True,
                    },
                },
            },
        ]
        saved = save_ruleset_version(session, validate_ruleset(config), created_by_user_id=None)
        contest.ruleset_version_id = saved.version.id
        own_qso = session.scalar(
            select(Qso).where(Qso.entry_revision_id == revision_id).order_by(Qso.id)
        )
        own_qso.exchange_sent_submitted = {"raw": "5", "rst": "599"}
        own_qso.exchange_received_submitted = {"raw": "8", "rst": "599"}
        participant = session.scalar(select(Participant))
        other_entry = Entry(
            contest_id=contest_id,
            participant_id=participant.id,
            entry_key="reciprocal-entry",
            category_values={"operator": "single"},
        )
        session.add(other_entry)
        session.flush()
        other_revision = EntryRevision(
            entry_id=other_entry.id,
            revision_number=1,
            input_format="cabrillo",
            storage_key="database://reciprocal/1",
            original_content="reciprocal log",
            content_sha256="e" * 64,
            byte_size=14,
            submitted_at=START,
        )
        session.add(other_revision)
        session.flush()
        other_station = Station(
            entry_revision_id=other_revision.id,
            callsign_submitted="F4ABC",
            callsign_normalized="F4ABC",
        )
        session.add(other_station)
        session.flush()
        session.add(
            Qso(
                entry_revision_id=other_revision.id,
                station_id=other_station.id,
                source_line_number=1,
                occurred_at=START + timedelta(seconds=60),
                callsign_submitted="EA7KLK",
                callsign_normalized="EA7KLK",
                band="20M",
                mode="CW",
                exchange_sent_submitted={"raw": "9", "rst": "599"},
                exchange_received_submitted={"raw": "6", "rst": "599"},
            )
        )
        session.flush()
        run = score_entry_revision(
            session,
            entry_id=entry_id,
            revision_id=revision_id,
            idempotency_key="cross-log-match",
        )
        finding = run.explanation["cross_log"][str(own_qso.id)]
        assert finding["reason_code"] == "counterpart_match"
        assert finding["evidence"]["timestamp_difference_seconds"] == 60


def test_upload_toggle_and_idempotent_replay_control_automatic_recalculation(scoring_db):
    factory, contest_id, entry_id, revision_id = scoring_db
    with factory() as session:
        contest = session.get(Contest, contest_id)
        contest.auto_recalculate_on_upload = False
        session.commit()
        from backend.app.logs.service import recalculate_after_accepted_upload

        assert (
            recalculate_after_accepted_upload(
                session,
                contest_id=contest_id,
                entry_id=entry_id,
                revision_id=revision_id,
                replayed=False,
            )
            == []
        )
        contest.auto_recalculate_on_upload = True
        session.commit()
        runs = recalculate_after_accepted_upload(
            session,
            contest_id=contest_id,
            entry_id=entry_id,
            revision_id=revision_id,
            replayed=False,
        )
        assert runs[0]["status"] == "completed"
        assert (
            recalculate_after_accepted_upload(
                session,
                contest_id=contest_id,
                entry_id=entry_id,
                revision_id=revision_id,
                replayed=True,
            )
            == []
        )


def test_manager_review_endpoint_records_audited_override_and_exposes_runs(scoring_db, monkeypatch):
    factory, contest_id, _entry_id, revision_id = scoring_db
    monkeypatch.setattr(
        "backend.app.api.auth.get_settings", lambda: SimpleNamespace(secure_cookies=False)
    )

    def override_session():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    with factory.begin() as session:
        manager = session.scalar(select(SystemUser))
        token, csrf, _record = issue_session(session, manager)
        outsider = SystemUser(
            username="other-manager",
            email_normalized="other@example.test",
            display_name="Other Manager",
            role=SystemRole.CONTEST_MANAGER,
            password_hash="unused-test-hash",
        )
        session.add(outsider)
        session.flush()
        outsider_token, outsider_csrf, _outsider_record = issue_session(session, outsider)
        qso = session.scalar(
            select(Qso).where(Qso.entry_revision_id == revision_id).order_by(Qso.id)
        )
        qso_id = qso.id
    client = TestClient(app)
    client.cookies.set("contestmaster_session", token)
    client.cookies.set("contestmaster_csrf", csrf)
    try:
        response = client.post(
            f"/api/v1/contests/{contest_id}/qsos/{qso_id}/decisions",
            headers={"X-CSRF-Token": csrf},
            json={
                "status": "not_credited",
                "reason_code": "bad_exchange",
                "reason": "Evidence confirms the received exchange is wrong.",
                "evidence": {"source": "cross-check"},
            },
        )
        assert response.status_code == 201, response.text
        assert response.json()["status"] == "not_credited"
        assert response.json()["score_runs"][0]["status"] == "completed"
        scores = client.get(f"/api/v1/contests/{contest_id}/score-runs")
        assert scores.status_code == 200
        assert len(scores.json()["items"]) == 1
        detail = client.get(
            f"/api/v1/contests/{contest_id}/score-runs/{scores.json()['items'][0]['id']}"
        )
        assert detail.status_code == 200
        assert len(detail.json()["qso_scores"]) == 2
        assert all(type(row["points"]) is int for row in detail.json()["qso_scores"])
        outsider_client = TestClient(app)
        outsider_client.cookies.set("contestmaster_session", outsider_token)
        outsider_client.cookies.set("contestmaster_csrf", outsider_csrf)
        denied = outsider_client.get(
            f"/api/v1/contests/{contest_id}/score-runs/{scores.json()['items'][0]['id']}"
        )
        assert denied.status_code == 404
        with factory() as session:
            decision = session.scalar(select(QsoDecision).where(QsoDecision.qso_id == qso_id))
            assert decision.reviewer_user_id == manager.id
            assert decision.created_at.tzinfo is not None
    finally:
        app.dependency_overrides.clear()
