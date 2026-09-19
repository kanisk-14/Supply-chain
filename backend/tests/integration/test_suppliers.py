"""Supplier endpoint integration tests (duplicate code, no performance fields)."""

import pytest

from app.modules.users.models import UserRole
from tests.conftest import login


def _manager_headers(api_client, seed):
    account = seed.user("sup@mgr.com", role=UserRole.SUPPLY_CHAIN_MANAGER)
    token = login(api_client, account["email"], account["password"])
    return {"Authorization": f"Bearer {token}"}


class TestSupplierCRUD:
    @pytest.mark.db
    def test_create_supplier(self, api_client, seed):
        headers = _manager_headers(api_client, seed)
        response = api_client.post(
            "/api/v1/suppliers",
            json={
                "name": "Acme Supplies",
                "code": "SUP-ACME",
                "contact_name": "Wile",
                "email": "contact@acme.example",
            },
            headers=headers,
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["code"] == "SUP-ACME"
        assert data["is_active"] is True
        assert data["contact_name"] == "Wile"

    @pytest.mark.db
    def test_duplicate_code_conflict(self, api_client, seed, catalog):
        catalog.supplier(code="SUP-DUP")
        headers = _manager_headers(api_client, seed)
        response = api_client.post(
            "/api/v1/suppliers", json={"name": "Other", "code": "SUP-DUP"}, headers=headers
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "CONFLICT"

    @pytest.mark.db
    def test_list_and_get(self, api_client, seed, catalog):
        made = catalog.supplier(code="SUP-A", name="Supplier A")
        headers = _manager_headers(api_client, seed)
        listing = api_client.get("/api/v1/suppliers", headers=headers)
        assert listing.status_code == 200
        assert any(s["code"] == "SUP-A" for s in listing.json()["data"])
        single = api_client.get(f"/api/v1/suppliers/{made['id']}", headers=headers)
        assert single.json()["data"]["name"] == "Supplier A"

    @pytest.mark.db
    def test_patch_supplier(self, api_client, seed, catalog):
        made = catalog.supplier(code="SUP-P", name="Before")
        headers = _manager_headers(api_client, seed)
        response = api_client.patch(
            f"/api/v1/suppliers/{made['id']}",
            json={"name": "After", "is_active": False},
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "After"
        assert data["is_active"] is False

    @pytest.mark.db
    def test_patch_duplicate_code_conflict(self, api_client, seed, catalog):
        catalog.supplier(code="SUP-EXIST")
        made = catalog.supplier(code="SUP-TARGET")
        headers = _manager_headers(api_client, seed)
        response = api_client.patch(
            f"/api/v1/suppliers/{made['id']}",
            json={"code": "SUP-EXIST"},
            headers=headers,
        )
        assert response.status_code == 409

    @pytest.mark.db
    def test_missing_supplier_404(self, api_client, seed):
        headers = _manager_headers(api_client, seed)
        response = api_client.get("/api/v1/suppliers/99999", headers=headers)
        assert response.status_code == 404


class TestNoPerformanceFields:
    @pytest.mark.db
    def test_create_rejects_performance_payload(self, api_client, seed):
        headers = _manager_headers(api_client, seed)
        response = api_client.post(
            "/api/v1/suppliers",
            json={
                "name": "Acme",
                "code": "SUP-PERF",
                "on_time_rate": 99.9,
                "lead_time_days": 3,
            },
            headers=headers,
        )
        # Unknown fields are rejected rather than silently accepted/stored.
        assert response.status_code in (400, 422)

    @pytest.mark.db
    def test_response_never_contains_performance_fields(self, api_client, seed, catalog):
        catalog.supplier(code="SUP-READ", name="Plain")
        headers = _manager_headers(api_client, seed)
        response = api_client.get("/api/v1/suppliers", headers=headers)
        assert response.status_code == 200
        payload = str(response.json())
        for field in ("on_time_rate", "lead_time_days", "rating", "performance"):
            assert field not in payload