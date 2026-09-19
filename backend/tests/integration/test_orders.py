"""Order endpoint + service integration tests.

Covers creation rules (at least one line item, positive quantity, existing
products, no duplicate lines), the PLACED → CONFIRMED → FULFILLED / CANCELLED
state machine (both valid and invalid transitions), RBAC, audit logging, and
pagination/filters.
"""

from sqlalchemy import func, select

import pytest
from app.modules.audit_logs.models import AuditLog
from app.modules.orders.models import Order, OrderItem
from app.modules.users.models import UserRole
from tests.conftest import login


def _headers_for(api_client, seed, role, email):
    account = seed.user(email, role=role)
    token = login(api_client, account["email"], account["password"])
    return {"Authorization": f"Bearer {token}"}


def _scm_headers(api_client, seed):
    return _headers_for(api_client, seed, UserRole.SUPPLY_CHAIN_MANAGER, "scm@orders.com")


def _setup(api_client, seed, catalog):
    headers = _scm_headers(api_client, seed)
    supplier = catalog.supplier(code="SUP-ORD")
    p1 = catalog.product(supplier_id=supplier["id"], sku="SKU-ORD1", name="Widget A")
    p2 = catalog.product(supplier_id=supplier["id"], sku="SKU-ORD2", name="Widget B")
    return {"headers": headers, "supplier": supplier, "p1": p1, "p2": p2}


def _create_order(api_client, headers, items):
    return api_client.post("/api/v1/orders", json={"items": items}, headers=headers)


def _count(db, model):
    return int(db.execute(select(func.count()).select_from(model)).scalar_one())


