"""Supplier business rules.

Master-data-only: no performance fields exist anywhere in this module. Unique
``code`` conflicts surface as ``CONFLICT``; writes are transactional and audited.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.exceptions import ConflictError, NotFoundError
from app.common.transactions import transaction
from app.modules.audit_logs.service import AuditLogService
from app.modules.suppliers.models import Supplier
from app.modules.suppliers.repositories import SupplierRepository
from app.modules.suppliers.schemas import (
    SupplierCreate,
    SupplierUpdate,
    supplier_payload,
)
from app.modules.users.models import User


class SupplierService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = SupplierRepository(db)
        self.audit = AuditLogService(db)

    def list(self, *, page, limit, name=None, code=None, is_active=None) -> dict:
        result = self.repo.list(
            page=page,
            limit=limit,
            name=name,
            code=code,
            is_active=is_active,
        )
        return {
            "items": [supplier_payload(s) for s in result.items],
            "total": result.total,
        }

    def get(self, supplier_id: int) -> dict:
        return supplier_payload(self._get_or_raise(supplier_id))

    def create(self, payload: SupplierCreate, *, actor: User) -> dict:
        with transaction(self.db):
            data = payload.model_dump()
            if self.repo.exists_by_code(data["code"]):
                raise ConflictError(f"Supplier code {data['code']!r} already exists")
            supplier = Supplier(
                name=data["name"],
                code=data["code"],
                contact_name=data.get("contact_name"),
                email=data.get("email"),
                phone=data.get("phone"),
                address=data.get("address"),
            )
            self.repo.add(supplier)
            self.audit.record(
                user_id=actor.id,
                action="SUPPLIER.CREATE",
                entity_type="supplier",
                entity_id=supplier.id,
                new_value={
                    "id": supplier.id,
                    "name": supplier.name,
                    "code": supplier.code,
                },
            )
            return supplier_payload(supplier)

    def update(
        self, supplier_id: int, payload: SupplierUpdate, *, actor: User
    ) -> dict:
        with transaction(self.db):
            supplier = self._get_or_raise(supplier_id)
            changes = payload.model_dump(exclude_unset=True)

            if "code" in changes and changes["code"].strip():
                new_code = changes["code"].strip()
                if self.repo.exists_by_code(new_code, exclude_id=supplier.id):
                    raise ConflictError(
                        f"Supplier code {new_code!r} already exists"
                    )
                supplier.code = new_code

            for field in ("name", "contact_name", "email", "phone", "address"):
                if field in changes:
                    setattr(supplier, field, changes[field])
            if "is_active" in changes:
                supplier.is_active = changes["is_active"]

            self.db.flush()
            self.audit.record(
                user_id=actor.id,
                action="SUPPLIER.UPDATE",
                entity_type="supplier",
                entity_id=supplier.id,
                old_value={"id": supplier.id, "code": supplier.code, "name": supplier.name},
                new_value={
                    "id": supplier.id,
                    "name": supplier.name,
                    "code": supplier.code,
                    "is_active": supplier.is_active,
                },
            )
            return supplier_payload(supplier)

    def _get_or_raise(self, supplier_id: int) -> Supplier:
        supplier = self.repo.get_by_id(supplier_id)
        if supplier is None:
            raise NotFoundError(f"Supplier {supplier_id} not found")
        return supplier