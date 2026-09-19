"""Centralized exception handling.

All error responses are built here via the envelope helpers, so response
formatting is never scattered across the application. Internal stack traces and
database errors are never exposed to clients.

Mapping:
    AppError subclasses      -> their declared status_code + code
    RequestValidationError   -> 422 VALIDATION_ERROR (FastAPI/Pydantic)
    Starlette HTTPException  -> status code + best-effort code
    unhandled Exception      -> 500 INTERNAL_ERROR (logged server-side)
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.common.exceptions import AppError
from app.common.responses import build_error_response

logger = logging.getLogger("app")

_HTTP_ERROR_CODES = {
    400: "VALIDATION_ERROR",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "TOO_MANY_REQUESTS",
}


def _clean_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reduce Pydantic error dicts to a JSON-safe, client-friendly shape.

    The raw ``errors()`` output can embed exception objects in ``context``,
    which the JSON encoder cannot serialize; never forward it verbatim.
    """
    cleaned: list[dict[str, Any]] = []
    for error in errors:
        loc = error.get("loc", ())
        cleaned.append(
            {
                "field": ".".join(str(part) for part in loc),
                "message": str(error.get("msg", "Invalid value")),
                "type": error.get("type", "value_error"),
            }
        )
    return cleaned


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=build_error_response(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=build_error_response(
                "VALIDATION_ERROR",
                "Request validation failed",
                details=_clean_validation_errors(exc.errors()),
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        message = str(exc.detail) if exc.detail else "HTTP error"
        return JSONResponse(
            status_code=exc.status_code,
            content=build_error_response(
                _HTTP_ERROR_CODES.get(exc.status_code, "HTTP_ERROR"),
                message,
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=build_error_response(
                "INTERNAL_ERROR",
                "Internal server error",
            ),
        )