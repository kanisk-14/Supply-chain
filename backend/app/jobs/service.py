"""Scheduled alert check: time-based SHIPMENT_OVERDUE reconciliation.

Time-based rules can flip between writes (a shipment becomes overdue simply
because the clock passes ``expected_delivery_at``). The reactive path in
``app/modules/shipments/service.py`` handles the on-write direction; this job
covers the elapsed-time direction.

It deliberately reconciles only the targeted set: the union of

- potentially overdue shipments (``expected_delivery_at < now`` and not
  DELIVERED), and
- shipments referenced by unresolved SHIPMENT_OVERDUE alerts (whose condition
  may now be false, e.g. a shipment delivered outside the reactive path).

so it never re-evaluates every alert in the database. ``run_overdue_check`` is
synchronous and safe to call from tests, the ``python -m app.jobs.scheduler``
daemon, or an optional in-process thread (``SCHEDULER_ENABLED``).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.transactions import transaction
from app.core.database import utcnow
from app.modules.alerts.models import Alert, AlertType
from app.modules.alerts.repositories import AlertRepository
from app.modules.alerts.service import AlertService
from app.modules.shipments.repositories import ShipmentRepository


def _unresolved_overdue_ids(db: Session) -> set[int]:
    return set(
        db.execute(
            select(Alert.id).where(
                Alert.type == AlertType.SHIPMENT_OVERDUE,
                Alert.is_resolved.is_(False),
            )
        ).scalars()
    )


def run_overdue_check(db: Session) -> dict:
    """Evaluate SHIPMENT_OVERDUE for the affected shipments and reconcile.

    Returns a small report: ``checked``, ``created``, ``resolved``, and the
    evaluation timestamp. The caller owns the session; this function commits
    its own unit of work on success and rolls it back on failure.
    """
    with transaction(db):
        now = utcnow()
        shipments = ShipmentRepository(db)
        alerts = AlertService(db)
        alert_repo = AlertRepository(db)

        before = _unresolved_overdue_ids(db)

        candidates = shipments.list_potentially_overdue(now)
        for shipment in candidates:
            alerts.reconcile_shipment_overdue(
                shipment_id=shipment.id,
                status=shipment.status,
                expected_delivery_at=shipment.expected_delivery_at,
                now=now,
            )

        stale = alert_repo.unresolved_of_type(AlertType.SHIPMENT_OVERDUE)
        for alert in stale:
            shipment = shipments.get_by_id(alert.entity_id)
            if shipment is None:
                continue
            alerts.reconcile_shipment_overdue(
                shipment_id=shipment.id,
                status=shipment.status,
                expected_delivery_at=shipment.expected_delivery_at,
                now=now,
            )

        after = _unresolved_overdue_ids(db)
        return {
            "checked": len(candidates) + len(stale),
            "created": len(after - before),
            "resolved": len(before - after),
            "checked_at": now.isoformat(),
        }