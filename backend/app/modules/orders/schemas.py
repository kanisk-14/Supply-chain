"""Order API schemas.

An order is always created with at least one line item; line-item field rules
(``quantity > 0``) are validated by Pydantic, while cross-item business rules
(non-empty order, duplicate product lines, unknown products) are enforced by the
service layer and surface as ``VALIDATION_ERROR``/``NOT_FOUND``.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from app.state_machines.order import OrderStatus


class OrderItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: int
    quantity: Decimal

    @field_validator("quantity")
    @classmethod
    def _quantity_positive(cls, value: Decimal) -> Decimal:
        # ``value != value`` catches NaN, which ``> 0`` lets slip through.
        if value != value or value <= 0:
            raise ValueError("quantity must be > 0")
        return value


class OrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[OrderItemCreate]


class _ProductBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    name: str
    unit: str


class OrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    quantity: Decimal
    product: _ProductBrief


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_number: str
    status: OrderStatus
    created_by: int
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemRead]


def order_payload(order: Any, *, include_shipments: bool = False) -> dict:
    """Serialize an order with its line items (and shipments when requested)."""
    data = OrderRead.model_validate(order).model_dump(mode="json")
    if include_shipments:
        # Imported lazily so the two modules never form an import cycle.
        from app.modules.shipments.schemas import shipment_payload

        data["shipments"] = [
            shipment_payload(s) for s in getattr(order, "shipments", [])
        ]
    return data