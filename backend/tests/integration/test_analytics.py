"""Analytics endpoint integration tests.

KPIs are computed live from operational data, so these tests seed deterministic
orders/shipments/history/transactions rows directly (setup) and read the
analytics through the API (assertion), including the SQL window-function
bottleneck metrics and MySQL-specific conditional aggregation.
"""

import datetime as dt
from datetime import datetime
from decimal import Decimal

import pytest

from app.modules.audit_logs.models import AuditLog
from app.modules.inventory.models import (
    Inventory,
    InventoryTransaction,
    InventoryTransactionType,
)
from app.modules.orders.models import Order, OrderItem
from app.modules.shipments.models import Shipment, ShipmentStatus, ShipmentStatusHistory
from app.modules.users.models import UserRole
from app.state_machines.order import OrderStatus

from tests.conftest import login


def _analyst_headers(api_client, seed):
    account = seed.user(
        "analyst@metrics.com", role=UserRole.ANALYST, name="Analyst"
    )
    token = login(api_client, account["email"], account["password"])
    return {"Authorization": f"Bearer {token}"}, account["id"]


def _seed_scenario(session_factory, actor_id):
    """Deterministic snapshot used by every KPI assertion below.

    Timestamps are relative to ``now`` so the numbers survive any wall clock:
      - inventory: WH1=5 (low), WH2=50  -> total 55, low 1 row / 1 item
      - orders: O1 CONFIRMED, O2 PLACED, O3 FULFILLED -> 2 active
      - shipments: SH1 delivered (late), SH2 delivered (on time),
        SH3 in-transit overdue, SH4 packed
      - movements: +50 receipt 5d ago, -45 adjustment 4d ago
    """
    now = datetime.utcnow()

    def ago(hours):
        return now - dt.timedelta(hours=hours)

    from app.modules.suppliers.models import Supplier
    from app.modules.warehouses.models import Warehouse
    from app.modules.products.models import Product

    with session_factory() as db:
        supplier = Supplier(name="Alpha Supplier", code="SUP-A")
        wh1 = Warehouse(name="Warehouse One", code="WH-1")
        wh2 = Warehouse(name="Warehouse Two", code="WH-2")
        product = Product(
            supplier=supplier,
            sku="SKU-A",
            name="Crate",
            unit="unit",
            reorder_threshold=Decimal("10"),
        )
        db.add_all([supplier, wh1, wh2, product])
        db.flush()

        inv1 = Inventory(
            product_id=product.id, warehouse_id=wh1.id, quantity=Decimal("5")
        )
        inv2 = Inventory(
            product_id=product.id, warehouse_id=wh2.id, quantity=Decimal("50")
        )
        db.add_all([inv1, inv2])
        db.flush()

        orders = []
        for i, (number, status, created_hours) in enumerate(
            [
                ("ORD-A-1", OrderStatus.CONFIRMED, 72),
                ("ORD-A-2", OrderStatus.PLACED, 48),
                ("ORD-A-3", OrderStatus.FULFILLED, 30),
            ],
            1,
        ):
            order = Order(
                order_number=number,
                status=status,
                created_by=actor_id,
                created_at=ago(created_hours),
            )
            db.add(order)
            db.flush()
            db.add(OrderItem(order_id=order.id, product_id=product.id, quantity=Decimal("10")))
            orders.append(order)

        def shipment(number, order, status, created_h, expected_h, actual_h):
            row = Shipment(
                shipment_number=number,
                order_id=order.id,
                status=status,
                created_by=actor_id,
                created_at=ago(created_h),
                expected_delivery_at=ago(expected_h) if expected_h else None,
                actual_delivery_at=ago(actual_h) if actual_h else None,
            )
            db.add(row)
            db.flush()
            return row

        sh1 = shipment("SHP-A-1", orders[0], ShipmentStatus.DELIVERED, 72, 48, 24)
        sh2 = shipment("SHP-A-2", orders[1], ShipmentStatus.DELIVERED, 48, None, 30)
        sh3 = shipment("SHP-A-3", orders[2], ShipmentStatus.IN_TRANSIT, 30, 12, None)
        sh4 = shipment("SHP-A-4", orders[2], ShipmentStatus.PACKED, 20, None, None)

        def history(row, status, hours):
            db.add(
                ShipmentStatusHistory(
                    shipment_id=row.id,
                    status=status,
                    changed_by=actor_id,
                    changed_at=ago(hours),
                )
            )

        history(sh1, ShipmentStatus.PACKED, 72)
        history(sh1, ShipmentStatus.IN_TRANSIT, 70)
        history(sh1, ShipmentStatus.DELIVERED, 24)
        history(sh2, ShipmentStatus.PACKED, 48)
        history(sh2, ShipmentStatus.IN_TRANSIT, 46)
        history(sh2, ShipmentStatus.DELIVERED, 30)
        history(sh3, ShipmentStatus.PACKED, 30)
        history(sh3, ShipmentStatus.IN_TRANSIT, 29)
        history(sh4, ShipmentStatus.PACKED, 20)

        # confirm -> packed timings: 74h ago, 50h ago, 31h ago, 11h after that
        for order_id, hours in [(orders[0].id, 74), (orders[1].id, 50), (orders[2].id, 31)]:
            db.add(
                AuditLog(
                    user_id=actor_id,
                    action="ORDER_CONFIRMED",
                    entity_type="order",
                    entity_id=order_id,
                    old_value=None,
                    new_value={"status": "CONFIRMED"},
                    created_at=ago(hours),
                )
            )

        db.add(
            InventoryTransaction(
                product_id=product.id,
                warehouse_id=wh2.id,
                type=InventoryTransactionType.RECEIPT,
                quantity=Decimal("50"),
                reference_type="RECEIPT",
                created_by=actor_id,
                created_at=ago(120),
            )
        )
        db.add(
            InventoryTransaction(
                product_id=product.id,
                warehouse_id=wh1.id,
                type=InventoryTransactionType.ADJUSTMENT,
                quantity=Decimal("-45"),
                reference_type="ADJUSTMENT",
                created_by=actor_id,
                created_at=ago(96),
            )
        )
        db.commit()


