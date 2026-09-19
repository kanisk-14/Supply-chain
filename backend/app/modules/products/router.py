"""Product endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.common.pagination import resolve_pagination
from app.common.responses import build_paged_response, build_success_response
from app.core.database import get_db
from app.modules.auth.dependencies import require_permissions
from app.modules.auth.permissions import Permission
from app.modules.products.schemas import ProductCreate, ProductUpdate
from app.modules.products.service import ProductService
from app.modules.users.models import User

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", summary="List products")
def list_products(
    page: int | None = Query(default=None, ge=0),
    limit: int | None = Query(default=None, ge=0),
    supplier_id: int | None = Query(default=None),
    sku: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    _user: User = Depends(require_permissions(Permission.PRODUCTS_READ)),
    db=Depends(get_db),
) -> dict:
    service = ProductService(db)
    result = service.list(
        page=page,
        limit=limit,
        supplier_id=supplier_id,
        sku=sku,
        is_active=is_active,
    )
    resolved_page, resolved_limit = resolve_pagination(page, limit)
    return build_paged_response(
        result["items"],
        page=resolved_page,
        limit=resolved_limit,
        total=result["total"],
        message="Products retrieved",
    )


@router.get("/{product_id}", summary="Get a single product")
def get_product(
    product_id: int,
    _user: User = Depends(require_permissions(Permission.PRODUCTS_READ)),
    db=Depends(get_db),
) -> dict:
    return build_success_response(
        ProductService(db).get(product_id), message="Product retrieved"
    )


@router.post("", status_code=201, summary="Create a product")
def create_product(
    payload: ProductCreate,
    actor: User = Depends(require_permissions(Permission.PRODUCTS_WRITE)),
    db=Depends(get_db),
) -> dict:
    return build_success_response(
        ProductService(db).create(payload, actor=actor),
        message="Product created",
    )


@router.patch("/{product_id}", summary="Update a product")
def update_product(
    product_id: int,
    payload: ProductUpdate,
    actor: User = Depends(require_permissions(Permission.PRODUCTS_WRITE)),
    db=Depends(get_db),
) -> dict:
    return build_success_response(
        ProductService(db).update(product_id, payload, actor=actor),
        message="Product updated",
    )