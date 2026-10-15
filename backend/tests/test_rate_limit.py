from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from backend.app.rate_limit import SlidingWindowLimiter, enforce_rate_limit


def test_sliding_window_expires_old_attempts_and_returns_retry_time():
    limiter = SlidingWindowLimiter()

    assert limiter.allow("login", "peer", limit=2, window_seconds=10, now=0) == (True, 0)
    assert limiter.allow("login", "peer", limit=2, window_seconds=10, now=1) == (True, 0)
    assert limiter.allow("login", "peer", limit=2, window_seconds=10, now=2) == (False, 8)
    assert limiter.allow("login", "peer", limit=2, window_seconds=10, now=10) == (True, 0)


def test_limiter_bounds_identity_bucket_growth():
    limiter = SlidingWindowLimiter(max_buckets=1)

    assert limiter.allow("request", "first", limit=1, window_seconds=60, now=0)[0]
    assert limiter.allow("request", "second", limit=1, window_seconds=60, now=1) == (False, 60)
    assert len(limiter._windows) == 1


def test_rate_limit_response_includes_retry_after():
    app = FastAPI()

    @app.get("/limited")
    def limited(request: Request):
        enforce_rate_limit(
            request,
            "example",
            identity="test",
            limit=1,
            window_seconds=30,
        )
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/limited").status_code == 200
    rejected = client.get("/limited")
    assert rejected.status_code == 429
    assert rejected.headers["Retry-After"]
