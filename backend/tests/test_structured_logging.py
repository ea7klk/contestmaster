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


def test_exception_logging_records_type_without_untrusted_message_or_traceback():
    import sys

    try:
        raise RuntimeError("session-token=private-value")
    except RuntimeError:
        record = logging.LogRecord("api", logging.ERROR, "", 0, "operation_failed", (), None)
        record.exc_info = sys.exc_info()
        output = JsonFormatter().format(record)

    assert '"exception_type":"RuntimeError"' in output
    assert "private-value" not in output
    assert "Traceback" not in output


def test_job_events_include_safe_correlation_fields_and_omit_unapproved_fields():
    record = logging.LogRecord("jobs", logging.INFO, "", 0, "master_data_sync_finished", (), None)
    record.dataset_key = "cty"
    record.run_id = 17
    record.status = "succeeded"
    record.participant_email = "private@example.test"

    payload = json.loads(JsonFormatter().format(record))

    assert payload["dataset_key"] == "cty"
    assert payload["run_id"] == 17
    assert payload["status"] == "succeeded"
    assert "participant_email" not in payload
