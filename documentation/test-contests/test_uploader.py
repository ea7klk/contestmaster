"""Tests for the public, idempotent test-log upload client."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
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
    first = upload_logs.upload_one("http://127.0.0.1:8000", "test-cabrillo-sprint", log)
    second = upload_logs.upload_one("http://127.0.0.1:8000", "test-cabrillo-sprint", log)

    assert first.accepted and first.entry_id == 42
    assert second.accepted and second.entry_id == 42
    assert requests[0].full_url.endswith("/api/v1/public/contests/test-cabrillo-sprint/logs")
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
