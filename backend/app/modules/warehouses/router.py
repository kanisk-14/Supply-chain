"""Warehouse endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.common.pagination import resolve_pagination
from app.common.responses import build_paged_response, build_success_response
from app.core.database import get_db
from app.modules.auth.dependencies import require_permissions
from app.modules.auth.permissions import Permission
from app.modules.users.models import User
from app.modules.warehouses.schemas import WarehouseCreate, WarehouseUpdate
from app.modules.warehouses.service import WarehouseService

router = APIRouter(prefix="/warehouses", tags=["warehouses"])


@router.get("", summary="List warehouses")
def list_warehouses(
    page: int | None = Query(default=None, ge=0),
    limit: int | None = Query(default=None, ge=0),
    is_active: bool | None = Query(default=None),
    _user: User = Depends(require_permissions(Permission.WAREHOUSES_READ)),
    db=Depends(get_db),
) -> dict:
    service = WarehouseService(db)
    result = service.list(page=page, limit=limit, is_active=is_active)
    resolved_page, resolved_limit = resolve_pagination(page, limit)
    return build_paged_response(
        result["items"],
        page=resolved_page,
        limit=resolved_limit,
        total=result["total"],
        message="Warehouses retrieved",
    )


@router.get("/{warehouse_id}", summary="Get a single warehouse")
def get_warehouse(
    warehouse_id: int,
    _user: User = Depends(require_permissions(Permission.WAREHOUSES_READ)),
    db=Depends(get_db),
) -> dict:
    return build_success_response(
        WarehouseService(db).get(warehouse_id), message="Warehouse retrieved"
    )


@router.post("", status_code=201, summary="Create a warehouse")
def create_warehouse(
    payload: WarehouseCreate,
    actor: User = Depends(require_permissions(Permission.WAREHOUSES_WRITE)),
    db=Depends(get_db),
) -> dict:
    return build_success_response(
        WarehouseService(db).create(payload, actor=actor),
        message="Warehouse created",
    )


@router.patch("/{warehouse_id}", summary="Update a warehouse")
def update_warehouse(
    warehouse_id: int,
    payload: WarehouseUpdate,
    actor: User = Depends(require_permissions(Permission.WAREHOUSES_WRITE)),
    db=Depends(get_db),
) -> dict:
    return build_success_response(
        WarehouseService(db).update(warehouse_id, payload, actor=actor),
        message="Warehouse updated",
    )