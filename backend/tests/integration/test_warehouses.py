"""Warehouse endpoint integration tests (unique code)."""

import pytest

from app.modules.users.models import UserRole
from tests.conftest import login


def _manager_headers(api_client, seed):
    account = seed.user("wh@mgr.com", role=UserRole.WAREHOUSE_MANAGER)
    token = login(api_client, account["email"], account["password"])
    return {"Authorization": f"Bearer {token}"}


class TestWarehouseCRUD:
    @pytest.mark.db
    def test_create_warehouse(self, api_client, seed):
        headers = _manager_headers(api_client, seed)
        response = api_client.post(
            "/api/v1/warehouses",
            json={"code": "WH-MAIN", "name": "Main Hub", "address": "1 Main St"},
            headers=headers,
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["code"] == "WH-MAIN"
        assert data["is_active"] is True

    @pytest.mark.db
    def test_duplicate_code_conflict(self, api_client, seed, catalog):
        catalog.warehouse(code="WH-DUP")
        headers = _manager_headers(api_client, seed)
        response = api_client.post(
            "/api/v1/warehouses",
            json={"code": "WH-DUP", "name": "Other"},
            headers=headers,
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "CONFLICT"

    @pytest.mark.db
    def test_list_and_get(self, api_client, seed, catalog):
        made = catalog.warehouse(code="WH-A", name="Warehouse A")
        headers = _manager_headers(api_client, seed)
        listing = api_client.get("/api/v1/warehouses", headers=headers)
        assert listing.status_code == 200
        assert any(w["code"] == "WH-A" for w in listing.json()["data"])
        single = api_client.get(f"/api/v1/warehouses/{made['id']}", headers=headers)
        assert single.json()["data"]["name"] == "Warehouse A"

    @pytest.mark.db
    def test_patch_warehouse(self, api_client, seed, catalog):
        made = catalog.warehouse(code="WH-P", name="Before")
        headers = _manager_headers(api_client, seed)
        response = api_client.patch(
            f"/api/v1/warehouses/{made['id']}",
            json={"name": "After", "is_active": False},
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "After"
        assert data["is_active"] is False

    @pytest.mark.db
    def test_patch_duplicate_code_conflict(self, api_client, seed, catalog):
        catalog.warehouse(code="WH-EXIST")
        made = catalog.warehouse(code="WH-TARGET")
        headers = _manager_headers(api_client, seed)
        response = api_client.patch(
            f"/api/v1/warehouses/{made['id']}",
            json={"code": "WH-EXIST"},
            headers=headers,
        )
        assert response.status_code == 409

    @pytest.mark.db
    def test_missing_warehouse_404(self, api_client, seed):
        headers = _manager_headers(api_client, seed)
        response = api_client.get("/api/v1/warehouses/99999", headers=headers)
        assert response.status_code == 404