from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from backend.app.api.auth import hash_password
from backend.app.audit import record_audit_event
from backend.app.audit_retention import prune_expired_audit_events
from backend.app.db import Base, get_session
from backend.app.main import app
from backend.app.models import AuditEvent, SystemRole, SystemUser


def _admin_fixture(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
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
    with factory.begin() as session:
        admin = SystemUser(
            username="audit-admin",
            email_normalized="audit-admin@example.test",
            display_name="Audit Admin",
            role=SystemRole.GLOBAL_ADMINISTRATOR,
            password_hash=hash_password("Correct horse battery staple"),
        )
        manager = SystemUser(
            username="audit-manager",
            email_normalized="audit-manager@example.test",
            display_name="Audit Manager",
            role=SystemRole.CONTEST_MANAGER,
            password_hash=hash_password("Correct horse battery staple"),
        )
        session.add_all([admin, manager])
        session.flush()
        admin_id, manager_id = admin.id, manager.id
        record_audit_event(
            session,
            actor_user_id=admin.id,
            action="contest.updated",
            target_type="contest",
            target_id=41,
            metadata={"fields": ["name"]},
            request_id="audit-test-request",
        )
        record_audit_event(
            session,
            actor_user_id=None,
            action="entry.submitted",
            target_type="entry",
            target_id=99,
            metadata={"input_format": "adif"},
        )
        session.add(
            AuditEvent(
                action="old.event",
                target_type="contest",
                target_id="old",
                event_metadata={},
                occurred_at=datetime.now(UTC) - timedelta(days=91),
            )
        )
    return engine, factory, admin_id, manager_id


def _client(email: str) -> TestClient:
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Correct horse battery staple"},
    )
    assert response.status_code == 200
    return client


def test_audit_log_is_global_admin_only_and_searchable(monkeypatch):
    engine, _factory, _admin_id, _manager_id = _admin_fixture(monkeypatch)
    try:
        assert TestClient(app).get("/api/v1/admin/audit-events").status_code == 401
        manager = _client("audit-manager@example.test")
        assert manager.get("/api/v1/admin/audit-events").status_code == 403

        admin = _client("audit-admin@example.test")
        response = admin.get("/api/v1/admin/audit-events?q=contest.updated")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["actor"] == "Audit Admin"
        assert body["items"][0]["metadata"] == {"fields": ["name"]}
        assert body["items"][0]["request_id"] == "audit-test-request"
        assert admin.get("/api/v1/admin/audit-events?action=entry.submitted").json()["total"] == 1
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_audit_retention_prunes_only_events_older_than_90_days(monkeypatch):
    engine, factory, _admin_id, _manager_id = _admin_fixture(monkeypatch)
    try:
        now = datetime.now(UTC)
        with factory.begin() as session:
            session.add(
                AuditEvent(
                    action="cutoff.event",
                    target_type="contest",
                    target_id="cutoff",
                    event_metadata={},
                    occurred_at=now - timedelta(days=90),
                )
            )
        removed = prune_expired_audit_events(factory, now=now)
        assert removed == 1
        with factory() as session:
            actions = set(session.scalars(select(AuditEvent.action)))
        assert "old.event" not in actions
        assert "cutoff.event" in actions
        assert "contest.updated" in actions
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()
