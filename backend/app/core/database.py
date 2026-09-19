"""Database infrastructure.

Holds the single SQLAlchemy ``Base`` (one canonical metadata registry for the
whole application), the engine and session factory bound to ``DATABASE_URL``,
and the FastAPI ``get_db`` dependency.

Transaction boundaries are owned by the *service* layer. Repositories receive a
``Session`` but must never commit; services open ``session.begin()`` so that a
failed step rolls back the entire unit of work (see docs/ARCHITECTURE.md).

The health-check helper below is a deliberate infrastructure exception to the
"no database access outside the repository layer" rule: it only pings the
engine and never touches business data.
"""

from datetime import datetime, timezone
from typing import Generator

from datetime import datetime, timezone
from typing import Generator

from sqlalchemy import Enum as SAEnum, MetaData, text, create_engine
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session, sessionmaker

from app.core.config import settings

# Constraint/index naming convention so that Alembic autogenerate produces
# stable, predictable names for every object it creates.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base used by every ORM model. One schema, one metadata."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def sa_enum(enum_cls: type) -> SAEnum:
    """Build a MySQL native ENUM column type from a ``str`` Enum.

    ``values_callable`` guarantees the stored values are the enum *values*
    (identical to names for the ``str`` enums used here).
    """
    return SAEnum(
        enum_cls,
        name=f"{enum_cls.__name__}_enum",
        values_callable=lambda obj: [m.value for m in obj],
    )


def create_db_engine(database_url: str):
    """Build an engine for a MySQL DSN with production-safe pool settings."""
    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_recycle=settings.DB_POOL_RECYCLE,
    )


engine = create_db_engine(settings.DATABASE_URL)

SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def check_database_connectivity(connectable=None) -> None:
    """Execute a trivial ``SELECT 1`` against the engine.

    Raises on connection failure; callers decide how to surface the result.
    """
    target = connectable or engine
    with target.connect() as conn:
        conn.execute(text("SELECT 1"))


def utcnow() -> datetime:
    """UTC timestamp used as the Python-side default for DATETIME columns.

    MySQL DATETIME is naive; the app stores naive UTC everywhere and treats
    every persisted timestamp as UTC.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TimestampMixin:
    """created_at/updated_at DATETIME(6) columns.

    MySQL-side ``CURRENT_TIMESTAMP(6)`` defaults keep the database correct even
    when writes bypass the ORM; Python-side defaults keep tests deterministic.
    """

    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6),
        nullable=False,
        default=utcnow,
        server_default=text("CURRENT_TIMESTAMP(6)"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=text("CURRENT_TIMESTAMP(6)"),
        server_onupdate=text("CURRENT_TIMESTAMP(6)"),
    )