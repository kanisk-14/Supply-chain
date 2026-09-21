"use client";

import React, { useEffect, useState } from "react";
import { alertsApi, inventoryApi, ordersApi, shipmentsApi, warehousesApi } from "@/lib/api";
import { Alert, InventoryItem, InventoryTransaction, Shipment, Warehouse } from "@/types/api";
import { Boxes, AlertTriangle, Truck, ShoppingCart, ArrowRight, Warehouse as WarehouseIcon, History, RefreshCw } from "lucide-react";
import Link from "next/link";
import StatusBadge from "@/components/common/StatusBadge";
import FeedbackAlert from "@/components/common/FeedbackAlert";

interface WarehouseManagerDashboardProps {
  warehouseId: number | null;
}

// Warehouse-scoped operational dashboard. Uses only endpoints the
// WAREHOUSE_MANAGER role is authorized for (warehouses / inventory /
// inventory-transactions / orders / shipments / alerts — all warehouse-scoped
// server-side). Deliberately makes NO analyticsApi calls: the backend denies
// analytics:read to this role, so those would only produce 403s.
export default function WarehouseManagerDashboard({ warehouseId }: WarehouseManagerDashboardProps) {
  const [warehouse, setWarehouse] = useState<Warehouse | null>(null);
  const [warehouseInventory, setWarehouseInventory] = useState<InventoryItem[]>([]);
  const [lowStockItems, setLowStockItems] = useState<InventoryItem[]>([]);
  const [recentShipments, setRecentShipments] = useState<Shipment[]>([]);
  const [recentTransactions, setRecentTransactions] = useState<InventoryTransaction[]>([]);
  const [activeAlerts, setActiveAlerts] = useState<Alert[]>([]);
  const [orderCount, setOrderCount] = useState(0);
  const [inTransitCount, setInTransitCount] = useState(0);
  const [delayedCount, setDelayedCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDashboardData = async () => {
    if (warehouseId === null) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [wh, inv, low, shp, tx, alt, ord, transit, delayed] = await Promise.allSettled([
        warehousesApi.get(warehouseId),
        inventoryApi.list({ warehouse_id: warehouseId, limit: 10 }),
        inventoryApi.list({ warehouse_id: warehouseId, below_threshold: true, limit: 10 }),
        shipmentsApi.list({ limit: 5 }),
        inventoryApi.transactions({ warehouse_id: warehouseId, limit: 5 }),
        alertsApi.list({ resolved: false, limit: 5 }),
        ordersApi.list({ limit: 1 }),
        shipmentsApi.list({ status: "IN_TRANSIT", limit: 1 }),
        shipmentsApi.list({ is_delayed: true, limit: 1 }),
      ]);

      if (wh.status === "fulfilled") setWarehouse(wh.value);
      if (inv.status === "fulfilled") setWarehouseInventory(inv.value.data || []);
      if (low.status === "fulfilled") setLowStockItems(low.value.data || []);
      if (shp.status === "fulfilled") setRecentShipments(shp.value.data || []);
      if (tx.status === "fulfilled") setRecentTransactions(tx.value.data || []);
      if (alt.status === "fulfilled") setActiveAlerts(alt.value.data || []);
      if (ord.status === "fulfilled") setOrderCount(ord.value.meta?.total ?? 0);
      if (transit.status === "fulfilled") setInTransitCount(transit.value.meta?.total ?? 0);
      if (delayed.status === "fulfilled") setDelayedCount(delayed.value.meta?.total ?? 0);

      const failures = [wh, inv, low, shp, tx, alt, ord, transit, delayed].filter(
        (r) => r.status === "rejected"
      );
      if (failures.length > 0) {
        setError("Failed to load some dashboard data");
      }
    } catch (err: any) {
      setError(err.message || "An unexpected error occurred");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboardData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [warehouseId]);

  if (warehouseId === null) {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-6 text-center">
        <p className="text-sm font-semibold text-amber-800">No warehouse assigned</p>
        <p className="mt-1 text-xs text-amber-700">
          Your account is not assigned to a warehouse yet. Contact an administrator.
        </p>
      </div>
    );
  }

  const totalUnits = warehouseInventory.reduce((sum, item) => sum + Number(item.quantity), 0);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <WarehouseIcon className="h-5 w-5 text-indigo-600" />
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">
              Warehouse Dashboard
            </h1>
          </div>
          <p className="text-xs sm:text-sm text-slate-500">
            {warehouse ? `${warehouse.name} (${warehouse.code})` : `Warehouse #${warehouseId}`} —
            Operational metrics and inventory status
          </p>
        </div>
        <button
          onClick={fetchDashboardData}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3.5 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 shadow-sm disabled:opacity-50"
        >
          <RefreshCw className="h-4 w-4 text-slate-500" />
          Refresh
        </button>
      </div>

      {error && <FeedbackAlert type="error" message={error} onDismiss={() => setError(null)} />}

      {/* Top KPI Cards - Warehouse Scoped */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500">Warehouse Stock</span>
            <Boxes className="h-4 w-4 text-blue-500" />
          </div>
          <p className="mt-2 text-2xl font-bold text-slate-900">
            {loading ? "-" : totalUnits.toLocaleString()}
          </p>
          <span className="text-[11px] text-slate-500">Units in this warehouse</span>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500">Low Stock Items</span>
            <AlertTriangle className="h-4 w-4 text-amber-500" />
          </div>
          <p className={`mt-2 text-2xl font-bold ${lowStockItems.length > 0 ? "text-amber-600" : "text-slate-900"}`}>
            {loading ? "-" : lowStockItems.length}
          </p>
          <span className="text-[11px] text-slate-500">Below reorder threshold</span>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500">Relevant Orders</span>
            <ShoppingCart className="h-4 w-4 text-sky-500" />
          </div>
          <p className="mt-2 text-2xl font-bold text-slate-900">
            {loading ? "-" : orderCount}
          </p>
          <span className="text-[11px] text-slate-500">Touching this warehouse</span>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500">In-Transit Shipments</span>
            <Truck className="h-4 w-4 text-indigo-500" />
          </div>
          <p className="mt-2 text-2xl font-bold text-slate-900">
            {loading ? "-" : inTransitCount}
          </p>
          <span className="text-[11px] text-slate-500">From this warehouse</span>
        </div>
      </div>

      {/* Active Alerts & Low Stock */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Active Alerts Panel */}
        <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden flex flex-col">
          <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-amber-500" />
              <h2 className="text-sm font-semibold text-slate-900">Warehouse Alerts</h2>
            </div>
            <Link
              href="/alerts"
              className="inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:text-indigo-700"
            >
              View all <ArrowRight className="h-3 w-3" />
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
                  <div key={alert.id} className="flex items-start justify-between rounded-lg border border-slate-100 bg-slate-50 p-3">
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

        {/* Low Stock Focus */}
        <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
          <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
            <h2 className="text-sm font-semibold text-slate-900">
              Low Stock Items (Warehouse #{warehouseId})
            </h2>
            <Link
              href="/inventory"
              className="text-xs font-medium text-indigo-600 hover:text-indigo-700"
            >
              View all inventory →
            </Link>
          </div>
          <div className="p-6">
            {lowStockItems.length === 0 ? (
              <p className="text-xs text-emerald-600 text-center py-6">
                No low stock items. All products above reorder threshold.
              </p>
            ) : (
              <div className="space-y-3 max-h-64 overflow-y-auto">
                {lowStockItems.slice(0, 10).map((item) => {
                  const prod = item.product;
                  const threshold = Number(prod?.reorder_threshold ?? 0);
                  const qty = Number(item.quantity);
                  return (
                    <div key={item.id} className="flex items-center justify-between rounded-lg border border-amber-100 bg-amber-50 p-3">
                      <div className="space-y-1">
                        <p className="text-xs font-medium text-slate-900">{prod?.name || `Product #${item.product_id}`}</p>
                        <p className="text-[10px] text-slate-500 font-mono">SKU: {prod?.sku || "N/A"}</p>
                      </div>
                      <div className="text-right">
                        <p className="text-xs font-bold text-amber-600">{qty.toLocaleString()} {prod?.unit || "units"}</p>
                        <p className="text-[10px] text-slate-500">Threshold: {threshold.toLocaleString()}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Recent Shipments & Stock Movements */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Shipments */}
        <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden flex flex-col">
          <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
            <div className="flex items-center gap-2">
              <Truck className="h-5 w-5 text-indigo-500" />
              <h2 className="text-sm font-semibold text-slate-900">Recent Shipments</h2>
            </div>
            <Link
              href="/shipments"
              className="inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:text-indigo-700"
            >
              View all <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
          <div className="flex-1 p-4">
            {delayedCount > 0 && (
              <p className="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs font-medium text-red-700">
                {delayedCount} delayed shipment{delayedCount === 1 ? "" : "s"} need attention.
              </p>
            )}
            {recentShipments.length === 0 ? (
              <p className="text-xs text-slate-500 text-center py-6">No shipments found.</p>
            ) : (
              <div className="space-y-3">
                {recentShipments.map((s) => (
                  <div key={s.id} className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 p-3">
                    <div>
                      <Link
                        href={`/shipments/${s.id}`}
                        className="text-xs font-mono font-semibold text-indigo-600 hover:underline"
                      >
                        {s.shipment_number}
                      </Link>
                      <p className="text-[10px] text-slate-400 mt-0.5">
                        Order #{s.order_id} · {new Date(s.created_at).toLocaleString()}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <StatusBadge status={s.status} size="sm" />
                      {s.is_delayed && <StatusBadge isDelayed={true} size="sm" />}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Recent Stock Movements */}
        <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
          <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
            <div className="flex items-center gap-2">
              <History className="h-5 w-5 text-slate-500" />
              <h2 className="text-sm font-semibold text-slate-900">Recent Stock Movements</h2>
            </div>
            <Link href="/inventory" className="text-xs font-medium text-indigo-600 hover:text-indigo-700">
              View inventory →
            </Link>
          </div>
          <div className="p-4">
            {recentTransactions.length === 0 ? (
              <p className="text-xs text-slate-500 text-center py-6">No recent movements.</p>
            ) : (
              <div className="space-y-3">
                {recentTransactions.map((tx) => {
                  const num = Number(tx.delta);
                  return (
                    <div key={tx.id} className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 p-3">
                      <div>
                        <p className="text-xs font-medium text-slate-800">
                          {tx.product?.name || `Product #${tx.product_id}`}
                        </p>
                        <p className="text-[10px] text-slate-400 mt-0.5">
                          {tx.type.replace(/_/g, " ")} · {new Date(tx.created_at).toLocaleString()}
                        </p>
                      </div>
                      <span className={`font-mono text-xs font-semibold ${num >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                        {num > 0 ? `+${num}` : num}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Operational Metrics */}
      <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
        <div className="border-b border-slate-100 px-6 py-4">
          <h2 className="text-sm font-semibold text-slate-900">Warehouse Operational Metrics</h2>
          <p className="text-xs text-slate-500 mt-0.5">Key indicators for warehouse #{warehouseId} operations</p>
        </div>
        <div className="p-6 grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="rounded-lg bg-slate-50 p-4 border border-slate-100">
            <span className="text-xs text-slate-500">Total SKUs</span>
            <p className="mt-1 text-xl font-bold text-slate-900">{warehouseInventory.length}</p>
          </div>
          <div className="rounded-lg bg-slate-50 p-4 border border-slate-100">
            <span className="text-xs text-slate-500">Low Stock Count</span>
            <p className="mt-1 text-xl font-bold text-amber-600">{lowStockItems.length}</p>
          </div>
          <div className="rounded-lg bg-slate-50 p-4 border border-slate-100">
            <span className="text-xs text-slate-500">Total Units</span>
            <p className="mt-1 text-xl font-bold text-slate-900">
              {totalUnits.toLocaleString()}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
