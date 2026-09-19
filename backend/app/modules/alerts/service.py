"""Low-stock alert derivation.

Alerts are derived conditions, never a source of truth. Inventory mutations call
``reconcile_low_stock`` inside their own transaction so the alert cache reflects
the just-written state: one unresolved ``LOW_STOCK`` alert per product while any
of its (product, warehouse) rows sit below the reorder threshold, resolved as
soon as the product is back above it.

This is the reactive (on-write) half of the documented alert model; the
scheduled evaluator in ``app/jobs/`` remains a later stage.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.alerts.models import AlertSeverity, AlertType
from app.modules.alerts.repositories import AlertRepository


class AlertService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = AlertRepository(db)

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
            if not self.repo.has_unresolved(AlertType.LOW_STOCK, "product", product_id):
                self.repo.add(
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
            for alert in self.repo.unresolved_for(
                AlertType.LOW_STOCK, "product", product_id
            ):
                if _product_back_above_threshold(self.db, product_id, threshold):
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