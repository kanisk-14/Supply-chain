"""Shipment lifecycle state machine.

Persisted states are only:
    PACKED → IN_TRANSIT → DELIVERED

DELAYED is intentionally NOT a persisted state. A shipment is derived to be
delayed — ``expected_delivery_at < now AND status != DELIVERED`` — by the
service/analytics layer, never stored.

PACKED → DELIVERED is not configured here; the business rule requires the
intermediate IN_TRANSIT dispatch step.
"""

from __future__ import annotations

from enum import Enum

from app.state_machines.base import StateMachine


class ShipmentStatus(str, Enum):
    PACKED = "PACKED"
    IN_TRANSIT = "IN_TRANSIT"
    DELIVERED = "DELIVERED"


class ShipmentStateMachine(StateMachine):
    name = "shipment"
    initial = ShipmentStatus.PACKED
    states = set(ShipmentStatus)
    transitions = {
        ShipmentStatus.PACKED: {ShipmentStatus.IN_TRANSIT},
        ShipmentStatus.IN_TRANSIT: {ShipmentStatus.DELIVERED},
        ShipmentStatus.DELIVERED: set(),
    }


shipment_state_machine = ShipmentStateMachine()