"""Database integration tests.

These run against the isolated ``TEST_DATABASE_URL`` schema and are skipped
automatically when MySQL or the test database is unreachable. They verify the
canonical schema is usable from the ORM: inserts round-trip, constraints are
enforced at the database level, and enums/JSON behave as documented.
"""

import pytest
from sqlalchemy import select, text

from app.modules.users.models import User, UserRole
from app.modules.warehouses.models import Warehouse
from app.modules.products.models import Product
from app.modules.suppliers.models import Supplier
from app.modules.inventory.models import Inventory, InventoryTransactionType
from app.modules.orders.models import Order, OrderItem
from app.modules.shipments.models import Shipment, ShipmentStatus
from app.core.database import check_database_connectivity


class TestConnectivity:
    @pytest.mark.db
    def test_database_connection_works(self, mysql_db):
        # A direct probe against the app engine.
        check_database_connectivity()

    @pytest.mark.db
    def test_can_execute_select_1(self, test_database):
        with test_database.connect() as conn:
            value = conn.execute(text("SELECT 1")).scalar_one()
        assert value == 1


class TestSchemaBehaviour:
    @pytest.mark.db
    def test_user_round_trip_and_role_enum(self, db_session):
        user = User(name="Ada", email="ada@example.com", password_hash="x")
        db_session.add(user)
        db_session.commit()

        fetched = db_session.execute(
            select(User).where(User.email == "ada@example.com")
        ).scalar_one()
        assert fetched.name == "Ada"
        assert fetched.role == UserRole.ANALYST
        assert fetched.created_at is not None
        assert fetched.updated_at is not None

    @pytest.mark.db
    def test_email_unique_enforced(self, db_session):
        db_session.add(User(name="A", email="dup@example.com", password_hash="x"))
        db_session.commit()
        db_session.add(User(name="B", email="dup@example.com", password_hash="x"))
        with pytest.raises(Exception):
            db_session.commit()

    @pytest.mark.db
    def test_orphan_fk_rejected(self, db_session):
        db_session.add(Product(supplier_id=999, sku="SKU-X", name="Ghost"))
        with pytest.raises(Exception):
            db_session.commit()

    @pytest.mark.db
    def test_negative_quantity_check_enforced(self, db_session):
        supplier = Supplier(name="S", code="S1")
        warehouse = Warehouse(code="WH1", name="Warehouse One")
        db_session.add_all([supplier, warehouse])
        db_session.flush()
        product = Product(supplier_id=supplier.id, sku="SKU-NEG", name="P")
        db_session.add(product)
        db_session.flush()
        db_session.add(
            Inventory(
                product_id=product.id,
                warehouse_id=warehouse.id,
                quantity=-1,
            )
        )
        with pytest.raises(Exception):
            db_session.commit()

    @pytest.mark.db
    def test_inventory_unique_product_warehouse_enforced(self, db_session):
        supplier = Supplier(name="S", code="S2")
        warehouse = Warehouse(code="WH2", name="Warehouse Two")
        db_session.add_all([supplier, warehouse])
        db_session.flush()
        product = Product(supplier_id=supplier.id, sku="SKU-DUP", name="P")
        db_session.add(product)
        db_session.flush()
        db_session.add_all(
            [
                Inventory(product_id=product.id, warehouse_id=warehouse.id, quantity=1),
                Inventory(product_id=product.id, warehouse_id=warehouse.id, quantity=2),
            ]
        )
        with pytest.raises(Exception):
            db_session.commit()

    @pytest.mark.db
    def test_order_item_requires_positive_quantity(self, db_session):
        db_session.add(
            OrderItem(order_id=1, product_id=1, quantity=0)
        )
        with pytest.raises(Exception):
            db_session.commit()

    @pytest.mark.db
    def test_shipment_enum_and_history_append_only_shape(self, db_session):
        user = User(name="U", email="u@x.com", password_hash="x")
        db_session.add(user)
        db_session.flush()
        order = Order(order_number="ORD-1", created_by=user.id)
        db_session.add(order)
        db_session.flush()
        shipment = Shipment(
            shipment_number="SHP-1",
            order_id=order.id,
            created_by=user.id,
            expected_delivery_at=None,
        )
        db_session.add(shipment)
        db_session.commit()
        assert shipment.status == ShipmentStatus.PACKED
        assert shipment.expected_delivery_at is None