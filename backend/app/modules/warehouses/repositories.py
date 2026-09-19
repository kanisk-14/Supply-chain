"""Warehouse data access layer."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.common.pagination import apply_pagination, count_total
from app.modules.warehouses.models import Warehouse


@dataclass
class WarehouseListResult:
    items: list[Warehouse]
    total: int


class WarehouseRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(
        self,
        *,
        page: int | None,
        limit: int | None,
        is_active: bool | None = None,
    ) -> WarehouseListResult:
        stmt: Select[tuple[Warehouse]] = select(Warehouse)
        if is_active is not None:
            stmt = stmt.where(Warehouse.is_active == is_active)
        total = count_total(self.db, stmt, Warehouse.id)
        items = self.db.execute(apply_pagination(stmt.order_by(Warehouse.id), page, limit)).scalars().all()
        return WarehouseListResult(items=items, total=total)

    def get_by_id(self, warehouse_id: int) -> Warehouse | None:
        return self.db.execute(
            select(Warehouse).where(Warehouse.id == warehouse_id)
        ).scalar_one_or_none()

    def exists_by_code(self, code: str, *, exclude_id: int | None = None) -> bool:
        stmt = select(func.count()).select_from(Warehouse).where(Warehouse.code == code)
        if exclude_id is not None:
            stmt = stmt.where(Warehouse.id != exclude_id)
        return int(self.db.execute(stmt).scalar_one()) > 0

    def add(self, warehouse: Warehouse) -> None:
        self.db.add(warehouse)
        self.db.flush()