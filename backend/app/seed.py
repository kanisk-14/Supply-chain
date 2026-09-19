"""Development-only seed data.

Run with::

    python -m app.seed

Creates one user per role, a few suppliers, products, warehouses, and starting
inventory. It is **development-only**: it refuses to run when
``ENVIRONMENT=production`` and uses clearly non-production credentials. Running
it twice is safe (existing natural keys are skipped).
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import create_db_engine, sessionmaker
from app.core.security import hash_password
from app.modules.inventory.service import InventoryService
from app.modules.products.schemas import ProductCreate
from app.modules.products.service import ProductService
from app.modules.suppliers.schemas import SupplierCreate
from app.modules.suppliers.service import SupplierService
from app.modules.users.models import User, UserRole
from app.modules.warehouses.schemas import WarehouseCreate
from app.modules.warehouses.service import WarehouseService

# Dev-only credentials — never used in any other environment.
SEED_USERS = [
    dict(name="System Admin", email="admin@example.com", password="Admin123!", role=UserRole.ADMIN),
    dict(name="Sofia Warehouse", email="warehouse@example.com", password="Warehouse123!", role=UserRole.WAREHOUSE_MANAGER),
    dict(name="Liam Supply", email="supply@example.com", password="Supply123!", role=UserRole.SUPPLY_CHAIN_MANAGER),
    dict(name="Mia Analyst", email="analyst@example.com", password="Analyst123!", role=UserRole.ANALYST),
]

SEED_SUPPLIERS = [
    dict(name="Northwind Components", code="SUP-001", contact_name="Greg North", email="sales@northwind.example", phone="+1-555-0100", address="100 Industrial Pkwy, Detroit, MI"),
    dict(name="Blue Harbor Metals", code="SUP-002", contact_name="Nadia Blue", email="orders@blueharbor.example", phone="+1-555-0101", address="42 Dock Street, Seattle, WA"),
    dict(name="Everpeak Plastics", code="SUP-003", contact_name="Tom Peak", email="info@everpeak.example", phone="+1-555-0102", address="7 Mountain Rd, Denver, CO"),
]

SEED_PRODUCTS = [
    dict(supplier_code="SUP-001", sku="SKU-0001", name="Bearing Assembly 40mm", unit="piece", reorder_threshold="50"),
    dict(supplier_code="SUP-001", sku="SKU-0002", name="Drive Shaft Steel", unit="piece", reorder_threshold="25"),
    dict(supplier_code="SUP-002", sku="SKU-0003", name="Aluminium Sheet 1m", unit="sheet", reorder_threshold="300"),
    dict(supplier_code="SUP-002", sku="SKU-0004", name="Copper Wire Reel", unit="reel", reorder_threshold="80"),
    dict(supplier_code="SUP-003", sku="SKU-0005", name="ABS Resin Granules", unit="kg", reorder_threshold="500"),
    dict(supplier_code="SUP-003", sku="SKU-0006", name="Polymer Gasket Set", unit="set", reorder_threshold="120"),
]

SEED_WAREHOUSES = [
    dict(code="WH-001", name="Central Distribution", address="1 Hub Road, Chicago, IL"),
    dict(code="WH-002", name="West Coast Fulfillment", address="88 Bay Street, San Francisco, CA"),
]

SEED_INVENTORY = [
    dict(sku="SKU-0001", warehouse_code="WH-001", quantity="100"),
    dict(sku="SKU-0001", warehouse_code="WH-002", quantity="40"),
    dict(sku="SKU-0002", warehouse_code="WH-001", quantity="60"),
    dict(sku="SKU-0003", warehouse_code="WH-001", quantity="450"),
    dict(sku="SKU-0004", warehouse_code="WH-002", quantity="20"),
    dict(sku="SKU-0005", warehouse_code="WH-001", quantity="800"),
]


def _first(db: Session, model, **filters):
    query = db.query(model)
    for column, value in filters.items():
        query = query.filter(getattr(model, column) == value)
    return query.first()


def _seed_users(db: Session) -> dict[str, User]:
    by_role: dict[str, User] = {}
    for spec in SEED_USERS:
        existing = _first(db, User, email=spec["email"])
        if existing is None:
            existing = User(
                name=spec["name"],
                email=spec["email"],
                password_hash=hash_password(spec["password"]),
                role=spec["role"],
            )
            db.add(existing)
            db.flush()
        by_role[spec["role"].value] = existing
    return by_role


def _seed_suppliers(db: Session, service: SupplierService, actor: User) -> dict[str, int]:
    by_code: dict[str, int] = {}
    from app.modules.suppliers.models import Supplier

    for spec in SEED_SUPPLIERS:
        existing = _first(db, Supplier, code=spec["code"])
        if existing is not None:
            by_code[spec["code"]] = existing.id
            continue
        created = service.create(SupplierCreate(**spec), actor=actor)
        by_code[spec["code"]] = created["id"]
    return by_code


def _seed_products(db: Session, service: ProductService, actor: User, supplier_ids: dict[str, int]) -> dict[str, int]:
    from app.modules.products.models import Product

    by_sku: dict[str, int] = {}
    for spec in SEED_PRODUCTS:
        existing = _first(db, Product, sku=spec["sku"])
        if existing is not None:
            by_sku[spec["sku"]] = existing.id
            continue
        created = service.create(
            ProductCreate(
                supplier_id=supplier_ids[spec["supplier_code"]],
                sku=spec["sku"],
                name=spec["name"],
                unit=spec["unit"],
                reorder_threshold=spec["reorder_threshold"],
            ),
            actor=actor,
        )
        by_sku[spec["sku"]] = created["id"]
    return by_sku


def _seed_warehouses(db: Session, service: WarehouseService, actor: User) -> dict[str, int]:
    from app.modules.warehouses.models import Warehouse

    by_code: dict[str, int] = {}
    for spec in SEED_WAREHOUSES:
        existing = _first(db, Warehouse, code=spec["code"])
        if existing is not None:
            by_code[spec["code"]] = existing.id
            continue
        created = service.create(WarehouseCreate(**spec), actor=actor)
        by_code[spec["code"]] = created["id"]
    return by_code


def _seed_inventory(db: Session, service: InventoryService, actor: User, product_ids: dict[str, int], warehouse_ids: dict[str, int]) -> None:
    from app.modules.inventory.models import Inventory

    for spec in SEED_INVENTORY:
        product_id = product_ids[spec["sku"]]
        warehouse_id = warehouse_ids[spec["warehouse_code"]]
        exists = (
            db.query(Inventory)
            .filter(
                Inventory.product_id == product_id,
                Inventory.warehouse_id == warehouse_id,
            )
            .first()
        )
        if exists is not None:
            continue
        service.adjust(
            product_id=product_id,
            warehouse_id=warehouse_id,
            delta=Decimal(spec["quantity"]),
            reason="Initial seed stock",
            actor=actor,
        )


def run_seed() -> None:
    if settings.is_production:
        raise SystemExit("Refusing to seed the production environment")

    engine = create_db_engine(settings.DATABASE_URL)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with session_factory() as db:
        users = _seed_users(db)
        admin = users[UserRole.ADMIN.value]
        supplier_ids = _seed_suppliers(db, SupplierService(db), admin)
        product_ids = _seed_products(db, ProductService(db), admin, supplier_ids)
        warehouse_ids = _seed_warehouses(db, WarehouseService(db), admin)
        _seed_inventory(db, InventoryService(db), admin, product_ids, warehouse_ids)
        db.commit()
    engine.dispose()

    print("Seed complete. Credentials (development only):")
    for spec in SEED_USERS:
        print(f"  {spec['role'].value:<22} {spec['email']} / {spec['password']}")


if __name__ == "__main__":
    run_seed()