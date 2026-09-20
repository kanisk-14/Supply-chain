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

from collections.abc import Callable, Sequence
from datetime import datetime
from decimal import Decimal

from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import Session

from app.common.exceptions import NotFoundError
from app.core.database import utcnow
from app.modules.alerts.models import Alert, AlertSeverity, AlertType
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
        product_above_threshold: bool | None = None,
    ) -> None:
        """Create or resolve the LOW_STOCK alert for a product after a change.

        ``product_above_threshold`` lets callers that already know the whole
        product is at/above the threshold skip the extra scan; when omitted it
        is derived from the inventory rows.
        """
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
            if product_above_threshold is None:
                min_quantity = self.repo.product_min_quantity(product_id)
                product_above_threshold = (
                    min_quantity is None or min_quantity >= threshold
                )
            if product_above_threshold:
                self._resolve_open(
                    AlertType.LOW_STOCK, "product", product_id
                )

    def reconcile_low_stock_threshold_change(
        self,
        *,
        product_id: int,
        threshold: Decimal,
        stocks: Sequence[tuple[Decimal, str]],
    ) -> None:
        """Reconcile LOW_STOCK after a ``reorder_threshold`` update.

        ``stocks`` is ``(quantity, warehouse_code)`` for every inventory row of
        the product. A row now below the new threshold re-opens (or refreshes)
        the product's alert — using the most severe (lowest) row for the
        severity/message; when every row is at/above the threshold open alerts
        resolve.
        """
        if not stocks:
            self._resolve_open(AlertType.LOW_STOCK, "product", product_id)
            return
        lowest = min(stocks, key=lambda stock: stock[0])
        if lowest[0] < threshold:
            self.reconcile_low_stock(
                product_id=product_id,
                quantity=lowest[0],
                threshold=threshold,
                warehouse_code=lowest[1],
            )
        else:
            self._resolve_open(AlertType.LOW_STOCK, "product", product_id)

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

        Implemented as ``INSERT ... ON DUPLICATE KEY UPDATE`` against the UNIQUE
        ``active_key`` column, so the check-and-insert is one atomic statement:
        concurrent requests racing to open the same alert cannot both insert, and
        an existing open alert is refreshed to the latest severity/message so a
        stale severity never survives (e.g. WARNING → CRITICAL → WARNING).
        """
        stmt = mysql_insert(Alert).values(
            type=alert_type,
            severity=severity,
            entity_type=entity_type,
            entity_id=entity_id,
            message=message,
            is_resolved=False,
            active_key=self.repo.unresolve_key(alert_type, entity_type, entity_id),
            created_at=utcnow(),
        )
        stmt = stmt.on_duplicate_key_update(
            severity=stmt.inserted.severity,
            message=stmt.inserted.message,
        )
        self.db.execute(stmt)

    def resolve(
        self, *, alert_type: AlertType, entity_type: str, entity_id: int
    ) -> None:
        """Resolve every open alert for an entity (e.g. the overdue sweep)."""
        self._resolve_open(alert_type, entity_type, entity_id)

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