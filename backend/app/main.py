import asyncio
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware

from backend.app.api.errors import (
    API_ERROR_RESPONSES,
    error_response,
    http_error_handler,
    unexpected_error_handler,
    validation_error_handler,
)
from backend.app.config import get_settings
from backend.app.db import SessionFactory, engine, get_session
from backend.app.logging_config import configure_logging
from backend.app.master_data.scheduler import (
    has_active_cty_version,
    nightly_master_data_timer,
    run_cty_sync,
)
from backend.app.models import MasterDataVersionStatus
from backend.app.request_context import request_id_var

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("contestmaster.http")
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    timer: asyncio.Task[None] | None = None
    sync_lock = asyncio.Lock()
    if settings.master_data_scheduler_enabled:
        if not has_active_cty_version(SessionFactory):
            await run_cty_sync(SessionFactory, sync_lock)
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
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-ID", "X-CSRF-Token"],
)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    candidate = request.headers.get("X-Request-ID", "")
    request_id = candidate if REQUEST_ID_PATTERN.fullmatch(candidate) else str(uuid.uuid4())
    token = request_id_var.set(request_id)
    request.state.request_id = request_id
    started = time.perf_counter()
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "http_request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        return response
    except Exception:
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
        return response
    finally:
        request_id_var.reset(token)


@app.get(f"{settings.api_prefix}/health/live", tags=["health"], responses=API_ERROR_RESPONSES)
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get(f"{settings.api_prefix}/health/ready", tags=["health"], responses=API_ERROR_RESPONSES)
def readiness(session: Session = Depends(get_session)) -> dict[str, str]:  # noqa: B008
    session.execute(text("SELECT 1"))
    return {"status": "ready", "database": "ready"}


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
