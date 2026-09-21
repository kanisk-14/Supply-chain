"use client";

import React, { useEffect, useState, useCallback } from "react";
import ProtectedRoute from "@/components/auth/ProtectedRoute";
import AppLayout from "@/components/common/AppLayout";
import DataTable, { Column } from "@/components/common/DataTable";
import Modal from "@/components/common/Modal";
import FeedbackAlert from "@/components/common/FeedbackAlert";
import { useAuth } from "@/context/AuthContext";
import {
  inventoryApi,
  productsApi,
  warehousesApi,
} from "@/lib/api";
import {
  InventoryItem,
  InventoryTransaction,
  Product,
  Warehouse,
  PaginationMeta,
} from "@/types/api";
import {
  ArrowDownUp,
  ArrowRightLeft,
  Filter,
  History,
  Boxes,
  AlertTriangle,
} from "lucide-react";

export default function InventoryPage() {
  const { hasPermission } = useAuth();
  const canWriteInventory = hasPermission("inventory:write");
  // WAREHOUSE_MANAGER lacks products:read and ANALYST lacks both master-data
  // reads: only request dropdown data the role is authorized for so the page
  // never fires requests that 403.
  const canReadProducts = hasPermission("products:read");
  const canReadTransactions = hasPermission("inventory:transactions:read");
  const canReadWarehouses = hasPermission("warehouses:read");

  const [activeTab, setActiveTab] = useState<"stock" | "transactions">("stock");

  // Stock State
  const [inventory, setInventory] = useState<InventoryItem[]>([]);
  const [stockMeta, setStockMeta] = useState<PaginationMeta>({ page: 1, limit: 10, total: 0, pages: 1 });
  const [stockLoading, setStockLoading] = useState(true);

  // Filters for stock
  const [filterProductId, setFilterProductId] = useState<string>("");
  const [filterWarehouseId, setFilterWarehouseId] = useState<string>("");
  const [filterBelowThreshold, setFilterBelowThreshold] = useState<boolean>(false);

  // Transactions State
  const [transactions, setTransactions] = useState<InventoryTransaction[]>([]);
  const [txMeta, setTxMeta] = useState<PaginationMeta>({ page: 1, limit: 10, total: 0, pages: 1 });
  const [txLoading, setTxLoading] = useState(false);
  const [txTypeFilter, setTxTypeFilter] = useState<string>("");

  // Master Data Cache for dropdowns
  const [products, setProducts] = useState<Product[]>([]);
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);

  // Modals
  const [adjustModalOpen, setAdjustModalOpen] = useState(false);
  const [transferModalOpen, setTransferModalOpen] = useState(false);

  // Form states
  const [adjustForm, setAdjustForm] = useState({
    product_id: "",
    warehouse_id: "",
    delta: "",
    reason: "",
  });
  const [transferForm, setTransferForm] = useState({
    product_id: "",
    from_warehouse_id: "",
    to_warehouse_id: "",
    quantity: "",
  });

  const [actionLoading, setActionLoading] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string; details?: any } | null>(null);

  const fetchProductsAndWarehouses = async () => {
    try {
      const [prodRes, whRes] = await Promise.all([
        canReadProducts
          ? productsApi.list({ limit: 100 })
          : Promise.resolve({ data: [] as Product[] }),
        canReadWarehouses
          ? warehousesApi.list({ limit: 100 })
          : Promise.resolve({ data: [] as Warehouse[] }),
      ]);
      setProducts(prodRes.data || []);
      setWarehouses(whRes.data || []);
    } catch (err) {
      console.error("Failed to load products/warehouses:", err);
    }
  };

  const loadStock = useCallback(async (page = 1, limit = 10) => {
    setStockLoading(true);
    try {
      const res = await inventoryApi.list({
        page,
        limit,
        product_id: filterProductId ? Number(filterProductId) : undefined,
        warehouse_id: filterWarehouseId ? Number(filterWarehouseId) : undefined,
        below_threshold: filterBelowThreshold || undefined,
      });
      setInventory(res.data || []);
      setStockMeta(res.meta);
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message || "Failed to load inventory" });
    } finally {
      setStockLoading(false);
    }
  }, [filterProductId, filterWarehouseId, filterBelowThreshold]);

  const loadTransactions = useCallback(async (page = 1, limit = 10) => {
    setTxLoading(true);
    try {
      const res = await inventoryApi.transactions({
        page,
        limit,
        product_id: filterProductId ? Number(filterProductId) : undefined,
        warehouse_id: filterWarehouseId ? Number(filterWarehouseId) : undefined,
        type: txTypeFilter || undefined,
      });
      setTransactions(res.data || []);
      setTxMeta(res.meta);
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message || "Failed to load transactions" });
    } finally {
      setTxLoading(false);
    }
  }, [filterProductId, filterWarehouseId, txTypeFilter]);

  useEffect(() => {
    fetchProductsAndWarehouses();
  }, []);

  useEffect(() => {
    if (activeTab === "transactions" && canReadTransactions) {
      loadTransactions(1, txMeta.limit);
    } else {
      loadStock(1, stockMeta.limit);
    }
  }, [activeTab, canReadTransactions, loadStock, loadTransactions, stockMeta.limit, txMeta.limit]);

  // Adjust Form Submit
  const handleAdjustSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!adjustForm.product_id || !adjustForm.warehouse_id || !adjustForm.delta) {
      setFeedback({ type: "error", message: "Please fill in all required fields." });
      return;
    }

    const deltaNum = Number(adjustForm.delta);
    if (isNaN(deltaNum) || deltaNum === 0) {
      setFeedback({ type: "error", message: "Delta must be a non-zero number." });
      return;
    }

    setActionLoading(true);
    setFeedback(null);
    try {
      await inventoryApi.adjust({
        product_id: Number(adjustForm.product_id),
        warehouse_id: Number(adjustForm.warehouse_id),
        delta: deltaNum,
        reason: adjustForm.reason || undefined,
      });
      setFeedback({ type: "success", message: "Stock successfully adjusted." });
      setAdjustModalOpen(false);
      setAdjustForm({ product_id: "", warehouse_id: "", delta: "", reason: "" });
      loadStock(stockMeta.page, stockMeta.limit);
    } catch (err: any) {
      setFeedback({
        type: "error",
        message: err.message || "Failed to adjust stock",
        details: err.details,
      });
    } finally {
      setActionLoading(false);
    }
  };

  // Transfer Form Submit
  const handleTransferSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (
      !transferForm.product_id ||
      !transferForm.from_warehouse_id ||
      !transferForm.to_warehouse_id ||
      !transferForm.quantity
    ) {
      setFeedback({ type: "error", message: "Please fill in all required fields." });
      return;
    }

    if (transferForm.from_warehouse_id === transferForm.to_warehouse_id) {
      setFeedback({
        type: "error",
        message: "Source and destination warehouses cannot be the same.",
      });
      return;
    }

    const qty = Number(transferForm.quantity);
    if (isNaN(qty) || qty <= 0) {
      setFeedback({ type: "error", message: "Transfer quantity must be greater than zero." });
      return;
    }

    setActionLoading(true);
    setFeedback(null);
    try {
      await inventoryApi.transfer({
        product_id: Number(transferForm.product_id),
        from_warehouse_id: Number(transferForm.from_warehouse_id),
        to_warehouse_id: Number(transferForm.to_warehouse_id),
        quantity: qty,
      });
      setFeedback({ type: "success", message: "Stock successfully transferred." });
      setTransferModalOpen(false);
      setTransferForm({
        product_id: "",
        from_warehouse_id: "",
        to_warehouse_id: "",
        quantity: "",
      });
      loadStock(stockMeta.page, stockMeta.limit);
    } catch (err: any) {
      setFeedback({
        type: "error",
        message: err.message || "Failed to transfer stock",
        details: err.details,
      });
    } finally {
      setActionLoading(false);
    }
  };

  // Stock Columns
  const stockColumns: Column<InventoryItem>[] = [
    {
      key: "product",
      header: "Product / SKU",
      render: (item) => {
        const prod = item.product || products.find((p) => p.id === item.product_id);
        return (
          <div>
            <p className="font-semibold text-slate-900">{prod?.name || `Product #${item.product_id}`}</p>
            <span className="text-xs text-slate-500 font-mono">{prod?.sku || "SKU N/A"}</span>
          </div>
        );
      },
    },
    {
      key: "warehouse",
      header: "Warehouse",
      render: (item) => {
        const wh = item.warehouse || warehouses.find((w) => w.id === item.warehouse_id);
        return (
          <div>
            <p className="text-slate-800 font-medium">{wh?.name || `Warehouse #${item.warehouse_id}`}</p>
            <span className="text-xs text-slate-400 font-mono">{wh?.code}</span>
          </div>
        );
      },
    },
    {
      key: "quantity",
      header: "Quantity On Hand",
      render: (item) => {
        const prod = item.product || products.find((p) => p.id === item.product_id);
        const threshold = Number(prod?.reorder_threshold ?? 0);
        const qty = Number(item.quantity);
        const isBelow = qty < threshold;

        return (
          <div className="flex items-center gap-2">
            <span className={`font-semibold ${isBelow ? "text-amber-600" : "text-slate-900"}`}>
              {qty.toLocaleString()} {prod?.unit || "units"}
            </span>
            {isBelow && (
              <span className="inline-flex items-center gap-1 rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 border border-amber-200">
                <AlertTriangle className="h-3 w-3" /> Low Stock
              </span>
            )}
          </div>
        );
      },
    },
    {
      key: "threshold",
      header: "Reorder Threshold",
      render: (item) => {
        const prod = item.product || products.find((p) => p.id === item.product_id);
        return <span>{prod ? `${Number(prod.reorder_threshold).toLocaleString()} ${prod.unit}` : "-"}</span>;
      },
    },
    {
      key: "updated_at",
      header: "Last Updated",
      render: (item) => (
        <span className="text-xs text-slate-500">
          {new Date(item.updated_at).toLocaleString()}
        </span>
      ),
    },
  ];

  // Transaction Columns
  const txColumns: Column<InventoryTransaction>[] = [
    {
      key: "created_at",
      header: "Timestamp",
      render: (tx) => (
        <span className="text-xs text-slate-500 font-mono">
          {new Date(tx.created_at).toLocaleString()}
        </span>
      ),
    },
    {
      key: "type",
      header: "Type",
      render: (tx) => {
        const colors: Record<string, string> = {
          ADJUSTMENT: "bg-purple-50 text-purple-700 border-purple-200",
          TRANSFER_IN: "bg-emerald-50 text-emerald-700 border-emerald-200",
          TRANSFER_OUT: "bg-amber-50 text-amber-700 border-amber-200",
          DISPATCH: "bg-blue-50 text-blue-700 border-blue-200",
        };
        return (
          <span className={`inline-block px-2 py-0.5 text-[10px] font-bold rounded border uppercase ${colors[tx.type] || "bg-slate-100"}`}>
            {tx.type.replace(/_/g, " ")}
          </span>
        );
      },
    },
    {
      key: "delta",
      header: "Delta",
      render: (tx) => {
        const num = Number(tx.delta);
        return (
          <span className={`font-mono font-semibold ${num >= 0 ? "text-emerald-600" : "text-red-600"}`}>
            {num > 0 ? `+${num}` : num}
          </span>
        );
      },
    },
    {
      key: "product",
      header: "Product",
      render: (tx) => {
        const prod = tx.product || products.find((p) => p.id === tx.product_id);
        return <span className="font-medium text-slate-800">{prod?.name || `#${tx.product_id}`}</span>;
      },
    },
    {
      key: "warehouse",
      header: "Warehouse",
      render: (tx) => {
        const wh = tx.warehouse || warehouses.find((w) => w.id === tx.warehouse_id);
        return <span>{wh?.name || `#${tx.warehouse_id}`}</span>;
      },
    },
    {
      key: "reason",
      header: "Reason / Reference",
      render: (tx) => (
        <div className="text-xs">
          <p className="text-slate-700">{tx.reason || "-"}</p>
          {tx.reference_id && (
            <span className="text-[10px] text-slate-400 font-mono">Ref ID: {tx.reference_id}</span>
          )}
        </div>
      ),
    },
  ];

  return (
    <ProtectedRoute requiredPermissions={["inventory:read"]}>
      <AppLayout>
        <div className="space-y-6">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-slate-900">
                Inventory Management
              </h1>
              <p className="text-xs sm:text-sm text-slate-500 mt-1">
                Monitor real-time warehouse stock, record adjustments, and coordinate inter-facility transfers
              </p>
            </div>
            {canWriteInventory && (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setAdjustModalOpen(true)}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 shadow-sm"
                >
                  <ArrowDownUp className="h-3.5 w-3.5" /> Adjust Stock
                </button>
                <button
                  onClick={() => setTransferModalOpen(true)}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-2 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700"
                >
                  <ArrowRightLeft className="h-3.5 w-3.5" /> Transfer Stock
                </button>
              </div>
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

          {/* Tab Selection */}
          <div className="flex items-center border-b border-slate-200">
            <button
              onClick={() => setActiveTab("stock")}
              className={`flex items-center gap-2 px-4 py-3 text-xs font-medium border-b-2 transition-colors ${
                activeTab === "stock"
                  ? "border-indigo-600 text-indigo-600 font-semibold"
                  : "border-transparent text-slate-500 hover:text-slate-700"
              }`}
            >
              <Boxes className="h-4 w-4" /> Current Warehouse Stock
            </button>
            {canReadTransactions && (
            <button
              onClick={() => setActiveTab("transactions")}
              className={`flex items-center gap-2 px-4 py-3 text-xs font-medium border-b-2 transition-colors ${
                activeTab === "transactions"
                  ? "border-indigo-600 text-indigo-600 font-semibold"
                  : "border-transparent text-slate-500 hover:text-slate-700"
              }`}
            >
              <History className="h-4 w-4" /> Stock Movement History
            </button>
            )}
          </div>

          {/* Filters Bar */}
          <div className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
            <div className="flex items-center gap-1 text-slate-400">
              <Filter className="h-4 w-4" />
              <span className="text-xs font-medium text-slate-700">Filters:</span>
            </div>

            <select
              value={filterProductId}
              onChange={(e) => setFilterProductId(e.target.value)}
              className="rounded-md border border-slate-300 py-1.5 px-2.5 text-xs bg-white text-slate-700 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              <option value="">All Products</option>
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.sku} - {p.name}
                </option>
              ))}
            </select>

            <select
              value={filterWarehouseId}
              onChange={(e) => setFilterWarehouseId(e.target.value)}
              className="rounded-md border border-slate-300 py-1.5 px-2.5 text-xs bg-white text-slate-700 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              <option value="">All Warehouses</option>
              {warehouses.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.code} - {w.name}
                </option>
              ))}
            </select>

            {activeTab === "stock" && (
              <label className="flex items-center gap-1.5 text-xs text-slate-700 cursor-pointer ml-2">
                <input
                  type="checkbox"
                  checked={filterBelowThreshold}
                  onChange={(e) => setFilterBelowThreshold(e.target.checked)}
                  className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                />
                Below Reorder Threshold Only
              </label>
            )}

            {activeTab === "transactions" && (
              <select
                value={txTypeFilter}
                onChange={(e) => setTxTypeFilter(e.target.value)}
                className="rounded-md border border-slate-300 py-1.5 px-2.5 text-xs bg-white text-slate-700 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              >
                <option value="">All Transaction Types</option>
                <option value="ADJUSTMENT">ADJUSTMENT</option>
                <option value="TRANSFER_IN">TRANSFER_IN</option>
                <option value="TRANSFER_OUT">TRANSFER_OUT</option>
                <option value="DISPATCH">DISPATCH</option>
              </select>
            )}

            {(filterProductId || filterWarehouseId || filterBelowThreshold || txTypeFilter) && (
              <button
                onClick={() => {
                  setFilterProductId("");
                  setFilterWarehouseId("");
                  setFilterBelowThreshold(false);
                  setTxTypeFilter("");
                }}
                className="text-xs text-indigo-600 hover:text-indigo-800 ml-auto"
              >
                Reset filters
              </button>
            )}
          </div>

          {/* Table Display */}
          {activeTab === "transactions" && canReadTransactions ? (
            <DataTable
              columns={txColumns}
              data={transactions}
              isLoading={txLoading}
              meta={txMeta}
              onPageChange={(p) => loadTransactions(p, txMeta.limit)}
              onLimitChange={(l) => loadTransactions(1, l)}
              emptyMessage="No stock transactions found."
            />
          ) : (
            <DataTable
              columns={stockColumns}
              data={inventory}
              isLoading={stockLoading}
              meta={stockMeta}
              onPageChange={(p) => loadStock(p, stockMeta.limit)}
              onLimitChange={(l) => loadStock(1, l)}
              emptyMessage="No inventory matches the selected criteria."
            />
          )}

          {/* Adjust Modal */}
          <Modal
            isOpen={adjustModalOpen}
            onClose={() => setAdjustModalOpen(false)}
            title="Adjust Warehouse Stock"
          >
            <form onSubmit={handleAdjustSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700">Product *</label>
                <select
                  required
                  value={adjustForm.product_id}
                  onChange={(e) => setAdjustForm({ ...adjustForm, product_id: e.target.value })}
                  className="mt-1 block w-full rounded-md border border-slate-300 p-2 text-sm bg-white text-slate-700 focus:border-indigo-500 focus:outline-none"
                >
                  <option value="">Select a product</option>
                  {products.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.sku} - {p.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700">Warehouse *</label>
                <select
                  required
                  value={adjustForm.warehouse_id}
                  onChange={(e) => setAdjustForm({ ...adjustForm, warehouse_id: e.target.value })}
                  className="mt-1 block w-full rounded-md border border-slate-300 p-2 text-sm bg-white text-slate-700 focus:border-indigo-500 focus:outline-none"
                >
                  <option value="">Select a warehouse</option>
                  {warehouses.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.code} - {w.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700">
                  Delta (Signed Number, e.g. +50 or -15) *
                </label>
                <input
                  type="number"
                  step="any"
                  required
                  value={adjustForm.delta}
                  onChange={(e) => setAdjustForm({ ...adjustForm, delta: e.target.value })}
                  placeholder="e.g. 50 or -20"
                  className="mt-1 block w-full rounded-md border border-slate-300 p-2 text-sm text-slate-700 focus:border-indigo-500 focus:outline-none"
                />
                <span className="text-[11px] text-slate-500">
                  Negative values deduct stock and require sufficient available inventory.
                </span>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700">Reason</label>
                <input
                  type="text"
                  value={adjustForm.reason}
                  onChange={(e) => setAdjustForm({ ...adjustForm, reason: e.target.value })}
                  placeholder="e.g. Cycle count adjustment"
                  className="mt-1 block w-full rounded-md border border-slate-300 p-2 text-sm text-slate-700 focus:border-indigo-500 focus:outline-none"
                />
              </div>

              <div className="mt-6 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setAdjustModalOpen(false)}
                  className="rounded-md border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading}
                  className="rounded-md bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  {actionLoading ? "Adjusting..." : "Submit Adjustment"}
                </button>
              </div>
            </form>
          </Modal>

          {/* Transfer Modal */}
          <Modal
            isOpen={transferModalOpen}
            onClose={() => setTransferModalOpen(false)}
            title="Transfer Stock Between Warehouses"
          >
            <form onSubmit={handleTransferSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700">Product *</label>
                <select
                  required
                  value={transferForm.product_id}
                  onChange={(e) => setTransferForm({ ...transferForm, product_id: e.target.value })}
                  className="mt-1 block w-full rounded-md border border-slate-300 p-2 text-sm bg-white text-slate-700 focus:border-indigo-500 focus:outline-none"
                >
                  <option value="">Select a product</option>
                  {products.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.sku} - {p.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-700">Source Warehouse *</label>
                  <select
                    required
                    value={transferForm.from_warehouse_id}
                    onChange={(e) => setTransferForm({ ...transferForm, from_warehouse_id: e.target.value })}
                    className="mt-1 block w-full rounded-md border border-slate-300 p-2 text-sm bg-white text-slate-700 focus:border-indigo-500 focus:outline-none"
                  >
                    <option value="">Select source</option>
                    {warehouses.map((w) => (
                      <option key={w.id} value={w.id}>
                        {w.code} - {w.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700">Destination Warehouse *</label>
                  <select
                    required
                    value={transferForm.to_warehouse_id}
                    onChange={(e) => setTransferForm({ ...transferForm, to_warehouse_id: e.target.value })}
                    className="mt-1 block w-full rounded-md border border-slate-300 p-2 text-sm bg-white text-slate-700 focus:border-indigo-500 focus:outline-none"
                  >
                    <option value="">Select destination</option>
                    {warehouses.map((w) => (
                      <option key={w.id} value={w.id}>
                        {w.code} - {w.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700">Transfer Quantity *</label>
                <input
                  type="number"
                  step="any"
                  min="0.001"
                  required
                  value={transferForm.quantity}
                  onChange={(e) => setTransferForm({ ...transferForm, quantity: e.target.value })}
                  placeholder="e.g. 50"
                  className="mt-1 block w-full rounded-md border border-slate-300 p-2 text-sm text-slate-700 focus:border-indigo-500 focus:outline-none"
                />
              </div>

              <div className="mt-6 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setTransferModalOpen(false)}
                  className="rounded-md border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading}
                  className="rounded-md bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  {actionLoading ? "Transferring..." : "Execute Transfer"}
                </button>
              </div>
            </form>
          </Modal>
        </div>
      </AppLayout>
    </ProtectedRoute>
  );
}

