"""Inventory endpoints.

Reads require any authenticated role; adjustments and transfers require
``INVENTORY_WRITE`` (WAREHOUSE_MANAGER / SUPPLY_CHAIN_MANAGER / ADMIN), matching
the documented contract.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.common.pagination import resolve_pagination
from app.common.responses import build_paged_response, build_success_response
from app.core.database import get_db
from app.modules.auth.dependencies import require_permissions
from app.modules.auth.permissions import Permission
from app.modules.inventory.models import InventoryTransactionType
from app.modules.inventory.schemas import AdjustRequest, TransferRequest
from app.modules.inventory.service import InventoryService
from app.modules.users.models import User

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("", summary="List inventory (current stock)")
def list_inventory(
    page: int | None = Query(default=None, ge=0),
    limit: int | None = Query(default=None, ge=0),
    product_id: int | None = Query(default=None),
    warehouse_id: int | None = Query(default=None),
    below_threshold: bool | None = Query(default=None),
    actor: User = Depends(require_permissions(Permission.INVENTORY_READ)),
    db=Depends(get_db),
) -> dict:
    service = InventoryService(db)
    result = service.list(
        page=page,
        limit=limit,
        product_id=product_id,
        warehouse_id=warehouse_id,
        below_threshold=below_threshold,
        actor=actor,
    )
    resolved_page, resolved_limit = resolve_pagination(page, limit)
    return build_paged_response(
        result["items"],
        page=resolved_page,
        limit=resolved_limit,
        total=result["total"],
        message="Inventory retrieved",
    )


@router.post("/adjust", summary="Adjust stock by a signed delta")
def adjust_stock(
    payload: AdjustRequest,
    actor: User = Depends(require_permissions(Permission.INVENTORY_WRITE)),
    db=Depends(get_db),
) -> dict:
    service = InventoryService(db)
    record = service.adjust(
        product_id=payload.product_id,
        warehouse_id=payload.warehouse_id,
        delta=payload.delta,
        reason=payload.reason,
        actor=actor,
    )
    return build_success_response(record, message="Inventory adjusted")


@router.post("/transfer", summary="Atomically transfer stock between warehouses")
def transfer_stock(
    payload: TransferRequest,
    actor: User = Depends(require_permissions(Permission.INVENTORY_WRITE)),
    db=Depends(get_db),
) -> dict:
    service = InventoryService(db)
    records = service.transfer(
        product_id=payload.product_id,
        from_warehouse_id=payload.from_warehouse_id,
        to_warehouse_id=payload.to_warehouse_id,
        quantity=payload.quantity,
        actor=actor,
    )
    return build_success_response(records, message="Inventory transferred")


@router.get("/transactions", summary="Append-only stock movement history")
def list_transactions(
    page: int | None = Query(default=None, ge=0),
    limit: int | None = Query(default=None, ge=0),
    product_id: int | None = Query(default=None),
    warehouse_id: int | None = Query(default=None),
    type: InventoryTransactionType | None = Query(default=None),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    actor: User = Depends(require_permissions(Permission.INVENTORY_TRANSACTIONS_READ)),
    db=Depends(get_db),
) -> dict:
    service = InventoryService(db)
    result = service.list_transactions(
        page=page,
        limit=limit,
        product_id=product_id,
        warehouse_id=warehouse_id,
        txn_type=type,
        start=start,
        end=end,
        actor=actor,
    )
    resolved_page, resolved_limit = resolve_pagination(page, limit)
    return build_paged_response(
        result["items"],
        page=resolved_page,
        limit=resolved_limit,
        total=result["total"],
        message="Inventory transactions retrieved",
    )


@router.get("/{inventory_id}", summary="Get a single inventory record")
def get_inventory(
    inventory_id: int,
    _user: User = Depends(require_permissions(Permission.INVENTORY_READ)),
    db=Depends(get_db),
) -> dict:
    return build_success_response(
        InventoryService(db).get(inventory_id), message="Inventory retrieved"
    )