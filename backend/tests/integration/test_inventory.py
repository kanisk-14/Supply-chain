"""Inventory endpoint + service integration tests.

Stock mutations must be transactional, row-locked, and audited; every rule in
the Stage 2 spec (non-negative stock, unique product×warehouse, append-only
history, atomic transfers) is exercised below.
"""

from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.modules.alerts.models import Alert
from app.modules.audit_logs.models import AuditLog
from app.modules.inventory.models import (
    Inventory,
    InventoryTransaction,
    InventoryTransactionType,
)
from app.modules.users.models import User, UserRole
from tests.conftest import login


def _warehouse_manager_headers(api_client, seed):
    account = seed.user("wm@inv.com", role=UserRole.WAREHOUSE_MANAGER)
    token = login(api_client, account["email"], account["password"])
    return {"Authorization": f"Bearer {token}"}


def _setup(api_client, seed, catalog, threshold=10):
    """Return headers plus a supplier/warehouses/product ready to stock."""
    headers = _warehouse_manager_headers(api_client, seed)
    supplier = catalog.supplier(code="SUP-INV")
    wh_a = catalog.warehouse(code="WH-A", name="Warehouse A")
    wh_b = catalog.warehouse(code="WH-B", name="Warehouse B")
    product = catalog.product(
        supplier_id=supplier["id"], sku="SKU-INV", reorder_threshold=threshold
    )
    return {
        "headers": headers,
        "supplier": supplier,
        "warehouse_a": wh_a,
        "warehouse_b": wh_b,
        "product": product,
    }


def _adjust(api_client, headers, product_id, warehouse_id, delta):
    return api_client.post(
        "/api/v1/inventory/adjust",
        json={
            "product_id": product_id,
            "warehouse_id": warehouse_id,
            "delta": delta,
            "reason": "test",
        },
        headers=headers,
    )


def _count(db, model):
    return int(db.execute(select(func.count()).select_from(model)).scalar_one())


