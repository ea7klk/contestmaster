from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.auth import hash_password
from backend.app.db import Base, get_session
from backend.app.main import app
from backend.app.models import (
    AuditEvent,
    CallsignPrefix,
    Contest,
    ContestEntity,
    ContestMasterDataVersion,
    ContestStatus,
    CQZone,
    EntityType,
    Entry,
    EntryRevision,
    ITUZone,
    MasterDataAuthorityRole,
    MasterDataRunStatus,
    MasterDataSource,
    MasterDataSyncRun,
    MasterDataVersion,
    MasterDataVersionStatus,
    Participant,
    PrefixEntityAssignment,
    Qso,
    RulesetVersion,
    ScoreRun,
    ScoreRunMasterDataVersion,
    ScoreRunStatus,
    SystemRole,
    SystemUser,
)


@pytest.fixture
def admin_database(monkeypatch):
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
        "backend.app.api.auth.get_settings",
        lambda: type("Settings", (), {"secure_cookies": False})(),
    )
    try:
        yield factory
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def add_system_user(factory, role: SystemRole, username: str) -> int:
    with factory.begin() as session:
        user = SystemUser(
            username=username,
            email_normalized=f"{username}@example.test",
            display_name=username,
            role=role,
            password_hash=hash_password("Correct horse battery staple"),
        )
        session.add(user)
        session.flush()
        return user.id


def sign_in(email: str) -> TestClient:
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Correct horse battery staple"},
    )
    assert response.status_code == 200
    return client


def create_version(
    session,
    *,
    dataset: str = "cty",
    status: MasterDataVersionStatus = MasterDataVersionStatus.CANDIDATE,
    source_key: str | None = None,
) -> MasterDataVersion:
    source = MasterDataSource(
        source_key=source_key or f"source-{dataset}",
        name=f"Source {dataset}",
        canonical_url="https://example.test/data",
        authority_role=MasterDataAuthorityRole.PRIMARY_OPERATIONAL,
        enabled=True,
    )
    session.add(source)
    session.flush()
    moment = datetime(2026, 1, 1, tzinfo=UTC)
    run = MasterDataSyncRun(
        source_id=source.id,
        dataset_key=dataset,
        started_at=moment,
        finished_at=moment + timedelta(minutes=1),
        retrieved_at=moment,
        source_url=source.canonical_url,
        source_release="2026-01",
        checksum="a" * 64,
        parser_version="test-1",
        status=MasterDataRunStatus.SUCCEEDED,
        record_counts={"entities": 1},
        change_detected=status is MasterDataVersionStatus.CANDIDATE,
    )
    session.add(run)
    session.flush()
    version = MasterDataVersion(
        sync_run_id=run.id,
        dataset_key=dataset,
        source_release=run.source_release,
        retrieved_at=moment,
        checksum=run.checksum,
        activated_at=moment if status is MasterDataVersionStatus.ACTIVE else None,
        valid_from=moment,
        valid_to=moment + timedelta(days=1) if status is MasterDataVersionStatus.RETIRED else None,
        status=status,
    )
    session.add(version)
    session.flush()
    return version


def test_master_data_admin_routes_are_global_admin_only_and_show_provenance(admin_database):
    add_system_user(admin_database, SystemRole.GLOBAL_ADMINISTRATOR, "admin")
    add_system_user(admin_database, SystemRole.CONTEST_MANAGER, "manager")
    with admin_database.begin() as session:
        version = create_version(session, status=MasterDataVersionStatus.ACTIVE)
        version_id = version.id

    assert TestClient(app).get("/api/v1/admin/master-data/versions").status_code == 401
    manager = sign_in("manager@example.test")
    assert manager.get("/api/v1/admin/master-data/versions").status_code == 403
    assert manager.get("/api/v1/admin/master-data/sync-runs").status_code == 403
    admin = sign_in("admin@example.test")
    response = admin.get("/api/v1/admin/master-data/versions")
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["id"] == version_id
    assert item["is_current"] is True
    assert item["provenance"]["source_url"] == "https://example.test/data"
    assert item["provenance"]["status"] == "succeeded"
    assert item["can_delete"] is False
    assert admin.get("/api/v1/admin/master-data/sync-runs").json()["items"][0][
        "change_detected"
    ] is False


