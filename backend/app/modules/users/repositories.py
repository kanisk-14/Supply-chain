"""Users data access layer. The only place user rows are queried."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.common.pagination import apply_pagination, count_total, resolve_pagination
from app.modules.users.models import User, UserRole


@dataclass
class UserListResult:
    items: list[User]
    total: int


class UserRepository:
    """CRUD over ``users``. Receives a ``Session`` and never commits."""

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _apply_filters(
        stmt: Select[tuple[User]],
        *,
        email: str | None,
        role: UserRole | None,
        is_active: bool | None,
    ) -> Select[tuple[User]]:
        if email:
            stmt = stmt.where(User.email == email.lower())
        if role is not None:
            stmt = stmt.where(User.role == role)
        if is_active is not None:
            stmt = stmt.where(User.is_active == is_active)
        return stmt

    def list(
        self,
        *,
        page: int | None,
        limit: int | None,
        email: str | None = None,
        role: UserRole | None = None,
        is_active: bool | None = None,
    ) -> UserListResult:
        stmt = self._apply_filters(
            select(User),
            email=email,
            role=role,
            is_active=is_active,
        )
        total = count_total(self.db, stmt, User.id)
        resolved_page, resolved_limit = resolve_pagination(page, limit)
        items = self.db.execute(
            apply_pagination(stmt.order_by(User.id), page, limit)
        ).scalars().all()
        return UserListResult(items=items, total=total)

    def get_by_id(self, user_id: int) -> User | None:
        return self.db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()

    def get_by_email(self, email: str) -> User | None:
        return self.db.execute(
            select(User).where(User.email == email.lower())
        ).scalar_one_or_none()

    def exists_by_email(self, email: str, *, exclude_id: int | None = None) -> bool:
        stmt = select(func.count()).select_from(User).where(User.email == email.lower())
        if exclude_id is not None:
            stmt = stmt.where(User.id != exclude_id)
        return int(self.db.execute(stmt).scalar_one()) > 0

    def add(self, user: User) -> None:
        self.db.add(user)
        self.db.flush()