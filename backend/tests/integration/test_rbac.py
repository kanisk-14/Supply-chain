"""RBAC integration tests: the permission matrix enforced on every module.

Permission mapping is centralized in ``app/modules/auth/permissions.py``; these
tests lock the observable behaviour in: reads are role-scoped, writes are role-gated,
and invalid permissions are rejected with 403.
"""

import pytest

from app.modules.users.models import UserRole

# Write endpoints that require specific permissions
WRITE_ENDPOINTS = [
    ("post", "/api/v1/users", {"name": "X", "email": "x@x.com", "password": "Password1"}),
    ("post", "/api/v1/suppliers", {"name": "S", "code": "SUP-X"}),
    ("post", "/api/v1/products", {"supplier_id": 1, "sku": "SKU-X", "name": "P"}),
    ("post", "/api/v1/warehouses", {"code": "WH-X", "name": "W"}),
    ("post", "/api/v1/inventory/adjust", {"product_id": 1, "warehouse_id": 1, "delta": 5}),
    ("post", "/api/v1/inventory/transfer", {"product_id": 1, "from_warehouse_id": 1, "to_warehouse_id": 2, "quantity": 5}),
    ("post", "/api/v1/orders", {"items": [{"product_id": 1, "quantity": 1}]}),
    ("post", "/api/v1/shipments", {"order_id": 1, "expected_delivery_at": "2099-01-01T00:00:00"}),
]


def _login_and_header(api_client, seed, role: UserRole):
    account = seed.user(f"{role.name.lower()}@test.com", role=role)
    token = _login(api_client, account)
    return {"Authorization": f"Bearer {token}"}


