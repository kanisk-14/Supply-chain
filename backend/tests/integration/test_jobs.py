"""Scheduled SHIPMENT_OVERDUE evaluator tests.

``run_overdue_check`` must reconcile only the affected shipments: create alerts
for time-overdue candidates, stay idempotent on repeat runs, and sweep stale
open alerts when the shipment recovered outside the reactive path (e.g. a direct
status change). ``run_loop`` layers the polling loop on top of it.
"""

import datetime as dt
import threading
from datetime import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.jobs.scheduler import run_loop, run_once
from app.jobs.service import run_overdue_check
from app.modules.alerts.models import Alert, AlertType
from app.modules.orders.models import Order, OrderItem
from app.modules.shipments.models import (
    Shipment,
    ShipmentStatus,
    ShipmentStatusHistory,
)
from app.modules.users.models import UserRole
from app.state_machines.order import OrderStatus

from tests.conftest import login


def _seed_overdue(session_factory, user_id, *, delivered=False):
    """One order + one PACKED shipment whose expected date is in the past."""
    now = datetime.utcnow()
    return _seed_with_expected(
        session_factory, user_id, now - dt.timedelta(days=1), delivered=delivered
    )


def _seed_with_expected(session_factory, user_id, expected_at, *, delivered=False):
    """One order + one shipment with an explicit ``expected_delivery_at``."""
    with session_factory() as db:
        from app.modules.products.models import Product
        from app.modules.suppliers.models import Supplier

        supplier = Supplier(name="Job Supplier", code="SUP-JOB")
        product = Product(
            supplier=supplier, sku="SKU-JOB", name="Bolt", unit="unit",
            reorder_threshold=Decimal("5"),
        )
        db.add_all([supplier, product])
        db.flush()
        order = Order(
            order_number="ORD-JOB-1",
            status=OrderStatus.CONFIRMED,
            created_by=user_id,
        )
        db.add(order)
        db.flush()
        db.add(OrderItem(order_id=order.id, product_id=product.id, quantity=Decimal("1")))
        shipment = Shipment(
            shipment_number="SHP-JOB-1",
            order_id=order.id,
            status=ShipmentStatus.DELIVERED if delivered else ShipmentStatus.PACKED,
            created_by=user_id,
            expected_delivery_at=expected_at,
            actual_delivery_at=datetime.utcnow() if delivered else None,
        )
        db.add(shipment)
        db.commit()
        return {"order_id": order.id, "shipment_id": shipment.id}


def _flip_status_directly(session_factory, shipment_id, status):
    with session_factory() as db:
        row = db.execute(
            select(Shipment).where(Shipment.id == shipment_id)
        ).scalar_one()
        row.status = status
        db.commit()


def _alert_count(session_factory):
    with session_factory() as db:
        return int(
            db.execute(
                select(func.count()).select_from(Alert).where(
                    Alert.type == AlertType.SHIPMENT_OVERDUE
                )
            ).scalar_one()
        )


def _open_alert_count(session_factory):
    with session_factory() as db:
        return int(
            db.execute(
                select(func.count()).select_from(Alert).where(
                    Alert.type == AlertType.SHIPMENT_OVERDUE,
                    Alert.is_resolved.is_(False),
                )
            ).scalar_one()
        )


