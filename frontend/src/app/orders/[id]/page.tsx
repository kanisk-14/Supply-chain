"use client";

import React, { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import ProtectedRoute from "@/components/auth/ProtectedRoute";
import AppLayout from "@/components/common/AppLayout";
import StatusBadge from "@/components/common/StatusBadge";
import FeedbackAlert from "@/components/common/FeedbackAlert";
import Modal from "@/components/common/Modal";
import { useAuth } from "@/context/AuthContext";
import { ordersApi, shipmentsApi } from "@/lib/api";
import { Order, Shipment } from "@/types/api";
import Link from "next/link";
import {
  ArrowLeft,
  CheckCircle,
  XCircle,
  PackageCheck,
  Truck,
  Plus,
} from "lucide-react";

export default function OrderDetailsPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { hasPermission } = useAuth();
  const canWriteOrders = hasPermission("orders:write");
  const canWriteShipments = hasPermission("shipments:write");

  const [order, setOrder] = useState<Order | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string; details?: any } | null>(null);

  // Create Shipment Modal
  const [shipmentModalOpen, setShipmentModalOpen] = useState(false);
  const [expectedDelivery, setExpectedDelivery] = useState("");

  const loadOrder = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const data = await ordersApi.get(Number(id), true);
      setOrder(data);
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message || "Failed to load order" });
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    loadOrder();
  }, [loadOrder]);

  const handleConfirm = async () => {
    if (!order) return;
    setActionLoading(true);
    setFeedback(null);
    try {
      const updated = await ordersApi.confirm(order.id);
      setOrder(updated);
      setFeedback({ type: "success", message: "Order confirmed successfully." });
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message || "Failed to confirm order", details: err.details });
    } finally {
      setActionLoading(false);
    }
  };

  const handleFulfill = async () => {
    if (!order) return;
    setActionLoading(true);
    setFeedback(null);
    try {
      const updated = await ordersApi.fulfill(order.id);
      setOrder(updated);
      setFeedback({ type: "success", message: "Order marked as fulfilled." });
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message || "Failed to fulfill order", details: err.details });
    } finally {
      setActionLoading(false);
    }
  };

  const handleCancel = async () => {
    if (!order) return;
    if (!confirm("Are you sure you want to cancel this order?")) return;
    setActionLoading(true);
    setFeedback(null);
    try {
      const updated = await ordersApi.cancel(order.id);
      setOrder(updated);
      setFeedback({ type: "success", message: "Order has been cancelled." });
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message || "Failed to cancel order", details: err.details });
    } finally {
      setActionLoading(false);
    }
  };

  const handleCreateShipment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!order) return;
    setActionLoading(true);
    setFeedback(null);
    try {
      const newShipment = await shipmentsApi.create({
        order_id: order.id,
        expected_delivery_at: expectedDelivery ? new Date(expectedDelivery).toISOString() : null,
      });
      setFeedback({
        type: "success",
        message: `Shipment ${newShipment.shipment_number} created successfully!`,
      });
      setShipmentModalOpen(false);
      setExpectedDelivery("");
      loadOrder();
    } catch (err: any) {
      setFeedback({
        type: "error",
        message: err.message || "Failed to create shipment",
        details: err.details,
      });
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <ProtectedRoute requiredPermissions={["orders:read"]}>
        <AppLayout>
          <div className="flex h-64 items-center justify-center">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-600 border-t-transparent" />
          </div>
        </AppLayout>
      </ProtectedRoute>
    );
  }

  if (!order) {
    return (
      <ProtectedRoute requiredPermissions={["orders:read"]}>
        <AppLayout>
          <div className="text-center py-12">
            <p className="text-sm font-semibold text-slate-700">Order not found.</p>
            <Link
              href="/orders"
              className="mt-4 inline-flex items-center gap-1 text-xs text-indigo-600 hover:underline"
            >
              <ArrowLeft className="h-4 w-4" /> Back to orders
            </Link>
          </div>
        </AppLayout>
      </ProtectedRoute>
    );
  }

  return (
    <ProtectedRoute requiredPermissions={["orders:read"]}>
      <AppLayout>
        <div className="space-y-6">
          {/* Top Bar */}
          <div>
            <Link
              href="/orders"
              className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-slate-800 mb-3"
            >
              <ArrowLeft className="h-3.5 w-3.5" /> Back to orders
            </Link>
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <div className="flex items-center gap-3">
                <h1 className="text-2xl font-bold tracking-tight text-slate-900 font-mono">
                  {order.order_number}
                </h1>
                <StatusBadge status={order.status} />
              </div>

              {/* Action Buttons */}
              {canWriteOrders && (
                <div className="flex flex-wrap items-center gap-2">
                  {order.status === "PLACED" && (
                    <>
                      <button
                        onClick={handleConfirm}
                        disabled={actionLoading}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-2 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700 disabled:opacity-50"
                      >
                        <CheckCircle className="h-4 w-4" /> Confirm Order
                      </button>
                      <button
                        onClick={handleCancel}
                        disabled={actionLoading}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-red-200 bg-white px-3 py-2 text-xs font-medium text-red-600 shadow-sm hover:bg-red-50 disabled:opacity-50"
                      >
                        <XCircle className="h-4 w-4" /> Cancel Order
                      </button>
                    </>
                  )}

                  {order.status === "CONFIRMED" && (
                    <>
                      {canWriteShipments && (
                        <button
                          onClick={() => setShipmentModalOpen(true)}
                          disabled={actionLoading}
                          className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-2 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700 disabled:opacity-50"
                        >
                          <Truck className="h-4 w-4" /> Create Shipment
                        </button>
                      )}
                      <button
                        onClick={handleFulfill}
                        disabled={actionLoading}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-2 text-xs font-semibold text-white shadow-sm hover:bg-emerald-700 disabled:opacity-50"
                      >
                        <PackageCheck className="h-4 w-4" /> Fulfill Order
                      </button>
                      <button
                        onClick={handleCancel}
                        disabled={actionLoading}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-red-200 bg-white px-3 py-2 text-xs font-medium text-red-600 shadow-sm hover:bg-red-50 disabled:opacity-50"
                      >
                        <XCircle className="h-4 w-4" /> Cancel Order
                      </button>
                    </>
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

          {/* Details Card */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
            <div>
              <span className="text-xs text-slate-500">Order ID</span>
              <p className="mt-1 text-sm font-semibold text-slate-900 font-mono">#{order.id}</p>
            </div>
            <div>
              <span className="text-xs text-slate-500">Created At</span>
              <p className="mt-1 text-sm font-semibold text-slate-900">
                {new Date(order.created_at).toLocaleString()}
              </p>
            </div>
            <div>
              <span className="text-xs text-slate-500">Created By User</span>
              <p className="mt-1 text-sm font-semibold text-slate-900 font-mono">
                User #{order.created_by}
              </p>
            </div>
          </div>

          {/* Line Items Table */}
          <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
            <div className="border-b border-slate-100 px-6 py-4">
              <h2 className="text-sm font-semibold text-slate-900">Line Items</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-left text-xs text-slate-600">
                <thead className="bg-slate-50 uppercase text-[10px] tracking-wider text-slate-500 font-semibold">
                  <tr>
                    <th className="px-6 py-3">Product Name</th>
                    <th className="px-6 py-3">SKU</th>
                    <th className="px-6 py-3">Quantity</th>
                    <th className="px-6 py-3">Unit</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {order.items.map((item, idx) => (
                    <tr key={idx} className="hover:bg-slate-50">
                      <td className="px-6 py-3.5 font-medium text-slate-900">
                        {item.product?.name || `Product #${item.product_id}`}
                      </td>
                      <td className="px-6 py-3.5 font-mono text-slate-500">
                        {item.product?.sku || "-"}
                      </td>
                      <td className="px-6 py-3.5 font-semibold text-slate-800">
                        {Number(item.quantity).toLocaleString()}
                      </td>
                      <td className="px-6 py-3.5 text-slate-500">{item.product?.unit || "units"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Associated Shipments */}
          <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
            <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
              <h2 className="text-sm font-semibold text-slate-900">Associated Shipments</h2>
              {canWriteShipments && order.status === "CONFIRMED" && (
                <button
                  onClick={() => setShipmentModalOpen(true)}
                  className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-600 hover:text-indigo-700"
                >
                  <Plus className="h-3.5 w-3.5" /> New Shipment
                </button>
              )}
            </div>
            <div className="p-6">
              {!order.shipments || order.shipments.length === 0 ? (
                <p className="text-xs text-slate-500 text-center py-4">
                  No shipments created for this order yet.
                </p>
              ) : (
                <div className="divide-y divide-slate-100">
                  {order.shipments.map((shipment) => (
                    <div
                      key={shipment.id}
                      className="py-3 flex items-center justify-between hover:bg-slate-50 px-2 rounded-lg"
                    >
                      <div className="space-y-1">
                        <Link
                          href={`/shipments/${shipment.id}`}
                          className="font-mono text-xs font-semibold text-indigo-600 hover:underline"
                        >
                          {shipment.shipment_number}
                        </Link>
                        <p className="text-[11px] text-slate-400">
                          Created {new Date(shipment.created_at).toLocaleString()}
                        </p>
                      </div>
                      <div className="flex items-center gap-3">
                        <StatusBadge status={shipment.status} isDelayed={shipment.is_delayed} />
                        <Link
                          href={`/shipments/${shipment.id}`}
                          className="text-xs font-medium text-slate-600 hover:text-indigo-600"
                        >
                          View →
                        </Link>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Create Shipment Modal */}
          <Modal
            isOpen={shipmentModalOpen}
            onClose={() => setShipmentModalOpen(false)}
            title={`Create Shipment for Order ${order.order_number}`}
          >
            <form onSubmit={handleCreateShipment} className="space-y-4">
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
                <span className="text-[11px] text-slate-500">
                  Shipment will be created in PACKED status. Stock deduction occurs upon dispatch.
                </span>
              </div>

              <div className="mt-6 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShipmentModalOpen(false)}
                  className="rounded-md border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading}
                  className="rounded-md bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  {actionLoading ? "Creating..." : "Create Shipment"}
                </button>
              </div>
            </form>
          </Modal>
        </div>
      </AppLayout>
    </ProtectedRoute>
  );
}

