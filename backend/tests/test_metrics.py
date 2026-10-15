from fastapi.testclient import TestClient
from prometheus_client import generate_latest
from pydantic import SecretStr

from backend.app import main
from backend.app.metrics import (
    HTTP_DURATION,
    HTTP_REQUESTS,
    MASTER_DATA_SYNCS,
    UPLOADS,
    normalized_method,
    normalized_status_class,
    record_http_request,
    record_master_data_sync,
    record_upload,
)


def test_http_metrics_use_bounded_method_and_status_labels():
    before = HTTP_REQUESTS.labels("GET", "2xx")._value.get()
    duration_count = HTTP_DURATION.labels("GET")._sum.get()
    record_http_request("get", 200, 0.25)

    assert HTTP_REQUESTS.labels("GET", "2xx")._value.get() == before + 1
    assert HTTP_DURATION.labels("GET")._sum.get() >= duration_count + 0.25
    assert normalized_method("UNTRUSTED-CUSTOM-METHOD") == "OTHER"
    assert normalized_status_class(700) == "other"


def test_operational_metrics_endpoint_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(main.settings, "metrics_enabled", False)
    response = TestClient(main.app).get("/internal/metrics")

    assert response.status_code == 404
    assert "contestmaster_http_requests_total" not in response.text


def test_operational_metrics_endpoint_requires_configured_bearer_token(monkeypatch):
    monkeypatch.setattr(main.settings, "metrics_enabled", True)
    monkeypatch.setattr(main.settings, "metrics_bearer_token", SecretStr("T" * 48))
    client = TestClient(main.app)

    unauthorized = client.get("/internal/metrics")
    assert unauthorized.status_code == 401
    assert unauthorized.headers["WWW-Authenticate"] == "Bearer"

    authorized = client.get("/internal/metrics", headers={"Authorization": f"Bearer {'T' * 48}"})
    assert authorized.status_code == 200
    assert "contestmaster_http_requests_total" in authorized.text
    assert "contestmaster_log_uploads_total" in authorized.text
    assert "target@example.test" not in authorized.text


def test_upload_and_master_data_metrics_allow_only_fixed_labels():
    before = UPLOADS.labels("accepted")._value.get()
    sync_before = MASTER_DATA_SYNCS.labels("cty", "unchanged")._value.get()
    record_upload(201)
    record_upload(422)
    record_upload(503)
    record_master_data_sync("cty", "unchanged")
    record_master_data_sync("attacker-controlled-source", "failed")

    assert UPLOADS.labels("accepted")._value.get() == before + 1
    assert MASTER_DATA_SYNCS.labels("cty", "unchanged")._value.get() == sync_before + 1
    text = generate_latest(main.metrics_registry).decode()
    assert "attacker-controlled-source" not in text
