"""FastAPI application factory.

Stage 4 scope: live-computed analytics (overview, inventory, shipments,
suppliers, bottlenecks) and a derived-conditions alert engine (LOW_STOCK,
SHIPMENT_OVERDUE) with a read-only alerts API and an optional in-process
scheduler, on top of Stages 1-3 (envelope/errors/pagination, auth/RBAC/master
data, order + shipment lifecycle). ML, a GUI, and external integrations remain
later stages.
"""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.common.handlers import register_exception_handlers
from app.common.responses import build_success_response
from app.core.config import settings
from app.core.database import check_database_connectivity

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"

APP_TITLE = "Supply Chain Tracking & Analytics"
APP_DESCRIPTION = (
    "Backend foundation for a supply-chain tracking and analytics system. "
    "Stage 1 provides the API conventions, consistent response envelope, "
    "centralized error handling, and the health endpoint; Stage 2 adds JWT "
    "authentication, role-based access control, users/suppliers/products/"
    "warehouses master data, and warehouse inventory with transactional stock "
    "mutations; Stage 3 adds the order lifecycle (PLACED → CONFIRMED → "
    "FULFILLED/CANCELLED) and the shipment lifecycle (PACKED → IN_TRANSIT → "
    "DELIVERED) with append-only shipment history, derived delay tracking, and "
    "inventory integration on dispatch; Stage 4 adds live-computed analytics "
    "and a derived-condition alert engine (LOW_STOCK, SHIPMENT_OVERDUE) with a "
    "read-only alerts API and an optional in-process scheduler. Endpoints are "
    "documented in docs/API_CONTRACT.md."
)


def _scheduler_thread(stop_event: threading.Event) -> threading.Thread:
    """Background thread running the scheduled SHIPMENT_OVERDUE evaluator."""
    from app.jobs.scheduler import run_loop

    thread = threading.Thread(
        target=run_loop,
        kwargs={
            "interval_seconds": settings.SCHEDULER_INTERVAL_SECONDS,
            "stop_event": stop_event,
        },
        daemon=True,
        name="overdue-alert-scheduler",
    )
    thread.start()
    return thread


def create_app() -> FastAPI:
    lifespan_stop_event: threading.Event | None = None
    lifespan_thread: threading.Thread | None = None

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        nonlocal lifespan_stop_event, lifespan_thread
        if settings.SCHEDULER_ENABLED:
            lifespan_stop_event = threading.Event()
            lifespan_thread = _scheduler_thread(lifespan_stop_event)
        try:
            yield
        finally:
            if lifespan_thread is not None and lifespan_stop_event is not None:
                lifespan_stop_event.set()
                lifespan_thread.join(timeout=10)
                if lifespan_thread.is_alive():
                    # The scheduler ignored 10s of stop-signal + join time, so
                    # a clean synchronous shutdown did not happen. Report it
                    # instead of silently assuming termination: the daemon
                    # thread is eventually reaped with the interpreter, but a
                    # caller that watches logs should see this — it is the only
                    # signal that an evaluation may have been interrupted mid
                    # unit-of-work after the stop event fired.
                    lifespan_conf = settings.SCHEDULER_ENABLED
                    logger.warning(
                        "Scheduler thread marked alive after 10s stop+join "
                        "shutdown (SCHEDULER_ENABLED=%s); the final tick may "
                        "have been cut off — check unresolved SHIPMENT_OVERDUE "
                        "alerts on next start.",
                        lifespan_conf,
                    )

    app = FastAPI(
        title=APP_TITLE,
        description=APP_DESCRIPTION,
        version="0.4.0",
        lifespan=lifespan,
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    allowed_origins = settings.cors_origins_list
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    @app.get("/health", tags=["system"], summary="Health check")
    def health() -> dict:
        """Lightweight liveness check plus a database connectivity probe.

        The probe never leaks driver/database internals to clients: a failing
        database is reported as ``database: "error"`` without the exception
        text, keeping the endpoint cheap and safe.
        """
        database = "ok"
        try:
            check_database_connectivity()
        except Exception:  # noqa: BLE001 - converted to a status field, not raised
            database = "error"
        return build_success_response(
            {
                "status": "ok",
                "database": database,
                "environment": settings.ENVIRONMENT,
            },
            message="Health check",
        )

    from app.modules.alerts.router import router as alerts_router
    from app.modules.analytics.router import router as analytics_router
    from app.modules.auth.router import router as auth_router
    from app.modules.inventory.router import router as inventory_router
    from app.modules.orders.router import router as orders_router
    from app.modules.products.router import router as products_router
    from app.modules.shipments.router import router as shipments_router
    from app.modules.suppliers.router import router as suppliers_router
    from app.modules.users.router import router as users_router
    from app.modules.warehouses.router import router as warehouses_router

    for router in (
        auth_router,
        users_router,
        suppliers_router,
        products_router,
        warehouses_router,
        inventory_router,
        orders_router,
        shipments_router,
        alerts_router,
        analytics_router,
    ):
        app.include_router(router, prefix=API_PREFIX)

    return app


app = create_app()