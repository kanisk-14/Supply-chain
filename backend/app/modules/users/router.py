"""User endpoints.

Writes are ADMIN-only (``USERS_WRITE``); reads are available to any
authenticated user. All authorization is delegated to ``require_permissions`` —
the router never inspects roles itself.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.common.responses import build_paged_response, build_success_response
from app.core.database import get_db
from app.modules.auth.dependencies import require_permissions
from app.modules.auth.permissions import Permission
from app.modules.users.models import User, UserRole
from app.modules.users.schemas import UserCreate, UserUpdate
from app.modules.users.service import UserService
from app.common.pagination import resolve_pagination

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", summary="List users")
def list_users(
    page: int | None = Query(default=None, ge=0),
    limit: int | None = Query(default=None, ge=0),
    email: str | None = Query(default=None),
    role: UserRole | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    _user: User = Depends(require_permissions(Permission.USERS_READ)),
    db=Depends(get_db),
) -> dict:
    service = UserService(db)
    result = service.list(
        page=page,
        limit=limit,
        email=email,
        role=role,
        is_active=is_active,
    )
    resolved_page, resolved_limit = resolve_pagination(page, limit)
    return build_paged_response(
        result["items"],
        page=resolved_page,
        limit=resolved_limit,
        total=result["total"],
        message="Users retrieved",
    )


@router.get("/{user_id}", summary="Get a single user")
def get_user(
    user_id: int,
    _user: User = Depends(require_permissions(Permission.USERS_READ)),
    db=Depends(get_db),
) -> dict:
    return build_success_response(
        UserService(db).get(user_id), message="User retrieved"
    )


@router.post("", status_code=201, summary="Create a user")
def create_user(
    payload: UserCreate,
    actor: User = Depends(require_permissions(Permission.USERS_WRITE)),
    db=Depends(get_db),
) -> dict:
    return build_success_response(
        UserService(db).create(payload, actor=actor), message="User created"
    )


@router.patch("/{user_id}", summary="Update a user")
def update_user(
    user_id: int,
    payload: UserUpdate,
    actor: User = Depends(require_permissions(Permission.USERS_WRITE)),
    db=Depends(get_db),
) -> dict:
    return build_success_response(
        UserService(db).update(user_id, payload, actor=actor),
        message="User updated",
    )