"""Inventory business rules.

Stock mutations are the most concurrency-sensitive code in the system and follow
the documented transaction boundary precisely:

    session.begin()
      → lock affected rows (SELECT ... FOR UPDATE)
      → validate the rule (non-negative stock, positive transfer)
      → mutate quantities
      → append inventory_transactions rows
      → write audit_log entries
      → re-evaluate derived LOW_STOCK alerts
      → commit; any failure rolls back the whole unit of work

Adjusts and transfers therefore run in a single database transaction with row
locks held until commit — a failed transfer can never publish half of its effect.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.exceptions import (
    ConflictError,
    InsufficientInventoryError,
    NotFoundError,
    ValidationError,
)
from app.common.transactions import transaction
from app.modules.alerts.service import AlertService
from app.modules.audit_logs.service import AuditLogService
from app.modules.inventory.models import (
    Inventory,
    InventoryTransaction,
    InventoryTransactionType as TxnType,
)
from app.modules.inventory.repositories import InventoryRepository
from app.modules.inventory.schemas import (
    inventory_payload,
    transaction_payload,
)
from app.modules.products.repositories import ProductRepository
from app.modules.users.models import User
from app.modules.warehouses.models import Warehouse
from app.modules.warehouses.repositories import WarehouseRepository


class InventoryService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = InventoryRepository(db)
        self.products = ProductRepository(db)
        self.warehouses = WarehouseRepository(db)
        self.audit = AuditLogService(db)
        self.alerts = AlertService(db)

    # ---- reads ----

    def list(self, *, page, limit, product_id=None, warehouse_id=None, below_threshold=None) -> dict:
        result = self.repo.list(
            page=page,
            limit=limit,
            product_id=product_id,
            warehouse_id=warehouse_id,
            below_threshold=below_threshold,
        )
        items = [
            inventory_payload(row)
            for row in result.items
            if getattr(row, "product", None) is not None
            and getattr(row, "warehouse", None) is not None
        ]
        return {"items": items, "total": result.total}

    def get(self, inventory_id: int) -> dict:
        row = self.repo.get_by_id(inventory_id)
        if row is None:
            raise NotFoundError(f"Inventory record {inventory_id} not found")
        return inventory_payload(row)

    def list_transactions(
        self,
        *,
        page,
        limit,
        product_id=None,
        warehouse_id=None,
        txn_type=None,
        start=None,
        end=None,
    ) -> dict:
        result = self.repo.list_transactions(
            page=page,
            limit=limit,
            product_id=product_id,
            warehouse_id=warehouse_id,
            txn_type=txn_type,
            start=start,
            end=end,
        )
        return {
            "items": [transaction_payload(t) for t in result.items],
            "total": result.total,
        }

    # ---- mutations ----

    def adjust(
        self,
        *,
        product_id: int,
        warehouse_id: int,
        delta: Decimal,
        reason: str | None,
        actor: User,
    ) -> dict:
        with transaction(self.db):
            product = self.products.get_by_id(product_id)
            if product is None:
                raise NotFoundError(f"Product {product_id} not found")
            warehouse = self.warehouses.get_by_id(warehouse_id)
            if warehouse is None:
                raise NotFoundError(f"Warehouse {warehouse_id} not found")

            row = self.repo.get_for_update(product_id, warehouse_id)
            if row is None:
                # New (product, warehouse) pair starts at zero stock.
                if delta < 0:
                    raise InsufficientInventoryError(
                        "Cannot adjust below zero on empty stock",
                        details={
                            "available": "0",
                            "required": str(abs(delta)),
                        },
                    )
                row = Inventory(
                    product_id=product_id,
                    warehouse_id=warehouse_id,
                    quantity=Decimal("0"),
                )
                self.repo.add(row)

            old_quantity = row.quantity
            new_quantity = old_quantity + delta
            if new_quantity < 0:
                raise InsufficientInventoryError(
                    "Adjustment would leave stock negative",
                    details={
                        "available": str(old_quantity),
                        "required": str(abs(delta)),
                    },
                )
            row.quantity = new_quantity

            self.repo.add_transaction(
                InventoryTransaction(
                    product_id=product_id,
                    warehouse_id=warehouse_id,
                    type=TxnType.ADJUSTMENT,
                    quantity=delta,
                    reference_type="ADJUSTMENT",
                    created_by=actor.id,
                )
            )
            self.audit.record(
                user_id=actor.id,
                action="INVENTORY.ADJUST",
                entity_type="inventory",
                entity_id=row.id,
                old_value={
                    "product_id": product_id,
                    "warehouse_id": warehouse_id,
                    "quantity": str(old_quantity),
                    "reason": reason,
                },
                new_value={
                    "product_id": product_id,
                    "warehouse_id": warehouse_id,
                    "quantity": str(new_quantity),
                    "reason": reason,
                },
            )
            self.alerts.reconcile_low_stock(
                product_id=product_id,
                quantity=new_quantity,
                threshold=product.reorder_threshold,
                warehouse_code=warehouse.code,
            )
            self.db.flush()
            return inventory_payload(row)

    def transfer(
        self,
        *,
        product_id: int,
        from_warehouse_id: int,
        to_warehouse_id: int,
        quantity: Decimal,
        actor: User,
    ) -> list[dict]:
        if from_warehouse_id == to_warehouse_id:
            raise ValidationError(
                "Source and destination warehouses must differ",
                details={
                    "from_warehouse_id": from_warehouse_id,
                    "to_warehouse_id": to_warehouse_id,
                },
            )

        with transaction(self.db):
            product = self.products.get_by_id(product_id)
            if product is None:
                raise NotFoundError(f"Product {product_id} not found")
            from_wh = self.warehouses.get_by_id(from_warehouse_id)
            if from_wh is None:
                raise NotFoundError(f"Warehouse {from_warehouse_id} not found")
            to_wh = self.warehouses.get_by_id(to_warehouse_id)
            if to_wh is None:
                raise NotFoundError(f"Warehouse {to_warehouse_id} not found")

            # Lock both warehouse rows for this product, in one ordered statement,
            # so concurrent transfers acquire locks in the same order.
            rows = self.repo.get_many_for_update(
                product_id, [from_warehouse_id, to_warehouse_id]
            )
            source = next(
                (r for r in rows if r.warehouse_id == from_warehouse_id), None
            )
            destination = next(
                (r for r in rows if r.warehouse_id == to_warehouse_id), None
            )

            if source is None:
                raise InsufficientInventoryError(
                    "Source warehouse has no stock for this product",
                    details={"available": "0", "required": str(quantity)},
                )
            if source.quantity < quantity:
                raise InsufficientInventoryError(
                    "Insufficient stock to transfer",
                    details={
                        "available": str(source.quantity),
                        "required": str(quantity),
                    },
                )

            if destination is None:
                destination = Inventory(
                    product_id=product_id,
                    warehouse_id=to_warehouse_id,
                    quantity=Decimal("0"),
                )
                self.repo.add(destination)

            source.quantity -= quantity
            destination.quantity += quantity
            self.db.flush()

            self.repo.add_transaction(
                InventoryTransaction(
                    product_id=product_id,
                    warehouse_id=from_warehouse_id,
                    type=TxnType.TRANSFER_OUT,
                    quantity=-quantity,
                    reference_type="TRANSFER",
                    created_by=actor.id,
                )
            )
            self.repo.add_transaction(
                InventoryTransaction(
                    product_id=product_id,
                    warehouse_id=to_warehouse_id,
                    type=TxnType.TRANSFER_IN,
                    quantity=quantity,
                    reference_type="TRANSFER",
                    created_by=actor.id,
                )
            )
            self.audit.record(
                user_id=actor.id,
                action="INVENTORY.TRANSFER",
                entity_type="inventory",
                entity_id=source.id,
                old_value={
                    "product_id": product_id,
                    "warehouse_id": from_warehouse_id,
                    "quantity": str(source.quantity + quantity),
                },
                new_value={
                    "product_id": product_id,
                    "warehouse_id": from_warehouse_id,
                    "quantity": str(source.quantity),
                },
            )
            if destination.id is not None:
                self.audit.record(
                    user_id=actor.id,
                    action="INVENTORY.TRANSFER",
                    entity_type="inventory",
                    entity_id=destination.id,
                    old_value={
                        "product_id": product_id,
                        "warehouse_id": to_warehouse_id,
                        "quantity": str(destination.quantity - quantity),
                    },
                    new_value={
                        "product_id": product_id,
                        "warehouse_id": to_warehouse_id,
                        "quantity": str(destination.quantity),
                    },
                )

            self.alerts.reconcile_low_stock(
                product_id=product_id,
                quantity=source.quantity,
                threshold=product.reorder_threshold,
                warehouse_code=from_wh.code,
            )
            self.alerts.reconcile_low_stock(
                product_id=product_id,
                quantity=destination.quantity,
                threshold=product.reorder_threshold,
                warehouse_code=to_wh.code,
            )
            self.db.flush()
            return [inventory_payload(source), inventory_payload(destination)]

    def dispatch_stock(
        self,
        *,
        product_id: int,
        warehouse_id: int,
        quantity: Decimal,
        reference_id: int,
        actor: User,
    ) -> tuple[Decimal, Decimal]:
        """Decrement stock as goods physically leave for a shipment dispatch.

        Reused by the shipment service inside its own transaction (this method
        never commits): it locks the ``(product, warehouse)`` row FOR UPDATE,
        validates availability, decrements the quantity, appends a
        ``SHIPMENT_DISPATCH`` inventory transaction, and re-evaluates the
        derived LOW_STOCK alert. A shortage raises
        :class:`~app.common.exceptions.InsufficientInventoryError`, which rolls
        back the caller's whole unit of work.

        Returns ``(old_quantity, new_quantity)`` so the caller can audit them.
        """
        row = self.repo.get_for_update(product_id, warehouse_id)
        if row is None or row.quantity < quantity:
            raise InsufficientInventoryError(
                "Insufficient stock to dispatch for shipment",
                details={
                    "product_id": product_id,
                    "warehouse_id": warehouse_id,
                    "available": str(row.quantity) if row is not None else "0",
                    "required": str(quantity),
                },
            )

        product = self.products.get_by_id(product_id)
        warehouse = self.warehouses.get_by_id(warehouse_id)
        old_quantity = row.quantity
        new_quantity = old_quantity - quantity
        row.quantity = new_quantity

        self.repo.add_transaction(
            InventoryTransaction(
                product_id=product_id,
                warehouse_id=warehouse_id,
                type=TxnType.SHIPMENT_DISPATCH,
                quantity=-quantity,
                reference_type="SHIPMENT",
                reference_id=reference_id,
                created_by=actor.id,
            )
        )
        if product is not None and warehouse is not None:
            self.alerts.reconcile_low_stock(
                product_id=product_id,
                quantity=new_quantity,
                threshold=product.reorder_threshold,
                warehouse_code=warehouse.code,
            )
        return old_quantity, new_quantity