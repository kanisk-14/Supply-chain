"""Audit log service.

Domain services call ``AuditLogService.record`` inside their own transaction
instead of building ``AuditLog`` rows directly, so the appends are centralized
and never formatted ad hoc. This service never commits — the caller owns the
transaction boundary.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.modules.audit_logs.repositories import AuditLogRepository


def json_safe(value: Any) -> Any:
    """Make a value safe to embed in the JSON ``old_value``/``new_value``.

    Decimals and datetimes are not natively JSON-serializable; reduce them to
    primitive values here so every audit payload round-trips.
    """
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, float) or isinstance(value, int) or value is None:
        return value
    return str(value)


class AuditLogService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = AuditLogRepository(db)

    def record(
        self,
        *,
        user_id: int,
        action: str,
        entity_type: str,
        entity_id: int,
        old_value: dict[str, Any] | None = None,
        new_value: dict[str, Any] | None = None,
    ) -> None:
        """Append one audit entry (flushed, never committed by this service)."""
        self.repo.add(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_value=json_safe(old_value),
            new_value=json_safe(new_value),
        )

    def for_entity(self, entity_type: str, entity_id: int) -> list:
        """Read-only history for an entity (used by tests and tooling)."""
        return [a for a in self.repo.list_for_entity(entity_type, entity_id)]