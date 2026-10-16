from datetime import UTC, datetime, timedelta
from hashlib import sha256
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import identity_cli
from backend.app.api.auth import (
    hash_password,
    require_authenticated_user,
    verify_password,
)
from backend.app.db import Base, get_session
from backend.app.main import app
from backend.app.models import (
    AuditEvent,
    Contest,
    ContestStatus,
    Entry,
    EntryAccessGrant,
    Participant,
    SystemRole,
    SystemSession,
    SystemUser,
)


@pytest.fixture
def identity_database(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(
        "backend.app.api.auth.get_settings", lambda: SimpleNamespace(secure_cookies=False)
    )

    def override_session():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        yield factory
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def add_user(
    factory,
    role=SystemRole.GLOBAL_ADMINISTRATOR,
    username="admin",
    email="admin@example.test",
):
    with factory.begin() as session:
        user = SystemUser(
            username=username,
            email_normalized=email,
            display_name=username,
            role=role,
            password_hash=hash_password("Correct horse battery staple"),
        )
        session.add(user)
        session.flush()
        return user.id


def test_privileged_login_is_rate_limited_by_peer_and_account(identity_database):
    client = TestClient(app)
    payload = {"email": "target@example.test", "password": "incorrect"}

    for _ in range(10):
        assert client.post("/api/v1/auth/login", json=payload).status_code == 401

    rejected = client.post("/api/v1/auth/login", json=payload)
    assert rejected.status_code == 429
    assert int(rejected.headers["Retry-After"]) > 0
    assert "target@example.test" not in rejected.text


def test_password_hashing_is_salted_and_rejects_wrong_password():
    first = hash_password("Correct horse battery staple")
    second = hash_password("Correct horse battery staple")

    assert first != second
    assert verify_password("Correct horse battery staple", first)
    assert not verify_password("wrong password", first)


def test_password_hashing_rejects_short_passwords():
    with pytest.raises(ValueError, match="12 characters"):
        hash_password("short")


def test_first_admin_bootstrap_only_succeeds_once(identity_database, monkeypatch):
    monkeypatch.setattr(identity_cli, "SessionFactory", identity_database)
    first_id = identity_cli.create_first_administrator(
        username="root-admin",
        email="Admin@example.test",
        display_name="Initial Administrator",
        password="Safe bootstrap passphrase",
    )
    with identity_database() as session:
        created = session.get(SystemUser, first_id)
        assert created is not None
        assert created.role is SystemRole.GLOBAL_ADMINISTRATOR
        assert created.email_normalized == "admin@example.test"
        event = session.query(AuditEvent).one()
        assert event.actor_user_id is None
        assert event.action == "system_user.initial_global_administrator_bootstrapped"
        assert event.target_id == str(first_id)
        assert event.event_metadata["bootstrap"] is True

    with pytest.raises(ValueError, match="only before any user exists"):
        identity_cli.create_first_administrator(
            username="second-admin",
            email="second@example.test",
            display_name="Second Administrator",
            password="Another safe bootstrap passphrase",
        )


def test_privileged_auth_dependency_rejects_anonymous_requests():
    from starlette.requests import Request

    request = Request({"type": "http", "method": "GET", "headers": [], "path": "/"})
    session = Session(create_engine("sqlite://"))
    try:
        with pytest.raises(HTTPException) as error:
            require_authenticated_user(request, session)
    finally:
        session.close()

    assert error.value.status_code == 401
    assert error.value.headers == {"WWW-Authenticate": "Session"}


def test_login_issues_http_only_session_and_csrf_cookie_then_me_returns_role(identity_database):
    add_user(identity_database)
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "ADMIN@example.test", "password": "Correct horse battery staple"},
    )

    assert response.status_code == 200
    assert response.json()["user"]["role"] == "global_administrator"
    assert "httponly" in response.headers.get_list("set-cookie")[0].lower()
    csrf_header = next(
        cookie
        for cookie in response.headers.get_list("set-cookie")
        if cookie.startswith("contestmaster_csrf=")
    )
    assert "path=/;" in csrf_header.lower()
    session_cookie = client.cookies.get("contestmaster_session")
    csrf_cookie = client.cookies.get("contestmaster_csrf")
    assert session_cookie and csrf_cookie
    assert csrf_cookie == response.json()["csrf_token"]

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "admin@example.test"


