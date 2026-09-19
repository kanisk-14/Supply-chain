"""Application configuration.

All runtime configuration is read from environment variables (optionally loaded
from a `.env` file). Values are validated eagerly wherever possible so that an
invalid configuration fails clearly at startup instead of at request time.

Never hardcode passwords, database credentials, JWT secrets, or production URLs
in application code — everything comes from this settings object.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

VALID_ENVIRONMENTS = {"development", "test", "staging", "production"}

_BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Runtime
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # Database
    DATABASE_URL: str = "mysql+pymysql://root@127.0.0.1:3306/supply_chain?charset=utf8mb4"
    TEST_DATABASE_URL: str | None = None
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_RECYCLE: int = 1800

    # Security / JWT (activated in Stage 2)
    JWT_SECRET: str = "change-this-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # CORS — comma-separated list of allowed origins
    CORS_ORIGINS: str = "http://localhost:3000"

    @field_validator("ENVIRONMENT")
    @classmethod
    def _validate_environment(cls, value: str) -> str:
        if value.lower() not in VALID_ENVIRONMENTS:
            raise ValueError(
                f"ENVIRONMENT must be one of {sorted(VALID_ENVIRONMENTS)}, got {value!r}"
            )
        return value.lower()

    @field_validator("DATABASE_URL", "TEST_DATABASE_URL")
    @classmethod
    def _validate_mysql_dsn(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.startswith("mysql+pymysql://"):
            raise ValueError(
                "DATABASE_URL must use the mysql+pymysql:// scheme "
                f"(got a value not starting with that scheme). SQLAlchemy engines "
                f"are created from a single canonical DSN; drivers other than "
                f"PyMySQL are not supported."
            )
        return value

    @field_validator("JWT_SECRET")
    @classmethod
    def _validate_jwt_secret(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("JWT_SECRET must be at least 8 characters long")
        return value

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse the comma-separated CORS_ORIGINS value into a list.

        Empty entries are dropped so a trailing comma does not introduce an
        empty origin. Unrestricted cross-origin access is never allowed.
        """
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (pydantic-settings + lru_cache)."""
    return Settings()


settings = get_settings()