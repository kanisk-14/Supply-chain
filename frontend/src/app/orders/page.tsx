"use client";

import React, { useEffect, useState, useCallback } from "react";
import ProtectedRoute from "@/components/auth/ProtectedRoute";
import AppLayout from "@/components/common/AppLayout";
import DataTable, { Column } from "@/components/common/DataTable";
import Modal from "@/components/common/Modal";
import StatusBadge from "@/components/common/StatusBadge";
import FeedbackAlert from "@/components/common/FeedbackAlert";
import { useAuth } from "@/context/AuthContext";
import { ordersApi, productsApi } from "@/lib/api";
import { Order, Product, PaginationMeta, OrderStatus } from "@/types/api";
import { useRouter } from "next/navigation";
import { ShoppingCart, Plus, Filter, Trash2 } from "lucide-react";

export default function OrdersPage() {
  const router = useRouter();
  const { hasPermission } = useAuth();
  const canWriteOrders = hasPermission("orders:write");

  const [orders, setOrders] = useState<Order[]>([]);
  const [meta, setMeta] = useState<PaginationMeta>({ page: 1, limit: 10, total: 0, pages: 1 });
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>("");

  // Create Order Modal
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [products, setProducts] = useState<Product[]>([]);
  const [lineItems, setLineItems] = useState<Array<{ product_id: string; quantity: string }>>([
    { product_id: "", quantity: "1" },
  ]);
  const [createLoading, setCreateLoading] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string; details?: any } | null>(null);

  const loadOrders = useCallback(async (page = 1, limit = 10) => {
    setLoading(true);
    try {
      const res = await ordersApi.list({
        page,
        limit,
        status: statusFilter || undefined,
        include_shipments: true,
      });
      setOrders(res.data || []);
      setMeta(res.meta);
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message || "Failed to load orders" });
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    loadOrders(1, meta.limit);
  }, [loadOrders, meta.limit]);

  const loadProducts = async () => {
    try {
      const res = await productsApi.list({ limit: 100, is_active: true });
      setProducts(res.data || []);
    } catch (err) {
      console.error("Failed to fetch products:", err);
    }
  };

  const handleOpenCreateModal = () => {
    loadProducts();
    setLineItems([{ product_id: "", quantity: "1" }]);
    setCreateModalOpen(true);
  };

  const handleAddLineItem = () => {
    setLineItems([...lineItems, { product_id: "", quantity: "1" }]);
  };

  const handleRemoveLineItem = (index: number) => {
    if (lineItems.length === 1) return;
    setLineItems(lineItems.filter((_, i) => i !== index));
  };

  const handleLineItemChange = (index: number, field: "product_id" | "quantity", value: string) => {
    const updated = [...lineItems];
    updated[index][field] = value;
    setLineItems(updated);
  };

  const handleCreateOrder = async (e: React.FormEvent) => {
    e.preventDefault();
    // Validate line items
    for (const item of lineItems) {
      if (!item.product_id || !item.quantity || Number(item.quantity) <= 0) {
        setFeedback({
          type: "error",
          message: "All line items must have a valid product and a quantity greater than 0.",
        });
        return;
      }
    }

    // Check for duplicate products
    const productIds = lineItems.map((i) => i.product_id);
    if (new Set(productIds).size !== productIds.length) {
      setFeedback({
        type: "error",
        message: "Duplicate products found in line items. Each product must be unique per order.",
      });
      return;
    }

    setCreateLoading(true);
    setFeedback(null);

    try {
      const newOrder = await ordersApi.create({
        items: lineItems.map((item) => ({
          product_id: Number(item.product_id),
          quantity: Number(item.quantity),
        })),
      });
      setFeedback({ type: "success", message: `Order ${newOrder.order_number} created successfully!` });
      setCreateModalOpen(false);
      loadOrders(1, meta.limit);
    } catch (err: any) {
      setFeedback({
        type: "error",
        message: err.message || "Failed to create order",
        details: err.details,
      });
    } finally {
      setCreateLoading(false);
    }
  };

  const columns: Column<Order>[] = [
    {
      key: "order_number",
      header: "Order Number",
      render: (order) => (
        <span className="font-semibold text-indigo-600 font-mono hover:underline">
          {order.order_number}
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      render: (order) => <StatusBadge status={order.status} />,
    },
    {
      key: "items",
      header: "Line Items",
      render: (order) => {
        const count = order.items?.length || 0;
        return (
          <span className="text-slate-700">
            {count} {count === 1 ? "item" : "items"}
          </span>
        );
      },
    },
    {
      key: "created_at",
      header: "Created At",
      render: (order) => (
        <span className="text-xs text-slate-500">
          {new Date(order.created_at).toLocaleString()}
        </span>
      ),
    },
    {
      key: "created_by",
      header: "Created By",
      render: (order) => (
        <span className="text-xs text-slate-500 font-mono">User #{order.created_by}</span>
      ),
    },
  ];

  return (
    <ProtectedRoute requiredPermissions={["orders:read"]}>
      <AppLayout>
        <div className="space-y-6">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-slate-900">
                Purchase Orders
              </h1>
              <p className="text-xs sm:text-sm text-slate-500 mt-1">
                Manage order lifecycles (Placed → Confirmed → Fulfilled / Cancelled)
              </p>
            </div>
            {canWriteOrders && (
              <button
                onClick={handleOpenCreateModal}
                className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3.5 py-2 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700"
              >
                <Plus className="h-4 w-4" /> New Order
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

          {/* Filters */}
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
              <option value="PLACED">PLACED</option>
              <option value="CONFIRMED">CONFIRMED</option>
              <option value="FULFILLED">FULFILLED</option>
              <option value="CANCELLED">CANCELLED</option>
            </select>
            {statusFilter && (
              <button
                onClick={() => setStatusFilter("")}
                className="text-xs text-indigo-600 hover:text-indigo-800 ml-auto"
              >
                Reset filter
              </button>
            )}
          </div>

          {/* Table */}
          <DataTable
            columns={columns}
            data={orders}
            isLoading={loading}
            meta={meta}
            onPageChange={(p) => loadOrders(p, meta.limit)}
            onLimitChange={(l) => loadOrders(1, l)}
            onRowClick={(order) => router.push(`/orders/${order.id}`)}
            emptyMessage="No orders found."
          />

          {/* Create Order Modal */}
          <Modal
            isOpen={createModalOpen}
            onClose={() => setCreateModalOpen(false)}
            title="Create New Order"
            maxWidth="xl"
          >
            <form onSubmit={handleCreateOrder} className="space-y-4">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-semibold text-slate-700 uppercase tracking-wider">
                    Order Items *
                  </label>
                  <button
                    type="button"
                    onClick={handleAddLineItem}
                    className="inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:text-indigo-700"
                  >
                    <Plus className="h-3.5 w-3.5" /> Add line
                  </button>
                </div>

                <div className="space-y-3 max-h-64 overflow-y-auto pr-1">
                  {lineItems.map((item, idx) => (
                    <div key={idx} className="flex items-center gap-3">
                      <div className="flex-1">
                        <select
                          required
                          value={item.product_id}
                          onChange={(e) => handleLineItemChange(idx, "product_id", e.target.value)}
                          className="w-full rounded-md border border-slate-300 p-2 text-xs bg-white text-slate-700 focus:border-indigo-500 focus:outline-none"
                        >
                          <option value="">Select product</option>
                          {products.map((p) => (
                            <option key={p.id} value={p.id}>
                              {p.sku} - {p.name}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="w-28">
                        <input
                          type="number"
                          step="any"
                          min="1"
                          required
                          value={item.quantity}
                          onChange={(e) => handleLineItemChange(idx, "quantity", e.target.value)}
                          placeholder="Qty"
                          className="w-full rounded-md border border-slate-300 p-2 text-xs text-slate-700 focus:border-indigo-500 focus:outline-none"
                        />
                      </div>
                      <button
                        type="button"
                        disabled={lineItems.length === 1}
                        onClick={() => handleRemoveLineItem(idx)}
                        className="rounded p-1 text-slate-400 hover:text-red-600 disabled:opacity-30 disabled:hover:text-slate-400"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                </div>
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
                  disabled={createLoading}
                  className="rounded-md bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  {createLoading ? "Creating..." : "Submit Order"}
                </button>
              </div>
            </form>
          </Modal>
        </div>
      </AppLayout>
    </ProtectedRoute>
  );
}

