"""User business rules.

Only-user concerns live here; routing/permissions stay in the router, HTTP
shaping is handled by schemas, and SQL stays in the repository. Writes run
inside an explicit transaction whose commit/rollback the service owns.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.common.transactions import transaction
from app.core.security import hash_password
from app.modules.audit_logs.service import AuditLogService
from app.modules.users.models import User, UserRole
from app.modules.users.repositories import UserRepository
from app.modules.users.schemas import UserCreate, UserUpdate, public_user_payload


class UserService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = UserRepository(db)
        self.audit = AuditLogService(db)

    def list(
        self,
        *,
        page: int | None,
        limit: int | None,
        email: str | None = None,
        role: UserRole | None = None,
        is_active: bool | None = None,
    ) -> dict:
        result = self.repo.list(
            page=page,
            limit=limit,
            email=email,
            role=role,
            is_active=is_active,
        )
        items = [public_user_payload(u) for u in result.items]
        return {"items": items, "total": result.total}

    def get(self, user_id: int) -> dict:
        user = self._get_or_raise(user_id)
        return public_user_payload(user)

    def create(
        self,
        payload: UserCreate,
        *,
        actor: User,
    ) -> dict:
        with transaction(self.db):
            payload_dict = payload.model_dump()
            if self.repo.exists_by_email(payload_dict["email"]):
                raise ConflictError(
                    f"User with email {payload_dict['email']!r} already exists"
                )
            user = User(
                name=payload_dict["name"],
                email=payload_dict["email"],
                password_hash=hash_password(payload_dict["password"]),
                role=payload_dict["role"],
                is_active=payload_dict["is_active"],
            )
            self.repo.add(user)
            self.audit.record(
                user_id=actor.id,
                action="USER.CREATE",
                entity_type="user",
                entity_id=user.id,
                new_value={
                    "id": user.id,
                    "name": user.name,
                    "email": user.email,
                    "role": user.role.value,
                    "is_active": user.is_active,
                },
            )
            return public_user_payload(user)

    def update(
        self,
        user_id: int,
        payload: UserUpdate,
        *,
        actor: User,
    ) -> dict:
        with transaction(self.db):
            user = self._get_or_raise(user_id)
            changes = payload.model_dump(exclude_unset=True)

            # Guard against self-lockout / self-escalation: an admin must never
            # be able to revoke their own role or deactivate their own account.
            if actor.id == user.id and {"role", "is_active"} & changes.keys():
                raise ForbiddenError(
                    "Cannot change your own role or active status"
                )

            old_snapshot = {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "role": user.role.value,
                "is_active": user.is_active,
            }

            if "email" in changes:
                email = changes["email"]
                if self.repo.exists_by_email(email, exclude_id=user.id):
                    raise ConflictError(
                        f"User with email {email!r} already exists"
                    )
                user.email = email

            if "name" in changes:
                user.name = changes["name"]
            if "password" in changes:
                user.password_hash = hash_password(changes["password"])
            if "role" in changes:
                user.role = changes["role"]
            if "is_active" in changes:
                user.is_active = changes["is_active"]

            self.db.flush()
            self.audit.record(
                user_id=actor.id,
                action="USER.UPDATE",
                entity_type="user",
                entity_id=user.id,
                old_value=old_snapshot,
                new_value={
                    "id": user.id,
                    "name": user.name,
                    "email": user.email,
                    "role": user.role.value,
                    "is_active": user.is_active,
                },
            )
            return public_user_payload(user)

    def _get_or_raise(self, user_id: int) -> User:
        user = self.repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found")
        return user