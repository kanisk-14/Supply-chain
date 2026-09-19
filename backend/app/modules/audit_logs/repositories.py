"""Audit log data access layer."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.audit_logs.models import AuditLog


class AuditLogRepository:
    """Append-only writes and reads over ``audit_logs``. Never commits."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def add(
        self,
        *,
        user_id: int,
        action: str,
        entity_type: str,
        entity_id: int,
        old_value: dict[str, Any] | None = None,
        new_value: dict[str, Any] | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_value=old_value,
            new_value=new_value,
        )
        self.db.add(entry)
        self.db.flush()
        return entry

    def list_for_entity(self, entity_type: str, entity_id: int) -> list[AuditLog]:
        return self.db.execute(
            select(AuditLog)
            .where(
                AuditLog.entity_type == entity_type,
                AuditLog.entity_id == entity_id,
            )
            .order_by(AuditLog.id)
        ).scalars().all()