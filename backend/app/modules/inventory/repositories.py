"""Inventory data access layer.

The lock helpers are the concurrency core: every stock mutation ``SELECTs ... FOR
UPDATE`` on the affected ``(product, warehouse)`` rows *inside* the service's
transaction so a blind read-modify-write can never race (see
docs/ARCHITECTURE.md). Nothing here commits.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.common.pagination import apply_pagination, count_total
from app.modules.inventory.models import (
    Inventory,
    InventoryTransaction,
    InventoryTransactionType as TxnType,
)
from app.modules.products.models import Product


@dataclass
class InventoryListResult:
    items: list[Inventory]
    total: int


@dataclass
class TransactionListResult:
    items: list[InventoryTransaction]
    total: int


class InventoryRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ---- current state ----

    def list(
        self,
        *,
        page: int | None,
        limit: int | None,
        product_id: int | None = None,
        warehouse_id: int | None = None,
        below_threshold: bool | None = None,
    ) -> InventoryListResult:
        stmt: Select[tuple[Inventory]] = select(Inventory)
        if product_id is not None:
            stmt = stmt.where(Inventory.product_id == product_id)
        if warehouse_id is not None:
            stmt = stmt.where(Inventory.warehouse_id == warehouse_id)
        if below_threshold is not None:
            # Derive low stock by comparing to the product's reorder threshold.
            stmt = stmt.join(Product, Inventory.product_id == Product.id)
            if below_threshold:
                stmt = stmt.where(Inventory.quantity < Product.reorder_threshold)
            else:
                stmt = stmt.where(Inventory.quantity >= Product.reorder_threshold)
        total = count_total(self.db, stmt, Inventory.id)
        items = self.db.execute(apply_pagination(stmt.order_by(Inventory.id), page, limit)).scalars().all()
        return InventoryListResult(items=items, total=total)

    def get_by_id(self, inventory_id: int) -> Inventory | None:
        return self.db.execute(
            select(Inventory).where(Inventory.id == inventory_id)
        ).scalar_one_or_none()

    def get_for_update(
        self, product_id: int, warehouse_id: int
    ) -> Inventory | None:
        """Fetch one row with SELECT ... FOR UPDATE (locks against writers)."""
        return self.db.execute(
            select(Inventory)
            .where(
                Inventory.product_id == product_id,
                Inventory.warehouse_id == warehouse_id,
            )
            .with_for_update()
        ).scalar_one_or_none()

    def get_many_for_update(
        self, product_id: int, warehouse_ids: list[int]
    ) -> list[Inventory]:
        """Lock several warehouse rows for one product.

        Rows come back ordered by warehouse id so two concurrent transfers touch
        the same lock order and cannot deadlock on each other.
        """
        return self.db.execute(
            select(Inventory)
            .where(
                Inventory.product_id == product_id,
                Inventory.warehouse_id.in_(warehouse_ids),
            )
            .order_by(Inventory.warehouse_id)
            .with_for_update()
        ).scalars().all()

    def add(self, inventory: Inventory) -> None:
        self.db.add(inventory)
        self.db.flush()

    # ---- append-only history ----

    def list_transactions(
        self,
        *,
        page: int | None,
        limit: int | None,
        product_id: int | None = None,
        warehouse_id: int | None = None,
        txn_type: TxnType | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> TransactionListResult:
        stmt: Select[tuple[InventoryTransaction]] = select(InventoryTransaction)
        if product_id is not None:
            stmt = stmt.where(InventoryTransaction.product_id == product_id)
        if warehouse_id is not None:
            stmt = stmt.where(
                InventoryTransaction.warehouse_id == warehouse_id
            )
        if txn_type is not None:
            stmt = stmt.where(InventoryTransaction.type == txn_type)
        if start is not None:
            stmt = stmt.where(InventoryTransaction.created_at >= start)
        if end is not None:
            stmt = stmt.where(InventoryTransaction.created_at <= end)
        total = count_total(self.db, stmt, InventoryTransaction.id)
        items = self.db.execute(
            apply_pagination(
                stmt.order_by(InventoryTransaction.id.desc()), page, limit
            )
        ).scalars().all()
        return TransactionListResult(items=items, total=total)

    def add_transaction(self, transaction: InventoryTransaction) -> None:
        self.db.add(transaction)
        self.db.flush()