"""Analytics service: live derived KPIs assembled from operational data.

Pure read-side aggregation. Nothing computed here is persisted; the repository
does all heavy lifting in SQL and this service only formats results into
JSON-safe units (hours, rates) and builds the bottleneck report.
"""

from __future__ import annotations

from datetime import date as _date
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.modules.analytics.repositories import (
    PERIODS,
    STAGE_PACKED_TO_TRANSIT,
    STAGE_TRANSIT_TO_DELIVERED,
    AnalyticsRepository,
)

HOURS_PER_SECOND = 3600.0


def _hours(value) -> float | None:
    return round(float(value) / HOURS_PER_SECOND, 4) if value is not None else None


def _stock(value) -> float:
    return round(float(value), 4)


def _rate(numerator, denominator) -> float:
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _bucket_label(value) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, _date):
        return value.isoformat()
    return str(value)


class AnalyticsService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = AnalyticsRepository(db)

    def _validate_period(self, period: str | None) -> str:
        period = period or "day"
        if period not in PERIODS:
            period = "day"
        return period

    def _window(self, period: str, days: int | None) -> tuple[datetime, datetime]:
        now = utcnow()
        span = max(1, min(int(days or 30), 365))
        start = now - timedelta(days=span)
        return start, now

    # ---- overview ----

    def overview(self) -> dict:
        return self.repo.overview(utcnow())

    # ---- inventory ----

    def inventory(self, *, period: str | None, days: int | None) -> dict:
        period = self._validate_period(period)
        start, end = self._window(period, days)
        low_stock_rows, low_stock_items, total_stock = self.repo.inventory_totals()
        trends = [
            {
                "period": _bucket_label(bucket),
                "stock_in": _stock(stock_in),
                "stock_out": _stock(stock_out),
                "net_movement": _stock(net),
            }
            for bucket, stock_in, stock_out, net in self.repo.movement_trends(
                start=start, end=end, period=period
            )
        ]
        return {
            "total_stock": _stock(total_stock),
            "low_stock_rows": low_stock_rows,
            "low_stock_items": low_stock_items,
            "stock_by_warehouse": [
                {
                    "warehouse_id": wh_id,
                    "warehouse_code": code,
                    "warehouse_name": name,
                    "total_stock": _stock(total),
                }
                for wh_id, code, name, total in self.repo.stock_by_warehouse()
            ],
            "stock_by_product": [
                {
                    "product_id": p_id,
                    "sku": sku,
                    "name": name,
                    "total_stock": _stock(total),
                }
                for p_id, sku, name, total in self.repo.stock_by_product()
            ],
            "movement_trends": trends,
            "trend_period": period,
        }

    # ---- shipments ----

    def shipments(self, *, period: str | None, days: int | None) -> dict:
        period = self._validate_period(period)
        start, end = self._window(period, days)
        summary = self.repo.shipment_summary(utcnow())
        performance = [
            {
                "period": _bucket_label(bucket),
                "delivered": delivered,
                "on_time": int(on_time),
                "late": int(late),
                "on_time_rate": _rate(on_time, delivered),
            }
            for bucket, delivered, on_time, late in self.repo.delivery_performance(
                start=start, end=end, period=period
            )
        ]
        return {
            "delivered_shipments": summary["delivered_shipments"],
            "delayed_shipments": summary["delayed_shipments"],
            "average_delivery_hours": _hours(summary["avg_delivery_seconds"]),
            "average_delay_hours": _hours(summary["avg_delay_seconds"]),
            "delivery_performance": performance,
            "performance_period": period,
        }

    # ---- suppliers ----

    def suppliers(self) -> dict:
        rows = self.repo.supplier_performance()
        return {
            "suppliers": [
                {
                    "supplier_id": s_id,
                    "code": code,
                    "name": name,
                    "order_count": order_count,
                    "delivery_count": delivery_count,
                    "on_time_delivery_rate": _rate(on_time_count, delivery_count),
                    "average_delivery_hours": _hours(avg_seconds),
                }
                for s_id, code, name, order_count, delivery_count, on_time_count, avg_seconds in rows
            ]
        }

    # ---- bottlenecks ----

    def bottlenecks(self) -> dict:
        segments = [
            self._segment(
                "order_confirmed_to_packed",
                self.repo.confirm_to_packed_stats,
                self.repo.confirm_to_packed_percentile,
            ),
            self._segment(
                "packed_to_in_transit",
                lambda: self.repo.stage_stats(*STAGE_PACKED_TO_TRANSIT),
                lambda p: self.repo.stage_percentile(*STAGE_PACKED_TO_TRANSIT, p),
            ),
            self._segment(
                "in_transit_to_delivered",
                lambda: self.repo.stage_stats(*STAGE_TRANSIT_TO_DELIVERED),
                lambda p: self.repo.stage_percentile(*STAGE_TRANSIT_TO_DELIVERED, p),
            ),
        ]
        return {"segments": segments, "unit": "hours"}

    def _segment(self, name, stats_fn, percentile_fn) -> dict:
        count, avg_seconds, min_seconds, max_seconds = stats_fn()
        return {
            "name": name,
            "count": count,
            "avg_hours": _hours(avg_seconds),
            "min_hours": _hours(min_seconds),
            "max_hours": _hours(max_seconds),
            "p50_hours": _hours(percentile_fn(0.5)),
            "p90_hours": _hours(percentile_fn(0.9)),
        }