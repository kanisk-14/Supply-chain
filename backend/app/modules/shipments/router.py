"""Shipment endpoints.

Reads require any authenticated role; creating, dispatching, and delivering
require ``SHIPMENTS_WRITE`` (WAREHOUSE_MANAGER / SUPPLY_CHAIN_MANAGER / ADMIN).
Routers only translate HTTP to service calls — every business rule lives in the
service layer.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.common.pagination import resolve_pagination
from app.common.responses import build_paged_response, build_success_response
from app.core.database import get_db
from app.modules.auth.dependencies import require_permissions
from app.modules.auth.permissions import Permission
from app.modules.shipments.schemas import ShipmentCreate, ShipmentDispatchRequest
from app.modules.shipments.service import ShipmentService
from app.modules.users.models import User
from app.state_machines.shipment import ShipmentStatus

router = APIRouter(prefix="/shipments", tags=["shipments"])


@router.get("", summary="List shipments (paged)")
def list_shipments(
    page: int | None = Query(default=None, ge=0),
    limit: int | None = Query(default=None, ge=0),
    order_id: int | None = Query(default=None),
    status: ShipmentStatus | None = Query(default=None),
    is_delayed: bool | None = Query(default=None),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    _user: User = Depends(require_permissions(Permission.SHIPMENTS_READ)),
    db=Depends(get_db),
) -> dict:
    service = ShipmentService(db)
    result = service.list(
        page=page,
        limit=limit,
        order_id=order_id,
        status=status,
        is_delayed=is_delayed,
        start=start,
        end=end,
    )
    resolved_page, resolved_limit = resolve_pagination(page, limit)
    return build_paged_response(
        result["items"],
        page=resolved_page,
        limit=resolved_limit,
        total=result["total"],
        message="Shipments retrieved",
    )


@router.get("/{shipment_id}/history", summary="Append-only shipment status history")
def get_shipment_history(
    shipment_id: int,
    _user: User = Depends(require_permissions(Permission.SHIPMENTS_READ)),
    db=Depends(get_db),
) -> dict:
    return build_success_response(
        ShipmentService(db).history(shipment_id), message="Shipment history retrieved"
    )


@router.get("/{shipment_id}", summary="Get a single shipment")
def get_shipment(
    shipment_id: int,
    _user: User = Depends(require_permissions(Permission.SHIPMENTS_READ)),
    db=Depends(get_db),
) -> dict:
    return build_success_response(
        ShipmentService(db).get(shipment_id), message="Shipment retrieved"
    )


@router.post("", status_code=201, summary="Create a shipment for a CONFIRMED order")
def create_shipment(
    payload: ShipmentCreate,
    actor: User = Depends(require_permissions(Permission.SHIPMENTS_WRITE)),
    db=Depends(get_db),
) -> dict:
    return build_success_response(
        ShipmentService(db).create(payload, actor=actor), message="Shipment created"
    )


@router.post("/{shipment_id}/dispatch", summary="Dispatch (PACKED → IN_TRANSIT)")
def dispatch_shipment(
    shipment_id: int,
    payload: ShipmentDispatchRequest,
    actor: User = Depends(require_permissions(Permission.SHIPMENTS_WRITE)),
    db=Depends(get_db),
) -> dict:
    return build_success_response(
        ShipmentService(db).dispatch(shipment_id, payload, actor=actor),
        message="Shipment dispatched",
    )


@router.post("/{shipment_id}/deliver", summary="Deliver (IN_TRANSIT → DELIVERED)")
def deliver_shipment(
    shipment_id: int,
    actor: User = Depends(require_permissions(Permission.SHIPMENTS_WRITE)),
    db=Depends(get_db),
) -> dict:
    return build_success_response(
        ShipmentService(db).deliver(shipment_id, actor=actor),
        message="Shipment delivered",
    )