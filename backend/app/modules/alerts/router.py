"""Alert endpoints (read-only).

Alerts are derived conditions produced by the alert service and the scheduled
evaluator. There are no create/update/delete endpoints: clients cannot set the
underlying inventory or shipment state through alerts, and the resolve lifecycle
is automatic.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.common.pagination import resolve_pagination
from app.common.responses import build_paged_response, build_success_response
from app.core.database import get_db
from app.modules.alerts.models import AlertSeverity, AlertType
from app.modules.alerts.service import AlertService
from app.modules.auth.dependencies import require_permissions
from app.modules.auth.permissions import Permission
from app.modules.users.models import User

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", summary="List derived alerts (paged)")
def list_alerts(
    page: int | None = Query(default=None, ge=0),
    limit: int | None = Query(default=None, ge=0),
    type: AlertType | None = Query(default=None),
    severity: AlertSeverity | None = Query(default=None),
    entity_type: str | None = Query(default=None, min_length=1, max_length=32),
    entity_id: int | None = Query(default=None),
    resolved: bool | None = Query(default=None),
    _user: User = Depends(require_permissions(Permission.ALERTS_READ)),
    db=Depends(get_db),
) -> dict:
    service = AlertService(db)
    result = service.list(
        page=page,
        limit=limit,
        alert_type=type,
        severity=severity,
        entity_type=entity_type,
        entity_id=entity_id,
        is_resolved=resolved,
    )
    resolved_page, resolved_limit = resolve_pagination(page, limit)
    return build_paged_response(
        result["items"],
        page=resolved_page,
        limit=resolved_limit,
        total=result["total"],
        message="Alerts retrieved",
    )


@router.get("/{alert_id}", summary="Get a single alert")
def get_alert(
    alert_id: int,
    _user: User = Depends(require_permissions(Permission.ALERTS_READ)),
    db=Depends(get_db),
) -> dict:
    return build_success_response(
        AlertService(db).get(alert_id), message="Alert retrieved"
    )