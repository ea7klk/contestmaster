from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErrorDetail(BaseModel):
    location: list[str | int]
    message: str
    type: str


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str | None
    details: list[ErrorDetail] | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorBody


API_ERROR_RESPONSES = {
    422: {"model": ErrorEnvelope, "description": "Invalid request."},
    409: {
        "model": ErrorEnvelope,
        "description": "The requested change conflicts with retained data.",
    },
    500: {"model": ErrorEnvelope, "description": "Unexpected server error."},
}


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
) -> JSONResponse:
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": getattr(request.state, "request_id", None),
    }
    if details is not None:
        error["details"] = details
    return JSONResponse(status_code=status_code, content={"error": error})


async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = "not_found" if exc.status_code == 404 else "http_error"
    message = exc.detail if isinstance(exc.detail, str) else "The request could not be completed."
    response = error_response(request, exc.status_code, code, message)
    if exc.headers:
        for name, value in exc.headers.items():
            response.headers[name] = value
    return response


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        {"location": list(item["loc"]), "message": item["msg"], "type": item["type"]}
        for item in exc.errors()
    ]
    return error_response(request, 422, "validation_error", "Request validation failed.", details)


async def unexpected_error_handler(request: Request, _exc: Exception) -> JSONResponse:
    # Middleware/application logging captures exceptions without returning internals to clients.
    return error_response(request, 500, "internal_error", "An unexpected server error occurred.")
