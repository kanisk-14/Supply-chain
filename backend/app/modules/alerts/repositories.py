"""Alert data access layer (derived conditions only, never writable by clients)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.common.pagination import apply_pagination, count_total
from app.core.database import utcnow
from app.modules.alerts.models import Alert, AlertSeverity, AlertType


@dataclass
class AlertListResult:
    items: list[Alert]
    total: int


class AlertRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(
        self,
        *,
        page: int | None,
        limit: int | None,
        alert_type: AlertType | None = None,
        severity: AlertSeverity | None = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
        is_resolved: bool | None = None,
    ) -> AlertListResult:
        stmt: Select[tuple[Alert]] = select(Alert)
        if alert_type is not None:
            stmt = stmt.where(Alert.type == alert_type)
        if severity is not None:
            stmt = stmt.where(Alert.severity == severity)
        if entity_type is not None:
            stmt = stmt.where(Alert.entity_type == entity_type)
        if entity_id is not None:
            stmt = stmt.where(Alert.entity_id == entity_id)
        if is_resolved is not None:
            stmt = stmt.where(Alert.is_resolved.is_(is_resolved))
        total = count_total(self.db, stmt, Alert.id)
        items = self.db.execute(
            apply_pagination(
                stmt.order_by(Alert.created_at.desc(), Alert.id.desc()), page, limit
            )
        ).scalars().all()
        return AlertListResult(items=items, total=total)

    def get_by_id(self, alert_id: int) -> Alert | None:
        return self.db.execute(
            select(Alert).where(Alert.id == alert_id)
        ).scalar_one_or_none()

    def unresolved_for(self, alert_type: AlertType, entity_type: str, entity_id: int) -> list[Alert]:
        return self.db.execute(
            select(Alert).where(
                Alert.type == alert_type,
                Alert.entity_type == entity_type,
                Alert.entity_id == entity_id,
                Alert.is_resolved.is_(False),
            )
        ).scalars().all()

    def has_unresolved(
        self, alert_type: AlertType, entity_type: str, entity_id: int
    ) -> bool:
        stmt = (
            select(func.count())
            .select_from(Alert)
            .where(
                Alert.type == alert_type,
                Alert.entity_type == entity_type,
                Alert.entity_id == entity_id,
                Alert.is_resolved.is_(False),
            )
        )
        return int(self.db.execute(stmt).scalar_one()) > 0

    def unresolve_key(self, alert_type: AlertType, entity_type: str, entity_id: int) -> str:
        """Deterministic storage key for one open (type, entity) episode.

        Non-NULL only while the alert is unresolved; it backs the UNIQUE index
        that guarantees at most one open alert per episode at the InnoDB level.
        """
        return f"{alert_type.value}:{entity_type}:{entity_id}"

    def unresolved_of_type(self, alert_type: AlertType) -> list[Alert]:
        """Open alerts for one rule — the scheduled evaluator's sweep target."""
        return self.db.execute(
            select(Alert)
            .where(Alert.type == alert_type, Alert.is_resolved.is_(False))
            .order_by(Alert.id)
        ).scalars().all()

    def add(
        self,
        *,
        alert_type: AlertType,
        severity,
        entity_type: str,
        entity_id: int,
        message: str,
    ) -> Alert:
        alert = Alert(
            type=alert_type,
            severity=severity,
            entity_type=entity_type,
            entity_id=entity_id,
            message=message,
            active_key=self.unresolve_key(alert_type, entity_type, entity_id),
        )
        self.db.add(alert)
        self.db.flush()
        return alert

    def mark_resolved(self, alert: Alert) -> None:
        alert.is_resolved = True
        alert.resolved_at = utcnow()
        alert.active_key = None
        self.db.flush()

    def product_min_quantity(self, product_id: int) -> Decimal | None:
        """Lowest current inventory quantity for a product (None when no rows).

        Callers (e.g. LOW_STOCK reconciliation) combine this with the threshold
        to decide whether a product has moved back above it. Aggregated in SQL
        so the per-row fetch-and-min in Python is avoided.
        """
        from app.modules.inventory.models import Inventory

        return self.db.execute(
            select(func.min(Inventory.quantity)).where(
                Inventory.product_id == product_id
            )
        ).scalar_one()