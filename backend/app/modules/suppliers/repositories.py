"""Supplier data access layer."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.common.pagination import apply_pagination, count_total
from app.modules.suppliers.models import Supplier


@dataclass
class SupplierListResult:
    items: list[Supplier]
    total: int


class SupplierRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(
        self,
        *,
        page: int | None,
        limit: int | None,
        name: str | None = None,
        code: str | None = None,
        is_active: bool | None = None,
    ) -> SupplierListResult:
        stmt: Select[tuple[Supplier]] = select(Supplier)
        if name:
            stmt = stmt.where(Supplier.name.like(f"%{name}%"))
        if code:
            stmt = stmt.where(Supplier.code.like(f"%{code}%"))
        if is_active is not None:
            stmt = stmt.where(Supplier.is_active == is_active)
        total = count_total(self.db, stmt, Supplier.id)
        items = self.db.execute(apply_pagination(stmt.order_by(Supplier.id), page, limit)).scalars().all()
        return SupplierListResult(items=items, total=total)

    def get_by_id(self, supplier_id: int) -> Supplier | None:
        return self.db.execute(
            select(Supplier).where(Supplier.id == supplier_id)
        ).scalar_one_or_none()

    def exists_by_code(self, code: str, *, exclude_id: int | None = None) -> bool:
        stmt = select(func.count()).select_from(Supplier).where(Supplier.code == code)
        if exclude_id is not None:
            stmt = stmt.where(Supplier.id != exclude_id)
        return int(self.db.execute(stmt).scalar_one()) > 0

    def add(self, supplier: Supplier) -> None:
        self.db.add(supplier)
        self.db.flush()