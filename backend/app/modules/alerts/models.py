from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger, Boolean, String, func
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, sa_enum, utcnow


class AlertType(str, Enum):
    LOW_STOCK = "LOW_STOCK"
    SHIPMENT_OVERDUE = "SHIPMENT_OVERDUE"


class AlertSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class Alert(Base):
    """Derived operational condition, never a source of truth.

    ``entity_type``/``entity_id`` form a polymorphic reference to the entity the
    alert is about (e.g. ``product`` for LOW_STOCK, ``shipment`` for
    SHIPMENT_OVERDUE). No cross-table FK is enforced because the target depends
    on ``entity_type``; integrity is maintained by the alert service.
    """

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type: Mapped[AlertType] = mapped_column(sa_enum(AlertType), nullable=False)
    severity: Mapped[AlertSeverity] = mapped_column(sa_enum(AlertSeverity), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message: Mapped[str] = mapped_column(String(255), nullable=False)
    is_resolved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6),
        nullable=False,
        default=utcnow,
        server_default=func.current_timestamp(6),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Alert id={self.id} type={self.type.value} entity={self.entity_type}:{self.entity_id}>"