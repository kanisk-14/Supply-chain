"""Shipment business rules and transactional workflows.

The shipment lifecycle is driven purely by ``ShipmentStateMachine``:
``PACKED → IN_TRANSIT → DELIVERED``. Every valid transition appends a row to
``shipment_status_history`` (append-only, never updated). ``DELAYED`` is never
persisted — it is derived per read via :func:`app.modules.shipments.schemas.is_delayed`.

Inventory integration: ``dispatch`` is the moment goods physically leave a
warehouse. For every order line item it locks the ``(product, warehouse)`` row
FOR UPDATE, validates availability, decrements stock, and appends a
``SHIPMENT_DISPATCH`` inventory transaction — all inside one transaction by
reusing :meth:`app.modules.inventory.service.InventoryService.dispatch_stock`.
A shortage of any line rolls the whole dispatch back (shipment stays PACKED, no
history, no inventory movement, no audit). The shipment carries the full order
(no per-shipment line split exists in the schema), so a second dispatch for the
same order will fail the stock check rather than oversell.
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session

from app.common.exceptions import NotFoundError, ValidationError
from app.common.transactions import transaction
from app.core.database import utcnow
from app.modules.alerts.service import AlertService
from app.modules.audit_logs.service import AuditLogService
from app.modules.inventory.service import InventoryService
from app.modules.orders.repositories import OrderRepository
from app.modules.orders.models import OrderStatus
from app.modules.shipments.models import Shipment
from app.modules.shipments.repositories import ShipmentRepository
from app.modules.shipments.schemas import (
    ShipmentCreate,
    ShipmentDispatchRequest,
    history_payload,
    shipment_payload,
)
from app.modules.users.models import User
from app.modules.warehouses.repositories import WarehouseRepository
from app.state_machines.shipment import ShipmentStatus, shipment_state_machine


class ShipmentService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ShipmentRepository(db)
        self.orders = OrderRepository(db)
        self.warehouses = WarehouseRepository(db)
        self.inventory = InventoryService(db)
        self.audit = AuditLogService(db)
        self.alerts = AlertService(db)

    # ---- reads ----

    def list(
        self,
        *,
        page,
        limit,
        order_id=None,
        status=None,
        is_delayed=None,
        start=None,
        end=None,
    ) -> dict:
        result = self.repo.list(
            page=page,
            limit=limit,
            order_id=order_id,
            status=status,
            is_delayed=is_delayed,
            start=start,
            end=end,
        )
        return {
            "items": [shipment_payload(s) for s in result.items],
            "total": result.total,
        }

    def get(self, shipment_id: int) -> dict:
        return shipment_payload(self._get_or_raise(shipment_id))

    def history(self, shipment_id: int) -> list[dict]:
        self._get_or_raise(shipment_id)
        return [history_payload(row) for row in self.repo.list_history(shipment_id)]

    # ---- create ----

    def create(self, payload: ShipmentCreate, *, actor: User) -> dict:
        with transaction(self.db):
            order = self.orders.get_by_id(payload.order_id)
            if order is None:
                raise NotFoundError(f"Order {payload.order_id} not found")
            if order.status != OrderStatus.CONFIRMED:
                raise ValidationError(
                    "A shipment can only be created for a CONFIRMED order",
                    details={
                        "order_id": order.id,
                        "order_status": order.status.value,
                    },
                )

            shipment = Shipment(
                order_id=order.id,
                created_by=actor.id,
                expected_delivery_at=payload.expected_delivery_at,
                # Pending placeholder so the insert satisfies the NOT NULL
                # unique column; replaced by the deterministic id-based number
                # right after flush, within the same transaction.
                shipment_number=f"SHP-PEND-{uuid4().hex[:16]}",
            )
            self.repo.add(shipment)
            # A deterministic unique shipment number derived from the primary key.
            shipment.shipment_number = f"SHP-{shipment.id:08d}"
            self.db.flush()

            # An initial PACKED history row reflects creation itself.
            now = utcnow()
            self.repo.add_history(shipment.id, ShipmentStatus.PACKED, actor.id, now)

            self.alerts.reconcile_shipment_overdue(
                shipment_id=shipment.id,
                status=shipment.status,
                expected_delivery_at=shipment.expected_delivery_at,
            )

            self.audit.record(
                user_id=actor.id,
                action="SHIPMENT_CREATED",
                entity_type="shipment",
                entity_id=shipment.id,
                new_value={
                    "id": shipment.id,
                    "shipment_number": shipment.shipment_number,
                    "order_id": shipment.order_id,
                    "status": ShipmentStatus.PACKED.value,
                    "expected_delivery_at": (
                        shipment.expected_delivery_at.isoformat()
                        if shipment.expected_delivery_at
                        else None
                    ),
                },
            )
            return shipment_payload(shipment)

    # ---- state transitions ----

    def dispatch(
        self,
        shipment_id: int,
        payload: ShipmentDispatchRequest,
        *,
        actor: User,
    ) -> dict:
        with transaction(self.db):
            shipment = self._get_or_raise(shipment_id)
            order = self.orders.get_by_id(shipment.order_id)
            if order is None:
                raise NotFoundError(f"Order {shipment.order_id} not found")

            # Raises InvalidStateTransitionError (409) when disallowed.
            shipment_state_machine.transition(
                shipment.status, ShipmentStatus.IN_TRANSIT
            )

            warehouse = self.warehouses.get_by_id(payload.warehouse_id)
            if warehouse is None:
                raise NotFoundError(f"Warehouse {payload.warehouse_id} not found")

            # Stock-out per line item, in product order so concurrent dispatches
            # acquire row locks in the same deterministic sequence.
            consumed = []
            for item in sorted(order.items, key=lambda i: i.product_id):
                old_qty, new_qty = self.inventory.dispatch_stock(
                    product_id=item.product_id,
                    warehouse_id=payload.warehouse_id,
                    quantity=item.quantity,
                    reference_id=shipment.id,
                    actor=actor,
                )
                consumed.append(
                    {
                        "product_id": item.product_id,
                        "quantity": str(item.quantity),
                        "available": str(old_qty),
                        "remaining": str(new_qty),
                    }
                )

            old_status = shipment.status
            shipment.status = ShipmentStatus.IN_TRANSIT
            if payload.expected_delivery_at is not None:
                shipment.expected_delivery_at = payload.expected_delivery_at
            self.db.flush()

            now = utcnow()
            self.repo.add_history(
                shipment.id, ShipmentStatus.IN_TRANSIT, actor.id, now
            )
            self.alerts.reconcile_shipment_overdue(
                shipment_id=shipment.id,
                status=shipment.status,
                expected_delivery_at=shipment.expected_delivery_at,
            )
            self.audit.record(
                user_id=actor.id,
                action="SHIPMENT_DISPATCHED",
                entity_type="shipment",
                entity_id=shipment.id,
                old_value={"status": old_status.value, "order_id": order.id},
                new_value={
                    "status": ShipmentStatus.IN_TRANSIT.value,
                    "order_id": order.id,
                    "warehouse_id": payload.warehouse_id,
                    "expected_delivery_at": (
                        shipment.expected_delivery_at.isoformat()
                        if shipment.expected_delivery_at
                        else None
                    ),
                    "stock_out": consumed,
                },
            )
            return shipment_payload(shipment)

    def deliver(self, shipment_id: int, *, actor: User) -> dict:
        with transaction(self.db):
            shipment = self._get_or_raise(shipment_id)

            # Raises InvalidStateTransitionError (409) when disallowed.
            shipment_state_machine.transition(
                shipment.status, ShipmentStatus.DELIVERED
            )

            old_status = shipment.status
            now = utcnow()
            shipment.status = ShipmentStatus.DELIVERED
            shipment.actual_delivery_at = now
            self.db.flush()

            self.repo.add_history(shipment.id, ShipmentStatus.DELIVERED, actor.id, now)
            self.alerts.reconcile_shipment_overdue(
                shipment_id=shipment.id,
                status=shipment.status,
                expected_delivery_at=shipment.expected_delivery_at,
            )
            self.audit.record(
                user_id=actor.id,
                action="SHIPMENT_DELIVERED",
                entity_type="shipment",
                entity_id=shipment.id,
                old_value={"status": old_status.value, "order_id": shipment.order_id},
                new_value={
                    "status": ShipmentStatus.DELIVERED.value,
                    "order_id": shipment.order_id,
                    "actual_delivery_at": now.isoformat(),
                },
            )
            return shipment_payload(shipment)

    def _get_or_raise(self, shipment_id: int) -> Shipment:
        shipment = self.repo.get_by_id(shipment_id)
        if shipment is None:
            raise NotFoundError(f"Shipment {shipment_id} not found")
        return shipment