def test_login_rejects_invalid_credentials_without_creating_session(identity_database):
    add_user(identity_database)
    response = TestClient(app).post(
        "/api/v1/auth/login",
        json={"email": "admin@example.test", "password": "incorrect password"},
    )

    assert response.status_code == 401
    with identity_database() as session:
        assert session.query(SystemSession).count() == 0


def test_mutation_requires_csrf_and_logout_revokes_session(identity_database):
    add_user(identity_database)
    client = TestClient(app)
    client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.test", "password": "Correct horse battery staple"},
    )

    without_header = client.post("/api/v1/auth/logout")
    assert without_header.status_code == 403

    csrf = client.cookies.get("contestmaster_csrf")
    logout = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
    assert logout.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401
    with identity_database() as session:
        record = session.query(SystemSession).one()
        assert record.revoked_at is not None


def test_expired_privileged_session_is_rejected(identity_database):
    user_id = add_user(identity_database)
    with identity_database.begin() as session:
        session.add(
            SystemSession(
                user_id=user_id,
                token_hash=sha256(b"expired-token").hexdigest(),
                csrf_token_hash="b" * 64,
                created_at=datetime.now(UTC) - timedelta(days=2),
                expires_at=datetime.now(UTC) - timedelta(days=1),
            )
        )

    client = TestClient(app)
    client.cookies.set("contestmaster_session", "expired-token")
    assert client.get("/api/v1/auth/me").status_code == 401


def test_global_admin_can_create_manager_but_manager_cannot(identity_database):
    add_user(identity_database)
    client = TestClient(app)
    client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.test", "password": "Correct horse battery staple"},
    )
    csrf = client.cookies.get("contestmaster_csrf")
    created = client.post(
        "/api/v1/auth/admin/users",
        headers={"X-CSRF-Token": csrf},
        json={
            "username": "manager",
            "email": "manager@example.test",
            "display_name": "Contest Manager",
            "password": "Another correct horse battery",
            "audit_reason": "Organizer account provisioned for a scheduled event",
        },
    )
    assert created.status_code == 201
    assert created.json()["role"] == "contest_manager"
    assert "password_hash" not in created.text
    with identity_database() as session:
        event = session.query(AuditEvent).one()
        assert event.actor_user_id == 1
        assert event.action == "system_user.contest_manager_created"
        assert event.target_type == "system_user"
        assert event.target_id == str(created.json()["id"])
        assert event.reason == "Organizer account provisioned for a scheduled event"
        assert event.occurred_at.tzinfo is not None
        assert event.request_id is not None

    manager_client = TestClient(app)
    signed_in = manager_client.post(
        "/api/v1/auth/login",
        json={"email": "manager@example.test", "password": "Another correct horse battery"},
    )
    assert signed_in.status_code == 200
    denied = manager_client.post(
        "/api/v1/auth/admin/users",
        headers={"X-CSRF-Token": manager_client.cookies.get("contestmaster_csrf")},
        json={
            "username": "manager2",
            "email": "manager2@example.test",
            "display_name": "Another Manager",
            "password": "Another secure horse battery",
        },
    )
    assert denied.status_code == 403


