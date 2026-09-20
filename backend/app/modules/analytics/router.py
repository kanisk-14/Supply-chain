"""Analytics endpoints.

All analytics are computed live from operational data (SQL aggregation in the
repository); nothing is stored as a KPI value. Reads require ``ANALYTICS_READ``
(available to every authenticated role).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.common.responses import build_success_response
from app.core.database import get_db
from app.modules.analytics.service import AnalyticsService
from app.modules.auth.dependencies import require_permissions
from app.modules.auth.permissions import Permission
from app.modules.users.models import User

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview", summary="Global operational KPIs")
def analytics_overview(
    _user: User = Depends(require_permissions(Permission.ANALYTICS_READ)),
    db=Depends(get_db),
) -> dict:
    return build_success_response(
        AnalyticsService(db).overview(), message="Analytics overview"
    )


@router.get("/inventory", summary="Inventory KPIs, distribution, and trends")
def analytics_inventory(
    period: str | None = Query(default=None, pattern="^(day|week|month)$"),
    days: int | None = Query(default=None, ge=1, le=365),
    _user: User = Depends(require_permissions(Permission.ANALYTICS_READ)),
    db=Depends(get_db),
) -> dict:
    return build_success_response(
        AnalyticsService(db).inventory(period=period, days=days),
        message="Inventory analytics",
    )


@router.get("/shipments", summary="Shipment KPIs and delivery performance")
def analytics_shipments(
    period: str | None = Query(default=None, pattern="^(day|week|month)$"),
    days: int | None = Query(default=None, ge=1, le=365),
    _user: User = Depends(require_permissions(Permission.ANALYTICS_READ)),
    db=Depends(get_db),
) -> dict:
    return build_success_response(
        AnalyticsService(db).shipments(period=period, days=days),
        message="Shipment analytics",
    )


@router.get("/suppliers", summary="Supplier performance computed from orders/shipments")
def analytics_suppliers(
    _user: User = Depends(require_permissions(Permission.ANALYTICS_READ)),
    db=Depends(get_db),
) -> dict:
    return build_success_response(
        AnalyticsService(db).suppliers(), message="Supplier analytics"
    )


@router.get("/bottlenecks", summary="Time spent in each shipment lifecycle stage")
def analytics_bottlenecks(
    _user: User = Depends(require_permissions(Permission.ANALYTICS_READ)),
    db=Depends(get_db),
) -> dict:
    return build_success_response(
        AnalyticsService(db).bottlenecks(), message="Bottleneck analytics"
    )