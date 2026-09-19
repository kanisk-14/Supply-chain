"""Shared test fixtures.

The application factory keeps tests independent of global startup state.
Database-backed tests build their own engine against ``TEST_DATABASE_URL`` so
the dev database is never touched and tests skip cleanly when MySQL is absent.

``api_client`` rebuilds the application with ``get_db`` overridden to the test
database so HTTP tests exercise the real router → service → repository pipeline
without ever touching the development schema.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import (
    Base,
    create_db_engine,
    check_database_connectivity,
    get_db,
)
from app.core.security import hash_password
from app.main import create_app
from app.modules.users.models import User, UserRole
from app.modules.suppliers.models import Supplier
from app.modules.warehouses.models import Warehouse
from app.modules.products.models import Product
from app.modules.inventory.models import Inventory

# Import every model module so metadata is complete before create_all/drop_all.
import app.modules.users.models  # noqa: F401
import app.modules.suppliers.models  # noqa: F401
import app.modules.products.models  # noqa: F401
import app.modules.warehouses.models  # noqa: F401
import app.modules.inventory.models  # noqa: F401
import app.modules.orders.models  # noqa: F401
import app.modules.shipments.models  # noqa: F401
import app.modules.alerts.models  # noqa: F401
import app.modules.audit_logs.models  # noqa: F401


@pytest.fixture(scope="session")
def app():
    return create_app()


@pytest.fixture()
def client(app):
    with TestClient(app) as test_client:
        yield test_client


def mysql_available() -> bool:
    try:
        check_database_connectivity()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def mysql_db():
    """Set when a MySQL server (the app engine) is reachable."""
    if not mysql_available():
        pytest.skip("MySQL is not reachable; skipping database-backed tests")
    return True


@pytest.fixture(scope="session")
def test_database(mysql_db):
    """Provision an isolated schema in the configured test database.

    The schema is created from the same metadata used by migrations, so it is
    always in sync with the canonical models.
    """
    url = settings.TEST_DATABASE_URL
    if not url:
        pytest.skip("TEST_DATABASE_URL is not configured")

    engine = create_db_engine(url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("TEST_DATABASE_URL is not reachable")

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


def _reset_schema(engine) -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


@pytest.fixture()
def session_factory(test_database):
    """A fresh sessionmaker bound to the isolated test schema."""
    return sessionmaker(
        bind=test_database, autoflush=False, expire_on_commit=False
    )


@pytest.fixture()
def db_session(test_database):
    session_factory = sessionmaker(
        bind=test_database, autoflush=False, expire_on_commit=False
    )
    db = session_factory()
    yield db
    db.close()


@pytest.fixture()
def api_client(test_database):
    """TestClient whose ``get_db`` dependency talks to the test database.

    The schema is fully reset per test so each test starts empty.
    """
    _reset_schema(test_database)
    factory = sessionmaker(
        bind=test_database, autoflush=False, expire_on_commit=False
    )

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    test_app = create_app()
    test_app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(test_app, raise_server_exceptions=False) as test_client:
            yield test_client
    finally:
        test_app.dependency_overrides.clear()


class UserSeed:
    """Small helper to drop users (or other rows) straight into the test DB."""

    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    def user(
        self,
        email: str,
        role: UserRole = UserRole.ANALYST,
        password: str = "Password123!",
        name: str = "Test User",
        is_active: bool = True,
    ) -> dict:
        password_hash = hash_password(password)
        with self.session_factory() as db:
            user = User(
                name=name,
                email=email,
                password_hash=password_hash,
                role=role,
                is_active=is_active,
            )
            db.add(user)
            db.commit()
            return {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "role": user.role,
                "password": password,
                "is_active": user.is_active,
            }


@pytest.fixture()
def seed(session_factory):
    """Seed helper bound to the test schema (see ``UserSeed``)."""
    return UserSeed(session_factory)


class CatalogSeeder:
    """Direct-insert helpers for master data used to set up test scenarios.

    The modules under test arrive later via the API; this seeds the *reference*
    rows (suppliers, warehouses, products, starting inventory) they depend on.
    """

    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    def _insert(self, model, **fields) -> dict:
        with self.session_factory() as db:
            row = model(**fields)
            db.add(row)
            db.commit()
            return {"id": row.id, **{k: getattr(row, k) for k in fields}}

    def supplier(self, code="SUP-001", name="Test Supplier") -> dict:
        return self._insert(Supplier, name=name, code=code)

    def warehouse(self, code="WH-001", name="Warehouse One") -> dict:
        return self._insert(Warehouse, name=name, code=code)

    def product(
        self,
        supplier_id: int,
        sku: str = "SKU-1",
        name: str = "Widget",
        unit: str = "unit",
        reorder_threshold=10,
    ) -> dict:
        return self._insert(
            Product,
            supplier_id=supplier_id,
            sku=sku,
            name=name,
            unit=unit,
            reorder_threshold=reorder_threshold,
        )

    def inventory(self, product_id: int, warehouse_id: int, quantity) -> dict:
        return self._insert(
            Inventory,
            product_id=product_id,
            warehouse_id=warehouse_id,
            quantity=quantity,
        )

    def count(self, model) -> int:
        from sqlalchemy import select, func

        with self.session_factory() as db:
            return int(db.execute(select(func.count()).select_from(model)).scalar_one())

    def fetch(self, model, row_id: int):
        from sqlalchemy import select

        with self.session_factory() as db:
            return db.execute(select(model).where(model.id == row_id)).scalar_one_or_none()


@pytest.fixture()
def catalog(session_factory):
    """Direct-insert helper for suppliers/warehouses/products/inventory rows."""
    return CatalogSeeder(session_factory)


@pytest.fixture()
def auth_headers():
    """Build Authorization headers from a previously obtained token."""

    def _build(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    return _build


def login(client, email: str, password: str) -> str:
    """Login through the real endpoint and return the access token."""
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["access_token"]