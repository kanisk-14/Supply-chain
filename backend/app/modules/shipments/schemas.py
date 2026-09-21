"""Shipment API schemas.

``DELAYED`` is never a persisted value: ``is_delayed`` is derived on every read
(``expected_delivery_at < now AND status != DELIVERED``) and computed by
:func:`is_delayed`, which the same code path reuses for the ``is_delayed`` list
filter — one definition, no drift.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.core.database import utcnow
from app.state_machines.shipment import ShipmentStatus


class ShipmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: int
    expected_delivery_at: datetime | None = None


class ShipmentDispatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    warehouse_id: int
    expected_delivery_at: datetime | None = None


class ShipmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    shipment_number: str
    tracking_number: str
    order_id: int
    status: ShipmentStatus
    expected_delivery_at: datetime | None
    actual_delivery_at: datetime | None
    created_by: int
    created_at: datetime
    updated_at: datetime


class ShipmentStatusHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    shipment_id: int
    status: ShipmentStatus
    changed_at: datetime
    changed_by: int


def is_delayed(
    expected_delivery_at: datetime | None,
    status: ShipmentStatus,
    now: datetime | None = None,
) -> bool:
    """Derived rule: delayed iff past the expectation and not yet delivered."""
    if expected_delivery_at is None or status == ShipmentStatus.DELIVERED:
        return False
    now = now or utcnow()
    return expected_delivery_at < now


def shipment_payload(shipment: Any) -> dict:
    data = ShipmentRead.model_validate(shipment).model_dump(mode="json")
    data["is_delayed"] = is_delayed(shipment.expected_delivery_at, shipment.status)
    return data


def history_payload(entry: Any) -> dict:
    return ShipmentStatusHistoryRead.model_validate(entry).model_dump(mode="json")


def public_tracking_payload(shipment: Any, history_rows: list[Any]) -> dict:
    """End-user tracking view.

    Deliberately exposes only what a recipient needs: the public tracking
    number, current status, delivery timestamps, derived delay state, and the
    status timeline (status + timestamp per step, ascending). Internal database
    ids, order/user/warehouse references, supplier/inventory data, audit info,
    and permissions never leave the server here.
    """
    status = shipment.status
    return {
        "tracking_number": shipment.tracking_number,
        "status": status.value if hasattr(status, "value") else status,
        "is_delayed": is_delayed(shipment.expected_delivery_at, shipment.status),
        "expected_delivery_at": (
            shipment.expected_delivery_at.isoformat()
            if shipment.expected_delivery_at
            else None
        ),
        "actual_delivery_at": (
            shipment.actual_delivery_at.isoformat()
            if shipment.actual_delivery_at
            else None
        ),
        "timeline": [
            {
                "status": (
                    entry.status.value
                    if hasattr(entry.status, "value")
                    else entry.status
                ),
                "changed_at": entry.changed_at.isoformat(),
            }
            for entry in history_rows
        ],
    }