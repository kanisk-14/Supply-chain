"""Analytics data access layer.

Everything here is a pure SQL aggregation over the operational tables. No KPI is
stored anywhere — analytics are computed live at read time. Loading entire tables
into Python is deliberately avoided for the normal KPIs; the only Python-side
work in the service is formatting/rounding numbers.

Bottleneck detection reads ``shipment_status_history`` with a LAG window to pair
each transition with its predecessor, and ``audit_logs`` (ORDER_CONFIRMED) for
the order side of the confirmation→packed segment. MySQL 8.0+ window functions
keep these fully aggregated inside the database.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Select,
    and_,
    case,
    func,
    literal_column,
    or_,
    select,
)
from sqlalchemy.orm import Session

from app.modules.audit_logs.models import AuditLog
from app.modules.inventory.models import Inventory, InventoryTransaction
from app.modules.orders.models import Order, OrderItem
from app.modules.products.models import Product
from app.modules.shipments.models import Shipment, ShipmentStatusHistory
from app.modules.suppliers.models import Supplier
from app.modules.warehouses.models import Warehouse
from app.state_machines.order import OrderStatus
from app.state_machines.shipment import ShipmentStatus

STAGE_PACKED_TO_TRANSIT = (ShipmentStatus.PACKED, ShipmentStatus.IN_TRANSIT)
STAGE_TRANSIT_TO_DELIVERED = (ShipmentStatus.IN_TRANSIT, ShipmentStatus.DELIVERED)

PERIODS = {"day", "week", "month"}


def _bucket_expr(column, period: str):
    """SQL expression producing a sortable bucket label for a timestamp column."""
    if period == "day":
        return func.date(column)
    if period == "week":
        # ISO week, e.g. "2026-W38".
        return func.date_format(column, "%x-W%v")
    return func.date_format(column, "%Y-%m")


def _seconds_timediff(earlier, later):
    """TIMESTAMPDIFF(SECOND, earlier, later) — MySQL 8 window-friendly."""
    return func.timestampdiff(literal_column("SECOND"), earlier, later)


def _int_or_none(value) -> int | None:
    return None if value is None else int(value)


def _decimal_or_none(value) -> Decimal | None:
    return None if value is None else Decimal(value)


class AnalyticsRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ---- overview ----

    def overview(self, now: datetime) -> dict:
        low_stock_join = Inventory.product_id == Product.id
        low_stock_cond = Inventory.quantity < Product.reorder_threshold
        delayed_cond = and_(
            Shipment.expected_delivery_at.isnot(None),
            Shipment.expected_delivery_at < now,
            Shipment.status != ShipmentStatus.DELIVERED,
        )
        queries = {
            "total_products": select(func.count(Product.id)),
            "total_inventory_units": select(
                func.coalesce(func.sum(Inventory.quantity), 0)
            ),
            "low_stock_rows": select(func.count(Inventory.id))
            .join(Product, low_stock_join)
            .where(low_stock_cond),
            "low_stock_items": select(func.count(func.distinct(Inventory.product_id)))
            .join(Product, low_stock_join)
            .where(low_stock_cond),
            "active_orders": select(func.count(Order.id)).where(
                Order.status.in_((OrderStatus.PLACED, OrderStatus.CONFIRMED))
            ),
            "shipments_in_transit": select(func.count(Shipment.id)).where(
                Shipment.status == ShipmentStatus.IN_TRANSIT
            ),
            "delayed_shipments": select(func.count(Shipment.id)).where(delayed_cond),
        }
        return {
            name: int(self.db.execute(stmt).scalar_one())
            for name, stmt in queries.items()
        }

    # ---- inventory ----

    def inventory_totals(self) -> tuple[int, int, Decimal]:
        """(low_stock_rows, low_stock_items, total_stock) in one round trip."""
        low_stock_join = Inventory.product_id == Product.id
        low_stock_cond = Inventory.quantity < Product.reorder_threshold
        stmt = (
            select(
                func.coalesce(
                    func.sum(case((low_stock_cond, 1), else_=literal_column("0"))),
                    0,
                ),
                func.count(
                    func.distinct(
                        case(
                            (low_stock_cond, Inventory.product_id),
                            else_=literal_column("NULL"),
                        )
                    )
                ),
                func.coalesce(func.sum(Inventory.quantity), 0),
            )
            .select_from(Inventory)
            .join(Product, low_stock_join)
        )
        row = self.db.execute(stmt).one()
        return int(row[0]), int(row[1]), Decimal(row[2])

    def stock_by_warehouse(self) -> list[tuple]:
        stmt = (
            select(
                Warehouse.id,
                Warehouse.code,
                Warehouse.name,
                func.coalesce(func.sum(Inventory.quantity), 0).label("total"),
            )
            .join(Inventory, Inventory.warehouse_id == Warehouse.id)
            .group_by(Warehouse.id, Warehouse.code, Warehouse.name)
            .order_by(Warehouse.id)
        )
        return [tuple(r) for r in self.db.execute(stmt)]

    def stock_by_product(self) -> list[tuple]:
        stmt = (
            select(
                Product.id,
                Product.sku,
                Product.name,
                func.coalesce(func.sum(Inventory.quantity), 0).label("total"),
            )
            .join(Inventory, Inventory.product_id == Product.id)
            .group_by(Product.id, Product.sku, Product.name)
            .order_by(Product.id)
        )
        return [tuple(r) for r in self.db.execute(stmt)]

    def movement_trends(
        self, *, start: datetime, end: datetime, period: str
    ) -> list[tuple]:
        qty = InventoryTransaction.quantity
        bucket = _bucket_expr(InventoryTransaction.created_at, period)
        stmt = (
            select(
                bucket.label("bucket"),
                func.coalesce(
                    func.sum(case((qty > 0, qty), else_=literal_column("0"))), 0
                ).label("stock_in"),
                func.coalesce(
                    func.sum(case((qty < 0, -qty), else_=literal_column("0"))), 0
                ).label("stock_out"),
                func.coalesce(func.sum(qty), 0).label("net_movement"),
            )
            .where(
                and_(
                    InventoryTransaction.created_at >= start,
                    InventoryTransaction.created_at <= end,
                )
            )
            .group_by(bucket)
            .order_by(bucket)
        )
        return [tuple(r) for r in self.db.execute(stmt)]

    # ---- shipments ----

    def shipment_summary(self, now: datetime) -> dict:
        avg_delivery = select(
            func.avg(
                _seconds_timediff(Shipment.created_at, Shipment.actual_delivery_at)
            )
        ).where(Shipment.status == ShipmentStatus.DELIVERED)
        avg_delay = select(
            func.avg(
                case(
                    (
                        and_(
                            Shipment.expected_delivery_at.isnot(None),
                            Shipment.actual_delivery_at.isnot(None),
                            Shipment.actual_delivery_at > Shipment.expected_delivery_at,
                        ),
                        _seconds_timediff(
                            Shipment.expected_delivery_at, Shipment.actual_delivery_at
                        ),
                    ),
                    else_=literal_column("NULL"),
                )
            )
        ).where(Shipment.status == ShipmentStatus.DELIVERED)
        return {
            "delivered_shipments": int(
                self.db.execute(
                    select(func.count(Shipment.id)).where(
                        Shipment.status == ShipmentStatus.DELIVERED
                    )
                ).scalar_one()
            ),
            "delayed_shipments": int(
                self.db.execute(
                    select(func.count(Shipment.id)).where(
                        and_(
                            Shipment.expected_delivery_at.isnot(None),
                            Shipment.expected_delivery_at < now,
                            Shipment.status != ShipmentStatus.DELIVERED,
                        )
                    )
                ).scalar_one()
            ),
            "avg_delivery_seconds": _decimal_or_none(
                self.db.execute(avg_delivery).scalar_one()
            ),
            "avg_delay_seconds": _decimal_or_none(
                self.db.execute(avg_delay).scalar_one()
            ),
        }

    def delivery_performance(
        self, *, start: datetime, end: datetime, period: str
    ) -> list[tuple]:
        bucket = _bucket_expr(Shipment.actual_delivery_at, period)
        stmt = (
            select(
                bucket.label("bucket"),
                func.count(Shipment.id).label("delivered"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                or_(
                                    Shipment.expected_delivery_at.is_(None),
                                    Shipment.actual_delivery_at
                                    <= Shipment.expected_delivery_at,
                                ),
                                1,
                            ),
                            else_=literal_column("0"),
                        )
                    ),
                    0,
                ).label("on_time"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(
                                    Shipment.expected_delivery_at.isnot(None),
                                    Shipment.actual_delivery_at
                                    > Shipment.expected_delivery_at,
                                ),
                                1,
                            ),
                            else_=literal_column("0"),
                        )
                    ),
                    0,
                ).label("late"),
            )
            .where(
                and_(
                    Shipment.status == ShipmentStatus.DELIVERED,
                    Shipment.actual_delivery_at.isnot(None),
                    Shipment.actual_delivery_at >= start,
                    Shipment.actual_delivery_at <= end,
                )
            )
            .group_by(bucket)
            .order_by(bucket)
        )
        return [tuple(r) for r in self.db.execute(stmt)]

    # ---- suppliers ----

    def supplier_performance(self) -> list[tuple]:
        """Per-supplier aggregates computed solely from orders/shipments.

        A shipment belongs to an *order*, not to a line item, so shipment
        metrics are attributed to every supplier that contributes a product line
        to that order — but each distinct order/shipment is counted exactly
        once per supplier. Building ``(supplier, order)`` and ``(supplier,
        shipment)`` sets with ``DISTINCT`` before aggregating prevents a
        multi-line order (possibly covering several suppliers) from inflating
        counts or skewing the average delivery time. ``order_count`` counts an
        order once per supplier contributing a line to it;
        ``delivery_count``/``on_time_count`` count delivered shipments of those
        orders. No performance value is stored on the supplier row itself.
        """
        sh = Shipment
        # Distinct (supplier, order) pairs: order_count attributes an order to
        # every supplier with a line on it, once.
        supplier_orders = (
            select(
                Product.supplier_id.label("supplier_id"),
                OrderItem.order_id.label("order_id"),
            )
            .select_from(Product)
            .join(OrderItem, OrderItem.product_id == Product.id)
            .distinct()
            .subquery()
        )
        order_agg = (
            select(
                supplier_orders.c.supplier_id.label("supplier_id"),
                func.count(supplier_orders.c.order_id).label("order_count"),
            )
            .group_by(supplier_orders.c.supplier_id)
            .subquery()
        )
        # Distinct (supplier, shipment) rows: strip line-item multiplicity so a
        # single shipment is never replicated through two order lines.
        supplier_shipments = (
            select(
                Product.supplier_id.label("supplier_id"),
                sh.id.label("shipment_id"),
                sh.status.label("status"),
                sh.created_at.label("created_at"),
                sh.actual_delivery_at.label("actual_delivery_at"),
                sh.expected_delivery_at.label("expected_delivery_at"),
            )
            .select_from(Product)
            .join(OrderItem, OrderItem.product_id == Product.id)
            .join(Order, Order.id == OrderItem.order_id)
            .join(sh, sh.order_id == Order.id)
            .distinct()
            .subquery()
        )
        shipment_agg = (
            select(
                supplier_shipments.c.supplier_id.label("supplier_id"),
                func.count(
                    func.distinct(
                        case(
                            (
                                supplier_shipments.c.status
                                == ShipmentStatus.DELIVERED,
                                supplier_shipments.c.shipment_id,
                            ),
                            else_=literal_column("NULL"),
                        )
                    )
                ).label("delivery_count"),
                func.count(
                    func.distinct(
                        case(
                            (
                                and_(
                                    supplier_shipments.c.status
                                    == ShipmentStatus.DELIVERED,
                                    or_(
                                        supplier_shipments.c.expected_delivery_at.is_(
                                            None
                                        ),
                                        and_(
                                            supplier_shipments.c.actual_delivery_at.isnot(
                                                None
                                            ),
                                            supplier_shipments.c.actual_delivery_at
                                            <= supplier_shipments.c.expected_delivery_at,
                                        ),
                                    ),
                                ),
                                supplier_shipments.c.shipment_id,
                            ),
                            else_=literal_column("NULL"),
                        )
                    )
                ).label("on_time_count"),
                func.avg(
                    case(
                        (
                            supplier_shipments.c.status
                            == ShipmentStatus.DELIVERED,
                            _seconds_timediff(
                                supplier_shipments.c.created_at,
                                supplier_shipments.c.actual_delivery_at,
                            ),
                        ),
                        else_=literal_column("NULL"),
                    )
                ).label("avg_delivery_seconds"),
            )
            .group_by(supplier_shipments.c.supplier_id)
            .subquery()
        )
        stmt = (
            select(
                Supplier.id,
                Supplier.code,
                Supplier.name,
                func.coalesce(order_agg.c.order_count, 0).label("order_count"),
                func.coalesce(
                    shipment_agg.c.delivery_count, 0
                ).label("delivery_count"),
                func.coalesce(
                    shipment_agg.c.on_time_count, 0
                ).label("on_time_count"),
                shipment_agg.c.avg_delivery_seconds.label("avg_delivery_seconds"),
            )
            .select_from(Supplier)
            .join(Product, Product.supplier_id == Supplier.id)
            .outerjoin(order_agg, order_agg.c.supplier_id == Supplier.id)
            .outerjoin(shipment_agg, shipment_agg.c.supplier_id == Supplier.id)
            .group_by(
                Supplier.id,
                Supplier.code,
                Supplier.name,
                order_agg.c.order_count,
                shipment_agg.c.delivery_count,
                shipment_agg.c.on_time_count,
                shipment_agg.c.avg_delivery_seconds,
            )
            .order_by(Supplier.id)
        )
        return [tuple(r) for r in self.db.execute(stmt)]

    # ---- bottlenecks ----

    def _stage_duration_stmt(self, from_status, to_status) -> Select:
        """One row per consecutive ``from → to`` transition: elapsed seconds.

        Chronology is determined by ``changed_at`` first — history insertion
        order is used only as a deterministic tiebreaker for equal timestamps
        (the UNIQUE-per-shipment window would be ambiguous otherwise). The
        history row's ``id`` is never used to re-order across *different*
        timestamps: an out-of-order backfill may carry ids that do not match
        the real sequence of events.
        """
        hist = select(
            ShipmentStatusHistory.shipment_id.label("shipment_id"),
            ShipmentStatusHistory.status.label("status"),
            ShipmentStatusHistory.changed_at.label("changed_at"),
            func.lag(ShipmentStatusHistory.status)
            .over(
                partition_by=ShipmentStatusHistory.shipment_id,
                order_by=(
            ShipmentStatusHistory.changed_at,
            ShipmentStatusHistory.id,
        ),
            )
            .label("prev_status"),
            func.lag(ShipmentStatusHistory.changed_at)
            .over(
                partition_by=ShipmentStatusHistory.shipment_id,
                order_by=(
            ShipmentStatusHistory.changed_at,
            ShipmentStatusHistory.id,
        ),
            )
            .label("prev_changed_at"),
        ).subquery()
        return select(
            _seconds_timediff(hist.c.prev_changed_at, hist.c.changed_at).label("secs")
        ).where(
            hist.c.prev_changed_at.isnot(None),
            hist.c.prev_status == from_status.value,
            hist.c.status == to_status.value,
        )

    def stage_stats(self, from_status, to_status) -> tuple[int, Decimal | None, Decimal | None, Decimal | None]:
        """(count, avg_seconds, min_seconds, max_seconds) for a status pair."""
        secs = self._stage_duration_stmt(from_status, to_status).subquery()
        row = self.db.execute(
            select(
                func.count(secs.c.secs),
                func.avg(secs.c.secs),
                func.min(secs.c.secs),
                func.max(secs.c.secs),
            )
        ).one()
        return int(row[0]), _decimal_or_none(row[1]), _decimal_or_none(row[2]), _decimal_or_none(row[3])

    def stage_percentile(self, from_status, to_status, percentile: float) -> int | None:
        stmt = self._percentile_stmt(self._stage_duration_stmt(from_status, to_status), percentile)
        return _int_or_none(self.db.execute(stmt).scalar_one())

    def _confirm_to_packed_durations_stmt(self) -> Select:
        """Order confirmed (audit_logs) → first PACKED history row, in seconds."""
        confirmed = (
            select(
                AuditLog.entity_id.label("order_id"),
                AuditLog.created_at.label("confirmed_at"),
            )
            .where(
                AuditLog.action == "ORDER_CONFIRMED",
                AuditLog.entity_type == "order",
            )
            .subquery()
        )
        first_packed = (
            select(
                ShipmentStatusHistory.shipment_id.label("shipment_id"),
                ShipmentStatusHistory.changed_at.label("packed_at"),
                func.row_number()
                .over(
                    partition_by=ShipmentStatusHistory.shipment_id,
                    order_by=(
            ShipmentStatusHistory.changed_at,
            ShipmentStatusHistory.id,
        ),
                )
                .label("rn"),
            )
            .where(ShipmentStatusHistory.status == ShipmentStatus.PACKED)
            .subquery()
        )
        return (
            select(
                _seconds_timediff(
                    confirmed.c.confirmed_at, first_packed.c.packed_at
                ).label("secs")
            )
            .select_from(confirmed)
            .join(Shipment, Shipment.order_id == confirmed.c.order_id)
            .join(first_packed, first_packed.c.shipment_id == Shipment.id)
            .where(first_packed.c.rn == 1)
        )

    def confirm_to_packed_stats(self) -> tuple[int, Decimal | None, Decimal | None, Decimal | None]:
        """(count, avg_seconds, min_seconds, max_seconds) for confirm → packed."""
        secs = self._confirm_to_packed_durations_stmt().subquery()
        row = self.db.execute(
            select(
                func.count(secs.c.secs),
                func.avg(secs.c.secs),
                func.min(secs.c.secs),
                func.max(secs.c.secs),
            )
        ).one()
        return int(row[0]), _decimal_or_none(row[1]), _decimal_or_none(row[2]), _decimal_or_none(row[3])

    def confirm_to_packed_percentile(self, percentile: float) -> int | None:
        stmt = self._percentile_stmt(
            self._confirm_to_packed_durations_stmt(), percentile
        )
        return _int_or_none(self.db.execute(stmt).scalar_one())

    def _percentile_stmt(self, duration_stmt: Select, percentile: float) -> Select:
        """Largest duration whose PERCENT_RANK is <= ``percentile`` (0..1)."""
        durations = duration_stmt.subquery()
        ranked = (
            select(
                durations.c.secs.label("secs"),
                func.percent_rank().over(order_by=durations.c.secs).label("rank"),
            )
            .select_from(durations)
            .subquery()
        )
        return select(func.max(ranked.c.secs)).select_from(ranked).where(
            ranked.c.rank <= percentile
        )