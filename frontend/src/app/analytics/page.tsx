"use client";

import React, { useEffect, useState } from "react";
import ProtectedRoute from "@/components/auth/ProtectedRoute";
import AppLayout from "@/components/common/AppLayout";
import DataTable, { Column } from "@/components/common/DataTable";
import FeedbackAlert from "@/components/common/FeedbackAlert";
import { analyticsApi } from "@/lib/api";
import {
  AnalyticsOverview,
  InventoryAnalytics,
  ShipmentAnalytics,
  SupplierAnalytics,
  BottleneckAnalytics,
} from "@/types/api";
import { BarChart2, RefreshCw } from "lucide-react";

// Restricted to ADMIN / SUPPLY_CHAIN_MANAGER / ANALYST (see PAGE_PERMISSIONS).
// All three roles hold analytics:read, so every request here is authorized.
export default function AnalyticsPage() {
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [inventory, setInventory] = useState<InventoryAnalytics | null>(null);
  const [shipments, setShipments] = useState<ShipmentAnalytics | null>(null);
  const [suppliers, setSuppliers] = useState<SupplierAnalytics | null>(null);
  const [bottlenecks, setBottlenecks] = useState<BottleneckAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);

  const loadAnalytics = async () => {
    setLoading(true);
    setFeedback(null);
    try {
      const [ov, inv, shp, sup, btn] = await Promise.allSettled([
        analyticsApi.getOverview(),
        analyticsApi.getInventory(),
        analyticsApi.getShipments(),
        analyticsApi.getSuppliers(),
        analyticsApi.getBottlenecks(),
      ]);
      if (ov.status === "fulfilled") setOverview(ov.value);
      if (inv.status === "fulfilled") setInventory(inv.value);
      if (shp.status === "fulfilled") setShipments(shp.value);
      if (sup.status === "fulfilled") setSuppliers(sup.value);
      if (btn.status === "fulfilled") setBottlenecks(btn.value);
      const failed = [ov, inv, shp, sup, btn].filter((r) => r.status === "rejected");
      if (failed.length > 0) {
        setFeedback({ type: "error", message: "Failed to load some analytics sections." });
      }
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message || "Failed to load analytics" });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAnalytics();
  }, []);

  const bottleneckColumns: Column<{ id: string; stage: string; avg_hours: number | null; p50_hours: number | null; p90_hours: number | null; count: number }>[] = [
    { key: "stage", header: "Lifecycle Stage", render: (s) => <span className="font-medium text-slate-900">{s.stage}</span> },
    { key: "count", header: "Samples", render: (s) => <span>{s.count}</span> },
    { key: "avg", header: "Average (h)", render: (s) => <span>{s.avg_hours !== null ? s.avg_hours.toFixed(1) : "-"}</span> },
    { key: "p50", header: "p50 (h)", render: (s) => <span>{s.p50_hours !== null ? s.p50_hours.toFixed(1) : "-"}</span> },
    { key: "p90", header: "p90 (h)", render: (s) => <span>{s.p90_hours !== null ? s.p90_hours.toFixed(1) : "-"}</span> },
  ];

  const kpi = (label: string, value: string | number) => (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <span className="text-xs font-medium text-slate-500">{label}</span>
      <p className="mt-2 text-2xl font-bold text-slate-900">{loading ? "-" : value}</p>
    </div>
  );

  return (
    <ProtectedRoute requiredPermissions={["analytics:read"]} requiredRoles={["ADMIN", "SUPPLY_CHAIN_MANAGER", "ANALYST"]}>
      <AppLayout>
        <div className="space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <BarChart2 className="h-5 w-5 text-indigo-600" />
                <h1 className="text-2xl font-bold tracking-tight text-slate-900">Analytics</h1>
              </div>
              <p className="text-xs sm:text-sm text-slate-500 mt-1">
                Network-wide computed metrics across inventory, shipments, suppliers, and lifecycle bottlenecks
              </p>
            </div>
            <button
              onClick={loadAnalytics}
              disabled={loading}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3.5 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 shadow-sm disabled:opacity-50"
            >
              <RefreshCw className="h-4 w-4 text-slate-500" />
              Refresh
            </button>
          </div>

          {feedback && (
            <FeedbackAlert type={feedback.type} message={feedback.message} onDismiss={() => setFeedback(null)} />
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
            {kpi("Products", overview?.product_count ?? 0)}
            {kpi("Total Stock", Number(overview?.total_stock ?? 0).toLocaleString())}
            {kpi("Low Stock", overview?.low_stock_count ?? 0)}
            {kpi("Active Orders", overview?.active_orders_count ?? 0)}
            {kpi("In Transit", overview?.in_transit_shipments_count ?? 0)}
            {kpi("Delayed", overview?.delayed_shipments_count ?? 0)}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
              <div className="border-b border-slate-100 px-6 py-4">
                <h2 className="text-sm font-semibold text-slate-900">Stock by Warehouse</h2>
              </div>
              <div className="p-6">
                {!inventory?.by_warehouse || inventory.by_warehouse.length === 0 ? (
                  <p className="text-xs text-slate-500 text-center py-6">No inventory data</p>
                ) : (
                  <div className="space-y-4">
                    {inventory.by_warehouse.map((wh) => (
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
                              width: `${Math.min(100, ((Number(wh.total_quantity) || 0) / (inventory.total_inventory || 1)) * 100)}%`,
                            }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
              <div className="border-b border-slate-100 px-6 py-4">
                <h2 className="text-sm font-semibold text-slate-900">Shipment Performance</h2>
              </div>
              <div className="p-6 grid grid-cols-2 gap-4">
                <div className="rounded-lg bg-slate-50 p-4 border border-slate-100">
                  <span className="text-xs text-slate-500">Delivered</span>
                  <p className="mt-1 text-xl font-bold text-slate-900">{shipments?.delivered_count ?? 0}</p>
                  <span className="text-[11px] text-emerald-600">{shipments?.on_time_count ?? 0} on time</span>
                </div>
                <div className="rounded-lg bg-slate-50 p-4 border border-slate-100">
                  <span className="text-xs text-slate-500">Delayed</span>
                  <p className="mt-1 text-xl font-bold text-red-600">{shipments?.delayed_count ?? 0}</p>
                </div>
                <div className="rounded-lg bg-slate-50 p-4 border border-slate-100">
                  <span className="text-xs text-slate-500">Avg Delivery</span>
                  <p className="mt-1 text-xl font-bold text-slate-900">
                    {shipments?.avg_delivery_hours !== null && shipments?.avg_delivery_hours !== undefined
                      ? `${shipments.avg_delivery_hours.toFixed(1)} hrs`
                      : "N/A"}
                  </p>
                </div>
                <div className="rounded-lg bg-slate-50 p-4 border border-slate-100">
                  <span className="text-xs text-slate-500">Avg Delay</span>
                  <p className="mt-1 text-xl font-bold text-amber-600">
                    {shipments?.avg_delay_hours !== null && shipments?.avg_delay_hours !== undefined
                      ? `${shipments.avg_delay_hours.toFixed(1)} hrs`
                      : "0.0 hrs"}
                  </p>
                </div>
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
            <div className="border-b border-slate-100 px-6 py-4">
              <h2 className="text-sm font-semibold text-slate-900">Supplier Activity</h2>
            </div>
            <div className="p-6">
              {!suppliers?.suppliers || suppliers.suppliers.length === 0 ? (
                <p className="text-xs text-slate-500 text-center py-6">No suppliers registered</p>
              ) : (
                <div className="divide-y divide-slate-100">
                  {suppliers.suppliers.map((sup) => (
                    <div key={sup.supplier_id} className="py-2.5 flex items-center justify-between text-xs">
                      <div>
                        <p className="font-medium text-slate-900">{sup.supplier_name}</p>
                        <p className="text-[11px] text-slate-400">Code: {sup.supplier_code}</p>
                      </div>
                      <div className="text-right">
                        <span className="font-semibold text-slate-700">{sup.total_orders ?? 0} orders</span>
                        {sup.performance_score !== null && sup.performance_score !== undefined && (
                          <p className="text-[11px] text-emerald-600 font-medium">Score: {sup.performance_score}%</p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
            <div className="border-b border-slate-100 px-6 py-4">
              <h2 className="text-sm font-semibold text-slate-900">Lifecycle Bottleneck Timing</h2>
            </div>
            <DataTable
              columns={bottleneckColumns}
              data={(bottlenecks?.stages || []).map((s, i) => ({ ...s, id: `stage-${i}` }))}
              isLoading={loading}
              emptyMessage="Insufficient lifecycle history to calculate stage bottlenecks."
            />
          </div>
        </div>
      </AppLayout>
    </ProtectedRoute>
  );
}
