"""Authentication business rules.

Login never reveals whether the email exists or the password was wrong — both
failures surface as the same generic 401. Successful authentication returns a
signed access token carrying only the user id.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.exceptions import UnauthorizedError
from app.core.security import create_access_token, verify_password
from app.modules.users.models import User
from app.modules.users.repositories import UserRepository


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)

    def authenticate(self, email: str, password: str) -> User:
        """Validate credentials; raise 401 on any failure (no user enumeration)."""
        user = self.users.get_by_email(email)
        if user is None or not user.is_active:
            raise UnauthorizedError("Invalid email or password")
        if not verify_password(password, user.password_hash):
            raise UnauthorizedError("Invalid email or password")
        return user

    def issue_token(self, user: User) -> str:
        return create_access_token(user.id)