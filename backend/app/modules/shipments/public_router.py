"""Public (unauthenticated) package tracking endpoints.

This router intentionally declares NO authentication or permission
dependencies: ``GET /public/tracking/{tracking_number}`` is safe for anonymous
end users because the service returns only the public projection
(``public_tracking_payload``) — no ids, no order/user/warehouse references, no
supplier/inventory data, no audit or analytics internals.

No other internal API is exposed here; everything else stays behind RBAC on
the authenticated routers.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path

from app.common.responses import build_success_response
from app.core.database import get_db
from app.modules.shipments.service import ShipmentService

router = APIRouter(prefix="/public/tracking", tags=["public-tracking"])


@router.get(
    "/{tracking_number}",
    summary="Public package tracking lookup (no authentication required)",
)
def get_public_tracking(
    tracking_number: str = Path(min_length=1, max_length=32),
    db=Depends(get_db),
) -> dict:
    return build_success_response(
        ShipmentService(db).get_public_tracking(tracking_number),
        message="Shipment tracking retrieved",
    )
