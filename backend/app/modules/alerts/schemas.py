"""Alert API schemas.

Alerts are derived conditions: clients may read them, never write them. There is
no create/update payload — an alert's only lifecycle is the auto
create → resolve → (re)create path driven by the alert service and scheduler.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.modules.alerts.models import AlertSeverity, AlertType


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: AlertType
    severity: AlertSeverity
    entity_type: str
    entity_id: int
    message: str
    is_resolved: bool
    created_at: datetime
    resolved_at: datetime | None


def alert_payload(alert: Any) -> dict:
    return AlertRead.model_validate(alert).model_dump(mode="json")