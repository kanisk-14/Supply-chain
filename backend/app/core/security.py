"""Security primitives.

Stage 2 wires authentication into request handling: passwords are hashed with
bcrypt (a purpose-built KDF, never stored in plaintext) and JWTs are issued and
verified with the configured ``JWT_SECRET``. JWT subjects reference the user
primary key as a string so consumers never infer a type from ``sub``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.core.config import settings

# Expose the configured JWT parameters once so modules import them from a
# single place instead of reading settings directly.
JWT_ALGORITHM: str = settings.JWT_ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES: int = settings.ACCESS_TOKEN_EXPIRE_MINUTES


def hash_password(raw_password: str) -> str:
    """Hash a plaintext password with bcrypt. Never reversible.

    bcrypt ignores bytes beyond 72; callers must validate length before use.
    """
    return bcrypt.hashpw(raw_password.encode("utf-8"), bcrypt.gensalt()).decode(
        "utf-8"
    )


def verify_password(raw_password: str, password_hash: str) -> bool:
    """Return True when ``raw_password`` matches the stored bcrypt hash."""
    try:
        return bcrypt.checkpw(
            raw_password.encode("utf-8"), password_hash.encode("utf-8")
        )
    except ValueError:
        # Malformed/legacy hash — treat as a mismatch, never raise to callers.
        return False


def create_access_token(
    user_id: int,
    *,
    extra: dict[str, Any] | None = None,
    expires_minutes: int | None = None,
) -> str:
    """Issue a signed JWT whose ``sub`` is the user primary key.

    ``exp`` is emitted from the configured lifetime unless overridden.
    """
    now = datetime.now(timezone.utc)
    minutes = expires_minutes or ACCESS_TOKEN_EXPIRE_MINUTES
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT. Raises ``jwt.InvalidTokenError`` on failure."""
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[JWT_ALGORITHM])