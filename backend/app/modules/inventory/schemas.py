"""Inventory API schemas.

Current stock is a per ``(product, warehouse)`` row; the transaction history is
append-only and returned separately from live quantities.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.inventory.models import InventoryTransactionType


class AdjustRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: int
    warehouse_id: int
    delta: Decimal
    reason: str | None = Field(default=None, max_length=255)

    @field_validator("delta")
    @classmethod
    def _delta_nonzero(cls, value: Decimal) -> Decimal:
        if value == 0:
            raise ValueError("delta must not be zero")
        return value


class TransferRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: int
    from_warehouse_id: int
    to_warehouse_id: int
    quantity: Decimal

    @field_validator("quantity")
    @classmethod
    def _quantity_positive(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("quantity must be > 0")
        return value


class _ProductBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    name: str
    unit: str
    reorder_threshold: Decimal


class _WarehouseBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str


class InventoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    warehouse_id: int
    quantity: Decimal
    created_at: datetime
    updated_at: datetime
    product: _ProductBrief
    warehouse: _WarehouseBrief
    below_threshold: bool = False


class InventoryTransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    warehouse_id: int
    type: InventoryTransactionType
    quantity: Decimal
    reference_type: str | None
    reference_id: int | None
    created_by: int
    created_at: datetime


def inventory_payload(inventory: Any, *, below_threshold: bool | None = None) -> dict:
    """Serialize an inventory row with product/warehouse briefs.

    ``below_threshold`` is derived (quantity < product reorder threshold) unless
    explicitly supplied by the caller.
    """
    product = getattr(inventory, "product", None)
    warehouse = getattr(inventory, "warehouse", None)
    below = below_threshold
    if below is None and product is not None:
        below = inventory.quantity < product.reorder_threshold
    read = InventoryRead.model_validate(inventory)
    data = read.model_dump(mode="json")
    data["below_threshold"] = bool(below) if below is not None else False
    return data


def transaction_payload(transaction: Any) -> dict:
    return InventoryTransactionRead.model_validate(transaction).model_dump(mode="json")