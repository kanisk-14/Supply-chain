"""Configuration validation tests.

An invalid configuration must fail clearly at Settings construction time
rather than surfacing as a confusing runtime error later.
"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


class TestValidConfiguration:
    def test_defaults_load(self):
        settings = Settings()
        assert settings.ENVIRONMENT in {"development", "test", "staging", "production"}
        assert settings.DATABASE_URL.startswith("mysql+pymysql://")

    def test_cors_origins_parsed(self):
        settings = Settings(CORS_ORIGINS="http://localhost:3000,https://app.example.com")
        assert settings.cors_origins_list == [
            "http://localhost:3000",
            "https://app.example.com",
        ]

    def test_cors_origins_trailing_comma_stripped(self):
        settings = Settings(CORS_ORIGINS="http://localhost:3000,")
        assert settings.cors_origins_list == ["http://localhost:3000"]


class TestInvalidConfiguration:
    def test_invalid_environment_fails_clearly(self):
        with pytest.raises(ValidationError):
            Settings(ENVIRONMENT="banana")

    def test_non_mysql_dsn_fails_clearly(self):
        with pytest.raises(ValidationError):
            Settings(DATABASE_URL="postgresql://user:pass@localhost/db")

    def test_short_jwt_secret_fails_clearly(self):
        with pytest.raises(ValidationError):
            Settings(JWT_SECRET="tiny")

    def test_malformed_dsn_fails_clearly(self):
        with pytest.raises(ValidationError):
            Settings(DATABASE_URL="not-a-url")

    def test_test_database_url_optional_but_validated(self):
        with pytest.raises(ValidationError):
            Settings(TEST_DATABASE_URL="sqlite:///x.db")