"""Warehouse business rules. Unique ``code`` conflicts become ``CONFLICT``."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.exceptions import ConflictError, NotFoundError
from app.common.transactions import transaction
from app.modules.audit_logs.service import AuditLogService
from app.modules.users.models import User
from app.modules.warehouses.models import Warehouse
from app.modules.warehouses.repositories import WarehouseRepository
from app.modules.warehouses.schemas import (
    WarehouseCreate,
    WarehouseUpdate,
    warehouse_payload,
)


class WarehouseService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = WarehouseRepository(db)
        self.audit = AuditLogService(db)

    def list(self, *, page, limit, is_active=None) -> dict:
        result = self.repo.list(page=page, limit=limit, is_active=is_active)
        return {
            "items": [warehouse_payload(w) for w in result.items],
            "total": result.total,
        }

    def get(self, warehouse_id: int) -> dict:
        return warehouse_payload(self._get_or_raise(warehouse_id))

    def create(self, payload: WarehouseCreate, *, actor: User) -> dict:
        with transaction(self.db):
            data = payload.model_dump()
            if self.repo.exists_by_code(data["code"].strip()):
                raise ConflictError(f"Warehouse code {data['code']!r} already exists")
            warehouse = Warehouse(
                code=data["code"].strip(),
                name=data["name"],
                address=data.get("address"),
            )
            self.repo.add(warehouse)
            self.audit.record(
                user_id=actor.id,
                action="WAREHOUSE.CREATE",
                entity_type="warehouse",
                entity_id=warehouse.id,
                new_value={
                    "id": warehouse.id,
                    "code": warehouse.code,
                    "name": warehouse.name,
                },
            )
            return warehouse_payload(warehouse)

    def update(
        self, warehouse_id: int, payload: WarehouseUpdate, *, actor: User
    ) -> dict:
        with transaction(self.db):
            warehouse = self._get_or_raise(warehouse_id)
            changes = payload.model_dump(exclude_unset=True)

            if "code" in changes and changes["code"].strip():
                new_code = changes["code"].strip()
                if self.repo.exists_by_code(new_code, exclude_id=warehouse.id):
                    raise ConflictError(
                        f"Warehouse code {new_code!r} already exists"
                    )
                warehouse.code = new_code

            for field in ("name", "address"):
                if field in changes:
                    setattr(warehouse, field, changes[field])
            if "is_active" in changes:
                warehouse.is_active = changes["is_active"]

            self.db.flush()
            self.audit.record(
                user_id=actor.id,
                action="WAREHOUSE.UPDATE",
                entity_type="warehouse",
                entity_id=warehouse.id,
                old_value={"id": warehouse.id, "code": warehouse.code, "name": warehouse.name},
                new_value={
                    "id": warehouse.id,
                    "code": warehouse.code,
                    "name": warehouse.name,
                    "is_active": warehouse.is_active,
                },
            )
            return warehouse_payload(warehouse)

    def _get_or_raise(self, warehouse_id: int) -> Warehouse:
        warehouse = self.repo.get_by_id(warehouse_id)
        if warehouse is None:
            raise NotFoundError(f"Warehouse {warehouse_id} not found")
        return warehouse