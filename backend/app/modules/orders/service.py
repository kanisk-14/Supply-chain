"""Order business rules and transactional workflows.

State-transition logic is delegated to ``OrderStateMachine``; every transition
is validated there, persisted by this service, and written to ``audit_logs``.
Order creation is a single transaction that validates the line items
(non-empty, unique products, existing products) before persisting the order and
its items together.
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session

from app.common.exceptions import NotFoundError, ValidationError
from app.common.transactions import transaction
from app.modules.audit_logs.service import AuditLogService
from app.modules.orders.models import Order, OrderItem
from app.modules.orders.repositories import OrderRepository
from app.modules.orders.schemas import OrderCreate, order_payload
from app.modules.products.repositories import ProductRepository
from app.modules.users.models import User
from app.state_machines.order import OrderStatus, order_state_machine

AUDIT_ACTIONS = {
    OrderStatus.PLACED: None,
    OrderStatus.CONFIRMED: "ORDER_CONFIRMED",
    OrderStatus.FULFILLED: "ORDER_FULFILLED",
    OrderStatus.CANCELLED: "ORDER_CANCELLED",
}


class OrderService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = OrderRepository(db)
        self.products = ProductRepository(db)
        self.audit = AuditLogService(db)

    # ---- reads ----

    def list(
        self,
        *,
        page,
        limit,
        status=None,
        created_by=None,
        start=None,
        end=None,
        include_shipments=False,
    ) -> dict:
        result = self.repo.list(
            page=page,
            limit=limit,
            status=status,
            created_by=created_by,
            start=start,
            end=end,
        )
        return {
            "items": [
                order_payload(o, include_shipments=include_shipments)
                for o in result.items
            ],
            "total": result.total,
        }

    def get(self, order_id: int, *, include_shipments: bool = False) -> dict:
        return order_payload(
            self._get_or_raise(order_id), include_shipments=include_shipments
        )

    # ---- create ----

    def create(self, payload: OrderCreate, *, actor: User) -> dict:
        with transaction(self.db):
            items = payload.items
            if not items:
                raise ValidationError(
                    "An order must contain at least one line item",
                    details={"items": "must not be empty"},
                )

            seen: set[int] = set()
            for item in items:
                if item.product_id in seen:
                    raise ValidationError(
                        "An order cannot repeat the same product twice",
                        details={"product_id": item.product_id},
                    )
                seen.add(item.product_id)
                if self.products.get_by_id(item.product_id) is None:
                    raise NotFoundError(f"Product {item.product_id} not found")

            order = Order(
                created_by=actor.id,
                # Pending placeholder so the insert satisfies the NOT NULL
                # unique column; replaced by the deterministic id-based number
                # right after flush, within the same transaction.
                order_number=f"ORD-PEND-{uuid4().hex[:16]}",
            )
            self.repo.add(order)
            # A deterministic unique order number derived from the primary key.
            order.order_number = f"ORD-{order.id:08d}"
            for item in items:
                order.items.append(
                    OrderItem(product_id=item.product_id, quantity=item.quantity)
                )
            self.db.flush()

            self.audit.record(
                user_id=actor.id,
                action="ORDER_CREATED",
                entity_type="order",
                entity_id=order.id,
                new_value={
                    "id": order.id,
                    "order_number": order.order_number,
                    "status": OrderStatus.PLACED.value,
                    "created_by": actor.id,
                    "items": [
                        {
                            "product_id": item.product_id,
                            "quantity": str(item.quantity),
                        }
                        for item in order.items
                    ],
                },
            )
            return order_payload(order)

    # ---- state transitions ----

    def confirm(self, order_id: int, *, actor: User) -> dict:
        return self._transition(
            order_id, OrderStatus.CONFIRMED, AUDIT_ACTIONS[OrderStatus.CONFIRMED], actor
        )

    def fulfill(self, order_id: int, *, actor: User) -> dict:
        return self._transition(
            order_id, OrderStatus.FULFILLED, AUDIT_ACTIONS[OrderStatus.FULFILLED], actor
        )

    def cancel(self, order_id: int, *, actor: User) -> dict:
        return self._transition(
            order_id, OrderStatus.CANCELLED, AUDIT_ACTIONS[OrderStatus.CANCELLED], actor
        )

    def _transition(
        self, order_id: int, target: OrderStatus, action: str, actor: User
    ) -> dict:
        """Validate against the state machine, persist, and audit atomically."""
        with transaction(self.db):
            order = self._get_or_raise(order_id)
            old_status = order.status
            # Raises InvalidStateTransitionError (409) when disallowed.
            order_state_machine.transition(old_status, target)
            order.status = target
            self.db.flush()
            self.audit.record(
                user_id=actor.id,
                action=action,
                entity_type="order",
                entity_id=order.id,
                old_value={"status": old_status.value},
                new_value={
                    "status": target.value,
                    "order_number": order.order_number,
                },
            )
            return order_payload(order)

    def _get_or_raise(self, order_id: int) -> Order:
        order = self.repo.get_by_id(order_id)
        if order is None:
            raise NotFoundError(f"Order {order_id} not found")
        return order