def test_contest_api_scopes_managers_and_allows_admin_visibility(identity_database):
    admin_id = add_user(identity_database)
    add_user(
        identity_database,
        role=SystemRole.CONTEST_MANAGER,
        username="manager-one",
        email="one@example.test",
    )
    add_user(
        identity_database,
        role=SystemRole.CONTEST_MANAGER,
        username="manager-two",
        email="two@example.test",
    )

    def sign_in(email):
        client = TestClient(app)
        signed = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "Correct horse battery staple"},
        )
        assert signed.status_code == 200
        return client

    first_manager = sign_in("one@example.test")
    payload = {
        "name": "Spring Sprint",
        "slug": "spring-sprint",
        "description": "Test contest",
        "starts_at": "2026-05-01T00:00:00Z",
        "ends_at": "2026-05-01T06:00:00Z",
        "log_submission_cutoff_at": "2026-05-08T00:00:00Z",
        "auto_recalculate_on_upload": True,
        "audit_reason": "Initial contest setup",
    }
    created = first_manager.post(
        "/api/v1/contests",
        headers={"X-CSRF-Token": first_manager.cookies.get("contestmaster_csrf")},
        json=payload,
    )
    assert created.status_code == 201
    contest = created.json()
    assert contest["owner_user_id"] != admin_id
    assert contest["status"] == "draft"
    assert contest["auto_recalculate_on_upload"] is True

    other_manager = sign_in("two@example.test")
    assert other_manager.get("/api/v1/contests").json()["meta"]["total"] == 0
    assert other_manager.get(f"/api/v1/contests/{contest['id']}").status_code == 404

    admin = sign_in("admin@example.test")
    listing = admin.get("/api/v1/contests")
    assert listing.status_code == 200
    assert listing.json()["meta"]["total"] == 1
    assert admin.get(f"/api/v1/contests/{contest['id']}").status_code == 200

    changed = {**payload, "name": "Updated Sprint", "audit_reason": "Corrected event title"}
    forbidden = other_manager.put(
        f"/api/v1/contests/{contest['id']}",
        headers={"X-CSRF-Token": other_manager.cookies.get("contestmaster_csrf")},
        json=changed,
    )
    assert forbidden.status_code == 404
    updated = first_manager.put(
        f"/api/v1/contests/{contest['id']}",
        headers={"X-CSRF-Token": first_manager.cookies.get("contestmaster_csrf")},
        json=changed,
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated Sprint"
    with identity_database() as session:
        events = session.query(AuditEvent).order_by(AuditEvent.id).all()
        assert [event.action for event in events] == ["contest.created", "contest.updated"]
        assert all(event.actor_user_id == contest["owner_user_id"] for event in events)
        assert all(event.target_id == str(contest["id"]) for event in events)
        assert [event.reason for event in events] == [
            "Initial contest setup",
            "Corrected event title",
        ]
        assert events[1].event_metadata == {"changed_fields": ["name"]}


def test_contest_mutations_require_session_and_csrf_and_ignore_client_owner(identity_database):
    admin_id = add_user(identity_database)
    client = TestClient(app)
    payload = {
        "name": "Boundary contest",
        "slug": "boundary-contest",
        "starts_at": "2026-05-01T00:00:00Z",
        "ends_at": "2026-05-01T06:00:00Z",
        "log_submission_cutoff_at": "2026-05-08T00:00:00Z",
        "owner_user_id": admin_id + 500,
    }
    assert client.get("/api/v1/contests").status_code == 401
    assert client.post("/api/v1/contests", json=payload).status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "admin@example.test", "password": "Correct horse battery staple"},
        ).status_code
        == 200
    )
    csrf = client.cookies.get("contestmaster_csrf")
    assert client.post("/api/v1/contests", json=payload).status_code == 403
    rejected_owner_override = client.post(
        "/api/v1/contests", headers={"X-CSRF-Token": csrf}, json=payload
    )
    assert rejected_owner_override.status_code == 422
    payload.pop("owner_user_id")
    created = client.post("/api/v1/contests", headers={"X-CSRF-Token": csrf}, json=payload)
    assert created.status_code == 201
    assert created.json()["owner_user_id"] == admin_id


@pytest.mark.parametrize(
    "start,end",
    [
        ("2026-05-01T00:00:00", "2026-05-01T06:00:00Z"),
        ("2026-05-01T06:00:00Z", "2026-05-01T00:00:00Z"),
    ],
)
def test_contest_creation_rejects_naive_or_reversed_times(identity_database, start, end):
    add_user(identity_database)
    client = TestClient(app)
    client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.test", "password": "Correct horse battery staple"},
    )
    payload = {
        "name": "Bad contest",
        "slug": "bad-contest",
        "starts_at": start,
        "ends_at": end,
        "log_submission_cutoff_at": "2026-05-08T00:00:00Z",
    }
    response = client.post(
        "/api/v1/contests",
        headers={"X-CSRF-Token": client.cookies.get("contestmaster_csrf")},
        json=payload,
    )
    assert response.status_code == 422


