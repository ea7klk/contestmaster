from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.auth import hash_password
from backend.app.db import Base, get_session
from backend.app.main import app
from backend.app.models import AuditEvent, OperatingCatalogItem, SystemRole, SystemUser


@pytest.fixture
def catalog_database(monkeypatch):
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
        "backend.app.api.auth.get_settings", lambda: SimpleNamespace(secure_cookies=False)
    )
    try:
        yield factory
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def add_user(factory, role: SystemRole, username: str) -> None:
    with factory.begin() as session:
        session.add(
            SystemUser(
                username=username,
                email_normalized=f"{username}@example.test",
                display_name=username,
                role=role,
                password_hash=hash_password("Correct horse battery staple"),
            )
        )


def signed_in(email: str) -> tuple[TestClient, str]:
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "Correct horse battery staple"}
    )
    assert response.status_code == 200
    return client, response.json()["csrf_token"]


def test_public_catalog_lists_active_values_and_admin_routes_require_global_role(catalog_database):
    add_user(catalog_database, SystemRole.CONTEST_MANAGER, "manager")
    with catalog_database.begin() as session:
        session.add(
            OperatingCatalogItem(
                kind="band",
                key="60m",
                label="60 m",
                description="",
                frequency_range="5 MHz",
                sort_order=0,
                is_active=True,
                contest_free=True,
            )
        )

    public = TestClient(app)
    result = public.get("/api/v1/rulesets/operating-catalog")
    assert result.status_code == 200
    assert result.json()["items"][0]["contest_free"] is True
    assert public.get("/api/v1/rulesets/admin/operating-catalog").status_code == 401

    manager, _csrf = signed_in("manager@example.test")
    assert manager.get("/api/v1/rulesets/admin/operating-catalog").status_code == 403
    assert (
        manager.post(
            "/api/v1/rulesets/admin/operating-catalog",
            json={"kind": "mode", "key": "FT8", "label": "FT8"},
        ).status_code
        == 403
    )


def test_global_admin_can_manage_catalog_and_every_change_is_audited(catalog_database):
    add_user(catalog_database, SystemRole.GLOBAL_ADMINISTRATOR, "admin")
    client, csrf = signed_in("admin@example.test")
    headers = {"X-CSRF-Token": csrf}
    created = client.post(
        "/api/v1/rulesets/admin/operating-catalog",
        headers=headers,
        json={
            "kind": "mode",
            "key": "FT8",
            "label": "FT8",
            "description": "Weak-signal digital mode",
            "sort_order": 15,
            "is_active": True,
            "contest_free": False,
        },
    )
    assert created.status_code == 201
    item = created.json()
    assert client.get("/api/v1/rulesets/operating-catalog").json()["items"][0]["key"] == "FT8"

    updated = client.put(
        f"/api/v1/rulesets/admin/operating-catalog/{item['id']}",
        headers=headers,
        json={
            "kind": "mode",
            "key": "FT8",
            "label": "FT8 digital",
            "description": "Updated label",
            "sort_order": 15,
            "is_active": False,
            "contest_free": False,
        },
    )
    assert updated.status_code == 200
    assert client.get("/api/v1/rulesets/operating-catalog").json()["items"] == []
    assert (
        client.delete(
            f"/api/v1/rulesets/admin/operating-catalog/{item['id']}", headers=headers
        ).status_code
        == 204
    )
    with catalog_database() as session:
        actions = session.scalars(select(AuditEvent.action).order_by(AuditEvent.id)).all()
    assert actions == [
        "operating_catalog.item_created",
        "operating_catalog.item_updated",
        "operating_catalog.item_deleted",
    ]


def test_catalog_key_in_a_saved_ruleset_cannot_be_deleted(catalog_database):
    add_user(catalog_database, SystemRole.GLOBAL_ADMINISTRATOR, "admin")
    client, csrf = signed_in("admin@example.test")
    headers = {"X-CSRF-Token": csrf}
    item = client.post(
        "/api/v1/rulesets/admin/operating-catalog",
        headers=headers,
        json={
            "kind": "band",
            "key": "60m",
            "label": "60 m",
            "description": "",
            "frequency_range": "5 MHz",
            "sort_order": 0,
            "is_active": True,
            "contest_free": False,
        },
    ).json()
    with catalog_database.begin() as session:
        from backend.app.models import RulesetVersion

        session.add(
            RulesetVersion(
                ruleset_key="sample",
                version="1",
                rule_type_keys=["eligibility"],
                configuration={
                    "rules": [{"rule": {"kind": "eligibility", "allowed_bands": ["60m"]}}]
                },
            )
        )
    response = client.delete(
        f"/api/v1/rulesets/admin/operating-catalog/{item['id']}", headers=headers
    )
    assert response.status_code == 409
    assert "deactivate" in response.json()["error"]["message"]


def test_ruleset_validation_requires_active_band_and_mode_catalog_keys(catalog_database):
    payload = {
        "schema_version": 1,
        "ruleset_key": "catalog-test",
        "version": "1",
        "rules": [
            {
                "id": "schedule",
                "rule": {
                    "kind": "schedule",
                    "duration_minutes": 60,
                    "fixed_start_utc": "2026-01-01T00:00:00Z",
                },
            },
            {
                "id": "submission",
                "rule": {
                    "kind": "submission",
                    "cutoff_mode": "at_utc",
                    "cutoff_utc": "2026-01-02T00:00:00Z",
                    "late_policy": "reject",
                },
            },
            {
                "id": "categories",
                "rule": {
                    "kind": "categories",
                    "dimensions": [
                        {
                            "key": "operator",
                            "label": "Operator",
                            "choices": [{"key": "single", "label": "Single"}],
                        }
                    ],
                },
            },
            {
                "id": "exchange",
                "rule": {
                    "kind": "exchange",
                    "fields": [
                        {
                            "key": "serial",
                            "label": "Serial",
                            "value_type": "serial",
                            "serial_scope": "entry",
                        }
                    ],
                },
            },
            {
                "id": "eligibility",
                "rule": {"kind": "eligibility", "allowed_bands": ["60m"], "allowed_modes": ["FT8"]},
            },
            {
                "id": "duplicates",
                "rule": {
                    "kind": "duplicates",
                    "scope": ["worked_callsign"],
                    "effect": "not_credited",
                },
            },
            {"id": "points", "rule": {"kind": "points", "fact": "fixed", "fixed_points": 1}},
            {
                "id": "score",
                "rule": {"kind": "score_formula", "start": {"variable": "points_total"}},
            },
            {"id": "format", "rule": {"kind": "format_mapping", "format": "cabrillo"}},
        ],
    }
    response = TestClient(app).post("/api/v1/rulesets/validate", json=payload)
    assert response.status_code == 422
    assert "not an active band" in str(response.json())

    with catalog_database.begin() as session:
        session.add_all(
            [
                OperatingCatalogItem(
                    kind="band",
                    key="60m",
                    label="60 m",
                    description="",
                    sort_order=1,
                    is_active=True,
                    contest_free=False,
                ),
                OperatingCatalogItem(
                    kind="mode",
                    key="FT8",
                    label="FT8",
                    description="",
                    sort_order=1,
                    is_active=True,
                    contest_free=False,
                ),
            ]
        )
    assert TestClient(app).post("/api/v1/rulesets/validate", json=payload).status_code == 200

    with catalog_database.begin() as session:
        session.scalar(
            select(OperatingCatalogItem).where(OperatingCatalogItem.kind == "mode")
        ).is_active = False
    response = TestClient(app).post("/api/v1/rulesets/validate", json=payload)
    assert response.status_code == 422
    assert "not an active mode" in str(response.json())
