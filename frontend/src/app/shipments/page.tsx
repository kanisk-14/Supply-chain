"use client";

import React, { useEffect, useState, useCallback } from "react";
import ProtectedRoute from "@/components/auth/ProtectedRoute";
import AppLayout from "@/components/common/AppLayout";
import DataTable, { Column } from "@/components/common/DataTable";
import Modal from "@/components/common/Modal";
import StatusBadge from "@/components/common/StatusBadge";
import FeedbackAlert from "@/components/common/FeedbackAlert";
import { useAuth } from "@/context/AuthContext";
import { shipmentsApi, ordersApi } from "@/lib/api";
import { Shipment, Order, PaginationMeta, ShipmentStatus } from "@/types/api";
import { useRouter } from "next/navigation";
import { Truck, Plus, Filter, AlertTriangle } from "lucide-react";

export default function ShipmentsPage() {
  const router = useRouter();
  const { hasPermission } = useAuth();
  const canWriteShipments = hasPermission("shipments:write");

  const [shipments, setShipments] = useState<Shipment[]>([]);
  const [meta, setMeta] = useState<PaginationMeta>({ page: 1, limit: 10, total: 0, pages: 1 });
  const [loading, setLoading] = useState(true);

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [delayedOnly, setDelayedOnly] = useState<boolean>(false);

  // Create Shipment Modal
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [confirmedOrders, setConfirmedOrders] = useState<Order[]>([]);
  const [selectedOrderId, setSelectedOrderId] = useState<string>("");
  const [expectedDelivery, setExpectedDelivery] = useState<string>("");
  const [createLoading, setCreateLoading] = useState(false);

  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string; details?: any } | null>(null);

  const loadShipments = useCallback(async (page = 1, limit = 10) => {
    setLoading(true);
    try {
      const res = await shipmentsApi.list({
        page,
        limit,
        status: statusFilter || undefined,
        is_delayed: delayedOnly || undefined,
      });
      setShipments(res.data || []);
      setMeta(res.meta);
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message || "Failed to load shipments" });
    } finally {
      setLoading(false);
    }
  }, [statusFilter, delayedOnly]);

  useEffect(() => {
    loadShipments(1, meta.limit);
  }, [loadShipments, meta.limit]);

  const loadConfirmedOrders = async () => {
    try {
      const res = await ordersApi.list({ status: "CONFIRMED", limit: 100 });
      setConfirmedOrders(res.data || []);
    } catch (err) {
      console.error("Failed to load confirmed orders:", err);
    }
  };

  const handleOpenCreateModal = () => {
    loadConfirmedOrders();
    setSelectedOrderId("");
    setExpectedDelivery("");
    setCreateModalOpen(true);
  };

  const handleCreateShipment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedOrderId) {
      setFeedback({ type: "error", message: "Please select an order." });
      return;
    }

    setCreateLoading(true);
    setFeedback(null);
    try {
      const newShipment = await shipmentsApi.create({
        order_id: Number(selectedOrderId),
        expected_delivery_at: expectedDelivery ? new Date(expectedDelivery).toISOString() : null,
      });
      setFeedback({
        type: "success",
        message: `Shipment ${newShipment.shipment_number} created successfully.`,
      });
      setCreateModalOpen(false);
      loadShipments(1, meta.limit);
    } catch (err: any) {
      setFeedback({
        type: "error",
        message: err.message || "Failed to create shipment",
        details: err.details,
      });
    } finally {
      setCreateLoading(false);
    }
  };

  const columns: Column<Shipment>[] = [
    {
      key: "shipment_number",
      header: "Shipment #",
      render: (s) => (
        <span className="font-semibold text-indigo-600 font-mono hover:underline">
          {s.shipment_number}
        </span>
      ),
    },
    {
      key: "order_id",
      header: "Order #",
      render: (s) => <span className="font-mono text-slate-700">Order #{s.order_id}</span>,
    },
    {
      key: "status",
      header: "Status",
      render: (s) => (
        <div className="flex items-center gap-2">
          <StatusBadge status={s.status} />
          {s.is_delayed && <StatusBadge isDelayed={true} />}
        </div>
      ),
    },
    {
      key: "expected_delivery_at",
      header: "Expected Delivery",
      render: (s) => (
        <span className="text-xs text-slate-600">
          {s.expected_delivery_at ? new Date(s.expected_delivery_at).toLocaleString() : "Not set"}
        </span>
      ),
    },
    {
      key: "actual_delivery_at",
      header: "Actual Delivery",
      render: (s) => (
        <span className="text-xs text-slate-600">
          {s.actual_delivery_at ? new Date(s.actual_delivery_at).toLocaleString() : "-"}
        </span>
      ),
    },
    {
      key: "created_at",
      header: "Created",
      render: (s) => (
        <span className="text-xs text-slate-400">
          {new Date(s.created_at).toLocaleDateString()}
        </span>
      ),
    },
  ];

  return (
    <ProtectedRoute requiredPermissions={["shipments:read"]}>
      <AppLayout>
        <div className="space-y-6">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-slate-900">
                Shipment Tracking
              </h1>
              <p className="text-xs sm:text-sm text-slate-500 mt-1">
                Monitor fulfillment transitions (Packed → In Transit → Delivered) and track delivery delays
              </p>
            </div>
            {canWriteShipments && (
              <button
                onClick={handleOpenCreateModal}
                className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3.5 py-2 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700"
              >
                <Plus className="h-4 w-4" /> Create Shipment
              </button>
            )}
          </div>

          {feedback && (
            <FeedbackAlert
              type={feedback.type}
              message={feedback.message}
              details={feedback.details}
              onDismiss={() => setFeedback(null)}
            />
          )}

          {/* Filters Bar */}
          <div className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
            <div className="flex items-center gap-1 text-slate-400">
              <Filter className="h-4 w-4" />
              <span className="text-xs font-medium text-slate-700">Status:</span>
            </div>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="rounded-md border border-slate-300 py-1.5 px-2.5 text-xs bg-white text-slate-700 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              <option value="">All Statuses</option>
              <option value="PACKED">PACKED</option>
              <option value="IN_TRANSIT">IN_TRANSIT</option>
              <option value="DELIVERED">DELIVERED</option>
            </select>

            <label className="flex items-center gap-1.5 text-xs text-slate-700 cursor-pointer ml-3">
              <input
                type="checkbox"
                checked={delayedOnly}
                onChange={(e) => setDelayedOnly(e.target.checked)}
                className="rounded border-slate-300 text-red-600 focus:ring-red-500"
              />
              Delayed Only
            </label>

            {(statusFilter || delayedOnly) && (
              <button
                onClick={() => {
                  setStatusFilter("");
                  setDelayedOnly(false);
                }}
                className="text-xs text-indigo-600 hover:text-indigo-800 ml-auto"
              >
                Reset filters
              </button>
            )}
          </div>

          {/* Table */}
          <DataTable
            columns={columns}
            data={shipments}
            isLoading={loading}
            meta={meta}
            onPageChange={(p) => loadShipments(p, meta.limit)}
            onLimitChange={(l) => loadShipments(1, l)}
            onRowClick={(s) => router.push(`/shipments/${s.id}`)}
            emptyMessage="No shipments found."
          />

          {/* Create Shipment Modal */}
          <Modal
            isOpen={createModalOpen}
            onClose={() => setCreateModalOpen(false)}
            title="Create Shipment for Confirmed Order"
          >
            <form onSubmit={handleCreateShipment} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700">
                  Select Confirmed Order *
                </label>
                <select
                  required
                  value={selectedOrderId}
                  onChange={(e) => setSelectedOrderId(e.target.value)}
                  className="mt-1 block w-full rounded-md border border-slate-300 p-2 text-xs bg-white text-slate-700 focus:border-indigo-500 focus:outline-none"
                >
                  <option value="">Select an order</option>
                  {confirmedOrders.map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.order_number} ({o.items?.length || 0} line items)
                    </option>
                  ))}
                </select>
                {confirmedOrders.length === 0 && (
                  <span className="text-[11px] text-amber-600 mt-1 block">
                    No CONFIRMED orders available. Only confirmed orders can have shipments created.
                  </span>
                )}
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700">
                  Expected Delivery Date & Time (Optional)
                </label>
                <input
                  type="datetime-local"
                  value={expectedDelivery}
                  onChange={(e) => setExpectedDelivery(e.target.value)}
                  className="mt-1 block w-full rounded-md border border-slate-300 p-2 text-xs text-slate-700 focus:border-indigo-500 focus:outline-none"
                />
              </div>

              <div className="mt-6 flex justify-end gap-2 border-t border-slate-100 pt-4">
                <button
                  type="button"
                  onClick={() => setCreateModalOpen(false)}
                  className="rounded-md border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createLoading || confirmedOrders.length === 0}
                  className="rounded-md bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  {createLoading ? "Creating..." : "Create Shipment"}
                </button>
              </div>
            </form>
          </Modal>
        </div>
      </AppLayout>
    </ProtectedRoute>
  );
}