def test_manager_can_save_and_select_ruleset_only_for_owned_draft(identity_database):
    from backend.app.models import Contest, RulesetActivation, RulesetVersion
    from backend.tests.test_rulesets import valid_payload

    manager_id = add_user(
        identity_database,
        role=SystemRole.CONTEST_MANAGER,
        username="rules-manager",
        email="rules@example.test",
    )
    add_user(
        identity_database,
        role=SystemRole.CONTEST_MANAGER,
        username="other-manager",
        email="other@example.test",
    )
    from datetime import UTC, datetime

    with identity_database.begin() as session:
        contest = Contest(
            owner_user_id=manager_id,
            name="Ruleset contest",
            slug="ruleset-contest",
            starts_at=datetime(2026, 1, 1, tzinfo=UTC),
            ends_at=datetime(2026, 1, 1, 2, tzinfo=UTC),
            log_submission_cutoff_at=datetime(2026, 1, 2, tzinfo=UTC),
        )
        session.add(contest)
        session.flush()
        contest_id = contest.id

    manager = TestClient(app)
    assert (
        manager.post(
            "/api/v1/auth/login",
            json={"email": "rules@example.test", "password": "Correct horse battery staple"},
        ).status_code
        == 200
    )
    saved = manager.post(
        "/api/v1/rulesets/versions",
        headers={"X-CSRF-Token": manager.cookies.get("contestmaster_csrf")},
        json=valid_payload(),
    )
    assert saved.status_code == 201
    version_id = saved.json()["id"]
    selected = manager.put(
        f"/api/v1/contests/{contest_id}/ruleset",
        headers={"X-CSRF-Token": manager.cookies.get("contestmaster_csrf")},
        json={"ruleset_version_id": version_id},
    )
    assert selected.status_code == 200
    assert selected.json()["ruleset_version_id"] == version_id

    other = TestClient(app)
    assert (
        other.post(
            "/api/v1/auth/login",
            json={"email": "other@example.test", "password": "Correct horse battery staple"},
        ).status_code
        == 200
    )
    forbidden = other.put(
        f"/api/v1/contests/{contest_id}/ruleset",
        headers={"X-CSRF-Token": other.cookies.get("contestmaster_csrf")},
        json={"ruleset_version_id": version_id},
    )
    assert forbidden.status_code == 404
    assert (
        other.post(
            "/api/v1/rulesets/versions",
            headers={"X-CSRF-Token": other.cookies.get("contestmaster_csrf")},
            json=valid_payload(),
        ).status_code
        == 200
    )

    with identity_database() as session:
        assert session.query(RulesetVersion).count() == 1
        assert session.query(RulesetActivation).count() == 1
        assert {event.action for event in session.query(AuditEvent).all()} == {
            "ruleset_version.created",
            "contest.ruleset_activated",
        }


def test_invalid_ruleset_cannot_be_persisted(identity_database):
    from backend.app.models import RulesetVersion
    from backend.tests.test_rulesets import valid_payload

    add_user(identity_database)
    client = TestClient(app)
    client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.test", "password": "Correct horse battery staple"},
    )
    invalid = valid_payload()
    invalid["version"] = "invalid-config"
    invalid["rules"] = [  # A syntactically valid definition missing required rule types.
        rule for rule in invalid["rules"] if rule["rule"]["kind"] != "score_formula"
    ]
    response = client.post(
        "/api/v1/rulesets/versions",
        headers={"X-CSRF-Token": client.cookies.get("contestmaster_csrf")},
        json=invalid,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_ruleset"
    with identity_database() as session:
        assert session.query(RulesetVersion).count() == 0


def test_contest_status_requires_ruleset_and_public_routes_only_show_published(
    identity_database,
):
    from backend.tests.test_rulesets import valid_payload

    manager_id = add_user(
        identity_database,
        role=SystemRole.CONTEST_MANAGER,
        username="status-manager",
        email="status@example.test",
    )
    with identity_database.begin() as session:
        contest = Contest(
            owner_user_id=manager_id,
            name="Status contest",
            slug="status-contest",
            starts_at=datetime(2026, 1, 1, tzinfo=UTC),
            ends_at=datetime(2026, 1, 1, 2, tzinfo=UTC),
            log_submission_cutoff_at=datetime(2026, 1, 2, tzinfo=UTC),
        )
        session.add(contest)
        session.flush()
        contest_id = contest.id

    client = TestClient(app)
    assert client.get("/api/v1/public/contests").json()["items"] == []
    assert client.get("/api/v1/public/contests/status-contest").status_code == 404
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "status@example.test", "password": "Correct horse battery staple"},
        ).status_code
        == 200
    )
    headers = {"X-CSRF-Token": client.cookies.get("contestmaster_csrf")}

    blocked = client.put(
        f"/api/v1/contests/{contest_id}/status",
        headers=headers,
        json={"status": "open"},
    )
    assert blocked.status_code == 409

    saved = client.post("/api/v1/rulesets/versions", headers=headers, json=valid_payload())
    assert saved.status_code == 201
    selected = client.put(
        f"/api/v1/contests/{contest_id}/ruleset",
        headers=headers,
        json={"ruleset_version_id": saved.json()["id"]},
    )
    assert selected.status_code == 200
    opened = client.put(
        f"/api/v1/contests/{contest_id}/status",
        headers=headers,
        json={"status": "open", "audit_reason": "Registration opened"},
    )
    assert opened.status_code == 200
    assert opened.json()["status"] == "open"
    assert (
        client.put(
            f"/api/v1/contests/{contest_id}/status",
            headers=headers,
            json={"status": "published"},
        ).status_code
        == 409
    )
    closed = client.put(
        f"/api/v1/contests/{contest_id}/status",
        headers=headers,
        json={"status": "closed"},
    )
    assert closed.status_code == 200
    published = client.put(
        f"/api/v1/contests/{contest_id}/status",
        headers=headers,
        json={"status": "published"},
    )
    assert published.status_code == 409
    public_list = client.get("/api/v1/public/contests")
    assert public_list.status_code == 200
    assert public_list.json()["items"] == []
    assert client.get("/api/v1/public/contests/status-contest").status_code == 404
    with identity_database() as session:
        assert [event.action for event in session.query(AuditEvent).all()] == [
            "ruleset_version.created",
            "contest.ruleset_activated",
            "contest.status_changed",
            "contest.status_changed",
        ]


