"""Auth FastAPI dependencies.

``get_current_user`` resolves and validates the bearer JWT against the database;
``require_permissions`` composes with it to enforce role checks centrally. No
router decides authorization itself — it only declares the permissions it needs.
"""

from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.common.exceptions import ForbiddenError, UnauthorizedError
from app.core.database import get_db
from app.core.security import decode_access_token
from app.modules.auth.permissions import Permission, has_permissions
from app.modules.users.models import User
from app.modules.users.repositories import UserRepository

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the authenticated user from the bearer token.

    Rejects missing/invalid/expired tokens and inactive accounts with 401.
    """
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError("Not authenticated")

    try:
        payload = decode_access_token(credentials.credentials)
    except Exception:  # noqa: BLE001 - any JWT failure means invalid credentials
        raise UnauthorizedError("Invalid or expired token") from None

    subject = payload.get("sub")
    if subject is None or not str(subject).isdigit():
        raise UnauthorizedError("Invalid or expired token")

    user = UserRepository(db).get_by_id(int(subject))
    if user is None or not user.is_active:
        raise UnauthorizedError("Invalid or expired token")
    return user


def require_permissions(*permissions: Permission):
    """Build a dependency granting the current user iff they hold all perms."""

    def dependency(user: User = Depends(get_current_user)) -> User:
        if not has_permissions(user.role, *permissions):
            needed = ", ".join(p.value for p in permissions)
            raise ForbiddenError(
                f"Role {user.role.value} is not allowed to perform "
                f"this action (requires {needed})"
            )
        return user

    return dependency