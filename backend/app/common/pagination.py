"""Pagination conventions.

Defaults: page=1, limit=25, max_limit=100.
"""

from __future__ import annotations

from typing import Any, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

DEFAULT_PAGE = 1
DEFAULT_LIMIT = 25
MAX_LIMIT = 100

_T = TypeVar("_T")


def resolve_pagination(page: int | None, limit: int | None) -> tuple[int, int]:
    """Clamp caller-supplied page/limit to the documented conventions."""
    resolved_page = max(DEFAULT_PAGE, int(page or DEFAULT_PAGE))
    resolved_limit = min(MAX_LIMIT, max(1, int(limit or DEFAULT_LIMIT)))
    return resolved_page, resolved_limit


def apply_pagination(
    stmt: Select[tuple[_T]],
    page: int | None,
    limit: int | None,
) -> Select[tuple[_T]]:
    """Apply offset/limit to a SQLAlchemy select statement."""
    resolved_page, resolved_limit = resolve_pagination(page, limit)
    return stmt.offset((resolved_page - 1) * resolved_limit).limit(resolved_limit)


def count_total(db: Session, stmt: Select, count_column: Any) -> int:
    """Count rows of a select via a COUNT subquery (MySQL-friendly)."""
    sub = stmt.subquery()
    count_stmt = select(func.count(count_column)).select_from(sub)
    return int(db.execute(count_stmt).scalar_one())


def pagination_meta(page: int, limit: int, total: int) -> dict[str, Any]:
    return {
        "page": page,
        "limit": limit,
        "total": total,
        "pages": (total + limit - 1) // limit if limit else 0,
    }