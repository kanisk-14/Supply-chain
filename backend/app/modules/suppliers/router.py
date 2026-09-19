"""Supplier endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.common.pagination import resolve_pagination
from app.common.responses import build_paged_response, build_success_response
from app.core.database import get_db
from app.modules.auth.dependencies import require_permissions
from app.modules.auth.permissions import Permission
from app.modules.suppliers.schemas import SupplierCreate, SupplierUpdate
from app.modules.suppliers.service import SupplierService
from app.modules.users.models import User

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.get("", summary="List suppliers")
def list_suppliers(
    page: int | None = Query(default=None, ge=0),
    limit: int | None = Query(default=None, ge=0),
    name: str | None = Query(default=None),
    code: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    _user: User = Depends(require_permissions(Permission.SUPPLIERS_READ)),
    db=Depends(get_db),
) -> dict:
    service = SupplierService(db)
    result = service.list(page=page, limit=limit, name=name, code=code, is_active=is_active)
    resolved_page, resolved_limit = resolve_pagination(page, limit)
    return build_paged_response(
        result["items"],
        page=resolved_page,
        limit=resolved_limit,
        total=result["total"],
        message="Suppliers retrieved",
    )


@router.get("/{supplier_id}", summary="Get a single supplier")
def get_supplier(
    supplier_id: int,
    _user: User = Depends(require_permissions(Permission.SUPPLIERS_READ)),
    db=Depends(get_db),
) -> dict:
    return build_success_response(
        SupplierService(db).get(supplier_id), message="Supplier retrieved"
    )


@router.post("", status_code=201, summary="Create a supplier")
def create_supplier(
    payload: SupplierCreate,
    actor: User = Depends(require_permissions(Permission.SUPPLIERS_WRITE)),
    db=Depends(get_db),
) -> dict:
    return build_success_response(
        SupplierService(db).create(payload, actor=actor),
        message="Supplier created",
    )


@router.patch("/{supplier_id}", summary="Update a supplier")
def update_supplier(
    supplier_id: int,
    payload: SupplierUpdate,
    actor: User = Depends(require_permissions(Permission.SUPPLIERS_WRITE)),
    db=Depends(get_db),
) -> dict:
    return build_success_response(
        SupplierService(db).update(supplier_id, payload, actor=actor),
        message="Supplier updated",
    )