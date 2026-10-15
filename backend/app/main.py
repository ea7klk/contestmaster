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
from backend.app.db import engine, get_session
from backend.app.logging_config import configure_logging
from backend.app.request_context import request_id_var

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("contestmaster.http")
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield
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
