from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, String, func
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin, sa_enum, utcnow
from app.state_machines.shipment import ShipmentStatus


class Shipment(TimestampMixin, Base):
    """A shipment of an order. An order may have many shipments (1:N).

    DELAYED is never persisted: a shipment is derived as delayed when
    ``expected_delivery_at < now AND status != DELIVERED``.
    """

    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    shipment_number: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True, index=True
    )
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[ShipmentStatus] = mapped_column(
        sa_enum(ShipmentStatus),
        nullable=False,
        default=ShipmentStatus.PACKED,
        server_default=ShipmentStatus.PACKED.value,
    )
    expected_delivery_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    actual_delivery_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    warehouse_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    order = relationship("Order", back_populates="shipments", lazy="selectin")
    history = relationship(
        "ShipmentStatusHistory",
        back_populates="shipment",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ShipmentStatusHistory.changed_at",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Shipment id={self.id} number={self.shipment_number!r} status={self.status.value}>"


class ShipmentStatusHistory(Base):
    """Append-only log of shipment transitions. Never updated in place."""

    __tablename__ = "shipment_status_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    shipment_id: Mapped[int] = mapped_column(
        ForeignKey("shipments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[ShipmentStatus] = mapped_column(sa_enum(ShipmentStatus), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6),
        nullable=False,
        default=utcnow,
        server_default=func.current_timestamp(6),
    )
    changed_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    shipment = relationship("Shipment", back_populates="history")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ShipmentStatusHistory id={self.id} shipment={self.shipment_id} status={self.status.value}>"