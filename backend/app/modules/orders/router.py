"""Order endpoints.

Reads require any authenticated role; creating orders and driving their state
machine require ``ORDERS_WRITE`` (SUPPLY_CHAIN_MANAGER / ADMIN). Routers only
translate HTTP to service calls — every business rule lives in the service.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.common.pagination import resolve_pagination
from app.common.responses import build_paged_response, build_success_response
from app.core.database import get_db
from app.modules.auth.dependencies import require_permissions
from app.modules.auth.permissions import Permission
from app.modules.orders.schemas import OrderCreate
from app.modules.orders.service import OrderService
from app.modules.users.models import User
from app.state_machines.order import OrderStatus

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("", summary="List orders (paged)")
def list_orders(
    page: int | None = Query(default=None, ge=0),
    limit: int | None = Query(default=None, ge=0),
    status: OrderStatus | None = Query(default=None),
    created_by: int | None = Query(default=None),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    include_shipments: bool = Query(default=False),
    _user: User = Depends(require_permissions(Permission.ORDERS_READ)),
    db=Depends(get_db),
) -> dict:
    service = OrderService(db)
    result = service.list(
        page=page,
        limit=limit,
        status=status,
        created_by=created_by,
        start=start,
        end=end,
        include_shipments=include_shipments,
    )
    resolved_page, resolved_limit = resolve_pagination(page, limit)
    return build_paged_response(
        result["items"],
        page=resolved_page,
        limit=resolved_limit,
        total=result["total"],
        message="Orders retrieved",
    )


@router.get("/{order_id}", summary="Get a single order with its line items")
def get_order(
    order_id: int,
    include_shipments: bool = Query(default=False),
    _user: User = Depends(require_permissions(Permission.ORDERS_READ)),
    db=Depends(get_db),
) -> dict:
    return build_success_response(
        OrderService(db).get(order_id, include_shipments=include_shipments),
        message="Order retrieved",
    )


@router.post("", status_code=201, summary="Create an order")
def create_order(
    payload: OrderCreate,
    actor: User = Depends(require_permissions(Permission.ORDERS_WRITE)),
    db=Depends(get_db),
) -> dict:
    return build_success_response(
        OrderService(db).create(payload, actor=actor), message="Order created"
    )


@router.post("/{order_id}/confirm", summary="Confirm an order (PLACED → CONFIRMED)")
def confirm_order(
    order_id: int,
    actor: User = Depends(require_permissions(Permission.ORDERS_WRITE)),
    db=Depends(get_db),
) -> dict:
    return build_success_response(
        OrderService(db).confirm(order_id, actor=actor), message="Order confirmed"
    )


@router.post("/{order_id}/fulfill", summary="Fulfill an order (CONFIRMED → FULFILLED)")
def fulfill_order(
    order_id: int,
    actor: User = Depends(require_permissions(Permission.ORDERS_WRITE)),
    db=Depends(get_db),
) -> dict:
    return build_success_response(
        OrderService(db).fulfill(order_id, actor=actor), message="Order fulfilled"
    )


@router.post("/{order_id}/cancel", summary="Cancel an order (PLACED/CONFIRMED → CANCELLED)")
def cancel_order(
    order_id: int,
    actor: User = Depends(require_permissions(Permission.ORDERS_WRITE)),
    db=Depends(get_db),
) -> dict:
    return build_success_response(
        OrderService(db).cancel(order_id, actor=actor), message="Order cancelled"
    )