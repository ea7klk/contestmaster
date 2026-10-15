from fastapi.testclient import TestClient

from backend.app.db import get_session
from backend.app.main import app


class FakeSession:
    def execute(self, _statement):
        return 1


def test_openapi_is_published_under_versioned_api_path():
    response = TestClient(app).get("/api/v1/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "Contestmaster API"
    assert "/api/v1/health/ready" in response.json()["paths"]
    assert "ErrorEnvelope" in response.json()["components"]["schemas"]
    assert "422" in response.json()["paths"]["/api/v1/health/ready"]["get"]["responses"]


def test_request_id_is_echoed_and_error_is_enveloped():
    response = TestClient(app).get("/api/v1/no-such-route", headers={"X-Request-ID": "test-123"})

    assert response.status_code == 404
    assert response.headers["X-Request-ID"] == "test-123"
    assert response.json()["error"]["code"] == "not_found"
    assert response.json()["error"]["request_id"] == "test-123"


def test_invalid_request_id_is_replaced():
    response = TestClient(app).get("/api/v1/no-such-route", headers={"X-Request-ID": "bad id\n"})

    assert response.status_code == 404
    assert response.headers["X-Request-ID"] != "bad id\n"


def test_unexpected_failure_returns_generic_error_and_keeps_request_id():
    def fail():
        raise RuntimeError("database secret should not be exposed")

    app.add_api_route("/_test/failure", fail, methods=["GET"], include_in_schema=False)
    route = app.router.routes[-1]
    try:
        response = TestClient(app).get("/_test/failure", headers={"X-Request-ID": "failure-7"})
    finally:
        app.router.routes.remove(route)

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "failure-7"
    assert response.json()["error"]["code"] == "internal_error"
    assert "database secret" not in response.text


def test_readiness_checks_database_dependency():
    app.dependency_overrides[get_session] = lambda: FakeSession()
    try:
        response = TestClient(app).get("/api/v1/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ready"}
