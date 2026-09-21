"use client";

import React, { useEffect, useState } from "react";
import StatusBadge from "@/components/common/StatusBadge";
import FeedbackAlert from "@/components/common/FeedbackAlert";
import { analyticsApi, alertsApi } from "@/lib/api";
import {
  AnalyticsOverview,
  InventoryAnalytics,
  ShipmentAnalytics,
  SupplierAnalytics,
  BottleneckAnalytics,
  Alert,
} from "@/types/api";
import Link from "next/link";
import {
  Boxes,
  ShoppingCart,
  Truck,
  AlertTriangle,
  Clock,
  Package,
  ArrowRight,
  TrendingUp,
} from "lucide-react";

interface AdminDashboardProps {
  title?: string;
  subtitle?: string;
}

// Full operational dashboard. Allowed callers (ADMIN, SUPPLY_CHAIN_MANAGER,
// ANALYST) all hold analytics:read + alerts:read on the backend, so every
// request below is authorized for each of them — no 403s by construction.
export default function AdminDashboard({
  title = "Operational Dashboard",
  subtitle = "Real-time operational KPIs computed live from the supply chain network",
}: AdminDashboardProps) {
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [inventoryAnalytics, setInventoryAnalytics] = useState<InventoryAnalytics | null>(null);
  const [shipmentAnalytics, setShipmentAnalytics] = useState<ShipmentAnalytics | null>(null);
  const [supplierAnalytics, setSupplierAnalytics] = useState<SupplierAnalytics | null>(null);
  const [bottlenecks, setBottlenecks] = useState<BottleneckAnalytics | null>(null);
  const [activeAlerts, setActiveAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDashboardData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [ov, inv, shp, sup, btn, alt] = await Promise.allSettled([
        analyticsApi.getOverview(),
        analyticsApi.getInventory(),
        analyticsApi.getShipments(),
        analyticsApi.getSuppliers(),
        analyticsApi.getBottlenecks(),
        alertsApi.list({ resolved: false, limit: 5 }),
      ]);

      if (ov.status === "fulfilled") setOverview(ov.value);
      if (inv.status === "fulfilled") setInventoryAnalytics(inv.value);
      if (shp.status === "fulfilled") setShipmentAnalytics(shp.value);
      if (sup.status === "fulfilled") setSupplierAnalytics(sup.value);
      if (btn.status === "fulfilled") setBottlenecks(btn.value);
      if (alt.status === "fulfilled") setActiveAlerts(alt.value.data || []);

      if (ov.status === "rejected") {
        setError(ov.reason?.message || "Failed to load dashboard data");
      }
    } catch (err: any) {
      setError(err.message || "An unexpected error occurred");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboardData();
  }, []);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">{title}</h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1">{subtitle}</p>
        </div>
        <button
          onClick={fetchDashboardData}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3.5 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 shadow-sm disabled:opacity-50"
        >
          <TrendingUp className="h-4 w-4 text-slate-500" />
          Refresh Analytics
        </button>
      </div>

      {error && <FeedbackAlert type="error" message={error} onDismiss={() => setError(null)} />}

      {/* Top KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500">Products</span>
            <Package className="h-4 w-4 text-indigo-500" />
          </div>
          <p className="mt-2 text-2xl font-bold text-slate-900">
            {loading ? "-" : overview?.product_count ?? 0}
          </p>
          <span className="text-[11px] text-slate-500">Active catalog items</span>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500">Total Stock</span>
            <Boxes className="h-4 w-4 text-blue-500" />
          </div>
          <p className="mt-2 text-2xl font-bold text-slate-900">
            {loading ? "-" : Number(overview?.total_stock ?? 0).toLocaleString()}
          </p>
          <span className="text-[11px] text-slate-500">Units across warehouses</span>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500">Low Stock</span>
            <AlertTriangle className="h-4 w-4 text-amber-500" />
          </div>
          <p
            className={`mt-2 text-2xl font-bold ${
              (overview?.low_stock_count ?? 0) > 0 ? "text-amber-600" : "text-slate-900"
            }`}
          >
            {loading ? "-" : overview?.low_stock_count ?? 0}
          </p>
          <span className="text-[11px] text-slate-500">Below reorder threshold</span>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500">Active Orders</span>
            <ShoppingCart className="h-4 w-4 text-sky-500" />
          </div>
          <p className="mt-2 text-2xl font-bold text-slate-900">
            {loading ? "-" : overview?.active_orders_count ?? 0}
          </p>
          <span className="text-[11px] text-slate-500">Placed / Confirmed</span>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500">In Transit</span>
            <Truck className="h-4 w-4 text-indigo-500" />
          </div>
          <p className="mt-2 text-2xl font-bold text-slate-900">
            {loading ? "-" : overview?.in_transit_shipments_count ?? 0}
          </p>
          <span className="text-[11px] text-slate-500">En route shipments</span>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500">Delayed</span>
            <Clock className="h-4 w-4 text-red-500" />
          </div>
          <p
            className={`mt-2 text-2xl font-bold ${
              (overview?.delayed_shipments_count ?? 0) > 0 ? "text-red-600" : "text-slate-900"
            }`}
          >
            {loading ? "-" : overview?.delayed_shipments_count ?? 0}
          </p>
          <span className="text-[11px] text-slate-500">Past expected delivery</span>
        </div>
      </div>

      {/* Active Alerts & Delivery Metrics */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Active Alerts Panel */}
        <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden flex flex-col">
          <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-amber-500" />
              <h2 className="text-sm font-semibold text-slate-900">Unresolved Alerts</h2>
            </div>
            <Link
              href="/alerts"
              className="inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:text-indigo-700"
            >
              View all alerts <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
          <div className="flex-1 p-4">
            {activeAlerts.length === 0 ? (
              <div className="flex h-36 flex-col items-center justify-center text-center">
                <p className="text-xs font-medium text-emerald-600">
                  All systems normal. No active alerts.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {activeAlerts.map((alert) => (
                  <div
                    key={alert.id}
                    className="flex items-start justify-between rounded-lg border border-slate-100 bg-slate-50 p-3"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <StatusBadge alertType={alert.type} size="sm" />
                        <StatusBadge severity={alert.severity} size="sm" />
                      </div>
                      <p className="text-xs text-slate-800 font-medium">{alert.message}</p>
                      <span className="text-[10px] text-slate-400">
                        Created {new Date(alert.created_at).toLocaleString()}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Shipment Performance Metrics */}
        <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden flex flex-col">
          <div className="border-b border-slate-100 px-6 py-4">
            <h2 className="text-sm font-semibold text-slate-900">Shipment Performance</h2>
          </div>
          <div className="p-6 grid grid-cols-2 gap-4 flex-1">
            <div className="rounded-lg bg-slate-50 p-4 border border-slate-100">
              <span className="text-xs text-slate-500">Delivered Shipments</span>
              <p className="mt-1 text-xl font-bold text-slate-900">
                {shipmentAnalytics?.delivered_count ?? 0}
              </p>
              <span className="text-[11px] text-emerald-600">
                {shipmentAnalytics?.on_time_count ?? 0} on time
              </span>
            </div>
            <div className="rounded-lg bg-slate-50 p-4 border border-slate-100">
              <span className="text-xs text-slate-500">Delayed Shipments</span>
              <p className="mt-1 text-xl font-bold text-red-600">
                {shipmentAnalytics?.delayed_count ?? 0}
              </p>
              <span className="text-[11px] text-slate-500">Historical & active</span>
            </div>
            <div className="rounded-lg bg-slate-50 p-4 border border-slate-100">
              <span className="text-xs text-slate-500">Avg Delivery Duration</span>
              <p className="mt-1 text-xl font-bold text-slate-900">
                {shipmentAnalytics?.avg_delivery_hours !== null &&
                shipmentAnalytics?.avg_delivery_hours !== undefined
                  ? `${shipmentAnalytics.avg_delivery_hours.toFixed(1)} hrs`
                  : "N/A"}
              </p>
            </div>
            <div className="rounded-lg bg-slate-50 p-4 border border-slate-100">
              <span className="text-xs text-slate-500">Avg Delay Hours</span>
              <p className="mt-1 text-xl font-bold text-amber-600">
                {shipmentAnalytics?.avg_delay_hours !== null &&
                shipmentAnalytics?.avg_delay_hours !== undefined
                  ? `${shipmentAnalytics.avg_delay_hours.toFixed(1)} hrs`
                  : "0.0 hrs"}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Bottlenecks Stage Timing Table */}
      <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
        <div className="border-b border-slate-100 px-6 py-4">
          <h2 className="text-sm font-semibold text-slate-900">Lifecycle Bottleneck Timing</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Computed duration metrics across shipment lifecycle transitions
          </p>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-left text-xs text-slate-600">
            <thead className="bg-slate-50 uppercase text-[10px] tracking-wider text-slate-500 font-semibold">
              <tr>
                <th className="px-6 py-3">Lifecycle Stage</th>
                <th className="px-6 py-3">Sample Count</th>
                <th className="px-6 py-3">Average Hours</th>
                <th className="px-6 py-3">Median (p50)</th>
                <th className="px-6 py-3">90th Percentile (p90)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white">
              {!bottlenecks?.stages || bottlenecks.stages.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-slate-500">
                    Insufficient lifecycle history to calculate stage bottlenecks.
                  </td>
                </tr>
              ) : (
                bottlenecks.stages.map((stage, idx) => (
                  <tr key={idx} className="hover:bg-slate-50">
                    <td className="px-6 py-3.5 font-medium text-slate-900">{stage.stage}</td>
                    <td className="px-6 py-3.5">{stage.count}</td>
                    <td className="px-6 py-3.5">
                      {stage.avg_hours !== null ? `${stage.avg_hours.toFixed(1)} h` : "-"}
                    </td>
                    <td className="px-6 py-3.5">
                      {stage.p50_hours !== null ? `${stage.p50_hours.toFixed(1)} h` : "-"}
                    </td>
                    <td className="px-6 py-3.5">
                      {stage.p90_hours !== null ? `${stage.p90_hours.toFixed(1)} h` : "-"}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Warehouse Inventory Distribution & Supplier Performance */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Inventory Distribution */}
        <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
          <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
            <h2 className="text-sm font-semibold text-slate-900">Stock by Warehouse</h2>
            <Link
              href="/inventory"
              className="text-xs font-medium text-indigo-600 hover:text-indigo-700"
            >
              Manage inventory →
            </Link>
          </div>
          <div className="p-6">
            {!inventoryAnalytics?.by_warehouse || inventoryAnalytics.by_warehouse.length === 0 ? (
              <p className="text-xs text-slate-500 text-center py-6">No inventory data</p>
            ) : (
              <div className="space-y-4">
                {inventoryAnalytics.by_warehouse.map((wh) => (
                  <div key={wh.warehouse_id} className="space-y-1">
                    <div className="flex items-center justify-between text-xs font-medium">
                      <span className="text-slate-800">{wh.warehouse_name}</span>
                      <span className="text-slate-500 font-semibold">
                        {Number(wh.total_quantity).toLocaleString()} units
                      </span>
                    </div>
                    <div className="h-2 w-full rounded-full bg-slate-100 overflow-hidden">
                      <div
                        className="h-full bg-indigo-500 rounded-full"
                        style={{
                          width: `${Math.min(
                            100,
                            ((Number(wh.total_quantity) || 0) /
                              (inventoryAnalytics.total_inventory || 1)) *
                              100
                          )}%`,
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Supplier Performance */}
        <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
          <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
            <h2 className="text-sm font-semibold text-slate-900">Supplier Activity</h2>
            <Link
              href="/suppliers"
              className="text-xs font-medium text-indigo-600 hover:text-indigo-700"
            >
              View suppliers →
            </Link>
          </div>
          <div className="p-6">
            {!supplierAnalytics?.suppliers || supplierAnalytics.suppliers.length === 0 ? (
              <p className="text-xs text-slate-500 text-center py-6">No suppliers registered</p>
            ) : (
              <div className="divide-y divide-slate-100">
                {supplierAnalytics.suppliers.map((sup) => (
                  <div key={sup.supplier_id} className="py-2.5 flex items-center justify-between text-xs">
                    <div>
                      <p className="font-medium text-slate-900">{sup.supplier_name}</p>
                      <p className="text-[11px] text-slate-400">Code: {sup.supplier_code}</p>
                    </div>
                    <div className="text-right">
                      <span className="font-semibold text-slate-700">
                        {sup.total_orders ?? 0} orders
                      </span>
                      {sup.performance_score !== null && sup.performance_score !== undefined && (
                        <p className="text-[11px] text-emerald-600 font-medium">
                          Score: {sup.performance_score}%
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
