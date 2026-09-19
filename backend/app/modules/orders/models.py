from __future__ import annotations

from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin, sa_enum
from app.state_machines.order import OrderStatus


class Order(TimestampMixin, Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_number: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True, index=True
    )
    status: Mapped[OrderStatus] = mapped_column(
        sa_enum(OrderStatus),
        nullable=False,
        default=OrderStatus.PLACED,
        server_default=OrderStatus.PLACED.value,
    )
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    items = relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )
    shipments = relationship("Shipment", back_populates="order", lazy="selectin")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Order id={self.id} number={self.order_number!r} status={self.status.value}>"


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        UniqueConstraint("order_id", "product_id", name="uq_order_item_line"),
        CheckConstraint("quantity > 0", name="qty_positive"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)

    order = relationship("Order", back_populates="items")
    product = relationship("Product", lazy="joined")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<OrderItem id={self.id} order={self.order_id} product={self.product_id}>"