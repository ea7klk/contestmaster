import asyncio
import hmac
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware

from backend.app.adjudication.api import router as adjudication_router
from backend.app.api.contests import public_router as public_contest_router
from backend.app.api.contests import router as contest_router
from backend.app.api.errors import (
    API_ERROR_RESPONSES,
    error_response,
    http_error_handler,
    unexpected_error_handler,
    validation_error_handler,
)
from backend.app.api.identity import router as identity_router
from backend.app.api.master_data_admin import router as master_data_admin_router
from backend.app.api.participant_identity import router as participant_identity_router
from backend.app.body_limit import RequestBodyLimitMiddleware
from backend.app.config import get_settings
from backend.app.db import SessionFactory, engine, get_session
from backend.app.logging_config import configure_logging
from backend.app.logs.api import MAX_REQUEST_BYTES
from backend.app.logs.api import router as log_router
from backend.app.master_data.scheduler import (
    has_all_required_versions,
    nightly_master_data_timer,
    run_master_data_sync,
)
from backend.app.metrics import record_http_request, record_upload
from backend.app.metrics import registry as metrics_registry
from backend.app.migrations import upgrade_database
from backend.app.models import MasterDataVersionStatus
from backend.app.request_context import request_id_var
from backend.app.results.api import public_router as public_results_router
from backend.app.results.api import router as results_router
from backend.app.rulesets.api import router as ruleset_router
from backend.app.rulesets.operating_catalog_api import router as operating_catalog_router

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("contestmaster.http")
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
MAX_JSON_REQUEST_BYTES = 1024 * 1024


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    timer: asyncio.Task[None] | None = None
    sync_lock = asyncio.Lock()
    await asyncio.to_thread(upgrade_database)
    if settings.master_data_scheduler_enabled:
        if not has_all_required_versions(SessionFactory):
            await run_master_data_sync(SessionFactory, sync_lock)
        timer = asyncio.create_task(
            nightly_master_data_timer(
                SessionFactory, sync_lock, settings.master_data_nightly_hour_utc
            ),
            name="master-data-nightly-timer",
        )
    try:
        yield
    finally:
        if timer is not None:
            timer.cancel()
            try:
                await timer
            except asyncio.CancelledError:
                pass
        engine.dispose()


