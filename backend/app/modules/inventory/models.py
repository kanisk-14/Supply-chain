from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin, sa_enum, utcnow


class InventoryTransactionType(str, Enum):
    RECEIPT = "RECEIPT"
    ORDER_ALLOCATION = "ORDER_ALLOCATION"
    SHIPMENT_DISPATCH = "SHIPMENT_DISPATCH"
    ADJUSTMENT = "ADJUSTMENT"
    TRANSFER_IN = "TRANSFER_IN"
    TRANSFER_OUT = "TRANSFER_OUT"


class Inventory(TimestampMixin, Base):
    """Current stock of a product at a warehouse.

    This is state, not history. Nothing here records where quantities came from.
    """

    __tablename__ = "inventory"
    __table_args__ = (
        UniqueConstraint("product_id", "warehouse_id", name="uq_inventory_product_warehouse"),
        CheckConstraint("quantity >= 0", name="qty_nonnegative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False, default=Decimal("0"), server_default="0.0000"
    )

    product = relationship("Product", lazy="joined")
    warehouse = relationship("Warehouse", lazy="joined")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Inventory product={self.product_id} warehouse={self.warehouse_id} qty={self.quantity}>"


class InventoryTransaction(Base):
    """Append-only record of stock movements.

    Positive quantity = stock-in (RECEIPT, TRANSFER_IN, positive ADJUSTMENT).
    Negative quantity = stock-out (ORDER_ALLOCATION, SHIPMENT_DISPATCH,
    TRANSFER_OUT, negative ADJUSTMENT).

    This table is NOT the current inventory state; ``inventory`` is.
    """

    __tablename__ = "inventory_transactions"
    __table_args__ = (
        CheckConstraint("quantity <> 0", name="txn_qty_nonzero"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    type: Mapped[InventoryTransactionType] = mapped_column(
        sa_enum(InventoryTransactionType), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(32))
    reference_id: Mapped[int | None] = mapped_column(BigInteger)
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6),
        nullable=False,
        default=utcnow,
        server_default=func.current_timestamp(6),
    )