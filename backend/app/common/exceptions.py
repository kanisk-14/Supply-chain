"""Application-level exceptions.

Centralized here so that error handling lives in exactly one place: each
exception carries a stable, machine-readable error ``code`` used by the global
exception handler to build the response envelope. Routers/services raise these;
they never format HTTP responses themselves.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base class for all application errors.

    Attributes:
        status_code: HTTP status code mapped to this error.
        code: stable machine-readable error code returned to clients.
        message: human-readable message.
        details: optional structured detail object (never stack traces).
    """

    status_code: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(
        self,
        message: str = "An error occurred",
        *,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class ValidationError(AppError):
    status_code = 400
    code = "VALIDATION_ERROR"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"


class UnauthorizedError(AppError):
    status_code = 401
    code = "UNAUTHORIZED"


class ForbiddenError(AppError):
    status_code = 403
    code = "FORBIDDEN"


class InvalidStateTransitionError(AppError):
    status_code = 409
    code = "INVALID_STATE_TRANSITION"


class InsufficientInventoryError(AppError):
    status_code = 409
    code = "INSUFFICIENT_INVENTORY"


APP_ERROR_TYPES = (
    NotFoundError,
    ValidationError,
    ConflictError,
    UnauthorizedError,
    ForbiddenError,
    InvalidStateTransitionError,
    InsufficientInventoryError,
)