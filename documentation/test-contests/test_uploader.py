"""Tests for the public, idempotent test-log upload client."""

from __future__ import annotations

import importlib.util
import io
import json
import logging
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request

UPLOAD_SCRIPT = Path(__file__).resolve().parent / "upload_logs.py"
UPLOAD_SPEC = importlib.util.spec_from_file_location("test_contest_uploader", UPLOAD_SCRIPT)
assert UPLOAD_SPEC and UPLOAD_SPEC.loader
upload_logs = importlib.util.module_from_spec(UPLOAD_SPEC)
sys.modules[UPLOAD_SPEC.name] = upload_logs
UPLOAD_SPEC.loader.exec_module(upload_logs)


def test_upload_is_anonymous_and_uses_content_stable_idempotency_key(
    tmp_path: Path, monkeypatch
):
    log = tmp_path / "K0AAA.log"
    log.write_bytes(b"START-OF-LOG: 3.0\nEND-OF-LOG:\n")
    requests: list[Request] = []

    class Response:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return json.dumps(
                {"status": "accepted", "entry_id": 42, "receipt_token": "must-not-escape"}
            ).encode()

    def fake_urlopen(request: Request, timeout: int):
        assert timeout == 30
        requests.append(request)
        return Response()

    monkeypatch.setattr(upload_logs, "urlopen", fake_urlopen)
    first = upload_logs.upload_one("http://127.0.0.1:8000", "test-cabrillo-results-sprint", log)
    second = upload_logs.upload_one("http://127.0.0.1:8000", "test-cabrillo-results-sprint", log)

    assert first.accepted and first.entry_id == 42
    assert second.accepted and second.entry_id == 42
    assert requests[0].full_url.endswith(
        "/api/v1/public/contests/test-cabrillo-results-sprint/logs"
    )
    assert requests[0].get_header("Idempotency-key") == requests[1].get_header(
        "Idempotency-key"
    )
    assert requests[0].get_header("Authorization") is None
    assert requests[0].get_header("Content-type").startswith("multipart/form-data; boundary=")
    assert b'name="file"; filename="K0AAA.log"' in requests[0].data
    assert not hasattr(first, "receipt_token")


def test_app_base_url_normalizes_vite_and_api_urls():
    assert upload_logs._base_url("http://127.0.0.1:5173/") == "http://127.0.0.1:5173"
    assert upload_logs._base_url("http://127.0.0.1:8000/api/v1") == "http://127.0.0.1:8000"
    assert (
        upload_logs._display_url("https://user:password@example.test/app?token=secret")
        == "https://example.test/app"
    )


def test_default_delay_stays_below_the_updated_api_rate_limit():
    assert upload_logs.DEFAULT_DELAY_SECONDS == 1.1
    assert 60 / upload_logs.DEFAULT_DELAY_SECONDS < 60


def test_upload_batch_logs_progress_and_summary_metrics(tmp_path: Path, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="contestmaster.test_upload")
    log_dir = tmp_path / "cabrillo" / "logs"
    log_dir.mkdir(parents=True)
    (log_dir / "K0AAA.log").write_text("fixture", encoding="utf-8")
    monkeypatch.setitem(
        upload_logs.CONTESTS,
        "cabrillo",
        (tmp_path / "cabrillo", "test-cabrillo-results-sprint"),
    )
    monkeypatch.setattr(
        upload_logs,
        "upload_one",
        lambda *_args: upload_logs.UploadResult(
            "K0AAA.log", True, entry_id=42, elapsed_seconds=0.25
        ),
    )

    results = upload_logs.upload_set(
        "http://127.0.0.1:8000", "cabrillo", upload_logs.DEFAULT_DELAY_SECONDS
    )

    messages = caplog.text
    assert len(results) == 1 and results[0].accepted
    assert "Starting cabrillo batch" in messages
    assert "Uploading K0AAA.log [1/1]" in messages
    assert "Accepted K0AAA.log [1/1]" in messages
    assert "cabrillo summary: total=1 accepted=1 failed=0 retries=0" in messages
    assert "rate=" in messages and "logs/min" in messages


def test_retry_and_failure_logs_include_safe_details_without_tokens(
    tmp_path: Path, monkeypatch, caplog
):
    caplog.set_level(logging.INFO, logger="contestmaster.test_upload")
    log = tmp_path / "K0AAA.log"
    log.write_text("fixture", encoding="utf-8")
    calls = 0

    class Response:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b'{"status":"accepted","entry_id":42}'

    def rate_limited_then_accepted(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise HTTPError(
                "https://example.test/upload",
                429,
                "Too Many Requests",
                {"Retry-After": "0"},
                io.BytesIO(b'{"detail":"slow down"}'),
            )
        return Response()

    monkeypatch.setattr(upload_logs, "urlopen", rate_limited_then_accepted)
    monkeypatch.setattr(upload_logs.time, "sleep", lambda _delay: None)
    result = upload_logs.upload_one(
        "http://127.0.0.1:8000", "test-cabrillo-results-sprint", log
    )
    assert result.accepted and result.retries == 1
    assert "API rate limit (HTTP 429)" in caplog.text
    assert "retry 1/4" in caplog.text

    caplog.clear()
    error_payload = (
        b'{"detail":"contest closed","receipt_token":"sensitive-test-token"}'
    )
    monkeypatch.setattr(
        upload_logs,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            HTTPError(
                "https://example.test/upload",
                409,
                "Conflict",
                {},
                io.BytesIO(error_payload),
            )
        ),
    )
    failure_dir = tmp_path / "failure"
    (failure_dir / "logs").mkdir(parents=True)
    (failure_dir / "logs" / log.name).write_text("fixture", encoding="utf-8")
    monkeypatch.setitem(
        upload_logs.CONTESTS,
        "cabrillo",
        (failure_dir, "test-cabrillo-results-sprint"),
    )
    batch_results = upload_logs.upload_set(
        "http://127.0.0.1:8000", "cabrillo", upload_logs.DEFAULT_DELAY_SECONDS
    )
    assert len(batch_results) == 1 and not batch_results[0].accepted
    assert "HTTP 409: contest closed" in caplog.text
    assert "1/1" in caplog.text
    assert "sensitive-test-token" not in caplog.text
