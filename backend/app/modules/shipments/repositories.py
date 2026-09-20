"""Shipment data access layer.

Shipments and their append-only status history are read/written only here.
Repositories receive a ``Session`` and never commit; the shipment service owns
the transaction boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, and_, not_, select
from sqlalchemy.orm import Session

from app.common.pagination import apply_pagination, count_total
from app.core.database import utcnow
from app.modules.shipments.models import Shipment, ShipmentStatusHistory
from app.state_machines.shipment import ShipmentStatus


@dataclass
class ShipmentListResult:
    items: list[Shipment]
    total: int


class ShipmentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(
        self,
        *,
        page: int | None,
        limit: int | None,
        order_id: int | None = None,
        status: ShipmentStatus | None = None,
        is_delayed: bool | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> ShipmentListResult:
        stmt: Select[tuple[Shipment]] = select(Shipment)
        if order_id is not None:
            stmt = stmt.where(Shipment.order_id == order_id)
        if status is not None:
            stmt = stmt.where(Shipment.status == status)
        if start is not None:
            stmt = stmt.where(Shipment.created_at >= start)
        if end is not None:
            stmt = stmt.where(Shipment.created_at <= end)
        if is_delayed is not None:
            now = utcnow()
            # DELAYED is never persisted — it is derived at query time:
            #   expected_delivery_at < now AND status != DELIVERED
            delayed = and_(
                Shipment.expected_delivery_at.isnot(None),
                Shipment.expected_delivery_at < now,
                Shipment.status != ShipmentStatus.DELIVERED,
            )
            stmt = stmt.where(delayed if is_delayed else not_(delayed))
        total = count_total(self.db, stmt, Shipment.id)
        items = self.db.execute(
            apply_pagination(stmt.order_by(Shipment.id.desc()), page, limit)
        ).scalars().all()
        return ShipmentListResult(items=items, total=total)

    def get_by_id(self, shipment_id: int) -> Shipment | None:
        return self.db.execute(
            select(Shipment).where(Shipment.id == shipment_id)
        ).scalar_one_or_none()

    def list_potentially_overdue(self, now: datetime) -> list[Shipment]:
        """Shipments that may now be overdue (``expected < now``, not delivered).

        This is the targeted candidate set for the scheduled SHIPMENT_OVERDUE
        evaluator — it never scans every shipment, only the ones the time-based
        rule could have just flipped for.
        """
        return self.db.execute(
            select(Shipment).where(
                Shipment.expected_delivery_at.isnot(None),
                Shipment.expected_delivery_at < now,
                Shipment.status != ShipmentStatus.DELIVERED,
            )
        ).scalars().all()

    def add(self, shipment: Shipment) -> None:
        self.db.add(shipment)
        self.db.flush()

    def add_history(
        self,
        shipment_id: int,
        status: ShipmentStatus,
        changed_by: int,
        changed_at: datetime,
    ) -> None:
        """Append one history row. Existing rows are never updated."""
        self.db.add(
            ShipmentStatusHistory(
                shipment_id=shipment_id,
                status=status,
                changed_by=changed_by,
                changed_at=changed_at,
            )
        )
        self.db.flush()

    def list_history(self, shipment_id: int) -> list[ShipmentStatusHistory]:
        return self.db.execute(
            select(ShipmentStatusHistory)
            .where(ShipmentStatusHistory.shipment_id == shipment_id)
            .order_by(ShipmentStatusHistory.changed_at, ShipmentStatusHistory.id)
        ).scalars().all()