class TestOrderCreation:
    @pytest.mark.db
    def test_create_order_with_items(self, api_client, seed, catalog, session_factory):
        ctx = _setup(api_client, seed, catalog)
        response = _create_order(
            api_client,
            ctx["headers"],
            [
                {"product_id": ctx["p1"]["id"], "quantity": 10},
                {"product_id": ctx["p2"]["id"], "quantity": 2.5},
            ],
        )
        assert response.status_code == 201, response.text
        data = response.json()["data"]
        assert data["order_number"].startswith("ORD-")
        assert data["status"] == "PLACED"
        assert len(data["items"]) == 2
        assert data["items"][0]["product"]["sku"] == "SKU-ORD1"
        assert float(data["items"][0]["quantity"]) == 10

        with session_factory() as db:
            order = db.execute(select(Order)).scalar_one()
            assert order.order_number == data["order_number"]
            assert order.status.value == "PLACED"
            assert _count(db, OrderItem) == 2
            audits = db.execute(select(AuditLog)).scalars().all()
            assert any(a.action == "ORDER_CREATED" for a in audits)

    @pytest.mark.db
    def test_order_numbers_are_unique_across_orders(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        first = _create_order(api_client, ctx["headers"], [{"product_id": ctx["p1"]["id"], "quantity": 1}])
        second = _create_order(api_client, ctx["headers"], [{"product_id": ctx["p1"]["id"], "quantity": 2}])
        assert first.status_code == 201 and second.status_code == 201
        assert (
            first.json()["data"]["order_number"] != second.json()["data"]["order_number"]
        )

    @pytest.mark.db
    def test_order_with_no_items_400(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        response = _create_order(api_client, ctx["headers"], [])
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    @pytest.mark.db
    def test_order_quantity_zero_or_negative_422(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        for quantity in (0, -3):
            response = _create_order(
                api_client, ctx["headers"], [{"product_id": ctx["p1"]["id"], "quantity": quantity}]
            )
            assert response.status_code == 422, response.text

    @pytest.mark.db
    def test_order_unknown_product_404(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        response = _create_order(
            api_client, ctx["headers"], [{"product_id": 999999, "quantity": 1}]
        )
        assert response.status_code == 404

    @pytest.mark.db
    def test_order_duplicate_product_line_400(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        response = _create_order(
            api_client,
            ctx["headers"],
            [
                {"product_id": ctx["p1"]["id"], "quantity": 1},
                {"product_id": ctx["p1"]["id"], "quantity": 2},
            ],
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


class TestOrderReads:
    @pytest.mark.db
    def test_get_order_with_items(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        created = _create_order(
            api_client, ctx["headers"], [{"product_id": ctx["p1"]["id"], "quantity": 4}]
        ).json()["data"]
        response = api_client.get(f"/api/v1/orders/{created['id']}", headers=ctx["headers"])
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["id"] == created["id"]
        assert len(data["items"]) == 1
        assert "shipments" not in data

        with_ships = api_client.get(
            f"/api/v1/orders/{created['id']}",
            params={"include_shipments": True},
            headers=ctx["headers"],
        )
        assert with_ships.json()["data"]["shipments"] == []

    @pytest.mark.db
    def test_get_missing_order_404(self, api_client, seed):
        headers = _scm_headers(api_client, seed)
        response = api_client.get("/api/v1/orders/999999", headers=headers)
        assert response.status_code == 404

    @pytest.mark.db
    def test_list_orders_filters_and_pagination(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        for _ in range(3):
            _create_order(api_client, ctx["headers"], [{"product_id": ctx["p1"]["id"], "quantity": 1}])

        listing = api_client.get(
            "/api/v1/orders",
            params={"status": "PLACED", "page": 1, "limit": 2},
            headers=ctx["headers"],
        )
        assert listing.status_code == 200
        body = listing.json()
        assert len(body["data"]) == 2
        assert body["meta"]["total"] == 3
        assert body["meta"]["pages"] == 2

        by_status = api_client.get(
            "/api/v1/orders", params={"status": "CANCELLED"}, headers=ctx["headers"]
        )
        assert by_status.json()["meta"]["total"] == 0


class TestOrderTransitions:
    def _confirmed_order(self, api_client, ctx):
        created = _create_order(
            api_client, ctx["headers"], [{"product_id": ctx["p1"]["id"], "quantity": 4}]
        ).json()["data"]
        confirmed = api_client.post(
            f"/api/v1/orders/{created['id']}/confirm", headers=ctx["headers"]
        )
        assert confirmed.status_code == 200
        return created["id"]

    @pytest.mark.db
    def test_confirm_placed_order(self, api_client, seed, catalog, session_factory):
        ctx = _setup(api_client, seed, catalog)
        order_id = self._confirmed_order(api_client, ctx)
        with session_factory() as db:
            order = db.get(Order, order_id)
            assert order.status.value == "CONFIRMED"
            audits = db.execute(
                select(AuditLog).where(
                    AuditLog.entity_id == order_id,
                    AuditLog.action == "ORDER_CONFIRMED",
                )
            ).scalars().all()
            assert len(audits) == 1

    @pytest.mark.db
    def test_confirm_twice_rejected_409(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        order_id = self._confirmed_order(api_client, ctx)
        response = api_client.post(f"/api/v1/orders/{order_id}/confirm", headers=ctx["headers"])
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"

    @pytest.mark.db
    def test_fulfill_from_placed_rejected_409(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        created = _create_order(
            api_client, ctx["headers"], [{"product_id": ctx["p1"]["id"], "quantity": 4}]
        ).json()["data"]
        response = api_client.post(f"/api/v1/orders/{created['id']}/fulfill", headers=ctx["headers"])
        assert response.status_code == 409

    @pytest.mark.db
    def test_fulfill_confirmed_order(self, api_client, seed, catalog, session_factory):
        ctx = _setup(api_client, seed, catalog)
        order_id = self._confirmed_order(api_client, ctx)
        response = api_client.post(f"/api/v1/orders/{order_id}/fulfill", headers=ctx["headers"])
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "FULFILLED"
        with session_factory() as db:
            audits = db.execute(
                select(AuditLog).where(
                    AuditLog.entity_id == order_id,
                    AuditLog.action == "ORDER_FULFILLED",
                )
            ).scalars().all()
            assert len(audits) == 1

    @pytest.mark.db
    def test_cancel_placed_order(self, api_client, seed, catalog, session_factory):
        ctx = _setup(api_client, seed, catalog)
        created = _create_order(
            api_client, ctx["headers"], [{"product_id": ctx["p1"]["id"], "quantity": 4}]
        ).json()["data"]
        response = api_client.post(f"/api/v1/orders/{created['id']}/cancel", headers=ctx["headers"])
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "CANCELLED"
        with session_factory() as db:
            order = db.get(Order, created["id"])
            assert order.status.value == "CANCELLED"
            audits = db.execute(
                select(AuditLog).where(
                    AuditLog.entity_id == created["id"],
                    AuditLog.action == "ORDER_CANCELLED",
                )
            ).scalars().all()
            assert len(audits) == 1

    @pytest.mark.db
    def test_cancel_confirmed_order(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        order_id = self._confirmed_order(api_client, ctx)
        response = api_client.post(f"/api/v1/orders/{order_id}/cancel", headers=ctx["headers"])
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "CANCELLED"

    @pytest.mark.db
    def test_cancel_fulfilled_order_rejected_409(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        order_id = self._confirmed_order(api_client, ctx)
        api_client.post(f"/api/v1/orders/{order_id}/fulfill", headers=ctx["headers"])
        response = api_client.post(f"/api/v1/orders/{order_id}/cancel", headers=ctx["headers"])
        assert response.status_code == 409

    @pytest.mark.db
    def test_cancel_twice_rejected_409(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        created = _create_order(
            api_client, ctx["headers"], [{"product_id": ctx["p1"]["id"], "quantity": 4}]
        ).json()["data"]
        api_client.post(f"/api/v1/orders/{created['id']}/cancel", headers=ctx["headers"])
        response = api_client.post(f"/api/v1/orders/{created['id']}/cancel", headers=ctx["headers"])
        assert response.status_code == 409

    @pytest.mark.db
    def test_transition_unknown_order_404(self, api_client, seed):
        headers = _scm_headers(api_client, seed)
        response = api_client.post("/api/v1/orders/999999/confirm", headers=headers)
        assert response.status_code == 404


class TestOrderAuthorization:
    @pytest.mark.db
    def test_requires_authentication(self, api_client):
        response = api_client.get("/api/v1/orders")
        assert response.status_code == 401

    @pytest.mark.db
    def test_analyst_cannot_create_order_403(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        analyst_headers = _headers_for(
            api_client, seed, UserRole.ANALYST, "analyst@orders.com"
        )
        response = _create_order(
            api_client,
            analyst_headers,
            [{"product_id": ctx["p1"]["id"], "quantity": 1}],
        )
        assert response.status_code == 403

    @pytest.mark.db
    def test_warehouse_manager_cannot_create_order_403(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        wm_headers = _headers_for(
            api_client, seed, UserRole.WAREHOUSE_MANAGER, "wm@orders.com"
        )
        response = _create_order(
            api_client, wm_headers, [{"product_id": ctx["p1"]["id"], "quantity": 1}]
        )
        assert response.status_code == 403

    @pytest.mark.db
    def test_analyst_can_read_orders(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        _create_order(api_client, ctx["headers"], [{"product_id": ctx["p1"]["id"], "quantity": 1}])
        analyst_headers = _headers_for(
            api_client, seed, UserRole.ANALYST, "analyst-read@orders.com"
        )
        listing = api_client.get("/api/v1/orders", headers=analyst_headers)
        assert listing.status_code == 200
        assert listing.json()["meta"]["total"] == 1

    @pytest.mark.db
    def test_analyst_cannot_confirm_order_403(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        created = _create_order(
            api_client, ctx["headers"], [{"product_id": ctx["p1"]["id"], "quantity": 1}]
        ).json()["data"]
        analyst_headers = _headers_for(
            api_client, seed, UserRole.ANALYST, "analyst-confirm@orders.com"
        )
        response = api_client.post(
            f"/api/v1/orders/{created['id']}/confirm", headers=analyst_headers
        )
        assert response.status_code == 403