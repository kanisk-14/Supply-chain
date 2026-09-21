"use client";

import React, { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import ProtectedRoute from "@/components/auth/ProtectedRoute";
import AppLayout from "@/components/common/AppLayout";
import StatusBadge from "@/components/common/StatusBadge";
import FeedbackAlert from "@/components/common/FeedbackAlert";
import Modal from "@/components/common/Modal";
import { useAuth } from "@/context/AuthContext";
import { shipmentsApi, warehousesApi } from "@/lib/api";
import { Shipment, ShipmentStatusHistory, Warehouse } from "@/types/api";
import Link from "next/link";
import {
  ArrowLeft,
  Truck,
  CheckCircle2,
  Clock,
  Send,
  Package,
  Check,
} from "lucide-react";

export default function ShipmentDetailsPage() {
  const { id } = useParams<{ id: string }>();
  const { hasPermission } = useAuth();
  const canWriteShipments = hasPermission("shipments:write");
  // ANALYST can read shipments but not warehouses: only fetch the warehouse
  // list when permitted so the dropdown never produces a 403.
  const canReadWarehouses = hasPermission("warehouses:read");

  const [shipment, setShipment] = useState<Shipment | null>(null);
  const [history, setHistory] = useState<ShipmentStatusHistory[]>([]);
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string; details?: any } | null>(null);

  // Dispatch Modal
  const [dispatchModalOpen, setDispatchModalOpen] = useState(false);
  const [dispatchWarehouseId, setDispatchWarehouseId] = useState("");
  const [updatedExpectedDelivery, setUpdatedExpectedDelivery] = useState("");

  const loadShipmentAndHistory = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const [shipmentData, historyData, whData] = await Promise.all([
        shipmentsApi.get(Number(id)),
        shipmentsApi.history(Number(id)),
        canReadWarehouses
          ? warehousesApi.list({ limit: 100 })
          : Promise.resolve({ data: [] as Warehouse[] }),
      ]);
      setShipment(shipmentData);
      setHistory(historyData);
      setWarehouses(whData.data || []);
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message || "Failed to load shipment details" });
    } finally {
      setLoading(false);
    }
  }, [id, canReadWarehouses]);

  useEffect(() => {
    loadShipmentAndHistory();
  }, [loadShipmentAndHistory]);

  const handleDispatch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!shipment || !dispatchWarehouseId) {
      setFeedback({ type: "error", message: "Please select a fulfillment warehouse." });
      return;
    }

    setActionLoading(true);
    setFeedback(null);
    try {
      const updated = await shipmentsApi.dispatch(shipment.id, {
        warehouse_id: Number(dispatchWarehouseId),
        expected_delivery_at: updatedExpectedDelivery
          ? new Date(updatedExpectedDelivery).toISOString()
          : undefined,
      });
      setShipment(updated);
      setDispatchModalOpen(false);
      setFeedback({
        type: "success",
        message: "Shipment successfully dispatched. Inventory has been deducted from the chosen warehouse.",
      });
      loadShipmentAndHistory();
    } catch (err: any) {
      setFeedback({
        type: "error",
        message: err.message || "Failed to dispatch shipment",
        details: err.details,
      });
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeliver = async () => {
    if (!shipment) return;
    if (!confirm("Confirm delivery of this shipment?")) return;

    setActionLoading(true);
    setFeedback(null);
    try {
      const updated = await shipmentsApi.deliver(shipment.id);
      setShipment(updated);
      setFeedback({
        type: "success",
        message: "Shipment delivered. Related overdue alerts resolved.",
      });
      loadShipmentAndHistory();
    } catch (err: any) {
      setFeedback({
        type: "error",
        message: err.message || "Failed to deliver shipment",
        details: err.details,
      });
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <ProtectedRoute requiredPermissions={["shipments:read"]}>
        <AppLayout>
          <div className="flex h-64 items-center justify-center">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-600 border-t-transparent" />
          </div>
        </AppLayout>
      </ProtectedRoute>
    );
  }

  if (!shipment) {
    return (
      <ProtectedRoute requiredPermissions={["shipments:read"]}>
        <AppLayout>
          <div className="text-center py-12">
            <p className="text-sm font-semibold text-slate-700">Shipment not found.</p>
            <Link
              href="/shipments"
              className="mt-4 inline-flex items-center gap-1 text-xs text-indigo-600 hover:underline"
            >
              <ArrowLeft className="h-4 w-4" /> Back to shipments
            </Link>
          </div>
        </AppLayout>
      </ProtectedRoute>
    );
  }

  const stages = [
    { key: "PACKED", label: "Packed", icon: Package },
    { key: "IN_TRANSIT", label: "In Transit", icon: Truck },
    { key: "DELIVERED", label: "Delivered", icon: CheckCircle2 },
  ];

  const currentStageIndex = stages.findIndex((s) => s.key === shipment.status);

  return (
    <ProtectedRoute requiredPermissions={["shipments:read"]}>
      <AppLayout>
        <div className="space-y-6">
          {/* Top Bar */}
          <div>
            <Link
              href="/shipments"
              className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-slate-800 mb-3"
            >
              <ArrowLeft className="h-3.5 w-3.5" /> Back to shipments
            </Link>
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <div className="flex items-center gap-3">
                <h1 className="text-2xl font-bold tracking-tight text-slate-900 font-mono">
                  {shipment.shipment_number}
                </h1>
                <StatusBadge status={shipment.status} />
                {shipment.is_delayed && <StatusBadge isDelayed={true} />}
              </div>

              {/* State Machine Transition Actions */}
              {canWriteShipments && (
                <div className="flex items-center gap-2">
                  {shipment.status === "PACKED" && (
                    <button
                      onClick={() => setDispatchModalOpen(true)}
                      disabled={actionLoading}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3.5 py-2 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700 disabled:opacity-50"
                    >
                      <Send className="h-4 w-4" /> Dispatch Shipment
                    </button>
                  )}
                  {shipment.status === "IN_TRANSIT" && (
                    <button
                      onClick={handleDeliver}
                      disabled={actionLoading}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3.5 py-2 text-xs font-semibold text-white shadow-sm hover:bg-emerald-700 disabled:opacity-50"
                    >
                      <Check className="h-4 w-4" /> Mark as Delivered
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>

          {feedback && (
            <FeedbackAlert
              type={feedback.type}
              message={feedback.message}
              details={feedback.details}
              onDismiss={() => setFeedback(null)}
            />
          )}

          {/* Details Overview Card */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
            <div>
              <span className="text-xs text-slate-500">Linked Order</span>
              <p className="mt-1">
                <Link
                  href={`/orders/${shipment.order_id}`}
                  className="text-sm font-semibold text-indigo-600 font-mono hover:underline"
                >
                  Order #{shipment.order_id}
                </Link>
              </p>
            </div>
            <div>
              <span className="text-xs text-slate-500">Expected Delivery</span>
              <p className="mt-1 text-sm font-semibold text-slate-900">
                {shipment.expected_delivery_at
                  ? new Date(shipment.expected_delivery_at).toLocaleString()
                  : "Not specified"}
              </p>
            </div>
            <div>
              <span className="text-xs text-slate-500">Actual Delivery</span>
              <p className="mt-1 text-sm font-semibold text-slate-900">
                {shipment.actual_delivery_at
                  ? new Date(shipment.actual_delivery_at).toLocaleString()
                  : "In Progress"}
              </p>
            </div>
            <div>
              <span className="text-xs text-slate-500">Created At</span>
              <p className="mt-1 text-sm font-semibold text-slate-900">
                {new Date(shipment.created_at).toLocaleString()}
              </p>
            </div>
          </div>

          {/* Visual Status Progress Flow */}
          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-sm font-semibold text-slate-900 mb-6">Fulfillment Progress</h2>
            <div className="flex items-center justify-between max-w-2xl mx-auto relative">
              <div className="absolute top-5 left-8 right-8 h-0.5 bg-slate-200 -z-0" />
              <div
                className="absolute top-5 left-8 h-0.5 bg-indigo-600 transition-all duration-300 -z-0"
                style={{
                  width: `${(Math.max(0, currentStageIndex) / (stages.length - 1)) * 100}%`,
                }}
              />

              {stages.map((stage, idx) => {
                const Icon = stage.icon;
                const isPassed = idx < currentStageIndex;
                const isCurrent = idx === currentStageIndex;

                return (
                  <div key={stage.key} className="flex flex-col items-center relative z-10">
                    <div
                      className={`flex h-10 w-10 items-center justify-center rounded-full border-2 transition-all ${
                        isCurrent
                          ? "border-indigo-600 bg-indigo-600 text-white shadow-md ring-4 ring-indigo-50"
                          : isPassed
                          ? "border-indigo-600 bg-indigo-600 text-white"
                          : "border-slate-300 bg-white text-slate-400"
                      }`}
                    >
                      <Icon className="h-5 w-5" />
                    </div>
                    <span
                      className={`mt-2 text-xs font-medium ${
                        isCurrent || isPassed ? "text-slate-900 font-semibold" : "text-slate-400"
                      }`}
                    >
                      {stage.label}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Status Timeline History */}
          <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
            <div className="border-b border-slate-100 px-6 py-4">
              <h2 className="text-sm font-semibold text-slate-900">Status History Audit Trail</h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Append-only record of lifecycle transitions
              </p>
            </div>
            <div className="p-6">
              {history.length === 0 ? (
                <p className="text-xs text-slate-500 text-center py-4">No history records found.</p>
              ) : (
                <div className="relative border-l-2 border-slate-200 ml-4 space-y-6">
                  {history.map((entry) => (
                    <div key={entry.id} className="relative pl-6">
                      <div className="absolute -left-2 top-1.5 h-3.5 w-3.5 rounded-full border-2 border-white bg-indigo-600 shadow-sm" />
                      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1">
                        <div className="flex items-center gap-2">
                          <StatusBadge status={entry.status} size="sm" />
                          <span className="text-xs text-slate-500 font-mono">
                            Actor: User #{entry.changed_by}
                          </span>
                        </div>
                        <span className="text-xs text-slate-400">
                          {new Date(entry.changed_at).toLocaleString()}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Dispatch Modal */}
          <Modal
            isOpen={dispatchModalOpen}
            onClose={() => setDispatchModalOpen(false)}
            title="Dispatch Shipment"
          >
            <form onSubmit={handleDispatch} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700">
                  Fulfillment Warehouse *
                </label>
                <select
                  required
                  value={dispatchWarehouseId}
                  onChange={(e) => setDispatchWarehouseId(e.target.value)}
                  className="mt-1 block w-full rounded-md border border-slate-300 p-2 text-xs bg-white text-slate-700 focus:border-indigo-500 focus:outline-none"
                >
                  <option value="">Select fulfilling warehouse</option>
                  {warehouses.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.code} - {w.name}
                    </option>
                  ))}
                </select>
                <span className="text-[11px] text-slate-500 mt-1 block">
                  Items in the order will be deducted from this warehouse upon dispatch.
                </span>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700">
                  Update Expected Delivery (Optional)
                </label>
                <input
                  type="datetime-local"
                  value={updatedExpectedDelivery}
                  onChange={(e) => setUpdatedExpectedDelivery(e.target.value)}
                  className="mt-1 block w-full rounded-md border border-slate-300 p-2 text-xs text-slate-700 focus:border-indigo-500 focus:outline-none"
                />
              </div>

              <div className="mt-6 flex justify-end gap-2 border-t border-slate-100 pt-4">
                <button
                  type="button"
                  onClick={() => setDispatchModalOpen(false)}
                  className="rounded-md border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading}
                  className="rounded-md bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  {actionLoading ? "Dispatching..." : "Confirm Dispatch"}
                </button>
              </div>
            </form>
          </Modal>
        </div>
      </AppLayout>
    </ProtectedRoute>
  );
}