def test_public_upcoming_contests_include_open_future_and_running_only(
    identity_database, monkeypatch
):
    owner_id = add_user(identity_database)
    now = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now if tz else now.replace(tzinfo=None)

    monkeypatch.setattr("backend.app.api.contests.datetime", FixedDateTime)
    with identity_database.begin() as session:
        session.add_all(
            [
                Contest(
                    owner_user_id=owner_id,
                    name="Future public",
                    slug="future-public",
                    starts_at=now + timedelta(days=1),
                    ends_at=now + timedelta(days=1, hours=2),
                    log_submission_cutoff_at=now + timedelta(days=2),
                    status=ContestStatus.OPEN,
                ),
                Contest(
                    owner_user_id=owner_id,
                    name="Running public",
                    slug="running-public",
                    starts_at=now,
                    ends_at=now + timedelta(hours=1),
                    log_submission_cutoff_at=now + timedelta(days=1),
                    status=ContestStatus.OPEN,
                ),
                Contest(
                    owner_user_id=owner_id,
                    name="Ended at boundary",
                    slug="ended-boundary",
                    starts_at=now - timedelta(hours=1),
                    ends_at=now,
                    log_submission_cutoff_at=now + timedelta(days=1),
                    status=ContestStatus.OPEN,
                ),
                Contest(
                    owner_user_id=owner_id,
                    name="Draft future",
                    slug="draft-future",
                    starts_at=now + timedelta(days=2),
                    ends_at=now + timedelta(days=2, hours=2),
                    log_submission_cutoff_at=now + timedelta(days=3),
                    status=ContestStatus.DRAFT,
                ),
            ]
        )

    client = TestClient(app)
    response = client.get("/api/v1/public/contests/upcoming")
    assert response.status_code == 200
    payload = response.json()
    assert [item["slug"] for item in payload["items"]] == [
        "running-public",
        "future-public",
    ]
    assert payload["as_of"] == now.isoformat().replace("+00:00", "Z")
    details = client.get("/api/v1/public/contests/future-public")
    assert details.status_code == 200
    assert details.json()["log_submission_cutoff_at"] == "2026-10-18T12:00:00Z"
    assert client.get("/api/v1/public/contests/draft-future").status_code == 404


