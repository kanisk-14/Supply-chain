"""Alert engine integration tests.

Covers the derived-conditions lifecycle:
- LOW_STOCK     : created below threshold, deduped while open, resolved when
                  every warehouse recovers, recreated on the next episode.
- SHIPMENT_OVERDUE: mirrors the delivered rule (``expected < now and not
                  delivered``) reactively on shipment create/dispatch/deliver.
- read-only API with pagination/filtering, plus auth failure behaviour.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.modules.alerts.models import Alert, AlertSeverity, AlertType
from app.modules.shipments.models import Shipment, ShipmentStatus
from app.modules.users.models import UserRole

from tests.conftest import login


def _headers_for(api_client, seed, role, email):
    account = seed.user(email, role=role)
    token = login(api_client, account["email"], account["password"])
    return {"Authorization": f"Bearer {token}"}


def _whm_headers(api_client, seed):
    return _headers_for(
        api_client, seed, UserRole.WAREHOUSE_MANAGER, "wh@alerts.com"
    )


def _scm_headers(api_client, seed):
    return _headers_for(
        api_client, seed, UserRole.SUPPLY_CHAIN_MANAGER, "scm@alerts.com"
    )


def _analyst_headers(api_client, seed):
    return _headers_for(api_client, seed, UserRole.ANALYST, "analyst@alerts.com")


def _setup(api_client, seed, catalog, stock=100, threshold=10):
    supplier = catalog.supplier(code="SUP-ALT")
    warehouse = catalog.warehouse(code="WH-ALT", name="Alerts Bay")
    product = catalog.product(
        supplier_id=supplier["id"], sku="SKU-ALT", name="Alert Crate",
        reorder_threshold=threshold,
    )
    catalog.inventory(
        product_id=product["id"], warehouse_id=warehouse["id"], quantity=stock
    )
    return {
        "wh": _whm_headers(api_client, seed),
        "scm": _scm_headers(api_client, seed),
        "analyst": _analyst_headers(api_client, seed),
        "warehouse": warehouse,
        "product": product,
    }


def _adjust(ctx, api_client, delta, reason="stock movement"):
    return api_client.post(
        "/api/v1/inventory/adjust",
        json={
            "product_id": ctx["product"]["id"],
            "warehouse_id": ctx["warehouse"]["id"],
            "delta": delta,
            "reason": reason,
        },
        headers=ctx["wh"],
    )


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


def _list_alerts(api_client, header, **params):
    response = api_client.get("/api/v1/alerts", headers=header, params=params)
    assert response.status_code == 200, response.text
    body = response.json()
    return {"items": body["data"], "total": body["meta"]["total"], "page": body["meta"]["page"], "limit": body["meta"]["limit"]}


class TestLowStockLifecycle:
    @pytest.mark.db
    def test_alert_created_when_below_threshold(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        response = _adjust(ctx, api_client, "-95")
        assert response.status_code == 200, response.text

        data = _list_alerts(api_client, ctx["analyst"])
        assert data["total"] == 1
        alert = data["items"][0]
        assert alert["type"] == "LOW_STOCK"
        assert alert["severity"] == "WARNING"
        assert alert["entity_type"] == "product"
        assert alert["entity_id"] == ctx["product"]["id"]
        assert alert["is_resolved"] is False

    @pytest.mark.db
    def test_alert_critical_at_zero_and_deduped_while_open(
        self, api_client, seed, catalog
    ):
        ctx = _setup(api_client, seed, catalog)
        _adjust(ctx, api_client, "-95")
        _adjust(ctx, api_client, "-5")  # quantity now 0

        data = _list_alerts(api_client, ctx["analyst"])
        assert data["total"] == 1  # same open episode, not duplicated
        assert data["items"][0]["severity"] == "WARNING"

    @pytest.mark.db
    def test_alert_resolves_when_product_back_above_threshold(
        self, api_client, seed, catalog, session_factory
    ):
        ctx = _setup(api_client, seed, catalog)
        _adjust(ctx, api_client, "-95")  # 5 < 10
        _adjust(ctx, api_client, "+6")   # 11 >= 10

        data = _list_alerts(api_client, ctx["analyst"], resolved="true")
        assert data["total"] == 1
        alert = data["items"][0]
        assert alert["is_resolved"] is True
        assert alert["resolved_at"] is not None

        with session_factory() as db:
            stored = db.execute(select(Alert)).scalar_one()
            assert stored.is_resolved is True
            assert stored.resolved_at is not None

    @pytest.mark.db
    def test_alert_reactivates_as_a_fresh_row_after_resolution(
        self, api_client, seed, catalog
    ):
        ctx = _setup(api_client, seed, catalog)
        _adjust(ctx, api_client, "-95")  # create
        _adjust(ctx, api_client, "+6")   # resolve
        _adjust(ctx, api_client, "-6")   # recreate (5 < 10)

        data = _list_alerts(api_client, ctx["analyst"])
        assert data["total"] == 2  # one resolved history row + one open
        open_rows = [a for a in data["items"] if a["is_resolved"] is False]
        resolved_rows = [a for a in data["items"] if a["is_resolved"] is True]
        assert len(open_rows) == 1
        assert len(resolved_rows) == 1
        assert open_rows[0]["id"] > resolved_rows[0]["id"]

    @pytest.mark.db
    def test_corrects_without_an_open_alert_when_stock_recovers_before_first_check(
        self, api_client, seed, catalog
    ):
        """No LOW_STOCK alert is ever created when the only stock row is healthy."""
        ctx = _setup(api_client, seed, catalog, stock=5)
        _adjust(ctx, api_client, "+6")  # 11 >= 10, but no alert existed

        data = _list_alerts(api_client, ctx["analyst"])
        assert data["total"] == 0


class TestShipmentOverdueLifecycle:
    @pytest.mark.db
    def test_alert_created_at_creation_when_expected_in_past(
        self, api_client, seed, catalog
    ):
        ctx = _setup(api_client, seed, catalog)
        order = _confirmed_order(api_client, ctx)
        past = datetime.utcnow() - timedelta(days=1)
        response = _create_shipment(api_client, ctx, order["id"], expected=past)
        assert response.status_code == 201, response.text

        data = _list_alerts(api_client, ctx["analyst"])
        assert data["total"] == 1
        alert = data["items"][0]
        assert alert["type"] == "SHIPMENT_OVERDUE"
        assert alert["severity"] == "WARNING"
        assert alert["entity_type"] == "shipment"
        assert alert["is_resolved"] is False

    @pytest.mark.db
    def test_not_overdue_when_expected_in_future(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        order = _confirmed_order(api_client, ctx)
        future = datetime.utcnow() + timedelta(days=30)
        response = _create_shipment(api_client, ctx, order["id"], expected=future)
        assert response.status_code == 201, response.text

        data = _list_alerts(api_client, ctx["analyst"])
        assert data["total"] == 0

    @pytest.mark.db
    def test_delivery_resolves_an_open_overdue_alert(
        self, api_client, seed, catalog
    ):
        ctx = _setup(api_client, seed, catalog)
        order = _confirmed_order(api_client, ctx)
        past = datetime.utcnow() - timedelta(days=1)
        shipment = _create_shipment(api_client, ctx, order["id"], expected=past)
        shipment_id = shipment.json()["data"]["id"]

        dispatched = api_client.post(
            f"/api/v1/shipments/{shipment_id}/dispatch",
            json={"warehouse_id": ctx["warehouse"]["id"]},
            headers=ctx["wh"],
        )
        assert dispatched.status_code == 200, dispatched.text

        data = _list_alerts(api_client, ctx["analyst"])
        assert data["total"] == 1
        assert data["items"][0]["is_resolved"] is False

        delivered = api_client.post(
            f"/api/v1/shipments/{shipment_id}/deliver", headers=ctx["wh"]
        )
        assert delivered.status_code == 200, delivered.text

        data = _list_alerts(api_client, ctx["analyst"], resolved="true")
        assert data["total"] == 1
        assert data["items"][0]["is_resolved"] is True
        assert data["items"][0]["resolved_at"] is not None

    @pytest.mark.db
    def test_dispatch_with_future_expected_resolves_open_alert(
        self, api_client, seed, catalog
    ):
        ctx = _setup(api_client, seed, catalog)
        order = _confirmed_order(api_client, ctx)
        past = datetime.utcnow() - timedelta(days=1)
        shipment = _create_shipment(api_client, ctx, order["id"], expected=past)
        shipment_id = shipment.json()["data"]["id"]

        future = datetime.utcnow() + timedelta(days=30)
        dispatched = api_client.post(
            f"/api/v1/shipments/{shipment_id}/dispatch",
            json={
                "warehouse_id": ctx["warehouse"]["id"],
                "expected_delivery_at": future.isoformat(),
            },
            headers=ctx["wh"],
        )
        assert dispatched.status_code == 200, dispatched.text

        data = _list_alerts(api_client, ctx["analyst"])
        assert data["total"] == 1
        assert data["items"][0]["is_resolved"] is True


class TestAlertsApi:
    @pytest.mark.db
    def test_list_filters_and_pagination(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        # two LOW_STOCK alerts (open + resolved) and one overdue alert
        _adjust(ctx, api_client, "-95")
        _adjust(ctx, api_client, "+6")
        order = _confirmed_order(api_client, ctx)
        _create_shipment(
            api_client, ctx, order["id"],
            expected=datetime.utcnow() - timedelta(days=1),
        )

        all_data = _list_alerts(api_client, ctx["analyst"])
        assert all_data["total"] == 2  # one resolved LOW_STOCK + one open overdue

        by_type = _list_alerts(api_client, ctx["analyst"], type="LOW_STOCK")
        assert by_type["total"] == 1
        assert {a["type"] for a in by_type["items"]} == {"LOW_STOCK"}

        open_only = _list_alerts(api_client, ctx["analyst"], resolved="false")
        assert open_only["total"] == 1
        assert all(a["is_resolved"] is False for a in open_only["items"])

        by_entity = _list_alerts(
            api_client, ctx["analyst"], entity_type="shipment",
            entity_id=1,
        )
        assert by_entity["total"] == 1
        assert by_entity["items"][0]["type"] == "SHIPMENT_OVERDUE"

        paged = _list_alerts(api_client, ctx["analyst"], page=1, limit=2)
        assert paged["total"] == 2
        assert len(paged["items"]) == 2
        assert paged["page"] == 1
        assert paged["limit"] == 2

    @pytest.mark.db
    def test_get_single_alert_and_404(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        _adjust(ctx, api_client, "-95")

        data = _list_alerts(api_client, ctx["analyst"])
        alert_id = data["items"][0]["id"]

        response = api_client.get(
            f"/api/v1/alerts/{alert_id}", headers=ctx["analyst"]
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["id"] == alert_id

        response = api_client.get(
            "/api/v1/alerts/999999", headers=ctx["analyst"]
        )
        assert response.status_code == 404

    @pytest.mark.db
    def test_reads_require_authentication(self, api_client, seed, catalog):
        response = api_client.get("/api/v1/alerts")
        assert response.status_code == 401

        response = api_client.get("/api/v1/analytics/overview")
        assert response.status_code == 401

    @pytest.mark.db
    def test_no_write_paths_exist(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        response = api_client.post(
            "/api/v1/alerts",
            json={"type": "LOW_STOCK", "entity_id": 1, "entity_type": "product"},
            headers=ctx["wh"],
        )
        assert response.status_code == 405  # GET-only collection, no write path