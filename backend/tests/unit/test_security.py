"""Security primitive tests (hashing + JWT), no database required."""

import time

import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_is_not_plaintext(self):
        digest = hash_password("SuperSecret1")
        assert "SuperSecret1" not in digest
        assert digest != "SuperSecret1"

    def test_verify_correct_password(self):
        digest = hash_password("SuperSecret1")
        assert verify_password("SuperSecret1", digest) is True

    def test_verify_wrong_password(self):
        digest = hash_password("SuperSecret1")
        assert verify_password("TotallyWrong", digest) is False

    def test_hashes_are_salted(self):
        a = hash_password("SamePassword1")
        b = hash_password("SamePassword1")
        assert a != b

    def test_verify_malformed_hash_is_rejected(self):
        assert verify_password("x", "not-a-bcrypt-hash") is False


class TestJwt:
    def test_token_round_trip(self):
        token = create_access_token(42)
        payload = decode_access_token(token)
        assert payload["sub"] == "42"

    def test_token_carries_expiry(self):
        token = create_access_token(1)
        payload = decode_access_token(token)
        assert "exp" in payload
        assert payload["exp"] > int(time.time())

    def test_custom_lifetime(self):
        short = create_access_token(1, expires_minutes=1)
        assert decode_access_token(short)["exp"] <= int(time.time()) + 90

    def test_extra_claims(self):
        token = create_access_token(7, extra={"role": "ADMIN"})
        assert decode_access_token(token)["role"] == "ADMIN"

    def test_rejects_tampered_token(self):
        token = create_access_token(1)
        with pytest.raises(jwt.InvalidTokenError):
            decode_access_token(token + "x")

    def test_rejects_token_signed_with_different_secret(self):
        token = jwt.encode(
            {"sub": "1", "exp": int(time.time()) + 60},
            "some-other-secret-key",
            algorithm="HS256",
        )
        with pytest.raises(jwt.InvalidTokenError):
            decode_access_token(token)

    def test_rejects_expired_token(self):
        token = jwt.encode(
            {"sub": "1", "exp": int(time.time()) - 10},
            settings.JWT_SECRET,
            algorithm=settings.JWT_ALGORITHM,
        )
        with pytest.raises(jwt.ExpiredSignatureError):
            decode_access_token(token)