def test_manager_can_create_rotate_and_revoke_entry_receipt_grants(identity_database):
    from backend.app.api.contests import _token_digest

    manager_id = add_user(
        identity_database,
        role=SystemRole.CONTEST_MANAGER,
        username="grant-manager",
        email="grant@example.test",
    )
    with identity_database.begin() as session:
        participant = Participant(callsign_submitted="EA7KLK")
        session.add(participant)
        session.flush()
        contest = Contest(
            owner_user_id=manager_id,
            name="Grant contest",
            slug="grant-contest",
            starts_at=datetime(2026, 1, 1, tzinfo=UTC),
            ends_at=datetime(2026, 1, 1, 2, tzinfo=UTC),
            log_submission_cutoff_at=datetime(2026, 1, 2, tzinfo=UTC),
        )
        session.add(contest)
        session.flush()
        entry = Entry(contest_id=contest.id, participant_id=participant.id, entry_key="ea7klk")
        session.add(entry)
        session.flush()
        contest_id, entry_id = contest.id, entry.id

    client = TestClient(app)
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "grant@example.test", "password": "Correct horse battery staple"},
        ).status_code
        == 200
    )
    headers = {"X-CSRF-Token": client.cookies.get("contestmaster_csrf")}
    endpoint = f"/api/v1/contests/{contest_id}/entries/{entry_id}/access-grant"
    created = client.put(endpoint, headers=headers, json={"operation": "create"})
    assert created.status_code == 200
    first_token = created.json()["receipt_token"]
    assert first_token
    with identity_database() as session:
        grant = session.query(EntryAccessGrant).one()
        assert grant.token_hash == _token_digest(first_token)
        assert first_token not in grant.token_hash

    duplicate = client.put(endpoint, headers=headers, json={"operation": "create"})
    assert duplicate.status_code == 409
    expiry = "2027-01-01T00:00:00Z"
    extended = client.put(
        endpoint,
        headers=headers,
        json={"operation": "set_expiry", "expires_at": expiry},
    )
    assert extended.status_code == 200
    assert extended.json()["expires_at"] == expiry

    rotated = client.put(endpoint, headers=headers, json={"operation": "rotate"})
    assert rotated.status_code == 200
    second_token = rotated.json()["receipt_token"]
    assert second_token and second_token != first_token
    assert rotated.json()["active"] is True
    revoked = client.put(endpoint, headers=headers, json={"operation": "revoke"})
    assert revoked.status_code == 200
    assert revoked.json()["active"] is False
    with identity_database() as session:
        grants = session.query(EntryAccessGrant).order_by(EntryAccessGrant.id).all()
        assert grants[0].revoked_at is not None
        assert grants[1].revoked_at is not None
        assert {event.action for event in session.query(AuditEvent).all()} == {
            "entry_access_grant.create",
            "entry_access_grant.set_expiry",
            "entry_access_grant.rotate",
            "entry_access_grant.revoke",
        }


def test_entry_receipt_grants_are_contest_scoped_and_manager_scoped(identity_database):
    manager_id = add_user(
        identity_database,
        role=SystemRole.CONTEST_MANAGER,
        username="grant-owner",
        email="owner@example.test",
    )
    add_user(
        identity_database,
        role=SystemRole.CONTEST_MANAGER,
        username="grant-outsider",
        email="outsider@example.test",
    )
    with identity_database.begin() as session:
        participant = Participant()
        session.add(participant)
        session.flush()
        contest = Contest(
            owner_user_id=manager_id,
            name="Scoped contest",
            slug="scoped-contest",
            starts_at=datetime(2026, 1, 1, tzinfo=UTC),
            ends_at=datetime(2026, 1, 1, 2, tzinfo=UTC),
            log_submission_cutoff_at=datetime(2026, 1, 2, tzinfo=UTC),
        )
        session.add(contest)
        session.flush()
        entry = Entry(contest_id=contest.id, participant_id=participant.id, entry_key="guest")
        session.add(entry)
        session.flush()
        contest_id, entry_id = contest.id, entry.id

    outsider = TestClient(app)
    assert (
        outsider.post(
            "/api/v1/auth/login",
            json={"email": "outsider@example.test", "password": "Correct horse battery staple"},
        ).status_code
        == 200
    )
    denied = outsider.put(
        f"/api/v1/contests/{contest_id}/entries/{entry_id}/access-grant",
        headers={"X-CSRF-Token": outsider.cookies.get("contestmaster_csrf")},
        json={"operation": "create"},
    )
    assert denied.status_code == 404
