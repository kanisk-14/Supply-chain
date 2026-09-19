from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, JSON, String, func
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, utcnow


class AuditLog(Base):
    """System-change accountability: who changed what, when.

    Distinct from ``shipment_status_history``, which answers "what happened to
    this shipment?". ``audit_logs`` answers "who changed what in the system?"
    across every entity. Old/new values are stored as JSON so any field shape
    can be captured without schema churn.

    ``entity_type``/``entity_id`` form a polymorphic reference to the target
    entity (e.g. ``order``/123, ``shipment``/55) — no cross-table FK because the
    target depends on ``entity_type``.
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    old_value: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6),
        nullable=False,
        default=utcnow,
        server_default=func.current_timestamp(6),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AuditLog id={self.id} user={self.user_id} action={self.action!r}>"