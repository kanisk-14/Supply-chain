"""Shipment endpoint + service integration tests.

Covers the PACKED → IN_TRANSIT → DELIVERED state machine (valid and invalid
transitions), append-only shipment status history, derived is_delayed
calculation, delivery timestamps, transactional inventory stock-out on dispatch
(including insufficient-stock rollback), RBAC, and audit logging.
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.modules.audit_logs.models import AuditLog
from app.modules.inventory.models import (
    Inventory,
    InventoryTransaction,
    InventoryTransactionType,
)
from app.modules.orders.models import Order, OrderItem
from app.modules.shipments.models import Shipment, ShipmentStatusHistory
from app.modules.users.models import User, UserRole
from tests.conftest import login


def _headers_for(api_client, seed, role, email):
    account = seed.user(email, role=role)
    token = login(api_client, account["email"], account["password"])
    return {"Authorization": f"Bearer {token}"}


def _scm_headers(api_client, seed):
    return _headers_for(api_client, seed, UserRole.SUPPLY_CHAIN_MANAGER, "scm@ships.com")


def _whm_headers(api_client, seed):
    return _headers_for(api_client, seed, UserRole.WAREHOUSE_MANAGER, "wh@ships.com")


def _setup(api_client, seed, catalog, stock=100):
    scm_headers = _scm_headers(api_client, seed)
    wh_headers = _whm_headers(api_client, seed)
    supplier = catalog.supplier(code="SUP-SHP")
    warehouse = catalog.warehouse(code="WH-SHP", name="Dispatch Bay")
    product = catalog.product(supplier_id=supplier["id"], sku="SKU-SHP", name="Crate")
    catalog.inventory(product_id=product["id"], warehouse_id=warehouse["id"], quantity=stock)
    return {
        "scm": scm_headers,
        "wh": wh_headers,
        "supplier": supplier,
        "warehouse": warehouse,
        "product": product,
    }


def _confirmed_order(api_client, ctx, quantity=10) -> dict:
    created = api_client.post(
        "/api/v1/orders",
        json={"items": [{"product_id": ctx["product"]["id"], "quantity": quantity}]},
        headers=ctx["scm"],
    ).json()["data"]
    confirmed = api_client.post(
        f"/api/v1/orders/{created['id']}/confirm", headers=ctx["scm"]
    )
    assert confirmed.status_code == 200, confirmed.text
    return confirmed.json()["data"]


def _create_shipment(api_client, ctx, order_id, expected=None):
    body = {"order_id": order_id}
    if expected is not None:
        body["expected_delivery_at"] = expected.isoformat()
    return api_client.post("/api/v1/shipments", json=body, headers=ctx["wh"])


def _dispatch(api_client, ctx, shipment_id, expected=None):
    body = {"warehouse_id": ctx["warehouse"]["id"]}
    if expected is not None:
        body["expected_delivery_at"] = expected.isoformat()
    return api_client.post(
        f"/api/v1/shipments/{shipment_id}/dispatch", json=body, headers=ctx["wh"]
    )


def _count(db, model):
    return int(db.execute(select(func.count()).select_from(model)).scalar_one())


class TestShipmentCreation:
    @pytest.mark.db
    def test_create_shipment(self, api_client, seed, catalog, session_factory):
        ctx = _setup(api_client, seed, catalog)
        order = _confirmed_order(api_client, ctx)
        response = _create_shipment(api_client, ctx, order["id"])
        assert response.status_code == 201, response.text
        data = response.json()["data"]
        assert data["shipment_number"].startswith("SHP-")
        assert data["status"] == "PACKED"
        assert data["order_id"] == order["id"]
        assert data["actual_delivery_at"] is None
        assert data["is_delayed"] is False

        with session_factory() as db:
            shipment = db.execute(select(Shipment)).scalar_one()
            assert shipment.shipment_number == data["shipment_number"]
            assert shipment.status.value == "PACKED"
            history = db.execute(select(ShipmentStatusHistory)).scalars().all()
            assert [h.status.value for h in history] == ["PACKED"]
            audits = db.execute(select(AuditLog)).scalars().all()
            assert any(a.action == "SHIPMENT_CREATED" for a in audits)

    @pytest.mark.db
    def test_create_shipment_unknown_order_404(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        response = _create_shipment(api_client, ctx, 999999)
        assert response.status_code == 404

    @pytest.mark.db
    def test_create_shipment_for_placed_order_400(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        created = api_client.post(
            "/api/v1/orders",
            json={"items": [{"product_id": ctx["product"]["id"], "quantity": 1}]},
            headers=ctx["scm"],
        ).json()["data"]
        response = _create_shipment(api_client, ctx, created["id"])
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    @pytest.mark.db
    def test_create_shipment_for_cancelled_order_400(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        created = api_client.post(
            "/api/v1/orders",
            json={"items": [{"product_id": ctx["product"]["id"], "quantity": 1}]},
            headers=ctx["scm"],
        ).json()["data"]
        api_client.post(f"/api/v1/orders/{created['id']}/cancel", headers=ctx["scm"])
        response = _create_shipment(api_client, ctx, created["id"])
        assert response.status_code == 400

    @pytest.mark.db
    def test_shipment_numbers_are_unique(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        order = _confirmed_order(api_client, ctx)
        first = _create_shipment(api_client, ctx, order["id"])
        second = _create_shipment(api_client, ctx, order["id"])
        assert first.status_code == 201 and second.status_code == 201
        assert (
            first.json()["data"]["shipment_number"]
            != second.json()["data"]["shipment_number"]
        )


class TestDispatch:
    @pytest.mark.db
    def test_dispatch_decrements_inventory_and_records_history(
        self, api_client, seed, catalog, session_factory
    ):
        ctx = _setup(api_client, seed, catalog, stock=50)
        order = _confirmed_order(api_client, ctx, quantity=10)
        shipment = _create_shipment(api_client, ctx, order["id"]).json()["data"]
        future = datetime.now() + timedelta(days=3)

        response = _dispatch(api_client, ctx, shipment["id"], expected=future)
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["status"] == "IN_TRANSIT"
        assert data["expected_delivery_at"] is not None
        assert data["is_delayed"] is False

        with session_factory() as db:
            inv = db.execute(select(Inventory)).scalar_one()
            assert float(inv.quantity) == 40
            txns = db.execute(select(InventoryTransaction)).scalars().all()
            assert len(txns) == 1
            assert txns[0].type == InventoryTransactionType.SHIPMENT_DISPATCH
            assert float(txns[0].quantity) == -10
            assert txns[0].reference_type == "SHIPMENT"
            assert txns[0].reference_id == shipment["id"]

            history = db.execute(
                select(ShipmentStatusHistory).order_by(ShipmentStatusHistory.changed_at)
            ).scalars().all()
            assert [h.status.value for h in history] == ["PACKED", "IN_TRANSIT"]

            audits = db.execute(
                select(AuditLog).where(AuditLog.action == "SHIPMENT_DISPATCHED")
            ).scalars().all()
            assert len(audits) == 1

    @pytest.mark.db
    def test_dispatch_keeps_existing_expected_delivery_at(self, api_client, seed, catalog, session_factory):
        ctx = _setup(api_client, seed, catalog, stock=50)
        order = _confirmed_order(api_client, ctx, quantity=5)
        future = datetime.now() + timedelta(days=2)
        shipment = _create_shipment(api_client, ctx, order["id"], expected=future).json()["data"]

        response = _dispatch(api_client, ctx, shipment["id"])
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["expected_delivery_at"] == future.isoformat()

    @pytest.mark.db
    def test_dispatch_twice_rejected_409(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog, stock=50)
        order = _confirmed_order(api_client, ctx, quantity=5)
        shipment = _create_shipment(api_client, ctx, order["id"]).json()["data"]
        assert _dispatch(api_client, ctx, shipment["id"]).status_code == 200
        response = _dispatch(api_client, ctx, shipment["id"])
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"

    @pytest.mark.db
    def test_dispatch_unknown_shipment_404(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        response = _dispatch(api_client, ctx, 999999)
        assert response.status_code == 404

    @pytest.mark.db
    def test_dispatch_unknown_warehouse_404_rolls_back(self, api_client, seed, catalog, session_factory):
        ctx = _setup(api_client, seed, catalog, stock=50)
        order = _confirmed_order(api_client, ctx, quantity=5)
        shipment = _create_shipment(api_client, ctx, order["id"]).json()["data"]
        response = api_client.post(
            f"/api/v1/shipments/{shipment['id']}/dispatch",
            json={"warehouse_id": 999999},
            headers=ctx["wh"],
        )
        assert response.status_code == 404
        with session_factory() as db:
            row = db.get(Shipment, shipment["id"])
            assert row.status.value == "PACKED"
            assert _count(db, InventoryTransaction) == 0
            dispatch_audits = db.execute(
                select(AuditLog).where(AuditLog.action == "SHIPMENT_DISPATCHED")
            ).scalars().all()
            assert dispatch_audits == []

    @pytest.mark.db
    def test_dispatch_insufficient_inventory_409_and_rolls_back_all_tables(
        self, api_client, seed, catalog, session_factory
    ):
        ctx = _setup(api_client, seed, catalog, stock=2)
        order = _confirmed_order(api_client, ctx, quantity=10)
        shipment = _create_shipment(api_client, ctx, order["id"]).json()["data"]

        response = _dispatch(api_client, ctx, shipment["id"])
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "INSUFFICIENT_INVENTORY"

        with session_factory() as db:
            inv = db.execute(select(Inventory)).scalar_one()
            assert float(inv.quantity) == 2  # untouched
            assert _count(db, InventoryTransaction) == 0
            row = db.get(Shipment, shipment["id"])
            assert row.status.value == "PACKED"  # transition not persisted
            history = db.execute(select(ShipmentStatusHistory)).scalars().all()
            assert [h.status.value for h in history] == ["PACKED"]
            audits = db.execute(
                select(AuditLog).where(AuditLog.action == "SHIPMENT_DISPATCHED")
            ).scalars().all()
            assert audits == []

    @pytest.mark.db
    def test_dispatch_partial_failure_rolls_back_earlier_lines(
        self, api_client, seed, catalog, session_factory
    ):
        """Multi-line order: the first line would succeed, the second cannot.

        Proves the whole dispatch is atomic across products — no partial stock
        movement, history, transaction, or audit survives the failure.
        """
        ctx = _setup(api_client, seed, catalog)
        supplier = ctx["supplier"]
        p_a = catalog.product(supplier_id=supplier["id"], sku="SKU-SHPA", name="A")
        p_b = catalog.product(supplier_id=supplier["id"], sku="SKU-SHPB", name="B")
        catalog.inventory(product_id=p_a["id"], warehouse_id=ctx["warehouse"]["id"], quantity=5)
        catalog.inventory(product_id=p_b["id"], warehouse_id=ctx["warehouse"]["id"], quantity=1)

        created = api_client.post(
            "/api/v1/orders",
            json={
                "items": [
                    {"product_id": p_a["id"], "quantity": 2},
                    {"product_id": p_b["id"], "quantity": 5},
                ]
            },
            headers=ctx["scm"],
        ).json()["data"]
        api_client.post(f"/api/v1/orders/{created['id']}/confirm", headers=ctx["scm"])
        shipment = _create_shipment(api_client, ctx, created["id"]).json()["data"]

        response = _dispatch(api_client, ctx, shipment["id"])
        assert response.status_code == 409

        with session_factory() as db:
            invs = {r.product_id: float(r.quantity) for r in db.execute(select(Inventory)).scalars()}
            assert invs[p_a["id"]] == 5  # first line rolled back too
            assert invs[p_b["id"]] == 1
            assert _count(db, InventoryTransaction) == 0
            row = db.get(Shipment, shipment["id"])
            assert row.status.value == "PACKED"
            history = db.execute(select(ShipmentStatusHistory)).scalars().all()
            assert [h.status.value for h in history] == ["PACKED"]
            dispatch_audits = db.execute(
                select(AuditLog).where(AuditLog.action == "SHIPMENT_DISPATCHED")
            ).scalars().all()
            assert dispatch_audits == []


class TestDeliver:
    @pytest.mark.db
    def test_deliver_sets_timestamp_and_audits(self, api_client, seed, catalog, session_factory):
        ctx = _setup(api_client, seed, catalog, stock=50)
        order = _confirmed_order(api_client, ctx, quantity=5)
        shipment = _create_shipment(api_client, ctx, order["id"]).json()["data"]
        _dispatch(api_client, ctx, shipment["id"])

        response = api_client.post(
            f"/api/v1/shipments/{shipment['id']}/deliver", headers=ctx["wh"]
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["status"] == "DELIVERED"
        assert data["actual_delivery_at"] is not None
        assert data["is_delayed"] is False

        with session_factory() as db:
            row = db.get(Shipment, shipment["id"])
            assert row.actual_delivery_at is not None
            received_at = datetime.fromisoformat(data["actual_delivery_at"])
            assert received_at <= datetime.now()
            history = db.execute(select(ShipmentStatusHistory).order_by(ShipmentStatusHistory.id)).scalars().all()
            assert [h.status.value for h in history] == ["PACKED", "IN_TRANSIT", "DELIVERED"]
            audits = db.execute(
                select(AuditLog).where(AuditLog.action == "SHIPMENT_DELIVERED")
            ).scalars().all()
            assert len(audits) == 1

    @pytest.mark.db
    def test_deliver_without_dispatch_rejected_409(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        order = _confirmed_order(api_client, ctx, quantity=5)
        shipment = _create_shipment(api_client, ctx, order["id"]).json()["data"]
        response = api_client.post(
            f"/api/v1/shipments/{shipment['id']}/deliver", headers=ctx["wh"]
        )
        assert response.status_code == 409

    @pytest.mark.db
    def test_deliver_twice_rejected_409(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog, stock=50)
        order = _confirmed_order(api_client, ctx, quantity=5)
        shipment = _create_shipment(api_client, ctx, order["id"]).json()["data"]
        _dispatch(api_client, ctx, shipment["id"])
        assert api_client.post(
            f"/api/v1/shipments/{shipment['id']}/deliver", headers=ctx["wh"]
        ).status_code == 200
        response = api_client.post(
            f"/api/v1/shipments/{shipment['id']}/deliver", headers=ctx["wh"]
        )
        assert response.status_code == 409

    @pytest.mark.db
    def test_deliver_unknown_shipment_404(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        response = api_client.post(
            "/api/v1/shipments/999999/deliver", headers=ctx["wh"]
        )
        assert response.status_code == 404


class TestHistory:
    def _history(self, response):
        assert response.status_code == 200
        return response.json()["data"]

    @pytest.mark.db
    def test_history_is_append_only(self, api_client, seed, catalog, session_factory):
        ctx = _setup(api_client, seed, catalog, stock=50)
        order = _confirmed_order(api_client, ctx, quantity=5)
        shipment = _create_shipment(api_client, ctx, order["id"]).json()["data"]

        history_rows = []
        with session_factory() as db:
            first = db.execute(select(ShipmentStatusHistory)).scalar_one()
            history_rows.append((first.id, first.status.value))

        _dispatch(api_client, ctx, shipment["id"])
        api_client.post(f"/api/v1/shipments/{shipment['id']}/deliver", headers=ctx["wh"])

        rows = self._history(
            api_client.get(f"/api/v1/shipments/{shipment['id']}/history", headers=ctx["wh"])
        )
        assert [r["status"] for r in rows] == ["PACKED", "IN_TRANSIT", "DELIVERED"]
        assert len(rows) == 3

        with session_factory() as db:
            db_rows = db.execute(
                select(ShipmentStatusHistory).order_by(ShipmentStatusHistory.id)
            ).scalars().all()
            assert len(db_rows) == 3
            # The original PACKED row was never modified in place.
            assert db_rows[0].id == history_rows[0][0]
            assert db_rows[0].status.value == history_rows[0][1]
            assert db_rows[0].changed_at is not None

    @pytest.mark.db
    def test_history_unknown_shipment_404(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        response = api_client.get(
            "/api/v1/shipments/999999/history", headers=ctx["wh"]
        )
        assert response.status_code == 404


class TestDelayed:
    @pytest.mark.db
    def test_delayed_derived_until_delivered(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog, stock=50)
        order = _confirmed_order(api_client, ctx, quantity=5)
        past = datetime.now() - timedelta(hours=6)
        shipment = _create_shipment(api_client, ctx, order["id"], expected=past).json()["data"]

        assert shipment["is_delayed"] is True

        dispatched = _dispatch(api_client, ctx, shipment["id"]).json()["data"]
        assert dispatched["is_delayed"] is True

        delivered = api_client.post(
            f"/api/v1/shipments/{shipment['id']}/deliver", headers=ctx["wh"]
        ).json()["data"]
        assert delivered["status"] == "DELIVERED"
        assert delivered["is_delayed"] is False  # delivered is never delayed

    @pytest.mark.db
    def test_no_expected_delivery_is_never_delayed(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        order = _confirmed_order(api_client, ctx, quantity=1)
        shipment = _create_shipment(api_client, ctx, order["id"]).json()["data"]
        assert shipment["expected_delivery_at"] is None
        assert shipment["is_delayed"] is False

    @pytest.mark.db
    def test_is_delayed_list_filter(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog, stock=50)
        order = _confirmed_order(api_client, ctx, quantity=5)
        past = datetime.now() - timedelta(hours=6)
        future = datetime.now() + timedelta(days=1)
        _create_shipment(api_client, ctx, order["id"], expected=past).json()["data"]
        _create_shipment(api_client, ctx, order["id"], expected=future).json()["data"]

        delayed = api_client.get(
            "/api/v1/shipments",
            params={"is_delayed": True},
            headers=ctx["wh"],
        )
        assert delayed.status_code == 200
        assert len(delayed.json()["data"]) == 1
        assert delayed.json()["data"][0]["is_delayed"] is True

        on_time = api_client.get(
            "/api/v1/shipments",
            params={"is_delayed": False},
            headers=ctx["wh"],
        )
        assert len(on_time.json()["data"]) == 1
        assert on_time.json()["data"][0]["is_delayed"] is False


class TestShipmentReads:
    @pytest.mark.db
    def test_get_shipment(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        order = _confirmed_order(api_client, ctx, quantity=2)
        shipment = _create_shipment(api_client, ctx, order["id"]).json()["data"]
        response = api_client.get(f"/api/v1/shipments/{shipment['id']}", headers=ctx["wh"])
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["id"] == shipment["id"]
        assert data["order_id"] == order["id"]

    @pytest.mark.db
    def test_get_missing_shipment_404(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        response = api_client.get("/api/v1/shipments/999999", headers=ctx["wh"])
        assert response.status_code == 404

    @pytest.mark.db
    def test_list_shipments_filters(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog, stock=50)
        o1 = _confirmed_order(api_client, ctx, quantity=2)
        o2 = _confirmed_order(api_client, ctx, quantity=3)
        s1 = _create_shipment(api_client, ctx, o1["id"]).json()["data"]
        _create_shipment(api_client, ctx, o2["id"]).json()["data"]

        by_order = api_client.get(
            "/api/v1/shipments", params={"order_id": o1["id"]}, headers=ctx["wh"]
        )
        assert by_order.json()["meta"]["total"] == 1
        assert by_order.json()["data"][0]["id"] == s1["id"]

        dispatched = _dispatch(api_client, ctx, s1["id"]).json()["data"]
        by_status = api_client.get(
            "/api/v1/shipments", params={"status": "IN_TRANSIT"}, headers=ctx["wh"]
        )
        assert by_status.json()["meta"]["total"] == 1
        assert by_status.json()["data"][0]["id"] == dispatched["id"]


class TestServiceTransactionality:
    """Prove the dispatch unit of work rolls back a mid-transaction failure."""

    @pytest.mark.db
    def test_dispatch_failure_after_partial_stock_out_rolls_back_everything(
        self, db_session, session_factory, catalog, seed
    ):
        supplier = catalog.supplier(code="SUP-TXS")
        wh = catalog.warehouse(code="WH-TXS")
        p_a = catalog.product(supplier_id=supplier["id"], sku="SKU-TXA")
        p_b = catalog.product(supplier_id=supplier["id"], sku="SKU-TXB")
        catalog.inventory(product_id=p_a["id"], warehouse_id=wh["id"], quantity=10)
        catalog.inventory(product_id=p_b["id"], warehouse_id=wh["id"], quantity=10)
        # Load the actor on a fresh session: reusing ``db_session`` here would
        # open a REPEATABLE READ snapshot before the shipment exists (created on
        # another session below), making it invisible to the service call.
        with session_factory() as db:
            actor = db.get(User, seed.user("txs@actor.com")["id"])

        with session_factory() as db:
            order = Order(created_by=actor.id, order_number="ORD-TXS-0001")
            db.add(order)
            db.flush()
            order.order_number = f"ORD-{order.id:08d}"
            order.items.append(OrderItem(product_id=p_a["id"], quantity=Decimal("2")))
            order.items.append(OrderItem(product_id=p_b["id"], quantity=Decimal("2")))
            shipment = Shipment(
                order_id=order.id,
                shipment_number=f"SHP-PEND-{order.id}0000000000",
                created_by=actor.id,
            )
            db.add(shipment)
            db.commit()
            shipment_id = shipment.id

        from app.modules.inventory.service import InventoryService
        from app.modules.shipments.repositories import ShipmentRepository
        from app.modules.shipments.schemas import ShipmentDispatchRequest
        from app.modules.shipments.service import ShipmentService

        class FailingInventoryService(InventoryService):
            def __init__(self, db):
                super().__init__(db)
                self.dispatch_calls = 0

            def dispatch_stock(self, **kwargs):
                self.dispatch_calls += 1
                # First line succeeds (stock actually moves in the transaction),
                # the second raises -> the whole dispatch must roll back.
                if self.dispatch_calls >= 2:
                    raise RuntimeError("boom-mid-dispatch")
                return super().dispatch_stock(**kwargs)

        service = ShipmentService(db_session)
        service.inventory = FailingInventoryService(db_session)

        with pytest.raises(RuntimeError) as exc_info:
            service.dispatch(
                shipment_id,
                ShipmentDispatchRequest(warehouse_id=wh["id"]),
                actor=actor,
            )
        assert exc_info.value.args[0] == "boom-mid-dispatch"

        with session_factory() as db:
            invs = {
                r.product_id: float(r.quantity)
                for r in db.execute(select(Inventory)).scalars()
            }
            assert invs[p_a["id"]] == 10  # first line rolled back
            assert invs[p_b["id"]] == 10
            row = db.get(Shipment, shipment_id)
            assert row.status.value == "PACKED"
            assert _count(db, InventoryTransaction) == 0
            assert _count(db, ShipmentStatusHistory) == 0
            dispatch_audits = db.execute(
                select(AuditLog).where(AuditLog.action == "SHIPMENT_DISPATCHED")
            ).scalars().all()
            assert dispatch_audits == []


class TestShipmentAuthorization:
    @pytest.mark.db
    def test_requires_authentication(self, api_client):
        assert api_client.get("/api/v1/shipments").status_code == 401

    @pytest.mark.db
    def test_analyst_cannot_create_or_dispatch_403(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        order = _confirmed_order(api_client, ctx, quantity=2)
        analyst_headers = _headers_for(
            api_client, seed, UserRole.ANALYST, "analyst@ships.com"
        )
        create = api_client.post(
            "/api/v1/shipments", json={"order_id": order["id"]}, headers=analyst_headers
        )
        assert create.status_code == 403

        shipment = _create_shipment(api_client, ctx, order["id"]).json()["data"]
        dispatch = api_client.post(
            f"/api/v1/shipments/{shipment['id']}/dispatch",
            json={"warehouse_id": ctx["warehouse"]["id"]},
            headers=analyst_headers,
        )
        assert dispatch.status_code == 403

    @pytest.mark.db
    def test_analyst_can_read_shipments_and_history(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        order = _confirmed_order(api_client, ctx, quantity=2)
        shipment = _create_shipment(api_client, ctx, order["id"]).json()["data"]
        analyst_headers = _headers_for(
            api_client, seed, UserRole.ANALYST, "analyst-read@ships.com"
        )
        listing = api_client.get("/api/v1/shipments", headers=analyst_headers)
        assert listing.status_code == 200
        single = api_client.get(f"/api/v1/shipments/{shipment['id']}", headers=analyst_headers)
        assert single.status_code == 200
        history = api_client.get(
            f"/api/v1/shipments/{shipment['id']}/history", headers=analyst_headers
        )
        assert history.status_code == 200