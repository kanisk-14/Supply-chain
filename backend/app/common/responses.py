"""Consistent HTTP response envelopes.

Every successful response has the shape::

    {"success": true, "data": ..., "message": "..."}

Paginated collections add ``meta`` (page/limit/total). Every error has::

    {"success": false, "error": {"code": ..., "message": ..., "details": ...}}

These builders are used by the envelope router and the global exception
handlers, so controllers never format responses ad hoc.
"""

from __future__ import annotations

from typing import Any

DEFAULT_SUCCESS_MESSAGE = "Operation successful"


def build_success_response(
    data: Any = None,
    message: str = DEFAULT_SUCCESS_MESSAGE,
) -> dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "message": message,
    }


def build_paged_response(
    data: list[Any],
    page: int,
    limit: int,
    total: int,
    message: str = DEFAULT_SUCCESS_MESSAGE,
) -> dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "meta": {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": (total + limit - 1) // limit if limit else 0,
        },
        "message": message,
    }


def build_error_response(
    code: str,
    message: str,
    details: Any = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return {"success": False, "error": error}