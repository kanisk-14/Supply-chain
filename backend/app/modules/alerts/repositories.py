"""Alert data access layer (derived conditions only, never writable by clients)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.modules.alerts.models import Alert, AlertType


class AlertRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

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
        )
        self.db.add(alert)
        self.db.flush()
        return alert

    def mark_resolved(self, alert: Alert) -> None:
        alert.is_resolved = True
        alert.resolved_at = utcnow()
        self.db.flush()