class TestAdjust:
    @pytest.mark.db
    def test_positive_adjust_creates_stock(self, api_client, seed, catalog, session_factory):
        ctx = _setup(api_client, seed, catalog)
        response = _adjust(api_client, ctx["headers"], ctx["product"]["id"], ctx["warehouse_a"]["id"], 50)
        assert response.status_code == 200
        data = response.json()["data"]
        assert float(data["quantity"]) == 50

        with session_factory() as db:
            row = db.execute(
                select(Inventory).where(
                    Inventory.product_id == ctx["product"]["id"],
                    Inventory.warehouse_id == ctx["warehouse_a"]["id"],
                )
            ).scalar_one()
            assert float(row.quantity) == 50

    @pytest.mark.db
    def test_negative_adjust_within_stock(self, api_client, seed, catalog, session_factory):
        ctx = _setup(api_client, seed, catalog)
        _adjust(api_client, ctx["headers"], ctx["product"]["id"], ctx["warehouse_a"]["id"], 40)
        response = _adjust(api_client, ctx["headers"], ctx["product"]["id"], ctx["warehouse_a"]["id"], -15)
        assert response.status_code == 200
        assert float(response.json()["data"]["quantity"]) == 25

    @pytest.mark.db
    def test_negative_adjust_below_zero_409(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        _adjust(api_client, ctx["headers"], ctx["product"]["id"], ctx["warehouse_a"]["id"], 5)
        response = _adjust(api_client, ctx["headers"], ctx["product"]["id"], ctx["warehouse_a"]["id"], -6)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "INSUFFICIENT_INVENTORY"

    @pytest.mark.db
    def test_negative_adjust_on_empty_stock_409(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        response = _adjust(api_client, ctx["headers"], ctx["product"]["id"], ctx["warehouse_b"]["id"], -1)
        assert response.status_code == 409

    @pytest.mark.db
    def test_adjust_zero_delta_rejected_422(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        response = _adjust(api_client, ctx["headers"], ctx["product"]["id"], ctx["warehouse_a"]["id"], 0)
        assert response.status_code == 422

    @pytest.mark.db
    def test_adjust_invalid_product_404(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        response = _adjust(api_client, ctx["headers"], 99999, ctx["warehouse_a"]["id"], 5)
        assert response.status_code == 404

    @pytest.mark.db
    def test_adjust_invalid_warehouse_404(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        response = _adjust(api_client, ctx["headers"], ctx["product"]["id"], 99999, 5)
        assert response.status_code == 404

    @pytest.mark.db
    def test_adjusment_is_transactional_and_audited(self, api_client, seed, catalog, session_factory):
        ctx = _setup(api_client, seed, catalog)
        _adjust(api_client, ctx["headers"], ctx["product"]["id"], ctx["warehouse_a"]["id"], 50)

        with session_factory() as db:
            txns = db.execute(select(InventoryTransaction)).scalars().all()
            assert len(txns) == 1
            assert txns[0].type == InventoryTransactionType.ADJUSTMENT
            assert txns[0].quantity == Decimal("50.0000")

            audits = db.execute(select(AuditLog)).scalars().all()
            assert any(a.action == "INVENTORY.ADJUST" for a in audits)

    @pytest.mark.db
    def test_concurrent_dup_insert_fails_cleanly(self, session_factory, catalog, seed):
        """(product, warehouse) uniqueness is enforced at the DB level."""
        supplier = catalog.supplier(code="SUP-UNIQ")
        wh = catalog.warehouse(code="WH-UNIQ")
        product = catalog.product(supplier_id=supplier["id"], sku="SKU-UNIQ")
        catalog.inventory(product_id=product["id"], warehouse_id=wh["id"], quantity=1)

        with session_factory() as db:
            db.add(
                Inventory(product_id=product["id"], warehouse_id=wh["id"], quantity=2)
            )
            with pytest.raises(Exception):
                db.commit()


class TestTransfer:
    @pytest.mark.db
    def test_transfer_moves_stock(self, api_client, seed, catalog, session_factory):
        ctx = _setup(api_client, seed, catalog)
        _adjust(api_client, ctx["headers"], ctx["product"]["id"], ctx["warehouse_a"]["id"], 30)
        response = api_client.post(
            "/api/v1/inventory/transfer",
            json={
                "product_id": ctx["product"]["id"],
                "from_warehouse_id": ctx["warehouse_a"]["id"],
                "to_warehouse_id": ctx["warehouse_b"]["id"],
                "quantity": 12,
            },
            headers=ctx["headers"],
        )
        assert response.status_code == 200
        rows = response.json()["data"]
        by_wh = {r["warehouse_id"]: r for r in rows}
        assert float(by_wh[ctx["warehouse_a"]["id"]]["quantity"]) == 18
        assert float(by_wh[ctx["warehouse_b"]["id"]]["quantity"]) == 12

        with session_factory() as db:
            txns = db.execute(
                select(InventoryTransaction).order_by(InventoryTransaction.id)
            ).scalars().all()
            types = [t.type for t in txns]
            assert types == [
                InventoryTransactionType.ADJUSTMENT,
                InventoryTransactionType.TRANSFER_OUT,
                InventoryTransactionType.TRANSFER_IN,
            ]
            out = txns[1]
            into = txns[2]
            assert out.quantity == Decimal("-12.0000")
            assert into.quantity == Decimal("12.0000")

            audits = db.execute(select(AuditLog)).scalars().all()
            assert len([a for a in audits if a.action == "INVENTORY.TRANSFER"]) == 2

    @pytest.mark.db
    def test_transfer_to_new_warehouse_creates_dest(self, api_client, seed, catalog, session_factory):
        ctx = _setup(api_client, seed, catalog)
        _adjust(api_client, ctx["headers"], ctx["product"]["id"], ctx["warehouse_a"]["id"], 10)
        response = api_client.post(
            "/api/v1/inventory/transfer",
            json={
                "product_id": ctx["product"]["id"],
                "from_warehouse_id": ctx["warehouse_a"]["id"],
                "to_warehouse_id": ctx["warehouse_b"]["id"],
                "quantity": 4,
            },
            headers=ctx["headers"],
        )
        assert response.status_code == 200
        with session_factory() as db:
            rows = db.execute(select(Inventory)).scalars().all()
            by_wh = {r.warehouse_id: r for r in rows}
            assert float(by_wh[ctx["warehouse_a"]["id"]].quantity) == 6
            assert float(by_wh[ctx["warehouse_b"]["id"]].quantity) == 4

    @pytest.mark.db
    def test_insufficient_stock_409_and_rolls_back(self, api_client, seed, catalog, session_factory):
        ctx = _setup(api_client, seed, catalog)
        _adjust(api_client, ctx["headers"], ctx["product"]["id"], ctx["warehouse_a"]["id"], 5)
        response = api_client.post(
            "/api/v1/inventory/transfer",
            json={
                "product_id": ctx["product"]["id"],
                "from_warehouse_id": ctx["warehouse_a"]["id"],
                "to_warehouse_id": ctx["warehouse_b"]["id"],
                "quantity": 10,
            },
            headers=ctx["headers"],
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "INSUFFICIENT_INVENTORY"

        with session_factory() as db:
            # No transfer records were written, inventory untouched.
            txns = db.execute(select(InventoryTransaction)).scalars().all()
            assert [t.type for t in txns] == [InventoryTransactionType.ADJUSTMENT]
            source = db.execute(
                select(Inventory).where(Inventory.warehouse_id == ctx["warehouse_a"]["id"])
            ).scalar_one()
            assert float(source.quantity) == 5
            dest = db.execute(
                select(Inventory).where(Inventory.warehouse_id == ctx["warehouse_b"]["id"])
            ).scalar_one_or_none()
            assert dest is None

    @pytest.mark.db
    def test_transfer_missing_warehouse_404_no_partial_change(self, api_client, seed, catalog, session_factory):
        ctx = _setup(api_client, seed, catalog)
        _adjust(api_client, ctx["headers"], ctx["product"]["id"], ctx["warehouse_a"]["id"], 9)
        response = api_client.post(
            "/api/v1/inventory/transfer",
            json={
                "product_id": ctx["product"]["id"],
                "from_warehouse_id": ctx["warehouse_a"]["id"],
                "to_warehouse_id": 123456,
                "quantity": 3,
            },
            headers=ctx["headers"],
        )
        assert response.status_code == 404
        with session_factory() as db:
            source = db.execute(
                select(Inventory).where(Inventory.warehouse_id == ctx["warehouse_a"]["id"])
            ).scalar_one()
            assert float(source.quantity) == 9
            assert _count(db, InventoryTransaction) == 1

    @pytest.mark.db
    def test_transfer_same_warehouse_400(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        _adjust(api_client, ctx["headers"], ctx["product"]["id"], ctx["warehouse_a"]["id"], 5)
        response = api_client.post(
            "/api/v1/inventory/transfer",
            json={
                "product_id": ctx["product"]["id"],
                "from_warehouse_id": ctx["warehouse_a"]["id"],
                "to_warehouse_id": ctx["warehouse_a"]["id"],
                "quantity": 2,
            },
            headers=ctx["headers"],
        )
        assert response.status_code == 400

    @pytest.mark.db
    def test_transfer_zero_or_negative_quantity_422(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        for q in (0, -3):
            response = api_client.post(
                "/api/v1/inventory/transfer",
                json={
                    "product_id": ctx["product"]["id"],
                    "from_warehouse_id": ctx["warehouse_a"]["id"],
                    "to_warehouse_id": ctx["warehouse_b"]["id"],
                    "quantity": q,
                },
                headers=ctx["headers"],
            )
            assert response.status_code == 422


class TestServiceTransactionality:
    """Prove the service-level transaction boundary rolls back on failure."""

    @pytest.mark.db
    def test_failure_after_partial_mutation_rolls_back_everything(
        self, db_session, session_factory, catalog, seed
    ):
        supplier = catalog.supplier(code="SUP-TX")
        wh_a = catalog.warehouse(code="WH-TXA")
        wh_b = catalog.warehouse(code="WH-TXB")
        product = catalog.product(supplier_id=supplier["id"], sku="SKU-TX")
        actor_dict = seed.user("tx@actor.com", role=UserRole.WAREHOUSE_MANAGER)
        actor = db_session.get(User, actor_dict["id"])

        from app.modules.inventory.models import Inventory as InvModel
        from app.modules.inventory.service import InventoryService

        # Seed 10 units so the mutation itself is valid.
        inv_a = catalog.inventory(
            product_id=product["id"], warehouse_id=wh_a["id"], quantity=10
        )

        from app.modules.inventory.repositories import InventoryRepository as InvRepo

        class FailingRepo(InvRepo):
            def __init__(self, db):
                super().__init__(db)
                self.sentinel = "boom-mid-transaction"
                self.transaction_creates = 0

            def add_transaction(self, transaction):
                self.transaction_creates += 1
                # Fail on the second append (TRANSFER_IN) — after the source
                # row and the TRANSFER_OUT row were already written.
                if self.transaction_creates >= 2:
                    raise RuntimeError(self.sentinel)
                return super().add_transaction(transaction)

        session = db_session

        from sqlalchemy.orm import Session

        service = InventoryService.__new__(InventoryService)
        service.db = session
        service.repo = FailingRepo(session)
        from app.modules.products.repositories import ProductRepository
        from app.modules.warehouses.repositories import WarehouseRepository
        from app.modules.audit_logs.service import AuditLogService
        from app.modules.alerts.service import AlertService

        service.products = ProductRepository(session)
        service.warehouses = WarehouseRepository(session)
        service.audit = AuditLogService(session)
        service.alerts = AlertService(session)

        with pytest.raises(RuntimeError) as exc_info:
            service.transfer(
                product_id=product["id"],
                from_warehouse_id=wh_a["id"],
                to_warehouse_id=wh_b["id"],
                quantity=4,
                actor=actor,
            )
        assert exc_info.value.args[0] == "boom-mid-transaction"

        # The whole unit of work rolled back: no partial stock, no history rows.
        with session_factory() as db:
            assert float(db.execute(
                select(Inventory.quantity).where(Inventory.id == inv_a["id"])
            ).scalar_one()) == 10
            assert db.execute(
                select(Inventory).where(Inventory.warehouse_id == wh_b["id"])
            ).scalar_one_or_none() is None
            assert _count(db, InventoryTransaction) == 0

    @pytest.mark.db
    def test_failed_transfer_leaves_no_audit_or_transactions(
        self, db_session, session_factory, catalog, seed
    ):
        """Insufficient-stock transfer raises inside the txn -> full rollback."""
        supplier = catalog.supplier(code="SUP-RA")
        wh = catalog.warehouse(code="WH-RA1")
        product = catalog.product(supplier_id=supplier["id"], sku="SKU-RA")
        actor_dict = seed.user("ra@actor.com", role=UserRole.WAREHOUSE_MANAGER)
        actor = db_session.get(User, actor_dict["id"])
        catalog.inventory(product_id=product["id"], warehouse_id=wh["id"], quantity=2)

        from app.modules.inventory.service import InventoryService

        service = InventoryService(db_session)
        with pytest.raises(Exception) as exc_info:
            service.transfer(
                product_id=product["id"],
                from_warehouse_id=wh["id"],
                to_warehouse_id=999999,
                quantity=5,
                actor=actor,
            )
        assert exc_info.type.__name__ in ("NotFoundError", "InsufficientInventoryError")

        with session_factory() as db:
            assert _count(db, InventoryTransaction) == 0
            assert _count(db, AuditLog) == 0


class TestHistoryAndAlerts:
    @pytest.mark.db
    def test_transactions_is_append_only_and_filterable(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog, threshold=10)
        _adjust(api_client, ctx["headers"], ctx["product"]["id"], ctx["warehouse_a"]["id"], 5)
        api_client.post(
            "/api/v1/inventory/transfer",
            json={
                "product_id": ctx["product"]["id"],
                "from_warehouse_id": ctx["warehouse_a"]["id"],
                "to_warehouse_id": ctx["warehouse_b"]["id"],
                "quantity": 2,
            },
            headers=ctx["headers"],
        )

        listing = api_client.get("/api/v1/inventory/transactions", headers=ctx["headers"])
        assert listing.status_code == 200
        data = listing.json()["data"]
        assert [t["type"] for t in data] == [
            "TRANSFER_IN",
            "TRANSFER_OUT",
            "ADJUSTMENT",
        ]

        only_out = api_client.get(
            "/api/v1/inventory/transactions",
            params={"type": "TRANSFER_OUT"},
            headers=ctx["headers"],
        )
        assert [t["type"] for t in only_out.json()["data"]] == ["TRANSFER_OUT"]

        by_product = api_client.get(
            "/api/v1/inventory/transactions",
            params={"product_id": ctx["product"]["id"]},
            headers=ctx["headers"],
        )
        assert by_product.json()["data"]

        for_entry = api_client.get(
            "/api/v1/inventory/transactions",
            params={"warehouse_id": ctx["warehouse_b"]["id"]},
            headers=ctx["headers"],
        )
        assert [t["type"] for t in for_entry.json()["data"]] == ["TRANSFER_IN"]

        for_exit = api_client.get(
            "/api/v1/inventory/transactions",
            params={"warehouse_id": ctx["warehouse_a"]["id"]},
            headers=ctx["headers"],
        )
        assert [t["type"] for t in for_exit.json()["data"]] == [
            "TRANSFER_OUT",
            "ADJUSTMENT",
        ]

    @pytest.mark.db
    def test_append_only_transactions_never_mutated(self, api_client, seed, catalog, session_factory):
        ctx = _setup(api_client, seed, catalog)
        _adjust(api_client, ctx["headers"], ctx["product"]["id"], ctx["warehouse_a"]["id"], 7)
        with session_factory() as db:
            first = db.execute(select(InventoryTransaction)).scalar_one()
            original_qty = first.quantity
            original_type = first.type
        # Two more mutations must append, never touch the first row.
        _adjust(api_client, ctx["headers"], ctx["product"]["id"], ctx["warehouse_a"]["id"], -3)
        _adjust(api_client, ctx["headers"], ctx["product"]["id"], ctx["warehouse_a"]["id"], 2)
        with session_factory() as db:
            rows = db.execute(
                select(InventoryTransaction).order_by(InventoryTransaction.id)
            ).scalars().all()
            assert [t.type for t in rows] == [
                InventoryTransactionType.ADJUSTMENT,
                InventoryTransactionType.ADJUSTMENT,
                InventoryTransactionType.ADJUSTMENT,
            ]
            assert rows[0].quantity == original_qty and rows[0].type == original_type

    @pytest.mark.db
    def test_low_stock_alert_created_and_resolved(self, api_client, seed, catalog, session_factory):
        ctx = _setup(api_client, seed, catalog, threshold=10)
        _adjust(api_client, ctx["headers"], ctx["product"]["id"], ctx["warehouse_a"]["id"], 5)
        with session_factory() as db:
            active = db.execute(
                select(Alert).where(Alert.entity_id == ctx["product"]["id"])
            ).scalars().all()
            assert len([a for a in active if not a.is_resolved]) == 1

        _adjust(api_client, ctx["headers"], ctx["product"]["id"], ctx["warehouse_a"]["id"], 20)
        with session_factory() as db:
            alerts = db.execute(
                select(Alert).where(Alert.entity_id == ctx["product"]["id"])
            ).scalars().all()
            assert alerts
            assert all(a.is_resolved for a in alerts)


class TestInventoryReads:
    @pytest.mark.db
    def test_list_and_get_with_details(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog)
        _adjust(api_client, ctx["headers"], ctx["product"]["id"], ctx["warehouse_a"]["id"], 40)

        listing = api_client.get(
            "/api/v1/inventory",
            params={"warehouse_id": ctx["warehouse_a"]["id"]},
            headers=ctx["headers"],
        )
        assert listing.status_code == 200
        row = listing.json()["data"][0]
        assert row["product"]["sku"] == "SKU-INV"
        assert row["warehouse"]["code"] == "WH-A"
        assert float(row["quantity"]) == 40
        assert row["below_threshold"] is False

        single = api_client.get(f"/api/v1/inventory/{row['id']}", headers=ctx["headers"])
        assert single.json()["data"]["id"] == row["id"]

    @pytest.mark.db
    def test_below_threshold_filter(self, api_client, seed, catalog):
        ctx = _setup(api_client, seed, catalog, threshold=10)
        _adjust(api_client, ctx["headers"], ctx["product"]["id"], ctx["warehouse_a"]["id"], 4)
        _adjust(api_client, ctx["headers"], ctx["product"]["id"], ctx["warehouse_b"]["id"], 400)

        below = api_client.get(
            "/api/v1/inventory",
            params={"below_threshold": True},
            headers=ctx["headers"],
        )
        assert below.status_code == 200
        rows = below.json()["data"]
        assert len(rows) == 1
        assert rows[0]["below_threshold"] is True

        above = api_client.get(
            "/api/v1/inventory",
            params={"below_threshold": False},
            headers=ctx["headers"],
        )
        assert all(r["below_threshold"] is False for r in above.json()["data"])

    @pytest.mark.db
    def test_missing_inventory_404(self, api_client, seed):
        headers = _warehouse_manager_headers(api_client, seed)
        response = api_client.get("/api/v1/inventory/999999", headers=headers)
        assert response.status_code == 404