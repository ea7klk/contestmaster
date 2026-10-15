import json
import logging

from backend.app.logging_config import JsonFormatter
from backend.app.request_context import request_id_var


def test_request_log_is_json_and_includes_correlation_fields():
    token = request_id_var.set("request-42")
    try:
        record = logging.LogRecord("api", logging.INFO, "", 0, "http_request", (), None)
        record.method = "GET"
        record.path = "/api/v1/health/live"
        record.status_code = 200
        record.duration_ms = 1.25
        payload = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)

    assert payload["request_id"] == "request-42"
    assert payload["method"] == "GET"
    assert payload["status_code"] == 200
