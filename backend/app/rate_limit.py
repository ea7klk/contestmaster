"""Small process-local sliding-window limits for the single-process deployment."""

from __future__ import annotations

import math
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


class SlidingWindowLimiter:
    """Bounded-memory sliding window limiter; use an edge limiter when scaling out."""

    def __init__(self, *, max_buckets: int = 20_000) -> None:
        self._windows: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._max_buckets = max_buckets

    def allow(
        self,
        bucket: str,
        identity: str,
        *,
        limit: int,
        window_seconds: int,
        now: float | None = None,
    ) -> tuple[bool, int]:
        if limit < 1 or window_seconds < 1:
            raise ValueError("rate limit and window must be positive")
        current = time.monotonic() if now is None else now
        key = (bucket, identity)
        cutoff = current - window_seconds
        with self._lock:
            if key not in self._windows and len(self._windows) >= self._max_buckets:
                expired = [
                    candidate
                    for candidate, values in self._windows.items()
                    if not values or values[-1] <= cutoff
                ]
                for candidate in expired:
                    self._windows.pop(candidate, None)
                if len(self._windows) >= self._max_buckets:
                    return False, window_seconds
            attempts = self._windows[key]
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if len(attempts) >= limit:
                return False, max(1, math.ceil(attempts[0] + window_seconds - current))
            attempts.append(current)
            return True, 0

    def clear(self) -> None:
        """Clear in-memory state; useful for deterministic tests and process shutdown."""
        with self._lock:
            self._windows.clear()


limiter = SlidingWindowLimiter()


def request_identity(request: Request) -> str:
    """Use the directly connected peer; forwarded headers are not trusted by default."""
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(
    request: Request,
    bucket: str,
    *,
    identity: str | None = None,
    limit: int,
    window_seconds: int,
    message: str = "Too many requests. Retry later.",
) -> None:
    allowed, retry_after = limiter.allow(
        bucket,
        identity or request_identity(request),
        limit=limit,
        window_seconds=window_seconds,
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=message,
            headers={"Retry-After": str(retry_after)},
        )
