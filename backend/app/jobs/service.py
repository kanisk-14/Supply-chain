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


def _unresolved_overdue_alert_ids(db: Session) -> set[int]:
    """IDs of currently open SHIPMENT_OVERDUE *alert rows* (not shipments).

    ``run_overdue_check`` snapshots this set before and after reconciliation so
    the report can count freshly created and freshly resolved alerts.
    """
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

        before = _unresolved_overdue_alert_ids(db)

        # Time-overdue candidates are fetched as lightweight (id, status,
        # expected) rows — no ORM instance graph to hydrate.
        candidates = shipments.list_potentially_overdue(now)

        # Sweep open alerts whose condition may already be false (e.g. a
        # delivery written outside the reactive path). Their referenced
        # shipment ids are noted now so the overlap with the candidate set can
        # be removed before any reconciliation happens.
        stale = alert_repo.unresolved_of_type(AlertType.SHIPMENT_OVERDUE)

        # One shipment can be BOTH a time-overdue candidate AND referenced by an
        # open SHIPMENT_OVERDUE alert (the alert was created by a previous run,
        # so it is in the open-alert sweep) — reconcile it exactly once, never
        # once from each set, so the ``checked`` count and the per-row database
        # work represent unique entities processed.
        ids = {shipment_id for shipment_id, _status, _expected in candidates}
        ids.update(alert.entity_id for alert in stale)

        checked = 0
        if ids:
            # Reconcile every unique shipment from one batched status fetch —
            # the same lookup the old candidate path per-row would otherwise
            # repeat — so a shipment shared by both sets is not fetched twice.
            rows = shipments.get_status_rows(sorted(ids))
            for shipment_id in sorted(ids):
                checked += 1
                info = rows.get(shipment_id)
                if info is None:
                    # The referenced shipment no longer exists: its open alert
                    # is stale and must not linger unresolved forever.
                    alerts.resolve(
                        alert_type=AlertType.SHIPMENT_OVERDUE,
                        entity_type="shipment",
                        entity_id=shipment_id,
                    )
                    continue
                alerts.reconcile_shipment_overdue(
                    shipment_id=shipment_id,
                    status=info[0],
                    expected_delivery_at=info[1],
                    now=now,
                )

        after = _unresolved_overdue_alert_ids(db)
        return {
            "checked": checked,
            "created": len(after - before),
            "resolved": len(before - after),
            "checked_at": now.isoformat(),
        }