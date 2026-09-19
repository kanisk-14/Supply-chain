"""Product data access layer."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.common.pagination import apply_pagination, count_total
from app.modules.products.models import Product


@dataclass
class ProductListResult:
    items: list[Product]
    total: int


class ProductRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(
        self,
        *,
        page: int | None,
        limit: int | None,
        supplier_id: int | None = None,
        sku: str | None = None,
        is_active: bool | None = None,
    ) -> ProductListResult:
        stmt: Select[tuple[Product]] = select(Product)
        if supplier_id is not None:
            stmt = stmt.where(Product.supplier_id == supplier_id)
        if sku:
            stmt = stmt.where(Product.sku == sku)
        if is_active is not None:
            stmt = stmt.where(Product.is_active == is_active)
        total = count_total(self.db, stmt, Product.id)
        items = self.db.execute(apply_pagination(stmt.order_by(Product.id), page, limit)).scalars().all()
        return ProductListResult(items=items, total=total)

    def get_by_id(self, product_id: int) -> Product | None:
        return self.db.execute(
            select(Product).where(Product.id == product_id)
        ).scalar_one_or_none()

    def exists_by_sku(self, sku: str, *, exclude_id: int | None = None) -> bool:
        stmt = select(func.count()).select_from(Product).where(Product.sku == sku)
        if exclude_id is not None:
            stmt = stmt.where(Product.id != exclude_id)
        return int(self.db.execute(stmt).scalar_one()) > 0

    def add(self, product: Product) -> None:
        self.db.add(product)
        self.db.flush()