def _get(client, headers, path, **params):
    response = client.get(path, headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()["data"]


class TestOverview:
    @pytest.mark.db
    def test_overview_kpis(self, api_client, seed, session_factory):
        headers, actor_id = _analyst_headers(api_client, seed)
        _seed_scenario(session_factory, actor_id)

        data = _get(client=api_client, headers=headers, path="/api/v1/analytics/overview")
        assert data["total_products"] == 1
        assert data["total_inventory_units"] == 55
        assert data["low_stock_rows"] == 1
        assert data["low_stock_items"] == 1
        assert data["active_orders"] == 2
        assert data["shipments_in_transit"] == 1
        assert data["delayed_shipments"] == 1


class TestInventoryAnalytics:
    @pytest.mark.db
    def test_inventory_kpis_and_trends(self, api_client, seed, session_factory):
        headers, actor_id = _analyst_headers(api_client, seed)
        _seed_scenario(session_factory, actor_id)

        data = _get(
            client=api_client,
            headers=headers,
            path="/api/v1/analytics/inventory",
            period="day",
            days=30,
        )
        assert data["total_stock"] == 55
        assert data["low_stock_rows"] == 1
        assert data["low_stock_items"] == 1

        by_wh = {w["warehouse_code"]: w["total_stock"] for w in data["stock_by_warehouse"]}
        assert by_wh == {"WH-1": 5, "WH-2": 50}

        by_product = data["stock_by_product"]
        assert len(by_product) == 1
        assert by_product[0]["sku"] == "SKU-A"
        assert by_product[0]["total_stock"] == 55

        trends = data["movement_trends"]
        assert len(trends) >= 2
        assert sum(t["stock_in"] for t in trends) == 50
        assert sum(t["stock_out"] for t in trends) == 45
        assert sum(t["net_movement"] for t in trends) == 5
        assert data["trend_period"] == "day"


class TestShipmentAnalytics:
    @pytest.mark.db
    def test_shipment_kpis(self, api_client, seed, session_factory):
        headers, actor_id = _analyst_headers(api_client, seed)
        _seed_scenario(session_factory, actor_id)

        data = _get(
            client=api_client,
            headers=headers,
            path="/api/v1/analytics/shipments",
            period="day",
            days=30,
        )
        assert data["delivered_shipments"] == 2
        assert data["delayed_shipments"] == 1
        assert data["average_delivery_hours"] == pytest.approx(33.0, abs=0.001)
        assert data["average_delay_hours"] == pytest.approx(24.0, abs=0.001)

        perf = data["delivery_performance"]
        assert sum(p["delivered"] for p in perf) == 2
        assert sum(p["on_time"] for p in perf) == 1
        assert sum(p["late"] for p in perf) == 1


class TestSupplierAnalytics:
    @pytest.mark.db
    def test_supplier_kpis_computed_from_orders(self, api_client, seed, session_factory):
        headers, actor_id = _analyst_headers(api_client, seed)
        _seed_scenario(session_factory, actor_id)

        data = _get(client=api_client, headers=headers, path="/api/v1/analytics/suppliers")
        assert len(data["suppliers"]) == 1
        supplier = data["suppliers"][0]
        assert supplier["code"] == "SUP-A"
        assert supplier["order_count"] == 3
        assert supplier["delivery_count"] == 2
        assert supplier["on_time_delivery_rate"] == pytest.approx(0.5, abs=0.001)
        assert supplier["average_delivery_hours"] == pytest.approx(33.0, abs=0.001)

    @pytest.mark.db
    def test_multi_line_order_counts_each_shipment_once(
        self, api_client, seed, session_factory
    ):
        """One order with two lines from the same supplier is still ONE order
        with ONE shipment: line-item multiplicity must not inflate
        order_count/delivery_count or skew the average delivery time."""
        headers, actor_id = _analyst_headers(api_client, seed)
        now = datetime.utcnow()

        from app.modules.suppliers.models import Supplier
        from app.modules.products.models import Product

        with session_factory() as db:
            supplier = Supplier(name="Line Supplier", code="SUP-LINE")
            p1 = Product(
                supplier=supplier, sku="SKU-L1", name="Part One", unit="unit",
                reorder_threshold=Decimal("2"),
            )
            p2 = Product(
                supplier=supplier, sku="SKU-L2", name="Part Two", unit="unit",
                reorder_threshold=Decimal("2"),
            )
            db.add_all([supplier, p1, p2])
            db.flush()
            order = Order(
                order_number="ORD-LINE",
                status=OrderStatus.FULFILLED,
                created_by=actor_id,
                created_at=now - dt.timedelta(hours=40),
            )
            db.add(order)
            db.flush()
            db.add_all([
                OrderItem(order_id=order.id, product_id=p1.id, quantity=Decimal("5")),
                OrderItem(order_id=order.id, product_id=p2.id, quantity=Decimal("5")),
            ])
            shipment = Shipment(
                shipment_number="SHP-LINE",
                order_id=order.id,
                status=ShipmentStatus.DELIVERED,
                created_by=actor_id,
                created_at=now - dt.timedelta(hours=40),
                expected_delivery_at=None,
                actual_delivery_at=now - dt.timedelta(hours=10),
            )
            db.add(shipment)
            db.commit()

        data = _get(client=api_client, headers=headers, path="/api/v1/analytics/suppliers")
        supplier = next(s for s in data["suppliers"] if s["code"] == "SUP-LINE")
        assert supplier["order_count"] == 1
        assert supplier["delivery_count"] == 1
        assert supplier["on_time_delivery_rate"] == pytest.approx(1.0, abs=0.001)
        assert supplier["average_delivery_hours"] == pytest.approx(30.0, abs=0.001)

    @pytest.mark.db
    def test_multi_supplier_order_attributes_shipment_to_each_supplier_once(
        self, api_client, seed, session_factory
    ):
        """A shipment belongs to an order covering several suppliers; each
        supplier with a line on that order gets the order and its shipment
        counted exactly once."""
        headers, actor_id = _analyst_headers(api_client, seed)
        now = datetime.utcnow()

        from app.modules.suppliers.models import Supplier
        from app.modules.products.models import Product

        with session_factory() as db:
            s1 = Supplier(name="Supplier Alpha", code="SUP-ALPHA")
            s2 = Supplier(name="Supplier Beta", code="SUP-BETA")
            p1 = Product(
                supplier=s1, sku="SKU-M1", name="Alpha Part", unit="unit",
                reorder_threshold=Decimal("2"),
            )
            p2 = Product(
                supplier=s2, sku="SKU-M2", name="Beta Part", unit="unit",
                reorder_threshold=Decimal("2"),
            )
            db.add_all([s1, s2, p1, p2])
            db.flush()
            order = Order(
                order_number="ORD-MULTI",
                status=OrderStatus.FULFILLED,
                created_by=actor_id,
                created_at=now - dt.timedelta(hours=40),
            )
            db.add(order)
            db.flush()
            db.add_all([
                OrderItem(order_id=order.id, product_id=p1.id, quantity=Decimal("3")),
                OrderItem(order_id=order.id, product_id=p2.id, quantity=Decimal("3")),
            ])
            shipment = Shipment(
                shipment_number="SHP-MULTI",
                order_id=order.id,
                status=ShipmentStatus.DELIVERED,
                created_by=actor_id,
                created_at=now - dt.timedelta(hours=40),
                expected_delivery_at=now - dt.timedelta(hours=20),
                actual_delivery_at=now - dt.timedelta(hours=10),
            )
            db.add(shipment)
            db.commit()

        data = _get(client=api_client, headers=headers, path="/api/v1/analytics/suppliers")
        alpha = next(s for s in data["suppliers"] if s["code"] == "SUP-ALPHA")
        beta = next(s for s in data["suppliers"] if s["code"] == "SUP-BETA")
        for supplier in (alpha, beta):
            assert supplier["order_count"] == 1
            assert supplier["delivery_count"] == 1
            # Shipment 40h -> 10h, delivered 10h after its 20h deadline.
            assert supplier["average_delivery_hours"] == pytest.approx(30.0, abs=0.001)
            assert supplier["on_time_delivery_rate"] == pytest.approx(0.0, abs=0.001)


class TestBottlenecks:
    @pytest.mark.db
    def test_bottleneck_segments(self, api_client, seed, session_factory):
        headers, actor_id = _analyst_headers(api_client, seed)
        _seed_scenario(session_factory, actor_id)

        data = _get(client=api_client, headers=headers, path="/api/v1/analytics/bottlenecks")
        assert data["unit"] == "hours"
        segments = {s["name"]: s for s in data["segments"]}

        confirm_to_packed = segments["order_confirmed_to_packed"]
        assert confirm_to_packed["count"] == 4
        assert confirm_to_packed["avg_hours"] == pytest.approx(4.0, abs=0.001)
        assert confirm_to_packed["min_hours"] == pytest.approx(1.0, abs=0.001)
        assert confirm_to_packed["max_hours"] == pytest.approx(11.0, abs=0.001)
        assert confirm_to_packed["p50_hours"] == pytest.approx(2.0, abs=0.001)
        assert confirm_to_packed["p90_hours"] == pytest.approx(2.0, abs=0.001)

        packed_to_transit = segments["packed_to_in_transit"]
        assert packed_to_transit["count"] == 3
        assert packed_to_transit["avg_hours"] == pytest.approx(5 / 3, abs=0.001)
        assert packed_to_transit["min_hours"] == pytest.approx(1.0, abs=0.001)
        assert packed_to_transit["max_hours"] == pytest.approx(2.0, abs=0.001)
        assert packed_to_transit["p50_hours"] == pytest.approx(2.0, abs=0.001)

        transit_to_delivered = segments["in_transit_to_delivered"]
        assert transit_to_delivered["count"] == 2
        assert transit_to_delivered["avg_hours"] == pytest.approx(31.0, abs=0.001)
        assert transit_to_delivered["min_hours"] == pytest.approx(16.0, abs=0.001)
        assert transit_to_delivered["max_hours"] == pytest.approx(46.0, abs=0.001)
        assert transit_to_delivered["p50_hours"] == pytest.approx(16.0, abs=0.001)
        assert transit_to_delivered["p90_hours"] == pytest.approx(16.0, abs=0.001)

    @pytest.mark.db
    def test_bottlenecks_use_changed_at_not_history_insertion_order(
        self, api_client, seed, session_factory
    ):
        """Stage durations follow the *event* time (``changed_at``), never the
        history row insertion ``id``: a backfill that inserts the DELIVERED row
        before the IN_TRANSIT row must still produce 10h PACKED->IN_TRANSIT and
        40h IN_TRANSIT->DELIVERED (an id-ordered window would see no valid
        transitions at all)."""
        headers, actor_id = _analyst_headers(api_client, seed)
        now = datetime.utcnow()

        from app.modules.suppliers.models import Supplier
        from app.modules.products.models import Product

        with session_factory() as db:
            supplier = Supplier(name="Backfill Supplier", code="SUP-BF")
            product = Product(
                supplier=supplier, sku="SKU-BF", name="Backfilled", unit="unit",
                reorder_threshold=Decimal("2"),
            )
            db.add_all([supplier, product])
            db.flush()
            order = Order(
                order_number="ORD-BF",
                status=OrderStatus.FULFILLED,
                created_by=actor_id,
                created_at=now - dt.timedelta(hours=50),
            )
            db.add(order)
            db.flush()
            db.add(OrderItem(order_id=order.id, product_id=product.id, quantity=Decimal("1")))
            shipment = Shipment(
                shipment_number="SHP-BF",
                order_id=order.id,
                status=ShipmentStatus.DELIVERED,
                created_by=actor_id,
                created_at=now - dt.timedelta(hours=50),
                expected_delivery_at=None,
                actual_delivery_at=now - dt.timedelta(hours=10),
            )
            db.add(shipment)
            db.flush()
            # Insert OUT of chronological order on purpose: DELIVERED comes
            # before IN_TRANSIT, so an id-based window is nonsensical.
            def history(status, hours):
                db.add(
                    ShipmentStatusHistory(
                        shipment_id=shipment.id,
                        status=status,
                        changed_by=actor_id,
                        changed_at=now - dt.timedelta(hours=hours),
                    )
                )

            history(ShipmentStatus.PACKED, 50)
            history(ShipmentStatus.DELIVERED, 0)    # id-inserted before transit
            history(ShipmentStatus.IN_TRANSIT, 40)
            db.commit()

        data = _get(client=api_client, headers=headers, path="/api/v1/analytics/bottlenecks")
        segments = {s["name"]: s for s in data["segments"]}

        packed_to_transit = segments["packed_to_in_transit"]
        assert packed_to_transit["count"] == 1
        assert packed_to_transit["avg_hours"] == pytest.approx(10.0, abs=0.001)
        assert packed_to_transit["max_hours"] == pytest.approx(10.0, abs=0.001)

        transit_to_delivered = segments["in_transit_to_delivered"]
        assert transit_to_delivered["count"] == 1
        assert transit_to_delivered["avg_hours"] == pytest.approx(40.0, abs=0.001)
        assert transit_to_delivered["max_hours"] == pytest.approx(40.0, abs=0.001)