"""Product endpoint integration tests.

Covers unique SKU, valid supplier, non-negative reorder threshold, and the rule
that products carry no inventory quantity.
"""

import pytest

from app.modules.users.models import UserRole
from tests.conftest import login


def _manager_headers(api_client, seed):
    account = seed.user("prod@mgr.com", role=UserRole.SUPPLY_CHAIN_MANAGER)
    token = login(api_client, account["email"], account["password"])
    return {"Authorization": f"Bearer {token}"}


def _given_supplier(api_client, seed, code="SUP-1"):
    headers = _manager_headers(api_client, seed)
    response = api_client.post(
        "/api/v1/suppliers", json={"name": "Supplier", "code": code}, headers=headers
    )
    assert response.status_code == 201
    return response.json()["data"]["id"], headers


class TestProductCRUD:
    @pytest.mark.db
    def test_create_product_with_supplier(self, api_client, seed):
        supplier_id, headers = _given_supplier(api_client, seed)
        response = api_client.post(
            "/api/v1/products",
            json={
                "supplier_id": supplier_id,
                "sku": "SKU-100",
                "name": "Gear",
                "unit": "piece",
                "reorder_threshold": "25",
            },
            headers=headers,
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["sku"] == "SKU-100"
        assert float(data["reorder_threshold"]) == 25
        assert data["supplier"]["id"] == supplier_id

    @pytest.mark.db
    def test_default_reorder_threshold_zero(self, api_client, seed):
        supplier_id, headers = _given_supplier(api_client, seed)
        response = api_client.post(
            "/api/v1/products",
            json={"supplier_id": supplier_id, "sku": "SKU-Z", "name": "Zero"},
            headers=headers,
        )
        assert response.status_code == 201
        assert float(response.json()["data"]["reorder_threshold"]) == 0

    @pytest.mark.db
    def test_duplicate_sku_conflict(self, api_client, seed):
        supplier_id, headers = _given_supplier(api_client, seed)
        first = api_client.post(
            "/api/v1/products",
            json={"supplier_id": supplier_id, "sku": "SKU-DUP", "name": "A"},
            headers=headers,
        )
        assert first.status_code == 201
        second = api_client.post(
            "/api/v1/products",
            json={"supplier_id": supplier_id, "sku": "SKU-DUP", "name": "B"},
            headers=headers,
        )
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "CONFLICT"

    @pytest.mark.db
    def test_invalid_supplier_404(self, api_client, seed):
        _, headers = _given_supplier(api_client, seed)
        response = api_client.post(
            "/api/v1/products",
            json={"supplier_id": 55555, "sku": "SKU-X", "name": "Ghost"},
            headers=headers,
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"

    @pytest.mark.db
    def test_negative_reorder_threshold_400(self, api_client, seed):
        supplier_id, headers = _given_supplier(api_client, seed)
        response = api_client.post(
            "/api/v1/products",
            json={
                "supplier_id": supplier_id,
                "sku": "SKU-NEG",
                "name": "Neg",
                "reorder_threshold": -1,
            },
            headers=headers,
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    @pytest.mark.db
    def test_list_filters_by_supplier_and_sku(self, api_client, seed):
        supplier_id, headers = _given_supplier(api_client, seed)
        api_client.post(
            "/api/v1/products",
            json={"supplier_id": supplier_id, "sku": "SKU-F1", "name": "One"},
            headers=headers,
        )
        result = api_client.get(
            "/api/v1/products",
            params={"sku": "SKU-F1"},
            headers=headers,
        )
        assert result.status_code == 200
        assert len(result.json()["data"]) == 1
        assert result.json()["data"][0]["sku"] == "SKU-F1"

    @pytest.mark.db
    def test_get_and_patch(self, api_client, seed):
        supplier_id, headers = _given_supplier(api_client, seed)
        created = api_client.post(
            "/api/v1/products",
            json={"supplier_id": supplier_id, "sku": "SKU-P", "name": "Before"},
            headers=headers,
        ).json()["data"]
        patched = api_client.patch(
            f"/api/v1/products/{created['id']}",
            json={"name": "After", "is_active": False},
            headers=headers,
        )
        assert patched.status_code == 200
        assert patched.json()["data"]["name"] == "After"
        assert patched.json()["data"]["is_active"] is False

        fetched = api_client.get(f"/api/v1/products/{created['id']}", headers=headers)
        assert fetched.status_code == 200
        assert float(fetched.json()["data"]["reorder_threshold"]) >= 0

    @pytest.mark.db
    def test_patch_no_inventory_quantity_field(self, api_client, seed, catalog):
        supplier = catalog.supplier(code="SUP-Q")
        product = catalog.product(supplier_id=supplier["id"], sku="SKU-Q")
        headers = _manager_headers(api_client, seed)
        response = api_client.get(f"/api/v1/products/{product['id']}", headers=headers)
        assert response.status_code == 200
        payload = str(response.json())
        assert "quantity" not in payload
        assert "stock" not in payload