def test_admin_can_activate_only_successful_candidate_and_preserves_effective_intervals(
    admin_database,
):
    admin_id = add_system_user(admin_database, SystemRole.GLOBAL_ADMINISTRATOR, "admin")
    with admin_database.begin() as session:
        active = create_version(session, status=MasterDataVersionStatus.ACTIVE)
        candidate = create_version(session, source_key="source-cty-candidate")
        active_id, candidate_id = active.id, candidate.id

    admin = sign_in("admin@example.test")
    csrf = admin.cookies.get("contestmaster_csrf")
    response = admin.post(
        f"/api/v1/admin/master-data/versions/{candidate_id}/activate",
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "active"
    with admin_database() as session:
        old = session.get(MasterDataVersion, active_id)
        new = session.get(MasterDataVersion, candidate_id)
        assert old is not None and old.status is MasterDataVersionStatus.RETIRED
        assert old.valid_to == new.valid_from
        assert new is not None and new.status is MasterDataVersionStatus.ACTIVE
        assert new.activated_at == new.valid_from
        event = session.query(AuditEvent).one()
        assert event.actor_user_id == admin_id
        assert event.action == "master_data.version_activated"


def test_admin_deletes_unreferenced_snapshot_but_keeps_sync_and_audit_history(admin_database):
    admin_id = add_system_user(admin_database, SystemRole.GLOBAL_ADMINISTRATOR, "admin")
    with admin_database.begin() as session:
        version = create_version(session, status=MasterDataVersionStatus.RETIRED)
        zone = CQZone(version_id=version.id, code="1", name="CQ Zone 1")
        itu_zone = ITUZone(version_id=version.id, code="1", name="ITU Zone 1")
        entity = ContestEntity(
            version_id=version.id,
            namespace="cty",
            authority_code="EA",
            name="Spain",
            entity_type=EntityType.CONTEST_ENTITY,
        )
        prefix = CallsignPrefix(
            version_id=version.id, prefix_pattern="EA", allocation_type="exact"
        )
        session.add_all([zone, itu_zone, entity, prefix])
        session.flush()
        session.add(
            PrefixEntityAssignment(
                version_id=version.id,
                prefix_id=prefix.id,
                entity_id=entity.id,
                source_note="test allocation",
            )
        )
        version_id, sync_run_id = version.id, version.sync_run_id

    admin = sign_in("admin@example.test")
    response = admin.get("/api/v1/admin/master-data/versions")
    item = response.json()["items"][0]
    assert item["can_delete"] is True
    csrf = admin.cookies.get("contestmaster_csrf")
    deleted = admin.delete(
        f"/api/v1/admin/master-data/versions/{version_id}",
        headers={"X-CSRF-Token": csrf},
    )
    assert deleted.status_code == 204
    with admin_database() as session:
        assert session.get(MasterDataVersion, version_id) is None
        assert session.get(MasterDataSyncRun, sync_run_id) is not None
        assert session.query(CQZone).count() == 0
        assert session.query(ITUZone).count() == 0
        assert session.query(ContestEntity).count() == 0
        assert session.query(CallsignPrefix).count() == 0
        assert session.query(PrefixEntityAssignment).count() == 0
        event = session.query(AuditEvent).one()
        assert event.actor_user_id == admin_id
        assert event.action == "master_data.version_deleted"
        assert event.target_id == str(version_id)


def _add_score_references(session, version: MasterDataVersion, owner_id: int):
    participant = Participant(callsign_submitted="EA7KLK")
    session.add(participant)
    session.flush()
    contest = Contest(
        owner_user_id=owner_id,
        name="Reference contest",
        slug=f"reference-{version.id}",
        starts_at=datetime(2026, 2, 1, tzinfo=UTC),
        ends_at=datetime(2026, 2, 1, 2, tzinfo=UTC),
        log_submission_cutoff_at=datetime(2026, 2, 2, tzinfo=UTC),
        status=ContestStatus.CLOSED,
    )
    session.add(contest)
    session.flush()
    entry = Entry(contest_id=contest.id, participant_id=participant.id, entry_key="ref-entry")
    session.add(entry)
    session.flush()
    revision = EntryRevision(
        entry_id=entry.id,
        revision_number=1,
        input_format="cabrillo",
        storage_key="test/ref.log",
        content_sha256="b" * 64,
        byte_size=10,
        submitted_at=datetime(2026, 2, 1, tzinfo=UTC),
    )
    ruleset = RulesetVersion(ruleset_key="ref-rules", version="1", configuration={})
    session.add_all([revision, ruleset])
    session.flush()
    score_run = ScoreRun(
        entry_id=entry.id,
        entry_revision_id=revision.id,
        ruleset_version_id=ruleset.id,
        master_data_version_id=version.id,
        run_number=1,
        status=ScoreRunStatus.COMPLETED,
        input_digest="c" * 64,
        ruleset_snapshot={},
        points=0,
        multiplier_count=0,
        penalty_points=0,
        final_score=0,
    )
    session.add(score_run)
    session.flush()
    return contest, revision, score_run


@pytest.mark.parametrize("reference", ["contest", "score_run", "qso"])
def test_delete_is_rejected_for_each_historical_reference_type(admin_database, reference):
    owner_id = add_system_user(
        admin_database, SystemRole.CONTEST_MANAGER, f"owner-{reference}"
    )
    add_system_user(admin_database, SystemRole.GLOBAL_ADMINISTRATOR, "admin")
    with admin_database.begin() as session:
        version = create_version(
            session,
            dataset=f"dataset-{reference}",
            status=MasterDataVersionStatus.RETIRED,
            source_key=f"source-{reference}",
        )
        contest, revision, score_run = _add_score_references(session, version, owner_id)
        if reference == "contest":
            session.add(
                ContestMasterDataVersion(
                    contest_id=contest.id,
                    dataset_key=version.dataset_key,
                    master_data_version_id=version.id,
                )
            )
        elif reference == "score_run":
            session.add(
                ScoreRunMasterDataVersion(
                    score_run_id=score_run.id,
                    dataset_key=version.dataset_key,
                    master_data_version_id=version.id,
                )
            )
        else:
            session.add(
                Qso(
                    entry_revision_id=revision.id,
                    occurred_at=datetime(2026, 2, 1, 1, tzinfo=UTC),
                    callsign_submitted="EA1ABC",
                    resolved_master_data_version_id=version.id,
                )
            )
        version_id = version.id

    admin = sign_in("admin@example.test")
    item = admin.get("/api/v1/admin/master-data/versions").json()["items"][0]
    assert item["can_delete"] is False
    deleted = admin.delete(
        f"/api/v1/admin/master-data/versions/{version_id}",
        headers={"X-CSRF-Token": admin.cookies.get("contestmaster_csrf")},
    )
    assert deleted.status_code == 409
    with admin_database() as session:
        assert session.get(MasterDataVersion, version_id) is not None


