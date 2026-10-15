"""Bound request bodies even when clients omit Content-Length."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request
from starlette.responses import JSONResponse

ASGIApp = Callable[
    [dict, Callable[..., Awaitable[dict]], Callable[..., Awaitable[None]]], Awaitable[None]
]


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, *, json_limit: int, upload_limit: int) -> None:
        self.app = app
        self.json_limit = json_limit
        self.upload_limit = upload_limit

    async def __call__(
        self,
        scope: dict,
        receive: Callable[..., Awaitable[dict]],
        send: Callable[..., Awaitable[None]],
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        is_upload = (
            scope.get("method") == "POST"
            and path.startswith("/api/v1/public/contests/")
            and path.endswith("/logs")
        )
        limit = self.upload_limit if is_upload else self.json_limit
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            body.extend(message.get("body", b""))
            if len(body) > limit:
                request = Request(scope)
                response = JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "request_too_large",
                            "message": (
                                "Log upload requests may not exceed 5 MiB plus multipart overhead."
                                if is_upload
                                else "JSON API requests may not exceed 1 MiB."
                            ),
                            "request_id": getattr(request.state, "request_id", None),
                        }
                    },
                )
                await response(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        replayed = False

        async def replay_receive() -> dict:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay_receive, send)
