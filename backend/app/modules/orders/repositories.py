"""Order data access layer.

Orders and their line items are read/written only here. Repositories receive a
``Session`` and never commit; the order service owns the transaction boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.common.pagination import apply_pagination, count_total
from app.modules.orders.models import Order, OrderItem
from app.state_machines.order import OrderStatus


@dataclass
class OrderListResult:
    items: list[Order]
    total: int


class OrderRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(
        self,
        *,
        page: int | None,
        limit: int | None,
        status: OrderStatus | None = None,
        created_by: int | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> OrderListResult:
        stmt: Select[tuple[Order]] = select(Order)
        if status is not None:
            stmt = stmt.where(Order.status == status)
        if created_by is not None:
            stmt = stmt.where(Order.created_by == created_by)
        if start is not None:
            stmt = stmt.where(Order.created_at >= start)
        if end is not None:
            stmt = stmt.where(Order.created_at <= end)
        total = count_total(self.db, stmt, Order.id)
        items = self.db.execute(
            apply_pagination(stmt.order_by(Order.id.desc()), page, limit)
        ).scalars().all()
        return OrderListResult(items=items, total=total)

    def get_by_id(self, order_id: int) -> Order | None:
        return self.db.execute(
            select(Order).where(Order.id == order_id)
        ).scalar_one_or_none()

    def add(self, order: Order) -> None:
        self.db.add(order)
        self.db.flush()

    def items_for(self, order_id: int) -> list[OrderItem]:
        return self.db.execute(
            select(OrderItem).where(OrderItem.order_id == order_id)
        ).scalars().all()