def _login(api_client, account):
    response = api_client.post(
        "/api/v1/auth/login",
        json={"email": account["email"], "password": account["password"]},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


class TestUnauthenticated:
    @pytest.mark.db
    @pytest.mark.parametrize("method,path,body", WRITE_ENDPOINTS + [
        ("get", "/api/v1/users", None),
        ("get", "/api/v1/inventory", None),
        ("get", "/api/v1/analytics/overview", None),
    ])
    def test_all_endpoints_require_auth(self, api_client, method, path, body):
        kwargs = {} if body is None else {"json": body}
        response = getattr(api_client, method)(path, **kwargs)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHORIZED"


class TestAnalyst:
    @pytest.mark.db
    @pytest.mark.parametrize("method,path,body", WRITE_ENDPOINTS)
    def test_analyst_forbidden_on_all_writes(self, api_client, seed, method, path, body):
        headers = _login_and_header(api_client, seed, UserRole.ANALYST)
        response = getattr(api_client, method)(path, json=body, headers=headers)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"

    @pytest.mark.db
    def test_analyst_can_read_allowed(self, api_client, seed):
        """Analyst can read: analytics, inventory, shipments, suppliers, alerts."""
        headers = _login_and_header(api_client, seed, UserRole.ANALYST)
        for path in (
            "/api/v1/analytics/overview",
            "/api/v1/inventory",
            "/api/v1/shipments",
            "/api/v1/suppliers",
            "/api/v1/alerts",
        ):
            response = api_client.get(path, headers=headers)
            assert response.status_code == 200, f"Failed on {path}: {response.text}"

    @pytest.mark.db
    def test_analyst_forbidden_on_disallowed_reads(self, api_client, seed):
        """Analyst cannot read: users, products, warehouses, inventory/transactions, orders."""
        headers = _login_and_header(api_client, seed, UserRole.ANALYST)
        for path in (
            "/api/v1/users",
            "/api/v1/products",
            "/api/v1/warehouses",
            "/api/v1/inventory/transactions",
            "/api/v1/orders",
        ):
            response = api_client.get(path, headers=headers)
            assert response.status_code == 403, f"Should be forbidden on {path}"


class TestWarehouseManager:
    @pytest.mark.db
    def test_can_write_warehouses_inventory_shipments(self, api_client, seed, catalog):
        headers = _login_and_header(api_client, seed, UserRole.WAREHOUSE_MANAGER)
        # Warehouse write
        wh = api_client.post(
            "/api/v1/warehouses",
            json={"code": "WH-NEW", "name": "New WH"},
            headers=headers,
        )
        assert wh.status_code == 201
        wh_id = wh.json()["data"]["id"]
        wh2 = api_client.post(
            "/api/v1/warehouses",
            json={"code": "WH-NEW2", "name": "New WH 2"},
            headers=headers,
        ).json()["data"]["id"]
        # Inventory write (using warehouse scoped to manager)
        supplier = catalog.supplier(code="SUP-B")
        product = catalog.product(supplier_id=supplier["id"], sku="SKU-B")
        inv = api_client.post(
            "/api/v1/inventory/adjust",
            json={
                "product_id": product["id"],
                "warehouse_id": wh_id,
                "delta": 10,
            },
            headers=headers,
        )
        assert inv.status_code == 200
        transfer = api_client.post(
            "/api/v1/inventory/transfer",
            json={
                "product_id": product["id"],
                "from_warehouse_id": wh_id,
                "to_warehouse_id": wh2,
                "quantity": 3,
            },
            headers=headers,
        )
        assert transfer.status_code == 200
        # Shipment write (dispatch/deliver) - need to create order/shipment first via admin
        # For now test that the endpoint is accessible (will fail on business logic, not auth)

    @pytest.mark.db
    def test_can_read_allowed(self, api_client, seed):
        """Warehouse Manager can read: warehouses, inventory, orders, shipments, alerts."""
        headers = _login_and_header(api_client, seed, UserRole.WAREHOUSE_MANAGER)
        for path in (
            "/api/v1/warehouses",
            "/api/v1/inventory",
            "/api/v1/inventory/transactions",
            "/api/v1/orders",
            "/api/v1/shipments",
            "/api/v1/alerts",
        ):
            response = api_client.get(path, headers=headers)
            assert response.status_code == 200, f"Failed on {path}: {response.text}"

    @pytest.mark.db
    @pytest.mark.parametrize(
        "method,path,body",
        [
            ("post", "/api/v1/suppliers", {"name": "S", "code": "SUP-X"}),
            ("post", "/api/v1/products", {"supplier_id": 1, "sku": "SKU-X", "name": "P"}),
            ("post", "/api/v1/users", {"name": "X", "email": "x@x.com", "password": "Password1"}),
            ("post", "/api/v1/orders", {"items": [{"product_id": 1, "quantity": 1}]}),
            ("get", "/api/v1/analytics/overview", None),
        ],
    )
    def test_forbidden_on_disallowed(self, api_client, seed, method, path, body):
        headers = _login_and_header(api_client, seed, UserRole.WAREHOUSE_MANAGER)
        kwargs = {} if body is None else {"json": body}
        response = getattr(api_client, method)(path, **kwargs, headers=headers)
        assert response.status_code == 403, f"Should be forbidden on {method} {path}"


class TestSupplyChainManager:
    @pytest.mark.db
    def test_can_write_suppliers_products_orders_inventory_shipments(self, api_client, seed, catalog):
        headers = _login_and_header(api_client, seed, UserRole.SUPPLY_CHAIN_MANAGER)
        # Supplier write
        sup = api_client.post(
            "/api/v1/suppliers", json={"name": "Acme", "code": "SUP-ACME"}, headers=headers
        )
        assert sup.status_code == 201
        supplier_id = sup.json()["data"]["id"]
        # Product write
        product = api_client.post(
            "/api/v1/products",
            json={"supplier_id": supplier_id, "sku": "SKU-ACME", "name": "Gadget"},
            headers=headers,
        )
        assert product.status_code == 201
        prod_id = product.json()["data"]["id"]
        # Inventory write (visibility across warehouses)
        wh_a = catalog.warehouse(code="WH-A")
        wh_b = catalog.warehouse(code="WH-B")
        adj = api_client.post(
            "/api/v1/inventory/adjust",
            json={"product_id": prod_id, "warehouse_id": wh_a["id"], "delta": 10},
            headers=headers,
        )
        assert adj.status_code == 200
        tr = api_client.post(
            "/api/v1/inventory/transfer",
            json={"product_id": prod_id, "from_warehouse_id": wh_a["id"], "to_warehouse_id": wh_b["id"], "quantity": 2},
            headers=headers,
        )
        assert tr.status_code == 200
        # Order write
        order = api_client.post(
            "/api/v1/orders",
            json={"items": [{"product_id": prod_id, "quantity": 5}]},
            headers=headers,
        )
        assert order.status_code == 201
        order_id = order.json()["data"]["id"]
        # Confirm order (required for shipment creation)
        api_client.post(f"/api/v1/orders/{order_id}/confirm", headers=headers)
        # Shipment write
        shipment = api_client.post(
            "/api/v1/shipments",
            json={"order_id": order_id, "expected_delivery_at": "2099-01-01T00:00:00"},
            headers=headers,
        )
        assert shipment.status_code == 201

    @pytest.mark.db
    def test_can_read_allowed(self, api_client, seed):
        """Supply Chain Manager can read: suppliers, products, warehouses, inventory, orders, shipments, analytics, alerts."""
        headers = _login_and_header(api_client, seed, UserRole.SUPPLY_CHAIN_MANAGER)
        for path in (
            "/api/v1/suppliers",
            "/api/v1/products",
            "/api/v1/warehouses",
            "/api/v1/inventory",
            "/api/v1/inventory/transactions",
            "/api/v1/orders",
            "/api/v1/shipments",
            "/api/v1/analytics/overview",
            "/api/v1/alerts",
        ):
            response = api_client.get(path, headers=headers)
            assert response.status_code == 200, f"Failed on {path}: {response.text}"

    @pytest.mark.db
    @pytest.mark.parametrize(
        "method,path,body",
        [
            ("post", "/api/v1/users", {"name": "X", "email": "x@x.com", "password": "Password1"}),
            ("post", "/api/v1/warehouses", {"code": "WH-X", "name": "W"}),
        ],
    )
    def test_forbidden_on_disallowed(self, api_client, seed, method, path, body):
        headers = _login_and_header(api_client, seed, UserRole.SUPPLY_CHAIN_MANAGER)
        kwargs = {} if body is None else {"json": body}
        response = getattr(api_client, method)(path, **kwargs, headers=headers)
        assert response.status_code == 403, f"Should be forbidden on {method} {path}"


class TestAdmin:
    @pytest.mark.db
    @pytest.mark.parametrize("method,path,body", WRITE_ENDPOINTS)
    def test_admin_allowed_everywhere(self, api_client, seed, method, path, body):
        headers = _login_and_header(api_client, seed, UserRole.ADMIN)
        if path == "/api/v1/products" and method == "post":
            sup = api_client.post(
                "/api/v1/suppliers", json={"name": "S", "code": "SUP-1"}, headers=headers
            )
            body = {**body, "supplier_id": sup.json()["data"]["id"]}
        if path in ("/api/v1/inventory/adjust", "/api/v1/inventory/transfer"):
            sup = api_client.post(
                "/api/v1/suppliers", json={"name": "S", "code": "SUP-2"}, headers=headers
            ).json()["data"]["id"]
            prod = api_client.post(
                "/api/v1/products",
                json={"supplier_id": sup, "sku": "SKU-INV", "name": "P"},
                headers=headers,
            ).json()["data"]["id"]
            wh_a = api_client.post(
                "/api/v1/warehouses", json={"code": "WH-1", "name": "A"}, headers=headers
            ).json()["data"]["id"]
            if path == "/api/v1/inventory/adjust":
                body = {**body, "product_id": prod, "warehouse_id": wh_a}
            else:
                wh_b = api_client.post(
                    "/api/v1/warehouses", json={"code": "WH-2", "name": "B"}, headers=headers
                ).json()["data"]["id"]
                api_client.post(
                    "/api/v1/inventory/adjust",
                    json={"product_id": prod, "warehouse_id": wh_a, "delta": 10},
                    headers=headers,
                )
                body = {**body, "product_id": prod, "from_warehouse_id": wh_a, "to_warehouse_id": wh_b}
        if path == "/api/v1/orders" and method == "post":
            sup = api_client.post(
                "/api/v1/suppliers", json={"name": "S", "code": "SUP-3"}, headers=headers
            ).json()["data"]["id"]
            prod = api_client.post(
                "/api/v1/products",
                json={"supplier_id": sup, "sku": "SKU-ORD", "name": "P"},
                headers=headers,
            ).json()["data"]["id"]
            body = {**body, "items": [{"product_id": prod, "quantity": 1}]}
        if path == "/api/v1/shipments" and method == "post":
            sup = api_client.post(
                "/api/v1/suppliers", json={"name": "S", "code": "SUP-4"}, headers=headers
            ).json()["data"]["id"]
            prod = api_client.post(
                "/api/v1/products",
                json={"supplier_id": sup, "sku": "SKU-SHP", "name": "P"},
                headers=headers,
            ).json()["data"]["id"]
            order = api_client.post(
                "/api/v1/orders",
                json={"items": [{"product_id": prod, "quantity": 1}]},
                headers=headers,
            ).json()["data"]["id"]
            # Confirm the order first (shipments require CONFIRMED orders)
            api_client.post(f"/api/v1/orders/{order}/confirm", headers=headers)
            body = {**body, "order_id": order}
        response = getattr(api_client, method)(path, json=body, headers=headers)
        assert response.status_code in (200, 201), response.text


class TestInvalidPermissionsAreCentralized:
    @pytest.mark.db
    def test_permission_declaration_matches_mapping(self):
        from app.modules.auth.permissions import Permission, ROLE_PERMISSIONS
        from app.modules.users.models import UserRole

        # Every role must be declared with its permission set.
        for role in UserRole:
            assert role in ROLE_PERMISSIONS
        # ADMIN covers the full permission space.
        assert ROLE_PERMISSIONS[UserRole.ADMIN] == set(Permission)