class TestRunOverdueCheck:
    @pytest.mark.db
    def test_creates_alert_for_time_overdue_shipment(self, session_factory, seed):
        actor = seed.user("jobs@overdue.com", role=UserRole.ANALYST)
        _seed_overdue(session_factory, actor["id"])

        with session_factory() as db:
            report = run_overdue_check(db)

        assert report["created"] == 1
        assert report["resolved"] == 0
        assert report["checked"] >= 1
        assert _alert_count(session_factory) == 1
        assert _open_alert_count(session_factory) == 1

    @pytest.mark.db
    def test_is_idempotent(self, session_factory, seed):
        actor = seed.user("jobs@idempotent.com", role=UserRole.ANALYST)
        _seed_overdue(session_factory, actor["id"])

        with session_factory() as db:
            run_overdue_check(db)
        with session_factory() as db:
            second = run_overdue_check(db)

        assert second["created"] == 0
        assert second["resolved"] == 0
        assert _alert_count(session_factory) == 1
        assert _open_alert_count(session_factory) == 1

    @pytest.mark.db
    def test_resolves_stale_alert_after_direct_delivery(self, session_factory, seed):
        actor = seed.user("jobs@sweep.com", role=UserRole.ANALYST)
        _seed_overdue(session_factory, actor["id"])

        with session_factory() as db:
            run_overdue_check(db)
        assert _open_alert_count(session_factory) == 1

        # Delivery happened outside the reactive path (direct status write).
        _flip_status_directly(session_factory, 1, ShipmentStatus.DELIVERED)

        with session_factory() as db:
            report = run_overdue_check(db)

        assert report["resolved"] == 1
        assert report["created"] == 0
        assert _open_alert_count(session_factory) == 0
        assert _alert_count(session_factory) == 1  # resolved row kept

    @pytest.mark.db
    def test_delivered_shipment_with_past_expected_never_creates_alert(
        self, session_factory, seed
    ):
        actor = seed.user("jobs@delivered.com", role=UserRole.ANALYST)
        _seed_overdue(session_factory, actor["id"], delivered=True)

        with session_factory() as db:
            report = run_overdue_check(db)

        assert report["created"] == 0
        assert _alert_count(session_factory) == 0

    @pytest.mark.db
    def test_strict_boundary_expected_equals_now_is_not_overdue(
        self, session_factory, seed, monkeypatch
    ):
        """Overdue is ``expected_delivery_at < now`` (strict): at the exact
        instant the shipment is not yet late."""
        actor = seed.user("jobs@boundary.com", role=UserRole.ANALYST)
        reference = datetime(2026, 3, 1, 9, 0, 0, 0)
        _seed_with_expected(
            session_factory, actor["id"], reference
        )

        monkeypatch.setattr("app.jobs.service.utcnow", lambda: reference)
        with session_factory() as db:
            report = run_overdue_check(db)
        assert report["created"] == 0
        assert _open_alert_count(session_factory) == 0

        # One microsecond later the same shipment is overdue.
        monkeypatch.setattr(
            "app.jobs.service.utcnow",
            lambda: reference + dt.timedelta(microseconds=1),
        )
        with session_factory() as db:
            report = run_overdue_check(db)
        assert report["created"] == 1
        assert _open_alert_count(session_factory) == 1

    @pytest.mark.db
    def test_stale_alert_resolves_when_shipment_row_is_deleted(
        self, session_factory, seed
    ):
        """An open alert pointing at a removed shipment must not linger: the
        sweep resolves it instead of crashing on a missing reference."""
        actor = seed.user("jobs@missing.com", role=UserRole.ANALYST)
        ids = _seed_overdue(session_factory, actor["id"])

        with session_factory() as db:
            run_overdue_check(db)
        assert _open_alert_count(session_factory) == 1

        with session_factory() as db:
            db.execute(
                delete(ShipmentStatusHistory).where(
                    ShipmentStatusHistory.shipment_id == ids["shipment_id"]
                )
            )
            db.execute(
                delete(Shipment).where(Shipment.id == ids["shipment_id"])
            )
            db.commit()

        with session_factory() as db:
            report = run_overdue_check(db)

        assert report["resolved"] == 1
        assert report["created"] == 0
        assert _alert_count(session_factory) == 1  # resolved history row kept
        assert _open_alert_count(session_factory) == 0


class TestRunOnceAndLoop:
    @pytest.mark.db
    def test_run_once_uses_session_factory(self, session_factory, seed):
        actor = seed.user("jobs@once.com", role=UserRole.ANALYST)
        _seed_overdue(session_factory, actor["id"])

        report = run_once(session_factory)

        assert report["created"] == 1
        assert _open_alert_count(session_factory) == 1

    @pytest.mark.db
    def test_run_loop_stops_via_event(self, session_factory, seed):
        actor = seed.user("jobs@loop.com", role=UserRole.ANALYST)
        _seed_overdue(session_factory, actor["id"])

        stop_event = threading.Event()
        reports = []

        def on_tick(report):
            reports.append(report)
            if len(reports) >= 2:
                stop_event.set()

        thread = threading.Thread(
            target=run_loop,
            kwargs={
                "interval_seconds": 0.05,
                "session_factory": session_factory,
                "stop_event": stop_event,
                "on_tick": on_tick,
            },
            daemon=True,
        )
        thread.start()
        thread.join(timeout=10)

        assert thread.is_alive() is False
        assert len(reports) >= 2
        # The startup tick reports the newly created overdue alert.
        assert reports[0]["created"] == 1
        assert reports[-1]["created"] == 0  # subsequent cycles stay idempotent
        assert _open_alert_count(session_factory) == 1


class TestSchedulerLifecycle:
    def test_lifespan_starts_and_stops_scheduler_when_enabled(self, monkeypatch):
        import app.main as main_module

        started = []
        joined = []

        class FakeThread:
            def __init__(self, stop_event):
                self.stop_event = stop_event

            def join(self, timeout=None):
                joined.append((self, timeout, self.stop_event.is_set()))

            def is_alive(self):
                return False

        def fake_thread(stop_event):
            started.append(stop_event)
            return FakeThread(stop_event)

        monkeypatch.setattr(main_module.settings, "SCHEDULER_ENABLED", True)
        monkeypatch.setattr(main_module, "_scheduler_thread", fake_thread)

        app = main_module.create_app()
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200
            assert len(started) == 1

        # Lifespan teardown sets the stop event and joins the thread.
        assert len(started) == 1
        assert len(joined) == 1
        fake, timeout, stop_set_before_join = joined[0]
        assert fake.stop_event is started[0]
        assert timeout == 10
        assert stop_set_before_join is True

    def test_lifespan_does_not_start_scheduler_when_disabled(self, monkeypatch):
        import app.main as main_module

        started = []

        monkeypatch.setattr(main_module.settings, "SCHEDULER_ENABLED", False)
        monkeypatch.setattr(
            main_module, "_scheduler_thread", lambda stop_event: started.append(stop_event)
        )

        app = main_module.create_app()
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200

        assert started == []