"""FastAPI application factory.

Stage 2 scope: JWT authentication + RBAC and the master-data/inventory resource
endpoints (users, suppliers, products, warehouses, inventory) layered on the
Stage 1 foundation (envelope, errors, pagination, repository/service split).
Orders, shipments, analytics, ML, and scheduled jobs remain later stages.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.common.handlers import register_exception_handlers
from app.common.responses import build_success_response
from app.core.config import settings
from app.core.database import check_database_connectivity

API_PREFIX = "/api/v1"

APP_TITLE = "Supply Chain Tracking & Analytics"
APP_DESCRIPTION = (
    "Backend foundation for a supply-chain tracking and analytics system. "
    "Stage 1 provides the API conventions, consistent response envelope, "
    "centralized error handling, and the health endpoint; Stage 2 adds JWT "
    "authentication, role-based access control, users/suppliers/products/"
    "warehouses master data, and warehouse inventory with transactional stock "
    "mutations. Endpoints are documented in docs/API_CONTRACT.md."
)


def create_app() -> FastAPI:
    app = FastAPI(
        title=APP_TITLE,
        description=APP_DESCRIPTION,
        version="0.2.0",
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

    from app.modules.auth.router import router as auth_router
    from app.modules.inventory.router import router as inventory_router
    from app.modules.products.router import router as products_router
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
    ):
        app.include_router(router, prefix=API_PREFIX)

    return app


app = create_app()