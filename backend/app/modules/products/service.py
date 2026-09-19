"""Product business rules.

- ``sku`` is unique (``CONFLICT`` on duplicates).
- ``supplier_id`` must reference an existing supplier (``NOT_FOUND``).
- ``reorder_threshold`` must be >= 0 (``VALIDATION_ERROR``).
- No inventory quantity is stored here — stock lives on ``inventory`` only.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.common.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.common.transactions import transaction
from app.modules.audit_logs.service import AuditLogService
from app.modules.products.models import Product
from app.modules.products.repositories import ProductRepository
from app.modules.products.schemas import (
    ProductCreate,
    ProductUpdate,
    product_payload,
)
from app.modules.suppliers.repositories import SupplierRepository
from app.modules.users.models import User


class ProductService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ProductRepository(db)
        self.suppliers = SupplierRepository(db)
        self.audit = AuditLogService(db)

    def list(
        self,
        *,
        page,
        limit,
        supplier_id=None,
        sku=None,
        is_active=None,
    ) -> dict:
        result = self.repo.list(
            page=page,
            limit=limit,
            supplier_id=supplier_id,
            sku=sku,
            is_active=is_active,
        )
        return {
            "items": [product_payload(p) for p in result.items],
            "total": result.total,
        }

    def get(self, product_id: int) -> dict:
        return product_payload(self._get_or_raise(product_id))

    def create(self, payload: ProductCreate, *, actor: User) -> dict:
        with transaction(self.db):
            data = payload.model_dump()
            self._validate_threshold(data["reorder_threshold"])
            self._require_supplier(data["supplier_id"])
            if self.repo.exists_by_sku(data["sku"].strip()):
                raise ConflictError(f"SKU {data['sku']!r} already exists")

            product = Product(
                supplier_id=data["supplier_id"],
                sku=data["sku"].strip(),
                name=data["name"],
                description=data.get("description"),
                unit=data["unit"],
                reorder_threshold=data["reorder_threshold"],
            )
            self.repo.add(product)
            self.audit.record(
                user_id=actor.id,
                action="PRODUCT.CREATE",
                entity_type="product",
                entity_id=product.id,
                new_value={
                    "id": product.id,
                    "sku": product.sku,
                    "name": product.name,
                    "supplier_id": product.supplier_id,
                },
            )
            return product_payload(product)

    def update(
        self, product_id: int, payload: ProductUpdate, *, actor: User
    ) -> dict:
        with transaction(self.db):
            product = self._get_or_raise(product_id)
            changes = payload.model_dump(exclude_unset=True)

            if "reorder_threshold" in changes:
                self._validate_threshold(changes["reorder_threshold"])
                product.reorder_threshold = changes["reorder_threshold"]

            if "supplier_id" in changes and changes["supplier_id"] != product.supplier_id:
                self._require_supplier(changes["supplier_id"])
                product.supplier_id = changes["supplier_id"]

            if "sku" in changes and changes["sku"].strip() != product.sku:
                new_sku = changes["sku"].strip()
                if self.repo.exists_by_sku(new_sku, exclude_id=product.id):
                    raise ConflictError(f"SKU {new_sku!r} already exists")
                product.sku = new_sku

            for field in ("name", "description", "unit"):
                if field in changes:
                    setattr(product, field, changes[field])
            if "is_active" in changes:
                product.is_active = changes["is_active"]

            self.db.flush()
            self.audit.record(
                user_id=actor.id,
                action="PRODUCT.UPDATE",
                entity_type="product",
                entity_id=product.id,
                old_value={"id": product.id, "sku": product.sku, "name": product.name},
                new_value={
                    "id": product.id,
                    "sku": product.sku,
                    "name": product.name,
                    "supplier_id": product.supplier_id,
                    "reorder_threshold": str(product.reorder_threshold),
                    "is_active": product.is_active,
                },
            )
            return product_payload(product)

    def _require_supplier(self, supplier_id: int) -> None:
        if self.suppliers.get_by_id(supplier_id) is None:
            raise NotFoundError(f"Supplier {supplier_id} not found")

    @staticmethod
    def _validate_threshold(threshold: Decimal) -> None:
        if threshold < 0:
            raise ValidationError(
                "reorder_threshold must be >= 0",
                details={"reorder_threshold": str(threshold)},
            )

    def _get_or_raise(self, product_id: int) -> Product:
        product = self.repo.get_by_id(product_id)
        if product is None:
            raise NotFoundError(f"Product {product_id} not found")
        return product