app = FastAPI(
    title="Contestmaster API",
    version="1.0.0",
    description="Versioned REST API for the Contestmaster amateur radio contest engine.",
    openapi_url=f"{settings.api_prefix}/openapi.json",
    docs_url=f"{settings.api_prefix}/docs",
    redoc_url=f"{settings.api_prefix}/redoc",
    lifespan=lifespan,
)
app.add_exception_handler(StarletteHTTPException, http_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(Exception, unexpected_error_handler)
app.add_middleware(
    RequestBodyLimitMiddleware,
    json_limit=MAX_JSON_REQUEST_BYTES,
    upload_limit=MAX_REQUEST_BYTES,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "X-Request-ID",
        "X-CSRF-Token",
        "Idempotency-Key",
        "X-Entry-Receipt",
    ],
)
app.include_router(ruleset_router, prefix=f"{settings.api_prefix}/rulesets")
app.include_router(operating_catalog_router, prefix=f"{settings.api_prefix}/rulesets")
app.include_router(identity_router, prefix=f"{settings.api_prefix}/auth")
app.include_router(participant_identity_router, prefix=f"{settings.api_prefix}/participants/auth")
app.include_router(log_router, prefix=f"{settings.api_prefix}/public")
app.include_router(master_data_admin_router, prefix=settings.api_prefix)
app.include_router(contest_router, prefix=f"{settings.api_prefix}/contests")
app.include_router(public_contest_router, prefix=f"{settings.api_prefix}/public/contests")
app.include_router(adjudication_router, prefix=settings.api_prefix)
app.include_router(results_router, prefix=settings.api_prefix)
app.include_router(public_results_router, prefix=settings.api_prefix)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    candidate = request.headers.get("X-Request-ID", "")
    request_id = candidate if REQUEST_ID_PATTERN.fullmatch(candidate) else str(uuid.uuid4())
    token = request_id_var.set(request_id)
    request.state.request_id = request_id
    started = time.perf_counter()
    try:
        is_log_upload = (
            request.method == "POST"
            and request.url.path.startswith(f"{settings.api_prefix}/public/contests/")
            and request.url.path.endswith("/logs")
        )
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                declared_length = int(content_length)
            except ValueError:
                declared_length = MAX_JSON_REQUEST_BYTES + 1
            request_limit = MAX_REQUEST_BYTES if is_log_upload else MAX_JSON_REQUEST_BYTES
            oversized = declared_length < 0 or declared_length > request_limit
            if oversized:
                message = (
                    "Log upload requests may not exceed 5 MiB plus multipart overhead."
                    if is_log_upload
                    else "JSON API requests may not exceed 1 MiB."
                )
                response = error_response(
                    request,
                    413,
                    "request_too_large",
                    message,
                )
                response.headers["X-Request-ID"] = request_id
                _add_security_headers(response)
                record_http_request(request.method, 413, time.perf_counter() - started)
                if is_log_upload:
                    record_upload(413)
                return response
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        _add_security_headers(response)
        duration = time.perf_counter() - started
        record_http_request(request.method, response.status_code, duration)
        if is_log_upload or (
            request.method in {"POST", "PUT"}
            and request.url.path.startswith(f"{settings.api_prefix}/public/entries/")
            and request.url.path.endswith("/log")
        ):
            record_upload(response.status_code)
        logger.info(
            "http_request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration * 1000, 2),
            },
        )
        return response
    except Exception:
        record_http_request(request.method, 500, time.perf_counter() - started)
        logger.error(
            "http_request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": 500,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        response = error_response(
            request, 500, "internal_error", "An unexpected server error occurred."
        )
        response.headers["X-Request-ID"] = request_id
        _add_security_headers(response)
        return response
    finally:
        request_id_var.reset(token)


def _add_security_headers(response) -> None:
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Cache-Control", "no-store")
    if settings.app_env in {"staging", "production"}:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )


@app.get(f"{settings.api_prefix}/health/live", tags=["health"], responses=API_ERROR_RESPONSES)
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get(f"{settings.api_prefix}/health/ready", tags=["health"], responses=API_ERROR_RESPONSES)
def readiness(session: Session = Depends(get_session)) -> dict[str, str]:  # noqa: B008
    session.execute(text("SELECT 1"))
    return {"status": "ready", "database": "ready"}


@app.get("/internal/metrics", include_in_schema=False)
def operational_metrics(request: Request) -> Response:
    if not settings.metrics_enabled or settings.metrics_bearer_token is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Not found.")
    expected = f"Bearer {settings.metrics_bearer_token.get_secret_value()}"
    supplied = request.headers.get("authorization", "")
    if not hmac.compare_digest(supplied, expected):
        from fastapi import HTTPException

        raise HTTPException(
            status_code=401,
            detail="Metrics authorization is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Response(generate_latest(metrics_registry), media_type=CONTENT_TYPE_LATEST)


@app.get(f"{settings.api_prefix}/master-data/status", tags=["master-data"])
def master_data_status(session: Session = Depends(get_session)) -> dict[str, object]:  # noqa: B008
    from sqlalchemy import desc, select

    from backend.app.models import MasterDataSyncRun, MasterDataVersion

    active = list(
        session.scalars(
            select(MasterDataVersion)
            .where(MasterDataVersion.status == MasterDataVersionStatus.ACTIVE)
            .order_by(MasterDataVersion.dataset_key)
        )
    )
    latest = session.scalar(select(MasterDataSyncRun).order_by(desc(MasterDataSyncRun.started_at)))
    return {
        "active_versions": [
            {
                "dataset_key": version.dataset_key,
                "version_id": version.id,
                "source_release": version.source_release,
                "valid_from": version.valid_from,
                "valid_to": version.valid_to,
            }
            for version in active
        ],
        "latest_run": (
            {
                "id": latest.id,
                "dataset_key": latest.dataset_key,
                "status": latest.status.value,
                "started_at": latest.started_at,
                "finished_at": latest.finished_at,
                "change_detected": latest.change_detected,
                "has_error": latest.error_summary is not None,
            }
            if latest
            else None
        ),
    }
