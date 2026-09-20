"""Alert derivation: create/resolve lifecycle for derived operational conditions.

Alerts are a cache of *derived* conditions, never a source of truth (inventory
and shipment state live in their own tables). The lifecycle is:

- condition becomes true  → ensure exactly one unresolved alert exists
  (no duplicate when one is already open);
- condition becomes false → resolve all open alerts for that condition
  (``resolved_at`` is set);
- condition becomes true again later → a fresh alert row is created; the
  resolved row is kept as history.

Evaluation is reactive: the write path calls the affected reducer (e.g.
``reconcile_low_stock`` after an inventory mutation, ``reconcile_shipment_overdue``
after a shipment change) so only the touched entity is re-checked — never every
alert in the database. Time-based conditions that can flip without a write
(overdue shipments) are covered by the scheduled evaluator in ``app/jobs/``.

Clients cannot set the underlying operational condition through alerts; the API
is read-only (``app/modules/alerts/router.py``).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.exceptions import NotFoundError
from app.core.database import utcnow
from app.modules.alerts.models import AlertSeverity, AlertType
from app.modules.alerts.repositories import AlertRepository
from app.modules.alerts.schemas import alert_payload
from app.state_machines.shipment import ShipmentStatus


class AlertService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = AlertRepository(db)

    # ---- reads (API) ----

    def list(self, *, page, limit, alert_type=None, severity=None, entity_type=None, entity_id=None, is_resolved=None) -> dict:
        result = self.repo.list(
            page=page,
            limit=limit,
            alert_type=alert_type,
            severity=severity,
            entity_type=entity_type,
            entity_id=entity_id,
            is_resolved=is_resolved,
        )
        return {
            "items": [alert_payload(a) for a in result.items],
            "total": result.total,
        }

    def get(self, alert_id: int) -> dict:
        alert = self.repo.get_by_id(alert_id)
        if alert is None:
            raise NotFoundError(f"Alert {alert_id} not found")
        return alert_payload(alert)

    # ---- reactive reducers ----

    def reconcile_low_stock(
        self,
        *,
        product_id: int,
        quantity: Decimal,
        threshold: Decimal,
        warehouse_code: str,
    ) -> None:
        """Create or resolve the LOW_STOCK alert for a product after a change."""
        below = quantity < threshold
        if below:
            self._ensure_alert(
                alert_type=AlertType.LOW_STOCK,
                severity=(
                    AlertSeverity.CRITICAL
                    if quantity == 0
                    else AlertSeverity.WARNING
                ),
                entity_type="product",
                entity_id=product_id,
                message=(
                    f"Stock below reorder threshold at warehouse "
                    f"{warehouse_code} (quantity={quantity})"
                ),
            )
        else:
            if _product_back_above_threshold(self.db, product_id, threshold):
                self._resolve_open(
                    AlertType.LOW_STOCK, "product", product_id
                )

    def reconcile_shipment_overdue(
        self,
        *,
        shipment_id: int,
        status: ShipmentStatus,
        expected_delivery_at: datetime | None,
        now: datetime | None = None,
    ) -> None:
        """Create or resolve the SHIPMENT_OVERDUE alert for one shipment.

        Overdue iff ``expected_delivery_at < now AND status != DELIVERED`` —
        the same derived rule the shipments module exposes. Calling this after
        every shipment mutation keeps the alert in step with the shipment row
        it mirrors.
        """
        if now is None:
            now = utcnow()
        overdue = (
            expected_delivery_at is not None
            and status != ShipmentStatus.DELIVERED
            and expected_delivery_at < now
        )
        if overdue:
            self._ensure_alert(
                alert_type=AlertType.SHIPMENT_OVERDUE,
                severity=AlertSeverity.WARNING,
                entity_type="shipment",
                entity_id=shipment_id,
                message=(
                    f"Shipment is overdue (expected delivery at "
                    f"{expected_delivery_at.isoformat()})"
                ),
            )
        else:
            self._resolve_open(AlertType.SHIPMENT_OVERDUE, "shipment", shipment_id)

    # ---- lifecycle helpers ----

    def _ensure_alert(
        self,
        *,
        alert_type: AlertType,
        severity: AlertSeverity,
        entity_type: str,
        entity_id: int,
        message: str,
    ) -> None:
        """Create an alert unless an equivalent unresolved one already exists.

        ``equivalent`` = same type + same entity; an identically-scoped open
        alert is never duplicated. When all existing alerts for the condition
        are resolved (previous episode over), this creates a fresh row, which
        is the documented reactivation behaviour.
        """
        if not self.repo.has_unresolved(alert_type, entity_type, entity_id):
            self.repo.add(
                alert_type=alert_type,
                severity=severity,
                entity_type=entity_type,
                entity_id=entity_id,
                message=message,
            )

    def _resolve_open(
        self,
        alert_type: AlertType,
        entity_type: str,
        entity_id: int,
        predicate: Callable[[object], bool] | None = None,
    ) -> None:
        """Resolve every open alert for an entity, optionally via a predicate.

        ``predicate`` lets callers (e.g. low stock) only resolve when the whole
        entity is truly back to normal.
        """
        for alert in self.repo.unresolved_for(alert_type, entity_type, entity_id):
            if predicate is None or predicate(alert):
                self.repo.mark_resolved(alert)


def _product_back_above_threshold(
    db: Session, product_id: int, threshold: Decimal
) -> bool:
    from app.modules.inventory.models import Inventory

    rows = db.execute(
        select(Inventory.quantity).where(Inventory.product_id == product_id)
    ).scalars().all()
    if not rows:
        return True
    return min(rows) >= threshold