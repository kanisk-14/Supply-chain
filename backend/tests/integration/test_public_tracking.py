"""Public package tracking integration tests.

Covers the dedicated public ``tracking_number`` (generation, format,
uniqueness, stability, immutability) and the unauthenticated
``GET /api/v1/public/tracking/{tracking_number}`` endpoint: lookups for
PACKED / IN_TRANSIT / DELIVERED / delayed shipments, timeline ordering,
not-found handling, absence of sensitive/internal fields, and regression
checks that internal shipment APIs still require authentication.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

import pytest

from app.modules.users.models import UserRole
from tests.conftest import login

TRACKING_PATTERN = re.compile(r"^TRK-[0-9A-F]{8}$")

PUBLIC_DATA_KEYS = {
    "tracking_number",
    "status",
    "is_delayed",
    "expected_delivery_at",
    "actual_delivery_at",
    "timeline",
}

TIMELINE_ENTRY_KEYS = {"status", "changed_at"}

# Keys that must never appear anywhere in the public tracking payload.
FORBIDDEN_KEYS = {
    "id",
    "shipment_id",
    "order_id",
    "created_by",
    "changed_by",
    "warehouse",
    "warehouse_id",
    "supplier",
    "suppliers",
    "inventory",
    "quantity",
    "user",
    "users",
    "audit",
    "permissions",
    "analytics",
    "email",
    "password",
    "password_hash",
    "token",
}


def _scm_headers(api_client, seed):
    account = seed.user("scm@track.com", role=UserRole.SUPPLY_CHAIN_MANAGER)
    token = login(api_client, account["email"], account["password"])
    return {"Authorization": f"Bearer {token}"}


def _setup(api_client, seed, catalog, stock=100):
    headers = _scm_headers(api_client, seed)
    supplier = catalog.supplier(code="SUP-TRK")
    warehouse = catalog.warehouse(code="WH-TRK", name="Tracking Bay")
    product = catalog.product(supplier_id=supplier["id"], sku="SKU-TRK", name="Parcel")
    catalog.inventory(product_id=product["id"], warehouse_id=warehouse["id"], quantity=stock)
    return {"scm": headers, "warehouse": warehouse, "product": product}


def _create_shipment(api_client, ctx, expected=None) -> dict:
    created = api_client.post(
        "/api/v1/orders",
        json={"items": [{"product_id": ctx["product"]["id"], "quantity": 2}]},
        headers=ctx["scm"],
    )
    assert created.status_code == 201, created.text
    order_id = created.json()["data"]["id"]
    confirmed = api_client.post(f"/api/v1/orders/{order_id}/confirm", headers=ctx["scm"])
    assert confirmed.status_code == 200, confirmed.text
    body: dict = {"order_id": order_id}
    if expected is not None:
        body["expected_delivery_at"] = expected.isoformat()
    shipment = api_client.post("/api/v1/shipments", json=body, headers=ctx["scm"])
    assert shipment.status_code == 201, shipment.text
    return shipment.json()["data"]


def _dispatch(api_client, ctx, shipment_id, expected=None) -> dict:
    body: dict = {"warehouse_id": ctx["warehouse"]["id"]}
    if expected is not None:
        body["expected_delivery_at"] = expected.isoformat()
    res = api_client.post(f"/api/v1/shipments/{shipment_id}/dispatch", json=body, headers=ctx["scm"])
    assert res.status_code == 200, res.text
    return res.json()["data"]


def _collect_keys(node, acc: set) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            acc.add(key)
            _collect_keys(value, acc)
    elif isinstance(node, list):
        for item in node:
            _collect_keys(item, acc)


def _public_get(api_client, tracking_number: str, headers=None):
    return api_client.get(f"/api/v1/public/tracking/{tracking_number}", headers=headers or {})


class TestTrackingNumberGeneration:
    @pytest.mark.db
    def test_generated_on_create_with_public_format(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        shipment = _create_shipment(api_client, ctx)
        assert TRACKING_PATTERN.match(shipment["tracking_number"]), shipment["tracking_number"]

    @pytest.mark.db
    def test_unique_across_shipments(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        numbers = [_create_shipment(api_client, ctx)["tracking_number"] for _ in range(10)]
        assert len(set(numbers)) == 10
        assert all(TRACKING_PATTERN.match(n) for n in numbers)

    @pytest.mark.db
    def test_stable_across_lifecycle(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        shipment = _create_shipment(api_client, ctx)
        tracking = shipment["tracking_number"]

        dispatched = _dispatch(api_client, ctx, shipment["id"])
        assert dispatched["tracking_number"] == tracking

        delivered = api_client.post(
            f"/api/v1/shipments/{shipment['id']}/deliver", headers=ctx["scm"]
        )
        assert delivered.status_code == 200, delivered.text
        assert delivered.json()["data"]["tracking_number"] == tracking

        listed = api_client.get("/api/v1/shipments", headers=ctx["scm"]).json()["data"]
        assert listed[0]["tracking_number"] == tracking

    @pytest.mark.db
    def test_cannot_be_set_or_changed_via_api(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        created = api_client.post(
            "/api/v1/orders",
            json={"items": [{"product_id": ctx["product"]["id"], "quantity": 1}]},
            headers=ctx["scm"],
        ).json()["data"]
        api_client.post(f"/api/v1/orders/{created['id']}/confirm", headers=ctx["scm"])
        # Extra field is forbidden by the create schema.
        rejected = api_client.post(
            "/api/v1/shipments",
            json={"order_id": created["id"], "tracking_number": "TRK-AAAAAAAA"},
            headers=ctx["scm"],
        )
        assert rejected.status_code in (400, 422), rejected.text


class TestPublicLookup:
    @pytest.mark.db
    def test_packed_shipment_unauthenticated(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        future = datetime.utcnow() + timedelta(days=3)
        shipment = _create_shipment(api_client, ctx, expected=future)

        res = _public_get(api_client, shipment["tracking_number"])
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["success"] is True
        data = body["data"]
        assert set(data.keys()) == PUBLIC_DATA_KEYS
        assert data["tracking_number"] == shipment["tracking_number"]
        assert data["status"] == "PACKED"
        assert data["is_delayed"] is False
        assert data["actual_delivery_at"] is None
        assert [e["status"] for e in data["timeline"]] == ["PACKED"]

    @pytest.mark.db
    def test_in_transit_timeline_ordering(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        shipment = _create_shipment(api_client, ctx)
        _dispatch(api_client, ctx, shipment["id"])

        data = _public_get(api_client, shipment["tracking_number"]).json()["data"]
        assert data["status"] == "IN_TRANSIT"
        statuses = [e["status"] for e in data["timeline"]]
        assert statuses == ["PACKED", "IN_TRANSIT"]
        changed = [e["changed_at"] for e in data["timeline"]]
        assert changed == sorted(changed)
        assert all(set(e.keys()) == TIMELINE_ENTRY_KEYS for e in data["timeline"])

    @pytest.mark.db
    def test_delivered_shipment(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        past = datetime.utcnow() - timedelta(days=1)
        shipment = _create_shipment(api_client, ctx, expected=past)
        _dispatch(api_client, ctx, shipment["id"])
        delivered = api_client.post(
            f"/api/v1/shipments/{shipment['id']}/deliver", headers=ctx["scm"]
        )
        assert delivered.status_code == 200, delivered.text

        data = _public_get(api_client, shipment["tracking_number"]).json()["data"]
        assert data["status"] == "DELIVERED"
        # Delivered is never delayed, even past the expectation.
        assert data["is_delayed"] is False
        assert data["actual_delivery_at"] is not None
        assert [e["status"] for e in data["timeline"]] == [
            "PACKED",
            "IN_TRANSIT",
            "DELIVERED",
        ]

    @pytest.mark.db
    def test_delayed_shipment(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        past = datetime.utcnow() - timedelta(days=2)
        shipment = _create_shipment(api_client, ctx, expected=past)

        data = _public_get(api_client, shipment["tracking_number"]).json()["data"]
        assert data["status"] == "PACKED"
        assert data["is_delayed"] is True

    @pytest.mark.db
    def test_lookup_is_case_insensitive(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        shipment = _create_shipment(api_client, ctx)
        res = _public_get(api_client, shipment["tracking_number"].lower())
        assert res.status_code == 200, res.text
        assert res.json()["data"]["tracking_number"] == shipment["tracking_number"]

    @pytest.mark.db
    def test_invalid_tracking_number_returns_not_found(self, api_client, seed, catalog):
        _setup(api_client, seed, catalog)
        res = _public_get(api_client, "TRK-FFFFFFFF")
        assert res.status_code == 404, res.text
        body = res.json()
        assert body["success"] is False
        assert body["error"]["code"] == "NOT_FOUND"

    @pytest.mark.db
    def test_no_sensitive_or_internal_fields_exposed(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        shipment = _create_shipment(api_client, ctx)
        _dispatch(api_client, ctx, shipment["id"])
        api_client.post(f"/api/v1/shipments/{shipment['id']}/deliver", headers=ctx["scm"])

        data = _public_get(api_client, shipment["tracking_number"]).json()["data"]
        keys: set = set()
        _collect_keys(data, keys)
        leaked = keys & FORBIDDEN_KEYS
        assert not leaked, f"Public payload leaks internal fields: {sorted(leaked)}"

    @pytest.mark.db
    def test_public_lookup_works_for_authenticated_users_too(
        self, api_client, seed, catalog
    ):
        ctx = _setup(api_client, seed, catalog)
        shipment = _create_shipment(api_client, ctx)
        res = _public_get(api_client, shipment["tracking_number"], headers=ctx["scm"])
        assert res.status_code == 200, res.text


class TestInternalApisStillProtected:
    @pytest.mark.db
    def test_internal_shipment_apis_require_auth(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        shipment = _create_shipment(api_client, ctx)
        # No Authorization header on any of these.
        assert api_client.get("/api/v1/shipments").status_code == 401
        assert api_client.get(f"/api/v1/shipments/{shipment['id']}").status_code == 401
        assert (
            api_client.get(f"/api/v1/shipments/{shipment['id']}/history").status_code
            == 401
        )
        assert (
            api_client.post(
                "/api/v1/shipments", json={"order_id": 1}
            ).status_code
            == 401
        )

    @pytest.mark.db
    def test_internal_shipment_detail_still_includes_tracking_number(
        self, api_client, seed, catalog
    ):
        """RBAC regression: authenticated reads keep working and now carry
        the tracking number for internal share/copy flows."""
        ctx = _setup(api_client, seed, catalog)
        shipment = _create_shipment(api_client, ctx)
        res = api_client.get(f"/api/v1/shipments/{shipment['id']}", headers=ctx["scm"])
        assert res.status_code == 200, res.text
        assert res.json()["data"]["tracking_number"] == shipment["tracking_number"]
